"""
Inicializador Desktop Moderno do RemoteXPTI (Engine Edge WebView2 + React 18 + FastAPI).
Executa o backend assíncrono em segundo plano e abre a janela gráfica nativa com aceleração de hardware.
"""

import sys
import threading
import time
import urllib.request
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

def _apply_window_icon(window_title: str):
    time.sleep(1.0)
    try:
        import ctypes
        from pathlib import Path
        icon_path = Path(__file__).parent / "imagens" / "app_icon.ico"
        if not icon_path.exists():
            icon_path = Path(__file__).parent / "imagens" / "icon.ico"
        if icon_path.exists():
            hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
            if hwnd:
                IMAGE_ICON = 1
                LR_LOADFROMFILE = 0x00000010
                LR_DEFAULTSIZE = 0x00000040
                hicon = ctypes.windll.user32.LoadImageW(
                    None, str(icon_path.resolve()), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
                )
                if hicon:
                    WM_SETICON = 0x0080
                    ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 1, hicon)  # ICON_BIG
                    ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 0, hicon)  # ICON_SMALL
    except Exception:
        pass

def main():
    # 1. Inicia o backend FastAPI + WebSockets em segundo plano
    t = threading.Thread(target=_start_backend, daemon=True)
    t.start()

    # 2. Aguarda o servidor local responder
    if not wait_for_server():
        print("Erro: O backend local não respondeu a tempo.")
        sys.exit(1)

    title = "RemoteXPTI - RDP Quick Launcher"

    # Thread para aplicar o ícone oficial da XPTi na barra de tarefas e janela
    threading.Thread(target=_apply_window_icon, args=(title,), daemon=True).start()

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

    webview.start(debug=False)

if __name__ == "__main__":
    main()
