"""
Controlador do Painel de Monitoramento de ONUs Ajin (Jurerê Internacional)
utilizando Microsoft Edge WebView acoplado nativamente ao container Tkinter.
Fornece 100% do layout visual e 100% das funções operacionais do dashboard.
"""

import os
import sys
import time
import subprocess
import threading
from pathlib import Path
from typing import Optional

try:
    import win32gui
    import win32process
    import win32con
except ImportError:
    win32gui = None
    win32process = None
    win32con = None

from logger import log
from ajin_dashboard import AjinDashboardServer


def get_edge_executable() -> Optional[str]:
    """Localiza o executável do Microsoft Edge no sistema Windows."""
    paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


def cleanup_orphaned_ajin_edge_processes(cache_dir: Path):
    """Encerra de forma silenciosa processos msedge.exe antigos atrelados ao cache do dashboard Ajin."""
    cache_str = str(cache_dir).lower()
    creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        import win32com.client
        wmi = win32com.client.GetObject("winmgmts:")
        procs = wmi.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name = 'msedge.exe'")
        for p in procs:
            cmd = (p.CommandLine or "").lower()
            if cache_str in cmd:
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.ProcessId)], capture_output=True, creationflags=creation_flags)
                except Exception:
                    try:
                        p.Terminate()
                    except Exception:
                        pass
    except Exception:
        pass

    for lock_name in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        lock_file = cache_dir / lock_name
        if lock_file.exists():
            try:
                lock_file.unlink()
            except Exception:
                pass


class WebAjinManager:
    """Controlador que acopla o Dashboard real da Ajin no RemoteXPTI."""

    def __init__(self, container_widget):
        self.container = container_widget
        try:
            self.container_hwnd = container_widget.winfo_id()
        except Exception:
            self.container_hwnd = None

        self.server = AjinDashboardServer.get_instance()
        self.port = 0
        self.edge_proc: Optional[subprocess.Popen] = None
        self.edge_hwnd: Optional[int] = None
        self._is_docked = False
        self._is_visible = False
        self._drawer_offset = 0

        # Inicia o servidor em segundo plano e prepara o Edge
        threading.Thread(target=self._init_server_and_dock, daemon=True).start()

    def set_drawer_offset(self, offset: int):
        self._drawer_offset = max(0, offset)
        self.resize()

    def show(self):
        """Exibe o painel web da Ajin e redimensiona para ocupar o container."""
        self._is_visible = True
        log.info("[WebAjinManager] show() acionado - Revelando janela do Dashboard Ajin")
        if not self.edge_hwnd or not self._is_docked:
            if not self.edge_proc:
                self._init_server_and_dock()
            return
        try:
            w = max(300, self.container.winfo_width() - getattr(self, "_drawer_offset", 0))
            h = max(300, self.container.winfo_height())
            win32gui.SetWindowPos(
                self.edge_hwnd, win32con.HWND_TOP, 0, 0, w, h,
                win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE
            )
            win32gui.ShowWindow(self.edge_hwnd, win32con.SW_SHOW)
            win32gui.InvalidateRect(self.edge_hwnd, None, True)
            win32gui.UpdateWindow(self.edge_hwnd)
        except Exception as e:
            log.error(f"[WebAjinManager] Erro ao exibir janela do Edge: {e}")

    def hide(self):
        """Oculta o painel web quando o usuário volta para a Grade ou Mapa."""
        self._is_visible = False
        log.info("[WebAjinManager] hide() acionado - Ocultando janela do Dashboard Ajin")
        if self.edge_hwnd:
            try:
                win32gui.ShowWindow(self.edge_hwnd, win32con.SW_HIDE)
            except Exception as e:
                log.error(f"[WebAjinManager] Erro ao ocultar janela do Edge: {e}")

    def resize(self):
        """Ajusta o tamanho do Edge para corresponder ao container com offset do drawer."""
        if not self.edge_hwnd or not self._is_docked or not self.container:
            return
        try:
            w = max(300, self.container.winfo_width() - getattr(self, "_drawer_offset", 0))
            h = self.container.winfo_height()
            if w > 50 and h > 50:
                win32gui.SetWindowPos(
                    self.edge_hwnd, win32con.HWND_TOP, 0, 0, w, h,
                    win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE
                )
        except Exception:
            pass

    def _init_server_and_dock(self):
        try:
            self.port = self.server.start()
            log.info(f"[WebAjinManager] Servidor do Dashboard Ajin pronto na porta {self.port}")
        except Exception as e:
            log.error(f"[WebAjinManager] Erro ao iniciar servidor do Dashboard Ajin: {e}")
            return

        edge_exe = get_edge_executable()
        if not edge_exe:
            log.error("[WebAjinManager] Microsoft Edge não encontrado no sistema!")
            return

        cache_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RemoteXPTI" / "ajin_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cleanup_orphaned_ajin_edge_processes(cache_dir)

        if not self.container_hwnd:
            try:
                self.container_hwnd = self.container.winfo_id()
            except Exception:
                pass
        target_parent_hwnd = self.container_hwnd
        if not target_parent_hwnd:
            log.error("[WebAjinManager] Container HWND não disponível para acoplamento.")
            return

        try:
            crect = win32gui.GetClientRect(target_parent_hwnd)
            w = max(400, crect[2])
            h = max(300, crect[3])
        except Exception:
            w, h = 1100, 700

        log.info(f"[WebAjinManager] Iniciando Edge ({edge_exe}) para container HWND={target_parent_hwnd} ({w}x{h})...")

        # Inicia fora da tela para evitar flickering
        cmd = [
            edge_exe,
            f"--app=http://127.0.0.1:{self.port}",
            f"--user-data-dir={str(cache_dir)}",
            "--no-first-run",
            "--no-default-browser-check",
            "--proxy-bypass-list=<-loopback>;127.0.0.1;localhost",
            "--disable-extensions",
            "--disable-component-update",
            "--disable-sync",
            "--disable-features=Translate",
            "--enable-features=IntensiveWakeUpThrottling,QuickBackForwardCache",
            "--disable-background-networking",
            "--window-position=-10000,-10000",
            f"--window-size={w},{h}"
        ]

        self.edge_proc = subprocess.Popen(cmd, creationflags=0)
        log.info(f"[WebAjinManager] Processo Edge do Ajin instanciado com PID={self.edge_proc.pid}")

        def find_and_dock(parent_hwnd, initial_w, initial_h):
            found_hwnd = None
            try:
                for attempt in range(70):
                    time.sleep(0.08)

                    def enum_cb(h, _):
                        nonlocal found_hwnd
                        cname = win32gui.GetClassName(h)
                        if "Chrome_WidgetWin_1" in cname:
                            try:
                                _, pid = win32process.GetWindowThreadProcessId(h)
                                title = win32gui.GetWindowText(h)
                                style = win32gui.GetWindowLong(h, win32con.GWL_STYLE)
                                rect = win32gui.GetWindowRect(h)
                                rw = rect[2] - rect[0]
                                rh = rect[3] - rect[1]

                                is_our_pid = (self.edge_proc and pid == self.edge_proc.pid)
                                has_title = "127.0.0.1" in title or f"{self.port}" in title or "Monitoramento" in title or "ONUs" in title
                                has_caption = (style & win32con.WS_CAPTION) != 0
                                has_size = rw > 200 and rh > 200

                                if (is_our_pid or has_title) and has_caption and has_size:
                                    found_hwnd = h
                            except Exception:
                                pass
                    win32gui.EnumWindows(enum_cb, None)
                    if found_hwnd:
                        break

                if found_hwnd:
                    self.edge_hwnd = found_hwnd
                    log.info(f"[WebAjinManager] Janela do Edge localizada com sucesso: HWND={found_hwnd}")

                    win32gui.ShowWindow(found_hwnd, win32con.SW_HIDE)

                    old_style = win32gui.GetWindowLong(found_hwnd, win32con.GWL_STYLE)
                    new_style = (old_style & ~win32con.WS_POPUP & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME & ~win32con.WS_MINIMIZEBOX & ~win32con.WS_MAXIMIZEBOX & ~win32con.WS_SYSMENU) | win32con.WS_CHILD | win32con.WS_CLIPCHILDREN | win32con.WS_CLIPSIBLINGS
                    win32gui.SetWindowLong(found_hwnd, win32con.GWL_STYLE, new_style)

                    old_ex = win32gui.GetWindowLong(found_hwnd, win32con.GWL_EXSTYLE)
                    new_ex = (old_ex & ~win32con.WS_EX_APPWINDOW & ~win32con.WS_EX_WINDOWEDGE & ~win32con.WS_EX_DLGMODALFRAME) | win32con.WS_EX_CONTROLPARENT
                    win32gui.SetWindowLong(found_hwnd, win32con.GWL_EXSTYLE, new_ex)

                    win32gui.SetParent(found_hwnd, parent_hwnd)

                    try:
                        crect = win32gui.GetClientRect(parent_hwnd)
                        final_w = max(crect[2], initial_w)
                        final_h = max(crect[3], initial_h)
                    except Exception:
                        final_w, final_h = initial_w, initial_h

                    win32gui.SetWindowPos(
                        found_hwnd, win32con.HWND_TOP, 0, 0, final_w, final_h,
                        win32con.SWP_FRAMECHANGED | (win32con.SWP_SHOWWINDOW if self._is_visible else win32con.SWP_HIDEWINDOW)
                    )
                    self._is_docked = True
                    log.info(f"[WebAjinManager] Edge acoplado com sucesso sem bordas no container HWND={parent_hwnd} ({final_w}x{final_h})")

                    if self._is_visible:
                        self.show()
                else:
                    log.error(f"[WebAjinManager] Janela do Edge não foi localizada após 70 tentativas.")
            except Exception as ex:
                log.error(f"[WebAjinManager] Erro no docking do Edge: {ex}", exc_info=True)

        threading.Thread(target=find_and_dock, args=(target_parent_hwnd, w, h), daemon=True).start()

    def shutdown(self):
        """Fecha o processo e o servidor na saída do RemoteXPTI."""
        log.info("[WebAjinManager] shutdown() acionado - Encerrando Edge e servidor Ajin...")
        self.hide()
        if self.edge_hwnd:
            try:
                win32gui.PostMessage(self.edge_hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self.edge_proc:
            try:
                self.edge_proc.terminate()
            except Exception:
                pass
            self.edge_proc = None
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
