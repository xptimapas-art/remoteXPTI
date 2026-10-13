$launcherPath = Join-Path $PSScriptRoot 'run_modern.bat'
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\cmd.exe" -Argument ('/c "' + $launcherPath + '"') -WorkingDirectory $PSScriptRoot
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
Register-ScheduledTask -TaskName 'LaunchRemoteModern' -Action $action -Settings $settings -Principal $principal -Force
Start-ScheduledTask -TaskName 'LaunchRemoteModern'
