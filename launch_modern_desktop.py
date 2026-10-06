import ctypes
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path
import webview

PORT = 8765
URL = f"http://127.0.0.1:{PORT}"

def _dbg(msg: str):
    try:
        debug_file = Path(__file__).parent / "launch_debug.txt"
        with open(debug_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

_dbg(f"Módulo carregado com argv: {sys.argv} (executable: {sys.executable})")

def _start_backend():
    import desktop_backend
    desktop_backend.start_backend_service(port=PORT)

def wait_for_server(timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{URL}/api/status", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False

def is_backend_running(timeout=0.6) -> bool:
    try:
        with urllib.request.urlopen(f"{URL}/api/status", timeout=timeout) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass
    return False

def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SYNCHRONIZE = 0x00100000
    h_proc = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
    if not h_proc:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if ctypes.windll.kernel32.GetExitCodeProcess(h_proc, ctypes.byref(exit_code)):
            STILL_ACTIVE = 259
            return exit_code.value == STILL_ACTIVE
        return False
    finally:
        ctypes.windll.kernel32.CloseHandle(h_proc)

def focus_existing_instance(window_title: str) -> bool:
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
        if hwnd:
            proc_id = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            current_pid = os.getpid()
            if proc_id.value == 0 or proc_id.value == current_pid:
                return False
            if not is_pid_alive(proc_id.value):
                return False

            SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
    except Exception as e:
        _dbg(f"focus_existing_instance exception: {e}")
    return False

def main():
    title = "RemoteXPTI - RDP Quick Launcher"
    _dbg("Entrou em main()...")

    try:
        # Permite agrupamento e ícone próprio na barra de tarefas do Windows
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("XPTI.RemoteXPTI.Modern.App")
        except Exception as e:
            _dbg(f"SetCurrentProcessExplicitAppUserModelID: {e}")

        # Se a janela gráfica já estiver aberta e visível, restaura foco e encerra processo duplicado
        has_win = focus_existing_instance(title)
        _dbg(f"focus_existing_instance: {has_win}")
        if has_win:
            _dbg("Janela já visível. Saindo.")
            sys.exit(0)

        # 1. Inicia o backend FastAPI + WebSockets em segundo plano caso ainda não esteja rodando
        bg_running = is_backend_running()
        _dbg(f"is_backend_running: {bg_running}")
        if not bg_running:
            _dbg("Iniciando backend em thread...")
            t = threading.Thread(target=_start_backend, daemon=True)
            t.start()

            # 2. Aguarda o servidor local responder
            _dbg("Aguardando backend...")
            if not wait_for_server():
                _dbg("Erro: backend não respondeu a tempo!")
                sys.exit(1)
            _dbg("Backend respondendo com sucesso.")

        # 3. Abre a janela nativa do Windows acelerada por GPU (Microsoft Edge WebView2)
        _dbg("Criando janela webview...")
        window = webview.create_window(
            title=title,
            url=URL,
            width=1280,
            height=780,
            min_size=(940, 620),
            background_color="#16171d",
            text_select=False,
        )

        icon_path = Path(__file__).parent / "imagens" / "app_icon.ico"
        if not icon_path.exists():
            icon_path = Path(__file__).parent / "imagens" / "icon.ico"
        icon_arg = str(icon_path.resolve()) if icon_path.exists() else None

        # Configura bandeja do sistema (System Tray) para manter o app vivo em segundo plano
        tray_icon = None

        def _show_window(icon=None, item=None):
            try:
                window.show()
                window.restore()
                hwnd = ctypes.windll.user32.FindWindowW(None, title)
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception as e:
                _dbg(f"show_window error: {e}")

        def _exit_app(icon=None, item=None):
            _dbg("Encerrando via ícone da bandeja...")
            try:
                if tray_icon:
                    tray_icon.stop()
            except Exception:
                pass
            import os
            os._exit(0)

        def _trigger_door_tray(icon=None, item=None):
            try:
                req = urllib.request.Request(
                    f"{URL}/api/doors/door_operacional/open",
                    data=b'{"source": "Bandeja Windows"}',
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=3):
                    pass
            except Exception as e:
                _dbg(f"Erro ao acionar porta pela bandeja: {e}")

        # Listener nativo de teclas rodando diretamente na sessão do desktop do usuário
        def _on_desktop_hotkey(door_id: str, hotkey: str):
            _dbg(f"Atalho nativo disparado no desktop: [{hotkey}] para porta {door_id}")
            try:
                body = f'{{"source": "Atalho Teclado ({hotkey})"}}'.encode("utf-8")
                req = urllib.request.Request(
                    f"{URL}/api/doors/{door_id}/open",
                    data=body,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=4) as resp:
                    _dbg(f"Disparo de porta via atalho concluído com sucesso (status {resp.status})")
            except Exception as e:
                _dbg(f"Erro ao disparar porta via atalho: {e}")

        from native_hotkeys import NativeHotkeyManager
        from config_manager import get_config_dir

        desktop_hotkey_mgr = NativeHotkeyManager(on_trigger_callback=_on_desktop_hotkey)

        def _sync_desktop_hotkeys():
            cfg_path = get_config_dir() / "doors_config.json"
            if not cfg_path.exists():
                cfg_path = Path(__file__).parent / "doors_config.json"
            if cfg_path.exists():
                try:
                    import json
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    if cfg.get("enabled", True):
                        desktop_hotkey_mgr.update_bindings(cfg.get("doors", []))
                    else:
                        desktop_hotkey_mgr.update_bindings([])
                except Exception as e:
                    _dbg(f"Erro ao carregar portas em _sync_desktop_hotkeys: {e}")

        _sync_desktop_hotkeys()
        desktop_hotkey_mgr.start()

        def _watch_doors_config():
            cfg_path = get_config_dir() / "doors_config.json"
            last_m = 0.0
            while True:
                try:
                    if cfg_path.exists():
                        m = cfg_path.stat().st_mtime
                        if m != last_m:
                            last_m = m
                            _sync_desktop_hotkeys()
                except Exception:
                    pass
                time.sleep(1.0)

        threading.Thread(target=_watch_doors_config, daemon=True).start()

        def _on_closing():
            _dbg("Janela solicitou fechamento: ocultando para a bandeja.")
            try:
                window.hide()
                return False  # Cancela o fechamento destrutivo do WebView
            except Exception as e:
                _dbg(f"_on_closing error: {e}")
                return True

        window.events.closing += _on_closing

        try:
            import pystray
            from PIL import Image

            if icon_path.exists():
                tray_img = Image.open(icon_path)
            else:
                tray_img = Image.new("RGBA", (32, 32), (0, 102, 204, 255))

            tray_menu = pystray.Menu(
                pystray.MenuItem("Abrir RemoteXPTI", _show_window, default=True),
                pystray.MenuItem("Acionar Porta Operacional [DEV]", _trigger_door_tray),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Sair", _exit_app),
            )

            tray_icon = pystray.Icon(
                "RemoteXPTI",
                tray_img,
                "RemoteXPTI - RDP Quick Launcher",
                tray_menu,
            )
            tray_icon.run_detached()
            _dbg("Bandeja do sistema (pystray) iniciada em segundo plano.")
        except Exception as e:
            _dbg(f"Erro ao inicializar pystray: {e}")

        _dbg(f"Chamando webview.start(icon={icon_arg})...")
        webview.start(debug=False, icon=icon_arg)
        _dbg("webview.start() finalizado normalmente.")

        # Se webview finalizou, encerra ícone e processo
        if desktop_hotkey_mgr:
            try:
                desktop_hotkey_mgr.stop()
            except Exception:
                pass
        if tray_icon:
            try:
                tray_icon.stop()
            except Exception:
                pass

        import os
        os._exit(0)

    except BaseException as e:
        import traceback
        _dbg(f"BaseException capturada: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise

if __name__ == "__main__":
    main()
