"""
Módulo de Gerenciamento do Mapa Web de Alta Performance (60-120 FPS).
Utiliza Leaflet.js + Google Satélite Híbrido acelerado por GPU via Microsoft Edge.
Comunicação bidirecional local e acoplamento nativo no container do RemoteXPTI.
"""

import os
import sys
import json
import time
import subprocess
import threading
import http.server
import socketserver
from pathlib import Path
from typing import Dict, Any, Optional, Callable

import win32gui
import win32con
import win32process

from map_manager import resolve_server_coordinates, DEFAULT_MAP_CENTER, DEFAULT_MAP_ZOOM


def get_resource_path(relative_path: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / relative_path
        if p.exists():
            return p
    if getattr(sys, "frozen", False):
        p = Path(sys.executable).parent / relative_path
        if p.exists():
            return p
    return Path(__file__).parent.resolve() / relative_path


def get_edge_executable() -> Optional[str]:
    """Localiza o executável nativo do Microsoft Edge no Windows."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <title>RemoteXPTI - Mapa de Acessos</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="/static/leaflet.css" />
    <link rel="stylesheet" href="/static/MarkerCluster.css" />
    <link rel="stylesheet" href="/static/MarkerCluster.Default.css" />
    <script src="/static/leaflet.js"></script>
    <script src="/static/leaflet.markercluster.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
        body, html, #map {
            width: 100%;
            height: 100%;
            background: #121318;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            overflow: hidden;
        }

        /* Top Overlay Toolbar (HUD) */
        .map-hud {
            position: absolute;
            top: 12px;
            left: 12px;
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(22, 23, 29, 0.90);
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            padding: 8px 14px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.14);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.55);
        }
        .map-title {
            font-size: 13px;
            font-weight: 700;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .map-search {
            background: #181a22;
            border: 1px solid #333748;
            border-radius: 6px;
            color: #fff;
            padding: 6px 12px;
            font-size: 12px;
            outline: none;
            width: 210px;
            transition: border-color 0.2s;
        }
        .map-search:focus {
            border-color: #0066cc;
        }
        .btn-action {
            background: #252834;
            color: #e2e8f0;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .btn-action:hover {
            background: #34384a;
            color: #ffffff;
        }

        /* Floating Bottom Card */
        .bottom-card {
            position: absolute;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 1000;
            width: min(720px, 92%);
            background: rgba(20, 22, 28, 0.94);
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            padding: 14px 18px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
            display: none;
            animation: slideUp 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes slideUp {
            from { opacity: 0; transform: translate(-50%, 15px); }
            to { opacity: 1; transform: translate(-50%, 0); }
        }
        .card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }
        .card-title-box {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .card-title {
            font-size: 16px;
            font-weight: 700;
            color: #ffffff;
        }
        .badge-status {
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .status-online {
            background: rgba(46, 189, 89, 0.18);
            color: #2ebd59;
            border: 1px solid rgba(46, 189, 89, 0.4);
        }
        .status-offline {
            background: rgba(240, 68, 56, 0.18);
            color: #f04438;
            border: 1px solid rgba(240, 68, 56, 0.4);
        }
        .status-checking {
            background: rgba(148, 163, 184, 0.18);
            color: #94a3b8;
            border: 1px solid rgba(148, 163, 184, 0.4);
        }
        .card-close {
            background: transparent;
            border: none;
            color: #8e92a0;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            padding: 2px 6px;
            border-radius: 4px;
        }
        .card-close:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.1);
        }
        .card-body {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .card-info {
            font-size: 12px;
            color: #a0a5b5;
            display: flex;
            gap: 14px;
        }
        .card-actions {
            display: flex;
            gap: 8px;
        }
        .btn-connect {
            background: #0066cc;
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: background 0.2s;
        }
        .btn-connect:hover {
            background: #0052a3;
        }
        .btn-edit {
            background: #2c303c;
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 6px;
            padding: 8px 14px;
            font-size: 12px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn-edit:hover {
            background: #3a3f4e;
        }

        /* Pulsing Radar Markers */
        .pulse-marker-online {
            width: 16px;
            height: 16px;
            background: #2ebd59;
            border-radius: 50%;
            border: 2px solid #ffffff;
            box-shadow: 0 0 0 0 rgba(46, 189, 89, 0.7);
            animation: pulse-green 2s infinite;
            cursor: pointer;
        }
        @keyframes pulse-green {
            0% { box-shadow: 0 0 0 0 rgba(46, 189, 89, 0.8); }
            70% { box-shadow: 0 0 0 14px rgba(46, 189, 89, 0); }
            100% { box-shadow: 0 0 0 0 rgba(46, 189, 89, 0); }
        }

        .pulse-marker-offline {
            width: 16px;
            height: 16px;
            background: #f04438;
            border-radius: 50%;
            border: 2px solid #ffffff;
            box-shadow: 0 0 0 0 rgba(240, 68, 56, 0.7);
            animation: pulse-red 2s infinite;
            cursor: pointer;
        }
        @keyframes pulse-red {
            0% { box-shadow: 0 0 0 0 rgba(240, 68, 56, 0.8); }
            70% { box-shadow: 0 0 0 12px rgba(240, 68, 56, 0); }
            100% { box-shadow: 0 0 0 0 rgba(240, 68, 56, 0); }
        }

        .pulse-marker-checking {
            width: 14px;
            height: 14px;
            background: #94a3b8;
            border-radius: 50%;
            border: 2px solid #ffffff;
            cursor: pointer;
        }

        /* MarkerCluster Dark Custom Styling */
        .marker-cluster-small, .marker-cluster-medium, .marker-cluster-large {
            background-color: rgba(0, 102, 204, 0.4) !important;
        }
        .marker-cluster-small div, .marker-cluster-medium div, .marker-cluster-large div {
            background-color: #0066cc !important;
            color: #ffffff !important;
            font-weight: 700 !important;
        }

        /* Leaflet Dark Tooltips */
        .leaflet-tooltip-dark {
            background: rgba(18, 20, 26, 0.9) !important;
            color: #ffffff !important;
            border: 1px solid rgba(255, 255, 255, 0.15) !important;
            border-radius: 6px !important;
            font-size: 11px !important;
            font-weight: 600 !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5) !important;
            padding: 4px 8px !important;
        }
        .leaflet-tooltip-dark::before {
            border-top-color: rgba(18, 20, 26, 0.9) !important;
        }
    </style>
</head>
<body>
    <div class="map-hud">
        <div class="map-title">🛰️ Mapa de Acessos</div>
        <input type="text" id="searchInput" class="map-search" placeholder="🔍 Filtrar servidor ou cidade..." />
        <button class="btn-action" onclick="centerSC()">📍 Centralizar SC</button>
        <span id="serverCountBadge" style="font-size: 11px; color: #8e92a0; margin-left: 6px;">Carregando...</span>
    </div>

    <div id="map"></div>

    <div id="bottomCard" class="bottom-card">
        <div class="card-header">
            <div class="card-title-box">
                <span id="cardTitle" class="card-title">Nome do Servidor</span>
                <span id="cardBadge" class="badge-status status-online">🟢 Online</span>
            </div>
            <button class="card-close" onclick="hideCard()">✕</button>
        </div>
        <div class="card-body">
            <div id="cardInfo" class="card-info">
                <span>🌐 Host: 10.0.0.1:3389</span>
                <span>📁 Grupo: SEJURI</span>
                <span>👤 Usuário: adm</span>
            </div>
            <div class="card-actions">
                <button class="btn-edit" onclick="editCurrentServer()">⚙️ Editar</button>
                <button class="btn-connect" onclick="connectCurrentServer()">🚀 Conectar Agora (RDP)</button>
            </div>
        </div>
    </div>

    <script>
        // Camadas de Mapas (Satélite Real Fotográfico como Padrão)
        const googleSatellite = L.tileLayer('https://mt{s}.google.com/vt/lyrs=y&hl=pt-BR&x={x}&y={y}&z={z}&s=Ga', {
            maxZoom: 20,
            subdomains: ['0', '1', '2', '3'],
            attribution: 'Google Satélite Híbrido'
        });
        const googleRoads = L.tileLayer('https://mt{s}.google.com/vt/lyrs=m&hl=pt-BR&x={x}&y={y}&z={z}&s=Ga', {
            maxZoom: 20,
            subdomains: ['0', '1', '2', '3'],
            attribution: 'Google Maps'
        });
        const cartoDark = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 19,
            subdomains: 'abcd',
            attribution: 'CartoDB Dark Matter'
        });
        const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            subdomains: ['a', 'b', 'c'],
            attribution: 'OpenStreetMap'
        });

        const map = L.map('map', {
            center: [-27.2423, -50.2189],
            zoom: 8,
            layers: [googleSatellite],
            zoomControl: false
        });

        window.addEventListener('resize', () => {
            if (map) map.invalidateSize();
        });

        // Controles de zoom no canto superior direito
        L.control.zoom({ position: 'topright' }).addTo(map);

        // Seletor de Camadas
        const baseMaps = {
            "🛰️ Google Satélite": googleSatellite,
            "🗺️ Google Maps": googleRoads,
            "🌑 CartoDB Dark": cartoDark,
            "🌍 OpenStreetMap": osm
        };
        L.control.layers(baseMaps, null, { position: 'topright' }).addTo(map);

        // Cluster de Marcadores
        const clusterGroup = L.markerClusterGroup({
            spiderfyOnMaxZoom: true,
            showCoverageOnHover: false,
            zoomToBoundsOnClick: true,
            maxClusterRadius: 35
        });
        map.addLayer(clusterGroup);

        let serversData = [];
        let markersMap = {};
        let currentSelectedServer = null;
        let lastServersJson = '';

        function createCustomIcon(status) {
            let cssClass = 'pulse-marker-checking';
            if (status === true) cssClass = 'pulse-marker-online';
            else if (status === false) cssClass = 'pulse-marker-offline';

            return L.divIcon({
                className: cssClass,
                iconSize: [16, 16],
                iconAnchor: [8, 8]
            });
        }

        async function loadServers() {
            try {
                const res = await fetch('/api/servers');
                const text = await res.text();
                lastServersJson = text;
                serversData = JSON.parse(text);
                renderMarkers(serversData);
            } catch (err) {
                console.error('Falha ao carregar servidores:', err);
            }
        }

        function renderMarkers(servers) {
            clusterGroup.clearLayers();
            markersMap = {};

            let mappedCount = 0;
            servers.forEach(s => {
                if (!s.latitude || !s.longitude) return;

                const icon = createCustomIcon(s.online);
                const marker = L.marker([s.latitude, s.longitude], { icon: icon });

                marker.bindTooltip(s.name, {
                    permanent: false,
                    direction: 'top',
                    className: 'leaflet-tooltip-dark',
                    offset: [0, -8]
                });

                marker.on('click', () => {
                    showCard(s);
                });

                clusterGroup.addLayer(marker);
                markersMap[s.id] = marker;
                mappedCount++;
            });

            const badge = document.getElementById('serverCountBadge');
            if (badge) {
                badge.innerText = `${mappedCount} servidores no mapa`;
            }
        }

        function showCard(s) {
            currentSelectedServer = s;
            document.getElementById('cardTitle').innerText = s.name;
            
            const badge = document.getElementById('cardBadge');
            if (s.online === true) {
                badge.className = 'badge-status status-online';
                badge.innerText = '🟢 Online (RDP Disponível)';
            } else if (s.online === false) {
                badge.className = 'badge-status status-offline';
                badge.innerText = '🔴 Offline';
            } else {
                badge.className = 'badge-status status-checking';
                badge.innerText = '⚪ Verificando...';
            }

            document.getElementById('cardInfo').innerHTML = `
                <span>🌐 <b>Host:</b> ${s.host}:${s.port || 3389}</span>
                <span>📁 <b>Grupo:</b> ${s.group || 'Geral'}</span>
                <span>👤 <b>Usuário:</b> ${s.username || 'Padrão'}</span>
            `;

            document.getElementById('bottomCard').style.display = 'block';
        }

        function hideCard() {
            document.getElementById('bottomCard').style.display = 'none';
            currentSelectedServer = null;
        }

        function connectCurrentServer() {
            if (currentSelectedServer) {
                fetch('/api/connect?id=' + currentSelectedServer.id);
            }
        }

        function editCurrentServer() {
            if (currentSelectedServer) {
                fetch('/api/edit?id=' + currentSelectedServer.id);
            }
        }

        function centerSC() {
            map.flyTo([-27.2423, -50.2189], 8, { duration: 1.2 });
        }

        // Busca com flyTo inteligente
        document.getElementById('searchInput').addEventListener('input', (e) => {
            const query = e.target.value.trim().toLowerCase();
            if (!query) {
                renderMarkers(serversData);
                return;
            }

            const filtered = serversData.filter(s =>
                (s.name && s.name.toLowerCase().includes(query)) ||
                (s.host && s.host.toLowerCase().includes(query)) ||
                (s.group && s.group.toLowerCase().includes(query))
            );

            renderMarkers(filtered);

            if (filtered.length === 1 && filtered[0].latitude && filtered[0].longitude) {
                map.flyTo([filtered[0].latitude, filtered[0].longitude], 13, { duration: 1.2 });
                showCard(filtered[0]);
            }
        });

        // Polling de Status Ping em segundo plano (a cada 2.5s)
        setInterval(async () => {
            try {
                const res = await fetch('/api/status');
                const statusMap = await res.json();
                serversData.forEach(s => {
                    if (statusMap[s.id] !== undefined) {
                        s.online = statusMap[s.id].online;
                        if (markersMap[s.id]) {
                            markersMap[s.id].setIcon(createCustomIcon(s.online));
                        }
                    }
                });

                if (currentSelectedServer && statusMap[currentSelectedServer.id] !== undefined) {
                    currentSelectedServer.online = statusMap[currentSelectedServer.id].online;
                    showCard(currentSelectedServer);
                }
            } catch (err) {}
        }, 2500);

        // Polling de sincronização da lista de servidores (a cada 4s)
        setInterval(async () => {
            try {
                const res = await fetch('/api/servers');
                const text = await res.text();
                if (text !== lastServersJson) {
                    lastServersJson = text;
                    serversData = JSON.parse(text);
                    renderMarkers(serversData);
                }
            } catch (err) {}
        }, 4000);

        loadServers();
    </script>
</body>
</html>
"""


class WebMapServer:
    """Servidor HTTP embutido para fornecer o frontend Leaflet e APIs REST."""

    def __init__(
        self,
        get_servers_func: Callable[[], list],
        get_status_func: Callable[[], dict],
        on_connect_func: Callable[[str], None],
        on_edit_func: Callable[[str], None],
    ):
        self.get_servers_func = get_servers_func
        self.get_status_func = get_status_func
        self.on_connect_func = on_connect_func
        self.on_edit_func = on_edit_func
        self.httpd: Optional[socketserver.TCPServer] = None
        self.port = 0
        self._thread: Optional[threading.Thread] = None

    def start(self):
        handler_cls = self._make_handler()
        self.httpd = socketserver.TCPServer(("127.0.0.1", 0), handler_cls)
        self.port = self.httpd.server_address[1]
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
        print(f"[WebMapServer] Servidor Leaflet iniciado em http://127.0.0.1:{self.port}")

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None

    def _make_handler(self):
        server_self = self

        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Silencia logs no terminal

            def do_GET(self):
                if self.path == "/" or self.path == "/index.html":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

                elif self.path.startswith("/static/"):
                    fname = self.path[len("/static/"):].split("?")[0]
                    file_path = get_resource_path(f"web/{fname}")
                    if file_path.exists() and file_path.is_file():
                        data = file_path.read_bytes()
                        mime = "text/css" if fname.endswith(".css") else "application/javascript"
                        self.send_response(200)
                        self.send_header("Content-Type", f"{mime}; charset=utf-8")
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Cache-Control", "public, max-age=86400")
                        self.end_headers()
                        self.wfile.write(data)
                    else:
                        self.send_response(404)
                        self.end_headers()

                elif self.path == "/api/servers":
                    servers = server_self.get_servers_func()
                    status_dict = server_self.get_status_func()
                    output = []
                    for s in servers:
                        s_id = s["id"]
                        stat = status_dict.get(s_id)
                        online_val = stat[0] if stat is not None else None
                        coords = resolve_server_coordinates(s)
                        output.append({
                            "id": s_id,
                            "name": s.get("name", "Servidor"),
                            "host": s.get("host", ""),
                            "port": s.get("port", 3389),
                            "group": s.get("group", "Geral"),
                            "username": s.get("username", ""),
                            "latitude": coords[0] if coords else None,
                            "longitude": coords[1] if coords else None,
                            "online": online_val
                        })
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(output).encode("utf-8"))

                elif self.path == "/api/status":
                    status_dict = server_self.get_status_func()
                    payload = {
                        s_id: {"online": val[0], "msg": val[1]}
                        for s_id, val in status_dict.items()
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode("utf-8"))

                elif self.path.startswith("/api/connect"):
                    s_id = self.path.split("=")[-1]
                    server_self.on_connect_func(s_id)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status": "ok"}')

                elif self.path.startswith("/api/edit"):
                    s_id = self.path.split("=")[-1]
                    server_self.on_edit_func(s_id)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status": "ok"}')

                else:
                    self.send_response(404)
                    self.end_headers()

        return Handler


class WebMapManager:
    """Controlador que acopla o Microsoft Edge ao container do RemoteXPTI."""

    def __init__(
        self,
        container_widget,
        get_servers_func: Callable[[], list],
        get_status_func: Callable[[], dict],
        on_connect_func: Callable[[str], None],
        on_edit_func: Callable[[str], None],
    ):
        self.container = container_widget
        self.get_servers_func = get_servers_func
        self.get_status_func = get_status_func
        self.on_connect_func = on_connect_func
        self.on_edit_func = on_edit_func

        self.server = WebMapServer(
            get_servers_func,
            get_status_func,
            on_connect_func,
            on_edit_func
        )
        self.edge_proc: Optional[subprocess.Popen] = None
        self.edge_hwnd: Optional[int] = None
        self._is_docked = False
        self._is_visible = False

    def start(self):
        """Inicia o servidor HTTP embutido."""
        self.server.start()

    def show(self):
        """Garante que o Edge esteja iniciado, docado no container e visível."""
        self._is_visible = True
        if not self._is_docked:
            self._launch_and_dock()
        elif self.edge_hwnd:
            try:
                win32gui.ShowWindow(self.edge_hwnd, win32con.SW_SHOW)
                self.resize()
            except Exception:
                pass

    def hide(self):
        """Oculta o mapa web quando o usuário volta para a grade."""
        self._is_visible = False
        if self.edge_hwnd:
            try:
                win32gui.ShowWindow(self.edge_hwnd, win32con.SW_HIDE)
            except Exception:
                pass

    def resize(self):
        """Ajusta o tamanho do Edge para corresponder perfeitamente ao container."""
        if not self.edge_hwnd or not self._is_visible:
            return
        try:
            w = self.container.winfo_width()
            h = self.container.winfo_height()
            if w > 50 and h > 50:
                win32gui.MoveWindow(self.edge_hwnd, 0, 0, w, h, True)
        except Exception:
            pass

    def _launch_and_dock(self):
        edge_exe = get_edge_executable()
        if not edge_exe:
            print("[WebMapManager] Microsoft Edge não encontrado no sistema.")
            return

        cache_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RemoteXPTI" / "map_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        w = max(400, self.container.winfo_width())
        h = max(300, self.container.winfo_height())

        cmd = [
            edge_exe,
            f"--app=http://127.0.0.1:{self.server.port}",
            f"--user-data-dir={str(cache_dir)}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate",
            "--disable-background-networking",
            f"--window-size={w},{h}",
            "--window-position=-32000,-32000"
        ]

        creation_flags = 0
        self.edge_proc = subprocess.Popen(cmd, creationflags=creation_flags)

        def find_and_dock_thread():
            target_parent_hwnd = self.container.winfo_id()
            found_hwnd = None

            for _ in range(40):
                time.sleep(0.08)
                if not self.edge_proc or self.edge_proc.poll() is not None:
                    break

                def enum_cb(h, _):
                    nonlocal found_hwnd
                    if win32gui.IsWindowVisible(h):
                        cname = win32gui.GetClassName(h)
                        if "Chrome_WidgetWin_1" in cname:
                            try:
                                _, pid = win32process.GetWindowThreadProcessId(h)
                                if pid == self.edge_proc.pid:
                                    found_hwnd = h
                            except Exception:
                                pass
                win32gui.EnumWindows(enum_cb, None)
                if found_hwnd:
                    break

            if found_hwnd:
                self.edge_hwnd = found_hwnd
                old_style = win32gui.GetWindowLong(found_hwnd, win32con.GWL_STYLE)
                new_style = (old_style & ~win32con.WS_POPUP & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME & ~win32con.WS_MINIMIZEBOX & ~win32con.WS_MAXIMIZEBOX & ~win32con.WS_SYSMENU) | win32con.WS_CHILD
                win32gui.SetWindowLong(found_hwnd, win32con.GWL_STYLE, new_style)
                win32gui.SetParent(found_hwnd, target_parent_hwnd)

                cur_w = self.container.winfo_width()
                cur_h = self.container.winfo_height()
                win32gui.MoveWindow(found_hwnd, 0, 0, cur_w, cur_h, True)
                win32gui.ShowWindow(found_hwnd, win32con.SW_SHOW if self._is_visible else win32con.SW_HIDE)
                self._is_docked = True
                print(f"[WebMapManager] Edge acoplado com sucesso no HWND {target_parent_hwnd}!")

        threading.Thread(target=find_and_dock_thread, daemon=True).start()

    def shutdown(self):
        """Fecha o processo e o servidor na saída do RemoteXPTI."""
        self.hide()
        if self.edge_hwnd:
            try:
                win32gui.PostMessage(self.edge_hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self.edge_proc:
            try:
                self.edge_proc.terminate()
            except Exception:
                pass
            self.edge_proc = None
        self.server.stop()
