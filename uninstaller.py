"""
Módulo de Desinstalação Completa do RemoteXPTI.
Remove executáveis, dados criptografados, atalhos do Windows e credenciais salvas no Windows Credential Manager.
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path


class Uninstaller:
    @staticmethod
    def cleanup_windows_credentials():
        """Remove todas as credenciais TERMSRV salvas no Gerenciador de Credenciais do Windows."""
        try:
            res = subprocess.run(["cmdkey", "/list"], capture_output=True, text=True, errors="replace")
            for line in res.stdout.splitlines():
                if "TERMSRV/" in line:
                    target = line.split("TERMSRV/")[-1].strip()
                    if target:
                        # Executa duas vezes para remover tanto Tipo Senha do Domínio quanto Genérico
                        subprocess.run(f'cmdkey /delete:TERMSRV/{target}', shell=True, capture_output=True)
                        subprocess.run(f'cmdkey /delete:TERMSRV/{target}', shell=True, capture_output=True)
        except Exception as e:
            print(f"[Uninstaller] Erro ao limpar credenciais: {e}")

    @classmethod
    def execute_complete_uninstallation(cls):
        """
        Executa a desinstalação completa:
        1. Limpa credenciais do Windows.
        2. Gera e executa o script em segundo plano para apagar arquivos, pastas e atalhos.
        3. Encerra o processo atual.
        """
        # 1. Limpa credenciais do Windows antes de encerrar
        cls.cleanup_windows_credentials()

        current_exe = Path(sys.executable).resolve()
        app_dir = current_exe.parent

        local_appdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        default_install_dir = Path(local_appdata) / "Programs" / "RemoteXPTI"

        userprofile = os.environ.get("USERPROFILE", "")
        appdata = os.environ.get("APPDATA", "")

        desktop_candidates = [
            Path(userprofile) / "Desktop" / "RemoteXPTI.lnk",
            Path(userprofile) / "OneDrive" / "Desktop" / "RemoteXPTI.lnk",
            Path(userprofile) / "OneDrive" / "Área de Trabalho" / "RemoteXPTI.lnk",
            Path(userprofile) / "Área de Trabalho" / "RemoteXPTI.lnk",
        ]
        start_shortcut = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "RemoteXPTI.lnk"

        temp_dir = Path(tempfile.gettempdir())
        script_path = temp_dir / "remotexpti_uninstall.cmd"
        vbs_path = temp_dir / "remotexpti_uninst_run.vbs"

        del_desktop_lines = "\n".join(f'del /f /q "{str(p)}" >nul 2>&1' for p in desktop_candidates)

        cmd_content = f"""@echo off
chcp 65001 >nul
title Desinstalando RemoteXPTI...

:: 1. Aguarda o processo encerrar por completo
ping 127.0.0.1 -n 3 >nul
taskkill /f /im "{current_exe.name}" >nul 2>&1
taskkill /f /im "RemoteXPTI.exe" >nul 2>&1

:: 2. Remove atalhos da Area de Trabalho e Menu Iniciar
{del_desktop_lines}
del /f /q "{str(start_shortcut)}" >nul 2>&1

:: 3. Remove perfis temporarios e scripts em %TEMP%
del /f /q "%TEMP%\\remotexpti_*.rdp" >nul 2>&1
del /f /q "%TEMP%\\remote_*.rdp" >nul 2>&1
del /f /q "%TEMP%\\.pending_update*" >nul 2>&1
del /f /q "%TEMP%\\remotexpti_update.cmd" >nul 2>&1
del /f /q "%TEMP%\\remotexpti_run.vbs" >nul 2>&1

:: 4. Remove pasta padrao de instalacao se existir
if exist "{str(default_install_dir)}" (
    rmdir /s /q "{str(default_install_dir)}" >nul 2>&1
)

:: 5. Se o executavel rodava de outra pasta
del /f /q "{str(current_exe)}" >nul 2>&1
del /f /q "{str(app_dir / 'servers.json')}" >nul 2>&1
del /f /q "{str(app_dir / '.secret.key')}" >nul 2>&1
del /f /q "{str(app_dir / '.pending_update.exe')}" >nul 2>&1
del /f /q "{str(app_dir / '.pending_update.part')}" >nul 2>&1
rmdir /s /q "{str(app_dir / 'thumbnails')}" >nul 2>&1
rmdir /s /q "{str(app_dir / 'imagens')}" >nul 2>&1

:: 6. Exibe mensagem de conclusao
powershell.exe -NoProfile -WindowStyle Hidden -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('O RemoteXPTI, seus atalhos, configuracoes e credenciais foram completamente desinstalados do computador.', 'RemoteXPTI - Desinstalacao Concluida', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)"

:: 7. Autoexclui este script e o vbs
del /f /q "{str(vbs_path)}" >nul 2>&1
del "%~f0"
"""
        script_path.write_text(cmd_content, encoding="utf-8")

        vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd.exe /c """ & "{str(script_path)}" & """", 0, False
'''
        vbs_path.write_text(vbs_content, encoding="utf-8")

        try:
            subprocess.run(["wscript.exe", "//b", "//nologo", str(vbs_path)], timeout=5.0)
        except Exception:
            os.startfile(str(script_path))

        # Encerra o processo imediatamente
        os._exit(0)
