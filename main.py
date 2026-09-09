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

def main():
    enable_high_dpi_awareness()
    from app import RemoteXPTIApp
    app = RemoteXPTIApp()
    app.mainloop()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
