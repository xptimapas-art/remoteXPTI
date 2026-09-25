import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Layers, X } from 'lucide-react';

interface Server {
  id: string;
  name: string;
  host: string;
  port: number;
  latitude?: number;
  longitude?: number;
  group?: string;
  username?: string;
}

interface Incident {
  id: string;
  name: string;
  host: string;
  port: number;
  offline_since: number;
  duration_seconds: number;
  latitude?: number;
  longitude?: number;
}

interface MapViewProps {
  servers: Server[];
  onConnect: (serverId: string) => void;
}

export const MapView: React.FC<MapViewProps> = ({ servers, onConnect }) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const currentTileLayerRef = useRef<L.TileLayer | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);

  const [activeLayer, setActiveLayer] = useState<'satellite' | 'roads' | 'osm'>('satellite');
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [isTrayOpen, setIsTrayOpen] = useState(false);
  const [selectedServer, setSelectedServer] = useState<Server | null>(null);

  // Formata duração do downtime exatamente como na referência: 14d 22h, 10d 7h
  const formatLossDuration = (sec: number) => {
    sec = Math.max(0, Math.floor(sec));
    if (sec < 60) return `${sec}s`;
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    if (m < 60) return `${m}m ${s < 10 ? '0' : ''}${s}s`;
    const h = Math.floor(m / 60);
    const remM = m % 60;
    if (h < 24) return `${h}h ${remM < 10 ? '0' : ''}${remM}m`;
    const d = Math.floor(h / 24);
    const remH = h % 24;
    return `${d}d ${remH}h`;
  };

  // Carrega incidentes da API local
  const loadIncidents = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8765/api/incidents');
      if (res.ok) {
        const data = await res.json();
        setIncidents(data);
      }
    } catch (e) {
      console.warn('Erro ao carregar incidentes:', e);
    }
  };

  useEffect(() => {
    loadIncidents();
    const interval = setInterval(loadIncidents, 10000);
    return () => clearInterval(interval);
  }, []);

  // Inicialização do Mapa
  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      const map = L.map(mapContainerRef.current, {
        center: [-27.2423, -50.2189],
        zoom: 8,
        zoomControl: false, // Usaremos nosso controle estilizado idêntico
      });

      // Satélite Real Oficial Google Híbrido
      const satLayer = L.tileLayer(
        'https://mt{s}.google.com/vt/lyrs=y&hl=pt-BR&x={x}&y={y}&z={z}&s=Ga',
        {
          subdomains: ['0', '1', '2', '3'],
          maxZoom: 20,
          attribution: 'Google Satélite Híbrido',
        }
      ).addTo(map);

      currentTileLayerRef.current = satLayer;
      markersLayerRef.current = L.layerGroup().addTo(map);
      mapInstanceRef.current = map;

      setTimeout(() => {
        map.invalidateSize();
      }, 150);
    }

    const map = mapInstanceRef.current;
    if (map) {
      map.invalidateSize();
    }
  }, []);

  // Troca de Camadas
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (currentTileLayerRef.current) {
      map.removeLayer(currentTileLayerRef.current);
    }

    let newLayer: L.TileLayer;
    if (activeLayer === 'satellite') {
      newLayer = L.tileLayer(
        'https://mt{s}.google.com/vt/lyrs=y&hl=pt-BR&x={x}&y={y}&z={z}&s=Ga',
        {
          subdomains: ['0', '1', '2', '3'],
          maxZoom: 20,
          attribution: 'Google Satélite Híbrido',
        }
      );
    } else if (activeLayer === 'roads') {
      newLayer = L.tileLayer(
        'https://mt{s}.google.com/vt/lyrs=m&hl=pt-BR&x={x}&y={y}&z={z}&s=Ga',
        {
          subdomains: ['0', '1', '2', '3'],
          maxZoom: 20,
          attribution: 'Google Maps',
        }
      );
    } else {
      newLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: 'OpenStreetMap',
      });
    }

    newLayer.addTo(map);
    currentTileLayerRef.current = newLayer;
  }, [activeLayer]);

  // Marcadores em Alfinete de Alta Definição com Halo Pulsante
  useEffect(() => {
    const map = mapInstanceRef.current;
    const markersGroup = markersLayerRef.current;
    if (!map || !markersGroup) return;

    markersGroup.clearLayers();

    const incidentIds = new Set(incidents.map((inc) => inc.id));
    const validServers = servers.filter((s) => s.latitude && s.longitude);

    validServers.forEach((s) => {
      const isIncident = incidentIds.has(s.id);
      const dotColor = isIncident ? '#f04438' : '#2ebd59';
      const haloColor = isIncident ? 'rgba(240, 68, 56, 0.45)' : 'rgba(46, 189, 89, 0.45)';
      const pinBg = isIncident ? '#261618' : '#142219';

      const customIcon = L.divIcon({
        className: 'leaflet-pin-container',
        html: `
          <div class="pin-marker ${isIncident ? 'pin-offline' : 'pin-online'}">
            <svg width="30" height="38" viewBox="0 0 30 38" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path class="pin-base" d="M15 1.5C7.544 1.5 1.5 7.544 1.5 15C1.5 24.8 13.9 36.6 14.5 37.1C14.8 37.4 15.2 37.4 15.5 37.1C16.1 36.6 28.5 24.8 28.5 15C28.5 7.544 22.456 1.5 15 1.5Z" fill="${pinBg}" stroke="#ffffff" stroke-width="2"/>
              <circle class="pin-halo" cx="15" cy="15" r="7.5" fill="${haloColor}"/>
              <circle class="pin-dot" cx="15" cy="15" r="5" fill="${dotColor}" stroke="#ffffff" stroke-width="1.2"/>
            </svg>
          </div>
        `,
        iconSize: [30, 38],
        iconAnchor: [15, 37],
        tooltipAnchor: [0, -38],
      });

      const marker = L.marker([s.latitude!, s.longitude!], { icon: customIcon }).addTo(markersGroup);

      marker.bindTooltip(s.name, {
        permanent: false,
        direction: 'top',
        className: 'leaflet-tooltip-dark',
        offset: [0, -38],
      });

      marker.on('click', () => {
        setSelectedServer(s);
      });
    });
  }, [servers, incidents]);

  const handleCenterSC = () => {
    if (mapInstanceRef.current) {
      mapInstanceRef.current.flyTo([-27.2423, -50.2189], 8, { duration: 1.2 });
    }
  };

  const handleIncidentClick = (inc: Incident) => {
    if (inc.latitude && inc.longitude && mapInstanceRef.current) {
      mapInstanceRef.current.flyTo([inc.latitude, inc.longitude], 13, { duration: 1.0 });
    }
    const srv = servers.find((s) => s.id === inc.id) || {
      id: inc.id,
      name: inc.name,
      host: inc.host,
      port: inc.port,
      latitude: inc.latitude,
      longitude: inc.longitude,
    };
    setSelectedServer(srv);
  };

  const cycleLayer = () => {
    if (activeLayer === 'satellite') setActiveLayer('roads');
    else if (activeLayer === 'roads') setActiveLayer('osm');
    else setActiveLayer('satellite');
  };

  return (
    <div className="flex-1 relative w-full h-full bg-[#0d1117] overflow-hidden select-none">
      {/* Container Leaflet */}
      <div ref={mapContainerRef} className="w-full h-full z-0" />

      {/* 1. TOP HUD CONTAINER (CANTO SUPERIOR ESQUERDO) - IDÊNTICO À REFERÊNCIA */}
      <div className="absolute top-3.5 left-3.5 z-20 flex flex-col gap-2">
        <div className="bg-[#12141a]/90 backdrop-blur-md border border-white/15 rounded-xl px-3 py-2 shadow-2xl flex items-center gap-3 text-xs text-white">
          <div className="font-bold flex items-center gap-1.5">
            <span>🗺️</span>
            <span>Mapa</span>
          </div>

          {/* Layer Pills */}
          <div className="flex items-center bg-[#14161d] border border-[#363a4a] rounded-md p-0.5 gap-0.5">
            <button
              onClick={() => setActiveLayer('satellite')}
              className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all flex items-center gap-1 ${
                activeLayer === 'satellite'
                  ? 'bg-[#0066cc] text-white shadow-md'
                  : 'text-[#9aa0b2] hover:text-white'
              }`}
            >
              <span>🛰️</span>
              <span>Satélite</span>
            </button>
            <button
              onClick={() => setActiveLayer('roads')}
              className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all flex items-center gap-1 ${
                activeLayer === 'roads'
                  ? 'bg-[#0066cc] text-white shadow-md'
                  : 'text-[#9aa0b2] hover:text-white'
              }`}
            >
              <span>🗺️</span>
              <span>Padrão</span>
            </button>
          </div>

          {/* Botão Incidentes com Contador e Pulso */}
          <button
            onClick={() => setIsTrayOpen(!isTrayOpen)}
            className={`px-2.5 py-1 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all border ${
              incidents.length > 0
                ? 'bg-rose-950/60 border-rose-800 text-rose-300 hover:bg-rose-900/80 shadow-[0_0_10px_rgba(244,63,94,0.3)]'
                : 'bg-[#21262d] border-[#30363d] text-slate-300'
            }`}
          >
            <span>🚨</span>
            <span>Incidentes</span>
            <span className="px-1.5 py-0.2 rounded-full bg-rose-600 text-white font-mono text-[10px]">
              {incidents.length}
            </span>
          </button>

          <span className="text-[11px] text-[#8e92a0]">
            {servers.filter((s) => s.latitude && s.longitude).length} servidores no mapa
          </span>
        </div>

        {/* 2. BANDEJA RETRÁTIL DE INCIDENTES (LOSS / DOWNTIME) */}
        {isTrayOpen && (
          <div className="w-[360px] bg-[#161318]/95 backdrop-blur-md border border-rose-900/60 rounded-xl shadow-2xl overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150">
            <div className="p-3 bg-rose-950/40 border-b border-rose-900/40 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-amber-400 font-bold text-xs">⚠️</span>
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-rose-300">
                  Servidores em Falha / Loss
                </span>
                <span className="px-1.5 py-0.2 rounded-full bg-rose-600 text-white font-mono text-[10px] font-bold">
                  {incidents.length}
                </span>
              </div>
              <button
                onClick={() => setIsTrayOpen(false)}
                className="text-slate-400 hover:text-white p-1 rounded transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="max-h-64 overflow-y-auto p-2 space-y-1">
              {incidents.length === 0 ? (
                <div className="text-center py-4 text-xs text-slate-400 italic">
                  ✨ Todos os servidores operando normalmente (0 em loss)
                </div>
              ) : (
                incidents.map((inc) => (
                  <div
                    key={inc.id}
                    onClick={() => handleIncidentClick(inc)}
                    className="flex items-center justify-between p-2 rounded-lg bg-white/[0.03] hover:bg-rose-900/25 border border-white/[0.06] hover:border-rose-700/50 cursor-pointer transition-all group"
                  >
                    <div className="flex items-center gap-2 min-w-0 pr-2">
                      <span className="w-2 h-2 rounded-full bg-rose-500 shadow-[0_0_6px_#f43f5e] animate-pulse flex-shrink-0" />
                      <span className="text-xs font-semibold text-slate-100 truncate group-hover:text-white">
                        {inc.name}
                      </span>
                    </div>
                    <span className="text-[11px] font-mono font-bold text-rose-400 bg-rose-950/80 border border-rose-800/60 px-2 py-0.5 rounded flex-shrink-0">
                      {formatLossDuration(inc.duration_seconds)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* 3. RIGHT CONTROLS STACK (CANTO SUPERIOR DIREITO) - IDÊNTICO À SEGUNDA IMAGEM */}
      <div className="absolute top-3.5 right-3.5 z-20 flex flex-col items-center gap-2">
        {/* Bússola Circular Estilo Google Maps */}
        <button
          onClick={handleCenterSC}
          title="Centralizar em Santa Catarina (Bússola / Norte)"
          className="w-9 h-9 rounded-full bg-[#12141a]/90 backdrop-blur-md border border-white/20 shadow-xl flex items-center justify-center hover:bg-[#242936] transition-transform active:scale-95 group"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="12" r="10.5" stroke="rgba(255,255,255,0.3)" strokeWidth="1.2" />
            <polygon points="12,3.5 15.5,12 8.5,12" fill="#ef4444" className="group-hover:filter drop-shadow-[0_0_6px_rgba(239,68,68,0.8)]" />
            <polygon points="12,20.5 15.5,12 8.5,12" fill="#cbd5e1" />
          </svg>
        </button>

        {/* Zoom Pill (+ e -) */}
        <div className="flex flex-col bg-[#12141a]/90 backdrop-blur-md border border-white/20 rounded-xl overflow-hidden shadow-xl">
          <button
            onClick={() => mapInstanceRef.current?.zoomIn()}
            className="w-9 h-9 flex items-center justify-center text-white hover:bg-[#242936] text-lg font-bold transition-colors"
          >
            +
          </button>
          <div className="w-full h-px bg-white/10" />
          <button
            onClick={() => mapInstanceRef.current?.zoomOut()}
            className="w-9 h-9 flex items-center justify-center text-white hover:bg-[#242936] text-lg font-bold transition-colors"
          >
            −
          </button>
        </div>

        {/* Botão de Camadas Abaixo do Zoom */}
        <button
          onClick={cycleLayer}
          title="Alternar Camada de Mapa"
          className="w-9 h-9 rounded-xl bg-[#12141a]/90 backdrop-blur-md border border-white/20 shadow-xl flex items-center justify-center text-white hover:bg-[#242936] transition-transform active:scale-95"
        >
          <Layers className="w-5 h-5 text-slate-200" />
        </button>
      </div>

      {/* 4. BOTTOM FLOATING CARD (QUANDO UM SERVIDOR É CLICADO) */}
      {selectedServer && (
        <div className="absolute bottom-5 left-1/2 -translate-x-1/2 z-30 w-[min(680px,94%)] bg-[#14161c]/95 backdrop-blur-md border border-white/20 rounded-xl p-4 shadow-2xl text-white animate-in slide-in-from-bottom-4 duration-200">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2.5">
              <h3 className="font-bold text-base">{selectedServer.name}</h3>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 font-semibold">
                🟢 Online (RDP Disponível)
              </span>
            </div>
            <button
              onClick={() => setSelectedServer(null)}
              className="text-slate-400 hover:text-white p-1 rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex items-center justify-between text-xs text-slate-300 pt-2 border-t border-white/10">
            <div className="flex items-center gap-4">
              <span>🌐 Host: <span className="font-mono text-white">{selectedServer.host}:{selectedServer.port || 3389}</span></span>
              <span>📁 Grupo: <span className="text-white">{selectedServer.group || 'Geral'}</span></span>
              <span>👤 Usuário: <span className="text-white">{selectedServer.username || 'Padrão'}</span></span>
            </div>

            <button
              onClick={() => onConnect(selectedServer.id)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-bold flex items-center gap-2 shadow-lg transition-transform active:scale-95"
            >
              <span>🚀</span>
              <span>Conectar Agora (RDP)</span>
            </button>
          </div>
        </div>
      )}

      {/* Estilos Globais do Leaflet (Alfinetes e Tooltips) */}
      <style>{`
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
      `}</style>
    </div>
  );
};
