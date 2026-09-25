import React, { useState, useEffect, useRef } from 'react';
import { Play } from 'lucide-react';
import { TitleBar } from './components/TitleBar';
import { ServersView } from './components/ServersView';
import { MapView } from './components/MapView';
import { AjinView } from './components/AjinView';
import { AddServerModal } from './components/AddServerModal';
import { EditServerModal } from './components/EditServerModal';
import { SettingsModal } from './components/SettingsModal';

const API_BASE = 'http://127.0.0.1:8765';
const WS_URL = 'ws://127.0.0.1:8765/ws/ajin';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<'servers' | 'map' | 'ajin'>('servers');
  const [servers, setServers] = useState<any[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedGroup, setSelectedGroup] = useState('Todos os Grupos');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingServerId, setEditingServerId] = useState<string | null>(null);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [isDev, setIsDev] = useState(false);
  const [rdpToast, setRdpToast] = useState<{ visible: boolean; name: string; host: string } | null>(null);
  const [mapTargetLocation, setMapTargetLocation] = useState<{
    lat: number;
    lon: number;
    zoom?: number;
    id?: string;
    itemType?: 'server' | 'onu';
    onu?: any;
  } | null>(null);

  const [telemetry, setTelemetry] = useState<any>({
    total: 39,
    online: 36,
    offline: 3,
    total_cameras: 64,
    active_problems: 0,
    coleta_formatted: '25/09/2026 12:01:09',
    server: { online: true, ip: '192.168.190.187', checked_at: '-' },
    olt: { modelo: 'C-Data FD1108S', ip: '192.168.1.100' },
    ports: {},
    rows: [],
  });
  const [countdown, setCountdown] = useState(10);
  const [currentTime, setCurrentTime] = useState('--:--:--');
  const wsRef = useRef<WebSocket | null>(null);

  // Carrega status de desenvolvedor
  const checkDevStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/dev/status`);
      if (res.ok) {
        const data = await res.json();
        setIsDev(Boolean(data.is_dev));
      }
    } catch (e) {
      console.warn('Erro ao verificar status DEV:', e);
    }
  };

  // Carrega lista de servidores da API local
  const loadServers = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/servers`);
      if (res.ok) {
        const data = await res.json();
        setServers(data.servers || []);
        setGroups(data.groups || []);
      }
    } catch (e) {
      console.warn('Erro ao carregar servidores locais:', e);
    }
  };

  // Carrega telemetria inicial da AJIN
  const loadTelemetry = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ajin/telemetry`);
      if (res.ok) {
        const data = await res.json();
        setTelemetry(data);
      }
    } catch (e) {
      console.warn('Erro ao carregar telemetria:', e);
    }
  };

  // Conexão WebSocket em Tempo Real (Push contínuo a 60 FPS)
  useEffect(() => {
    checkDevStatus();
    loadServers();
    loadTelemetry();

    const connectWebSocket = () => {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'initial_state' || msg.type === 'telemetry_update') {
            if (msg.data) setTelemetry(msg.data);
            if (msg.time) setCurrentTime(msg.time);
          } else if (msg.type === 'tick') {
            if (msg.time) setCurrentTime(msg.time);
            if (typeof msg.countdown === 'number') setCountdown(msg.countdown);
          } else if (msg.type === 'servers_status_updated') {
            loadServers();
          }
        } catch (e) {
          console.error('Falha ao processar mensagem do WebSocket:', e);
        }
      };

      ws.onclose = () => {
        setTimeout(connectWebSocket, 2000);
      };
    };

    connectWebSocket();

    // Polling de segurança a cada 15 segundos para manter contadores de LOSS atualizados
    const srvInterval = setInterval(() => {
      loadServers();
    }, 15000);

    return () => {
      clearInterval(srvInterval);
      wsRef.current?.close();
    };
  }, []);

  const handleConnect = async (serverId: string) => {
    const target = servers.find((s) => s.id === serverId);
    const name = target?.name || 'Servidor';
    const host = target?.host || '';

    setRdpToast({ visible: true, name, host });
    setTimeout(() => {
      setRdpToast(null);
    }, 4500);

    try {
      await fetch(`${API_BASE}/api/servers/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ server_id: serverId }),
      });
    } catch (e) {
      console.error('Erro ao conectar ao servidor:', e);
    }
  };

  const handleToggleFavorite = async (serverId: string) => {
    try {
      setServers((prev) =>
        prev.map((s) => (s.id === serverId ? { ...s, favorite: !s.favorite } : s))
      );
      await fetch(`${API_BASE}/api/servers/${serverId}/favorite`, { method: 'POST' });
    } catch (e) {
      console.error('Erro ao alternar favorito:', e);
    }
  };

  const handleGlobalRefresh = async () => {
    try {
      await fetch(`${API_BASE}/api/refresh_all`, { method: 'POST' });
      await loadServers();
      await loadTelemetry();
    } catch (e) {
      console.error('Erro ao atualizar geral:', e);
    }
  };

  const handleForceRefreshAjin = async () => {
    try {
      await fetch(`${API_BASE}/api/ajin/refresh`, { method: 'POST' });
    } catch (e) {
      console.error('Erro ao forçar refresh:', e);
    }
  };

  const handleSaveLabel = async (
    port: string,
    onuId: string,
    name: string,
    desc: string,
    lat?: number | null,
    lon?: number | null
  ) => {
    try {
      await fetch(`${API_BASE}/api/ajin/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          port,
          onu_id: onuId,
          name,
          desc,
          latitude: lat,
          longitude: lon,
        }),
      });
      loadTelemetry();
    } catch (e) {
      console.error('Erro ao salvar label:', e);
    }
  };

  const handleLocateOnuOnMap = (onu: any) => {
    if (onu.latitude && onu.longitude) {
      setMapTargetLocation({
        lat: Number(onu.latitude),
        lon: Number(onu.longitude),
        zoom: 16,
        itemType: 'onu',
        onu,
      });
      setCurrentTab('map');
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-[#0d1117] overflow-hidden select-none font-sans">
      {/* Top Header Barra idêntica à referência original */}
      <TitleBar
        currentTab={currentTab}
        setCurrentTab={(tab) => {
          if (tab === 'map') {
            setMapTargetLocation(null);
          }
          setCurrentTab(tab);
        }}
        searchTerm={searchTerm}
        setSearchTerm={setSearchTerm}
        selectedGroup={selectedGroup}
        setSelectedGroup={setSelectedGroup}
        groups={groups}
        isDev={isDev}
        onRefresh={handleGlobalRefresh}
        onAddServer={() => setIsAddModalOpen(true)}
        onOpenSettings={() => setIsSettingsModalOpen(true)}
      />

      {/* Main View Area com transição instantânea e sem sobreposição */}
      <main className="flex-1 flex overflow-hidden relative">
        {currentTab === 'servers' && (
          <ServersView
            servers={servers}
            searchTerm={searchTerm}
            selectedGroup={selectedGroup}
            onConnect={handleConnect}
            onEdit={(id) => setEditingServerId(id)}
            onToggleFavorite={handleToggleFavorite}
          />
        )}

        {currentTab === 'map' && (
          <MapView
            servers={servers}
            onus={telemetry.rows}
            onConnect={handleConnect}
            targetLocation={mapTargetLocation}
            onTargetLocationHandled={() => {
              setMapTargetLocation(null);
            }}
            onEditOnu={() => {
              setCurrentTab('ajin');
            }}
          />
        )}

        {currentTab === 'ajin' && (
          <AjinView
            telemetry={telemetry}
            countdown={countdown}
            currentTime={currentTime}
            onRefresh={handleForceRefreshAjin}
            onSaveLabel={handleSaveLabel}
            onLocateOnMap={handleLocateOnuOnMap}
          />
        )}
      </main>

      {/* Modais de Ação */}
      <AddServerModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        groups={groups}
        onServerAdded={() => {
          loadServers();
        }}
      />

      <EditServerModal
        serverId={editingServerId}
        isOpen={Boolean(editingServerId)}
        onClose={() => setEditingServerId(null)}
        groups={groups}
        onServerUpdated={() => {
          loadServers();
        }}
        onConnect={handleConnect}
      />

      <SettingsModal
        isOpen={isSettingsModalOpen}
        onClose={() => setIsSettingsModalOpen(false)}
        serverCount={servers.length}
        isDev={isDev}
        onDevStatusChanged={(val) => setIsDev(val)}
        onServersReload={() => {
          loadServers();
        }}
      />

      {/* Toast Flutuante de Disparo de RDP */}
      {rdpToast && (
        <div className="fixed bottom-6 right-6 z-[200] bg-[#16171d] border border-blue-500/50 shadow-2xl rounded-xl p-4 flex items-center space-x-3.5 animate-in slide-in-from-bottom-5 duration-200">
          <div className="w-10 h-10 rounded-lg bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-blue-400 shrink-0">
            <Play className="w-5 h-5 fill-current" />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center space-x-2">
              <span className="text-xs font-bold text-white leading-tight">{rdpToast.name}</span>
              <span className="text-[10px] font-mono text-blue-400 bg-blue-950/80 px-1.5 py-0.5 rounded border border-blue-800/40">
                {rdpToast.host}
              </span>
            </div>
            <span className="text-[11px] text-[#8e92a0] mt-1">
              Injetando credenciais via cmdkey e abrindo MSTSC nativo...
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
