Stop-Process -Name pythonw -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 600
$action = New-ScheduledTaskAction -Execute "C:\Windows\System32\cmd.exe" -Argument "/c C:\Users\XPTI\Documents\vscode\remoteXPTI\run_modern.bat" -WorkingDirectory "C:\Users\XPTI\Documents\vscode\remoteXPTI"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
Register-ScheduledTask -TaskName "LaunchRemoteModern" -Action $action -Settings $settings -Principal $principal -Force
Start-ScheduledTask -TaskName "LaunchRemoteModern"
Start-Sleep -Seconds 2
Get-Process pythonw, msedgewebview2 -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, MainWindowTitle
