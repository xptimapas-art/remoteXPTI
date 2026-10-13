param([string]$TestRoot, [string]$HelperPath)
$ErrorActionPreference = 'Stop'
$testPath = (Resolve-Path -LiteralPath $TestRoot).Path
if ([IO.Path]::GetFileName($testPath) -notlike 'remotexpti-test-*') { throw 'Pasta de fixture invalida.' }
. $HelperPath -JobPath unused

function Build-Fixture([string]$Destination, [string]$ClassName, [string]$Version) {
    $source = @"
using System;
using System.IO;
using System.Threading;
public class $ClassName {
    public static void Main(string[] args) {
        if (args.Length == 4) {
            File.WriteAllText(args[1], "{\"token\":\"" + args[3] + "\",\"version\":\"$Version\"}");
            Thread.Sleep(1500);
        }
    }
}
"@
    Add-Type -TypeDefinition $source -OutputAssembly $Destination -OutputType ConsoleApplication
}

foreach ($mode in @('success', 'rollback')) {
    $folder = Join-Path $testPath $mode
    $stage = Join-Path $folder 'stage'
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    $target = Join-Path $folder 'RemoteXPTI.exe'
    Build-Fixture $target ('Old' + $mode) 'old'
    $oldHash = Get-Sha256 $target
    $source = Join-Path $stage 'pending.exe'
    $version = if ($mode -eq 'success') { '99.1.8' } else { 'wrong-version' }
    Build-Fixture $source ('New' + $mode) $version
    $newHash = Get-Sha256 $source
    $job = @{ pid = 2147483647; target = $target; source = $source;
              backup = (Join-Path $folder 'RemoteXPTI.previous.exe'); token = ('a' * 64);
              receipt = (Join-Path $stage 'receipt.json'); result = (Join-Path $stage 'result.json');
              helper_ready = (Join-Path $stage 'helper-ready.json'); pending = (Join-Path $stage 'pending.json');
              version = '99.1.8'; sha256 = $newHash.ToLowerInvariant(); size = (Get-Item -LiteralPath $source).Length }
    $jobPath = Join-Path $stage 'job.json'
    Write-Json $jobPath $job
    Write-Json $job.pending @{ fixture = $true }
    Invoke-Update $jobPath
    $result = Get-Content -LiteralPath $job.result -Raw | ConvertFrom-Json
    if ($mode -eq 'success') {
        if ($result.status -ne 'success' -or (Get-Sha256 $target) -ne $newHash) { throw 'Instalacao de fixture falhou.' }
    } else {
        if ($result.status -ne 'failed' -or (Get-Sha256 $target) -ne $oldHash) { throw 'Rollback de fixture falhou.' }
    }
    if (Test-Path -LiteralPath $job.pending) { throw 'Estado pendente nao foi removido.' }
}
Start-Sleep -Seconds 2
Write-Output 'Helper: instalacao e rollback verificados com fixtures locais.'
