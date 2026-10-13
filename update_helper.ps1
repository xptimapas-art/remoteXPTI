param([Parameter(Mandatory = $true)][string]$JobPath)
$ErrorActionPreference = 'Stop'

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}

function Write-Json([string]$Path, $Data) {
    $temporary = $Path + '.tmp'
    $Data | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Invoke-Retry([scriptblock]$Operation) {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        try { & $Operation; return } catch {
            if ((Get-Date) -ge $deadline) { throw }
            Start-Sleep -Milliseconds 250
        }
    } while ($true)
}

function Invoke-Update([string]$Path) {
    $job = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    $stage = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Path))
    $target = [IO.Path]::GetFullPath($job.target)
    if ([IO.Path]::GetFileName($target) -ne 'RemoteXPTI.exe') { throw 'Executavel de destino invalido.' }
    if ($job.backup -ne [IO.Path]::Combine([IO.Path]::GetDirectoryName($target), 'RemoteXPTI.previous.exe')) {
        throw 'Caminho de backup invalido.'
    }
    foreach ($pair in @(@('source', 'pending.exe'), @('receipt', 'receipt.json'), @('result', 'result.json'),
                       @('pending', 'pending.json'), @('helper_ready', 'helper-ready.json'))) {
        if ($job.($pair[0]) -ne [IO.Path]::Combine($stage, $pair[1])) { throw 'Caminho de staging invalido.' }
    }
    if ($job.token -notmatch '^[0-9a-f]{64}$' -or $job.sha256 -notmatch '^[0-9a-f]{64}$') { throw 'Job invalido.' }
    $source = Get-Item -LiteralPath $job.source
    if ($source.Length -ne $job.size -or (Get-Sha256 $job.source) -ne $job.sha256) {
        throw 'A integridade do download mudou antes da instalacao.'
    }
    Write-Json $job.helper_ready @{ token = $job.token }
    $backedUp = $false
    $newProcess = $null
    try {
        # Espera o processo exato; rename com retry cobre o bootloader onefile.
        $oldProcess = Get-Process -Id $job.pid -ErrorAction SilentlyContinue
        if ($oldProcess -and -not $oldProcess.WaitForExit(30000)) { throw 'O aplicativo anterior nao encerrou.' }
        if (Test-Path -LiteralPath $job.backup) { Remove-Item -LiteralPath $job.backup -Force }
        Invoke-Retry { Move-Item -LiteralPath $job.target -Destination $job.backup }
        $backedUp = $true
        # Copy funciona mesmo quando AppData e pasta de instalacao estao em volumes diferentes.
        Invoke-Retry { Copy-Item -LiteralPath $job.source -Destination $job.target -Force }
        if ((Get-Sha256 $job.target) -ne $job.sha256) {
            throw 'A copia instalada nao corresponde ao download.'
        }
        $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
        $arguments = '--update-receipt "' + $job.receipt + '" --update-token ' + $job.token
        $newProcess = Start-Process -FilePath $job.target -ArgumentList $arguments -WorkingDirectory ([IO.Path]::GetDirectoryName($target)) -PassThru
        $deadline = (Get-Date).AddSeconds(90)
        $healthy = $false
        do {
            if (Test-Path -LiteralPath $job.receipt) {
                try { $receipt = Get-Content -LiteralPath $job.receipt -Raw -Encoding UTF8 | ConvertFrom-Json }
                catch { $receipt = $null }  # Aguarda uma escrita concorrente terminar.
                if ($receipt.token -eq $job.token -and $receipt.version -eq $job.version) { $healthy = $true; break }
                if ($receipt.token -eq $job.token -and $receipt.version -ne $job.version) {
                    throw 'A versao iniciada difere da release solicitada.'
                }
            }
            if ($newProcess.HasExited) { throw 'A nova versao encerrou antes de confirmar inicializacao.' }
            Start-Sleep -Milliseconds 250
        } while ((Get-Date) -lt $deadline)
        if (-not $healthy) { throw 'A nova interface nao confirmou inicializacao em 90 segundos.' }
        Write-Json $job.result @{ status = 'success'; version = $job.version; message = 'Atualizacao instalada.' }
        if (Test-Path -LiteralPath $job.pending) { Remove-Item -LiteralPath $job.pending }
    } catch {
        $message = $_.Exception.Message
        if ($newProcess -and -not $newProcess.HasExited) {
            # Somente a arvore do processo que este helper iniciou.
            & "$env:SystemRoot\System32\taskkill.exe" /PID $newProcess.Id /T /F | Out-Null
            $newProcess.WaitForExit(10000) | Out-Null
        }
        $restored = $false
        if ($backedUp) {
            try {
                Invoke-Retry {
                    if (Test-Path -LiteralPath $job.target) { Remove-Item -LiteralPath $job.target -Force }
                    Move-Item -LiteralPath $job.backup -Destination $job.target
                }
                $restored = $true
            } catch { $message += ' Falha ao restaurar backup: ' + $_.Exception.Message }
        }
        Write-Json $job.result @{ status = 'failed'; version = $job.version; message = $message }
        if (Test-Path -LiteralPath $job.pending) { Remove-Item -LiteralPath $job.pending }
        if ($restored) {
            Start-Process -FilePath $job.target -WorkingDirectory ([IO.Path]::GetDirectoryName($target))
        }
    }
}

# Dot-source disponibiliza as funcoes para testes sem executar uma instalacao.
if ($MyInvocation.InvocationName -ne '.') { Invoke-Update $JobPath }
