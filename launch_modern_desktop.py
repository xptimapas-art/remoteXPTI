"""
Inicializador Desktop Moderno do RemoteXPTI (Engine Edge WebView2 + React 18 + FastAPI).
Executa o backend assíncrono em segundo plano e abre a janela gráfica nativa com aceleração de hardware.
"""

import os
import sys
import threading
import time
import urllib.request
from pathlib import Path
import webview
import psutil

import desktop_backend

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
            proc_id = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            current_pid = os.getpid()
            if proc_id.value == 0 or proc_id.value == current_pid:
                return False
            try:
                proc = psutil.Process(proc_id.value)
                if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
                    return False
            except Exception:
                return False

            SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
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

        _dbg(f"Chamando webview.start(icon={icon_arg})...")
        webview.start(debug=False, icon=icon_arg)
        _dbg("webview.start() finalizado normalmente.")

        # Ao fechar a janela gráfica, encerra todo o processo e threads associadas
        import os
        os._exit(0)

    except BaseException as e:
        import traceback
        _dbg(f"BaseException capturada: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise

if __name__ == "__main__":
    main()
