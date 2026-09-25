import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

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

  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      // Centraliza em Santa Catarina
      const map = L.map(mapContainerRef.current, {
        center: [-27.2423, -50.2189],
        zoom: 8,
        zoomControl: true,
      });

      // CartoDB Dark Matter tiles (Dark Mode moderno para NOCs)
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19,
      }).addTo(map);

      mapInstanceRef.current = map;
    }

    const map = mapInstanceRef.current;

    // Adiciona Marcadores dos Servidores
    const validServers = servers.filter((s) => s.latitude && s.longitude);

    validServers.forEach((s) => {
      const customIcon = L.divIcon({
        className: 'custom-map-marker',
        html: `
          <div style="
            background: #2563eb;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: 2px solid #ffffff;
            box-shadow: 0 0 10px #3b82f6;
          "></div>
        `,
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      });

      const marker = L.marker([s.latitude!, s.longitude!], { icon: customIcon }).addTo(map);

      marker.bindPopup(`
        <div style="font-family: sans-serif; padding: 4px; color: #1e293b;">
          <h4 style="margin: 0 0 4px 0; font-weight: bold; font-size: 13px;">${s.name}</h4>
          <p style="margin: 0 0 6px 0; font-size: 11px; color: #64748b;">${s.host}:${s.port || 3389}</p>
          <button id="btn-conn-${s.id}" style="
            background: #2563eb;
            color: #ffffff;
            border: none;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: bold;
            border-radius: 4px;
            cursor: pointer;
            width: 100%;
          ">Conectar RDP</button>
        </div>
      `);

      marker.on('popupopen', () => {
        const btn = document.getElementById(`btn-conn-${s.id}`);
        if (btn) {
          btn.onclick = () => onConnect(s.id);
        }
      });
    });

    return () => {
      // Keep map instance alive for smooth tab switching
    };
  }, [servers, onConnect]);

  return (
    <div className="flex-1 relative w-full h-full bg-[#0d1117] overflow-hidden">
      <div ref={mapContainerRef} className="w-full h-full" />
    </div>
  );
};
