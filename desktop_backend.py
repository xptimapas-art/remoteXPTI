"""
Serviço Backend Local FastAPI + WebSockets para o RemoteXPTI Modern Desktop.
Fornece APIs de alta velocidade e streaming em tempo real para a interface React/Tauri.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from ajin_manager import AjinManager
from cloud_sync import CloudSyncManager
from config_manager import ConfigManager
from logger import log
from rdp_manager import RDPManager
from storage import StorageManager
from tuya_access_manager import TuyaAccessManager
from updater import SilentAutoUpdater
from version import CURRENT_VERSION, APP_NAME, GITHUB_REPO

config_mgr = ConfigManager()
tuya_mgr = TuyaAccessManager()

# Inicialização FastAPI
app = FastAPI(title="RemoteXPTI Modern Backend", version=CURRENT_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    threading.Thread(target=check_all_servers_status, daemon=True).start()

# Cache de coordenadas de ONUs da Ajin
onu_coordinates: Dict[str, Dict[str, Any]] = {}

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

def _save_onu_coordinates():
    try:
        from config_manager import get_config_dir
        coords_file = get_config_dir() / "onu_coordinates.json"
        with open(coords_file, "w", encoding="utf-8") as f:
            json.dump(onu_coordinates, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning(f"[DesktopBackend] Falha ao salvar onu_coordinates.json: {e}")

_load_onu_coordinates()

def _enrich_ajin_telemetry(data: Dict[str, Any]) -> Dict[str, Any]:
    if not data or not isinstance(data, dict):
        return data
    res = dict(data)
    rows = res.get("rows", [])
    enriched_rows = []
    for r in rows:
        rc = dict(r)
        k = f"{rc.get('port')}_{rc.get('id')}"
        if k in onu_coordinates:
            c = onu_coordinates[k]
            rc["latitude"] = c.get("latitude")
            rc["longitude"] = c.get("longitude")
        else:
            rc["latitude"] = None
            rc["longitude"] = None
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

def _load_downtime_history():
    global server_downtime
    try:
        from config_manager import get_config_dir
        hist_file = get_config_dir() / "downtime_history.json"
        if hist_file.exists():
            with open(hist_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    server_downtime = {str(k): float(v) for k, v in data.items()}
                    log.info(f"[DesktopBackend] Downtime histórico carregado: {len(server_downtime)} servidores em falha.")
    except Exception as e:
        log.warning(f"[DesktopBackend] Falha ao carregar downtime_history.json: {e}")

def _save_downtime_history():
    try:
        from config_manager import get_config_dir
        hist_file = get_config_dir() / "downtime_history.json"
        with open(hist_file, "w", encoding="utf-8") as f:
            json.dump(server_downtime, f, indent=2)
    except Exception as e:
        log.warning(f"[DesktopBackend] Falha ao salvar downtime_history.json: {e}")

_load_downtime_history()

def check_all_servers_status():
    """Verifica a conectividade RDP de todos os servidores em paralelo com ThreadPoolExecutor."""
    servers = list(storage_mgr.servers)
    now = time.time()
    changed = False

    def _check_one(srv):
        nonlocal changed
        s_id = srv["id"]
        host = srv.get("host", "")
        port = int(srv.get("port", 3389))
        is_online, msg = RDPManager.check_connection(host, port, timeout=1.3)

        if not is_online:
            if s_id not in server_downtime:
                server_downtime[s_id] = now
                changed = True
        else:
            if s_id in server_downtime:
                server_downtime.pop(s_id, None)
                changed = True

        off_since = server_downtime.get(s_id)
        duration = int(now - off_since) if off_since else 0
        server_status_cache[s_id] = {
            "is_online": is_online,
            "msg": msg,
            "offline_since": off_since,
            "duration_seconds": duration
        }

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(_check_one, servers))

    if changed:
        _save_downtime_history()

    broadcast_ws({"type": "servers_status_updated"})

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

class EditLabelRequest(BaseModel):
    port: str
    onu_id: str
    name: str = ""
    desc: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None

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
    download_url: str

class SetChannelRequest(BaseModel):
    channel: str

class DoorConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    feedback_sound: Optional[bool] = None
    feedback_notification: Optional[bool] = None
    user_code: Optional[str] = None
    doors: Optional[List[Dict[str, Any]]] = None

class DoorOpenRequest(BaseModel):
    source: Optional[str] = "Painel DEV"

class QRLoginRequest(BaseModel):
    user_code: Optional[str] = None

def sync_supabase_servers() -> tuple[bool, int, str]:
    if not CloudSyncManager.is_configured():
        return False, 0, "Supabase não configurado ou desabilitado"
    try:
        remote = CloudSyncManager.fetch_servers()
        if remote is not None:
            changed, added, updated = storage_mgr.merge_cloud_servers(remote)
            if changed:
                storage_mgr.save()
                log.info(f"[DesktopBackend] Nuvem sincronizada: {added} novos, {updated} atualizados.")
            return True, len(remote), f"{len(remote)} servidores na nuvem"
    except Exception as e:
        log.warning(f"[DesktopBackend] Erro ao sincronizar com Supabase: {e}")
        return False, 0, str(e)
    return False, 0, "Nenhum dado retornado do Supabase"

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

        s_id = sc.get("id", "")
        cached = server_status_cache.get(s_id)
        if cached:
            sc["is_online"] = cached.get("is_online", True)
            sc["status_msg"] = cached.get("msg", "Online")
            sc["offline_since"] = cached.get("offline_since")
            sc["duration_seconds"] = int(now - cached["offline_since"]) if cached.get("offline_since") else 0
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
            storage_mgr.record_connection(req.server_id)
            log.info(f"[DesktopBackend] Conexão RDP disparada com sucesso para {server.get('name')}: {msg}")
        else:
            log.error(f"[DesktopBackend] Falha ao disparar RDP para {server.get('name')}: {msg}")

    threading.Thread(target=_launch, daemon=True).start()
    return {"status": "launching", "server_name": server.get("name")}

@app.post("/api/servers/add")
def add_server(req: AddServerRequest):
    data = req.dict()
    new_s = storage_mgr.add_server(data)
    storage_mgr.save()

    # Se dev autenticado ou escopo corporativo, publica automaticamente no Supabase
    if config_mgr.is_dev_authenticated() or new_s.get("scope") == "corporate":
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
    data = req.dict(exclude_unset=True)
    updated = storage_mgr.update_server(server_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")

    # Se dev autenticado ou escopo corporativo, atualiza no Supabase
    if config_mgr.is_dev_authenticated() or updated.get("scope") == "corporate":
        def _push():
            ok, msg = CloudSyncManager.push_single_server(updated)
            if ok:
                log.info(f"[DesktopBackend] Servidor '{updated.get('name')}' atualizado no Supabase com sucesso.")
        threading.Thread(target=_push, daemon=True).start()

    return {"status": "updated", "server": updated}

@app.post("/api/servers/{server_id}/favorite")
def toggle_favorite(server_id: str):
    srv = storage_mgr.get_server(server_id)
    if not srv:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    srv["favorite"] = not bool(srv.get("favorite", False))
    storage_mgr.save()
    return {"status": "ok", "favorite": srv["favorite"]}

@app.delete("/api/servers/{server_id}")
def delete_server(server_id: str):
    srv = storage_mgr.get_server(server_id)
    is_corp = srv and srv.get("scope") == "corporate"
    ok = storage_mgr.delete_server(server_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")

    if (config_mgr.is_dev_authenticated() or is_corp) and CloudSyncManager.is_configured():
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

@app.post("/api/doors/{door_id}/open")
def open_door_endpoint(door_id: str, req: Optional[DoorOpenRequest] = None):
    require_dev_access()
    src = req.source if req and req.source else "Painel DEV"
    success, message = tuya_mgr.open_door(door_id, source=src)
    if not success:
        raise HTTPException(status_code=500, detail=message)
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
    if req.feedback_sound is not None:
        update_data["feedback_sound"] = req.feedback_sound
    if req.feedback_notification is not None:
        update_data["feedback_notification"] = req.feedback_notification
    if req.user_code is not None:
        update_data["user_code"] = req.user_code
    if req.doors is not None:
        update_data["doors"] = req.doors

    tuya_mgr.save_config(update_data)
    return {
        "success": True,
        "config": tuya_mgr.config,
        "doors": tuya_mgr.get_doors()
    }

@app.post("/api/doors/sync")
def sync_doors_cloud():
    require_dev_access()
    tuya_mgr._init_cloud_manager()
    return {
        "success": True,
        "cloud_status": tuya_mgr.get_cloud_status(),
        "doors": tuya_mgr.get_doors()
    }

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
    global updater_instance
    if not updater_instance:
        return {
            "current_version": CURRENT_VERSION,
            "new_version": "",
            "is_checking": False,
            "is_downloading": False,
            "update_ready": False,
            "channel": config_mgr.get_update_channel(),
            "status_message": "Pronto"
        }
    return {
        "current_version": CURRENT_VERSION,
        "new_version": updater_instance.new_version,
        "is_checking": updater_instance.is_checking,
        "is_downloading": updater_instance.is_downloading,
        "update_ready": updater_instance.update_ready,
        "channel": config_mgr.get_update_channel(),
        "status_message": getattr(updater_instance, "status_message", "Pronto")
    }

@app.post("/api/update/check")
def check_updates_manual():
    global updater_instance
    if not updater_instance:
        raise HTTPException(status_code=500, detail="Updater não inicializado")
    threading.Thread(target=updater_instance.start_background_check, args=(True,), daemon=True).start()
    return {"status": "started", "message": "Verificação de atualizações iniciada"}

@app.post("/api/update/restart")
def apply_update_restart():
    global updater_instance
    if not updater_instance:
        raise HTTPException(status_code=500, detail="Updater não inicializado")
    if not updater_instance.update_ready or not updater_instance.downloaded_file or not updater_instance.downloaded_file.exists():
        log.warning("[DesktopBackend] Tentativa de reiniciar mas o arquivo baixado não está em disco. Disparando novo download...")
        updater_instance.update_ready = False
        threading.Thread(target=updater_instance.start_background_check, args=(True,), daemon=True).start()
        return {"status": "downloading", "message": "O arquivo de atualização não foi encontrado no disco. Baixando novamente..."}

    def _do_restart():
        time.sleep(0.1)
        updater_instance.apply_update_and_restart(cleanup_func=_cleanup_before_restart)

    threading.Thread(target=_do_restart, daemon=True).start()
    return {"status": "restarting", "message": "Reiniciando aplicação para atualizar..."}

@app.get("/api/logs/path")
def get_logs_path():
    log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "RemoteXPTI" / "logs"
    log_file = log_dir / "remotexpti.log"
    return {"dir": str(log_dir), "file": str(log_file), "exists": log_file.exists()}

@app.post("/api/logs/open")
def open_logs_folder():
    log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "RemoteXPTI" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    if hasattr(os, "startfile"):
        try:
            os.startfile(str(log_dir))
        except Exception as e:
            log.warning(f"Erro ao abrir pasta de logs: {e}")
    return {"status": "ok", "path": str(log_dir)}

@app.get("/api/logs/tail")
def get_logs_tail(lines: int = 50):
    log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "RemoteXPTI" / "logs"
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

    def on_st(msg):
        _on_updater_status(msg)

    threading.Thread(
        target=updater_instance.download_and_install_specific,
        args=(req.tag, req.download_url, on_st),
        daemon=True
    ).start()
    return {"status": "downloading", "tag": req.tag}

@app.post("/api/update/channel")
def set_update_channel(req: SetChannelRequest):
    if req.channel not in ("public", "beta_tester"):
        raise HTTPException(status_code=400, detail="Canal inválido")
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

@app.post("/api/servers/{server_id}/check")
def check_single_server(server_id: str):
    srv = storage_mgr.get_server(server_id)
    if not srv:
        raise HTTPException(status_code=404, detail="Servidor não encontrado")
    host = srv.get("host", "")
    port = int(srv.get("port", 3389))
    now = time.time()
    is_online, msg = RDPManager.check_connection(host, port, timeout=1.5)

    if not is_online:
        if server_id not in server_downtime:
            server_downtime[server_id] = now
            _save_downtime_history()
    else:
        if server_id in server_downtime:
            server_downtime.pop(server_id, None)
            _save_downtime_history()

    off_since = server_downtime.get(server_id)
    duration = int(now - off_since) if off_since else 0
    stat = {
        "is_online": is_online,
        "msg": msg,
        "offline_since": off_since,
        "duration_seconds": duration
    }
    server_status_cache[server_id] = stat
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
    ajin_mgr.fetch_telemetry_async(force=True)
    return {"status": "refreshing"}

@app.post("/api/ajin/label")
def save_ajin_label(req: EditLabelRequest):
    ajin_mgr.update_label(req.port, req.onu_id, req.name, req.desc)
    k = f"{req.port}_{req.onu_id}"
    if req.latitude is not None and req.longitude is not None:
        onu_coordinates[k] = {
            "latitude": req.latitude,
            "longitude": req.longitude,
            "name": req.name or "",
            "desc": req.desc or "",
            "port": req.port,
            "onu_id": req.onu_id,
        }
        _save_onu_coordinates()
    elif k in onu_coordinates:
        onu_coordinates[k]["name"] = req.name or ""
        onu_coordinates[k]["desc"] = req.desc or ""
        _save_onu_coordinates()
    broadcast_ws({"type": "telemetry_update", "data": _enrich_ajin_telemetry(ajin_mgr.get_data())})
    return {"status": "saved"}

@app.post("/api/ajin/onu/location")
def set_onu_location(req: SetOnuLocationRequest):
    k = f"{req.port}_{req.onu_id}"
    if req.latitude is None and req.longitude is None:
        onu_coordinates.pop(k, None)
    else:
        onu_coordinates[k] = {
            "latitude": req.latitude,
            "longitude": req.longitude,
            "name": req.name or "",
            "desc": req.desc or "",
            "port": req.port,
            "onu_id": req.onu_id,
        }
    _save_onu_coordinates()
    broadcast_ws({"type": "telemetry_update", "data": _enrich_ajin_telemetry(ajin_mgr.get_data())})
    return {"status": "ok", "saved": k}

@app.get("/api/ajin/onu/locations")
def get_onu_locations():
    return onu_coordinates

# Endpoint WebSocket para telemetria contínua
@app.websocket("/ws/ajin")
async def websocket_ajin_endpoint(websocket: WebSocket):
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
thumbnails_path = Path(__file__).parent / "thumbnails"
if thumbnails_path.exists():
    app.mount("/thumbnails", StaticFiles(directory=str(thumbnails_path)), name="thumbnails")

# Monta arquivos estáticos do frontend React compilado
dist_path = Path(__file__).parent / "desktop_ui" / "dist"
if dist_path.exists():
    app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="static")

# Loop de contagem regressiva e broadcast periódico
def _background_heartbeat():
    # Sincronização inicial com Supabase na inicialização
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
    threading.Thread(target=_background_heartbeat, daemon=True).start()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    server.run()

if __name__ == "__main__":
    start_backend_service()
