import { useEffect, useRef, useState } from 'react';
import { Check, Folders, Info, Pencil, Plus, Trash2, X } from 'lucide-react';
import { readServerGroups, serverRequest } from './serverForm';
import type { ServerGroup } from './serverForm';

interface Props {
  onClose: () => void;
  onChanged: (groups: ServerGroup[], rename?: { from: string; to: string }, selected?: string) => void;
}
export function ServerGroupManager({ onClose, onChanged }: Props) {
  const [groups, setGroups] = useState<ServerGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [name, setName] = useState('');
  const [editing, setEditing] = useState<{ from: string; to: string } | null>(null);
  const [deleting, setDeleting] = useState<ServerGroup | null>(null);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const newInput = useRef<HTMLInputElement>(null);
  const editInput = useRef<HTMLInputElement>(null);
  const cancelDelete = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    let active = true;
    serverRequest('/api/groups').then(data => { if (active) setGroups(readServerGroups(data)); })
      .catch(caught => { if (active) setError(caught instanceof Error ? caught.message : 'Não foi possível carregar os grupos.'); })
      .finally(() => { if (active) { setLoading(false); newInput.current?.focus(); } });
    return () => { active = false; };
  }, []);
  const editingName = editing?.from;
  useEffect(() => { if (editingName) { editInput.current?.focus(); editInput.current?.select(); } }, [editingName]);
  useEffect(() => { if (!loading) newInput.current?.focus(); }, [loading]);
  useEffect(() => { if (deleting) cancelDelete.current?.focus(); }, [deleting]);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || pending.current) return;
      if (deleting) setDeleting(null); else if (editing) setEditing(null); else onClose();
    };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, [deleting, editing, onClose]);

  const mutate = async (method: string, body: { name: string; new_name?: string }) => {
    if (pending.current) return;
    if (method !== 'DELETE' && !(body.new_name ?? body.name).trim()) { setError('Informe o nome do grupo.'); return; }
    pending.current = true; setBusy(true); setError(''); setFeedback('');
    try {
      const data = await serverRequest('/api/groups', method, body);
      const expected = method === 'POST' ? 'created' : method === 'PUT' ? 'updated' : 'deleted';
      if (data.status !== expected) throw new Error('O app não confirmou a alteração. Atualize antes de repetir.');
      const items = readServerGroups(data);
      setGroups(items);
      onChanged(items, method === 'PUT' ? { from: body.name, to: body.new_name!.trim() } : undefined,
        method === 'POST' ? body.name.trim() : undefined);
      setName(''); setEditing(null); setDeleting(null);
      setFeedback(method === 'POST' ? 'Grupo criado.' : method === 'PUT' ? 'Grupo renomeado.' : 'Grupo excluído.');
    } catch (caught) {
      setDeleting(null);
      setError(caught instanceof Error ? caught.message : 'Não foi possível salvar a alteração.');
      try { setGroups(readServerGroups(await serverRequest('/api/groups'))); } catch { /* Preserve the displayed list on a failed refresh. */ }
    } finally { pending.current = false; setBusy(false); }
  };
  return <section className="sv-dialog sv-groups" role="dialog" aria-modal="true" aria-labelledby="sv-groups-title">
    <header className="sv-header"><div><Folders size={18} /><h2 id="sv-groups-title">Grupos de servidores</h2></div><button type="button" className="sv-icon" disabled={busy || Boolean(deleting)} aria-label="Voltar ao cadastro" onClick={onClose}><X size={17} /></button></header>
    <div className="sv-groups-body" inert={Boolean(deleting)}>
      <fieldset disabled={busy || loading} className="sv-group-fields">
        <div className="sv-new-group"><label className="sv-field"><span>Novo grupo</span><input ref={newInput} value={name} onChange={event => setName(event.target.value)} maxLength={60} placeholder="Nome do grupo" onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); void mutate('POST', { name: name.trim() }); } }} /></label>
          <button type="button" className="sv-secondary" onClick={() => void mutate('POST', { name: name.trim() })}><Plus size={15} />Criar grupo</button></div>
        {loading ? <p className="sv-hint" role="status">Carregando grupos…</p> : <>
          <div className="sv-group-head"><span>Grupo</span><span>Servidores</span><span>Ações</span></div>
          <ul className="sv-group-list">{groups.map(item => <li key={item.name} className={editing?.from === item.name ? 'sv-group-row sv-edit-row' : 'sv-group-row'}>
            {editing?.from === item.name ? <>
              <label className="sv-field"><span className="sr-only">Novo nome do grupo</span><input aria-label="Novo nome do grupo" ref={editInput} value={editing.to} maxLength={60} onChange={event => setEditing({ from: item.name, to: event.target.value })} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); void mutate('PUT', { name: editing.from, new_name: editing.to.trim() }); } }} /><small>Mantém os servidores neste grupo.</small></label>
              <div className="sv-row-actions"><button type="button" className="sv-icon" aria-label="Salvar nome" onClick={() => void mutate('PUT', { name: editing.from, new_name: editing.to.trim() })}><Check size={17} /></button><button type="button" className="sv-icon" aria-label="Cancelar edição" onClick={() => setEditing(null)}><X size={17} /></button></div>
            </> : <>
              <strong>{item.name}</strong><span className="sv-count">{item.server_count}</span>
              <div className="sv-row-actions"><button type="button" className="sv-icon" disabled={!item.rename_allowed} title={!item.rename_allowed ? 'No DEV, este grupo da empresa é somente leitura.' : 'Renomear grupo'} aria-label={'Renomear ' + item.name} onClick={() => { setError(''); setEditing({ from: item.name, to: item.name }); }}><Pencil size={16} /></button><button type="button" className="sv-icon sv-delete" disabled={!item.delete_allowed} title={!item.delete_allowed ? 'Mova os servidores antes de excluir o grupo.' : 'Excluir grupo'} aria-label={'Excluir ' + item.name} onClick={() => { setError(''); setDeleting(item); }}><Trash2 size={16} /></button></div>
            </>}
          </li>)}</ul>
        </>}
      </fieldset>
      <p className="sv-group-rule"><Info size={15} />Somente grupos vazios podem ser excluídos.</p>
      {groups.some(item => !item.rename_allowed) && <p className="sv-hint">Grupos usados por servidores da empresa são somente leitura no DEV.</p>}
      {error && <p className="sv-error" role="alert">{error}</p>}
      <footer className="sv-footer"><span role="status" aria-live="polite">{feedback}</span><button type="button" className="sv-primary" disabled={busy} onClick={onClose}>Concluir</button></footer>
    </div>
    {deleting && <div className="sv-delete-layer"><section role="alertdialog" className="sv-delete-box" aria-modal="true" aria-labelledby="sv-delete-title" aria-describedby="sv-delete-description">
      <h3 id="sv-delete-title">Excluir grupo?</h3><p id="sv-delete-description">O grupo “{deleting.name}” está vazio e será excluído.</p>
      <div><button ref={cancelDelete} type="button" className="sv-secondary" disabled={busy} onClick={() => setDeleting(null)}>Cancelar</button><button type="button" className="sv-primary" disabled={busy} onClick={() => void mutate('DELETE', { name: deleting.name })}>{busy ? 'Excluindo…' : 'Excluir grupo'}</button></div>
    </section></div>}
  </section>;
}
