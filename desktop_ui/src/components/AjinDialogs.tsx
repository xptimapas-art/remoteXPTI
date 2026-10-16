import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Search, Trash2, X } from 'lucide-react';
import { duration, formatStamp, hasCoordinates, incidentHistory, matchesSearch, onuKey, onuStatus, parseCoordinates, pointName } from './ajin';
import type { AjinScan, AjinTelemetry, DiscoveredONU, ONUItem, Registration } from './ajin';

export const statusLabels = { online:'Online', offline:'Offline', unknown:'Desconhecido', disabled:'Desativado' };
export function OnuStatus({ row }: { row: ONUItem }) {
  const status = onuStatus(row);
  return <span className={`aj-status aj-status-${status}`}><i />{statusLabels[status]}</span>;
}
export const onlineUptime = (row: ONUItem) => onuStatus(row) === 'online' ? row.uptime || '—' : '—';

function Dialog({ title, titleId, className = '', busy, onClose, children, role = 'dialog', descriptionId, initialFocus }: {
  title: string; titleId: string; className?: string; busy?: boolean; onClose: () => void; children: ReactNode;
  role?: 'dialog' | 'alertdialog'; descriptionId?: string; initialFocus?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    if (initialFocus) element?.querySelector<HTMLElement>(initialFocus)?.focus();
    return () => element?.close();
  }, [initialFocus]);
  return <dialog ref={dialog} className={`aj-dialog ${className}`} role={role} aria-labelledby={titleId} aria-describedby={descriptionId}
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header><h2 id={titleId}>{title}</h2><button type="button" className="aj-icon" aria-label="Fechar janela" disabled={busy} onClick={onClose}><X /></button></header>
    {children}
  </dialog>;
}

export function CatalogPointDialog({ row, onClose }: { row: ONUItem; onClose: () => void }) {
  return <Dialog title={`Detalhes · ${pointName(row)}`} titleId="aj-catalog-title" className="aj-edit-dialog" onClose={onClose}>
    <fieldset><div className="aj-readout"><span>Status<OnuStatus row={row} /></span></div>
      <div className="aj-form-grid"><label>Nome do ponto<input readOnly value={pointName(row)} /></label><label>Endereço / referência<input readOnly value={row.desc || ''} /></label></div>
      <div className="aj-coordinate-fields"><label>Latitude<input readOnly value={row.latitude ?? ''} /></label><label>Longitude<input readOnly value={row.longitude ?? ''} /></label></div>
      <p>Sem ONU vinculada. O ponto aparece em amarelo no mapa e não participa dos status online/offline.</p>
    </fieldset><footer><button type="button" onClick={onClose}>Fechar</button></footer>
  </Dialog>;
}

export function EditOnuDialog({ row, onSave, onDelete, onClose }: {
  row: ONUItem; onClose: () => void;
  onSave: (row: ONUItem, name: string, desc: string, lat: number | null, lon: number | null, notes: string, mapEnabled: boolean) => Promise<void>;
  onDelete: (row: ONUItem) => Promise<void>;
}) {
  const busyRef = useRef(false);
  const [name, setName] = useState(pointName(row)), [desc, setDesc] = useState(row.desc || '');
  const [notes, setNotes] = useState(row.notes || '');
  const [mapEnabled, setMapEnabled] = useState(row.map_enabled !== false);
  const [lat, setLat] = useState(row.latitude == null ? '' : String(row.latitude));
  const [lon, setLon] = useState(row.longitude == null ? '' : String(row.longitude));
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [confirmDelete, setConfirmDelete] = useState(false);
  const deleteReadyAt = useRef(0);
  const [deleteCountdown, setDeleteCountdown] = useState(3);
  let coordinatesValid = false;
  try { coordinatesValid = hasCoordinates(parseCoordinates(lat, lon)); } catch { /* Validated on save. */ }
  useEffect(() => {
    if (!confirmDelete) return;
    const remaining = () => Math.max(0, Math.ceil((deleteReadyAt.current - performance.now()) / 1000));
    setDeleteCountdown(remaining());
    const timer = window.setInterval(() => {
      const seconds = remaining();
      setDeleteCountdown(seconds);
      if (seconds === 0) window.clearInterval(timer);
    }, 100);
    return () => window.clearInterval(timer);
  }, [confirmDelete]);
  const run = async (remove: boolean) => {
    if (busyRef.current || (remove && (!confirmDelete || performance.now() < deleteReadyAt.current))) return;
    setError('');
    try {
      const coordinates = remove ? null : parseCoordinates(lat, lon);
      busyRef.current = true; setBusy(true);
      if (remove) await onDelete(row);
      else await onSave(row, name.trim(), desc.trim(), coordinates!.latitude, coordinates!.longitude, notes.trim(), mapEnabled);
      onClose();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'Não foi possível concluir a operação.');
    } finally { busyRef.current = false; setBusy(false); }
  };
  const cancelDeletion = () => { if (!busyRef.current) { setConfirmDelete(false); setError(''); } };
  if (confirmDelete) return <Dialog key="delete" title="Excluir ponto" titleId="aj-delete-title" className="aj-confirm-dialog" role="alertdialog"
    descriptionId="aj-delete-description" initialFocus="[data-cancel-delete]" busy={busy} onClose={cancelDeletion}>
    <div className="aj-confirm-body"><p className="aj-confirm-question">Tem certeza que deseja excluir <strong>{pointName(row)}</strong>?</p>
      <p id="aj-delete-description">O cadastro será removido para todos os clientes. A ONU continuará na rede e poderá aparecer no Scanner para nova homologação.</p>
      {error && <p className="aj-form-error" role="alert">{error}</p>}</div>
    <footer><button type="button" data-cancel-delete onClick={cancelDeletion} disabled={busy}>Cancelar</button>
      <button type="button" className="aj-danger" onClick={() => void run(true)} disabled={busy || deleteCountdown > 0}>{busy ? 'Excluindo…' : deleteCountdown > 0 ? `Sim, excluir ponto (${deleteCountdown}s)` : 'Sim, excluir ponto'}</button></footer>
  </Dialog>;
  return <Dialog key="edit" title={`Configurações · ${pointName(row)}`} titleId="aj-edit-title" className="aj-edit-dialog" busy={busy} onClose={onClose}>
    <form onSubmit={event => { event.preventDefault(); if (!confirmDelete) void run(false); }}>
      <fieldset disabled={busy}>
        <div className="aj-readout"><span>Status<OnuStatus row={row} /></span><span>UPTime<strong>{onlineUptime(row)}</strong></span></div>
        <div className="aj-form-grid"><label>Nome do ponto<input autoFocus value={name} onChange={event => setName(event.target.value)} maxLength={120} /></label>
          <label>Endereço / referência<input value={desc} onChange={event => setDesc(event.target.value)} maxLength={300} /></label></div>
        <div className="aj-device-fields"><label>MAC / serial<input readOnly value={row.serial || '—'} /></label><label>Fabricante<input readOnly value={row.vendor || '—'} /></label>
          <label>Porta PON<input readOnly value={row.port} /></label><label>ID da ONU<input readOnly value={row.id} /></label></div>
        <div className="aj-coordinate-fields"><label>Latitude<input inputMode="decimal" value={lat} onChange={event => setLat(event.target.value)} placeholder="Não informada" /></label>
          <label>Longitude<input inputMode="decimal" value={lon} onChange={event => setLon(event.target.value)} placeholder="Não informada" /></label></div>
        <div className="aj-map-option"><label><input type="checkbox" role="switch" checked={mapEnabled} onChange={event => setMapEnabled(event.target.checked)} />Ativar ponto</label>
          <small>{!coordinatesValid ? 'Aguardando latitude e longitude válidas para aparecer no mapa.' : !mapEnabled ? 'Desativado. Será exibido em amarelo no mapa, sem status online/offline.' : 'Ativo. O mapa mostra o status recebido do coletor.'}</small></div>
        <div className="aj-notes-field"><label htmlFor="aj-point-notes">Observações</label><textarea id="aj-point-notes" value={notes} onChange={event => setNotes(event.target.value)} maxLength={4000} rows={3} placeholder="Informações adicionais sobre este ponto…" /></div>
      </fieldset>
      {error && <p className="aj-form-error" role="alert">{error}</p>}
      <footer><button type="button" className="aj-delete" onClick={() => { deleteReadyAt.current = performance.now() + 3000; setDeleteCountdown(3); setConfirmDelete(true); setError(''); }} disabled={busy}><Trash2 />Excluir ponto</button>
        <div className="aj-footer-actions"><button type="button" onClick={onClose} disabled={busy}>Cancelar</button>
          <button type="submit" className="aj-primary" disabled={busy}>{busy ? 'Salvando…' : 'Salvar alterações'}</button></div></footer>
    </form>
  </Dialog>;
}

export function IncidentsDialog({ data, onClose }: { data: AjinTelemetry; onClose: () => void }) {
  const [search, setSearch] = useState('');
  const history = useMemo(() => incidentHistory(data), [data]);
  const labels = {open:'Em aberto', resolved:'Resolvido', unconfirmed:'Sem confirmação'};
  const filtered = history.filter(item => matchesSearch(search, [item.name, item.address, item.port, item.serial, labels[item.status]]));
  const open = filtered.filter(item => item.status === 'open').length, resolved = filtered.filter(item => item.status === 'resolved').length;
  return <Dialog title="Incidentes" titleId="aj-incidents-title" className="aj-wide-dialog" onClose={onClose}>
    <div className="aj-dialog-toolbar"><label className="aj-search"><Search /><input autoFocus aria-label="Buscar incidente" placeholder="Buscar ponto, endereço ou incidente…" value={search} onChange={event => setSearch(event.target.value)} /></label></div>
    <div className="aj-dialog-table"><table aria-label="Lista de incidentes"><thead><tr><th>Início</th><th>Ponto</th><th>Incidente</th><th>Status</th><th>Recuperação</th><th>Duração</th></tr></thead>
      <tbody>{filtered.map(item => <tr key={item.key}><td className="aj-mono">{formatStamp(item.opened)}</td><td title={[item.address, item.port, item.serial].filter(Boolean).join(' · ')}>{item.name}</td>
        <td>ONU sem comunicação</td><td><span className={`aj-event-state aj-event-${item.status}`}><i />{labels[item.status]}</span></td>
        <td className="aj-mono">{formatStamp(item.recovered)}</td><td className="aj-mono">{duration(item.durationSeconds) !== '—' ? duration(item.durationSeconds) : item.durationLabel || '—'}</td></tr>)}
        {!filtered.length && <tr><td colSpan={6} className="aj-empty">{history.length ? 'Nenhum incidente corresponde à busca.' : 'Nenhum incidente informado pelo coletor.'}</td></tr>}</tbody></table></div>
    <footer><span className="aj-dialog-summary">{filtered.length} incidentes · {open} em aberto · {resolved} resolvidos{filtered.length > open + resolved && ` · ${filtered.length - open - resolved} sem confirmação`}
      {data.stale && <small>Exibindo a última coleta salva; o estado atual não está confirmado.</small>}</span><button type="button" onClick={onClose}>Fechar</button></footer>
  </Dialog>;
}

const scanKey = (row: DiscoveredONU) => JSON.stringify([onuKey(row), row.serial]);
export function ScannerDialog({ scan, loading, error, onScan, onRegister, onClose }: {
  scan: AjinScan | null; loading: boolean; error: string; onScan: () => Promise<void>;
  onRegister: (devices: Registration[]) => Promise<void>; onClose: () => void;
}) {
  const [search, setSearch] = useState(''), [filter, setFilter] = useState('new'), [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false), busyRef = useRef(false), [actionError, setActionError] = useState(''), [notice, setNotice] = useState('');
  const selectAll = useRef<HTMLInputElement>(null);
  const devices = scan?.devices || [];
  const visible = devices.filter(row => (filter === 'all' || row.is_registered === (filter === 'registered')) && matchesSearch(search, [row.serial, row.point_name, row.street_desc, row.port, row.vendor, row.id]));
  const eligible = visible.filter(row => !row.is_registered && row.serial), selectedDevices = devices.filter(row => !row.is_registered && row.serial && selected.has(scanKey(row)));
  const all = eligible.length > 0 && eligible.every(row => selected.has(scanKey(row))), partial = !all && eligible.some(row => selected.has(scanKey(row)));
  useEffect(() => { if (selectAll.current) selectAll.current.indeterminate = partial; }, [partial]);
  const register = async (event: FormEvent) => {
    event.preventDefault(); if (busyRef.current || loading || error || !selectedDevices.length) return;
    busyRef.current = true; setBusy(true); setActionError(''); setNotice('');
    try {
      await onRegister(selectedDevices.map(row => ({port:row.port, id:String(row.id), serial:row.serial!, name:row.point_name || `Ponto ${row.id}`, desc:row.street_desc || row.desc || ''})));
      setNotice(`${selectedDevices.length} ONU(s) homologada(s).`); setSelected(new Set());
    } catch (exception) { setActionError(exception instanceof Error ? exception.message : 'Não foi possível homologar as ONUs.'); }
    finally { busyRef.current = false; setBusy(false); }
  };
  return <Dialog title="Scanner de ONUs" titleId="aj-scanner-title" className="aj-wide-dialog" busy={busy} onClose={onClose}>
    <form onSubmit={register}>
      <div className="aj-dialog-toolbar"><div className="aj-discovery-total">Novas ONUs <strong>{scan ? devices.filter(row => !row.is_registered).length : '—'}</strong></div>
        <button type="button" disabled={loading || busy} onClick={() => { setNotice(''); void onScan(); }}><RefreshCw className={loading ? 'aj-spinning' : ''} />{loading ? 'Consultando…' : 'Re-escanear'}</button>
        <label className="aj-search"><Search /><input aria-label="Filtrar descoberta" value={search} onChange={event => setSearch(event.target.value)} placeholder="Filtrar por MAC, serial ou porta…" /></label></div>
      <div className="aj-scan-tabs" aria-label="Cadastro das ONUs">{[['new','Não cadastradas'],['all','Todas'],['registered','Cadastradas']].map(([value,label]) => <button type="button" key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div>
      {(error || actionError) && <p className="aj-form-error aj-scan-error" role="alert"><AlertTriangle />{actionError || error}</p>}
      {notice && <p className="aj-scan-notice" role="status">{notice}</p>}
      <div className="aj-dialog-table"><table aria-label="Descoberta de ONUs"><thead><tr><th><input ref={selectAll} type="checkbox" aria-label="Selecionar todas as novas ONUs visíveis" checked={all} disabled={busy || loading || !eligible.length}
        onChange={event => { const checked = event.target.checked; setSelected(current => { const next = new Set(current); for (const row of eligible) { if (checked) next.add(scanKey(row)); else next.delete(scanKey(row)); } return next; }); }} /></th>
        <th>ID ONU</th><th>MAC / serial</th><th>Status</th><th>Porta PON</th><th>Fabricante</th><th>Cadastro</th></tr></thead>
        <tbody>{visible.map(row => <tr key={onuKey(row)} className={selected.has(scanKey(row)) ? 'aj-selected-row' : ''}>
          <td><input type="checkbox" aria-label={`Selecionar ONU ${row.id} · ${row.port}`} checked={!row.is_registered && selected.has(scanKey(row))} disabled={busy || loading || row.is_registered || !row.serial}
            onChange={event => { const checked = event.target.checked; setSelected(current => { const next = new Set(current); if (checked) next.add(scanKey(row)); else next.delete(scanKey(row)); return next; }); }} /></td>
          <td className="aj-mono">{row.id}</td><td className="aj-mono">{row.serial || '—'}</td><td><OnuStatus row={row} /></td><td className="aj-mono">{row.port}</td><td>{row.vendor || '—'}</td><td>{row.is_registered ? 'Cadastrada' : 'Novo'}</td></tr>)}
          {!visible.length && <tr><td colSpan={7} className="aj-empty">{loading && !scan ? 'Consultando descoberta no coletor…' : !scan ? 'A descoberta ainda não está disponível. Tente re-escanear.' : 'Nenhuma ONU corresponde ao filtro.'}</td></tr>}</tbody></table></div>
      <footer><span className="aj-dialog-summary" aria-live="polite">{selectedDevices.length} ONU(s) selecionada(s)</span><div className="aj-footer-actions"><button type="button" onClick={onClose} disabled={busy}>Fechar</button>
        <button type="submit" className="aj-primary" disabled={busy || loading || Boolean(error) || !selectedDevices.length}>{busy ? 'Homologando…' : 'Homologar selecionadas'}</button></div></footer>
    </form>
  </Dialog>;
}
