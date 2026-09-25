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
from version import CURRENT_VERSION

config_mgr = ConfigManager()

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

@app.on_event("startup")
async def on_startup():
    global main_event_loop
    main_event_loop = asyncio.get_running_loop()
    threading.Thread(target=check_all_servers_status, daemon=True).start()

# Callback do AjinManager para notificar o WebSocket
def _on_ajin_updated():
    broadcast_ws({"type": "telemetry_update", "data": ajin_mgr.get_data()})

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

class DevLoginRequest(BaseModel):
    password: str

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
    return {
        "success": success,
        "is_dev": config_mgr.is_dev_authenticated(),
        "channel": config_mgr.get_update_channel()
    }

@app.post("/api/dev/logout")
def dev_logout():
    config_mgr.logout_dev()
    return {
        "success": True,
        "is_dev": False,
        "channel": "public"
    }

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
        incidents.append({
            "id": s_id,
            "name": srv.get("name", "Servidor"),
            "host": srv.get("host", ""),
            "port": srv.get("port", 3389),
            "offline_since": offline_since,
            "duration_seconds": duration,
            "latitude": srv.get("latitude"),
            "longitude": srv.get("longitude")
        })
    incidents.sort(key=lambda x: x["duration_seconds"], reverse=True)
    return incidents

@app.get("/api/ajin/telemetry")
def get_ajin_telemetry():
    return ajin_mgr.get_data()

@app.post("/api/ajin/refresh")
def force_refresh_ajin():
    ajin_mgr.fetch_telemetry_async(force=True)
    return {"status": "refreshing"}

@app.post("/api/ajin/label")
def save_ajin_label(req: EditLabelRequest):
    ajin_mgr.save_label(req.port, req.onu_id, req.name, req.desc)
    return {"status": "saved"}

# Endpoint WebSocket para telemetria contínua
@app.websocket("/ws/ajin")
async def websocket_ajin_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Envia estado inicial imediatamente ao conectar
        await websocket.send_json({
            "type": "initial_state",
            "data": ajin_mgr.get_data(),
            "time": datetime.now().strftime("%H:%M:%S")
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

    # Primeira checagem imediata de conectividade de todos os servidores
    threading.Thread(target=check_all_servers_status, daemon=True).start()

    while True:
        time.sleep(1)
        refresh_countdown -= 1
        supabase_sync_counter += 1
        status_check_counter += 1
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
