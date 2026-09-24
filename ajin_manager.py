"""
Módulo de Gerenciamento de Telemetria das ONUs Ajin (RemoteXPTI).
Consome o endpoint REST do servidor coletor da empresa (192.168.12.10:3000)
com cache em disco, polling em segundo plano e zero sobrecarga de CPU.
"""

import csv
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

from logger import log

DEFAULT_HUB_HOST = "192.168.12.10:3000"


class AjinManager:
    """Gerenciador central de telemetria das ONUs da Ajin."""

    _instance: Optional["AjinManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AjinManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._lock = threading.Lock()
        self.hub_host = DEFAULT_HUB_HOST
        self._telemetry: Dict[str, Any] = {
            "total": 0,
            "online": 0,
            "offline": 0,
            "total_cameras": 0,
            "active_problems": 0,
            "ports": {},
            "rows": [],
            "events": [],
            "events_history": [],
            "unregistered": [],
            "coleta_formatted": "-",
            "server": {"online": False, "ip": "-", "checked_at": "-"},
            "olt": {"modelo": "-", "ip": "-"},
        }
        self._last_fetch_time: float = 0
        self._is_fetching: bool = False
        self._listeners: List[Callable[[], None]] = []

        # Diretório de cache local
        appdata = os.environ.get("LOCALAPPDATA", str(Path.home()))
        self._cache_dir = Path(appdata) / "RemoteXPTI" / "ajin_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self._cache_dir / "telemetry_cache.json"

        # Carrega cache prévio para exibição instantânea ao abrir
        self._load_disk_cache()

        # Thread de auto-refresh em segundo plano (a cada 10 segundos)
        self._stop_event = threading.Event()
        self._poller_thread = threading.Thread(
            target=self._background_poller, daemon=True
        )
        self._poller_thread.start()

    def add_listener(self, callback: Callable[[], None]):
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify_listeners(self):
        callbacks = list(self._listeners)
        for cb in callbacks:
            try:
                cb()
            except Exception as e:
                log.warning(f"[AjinManager] Erro no listener: {e}")

    def _load_disk_cache(self):
        if self._cache_file.exists():
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "rows" in data:
                        self._telemetry = data
            except Exception:
                pass

    def _save_disk_cache(self):
        try:
            tmp = str(self._cache_file) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._telemetry, f, ensure_ascii=False)
            os.replace(tmp, self._cache_file)
        except Exception:
            pass

    def get_data(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._telemetry)

    def fetch_telemetry_async(
        self,
        force: bool = False,
        callback: Optional[Callable[[bool], None]] = None,
    ):
        """Dispara a busca em thread separada para nunca travar a interface."""
        now = time.time()
        if (
            not force
            and (now - self._last_fetch_time) < 3.0
            and self._telemetry.get("rows")
        ):
            if callback:
                callback(True)
            return

        if self._is_fetching:
            return

        def _worker():
            self._is_fetching = True
            ok = False
            try:
                res = self._fetch_from_hub()
                if res:
                    with self._lock:
                        self._telemetry = res
                    self._last_fetch_time = time.time()
                    self._save_disk_cache()
                    self._notify_listeners()
                    ok = True
            except Exception as e:
                log.warning(f"[AjinManager] Falha ao sincronizar telemetria: {e}")
            finally:
                self._is_fetching = False
                if callback:
                    callback(ok)

        threading.Thread(target=_worker, daemon=True).start()

    def _fetch_from_hub(self) -> Optional[Dict[str, Any]]:
        """Faz a requisição ultraleve ao servidor da empresa."""
        url = f"http://{self.hub_host}/data"
        req = urllib.request.Request(
            url, headers={"User-Agent": "RemoteXPTI-Client/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                if resp.status == 200:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw)
        except Exception as e:
            # Fallback para IP ZeroTier da Ajin se LAN falhar
            fallback_url = "http://192.168.190.187:3000/data"
            try:
                with urllib.request.urlopen(fallback_url, timeout=3.0) as resp:
                    if resp.status == 200:
                        return json.loads(resp.read().decode("utf-8"))
            except Exception:
                pass
            raise e
        return None

    def update_label(
        self,
        port: str,
        onu_id: str,
        name: Optional[str] = None,
        desc: Optional[str] = None,
    ) -> bool:
        """Envia atualização de nome de ponto ou rua para o servidor hub."""
        url = f"http://{self.hub_host}/label"
        payload = json.dumps(
            {"port": port, "id": str(onu_id), "name": name, "desc": desc}
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "RemoteXPTI-Client",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    self.fetch_telemetry_async(force=True)
                    return True
        except Exception as e:
            log.warning(f"[AjinManager] Erro ao salvar label: {e}")
        return False

    def delete_onu(self, port: str, onu_id: str) -> bool:
        """Remove ou ignora uma ONU do monitoramento."""
        url = f"http://{self.hub_host}/delete_onu"
        payload = json.dumps({"port": port, "id": str(onu_id)}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "RemoteXPTI-Client",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    self.fetch_telemetry_async(force=True)
                    return True
        except Exception as e:
            log.warning(f"[AjinManager] Erro ao excluir ONU: {e}")
        return False

    def trigger_camera_sync(self) -> bool:
        """Dispara a sincronização de câmeras via ARP no servidor."""
        url = f"http://{self.hub_host}/api/sync_cameras"
        req = urllib.request.Request(
            url,
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status == 200:
                    self.fetch_telemetry_async(force=True)
                    return True
        except Exception as e:
            log.warning(f"[AjinManager] Erro no sync_cameras: {e}")
        return False

    def ping_camera(self, ip: str) -> bool:
        """Testa conectividade de uma câmera via API do hub."""
        url = f"http://{self.hub_host}/api/ping_camera?ip={urllib.parse.quote(ip)}"
        try:
            with urllib.request.urlopen(url, timeout=3.0) as resp:
                if resp.status == 200:
                    res = json.loads(resp.read().decode("utf-8"))
                    return res.get("online", False)
        except Exception:
            pass
        return False

    def export_csv(self, dest_path: str) -> bool:
        """Exporta os dados atuais para um arquivo CSV no computador local."""
        data = self.get_data()
        rows = data.get("rows", [])
        if not rows:
            return False

        try:
            with open(dest_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "Nome_do_Ponto",
                        "Canal_OLT",
                        "Em_Funcionamento",
                        "Serial_MAC",
                        "Descricao_Rua",
                        "Fabricante",
                        "Tempo_no_Status",
                        "Status_Desde",
                        "Cameras",
                    ]
                )
                for r in rows:
                    p_name = r.get("name") or "-"
                    canal = f"{r.get('port')}_{str(r.get('id')).zfill(3)}"
                    stt = "Sim" if r.get("status") == "Online" else "Não"
                    cams = "; ".join(
                        [
                            c.get("ip", "")
                            for c in r.get("cameras", [])
                            if c.get("ip")
                        ]
                    )
                    writer.writerow(
                        [
                            p_name,
                            canal,
                            stt,
                            r.get("serial", "-"),
                            r.get("desc", ""),
                            r.get("vendor", "-"),
                            r.get("uptime", "-"),
                            r.get("status_since", "-"),
                            cams,
                        ]
                    )
            return True
        except Exception as e:
            log.warning(f"[AjinManager] Erro ao exportar CSV: {e}")
            return False

    def _background_poller(self):
        """Loop contínuo em background para manter os dados sempre frescos (10s)."""
        time.sleep(1.0)
        while not self._stop_event.is_set():
            try:
                self.fetch_telemetry_async(force=True)
            except Exception:
                pass
            self._stop_event.wait(10.0)

    def stop(self):
        self._stop_event.set()
