"""
Bridge Autônomo de Sincronização de Telemetria das ONUs Ajin.
Monitora a chegada de novas coletas geradas pelo servidor da Ajin e compila
automaticamente o snapshot leve, mantendo a nuvem e o cache local sempre atualizados.
Totalmente desacoplado e independente da rotina existente da Ajin.
"""

import os
import sys
import glob
import time
import json
from pathlib import Path
from datetime import datetime

from ajin_manager import AjinManager, LOCAL_MONITORAMENTO_DIR
from logger import log


class AjinSyncBridge:
    """Monitor independente de novas coletas da Ajin."""

    def __init__(self, watch_dir: Path = LOCAL_MONITORAMENTO_DIR, poll_interval: int = 20):
        self.watch_dir = Path(watch_dir)
        self.poll_interval = max(5, poll_interval)
        self._last_processed_file: str = ""
        self._running = False

    def check_and_sync_once(self) -> bool:
        """Verifica se há novo CSV de coleta e compila o snapshot se necessário."""
        if not self.watch_dir.exists():
            return False

        csv_files = sorted(glob.glob(str(self.watch_dir / "onus_*.csv")))
        if not csv_files:
            return False

        latest_csv = os.path.basename(csv_files[-1])
        if latest_csv == self._last_processed_file:
            return False

        log.info(f"[AjinSyncBridge] Nova coleta detectada: {latest_csv}. Compilando snapshot leve...")
        self._last_processed_file = latest_csv

        try:
            mgr = AjinManager()
            snap = mgr._compile_from_local_csv()
            if snap:
                # Salva localmente
                out_path = self.watch_dir / "telemetry_current.json"
                tmp = str(out_path) + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(snap, f, ensure_ascii=False, indent=2)
                os.replace(tmp, out_path)

                # Força reload no AjinManager
                mgr.fetch_telemetry(force=True)
                log.info(f"[AjinSyncBridge] Snapshot compilado: {snap['summary']['total']} ONUs ({snap['summary']['online']} online).")
                return True
        except Exception as e:
            log.warning(f"[AjinSyncBridge] Erro ao compilar snapshot: {e}")

        return False

    def start_background_loop(self):
        """Inicia monitoramento contínuo em segundo plano."""
        import threading
        if self._running:
            return
        self._running = True

        def worker():
            log.info(f"[AjinSyncBridge] Monitoramento independente iniciado em {self.watch_dir} (intervalo={self.poll_interval}s)...")
            while self._running:
                try:
                    self.check_and_sync_once()
                except Exception as ex:
                    log.warning(f"[AjinSyncBridge] Erro no ciclo de sincronização: {ex}")
                time.sleep(self.poll_interval)

        threading.Thread(target=worker, daemon=True).start()

    def stop(self):
        self._running = False


if __name__ == "__main__":
    bridge = AjinSyncBridge()
    bridge.check_and_sync_once()
