import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import '../leaflet-setup';
import 'leaflet.markercluster';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import 'leaflet.markercluster/dist/MarkerCluster.Default.css';
import {
  Layers,
  X,
} from 'lucide-react';
import type { ONUItem } from './AjinView';
import { canShowOnMap, onuKey, onuStatus, pointName, signalValue } from './ajin';

function mapTooltip(title: string, detail: string) {
  const content = document.createElement('div');
  const heading = document.createElement('strong');
  heading.textContent = title;
  const description = document.createElement('span');
  description.style.color = '#94a3b8';
  description.textContent = detail;
  content.append(heading, document.createElement('br'), description);
  return content;
}

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

interface AjinMarkerEntry {
  marker: L.Marker & { ajinStatus?: string };
  row: ONUItem;
  iconKey: string;
  tooltipKey: string;
}

export const MapView: React.FC<MapViewProps> = React.memo(({
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
  const serverClusterGroupRef = useRef<L.MarkerClusterGroup | null>(null);
  const onuLayerRef = useRef<L.MarkerClusterGroup | null>(null);
  const serverMarkersMapRef = useRef<Map<string, L.Marker>>(new Map());
  const onuMarkersRef = useRef(new Map<string, AjinMarkerEntry>());

  const [activeLayer, setActiveLayer] = useState<'satellite' | 'roads' | 'osm'>('satellite');
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [isTrayOpen, setIsTrayOpen] = useState(true);
  const [showServers, setShowServers] = useState(true);
  const [showOnus, setShowOnus] = useState(true);
  const [selectedServer, setSelectedServer] = useState<Server | null>(null);
  const [selectedOnu, setSelectedOnu] = useState<ONUItem | null>(null);

  useEffect(() => {
    setSelectedOnu(previous => {
      if (!previous) return null;
      const current = onus.find(row => onuKey(row) === onuKey(previous));
      return showOnus && current && canShowOnMap(current) ? current : null;
    });
  }, [onus, showOnus]);

  const lastTargetKeyRef = useRef<string | null>(
    targetLocation ? `${targetLocation.lat}_${targetLocation.lon}_${targetLocation.itemType || ''}_${targetLocation.id || ''}` : null
  );

  // Formata duração do downtime exatamente como na referência: 15d 1h, 10d 9h
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
      const res = await fetch('/api/incidents');
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
    const handleIncidentsUpdated = () => loadIncidents();
    window.addEventListener('incidentsUpdated', handleIncidentsUpdated);
    return () => window.removeEventListener('incidentsUpdated', handleIncidentsUpdated);
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
          updateWhenZooming: false,
        }
      ).addTo(map);

      currentTileLayerRef.current = satLayer;
      // Agrupamento Inteligente de Servidores (MarkerCluster com Alertas de Status)
      const serverClusterGroup = L.markerClusterGroup({
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true,
        maxClusterRadius: 35,
        iconCreateFunction: (cluster) => {
          const markers = cluster.getAllChildMarkers();
          const totalCount = cluster.getChildCount();
          let offlineCount = 0;

          markers.forEach((m: any) => {
            if (m.isOffline) {
              offlineCount++;
            }
          });

          let clusterStatus = 'online';
          if (offlineCount === totalCount) {
            clusterStatus = 'critical'; // Todos offline: Vermelho
          } else if (offlineCount > 0) {
            clusterStatus = 'warning'; // 1 ou mais offline: Amarelo
          }

          let sizeClass = 'cluster-sm';
          let size = 38;
          if (totalCount >= 10 && totalCount < 100) {
            sizeClass = 'cluster-md';
            size = 44;
          } else if (totalCount >= 100) {
            sizeClass = 'cluster-lg';
            size = 50;
          }

          return L.divIcon({
            html: `<div><span>${totalCount}</span></div>`,
            className: `marker-cluster marker-cluster-${clusterStatus} ${sizeClass}`,
            iconSize: L.point(size, size),
          });
        },
      });

      // Tooltip informativo escuro ao passar o mouse sobre o cluster agrupado
      serverClusterGroup.on('clustermouseover', (e: any) => {
        const cluster = e.layer;
        const count = cluster.getChildCount();
        const markers = cluster.getAllChildMarkers();
        let offlineCount = 0;
        markers.forEach((m: any) => {
          if (m.isOffline) offlineCount++;
        });
        const onlineCount = count - offlineCount;

        let tooltipHtml = '';
        if (offlineCount === count) {
          tooltipHtml = `🔴 <strong>${count} servidores</strong><br/><span style="color:#ef4444;font-weight:700">Todos offline</span>`;
        } else if (offlineCount > 0) {
          tooltipHtml = `⚠️ <strong>${count} servidores</strong><br/><span style="color:#f59e0b;font-weight:700">${offlineCount} offline</span> · <span style="color:#10b981;font-weight:700">${onlineCount} online</span>`;
        } else {
          tooltipHtml = `🟢 <strong>${count} servidores</strong><br/><span style="color:#10b981;font-weight:700">Todos online</span>`;
        }

        cluster.bindTooltip(tooltipHtml, {
          permanent: false,
          direction: 'top',
          className: 'leaflet-tooltip-dark',
          offset: [0, -10],
        }).openTooltip();
      });

      serverClusterGroup.addTo(map);
      serverClusterGroupRef.current = serverClusterGroup;

      // Keep the group selectable when a server pin shares its location.
      map.createPane('ajin-cluster-pane').style.zIndex = '610';
      const onuLayer = L.markerClusterGroup({
        animate: false,
        clusterPane: 'ajin-cluster-pane',
        maxClusterRadius: 35,
        // Neighborhood view must show each numbered point, even when nearby.
        disableClusteringAtZoom: 14,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true,
        iconCreateFunction: cluster => {
          const markers = cluster.getAllChildMarkers() as (L.Marker & { ajinStatus?: string })[];
          const total = cluster.getChildCount();
          const counts = { online:0, offline:0, disabled:0, unknown:0 };
          for (const marker of markers) {
            const status = marker.ajinStatus as keyof typeof counts | undefined;
            counts[status && status in counts ? status : 'unknown']++;
          }
          const status = counts.offline === total ? 'critical' : counts.offline > 0 ? 'warning'
            : counts.disabled === total ? 'disabled' : counts.unknown === total ? 'unknown' : 'online';
          const content = document.createElement('div');
          const count = document.createElement('span');
          count.textContent = String(total);
          content.append(count);
          const detail = `${counts.online} online · ${counts.offline} offline · ${counts.disabled} desativados${counts.unknown ? ` · ${counts.unknown} desconhecidos` : ''}`;
          const tooltip = mapTooltip(`${total} pontos AJIN`, detail);
          if (cluster.getTooltip()) cluster.setTooltipContent(tooltip);
          else cluster.bindTooltip(tooltip, {
            direction:'top', className:'leaflet-tooltip-dark', offset:[0, -15],
          });
          const size = total >= 100 ? 50 : total >= 10 ? 44 : 38;
          const sizeClass = total >= 100 ? 'cluster-lg' : total >= 10 ? 'cluster-md' : 'cluster-sm';
          return L.divIcon({ html:content, className:`marker-cluster marker-cluster-${status} ${sizeClass} ajin-cluster`, iconSize:[size, size] });
        },
      }).addTo(map);
      onuLayerRef.current = onuLayer;

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
        serverClusterGroupRef.current = null;
        onuLayerRef.current = null;
        onuMarkersRef.current.clear();
        serverMarkersMapRef.current.clear();
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
          updateWhenZooming: false,
        }
      );
    } else if (activeLayer === 'roads') {
      newLayer = L.tileLayer(
        'https://mt{s}.google.com/vt/lyrs=m&hl=pt-BR&x={x}&y={y}&z={z}&s=Ga',
        {
          subdomains: ['0', '1', '2', '3'],
          maxZoom: 20,
          attribution: 'Google Maps',
          updateWhenZooming: false,
        }
      );
    } else {
      newLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: 'OpenStreetMap',
        updateWhenZooming: false,
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
    if (targetLocation.itemType === 'server' && targetLocation.id) {
      const targetMarker = serverMarkersMapRef.current.get(targetLocation.id);
      const clusterGroup = serverClusterGroupRef.current;
      if (targetMarker && clusterGroup) {
        clusterGroup.zoomToShowLayer(targetMarker, () => {
          targetMarker.openTooltip();
          const srv = servers.find((s) => s.id === targetLocation.id);
          if (srv) {
            setSelectedServer(srv);
            setSelectedOnu(null);
          }
        });
        onTargetLocationHandled?.();
        return;
      }
    }

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

  // Server markers do not depend on AJIN telemetry.
  useEffect(() => {
    const map = mapInstanceRef.current;
    const clusterGroup = serverClusterGroupRef.current;
    if (!map || !clusterGroup) return;

    clusterGroup.clearLayers();
    serverMarkersMapRef.current.clear();

    // 1. Plotar Servidores com Agrupamento (MarkerCluster)
    if (showServers) {
      const incidentIds = new Set(incidents.map((inc) => inc.id));
      const validServers = servers.filter((s) => s.latitude && s.longitude);
      const markersToAdd: L.Marker[] = [];

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

        const marker = L.marker([Number(s.latitude), Number(s.longitude)], { icon: customIcon });
        (marker as any).serverData = s;
        (marker as any).isOffline = isIncident;

        marker.bindTooltip(mapTooltip(s.name, `${s.host}:${s.port || 3389}`), {
          permanent: false,
          direction: 'top',
          className: 'leaflet-tooltip-dark',
          offset: [0, -38],
        });

        marker.on('click', () => {
          setSelectedServer(s);
          setSelectedOnu(null);
        });

        markersToAdd.push(marker);
        serverMarkersMapRef.current.set(s.id, marker);
      });

      clusterGroup.addLayers(markersToAdd);
    }

  }, [servers, incidents, showServers]);

  // Preserve marker objects/DOM across snapshots; uptime changes need no redraw.
  useEffect(() => {
    const map = mapInstanceRef.current, onuGroup = onuLayerRef.current;
    if (!map || !onuGroup) return;
    const cache = onuMarkersRef.current;
    if (!showOnus) {
      onuGroup.clearLayers(); cache.clear(); return;
    }
    if (showOnus && onus) {
      const validOnus = onus.filter(canShowOnMap);
      const keys = new Set(validOnus.map(onuKey));
      for (const [key, entry] of cache) {
        if (!keys.has(key)) { onuGroup.removeLayer(entry.marker); cache.delete(key); }
      }
      const markers: L.Marker[] = [];
      const statusChanges: L.Marker[] = [];
      let requestedMarker: L.Marker | undefined;

      validOnus.forEach((o) => {
        const key = onuKey(o), status = onuStatus(o);
        let entry = cache.get(key);
        const iconKey = JSON.stringify([pointName(o), status]);
        const tooltipKey = JSON.stringify([pointName(o), status, o.desc, o.port]);
        let customIcon: L.DivIcon | undefined;
        if (!entry || entry.iconKey !== iconKey) {
          const disabled = onuStatus(o) === 'disabled', isOnline = onuStatus(o) === 'online';
          const haloColor = disabled ? '#ffd54a' : isOnline ? 'rgba(34, 211, 238, 0.45)' : 'rgba(244, 63, 94, 0.5)';
          const pinBg = disabled ? '#ffd54a' : isOnline ? '#09252c' : '#330e16';
          const borderColor = disabled ? '#8a6510' : isOnline ? '#06b6d4' : '#f43f5e';

          // Point numbering is independent from the physical ONU ID (e.g. point 01 / ONU 91).
          const number = String(o.name || '').trim().match(/^(?:ponto\s+)?(\d+)$/i)?.[1] || '?';
          const pin = document.createElement('div');
          pin.className = `pin-marker pin-onu-numbered ${disabled ? 'pin-disabled' : isOnline ? 'pin-onu-online' : 'pin-offline'}`;
          pin.innerHTML = `
              <svg width="32" height="${disabled ? 32 : 42}" viewBox="0 0 30 ${disabled ? 30 : 38}" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                ${disabled ? `<circle class="pin-base" cx="15" cy="15" r="13.5" fill="${pinBg}" stroke="${borderColor}" stroke-width="2.2"/>` : `<path class="pin-base" d="M15 1.5C7.544 1.5 1.5 7.544 1.5 15C1.5 24.8 13.9 36.6 14.5 37.1C14.8 37.4 15.2 37.4 15.5 37.1C16.1 36.6 28.5 24.8 28.5 15C28.5 7.544 22.456 1.5 15 1.5Z" fill="${pinBg}" stroke="${borderColor}" stroke-width="2.2"/>`}
                <circle cx="15" cy="15" r="10" fill="${haloColor}"/>
                <text class="pin-point-number" x="15" y="15" dy=".35em" text-anchor="middle" fill="${disabled ? '#263d50' : '#ffffff'}"></text>
              </svg>
          `;
          const numberText = pin.querySelector('text')!;
          numberText.textContent = number;
          numberText.setAttribute('font-size', number.length > 2 ? '9' : '12');
          customIcon = L.divIcon({
            className: 'leaflet-pin-container', html: pin,
            iconSize: [32, disabled ? 32 : 42],
            iconAnchor: [16, disabled ? 16 : 41],
            tooltipAnchor: [0, disabled ? -16 : -42],
          });
        }
        if (!entry) {
          const marker = L.marker([Number(o.latitude), Number(o.longitude)], {icon:customIcon, title:pointName(o)});
          entry = {marker, row:o, iconKey, tooltipKey:''};
          const currentEntry = entry;
          marker.on('click', () => { setSelectedOnu(currentEntry.row); setSelectedServer(null); });
          cache.set(key, entry); markers.push(marker);
        } else {
          entry.row = o;
          if (customIcon) {
            entry.marker.setIcon(customIcon);
            entry.marker.options.title = pointName(o);
            entry.marker.getElement()?.setAttribute('title', pointName(o));
          }
          const location = entry.marker.getLatLng();
          if (location.lat !== Number(o.latitude) || location.lng !== Number(o.longitude)) {
            onuGroup.removeLayer(entry.marker);
            entry.marker.setLatLng([Number(o.latitude), Number(o.longitude)]);
            markers.push(entry.marker);
          }
          if (entry.marker.ajinStatus !== status) statusChanges.push(entry.marker);
        }
        entry.marker.ajinStatus = status;
        entry.iconKey = iconKey;
        if (entry.tooltipKey !== tooltipKey) {
          const text = status === 'disabled' ? 'Desativado' : o.status || 'Desconhecido';
          const content = mapTooltip(`${pointName(o)} (${text})`, o.desc || o.port);
          if (entry.marker.getTooltip()) entry.marker.setTooltipContent(content);
          else entry.marker.bindTooltip(content, {direction:'top', className:'leaflet-tooltip-dark', offset:[0, -36]});
          entry.tooltipKey = tooltipKey;
        }
        if (targetLocation?.onu && key === onuKey(targetLocation.onu)) requestedMarker = entry.marker;
      });
      if (markers.length) onuGroup.addLayers(markers);
      if (statusChanges.length) onuGroup.refreshClusters(statusChanges);
      if (requestedMarker) {
        // Resolve synchronously: zoomToShowLayer leaves moveend callbacks referring
        // to removed markers if a telemetry refresh rebuilds this group mid-zoom.
        let zoom = map.getZoom();
        map.setView(requestedMarker.getLatLng(), zoom, {animate:false});
        while (onuGroup.getVisibleParent(requestedMarker) !== requestedMarker && zoom < map.getMaxZoom()) {
          map.setZoom(++zoom, {animate:false});
        }
        const parent = onuGroup.getVisibleParent(requestedMarker);
        if (parent instanceof L.MarkerCluster) parent.spiderfy();
        onTargetLocationHandled?.();
      }
    }
  }, [onus, showOnus, targetLocation, onTargetLocationHandled]);

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
    const targetMarker = serverMarkersMapRef.current.get(inc.id);
    const clusterGroup = serverClusterGroupRef.current;
    const srv = servers.find((s) => s.id === inc.id) || {
      id: inc.id,
      name: inc.name,
      host: inc.host,
      port: inc.port,
      latitude: inc.latitude,
      longitude: inc.longitude,
    };

    if (targetMarker && clusterGroup) {
      clusterGroup.zoomToShowLayer(targetMarker, () => {
        targetMarker.openTooltip();
        setSelectedServer(srv);
        setSelectedOnu(null);
      });
    } else if (inc.latitude && inc.longitude && mapInstanceRef.current) {
      mapInstanceRef.current.stop();
      mapInstanceRef.current.flyTo([Number(inc.latitude), Number(inc.longitude)], 14, { duration: 1.0 });
      setSelectedServer(srv);
      setSelectedOnu(null);
    }
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
              title="Exibir ou ocultar pontos da Ajin no mapa"
              className={`px-2 py-1 rounded text-[11px] font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                showOnus
                  ? 'bg-cyan-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>⚡</span>
              <span>Pontos AJIN ({onus ? onus.filter(canShowOnMap).length : 0})</span>
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

        {/* 2. MENU SIMPLES DE SERVIDORES EM FALHA (IDÊNTICO À REFERÊNCIA DO USUÁRIO) */}
        {isTrayOpen && incidents.length > 0 && (
          <div className="w-[360px] max-w-[94vw] bg-[#18191f]/95 backdrop-blur-md border border-[#3b1e22] rounded-xl shadow-2xl overflow-hidden flex flex-col animate-in fade-in duration-150">
            {/* Header */}
            <div className="px-3.5 py-2.5 border-b border-[#3b1e22] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm">⚠️</span>
                <span className="text-[11px] font-black uppercase tracking-wider text-[#ff5c5c]">
                  FALHAS RDP CONFIRMADAS
                </span>
                <span className="px-2 py-0.5 rounded-full bg-[#e03131] text-white font-mono text-[11px] font-bold leading-none shadow-[0_0_6px_rgba(224,49,49,0.5)]">
                  {incidents.length}
                </span>
              </div>
              <button
                onClick={() => setIsTrayOpen(false)}
                className="text-slate-400 hover:text-white transition-colors cursor-pointer p-0.5"
                title="Fechar"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Lista simples de servidores */}
            <div className="max-h-[300px] overflow-y-auto p-2 space-y-1.5">
              {incidents.map((inc) => (
                <div
                  key={inc.id}
                  onClick={() => handleIncidentClick(inc)}
                  title="Falha persistente no teste da porta RDP. Clique para localizar no mapa."
                  className="px-3 py-2 rounded-lg bg-[#20222a]/90 hover:bg-[#282a35] border border-white/5 hover:border-red-500/40 transition-all cursor-pointer flex items-center justify-between group"
                >
                  <div className="flex items-center gap-2 min-w-0 mr-2">
                    <span className="w-2 h-2 rounded-full bg-[#ff4d4f] shadow-[0_0_8px_#ff4d4f] shrink-0" />
                    <span className="text-xs font-semibold text-slate-100 group-hover:text-white truncate">
                      {inc.name}
                    </span>
                  </div>

                  <span className="px-2.5 py-0.5 rounded border border-[#5c1d24] bg-[#2a1316] text-[#ff6b6b] font-mono text-xs font-semibold shrink-0">
                    {formatLossDuration(inc.duration_seconds)}
                  </span>
                </div>
              ))}
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
                  onuStatus(selectedOnu) === 'disabled' ? 'bg-yellow-950/80 text-yellow-300 border-yellow-700/60' : selectedOnu.status === 'Online'
                    ? 'bg-cyan-950/80 text-cyan-300 border-cyan-700/60'
                    : 'bg-rose-950/80 text-rose-300 border-rose-700/60'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${onuStatus(selectedOnu) === 'disabled' ? 'bg-yellow-400' : selectedOnu.status === 'Online' ? 'bg-cyan-400 animate-pulse' : 'bg-rose-400'}`} />
                {onuStatus(selectedOnu) === 'disabled' ? 'Desativado' : selectedOnu.status === 'Online' ? 'Online' : 'Fora de Funcionamento'}
              </span>
              {selectedOnu.catalog_number === undefined && <span className="text-xs px-2 py-0.5 rounded bg-[#1f2430] border border-white/10 text-slate-300 font-mono">
                {selectedOnu.port} • ID #{selectedOnu.id}
              </span>}
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
              {selectedOnu.catalog_number === undefined ? <><div>📟 <span className="text-slate-400">MAC / Serial:</span> <span className="font-mono text-cyan-300">{selectedOnu.serial || '-'}</span></div>
              <div>🏭 <span className="text-slate-400">Fabricante:</span> <span className="text-white">{selectedOnu.vendor || '—'}</span></div></> : <div className="text-yellow-300">Ponto desativado · sem ONU vinculada</div>}
            </div>
            <div className="space-y-1">
              {selectedOnu.catalog_number === undefined && <><div>📶 <span className="text-slate-400">Sinal:</span> <span className="font-mono text-emerald-400">{signalValue(selectedOnu)}</span></div>
              <div><span className="text-slate-400">UPTime:</span> <span className="font-mono">{onuStatus(selectedOnu) === 'disabled' ? '—' : selectedOnu.uptime || '—'}</span></div></>}
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

          {onEditOnu && selectedOnu.catalog_number === undefined && (
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

      {/* Estilos Globais do Leaflet (Alfinetes, Clusters e Tooltips) */}
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
        .pin-onu-numbered { width: 32px; height: 42px; filter: none; }
        .pin-onu-numbered:hover { filter: none; }
        .pin-onu-numbered.pin-disabled { height: 32px; transform-origin: center; }
        .pin-point-number { font-family: 'Segoe UI', Arial, sans-serif; font-weight: 700; font-variant-numeric: tabular-nums; }
        .marker-cluster.ajin-cluster { animation: none !important; filter: none; transition: none; }
        .marker-cluster.ajin-cluster div { box-shadow: none !important; }
        .marker-cluster-disabled { background: #ffd54a60; }
        .marker-cluster-disabled div { background: #ffd54a; color: #263d50; border: 2px solid white; text-align: center; font-weight: 800; }
        .marker-cluster-unknown { background: #8796a460; }
        .marker-cluster-unknown div { background: #657485; color: white; border: 2px solid white; text-align: center; font-weight: 800; }
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
          background: rgba(18, 20, 26, 0.92) !important;
          color: #ffffff !important;
          border: 1px solid rgba(255, 255, 255, 0.15) !important;
          border-radius: 6px !important;
          font-size: 11px !important;
          font-weight: 600 !important;
          box-shadow: 0 4px 12px rgba(0,0,0,0.5) !important;
          padding: 5px 9px !important;
          line-height: 1.35 !important;
        }
        .leaflet-tooltip-dark::before {
          border-top-color: rgba(18, 20, 26, 0.92) !important;
        }

        /* MarkerCluster Customizado para Servidores (Dark Moderno) */
        .marker-cluster {
          background-clip: padding-box;
          border-radius: 50% !important;
          transition: transform 0.22s cubic-bezier(0.175, 0.885, 0.32, 1.275);
          cursor: pointer !important;
          filter: drop-shadow(0 4px 10px rgba(0, 0, 0, 0.7));
        }
        .marker-cluster:hover {
          transform: scale(1.18);
          z-index: 10000 !important;
        }

        /* Tamanhos dos Clusters */
        .marker-cluster.cluster-sm {
          width: 38px !important;
          height: 38px !important;
        }
        .marker-cluster.cluster-sm div {
          width: 28px !important;
          height: 28px !important;
          margin-left: 5px !important;
          margin-top: 5px !important;
          border-radius: 50% !important;
          font-size: 13px !important;
        }
        .marker-cluster.cluster-sm span {
          line-height: 24px !important;
        }

        .marker-cluster.cluster-md {
          width: 44px !important;
          height: 44px !important;
        }
        .marker-cluster.cluster-md div {
          width: 34px !important;
          height: 34px !important;
          margin-left: 5px !important;
          margin-top: 5px !important;
          border-radius: 50% !important;
          font-size: 14px !important;
        }
        .marker-cluster.cluster-md span {
          line-height: 30px !important;
        }

        .marker-cluster.cluster-lg {
          width: 50px !important;
          height: 50px !important;
        }
        .marker-cluster.cluster-lg div {
          width: 38px !important;
          height: 38px !important;
          margin-left: 6px !important;
          margin-top: 6px !important;
          border-radius: 50% !important;
          font-size: 15px !important;
        }
        .marker-cluster.cluster-lg span {
          line-height: 34px !important;
        }

        /* 1. VERDE: Todos os servidores online */
        .marker-cluster-online {
          background-color: rgba(16, 185, 129, 0.38) !important;
        }
        .marker-cluster-online div {
          background-color: #10b981 !important;
          color: #ffffff !important;
          font-weight: 800 !important;
          border: 2px solid #ffffff !important;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.6) !important;
          text-align: center;
        }

        /* 2. AMARELO: 1 ou mais servidores offline no grupo (Alerta) */
        .marker-cluster-warning {
          background-color: rgba(245, 158, 11, 0.45) !important;
          animation: pulse-cluster-warning 2.2s infinite ease-in-out !important;
        }
        .marker-cluster-warning div {
          background-color: #f59e0b !important;
          color: #0f1117 !important;
          font-weight: 900 !important;
          border: 2px solid #ffffff !important;
          box-shadow: 0 4px 14px rgba(245, 158, 11, 0.8) !important;
          text-align: center;
        }

        /* 3. VERMELHO: Todos os servidores offline no grupo (Crítico) */
        .marker-cluster-critical {
          background-color: rgba(239, 68, 68, 0.50) !important;
          animation: pulse-cluster-critical 1.8s infinite ease-in-out !important;
        }
        .marker-cluster-critical div {
          background-color: #ef4444 !important;
          color: #ffffff !important;
          font-weight: 900 !important;
          border: 2px solid #ffffff !important;
          box-shadow: 0 4px 16px rgba(239, 68, 68, 0.85) !important;
          text-align: center;
        }

        @keyframes pulse-cluster-warning {
          0%, 100% {
            box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.6);
          }
          50% {
            box-shadow: 0 0 0 10px rgba(245, 158, 11, 0);
          }
        }

        @keyframes pulse-cluster-critical {
          0%, 100% {
            box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7);
          }
          50% {
            box-shadow: 0 0 0 12px rgba(239, 68, 68, 0);
          }
        }
      `}</style>
    </div>
  );
});
