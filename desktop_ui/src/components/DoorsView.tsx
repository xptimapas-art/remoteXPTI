import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { History, Lock, Plus, RefreshCw, Settings } from 'lucide-react';
import { AccessDialog } from './AccessDialog';
import { DoorCamera } from './DoorCamera';
import { isFacialDoor, openDoorLabel, readResponse } from './doors';
import type { CloudStatus, DoorConfig } from './doors';
import './Doors.css';

interface AccessLog { id: string; door_name: string; source: string; success: boolean; detail: string; timestamp: string; date: string }
interface Props {
  isDev: boolean; onOpenDevLogin: () => void; onOpenDoorsSettings: (doorId?: string) => void;
  onDoorTriggered?: (doorName: string, success: boolean, message: string) => void;
}
export const DoorsView = memo(function DoorsView({ isDev, onOpenDevLogin, onOpenDoorsSettings, onDoorTriggered }: Props) {
  const [doors, setDoors] = useState<DoorConfig[]>([]);
  const [cloud, setCloud] = useState<CloudStatus>({});
  const [logs, setLogs] = useState<AccessLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const [cameraDoorId, setCameraDoorId] = useState<string | null>(null);
  const sending = useRef(false);
  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await fetch('/api/doors', { signal }).then(readResponse<{ doors: DoorConfig[]; cloud_status: CloudStatus }>);
      if (signal?.aborted) return;
      setDoors(data.doors || []); setCloud(data.cloud_status || {}); setError('');
    } catch (exception) {
      if (!signal?.aborted) setError(exception instanceof Error ? exception.message : 'Falha ao carregar os acessos.');
    } finally { if (!signal?.aborted) setLoading(false); }
  }, []);
  useEffect(() => {
    if (!isDev) return;
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => { void load(controller.signal); }, 8000);
    const refresh = () => { void load(controller.signal); };
    window.addEventListener('doorsUpdated', refresh);
    return () => { controller.abort(); clearInterval(timer); window.removeEventListener('doorsUpdated', refresh); };
  }, [isDev, load]);
  useEffect(() => {
    if (!showHistory || !isDev) return;
    const controller = new AbortController();
    fetch('/api/doors/logs', { signal: controller.signal }).then(readResponse<{ logs: AccessLog[] }>).then(data => setLogs(data.logs || []))
      .catch(exception => { if (!controller.signal.aborted) setError(exception.message); });
    return () => controller.abort();
  }, [showHistory, isDev]);
  const unavailable = (door: DoorConfig) => cloud.global_enabled === false || door.enabled === false || (!isFacialDoor(door) && !cloud.connected);
  const open = async (door: DoorConfig) => {
    if (!isDev || sending.current || unavailable(door)) return;
    sending.current = true; setTriggeringId(door.id); setError(''); setMessage('');
    try {
      await fetch(`/api/doors/${encodeURIComponent(door.id)}/open`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source: 'Painel DEV' }),
      }).then(readResponse);
      const feedback = 'Comando enviado com sucesso.';
      setMessage(`${door.name}: ${feedback}`); onDoorTriggered?.(door.name, true, feedback); void load();
    } catch (exception) {
      const feedback = exception instanceof Error ? exception.message : 'Falha ao enviar o comando.';
      setError(feedback); onDoorTriggered?.(door.name, false, feedback);
    } finally { sending.current = false; setTriggeringId(null); }
  };
  const sync = async () => {
    if (syncing) return;
    setSyncing(true); setError('');
    try {
      const data = await fetch('/api/doors/sync', { method: 'POST' }).then(readResponse<{ doors: DoorConfig[]; cloud_status: CloudStatus }>);
      setDoors(data.doors || []); setCloud(data.cloud_status || {});
    } catch (exception) { setError(exception instanceof Error ? exception.message : 'Falha ao atualizar a conta Tuya.'); }
    finally { setSyncing(false); }
  };
  const cameraDoor = doors.find(door => door.id === cameraDoorId);
  const action = (door: DoorConfig) => <button className="xa-open" type="button" disabled={Boolean(triggeringId) || unavailable(door)} onClick={() => void open(door)}>
    {triggeringId === door.id ? 'Enviando…' : unavailable(door) ? door.enabled === false || cloud.global_enabled === false ? 'Acesso desativado' : 'Tuya desconectada' : openDoorLabel(door)}
  </button>;
  return <section className="xpti-access xa-page" aria-label="Portas e portões"><div className="xa-content">
    <div className="xa-toolbar"><h1>Portas e portões</h1>{isDev && <div className="xa-tools">
      <button type="button" onClick={() => onOpenDoorsSettings()}><Settings />Configurações</button>
      <button type="button" onClick={() => onOpenDoorsSettings('new')}><Plus />Adicionar acesso</button>
    </div>}</div>
    {!isDev ? <div className="xa-empty"><Lock /><h2>Acesso restrito</h2><p>Entre no modo DEV para visualizar e operar os acessos.</p><button className="xa-save" onClick={onOpenDevLogin}>Entrar</button></div>
      : loading ? <p role="status">Carregando acessos…</p>
      : doors.length === 0 ? <div className="xa-empty"><h2>Nenhum acesso cadastrado</h2><p>Adicione uma porta ou portão para começar.</p><button onClick={() => onOpenDoorsSettings('new')}><Plus />Adicionar acesso</button></div>
      : <div className="xa-grid">{doors.map(door => <article className="xa-card" key={door.id}>
        <button type="button" className="xa-camera" aria-label={`Câmera de ${door.name}`} onClick={() => setCameraDoorId(door.id)}>
          {door.camera?.source && door.camera.source !== 'none' && <span className="xa-camera-source">{door.camera.source === 'door' ? 'Câmera do equipamento' : 'Câmera Hikvision'}</span>}
          <DoorCamera doorId={door.id} linked={Boolean(door.camera?.source && door.camera.source !== 'none')} active={!cameraDoorId} />
        </button>
        <div className="xa-caption"><h2>{door.name}</h2><button type="button" className="xa-icon" aria-label={`Configurar ${door.name}`} onClick={() => onOpenDoorsSettings(door.id)}><Settings /></button></div>
        <div className="xa-meta"><span>{isFacialDoor(door) ? 'Facial / biometria' : 'Tuya'}</span>{door.hotkey && <kbd>{door.hotkey}</kbd>}</div>
        {action(door)}
      </article>)}</div>}
    <p className="xa-message" role="status">{message}</p>{error && <p className="xa-error" role="alert">{error}</p>}
    {isDev && <div className="xa-bottom"><span>Conta Tuya {cloud.connected ? 'conectada' : 'desconectada'}{cloud.global_enabled === false ? ' · acionamentos desativados' : ''}</span>
      <div className="xa-tools"><button type="button" className="xa-text" disabled={syncing} onClick={() => void sync()}><RefreshCw />{syncing ? 'Atualizando…' : 'Atualizar Tuya'}</button>
        <button type="button" className="xa-text" onClick={() => setShowHistory(true)}><History />Histórico de acionamentos</button></div>
    </div>}
    {showHistory && isDev && <AccessDialog title="Histórico de acionamentos" onClose={() => setShowHistory(false)}>
      {logs.length ? <table className="xa-history"><tbody>{logs.map(log => <tr key={log.id}><td>{log.date} {log.timestamp}<small>{log.source}</small></td><td>{log.door_name}<small>{log.detail}</small></td><td>{log.success ? 'Enviado' : 'Falhou'}</td></tr>)}</tbody></table> : <p>Nenhum acionamento registrado.</p>}
    </AccessDialog>}
    {cameraDoor && isDev && <AccessDialog title={cameraDoor.name} onClose={() => setCameraDoorId(null)} busy={Boolean(triggeringId)} footer={action(cameraDoor)}>
      <div className="xa-camera-large"><DoorCamera doorId={cameraDoor.id} linked={Boolean(cameraDoor.camera?.source && cameraDoor.camera.source !== 'none')} /></div><button type="button" className="xa-text" onClick={() => { setCameraDoorId(null); onOpenDoorsSettings(cameraDoor.id); }}>Configurar câmera</button>
      <p className="xa-hint">O botão abaixo envia o comando para este acesso.</p>
    </AccessDialog>}
  </div></section>;
});
