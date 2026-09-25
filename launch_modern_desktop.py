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

def main():
    # 1. Inicia o backend FastAPI + WebSockets em segundo plano
    t = threading.Thread(target=_start_backend, daemon=True)
    t.start()

    # 2. Aguarda o servidor local responder
    if not wait_for_server():
        print("Erro: O backend local não respondeu a tempo.")
        sys.exit(1)

    # 3. Abre a janela nativa do Windows acelerada por GPU (Microsoft Edge WebView2)
    window = webview.create_window(
        title="RemoteXPTI - Painel Operacional NOC & VMS",
        url=URL,
        width=1280,
        height=780,
        min_size=(940, 620),
        background_color="#0d1117",
        text_select=False,
        easy_drag=True
    )

    webview.start(debug=False)

if __name__ == "__main__":
    main()
