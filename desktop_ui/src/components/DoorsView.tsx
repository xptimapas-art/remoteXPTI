import React, { useState, useEffect } from 'react';
import {
  DoorClosed,
  DoorOpen,
  KeyRound,
  ShieldCheck,
  RefreshCw,
  Settings,
  Car,
  Clock,
  CheckCircle2,
  Lock,
} from 'lucide-react';

interface DoorItem {
  id: string;
  name: string;
  device_name?: string;
  device_id?: string;
  scene_id?: string;
  scene_name?: string;
  hotkey?: string;
  enabled?: boolean;
  cloud_online?: boolean;
  last_triggered?: string | null;
}

interface AccessLogItem {
  id: string;
  door_id: string;
  door_name: string;
  source: string;
  success: boolean;
  detail: string;
  timestamp: string;
  date: string;
}

interface DoorsViewProps {
  isDev: boolean;
  onOpenDevLogin: () => void;
  onOpenDoorsSettings: () => void;
  onDoorTriggered?: (doorName: string, success: boolean, msg: string) => void;
}

const API_BASE = 'http://127.0.0.1:8765';

export const DoorsView: React.FC<DoorsViewProps> = ({
  isDev,
  onOpenDevLogin,
  onOpenDoorsSettings,
  onDoorTriggered,
}) => {
  const [doors, setDoors] = useState<DoorItem[]>([]);
  const [cloudStatus, setCloudStatus] = useState<any>({ connected: false });
  const [logs, setLogs] = useState<AccessLogItem[]>([]);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);
  const [successId, setSuccessId] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const fetchDoorsData = async () => {
    if (!isDev) return;
    try {
      const [resDoors, resLogs] = await Promise.all([
        fetch(`${API_BASE}/api/doors`),
        fetch(`${API_BASE}/api/doors/logs`),
      ]);

      if (resDoors.ok) {
        const data = await resDoors.json();
        setDoors(data.doors || []);
        setCloudStatus(data.cloud_status || { connected: false });
      }

      if (resLogs.ok) {
        const dataLogs = await resLogs.json();
        setLogs(dataLogs.logs || []);
      }
    } catch (e) {
      console.warn('Erro ao carregar dados de portas:', e);
    }
  };

  useEffect(() => {
    if (isDev) {
      fetchDoorsData();
      const interval = setInterval(fetchDoorsData, 4000);
      return () => clearInterval(interval);
    }
  }, [isDev]);

  const handleOpenDoor = async (door: DoorItem) => {
    if (!isDev || triggeringId) return;

    setTriggeringId(door.id);
    try {
      const res = await fetch(`${API_BASE}/api/doors/${door.id}/open`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'Painel DEV' }),
      });

      const data = await res.json();
      if (res.ok && data.success) {
        setSuccessId(door.id);
        setTimeout(() => setSuccessId(null), 2500);
        onDoorTriggered?.(door.name, true, data.message || 'Comando enviado com sucesso!');
        fetchDoorsData();
      } else {
        onDoorTriggered?.(door.name, false, data.detail || 'Falha ao acionar porta.');
      }
    } catch (e: any) {
      onDoorTriggered?.(door.name, false, e.message || 'Erro de comunicação com o servidor.');
    } finally {
      setTriggeringId(null);
    }
  };

  const handleSyncCloud = async () => {
    setSyncing(true);
    try {
      const res = await fetch(`${API_BASE}/api/doors/sync`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setCloudStatus(data.cloud_status || {});
        setDoors(data.doors || []);
      }
    } catch (e) {
      console.warn('Erro ao sincronizar nuvem Tuya:', e);
    } finally {
      setSyncing(false);
    }
  };

  // Se não estiver em modo desenvolvedor, bloqueia a exibição
  if (!isDev) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 bg-[#0f1117] text-white select-none">
        <div className="max-w-md w-full bg-[#161822] border border-amber-500/30 rounded-2xl p-8 text-center shadow-2xl relative overflow-hidden">
          <div className="absolute -top-12 -right-12 w-32 h-32 bg-amber-500/10 rounded-full blur-2xl pointer-events-none" />
          <div className="w-16 h-16 rounded-2xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-400 mx-auto mb-5 shadow-inner">
            <Lock className="w-8 h-8" />
          </div>
          <h2 className="text-xl font-extrabold text-white mb-2 tracking-tight">
            Acesso Restrito: Modo Desenvolvedor
          </h2>
          <p className="text-xs text-slate-400 leading-relaxed mb-6">
            O módulo de acionamento de portões e fechaduras Tuya é de uso estrito e requer autenticação ativa de desenvolvedor para garantir a segurança das instalações físicas.
          </p>
          <button
            onClick={onOpenDevLogin}
            className="w-full py-3 px-4 bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-500 hover:to-amber-600 active:scale-98 text-white rounded-xl text-xs font-bold transition-all shadow-lg flex items-center justify-center gap-2 cursor-pointer border border-amber-400/40"
          >
            <KeyRound className="w-4 h-4" />
            <span>Autenticar como Desenvolvedor</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col bg-[#0f1117] text-white overflow-y-auto select-none p-6 space-y-6">
      {/* 1. TOPO / HEADER DO MÓDULO */}
      <div className="bg-[#151722] border border-[#272b3c] rounded-2xl p-5 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-500/20 to-orange-600/20 border border-amber-500/40 flex items-center justify-center text-amber-400 shadow-inner">
            <DoorClosed className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-lg font-extrabold text-white tracking-tight">
                Controle de Acesso & Portarias
              </h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 border border-amber-500/40 text-amber-300 flex items-center gap-1 font-mono">
                <ShieldCheck className="w-3 h-3" />
                Sessão DEV
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Fechaduras elétricas e motores de portão acionados via Tuya Smart Cloud e atalhos rápidos de teclado.
            </p>
          </div>
        </div>

        {/* Status da Nuvem e Ações Rápidas */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <div
            className={`px-3 py-1.5 rounded-xl border text-xs font-bold flex items-center gap-2 transition-all ${
              cloudStatus.connected
                ? 'bg-emerald-950/60 border-emerald-500/40 text-emerald-300'
                : 'bg-rose-950/60 border-rose-500/40 text-rose-300'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                cloudStatus.connected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'
              }`}
            />
            <span>{cloudStatus.connected ? 'Nuvem Conectada' : 'Nuvem Desconectada'}</span>
          </div>

          <button
            onClick={handleSyncCloud}
            disabled={syncing}
            title="Sincronizar e testar conexão com a Nuvem Tuya"
            className="px-3 py-1.5 rounded-xl bg-[#1f2230] hover:bg-[#2b2f42] border border-[#373c52] text-xs font-semibold text-slate-200 flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin text-amber-400' : ''}`} />
            <span>Sincronizar</span>
          </button>

          <button
            onClick={onOpenDoorsSettings}
            title="Configurar Portas, Atalhos de Teclado e Conta Tuya"
            className="px-3 py-1.5 rounded-xl bg-amber-600/20 hover:bg-amber-600/30 border border-amber-500/50 text-xs font-bold text-amber-300 flex items-center gap-1.5 transition-all shadow-sm cursor-pointer"
          >
            <Settings className="w-3.5 h-3.5" />
            <span>Configurações & Atalhos</span>
          </button>
        </div>
      </div>

      {/* 2. GRADE DE PORTAS E PORTÕES */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {doors.map((door) => {
          const isTriggering = triggeringId === door.id;
          const isSuccess = successId === door.id;
          const isGarage =
            door.name.toLowerCase().includes('portão') ||
            door.name.toLowerCase().includes('garagem') ||
            door.name.toLowerCase().includes('car');

          return (
            <div
              key={door.id}
              className={`bg-[#151722] border rounded-2xl p-5 shadow-xl transition-all relative overflow-hidden flex flex-col justify-between ${
                isSuccess
                  ? 'border-emerald-500/80 shadow-[0_0_25px_rgba(16,185,129,0.25)]'
                  : 'border-[#272b3c] hover:border-[#383e56]'
              }`}
            >
              {/* Topo do Card */}
              <div>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-11 h-11 rounded-xl flex items-center justify-center transition-all ${
                        isSuccess
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                          : 'bg-[#1e2230] text-amber-400 border border-[#353b52]'
                      }`}
                    >
                      {isGarage ? (
                        <Car className="w-5 h-5" />
                      ) : isSuccess ? (
                        <DoorOpen className="w-5 h-5" />
                      ) : (
                        <DoorClosed className="w-5 h-5" />
                      )}
                    </div>
                    <div>
                      <h3 className="font-extrabold text-sm text-white leading-tight">
                        {door.name}
                      </h3>
                      <span className="text-[11px] text-slate-400 font-medium">
                        {door.device_name || 'Fechadura Inteligente'}
                      </span>
                    </div>
                  </div>

                  {/* Badge de Atalho da Tecla */}
                  {door.hotkey && (
                    <div
                      title={`Atalho global no teclado do Windows: [ ${door.hotkey} ]`}
                      className="px-2.5 py-1 rounded-lg bg-[#1c202d] border border-amber-500/40 text-amber-300 font-mono text-xs font-extrabold shadow-sm flex items-center gap-1"
                    >
                      <span>⌨️</span>
                      <span>{door.hotkey}</span>
                    </div>
                  )}
                </div>

                {/* Status e Metadados */}
                <div className="bg-[#1a1d2b] border border-white/5 rounded-xl p-2.5 text-xs text-slate-300 space-y-1 my-3">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400 text-[11px]">Nuvem Tuya:</span>
                    <span className="text-emerald-400 font-semibold flex items-center gap-1 text-[11px]">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      Pronta para disparo
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400 text-[11px]">Último disparo:</span>
                    <span className="font-mono text-slate-300 text-[11px]">
                      {door.last_triggered ? door.last_triggered.split('T')[1] || door.last_triggered : 'Nenhum recente'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Botão de Disparo / Abertura Principal */}
              <div className="pt-2">
                <button
                  onClick={() => handleOpenDoor(door)}
                  disabled={isTriggering || !cloudStatus.connected}
                  className={`w-full py-3.5 px-4 rounded-xl font-extrabold text-xs tracking-wider transition-all shadow-lg flex items-center justify-center gap-2 cursor-pointer ${
                    isSuccess
                      ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-[0_0_15px_rgba(16,185,129,0.5)]'
                      : isTriggering
                      ? 'bg-amber-700/60 text-amber-200 cursor-wait'
                      : 'bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 active:scale-98 text-white shadow-[0_4px_16px_rgba(217,119,6,0.35)]'
                  }`}
                >
                  {isTriggering ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>DISPARANDO COMANDO...</span>
                    </>
                  ) : isSuccess ? (
                    <>
                      <CheckCircle2 className="w-4 h-4" />
                      <span>PORTA ABERTA COM SUCESSO!</span>
                    </>
                  ) : (
                    <>
                      {isGarage ? <Car className="w-4 h-4" /> : <DoorOpen className="w-4 h-4" />}
                      <span>{isGarage ? 'ABRIR PORTÃO' : 'ABRIR PORTA'}</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          );
        })}

        {doors.length === 0 && (
          <div className="col-span-full bg-[#151722] border border-dashed border-[#272b3c] rounded-2xl p-10 text-center text-slate-400">
            <DoorClosed className="w-10 h-10 mx-auto text-slate-500 mb-2" />
            <p className="text-sm font-bold text-white mb-1">Nenhuma porta configurada</p>
            <p className="text-xs text-slate-400 mb-4">
              Clique em Configurações para cadastrar a primeira fechadura ou portão.
            </p>
            <button
              onClick={onOpenDoorsSettings}
              className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-xl text-xs font-bold transition-all"
            >
              Abrir Configurações
            </button>
          </div>
        )}
      </div>

      {/* 3. PAINEL DE HISTÓRICO DE ACESSOS RECENTES */}
      <div className="bg-[#151722] border border-[#272b3c] rounded-2xl p-5 shadow-xl">
        <div className="flex items-center justify-between mb-4 border-b border-white/5 pb-3">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-amber-400" />
            <h2 className="font-extrabold text-xs text-white uppercase tracking-wider">
              Histórico Recente de Acessos
            </h2>
          </div>
          <span className="text-[11px] text-slate-400 font-mono">
            {logs.length} registro(s) capturado(s)
          </span>
        </div>

        {logs.length > 0 ? (
          <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
            {logs.map((log) => (
              <div
                key={log.id}
                className="bg-[#1a1d2b] hover:bg-[#202436] border border-white/5 rounded-xl px-3.5 py-2.5 flex items-center justify-between text-xs transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      log.success ? 'bg-emerald-400 shadow-[0_0_6px_#10b981]' : 'bg-rose-400 shadow-[0_0_6px_#f43f5e]'
                    }`}
                  />
                  <div>
                    <span className="font-bold text-white mr-2">{log.door_name}</span>
                    <span className="text-slate-400 text-[11px]">
                      via <strong className="text-amber-300">{log.source}</strong>
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-slate-400 font-mono">
                    {log.timestamp} • {log.date}
                  </span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      log.success
                        ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/50'
                        : 'bg-rose-950/80 text-rose-300 border border-rose-700/50'
                    }`}
                  >
                    {log.success ? 'Sucesso' : 'Falha'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-6 text-slate-500 text-xs">
            Nenhum acionamento registrado nesta sessão.
          </div>
        )}
      </div>
    </div>
  );
};
