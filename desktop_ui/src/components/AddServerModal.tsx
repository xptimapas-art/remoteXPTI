import React, { useEffect, useRef, useState } from 'react';
import { X, Server, ChevronDown, Check, Search, Plus, Eye, EyeOff, MapPin, ChevronRight } from 'lucide-react';
import { ServerGroupManager } from './ServerGroupManager';
import { BRAZIL_STATES, containDialogFocus, emptyServerDraft, parseCoordinate, pastedCoordinates, readServerGroups, serverPayload, serverRequest } from './serverForm';
import type { ServerDraft, ServerGroup } from './serverForm';
import './serverForm.css';

interface Props { isOpen: boolean; onClose: () => void; groups: string[]; onServerAdded: () => void }

export const AddServerModal: React.FC<Props> = ({ isOpen, onClose, groups, onServerAdded }) => {
  return isOpen ? <ServerForm onClose={onClose} groups={groups} onServerAdded={onServerAdded} /> : null;
};

const ServerForm: React.FC<Omit<Props, 'isOpen'>> = ({ onClose, groups, onServerAdded }) => {
  const [draft, setDraft] = useState(() => ({ ...emptyServerDraft(),
    group: groups.includes('BEMTEVI') ? 'BEMTEVI' : groups[0] ?? '' }));
  const [localGroups, setLocalGroups] = useState<{ source: string[]; items: string[] } | null>(null);
  const knownGroups = localGroups?.source === groups ? localGroups.items : groups;
  const [groupOpen, setGroupOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [managing, setManaging] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const submitting = useRef(false);
  const nameInput = useRef<HTMLInputElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const groupBox = useRef<HTMLDivElement>(null);
  const groupTrigger = useRef<HTMLButtonElement>(null);
  const patchDraft = (change: Partial<ServerDraft>) => setDraft(current => ({ ...current, ...change }));
  const changeGroups = (items: ServerGroup[], rename?: { from: string; to: string }, selected?: string) => {
    const names = items.map(item => item.name);
    setLocalGroups({ source: groups, items: names });
    setDraft(current => ({ ...current, group: selected ?? (rename && current.group === rename.from
      ? rename.to : names.includes(current.group) ? current.group : names[0] ?? '') }));
    onServerAdded();
  };
  useEffect(() => {
    if (!managing) nameInput.current?.focus();
  }, [managing]);
  useEffect(() => { if (groupOpen) searchInput.current?.focus(); }, [groupOpen]);
  useEffect(() => {
    if (managing) return;
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !submitting.current) {
        if (groupOpen) { setGroupOpen(false); groupTrigger.current?.focus(); } else onClose();
      }
    };
    const outside = (event: MouseEvent) => {
      if (groupBox.current && !groupBox.current.contains(event.target as Node)) setGroupOpen(false);
    };
    document.addEventListener('keydown', key); document.addEventListener('mousedown', outside);
    return () => { document.removeEventListener('keydown', key); document.removeEventListener('mousedown', outside); };
  }, [managing, groupOpen, onClose]);
  const selectGroup = (name: string) => { patchDraft({ group: name }); setGroupOpen(false); groupTrigger.current?.focus(); };
  const createGroup = async () => {
    if (submitting.current || !query.trim()) return;
    submitting.current = true; setSaving(true); setError('');
    try {
      const data = await serverRequest('/api/groups', 'POST', { name: query.trim() });
      if (data.status !== 'created') throw new Error('O app não confirmou a criação do grupo.');
      const items = readServerGroups(data);
      changeGroups(items, undefined, items.find(item => item.name.toLocaleLowerCase('pt-BR') === query.trim().toLocaleLowerCase('pt-BR'))?.name);
      setGroupOpen(false); setQuery('');
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Não foi possível criar o grupo.'); }
    finally { submitting.current = false; setSaving(false); }
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submitting.current) return;
    setError('');
    try {
      const payload = serverPayload(draft);
      submitting.current = true; setSaving(true);
      const data = await serverRequest('/api/servers/add', 'POST', payload);
      if (data.status !== 'created' || !data.server || typeof data.server !== 'object'
        || !('id' in data.server) || typeof data.server.id !== 'string') {
        throw new Error('O app não confirmou o cadastro. Atualize a lista antes de repetir.');
      }
      onServerAdded(); onClose();
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Não foi possível salvar o servidor.'); }
    finally { submitting.current = false; setSaving(false); }
  };
  const filtered = knownGroups.filter(name => name.toLocaleLowerCase('pt-BR').includes(query.trim().toLocaleLowerCase('pt-BR')));
  const exact = parseCoordinate(draft.latitude, 90) !== null && parseCoordinate(draft.longitude, 180) !== null;
  return <div className="sv-overlay" onKeyDown={containDialogFocus}>
    {managing ? <ServerGroupManager onClose={() => setManaging(false)} onChanged={changeGroups} /> :
    <section className="sv-dialog" role="dialog" aria-modal="true" aria-labelledby="sv-add-title">
      <header className="sv-header"><div><Server size={18} aria-hidden="true" /><h2 id="sv-add-title">Adicionar servidor</h2></div>
        <button type="button" className="sv-icon" aria-label="Fechar" disabled={saving} onClick={onClose}><X size={17} /></button></header>
      <form onSubmit={submit} className="sv-form">
        <fieldset className="sv-fields" disabled={saving}>
          <label className="sv-field sv-name"><span>Nome do servidor <em>*</em></span><input ref={nameInput} value={draft.name} onChange={event => patchDraft({ name: event.target.value })} placeholder="Ex.: Fraiburgo · BEMTEVI" required maxLength={120} /></label>
          <div className="sv-field sv-group" ref={groupBox}>
            <div className="sv-label-row"><span id="sv-group-label">Grupo</span><button type="button" onClick={() => { setGroupOpen(false); setManaging(true); }}>Gerenciar</button></div>
            <button type="button" ref={groupTrigger} className="sv-group-trigger" aria-labelledby="sv-group-label sv-group-value" aria-haspopup="listbox" aria-expanded={groupOpen} onClick={() => { setGroupOpen(!groupOpen); setQuery(''); }}>
              <span id="sv-group-value">{draft.group || 'Selecione um grupo'}</span><ChevronDown size={15} /></button>
            {groupOpen && <div className="sv-group-menu">
              <label className="sv-group-search"><Search size={15} /><input ref={searchInput} aria-label="Buscar ou criar grupo" placeholder="Buscar ou criar grupo…" maxLength={60} value={query} onChange={event => setQuery(event.target.value)}
                onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); const found = knownGroups.find(name => name.toLocaleLowerCase('pt-BR') === query.trim().toLocaleLowerCase('pt-BR')); if (found) selectGroup(found); else if (query.trim()) void createGroup(); } else if (event.key === 'ArrowDown') { event.preventDefault(); groupBox.current?.querySelector<HTMLButtonElement>('[role=option]')?.focus(); } }} /></label>
              <div role="listbox" aria-label="Grupos disponíveis" onKeyDown={event => { if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return; const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('button')]; const index = buttons.indexOf(document.activeElement as HTMLButtonElement); event.preventDefault(); buttons[(index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length]?.focus(); }}>
                {filtered.map(name => <button key={name} type="button" role="option" aria-selected={draft.group === name} onClick={() => selectGroup(name)}>{name}{draft.group === name && <Check size={15} />}</button>)}
              </div>
              {query.trim() && !knownGroups.some(name => name.toLocaleLowerCase('pt-BR') === query.trim().toLocaleLowerCase('pt-BR')) && <button type="button" className="sv-create-group" onClick={() => void createGroup()}><Plus size={15} />Criar grupo “{query.trim()}”</button>}
            </div>}
          </div>
          <label className="sv-field sv-host"><span>IP ou hostname <em>*</em></span><input value={draft.host} onChange={event => patchDraft({ host: event.target.value })} placeholder="Ex.: 192.168.12.10" required maxLength={253} spellCheck={false} /></label>
          <label className="sv-field sv-port"><span>Porta</span><input type="number" min={1} max={65535} required value={draft.port} onChange={event => patchDraft({ port: event.target.value })} /></label>
          <label className="sv-field sv-half"><span>Usuário</span><input value={draft.username} onChange={event => patchDraft({ username: event.target.value })} placeholder={'DOMÍNIO\\usuário'} autoComplete="off" spellCheck={false} /></label>
          <label className="sv-field sv-half"><span>Senha</span><div className="sv-password"><input type={showPassword ? 'text' : 'password'} value={draft.password} onChange={event => patchDraft({ password: event.target.value })} placeholder="Senha do acesso" autoComplete="new-password" /><button type="button" className="sv-icon" aria-label={showPassword ? 'Ocultar senha' : 'Mostrar senha'} aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></label>
          <fieldset className="sv-location"><legend><MapPin size={14} />Localização no mapa <small>Opcional</small></legend>
            <div className="sv-city-row"><label className="sv-field"><span>Cidade</span><input value={draft.city} onChange={event => patchDraft({ city: event.target.value })} placeholder="Ex.: Florianópolis" maxLength={100} /></label>
              <label className="sv-field"><span id="sv-state-label">Estado (UF)</span><select aria-labelledby="sv-state-label" value={draft.state} onChange={event => patchDraft({ state: event.target.value })}><option value="">UF</option>{BRAZIL_STATES.map(uf => <option key={uf}>{uf}</option>)}</select></label></div>
            <p className="sv-location-hint">{exact ? 'Usará as coordenadas informadas, com prioridade sobre cidade/estado.' : draft.city.trim() && draft.state ? 'Será usada uma localização aproximada de ' + draft.city.trim() + '/' + draft.state + '.' : 'Cidade/estado permitem uma localização aproximada no mapa.'}</p>
            <details className="sv-coordinates"><summary><ChevronRight size={14} />Informar coordenadas exatas</summary><div className="sv-coordinate-row">
              <label className="sv-field"><span>Latitude</span><input inputMode="decimal" value={draft.latitude} onChange={event => patchDraft({ latitude: event.target.value })} placeholder="Ex.: -27.5954" onPaste={event => { const pair = pastedCoordinates(event.clipboardData.getData('text')); if (pair) { event.preventDefault(); patchDraft({ latitude: pair[0], longitude: pair[1] }); } }} /></label>
              <label className="sv-field"><span>Longitude</span><input inputMode="decimal" value={draft.longitude} onChange={event => patchDraft({ longitude: event.target.value })} placeholder="Ex.: -48.5480" /></label>
            </div></details>
          </fieldset>
          <label className="sv-field sv-full"><span>Observações <small>Opcional</small></span><textarea rows={2} value={draft.notes} onChange={event => patchDraft({ notes: event.target.value })} placeholder="Informações sobre este servidor" /></label>
        </fieldset>
        <fieldset className="sv-rdp" disabled={saving}><legend>Ao conectar</legend><div>
          <label><input type="checkbox" checked={draft.fullscreen} onChange={event => patchDraft({ fullscreen: event.target.checked })} />Tela cheia</label>
          <label><input type="checkbox" checked={draft.admin_mode} onChange={event => patchDraft({ admin_mode: event.target.checked })} />Console / admin</label>
          <label><input type="checkbox" checked={draft.multimon} onChange={event => patchDraft({ multimon: event.target.checked })} />Vários monitores</label>
        </div></fieldset>
        {error && <p className="sv-error" role="alert">{error}</p>}
        <footer className="sv-footer"><span>* Campos obrigatórios</span><div><button type="button" className="sv-secondary" disabled={saving} onClick={onClose}>Cancelar</button><button type="submit" className="sv-primary" disabled={saving}>{saving ? 'Salvando…' : 'Salvar servidor'}</button></div></footer>
      </form>
    </section>}
  </div>;
};
