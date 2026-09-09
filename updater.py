import os
import sys
import json
import urllib.request
import urllib.error
import threading
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Callable
import customtkinter as ctk
from version import APP_NAME, CURRENT_VERSION, GITHUB_REPO

def parse_version(v_str: str) -> Tuple[int, ...]:
    """Converte 'v1.2.3' ou '1.2.3' em tupla comparável (1, 2, 3)."""
    clean = v_str.strip().lstrip("v").lstrip("V")
    parts = []
    for piece in clean.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


class SilentAutoUpdater:
    """
    Sistema de atualização em segundo plano estilo Antigravity/Chrome/VS Code:
    1. Checa a versão silenciosamente no GitHub Releases.
    2. Se houver versão nova, inicia o download em segundo plano sem travar nada.
    3. Quando o download termina, avisa o usuário e oferece o botão para Reiniciar.
    4. Ao reiniciar, substitui o executável e abre o novo aplicativo.
    """

    def __init__(
        self,
        on_ready_callback: Optional[Callable[[str], None]] = None,
        on_status_callback: Optional[Callable[[str], None]] = None
    ):
        self.on_ready_callback = on_ready_callback
        self.on_status_callback = on_status_callback
        self.is_checking = False
        self.is_downloading = False
        self.update_ready = False
        self.new_version = ""
        self.downloaded_file: Optional[Path] = None

    def notify_status(self, msg: str):
        if self.on_status_callback:
            self.on_status_callback(msg)

    def start_background_check(self, is_manual: bool = False):
        """Inicia a verificação e download automático em background."""
        if self.update_ready:
            if is_manual:
                self.notify_status(f"🚀 Versão v{self.new_version} já está baixada e pronta!")
            return

        if self.is_downloading:
            if is_manual:
                self.notify_status(f"⬇️ Baixando nova versão v{self.new_version} em segundo plano...")
            return

        if self.is_checking:
            if is_manual:
                self.notify_status("🔍 Verificação já em andamento...")
            return

        threading.Thread(target=self._worker, args=(is_manual,), daemon=True).start()

    def _get_latest_release_info(self) -> Tuple[str, str]:
        """
        Retorna (tag_name, download_url) da versao mais recente.
        Prioriza o redirecionamento web oficial do GitHub para NAO consumir a cota de 60 req/h da API.
        Se falhar, faz fallback para a API JSON.
        """
        tag_name = ""
        download_url = ""

        # Metodo 1: Redirecionamento Web (Sem limite de taxa de 60 req/h da API)
        try:
            web_url = f"https://github.com/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(
                web_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                final_url = resp.geturl()
                if "/releases/tag/" in final_url:
                    tag_name = final_url.split("/releases/tag/")[-1].split("/")[0].strip()
                    download_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag_name}/{APP_NAME}.exe"
                    return tag_name, download_url
        except Exception as e:
            print(f"[SilentUpdater] Metodo web indisponivel: {e}")

        # Metodo 2: Fallback para API REST do GitHub
        try:
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(
                api_url,
                headers={
                    "User-Agent": f"{APP_NAME}-SilentUpdater",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    tag_name = data.get("tag_name", "").strip()
                    for asset in data.get("assets", []):
                        name = asset.get("name", "")
                        if name.lower().endswith(".exe") and "setup" not in name.lower():
                            download_url = asset.get("browser_download_url", "")
                            break
                    if not download_url and data.get("assets"):
                        download_url = data["assets"][0].get("browser_download_url", "")
                    return tag_name, download_url
        except Exception as e:
            print(f"[SilentUpdater] Fallback API GitHub indisponivel: {e}")

        return tag_name, download_url

    def _worker(self, is_manual: bool = False):
        self.is_checking = True
        if is_manual:
            self.notify_status("🔍 Verificando atualizações no GitHub...")

        try:
            tag_name, download_url = self._get_latest_release_info()
            if not tag_name:
                if is_manual:
                    self.notify_status("⚠️ Servidor de atualizações indisponível.")
                return

            remote_ver = parse_version(tag_name)
            local_ver = parse_version(CURRENT_VERSION)

            if remote_ver <= local_ver:
                # Já está na versão mais recente
                if is_manual:
                    self.notify_status(f"✅ Você já está na versão mais recente (v{CURRENT_VERSION})!")
                return

            self.new_version = tag_name.lstrip("v").lstrip("V")
            if is_manual:
                self.notify_status(f"⬇️ Nova versão v{self.new_version} encontrada! Baixando em segundo plano...")

            if not download_url:
                if is_manual:
                    self.notify_status("⚠️ Arquivo da atualização não encontrado nos lançamentos.")
                return

            # Inicia o download silencioso em segundo plano
            self._download_update_silent(download_url)

        except Exception as e:
            # Falhas de rede em background não interrompem o uso do usuário
            print(f"[SilentUpdater] Verificação de atualização: {e}")
            if is_manual:
                self.notify_status("⚠️ Não foi possível verificar atualizações no momento.")
        finally:
            self.is_checking = False

    def _download_update_silent(self, download_url: str):
        self.is_downloading = True
        try:
            # Determina o diretório base da aplicação
            if getattr(sys, "frozen", False):
                app_dir = Path(sys.executable).parent
            else:
                app_dir = Path(__file__).parent.resolve()

            temp_part = app_dir / ".pending_update.part"
            temp_dest = app_dir / ".pending_update.exe"

            if temp_part.exists():
                try:
                    temp_part.unlink()
                except Exception:
                    pass

            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=60.0) as response:
                block_size = 65536
                with open(temp_part, "wb") as out_file:
                    while True:
                        buf = response.read(block_size)
                        if not buf:
                            break
                        out_file.write(buf)

            # Download concluído com sucesso e verificado (> 5MB)
            if temp_part.exists() and temp_part.stat().st_size > 5000000:
                if temp_dest.exists():
                    try:
                        temp_dest.unlink()
                    except Exception:
                        pass
                temp_part.replace(temp_dest)
                self.downloaded_file = temp_dest
                self.update_ready = True
                print(f"[SilentUpdater] Nova versão {self.new_version} baixada e pronta!")

                if self.on_ready_callback:
                    self.on_ready_callback(self.new_version)
            else:
                print("[SilentUpdater] Arquivo baixado incompleto ou corrompido.")

        except Exception as e:
            print(f"[SilentUpdater] Erro no download em background: {e}")
        finally:
            self.is_downloading = False

    def apply_update_and_restart(self):
        """Substitui o executável atual e reinicia o aplicativo imediatamente."""
        if not self.downloaded_file or not self.downloaded_file.exists():
            return

        is_frozen = getattr(sys, "frozen", False)
        current_exe = Path(sys.executable).resolve()
        app_dir = current_exe.parent

        if not is_frozen:
            # Modo dev (python main.py): move para dist/RemoteXPTI.exe e reinicia
            target = Path("dist/RemoteXPTI.exe")
            target.parent.mkdir(exist_ok=True)
            shutil.move(self.downloaded_file, target)
            print(f"[SilentUpdater] Atualização copiada para {target}")
            subprocess.Popen([sys.executable, "main.py"], cwd=str(Path(__file__).parent.resolve()))
            os._exit(0)

        # Modo executável compilado (.exe):
        import tempfile
        temp_dir = Path(tempfile.gettempdir())
        script_path = temp_dir / "remotexpti_update.cmd"
        vbs_path = temp_dir / "remotexpti_run.vbs"

        cmd_content = f"""@echo off
chcp 65001 >nul
title Atualizando RemoteXPTI...

:: 1. Aguarda 2 segundos para o processo anterior encerrar e liberar os arquivos
ping 127.0.0.1 -n 3 >nul
taskkill /f /im "{current_exe.name}" >nul 2>&1
taskkill /f /im "RemoteXPTI.exe" >nul 2>&1

:: 2. Substitui o executavel com retry seguro (ate 30 tentativas)
for /l %%i in (1, 1, 30) do (
    copy /y "{str(self.downloaded_file)}" "{str(current_exe)}" >nul 2>&1 && (
        del /f /q "{str(self.downloaded_file)}" >nul 2>&1
        goto :launch
    )
    taskkill /f /im "{current_exe.name}" >nul 2>&1
    ping 127.0.0.1 -n 2 >nul
)

:launch
:: 3. Aguarda 1 segundo, limpa ambiente e reinicia o aplicativo
ping 127.0.0.1 -n 2 >nul
set PYINSTALLER_RESET_ENVIRONMENT=1
set _MEIPASS2=
set _MEIPASS=
cd /d "{str(app_dir)}"
start "" "{str(current_exe)}"
del "%~f0"
exit
"""
        script_path.write_text(cmd_content, encoding="utf-8")

        # Dispara via wscript.exe de forma 100% oculta e desvinculada do processo atual
        vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd.exe /c """ & "{str(script_path)}" & """", 0, False
'''
        vbs_path.write_text(vbs_content, encoding="utf-8")

        try:
            subprocess.run(["wscript.exe", "//b", "//nologo", str(vbs_path)], timeout=5.0)
        except Exception:
            # Fallback caso wscript esteja restrito
            os.startfile(str(script_path))

        # Encerra o processo atual imediatamente
        os._exit(0)


class UpdatePromptBanner(ctk.CTkFrame):
    """Banner visual no topo do app avisando que o update está baixado e pronto para reiniciar."""

    def __init__(self, parent, new_version: str, on_restart_command, on_dismiss=None):
        super().__init__(
            parent,
            height=42,
            corner_radius=8,
            fg_color=("#0052a3", "#123456"),
            border_width=1,
            border_color="#0080ff"
        )
        self.pack_propagate(False)

        # Texto de aviso
        lbl = ctk.CTkLabel(
            self,
            text=f"🚀 Nova versão v{new_version} pronta para instalar!",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff"
        )
        lbl.pack(side="left", padx=16)

        # Botão Fechar / Mais tarde
        btn_close = ctk.CTkButton(
            self,
            text="✕",
            width=28,
            height=26,
            fg_color="transparent",
            hover_color=("#003d7a", "#1a4670"),
            text_color="#ffffff",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=on_dismiss or self.destroy
        )
        btn_close.pack(side="right", padx=(4, 10))

        # Botão Reiniciar Agora
        btn_restart = ctk.CTkButton(
            self,
            text="🔄 Reiniciar para Atualizar",
            height=28,
            fg_color="#00a8ff",
            hover_color="#0088cc",
            text_color="#ffffff",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=on_restart_command
        )
        btn_restart.pack(side="right", padx=6)
