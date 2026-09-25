import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {
  Layers,
  X,
  AlertTriangle,
  RefreshCw,
  Play,
  MapPin,
  Search,
  CheckCircle2,
  Clock,
} from 'lucide-react';
import type { ONUItem } from './AjinView';

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
  group?: string;
  username?: string;
  offline_since: number;
  offline_since_formatted?: string;
  duration_seconds: number;
  latitude?: number;
  longitude?: number;
}

interface MapViewProps {
  servers: Server[];
  onus?: ONUItem[];
  onConnect: (serverId: string) => void;
  targetLocation?: { lat: number; lon: number; zoom?: number; id?: string; itemType?: 'server' | 'onu'; onu?: ONUItem } | null;
  onEditOnu?: (onu: ONUItem) => void;
  onTargetLocationHandled?: () => void;
}

export const MapView: React.FC<MapViewProps> = ({
  servers,
  onus = [],
  onConnect,
  targetLocation,
  onEditOnu,
  onTargetLocationHandled,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const currentTileLayerRef = useRef<L.TileLayer | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);

  const [activeLayer, setActiveLayer] = useState<'satellite' | 'roads' | 'osm'>('satellite');
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [isTrayOpen, setIsTrayOpen] = useState(false);
  const [showServers, setShowServers] = useState(true);
  const [showOnus, setShowOnus] = useState(true);
  const [selectedServer, setSelectedServer] = useState<Server | null>(null);
  const [selectedOnu, setSelectedOnu] = useState<ONUItem | null>(null);
  const [incidentSearch, setIncidentSearch] = useState('');
  const [isRetestingAll, setIsRetestingAll] = useState(false);
  const [testingIncidentId, setTestingIncidentId] = useState<string | null>(null);

  const lastTargetKeyRef = useRef<string | null>(
    targetLocation ? `${targetLocation.lat}_${targetLocation.lon}_${targetLocation.itemType || ''}_${targetLocation.id || ''}` : null
  );

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

  const handleRetestAll = async () => {
    setIsRetestingAll(true);
    try {
      await fetch('http://127.0.0.1:8765/api/servers/check_status', { method: 'POST' });
      setTimeout(async () => {
        await loadIncidents();
        setIsRetestingAll(false);
      }, 1500);
    } catch (e) {
      console.warn('Erro ao retestar servidores:', e);
      setIsRetestingAll(false);
    }
  };

  const handleRetestSingle = async (e: React.MouseEvent, serverId: string) => {
    e.stopPropagation();
    setTestingIncidentId(serverId);
    try {
      await fetch(`http://127.0.0.1:8765/api/servers/${serverId}/check`, { method: 'POST' });
      await loadIncidents();
    } catch (e) {
      console.warn('Erro ao testar servidor individual:', e);
    } finally {
      setTestingIncidentId(null);
    }
  };

  const filteredIncidents = incidents.filter((inc) => {
    if (!incidentSearch.trim()) return true;
    const term = incidentSearch.toLowerCase().trim();
    const nameMatch = inc.name.toLowerCase().includes(term);
    const hostMatch = inc.host.toLowerCase().includes(term);
    const groupMatch = (inc.group || '').toLowerCase().includes(term);
    return nameMatch || hostMatch || groupMatch;
  });

  useEffect(() => {
    loadIncidents();
    const interval = setInterval(loadIncidents, 10000);
    return () => clearInterval(interval);
  }, []);

  // Inicialização do Mapa
  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      // Se houver localização alvo já solicitada ao abrir o mapa, inicializa já centrado nela
      const initialCenter: [number, number] = targetLocation
        ? [Number(targetLocation.lat), Number(targetLocation.lon)]
        : [-27.2423, -50.2189];
      const initialZoom = targetLocation ? (targetLocation.zoom || 16) : 8;

      const map = L.map(mapContainerRef.current, {
        center: initialCenter,
        zoom: initialZoom,
        zoomControl: false,
      });

      // Clique em área vazia do mapa fecha cards abertos e libera seleção
      map.on('click', () => {
        setSelectedServer(null);
        setSelectedOnu(null);
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

      if (targetLocation?.onu) {
        setSelectedOnu(targetLocation.onu);
        setSelectedServer(null);
      }

      setTimeout(() => {
        if (mapInstanceRef.current) {
          mapInstanceRef.current.invalidateSize();
        }
      }, 150);
    }

    // Cleanup completo do Leaflet ao desmontar a aba
    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
        currentTileLayerRef.current = null;
        markersLayerRef.current = null;
      }
    };
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

  // Navegação e foco suave quando uma localização alvo é solicitada
  useEffect(() => {
    if (!targetLocation || !mapInstanceRef.current) return;
    const targetKey = `${targetLocation.lat}_${targetLocation.lon}_${targetLocation.itemType || ''}_${targetLocation.id || ''}`;
    if (lastTargetKeyRef.current === targetKey) return;
    lastTargetKeyRef.current = targetKey;

    const map = mapInstanceRef.current;
    map.stop();
    map.flyTo([Number(targetLocation.lat), Number(targetLocation.lon)], targetLocation.zoom || 16, {
      duration: 1.0,
    });

    if (targetLocation.onu) {
      setSelectedOnu(targetLocation.onu);
      setSelectedServer(null);
    } else if (targetLocation.itemType === 'server') {
      const srv = servers.find((s) => s.id === targetLocation.id);
      if (srv) {
        setSelectedServer(srv);
        setSelectedOnu(null);
      }
    }

    onTargetLocationHandled?.();
  }, [targetLocation]);

  // Marcadores em Alfinete de Alta Definição com Halo Pulsante (Servidores e ONUs)
  useEffect(() => {
    const map = mapInstanceRef.current;
    const markersGroup = markersLayerRef.current;
    if (!map || !markersGroup) return;

    markersGroup.clearLayers();

    // 1. Plotar Servidores
    if (showServers) {
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

        const marker = L.marker([Number(s.latitude), Number(s.longitude)], { icon: customIcon }).addTo(markersGroup);

        marker.bindTooltip(`🖥️ <strong>${s.name}</strong><br/><span style="color:#94a3b8">${s.host}:${s.port || 3389}</span>`, {
          permanent: false,
          direction: 'top',
          className: 'leaflet-tooltip-dark',
          offset: [0, -38],
        });

        marker.on('click', () => {
          setSelectedServer(s);
          setSelectedOnu(null);
        });
      });
    }

    // 2. Plotar ONUs da Ajin
    if (showOnus && onus) {
      const validOnus = onus.filter((o) => o.latitude && o.longitude);

      validOnus.forEach((o) => {
        const isOnline = o.status === 'Online';
        const dotColor = isOnline ? '#22d3ee' : '#f43f5e';
        const haloColor = isOnline ? 'rgba(34, 211, 238, 0.45)' : 'rgba(244, 63, 94, 0.5)';
        const pinBg = isOnline ? '#09252c' : '#330e16';
        const borderColor = isOnline ? '#06b6d4' : '#f43f5e';

        const customIcon = L.divIcon({
          className: 'leaflet-pin-container',
          html: `
            <div class="pin-marker ${isOnline ? 'pin-onu-online' : 'pin-offline'}">
              <svg width="28" height="36" viewBox="0 0 30 38" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path class="pin-base" d="M15 1.5C7.544 1.5 1.5 7.544 1.5 15C1.5 24.8 13.9 36.6 14.5 37.1C14.8 37.4 15.2 37.4 15.5 37.1C16.1 36.6 28.5 24.8 28.5 15C28.5 7.544 22.456 1.5 15 1.5Z" fill="${pinBg}" stroke="${borderColor}" stroke-width="2.2"/>
                <circle class="pin-halo" cx="15" cy="15" r="7.5" fill="${haloColor}"/>
                <path d="M15 7L11 15H15L14 22L20 13H15L15 7Z" fill="${dotColor}"/>
              </svg>
            </div>
          `,
          iconSize: [28, 36],
          iconAnchor: [14, 35],
          tooltipAnchor: [0, -36],
        });

        const marker = L.marker([Number(o.latitude), Number(o.longitude)], { icon: customIcon }).addTo(markersGroup);

        const tooltipHtml = `⚡ <strong>${o.name || `Ponto ${o.id}`}</strong> (${o.status})<br/><span style="color:#94a3b8">${o.desc || o.port}</span>`;
        marker.bindTooltip(tooltipHtml, {
          permanent: false,
          direction: 'top',
          className: 'leaflet-tooltip-dark',
          offset: [0, -36],
        });

        marker.on('click', () => {
          setSelectedOnu(o);
          setSelectedServer(null);
        });
      });
    }
  }, [servers, incidents, onus, showServers, showOnus]);

  const handleCenterSC = () => {
    if (mapInstanceRef.current) {
      mapInstanceRef.current.stop();
      mapInstanceRef.current.flyTo([-27.2423, -50.2189], 8, { duration: 1.0 });
    }
    setSelectedServer(null);
    setSelectedOnu(null);
    lastTargetKeyRef.current = null;
    onTargetLocationHandled?.();
  };

  const handleIncidentClick = (inc: Incident) => {
    if (inc.latitude && inc.longitude && mapInstanceRef.current) {
      mapInstanceRef.current.stop();
      mapInstanceRef.current.flyTo([Number(inc.latitude), Number(inc.longitude)], 13, { duration: 1.0 });
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
    setSelectedOnu(null);
    lastTargetKeyRef.current = null;
    onTargetLocationHandled?.();
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

          {/* Layer Pills: Satélite / Padrão */}
          <div className="flex items-center bg-[#14161d] border border-[#363a4a] rounded-md p-0.5 gap-0.5">
            <button
              onClick={() => setActiveLayer('satellite')}
              className={`px-2 py-1 rounded text-[11px] font-bold transition-all flex items-center gap-1 cursor-pointer ${
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
              className={`px-2 py-1 rounded text-[11px] font-bold transition-all flex items-center gap-1 cursor-pointer ${
                activeLayer === 'roads'
                  ? 'bg-[#0066cc] text-white shadow-md'
                  : 'text-[#9aa0b2] hover:text-white'
              }`}
            >
              <span>🗺️</span>
              <span>Padrão</span>
            </button>
          </div>

          {/* Toggle Camada de Itens: Servidores & ONUs AJIN */}
          <div className="flex items-center bg-[#14161d] border border-[#363a4a] rounded-md p-0.5 gap-0.5">
            <button
              onClick={() => setShowServers(!showServers)}
              title="Exibir ou ocultar Servidores no mapa"
              className={`px-2 py-1 rounded text-[11px] font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                showServers
                  ? 'bg-blue-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>🖥️</span>
              <span>Servidores ({servers.filter((s) => s.latitude && s.longitude).length})</span>
            </button>
            <button
              onClick={() => setShowOnus(!showOnus)}
              title="Exibir ou ocultar ONUs da Ajin no mapa"
              className={`px-2 py-1 rounded text-[11px] font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                showOnus
                  ? 'bg-cyan-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>⚡</span>
              <span>ONUs AJIN ({onus ? onus.filter((o) => o.latitude && o.longitude).length : 0})</span>
            </button>
          </div>

          {/* Botão Incidentes com Contador e Pulso */}
          <button
            onClick={() => setIsTrayOpen(!isTrayOpen)}
            className={`px-2.5 py-1 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all border cursor-pointer ${
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
        </div>

        {/* 2. BANDEJA RETRÁTIL DE INCIDENTES (NOC COMMAND CENTER) */}
        {isTrayOpen && (
          <div className="w-[490px] max-w-[94vw] bg-[#11131a]/95 backdrop-blur-xl border border-rose-500/35 rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.85),0_0_25px_rgba(244,63,94,0.18)] overflow-hidden flex flex-col animate-in fade-in slide-in-from-top-2 duration-150">
            {/* Header da Central de Incidentes */}
            <div className="p-3.5 bg-gradient-to-r from-rose-950/60 via-[#1a141b]/80 to-rose-950/40 border-b border-rose-900/50 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="relative flex items-center justify-center w-8 h-8 rounded-xl bg-rose-500/15 border border-rose-500/40 shrink-0">
                  <span className="w-2 h-2 rounded-full bg-rose-500 shadow-[0_0_8px_#f43f5e] animate-ping absolute" />
                  <span className="w-2 h-2 rounded-full bg-rose-500 shadow-[0_0_8px_#f43f5e]" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-black uppercase tracking-wider text-rose-200">
                      Central de Incidentes RDP
                    </span>
                    <span className="px-1.5 py-0.2 rounded-full bg-rose-600 text-white font-mono text-[10px] font-extrabold shadow-[0_0_6px_#f43f5e]">
                      {incidents.length}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-400">
                    {incidents.length === 1
                      ? '1 servidor inacessível na porta 3389'
                      : `${incidents.length} servidores inacessíveis na porta 3389`}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={handleRetestAll}
                  disabled={isRetestingAll}
                  title="Retestar conectividade de todos os servidores agora"
                  className="px-2.5 py-1.5 rounded-lg bg-[#1f2432] hover:bg-[#2b3346] border border-white/10 text-slate-200 hover:text-white text-[11px] font-bold flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 text-cyan-400 ${isRetestingAll ? 'animate-spin' : ''}`} />
                  <span>{isRetestingAll ? 'Testando...' : 'Retestar Todos'}</span>
                </button>
                <button
                  onClick={() => setIsTrayOpen(false)}
                  className="w-7 h-7 rounded-lg bg-white/5 hover:bg-white/15 text-slate-400 hover:text-white flex items-center justify-center transition-colors cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Campo de Busca Rápida (quando houver mais de 2 incidentes) */}
            {incidents.length > 2 && (
              <div className="p-2.5 pb-1 border-b border-white/5 bg-[#0e1017]">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5 pointer-events-none" />
                  <input
                    type="text"
                    placeholder="Filtrar por nome, host ou grupo..."
                    value={incidentSearch}
                    onChange={(e) => setIncidentSearch(e.target.value)}
                    className="w-full bg-[#161822] border border-white/10 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500/50 transition-colors"
                  />
                </div>
              </div>
            )}

            {/* Lista Rolável de Cards de Servidores em Falha */}
            <div className="max-h-[380px] overflow-y-auto p-2.5 space-y-2">
              {incidents.length === 0 ? (
                <div className="text-center py-8 px-4">
                  <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mx-auto mb-2 text-emerald-400">
                    <CheckCircle2 className="w-6 h-6" />
                  </div>
                  <h4 className="text-xs font-bold text-emerald-300">Nenhum Incidente Ativo</h4>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Todos os servidores estão operando e respondendo normalmente via RDP.
                  </p>
                </div>
              ) : filteredIncidents.length === 0 ? (
                <div className="text-center py-6 text-xs text-slate-400 italic">
                  Nenhum servidor corresponde ao filtro &quot;{incidentSearch}&quot;
                </div>
              ) : (
                filteredIncidents.map((inc) => (
                  <div
                    key={inc.id}
                    onClick={() => handleIncidentClick(inc)}
                    className="p-3 rounded-xl bg-white/[0.03] hover:bg-rose-950/25 border border-white/[0.08] hover:border-rose-500/40 transition-all cursor-pointer group shadow-sm flex flex-col gap-2"
                  >
                    {/* Linha Superior: Nome, Grupo e Duração */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="w-2.5 h-2.5 rounded-full bg-rose-500 shadow-[0_0_8px_#f43f5e] shrink-0 animate-pulse" />
                        <span className="font-extrabold text-xs text-white group-hover:text-rose-200 transition-colors truncate">
                          {inc.name}
                        </span>
                        {inc.group && (
                          <span className="px-1.5 py-0.2 rounded bg-[#1e2330] border border-white/10 text-[10px] text-slate-400 font-medium shrink-0">
                            {inc.group}
                          </span>
                        )}
                      </div>

                      {/* Badge de Duração de Downtime */}
                      <span className="inline-flex items-center gap-1 font-mono font-bold text-[11px] text-rose-300 bg-rose-950/90 border border-rose-800/80 px-2 py-0.5 rounded-lg shrink-0 shadow-sm">
                        <Clock className="w-3 h-3 text-rose-400" />
                        {formatLossDuration(inc.duration_seconds)}
                      </span>
                    </div>

                    {/* Linha Central: Host:Porta e Data da Queda */}
                    <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-white/5">
                      <span className="font-mono text-slate-300 flex items-center gap-1">
                        <span className="text-slate-500">Host:</span> {inc.host}:{inc.port || 3389}
                      </span>
                      {inc.offline_since_formatted && (
                        <span className="text-[10px] text-slate-500">
                          Queda: {inc.offline_since_formatted}
                        </span>
                      )}
                    </div>

                    {/* Linha Inferior: Botões de Ação Rápida */}
                    <div className="flex items-center justify-between pt-1 gap-2">
                      <span className="text-[10px] text-rose-400/80 flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3 text-rose-400 shrink-0" />
                        <span>Porta RDP Inacessível</span>
                      </span>

                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={(e) => handleRetestSingle(e, inc.id)}
                          disabled={testingIncidentId === inc.id}
                          title="Testar porta 3389 deste servidor agora"
                          className="px-2 py-1 bg-[#1a1f2b] hover:bg-[#283144] border border-white/10 text-slate-300 rounded text-[10px] font-bold flex items-center gap-1 transition-colors cursor-pointer disabled:opacity-50"
                        >
                          <RefreshCw className={`w-2.5 h-2.5 text-cyan-400 ${testingIncidentId === inc.id ? 'animate-spin' : ''}`} />
                          <span>{testingIncidentId === inc.id ? '...' : 'Retestar'}</span>
                        </button>

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onConnect(inc.id);
                          }}
                          title="Tentar conexão direta via RDP (MSTSC)"
                          className="px-2.5 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-[10px] font-bold flex items-center gap-1 shadow-sm transition-colors cursor-pointer"
                        >
                          <Play className="w-2.5 h-2.5 fill-current" />
                          <span>Conectar</span>
                        </button>

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleIncidentClick(inc);
                          }}
                          title="Focar alfinete deste servidor no mapa"
                          className="px-2 py-1 bg-white/5 hover:bg-white/15 border border-white/10 text-slate-300 hover:text-white rounded text-[10px] font-bold flex items-center gap-1 transition-colors cursor-pointer"
                        >
                          <MapPin className="w-2.5 h-2.5 text-amber-400" />
                          <span>Focar</span>
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Rodapé Informativo da Central */}
            <div className="p-2.5 px-3.5 bg-[#0a0c12] border-t border-white/10 flex items-center justify-between text-[11px] text-slate-400 font-medium">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1 text-emerald-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  {servers.length - incidents.length} Online
                </span>
                <span className="text-slate-600">•</span>
                <span className="flex items-center gap-1 text-rose-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                  {incidents.length} em Loss
                </span>
              </div>
              <span className="text-[10px] text-slate-500 font-mono">
                Taxa de Operação: {servers.length > 0 ? (((servers.length - incidents.length) / servers.length) * 100).toFixed(0) : 100}%
              </span>
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

      {/* 5. BOTTOM FLOATING CARD (QUANDO UMA ONU É CLICADA) */}
      {selectedOnu && (
        <div className="absolute bottom-5 left-1/2 -translate-x-1/2 z-30 w-[min(720px,94%)] bg-[#10141d]/95 backdrop-blur-md border border-cyan-500/40 rounded-xl p-4 shadow-2xl text-white animate-in slide-in-from-bottom-4 duration-200">
          <div className="flex items-center justify-between mb-2.5">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="text-xl">⚡</span>
              <h3 className="font-extrabold text-base tracking-tight text-white">
                {selectedOnu.name || `Ponto ${selectedOnu.id}`}
              </h3>
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full border font-bold flex items-center gap-1.5 ${
                  selectedOnu.status === 'Online'
                    ? 'bg-cyan-950/80 text-cyan-300 border-cyan-700/60'
                    : 'bg-rose-950/80 text-rose-300 border-rose-700/60'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${selectedOnu.status === 'Online' ? 'bg-cyan-400 animate-pulse' : 'bg-rose-400'}`} />
                {selectedOnu.status === 'Online' ? 'Online' : 'Fora de Funcionamento'}
              </span>
              <span className="text-xs px-2 py-0.5 rounded bg-[#1f2430] border border-white/10 text-slate-300 font-mono">
                {selectedOnu.port} • ID #{selectedOnu.id}
              </span>
            </div>
            <button
              onClick={() => setSelectedOnu(null)}
              className="text-slate-400 hover:text-white p-1 rounded cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-slate-300 pt-2 border-t border-white/10">
            <div className="space-y-1">
              <div>📍 <span className="text-slate-400">Localização / Rua:</span> <strong className="text-white">{selectedOnu.desc || 'Não especificada'}</strong></div>
              <div>📟 <span className="text-slate-400">MAC / Serial:</span> <span className="font-mono text-cyan-300">{selectedOnu.serial || '-'}</span></div>
              <div>🏭 <span className="text-slate-400">Fabricante:</span> <span className="text-white">{selectedOnu.vendor || 'C-Data'}</span></div>
            </div>
            <div className="space-y-1">
              <div>📶 <span className="text-slate-400">Sinal / Uptime:</span> <span className="font-mono text-emerald-400">{selectedOnu.signal || selectedOnu.uptime || '-21.4 dBm'}</span></div>
              <div>🌐 <span className="text-slate-400">Coordenadas:</span> <span className="font-mono text-cyan-400">{Number(selectedOnu.latitude).toFixed(5)}, {Number(selectedOnu.longitude).toFixed(5)}</span></div>
              {selectedOnu.cameras && selectedOnu.cameras.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                  <span className="text-slate-400">📷 Câmeras:</span>
                  {selectedOnu.cameras.map((c: any, idx: number) => {
                    const ip = typeof c === 'string' ? (c.match(/ip=([0-9.]+)/) ? c.match(/ip=([0-9.]+)/)![1] : c) : (c.ip || '');
                    return (
                      <span key={idx} className="font-mono text-[10px] bg-blue-950/80 border border-blue-700/60 text-blue-300 px-1.5 py-0.2 rounded">
                        {ip}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {onEditOnu && (
            <div className="flex justify-end pt-2.5 mt-2 border-t border-white/10">
              <button
                onClick={() => onEditOnu(selectedOnu)}
                className="px-3 py-1.5 bg-[#1f2430] hover:bg-[#2b3242] border border-[#3e4659] text-slate-200 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
              >
                <span>✏️</span>
                <span>Editar Identificação / Coordenadas</span>
              </button>
            </div>
          )}
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
        .pin-onu-online .pin-halo {
          animation: pulse-halo-cyan 2.2s infinite ease-in-out;
        }
        @keyframes pulse-halo-cyan {
          0%, 100% { r: 6.5px; opacity: 0.35; }
          50% { r: 9px; opacity: 0.95; }
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
