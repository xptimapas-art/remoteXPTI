"""
Módulo de Desinstalação Completa do RemoteXPTI.
Remove executáveis, dados criptografados, atalhos do Windows e credenciais salvas no Windows Credential Manager.
Executa tudo 100% de forma silenciosa sem janelas de CMD piscando na tela.
"""

import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path


class Uninstaller:
    @staticmethod
    def cleanup_windows_credentials():
        """Remove todas as credenciais TERMSRV salvas no Gerenciador de Credenciais do Windows sem abrir janelas CMD."""
        creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        try:
            res = subprocess.run(
                ["cmdkey", "/list"],
                capture_output=True,
                text=True,
                errors="replace",
                creationflags=creation_flags
            )
            for line in res.stdout.splitlines():
                if "TERMSRV/" in line:
                    target = line.split("TERMSRV/")[-1].strip()
                    if target:
                        # Executa duas vezes para remover tanto Tipo Senha do Domínio quanto Genérico sem shell=True
                        subprocess.run(
                            ["cmdkey", f"/delete:TERMSRV/{target}"],
                            capture_output=True,
                            creationflags=creation_flags
                        )
                        subprocess.run(
                            ["cmdkey", f"/delete:TERMSRV/{target}"],
                            capture_output=True,
                            creationflags=creation_flags
                        )
        except Exception as e:
            print(f"[Uninstaller] Erro ao limpar credenciais: {e}")

    @staticmethod
    def remove_shortcuts():
        """Remove atalhos da Área de Trabalho (local e OneDrive) e do Menu Iniciar de forma nativa e silenciosa."""
        userprofile = os.environ.get("USERPROFILE", str(Path.home()))
        appdata = os.environ.get("APPDATA", "")

        candidates = [
            Path(userprofile) / "Desktop" / "RemoteXPTI.lnk",
            Path(userprofile) / "OneDrive" / "Desktop" / "RemoteXPTI.lnk",
            Path(userprofile) / "OneDrive" / "Área de Trabalho" / "RemoteXPTI.lnk",
            Path(userprofile) / "Área de Trabalho" / "RemoteXPTI.lnk",
            Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "RemoteXPTI.lnk",
        ]
        for p in candidates:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

    @staticmethod
    def remove_data_and_temp_files():
        """Remove perfis temporários RDP, arquivos de cache, miniaturas e configurações."""
        # 1. Limpa perfis temporários RDP e scripts no %TEMP%
        temp_dir = Path(tempfile.gettempdir())
        temp_patterns = [
            "remotexpti_*.rdp",
            "remote_*.rdp",
            ".pending_update*",
            "remotexpti_update.*",
            "remotexpti_run.*",
            "remotexpti_uninstall.*",
            "remotexpti_uninst_run.*"
        ]
        for pat in temp_patterns:
            for f in temp_dir.glob(pat):
                try:
                    f.unlink()
                except Exception:
                    pass

        # 2. Limpa dados locais da pasta da aplicação
        current_exe = Path(sys.executable).resolve()
        app_dir = current_exe.parent

        files_to_remove = [
            "servers.json",
            ".secret.key",
            ".pending_update.exe",
            ".pending_update.part",
            "version_app.txt",
            "version_setup.txt"
        ]
        for f_name in files_to_remove:
            f = app_dir / f_name
            try:
                if f.exists():
                    f.unlink()
            except Exception:
                pass

        dirs_to_remove = ["thumbnails", "imagens"]
        for d_name in dirs_to_remove:
            d = app_dir / d_name
            if d.exists() and d.is_dir():
                try:
                    shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass

    @classmethod
    def finalize_self_delete_and_exit(cls):
        """
        Inicia a exclusão do executável principal e pasta de instalação via PowerShell 100% oculto,
        e encerra o processo imediatamente sem abrir nenhuma janela preta de CMD.
        """
        current_exe = Path(sys.executable).resolve()
        local_appdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        default_install_dir = Path(local_appdata) / "Programs" / "RemoteXPTI"

        creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        ps_cmd = f"""
        Start-Sleep -Seconds 1
        Remove-Item -Path '{str(current_exe)}' -Force -ErrorAction SilentlyContinue
        if (Test-Path '{str(default_install_dir)}') {{
            Remove-Item -Path '{str(default_install_dir)}' -Recurse -Force -ErrorAction SilentlyContinue
        }}
        """
        try:
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-WindowStyle", "Hidden",
                    "-ExecutionPolicy", "Bypass",
                    "-Command", ps_cmd
                ],
                creationflags=creation_flags
            )
        except Exception:
            pass

        os._exit(0)

    @classmethod
    def execute_complete_uninstallation(cls):
        """Execução direta completa e 100% silenciosa (para uso sem interface gráfica)."""
        cls.cleanup_windows_credentials()
        cls.remove_shortcuts()
        cls.remove_data_and_temp_files()
        cls.finalize_self_delete_and_exit()
