#!/usr/bin/env python3
"""Dashboard de ONUs v2 - OLT + bancada, filtros, fabricante, historico e auto-refresh.
Integrado de forma nativa e autônoma ao RemoteXPTI.
"""
import csv
import glob
import json
import os
import re
import sys
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

try:
    import puxa_logs
except ImportError:
    ajin_dir = r"c:\Users\XPTI\Documents\vscode\monitoramentoAJIN"
    if os.path.exists(ajin_dir) and ajin_dir not in sys.path:
        sys.path.insert(0, ajin_dir)
    try:
        import puxa_logs
    except ImportError:
        puxa_logs = None

def get_logs_dir() -> str:
    candidates = [
        r"c:\Users\XPTI\Documents\vscode\monitoramentoAJIN\logs_ONU",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs_ONU"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "RemoteXPTI", "logs_ONU"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "RemoteXPTI", "logs_ONU"),
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.isdir(c):
            return c
    d = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RemoteXPTI", "logs_ONU")
    os.makedirs(d, exist_ok=True)
    return d

LOGS_DIR = get_logs_dir()
LABELS_FILE = os.path.join(LOGS_DIR, "onus_labels.json")
IGNORED_FILE = os.path.join(LOGS_DIR, "onus_ignored.json")
REGISTERED_FILE = os.path.join(LOGS_DIR, "onus_registered.json")
CAMERAS_FILE = os.path.join(LOGS_DIR, "onu_cameras.json")
REFRESH = 10
PORT = 3000
SERVER_IP = "192.168.190.187"
server_ping_state = {"online": False, "ip": SERVER_IP, "checked_at": "-"}



def load_cameras():
    try:
        if os.path.exists(CAMERAS_FILE):
            with open(CAMERAS_FILE, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except (OSError, ValueError):
        pass
    return {}

BENCH_DEVICES = [
    {"ip": "192.168.10.1", "label": "ONU Bancada 1 (EB01)", "mac": "00:19:46:3C:37:23"},
]

OLT_INFO = {
    "modelo": "C-Data FD1108S",
    "firmware": "OLT-SWE-1.2.16",
    "chassis": "CHASSIS-4.0",
    "placa": "PON-3.0 / fw PON-1.1.6",
    "mac": "00:A1:02:0B:00:38",
    "ip": "192.168.1.100",
}

VENDOR_PREFIXES = [
    ("00A10203", "C-Data"),
    ("001946", "Cianet / CTS"),
    ("8014A8", "Cianet CTS 2702B"),
]


def vendor_of(serial):
    s = (serial or "").upper()
    for prefixo, nome in VENDOR_PREFIXES:
        if s.startswith(prefixo):
            return nome
    return "-"


def format_point_name(val):
    if not val:
        return ""
    v = str(val).strip()
    if not v or v in ["??", "-"]:
        return ""
    m_num = re.match(r"^\d+$", v)
    if m_num:
        return f"Ponto {int(v):02d}"
    m_ponto = re.match(r"^(?:P(?:onto)?[_\s-]*)(\d+)$", v, re.IGNORECASE)
    if m_ponto:
        return f"Ponto {int(m_ponto.group(1)):02d}"
    return v


def parse_label_info(val):
    """
    Retorna (name, desc).
    Suporta dict {'name': 'Ponto 01', 'desc': 'Rua...'} ou string legado 'P_10 R. Tabaronas'.
    """
    if isinstance(val, dict):
        return val.get("name", "").strip(), val.get("desc", "").strip()
    if isinstance(val, str):
        v = val.strip()
        if not v or v in ["??", "-"]:
            return "", ""
        m_leg = re.match(r"^(?:P(?:onto)?[_\s-]*)(\d+)\s*(?:[-–—\s/]\s*(.*))?$", v, re.IGNORECASE)
        if m_leg:
            p_num = int(m_leg.group(1))
            p_name = f"Ponto {p_num:02d}"
            p_desc = (m_leg.group(2) or "").strip()
            return p_name, p_desc
        return v, ""
    return "", ""


def load_labels():
    try:
        with open(LABELS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_label(port, oid, name=None, desc=None):
    labels = load_labels()
    key = f"{port}|{oid}"
    cur_name, cur_desc = parse_label_info(labels.get(key))

    new_name = cur_name if name is None else format_point_name(name)
    new_desc = cur_desc if desc is None else desc.strip()

    if new_name or new_desc:
        labels[key] = {"name": new_name, "desc": new_desc}
    else:
        labels.pop(key, None)

    # Sincroniza com porta secundária se houver MAC consecutivo cadastrado
    reg = load_registered()
    ser = reg.get(key, "")
    if ser:
        sec_mac = find_multi_llid_secondary_mac(ser)
        if sec_mac:
            for k, s in reg.items():
                if k.startswith(f"{port}|") and s.upper() == sec_mac:
                    if new_name or new_desc:
                        labels[k] = {"name": new_name, "desc": new_desc}
                    else:
                        labels.pop(k, None)

    tmp = LABELS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LABELS_FILE)


STATE_TRACKER_FILE = os.path.join(LOGS_DIR, "onu_state_tracker.json")


def load_state_tracker():
    if os.path.exists(STATE_TRACKER_FILE):
        try:
            with open(STATE_TRACKER_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return bootstrap_state_tracker()


def save_state_tracker(tracker):
    tmp = STATE_TRACKER_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_TRACKER_FILE)


def format_uptime_duration(seconds):
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{int(seconds)}s"
    mins = int(seconds // 60)
    if mins < 60:
        return f"{mins}m"
    hours = int(mins // 60)
    rem_mins = mins % 60
    if hours < 24:
        return f"{hours}h {rem_mins:02d}m"
    days = int(hours // 24)
    rem_hours = hours % 24
    return f"{days}d {rem_hours:02d}h"


def format_uptime_detailed(seconds, status="Online"):
    if seconds < 0:
        seconds = 0
    days = int(seconds // 86400)
    rem1 = seconds % 86400
    hours = int(rem1 // 3600)
    rem2 = rem1 % 3600
    mins = int(rem2 // 60)
    secs = int(rem2 % 60)

    parts = []
    if days > 0:
        parts.append(f"{days} dia" if days == 1 else f"{days} dias")
    if hours > 0 or days > 0:
        parts.append(f"{hours} hora" if hours == 1 else f"{hours} horas")
    if mins > 0 or (days == 0 and hours > 0):
        parts.append(f"{mins} min" if mins == 1 else f"{mins} minutos")
    if days == 0 and hours == 0:
        parts.append(f"{secs} seg" if secs == 1 else f"{secs} segundos")

    dur_text = ", ".join(parts[:-1]) + (" e " + parts[-1] if len(parts) > 1 else parts[0]) if parts else "poucos segundos"
    return f"{status} há {dur_text}"


def bootstrap_state_tracker():
    tracker = {}
    files = sorted(glob.glob(os.path.join(LOGS_DIR, "onus_*.csv")), key=os.path.basename)
    for f in files[-500:]:
        dt = parse_snapshot_time(os.path.basename(f))
        if not dt:
            continue
        try:
            with open(f, newline="", encoding="utf-8", errors="replace") as fp:
                for row in csv.DictReader(fp):
                    port = (row.get("Slot-PON") or "").strip()
                    oid = (row.get("ONU_ID") or "").strip()
                    stt = (row.get("Status") or "").strip()
                    if not port or not oid:
                        continue
                    key = f"{port}|{oid}"
                    is_on = (stt.lower() == "online")
                    cur_stt = "Online" if is_on else "Offline"
                    if key not in tracker:
                        tracker[key] = {
                            "status": cur_stt,
                            "since": dt.isoformat(),
                            "last_seen": dt.isoformat()
                        }
                    else:
                        if tracker[key]["status"] != cur_stt:
                            tracker[key]["status"] = cur_stt
                            tracker[key]["since"] = dt.isoformat()
                        tracker[key]["last_seen"] = dt.isoformat()
        except Exception:
            pass
    if tracker:
        try:
            save_state_tracker(tracker)
        except Exception:
            pass
    return tracker


EVENTS_HISTORY_FILE = os.path.join(LOGS_DIR, "events_history.json")
MAX_EVENTS_HISTORY = 100


def load_events_history():
    if os.path.exists(EVENTS_HISTORY_FILE):
        try:
            with open(EVENTS_HISTORY_FILE, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return bootstrap_events_history()


def save_events_history(events):
    if len(events) > MAX_EVENTS_HISTORY:
        events = events[:MAX_EVENTS_HISTORY]
    tmp = EVENTS_HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    os.replace(tmp, EVENTS_HISTORY_FILE)


def append_event_history(event):
    """Adiciona um evento no topo da lista e persiste respeitando o limite de 100."""
    events = load_events_history()
    if events and events[0].get("port") == event.get("port") and str(events[0].get("onu_id")) == str(event.get("onu_id")) and events[0].get("type") == event.get("type") and events[0].get("timestamp") == event.get("timestamp"):
        return events
    events.insert(0, event)
    if len(events) > MAX_EVENTS_HISTORY:
        events = events[:MAX_EVENTS_HISTORY]
    save_events_history(events)
    return events


def bootstrap_events_history():
    events = []
    files = sorted(glob.glob(os.path.join(LOGS_DIR, "onus_*.csv")), key=os.path.basename)
    if len(files) < 2:
        return []

    labels = load_labels()
    ignored = load_ignored()
    _, known_serials = get_monitored_onus()
    prev_states = None
    state_since = {}

    for fpath in files[-300:]:
        fname = os.path.basename(fpath)
        f_dt = parse_snapshot_time(fname)
        if not f_dt:
            continue
        time_str = f_dt.strftime("%H:%M:%S")
        dt_full = f_dt.strftime("%d/%m/%Y às %H:%M:%S")
        iso_str = f_dt.isoformat()
        cur_states = read_snapshot(fpath)

        if prev_states is not None:
            # Quedas (prev online -> cur offline)
            for key, prev_info in prev_states.items():
                if f"{key[0]}|{key[1]}" in ignored:
                    continue
                cur_info = cur_states.get(key)
                if prev_info["online"] and (cur_info is None or not cur_info["online"]):
                    ser = prev_info["serial"] or known_serials.get(key, "")
                    p_name, p_desc = parse_label_info(labels.get(f"{key[0]}|{key[1]}"))
                    lbl_str = f"{p_name} {p_desc}".strip() if (p_name or p_desc) else ""
                    slot_code = f"{key[0]}_{str(key[1]).zfill(3)}"
                    state_since[key] = f_dt
                    events.append({
                        "id": f"evt_{f_dt.strftime('%Y%m%d_%H%M%S')}_{slot_code}_fell",
                        "timestamp": iso_str,
                        "datetime": dt_full,
                        "time": time_str,
                        "type": "fell",
                        "status": "PROBLEM",
                        "port": key[0],
                        "onu_id": str(key[1]),
                        "slot_code": slot_code,
                        "serial": ser,
                        "vendor": vendor_of(ser),
                        "point_name": p_name,
                        "street_desc": p_desc,
                        "label": lbl_str,
                        "downtime_seconds": 0,
                        "downtime_formatted": "-"
                    })

            # Voltas (prev offline -> cur online)
            for key, cur_info in cur_states.items():
                if f"{key[0]}|{key[1]}" in ignored:
                    continue
                prev_info = prev_states.get(key)
                if cur_info["online"] and (prev_info is None or not prev_info["online"]):
                    ser = cur_info["serial"] or known_serials.get(key, "")
                    p_name, p_desc = parse_label_info(labels.get(f"{key[0]}|{key[1]}"))
                    lbl_str = f"{p_name} {p_desc}".strip() if (p_name or p_desc) else ""
                    slot_code = f"{key[0]}_{str(key[1]).zfill(3)}"
                    fell_dt = state_since.get(key)
                    downtime_sec = max(0.0, (f_dt - fell_dt).total_seconds()) if fell_dt else 0.0
                    downtime_str = format_uptime_duration(downtime_sec) if downtime_sec > 0 else "recente"
                    state_since[key] = f_dt
                    events.append({
                        "id": f"evt_{f_dt.strftime('%Y%m%d_%H%M%S')}_{slot_code}_rose",
                        "timestamp": iso_str,
                        "datetime": dt_full,
                        "time": time_str,
                        "type": "rose",
                        "status": "RESOLVED",
                        "port": key[0],
                        "onu_id": str(key[1]),
                        "slot_code": slot_code,
                        "serial": ser,
                        "vendor": vendor_of(ser),
                        "point_name": p_name,
                        "street_desc": p_desc,
                        "label": lbl_str,
                        "downtime_seconds": int(downtime_sec),
                        "downtime_formatted": downtime_str
                    })

        prev_states = cur_states

    events.reverse()
    events = events[:MAX_EVENTS_HISTORY]
    if events:
        try:
            save_events_history(events)
        except Exception:
            pass
    return events


def load_ignored():
    try:
        with open(IGNORED_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return {k: {"deleted_snapshot": "", "deleted_at": ""} for k in data}
            if isinstance(data, dict):
                return data
            return {}
    except (OSError, ValueError):
        return {}


def save_ignored(ignored_dict):
    tmp = IGNORED_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ignored_dict, f, ensure_ascii=False, indent=2)
    os.replace(tmp, IGNORED_FILE)


def load_registered():
    """Retorna o dicionario {Slot-PON|ONU_ID: Serial/MAC} de ONUs cadastradas."""
    try:
        if os.path.exists(REGISTERED_FILE):
            with open(REGISTERED_FILE, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                if isinstance(data, list):
                    return {k: "" for k in data}
    except (OSError, ValueError):
        pass

    try:
        files = sorted(glob.glob(os.path.join(LOGS_DIR, "onus_*.csv")), key=os.path.basename)
        initial_reg = {}
        for fpath in files:
            with open(fpath, newline="", encoding="utf-8", errors="replace") as f:
                for row in csv.DictReader(f):
                    st = (row.get("Status") or "").strip().lower()
                    p = (row.get("Slot-PON") or "").strip()
                    i = (row.get("ONU_ID") or "").strip()
                    s = (row.get("Serial") or "").strip()
                    if st == "online" and p and i:
                        initial_reg[f"{p}|{i}"] = s
        if initial_reg:
            save_registered(initial_reg)
            return initial_reg
    except Exception:
        pass
    return {}


def save_registered(registered_dict):
    tmp = REGISTERED_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registered_dict, f, ensure_ascii=False, indent=2)
    os.replace(tmp, REGISTERED_FILE)


def find_multi_llid_secondary_mac(serial_str):
    """Retorna o MAC da porta secundária (serial + 1 em hex)."""
    if not serial_str:
        return None
    try:
        sec_mac_int = int(serial_str, 16) + 1
        return f"{sec_mac_int:012X}"
    except ValueError:
        return None


def detect_multi_llid_map(snapshot_rows):
    """
    Identifica portas secundárias na MESMA porta PON baseando-se em MACs consecutivos (MAC e MAC+1).
    Não depende de IDs da OLT serem consecutivos.
    """
    by_port = {}
    for r in snapshot_rows:
        by_port.setdefault(r["port"], []).append(r)

    secondary_keys = set()
    primary_info = {}
    secondary_to_primary = {}

    for port, devs in by_port.items():
        mac_map = {}
        for d in devs:
            ser = d.get("serial", "").strip()
            if not ser or ser == "0":
                continue
            try:
                m_int = int(ser, 16)
                mac_map[m_int] = d
            except ValueError:
                pass

        for d in devs:
            ser = d.get("serial", "").strip()
            if not ser or ser == "0":
                continue
            try:
                m_int = int(ser, 16)
                if (m_int - 1) in mac_map:
                    prim_dev = mac_map[m_int - 1]
                    sec_key = (port, d["id"])
                    prim_key = (port, prim_dev["id"])
                    secondary_keys.add(sec_key)
                    secondary_to_primary[sec_key] = prim_key
                    primary_info[prim_key] = {
                        "secondary_id": d["id"],
                        "secondary_serial": d["serial"],
                    }
            except ValueError:
                pass

    return secondary_keys, primary_info, secondary_to_primary


def delete_registered_onu(port, oid):
    key = f"{port}|{oid}"
    reg = load_registered()
    labels = load_labels()
    ignored = load_ignored()

    keys_to_del = {key}
    ser = reg.get(key, "")
    if ser:
        sec_mac = find_multi_llid_secondary_mac(ser)
        if sec_mac:
            for k, s in reg.items():
                if k.startswith(f"{port}|") and s.upper() == sec_mac:
                    keys_to_del.add(k)
        try:
            prev_mac = f"{int(ser, 16) - 1:012X}"
            for k, s in reg.items():
                if k.startswith(f"{port}|") and s.upper() == prev_mac:
                    keys_to_del.add(k)
        except ValueError:
            pass

    changed_reg = False
    for k in keys_to_del:
        if k in reg:
            del reg[k]
            changed_reg = True
        if k in labels:
            del labels[k]
        if k in ignored:
            del ignored[k]

    if changed_reg:
        save_registered(reg)

    tmp = LABELS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LABELS_FILE)
    save_ignored(ignored)


def ignore_onu(port, oid):
    delete_registered_onu(port, oid)


def unignore_onu(port, oid):
    pass


def save_batch_labels(items):
    labels = load_labels()
    ignored = load_ignored()
    reg = load_registered()
    changed_ignored = False
    changed_reg = False

    for it in items:
        port = str(it.get("port") or "").strip()
        oid = str(it.get("id") or "").strip()
        name = str(it.get("name") or "").strip()
        desc = str(it.get("desc") or "").strip()
        lbl = str(it.get("label") or "").strip()
        ser = str(it.get("serial") or "").strip()
        if not port or not oid:
            continue
        key = f"{port}|{oid}"
        if not name and not desc and lbl:
            name, desc = parse_label_info(lbl)

        fmt_name = format_point_name(name)
        if fmt_name or desc:
            labels[key] = {"name": fmt_name, "desc": desc}

        reg[key] = ser
        changed_reg = True
        if key in ignored:
            del ignored[key]
            changed_ignored = True

        sec_mac = find_multi_llid_secondary_mac(ser)
        if sec_mac:
            for k, s in reg.items():
                if k.startswith(f"{port}|") and s.upper() == sec_mac:
                    if fmt_name or desc:
                        labels[k] = {"name": fmt_name, "desc": desc}
                    if k in ignored:
                        del ignored[k]
                        changed_ignored = True

    tmp = LABELS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LABELS_FILE)
    if changed_ignored:
        save_ignored(ignored)
    if changed_reg:
        save_registered(reg)


PAGE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitoramento de ONUs</title>
<style>
  * { box-sizing: border-box; margin:0; padding:0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #eef1f5;
    color: #1e293b;
    height: 100vh;
    overflow: hidden;
  }

  /* LAYOUT PRINCIPAL: ESQUERDA (CONTEUDO) + DIREITA (SIDEBAR DIGIFORT) */
  .digifort-layout {
    display: grid;
    grid-template-columns: 1fr 240px;
    height: 100vh;
    width: 100vw;
  }

  /* COLUNA DA ESQUERDA */
  .main-panel {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
    background: #ffffff;
    border-right: 1px solid #cbd5e1;
  }

  /* BARRA DE BUSCA SUPERIOR */
  .top-search-bar {
    padding: 8px 12px;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    display: flex;
    gap: 10px;
    align-items: center;
  }
  .search-input-wrap {
    flex: 1;
    position: relative;
    display: flex;
    align-items: center;
  }
  .search-input-wrap svg {
    position: absolute;
    left: 10px;
    color: #64748b;
    pointer-events: none;
  }
  .search-input-wrap input {
    width: 100%;
    padding: 6px 30px 6px 32px;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    font-size: 13px;
    color: #0f172a;
    outline: none;
    background: #ffffff;
  }
  .search-input-wrap input:focus {
    border-color: #0284c7;
    box-shadow: 0 0 0 2px rgba(2,132,199,0.15);
  }
  .clear-btn {
    position: absolute;
    right: 8px;
    background: none;
    border: none;
    color: #94a3b8;
    cursor: pointer;
    font-size: 16px;
    line-height: 1;
    display: none;
  }
  .clear-btn:hover { color: #475569; }

  .digi-select {
    padding: 6px 10px;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    font-size: 12px;
    background: #ffffff;
    color: #334155;
    outline: none;
    cursor: pointer;
  }
  .digi-select:focus { border-color: #0284c7; }

  /* AVISO DE SERVIDOR SEM PING */
  .server-notice-banner {
    display: none;
    background: #fffbeb;
    border-bottom: 1px solid #fde68a;
    padding: 6px 14px;
    font-size: 12px;
    color: #92400e;
    align-items: center;
    justify-content: space-between;
  }
  .badge-ping-warn {
    background: #fef3c7;
    color: #b45309;
    border: 1px solid #fcd34d;
    padding: 1px 7px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
  }

  /* CONTAINER DA TABELA COM SCROLL */
  .table-container {
    flex: 1;
    overflow-y: auto;
    overflow-x: auto;
    background: #ffffff;
  }
  table.digi-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    text-align: left;
  }
  table.digi-table thead th {
    position: sticky;
    top: 0;
    background: #f1f5f9;
    color: #475569;
    font-weight: 600;
    padding: 6px 10px;
    border-bottom: 1px solid #cbd5e1;
    border-right: 1px solid #e2e8f0;
    user-select: none;
    z-index: 10;
  }
  table.digi-table thead th.sortable { cursor: pointer; }
  table.digi-table thead th.sortable:hover { background: #e2e8f0; color: #0284c7; }
  table.digi-table tbody tr {
    border-bottom: 1px solid #f1f5f9;
    height: 28px;
  }
  table.digi-table tbody tr:nth-child(even) { background: #fafafa; }
  table.digi-table tbody tr:hover { background: #e0f2fe !important; }
  table.digi-table tbody td {
    padding: 4px 10px;
    border-right: 1px solid #f1f5f9;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  table.digi-table tr.justfell td {
    background: #fef2f2 !important;
    color: #991b1b;
  }

  .dev-name {
    display: flex;
    align-items: center;
    gap: 7px;
    font-weight: 600;
    color: #334155;
  }
  .onu-badge-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 17px;
    height: 17px;
    flex-shrink: 0;
    vertical-align: middle;
  }
  .onu-badge-icon svg {
    display: block;
    width: 17px;
    height: 17px;
  }

  .stt-sim { color: #16a34a; font-weight: 700; display: inline-flex; align-items: center; gap: 4px; }
  .stt-nao { color: #dc2626; font-weight: 700; display: inline-flex; align-items: center; gap: 4px; }
  .stt-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
  .stt-sim .stt-dot { background: #16a34a; }
  .stt-nao .stt-dot { background: #dc2626; }

  .serial-txt { font-family: Consolas, monospace; color: #475569; font-size: 11px; }
  .badge-multi {
    background: #e0f2fe;
    color: #0369a1;
    border: 1px solid #bae6fd;
    border-radius: 3px;
    font-size: 9px;
    font-weight: 700;
    padding: 1px 4px;
    letter-spacing: 0.2px;
    flex-shrink: 0;
  }
  .vendor-tag {
    background: #f1f5f9;
    border: 1px solid #cbd5e1;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 10px;
    color: #475569;
    font-weight: 600;
  }
  .cam-badge {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    background: #f0fdf4;
    color: #15803d;
    border: 1px solid #bbf7d0;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    font-family: Consolas, monospace;
    text-decoration: none;
    transition: all 0.15s ease;
    cursor: pointer;
  }
  .cam-badge:hover {
    background: #dcfce7;
    border-color: #86efac;
    color: #166534;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  }
  .lbl-cell { cursor: pointer; color: #0f172a; font-weight: 500; }
  .lbl-cell:hover { text-decoration: underline; color: #0284c7; }
  .lbl-empty { color: #94a3b8; font-style: italic; font-size: 11px; }
  .del-btn {
    background: none;
    border: none;
    color: #94a3b8;
    cursor: pointer;
    font-size: 13px;
    padding: 2px 6px;
    border-radius: 4px;
    line-height: 1;
    transition: all 0.15s;
    opacity: 0.7;
  }
  .del-btn:hover {
    background: #fee2e2;
    color: #dc2626;
    opacity: 1;
  }

  /* SECAO DE TIMELINE / EVENTOS */
  .timeline-section, .bench-section {
    background: #f8fafc;
    border-top: 1px solid #e2e8f0;
    padding: 10px 14px;
    max-height: 200px;
    overflow-y: auto;
  }
  .events-grid {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 6px;
  }
  .change-card {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 8px 12px;
    flex: 1;
    min-width: 260px;
  }
  .change-card h4 { font-size: 12px; margin-bottom: 4px; display: flex; justify-content: space-between; }
  .change-card ul { list-style: none; font-size: 11px; padding: 0; }
  .change-card li { padding: 2px 0; border-bottom: 1px solid #f1f5f9; }

  /* BARRA INFERIOR DE STATUS E CONTROLES */
  .digifort-bottombar {
    padding: 6px 12px;
    background: #f1f5f9;
    border-top: 1px solid #cbd5e1;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
  }
  .bottom-checkboxes {
    display: flex;
    gap: 14px;
    align-items: center;
    font-size: 12px;
    color: #334155;
  }
  .digi-check {
    display: flex;
    align-items: center;
    gap: 5px;
    cursor: pointer;
    user-select: none;
  }
  .bottom-actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .count-text { font-size: 12px; color: #64748b; margin-right: 6px; }
  .digi-btn {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 12px;
    color: #334155;
    cursor: pointer;
    text-decoration: none;
    font-weight: 500;
  }
  .digi-btn:hover { background: #e2e8f0; }
  .digi-btn.primary {
    background: #0072bc;
    color: #ffffff;
    border-color: #00609c;
  }
  .digi-btn.primary:hover { background: #005f9e; }

  /* SIDEBAR DIGIFORT (BARRA AZUL VERTICAL À DIREITA) */
  .digifort-sidebar {
    background: #0072bc;
    background: linear-gradient(180deg, #0078d7 0%, #0063a8 100%);
    color: #ffffff;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow-y: auto;
    border-left: 1px solid #005694;
  }
  .sidebar-tile {
    padding: 10px 14px;
    border-bottom: 1px solid rgba(255,255,255,0.22);
    display: flex;
    align-items: center;
    gap: 12px;
    transition: background 0.15s;
  }
  .sidebar-tile:hover {
    background: rgba(255,255,255,0.08);
  }
  .tile-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    color: #ffffff;
    opacity: 0.95;
  }
  .tile-icon.green { color: #86efac; }
  .tile-icon.red { color: #fca5a5; }
  .tile-content {
    flex: 1;
    text-align: right;
  }
  .tile-num {
    font-size: 26px;
    font-weight: 800;
    line-height: 1.1;
    letter-spacing: -0.5px;
    color: #ffffff;
  }
  .tile-num.small { font-size: 16px; font-weight: 700; }
  .tile-sub {
    font-size: 10px;
    color: #bae6fd;
    margin-top: 1px;
  }
  .tile-lbl {
    font-size: 11px;
    font-weight: 600;
    color: #e0f2fe;
    text-transform: none;
    letter-spacing: 0.2px;
    margin-top: 2px;
  }
  .ports-breakdown {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-top: 4px;
    font-size: 11px;
    text-align: left;
  }
  .port-item {
    display: flex;
    justify-content: space-between;
    color: #e0f2fe;
    padding: 1px 0;
  }
  .port-item b { color: #ffffff; }

  .sidebar-footer {
    margin-top: auto;
    padding: 10px 14px;
    font-size: 11px;
    color: #bae6fd;
    border-top: 1px solid rgba(255,255,255,0.2);
    background: rgba(0,0,0,0.15);
    display: flex;
    justify-content: space-between;
  }

  /* MODAL DE DESCOBERTA / SCANNER */
  .modal-backdrop {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(2px);
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .modal-dialog {
    background: #ffffff;
    border-radius: 8px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    width: 92vw;
    max-width: 980px;
    height: 84vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border: 1px solid #cbd5e1;
  }
  .modal-header {
    padding: 12px 18px;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .modal-header h3 { font-size: 15px; color: #0f172a; margin: 0; font-weight: 700; }
  .modal-close {
    background: none; border: none; font-size: 22px; color: #94a3b8; cursor: pointer; line-height: 1;
  }
  .modal-close:hover { color: #0f172a; }
  .modal-subbar {
    padding: 8px 18px;
    background: #f1f5f9;
    border-bottom: 1px solid #e2e8f0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
  }
  .scan-filter-input {
    flex: 1;
    padding: 6px 10px;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    font-size: 12px;
    background: #ffffff;
    outline: none;
  }
  .scan-filter-input:focus { border-color: #0072bc; }
  .modal-body {
    flex: 1;
    overflow-y: auto;
    background: #ffffff;
  }
  .modal-footer {
    padding: 10px 18px;
    background: #f8fafc;
    border-top: 1px solid #e2e8f0;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .scan-label-input {
    width: 100%;
    padding: 4px 8px;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    font-size: 12px;
    background: #ffffff;
    box-sizing: border-box;
  }
  .scan-label-input:focus {
    border-color: #0072bc;
    outline: none;
    box-shadow: 0 0 0 2px rgba(0,114,188,0.15);
  }

  .mac-badge {
    font-family: Consolas, monospace;
    background: #f1f5f9;
    color: #0f172a;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 700;
    border: 1px solid #cbd5e1;
    display: inline-block;
  }
  .mac-chip {
    font-family: Consolas, monospace;
    background: #f8fafc;
    color: #0f172a;
    padding: 2px 8px;
    border-radius: 5px;
    font-size: 12px;
    font-weight: 700;
    border: 1px solid #cbd5e1;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .vendor-badge {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 4px;
    background: #e0f2fe;
    color: #0369a1;
    border: 1px solid #bae6fd;
  }
  .copy-mini-btn {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    cursor: pointer;
    line-height: 1;
    color: #475569;
    transition: all 0.15s;
    display: inline-flex;
    align-items: center;
  }
  .copy-mini-btn:hover {
    background: #f1f5f9;
    color: #0284c7;
    border-color: #0284c7;
  }
  .edit-mini-btn {
    background: none;
    border: 1px solid transparent;
    cursor: pointer;
    font-size: 11px;
    opacity: 0.6;
    padding: 1px 4px;
    border-radius: 3px;
    line-height: 1;
    transition: all 0.15s;
    vertical-align: middle;
  }
  .edit-mini-btn:hover {
    opacity: 1;
    background: #e2e8f0;
    border-color: #cbd5e1;
  }
  .uptime-txt {
    font-family: Consolas, monospace;
    font-size: 12px;
    font-weight: 600;
    color: #0f172a;
    white-space: nowrap;
    display: inline-block;
  }
  .uptime-txt.off {
    color: #dc2626;
    font-weight: 700;
  }
  .badge-fell {
    background: #fef2f2;
    color: #991b1b;
    border: 1px solid #fecaca;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .badge-rose {
    background: #f0fdf4;
    color: #166534;
    border: 1px solid #bbf7d0;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
  }
  .status-dot.red { background: #dc2626; }
  .status-dot.green { background: #16a34a; }

  /* =========================================================
     RESPONSIVIDADE PARA CELULAR E TABLETS
     ========================================================= */
  @media (max-width: 900px) {
    body {
      height: auto;
      min-height: 100vh;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
    }

    .digifort-layout {
      display: flex;
      flex-direction: column;
      height: auto;
      min-height: 100vh;
      width: 100%;
      overflow-x: hidden;
    }

    /* Coloca os cards de resumo azul no topo em grade responsiva */
    .digifort-sidebar {
      order: -1;
      height: auto;
      overflow: visible;
      border-left: none;
      border-bottom: 2px solid #005694;
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 1px;
      background: #005694;
    }

    .digifort-sidebar .sidebar-tile {
      background: #0072bc;
      padding: 8px 12px;
      border-bottom: none;
      min-height: 64px;
    }

    .digifort-sidebar .sidebar-tile:nth-child(n+5) {
      grid-column: span 2;
      background: #00609c;
    }

    .sidebar-footer {
      grid-column: span 2;
      padding: 8px 12px;
      font-size: 10px;
    }

    .tile-icon svg {
      width: 22px;
      height: 22px;
    }

    .tile-num {
      font-size: 20px;
    }

    .tile-lbl {
      font-size: 10px;
    }

    /* Painel Principal */
    .main-panel {
      height: auto;
      min-height: auto;
      border-right: none;
      overflow: visible;
    }

    /* Barra Superior de Busca e Filtros */
    .top-search-bar {
      flex-wrap: wrap;
      gap: 8px;
      padding: 10px;
      background: #f8fafc;
    }

    .search-input-wrap {
      flex: 1 1 100%;
    }

    .search-input-wrap input {
      padding: 10px 32px 10px 34px;
      font-size: 14px;
      height: 42px;
      border-radius: 6px;
    }

    .digi-select {
      flex: 1 1 calc(50% - 4px);
      height: 40px;
      font-size: 13px;
      border-radius: 6px;
    }

    #btnSyncCams, #btnScanner {
      flex: 1 1 100%;
      height: 40px;
      justify-content: center;
      font-size: 13px;
      border-radius: 6px;
    }

    /* Tabela Central */
    .table-container {
      flex: none;
      min-height: 340px;
      max-height: calc(100vh - 280px);
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      border-bottom: 1px solid #cbd5e1;
    }

    table.digi-table {
      min-width: 680px;
      font-size: 13px;
    }

    table.digi-table thead th {
      padding: 10px 10px;
      font-size: 12px;
    }

    table.digi-table tbody tr {
      height: 42px;
    }

    table.digi-table tbody td {
      padding: 8px 10px;
      font-size: 13px;
    }

    .del-btn, .digi-btn {
      min-height: 32px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }

    /* Rodapé de Controles */
    .digifort-bottombar {
      flex-direction: column;
      align-items: stretch;
      gap: 12px;
      padding: 14px 14px 28px 14px;
    }

    .bottom-checkboxes {
      flex-direction: column;
      align-items: flex-start;
      gap: 8px;
      background: #ffffff;
      padding: 12px;
      border-radius: 6px;
      border: 1px solid #cbd5e1;
    }

    .digi-check {
      font-size: 13px;
      padding: 4px 0;
      width: 100%;
    }

    .digi-check input[type="checkbox"] {
      width: 18px;
      height: 18px;
    }

    .bottom-actions {
      flex-direction: column;
      align-items: stretch;
      gap: 8px;
    }

    .bottom-actions .digi-btn {
      height: 42px;
      font-size: 14px;
      text-align: center;
      justify-content: center;
    }

    .count-text {
      text-align: center;
      margin-bottom: 2px;
      font-size: 13px;
    }

    /* Modais Responsivos */
    .modal-dialog {
      width: 96vw;
      max-width: 96vw;
      height: auto;
      max-height: 92vh;
      margin: 10px auto;
      border-radius: 12px;
    }

    .modal-header {
      padding: 12px 14px;
    }

    .modal-body {
      padding: 14px 12px;
    }

    #onuDetailModal .modal-body > div > div[style*="grid-template-columns"] {
      grid-template-columns: 1fr !important;
      gap: 10px !important;
    }

    .cam-modal-row {
      flex-direction: column !important;
      align-items: flex-start !important;
      gap: 8px !important;
    }

    .cam-modal-row > div:last-child {
      width: 100%;
      display: flex;
      justify-content: flex-start;
      gap: 8px;
    }

    .cam-modal-row .digi-btn {
      flex: 1;
      height: 36px;
      justify-content: center;
    }
  }

  @media (max-width: 480px) {
    .digifort-sidebar {
      grid-template-columns: 1fr 1fr;
    }
    .digi-select {
      flex: 1 1 100%;
    }
  }
</style>
</head>
<body>

<div class="digifort-layout">
  <!-- COLUNA PRINCIPAL -->
  <div class="main-panel">
    <!-- BARRA DE BUSCA SUPERIOR -->
    <div class="top-search-bar">
      <div class="search-input-wrap">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="text" id="fSearch" placeholder="Pesquisar por Nome, Serial / MAC (LAN 1 ou LAN 2), Ponto/Rua, Porta ou IP da Câmera..." autocomplete="off">
        <button class="clear-btn" id="clearBtn" title="Limpar">&times;</button>
      </div>
      <select id="fPort" class="digi-select">
        <option value="all">Todas as Portas PON</option>
      </select>
      <select id="fStatus" class="digi-select">
        <option value="all">Todos os Status</option>
        <option value="on">Somente Em Funcionamento (Online)</option>
        <option value="off">Somente Fora de Funcionamento (Offline)</option>
      </select>
      <button class="digi-btn" id="btnSyncCams" onclick="syncCameras(this)" style="display:flex;align-items:center;gap:6px;padding:6px 12px;font-weight:600;white-space:nowrap;" title="Sincronizar câmeras aprendidas na OLT agora">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
        <span>Atualizar C&acirc;meras</span>
      </button>
      <button class="digi-btn primary" id="btnScanner" onclick="openScannerModal()" style="display:flex;align-items:center;gap:6px;padding:6px 12px;font-weight:600;white-space:nowrap;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <span>Scanner de ONUs</span>
        <span id="scanBadge" style="display:none;background:#fef08a;color:#854d0e;border-radius:10px;padding:1px 6px;font-size:10px;font-weight:800;">0</span>
      </button>
      <button class="digi-btn" id="btnIncidents" onclick="openIncidentsModal()" style="display:flex;align-items:center;gap:6px;padding:6px 12px;font-weight:600;white-space:nowrap;background:#fff1f2;color:#be123c;border-color:#fecdd3;" title="Abrir Hist&oacute;rico de Incidentes &amp; Eventos">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        <span>Incidentes &amp; Eventos</span>
        <span id="incidentsBadge" style="display:none;background:#be123c;color:#fff;border-radius:10px;padding:1px 6px;font-size:10px;font-weight:800;">0</span>
      </button>
    </div>

    <!-- AVISO DE PING DO SERVIDOR -->
    <div class="server-notice-banner" id="serverWarnBanner">
      <div style="display:flex;align-items:center;gap:8px;">
        <span>⚠️</span>
        <span><b>Sem resposta de ping com o servidor (<span id="serverWarnIp">192.168.190.187</span>)</b> &mdash; Exibindo &uacute;ltima coleta salva localmente. As atualiza&ccedil;&otilde;es autom&aacute;ticas ser&atilde;o retomadas assim que o link for restabelecido.</span>
      </div>
      <span class="badge-ping-warn">Sem Ping</span>
    </div>

    <!-- TABELA CENTRAL -->
    <div class="table-container">
      <div id="tableWrap"></div>
    </div>

    <!-- PAINEL DE LINHA DO TEMPO / MUDANÇAS -->
    <div id="timelineSection" style="display:none;" class="timeline-section">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-weight:700;font-size:12px;color:#1e3a8a;">📊 Mudan&ccedil;as e Linha do Tempo de Eventos</span>
        <div style="display:flex;align-items:center;gap:6px;">
          <span style="font-size:11px;color:#64748b;">Janela:</span>
          <select id="selWindow" onchange="setWindow(this.value)" class="digi-select" style="padding:2px 6px;font-size:11px;">
            <option value="15" selected>&Uacute;ltimos 15 minutos</option>
            <option value="30">&Uacute;ltimos 30 minutos</option>
            <option value="60">&Uacute;ltima 1 hora</option>
            <option value="120">&Uacute;ltimas 2 horas</option>
            <option value="today">Desde a 1&ordf; coleta do dia</option>
            <option value="1">Coleta anterior (1 min)</option>
          </select>
        </div>
      </div>
      <div id="changesWrap"></div>
      <div id="eventsWrap"></div>
    </div>

    <!-- PAINEL DE BANCADA -->
    <div id="benchSection" style="display:none;" class="bench-section">
      <div style="font-weight:700;font-size:12px;color:#1e3a8a;margin-bottom:6px;">💻 ONUs de Bancada</div>
      <div id="benchWrap"></div>
    </div>

    <!-- RODAPÉ DE CONTROLES -->
    <div class="digifort-bottombar">
      <div class="bottom-checkboxes">
        <label class="digi-check">
          <input type="checkbox" id="chkShowOff" checked onchange="toggleShowOff(this.checked)">
          <span>Exibir fora de funcionamento</span>
        </label>
        <label class="digi-check">
          <input type="checkbox" id="chkShowCams" checked onchange="toggleShowCams(this.checked)">
          <span>Exibir C&acirc;meras Conectadas</span>
        </label>
        <label class="digi-check">
          <input type="checkbox" id="chkShowSlot" checked onchange="toggleShowSlot(this.checked)">
          <span>Exibir Canal OLT</span>
        </label>
        <label class="digi-check">
          <input type="checkbox" id="chkShowTimeline" onchange="toggleTimeline(this.checked)">
          <span>Exibir Mudan&ccedil;as / Linha do Tempo</span>
        </label>
        <label class="digi-check">
          <input type="checkbox" id="chkShowBench" onchange="toggleBench(this.checked)">
          <span>Exibir Bancada</span>
        </label>
        <label class="digi-check">
          <input type="checkbox" id="chkAutoRefresh" checked onchange="toggleAutoRefresh(this.checked)">
          <span>Auto-refresh (10s)</span>
        </label>
      </div>
      <div class="bottom-actions">
        <span class="count-text" id="countText">-</span>
        <a href="/export" class="digi-btn" title="Exportar relat&oacute;rio CSV com etiquetas">Exportar</a>
        <button class="digi-btn primary" onclick="load()" title="Atualizar dados agora">Atualizar</button>
      </div>
    </div>
  </div>

  <!-- SIDEBAR DIREITA (ESTILO DIGIFORT) -->
  <div class="digifort-sidebar">
    <!-- 1. TOTAL -->
    <div class="sidebar-tile">
      <div class="tile-icon">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="11" x2="3" y2="3"/><line x1="18" y1="11" x2="21" y2="3"/><rect x="2" y="11" width="20" height="10" rx="2" ry="2"/><circle cx="6" cy="16" r="0.8" fill="currentColor"/><circle cx="10" cy="16" r="0.8" fill="currentColor"/><circle cx="14" cy="16" r="0.8" fill="currentColor"/><circle cx="18" cy="16" r="0.8" fill="currentColor"/></svg>
      </div>
      <div class="tile-content">
        <div class="tile-num" id="sTotal">-</div>
        <div class="tile-lbl">Total</div>
      </div>
    </div>

    <!-- 2. ATIVADAS / EM FUNCIONAMENTO -->
    <div class="sidebar-tile">
      <div class="tile-icon green">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
      </div>
      <div class="tile-content">
        <div class="tile-num" id="sOn">-</div>
        <div class="tile-lbl">Em Funcionamento</div>
      </div>
    </div>

    <!-- 3. DESATIVADAS / FORA DE FUNCIONAMENTO -->
    <div class="sidebar-tile">
      <div class="tile-icon red">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
      </div>
      <div class="tile-content">
        <div class="tile-num" id="sOff">-</div>
        <div class="tile-lbl">Fora de Funcionamento</div>
      </div>
    </div>

    <!-- 4. CÂMERAS MAPEADAS -->
    <div class="sidebar-tile">
      <div class="tile-icon" style="color:#38bdf8;">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
      </div>
      <div class="tile-content">
        <div class="tile-num" id="sCams">-</div>
        <div class="tile-lbl">C&acirc;meras Mapeadas</div>
      </div>
    </div>

    <!-- 4. DISTRIBUIÇÃO POR PORTAS PON -->
    <div class="sidebar-tile" style="flex-direction:column;align-items:stretch;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div class="tile-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
        </div>
        <div class="tile-lbl" style="margin:0;">Portas PON</div>
      </div>
      <div class="ports-breakdown" id="sPortsList"></div>
    </div>

    <!-- 5. ÚLTIMA COLETA DO SERVIDOR -->
    <div class="sidebar-tile">
      <div class="tile-icon">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      </div>
      <div class="tile-content">
        <div class="tile-num small" id="sTime">-</div>
        <div class="tile-sub" id="sDate">-</div>
        <div class="tile-lbl">&Uacute;ltima Coleta</div>
      </div>
    </div>

    <!-- 6. STATUS DO SERVIDOR (PING) -->
    <div class="sidebar-tile">
      <div class="tile-icon" id="sServerIcon">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
      </div>
      <div class="tile-content">
        <div class="tile-num small" id="sServerStatus">-</div>
        <div class="tile-sub" id="sServerIp">192.168.190.187</div>
        <div class="tile-lbl">Servidor Coletor</div>
      </div>
    </div>

    <!-- 7. OLT INFO -->
    <div class="sidebar-tile">
      <div class="tile-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
      </div>
      <div class="tile-content">
        <div class="tile-num small" style="font-size:13px;" id="sOltModel">C-Data FD1108S</div>
        <div class="tile-sub" id="sOltIp">192.168.1.100</div>
        <div class="tile-lbl">OLT Principal</div>
      </div>
    </div>

    <!-- FOOTER CLOCK & REFRESH -->
    <div class="sidebar-footer">
      <div>Hora: <b id="clock">-</b></div>
      <div>Refresh: <b id="next">-</b>s</div>
    </div>
  </div>
</div>

<!-- MODAL SCANNER DE DESCOBERTA DE ONUS -->
<div id="scannerModal" class="modal-backdrop" style="display:none;">
  <div class="modal-dialog">
    <div class="modal-header">
      <div style="display:flex;align-items:center;gap:8px;">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0072bc" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <h3>Scanner de Rede &mdash; Descoberta de Novos MACs na OLT</h3>
      </div>
      <button class="modal-close" onclick="closeScannerModal()">&times;</button>
    </div>

    <div class="modal-subbar">
      <div style="display:flex;align-items:center;gap:8px;flex:1;">
        <input type="text" id="scanSearch" class="scan-filter-input" placeholder="Filtrar por MAC, porta ou descri&ccedil;&atilde;o..." oninput="renderScanList()">
        <select id="scanFilter" class="digi-select" onchange="renderScanList()">
          <option value="unregistered" selected>Novos Dispositivos (MAC N&atilde;o Registrado)</option>
          <option value="online">Apenas Novos Online</option>
          <option value="all">Todas as ONUs (Incluir MACs j&aacute; registrados)</option>
          <option value="registered">Apenas MACs J&aacute; Registrados</option>
        </select>
      </div>
      <button class="digi-btn" onclick="fetchScanData()" title="Atualizar varredura agora">&#x1F504; Re-escanear</button>
    </div>

    <div class="modal-body">
      <div id="scanTableWrap"></div>
    </div>

    <div class="modal-footer">
      <div style="display:flex;align-items:center;gap:12px;">
        <label class="digi-check" style="font-weight:600;">
          <input type="checkbox" id="scanSelectAll" onchange="toggleSelectAllScan(this.checked)">
          <span>Selecionar Todas</span>
        </label>
        <span id="scanCountInfo" style="color:#64748b;font-size:12px;">0 selecionadas</span>
      </div>
      <div style="display:flex;align-items:center;gap:8px;">
        <button class="digi-btn" onclick="closeScannerModal()">Cancelar</button>
        <button class="digi-btn primary" id="btnBatchAdd" onclick="submitBatchAdd()" style="font-weight:600;">+ Adicionar MACs Selecionados ao Monitoramento</button>
      </div>
    </div>
  </div>
</div>

<!-- MODAL DE DETALHES E GERENCIAMENTO DA ONU -->
<div id="onuDetailModal" class="modal-backdrop" style="display:none;">
  <div class="modal-dialog" style="max-width:680px;height:auto;max-height:90vh;">
    <div class="modal-header">
      <div style="display:flex;align-items:center;gap:10px;">
        <span class="onu-badge-icon" style="width:22px;height:22px;">
          <svg viewBox="0 0 20 20" width="22" height="22" fill="none"><rect width="20" height="20" rx="4" fill="#0284c7"/><path d="M5.5 8L4 3M14.5 8L16 3" stroke="#ffffff" stroke-width="1.6" stroke-linecap="round"/><rect x="3" y="8" width="14" height="8" rx="1.5" fill="#ffffff"/><circle cx="6" cy="12" r="0.9" fill="#0284c7"/><circle cx="9" cy="12" r="0.9" fill="#0284c7"/><circle cx="12" cy="12" r="0.9" fill="#0284c7"/><circle cx="14.8" cy="12" r="0.7" fill="#16a34a"/></svg>
        </span>
        <div>
          <h3 id="odmTitle" style="font-size:16px;margin:0;font-weight:800;color:#0f172a;">Painel de Gerenciamento da ONU</h3>
          <span id="odmSubtitle" style="font-size:11px;color:#64748b;">Informa&ccedil;&otilde;es t&eacute;cnicas, portas e c&acirc;meras vinculadas</span>
        </div>
      </div>
      <button class="modal-close" onclick="closeOnuModal()">&times;</button>
    </div>
    <div class="modal-body" style="padding:18px 22px;display:flex;flex-direction:column;gap:14px;">
      
      <!-- CARD DE DADOS TÉCNICOS DA ONU -->
      <div style="background:#f8fafc;border:1px solid #cbd5e1;border-radius:8px;padding:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;border-bottom:1px solid #e2e8f0;padding-bottom:8px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-weight:800;font-size:16px;color:#0284c7;" id="odmTitlePointName">Ponto XX</span>
            <span id="odmMultiBadge" style="display:none;" class="badge-multi">2 Portas LAN</span>
          </div>
          <span id="odmStatus" class="stt-sim"><span class="stt-dot"></span>Online</span>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:12px;">
          <div>
            <span style="color:#64748b;">Nome do Ponto:</span><br>
            <div style="display:flex;align-items:center;gap:6px;margin-top:2px;">
              <b id="odmPointName" style="font-size:14px;color:#0284c7;">-</b>
              <button class="digi-btn" style="padding:1px 6px;font-size:10px;" onclick="editPointNameFromModal()" title="Editar Nome do Ponto">✏️ Alterar</button>
            </div>
          </div>
          <div>
            <span style="color:#64748b;">Descri&ccedil;&atilde;o (Rua / Local):</span><br>
            <div style="display:flex;align-items:center;gap:6px;margin-top:2px;">
              <b id="odmStreetDesc" style="font-size:13px;color:#334155;">-</b>
              <button class="digi-btn" style="padding:1px 6px;font-size:10px;" onclick="editStreetDescFromModal()" title="Editar Rua / Local">✏️ Alterar</button>
            </div>
          </div>
          <div>
            <span style="color:#64748b;">Porta / Canal OLT:</span><br>
            <b id="odmSlotPort" style="font-size:12px;font-family:Consolas,monospace;color:#475569;margin-top:2px;display:inline-block;">-</b>
          </div>
          <div>
            <span style="color:#64748b;">Fabricante / Modelo da ONU:</span><br>
            <b id="odmVendor" style="font-size:13px;color:#334155;margin-top:2px;display:inline-block;">-</b>
          </div>
          <div>
            <span style="color:#64748b;">Endere&ccedil;o(s) MAC da ONU:</span><br>
            <div id="odmSerialSingle" style="display:flex;align-items:center;gap:6px;margin-top:2px;">
              <span class="mac-badge" id="odmSerial">-</span>
              <button class="copy-mini-btn" onclick="copyToClipboard(document.getElementById('odmSerial').textContent, this)" title="Copiar MAC">📋</button>
            </div>
            <div id="odmSerialMulti" style="display:none;margin-top:2px;">
              <div style="font-size:11px;color:#0284c7;display:flex;align-items:center;gap:4px;">
                <b>LAN 1:</b> <span class="mac-badge" id="odmSerial1">-</span>
                <button class="copy-mini-btn" onclick="copyToClipboard(document.getElementById('odmSerial1').textContent, this)" title="Copiar MAC LAN 1">📋</button>
              </div>
              <div style="font-size:11px;color:#0284c7;display:flex;align-items:center;gap:4px;margin-top:3px;">
                <b>LAN 2:</b> <span class="mac-badge" id="odmSerial2">-</span>
                <button class="copy-mini-btn" onclick="copyToClipboard(document.getElementById('odmSerial2').textContent, this)" title="Copiar MAC LAN 2">📋</button>
              </div>
            </div>
          </div>
          <div>
            <span style="color:#64748b;">Tempo no Status Atual:</span><br>
            <b id="odmUptimeDetailed" style="font-size:13px;color:#0f172a;margin-top:2px;display:inline-block;">-</b><br>
            <span id="odmStatusSince" style="font-size:11px;color:#64748b;">-</span>
          </div>
        </div>
      </div>

      <!-- SEÇÃO DE CÂMERAS E MACS VINCULADOS NA ONU -->
      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <div style="font-weight:700;font-size:13px;color:#166534;display:flex;align-items:center;gap:6px;">
            <span>📹 Endere&ccedil;os MAC e C&acirc;meras Vinculadas</span>
            <span id="odmCamsCount" style="background:#dcfce7;color:#15803d;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:800;">0</span>
          </div>
        </div>
        
        <div id="odmCamsList" style="display:flex;flex-direction:column;gap:8px;"></div>
      </div>

      <!-- AÇÕES DE GERENCIAMENTO -->
      <div style="display:flex;justify-content:space-between;align-items:center;background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:10px 14px;">
        <span style="font-size:12px;color:#64748b;">A&ccedil;&otilde;es do Dispositivo:</span>
        <div style="display:flex;gap:8px;">
          <button class="digi-btn" onclick="editLabelFromOnuModal()">✏️ Renomear Ponto</button>
          <button class="del-btn" style="opacity:1;padding:4px 8px;font-size:12px;background:#fee2e2;color:#dc2626;border-radius:4px;" onclick="deleteOnuFromModal()">🗑️ Excluir do Monitoramento</button>
        </div>
      </div>

    </div>
    <div class="modal-footer" style="justify-content:flex-end;">
      <button class="digi-btn" onclick="closeOnuModal()">Fechar</button>
    </div>
  </div>
</div>

<!-- MODAL CENTRAL DE INCIDENTES E EVENTOS -->
<div id="incidentsModal" class="modal-backdrop" style="display:none;">
  <div class="modal-dialog" style="max-width:1050px;height:86vh;">
    <div class="modal-header" style="background:#ffffff;border-bottom:1px solid #e2e8f0;padding:12px 18px;">
      <h3 style="color:#0f172a;font-size:15px;font-weight:700;margin:0;">Hist&oacute;rico de Incidentes &amp; Eventos</h3>
      <button class="modal-close" onclick="closeIncidentsModal()">&times;</button>
    </div>

    <!-- BARRA DE CONTROLE MINIMALISTA -->
    <div style="background:#f8fafc;border-bottom:1px solid #e2e8f0;padding:8px 18px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
      <!-- ABAS LIMPAS -->
      <div style="display:flex;gap:6px;align-items:center;">
        <button class="digi-btn primary" id="incTabProblems" onclick="setIncTab('problems')" style="padding:5px 12px;font-size:12px;font-weight:600;">
          Problemas Ativos <span id="incTabProblemsNum" style="background:#dc2626;color:#fff;padding:1px 6px;border-radius:10px;font-size:10px;margin-left:3px;">0</span>
        </button>
        <button class="digi-btn" id="incTabAll" onclick="setIncTab('all')" style="padding:5px 12px;font-size:12px;font-weight:600;">
          Todos os Eventos <span id="incTabAllNum" style="background:#e2e8f0;color:#475569;padding:1px 6px;border-radius:10px;font-size:10px;margin-left:3px;">0</span>
        </button>
        <button class="digi-btn" id="incTabResolved" onclick="setIncTab('resolved')" style="padding:5px 12px;font-size:12px;font-weight:600;">
          Resolvidos <span id="incTabResolvedNum" style="background:#dcfce7;color:#166534;padding:1px 6px;border-radius:10px;font-size:10px;margin-left:3px;">0</span>
        </button>
      </div>

      <!-- FILTROS E EXPORTAÇÃO -->
      <div style="display:flex;align-items:center;gap:8px;">
        <select id="incPeriodFilter" onchange="renderIncidentsTable()" class="digi-select" style="padding:4px 8px;font-size:12px;height:30px;">
          <option value="all" selected>Todo o Hist&oacute;rico (100)</option>
          <option value="today">Hoje</option>
          <option value="24h">&Uacute;ltimas 24 horas</option>
          <option value="7d">&Uacute;ltimos 7 dias</option>
          <option value="30d">&Uacute;ltimos 30 dias</option>
        </select>
        <input type="text" id="incSearch" class="scan-filter-input" placeholder="Filtrar por Ponto, Rua, MAC..." oninput="renderIncidentsTable()" style="width:190px;height:30px;font-size:12px;">
        <a href="/export_events" class="digi-btn" style="text-decoration:none;font-size:12px;height:30px;display:inline-flex;align-items:center;padding:0 10px;" title="Exportar hist&oacute;rico em CSV">Exportar CSV</a>
      </div>
    </div>

    <!-- CORPO COM A TABELA -->
    <div class="modal-body" style="padding:0;overflow-y:auto;flex:1;">
      <div id="incidentsTableWrap"></div>
    </div>

    <div class="modal-footer" style="justify-content:space-between;background:#f8fafc;padding:8px 18px;">
      <span style="font-size:11px;color:#94a3b8;" id="incFooterInfo">Hist&oacute;rico permanente limitado a 100 registros mais recentes.</span>
      <button class="digi-btn" onclick="closeIncidentsModal()">Fechar</button>
    </div>
  </div>
</div>

<script>
var REFRESH = """ + str(REFRESH) + """;
var ALL = null, BENCH = [], FELL = {};
var st = 'all', pf = 'all', q = '';
var showOff = true, showCams = true, showSlot = true, autoRefreshEnabled = true;
var sortKey = '', sortDir = 1;
var CURRENT_MODAL_ONU = null;

try {
  var savedShowCams = localStorage.getItem('onuShowCams');
  if(savedShowCams !== null) showCams = (savedShowCams === 'true');
  var savedShowOff = localStorage.getItem('onuShowOff');
  if(savedShowOff !== null) showOff = (savedShowOff === 'true');
  var savedShowSlot = localStorage.getItem('onuShowSlot');
  if(savedShowSlot !== null) showSlot = (savedShowSlot === 'true');
} catch(e) {}

function toggleShowCams(checked){
  showCams = checked;
  try { localStorage.setItem('onuShowCams', String(checked)); } catch(e) {}
  render();
}

function toggleShowSlot(checked){
  showSlot = checked;
  try { localStorage.setItem('onuShowSlot', String(checked)); } catch(e) {}
  render();
}

function copyToClipboard(text, btn){
  if(!text) return;
  text = text.trim();
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(function(){
      if(btn){
        var old = btn.innerHTML;
        btn.innerHTML = '✓ Copiado';
        btn.style.color = '#16a34a';
        setTimeout(function(){ btn.innerHTML = old; btn.style.color = ''; }, 1500);
      }
    }).catch(function(){
      prompt('Copie o endereço MAC abaixo (Ctrl+C):', text);
    });
  } else {
    prompt('Copie o endereço MAC abaixo (Ctrl+C):', text);
  }
}

function detectDeviceVendor(mac){
  if(!mac) return '';
  var m = mac.replace(/[:-]/g, '').toUpperCase();
  if(m.startsWith('001A3F') || m.startsWith('488AD2') || m.startsWith('E0508B') || m.startsWith('9002A9')) return 'Intelbras';
  if(m.startsWith('58108C') || m.startsWith('546CAC') || m.startsWith('4CBD8F') || m.startsWith('C42F90') || m.startsWith('BC5451')) return 'Hikvision';
  if(m.startsWith('98E55B') || m.startsWith('3CEF8C') || m.startsWith('E4246C') || m.startsWith('F4E2C6')) return 'Dahua';
  if(m.startsWith('00408C') || m.startsWith('ACCC8E')) return 'Axis';
  if(m.startsWith('00A102')) return 'C-Data';
  if(m.startsWith('001946') || m.startsWith('8014A8')) return 'Cianet';
  if(m.startsWith('52544C')) return 'Interface Bridge/VM';
  return 'Câmera / Dispositivo';
}

function openOnuModal(port, id, focusCamIp){
  var r = (ALL && ALL.rows || []).find(function(x){ return x.port === port && String(x.id) === String(id); });
  if(!r) return;
  CURRENT_MODAL_ONU = r;

  var slotCode = esc(r.port) + '_' + String(r.id).padStart(3, '0');
  var displayName = r.name ? esc(r.name) : slotCode;
  
  document.getElementById('odmTitle').innerHTML = 'Painel da ONU &mdash; ' + displayName;
  document.getElementById('odmTitlePointName').textContent = displayName;
  document.getElementById('odmPointName').textContent = r.name || '(sem ponto cadastrado)';
  document.getElementById('odmStreetDesc').textContent = r.desc || '(sem rua cadastrada)';
  document.getElementById('odmSlotPort').textContent = slotCode;
  
  var multiBadge = document.getElementById('odmMultiBadge');
  if(r.multi_llid){
    multiBadge.style.display = 'inline-block';
    multiBadge.textContent = '2 Portas LAN (Canais ' + r.id + ' e ' + r.secondary_id + ')';
    document.getElementById('odmSerialSingle').style.display = 'none';
    document.getElementById('odmSerialMulti').style.display = 'block';
    document.getElementById('odmSerial1').textContent = r.serial || '-';
    document.getElementById('odmSerial2').textContent = r.secondary_serial || '-';
  } else {
    multiBadge.style.display = 'none';
    document.getElementById('odmSerialSingle').style.display = 'flex';
    document.getElementById('odmSerialMulti').style.display = 'none';
    document.getElementById('odmSerial').textContent = r.serial || '-';
  }

  var isOnline = (r.status === 'Online');
  var sttEl = document.getElementById('odmStatus');
  sttEl.className = isOnline ? 'stt-sim' : 'stt-nao';
  sttEl.innerHTML = '<span class="stt-dot"></span>' + (isOnline ? 'Online' : 'Offline');

  document.getElementById('odmVendor').textContent = r.vendor || 'C-Data';
  var uptDetailEl = document.getElementById('odmUptimeDetailed');
  uptDetailEl.textContent = r.uptime_detailed || ((r.status === 'Online' ? 'Online' : 'Offline') + ' há ' + (r.uptime || '-'));
  uptDetailEl.style.color = isOnline ? '#0f172a' : '#dc2626';
  document.getElementById('odmStatusSince').textContent = r.status_since ? ('Desde: ' + r.status_since) : '';

  // Renderiza a lista de câmeras e MACs conectados
  var camsList = document.getElementById('odmCamsList');
  var camsCount = document.getElementById('odmCamsCount');
  var cams = r.cameras || [];
  camsCount.textContent = cams.length;

  if(!cams.length){
    camsList.innerHTML = '<div style="color:#64748b;font-size:12px;text-align:center;padding:12px;">Nenhum dispositivo/câmera com tráfego detectado nesta ONU no momento.</div>';
  } else {
    var html = '';
    cams.forEach(function(c, idx){
      var isFocused = (focusCamIp && c.ip === focusCamIp);
      var borderHighlight = isFocused ? 'border:2px solid #16a34a;background:#dcfce7;' : 'border:1px solid #bbf7d0;background:#ffffff;'
      var camIp = c.ip || '(IP direto / sem ARP)';
      var camMac = c.mac || '-';
      var vendor = detectDeviceVendor(camMac);
      var webBtn = (c.ip && (c.ip.startsWith('10.') || c.ip.startsWith('192.168.')))
        ? '<a href="http://' + esc(c.ip) + '" target="_blank" class="digi-btn primary" style="font-size:11px;padding:4px 9px;text-decoration:none;display:inline-flex;align-items:center;gap:4px;">🌐 Abrir Web &nearr;</a>'
        : '';

      html += '<div class="cam-modal-row" style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-radius:6px;gap:12px;' + borderHighlight + '">'
           +  '  <div style="display:flex;align-items:flex-start;gap:10px;">'
           +  '    <span style="font-size:20px;margin-top:2px;">📹</span>'
           +  '    <div>'
           +  '      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
           +  '        <span class="mac-chip"><b>MAC:</b> ' + esc(camMac) + '</span>'
           +  '        <button class="copy-mini-btn" onclick="copyToClipboard(&quot;' + esc(camMac) + '&quot;, this)" title="Copiar endereço MAC">📋 Copiar</button>'
           +  '        <span class="vendor-badge">' + esc(vendor) + '</span>'
           +  '      </div>'
           +  '      <div style="font-size:12px;margin-top:4px;color:#475569;">'
           +  '        <span style="color:#64748b;">IP Conectado:</span> <b style="font-family:Consolas,monospace;color:#0f172a;font-size:13px;">' + esc(camIp) + '</b>'
           +  '      </div>'
           +  '    </div>'
           +  '  </div>'
           +  '  <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
           +  '    <button class="digi-btn" id="btnPing_' + idx + '" onclick="testPingFromOnuModal(&quot;' + esc(c.ip) + '&quot;, ' + idx + ')" style="font-size:11px;padding:4px 10px;">⚡ Ping</button>'
           +       webBtn
           +  '  </div>'
           +  '</div>'
           +  '<div id="pingRes_' + idx + '" style="font-size:11px;display:none;padding-left:36px;"></div>';
    });
    camsList.innerHTML = html;
  }

  document.getElementById('onuDetailModal').style.display = 'flex';
}

function closeOnuModal(){
  document.getElementById('onuDetailModal').style.display = 'none';
}

function editPointNameFromModal(){
  if(!CURRENT_MODAL_ONU) return;
  editPointName(CURRENT_MODAL_ONU.port, CURRENT_MODAL_ONU.id);
}

function editStreetDescFromModal(){
  if(!CURRENT_MODAL_ONU) return;
  editStreetDesc(CURRENT_MODAL_ONU.port, CURRENT_MODAL_ONU.id);
}

function deleteOnuFromModal(){
  if(!CURRENT_MODAL_ONU) return;
  closeOnuModal();
  deleteOnu(CURRENT_MODAL_ONU.port, CURRENT_MODAL_ONU.id);
}

async function testPingFromOnuModal(ip, idx){
  if(!ip || ip.indexOf('(')>=0) return;
  var btn = document.getElementById('btnPing_' + idx);
  var res = document.getElementById('pingRes_' + idx);
  if(btn){ btn.disabled = true; btn.textContent = '⏳'; }
  if(res){ res.style.display = 'block'; res.innerHTML = '<span style="color:#0284c7;">Pingando ' + esc(ip) + '...</span>'; }

  try {
    var r = await fetch('/api/ping_camera?ip=' + encodeURIComponent(ip));
    var j = await r.json();
    if(j.online){
      if(res) res.innerHTML = '<b style="color:#16a34a;">✔ Online (Ping OK)</b>';
    } else {
      if(res) res.innerHTML = '<b style="color:#dc2626;">✖ Sem resposta de Ping</b>';
    }
  } catch(e){
    if(res) res.innerHTML = '<b style="color:#dc2626;">Erro:</b> ' + e;
  } finally {
    if(btn){ btn.disabled = false; btn.textContent = '⚡ Ping'; }
  }
}

try {
  var sk = localStorage.getItem('onuSortKey') || '';
  if(['port','id','status','serial','name','desc','label','vendor','ticks','uptime_seconds'].indexOf(sk)>=0) sortKey = sk;
  sortDir = localStorage.getItem('onuSortDir') === '-1' ? -1 : 1;
} catch(e) {}

function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
var ONU_ICON_HTML = '<span class="onu-badge-icon" title="Dispositivo ONU"><svg viewBox="0 0 20 20" width="17" height="17" fill="none"><rect width="20" height="20" rx="3.5" fill="#0284c7"/><path d="M5.5 8L4 3M14.5 8L16 3" stroke="#ffffff" stroke-width="1.6" stroke-linecap="round"/><rect x="3" y="8" width="14" height="8" rx="1.5" fill="#ffffff"/><circle cx="6" cy="12" r="0.9" fill="#0284c7"/><circle cx="9" cy="12" r="0.9" fill="#0284c7"/><circle cx="12" cy="12" r="0.9" fill="#0284c7"/><circle cx="14.8" cy="12" r="0.7" fill="#16a34a"/></svg></span>';

function formatPointName(val){
  if(!val) return '';
  var v = String(val).trim();
  if(!v || v === '??' || v === '-') return '';
  var mNum = v.match(/^(\\d+)$/);
  if(mNum){
    var n = parseInt(mNum[1], 10);
    return 'Ponto ' + String(n).padStart(2, '0');
  }
  var mPonto = v.match(/^(?:P(?:onto)?[_\\s-]*)(\\d+)$/i);
  if(mPonto){
    var n = parseInt(mPonto[1], 10);
    return 'Ponto ' + String(n).padStart(2, '0');
  }
  return v;
}

function editPointName(port, id){
  var r = (ALL && ALL.rows || []).find(function(x){ return x.port === port && String(x.id) === String(id); });
  var atual = (r && r.name) || '';
  var v = prompt('Informe o número ou nome do Ponto (ex: 1, 09, 22):', atual);
  if(v === null) return;
  var formatted = formatPointName(v);

  fetch('/label', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({port: port, id: id, name: formatted})
  })
  .then(function(res){ return res.json(); })
  .then(function(j){
    if(!j.ok){ alert('Falha ao salvar nome do ponto.'); return; }
    if(r){
      r.name = formatted;
      r.label = (formatted + ' ' + (r.desc || '')).trim();
    }
    delete FELL[port+'|'+id];
    render(); renderChanges(ALL);
    if(CURRENT_MODAL_ONU && CURRENT_MODAL_ONU.port === port && String(CURRENT_MODAL_ONU.id) === String(id)){
      openOnuModal(port, id);
    }
  })
  .catch(function(){ alert('Sem conexão com o servidor.'); });
}

function editStreetDesc(port, id){
  var r = (ALL && ALL.rows || []).find(function(x){ return x.port === port && String(x.id) === String(id); });
  var atual = (r && r.desc) || '';
  var v = prompt('Informe o nome da rua / local:', atual);
  if(v === null) return;
  v = v.trim();

  fetch('/label', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({port: port, id: id, desc: v})
  })
  .then(function(res){ return res.json(); })
  .then(function(j){
    if(!j.ok){ alert('Falha ao salvar rua/local.'); return; }
    if(r){
      r.desc = v;
      r.label = ((r.name || '') + ' ' + v).trim();
    }
    delete FELL[port+'|'+id];
    render(); renderChanges(ALL);
    if(CURRENT_MODAL_ONU && CURRENT_MODAL_ONU.port === port && String(CURRENT_MODAL_ONU.id) === String(id)){
      openOnuModal(port, id);
    }
  })
  .catch(function(){ alert('Sem conexão com o servidor.'); });
}

function deleteOnu(port, id){
  var r = (ALL.rows||[]).find(function(x){ return x.port === port && String(x.id) === String(id); });
  var name = (r && r.name) ? r.name : (esc(port) + '_' + String(id).padStart(3, '0'));
  var descText = (r && r.desc) ? ' ("' + r.desc + '")' : '';

  if(!confirm('Deseja excluir a ONU ' + name + descText + ' do monitoramento?\\n\\nEla saira do Dashboard principal e passara para a area do Scanner como novo dispositivo aguardando homologacao.')){
    return;
  }

  fetch('/delete_onu', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({port: port, id: id})
  })
  .then(function(res){ return res.json(); })
  .then(function(j){
    if(!j.ok){ alert('Falha ao excluir: ' + (j.error || 'Erro desconhecido')); return; }
    load();
    fetch('/api/scan').then(function(r){return r.json();}).then(function(d){updateScanBadge(d.unregistered_count);}).catch(function(){});
  })
  .catch(function(){ alert('Sem conexao com o servidor.'); });
}

function setSort(k){
  if(sortKey === k){ sortDir = -sortDir; } else { sortKey = k; sortDir = 1; }
  try {
    localStorage.setItem('onuSortKey', sortKey);
    localStorage.setItem('onuSortDir', String(sortDir));
  } catch(e) {}
  render();
}

function cmpRows(a, b){
  var va, vb;
  if(!sortKey){
    return (a.port === b.port) ? ((parseInt(a.id,10)||0) - (parseInt(b.id,10)||0))
                                : (a.port > b.port ? 1 : a.port < b.port ? -1 : 0);
  }
  if(sortKey === 'id' || sortKey === 'ticks' || sortKey === 'uptime_seconds'){
    va = parseFloat(a[sortKey]); if(isNaN(va)) va = Infinity;
    vb = parseFloat(b[sortKey]); if(isNaN(vb)) vb = Infinity;
    return (va - vb) * sortDir;
  }
  va = String(a[sortKey] == null ? '' : a[sortKey]);
  vb = String(b[sortKey] == null ? '' : b[sortKey]);
  if(sortKey === 'name' || sortKey === 'desc' || sortKey === 'label'){
    if(!va && !vb) return 0;
    if(!va) return 1;
    if(!vb) return -1;
    return va.localeCompare(vb, 'pt-BR', {numeric: true}) * sortDir;
  }
  return va.localeCompare(vb, 'pt-BR') * sortDir;
}

function thHtml(label, key, width){
  var style = width ? ' style="width:'+width+';"' : '';
  if(!key) return '<th'+style+'>'+label+'</th>';
  var arr = (key === sortKey) ? ' <span style="color:#0072bc;">'+(sortDir===1 ? '▲' : '▼')+'</span>' : '';
  return '<th class="sortable" title="Clique para ordenar" onclick="setSort(&quot;'+key+'&quot;)"'+style+'>'+label+arr+'</th>';
}

function render(){
  if(!ALL) return;
  var rows = ALL.rows.filter(function(r){
    if(!showOff && r.status!=='Online') return false;
    if(st==='on' && r.status!=='Online') return false;
    if(st==='off' && r.status!=='Offline') return false;
    if(pf!=='all' && r.port!==pf) return false;
    if(q){
      var qClean = q.replace(/[:-]/g, '');
      var ser1 = (r.serial || '').toLowerCase();
      var ser1Clean = ser1.replace(/[:-]/g, '');
      var ser2 = (r.secondary_serial || '').toLowerCase();
      var ser2Clean = ser2.replace(/[:-]/g, '');
      var camsText = (r.cameras || []).map(function(c){ 
        var cm = (c.mac || '').toLowerCase();
        return (c.ip || '') + ' ' + cm + ' ' + cm.replace(/[:-]/g, ''); 
      }).join(' ');
      var nameFull = (r.port + '_' + String(r.id).padStart(3, '0')).toLowerCase();
      var secNameFull = r.secondary_id ? (r.port + '_' + String(r.secondary_id).padStart(3, '0')).toLowerCase() : '';

      var matchQ = (ser1.indexOf(q)>=0 || ser1Clean.indexOf(qClean)>=0 ||
                    ser2.indexOf(q)>=0 || ser2Clean.indexOf(qClean)>=0 ||
                    String(r.id).indexOf(q)>=0 ||
                    (r.secondary_id && String(r.secondary_id).indexOf(q)>=0) ||
                    (r.name||'').toLowerCase().indexOf(q)>=0 ||
                    (r.desc||'').toLowerCase().indexOf(q)>=0 ||
                    (r.label||'').toLowerCase().indexOf(q)>=0 ||
                    r.port.toLowerCase().indexOf(q)>=0 ||
                    nameFull.indexOf(q)>=0 ||
                    secNameFull.indexOf(q)>=0 ||
                    (r.vendor||'').toLowerCase().indexOf(q)>=0 ||
                    camsText.indexOf(q)>=0 || (qClean && camsText.indexOf(qClean)>=0));
      if(!matchQ) return false;
    }
    return true;
  });

  document.getElementById('countText').textContent = rows.length+' de '+ALL.rows.length+' dispositivos';
  rows.sort(cmpRows);

  var colCount = 6 + (showCams ? 1 : 0) + (showSlot ? 1 : 0);
  var html = '<table class="digi-table"><thead><tr>'
          +  thHtml('Nome (Ponto)', 'name', '150px')
          +  thHtml('Em Funcionamento', 'status', '120px')
          +  thHtml('Endere&ccedil;o / Serial', 'serial', '135px')
          +  thHtml('Descri&ccedil;&atilde;o (Rua / Local)', 'desc', 'auto')
          +  (showCams ? thHtml('C&acirc;meras Conectadas', '', '240px') : '')
          +  thHtml('Fabricante', 'vendor', '95px')
          +  thHtml('Tempo no Status', 'uptime_seconds', '125px')
          +  (showSlot ? thHtml('Canal OLT', 'id', '115px') : '')
          +  thHtml('A&ccedil;&otilde;es', '', '85px')
          +  '</tr></thead><tbody>';

  if(!rows.length){
    html += '<tr><td colspan="'+colCount+'" style="text-align:center;padding:30px;color:#94a3b8;">Nenhum dispositivo encontrado para os filtros selecionados.</td></tr>';
  } else {
    rows.forEach(function(r){
      var fellCls = FELL[r.port+'|'+r.id] ? ' class="justfell"' : '';
      var isOnline = (r.status === 'Online');
      var sttHtml = isOnline ? '<span class="stt-sim"><span class="stt-dot"></span>Sim</span>'
                             : '<span class="stt-nao"><span class="stt-dot"></span>N&atilde;o</span>';

      var slotCode = esc(r.port) + '_' + String(r.id).padStart(3, '0');
      var pointNameDisplay = r.name ? '<span style="font-weight:800;font-size:13px;color:#0284c7;">' + esc(r.name) + '</span>'
                                    : '<span class="lbl-empty" style="font-size:12px;">+ nome do ponto</span>';

      var streetDescDisplay = r.desc ? '<span class="lbl-cell" onclick="editStreetDesc(&quot;'+esc(r.port)+'&quot;,&quot;'+esc(r.id)+'&quot;)" title="Clique para editar rua/local">'+esc(r.desc)+'</span>'
                                     : '<span class="lbl-empty lbl-cell" onclick="editStreetDesc(&quot;'+esc(r.port)+'&quot;,&quot;'+esc(r.id)+'&quot;)">+ adicionar rua</span>';

      var multiBadge = r.multi_llid ? '<span class="badge-multi" title="ONU 2 Portas LAN (Canais OLT '+esc(r.id)+' e '+esc(r.secondary_id)+')">2P</span>' : '';

      var camsHtml = '';
      if(r.cameras && r.cameras.length){
        camsHtml = '<div style="display:flex;flex-wrap:wrap;gap:4px;">';
        r.cameras.forEach(function(c){
          var camIp = c.ip || '(IP direto)';
          var camMac = c.mac || '';
          var titleText = 'Clique para abrir no menu da ONU | IP: ' + camIp + (camMac ? ' | MAC: ' + camMac : '');
          camsHtml += '<span class="cam-badge" onclick="openOnuModal(&quot;' + esc(r.port) + '&quot;,&quot;' + esc(r.id) + '&quot;,&quot;' + esc(c.ip) + '&quot;)" title="' + esc(titleText) + '">📹 ' + esc(camIp) + '</span>';
        });
        camsHtml += '</div>';
      } else {
        camsHtml = '<span style="color:#94a3b8;font-size:11px;">-</span>';
      }

      var nameHtml = '<div style="display:inline-flex;align-items:center;gap:6px;">'
                   + '  <span class="onu-badge-icon">' + ONU_ICON_HTML + '</span>'
                   + '  <span style="cursor:pointer;" onclick="openOnuModal(&quot;'+esc(r.port)+'&quot;,&quot;'+esc(r.id)+'&quot;)" title="Clique para abrir painel da ONU">' + pointNameDisplay + '</span>'
                   +    multiBadge
                   + '  <button class="edit-mini-btn" onclick="editPointName(&quot;'+esc(r.port)+'&quot;,&quot;'+esc(r.id)+'&quot;)" title="Editar Nome do Ponto">✏️</button>'
                   + '</div>';

      var slotHtml = '<span style="font-family:Consolas,monospace;font-size:11px;color:#475569;font-weight:600;cursor:pointer;" onclick="openOnuModal(&quot;'+esc(r.port)+'&quot;,&quot;'+esc(r.id)+'&quot;)" title="Clique para abrir painel da ONU">' + slotCode + '</span>';

      var descHtml = '<div style="display:flex;align-items:center;gap:5px;">'
                   +    streetDescDisplay
                   + '  <button class="edit-mini-btn" onclick="editStreetDesc(&quot;'+esc(r.port)+'&quot;,&quot;'+esc(r.id)+'&quot;)" title="Editar Rua / Local">✏️</button>'
                   + '</div>';

      var actionsHtml = '<div style="display:inline-flex;gap:4px;align-items:center;">'
                      + '<button class="digi-btn" style="padding:2px 7px;font-size:11px;background:#e0f2fe;color:#0369a1;border-color:#bae6fd;" onclick="openOnuModal(&quot;'+esc(r.port)+'&quot;,&quot;'+esc(r.id)+'&quot;)" title="Abrir menu de detalhes da ONU">🔍 Menu</button>'
                      + '<button class="del-btn" onclick="deleteOnu(&quot;'+esc(r.port)+'&quot;,&quot;'+esc(r.id)+'&quot;)" title="Excluir ONU do monitoramento">🗑️</button>'
                      + '</div>';

      var uptimeTooltip = (r.status === 'Online' ? 'Online contínuo' : 'Offline contínuo') + (r.status_since ? (' desde ' + r.status_since) : '');
      var uptimeClass = isOnline ? 'uptime-txt' : 'uptime-txt off';
      var uptimeHtml = '<span class="' + uptimeClass + '" title="' + esc(uptimeTooltip) + '">' + esc(r.uptime || '-') + '</span>';

      html += '<tr'+fellCls+'>'
           +  '<td>'+nameHtml+'</td>'
           +  '<td>'+sttHtml+'</td>'
           +  '<td><span class="serial-txt">'+esc(r.serial||'-')+'</span></td>'
           +  '<td>'+descHtml+'</td>'
           +  (showCams ? '<td>'+camsHtml+'</td>' : '')
           +  '<td><span class="vendor-tag">'+esc(r.vendor)+'</span></td>'
           +  '<td>'+uptimeHtml+'</td>'
           +  (showSlot ? '<td>'+slotHtml+'</td>' : '')
           +  '<td style="text-align:center;">'+actionsHtml+'</td>'
           +  '</tr>';
    });
  }
  html += '</tbody></table>';
  document.getElementById('tableWrap').innerHTML = html;
}

async function syncCameras(btn){
  if(btn){
    btn.disabled = true;
    btn.innerHTML = '<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span> <span>Mapeando...</span>';
  }
  try {
    var r = await fetch('/api/sync_cameras', {method: 'POST'});
    var res = await r.json();
    if(res.ok){
      await load();
    } else {
      alert('Aviso ao sincronizar câmeras: ' + (res.error || 'Erro'));
    }
  } catch(e){
    console.error(e);
  } finally {
    if(btn){
      btn.disabled = false;
      btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg> <span>Atualizar C&acirc;meras</span>';
    }
  }
}

var curWindow = '15';
function setWindow(v){
  curWindow = v;
  var selMain = document.getElementById('selWindow');
  if(selMain) selMain.value = v;
  var selInc = document.getElementById('incSelWindow');
  if(selInc) selInc.value = v;
  load();
}

function toggleShowOff(checked){
  showOff = checked;
  try { localStorage.setItem('onuShowOff', String(checked)); } catch(e) {}
  render();
}

function toggleTimeline(checked){
  document.getElementById('timelineSection').style.display = checked ? 'block' : 'none';
}

function toggleBench(checked){
  document.getElementById('benchSection').style.display = checked ? 'block' : 'none';
}

function toggleAutoRefresh(checked){
  autoRefreshEnabled = checked;
}

// CENTRAL DE INCIDENTES E EVENTOS
// CENTRAL DE INCIDENTES E EVENTOS (ESTILO ZABBIX)
var CURRENT_INC_TAB = 'problems'; // 'problems', 'all', 'resolved'

function openIncidentsModal(){
  document.getElementById('incidentsModal').style.display = 'flex';
  renderIncidentsTable();
}

function closeIncidentsModal(){
  document.getElementById('incidentsModal').style.display = 'none';
}

function setIncTab(tab){
  CURRENT_INC_TAB = tab;
  ['problems', 'all', 'resolved'].forEach(function(t){
    var btn = document.getElementById('incTab' + t.charAt(0).toUpperCase() + t.slice(1));
    if(btn){
      btn.className = (t === tab) ? 'digi-btn primary' : 'digi-btn';
    }
  });
  renderIncidentsTable();
}

function renderIncidentsTable(){
  if(!ALL) return;
  var problems = ALL.active_problems || [];
  var historyEvents = ALL.events_history || [];

  // Contadores
  var resolvedCount = historyEvents.filter(function(e){ return e.status === 'RESOLVED' || e.type === 'rose'; }).length;
  
  var elAct = document.getElementById('incActiveProblemsCount');
  if(elAct) elAct.textContent = problems.length;
  var elRes = document.getElementById('incResolvedCount');
  if(elRes) elRes.textContent = resolvedCount;
  var elTot = document.getElementById('incHistoryTotalCount');
  if(elTot) elTot.textContent = historyEvents.length;

  var elTabProb = document.getElementById('incTabProblemsNum');
  if(elTabProb) elTabProb.textContent = problems.length;
  var elTabAll = document.getElementById('incTabAllNum');
  if(elTabAll) elTabAll.textContent = historyEvents.length;
  var elTabRes = document.getElementById('incTabResolvedNum');
  if(elTabRes) elTabRes.textContent = resolvedCount;

  // Badge e estilo do botao superior
  var btnInc = document.getElementById('btnIncidents');
  var badge = document.getElementById('incidentsBadge');
  if(problems.length > 0){
    if(btnInc){
      btnInc.style.background = '#fff1f2';
      btnInc.style.color = '#be123c';
      btnInc.style.borderColor = '#fecdd3';
    }
    if(badge){
      badge.textContent = problems.length;
      badge.style.display = 'inline-block';
      badge.style.background = '#be123c';
    }
  } else {
    if(btnInc){
      btnInc.style.background = '#ffffff';
      btnInc.style.color = '#334155';
      btnInc.style.borderColor = '#cbd5e1';
    }
    if(badge){
      badge.textContent = '0';
      badge.style.display = 'none';
    }
  }

  var wrap = document.getElementById('incidentsTableWrap');
  if(!wrap) return;

  var qInc = (document.getElementById('incSearch') ? document.getElementById('incSearch').value : '').trim().toLowerCase();
  var period = document.getElementById('incPeriodFilter') ? document.getElementById('incPeriodFilter').value : 'all';

  var now = new Date();

  function matchSearch(item){
    if(!qInc) return true;
    var qClean = qInc.replace(/[:-]/g, '');
    var pt = (item.point_name || item.name || '').toLowerCase();
    var ru = (item.street_desc || item.desc || item.label || '').toLowerCase();
    var sl = (item.slot_code || (item.port + '_' + (item.onu_id || item.id)) || '').toLowerCase();
    var ser = (item.serial || '').toLowerCase();
    var serClean = ser.replace(/[:-]/g, '');
    return pt.indexOf(qInc)>=0 || ru.indexOf(qInc)>=0 || sl.indexOf(qInc)>=0 || ser.indexOf(qInc)>=0 || serClean.indexOf(qClean)>=0;
  }

  function matchPeriod(item){
    if(period === 'all') return true;
    if(!item.timestamp) return true;
    var dt = new Date(item.timestamp);
    if(isNaN(dt.getTime())) return true;
    var diffMs = now - dt;
    if(period === 'today') return dt.toDateString() === now.toDateString();
    if(period === '24h') return diffMs <= 24 * 3600 * 1000;
    if(period === '7d') return diffMs <= 7 * 24 * 3600 * 1000;
    if(period === '30d') return diffMs <= 30 * 24 * 3600 * 1000;
    return true;
  }

  if(CURRENT_INC_TAB === 'problems'){
    // ABA: PROBLEMAS ATIVOS (OFFLINE AGORA)
    var list = problems.filter(matchSearch);
    if(!list.length){
      wrap.innerHTML = '<div style="text-align:center;padding:50px 20px;color:#64748b;">'
                     + '  <div style="font-size:14px;font-weight:600;color:#0f172a;">Nenhum problema ativo</div>'
                     + '  <div style="font-size:12px;color:#94a3b8;margin-top:2px;">Todas as ' + (ALL.total || 0) + ' ONUs monitoradas est\u00e3o em funcionamento.</div>'
                     + '</div>';
      return;
    }

    var html = '<table class="digi-table"><thead><tr>'
             + '<th style="width:110px;">Status</th>'
             + '<th style="width:160px;">Nome (Ponto)</th>'
             + '<th>Descri&ccedil;&atilde;o (Rua / Local)</th>'
             + '<th style="width:125px;">Canal OLT</th>'
             + '<th style="width:135px;">Endere&ccedil;o / MAC</th>'
             + '<th style="width:150px;">Queda Desde</th>'
             + '<th style="width:110px;">Dura&ccedil;&atilde;o</th>'
             + '<th style="width:75px;text-align:center;">A&ccedil;&otilde;es</th>'
             + '</tr></thead><tbody>';

    list.forEach(function(item){
      var ptName = item.point_name
        ? '<span style="font-weight:700;color:#0f172a;">' + esc(item.point_name) + '</span>'
        : '<span class="lbl-empty">-</span>';
      var ruDesc = item.street_desc
        ? '<span style="color:#0f172a;font-weight:500;">' + esc(item.street_desc) + '</span>'
        : '<span class="lbl-empty">-</span>';
      var slotCode = esc(item.slot_code || (item.port + '_' + String(item.onu_id || item.id).padStart(3, '0')));

      html += '<tr>'
           +  '<td><span class="badge-fell"><span class="status-dot red"></span>Offline</span></td>'
           +  '<td>' + ptName + '</td>'
           +  '<td>' + ruDesc + '</td>'
           +  '<td><span style="font-family:Consolas,monospace;font-size:11px;color:#475569;">' + slotCode + '</span></td>'
           +  '<td><span class="serial-txt">' + esc(item.serial || '-') + '</span></td>'
           +  '<td><span style="font-family:Consolas,monospace;font-size:11px;color:#64748b;">' + esc(item.since || '-') + '</span></td>'
           +  '<td><span style="font-family:Consolas,monospace;font-size:11px;font-weight:600;color:#dc2626;" title="' + esc(item.duration_detailed || '') + '">' + esc(item.duration || '-') + '</span></td>'
           +  '<td style="text-align:center;"><button class="digi-btn" style="padding:2px 8px;font-size:11px;" onclick="closeIncidentsModal();openOnuModal(&quot;' + esc(item.port) + '&quot;,&quot;' + esc(item.onu_id || item.id) + '&quot;)">Ver</button></td>'
           +  '</tr>';
    });

    html += '</tbody></table>';
    wrap.innerHTML = html;

  } else {
    // ABA: HISTÓRICO GERAL OU APENAS RESOLVIDOS
    var list = historyEvents.slice();
    if(CURRENT_INC_TAB === 'resolved'){
      list = list.filter(function(e){ return e.status === 'RESOLVED' || e.type === 'rose'; });
    }
    list = list.filter(matchPeriod).filter(matchSearch);

    if(!list.length){
      wrap.innerHTML = '<div style="text-align:center;padding:50px 20px;color:#64748b;">'
                     + '  <div style="font-size:14px;font-weight:600;color:#0f172a;">Nenhum registro encontrado</div>'
                     + '  <div style="font-size:12px;color:#94a3b8;margin-top:2px;">Nenhum evento registrado para os filtros selecionados.</div>'
                     + '</div>';
      return;
    }

    var html = '<table class="digi-table"><thead><tr>'
             + '<th style="width:110px;">Status</th>'
             + '<th style="width:160px;">Nome (Ponto)</th>'
             + '<th>Descri&ccedil;&atilde;o (Rua / Local)</th>'
             + '<th style="width:125px;">Canal OLT</th>'
             + '<th style="width:135px;">Endere&ccedil;o / MAC</th>'
             + '<th style="width:150px;">Data e Hor&aacute;rio</th>'
             + '<th style="width:120px;">Tempo Fora</th>'
             + '<th style="width:75px;text-align:center;">A&ccedil;&otilde;es</th>'
             + '</tr></thead><tbody>';

    list.forEach(function(item){
      var isResolved = (item.status === 'RESOLVED' || item.type === 'rose');
      var badgeHtml = isResolved
        ? '<span class="badge-rose"><span class="status-dot green"></span>Online</span>'
        : '<span class="badge-fell"><span class="status-dot red"></span>Offline</span>';

      var ptName = (item.point_name || item.name)
        ? '<span style="font-weight:700;color:#0f172a;">' + esc(item.point_name || item.name) + '</span>'
        : '<span class="lbl-empty">-</span>';
      var ruDesc = (item.street_desc || item.desc)
        ? '<span style="color:#0f172a;font-weight:500;">' + esc(item.street_desc || item.desc) + '</span>'
        : '<span class="lbl-empty">-</span>';
      var slotCode = esc(item.slot_code || (item.port + '_' + String(item.onu_id || item.id).padStart(3, '0')));
      var timeDisplay = esc(item.datetime || item.time || '-');
      var downtimeDisplay = isResolved
        ? ('<span style="font-family:Consolas,monospace;font-size:11px;color:#166534;font-weight:600;">' + esc(item.downtime_formatted || 'recente') + '</span>')
        : '<span style="color:#94a3b8;font-size:11px;">-</span>';

      html += '<tr>'
           +  '<td>' + badgeHtml + '</td>'
           +  '<td>' + ptName + '</td>'
           +  '<td>' + ruDesc + '</td>'
           +  '<td><span style="font-family:Consolas,monospace;font-size:11px;color:#475569;">' + slotCode + '</span></td>'
           +  '<td><span class="serial-txt">' + esc(item.serial || '-') + '</span></td>'
           +  '<td><span style="font-family:Consolas,monospace;font-size:11px;color:#64748b;">' + timeDisplay + '</span></td>'
           +  '<td>' + downtimeDisplay + '</td>'
           +  '<td style="text-align:center;"><button class="digi-btn" style="padding:2px 8px;font-size:11px;" onclick="closeIncidentsModal();openOnuModal(&quot;' + esc(item.port) + '&quot;,&quot;' + esc(item.onu_id || item.id) + '&quot;)">Ver</button></td>'
           +  '</tr>';
    });

    html += '</tbody></table>';
    wrap.innerHTML = html;
  }
}

function renderChanges(d){
  var w = document.getElementById('changesWrap');
  if(!w) return;
  var problems = d.active_problems || [];
  var history = (d.events_history || []).slice(0, 10);

  var html = '<div class="events-grid">';

  html += '<div class="change-card"><h4 style="color:#0f172a;"><span>Problemas Ativos (' + problems.length + ')</span></h4><ul>';
  if(problems.length){
    problems.forEach(function(r){
      var ptName = r.point_name ? ('<b>' + esc(r.point_name) + '</b>') : ('<b>' + esc(r.slot_code) + '</b>');
      var stDesc = r.street_desc ? (' &mdash; <span style="color:#0f172a;font-weight:500;">' + esc(r.street_desc) + '</span>') : '';
      html += '<li style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;">'
           +  '<div><span class="badge-fell" style="margin-right:6px;"><span class="status-dot red"></span>Offline</span>' + ptName + stDesc + ' <span class="serial-txt" style="font-size:10px;">(' + esc(r.serial||'-') + ')</span> <span style="color:#dc2626;font-size:11px;font-weight:600;">(' + esc(r.duration||'-') + ')</span></div>'
           +  '<button class="digi-btn" style="padding:1px 6px;font-size:10px;" onclick="openOnuModal(&quot;' + esc(r.port) + '&quot;,&quot;' + esc(r.onu_id||r.id) + '&quot;)">Ver</button>'
           +  '</li>';
    });
  } else {
    html += '<li style="color:#16a34a;padding:6px 0;font-weight:600;">Nenhuma ONU fora do ar no momento.</li>';
  }
  html += '</ul></div>';

  html += '<div class="change-card"><h4 style="color:#0f172a;"><span>Hist&oacute;rico Recente (' + history.length + ')</span></h4><ul>';
  if(history.length){
    history.forEach(function(r){
      var isRes = (r.status === 'RESOLVED' || r.type === 'rose');
      var badge = isRes ? '<span class="badge-rose" style="margin-right:6px;"><span class="status-dot green"></span>Online</span>' : '<span class="badge-fell" style="margin-right:6px;"><span class="status-dot red"></span>Offline</span>';
      var ptName = r.point_name ? ('<b>' + esc(r.point_name) + '</b>') : ('<b>' + esc(r.slot_code || (r.port + '_' + r.onu_id)) + '</b>');
      var stDesc = r.street_desc ? (' &mdash; <span style="color:#0f172a;font-weight:500;">' + esc(r.street_desc) + '</span>') : '';
      var durInfo = isRes && r.downtime_formatted ? (' <span style="color:#166534;font-size:10px;font-weight:600;">(fora por ' + esc(r.downtime_formatted) + ')</span>') : '';
      html += '<li style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;">'
           +  '<div>' + badge + '<span style="font-size:10px;color:#64748b;margin-right:6px;">' + esc(r.time || '-') + '</span>' + ptName + stDesc + durInfo + '</div>'
           +  '<button class="digi-btn" style="padding:1px 6px;font-size:10px;" onclick="openOnuModal(&quot;' + esc(r.port) + '&quot;,&quot;' + esc(r.onu_id||r.id) + '&quot;)">Ver</button>'
           +  '</li>';
    });
  } else {
    html += '<li style="color:#94a3b8;padding:6px 0;">Nenhum hist\u00f3rico registrado ainda.</li>';
  }
  html += '</ul></div></div>';
  w.innerHTML = html;
}

function renderEvents(events){
  var w = document.getElementById('eventsWrap');
  if(!w) return;
  if(!events || !events.length){ w.innerHTML=''; return; }
  var html = '<div style="font-weight:700;font-size:11px;color:#1e3a8a;margin:8px 0 4px;">Hist&oacute;rico Recente de Transi&ccedil;&otilde;es</div><ul style="list-style:none;font-size:11px;padding:0;">';
  events.slice(0, 15).forEach(function(ev){
    var isResolved = (ev.status === 'RESOLVED' || ev.type === 'rose');
    var badge = isResolved ? '<span class="badge-rose" style="margin-right:6px;"><span class="status-dot green"></span>Online</span>' : '<span class="badge-fell" style="margin-right:6px;"><span class="status-dot red"></span>Offline</span>';
    var ptName = ev.point_name ? ('<b>' + esc(ev.point_name) + '</b>') : ('<b>' + esc(ev.slot_code || (ev.port + '_' + String(ev.onu_id || ev.id).padStart(3, '0'))) + '</b>');
    var stDesc = ev.street_desc ? (' &mdash; <span style="color:#0f172a;font-weight:500;">' + esc(ev.street_desc) + '</span>') : '';
    var durInfo = isResolved && ev.downtime_formatted ? (' <span style="color:#166534;font-size:10px;font-weight:600;">(fora por ' + esc(ev.downtime_formatted) + ')</span>') : '';

    html += '<li style="padding:4px 0;border-bottom:1px solid #f1f5f9;display:flex;justify-content:space-between;align-items:center;">'
         +  '<div style="display:flex;align-items:center;gap:8px;">'
         +  '  <span style="color:#64748b;font-weight:600;min-width:55px;">'+esc(ev.time || '-')+'</span>'
         +     badge
         +  '  <span>' + ptName + stDesc + durInfo + '</span>'
         +  '  <span class="serial-txt" style="font-size:10px;">('+esc(ev.serial||'-')+')</span>'
         +  '</div>'
         +  '<button class="digi-btn" style="padding:1px 6px;font-size:10px;" onclick="openOnuModal(&quot;' + esc(ev.port) + '&quot;,&quot;' + esc(ev.onu_id || ev.id) + '&quot;)">Ver</button>'
         +  '</li>';
  });
  html += '</ul>';
  w.innerHTML = html;
}

async function load(){
  try {
    var r = await fetch('/data?window=' + encodeURIComponent(curWindow));
    var d = await r.json();
    ALL = d; BENCH = d.bench||[];
    FELL = {};
    (d.changes.fell||[]).forEach(function(r){ FELL[r.port+'|'+r.id] = true; });

    // Atualiza Sidebar Digifort
    document.getElementById('sTotal').textContent = d.total;
    document.getElementById('sOn').textContent = d.online;
    document.getElementById('sOff').textContent = d.offline;
    if(document.getElementById('sCams')) document.getElementById('sCams').textContent = d.total_cameras || 0;

    var timeParts = (d.coleta_formatted || '-').split(' às ');
    document.getElementById('sDate').textContent = timeParts[0] || '-';
    document.getElementById('sTime').textContent = timeParts[1] || d.coleta_formatted || '-';

    // Portas PON breakdown na Sidebar
    var portsHtml = '';
    (d.ports||[]).forEach(function(p){
      portsHtml += '<div class="port-item"><span>'+esc(p.port)+'</span><b>'+p.online+' / '+p.total+'</b></div>';
    });
    document.getElementById('sPortsList').innerHTML = portsHtml;

    // Servidor Ping
    var srv = d.server || { online: false, ip: '192.168.190.187' };
    var sStatus = document.getElementById('sServerStatus');
    var sIcon = document.getElementById('sServerIcon');
    var warnBanner = document.getElementById('serverWarnBanner');
    var srvIpEl = document.getElementById('sServerIp');
    if(srvIpEl && srv.ip) srvIpEl.textContent = srv.ip;

    if(srv.online){
      if(sStatus){ sStatus.textContent = 'Ping OK'; sStatus.style.color = '#86efac'; }
      if(sIcon) sIcon.className = 'tile-icon green';
      if(warnBanner) warnBanner.style.display = 'none';
    } else {
      if(sStatus){ sStatus.textContent = 'Sem Ping'; sStatus.style.color = '#fca5a5'; }
      if(sIcon) sIcon.className = 'tile-icon red';
      if(warnBanner){
        warnBanner.style.display = 'flex';
        var warnIp = document.getElementById('serverWarnIp');
        if(warnIp) warnIp.textContent = srv.ip || '192.168.190.187';
      }
    }

    // Port Select Options
    var psel = document.getElementById('fPort');
    var cur = psel.value;
    var opts = '<option value="all">Todas as Portas PON</option>';
    (d.ports||[]).forEach(function(p){ opts += '<option value="'+esc(p.port)+'">'+esc(p.port)+'</option>'; });
    psel.innerHTML = opts;
    psel.value = Array.from(psel.options).some(function(o){return o.value===cur;}) ? cur : 'all';

    render();
    renderChanges(d);
    renderEvents(d.events_history || d.events || []);
    renderIncidentsTable();

    // Bancada
    var bh = '<table class="digi-table"><thead><tr><th>R&oacute;tulo</th><th>MAC</th><th>IP</th><th>Status</th></tr></thead><tbody>';
    BENCH.forEach(function(b){
      var isBOn = (b.status === 'Online');
      var bStt = isBOn ? '<span class="stt-sim"><span class="stt-dot"></span>Sim</span>'
                       : '<span class="stt-nao"><span class="stt-dot"></span>N&atilde;o</span>';
      bh += '<tr><td>'+esc(b.label)+'</td><td><span class="serial-txt">'+esc(b.mac||'-')+'</span></td><td>'+esc(b.ip)+'</td><td>'+bStt+'</td></tr>';
    });
    bh += '</tbody></table>';
    document.getElementById('benchWrap').innerHTML = bh;

    tickLeft = REFRESH;
    fetchScanData();
  } catch(e){
    console.error(e);
  }
}

// SCANNER DE ONUS
var SCAN_DATA = [];
var SCAN_SELECTED = {};

function openScannerModal(){
  document.getElementById('scannerModal').style.display = 'flex';
  var wrap = document.getElementById('scanTableWrap');
  if(!SCAN_DATA.length && wrap){
    wrap.innerHTML = '<div style="text-align:center;padding:40px;color:#0284c7;font-size:13px;font-weight:600;">&#x1F50D; Varrendo portas PON da OLT em tempo real...</div>';
  }
  fetchScanData();
}

function closeScannerModal(){
  document.getElementById('scannerModal').style.display = 'none';
}

async function fetchScanData(){
  try {
    var r = await fetch('/api/scan');
    var d = await r.json();
    var oldSelected = SCAN_SELECTED || {};
    var oldLabels = {};
    (SCAN_DATA||[]).forEach(function(x){
      if(x.tempLabel) oldLabels[x.port + '|' + x.id] = x.tempLabel;
    });

    SCAN_DATA = d.devices || [];
    SCAN_SELECTED = {};
    SCAN_DATA.forEach(function(x){
      var k = x.port + '|' + x.id;
      if(oldLabels[k]) x.tempLabel = oldLabels[k];
      if(oldSelected[k] !== undefined){
        SCAN_SELECTED[k] = oldSelected[k];
      } else if(x.is_unregistered){
        SCAN_SELECTED[k] = true;
      }
    });

    updateScanBadge(d.unregistered_count);
    renderScanList();
  } catch(e){
    console.error(e);
  }
}

function updateScanBadge(unregisteredCount){
  var b = document.getElementById('scanBadge');
  if(b){
    if(unregisteredCount > 0){
      b.style.display = 'inline-block';
      b.textContent = unregisteredCount + (unregisteredCount === 1 ? ' novo MAC' : ' novos MACs');
    } else {
      b.style.display = 'none';
    }
  }
}

function renderScanList(){
  var filt = document.getElementById('scanFilter').value;
  var q = (document.getElementById('scanSearch').value || '').trim().toLowerCase();

  var list = SCAN_DATA.filter(function(d){
    if(filt === 'unregistered' && d.is_registered) return false;
    if(filt === 'online' && (d.status !== 'Online' || d.is_registered)) return false;
    if(filt === 'registered' && !d.is_registered) return false;
    if(q){
      var match = (d.name.toLowerCase().indexOf(q)>=0 ||
                   d.serial.toLowerCase().indexOf(q)>=0 ||
                   (d.label||'').toLowerCase().indexOf(q)>=0 ||
                   d.vendor.toLowerCase().indexOf(q)>=0);
      if(!match) return false;
    }
    return true;
  });

  var selCount = 0;
  var html = '<table class="digi-table"><thead><tr>'
           + '<th style="width:36px;text-align:center;">#</th>'
           + '<th style="width:150px;">Nome / Porta</th>'
           + '<th style="width:105px;">Status</th>'
           + '<th style="width:150px;">Endere&ccedil;o MAC / Serial</th>'
           + '<th style="width:95px;">Fabricante</th>'
           + '<th>Descri&ccedil;&atilde;o / Ponto <span style="font-size:10px;font-weight:normal;color:#64748b;">(opcional)</span></th>'
           + '</tr></thead><tbody>';

  if(!list.length){
    html += '<tr><td colspan="6" style="text-align:center;padding:35px;color:#94a3b8;font-size:13px;">'
         + (filt === 'unregistered' || filt === 'online'
            ? '✨ <b>Nenhum novo dispositivo pendente!</b><br><span style="font-size:11px;color:#64748b;">Todos os endere&ccedil;os MAC/Seriais detectados na rede j&aacute; est&atilde;o registrados no monitoramento.</span>'
            : 'Nenhum dispositivo encontrado para os filtros selecionados.')
         + '</td></tr>';
  } else {
    list.forEach(function(d){
      var key = d.port + '|' + d.id;
      var isChecked = !!SCAN_SELECTED[key];
      if(isChecked) selCount++;
      var isOnline = (d.status === 'Online');
      var sttHtml = isOnline ? '<span class="stt-sim"><span class="stt-dot"></span>Online</span>'
                             : '<span class="stt-nao"><span class="stt-dot"></span>Offline</span>';

      var curVal = d.tempLabel != null ? d.tempLabel : (d.label || '');

      var fieldHtml = d.is_registered && filt !== 'unregistered'
        ? '<div style="display:flex;align-items:center;gap:6px;"><span class="badge-unlabeled" style="background:#dcfce7;color:#15803d;border-color:#86efac;font-size:10px;padding:1px 6px;border-radius:3px;">✔ MAC Registrado</span><span style="color:#0369a1;">'+esc(d.label || '(sem descrição)')+'</span></div>'
        : '<input type="text" class="scan-label-input" id="lbl_'+esc(d.port)+'_'+esc(d.id)+'" value="'+esc(curVal)+'" placeholder="Nome do Ponto / Rua (opcional)" oninput="updateTempLabel(&quot;'+esc(d.port)+'&quot;,&quot;'+esc(d.id)+'&quot;,this.value)">';

      var multiBadge = d.multi_llid ? '<span class="badge-multi" title="ONU 2 Portas LAN (Canais OLT '+esc(d.id)+' e '+esc(d.secondary_id)+')">2P LAN</span>' : '';
      html += '<tr>'
           + '<td style="text-align:center;"><input type="checkbox" '+(isChecked?'checked':'')+' onchange="toggleScanItem(&quot;'+esc(d.port)+'&quot;,&quot;'+esc(d.id)+'&quot;,this.checked)"></td>'
           + '<td><div class="dev-name">'+ONU_ICON_HTML+'<span>'+esc(d.name)+'</span>'+multiBadge+'</div></td>'
           + '<td>'+sttHtml+'</td>'
           + '<td><span class="serial-txt" style="font-size:12px;font-weight:700;color:#0f172a;">'+esc(d.serial||'-')+'</span></td>'
           + '<td><span class="vendor-tag">'+esc(d.vendor)+'</span></td>'
           + '<td>'+fieldHtml+'</td>'
           + '</tr>';
    });
  }
  html += '</tbody></table>';
  document.getElementById('scanTableWrap').innerHTML = html;
  document.getElementById('scanCountInfo').textContent = selCount + ' selecionadas de ' + list.length;
}

function toggleScanItem(port, id, checked){
  var key = port + '|' + id;
  if(checked) SCAN_SELECTED[key] = true;
  else delete SCAN_SELECTED[key];
  renderScanList();
}

function toggleSelectAllScan(checked){
  var filt = document.getElementById('scanFilter').value;
  var q = (document.getElementById('scanSearch').value || '').trim().toLowerCase();
  SCAN_DATA.forEach(function(d){
    if(filt === 'unregistered' && d.is_registered) return;
    if(filt === 'online' && (d.status !== 'Online' || d.is_registered)) return;
    if(filt === 'registered' && !d.is_registered) return;
    if(q){
      var match = (d.name.toLowerCase().indexOf(q)>=0 || d.serial.toLowerCase().indexOf(q)>=0);
      if(!match) return;
    }
    var key = d.port + '|' + d.id;
    if(checked) SCAN_SELECTED[key] = true;
    else delete SCAN_SELECTED[key];
  });
  renderScanList();
}

function updateTempLabel(port, id, val){
  var d = SCAN_DATA.find(function(x){ return x.port === port && String(x.id) === String(id); });
  if(d) d.tempLabel = val;
  if(val && val.trim()){
    SCAN_SELECTED[port + '|' + id] = true;
    var countEl = document.getElementById('scanCountInfo');
    var selCount = Object.keys(SCAN_SELECTED).length;
    if(countEl) countEl.textContent = selCount + ' selecionadas';
  }
}

async function submitBatchAdd(){
  var toAdd = [];
  SCAN_DATA.forEach(function(d){
    var key = d.port + '|' + d.id;
    if(SCAN_SELECTED[key]){
      var inp = document.getElementById('lbl_' + d.port + '_' + d.id);
      var finalLabel = inp ? inp.value.trim() : (d.tempLabel || d.label || '').trim();
      toAdd.push({
        port: d.port,
        id: d.id,
        serial: d.serial,
        label: finalLabel
      });
    }
  });

  if(!toAdd.length){
    alert('Nenhum dispositivo selecionado.');
    return;
  }

  var btn = document.getElementById('btnBatchAdd');
  var origText = btn ? btn.textContent : '';
  if(btn){
    btn.disabled = true;
    btn.textContent = 'Adicionando ao monitoramento...';
  }

  try {
    var r = await fetch('/api/add_devices', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(toAdd)
    });
    var j = await r.json();
    if(j.ok){
      // Atualizacao instantanea no estado local
      toAdd.forEach(function(item){
        var k = item.port + '|' + item.id;
        delete SCAN_SELECTED[k];
        var d = SCAN_DATA.find(function(x){ return x.port === item.port && String(x.id) === String(item.id); });
        if(d){
          d.is_registered = true;
          d.is_unregistered = false;
          if(item.label) d.label = item.label;
        }
      });
      var remainingUnreg = SCAN_DATA.filter(function(x){ return x.is_unregistered; }).length;
      updateScanBadge(remainingUnreg);
      renderScanList();
      closeScannerModal();
      load();
      fetchScanData();
    } else {
      alert('Falha ao adicionar: ' + (j.error || 'Erro desconhecido'));
    }
  } catch(e){
    alert('Sem conexao com o servidor.');
  } finally {
    if(btn){
      btn.disabled = false;
      btn.textContent = origText;
    }
  }
}

// Filtros de busca
var sInput = document.getElementById('fSearch');
var cBtn = document.getElementById('clearBtn');

sInput.addEventListener('input', function(e){
  q = e.target.value.trim().toLowerCase();
  cBtn.style.display = q ? 'block' : 'none';
  render();
});
cBtn.addEventListener('click', function(){
  sInput.value = '';
  q = '';
  cBtn.style.display = 'none';
  render();
});

document.getElementById('fStatus').addEventListener('change', function(e){ st = e.target.value; render(); });
document.getElementById('fPort').addEventListener('change', function(e){ pf = e.target.value; render(); });

var tickLeft = REFRESH;
setInterval(function(){
  if(autoRefreshEnabled){
    tickLeft--;
    if(tickLeft <= 0){
      tickLeft = REFRESH;
      load();
    }
  }
  document.getElementById('next').textContent = tickLeft;
}, 1000);

setInterval(function(){
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('pt-BR');
}, 1000);

var elShowCams = document.getElementById('chkShowCams');
if(elShowCams) elShowCams.checked = showCams;
var elShowOff = document.getElementById('chkShowOff');
if(elShowOff) elShowOff.checked = showOff;
var elShowSlot = document.getElementById('chkShowSlot');
if(elShowSlot) elShowSlot.checked = showSlot;

load();
// Checa novas ONUs para o badge do Scanner
fetch('/api/scan').then(function(r){return r.json();}).then(function(d){updateScanBadge(d.unregistered_count);}).catch(function(){});
</script>
</body>
</html>"""


def latest_csv():
    files = [f for f in glob.glob(os.path.join(LOGS_DIR, "onus_*.csv")) if os.path.getsize(f) > 100]
    if not files:
        return None, None
    latest = max(files, key=os.path.basename)
    return latest, os.path.basename(latest)


def read_snapshot(path):
    out = {}
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                port = (row.get("Slot-PON") or "").strip()
                try:
                    oid = int((row.get("ONU_ID") or "0").strip())
                except ValueError:
                    continue
                status = (row.get("Status") or "").strip().lower()
                serial = (row.get("Serial") or "").strip()
                out[(port, oid)] = {"online": status == "online", "serial": serial}
    except OSError:
        pass
    return out


def get_monitored_onus():
    """Retorna o conjunto de todas as ONUs homologadas/cadastradas e seus seriais de forma rapida."""
    monitored = set()
    serials = {}
    ignored = load_ignored()
    registered = load_registered()
    labels = load_labels()

    for key_str, ser in registered.items():
        if "|" in key_str and key_str not in ignored:
            p, i_s = key_str.split("|", 1)
            try:
                oid = int(i_s)
                monitored.add((p, oid))
                if ser:
                    serials[(p, oid)] = ser
            except ValueError:
                pass

    for lbl_key in labels:
        if "|" in lbl_key and lbl_key not in ignored:
            p, i_s = lbl_key.split("|", 1)
            try:
                oid = int(i_s)
                monitored.add((p, oid))
            except ValueError:
                pass

    return monitored, serials


def parse_snapshot_time(filename):
    if not filename:
        return None
    m = re.search(r"onus_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.csv", filename)
    if m:
        return datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6]))
    return None


def format_dt(dt):
    if not dt:
        return "-"
    return dt.strftime("%d/%m/%Y às %H:%M:%S")


def history_changes(cur_path, cur_name, window="15"):
    files = sorted([f for f in glob.glob(os.path.join(LOGS_DIR, "onus_*.csv")) if os.path.getsize(f) > 100],
                   key=os.path.basename, reverse=True)
    cur_dt = parse_snapshot_time(cur_name)
    prev_file = None

    if len(files) >= 2:
        if window == "1":
            prev_file = next((f for f in files if os.path.basename(f) != cur_name), None)
        elif window == "today":
            if cur_dt:
                day_files = [f for f in reversed(files) if parse_snapshot_time(os.path.basename(f)) and parse_snapshot_time(os.path.basename(f)).date() == cur_dt.date()]
                if day_files:
                    prev_file = day_files[0]
            if not prev_file:
                prev_file = files[-1]
        else:
            try:
                mins = int(window)
            except ValueError:
                mins = 15
            target_dt = cur_dt - timedelta(minutes=mins) if cur_dt else None
            if target_dt:
                best_diff = None
                for f in files:
                    if os.path.basename(f) == cur_name:
                        continue
                    f_dt = parse_snapshot_time(os.path.basename(f))
                    if f_dt:
                        diff = abs((f_dt - target_dt).total_seconds())
                        if best_diff is None or diff < best_diff:
                            best_diff = diff
                            prev_file = f
            if not prev_file:
                prev_file = next((f for f in files if os.path.basename(f) != cur_name), None)

    prev_name = os.path.basename(prev_file) if prev_file else None
    prev_dt = parse_snapshot_time(prev_name)

    res = {
        "fell": [], "rose": [],
        "current": cur_name,
        "current_time": format_dt(cur_dt),
        "previous": prev_name,
        "previous_time": format_dt(prev_dt),
        "window": str(window)
    }
    if not prev_file or not cur_path:
        return res

    labels = load_labels()
    ignored = load_ignored()
    _, known_serials = get_monitored_onus()
    cur = read_snapshot(cur_path)
    prev = read_snapshot(prev_file)

    for key, v in cur.items():
        if f"{key[0]}|{key[1]}" in ignored:
            continue
        p = prev.get(key)
        if v["online"] and (p is None or not p["online"]):
            ser = v["serial"] or known_serials.get(key, "")
            p_name, p_desc = parse_label_info(labels.get(f"{key[0]}|{key[1]}"))
            lbl_str = f"{p_name} {p_desc}".strip() if (p_name or p_desc) else ""
            res["rose"].append({
                "port": key[0], "id": str(key[1]), "serial": ser,
                "vendor": vendor_of(ser),
                "name": p_name,
                "desc": p_desc,
                "point_name": p_name,
                "street_desc": p_desc,
                "label": lbl_str
            })

    for key, v in prev.items():
        if f"{key[0]}|{key[1]}" in ignored:
            continue
        c = cur.get(key)
        if v["online"] and (c is None or not c["online"]):
            ser = v["serial"] or known_serials.get(key, "")
            p_name, p_desc = parse_label_info(labels.get(f"{key[0]}|{key[1]}"))
            lbl_str = f"{p_name} {p_desc}".strip() if (p_name or p_desc) else ""
            res["fell"].append({
                "port": key[0], "id": str(key[1]), "serial": ser,
                "vendor": vendor_of(ser),
                "name": p_name,
                "desc": p_desc,
                "point_name": p_name,
                "street_desc": p_desc,
                "label": lbl_str
            })

    keyf = lambda x: (x["port"], int(x["id"]))
    res["rose"].sort(key=keyf)
    res["fell"].sort(key=keyf)
    return res


def get_recent_events(limit=40):
    files = sorted(glob.glob(os.path.join(LOGS_DIR, "onus_*.csv")), key=os.path.basename)
    if len(files) < 2:
        return []

    labels = load_labels()
    ignored = load_ignored()
    _, known_serials = get_monitored_onus()
    events = []
    prev_states = None

    for fpath in files[-60:]:
        fname = os.path.basename(fpath)
        f_dt = parse_snapshot_time(fname)
        time_str = f_dt.strftime("%H:%M:%S") if f_dt else fname
        dt_full = f_dt.strftime("%d/%m/%Y %H:%M:%S") if f_dt else fname
        cur_states = read_snapshot(fpath)

        if prev_states is not None:
            for key, prev_info in prev_states.items():
                if f"{key[0]}|{key[1]}" in ignored:
                    continue
                cur_info = cur_states.get(key)
                if prev_info["online"] and (cur_info is None or not cur_info["online"]):
                    ser = prev_info["serial"] or known_serials.get(key, "")
                    p_name, p_desc = parse_label_info(labels.get(f"{key[0]}|{key[1]}"))
                    lbl_str = f"{p_name} {p_desc}".strip() if (p_name or p_desc) else ""
                    events.append({
                        "type": "fell",
                        "time": time_str,
                        "datetime": dt_full,
                        "port": key[0],
                        "id": str(key[1]),
                        "serial": ser,
                        "vendor": vendor_of(ser),
                        "name": p_name,
                        "desc": p_desc,
                        "point_name": p_name,
                        "street_desc": p_desc,
                        "label": lbl_str,
                    })
            for key, cur_info in cur_states.items():
                if f"{key[0]}|{key[1]}" in ignored:
                    continue
                prev_info = prev_states.get(key)
                if cur_info["online"] and (prev_info is None or not prev_info["online"]):
                    ser = cur_info["serial"] or known_serials.get(key, "")
                    p_name, p_desc = parse_label_info(labels.get(f"{key[0]}|{key[1]}"))
                    lbl_str = f"{p_name} {p_desc}".strip() if (p_name or p_desc) else ""
                    events.append({
                        "type": "rose",
                        "time": time_str,
                        "datetime": dt_full,
                        "port": key[0],
                        "id": str(key[1]),
                        "serial": ser,
                        "vendor": vendor_of(ser),
                        "name": p_name,
                        "desc": p_desc,
                        "point_name": p_name,
                        "street_desc": p_desc,
                        "label": lbl_str,
                    })
        prev_states = cur_states

    events.reverse()
    return events[:limit]


bench_state = {}

def ping_device(ip):
    try:
        cmd = ["ping", "-n", "1", "-w", "500", ip] if os.name == "nt" else ["ping", "-c", "1", "-W", "1", ip]
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        return r.returncode == 0
    except Exception:
        return False


def bench_ping_loop():
    while True:
        try:
            for d in BENCH_DEVICES:
                bench_state[d["ip"]] = ping_device(d["ip"])
        except Exception:
            pass
        time.sleep(5)


def bench_data():
    out = []
    for d in BENCH_DEVICES:
        out.append({
            "ip": d["ip"],
            "label": d.get("label", d["ip"]),
            "mac": d.get("mac", ""),
            "status": "Online" if bench_state.get(d["ip"], False) else "Offline",
        })
    return out


def load_data(window="15"):
    path, name = latest_csv()
    coleta_formatted = "-"
    if name:
        m = re.match(r"onus_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.csv", name)
        if m:
            coleta_formatted = f"{m.group(3)}/{m.group(2)}/{m.group(1)} às {m.group(4)}:{m.group(5)}:{m.group(6)}"
        else:
            coleta_formatted = name

    data = {
        "file": name, "coleta_formatted": coleta_formatted,
        "total": 0, "online": 0, "offline": 0,
        "rows": [], "bench": bench_data(), "olt": OLT_INFO,
        "ports": [], "changes": history_changes(path, name, window),
        "events": get_recent_events(limit=10),
        "server": dict(server_ping_state),
    }
    if not path:
        return data

    monitored_keys, known_serials = get_monitored_onus()
    labels = load_labels()
    ignored = load_ignored()
    cam_map = load_cameras()
    cur_dt = parse_snapshot_time(name) or datetime.now()
    tracker = load_state_tracker()
    tracker_changed = False

    rows = []
    online = offline = 0
    ports = {}
    seen_in_snapshot = {}
    raw_rows = []

    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            port = (row.get("Slot-PON") or "").strip()
            oid_str = (row.get("ONU_ID") or "").strip()
            try:
                oid = int(oid_str)
            except ValueError:
                continue

            status = (row.get("Status") or "").strip()
            is_on = (status.lower() == "online")
            ser = (row.get("Serial") or "").strip()
            key_str = f"{port}|{oid}"

            if key_str in ignored:
                del_snap = ignored[key_str].get("deleted_snapshot", "")
                if is_on and (not del_snap or (name and name > del_snap)):
                    unignore_onu(port, oid)
                    ignored.pop(key_str, None)

            if ser and ser != "0":
                known_serials[(port, oid)] = ser

            seen_in_snapshot[(port, oid)] = {
                "status": "Online" if is_on else "Offline",
                "ticks": (row.get("UptimeTicks") or "0").strip(),
                "serial": ser,
            }
            raw_rows.append({
                "port": port,
                "id": oid,
                "serial": ser,
                "status": "Online" if is_on else "Offline",
                "ticks": (row.get("UptimeTicks") or "0").strip(),
            })

    secondary_keys, primary_info, secondary_to_primary = detect_multi_llid_map(raw_rows)

    for (port, oid) in monitored_keys:
        if (port, oid) in secondary_keys:
            continue

        if f"{port}|{oid}" in ignored:
            continue

        snap = seen_in_snapshot.get((port, oid))
        if snap:
            stt = snap["status"]
            ticks = snap["ticks"]
            ser = snap["serial"] or known_serials.get((port, oid), "")
        else:
            stt = "Offline"
            ticks = "0"
            ser = known_serials.get((port, oid), "")

        is_on = (stt == "Online")
        if is_on:
            online += 1
        else:
            offline += 1

        p = ports.setdefault(port, {"port": port, "online": 0, "total": 0})
        p["total"] += 1
        if is_on:
            p["online"] += 1

        key_str = f"{port}|{oid}"
        prev_tracker = tracker.get(key_str)
        if not prev_tracker:
            tracker[key_str] = {
                "status": stt,
                "since": cur_dt.isoformat(),
                "last_seen": cur_dt.isoformat(),
            }
            tracker_changed = True
            since_dt = cur_dt
        else:
            if prev_tracker.get("status") != stt:
                old_stt = prev_tracker.get("status")
                old_since_str = prev_tracker.get("since")
                tracker[key_str]["status"] = stt
                tracker[key_str]["since"] = cur_dt.isoformat()
                tracker_changed = True
                since_dt = cur_dt

                # Registra evento permanente no histórico
                slot_code = f"{port}_{str(oid).zfill(3)}"
                lbl_val_temp = labels.get(f"{port}|{oid}")
                p_name_temp, p_desc_temp = parse_label_info(lbl_val_temp)
                lbl_str_temp = f"{p_name_temp} {p_desc_temp}".strip() if (p_name_temp or p_desc_temp) else ""
                downtime_sec = 0
                downtime_str = "-"
                if old_stt == "Offline" and stt == "Online" and old_since_str:
                    try:
                        old_dt = datetime.fromisoformat(old_since_str)
                        downtime_sec = max(0.0, (cur_dt - old_dt).total_seconds())
                        downtime_str = format_uptime_duration(downtime_sec)
                    except Exception:
                        pass

                append_event_history({
                    "id": f"evt_{cur_dt.strftime('%Y%m%d_%H%M%S')}_{slot_code}_{'rose' if is_on else 'fell'}",
                    "timestamp": cur_dt.isoformat(),
                    "datetime": cur_dt.strftime("%d/%m/%Y às %H:%M:%S"),
                    "time": cur_dt.strftime("%H:%M:%S"),
                    "type": "rose" if is_on else "fell",
                    "status": "RESOLVED" if is_on else "PROBLEM",
                    "port": port,
                    "onu_id": str(oid),
                    "slot_code": slot_code,
                    "serial": ser,
                    "vendor": vendor_of(ser),
                    "point_name": p_name_temp,
                    "street_desc": p_desc_temp,
                    "label": lbl_str_temp,
                    "downtime_seconds": int(downtime_sec),
                    "downtime_formatted": downtime_str
                })
            else:
                try:
                    since_dt = datetime.fromisoformat(prev_tracker["since"])
                except Exception:
                    since_dt = cur_dt
            tracker[key_str]["last_seen"] = cur_dt.isoformat()

        elapsed_sec = max(0.0, (cur_dt - since_dt).total_seconds())
        uptime_str = format_uptime_duration(elapsed_sec)
        uptime_detailed = format_uptime_detailed(elapsed_sec, status=stt)
        since_fmt = since_dt.strftime("%d/%m/%Y às %H:%M:%S")

        lbl_val = labels.get(f"{port}|{oid}")
        pinfo = primary_info.get((port, oid))
        if not lbl_val and pinfo:
            lbl_val = labels.get(f"{port}|{pinfo['secondary_id']}")

        p_name, p_desc = parse_label_info(lbl_val)

        cams = list(cam_map.get(f"{port}|{oid}", []))
        if pinfo:
            sec_cams = cam_map.get(f"{port}|{pinfo['secondary_id']}", [])
            seen_m = {c.get("mac") for c in cams if c.get("mac")}
            for sc in sec_cams:
                if sc.get("mac") not in seen_m:
                    cams.append(sc)

        rows.append({
            "port": port,
            "id": str(oid),
            "status": stt,
            "serial": ser,
            "vendor": vendor_of(ser),
            "ticks": ticks,
            "uptime": uptime_str,
            "uptime_seconds": int(elapsed_sec),
            "uptime_detailed": uptime_detailed,
            "status_since": since_fmt,
            "name": p_name,
            "desc": p_desc,
            "label": f"{p_name} {p_desc}".strip() if (p_name or p_desc) else "",
            "cameras": cams,
            "multi_llid": bool(pinfo),
            "secondary_id": str(pinfo["secondary_id"]) if pinfo else "",
            "secondary_serial": str(pinfo["secondary_serial"]) if pinfo else "",
        })

    if tracker_changed:
        try:
            save_state_tracker(tracker)
        except Exception:
            pass

    rows.sort(key=lambda x: (x["port"], int(x["id"] or 0)))
    tot_cams = sum(len(r.get("cameras", [])) for r in rows)

    # Monta lista de problemas ativos (atualmente offline)
    active_problems = []
    for r in rows:
        if r["status"] == "Offline":
            active_problems.append({
                "port": r["port"],
                "onu_id": r["id"],
                "slot_code": f"{r['port']}_{str(r['id']).zfill(3)}",
                "point_name": r["name"],
                "street_desc": r["desc"],
                "label": r["label"],
                "serial": r["serial"],
                "vendor": r["vendor"],
                "since": r["status_since"],
                "duration": r["uptime"],
                "duration_seconds": r["uptime_seconds"],
                "duration_detailed": r["uptime_detailed"],
                "status": "PROBLEM"
            })
    active_problems.sort(key=lambda x: x["duration_seconds"], reverse=True)

    data.update({
        "total": online + offline, "online": online, "offline": offline,
        "total_cameras": tot_cams,
        "rows": rows, "ports": [ports[k] for k in sorted(ports)],
        "active_problems": active_problems,
        "events_history": load_events_history()[:MAX_EVENTS_HISTORY],
    })
    return data


def scan_all_onus():
    path, name = latest_csv()
    if not path:
        return {"total_found": 0, "unregistered_count": 0, "online_count": 0, "devices": []}

    labels = load_labels()
    ignored = load_ignored()
    registered = load_registered()
    monitored_keys, known_serials = get_monitored_onus()
    cam_map = load_cameras()

    raw_rows = []
    seen = set()

    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            port = (row.get("Slot-PON") or "").strip()
            oid_str = (row.get("ONU_ID") or "").strip()
            try:
                oid = int(oid_str)
            except ValueError:
                continue

            status = (row.get("Status") or "").strip()
            is_on = (status.lower() == "online")
            ser = (row.get("Serial") or "").strip()
            ticks = (row.get("UptimeTicks") or "0").strip()

            if not ser or ser == "0":
                ser = known_serials.get((port, oid), "")

            if not ser or ser == "0":
                continue

            raw_rows.append({
                "port": port,
                "id": oid,
                "serial": ser,
                "status": "Online" if is_on else "Offline",
                "ticks": ticks,
                "is_on": is_on,
            })

    secondary_keys, primary_info, secondary_to_primary = detect_multi_llid_map(raw_rows)

    dev_list = []
    for r in raw_rows:
        port = r["port"]
        oid = r["id"]
        key_str = f"{port}|{oid}"
        ser = r["serial"]
        is_on = r["is_on"]

        if (port, oid) in secondary_keys:
            continue

        is_reg = (key_str in registered) or (key_str in labels)
        is_ignored = (key_str in ignored)

        if not is_on and not is_reg:
            continue

        lbl_val = labels.get(key_str)
        pinfo = primary_info.get((port, oid))
        if not lbl_val and pinfo:
            lbl_val = labels.get(f"{port}|{pinfo['secondary_id']}")
        
        p_name, p_desc = parse_label_info(lbl_val)
        lbl_str = f"{p_name} {p_desc}".strip() if (p_name or p_desc) else ""

        cams = list(cam_map.get(key_str, []))
        if pinfo:
            sec_cams = cam_map.get(f"{port}|{pinfo['secondary_id']}", [])
            seen_m = {c.get("mac") for c in cams if c.get("mac")}
            for sc in sec_cams:
                if sc.get("mac") not in seen_m:
                    cams.append(sc)

        if key_str not in seen:
            seen.add(key_str)
            dev_list.append({
                "port": port,
                "id": str(oid),
                "name": p_name or f"{port}_{str(oid).zfill(3)}",
                "point_name": p_name,
                "street_desc": p_desc,
                "status": "Online" if is_on else "Offline",
                "serial": ser,
                "vendor": vendor_of(ser),
                "ticks": r["ticks"],
                "label": lbl_str,
                "cameras": cams,
                "is_registered": is_reg,
                "is_unregistered": not is_reg,
                "is_ignored": is_ignored,
                "multi_llid": bool(pinfo),
                "secondary_id": str(pinfo["secondary_id"]) if pinfo else "",
                "secondary_serial": str(pinfo["secondary_serial"]) if pinfo else "",
            })

    for (port, oid) in monitored_keys:
        if (port, oid) in secondary_keys:
            continue
        key_str = f"{port}|{oid}"
        if key_str not in seen and key_str not in ignored:
            ser = known_serials.get((port, oid), "")
            is_reg = (key_str in registered) or (key_str in labels)
            lbl_val = labels.get(key_str)
            p_name, p_desc = parse_label_info(lbl_val)
            lbl_str = f"{p_name} {p_desc}".strip() if (p_name or p_desc) else ""

            seen.add(key_str)
            dev_list.append({
                "port": port,
                "id": str(oid),
                "name": p_name or f"{port}_{str(oid).zfill(3)}",
                "point_name": p_name,
                "street_desc": p_desc,
                "status": "Offline",
                "serial": ser,
                "vendor": vendor_of(ser),
                "ticks": "0",
                "label": lbl_str,
                "is_registered": is_reg,
                "is_unregistered": not is_reg,
                "is_ignored": False,
                "multi_llid": False,
                "secondary_id": "",
                "secondary_serial": "",
            })

    dev_list.sort(key=lambda x: (x["port"], int(x["id"])))
    unregistered_devs = [d for d in dev_list if not d["is_registered"]]
    online_c = sum(1 for d in dev_list if d["status"] == "Online")

    return {
        "total_found": len(dev_list),
        "unregistered_count": len(unregistered_devs),
        "online_count": online_c,
        "devices": dev_list,
    }


class Handler(BaseHTTPRequestHandler):
    def address_string(self):
        return str(self.client_address[0])

    def log_message(self, *a):
        pass

    def _log_access(self):
        try:
            with open(os.path.join(LOGS_DIR, "dash_access.log"), "a", encoding="utf-8") as f:
                f.write(f"{threading.current_thread().name} {self.client_address[0]} {self.command} {self.path}\n")
        except OSError:
            pass

    def _send(self, body, ctype):
        self._log_access()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/data":
            qs = urllib.parse.parse_qs(parsed.query)
            window = qs.get("window", ["15"])[0]
            self._send(json.dumps(load_data(window=window)).encode("utf-8"), "application/json; charset=utf-8")
        elif parsed.path == "/api/scan":
            self._send(json.dumps(scan_all_onus()).encode("utf-8"), "application/json; charset=utf-8")
        elif parsed.path == "/api/ping_camera":
            qs = urllib.parse.parse_qs(parsed.query)
            ip = qs.get("ip", [""])[0].strip()
            if not ip:
                self._send(json.dumps({"ok": False, "error": "ip obrigatorio"}).encode("utf-8"), "application/json; charset=utf-8")
            else:
                is_on = ping_device(ip)
                self._send(json.dumps({"ok": True, "online": is_on, "ip": ip}).encode("utf-8"), "application/json; charset=utf-8")
        elif parsed.path == "/export":
            d = load_data()
            csv_lines = ["Nome_do_Ponto,Canal_OLT,Em_Funcionamento,Serial_MAC,Rua_Descricao,Fabricante,Tempo_no_Status,Status_Desde"]
            for r in d.get("rows", []):
                p_name = r.get("name") or "-"
                slot_fmt = f"{r['port']}_{str(r['id']).zfill(3)}"
                stt_fmt = "Sim" if r["status"] == "Online" else "Não"
                p_desc = r.get("desc") or ""
                upt_str = r.get("uptime") or "-"
                since_str = r.get("status_since") or "-"
                csv_lines.append(f'"{p_name}","{slot_fmt}","{stt_fmt}","{r["serial"]}","{p_desc}","{r["vendor"]}","{upt_str}","{since_str}"')
            content = "\n".join(csv_lines).encode("utf-8-sig")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f"attachment; filename=onus_monitoramento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif parsed.path == "/export_events":
            events = load_events_history()[:MAX_EVENTS_HISTORY]
            csv_lines = ["ID,Data_Hora,Tipo,Status,Nome_do_Ponto,Rua_Descricao,Canal_OLT,Serial_MAC,Fabricante,Tempo_Indisponivel"]
            for e in events:
                e_id = e.get("id", "")
                dt_str = e.get("datetime", "")
                tp = "Offline" if e.get("type") == "fell" else "Online"
                stt = "PROBLEMA" if e.get("status") == "PROBLEM" else "RESOLVIDO"
                p_name = e.get("point_name") or "-"
                p_desc = e.get("street_desc") or ""
                slot = e.get("slot_code") or f"{e.get('port')}_{str(e.get('onu_id')).zfill(3)}"
                ser = e.get("serial") or ""
                vend = e.get("vendor") or ""
                downtime = e.get("downtime_formatted") or "-"
                csv_lines.append(f'"{e_id}","{dt_str}","{tp}","{stt}","{p_name}","{p_desc}","{slot}","{ser}","{vend}","{downtime}"')
            content = "\n".join(csv_lines).encode("utf-8-sig")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f"attachment; filename=historico_eventos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif parsed.path in ("/", "/index.html"):
            self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/label":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                port = str(body.get("port") or "").strip()
                oid = str(body.get("id") or "").strip()
                name = body.get("name")
                desc = body.get("desc")
                if "label" in body and name is None and desc is None:
                    leg_name, leg_desc = parse_label_info(body["label"])
                    name, desc = leg_name, leg_desc
                if not port or not oid:
                    raise ValueError("port/id obrigatorios")
                save_label(port, oid, name=name, desc=desc)
                self._send(json.dumps({"ok": True}).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as e:
                self._send(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/delete_onu":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                port = str(body.get("port") or "").strip()
                oid = str(body.get("id") or "").strip()
                if not port or not oid:
                    raise ValueError("port/id obrigatorios")
                ignore_onu(port, oid)
                self._send(json.dumps({"ok": True}).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as e:
                self._send(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/add_devices":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode("utf-8")) if n else []
                if not isinstance(body, list):
                    body = [body]
                save_batch_labels(body)
                self._send(json.dumps({"ok": True, "count": len(body)}).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as e:
                self._send(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/api/sync_cameras":
            try:
                import winrm
                session = winrm.Session(f"http://{SERVER_IP}:5985/wsman", auth=("Administrator", "AJIN#jurere"), transport="ntlm", read_timeout_sec=40, operation_timeout_sec=30)
                session.run_cmd("python C:\\temp\\coleta_cameras.py")
                if puxa_logs:
                    puxa_logs.pull_logs()
                self._send(json.dumps({"ok": True}).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as e:
                self._send(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"), "application/json; charset=utf-8")
        else:
            self.send_response(404)
            self.end_headers()


def server_ping_loop():
    while True:
        try:
            ok = ping_device(SERVER_IP)
            server_ping_state["online"] = ok
            server_ping_state["checked_at"] = datetime.now().strftime("%H:%M:%S")
        except Exception:
            server_ping_state["online"] = False
        time.sleep(3)


def auto_pull_loop():
    while True:
        try:
            if server_ping_state["online"] and puxa_logs:
                puxa_logs.pull_logs()
        except Exception:
            pass
        time.sleep(10)


def main():
    os.makedirs(LOGS_DIR, exist_ok=True)
    threading.Thread(target=server_ping_loop, daemon=True).start()
    threading.Thread(target=bench_ping_loop, daemon=True).start()
    threading.Thread(target=auto_pull_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Dashboard ONUs v2 rodando em {url} e na rede local (Ctrl+C para parar)")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nParado.")


if __name__ == "__main__":
    main()

class AjinDashboardServer:
    """Servidor web embutido do Dashboard da Ajin para o RemoteXPTI."""
    _instance: Optional["AjinDashboardServer"] = None

    def __init__(self, port: int = 0):
        self.desired_port = port
        self.port: int = 0
        self.httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @classmethod
    def get_instance(cls) -> "AjinDashboardServer":
        if cls._instance is None:
            cls._instance = AjinDashboardServer()
        return cls._instance

    def start(self) -> int:
        """Inicia o servidor em segundo plano ou conecta ao existente na porta 3000."""
        # 1. Testa se o servidor já está ativo (ex: rodando standalone na porta 3000)
        try:
            req = urllib.request.Request("http://127.0.0.1:3000/data", method="GET")
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                if resp.status == 200:
                    self.port = 3000
                    return self.port
        except Exception:
            pass

        if self.httpd and self.port > 0:
            return self.port

        global LOGS_DIR, LABELS_FILE, IGNORED_FILE, REGISTERED_FILE, CAMERAS_FILE
        LOGS_DIR = get_logs_dir()
        LABELS_FILE = os.path.join(LOGS_DIR, "onus_labels.json")
        IGNORED_FILE = os.path.join(LOGS_DIR, "onus_ignored.json")
        REGISTERED_FILE = os.path.join(LOGS_DIR, "onus_registered.json")
        CAMERAS_FILE = os.path.join(LOGS_DIR, "onu_cameras.json")
        os.makedirs(LOGS_DIR, exist_ok=True)

        target_ports = [3000, 3001, 3002, 0] if self.desired_port == 0 else [self.desired_port, 0]
        for p in target_ports:
            try:
                self.httpd = ThreadingHTTPServer(("127.0.0.1", p), Handler)
                self.port = self.httpd.server_address[1]
                break
            except OSError:
                continue

        if not self.httpd:
            raise RuntimeError("Não foi possível alocar uma porta para o servidor AjinDashboard.")

        threading.Thread(target=server_ping_loop, daemon=True).start()
        threading.Thread(target=bench_ping_loop, daemon=True).start()
        threading.Thread(target=auto_pull_loop, daemon=True).start()

        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None
            self.port = 0
