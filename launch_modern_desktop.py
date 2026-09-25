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

def _apply_window_icon(window_title: str):
    import ctypes
    from pathlib import Path

    icon_path = Path(__file__).parent / "imagens" / "app_icon.ico"
    if not icon_path.exists():
        icon_path = Path(__file__).parent / "imagens" / "icon.ico"
    if not icon_path.exists():
        return

    icon_str = str(icon_path.resolve())
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    LR_DEFAULTSIZE = 0x00000040
    WM_SETICON = 0x0080
    GCLP_HICON = -14
    GCLP_HICONSM = -34

    # Poll for window handle up to 6 seconds
    start_time = time.time()
    while time.time() - start_time < 6.0:
        time.sleep(0.25)
        hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
        if hwnd:
            try:
                # 32x32 big icon
                hicon_big = ctypes.windll.user32.LoadImageW(
                    None, icon_str, IMAGE_ICON, 32, 32, LR_LOADFROMFILE
                )
                # 16x16 small icon
                hicon_small = ctypes.windll.user32.LoadImageW(
                    None, icon_str, IMAGE_ICON, 16, 16, LR_LOADFROMFILE
                )
                if not hicon_big:
                    hicon_big = ctypes.windll.user32.LoadImageW(
                        None, icon_str, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
                    )
                if not hicon_small:
                    hicon_small = hicon_big

                if hicon_big:
                    ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 1, hicon_big)
                if hicon_small:
                    ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 0, hicon_small)

                # Set class icon for Taskbar and Alt+Tab
                try:
                    if ctypes.sizeof(ctypes.c_void_p) == 8:
                        if hicon_big:
                            ctypes.windll.user32.SetClassLongPtrW(hwnd, GCLP_HICON, hicon_big)
                        if hicon_small:
                            ctypes.windll.user32.SetClassLongPtrW(hwnd, GCLP_HICONSM, hicon_small)
                    else:
                        if hicon_big:
                            ctypes.windll.user32.SetClassLongW(hwnd, GCLP_HICON, hicon_big)
                        if hicon_small:
                            ctypes.windll.user32.SetClassLongW(hwnd, GCLP_HICONSM, hicon_small)
                except Exception:
                    pass
                break
            except Exception:
                pass

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

    # Permite agrupamento e ícone próprio na barra de tarefas do Windows
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("XPTI.RemoteXPTI.Modern.App")
    except Exception:
        pass

    # Se a janela já estiver aberta ou o backend já estiver ativo, restaura foco e encerra
    if focus_existing_instance(title) or is_backend_running():
        focus_existing_instance(title)
        sys.exit(0)

    # 1. Inicia o backend FastAPI + WebSockets em segundo plano
    t = threading.Thread(target=_start_backend, daemon=True)
    t.start()

    # 2. Aguarda o servidor local responder
    if not wait_for_server():
        print("Erro: O backend local não respondeu a tempo.")
        sys.exit(1)

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

    icon_path = Path(__file__).parent / "imagens" / "app_icon.ico"
    if not icon_path.exists():
        icon_path = Path(__file__).parent / "imagens" / "icon.ico"
    icon_arg = str(icon_path.resolve()) if icon_path.exists() else None

    webview.start(debug=False, icon=icon_arg)

if __name__ == "__main__":
    main()
