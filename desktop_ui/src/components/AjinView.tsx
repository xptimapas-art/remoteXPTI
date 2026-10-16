import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowDown, ArrowUp, Check, Clock, MapPin, RadioTower, RefreshCw, ScanLine, Search, X } from 'lucide-react';
import { ajinRows, canShowOnMap, filterRows, hasCoordinates, onuStatus, pointName } from './ajin';
import type { AjinScan, AjinTelemetry, ONUItem, Registration, SortField, StatusFilter } from './ajin';
import { CatalogPointDialog, EditOnuDialog, IncidentsDialog, onlineUptime, OnuStatus, ScannerDialog } from './AjinDialogs';
import './Ajin.css';
export type { ONUItem } from './ajin';

interface Props {
  telemetry: AjinTelemetry; connected: boolean;
  onRefresh: () => Promise<AjinTelemetry>;
  onSaveLabel: (port: string, id: string, name: string, desc: string, lat?: number | null, lon?: number | null, notes?: string, mapEnabled?: boolean) => Promise<AjinTelemetry>;
  onDelete: (row: ONUItem) => Promise<AjinTelemetry>;
  onScan: () => Promise<AjinScan>;
  onRegister: (devices: Registration[]) => Promise<void>;
  onLocateOnMap?: (row: ONUItem) => void;
}
const columns: { field: SortField; label: string }[] = [
  {field:'name', label:'Ponto'}, {field:'status', label:'Status'}, {field:'desc', label:'Endereço'}, {field:'uptime', label:'UPTime'},
  {field:'serial', label:'MAC / serial'}, {field:'vendor', label:'Fabricante'}, {field:'port', label:'Porta PON'},
];

function ConsultationClock({ paused, connected }: { paused: boolean; connected: boolean }) {
  const [countdown, setCountdown] = useState<number | null>(null);
  useEffect(() => {
    const tick = (event: Event) => { const detail = (event as CustomEvent<{countdown?: number}>).detail; if (Number.isFinite(detail.countdown)) setCountdown(detail.countdown!); };
    window.addEventListener('ajinTick', tick); return () => window.removeEventListener('ajinTick', tick);
  }, []);
  return <span className="aj-next-query">{paused ? 'Exibição pausada' : !connected ? 'Reconectando ao aplicativo…' : countdown === null ? 'Aguardando próxima consulta' : `Próxima consulta: ${countdown}s`}</span>;
}
const ONURow = memo(function ONURow({ row, onEdit, onMap }: { row: ONUItem; onEdit: (row: ONUItem) => void; onMap?: (row: ONUItem) => void }) {
  const located = canShowOnMap(row);
  const locationAction = located ? 'Ver no mapa' : hasCoordinates(row) ? 'Ativar no mapa' : 'Definir localização';
  return <tr><td className="aj-point"><strong>{pointName(row)}</strong></td><td><OnuStatus row={row} /></td>
    <td className="aj-address" title={row.desc}>{row.desc || '—'}</td><td className="aj-mono" title={row.status_since ? `Desde ${row.status_since}` : undefined}>{onlineUptime(row)}</td>
    <td className="aj-mono">{row.serial || '—'}</td><td>{row.vendor || '—'}</td><td className="aj-mono">{row.port || '—'}</td>
    <td><div className="aj-row-actions"><button type="button" className={located ? 'aj-icon aj-located' : 'aj-icon'}
      title={locationAction} aria-label={`${locationAction}: ${pointName(row)}`} onClick={() => located ? onMap?.(row) : onEdit(row)}><MapPin /></button>
      <button type="button" aria-label={`${row.catalog_number !== undefined ? 'Detalhes' : 'Menu'}: ${pointName(row)}`} aria-haspopup="dialog" onClick={() => onEdit(row)}>{row.catalog_number !== undefined ? 'Detalhes' : 'Menu'}</button></div></td></tr>;
});

export const AjinView = memo(function AjinView({ telemetry, connected, onRefresh, onSaveLabel, onDelete, onScan, onRegister, onLocateOnMap }: Props) {
  const [search, setSearch] = useState(''), [status, setStatus] = useState<StatusFilter>('active');
  const [sort, setSort] = useState<SortField>('name'), [ascending, setAscending] = useState(true);
  const [paused, setPaused] = useState<AjinTelemetry | null>(null), [refreshing, setRefreshing] = useState(false);
  const refreshingRef = useRef(false), mounted = useRef(true), scanRequest = useRef<Promise<void> | null>(null);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [editing, setEditing] = useState<ONUItem | null>(null);
  const [modal, setModal] = useState<'incidents' | 'scanner' | null>(null);
  const [scan, setScan] = useState<AjinScan | null>(null), [scanning, setScanning] = useState(false), [scanError, setScanError] = useState('');
  const data = paused || telemetry;
  const rows = useMemo(() => ajinRows(data), [data]);
  const counts = useMemo(() => rows.reduce((acc, row) => { acc[onuStatus(row)]++; return acc; }, {online:0, offline:0, unknown:0, disabled:0}), [rows]);
  const filtered = useMemo(() => filterRows(rows, search, '', status, sort, ascending), [rows, search, status, sort, ascending]);
  const collected = (data.coleta_formatted || '—').replace(/\s+às\s+/, ' ').split(' ');
  const connection = telemetry.collector?.status || 'connecting', outdated = Boolean(telemetry.stale) || connection !== 'online';
  const activeFilters = Boolean(search || status !== 'active');
  const fetchScan = useCallback((): Promise<void> => {
    if (scanRequest.current) return scanRequest.current;
    setScanning(true);
    const task = (async () => {
      try { const result = await onScan(); if (mounted.current) { setScan(result); setScanError(''); } }
      catch (exception) { if (mounted.current) setScanError(exception instanceof Error ? exception.message : 'Scanner indisponível.'); }
      finally { scanRequest.current = null; if (mounted.current) setScanning(false); }
    })();
    scanRequest.current = task; return task;
  }, [onScan]);
  useEffect(() => { mounted.current = true; void fetchScan(); const timer = window.setInterval(() => void fetchScan(), 30000); return () => { mounted.current = false; window.clearInterval(timer); }; }, [fetchScan]);
  const refresh = async () => {
    if (refreshingRef.current) return;
    refreshingRef.current = true; setRefreshing(true); setError(''); setNotice('');
    try { const snapshot = await onRefresh(); setPaused(current => current ? snapshot : null); setNotice('Últimos dados do coletor recebidos.'); }
    catch (exception) { setError(exception instanceof Error ? exception.message : 'Não foi possível consultar o coletor.'); }
    finally { refreshingRef.current = false; setRefreshing(false); }
  };
  const save = async (row: ONUItem, name: string, desc: string, lat: number | null, lon: number | null, notes: string, mapEnabled: boolean) => {
    const snapshot = await onSaveLabel(row.port, String(row.id), name, desc, lat, lon, notes, mapEnabled);
    setPaused(current => current ? snapshot : null); setNotice('Identificação salva.'); setError('');
  };
  const remove = async (row: ONUItem) => {
    const snapshot = await onDelete(row); setPaused(current => current ? snapshot : null); setNotice('Ponto excluído do monitoramento.'); setError(''); void fetchScan();
  };
  const register = async (devices: Registration[]) => {
    await onRegister(devices); setNotice('Homologação confirmada pelo coletor.');
    try { const snapshot = await onRefresh(); setPaused(current => current ? snapshot : null); }
    catch { setNotice('Homologação confirmada. O inventário será atualizado na próxima consulta ao coletor.'); }
    await fetchScan();
  };
  const newOnus = scan?.devices.filter(row => !row.is_registered).length || 0;
  return <section className="xpti-ajin" aria-label="Monitoramento AJIN">
    <div className="aj-workspace"><section className="aj-main"><div className="aj-inventory"><div className="aj-toolbar">
      <label className="aj-search"><Search /><input aria-label="Buscar ONU" placeholder="Buscar ponto, rua ou MAC…" value={search} onChange={event => setSearch(event.target.value)} /></label>
      <select aria-label="Filtrar status das ONUs" value={status} onChange={event => setStatus(event.target.value as StatusFilter)}><option value="active">Ativados</option><option value="all">Todos</option><option value="online">Online</option><option value="offline">Offline</option><option value="disabled">Desativados</option></select>
      <div className="aj-toolbar-actions"><button type="button" className="aj-primary" onClick={() => void refresh()} disabled={refreshing}><RefreshCw className={refreshing ? 'aj-spinning' : ''} />{refreshing ? 'Consultando…' : 'Atualizar'}</button>
        <button type="button" className="aj-incidents" aria-haspopup="dialog" onClick={() => setModal('incidents')}><AlertTriangle />Incidentes <b>{counts.offline}</b></button>
        <button type="button" className="aj-scanner" aria-haspopup="dialog" onClick={() => { setModal('scanner'); void fetchScan(); }} title={scanError || 'Descoberta de ONUs no coletor'}><ScanLine />Scanner{newOnus > 0 && <b>{newOnus}</b>}</button></div>
      </div>
      {outdated && <div className="aj-banner" role="status"><AlertTriangle /><span>{connection === 'connecting' ? 'Conectando ao coletor AJIN.' : connection === 'unavailable' ? 'Sem conexão com o coletor AJIN.' : 'A coleta está atrasada ou sem data válida.'} {rows.length ? `Exibindo a última coleta salva: ${data.coleta_formatted}.` : 'Aguardando dados dos dispositivos.'}</span></div>}
      {error && <div className="aj-banner aj-error" role="alert"><AlertTriangle /><span>{error}</span><button type="button" className="aj-icon" aria-label="Fechar erro" onClick={() => setError('')}><X /></button></div>}
      <div className="aj-table-scroll" tabIndex={0} aria-label="Tabela de ONUs"><table><thead><tr>{columns.map(column => <th key={column.field} aria-sort={sort === column.field ? ascending ? 'ascending' : 'descending' : 'none'}><button type="button" onClick={() => { if (sort === column.field) setAscending(value => !value); else { setSort(column.field); setAscending(true); } }}>{column.label}{sort === column.field && (ascending ? <ArrowUp /> : <ArrowDown />)}</button></th>)}<th>Ações</th></tr></thead>
        <tbody>{filtered.map(row => <ONURow key={JSON.stringify([row.port, row.id])} row={row} onEdit={setEditing} onMap={onLocateOnMap} />)}
          {!filtered.length && <tr><td colSpan={8} className="aj-empty">{rows.length ? 'Nenhum dispositivo corresponde aos filtros.' : 'Nenhum dispositivo recebido do coletor.'}</td></tr>}</tbody></table></div>
      <footer className="aj-table-footer"><span>Exibindo <b>{filtered.length}</b> de <b>{rows.length}</b> pontos{counts.unknown > 0 && ` · ${counts.unknown} com status desconhecido`}</span>
        {activeFilters && <button type="button" className="aj-text-button" onClick={() => { setSearch(''); setStatus('active'); }}>Limpar filtros</button>}<ConsultationClock paused={Boolean(paused)} connected={connected} /></footer>
      {notice && <div className="aj-notice" role="status" aria-live="polite"><Check /><span>{notice}</span></div>}
    </div></section>
    <aside className="aj-sidebar" aria-label="Painel lateral AJIN"><header><RadioTower /><h2>Visão da rede</h2></header>
      <div className="aj-summary">{[['all','Total de pontos',rows.length],['active','Ativados',counts.online + counts.offline],['disabled','Desativado',counts.disabled],['online','Online',counts.online],['offline','Offline',counts.offline]].map(([value,label,count]) => <button type="button" key={value} aria-pressed={status === value} onClick={() => setStatus(value as StatusFilter)}><span>{label}</span><strong>{count}</strong></button>)}</div>
      <section><h3><Clock />Última coleta</h3><strong className="aj-collection-time">{collected.find(part => /^\d{2}:\d{2}/.test(part)) || '—'}</strong><small>{collected.find(part => part.includes('/')) || 'Sem coleta'}</small></section>
      <section><h3>Servidor coletor</h3><span className={`aj-connection ${outdated || !connected ? 'aj-warning' : ''}`}><i />{!connected ? 'Reconectando ao app' : connection === 'connecting' ? 'Conectando ao coletor' : connection === 'unavailable' ? 'API indisponível' : outdated ? 'Coleta atrasada' : 'Coleta em dia'}</span><code>{telemetry.collector?.endpoint || '—'}</code></section>
      <section><h3>OLT principal</h3><p>{data.olt?.modelo || 'Não informada'}</p><code>{data.olt?.ip || '—'}</code></section>
      <footer><label><input type="checkbox" role="switch" aria-label="Atualização automática da tela AJIN" checked={!paused} onChange={event => setPaused(event.target.checked ? null : telemetry)} />Atualização automática</label><small>Consulta a cada 10 segundos</small></footer>
    </aside></div>
    {editing && (editing.catalog_number !== undefined ? <CatalogPointDialog row={editing} onClose={() => setEditing(null)} /> : <EditOnuDialog row={editing} onSave={save} onDelete={remove} onClose={() => setEditing(null)} />)}
    {modal === 'incidents' && <IncidentsDialog data={data} onClose={() => setModal(null)} />}
    {modal === 'scanner' && <ScannerDialog scan={scan} loading={scanning} error={scanError} onScan={fetchScan} onRegister={register} onClose={() => setModal(null)} />}
  </section>;
});
