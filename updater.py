import os
import sys
import json
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import threading
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Callable, List
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


def is_public_version(v_str: str) -> bool:
    """Retorna True se for uma versão do canal Público/Beta Geral (1.x.0).
    A segunda casa muda e a terceira casa é estritamente 0.
    """
    parts = parse_version(v_str)
    return len(parts) >= 3 and parts[2] == 0


def is_beta_tester_version(v_str: str) -> bool:
    """Retorna True se for uma versão do canal Beta Tester / Desenvolvimento (1.1.x ou 1.x.y com y > 0)."""
    parts = parse_version(v_str)
    return len(parts) >= 3 and parts[2] > 0


class SilentAutoUpdater:
    """
    Sistema de atualização em segundo plano estilo Antigravity/Chrome/VS Code:
    1. Checa a versão silenciosamente no GitHub Releases conforme o canal (Público vs Beta Tester).
    2. Se houver versão nova, inicia o download em segundo plano sem travar nada.
    3. Quando o download termina, avisa o usuário e oferece o botão para Reiniciar.
    4. Ao reiniciar, substitui o executável e abre o novo aplicativo.
    5. Permite ao desenvolvedor selecionar qualquer versão histórica para instalação/rollback.
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
        """Inicia a verificação e download automático em background conforme o canal configurado."""
        from config_manager import ConfigManager
        channel = ConfigManager().get_update_channel()
        channel_desc = "Beta Tester (1.1.x)" if channel == "beta_tester" else "Público (1.x.0)"
        log.info(f"[SilentUpdater] Iniciando verificação (manual={is_manual}, canal={channel_desc}). Versão atual: v{CURRENT_VERSION}")

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

    @staticmethod
    def fetch_all_releases() -> List[Dict[str, Any]]:
        """
        Consulta o GitHub Releases e retorna lista completa para o seletor de versões.
        Tenta primeiro a API JSON do GitHub. Em caso de Rate Limit (HTTP 403) ou falha de rede,
        aciona automaticamente o Feed Atom oficial de releases (sem limites de requisição).
        """
        releases: List[Dict[str, Any]] = []

        # 1. Tentativa via API JSON do GitHub
        try:
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=40"
            req = urllib.request.Request(
                api_url,
                headers={
                    "User-Agent": f"{APP_NAME}-VersionSelector",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    for item in data:
                        tag = item.get("tag_name", "").strip()
                        name = item.get("name", tag) or tag
                        published = (item.get("published_at") or "")[:10]
                        is_prerelease = bool(item.get("prerelease", False))

                        download_url = ""
                        for asset in item.get("assets", []):
                            aname = asset.get("name", "")
                            if aname.lower().endswith(".exe") and "setup" not in aname.lower():
                                download_url = asset.get("browser_download_url", "")
                                break
                        if not download_url:
                            download_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{APP_NAME}.exe"

                        is_pub = is_public_version(tag)
                        channel_label = "Público (Beta)" if is_pub else "Beta Tester"

                        releases.append({
                            "tag": tag,
                            "name": name,
                            "published": published,
                            "is_public": is_pub,
                            "is_prerelease": is_prerelease,
                            "channel_label": channel_label,
                            "download_url": download_url
                        })
                    if releases:
                        log.info(f"[SilentUpdater] {len(releases)} versões carregadas com sucesso via API GitHub.")
                        return releases
        except Exception as e:
            log.warning(f"[SilentUpdater] API do GitHub retornou aviso ({e}). Acionando fallback instantâneo por Feed Atom...")

        # 2. Fallback Imediato: Feed Atom de Releases do GitHub (Sem Rate Limit)
        try:
            feed_url = f"https://github.com/{GITHUB_REPO}/releases.atom"
            req_feed = urllib.request.Request(
                feed_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req_feed, timeout=8.0) as resp:
                if resp.status == 200:
                    root = ET.fromstring(resp.read())
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    for entry in root.findall("atom:entry", ns):
                        title = (entry.find("atom:title", ns).text or "").strip()
                        updated = (entry.find("atom:updated", ns).text or "")[:10]
                        link_elem = entry.find("atom:link", ns)
                        link = link_elem.attrib.get("href", "") if link_elem is not None else ""
                        if "/releases/tag/" in link:
                            tag = link.split("/releases/tag/")[-1].strip()
                        else:
                            tag = title.split()[0].strip()

                        is_pub = is_public_version(tag)
                        channel_label = "Público (Beta)" if is_pub else "Beta Tester"
                        dl_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{APP_NAME}.exe"

                        releases.append({
                            "tag": tag,
                            "name": title,
                            "published": updated,
                            "is_public": is_pub,
                            "is_prerelease": not is_pub,
                            "channel_label": channel_label,
                            "download_url": dl_url
                        })
                    log.info(f"[SilentUpdater] {len(releases)} versões carregadas com sucesso via Feed Atom do GitHub.")
        except Exception as e:
            log.error(f"[SilentUpdater] Falha também no fallback do feed de releases: {e}")

        return releases

    def _get_latest_release_info(self) -> Tuple[str, str]:
        """
        Retorna (tag_name, download_url) da versão mais recente conforme o canal do cliente.
        - Clientes no canal 'public' recebem apenas versões 1.x.0.
        - Desenvolvedores no canal 'beta_tester' recebem todas as versões (1.1.x ou 1.x.0).
        """
        from config_manager import ConfigManager
        channel = ConfigManager().get_update_channel()

        # 1. Se estiver no canal público, tenta primeiro o redirecionamento web oficial do GitHub
        if channel == "public":
            try:
                web_url = f"https://github.com/{GITHUB_REPO}/releases/latest"
                log.info(f"[SilentUpdater] [Canal Público] Consultando release oficial: {web_url}")
                req = urllib.request.Request(
                    web_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    final_url = resp.geturl()
                    if "/releases/tag/" in final_url:
                        tag_name = final_url.split("/releases/tag/")[-1].split("/")[0].strip()
                        if is_public_version(tag_name):
                            download_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag_name}/{APP_NAME}.exe"
                            log.info(f"[SilentUpdater] Release pública oficial detectada: {tag_name}")
                            return tag_name, download_url
            except Exception as e:
                log.warning(f"[SilentUpdater] Falha no redirect web público: {e}")

            # Fallback: pesquisa na lista de releases a primeira versão pública (1.x.0)
            log.info("[SilentUpdater] [Canal Público] Filtrando histórico de releases por versão 1.x.0...")
            all_releases = self.fetch_all_releases()
            for r in all_releases:
                if r["is_public"] and r["download_url"]:
                    log.info(f"[SilentUpdater] Versão pública encontrada na lista: {r['tag']}")
                    return r["tag"], r["download_url"]
            return "", ""

        else:
            # 2. Canal Beta Tester: pega a release mais recente absoluta (seja 1.1.x ou 1.x.0)
            log.info("[SilentUpdater] [Canal Beta Tester] Buscando versão mais recente absoluta...")
            all_releases = self.fetch_all_releases()
            if all_releases and all_releases[0]["download_url"]:
                log.info(f"[SilentUpdater] Mais nova versão beta tester encontrada: {all_releases[0]['tag']}")
                return all_releases[0]["tag"], all_releases[0]["download_url"]
            return "", ""

    def download_and_install_specific(self, tag_name: str, download_url: str, on_status=None):
        """Baixa e aplica uma versão específica escolhida pelo desenvolvedor no seletor de versões."""
        def worker():
            self.new_version = tag_name.lstrip("v").lstrip("V")
            if on_status:
                on_status(f"⬇️ Baixando {tag_name}...")
            self._download_update_silent(download_url)
            if self.update_ready:
                if on_status:
                    on_status(f"✅ Versão {tag_name} baixada com sucesso! Reiniciando...")
                self.apply_update_and_restart()
            else:
                if on_status:
                    on_status("⚠️ Falha ao baixar o arquivo da versão selecionada.")

        threading.Thread(target=worker, daemon=True).start()

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
$form.Size = New-Object System.Drawing.Size(460, 290)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "None"
$form.TopMost = $true
$form.BackColor = [System.Drawing.Color]::FromArgb(18, 19, 24)
$form.ForeColor = [System.Drawing.Color]::White

# Borda suave moderna e efeito visual na janela
$form.Add_Paint({{
    param($s, $e)
    $penBorder = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(36, 38, 48), 1.5)
    $e.Graphics.DrawRectangle($penBorder, 1, 1, $s.Width - 2, $s.Height - 2)
    $penHalo = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(223, 2, 9), 2.0)
    $e.Graphics.DrawEllipse($penHalo, 186, 20, 88, 88)
}})

$pngPath = Join-Path '{str(app_dir)}' "imagens\\app_icon.png"
if (Test-Path $pngPath) {{
    try {{
        $pbox = New-Object System.Windows.Forms.PictureBox
        $pbox.Size = New-Object System.Drawing.Size(76, 76)
        $pbox.Location = New-Object System.Drawing.Point(192, 26)
        $pbox.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
        $pbox.Image = [System.Drawing.Image]::FromFile($pngPath)
        $form.Controls.Add($pbox)
    }} catch {{}}
}}

$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.Text = "Atualizando RemoteXPTI"
$titleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 15, [System.Drawing.FontStyle]::Bold)
$titleLabel.ForeColor = [System.Drawing.Color]::White
$titleLabel.Location = New-Object System.Drawing.Point(20, 118)
$titleLabel.Size = New-Object System.Drawing.Size(420, 28)
$titleLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
$form.Controls.Add($titleLabel)

$subLabel = New-Object System.Windows.Forms.Label
$subLabel.Text = "XPti Tecnologia  •  Instalando v{self.new_version}"
$subLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
$subLabel.ForeColor = [System.Drawing.Color]::FromArgb(126, 131, 148)
$subLabel.Location = New-Object System.Drawing.Point(20, 148)
$subLabel.Size = New-Object System.Drawing.Size(420, 20)
$subLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
$form.Controls.Add($subLabel)

$pbar = New-Object System.Windows.Forms.ProgressBar
$pbar.Location = New-Object System.Drawing.Point(115, 190)
$pbar.Size = New-Object System.Drawing.Size(230, 4)
$pbar.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee
$pbar.MarqueeAnimationSpeed = 15
$form.Controls.Add($pbar)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Text = "Substituindo executável pela nova versão..."
$statusLabel.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
$statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(100, 104, 122)
$statusLabel.Location = New-Object System.Drawing.Point(20, 216)
$statusLabel.Size = New-Object System.Drawing.Size(420, 22)
$statusLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
$form.Controls.Add($statusLabel)

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
