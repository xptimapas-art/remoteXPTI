import sys
import ctypes
import multiprocessing

def enable_high_dpi_awareness():
    """Habilita reconhecimento de alta densidade de pixels no Windows para fontes nítidas."""
    if sys.platform == "win32":
        try:
            # Per-monitor DPI aware
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        try:
            # Associa explicitamente o ID do app para a barra de tarefas/bandeja exibir o ícone customizado
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("xpti.remotexpti.rdp.launcher")
        except Exception:
            pass

def main():
    enable_high_dpi_awareness()
    from logger import log
    from version import CURRENT_VERSION
    log.info(f"=== Iniciando RemoteXPTI v{CURRENT_VERSION} ===")
    from app import RemoteXPTIApp
    app = RemoteXPTIApp()
    app.mainloop()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
