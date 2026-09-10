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
from logger import log

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
        log.info(f"[SilentUpdater] Iniciando verificação de atualizações (manual={is_manual}). Versão instalada: v{CURRENT_VERSION}")
        if self.update_ready:
            log.info(f"[SilentUpdater] Nova versão v{self.new_version} já está baixada e pronta para reiniciar.")
            if is_manual:
                self.notify_status(f"🚀 Versão v{self.new_version} já está baixada e pronta!")
            return

        if self.is_downloading:
            log.info(f"[SilentUpdater] Download da versão v{self.new_version} já está em andamento.")
            if is_manual:
                self.notify_status(f"⬇️ Baixando nova versão v{self.new_version} em segundo plano...")
            return

        if self.is_checking:
            log.info("[SilentUpdater] Verificação de atualizações já em andamento.")
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
            log.info(f"[SilentUpdater] Consultando versão mais recente via Web redirect: {web_url}")
            req = urllib.request.Request(
                web_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                final_url = resp.geturl()
                log.info(f"[SilentUpdater] Resposta do redirect Web: {final_url}")
                if "/releases/tag/" in final_url:
                    tag_name = final_url.split("/releases/tag/")[-1].split("/")[0].strip()
                    download_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag_name}/{APP_NAME}.exe"
                    log.info(f"[SilentUpdater] Web redirect detectou versão: {tag_name}, URL: {download_url}")
                    return tag_name, download_url
        except Exception as e:
            log.warning(f"[SilentUpdater] Metodo web redirect indisponivel ({e}), tentando API REST...")

        # Metodo 2: Fallback para API REST do GitHub
        try:
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            log.info(f"[SilentUpdater] Consultando API REST: {api_url}")
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
                    log.info(f"[SilentUpdater] API REST detectou versão: {tag_name}, URL: {download_url}")
                    return tag_name, download_url
        except Exception as e:
            log.error(f"[SilentUpdater] Fallback API GitHub indisponivel: {e}")

        return tag_name, download_url

    def _worker(self, is_manual: bool = False):
        self.is_checking = True
        if is_manual:
            self.notify_status("🔍 Verificando atualizações no GitHub...")

        try:
            tag_name, download_url = self._get_latest_release_info()
            if not tag_name:
                log.warning("[SilentUpdater] Servidor de atualizações indisponível ou nenhuma tag retornada.")
                if is_manual:
                    self.notify_status("⚠️ Servidor de atualizações indisponível.")
                return

            remote_ver = parse_version(tag_name)
            local_ver = parse_version(CURRENT_VERSION)
            log.info(f"[SilentUpdater] Comparação de versões: Local=v{CURRENT_VERSION} ({local_ver}) vs Remota={tag_name} ({remote_ver})")

            if remote_ver <= local_ver:
                # Já está na versão mais recente
                log.info(f"[SilentUpdater] Aplicação já está na versão mais recente (v{CURRENT_VERSION}).")
                if is_manual:
                    self.notify_status(f"✅ Você já está na versão mais recente (v{CURRENT_VERSION})!")
                return

            self.new_version = tag_name.lstrip("v").lstrip("V")
            log.info(f"[SilentUpdater] Nova versão encontrada: v{self.new_version}! Baixando em segundo plano...")
            if is_manual:
                self.notify_status(f"⬇️ Nova versão v{self.new_version} encontrada! Baixando em segundo plano...")

            if not download_url:
                log.warning(f"[SilentUpdater] Executável não encontrado nos assets da release {tag_name}.")
                if is_manual:
                    self.notify_status("⚠️ Arquivo da atualização não encontrado nos lançamentos.")
                return

            # Inicia o download silencioso em segundo plano
            self._download_update_silent(download_url)

        except Exception as e:
            # Falhas de rede em background não interrompem o uso do usuário
            log.error(f"[SilentUpdater] Exceção na verificação de atualização: {e}", exc_info=True)
            if is_manual:
                self.notify_status("⚠️ Não foi possível verificar atualizações no momento.")
        finally:
            self.is_checking = False

    def _download_update_silent(self, download_url: str):
        self.is_downloading = True
        log.info(f"[SilentUpdater] Iniciando download silencioso da v{self.new_version} a partir de: {download_url}")
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
            downloaded_bytes = 0
            with urllib.request.urlopen(req, timeout=60.0) as response:
                block_size = 65536
                with open(temp_part, "wb") as out_file:
                    while True:
                        buf = response.read(block_size)
                        if not buf:
                            break
                        out_file.write(buf)
                        downloaded_bytes += len(buf)

            size_mb = downloaded_bytes / (1024 * 1024)
            log.info(f"[SilentUpdater] Download concluído: {downloaded_bytes} bytes ({size_mb:.2f} MB)")

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
                log.info(f"[SilentUpdater] Nova versão {self.new_version} baixada e pronta em {temp_dest}!")

                if self.on_ready_callback:
                    self.on_ready_callback(self.new_version)
            else:
                log.error(f"[SilentUpdater] Arquivo baixado incompleto ou corrompido (tamanho: {downloaded_bytes} bytes).")

        except Exception as e:
            log.error(f"[SilentUpdater] Erro no download em background: {e}", exc_info=True)
        finally:
            self.is_downloading = False

    def apply_update_and_restart(self):
        """Substitui o executável atual e reinicia o aplicativo imediatamente."""
        if not self.downloaded_file or not self.downloaded_file.exists():
            log.warning("[SilentUpdater] apply_update_and_restart chamado mas downloaded_file não existe.")
            return

        log.info(f"[SilentUpdater] Aplicando atualização para v{self.new_version} e reiniciando a aplicação...")

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
        ps1_path = temp_dir / "remotexpti_update_gui.ps1"
        current_pid = os.getpid()

        ps_script = f"""# Atualizador com Tela de Carregamento Moderna (Sem janelas de CMD)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = "Atualizando RemoteXPTI"
$form.Size = New-Object System.Drawing.Size(440, 195)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true
$form.BackColor = [System.Drawing.Color]::FromArgb(24, 26, 32)
$form.ForeColor = [System.Drawing.Color]::White

$iconPath = Join-Path '{str(app_dir)}' "imagens\\icon.ico"
if (Test-Path $iconPath) {{
    try {{ $form.Icon = New-Object System.Drawing.Icon($iconPath) }} catch {{}}
}}

$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.Text = "⚡ RemoteXPTI - Atualizando Sistema"
$titleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 12, [System.Drawing.FontStyle]::Bold)
$titleLabel.ForeColor = [System.Drawing.Color]::White
$titleLabel.Location = New-Object System.Drawing.Point(24, 20)
$titleLabel.Size = New-Object System.Drawing.Size(380, 26)
$form.Controls.Add($titleLabel)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Text = "Aplicando atualização para a versão v{self.new_version}..."
$statusLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
$statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(160, 165, 180)
$statusLabel.Location = New-Object System.Drawing.Point(24, 50)
$statusLabel.Size = New-Object System.Drawing.Size(380, 24)
$form.Controls.Add($statusLabel)

$pbar = New-Object System.Windows.Forms.ProgressBar
$pbar.Location = New-Object System.Drawing.Point(24, 82)
$pbar.Size = New-Object System.Drawing.Size(376, 18)
$pbar.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee
$pbar.MarqueeAnimationSpeed = 20
$form.Controls.Add($pbar)

$stepLabel = New-Object System.Windows.Forms.Label
$stepLabel.Text = "Substituindo executável pela nova versão..."
$stepLabel.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
$stepLabel.ForeColor = [System.Drawing.Color]::FromArgb(100, 150, 255)
$stepLabel.Location = New-Object System.Drawing.Point(24, 110)
$stepLabel.Size = New-Object System.Drawing.Size(380, 20)
$form.Controls.Add($stepLabel)

$logDir = Join-Path $env:LOCALAPPDATA "RemoteXPTI\\logs"
if (-not (Test-Path $logDir)) {{ New-Item -ItemType Directory -Path $logDir -Force | Out-Null }}
$logFile = Join-Path $logDir "remotexpti.log"

function Write-Log($msg) {{
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [AutoUpdater] $msg"
    try {{ Add-Content -Path $logFile -Value $line -ErrorAction SilentlyContinue }} catch {{}}
}}

Write-Log "Iniciando processo de atualização para v{self.new_version}..."

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 250
$script:ticks = 0

$timer.Add_Tick({{
    $script:ticks++
    if ($script:ticks -eq 2) {{
        Write-Log "Encerrando processos RemoteXPTI e Edge auxiliares..."
        try {{
            Stop-Process -Id {current_pid} -Force -ErrorAction SilentlyContinue
        }} catch {{}}
        try {{
            Get-Process -Name "RemoteXPTI" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        }} catch {{}}
        try {{
            $cache = (Join-Path $env:LOCALAPPDATA "RemoteXPTI\\map_cache").ToLower()
            Get-CimInstance Win32_Process -Filter "name = 'msedge.exe'" | Where-Object {{ $_.CommandLine -and $_.CommandLine.ToLower().Contains($cache) }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}
        }} catch {{}}
    }}
    if ($script:ticks -ge 4) {{
        $copied = $false
        $destPath = '{str(current_exe)}'
        $sourcePath = '{str(self.downloaded_file)}'
        $oldPath = "$destPath.old"

        for ($i = 0; $i -lt 30; $i++) {{
            try {{
                # Garante que nenhum processo RemoteXPTI está ativo segurando o executável
                Get-Process -Name "RemoteXPTI" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

                if (Test-Path $oldPath) {{
                    Remove-Item -Path $oldPath -Force -ErrorAction SilentlyContinue
                }}
                if (Test-Path $destPath) {{
                    try {{
                        Remove-Item -Path $destPath -Force -ErrorAction Stop
                    }} catch {{
                        Move-Item -Path $destPath -Destination $oldPath -Force -ErrorAction SilentlyContinue
                    }}
                }}
                Copy-Item -Path $sourcePath -Destination $destPath -Force -ErrorAction Stop
                Remove-Item -Path $sourcePath -Force -ErrorAction SilentlyContinue
                if (Test-Path $oldPath) {{
                    Remove-Item -Path $oldPath -Force -ErrorAction SilentlyContinue
                }}
                $copied = $true
                Write-Log "Executável substituído com sucesso na tentativa $i!"
                break
            }} catch {{
                $err = $_.Exception.Message
                Write-Log "Tentativa $i falhou ao substituir executável: $err"
                Start-Sleep -Milliseconds 350
            }}
        }}
        if ($copied) {{
            Write-Log "Iniciando nova versão v{self.new_version}..."
            $statusLabel.Text = "Versão v{self.new_version} instalada com sucesso!"
            $stepLabel.Text = "Iniciando RemoteXPTI..."
            $stepLabel.ForeColor = [System.Drawing.Color]::FromArgb(0, 204, 102)
            $pbar.Style = [System.Windows.Forms.ProgressBarStyle]::Continuous
            $pbar.Value = 100
            $form.Refresh()
            [System.Windows.Forms.Application]::DoEvents()
            $timer.Stop()
            
            $env:PYINSTALLER_RESET_ENVIRONMENT = "1"
            $env:_MEIPASS2 = $null
            $env:_MEIPASS = $null
            Start-Process -FilePath '{str(current_exe)}' -WorkingDirectory '{str(app_dir)}'
            
            Start-Sleep -Milliseconds 400
            $form.Hide()
            $form.Close()
            $form.Dispose()
            [System.Windows.Forms.Application]::Exit()
            Remove-Item -Path '{str(ps1_path)}' -Force -ErrorAction SilentlyContinue
            Stop-Process -Id $PID -Force
        }} elseif ($script:ticks -gt 35) {{
            $timer.Stop()
            Write-Log "ERRO CRÍTICO: Não foi possível substituir o executável após 30 tentativas."
            [System.Windows.Forms.MessageBox]::Show("Não foi possível substituir o executável. Verifique os logs de diagnóstico em %LOCALAPPDATA%\\RemoteXPTI\\logs ou execute o instalador Setup_RemoteXPTI.", "Erro na Atualização", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
            $form.Hide()
            $form.Close()
            $form.Dispose()
            [System.Windows.Forms.Application]::Exit()
            Remove-Item -Path '{str(ps1_path)}' -Force -ErrorAction SilentlyContinue
            Stop-Process -Id $PID -Force
        }}
    }}
}})

$form.Add_Shown({{ $timer.Start() }})
[System.Windows.Forms.Application]::Run($form)
Remove-Item -Path '{str(ps1_path)}' -Force -ErrorAction SilentlyContinue
Stop-Process -Id $PID -Force
"""
        ps1_path.write_text(ps_script, encoding="utf-8-sig")

        creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        try:
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-WindowStyle", "Hidden",
                    "-ExecutionPolicy", "Bypass",
                    "-File", str(ps1_path)
                ],
                creationflags=creation_flags
            )
        except Exception as e:
            print(f"[SilentUpdater] Erro ao disparar tela de atualização: {e}")

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
