import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Compass } from 'lucide-react';

interface Server {
  id: string;
  name: string;
  host: string;
  port: number;
  latitude?: number;
  longitude?: number;
  group?: string;
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

  // Inicialização do Mapa
  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      // Cria o mapa centrado em Santa Catarina
      const map = L.map(mapContainerRef.current, {
        center: [-27.2423, -50.2189],
        zoom: 8,
        zoomControl: true,
      });

      // Camada de Satélite Real Google Híbrido (Com relevo e nomes de ruas oficiais)
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

      // Invalida tamanho após layout estabilizar
      setTimeout(() => {
        map.invalidateSize();
      }, 150);
    }

    const map = mapInstanceRef.current;
    if (map) {
      map.invalidateSize();
    }
  }, []);

  // Troca de Camadas de Mapa
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

  // Atualização dos Marcadores dos Servidores
  useEffect(() => {
    const map = mapInstanceRef.current;
    const markersGroup = markersLayerRef.current;
    if (!map || !markersGroup) return;

    markersGroup.clearLayers();

    const validServers = servers.filter((s) => s.latitude && s.longitude);

    validServers.forEach((s) => {
      const customIcon = L.divIcon({
        className: 'custom-map-marker',
        html: `
          <div style="
            position: relative;
            width: 18px;
            height: 18px;
            display: flex;
            align-items: center;
            justify-content: center;
          ">
            <div style="
              position: absolute;
              width: 100%;
              height: 100%;
              border-radius: 50%;
              background: #38bdf8;
              opacity: 0.4;
              animation: ping 2s cubic-bezier(0, 0, 0.2, 1) infinite;
            "></div>
            <div style="
              width: 12px;
              height: 12px;
              border-radius: 50%;
              background: #0284c7;
              border: 2px solid #ffffff;
              box-shadow: 0 0 8px rgba(2, 132, 199, 0.9);
            "></div>
          </div>
        `,
        iconSize: [18, 18],
        iconAnchor: [9, 9],
      });

      const marker = L.marker([s.latitude!, s.longitude!], { icon: customIcon }).addTo(markersGroup);

      marker.bindPopup(`
        <div style="
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          min-width: 180px;
          color: #f1f5f9;
          background: #161b22;
          padding: 8px;
          border-radius: 8px;
        ">
          <div style="font-size: 10px; font-weight: bold; color: #38bdf8; text-transform: uppercase; margin-bottom: 2px;">
            ${s.group || 'Geral'}
          </div>
          <h4 style="margin: 0 0 4px 0; font-weight: bold; font-size: 13px; color: #ffffff;">${s.name}</h4>
          <p style="margin: 0 0 8px 0; font-size: 11px; font-family: monospace; color: #94a3b8;">${s.host}:${s.port || 3389}</p>
          <button id="btn-map-rdp-${s.id}" style="
            background: #2563eb;
            color: #ffffff;
            border: none;
            padding: 6px 12px;
            font-size: 11px;
            font-weight: bold;
            border-radius: 6px;
            cursor: pointer;
            width: 100%;
            transition: background 0.15s;
          ">Conectar RDP</button>
        </div>
      `, {
        className: 'custom-dark-popup',
      });

      marker.on('popupopen', () => {
        const btn = document.getElementById(`btn-map-rdp-${s.id}`);
        if (btn) {
          btn.onclick = () => onConnect(s.id);
        }
      });
    });
  }, [servers, onConnect]);

  const handleCenterSC = () => {
    if (mapInstanceRef.current) {
      mapInstanceRef.current.flyTo([-27.2423, -50.2189], 8, { duration: 1.2 });
    }
  };

  return (
    <div className="flex-1 relative w-full h-full bg-[#0d1117] overflow-hidden select-none">
      {/* Container do Leaflet */}
      <div ref={mapContainerRef} className="w-full h-full z-0" />

      {/* Controles Flutuantes Superiores */}
      <div className="absolute top-4 right-4 z-10 flex items-center gap-2">
        {/* Seletor de Camada */}
        <div className="bg-[#161b22]/90 backdrop-blur-md border border-[#30363d] rounded-xl p-1 shadow-xl flex items-center gap-1">
          <button
            onClick={() => setActiveLayer('satellite')}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
              activeLayer === 'satellite'
                ? 'bg-blue-600 text-white shadow'
                : 'text-slate-300 hover:text-white hover:bg-[#21262d]'
            }`}
          >
            🛰️ Satélite
          </button>
          <button
            onClick={() => setActiveLayer('roads')}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
              activeLayer === 'roads'
                ? 'bg-blue-600 text-white shadow'
                : 'text-slate-300 hover:text-white hover:bg-[#21262d]'
            }`}
          >
            🗺️ Ruas
          </button>
          <button
            onClick={() => setActiveLayer('osm')}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
              activeLayer === 'osm'
                ? 'bg-blue-600 text-white shadow'
                : 'text-slate-300 hover:text-white hover:bg-[#21262d]'
            }`}
          >
            🌐 OpenStreetMap
          </button>
        </div>

        {/* Botão de Centralizar Santa Catarina (Bússola) */}
        <button
          onClick={handleCenterSC}
          title="Centralizar em Santa Catarina"
          className="p-2 bg-[#161b22]/90 backdrop-blur-md hover:bg-[#21262d] border border-[#30363d] text-white rounded-xl shadow-xl transition-transform active:scale-95 flex items-center justify-center"
        >
          <Compass className="w-5 h-5 text-sky-400" />
        </button>
      </div>

      {/* Estilos Globais para o Popup Dark do Leaflet */}
      <style>{`
        .custom-dark-popup .leaflet-popup-content-wrapper {
          background: #161b22 !important;
          border: 1px solid #30363d !important;
          border-radius: 10px !important;
          box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5) !important;
          padding: 2px !important;
        }
        .custom-dark-popup .leaflet-popup-tip {
          background: #161b22 !important;
          border: 1px solid #30363d !important;
        }
        @keyframes ping {
          75%, 100% {
            transform: scale(2);
            opacity: 0;
          }
        }
      `}</style>
    </div>
  );
};
