@echo off
set "clientApp=%LOCALAPPDATA%\Programs\RemoteXPTI\RemoteXPTI.exe"
if not exist "%clientApp%" (
    echo A versao cliente ainda nao esta instalada em "%clientApp%".
    pause
    exit /b 1
)
start "" /d "%LOCALAPPDATA%\Programs\RemoteXPTI" "%clientApp%"
