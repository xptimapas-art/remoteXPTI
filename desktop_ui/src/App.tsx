import React, { useState, useEffect, useRef } from 'react';
import { TitleBar } from './components/TitleBar';
import { ServersView } from './components/ServersView';
import { MapView } from './components/MapView';
import { AjinView } from './components/AjinView';
import { AddServerModal } from './components/AddServerModal';
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
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);

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

    return () => {
      wsRef.current?.close();
    };
  }, []);

  const handleConnect = async (serverId: string) => {
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

  const handleSaveLabel = async (port: string, onuId: string, name: string, desc: string) => {
    try {
      await fetch(`${API_BASE}/api/ajin/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port, onu_id: onuId, name, desc }),
      });
      loadTelemetry();
    } catch (e) {
      console.error('Erro ao salvar label:', e);
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-[#0d1117] overflow-hidden select-none font-sans">
      {/* Top Header Barra idêntica à referência original */}
      <TitleBar
        currentTab={currentTab}
        setCurrentTab={setCurrentTab}
        searchTerm={searchTerm}
        setSearchTerm={setSearchTerm}
        selectedGroup={selectedGroup}
        setSelectedGroup={setSelectedGroup}
        groups={groups}
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
          />
        )}

        {currentTab === 'map' && (
          <MapView
            servers={servers}
            onConnect={handleConnect}
          />
        )}

        {currentTab === 'ajin' && (
          <AjinView
            telemetry={telemetry}
            countdown={countdown}
            currentTime={currentTime}
            onRefresh={handleForceRefreshAjin}
            onSaveLabel={handleSaveLabel}
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

      <SettingsModal
        isOpen={isSettingsModalOpen}
        onClose={() => setIsSettingsModalOpen(false)}
        serverCount={servers.length}
      />
    </div>
  );
};

export default App;
