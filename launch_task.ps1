$clientDir = Join-Path $env:LOCALAPPDATA 'Programs\RemoteXPTI'
$clientExe = Join-Path $clientDir 'RemoteXPTI.exe'
if (-not (Test-Path -LiteralPath $clientExe -PathType Leaf)) {
    throw "Instale a versao cliente antes de configurar a inicializacao: $clientExe"
}
$action = New-ScheduledTaskAction -Execute $clientExe -WorkingDirectory $clientDir
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
Register-ScheduledTask -TaskName 'LaunchRemoteModern' -Action $action -Settings $settings -Principal $principal -Force
Start-ScheduledTask -TaskName 'LaunchRemoteModern'
