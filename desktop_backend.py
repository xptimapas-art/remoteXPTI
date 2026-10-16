"""
Serviço Backend Local FastAPI + WebSockets para o RemoteXPTI Modern Desktop.
Fornece APIs de alta velocidade e streaming em tempo real para a interface React/Tauri.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import math
import os
import sys
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from ajin_manager import AjinManager
from cloud_sync import CloudSyncManager
from config_manager import ConfigManager
from logger import log
from runtime_paths import get_profile_dir, get_data_dir, is_development
from connection_health import ConnectionHealthMonitor, PROBE_TIMEOUT_SECONDS
from connection_diagnostics import ConnectionScanHistory, summarize_scan
from rdp_manager import RDPManager
from storage import StorageManager
from tuya_access_manager import TuyaAccessManager
from camera_snapshots import CameraSnapshots, CameraError
from camera_streams import CameraStream
from hotkey_capture import HotkeyCapture
from update_engine import SilentAutoUpdater
from version import CURRENT_VERSION, APP_NAME, GITHUB_REPO
from atomic_storage import PersistenceError
from wallpaper_previews import WallpaperPreviews

config_mgr = ConfigManager()
tuya_mgr = TuyaAccessManager()
camera_snapshots = CameraSnapshots()
hotkey_capture = HotkeyCapture()

# Inicialização FastAPI
app = FastAPI(title="RemoteXPTI Modern Backend", version=CURRENT_VERSION)


@app.exception_handler(PersistenceError)
async def persistence_error_handler(request: Request, error: PersistenceError):
    log.error(f"[DesktopBackend] Falha de persistência: {type(error).__name__}")
    return JSONResponse(status_code=507, content={"detail": str(error)})

@app.middleware("http")
async def protect_local_api(request, call_next):
    from local_api_security import allow_local_request
    if not allow_local_request(request.headers.get("host", ""), request.headers.get("origin"),
                               request.headers.get("sec-fetch-site")):
        return JSONResponse(status_code=403, content={"detail": "Origem não autorizada para a API local"})
    return await call_next(request)

storage_mgr = StorageManager()
ajin_mgr = AjinManager()

# Gerenciador de conexões WebSocket ativas
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()
main_event_loop = None

def broadcast_ws(message: dict):
    global main_event_loop
    if main_event_loop and main_event_loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(ws_manager.broadcast(message), main_event_loop)
        except Exception:
            pass


wallpaper_previews = WallpaperPreviews(
    get_data_dir() / "thumbnails",
    get_profile_dir() / "wallpaper_cache.json",
    enabled=lambda: is_development() or config_mgr.get_update_channel() == "beta_tester",
    current_server=lambda key: next((s for s in storage_mgr.servers if s["id"] == key), None),
    on_ready=lambda key: broadcast_ws({"type": "thumbnail_updated", "server_id": key}),
)


@app.on_event("shutdown")
async def stop_wallpaper_previews():
    wallpaper_previews.stop()

# Instância Global do Auto-Updater Silencioso
updater_instance: Optional[SilentAutoUpdater] = None

def _on_updater_ready(new_ver: str):
    log.info(f"[DesktopBackend] Nova versão pronta para instalação: v{new_ver}")
    broadcast_ws({
        "type": "update_ready",
        "data": {
            "new_version": new_ver,
            "current_version": CURRENT_VERSION,
        }
    })

def _on_updater_status(msg: str):
    log.info(f"[DesktopBackend] Status do updater: {msg}")
    broadcast_ws({
        "type": "update_status",
        "data": {
            "message": msg,
            "is_checking": updater_instance.is_checking if updater_instance else False,
            "is_downloading": updater_instance.is_downloading if updater_instance else False,
            "update_ready": updater_instance.update_ready if updater_instance else False,
            "new_version": updater_instance.new_version if updater_instance else "",
            "current_version": CURRENT_VERSION,
        }
    })

def _cleanup_before_restart():
    log.info("[DesktopBackend] Executando rotina de limpeza para reinício de update...")
    wallpaper_previews.stop()
    try:
        ajin_mgr.stop()
    except Exception:
        pass
    try:
        storage_mgr.save()
    except Exception:
        pass

updater_instance = SilentAutoUpdater(
    on_ready_callback=_on_updater_ready,
    on_status_callback=_on_updater_status,
    cleanup_callback=_cleanup_before_restart
)

@app.on_event("startup")
async def on_startup():
    global main_event_loop
    main_event_loop = asyncio.get_running_loop()
    _load_downtime_history()
    threading.Thread(target=_background_heartbeat, daemon=True).start()

# Cache de coordenadas de ONUs da Ajin
onu_coordinates: Dict[str, Dict[str, Any]] = {}
onu_coordinates_lock = threading.RLock()

def _load_onu_coordinates():
    global onu_coordinates
    try:
        from config_manager import get_config_dir
        coords_file = get_config_dir() / "onu_coordinates.json"
        if coords_file.exists():
            with open(coords_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    onu_coordinates = data
                    log.info(f"[DesktopBackend] Coordenadas de ONUs carregadas: {len(onu_coordinates)} cadastradas.")
                    return
        # Sementes padrão para pontos conhecidos no norte da ilha (Florianópolis / Ingleses)
        onu_coordinates = {
            "Slot1-PON1_6": {"latitude": -27.4335, "longitude": -48.4025, "name": "Ponto 10", "desc": "R. Tabaronas"},
            "Slot1-PON1_20": {"latitude": -27.4310, "longitude": -48.4010, "name": "Ponto 06", "desc": "R. Manjubas"},
            "Slot1-PON1_3": {"latitude": -27.4350, "longitude": -48.4040, "name": "Ponto 03", "desc": "R. Guarajubas"},
            "Slot2-PON1_20": {"latitude": -27.4380, "longitude": -48.4030, "name": "Ponto 20", "desc": "Angeloni"},
        }
        _save_onu_coordinates()
    except Exception as e:
        log.warning(f"[DesktopBackend] Falha ao carregar onu_coordinates.json: {e}")

def _save_onu_coordinates(data=None):
    try:
        from config_manager import get_config_dir
        coords_file = get_config_dir() / "onu_coordinates.json"
        temporary = coords_file.with_suffix('.json.tmp')
        with temporary.open("w", encoding="utf-8") as f:
            json.dump(onu_coordinates if data is None else data, f, indent=2, ensure_ascii=False)
        temporary.replace(coords_file)
    except Exception as e:
        log.warning(f"[DesktopBackend] Falha ao salvar onu_coordinates.json: {e}")
        raise HTTPException(status_code=500, detail='Não foi possível salvar as coordenadas neste PC.') from e


def _validate_onu_coordinates(latitude, longitude):
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail='Informe latitude e longitude juntas, ou deixe ambas vazias.')
    if latitude is not None and (not math.isfinite(latitude) or not math.isfinite(longitude)
                                or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
        raise HTTPException(status_code=422, detail='Latitude ou longitude fora do intervalo válido.')


def _store_onu_location(req):
    global onu_coordinates
    key = f'{req.port}_{req.onu_id}'
    with onu_coordinates_lock:
        updated = dict(onu_coordinates)
        if req.latitude is None:
            updated.pop(key, None)
        else:
            updated[key] = {'latitude':req.latitude, 'longitude':req.longitude,
                            'name':req.name or '', 'desc':req.desc or '',
                            'port':req.port, 'onu_id':req.onu_id}
        _save_onu_coordinates(updated)
        onu_coordinates = updated
    return key

def _enrich_ajin_telemetry(data: Dict[str, Any]) -> Dict[str, Any]:
    if not data or not isinstance(data, dict):
        return data
    res = dict(data)
    coordinates = onu_coordinates
    rows = res.get("rows", [])
    enriched_rows = []
    for r in rows:
        rc = dict(r)
        k = f"{rc.get('port')}_{rc.get('id')}"
        if k in coordinates and not rc.get('coordinates_shared'):
            c = coordinates[k]
            rc["latitude"] = c.get("latitude")
            rc["longitude"] = c.get("longitude")
        enriched_rows.append(rc)
    res["rows"] = enriched_rows
    return res

# Callback do AjinManager para notificar o WebSocket
def _on_ajin_updated():
    broadcast_ws({"type": "telemetry_update", "data": _enrich_ajin_telemetry(ajin_mgr.get_data())})

ajin_mgr.add_listener(_on_ajin_updated)

# Cache de status e rastreamento de downtime de servidores
server_status_cache: Dict[str, Dict[str, Any]] = {}
server_downtime: Dict[str, float] = {}
health_monitor = ConnectionHealthMonitor()
status_lock = threading.RLock()
status_scan_lock = threading.Lock()
server_probe_locks: Dict[str, Any] = {}
status_scan_history = ConnectionScanHistory(get_profile_dir() / "logs" / "rdp_status_scans.json")

def _load_downtime_history():
    global server_downtime
    try:
        from config_manager import get_config_dir
        hist_file = get_config_dir() / "downtime_history.json"
        if hist_file.exists():
            with open(hist_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    with status_lock:
                        health_monitor.restore(data)
                        server_downtime = health_monitor.downtime()
                    log.info(f"[DesktopBackend] Downtime histórico carregado: {len(server_downtime)} servidores em falha.")
    except Exception as e:
        log.warning(f"[DesktopBackend] Falha ao carregar downtime_history.json: {e}")

def _save_downtime_history():
    try:
        from config_manager import get_config_dir
        hist_file = get_config_dir() / "downtime_history.json"
        with status_lock:
            from update_engine import write_json_atomic
            write_json_atomic(hist_file, server_downtime)
    except Exception as e:
        log.warning(f"[DesktopBackend] Falha ao salvar downtime_history.json: {e}")

def _check_server_status(srv):
    global server_downtime
    server_id = srv['id']
    with status_lock:
        probe_lock = server_probe_locks.setdefault(server_id, threading.Lock())
    # Manual checks and scheduled scans use the same per-server lock and filter.
    with probe_lock:
        target = (srv.get('host', ''), srv.get('port', 3389))
        try:
            reachable, message = RDPManager.check_connection(*target, timeout=PROBE_TIMEOUT_SECONDS)
        except Exception as error:
            log.warning(f"[RDPHealth] Teste inconclusivo: {server_id} ({type(error).__name__}).")
            reachable, message = None, "Falha ao executar o teste neste computador."
        with status_lock:
            current = storage_mgr.get_server(server_id)
            if not current or (current.get('host', ''), current.get('port', 3389)) != target:
                return {}, False
            status, changed = health_monitor.observe(server_id, reachable, message, target=target)
            server_status_cache[server_id] = status
            server_downtime = health_monitor.downtime()
            if changed:
                log.info(f"[RDPHealth] {server_id}: {status['health_state']}; motivo={message}")
            return status, changed


def check_all_servers_status():
    """Confirm connectivity changes without overlapping scans or single-probe incidents."""
    if not status_scan_lock.acquire(blocking=False):
        return
    try:
        started_at, started = time.time(), time.monotonic()
        with status_lock:
            previous = {key: value.copy() for key, value in server_status_cache.items()}
        servers = list(storage_mgr.servers)
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(_check_server_status, servers))
        summary = summarize_scan(servers, results, previous, started_at=started_at,
                                 elapsed=time.monotonic() - started)
        last_summary = status_scan_history.latest()
        try:
            status_scan_history.append(summary)
        except OSError:
            log.warning("[RDPHealth] Não foi possível gravar o diagnóstico deste ciclo.")
        if summary["mass_failure"] or summary["inconclusive"]:
            log.warning(f"[RDPHealth] Ciclo: {summary['total']} testes, "
                        f"{summary['responded']} respostas, {summary['failed']} falhas RDP, "
                        f"{summary['inconclusive']} inconclusivos; "
                        f"falha coletiva={summary['mass_failure']}; redes={summary['affected_networks']}")
        elif last_summary and (last_summary.get("mass_failure") or last_summary.get("inconclusive")):
            log.info(f"[RDPHealth] Fim da falha coletiva/inconclusiva: {summary['responded']} respostas, "
                     f"{summary['failed']} falhas RDP.")
        if any(changed for _, changed in results):
            _save_downtime_history()
            broadcast_ws({"type": "incidents_updated"})
        broadcast_ws({"type": "servers_status_updated"})
    finally:
        status_scan_lock.release()

# Modelos Pydantic
class ConnectRequest(BaseModel):
    server_id: str

class AddServerRequest(BaseModel):
    name: str
    host: str
    port: int = 3389
    username: str = ""
    password: str = ""
    group: str = "BEMTEVI"
    notes: str = ""
    fullscreen: bool = True
    admin_mode: bool = False
    multimon: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=2)

class UpdateServerRequest(BaseModel):
    name: str
    host: str
    port: int = 3389
    username: str = ""
    password: Optional[str] = None
    group: str = "BEMTEVI"
    notes: str = ""
    fullscreen: bool = True
    admin_mode: bool = False
    multimon: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=2)


class GroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class RenameGroupRequest(GroupRequest):
    new_name: str = Field(min_length=1, max_length=60)

class EditLabelRequest(BaseModel):
    port: str
    onu_id: str
    name: str = ""
    desc: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = Field(default=None, max_length=4000)
    map_enabled: Optional[bool] = None

class AjinOnuRequest(BaseModel):
    port: str = Field(min_length=1, max_length=80)
    onu_id: str = Field(min_length=1, max_length=32)

class AjinDeviceRequest(BaseModel):
    port: str = Field(min_length=1, max_length=80)
    id: str = Field(min_length=1, max_length=32)
    serial: str = Field(min_length=1, max_length=100)
    name: str = Field(default='', max_length=120)
    desc: str = Field(default='', max_length=300)

class AjinRegisterRequest(BaseModel):
    devices: List[AjinDeviceRequest] = Field(min_length=1, max_length=200)

class SetOnuLocationRequest(BaseModel):
    port: str
    onu_id: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    name: Optional[str] = None
    desc: Optional[str] = None

class DevLoginRequest(BaseModel):
    password: str

class InstallVersionRequest(BaseModel):
    tag: str
    download_url: str = ""

class SetChannelRequest(BaseModel):
    channel: str

class DoorConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    hotkeys_enabled: Optional[bool] = None
    feedback_sound: Optional[bool] = None
    feedback_notification: Optional[bool] = None
    user_code: Optional[str] = None
    doors: Optional[List[Dict[str, Any]]] = None

class DoorOpenRequest(BaseModel):
    source: Optional[str] = "Painel DEV"

class DoorEditRequest(BaseModel):
    door: Dict[str, Any]
    original: Optional[Dict[str, Any]] = None
    delete: bool = False

class QRLoginRequest(BaseModel):
    user_code: Optional[str] = None

def sync_shared_doors() -> bool:
    if not CloudSyncManager.can_share_doors():
        return False
    try:
        raw = CloudSyncManager.fetch_doors_config()
        if not raw:
            return False
        from shared_doors import merge_config
        with tuya_mgr._lock:
            merged = merge_config(tuya_mgr.config, json.loads(raw))
            if merged != tuya_mgr.config:
                tuya_mgr.save_config(merged, push_to_cloud=False)
        return True
    except Exception as error:
        log.warning(f"[DesktopBackend] Falha ao sincronizar portas: {type(error).__name__}")
        return False


def sync_supabase_servers() -> tuple[bool, int, str]:
    doors_synced = sync_shared_doors()
    if not CloudSyncManager.is_configured():
        return doors_synced, 0, "Portas sincronizadas" if doors_synced else "Sincronização de servidores desabilitada"
    try:
        revision = storage_mgr.revision
        remote = CloudSyncManager.fetch_servers()
        if remote is not None:
            changed, added, updated = storage_mgr.merge_cloud_servers(remote, expected_revision=revision)
            if changed:
                log.info(f"[DesktopBackend] Nuvem sincronizada: {added} novos, {updated} atualizados.")
                broadcast_ws({"type": "servers_status_updated"})
            return True, len(remote), f"{len(remote)} servidores na nuvem"
    except Exception as e:
        log.warning(f"[DesktopBackend] Erro ao sincronizar com Supabase: {e}")
        return False, 0, str(e)
    return False, 0, "Não foi possível confirmar a consulta completa ao Supabase. Os dados locais foram preservados."

# Endpoints REST
@app.get("/api/status")
def get_status():
    return {
        "status": "online",
        "app_name": "RemoteXPTI Modern Desktop",
        "version": CURRENT_VERSION,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/servers")
def get_servers():
    servers = storage_mgr.servers
    now = time.time()
    # Remove senhas planas por segurança da API e anexa status de conexão
    safe_servers = []
    for s in servers:
        sc = s.copy()
        sc.pop("password", None)
        sc.pop("password_plain", None)
        sc["thumbnail_url"] = wallpaper_previews.image_url(s)

        s_id = sc.get("id", "")
        cached = server_status_cache.get(s_id)
        if cached:
            sc["is_online"] = cached.get("is_online", True)
            sc["status_msg"] = cached.get("msg", "Online")
            sc["offline_since"] = cached.get("offline_since")
            sc["duration_seconds"] = int(now - cached["offline_since"]) if cached.get("offline_since") else 0
            sc["health_state"] = cached.get("health_state")
            sc["last_probe_online"] = cached.get("last_probe_online")
            sc["last_valid_probe_at"] = cached.get("last_valid_probe_at")
        else:
            off_since = server_downtime.get(s_id)
            if off_since:
                sc["is_online"] = False
                sc["status_msg"] = "Porta 3389 fechada ou filtrada"
                sc["offline_since"] = off_since
                sc["duration_seconds"] = int(now - off_since)
            else:
                sc["is_online"] = True
                sc["status_msg"] = "Online"
                sc["offline_since"] = None
                sc["duration_seconds"] = 0

        safe_servers.append(sc)
    return {
        "servers": safe_servers,
        "groups": storage_mgr.get_groups(),
        "total": len(safe_servers)
    }

@app.post("/api/servers/connect")
def connect_server(req: ConnectRequest):
    server = storage_mgr.get_server(req.server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")

    def _launch():
        host = server.get("host", "")
        port = int(server.get("port", 3389))
        user = server.get("username", "")
        pwd = server.get("password_plain", "")
        full = bool(server.get("fullscreen", True))
        adm = bool(server.get("admin_mode", False))
        multi = bool(server.get("multimon", False))

        ok, msg = RDPManager.launch_rdp(
            host=host,
            port=port,
            username=user,
            password=pwd,
            fullscreen=full,
            admin_mode=adm,
            multimon=multi
        )
        if ok:
            wallpaper_previews.request(server)
            storage_mgr.record_connection(req.server_id)
            log.info(f"[DesktopBackend] Conexão RDP disparada com sucesso para {server.get('name')}: {msg}")
        else:
            log.error(f"[DesktopBackend] Falha ao disparar RDP para {server.get('name')}: {msg}")

    threading.Thread(target=_launch, daemon=True).start()
    return {"status": "launching", "server_name": server.get("name")}

@app.post("/api/servers/add")
def add_server(req: AddServerRequest):
    data = req.dict()
    if is_development():
        data["scope"] = "local"
    if not data["name"].strip() or not data["host"].strip() or not 1 <= data["port"] <= 65535:
        raise HTTPException(status_code=422, detail="Informe nome, endereço e porta válida (1 a 65535).")
    try:
        new_s = storage_mgr.add_server(data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    broadcast_ws({"type": "servers_status_updated"})

    # Se dev autenticado ou escopo corporativo, publica automaticamente no Supabase
    if CloudSyncManager.can_write_servers() and (config_mgr.is_dev_authenticated() or new_s.get("scope") == "corporate"):
        def _push():
            ok, msg = CloudSyncManager.push_single_server(new_s)
            if ok:
                log.info(f"[DesktopBackend] Servidor '{new_s.get('name')}' publicado no Supabase com sucesso.")
            else:
                log.warning(f"[DesktopBackend] Falha ao publicar servidor no Supabase: {msg}")
        threading.Thread(target=_push, daemon=True).start()

    return {"status": "created", "server": new_s}

@app.get("/api/servers/{server_id}")
def get_server_detail(server_id: str):
    server = storage_mgr.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    return server

@app.put("/api/servers/{server_id}")
def update_server(server_id: str, req: UpdateServerRequest):
    if is_development() and storage_mgr.is_corporate(server_id):
        raise HTTPException(status_code=403, detail="No DEV, o cadastro da empresa é somente leitura. Edite no aplicativo CLIENT.")
    data = req.dict(exclude_unset=True)
    try:
        updated = storage_mgr.update_server(server_id, data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    if not updated:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")

    # Se dev autenticado ou escopo corporativo, atualiza no Supabase
    if CloudSyncManager.can_write_servers() and (config_mgr.is_dev_authenticated() or updated.get("scope") == "corporate"):
        def _push():
            ok, msg = CloudSyncManager.push_single_server(updated)
            if ok:
                log.info(f"[DesktopBackend] Servidor '{updated.get('name')}' atualizado no Supabase com sucesso.")
        threading.Thread(target=_push, daemon=True).start()

    return {"status": "updated", "server": updated}


@app.get("/api/groups")
def get_server_groups():
    return {"groups": storage_mgr.group_details(allow_corporate=not is_development())}


@app.post("/api/groups")
def add_server_group(req: GroupRequest):
    try:
        storage_mgr.add_group(req.name)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    broadcast_ws({"type": "servers_status_updated"})
    return {"status": "created", **get_server_groups()}


@app.put("/api/groups")
def rename_server_group(req: RenameGroupRequest):
    try:
        storage_mgr.rename_group(req.name, req.new_name, allow_corporate=not is_development())
    except KeyError:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.") from None
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    if CloudSyncManager.can_write_servers():
        threading.Thread(target=lambda: CloudSyncManager.push_servers(storage_mgr.get_corporate_servers()), daemon=True).start()
    broadcast_ws({"type": "servers_status_updated"})
    return {"status": "updated", **get_server_groups()}


@app.delete("/api/groups")
def delete_server_group(req: GroupRequest):
    try:
        storage_mgr.delete_group(req.name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.") from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    broadcast_ws({"type": "servers_status_updated"})
    return {"status": "deleted", **get_server_groups()}

@app.post("/api/servers/{server_id}/favorite")
def toggle_favorite(server_id: str):
    favorite = storage_mgr.toggle_favorite(server_id)
    if favorite is None:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    return {"status": "ok", "favorite": favorite}

@app.delete("/api/servers/{server_id}")
def delete_server(server_id: str):
    global server_downtime
    srv = storage_mgr.get_server(server_id)
    is_corp = srv and srv.get("scope") == "corporate"
    if is_development() and is_corp:
        raise HTTPException(status_code=403, detail="O DEV não pode excluir servidores da empresa.")
    ok = storage_mgr.delete_server(server_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    with status_lock:
        was_offline = server_id in server_downtime
        health_monitor.forget(server_id)
        server_status_cache.pop(server_id, None)
        server_downtime = health_monitor.downtime()
        if was_offline:
            _save_downtime_history()
    if was_offline:
        broadcast_ws({"type": "incidents_updated"})

    if (config_mgr.is_dev_authenticated() or is_corp) and CloudSyncManager.can_write_servers():
        def _del():
            CloudSyncManager.delete_remote_server(server_id)
            log.info(f"[DesktopBackend] Servidor '{server_id}' removido do Supabase.")
        threading.Thread(target=_del, daemon=True).start()

    return {"status": "deleted"}

@app.get("/api/dev/status")
def get_dev_status():
    return {
        "is_dev": config_mgr.is_dev_authenticated(),
        "channel": config_mgr.get_update_channel(),
        "supabase_configured": CloudSyncManager.is_configured(),
        "server_read_only": is_development(),
        "supabase_url": config_mgr.get_supabase_config().get("url", "")
    }

@app.post("/api/dev/login")
def dev_login(req: DevLoginRequest):
    success = config_mgr.authenticate_dev(req.password)
    if success:
        tuya_mgr.reload_hotkeys()
    return {
        "success": success,
        "is_dev": config_mgr.is_dev_authenticated(),
        "channel": config_mgr.get_update_channel()
    }

@app.post("/api/dev/logout")
def dev_logout():
    config_mgr.logout_dev()
    tuya_mgr.reload_hotkeys()
    return {
        "success": True,
        "is_dev": False,
        "channel": "public"
    }

# ==============================================================================
# ENDPOINTS DE CONTROLE DE PORTÕES E ACESSOS TUYA (RESTRITO AO MODO DEV)
# ==============================================================================

def require_dev_access():
    if not config_mgr.is_dev_authenticated():
        raise HTTPException(
            status_code=403,
            detail="Acesso negado: Somente usuários em Modo Desenvolvedor podem acessar os portões."
        )

@app.get("/api/doors")
def get_doors_list():
    require_dev_access()
    return {
        "doors": tuya_mgr.get_doors(),
        "cloud_status": tuya_mgr.get_cloud_status()
    }

last_door_trigger = {}

@app.post("/api/doors/{door_id}/open")
def open_door_endpoint(door_id: str, req: Optional[DoorOpenRequest] = None):
    require_dev_access()
    now = time.time()
    if door_id in last_door_trigger and now - last_door_trigger[door_id] < 1.5:
        raise HTTPException(status_code=429, detail="Aguarde um momento antes de disparar novamente.")
    last_door_trigger[door_id] = now

    src = req.source if req and req.source else "Painel DEV"
    success, message = tuya_mgr.open_door(door_id, source=src)
    if not success:
        if "Sem conexão com a internet" in message:
            raise HTTPException(status_code=503, detail=message)
        raise HTTPException(status_code=500, detail=message)
        
    broadcast_ws({"type": "doors_updated"})
    return {
        "success": True,
        "message": message,
        "doors": tuya_mgr.get_doors()
    }

@app.get("/api/doors/config")
def get_doors_config():
    require_dev_access()
    return {
        "config": tuya_mgr.config,
        "cloud_status": tuya_mgr.get_cloud_status()
    }

@app.post("/api/doors/config")
def save_doors_config(req: DoorConfigRequest):
    require_dev_access()
    update_data = {}
    if req.enabled is not None:
        update_data["enabled"] = req.enabled
    if req.hotkeys_enabled is not None:
        update_data["hotkeys_enabled"] = req.hotkeys_enabled
    if req.feedback_sound is not None:
        update_data["feedback_sound"] = req.feedback_sound
    if req.feedback_notification is not None:
        update_data["feedback_notification"] = req.feedback_notification
    if req.user_code is not None:
        update_data["user_code"] = req.user_code
    if req.doors is not None:
        update_data["doors"] = req.doors

    try:
        tuya_mgr.save_config(update_data)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))
    except OSError:
        raise HTTPException(status_code=500, detail="Não foi possível gravar a configuração. Tente novamente.")
    broadcast_ws({"type": "doors_updated"})
    return {
        "success": True,
        "config": tuya_mgr.config,
        "doors": tuya_mgr.get_doors()
    }

def _resolve_door_camera(door_id: str):
    door = tuya_mgr.get_door(door_id)
    if not door:
        raise HTTPException(status_code=404, detail="Acesso não encontrado.")
    camera = door.get("camera") or {}
    if camera.get("source") == "door" and door.get("mode") in ("hikvision", "facial", "isapi"):
        connection = tuya_mgr._get_hikvision_config(door)
    elif camera.get("source") == "external":
        connection = {"host": camera.get("host"), "port": camera.get("port") or (443 if camera.get("protocol") == "https" else 80),
                      "protocol": camera.get("protocol") or "http", "username": camera.get("username"), "password": camera.get("password")}
    else:
        raise HTTPException(status_code=404, detail="Nenhuma câmera vinculada a este acesso.")
    return connection, camera

@app.get("/api/doors/{door_id}/camera")
def get_door_camera(door_id: str):
    require_dev_access()
    connection, camera = _resolve_door_camera(door_id)
    try:
        frame = camera_snapshots.get(connection, camera.get("channel", 1))
    except CameraError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))
    return Response(content=frame, media_type="image/jpeg", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

@app.get("/api/doors/{door_id}/camera/stream")
def get_door_camera_stream(door_id: str, request: Request):
    require_dev_access()
    connection, camera = _resolve_door_camera(door_id)
    try:
        stream = CameraStream(connection, camera.get("channel", 1), camera.get("rtsp_port", 554)).start()
    except CameraError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))

    async def video_chunks():
        try:
            while not await request.is_disconnected():
                if not config_mgr.is_dev_authenticated():
                    break
                chunk = await asyncio.to_thread(stream.read)
                if chunk == b'':
                    break
                if chunk:
                    yield chunk
        finally:
            stream.stop()
    return StreamingResponse(video_chunks(), media_type=stream.mime,
                             headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

@app.post("/api/doors/hotkey-capture")
def start_hotkey_capture():
    require_dev_access()
    try:
        return hotkey_capture.start()
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error))

@app.get("/api/doors/hotkey-capture/{capture_id}")
def get_hotkey_capture(capture_id: str):
    require_dev_access()
    return hotkey_capture.status(capture_id)

@app.delete("/api/doors/hotkey-capture/{capture_id}")
def cancel_hotkey_capture(capture_id: str):
    require_dev_access()
    hotkey_capture.cancel(capture_id)
    return {"success": True}

@app.put("/api/doors/{door_id}/config")
def save_single_door_config(door_id: str, req: DoorEditRequest):
    require_dev_access()
    try:
        tuya_mgr.save_door_config(door_id, req.door, req.original, delete=req.delete)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except OSError:
        raise HTTPException(status_code=500, detail="Não foi possível gravar a configuração. Tente novamente.")
    broadcast_ws({"type": "doors_updated"})
    return {"success": True, "doors": tuya_mgr.get_doors()}

@app.post("/api/doors/sync")
def sync_doors_cloud():
    require_dev_access()
    tuya_mgr._init_cloud_manager(force_sync=True)
    sync_shared_doors()
    broadcast_ws({"type": "doors_updated"})
    return {
        "success": True,
        "cloud_status": tuya_mgr.get_cloud_status(),
        "doors": tuya_mgr.get_doors()
    }


@app.post("/api/doors/shared-sync")
def unlock_shared_doors(req: DevLoginRequest):
    require_dev_access()
    if not config_mgr.authenticate_dev(req.password):
        raise HTTPException(status_code=403, detail="Senha DEV incorreta.")
    if not CloudSyncManager.can_share_doors():
        raise HTTPException(status_code=503, detail="Não foi possível habilitar a sincronização neste PC.")
    sync_shared_doors()
    try:
        tuya_mgr.save_config(push_to_cloud=True)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))
    broadcast_ws({"type":"doors_updated"})
    return {"success":True,"cloud_status":tuya_mgr.get_cloud_status(),"config":tuya_mgr.config}

@app.get("/api/doors/logs")
def get_doors_access_logs():
    require_dev_access()
    return {
        "logs": tuya_mgr.get_access_logs()
    }

@app.post("/api/doors/qr-login")
def generate_doors_qr_login(req: Optional[QRLoginRequest] = None):
    require_dev_access()
    user_code = req.user_code if req and req.user_code else None
    result = tuya_mgr.generate_qr_login(user_code)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Falha ao gerar QR Code"))
    return result

@app.post("/api/sync/supabase")
def manual_sync_supabase():
    ok, count, msg = sync_supabase_servers()
    storage_mgr.load()
    return {
        "success": ok,
        "count": count,
        "message": msg
    }

@app.post("/api/refresh_all")
def refresh_all():
    sync_supabase_servers()
    storage_mgr.load()
    ajin_mgr.fetch_telemetry_async(force=True)
    threading.Thread(target=check_all_servers_status, daemon=True).start()
    return {"status": "ok", "message": "Atualização e verificação de servidores solicitadas"}

# ==============================================================================
# ENDPOINTS DO SISTEMA DE AUTO-UPDATE
# ==============================================================================
@app.get("/api/update/status")
def get_update_status():
    if not updater_instance:
        raise HTTPException(status_code=503, detail="Updater não inicializado")
    return {**updater_instance.snapshot(), "channel": config_mgr.get_update_channel()}

@app.post("/api/update/healthy")
def confirm_update_healthy():
    from update_bootstrap import confirm_update_startup
    try:
        return {"confirmed": confirm_update_startup()}
    except (ValueError, OSError, KeyError, IndexError) as exc:
        log.error("[Updater] Confirmação de inicialização falhou: %s", exc)
        raise HTTPException(status_code=409, detail="A versão instalada não corresponde ao update")

@app.post("/api/update/check")
def check_updates_manual():
    if not updater_instance:
        raise HTTPException(status_code=503, detail="Updater não inicializado")
    started = updater_instance.start_background_check(is_manual=True)
    return {"status": "started" if started else updater_instance.state,
            "message": updater_instance.status_message}

@app.post("/api/update/restart")
def apply_update_restart():
    if not updater_instance:
        raise HTTPException(status_code=503, detail="Updater não inicializado")
    try:
        prepared = updater_instance.prepare_install()
    except (ValueError, OSError) as exc:
        updater_instance.notify_status(str(exc))
        raise HTTPException(status_code=409, detail=str(exc))
    def restart():
        time.sleep(0.3)  # Permite que a resposta HTTP seja entregue.
        updater_instance.launch_install(prepared, cleanup_func=_cleanup_before_restart)
    threading.Thread(target=restart, daemon=True).start()
    return {"status": "restarting", "message": "Instalando atualização e reiniciando..."}

@app.get("/api/logs/path")
def get_logs_path():
    log_dir = get_profile_dir() / "logs"
    log_file = log_dir / "remotexpti.log"
    return {"dir": str(log_dir), "file": str(log_file), "exists": log_file.exists()}

@app.post("/api/logs/open")
def open_logs_folder():
    log_dir = get_profile_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    if hasattr(os, "startfile"):
        try:
            os.startfile(str(log_dir))
        except Exception as e:
            log.warning(f"Erro ao abrir pasta de logs: {e}")
    return {"status": "ok", "path": str(log_dir)}

@app.get("/api/logs/tail")
def get_logs_tail(lines: int = 50):
    log_dir = get_profile_dir() / "logs"
    log_file = log_dir / "remotexpti.log"
    if not log_file.exists():
        return {"lines": []}
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
            return {"lines": all_lines[-lines:]}
    except Exception as e:
        return {"error": str(e), "lines": []}

@app.get("/api/update/releases")
def get_all_releases():
    try:
        releases = SilentAutoUpdater.fetch_all_releases()
        return {"releases": releases, "current_version": CURRENT_VERSION}
    except Exception as e:
        log.error(f"[DesktopBackend] Erro ao buscar releases: {e}")
        return {"releases": [], "error": str(e), "current_version": CURRENT_VERSION}

@app.post("/api/update/install_version")
def install_specific_version(req: InstallVersionRequest):
    global updater_instance
    if not updater_instance:
        raise HTTPException(status_code=500, detail="Updater não inicializado")

    if not config_mgr.is_dev_authenticated():
        raise HTTPException(status_code=403, detail="Instalação de versão específica exige login DEV")
    try:
        updater_instance.download_and_install_specific(req.tag, req.download_url)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"status": "downloading", "tag": req.tag}

@app.post("/api/update/channel")
def set_update_channel(req: SetChannelRequest):
    if req.channel not in ("public", "beta_tester"):
        raise HTTPException(status_code=400, detail="Canal inválido")
    if not config_mgr.is_dev_authenticated() and req.channel != "public":
        raise HTTPException(status_code=403, detail="Canal beta exige login DEV")
    config_mgr.set_update_channel(req.channel)
    broadcast_ws({
        "type": "update_channel_changed",
        "channel": config_mgr.get_update_channel()
    })
    return {"status": "ok", "channel": config_mgr.get_update_channel()}

@app.post("/api/servers/check_status")
def trigger_check_all():
    threading.Thread(target=check_all_servers_status, daemon=True).start()
    return {"status": "started", "message": "Verificação de conectividade iniciada"}


@app.get("/api/monitoring/status")
def get_monitoring_status():
    return {"latest_scan": status_scan_history.latest()}

@app.post("/api/servers/{server_id}/check")
def check_single_server(server_id: str):
    srv = storage_mgr.get_server(server_id)
    if not srv:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    stat, changed = _check_server_status(srv)
    if changed:
        _save_downtime_history()
        broadcast_ws({"type": "incidents_updated"})
    broadcast_ws({"type": "servers_status_updated"})
    return stat

@app.get("/api/incidents")
def get_incidents():
    now = time.time()
    incidents = []
    server_map = {s["id"]: s for s in storage_mgr.servers}
    for s_id, offline_since in list(server_downtime.items()):
        srv = server_map.get(s_id)
        if not srv:
            continue
        duration = max(0, int(now - float(offline_since)))
        try:
            dt = datetime.fromtimestamp(float(offline_since))
            formatted_date = dt.strftime("%d/%m às %H:%M")
        except Exception:
            formatted_date = "Recente"

        incidents.append({
            "id": s_id,
            "name": srv.get("name", "Servidor"),
            "host": srv.get("host", ""),
            "port": srv.get("port", 3389),
            "group": srv.get("group", "BEMTEVI"),
            "username": srv.get("username", "Padrão"),
            "offline_since": offline_since,
            "offline_since_formatted": formatted_date,
            "duration_seconds": duration,
            "latitude": srv.get("latitude"),
            "longitude": srv.get("longitude")
        })
    incidents.sort(key=lambda x: x["duration_seconds"], reverse=True)
    return incidents

@app.get("/api/ajin/telemetry")
def get_ajin_telemetry():
    return _enrich_ajin_telemetry(ajin_mgr.get_data())

@app.post("/api/ajin/refresh")
def force_refresh_ajin():
    completed, outcome = threading.Event(), []
    ajin_mgr.fetch_telemetry_async(force=True, callback=lambda ok: (outcome.append(ok), completed.set()))
    if not completed.wait(10):
        raise HTTPException(status_code=504, detail='O coletor demorou para responder. Tente novamente.')
    if not outcome[0]:
        raise HTTPException(status_code=502, detail='Não foi possível consultar o coletor AJIN. A última coleta foi preservada.')
    return {'status':'updated', 'telemetry':_enrich_ajin_telemetry(ajin_mgr.get_data())}

@app.post("/api/ajin/label")
def save_ajin_label(req: EditLabelRequest):
    _validate_onu_coordinates(req.latitude, req.longitude)
    changes = {} if req.notes is None else {'notes':req.notes}
    if req.map_enabled is not None:
        changes['map_enabled'] = req.map_enabled
    if {'latitude', 'longitude'} & req.model_fields_set:
        changes.update(latitude=req.latitude, longitude=req.longitude)
    if not ajin_mgr.update_label(req.port, req.onu_id, req.name, req.desc, **changes):
        raise HTTPException(status_code=502, detail='O coletor não confirmou a alteração da identificação. Tente novamente.')
    if {'latitude', 'longitude'} & req.model_fields_set:
        _store_onu_location(req)
    broadcast_ws({"type": "telemetry_update", "data": _enrich_ajin_telemetry(ajin_mgr.get_data())})
    return {"status": "saved", 'telemetry':_enrich_ajin_telemetry(ajin_mgr.get_data())}

@app.get('/api/ajin/scan')
def scan_ajin_onus():
    try:
        return ajin_mgr.scan_onus()
    except Exception:
        raise HTTPException(status_code=502, detail='Não foi possível consultar o Scanner no coletor AJIN. Tente novamente.')

@app.post('/api/ajin/onu/delete')
def delete_ajin_onu(req: AjinOnuRequest):
    if not ajin_mgr.delete_onu(req.port, req.onu_id):
        raise HTTPException(status_code=502, detail='O coletor não confirmou a exclusão. O ponto foi preservado no aplicativo.')
    return {'status':'deleted', 'telemetry':_enrich_ajin_telemetry(ajin_mgr.get_data())}

@app.post('/api/ajin/register')
def register_ajin_onus(req: AjinRegisterRequest):
    devices = [device.model_dump() for device in req.devices]
    if len({(device['port'], device['id']) for device in devices}) != len(devices):
        raise HTTPException(status_code=422, detail='A seleção contém ONUs repetidas.')
    try:
        confirmed = ajin_mgr.register_onus(devices)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=502, detail='Não foi possível conferir a descoberta no coletor AJIN.')
    if not confirmed:
        raise HTTPException(status_code=502, detail='O coletor não confirmou a homologação. Re-escaneie antes de tentar novamente.')
    return {'status':'registered', 'count':len(devices)}

@app.post("/api/ajin/onu/location")
def set_onu_location(req: SetOnuLocationRequest):
    _validate_onu_coordinates(req.latitude, req.longitude)
    k = _store_onu_location(req)
    broadcast_ws({"type": "telemetry_update", "data": _enrich_ajin_telemetry(ajin_mgr.get_data())})
    return {"status": "ok", "saved": k}

@app.get("/api/ajin/onu/locations")
def get_onu_locations():
    return onu_coordinates

# Endpoint WebSocket para telemetria contínua
@app.websocket("/ws/ajin")
async def websocket_ajin_endpoint(websocket: WebSocket):
    from local_api_security import allow_local_request
    if not allow_local_request(websocket.headers.get("host", ""), websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return
    await ws_manager.connect(websocket)
    try:
        # Envia estado inicial imediatamente ao conectar com coordenadas
        await websocket.send_json({
            "type": "initial_state",
            "data": _enrich_ajin_telemetry(ajin_mgr.get_data()),
            "time": datetime.now().strftime("%H:%M:%S")
        })
        # Envia status inicial do auto-updater
        if updater_instance:
            await websocket.send_json({
                "type": "update_status",
                "data": {
                    "message": getattr(updater_instance, "status_message", "Pronto"),
                    "is_checking": updater_instance.is_checking,
                    "is_downloading": updater_instance.is_downloading,
                    "update_ready": updater_instance.update_ready,
                    "new_version": updater_instance.new_version,
                    "current_version": CURRENT_VERSION,
                }
            })
        while True:
            # Mantém conexão viva e escuta mensagens do cliente se houver
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)

# Monta diretório de miniaturas dos servidores
thumbnails_path = get_data_dir() / "thumbnails"
thumbnails_path.mkdir(parents=True, exist_ok=True)
app.mount("/thumbnails", StaticFiles(directory=str(thumbnails_path)), name="thumbnails")

# Monta arquivos estáticos do frontend React compilado
dist_path = Path(__file__).parent / "desktop_ui" / "dist"
if dist_path.exists():
    app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="static")

def _background_init_task():
    try:
        log.info("[DesktopBackend] Iniciando background init (ONUs, Downtime, Tuya)...")
        _load_onu_coordinates()
        
        # Se __name__ != "__main__", o backend foi importado (ex: pelo launcher), logo está embutido
        is_embedded = (__name__ != "__main__")
        tuya_mgr.background_init(is_embedded=is_embedded)
        log.info("[DesktopBackend] Background init concluído com sucesso.")
    except Exception as e:
        log.error(f"[DesktopBackend] Erro no background init: {e}")

# Loop de contagem regressiva e broadcast periódico
def _background_heartbeat():
    # Sincronização e inicialização inicial na thread de background
    threading.Thread(target=_background_init_task, daemon=True).start()
    threading.Thread(target=sync_supabase_servers, daemon=True).start()

    refresh_countdown = 10
    supabase_sync_counter = 0
    status_check_counter = 0
    auto_update_counter = 0

    # Primeira checagem imediata de conectividade de todos os servidores
    threading.Thread(target=check_all_servers_status, daemon=True).start()

    while True:
        time.sleep(1)
        refresh_countdown -= 1
        supabase_sync_counter += 1
        status_check_counter += 1
        auto_update_counter += 1
        now_str = datetime.now().strftime("%H:%M:%S")

        if refresh_countdown <= 0:
            refresh_countdown = 10
            ajin_mgr.fetch_telemetry_async(force=True)

        # Sincroniza com Supabase a cada 60 segundos automaticamente
        if supabase_sync_counter >= 60:
            supabase_sync_counter = 0
            threading.Thread(target=sync_supabase_servers, daemon=True).start()

        # Verifica conectividade de todos os servidores a cada 30 segundos
        if status_check_counter >= 30:
            status_check_counter = 0
            threading.Thread(target=check_all_servers_status, daemon=True).start()

        # Checagem inicial de atualização aos 4s e a cada 45 minutos (2700s)
        if auto_update_counter == 4:
            if updater_instance:
                threading.Thread(target=updater_instance.start_background_check, args=(False,), daemon=True).start()
        elif auto_update_counter >= 2700:
            auto_update_counter = 5
            if updater_instance:
                threading.Thread(target=updater_instance.start_background_check, args=(False,), daemon=True).start()

        broadcast_ws({
            "type": "tick",
            "time": now_str,
            "countdown": refresh_countdown
        })

def start_backend_service(port: int = 8765):
    """Inicia o servidor Uvicorn em uma thread separada."""
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    try:
        server.run()
    except SystemExit as e:
        if e.code == 3:
            import ctypes
            import os
            ctypes.windll.user32.MessageBoxW(0, f"Erro ao iniciar o servidor local na porta {port}.\nTalvez a porta já esteja em uso por outro aplicativo.", "RemoteXPTI - Erro de Porta", 0x10)
            os._exit(1)
        raise
    except OSError as e:
        import ctypes
        import os
        ctypes.windll.user32.MessageBoxW(0, f"Erro ao iniciar o servidor local na porta {port}.\nTalvez a porta já esteja em uso por outro aplicativo.\n\nDetalhes: {e}", "RemoteXPTI - Erro de Porta", 0x10)
        os._exit(1)
    except Exception as e:
        import ctypes
        import os
        ctypes.windll.user32.MessageBoxW(0, f"Erro inesperado ao iniciar o servidor na porta {port}.\n\nDetalhes: {e}", "RemoteXPTI - Erro do Backend", 0x10)
        os._exit(1)

if __name__ == "__main__":
    start_backend_service()
