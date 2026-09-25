import React, { useState } from 'react';
import { X, Server } from 'lucide-react';

interface AddServerModalProps {
  isOpen: boolean;
  onClose: () => void;
  groups: string[];
  onServerAdded: () => void;
}

export const AddServerModal: React.FC<AddServerModalProps> = ({
  isOpen,
  onClose,
  groups,
  onServerAdded,
}) => {
  const [name, setName] = useState('');
  const [host, setHost] = useState('');
  const [port, setPort] = useState(3389);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [group, setGroup] = useState(groups[0] || 'BEMTEVI');
  const [notes, setNotes] = useState('');
  const [fullscreen, setFullscreen] = useState(true);
  const [adminMode, setAdminMode] = useState(false);
  const [multimon, setMultimon] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !host.trim()) {
      setError('Nome e IP/Host são obrigatórios.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const res = await fetch('http://127.0.0.1:8765/api/servers/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          host: host.trim(),
          port: Number(port) || 3389,
          username: username.trim(),
          password,
          group: group.trim() || 'BEMTEVI',
          notes: notes.trim(),
          fullscreen,
          admin_mode: adminMode,
          multimon,
        }),
      });

      if (!res.ok) {
        throw new Error('Falha ao adicionar servidor');
      }

      onServerAdded();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Erro ao salvar servidor');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 backdrop-blur-xs p-4">
      <div className="bg-[#16171d] border border-[#2e323e] rounded-xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col text-slate-200 animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#262832]">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400">
              <Server className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white leading-tight">Adicionar Novo Servidor</h3>
              <p className="text-[11px] text-[#8e92a0]">Configure as credenciais e parâmetros RDP</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-white hover:bg-[#262832] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4 text-xs">
          {error && (
            <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-medium">
              {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2 space-y-1">
              <label className="text-slate-300 font-semibold">Nome de Exibição *</label>
              <input
                type="text"
                placeholder="Ex: Fraiburgo - ALT"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none"
              />
            </div>

            <div className="space-y-1">
              <label className="text-slate-300 font-semibold">IP ou Host *</label>
              <input
                type="text"
                placeholder="10.189.x.x"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                required
                className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none font-mono"
              />
            </div>

            <div className="space-y-1">
              <label className="text-slate-300 font-semibold">Porta</label>
              <input
                type="number"
                value={port}
                onChange={(e) => setPort(Number(e.target.value))}
                className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none font-mono"
              />
            </div>

            <div className="space-y-1">
              <label className="text-slate-300 font-semibold">Usuário</label>
              <input
                type="text"
                placeholder="Administrador"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none"
              />
            </div>

            <div className="space-y-1">
              <label className="text-slate-300 font-semibold">Senha</label>
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none"
              />
            </div>

            <div className="col-span-2 space-y-1">
              <label className="text-slate-300 font-semibold flex items-center justify-between">
                <span>Grupo / Região</span>
                <span className="text-[10px] text-[#8e92a0]">Selecione ou digite novo</span>
              </label>
              <input
                list="groups-list"
                value={group}
                onChange={(e) => setGroup(e.target.value)}
                placeholder="Ex: BEMTEVI, ALT, UNETVALE..."
                className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none"
              />
              <datalist id="groups-list">
                {groups.map((g) => (
                  <option key={g} value={g} />
                ))}
              </datalist>
            </div>

            <div className="col-span-2 space-y-1">
              <label className="text-slate-300 font-semibold">Observações / Notas</label>
              <textarea
                rows={2}
                placeholder="Informações adicionais, credenciais secundárias..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none resize-none"
              />
            </div>
          </div>

          {/* Opções RDP */}
          <div className="p-3 bg-[#1a1c23] border border-[#262832] rounded-lg flex items-center justify-between gap-2">
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={fullscreen}
                onChange={(e) => setFullscreen(e.target.checked)}
                className="rounded accent-blue-600 w-3.5 h-3.5"
              />
              <span className="text-[11px] text-slate-300">Tela Cheia</span>
            </label>

            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={adminMode}
                onChange={(e) => setAdminMode(e.target.checked)}
                className="rounded accent-blue-600 w-3.5 h-3.5"
              />
              <span className="text-[11px] text-slate-300">Console / Admin</span>
            </label>

            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={multimon}
                onChange={(e) => setMultimon(e.target.checked)}
                className="rounded accent-blue-600 w-3.5 h-3.5"
              />
              <span className="text-[11px] text-slate-300">Multi-Monitor</span>
            </label>
          </div>

          {/* Footer Buttons */}
          <div className="flex items-center justify-end space-x-2 pt-2 border-t border-[#262832]">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-[#262832] hover:bg-[#343644] text-slate-300 text-xs font-semibold transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 rounded-lg bg-[#0066cc] hover:bg-[#0052a3] text-white text-xs font-bold transition-colors disabled:opacity-50"
            >
              {loading ? 'Salvando...' : 'Salvar Servidor'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
