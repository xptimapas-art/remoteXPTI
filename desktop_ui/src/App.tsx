import React, { useState, useEffect, useRef } from 'react';
import { TitleBar } from './components/TitleBar';
import { ServersView } from './components/ServersView';
import { MapView } from './components/MapView';
import { AjinView } from './components/AjinView';

const API_BASE = 'http://127.0.0.1:8765';
const WS_URL = 'ws://127.0.0.1:8765/ws/ajin';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<'servers' | 'map' | 'ajin'>('ajin');
  const [servers, setServers] = useState<any[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
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

  // Carrega servidores da API local
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
        // Reconexão automática em caso de queda transitória
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

  const handleForceRefresh = async () => {
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
    <div className="flex flex-col h-screen w-screen bg-[#0d1117] overflow-hidden select-none">
      {/* Top Header / Custom TitleBar */}
      <TitleBar
        currentTab={currentTab}
        setCurrentTab={setCurrentTab}
        serverCount={servers.length}
        onlineCount={servers.length}
      />

      {/* Main View Area com transição instantânea e zero sobreposição */}
      <main className="flex-1 flex overflow-hidden relative">
        {currentTab === 'servers' && (
          <ServersView
            servers={servers}
            groups={groups}
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
            onRefresh={handleForceRefresh}
            onSaveLabel={handleSaveLabel}
          />
        )}
      </main>
    </div>
  );
};

export default App;
