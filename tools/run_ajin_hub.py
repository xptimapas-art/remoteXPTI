"""Run the existing AJIN dashboard alongside its scheduled collector.

Deploy with dashboard.py and logs_ONU metadata in the same directory.
The collector's CSV files and camera mapping remain in C:\\temp.
"""
import os
from pathlib import Path
import threading
import logging
from http.server import ThreadingHTTPServer

import dashboard


def configure():
    root = Path(__file__).resolve().parent
    metadata = root / "logs_ONU"
    metadata.mkdir(exist_ok=True)
    dashboard.LOGS_DIR = os.environ.get("AJIN_COLLECTOR_DIR", r"C:\temp")
    # These paths were initialized during import and stay in the hub directory.
    dashboard.CAMERAS_FILE = str(Path(dashboard.LOGS_DIR) / "onu_cameras.json")
    dashboard.puxa_logs = None  # No remote copy: the collector runs on this server.
    lock = threading.RLock()
    original_load = dashboard.load_data

    def load_data(*args, **kwargs):
        with lock:
            return original_load(*args, **kwargs)

    dashboard.load_data = load_data

    def log_access(handler):
        try:
            with (metadata / "dash_access.log").open("a", encoding="utf-8") as stream:
                stream.write(f"{handler.client_address[0]} {handler.command} {handler.path}\n")
        except OSError:
            pass

    dashboard.Handler._log_access = log_access
    return dashboard


def main():
    app = configure()
    # Prime once before listening. Every client gets a ready snapshot instead of
    # repeating the expensive scan of CSV history inside its HTTP request.
    original_load = app.load_data
    cached = {"15": original_load()}
    cache_lock = threading.Lock()

    def load_cached(window="15"):
        window = str(window)
        with cache_lock:
            data = cached.get(window)
        if data is None:
            data = original_load(window=window)
            with cache_lock:
                cached[window] = data
        return {**data, "server": dict(app.server_ping_state)}

    def refresh():
        while True:
            with cache_lock:
                windows = list(cached)
            for window in windows:
                try:
                    data = original_load(window=window)
                    with cache_lock:
                        cached[window] = data
                except Exception:
                    logging.exception("Falha ao atualizar o snapshot AJIN")
            threading.Event().wait(10)

    logging.basicConfig(filename=str(Path(__file__).resolve().parent / "hub.log"),
                        level=logging.WARNING, encoding="utf-8")
    app.load_data = load_cached
    threading.Thread(target=refresh, daemon=True).start()
    threading.Thread(target=app.server_ping_loop, daemon=True).start()
    threading.Thread(target=app.bench_ping_loop, daemon=True).start()
    # The Scheduled Task owns this process and restarts it after failure.
    # No browser or additional SNMP collector is launched here.
    with ThreadingHTTPServer(("0.0.0.0", app.PORT), app.Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
