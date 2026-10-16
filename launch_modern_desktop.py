import sys

if len(sys.argv) > 1 and sys.argv[1] == '--verify-video-runtime':
    if len(sys.argv) != 3:
        raise SystemExit(2)
    from video_runtime_check import check_video_runtime
    raise SystemExit(0 if check_video_runtime(sys.argv[2]) else 1)

import ctypes
import os
import threading
import time
import urllib.request
from pathlib import Path
import webview
from windows_single_instance import WindowsSingleInstance
from desktop_lifecycle import stop_tray_icon
from runtime_paths import (get_profile_dir, get_window_title, get_mutex_name,
                           get_app_user_model_id, is_development)

import socket

def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

PORT = get_free_port()
URL = f"http://127.0.0.1:{PORT}"

def _dbg(msg: str):
    try:
        debug_file = get_profile_dir() / "logs" / "launch_debug.txt"
        debug_file.parent.mkdir(parents=True, exist_ok=True)
        with open(debug_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

_dbg(f"Módulo carregado (executable: {sys.executable})")

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

def main():
    title = get_window_title()
    _dbg("Entrou em main()...")
    
    # O backup de atualização é preservado para recuperação.

    instance = None
    tray_icon = None
    try:
        instance = WindowsSingleInstance(get_mutex_name())
        if instance.already_running:
            _dbg("Outra instância já está rodando (Mutex detectado). Trazendo para o foco e saindo.")
            instance.focus(title)
            return
        # Permite agrupamento e ícone próprio na barra de tarefas do Windows
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(get_app_user_model_id())
        except Exception as e:
            _dbg(f"SetCurrentProcessExplicitAppUserModelID: {e}")

        # 1. Inicia o backend FastAPI + WebSockets em segundo plano caso ainda nÃ£o esteja rodando
        bg_running = is_backend_running()
        _dbg(f"is_backend_running: {bg_running}")
        t = None
        if not bg_running:
            _dbg("Iniciando backend em thread...")
            t = threading.Thread(target=_start_backend, daemon=True)
            t.start()

        # 3. Abre a janela nativa do Windows acelerada por GPU (Microsoft Edge WebView2)
        _dbg("Criando janela webview...")
        
        loading_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body { background-color: #16171d; color: #ffffff; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; flex-direction: column; }
                .spinner { border: 4px solid rgba(255,255,255,0.1); width: 40px; height: 40px; border-radius: 50%; border-left-color: #09f; animation: spin 1s linear infinite; margin-bottom: 20px; }
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            </style>
        </head>
        <body>
            <div class="spinner"></div>
            <h2>Carregando RemoteXPTI...</h2>
        </body>
        </html>
        """

        # Client and DEV share the same window chrome; their profiles stay separate.
        integrated = True
        from desktop_window import DesktopWindow
        window_api = DesktopWindow(development=is_development())
        window = webview.create_window(
            title=title,
            url=URL if bg_running else None,
            html=loading_html if not bg_running else None,
            width=1280,
            height=780,
            min_size=(940, 620),
            background_color="#16171d",
            text_select=False,
            frameless=integrated,
            easy_drag=False,
            js_api=window_api,
        )
        if window_api:
            window_api._bind(window)
            window.events.shown += window_api._install_frame

        if not bg_running:
            def _wait_and_load():
                _dbg("Aguardando backend em thread separada...")
                start_t = time.time()
                success = False
                while time.time() - start_t < 90:
                    if is_backend_running(timeout=1):
                        success = True
                        break
                    if t and not t.is_alive():
                        _dbg("Backend thread died unexpectedly.")
                        break
                    time.sleep(0.3)
                
                if success:
                    _dbg("Backend respondendo, carregando URL.")
                    window.load_url(URL)
                else:
                    _dbg("Erro: backend nÃ£o respondeu a tempo ou falhou!")
                    try:
                        log_path = str(get_profile_dir() / "logs" / "launch_debug.txt")
                        # 0x15 = MB_RETRYCANCEL (5) + MB_ICONERROR (0x10)
                        resp = ctypes.windll.user32.MessageBoxW(0, f"O backend não respondeu (timeout 90s) ou falhou ao iniciar.\n\nVerifique os logs em:\n{log_path}\n\nDeseja tentar novamente?", "Erro ao iniciar - RemoteXPTI", 0x15)
                        if resp == 4: # IDRETRY
                            import subprocess
                            if getattr(sys, 'frozen', False):
                                subprocess.Popen(sys.argv)
                            else:
                                subprocess.Popen([sys.executable] + sys.argv)
                    except:
                        pass
                    stop_tray_icon(tray_icon)
                    os._exit(1)
            
            threading.Thread(target=_wait_and_load, daemon=True).start()

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
                instance.focus(title, current_only=True)
            except Exception as e:
                _dbg(f"show_window error: {e}")

        def _exit_app(icon=None, item=None):
            _dbg("Encerrando aplicativo e removendo ícone da bandeja...")
            stop_tray_icon(tray_icon)
            try:
                desktop_hotkey_mgr.stop()
            except Exception:
                pass
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

        def _trigger_facial_tray(icon=None, item=None):
            try:
                req = urllib.request.Request(
                    f"{URL}/api/doors/door_facial_hikvision/open",
                    data=b'{"source": "Bandeja Windows"}',
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=4) as resp:
                    _dbg(f"Disparo de facial pela bandeja concluído (status {resp.status})")
            except Exception as e:
                _dbg(f"Erro ao acionar facial pela bandeja: {e}")

        # Listener nativo de teclas rodando diretamente na sessÃ£o do desktop do usuÃ¡rio
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
                    _dbg(f"Disparo de porta via atalho concluÃ­do com sucesso (status {resp.status})")
            except Exception as e:
                _dbg(f"Erro ao disparar porta via atalho: {e}")

        from native_hotkeys import NativeHotkeyManager
        from config_manager import get_config_dir

        desktop_hotkey_mgr = NativeHotkeyManager(on_trigger_callback=_on_desktop_hotkey)

        def _sync_desktop_hotkeys():
            cfg_path = get_config_dir() / "doors_config.json"
            if not cfg_path.exists() and not is_development():
                cfg_path = Path(__file__).parent / "doors_config.json"
            if cfg_path.exists():
                try:
                    import json
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    if cfg.get("enabled", True) and cfg.get("hotkeys_enabled", True):
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
                pystray.MenuItem("Abrir " + ("RemoteXPTI DEV" if is_development() else "RemoteXPTI"), _show_window, default=True),
                pystray.MenuItem("Acionar Porta Operacional [DEV]", _trigger_door_tray),
                pystray.MenuItem("Acionar Facial Hikvision [DEV]", _trigger_facial_tray),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Sair", _exit_app),
            )

            tray_icon = pystray.Icon(
                "RemoteXPTI",
                tray_img,
                title,
                tray_menu,
            )
            tray_icon.run_detached()
            _dbg("Bandeja do sistema (pystray) iniciada em segundo plano.")
        except Exception as e:
            _dbg(f"Erro ao inicializar pystray: {e}")

        if is_development():
            def _reload_dev():
                _dbg('Recarregando interface DEV sem reiniciar processo ou bandeja.')
                window.load_url(URL)
            window_api._bind_dev_controls(reload=_reload_dev, stop=_exit_app)

        _dbg(f"Chamando webview.start(icon={icon_arg})...")
        webview.start(debug=False, icon=icon_arg)
        _dbg("webview.start() finalizado normalmente.")

        # Se webview finalizou, encerra Ã­cone e processo
        if desktop_hotkey_mgr:
            try:
                desktop_hotkey_mgr.stop()
            except Exception:
                pass
        stop_tray_icon(tray_icon)

        os._exit(0)

    except BaseException as e:
        if isinstance(e, SystemExit):
            raise
        import traceback
        tb = traceback.format_exc()
        msg = f"BaseException capturada: {type(e).__name__}: {e}\n{tb}"
        _dbg(msg)
        try:
            ctypes.windll.user32.MessageBoxW(0, f"Ocorreu um erro fatal ao iniciar:\n\n{type(e).__name__}: {e}", "RemoteXPTI - Erro Fatal", 0x10)
        except:
            pass
        raise
    finally:
        stop_tray_icon(tray_icon)
        if instance:
            instance.close()

if __name__ == "__main__":
    main()



