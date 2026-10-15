"""
Módulo de Gerenciamento de Telemetria das ONUs Ajin (RemoteXPTI).
Consome o endpoint REST do servidor coletor da empresa (192.168.190.187:3000)
com cache em disco, polling em segundo plano e zero sobrecarga de CPU.
"""

import csv
from datetime import datetime
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
from runtime_paths import get_profile_dir

DEFAULT_HUB_HOST = "192.168.190.187:3000"
FALLBACK_HUB_HOST = "192.168.12.10:3000"
COORDINATES_UNSET = object()


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
        self._active_hub_host = None
        self._collector_status = "connecting"
        self._checked_at = None
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
        self._fetch_callbacks = []
        self._pending_labels = {}
        self._pending_deletions = {}
        self._listeners: List[Callable[[], None]] = []

        # Diretório de cache local
        self._cache_dir = get_profile_dir() / "ajin_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self._cache_dir / "telemetry_cache.json"

        # Carrega cache prévio para exibição instantânea ao abrir
        self._load_disk_cache()

        self._stop_event = threading.Event()

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
            with self._lock:
                tmp = str(self._cache_file) + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._telemetry, f, ensure_ascii=False)
                os.replace(tmp, self._cache_file)
        except Exception:
            pass

    def get_data(self) -> Dict[str, Any]:
        with self._lock:
            data = dict(self._telemetry)
            data["collector"] = {
                "status": self._collector_status,
                "endpoint": self._active_hub_host or self.hub_host,
                "checked_at": self._checked_at,
            }
        data["stale"] = data["collector"]["status"] != "online"
        stamp = str(data.get("coleta_formatted", "")).replace(" às ", " ")
        try:
            collected = datetime.strptime(stamp, "%d/%m/%Y %H:%M:%S")
            age = (datetime.now() - collected).total_seconds()
            data["stale"] |= age > 300 or age < -60
        except ValueError:
            data["stale"] = True
        return data

    def fetch_telemetry_async(
        self,
        force: bool = False,
        callback: Optional[Callable[[bool], None]] = None,
    ):
        """Dispara a busca em thread separada para nunca travar a interface."""
        now = time.monotonic()
        with self._lock:
            recent = not force and (now - self._last_fetch_time) < 3.0 and self._collector_status == "online"
            if not recent:
                if callback:
                    self._fetch_callbacks.append(callback)
                if self._is_fetching:
                    return
                self._is_fetching = True
        if recent:
            if callback:
                callback(True)
            return

        def _worker():
            ok = False
            try:
                res = self._fetch_from_hub()
                self._validate_telemetry(res)
                with self._lock:
                    res = self._merge_pending_labels(res)
                    self._telemetry = res
                    self._last_fetch_time = time.monotonic()
                    self._collector_status = "online"
                    self._checked_at = datetime.now().isoformat(timespec="seconds")
                self._save_disk_cache()
                ok = True
            except Exception as e:
                with self._lock:
                    self._collector_status = "unavailable"
                    self._checked_at = datetime.now().isoformat(timespec="seconds")
                log.warning(f"[AjinManager] Falha ao sincronizar telemetria: {e}")
            finally:
                # Failure is also an update: show cached data as outdated.
                with self._lock:
                    self._is_fetching = False
                    callbacks, self._fetch_callbacks = self._fetch_callbacks, []
                self._notify_listeners()
                for listener in callbacks:
                    try:
                        listener(ok)
                    except Exception:
                        log.exception('[AjinManager] Falha ao concluir consulta')

        threading.Thread(target=_worker, daemon=True).start()

    def _fetch_from_hub(self) -> Optional[Dict[str, Any]]:
        """Tenta o servidor AJIN e, depois, o painel LAN legado."""
        last_error = None
        for host in dict.fromkeys((self.hub_host, FALLBACK_HUB_HOST)):
            req = urllib.request.Request(
                f"http://{host}/data", headers={"User-Agent": "RemoteXPTI-Client/1.0"}
            )
            try:
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    if resp.status != 200:
                        raise ValueError("Resposta inesperada do coletor AJIN")
                    data = json.loads(resp.read().decode("utf-8"))
                    self._validate_telemetry(data)
                    with self._lock:
                        self._active_hub_host = host
                    return data
            except Exception as exc:
                last_error = exc
        raise last_error

    @staticmethod
    def _validate_telemetry(data):
        if not isinstance(data, dict) or not isinstance(data.get("rows"), list) or any(
            not isinstance(row, dict) for row in data["rows"]
        ):
            raise ValueError("Telemetria AJIN inválida: lista de dispositivos ausente")

    def _hub_url(self, path):
        with self._lock:
            host = self._active_hub_host or self.hub_host
        return f"http://{host}{path}"

    def _merge_pending_labels(self, data):
        """Keep acknowledged edits visible while the hub refreshes its snapshot."""
        rows = []
        now = time.monotonic()
        self._pending_deletions = {key:deadline for key,deadline in self._pending_deletions.items()
                                   if deadline > now}
        for row in data['rows']:
            key = (row.get('port'), str(row.get('id')))
            if key in self._pending_deletions:
                continue
            pending = self._pending_labels.get(key)
            if pending:
                changes, deadline = pending
                if now >= deadline or all(row.get(field) == value for field, value in changes.items()):
                    self._pending_labels.pop(key, None)
                else:
                    row = {**row, **changes}
            rows.append(row)
        self._pending_labels = {key:value for key,value in self._pending_labels.items() if value[1] > now}
        result = {**data, 'rows': rows}
        if len(rows) != len(data['rows']):
            result['total'] = len(rows)
            result['online'] = sum(str(row.get('status', '')).lower() == 'online' for row in rows)
            result['offline'] = sum(str(row.get('status', '')).lower() == 'offline' for row in rows)
            if isinstance(data.get('active_problems'), list):
                result['active_problems'] = [problem for problem in data['active_problems']
                    if (problem.get('port'), str(problem.get('onu_id'))) not in self._pending_deletions]
        return result

    def update_label(
        self,
        port: str,
        onu_id: str,
        name: Optional[str] = None,
        desc: Optional[str] = None,
        notes: Optional[str] = None,
        map_enabled: Optional[bool] = None,
        latitude=COORDINATES_UNSET,
        longitude=COORDINATES_UNSET,
    ) -> bool:
        """Envia atualização de nome de ponto ou rua para o servidor hub."""
        has_location = latitude is not COORDINATES_UNSET or longitude is not COORDINATES_UNSET
        url = self._hub_url('/label' if notes is None and map_enabled is None and not has_location else '/api/point_label')
        values = {"port": port, "id": str(onu_id), "name": name, "desc": desc}
        if notes is not None:
            values['notes'] = notes
        if map_enabled is not None:
            values['map_enabled'] = map_enabled
        if has_location:
            values.update(latitude=latitude, longitude=longitude)
        payload = json.dumps(values).encode('utf-8')
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
                    acknowledgement = json.loads(resp.read().decode('utf-8'))
                    if acknowledgement.get('ok') is not True or (notes is not None and acknowledgement.get('notes_saved') is not True):
                        return False
                    if map_enabled is not None and acknowledgement.get('map_saved') is not True:
                        return False
                    if has_location and acknowledgement.get('coordinates_saved') is not True:
                        return False
                    changes = {key:value for key,value in {'name':name, 'desc':desc, 'notes':notes, 'map_enabled':map_enabled}.items() if value is not None}
                    if has_location:
                        changes.update(latitude=latitude, longitude=longitude, coordinates_shared=True)
                    with self._lock:
                        self._pending_labels[(port, str(onu_id))] = (changes, time.monotonic() + 30)
                        self._telemetry = self._merge_pending_labels(self._telemetry)
                    self._save_disk_cache()
                    self._notify_listeners()
                    return True
        except Exception as e:
            log.warning(f"[AjinManager] Erro ao salvar label: {e}")
        return False

    save_label = update_label

    def _hub_json(self, path: str, payload=None):
        """Read the collector contract, including negative acknowledgements on HTTP 200."""
        req = urllib.request.Request(
            self._hub_url(path),
            data=None if payload is None else json.dumps(payload).encode('utf-8'),
            headers={'Content-Type':'application/json', 'User-Agent':'RemoteXPTI-Client'},
            method='GET' if payload is None else 'POST',
        )
        with urllib.request.urlopen(req, timeout=8.0) as response:
            result = json.loads(response.read().decode('utf-8'))
            if response.status != 200 or not isinstance(result, dict):
                raise ValueError('Resposta inválida do coletor AJIN')
            if payload is not None and result.get('ok') is not True:
                raise ValueError('O coletor não confirmou a operação')
            return result

    def scan_onus(self):
        """Return the discovery table from the existing collector, without changing the OLT."""
        result = self._hub_json('/api/scan')
        if not isinstance(result.get('devices'), list) or any(
            not isinstance(row, dict) or not row.get('port') or row.get('id') is None
            or not isinstance(row.get('is_registered'), bool) for row in result['devices']
        ):
            raise ValueError('Lista de descoberta inválida')
        return result

    def register_onus(self, devices) -> bool:
        # Reject stale selections: an ONU ID may have been reassigned to a new MAC.
        current = {(str(row['port']), str(row['id'])):row for row in self.scan_onus()['devices']}
        for device in devices:
            row = current.get((device['port'], str(device['id'])))
            if not row or row['is_registered'] or str(row.get('serial', '')).upper() != device['serial'].upper():
                raise ValueError('A descoberta mudou. Re-escaneie e selecione as ONUs novamente.')
        try:
            self._hub_json('/api/add_devices', devices)
            with self._lock:
                for device in devices:
                    self._pending_deletions.pop((device['port'], str(device['id'])), None)
            self.fetch_telemetry_async(force=True)
            return True
        except Exception as exc:
            log.warning(f'[AjinManager] Erro ao homologar ONUs: {exc}')
            return False

    def delete_onu(self, port: str, onu_id: str) -> bool:
        """Remove the registration only after an explicit collector acknowledgement."""
        try:
            self._hub_json('/delete_onu', {'port':port, 'id':str(onu_id)})
            with self._lock:
                key = (port, str(onu_id))
                self._pending_labels.pop(key, None)
                self._pending_deletions[key] = time.monotonic() + 30
                self._telemetry = self._merge_pending_labels(self._telemetry)
            self._save_disk_cache()
            self._notify_listeners()
            self.fetch_telemetry_async(force=True)
            return True
        except Exception as exc:
            log.warning(f'[AjinManager] Erro ao excluir ONU: {exc}')
        return False

    def trigger_camera_sync(self) -> bool:
        """Dispara a sincronização de câmeras via ARP no servidor."""
        url = self._hub_url("/api/sync_cameras")
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
        url = self._hub_url(f"/api/ping_camera?ip={urllib.parse.quote(ip)}")
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

    def stop(self):
        self._stop_event.set()
