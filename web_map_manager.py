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
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, Callable

import win32gui
import win32con
import win32process

from logger import log
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

        /* Container que une o HUD e a Bandeja Retrátil à esquerda */
        .map-hud-container {
            position: absolute;
            top: 12px;
            left: 12px;
            z-index: 1000;
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            gap: 8px;
            pointer-events: none;
            max-height: calc(100vh - 24px);
        }

        /* Top Overlay Toolbar (HUD) */
        .map-hud {
            pointer-events: auto;
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

        /* Botão de Incidentes no HUD */
        .btn-incident {
            background: #1f212a;
            border-color: rgba(255, 255, 255, 0.12);
            color: #cbd5e1;
        }
        .btn-incident:hover {
            background: #2a2d39;
            color: #ffffff;
        }
        .btn-incident.has-loss {
            background: rgba(240, 68, 56, 0.16);
            border-color: rgba(240, 68, 56, 0.45);
            color: #ff6b6b;
        }
        .btn-incident.has-loss:hover {
            background: rgba(240, 68, 56, 0.26);
        }
        .incident-badge-pill {
            background: #333644;
            color: #94a3b8;
            font-size: 10px;
            font-weight: 800;
            padding: 1px 6px;
            border-radius: 10px;
            margin-left: 2px;
            transition: all 0.2s;
        }
        .btn-incident.has-loss .incident-badge-pill {
            background: #f04438;
            color: #ffffff;
            box-shadow: 0 0 8px rgba(240, 68, 56, 0.6);
        }

        /* Bandeja Retrátil de Incidentes saindo de baixo do menu */
        .incident-tray {
            pointer-events: auto;
            width: 330px;
            max-width: 90vw;
            background: rgba(18, 20, 26, 0.94);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(240, 68, 56, 0.35);
            border-radius: 10px;
            box-shadow: 0 10px 32px rgba(0, 0, 0, 0.65), 0 0 16px rgba(240, 68, 56, 0.12);
            overflow: hidden;
            display: none;
            flex-direction: column;
            animation: traySlideDown 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes traySlideDown {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .incident-tray-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 12px;
            background: rgba(240, 68, 56, 0.12);
            border-bottom: 1px solid rgba(240, 68, 56, 0.22);
        }
        .tray-title-box {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .tray-title {
            font-size: 11px;
            font-weight: 700;
            color: #ff6b6b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .tray-header-count {
            font-size: 10px;
            font-weight: 800;
            background: #f04438;
            color: #ffffff;
            padding: 1px 6px;
            border-radius: 8px;
        }
        .tray-close-btn {
            background: transparent;
            border: none;
            color: #8e92a0;
            font-size: 13px;
            cursor: pointer;
            padding: 2px 6px;
            border-radius: 4px;
            transition: all 0.15s;
        }
        .tray-close-btn:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.1);
        }
        .incident-list {
            max-height: 320px;
            overflow-y: auto;
            padding: 6px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .incident-list::-webkit-scrollbar {
            width: 4px;
        }
        .incident-list::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.18);
            border-radius: 4px;
        }
        .incident-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 10px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s ease;
            gap: 10px;
        }
        .incident-item:hover {
            background: rgba(240, 68, 56, 0.15);
            border-color: rgba(240, 68, 56, 0.45);
            transform: translateX(3px);
        }
        .incident-name-box {
            display: flex;
            align-items: center;
            gap: 7px;
            overflow: hidden;
            flex: 1;
            min-width: 0;
        }
        .incident-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #f04438;
            box-shadow: 0 0 6px #f04438;
            flex-shrink: 0;
            animation: blinkDot 1.4s infinite ease-in-out;
        }
        @keyframes blinkDot {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.35; transform: scale(0.85); }
        }
        .incident-name {
            font-size: 12px;
            font-weight: 600;
            color: #f1f3f7;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .incident-loss-badge {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 11px;
            font-weight: 700;
            color: #ff5252;
            background: rgba(240, 68, 56, 0.16);
            border: 1px solid rgba(240, 68, 56, 0.32);
            padding: 2px 7px;
            border-radius: 4px;
            white-space: nowrap;
            flex-shrink: 0;
        }
        .incident-empty {
            padding: 16px 12px;
            text-align: center;
            color: #8e92a0;
            font-size: 11px;
            font-style: italic;
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

        /* Layer Switcher no HUD */
        .layer-switch-box {
            display: flex;
            background: #14161d;
            border: 1px solid #363a4a;
            border-radius: 6px;
            padding: 2px;
            gap: 2px;
        }
        .btn-layer-toggle {
            background: transparent;
            color: #9aa0b2;
            border: none;
            border-radius: 4px;
            padding: 5px 11px;
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
            display: flex;
            align-items: center;
            gap: 5px;
            white-space: nowrap;
        }
        .btn-layer-toggle:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.08);
        }
        .btn-layer-toggle.active {
            background: #0066cc;
            color: #ffffff;
            box-shadow: 0 2px 8px rgba(0, 102, 204, 0.4);
        }

        /* Marcador em Alfinete de Alta Definição com Bolinha de Status */
        .leaflet-pin-container {
            background: transparent !important;
            border: none !important;
        }
        .pin-marker {
            width: 30px;
            height: 38px;
            cursor: pointer;
            filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.75));
            transition: transform 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            transform-origin: bottom center;
        }
        .pin-marker:hover {
            transform: scale(1.22) translateY(-4px);
            filter: drop-shadow(0 6px 14px rgba(0, 0, 0, 0.9));
            z-index: 9999 !important;
        }
        .pin-online .pin-halo {
            animation: pulse-halo-green 2.2s infinite ease-in-out;
        }
        @keyframes pulse-halo-green {
            0%, 100% { r: 6.5px; opacity: 0.35; }
            50% { r: 8.5px; opacity: 0.9; }
        }
        .pin-offline .pin-halo {
            animation: pulse-halo-red 2.2s infinite ease-in-out;
        }
        @keyframes pulse-halo-red {
            0%, 100% { r: 6.5px; opacity: 0.35; }
            50% { r: 8.5px; opacity: 0.9; }
        }

        /* MarkerCluster Dark Custom Styling (Azul Padrão - Todos Online) */
        .marker-cluster-small, .marker-cluster-medium, .marker-cluster-large {
            background-color: rgba(0, 102, 204, 0.45) !important;
        }
        .marker-cluster-small div, .marker-cluster-medium div, .marker-cluster-large div {
            background-color: #0066cc !important;
            color: #ffffff !important;
            font-weight: 800 !important;
            border: 2px solid #ffffff !important;
            box-shadow: 0 4px 10px rgba(0,0,0,0.6) !important;
        }

        /* MarkerCluster Alerta Amarelo/Âmbar (Quando houver servidor offline no grupo) */
        .marker-cluster-alert {
            background-color: rgba(245, 158, 11, 0.45) !important;
            animation: pulse-cluster-warning 2.5s infinite ease-in-out;
        }
        .marker-cluster-alert div {
            background-color: #f59e0b !important;
            color: #0f1117 !important;
            font-weight: 900 !important;
            border: 2px solid #ffffff !important;
            box-shadow: 0 4px 14px rgba(245, 158, 11, 0.75) !important;
        }
        @keyframes pulse-cluster-warning {
            0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.45); }
            50% { box-shadow: 0 0 0 8px rgba(245, 158, 11, 0); }
        }

        /* Controles do Leaflet (Zoom, Bússola e Camadas em Dark Glass) */
        .leaflet-bar {
            border: 1px solid rgba(255, 255, 255, 0.15) !important;
            border-radius: 8px !important;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6) !important;
            overflow: hidden !important;
            background: rgba(18, 20, 26, 0.88) !important;
            backdrop-filter: blur(12px) !important;
        }
        .leaflet-bar a {
            background-color: rgba(18, 20, 26, 0.88) !important;
            color: #ffffff !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;
            width: 34px !important;
            height: 34px !important;
            line-height: 34px !important;
            font-size: 16px !important;
            font-weight: 700 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            transition: all 0.2s ease !important;
        }
        .leaflet-bar a:last-child {
            border-bottom: none !important;
        }
        .leaflet-bar a:hover {
            background-color: #242936 !important;
            color: #0066cc !important;
        }

        /* Bússola Estilo Google Maps */
        .compass-control-container {
            margin-bottom: 8px !important;
            border-radius: 50% !important;
            width: 36px !important;
            height: 36px !important;
            border: 1px solid rgba(255, 255, 255, 0.2) !important;
        }
        .compass-btn {
            border-radius: 50% !important;
            width: 36px !important;
            height: 36px !important;
            padding: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .compass-btn:hover {
            background-color: #242936 !important;
        }
        .compass-btn:hover #compassNeedle {
            filter: drop-shadow(0 0 6px rgba(239, 68, 68, 0.7));
        }

        /* Botão de Bússola Compacto no HUD */
        .btn-compass-hud {
            padding: 5px 9px !important;
            font-size: 14px !important;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }

        /* Correção Definitiva do Quadrado Branco: Controle de Camadas */
        .leaflet-control-layers {
            border: 1px solid rgba(255, 255, 255, 0.15) !important;
            border-radius: 8px !important;
            background: rgba(18, 20, 26, 0.88) !important;
            backdrop-filter: blur(12px) !important;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6) !important;
            color: #ffffff !important;
        }
        .leaflet-control-layers-toggle {
            background-color: transparent !important;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='%23e2e8f0' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='12 2 2 7 12 12 22 7 12 2'%3E%3C/polygon%3E%3Cpolyline points='2 17 12 22 22 17'%3E%3C/polyline%3E%3Cpolyline points='2 12 12 17 22 12'%3E%3C/polyline%3E%3C/svg%3E") !important;
            background-size: 20px 20px !important;
            background-repeat: no-repeat !important;
            background-position: center !important;
            width: 34px !important;
            height: 34px !important;
        }
        .leaflet-control-layers-expanded {
            padding: 10px 14px !important;
            background: #141720 !important;
            border-radius: 8px !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
            font-size: 12px !important;
            font-weight: 600 !important;
            line-height: 1.6 !important;
        }
        .leaflet-control-layers-expanded label {
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            margin-bottom: 4px;
            color: #e2e8f0;
        }
        .leaflet-control-layers-expanded input[type="radio"] {
            accent-color: #0066cc;
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
    <div class="map-hud-container">
        <div class="map-hud">
            <div class="map-title">🗺️ Mapa</div>
            <div class="layer-switch-box">
                <button id="btnLayerSat" class="btn-layer-toggle active" onclick="setMapLayer('satellite')">
                    🛰️ Satélite
                </button>
                <button id="btnLayerRoads" class="btn-layer-toggle" onclick="setMapLayer('roads')">
                    🗺️ Padrão
                </button>
            </div>
            <button class="btn-action btn-compass-hud" onclick="centerSC()" title="Centralizar SC (Bússola / Orientação Norte)">🧭</button>
            <button id="btnToggleIncidents" class="btn-action btn-incident" onclick="toggleIncidentTray()">
                <span class="incident-icon">🚨</span> Incidentes <span id="incidentCountBadge" class="incident-badge-pill">0</span>
            </button>
            <span id="serverCountBadge" style="font-size: 11px; color: #8e92a0; margin-left: 4px;">Carregando...</span>
        </div>

        <!-- Bandeja Retrátil de Incidentes -->
        <div id="incidentTray" class="incident-tray">
            <div class="incident-tray-header">
                <div class="tray-title-box">
                    <span class="tray-title">⚠️ Servidores em Falha / Loss</span>
                    <span id="trayHeaderCount" class="tray-header-count">0</span>
                </div>
                <button class="tray-close-btn" onclick="toggleIncidentTray()" title="Recolher bandeja">✕</button>
            </div>
            <div id="incidentList" class="incident-list">
                <div class="incident-empty">Carregando incidentes...</div>
            </div>
        </div>
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

        // Controle de Bússola Estilo Google Maps
        const CompassControl = L.Control.extend({
            options: { position: 'topright' },
            onAdd: function(map) {
                const container = L.DomUtil.create('div', 'leaflet-bar compass-control-container');
                const btn = L.DomUtil.create('a', 'compass-btn', container);
                btn.href = '#';
                btn.title = 'Centralizar em Santa Catarina (Bússola / Orientação Norte)';
                btn.innerHTML = `
                    <svg id="compassNeedle" width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="12" cy="12" r="10.5" stroke="rgba(255,255,255,0.3)" stroke-width="1.2"/>
                        <polygon points="12,3.5 15.5,12 8.5,12" fill="#ef4444"/>
                        <polygon points="12,20.5 15.5,12 8.5,12" fill="#cbd5e1"/>
                        <circle cx="12" cy="12" r="2" fill="#0f172a" stroke="#ffffff" stroke-width="0.8"/>
                        <text x="12" y="2" font-size="4.5" font-weight="900" fill="#ef4444" text-anchor="middle" dominant-baseline="hanging">N</text>
                    </svg>
                `;
                L.DomEvent.disableClickPropagation(container);
                L.DomEvent.on(btn, 'click', function(e) {
                    L.DomEvent.preventDefault(e);
                    centerSC();
                    const needle = document.getElementById('compassNeedle');
                    if (needle) {
                        needle.style.transition = 'transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)';
                        needle.style.transform = 'rotate(360deg)';
                        setTimeout(() => {
                            needle.style.transition = 'none';
                            needle.style.transform = 'rotate(0deg)';
                        }, 650);
                    }
                });
                return container;
            }
        });
        map.addControl(new CompassControl());

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

        function setMapLayer(type) {
            if (type === 'satellite') {
                if (map.hasLayer(googleRoads)) map.removeLayer(googleRoads);
                if (map.hasLayer(cartoDark)) map.removeLayer(cartoDark);
                if (map.hasLayer(osm)) map.removeLayer(osm);
                if (!map.hasLayer(googleSatellite)) map.addLayer(googleSatellite);

                document.getElementById('btnLayerSat').classList.add('active');
                document.getElementById('btnLayerRoads').classList.remove('active');
            } else if (type === 'roads') {
                if (map.hasLayer(googleSatellite)) map.removeLayer(googleSatellite);
                if (map.hasLayer(cartoDark)) map.removeLayer(cartoDark);
                if (map.hasLayer(osm)) map.removeLayer(osm);
                if (!map.hasLayer(googleRoads)) map.addLayer(googleRoads);

                document.getElementById('btnLayerRoads').classList.add('active');
                document.getElementById('btnLayerSat').classList.remove('active');
            }
        }

        map.on('baselayerchange', (e) => {
            if (e.name.includes('Satélite')) {
                document.getElementById('btnLayerSat').classList.add('active');
                document.getElementById('btnLayerRoads').classList.remove('active');
            } else if (e.name.includes('Google Maps') || e.name.includes('Padrão')) {
                document.getElementById('btnLayerRoads').classList.add('active');
                document.getElementById('btnLayerSat').classList.remove('active');
            } else {
                document.getElementById('btnLayerSat').classList.remove('active');
                document.getElementById('btnLayerRoads').classList.remove('active');
            }
        });

        // Cluster de Marcadores com Alerta Amarelo para falhas locais
        const clusterGroup = L.markerClusterGroup({
            spiderfyOnMaxZoom: true,
            showCoverageOnHover: false,
            zoomToBoundsOnClick: true,
            maxClusterRadius: 35,
            iconCreateFunction: function(cluster) {
                const markers = cluster.getAllChildMarkers();
                const count = cluster.getChildCount();
                const hasOffline = markers.some(m => m.serverData && m.serverData.online === false);

                let c = ' marker-cluster-';
                if (count < 10) {
                    c += 'small';
                } else if (count < 100) {
                    c += 'medium';
                } else {
                    c += 'large';
                }

                if (hasOffline) {
                    c += ' marker-cluster-alert';
                }

                return new L.DivIcon({
                    html: '<div><span>' + count + '</span></div>',
                    className: 'marker-cluster' + c,
                    iconSize: new L.Point(40, 40)
                });
            }
        });
        map.addLayer(clusterGroup);

        let serversData = [];
        let markersMap = {};
        let currentSelectedServer = null;
        let lastServersJson = '';

        function createCustomIcon(status) {
            let statusClass = 'pin-checking';
            let dotColor = '#94a3b8';
            let haloColor = 'rgba(148, 163, 184, 0.25)';
            let pinBg = '#1c1f28';

            if (status === true) {
                statusClass = 'pin-online';
                dotColor = '#2ebd59';
                haloColor = 'rgba(46, 189, 89, 0.45)';
                pinBg = '#142219';
            } else if (status === false) {
                statusClass = 'pin-offline';
                dotColor = '#f04438';
                haloColor = 'rgba(240, 68, 56, 0.45)';
                pinBg = '#261618';
            }

            const html = `
                <div class="pin-marker ${statusClass}">
                    <svg width="30" height="38" viewBox="0 0 30 38" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path class="pin-base" d="M15 1.5C7.544 1.5 1.5 7.544 1.5 15C1.5 24.8 13.9 36.6 14.5 37.1C14.8 37.4 15.2 37.4 15.5 37.1C16.1 36.6 28.5 24.8 28.5 15C28.5 7.544 22.456 1.5 15 1.5Z" fill="${pinBg}" stroke="#ffffff" stroke-width="2"/>
                        <circle class="pin-halo" cx="15" cy="15" r="7.5" fill="${haloColor}"/>
                        <circle class="pin-dot" cx="15" cy="15" r="5" fill="${dotColor}" stroke="#ffffff" stroke-width="1.2"/>
                    </svg>
                </div>
            `;

            return L.divIcon({
                className: 'leaflet-pin-container',
                html: html,
                iconSize: [30, 38],
                iconAnchor: [15, 37],
                tooltipAnchor: [0, -38]
            });
        }

        async function loadServers() {
            try {
                const res = await fetch('/api/servers');
                if (res.ok) {
                    const text = await res.text();
                    lastServersJson = text;
                    serversData = JSON.parse(text);
                    renderMarkers(serversData);
                } else {
                    const badge = document.getElementById('serverCountBadge');
                    if (badge) badge.innerText = '0 servidores no mapa';
                }
            } catch (err) {
                console.error('Falha ao carregar servidores:', err);
                const badge = document.getElementById('serverCountBadge');
                if (badge) badge.innerText = 'Falha ao carregar lista';
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
                marker.serverData = s;

                marker.bindTooltip(s.name, {
                    permanent: false,
                    direction: 'top',
                    className: 'leaflet-tooltip-dark',
                    offset: [0, -38]
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
                const btn = document.querySelector('.btn-connect');
                if (btn) btn.innerText = '⏳ Conectando...';
                fetch('/api/connect?id=' + encodeURIComponent(currentSelectedServer.id))
                    .catch(err => console.error("Erro ao conectar:", err))
                    .finally(() => {
                        setTimeout(() => {
                            if (btn) btn.innerText = '🚀 Conectar Agora (RDP)';
                        }, 1200);
                    });
            }
        }

        function editCurrentServer() {
            if (currentSelectedServer) {
                fetch('/api/edit?id=' + encodeURIComponent(currentSelectedServer.id))
                    .catch(err => console.error("Erro ao abrir edição:", err));
            }
        }

        function centerSC() {
            map.flyTo([-27.2423, -50.2189], 8, { duration: 1.2 });
        }

        // --- Lógica da Bandeja de Incidentes (Loss / Downtime) ---
        let activeIncidents = [];
        let trayUserClosed = false;
        let isTrayOpen = false;

        function formatLossDuration(sec) {
            sec = Math.max(0, Math.floor(sec));
            if (sec < 60) {
                return `${sec}s`;
            }
            const m = Math.floor(sec / 60);
            const s = sec % 60;
            if (m < 60) {
                return `${m}m ${s < 10 ? '0' : ''}${s}s`;
            }
            const h = Math.floor(m / 60);
            const remM = m % 60;
            if (h < 24) {
                return `${h}h ${remM < 10 ? '0' : ''}${remM}m`;
            }
            const d = Math.floor(h / 24);
            const remH = h % 24;
            return `${d}d ${remH}h`;
        }

        function toggleIncidentTray(forceState) {
            const tray = document.getElementById('incidentTray');
            if (!tray) return;
            if (forceState !== undefined) {
                isTrayOpen = forceState;
            } else {
                isTrayOpen = !isTrayOpen;
                if (!isTrayOpen) {
                    trayUserClosed = true;
                } else {
                    trayUserClosed = false;
                }
            }
            tray.style.display = isTrayOpen ? 'flex' : 'none';
        }

        function renderIncidentsList() {
            const listEl = document.getElementById('incidentList');
            const btnToggle = document.getElementById('btnToggleIncidents');
            const countBadge = document.getElementById('incidentCountBadge');
            const trayCount = document.getElementById('trayHeaderCount');

            const count = activeIncidents.length;
            if (countBadge) countBadge.innerText = count;
            if (trayCount) trayCount.innerText = count;

            if (btnToggle) {
                if (count > 0) {
                    btnToggle.classList.add('has-loss');
                } else {
                    btnToggle.classList.remove('has-loss');
                }
            }

            if (!listEl) return;

            if (count === 0) {
                listEl.innerHTML = '<div class="incident-empty">✨ Todos os servidores operando normalmente (0 em loss)</div>';
                return;
            }

            // Garante ordenação estrita decrescente: maior tempo offline no topo
            activeIncidents.sort((a, b) => b.duration_seconds - a.duration_seconds);

            let html = '';
            activeIncidents.forEach(inc => {
                const durStr = formatLossDuration(inc.duration_seconds);
                const safeName = (inc.name || 'Servidor').replace(/"/g, '&quot;');
                html += `
                    <div class="incident-item" onclick="onIncidentClick('${inc.id}')" title="Clique para focar no servidor ${safeName}">
                        <div class="incident-name-box">
                            <span class="incident-dot"></span>
                            <span class="incident-name">${safeName}</span>
                        </div>
                        <span class="incident-loss-badge">${durStr}</span>
                    </div>
                `;
            });
            listEl.innerHTML = html;
        }

        function onIncidentClick(serverId) {
            const srv = serversData.find(s => s.id === serverId);
            if (srv) {
                if (srv.latitude && srv.longitude) {
                    map.flyTo([srv.latitude, srv.longitude], 13, { duration: 1.0 });
                }
                showCard(srv);
            }
        }

        async function loadIncidents() {
            try {
                const res = await fetch('/api/incidents');
                if (res.ok) {
                    activeIncidents = await res.json();
                    renderIncidentsList();

                    // Abre a bandeja automaticamente se surgiram incidentes e o usuário não fechou
                    if (activeIncidents.length > 0 && !trayUserClosed && !isTrayOpen) {
                        toggleIncidentTray(true);
                    }
                }
            } catch (err) {}
        }

        // Ticker local a cada 1s: avança contadores na tela suavemente ao vivo
        setInterval(() => {
            if (activeIncidents.length > 0) {
                activeIncidents.forEach(inc => {
                    inc.duration_seconds = (inc.duration_seconds || 0) + 1;
                });
                renderIncidentsList();
            }
        }, 1000);

        // Polling de incidentes em segundo plano a cada 2.0s
        setInterval(loadIncidents, 2000);
        loadIncidents();

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

        // Sincronização em tempo real da lista de servidores / busca do topo (a cada 700ms)
        setInterval(async () => {
            try {
                const res = await fetch('/api/servers');
                const text = await res.text();
                if (text !== lastServersJson) {
                    lastServersJson = text;
                    serversData = JSON.parse(text);
                    renderMarkers(serversData);

                    if (serversData.length === 1 && serversData[0].latitude && serversData[0].longitude) {
                        map.flyTo([serversData[0].latitude, serversData[0].longitude], 13, { duration: 1.2 });
                        showCard(serversData[0]);
                    }
                }
            } catch (err) {}
        }, 700);

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
        get_incidents_func: Optional[Callable[[], list]] = None,
    ):
        self.get_servers_func = get_servers_func
        self.get_status_func = get_status_func
        self.on_connect_func = on_connect_func
        self.on_edit_func = on_edit_func
        self.get_incidents_func = get_incidents_func
        self.httpd: Optional[socketserver.TCPServer] = None
        self.port = 0
        self._thread: Optional[threading.Thread] = None

    def start(self):
        handler_cls = self._make_handler()

        class QuietTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            daemon_threads = True
            allow_reuse_address = True

            def handle_error(self, request, client_address):
                pass  # Silencia desconexoes abruptas ao fechar o app

        self.httpd = QuietTCPServer(("127.0.0.1", 0), handler_cls)
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

            def _send_json(self, data_obj, status=200):
                body = json.dumps(data_obj).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/" or self.path == "/index.html":
                    html_bytes = HTML_TEMPLATE.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html_bytes)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(html_bytes)

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
                        self.send_header("Connection", "close")
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
                    self._send_json(output)

                elif self.path == "/api/status":
                    status_dict = server_self.get_status_func()
                    payload = {
                        s_id: {"online": val[0], "msg": val[1]}
                        for s_id, val in status_dict.items()
                    }
                    self._send_json(payload)

                elif self.path == "/api/incidents":
                    incidents = server_self.get_incidents_func() if server_self.get_incidents_func else []
                    self._send_json(incidents)

                elif self.path.startswith("/api/connect"):
                    parsed = urllib.parse.urlparse(self.path)
                    params = urllib.parse.parse_qs(parsed.query)
                    s_id = params.get("id", [None])[0]
                    if s_id:
                        server_self.on_connect_func(s_id)
                    self._send_json({"status": "ok"})

                elif self.path.startswith("/api/edit"):
                    parsed = urllib.parse.urlparse(self.path)
                    params = urllib.parse.parse_qs(parsed.query)
                    s_id = params.get("id", [None])[0]
                    if s_id:
                        server_self.on_edit_func(s_id)
                    self._send_json({"status": "ok"})

                else:
                    self.send_response(404)
                    self.end_headers()

        return Handler


def cleanup_orphaned_edge_processes(cache_dir: Path):
    """Encerra de forma nativa e 100% silenciosa processos msedge.exe antigos atrelados ao cache do mapa."""
    cache_str = str(cache_dir).lower()
    try:
        import win32com.client
        wmi = win32com.client.GetObject("winmgmts:")
        procs = wmi.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name = 'msedge.exe'")
        for p in procs:
            cmd = (p.CommandLine or "").lower()
            if cache_str in cmd:
                try:
                    p.Terminate()
                except Exception:
                    pass
    except Exception:
        pass

    for lock_name in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        lock_file = cache_dir / lock_name
        if lock_file.exists():
            try:
                lock_file.unlink()
            except Exception:
                pass


class WebMapManager:
    """Controlador que acopla o Microsoft Edge ao container do RemoteXPTI."""

    def __init__(
        self,
        container_widget,
        get_servers_func: Callable[[], list],
        get_status_func: Callable[[], dict],
        on_connect_func: Callable[[str], None],
        on_edit_func: Callable[[str], None],
        get_incidents_func: Optional[Callable[[], list]] = None,
    ):
        self.container = container_widget
        try:
            self.container_hwnd = container_widget.winfo_id()
        except Exception:
            self.container_hwnd = None

        self.get_servers_func = get_servers_func
        self.get_status_func = get_status_func
        self.on_connect_func = on_connect_func
        self.on_edit_func = on_edit_func
        self.get_incidents_func = get_incidents_func

        self.server = WebMapServer(
            get_servers_func,
            get_status_func,
            on_connect_func,
            on_edit_func,
            get_incidents_func
        )
        self.edge_proc: Optional[subprocess.Popen] = None
        self.edge_hwnd: Optional[int] = None
        self._is_docked = False
        self._is_visible = False

    def start(self):
        """Inicia o servidor HTTP embutido, limpa processos orfãos e pré-carrega o mapa em segundo plano."""
        log.info("[WebMapManager] Inicializando subsistema do mapa Leaflet...")
        cache_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RemoteXPTI" / "map_cache"
        cleanup_orphaned_edge_processes(cache_dir)
        self.server.start()
        log.info(f"[WebMapServer] Servidor Leaflet pronto em http://127.0.0.1:{self.server.port}")
        # Pré-carrega o Edge totalmente fora da tela para inicialização instantânea (0ms) sem flashes visíveis
        threading.Thread(target=self._launch_and_dock, daemon=True).start()

    def show(self):
        """Garante que o Edge esteja iniciado, docado no container e visível."""
        self._is_visible = True
        log.info(f"[WebMapManager] show() acionado (is_docked={self._is_docked}, edge_hwnd={self.edge_hwnd})")
        if not self._is_docked:
            if not self.edge_proc or self.edge_proc.poll() is not None:
                log.info("[WebMapManager] Edge não estava em execução. Disparando _launch_and_dock()...")
                self._launch_and_dock()
        if self.edge_hwnd and self._is_docked:
            try:
                w = max(400, self.container.winfo_width())
                h = max(300, self.container.winfo_height())
                log.info(f"[WebMapManager] Posicionando Edge no HWND_TOP com tamanho {w}x{h}...")
                win32gui.SetWindowPos(self.edge_hwnd, win32con.HWND_TOP, 0, 0, w, h, win32con.SWP_SHOWWINDOW)
                win32gui.ShowWindow(self.edge_hwnd, win32con.SW_SHOW)
                win32gui.InvalidateRect(self.edge_hwnd, None, True)
                win32gui.UpdateWindow(self.edge_hwnd)
            except Exception as e:
                log.error(f"[WebMapManager] Erro ao exibir janela do Edge: {e}")

    def hide(self):
        """Oculta o mapa web quando o usuário volta para a grade."""
        self._is_visible = False
        log.info("[WebMapManager] hide() acionado - Ocultando janela do mapa")
        if self.edge_hwnd:
            try:
                win32gui.ShowWindow(self.edge_hwnd, win32con.SW_HIDE)
            except Exception as e:
                log.error(f"[WebMapManager] Erro ao ocultar janela do Edge: {e}")

    def resize(self):
        """Ajusta o tamanho do Edge para corresponder perfeitamente ao container."""
        if not self.edge_hwnd or not self._is_docked or not self.container:
            return
        try:
            w = self.container.winfo_width()
            h = self.container.winfo_height()
            if w > 50 and h > 50:
                win32gui.SetWindowPos(self.edge_hwnd, win32con.HWND_TOP, 0, 0, w, h, win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE)
        except Exception:
            pass

    def _launch_and_dock(self):
        edge_exe = get_edge_executable()
        if not edge_exe:
            log.error("[WebMapManager] Microsoft Edge não encontrado no sistema!")
            return

        cache_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RemoteXPTI" / "map_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        if not self.container_hwnd:
            try:
                self.container_hwnd = self.container.winfo_id()
            except Exception:
                pass
        target_parent_hwnd = self.container_hwnd
        if not target_parent_hwnd:
            log.error("[WebMapManager] Container HWND não disponível para acoplamento.")
            return

        try:
            crect = win32gui.GetClientRect(target_parent_hwnd)
            w = max(400, crect[2])
            h = max(300, crect[3])
        except Exception:
            w, h = 1100, 700

        log.info(f"[WebMapManager] Iniciando Edge ({edge_exe}) para container HWND={target_parent_hwnd} ({w}x{h})...")

        # Inicia o Edge fora da tela (-10000, -10000) para NUNCA piscar ou mostrar '127.0.0.1_/' para o cliente
        cmd = [
            edge_exe,
            f"--app=http://127.0.0.1:{self.server.port}",
            f"--user-data-dir={str(cache_dir)}",
            "--no-first-run",
            "--no-default-browser-check",
            "--proxy-bypass-list=<-loopback>;127.0.0.1;localhost",
            "--disable-extensions",
            "--disable-component-update",
            "--disable-sync",
            "--disable-features=Translate",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-networking",
            "--window-position=-10000,-10000",
            f"--window-size={w},{h}"
        ]

        creation_flags = 0
        self.edge_proc = subprocess.Popen(cmd, creationflags=creation_flags)
        log.info(f"[WebMapManager] Processo Edge instanciado com PID={self.edge_proc.pid}")

        def find_and_dock_thread(parent_hwnd, initial_w, initial_h):
            found_hwnd = None
            try:
                for attempt in range(70):
                    time.sleep(0.08)

                    def enum_cb(h, _):
                        nonlocal found_hwnd
                        cname = win32gui.GetClassName(h)
                        if "Chrome_WidgetWin_1" in cname:
                            try:
                                _, pid = win32process.GetWindowThreadProcessId(h)
                                title = win32gui.GetWindowText(h)
                                style = win32gui.GetWindowLong(h, win32con.GWL_STYLE)
                                rect = win32gui.GetWindowRect(h)
                                rw = rect[2] - rect[0]
                                rh = rect[3] - rect[1]

                                is_our_pid = (self.edge_proc and pid == self.edge_proc.pid)
                                has_title = "127.0.0.1" in title or "RemoteXPTI" in title or f"{self.server.port}" in title
                                has_caption = (style & win32con.WS_CAPTION) != 0
                                has_size = rw > 200 and rh > 200

                                # Identifica a janela de aplicação real (com caption e tamanho de app)
                                if (is_our_pid or has_title) and has_caption and has_size:
                                    found_hwnd = h
                            except Exception:
                                pass
                    win32gui.EnumWindows(enum_cb, None)
                    if found_hwnd:
                        break

                if found_hwnd:
                    self.edge_hwnd = found_hwnd
                    log.info(f"[WebMapManager] Janela do Edge localizada com sucesso: HWND={found_hwnd}")

                    # Oculta imediatamente enquanto estilizamos para nunca piscar como popup
                    win32gui.ShowWindow(found_hwnd, win32con.SW_HIDE)

                    # Remove completamente todos os estilos de popup, barra de título e botões _ [] X
                    old_style = win32gui.GetWindowLong(found_hwnd, win32con.GWL_STYLE)
                    new_style = (old_style & ~win32con.WS_POPUP & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME & ~win32con.WS_MINIMIZEBOX & ~win32con.WS_MAXIMIZEBOX & ~win32con.WS_SYSMENU) | win32con.WS_CHILD | win32con.WS_CLIPCHILDREN | win32con.WS_CLIPSIBLINGS
                    win32gui.SetWindowLong(found_hwnd, win32con.GWL_STYLE, new_style)

                    # Remove estilos estendidos de aplicativo e bordas de diálogo
                    old_ex = win32gui.GetWindowLong(found_hwnd, win32con.GWL_EXSTYLE)
                    new_ex = (old_ex & ~win32con.WS_EX_APPWINDOW & ~win32con.WS_EX_WINDOWEDGE & ~win32con.WS_EX_DLGMODALFRAME) | win32con.WS_EX_CONTROLPARENT
                    win32gui.SetWindowLong(found_hwnd, win32con.GWL_EXSTYLE, new_ex)

                    # Acopla como janela filha inseparável do container Tkinter
                    win32gui.SetParent(found_hwnd, parent_hwnd)

                    try:
                        crect = win32gui.GetClientRect(parent_hwnd)
                        final_w = max(crect[2], initial_w)
                        final_h = max(crect[3], initial_h)
                    except Exception:
                        final_w, final_h = initial_w, initial_h

                    # Aplica forçadamente SWP_FRAMECHANGED para o DWM destruir fisicamente a barra de título e botões
                    win32gui.SetWindowPos(
                        found_hwnd, win32con.HWND_TOP, 0, 0, final_w, final_h,
                        win32con.SWP_FRAMECHANGED | (win32con.SWP_SHOWWINDOW if self._is_visible else win32con.SWP_HIDEWINDOW)
                    )
                    self._is_docked = True
                    log.info(f"[WebMapManager] Edge acoplado com sucesso sem bordas no container HWND={parent_hwnd} ({final_w}x{final_h})")

                    if self._is_visible:
                        self.show()
                else:
                    log.error(f"[WebMapManager] Janela do Edge não foi localizada após 70 tentativas. proc.poll={self.edge_proc.poll() if self.edge_proc else None}")
            except Exception as ex:
                log.error(f"[WebMapManager] Erro no docking do Edge: {ex}", exc_info=True)

        threading.Thread(target=find_and_dock_thread, args=(target_parent_hwnd, w, h), daemon=True).start()

    def shutdown(self):
        """Fecha o processo e o servidor na saída do RemoteXPTI."""
        log.info("[WebMapManager] shutdown() acionado - Encerrando Edge e servidor web...")
        self.hide()
        if self.edge_hwnd:
            try:
                win32gui.PostMessage(self.edge_hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self.edge_proc:
            try:
                creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.edge_proc.pid)], capture_output=True, creationflags=creation_flags)
            except Exception:
                try:
                    self.edge_proc.terminate()
                except Exception:
                    pass
            self.edge_proc = None
        cache_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RemoteXPTI" / "map_cache"
        cleanup_orphaned_edge_processes(cache_dir)
        self.server.stop()
        log.info("[WebMapManager] Subsistema do mapa finalizado com sucesso.")
