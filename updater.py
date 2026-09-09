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

    def __init__(self, on_ready_callback: Optional[Callable[[str], None]] = None):
        self.on_ready_callback = on_ready_callback
        self.is_checking = False
        self.is_downloading = False
        self.update_ready = False
        self.new_version = ""
        self.downloaded_file: Optional[Path] = None

    def start_background_check(self):
        """Inicia a verificação e download automático em background."""
        if self.is_checking or self.is_downloading or self.update_ready:
            return

        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        self.is_checking = True
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
                if resp.status != 200:
                    return
                data = json.loads(resp.read().decode("utf-8"))

            tag_name = data.get("tag_name", "").strip()
            remote_ver = parse_version(tag_name)
            local_ver = parse_version(CURRENT_VERSION)

            if remote_ver <= local_ver:
                # Já está na versão mais recente
                return

            self.new_version = tag_name.lstrip("v").lstrip("V")

            # Localiza o arquivo .exe nos assets
            assets = data.get("assets", [])
            download_url = ""
            for asset in assets:
                name = asset.get("name", "")
                if name.lower().endswith(".exe") and "setup" not in name.lower():
                    download_url = asset.get("browser_download_url", "")
                    break

            if not download_url and assets:
                # Fallback para qualquer .exe se não houver um exclusivo
                download_url = assets[0].get("browser_download_url", "")

            if not download_url:
                return

            # Inicia o download silencioso em segundo plano
            self._download_update_silent(download_url)

        except Exception as e:
            # Falhas de rede em background não interrompem o uso do usuário
            print(f"[SilentUpdater] Verificação de atualização: {e}")
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

            temp_dest = app_dir / ".pending_update.exe"

            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": f"{APP_NAME}-SilentUpdater"}
            )
            with urllib.request.urlopen(req, timeout=60.0) as response:
                block_size = 65536
                with open(temp_dest, "wb") as out_file:
                    while True:
                        buf = response.read(block_size)
                        if not buf:
                            break
                        out_file.write(buf)

            # Download 100% concluído e verificado
            if temp_dest.exists() and temp_dest.stat().st_size > 500000:
                self.downloaded_file = temp_dest
                self.update_ready = True
                print(f"[SilentUpdater] Nova versão {self.new_version} baixada e pronta!")

                if self.on_ready_callback:
                    self.on_ready_callback(self.new_version)

        except Exception as e:
            print(f"[SilentUpdater] Erro no download em background: {e}")
        finally:
            self.is_downloading = False

    def apply_update_and_restart(self):
        """Substitui o executável atual e reinicia o aplicativo imediatamente."""
        if not self.downloaded_file or not self.downloaded_file.exists():
            return

        is_frozen = getattr(sys, "frozen", False)
        current_exe = Path(sys.executable)

        if not is_frozen:
            # Modo dev (python main.py): apenas move para dist/RemoteXPTI.exe
            target = Path("dist/RemoteXPTI.exe")
            target.parent.mkdir(exist_ok=True)
            shutil.move(self.downloaded_file, target)
            print(f"[SilentUpdater] Atualização copiada para {target}")
            return

        # Modo executável compilado (.exe):
        # Usa PowerShell em segundo plano (oculto e sem criar nenhum arquivo .bat no disco)
        # para aguardar 1 segundo até o processo encerrar, substituir o executável e reabrir.
        ps_cmd = (
            f"Start-Sleep -Seconds 1; "
            f"Move-Item -Force -Path '{str(self.downloaded_file)}' -Destination '{str(current_exe)}'; "
            f"Start-Process -FilePath '{str(current_exe)}'"
        )
        creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        subprocess.Popen(
            ["powershell.exe", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            creationflags=creation_flags
        )

        # Encerra o processo atual
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
