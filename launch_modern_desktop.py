"""
Inicializador Desktop Moderno do RemoteXPTI (Engine Edge WebView2 + React 18 + FastAPI).
Executa o backend assíncrono em segundo plano e abre a janela gráfica nativa com aceleração de hardware.
"""

import sys
import threading
import time
import urllib.request
from pathlib import Path
import webview

import desktop_backend

PORT = 8765
URL = f"http://127.0.0.1:{PORT}"

def _start_backend():
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

def focus_existing_instance(window_title: str) -> bool:
    try:
        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
        if hwnd:
            SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False

def main():
    title = "RemoteXPTI - RDP Quick Launcher"

    try:
        # Permite agrupamento e ícone próprio na barra de tarefas do Windows
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("XPTI.RemoteXPTI.Modern.App")
        except Exception:
            pass

        # Se a janela gráfica já estiver aberta e visível, restaura foco e encerra processo duplicado
        if focus_existing_instance(title):
            sys.exit(0)

        # 1. Inicia o backend FastAPI + WebSockets em segundo plano caso ainda não esteja rodando
        if not is_backend_running():
            t = threading.Thread(target=_start_backend, daemon=True)
            t.start()

            # 2. Aguarda o servidor local responder
            if not wait_for_server():
                sys.exit(1)

        # 3. Abre a janela nativa do Windows acelerada por GPU (Microsoft Edge WebView2)
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

        webview.start(debug=False, icon=icon_arg)

        # Ao fechar a janela gráfica, encerra todo o processo e threads associadas
        import os
        os._exit(0)

    except SystemExit:
        raise
    except Exception:
        import traceback
        try:
            log_file = Path(__file__).parent / "launch_error.log"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {traceback.format_exc()}\n")
        except Exception:
            pass
        raise

if __name__ == "__main__":
    main()
