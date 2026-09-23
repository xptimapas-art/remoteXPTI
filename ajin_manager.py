"""
Módulo de Gerenciamento de Telemetria das ONUs Ajin (RemoteXPTI).
Consome o snapshot consolidado gerado pelo servidor da empresa com processamento ultraleve (< 5ms).
Suporta leitura direta via Supabase REST e fallback offline imediato para arquivos locais.
"""

import os
import sys
import json
import time
import glob
import re
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable
from datetime import datetime

from config_manager import ConfigManager
from logger import log

# Caminho local alternativo para fallback se executando no mesmo computador da empresa
LOCAL_MONITORAMENTO_DIR = Path(r"c:\Users\XPTI\Documents\vscode\monitoramentoAJIN\logs_ONU")


class AjinManager:
    """Gerenciador de dados das ONUs da Ajin com cache e zero sobrecarga de CPU."""

    _instance: Optional["AjinManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AjinManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._lock = threading.Lock()
        self._telemetry: Dict[str, Any] = {
            "id": "current",
            "collected_at": "",
            "summary": {
                "total": 0,
                "online": 0,
                "offline": 0,
                "availability_pct": 0.0,
                "ports": {
                    "Slot1-PON1": {"total": 0, "online": 0, "offline": 0},
                    "Slot1-PON2": {"total": 0, "online": 0, "offline": 0},
                    "Slot2-PON1": {"total": 0, "online": 0, "offline": 0},
                    "Slot2-PON2": {"total": 0, "online": 0, "offline": 0},
                }
            },
            "onus": [],
            "scanner": []
        }
        self._last_fetch_time: float = 0
        self._listeners: List[Callable[[], None]] = []
        self._cache_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RemoteXPTI" / "ajin_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self._cache_dir / "telemetry_cached.json"

        # Carrega cache prévio do disco para inicialização instantânea (0ms de espera)
        self._load_disk_cache()

    def add_listener(self, callback: Callable[[], None]):
        """Registra callback acionado quando novos dados forem recebidos."""
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
                    if isinstance(data, dict) and "onus" in data:
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

    def fetch_telemetry(self, force: bool = False) -> Dict[str, Any]:
        """
        Atualiza os dados de telemetria da Ajin.
        Aplica debounce de 4 segundos para evitar requisições redundantes.
        """
        now = time.time()
        if not force and (now - self._last_fetch_time) < 4.0:
            return self._telemetry

        self._last_fetch_time = now
        telemetry = None

        # 1. Tentativa via Supabase REST (Nuvem universal)
        telemetry = self._fetch_from_supabase()

        # 2. Se a nuvem não respondeu ou não tem dados, fallback para arquivo local
        if not telemetry:
            telemetry = self._fetch_from_local_files()

        if telemetry:
            with self._lock:
                self._telemetry = telemetry
            self._save_disk_cache()
            self._notify_listeners()

        return self._telemetry

    def _fetch_from_supabase(self) -> Optional[Dict[str, Any]]:
        """Consulta o snapshot consolidado no Supabase."""
        cfg = ConfigManager().get_supabase_config()
        if not cfg.get("enabled") or not cfg.get("url") or not cfg.get("key"):
            return None

        url = f"{cfg['url'].rstrip('/')}/rest/v1/ajin_telemetry?id=eq.current&select=*"
        headers = {
            "apikey": cfg["key"],
            "Authorization": f"Bearer {cfg['key']}",
            "Accept": "application/json",
            "User-Agent": "RemoteXPTI-Ajin/1.0"
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list) and len(data) > 0:
                        row = data[0]
                        return {
                            "id": "current",
                            "collected_at": row.get("collected_at", ""),
                            "summary": row.get("summary", {}),
                            "onus": row.get("onus", []),
                            "scanner": row.get("scanner", [])
                        }
        except urllib.error.HTTPError as he:
            if he.code != 404:
                log.warning(f"[AjinManager] Supabase HTTP {he.code}: {he.reason}")
        except Exception as e:
            log.warning(f"[AjinManager] Falha ao consultar Supabase: {e}")
        return None

    def _fetch_from_local_files(self) -> Optional[Dict[str, Any]]:
        """Fallback offline lendo os arquivos sincronizados em monitoramentoAJIN/logs_ONU."""
        if not LOCAL_MONITORAMENTO_DIR.exists():
            return None

        # Checa se já existe o telemetry_current.json gerado pelo coletor
        snap_file = LOCAL_MONITORAMENTO_DIR / "telemetry_current.json"
        if snap_file.exists():
            try:
                with open(snap_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "onus" in data:
                        return data
            except Exception:
                pass

        # Se ainda não existir telemetry_current.json, compila na hora a partir do último CSV
        try:
            return self._compile_from_local_csv()
        except Exception as e:
            log.error(f"[AjinManager] Erro no fallback local de telemetria: {e}")
            return None

    def _compile_from_local_csv(self) -> Optional[Dict[str, Any]]:
        reg_file = LOCAL_MONITORAMENTO_DIR / "onus_registered.json"
        labels_file = LOCAL_MONITORAMENTO_DIR / "onus_labels.json"
        cams_file = LOCAL_MONITORAMENTO_DIR / "onu_cameras.json"
        tracker_file = LOCAL_MONITORAMENTO_DIR / "onu_state_tracker.json"

        registered = {}
        if reg_file.exists():
            with open(reg_file, encoding="utf-8") as f:
                registered = json.load(f)

        labels = {}
        if labels_file.exists():
            with open(labels_file, encoding="utf-8") as f:
                labels = json.load(f)

        cameras = {}
        if cams_file.exists():
            with open(cams_file, encoding="utf-8") as f:
                cameras = json.load(f)

        tracker = {}
        if tracker_file.exists():
            with open(tracker_file, encoding="utf-8") as f:
                tracker = json.load(f)

        csv_files = sorted(glob.glob(str(LOCAL_MONITORAMENTO_DIR / "onus_*.csv")))
        if not csv_files:
            return None

        latest_csv = csv_files[-1]
        raw_status = {}
        import csv
        with open(latest_csv, newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                sp = row.get("Slot-PON", "").strip()
                oid = row.get("ONU_ID", "").strip()
                st = row.get("Status", "").strip()
                ser = row.get("Serial", "").strip()
                if sp and oid:
                    raw_status[f"{sp}|{oid}"] = {"status": st, "serial": ser}

        now = datetime.now()
        now_iso = now.isoformat()

        onus_list = []
        ports_summary = {
            "Slot1-PON1": {"total": 0, "online": 0, "offline": 0},
            "Slot1-PON2": {"total": 0, "online": 0, "offline": 0},
            "Slot2-PON1": {"total": 0, "online": 0, "offline": 0},
            "Slot2-PON2": {"total": 0, "online": 0, "offline": 0},
        }

        online_count = 0
        offline_count = 0

        # Helper local para prefixos
        def local_vendor_of(s):
            su = (s or "").upper()
            if su.startswith("00A10203"):
                return "C-Data"
            if su.startswith("001946"):
                return "Cianet / CTS"
            if su.startswith("8014A8"):
                return "Cianet CTS 2702B"
            return "Outro"

        def local_parse_label(val):
            if isinstance(val, dict):
                return val.get("name", "").strip(), val.get("desc", "").strip()
            if isinstance(val, str):
                v = val.strip()
                m_leg = re.match(r"^(?:P(?:onto)?[_\s-]*)(\d+)\s*(?:[-–—\s/]\s*(.*))?$", v, re.IGNORECASE)
                if m_leg:
                    return f"Ponto {int(m_leg.group(1)):02d}", (m_leg.group(2) or "").strip()
                return v, ""
            return "", ""

        def local_format_dur(secs):
            if secs < 0:
                secs = 0
            d = int(secs // 86400)
            h = int((secs % 86400) // 3600)
            m = int((secs % 3600) // 60)
            p = []
            if d > 0: p.append(f"{d}d")
            if h > 0 or d > 0: p.append(f"{h}h")
            p.append(f"{m}m")
            return " ".join(p) if p else "< 1m"

        for key, reg_mac in registered.items():
            parts = key.split("|")
            if len(parts) != 2:
                continue
            port, oid_str = parts[0], parts[1]
            try:
                oid = int(oid_str)
            except ValueError:
                oid = oid_str

            raw_info = raw_status.get(key, {})
            status_val = raw_info.get("status", "Offline")
            is_online = (status_val.lower() == "online")
            if is_online:
                online_count += 1
            else:
                offline_count += 1

            if port in ports_summary:
                ports_summary[port]["total"] += 1
                if is_online:
                    ports_summary[port]["online"] += 1
                else:
                    ports_summary[port]["offline"] += 1

            mac = reg_mac or raw_info.get("serial", "")
            vendor = local_vendor_of(mac)

            lbl_info = labels.get(key, "")
            p_name, p_desc = local_parse_label(lbl_info)
            if not p_name:
                p_name = f"Ponto #{oid}"

            cams = cameras.get(key, [])
            tr = tracker.get(key, {})
            since_str = tr.get("since", now_iso)
            try:
                since_dt = datetime.fromisoformat(since_str)
                duration_sec = (now - since_dt).total_seconds()
            except Exception:
                duration_sec = 0

            dur_text = local_format_dur(duration_sec)
            uptime_text = f"{'Online' if is_online else 'Offline'} há {dur_text}"

            onus_list.append({
                "id": key,
                "port": port,
                "onu_id": oid,
                "mac": mac,
                "vendor": vendor,
                "name": p_name,
                "description": p_desc,
                "status": "Online" if is_online else "Offline",
                "uptime_seconds": int(duration_sec),
                "uptime_text": uptime_text,
                "since": since_str,
                "cameras": cams
            })

        scanner_list = []
        for key, raw_info in raw_status.items():
            if key not in registered:
                ser = raw_info.get("serial", "")
                st = raw_info.get("status", "")
                if ser and ser != "000000000000" and len(ser) >= 8:
                    parts = key.split("|")
                    port = parts[0] if len(parts) > 0 else ""
                    oid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else parts[1]
                    scanner_list.append({
                        "id": key,
                        "port": port,
                        "onu_id": oid,
                        "mac": ser,
                        "vendor": local_vendor_of(ser),
                        "status": st
                    })

        total_homologadas = len(onus_list)
        avail_pct = round((online_count / total_homologadas * 100), 1) if total_homologadas > 0 else 0.0

        return {
            "id": "current",
            "collected_at": now_iso,
            "summary": {
                "total": total_homologadas,
                "online": online_count,
                "offline": offline_count,
                "availability_pct": avail_pct,
                "ports": ports_summary
            },
            "onus": onus_list,
            "scanner": scanner_list
        }

    def get_summary(self) -> Dict[str, Any]:
        return self._telemetry.get("summary", {})

    def get_scanner(self) -> List[Dict[str, Any]]:
        return self._telemetry.get("scanner", [])

    def get_onus(
        self,
        status_filter: str = "Todas",
        port_filter: str = "Todas as PONs",
        search_query: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Retorna as ONUs filtradas com processamento ultrarrápido em memória (< 1ms).
        """
        onus = self._telemetry.get("onus", [])
        status_filter = status_filter.strip().lower()
        port_filter = port_filter.strip()
        search_query = search_query.strip().lower()

        filtered = []
        for item in onus:
            # Filtro de Status
            if status_filter == "online" and item.get("status", "").lower() != "online":
                continue
            if status_filter == "offline" and item.get("status", "").lower() != "offline":
                continue

            # Filtro de Porta PON
            if port_filter not in ("Todas", "Todas as PONs", "Todas as Portas"):
                if item.get("port") != port_filter:
                    continue

            # Filtro de Busca
            if search_query:
                name_match = search_query in (item.get("name") or "").lower()
                desc_match = search_query in (item.get("description") or "").lower()
                mac_match = search_query in (item.get("mac") or "").lower()
                port_match = search_query in (item.get("port") or "").lower()
                id_match = search_query in str(item.get("onu_id") or "")

                cam_match = False
                for c in item.get("cameras", []):
                    if search_query in (c.get("ip") or "").lower() or search_query in (c.get("mac") or "").lower():
                        cam_match = True
                        break

                if not (name_match or desc_match or mac_match or port_match or id_match or cam_match):
                    continue

            filtered.append(item)

        return filtered

    def update_onu_label(self, port: str, onu_id: int, name: str, desc: str) -> Tuple[bool, str]:
        """Atualiza o nome/descrição de uma ONU no cache local, em disco e no Supabase."""
        key = f"{port}|{onu_id}"
        clean_name = (name or "").strip()
        clean_desc = (desc or "").strip()

        # Atualiza no cache em memória instantaneamente
        with self._lock:
            for item in self._telemetry.get("onus", []):
                if item.get("id") == key:
                    item["name"] = clean_name
                    item["description"] = clean_desc
                    break

        self._notify_listeners()
        self._save_disk_cache()

        # Atualiza no arquivo local onus_labels.json se existir
        labels_file = LOCAL_MONITORAMENTO_DIR / "onus_labels.json"
        if labels_file.exists():
            try:
                labels = {}
                with open(labels_file, "r", encoding="utf-8") as f:
                    labels = json.load(f)
                labels[key] = {"name": clean_name, "desc": clean_desc}
                tmp = str(labels_file) + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(labels, f, ensure_ascii=False, indent=2)
                os.replace(tmp, labels_file)
            except Exception as e:
                log.warning(f"[AjinManager] Aviso ao salvar rótulo localmente: {e}")

        # Atualiza no Supabase em segundo plano
        def push_label():
            cfg = ConfigManager().get_supabase_config()
            if not cfg.get("enabled") or not cfg.get("url") or not cfg.get("key"):
                return
            try:
                url = f"{cfg['url'].rstrip('/')}/rest/v1/ajin_labels"
                headers = {
                    "apikey": cfg["key"],
                    "Authorization": f"Bearer {cfg['key']}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates"
                }
                body = json.dumps({"key": key, "name": clean_name, "description": clean_desc}).encode("utf-8")
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status in (200, 201):
                        log.info(f"[AjinManager] Rótulo de {key} sincronizado na nuvem com sucesso.")
            except Exception:
                pass

        threading.Thread(target=push_label, daemon=True).start()
        return True, "Rótulo salvo com sucesso!"

    def homologate_onu(self, port: str, onu_id: int, mac: str, name: str, desc: str) -> Tuple[bool, str]:
        """Homologa um dispositivo do Scanner, movendo-o para a lista de ONUs ativas."""
        key = f"{port}|{onu_id}"
        clean_mac = (mac or "").upper().strip()

        # Atualiza arquivo local onus_registered.json
        reg_file = LOCAL_MONITORAMENTO_DIR / "onus_registered.json"
        if reg_file.exists():
            try:
                registered = {}
                with open(reg_file, "r", encoding="utf-8") as f:
                    registered = json.load(f)
                registered[key] = clean_mac
                tmp = str(reg_file) + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(registered, f, ensure_ascii=False, indent=2)
                os.replace(tmp, reg_file)
            except Exception as e:
                return False, f"Falha ao salvar registro: {e}"

        # Salva o rótulo
        self.update_onu_label(port, onu_id, name, desc)

        # Força nova leitura
        self.fetch_telemetry(force=True)
        return True, f"ONU {key} ({clean_mac}) homologada com sucesso!"
