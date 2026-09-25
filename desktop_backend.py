"""
Serviço Backend Local FastAPI + WebSockets para o RemoteXPTI Modern Desktop.
Fornece APIs de alta velocidade e streaming em tempo real para a interface React/Tauri.
"""

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from ajin_manager import AjinManager
from logger import log
from rdp_manager import RDPManager
from storage import StorageManager
from version import CURRENT_VERSION

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

# Callback do AjinManager para notificar o WebSocket
def _on_ajin_updated():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast({"type": "telemetry_update", "data": ajin_mgr.get_data()}),
                loop
            )
    except Exception:
        pass

ajin_mgr.add_listener(_on_ajin_updated)

# Modelos Pydantic
class ConnectRequest(BaseModel):
    server_id: str

class EditLabelRequest(BaseModel):
    port: str
    onu_id: str
    name: str = ""
    desc: str = ""

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
    # Remove senhas planas por segurança da API
    safe_servers = []
    for s in servers:
        sc = s.copy()
        sc.pop("password", None)
        sc.pop("password_plain", None)
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

        RDPManager.connect(
            host=host,
            port=port,
            username=user,
            password=pwd,
            fullscreen=full,
            admin_mode=adm,
            multimon=multi
        )
        storage_mgr.record_connection(req.server_id)

    threading.Thread(target=_launch, daemon=True).start()
    return {"status": "launching", "server_name": server.get("name")}

@app.get("/api/incidents")
def get_incidents():
    from config_manager import get_config_dir
    hist_file = get_config_dir() / "downtime_history.json"
    now = time.time()
    incidents = []
    if hist_file.exists():
        try:
            with open(hist_file, "r", encoding="utf-8") as f:
                downtime_map = json.load(f)
            server_map = {s["id"]: s for s in storage_mgr.servers}
            for s_id, offline_since in downtime_map.items():
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
        except Exception as e:
            log.warning(f"Erro ao carregar incidents: {e}")
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

# Monta arquivos estáticos do frontend React compilado
dist_path = Path(__file__).parent / "desktop_ui" / "dist"
if dist_path.exists():
    app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="static")

# Loop de contagem regressiva e broadcast periódico
def _background_heartbeat():
    refresh_countdown = 10
    while True:
        time.sleep(1)
        refresh_countdown -= 1
        now_str = datetime.now().strftime("%H:%M:%S")
        if refresh_countdown <= 0:
            refresh_countdown = 10
            ajin_mgr.fetch_telemetry_async(force=True)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running() and ws_manager.active_connections:
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast({
                        "type": "tick",
                        "time": now_str,
                        "countdown": refresh_countdown
                    }),
                    loop
                )
        except Exception:
            pass

def start_backend_service(port: int = 8765):
    """Inicia o servidor Uvicorn em uma thread separada."""
    threading.Thread(target=_background_heartbeat, daemon=True).start()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    server.run()

if __name__ == "__main__":
    start_backend_service()
