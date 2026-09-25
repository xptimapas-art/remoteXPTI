import React, { useState, useEffect } from 'react';
import { X, Server, Trash2, Play, Eye, EyeOff, Check, AlertCircle } from 'lucide-react';

interface EditServerModalProps {
  serverId: string | null;
  isOpen: boolean;
  onClose: () => void;
  groups: string[];
  onServerUpdated: () => void;
  onConnect: (serverId: string) => void;
}

export const EditServerModal: React.FC<EditServerModalProps> = ({
  serverId,
  isOpen,
  onClose,
  groups,
  onServerUpdated,
  onConnect,
}) => {
  const [name, setName] = useState('');
  const [host, setHost] = useState('');
  const [port, setPort] = useState(3389);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [group, setGroup] = useState('BEMTEVI');
  const [notes, setNotes] = useState('');
  const [fullscreen, setFullscreen] = useState(true);
  const [adminMode, setAdminMode] = useState(false);
  const [multimon, setMultimon] = useState(false);
  const [latitude, setLatitude] = useState<string>('');
  const [longitude, setLongitude] = useState<string>('');

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Carrega os dados reais do servidor com senha descriptografada
  useEffect(() => {
    if (!isOpen || !serverId) return;

    setLoading(true);
    setError('');
    setConfirmDelete(false);

    fetch(`http://127.0.0.1:8765/api/servers/${serverId}`)
      .then((res) => {
        if (!res.ok) throw new Error('Não foi possível carregar os dados do servidor');
        return res.json();
      })
      .then((data) => {
        setName(data.name || '');
        setHost(data.host || '');
        setPort(data.port || 3389);
        setUsername(data.username || '');
        setPassword(data.password_plain || '');
        setGroup(data.group || 'BEMTEVI');
        setNotes(data.notes || '');
        setFullscreen(data.fullscreen !== false);
        setAdminMode(Boolean(data.admin_mode));
        setMultimon(Boolean(data.multimon));
        setLatitude(data.latitude !== undefined && data.latitude !== null ? String(data.latitude) : '');
        setLongitude(data.longitude !== undefined && data.longitude !== null ? String(data.longitude) : '');
      })
      .catch((err) => {
        setError(err.message || 'Erro ao carregar dados');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [isOpen, serverId]);

  if (!isOpen || !serverId) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !host.trim()) {
      setError('Nome e IP/Host são obrigatórios.');
      return;
    }

    setSaving(true);
    setError('');

    try {
      const res = await fetch(`http://127.0.0.1:8765/api/servers/${serverId}`, {
        method: 'PUT',
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
          latitude: latitude.trim() ? parseFloat(latitude) : null,
          longitude: longitude.trim() ? parseFloat(longitude) : null,
        }),
      });

      if (!res.ok) {
        throw new Error('Falha ao salvar alterações');
      }

      onServerUpdated();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Erro ao salvar alterações');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }

    setSaving(true);
    try {
      const res = await fetch(`http://127.0.0.1:8765/api/servers/${serverId}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error('Falha ao excluir servidor');
      onServerUpdated();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Erro ao excluir');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/80 backdrop-blur-xs p-4">
      <div className="bg-[#16171d] border border-[#2e323e] rounded-xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col text-slate-200 animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#262832]">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400">
              <Server className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white leading-tight">
                Editar Credenciais & Servidor
              </h3>
              <p className="text-[11px] text-[#8e92a0]">
                Atualize credenciais RDP e parâmetros de conexão
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-white hover:bg-[#262832] transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        {loading ? (
          <div className="p-12 flex flex-col items-center justify-center text-slate-400 space-y-2">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-xs">Carregando credenciais...</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-5 space-y-4 text-xs">
            {error && (
              <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-medium flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
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
                <label className="text-slate-300 font-semibold">Porta RDP</label>
                <input
                  type="number"
                  value={port}
                  onChange={(e) => setPort(Number(e.target.value))}
                  className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none font-mono"
                />
              </div>

              <div className="space-y-1">
                <label className="text-slate-300 font-semibold">Usuário RDP</label>
                <input
                  type="text"
                  placeholder="Administrador"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none"
                />
              </div>

              <div className="space-y-1">
                <label className="text-slate-300 font-semibold">Senha RDP</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg pl-3 pr-9 py-2 text-white outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="col-span-2 space-y-1">
                <label className="text-slate-300 font-semibold flex items-center justify-between">
                  <span>Grupo / Região</span>
                  <span className="text-[10px] text-[#8e92a0]">Selecione ou digite</span>
                </label>
                <input
                  list="edit-groups-list"
                  value={group}
                  onChange={(e) => setGroup(e.target.value)}
                  placeholder="Ex: BEMTEVI, ALT, UNETVALE..."
                  className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none"
                />
                <datalist id="edit-groups-list">
                  {groups.map((g) => (
                    <option key={g} value={g} />
                  ))}
                </datalist>
              </div>

              <div className="col-span-2 space-y-1">
                <label className="text-slate-300 font-semibold">Observações / Notas</label>
                <textarea
                  rows={2}
                  placeholder="Informações adicionais..."
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none resize-none"
                />
              </div>

              <div className="space-y-1">
                <label className="text-slate-300 font-semibold flex items-center justify-between">
                  <span>Latitude</span>
                  <span className="text-[10px] text-[#8e92a0]">Opcional (Mapa)</span>
                </label>
                <input
                  type="text"
                  placeholder="Ex: -27.1394"
                  value={latitude}
                  onChange={(e) => setLatitude(e.target.value)}
                  className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none font-mono text-xs"
                />
              </div>

              <div className="space-y-1">
                <label className="text-slate-300 font-semibold flex items-center justify-between">
                  <span>Longitude</span>
                  <span className="text-[10px] text-[#8e92a0]">Opcional (Mapa)</span>
                </label>
                <input
                  type="text"
                  placeholder="Ex: -48.5144"
                  value={longitude}
                  onChange={(e) => setLongitude(e.target.value)}
                  className="w-full bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-lg px-3 py-2 text-white outline-none font-mono text-xs"
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

            {/* Footer com Ações */}
            <div className="flex items-center justify-between pt-2 border-t border-[#262832]">
              {/* Botão de Excluir */}
              <button
                type="button"
                onClick={handleDelete}
                className={`px-3 py-2 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer ${
                  confirmDelete
                    ? 'bg-rose-600 hover:bg-rose-700 text-white animate-pulse'
                    : 'bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30'
                }`}
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>{confirmDelete ? 'Confirmar Exclusão?' : 'Excluir'}</span>
              </button>

              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  onClick={() => {
                    onConnect(serverId);
                    onClose();
                  }}
                  className="px-3 py-2 rounded-lg bg-[#262832] hover:bg-[#343644] text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <Play className="w-3.5 h-3.5 fill-current text-blue-400" />
                  <span>Testar RDP</span>
                </button>

                <button
                  type="submit"
                  disabled={saving}
                  className="px-5 py-2 rounded-lg bg-[#0066cc] hover:bg-[#0052a3] text-white text-xs font-bold flex items-center gap-1.5 transition-colors disabled:opacity-50 cursor-pointer shadow-sm"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>{saving ? 'Salvando...' : 'Salvar Alterações'}</span>
                </button>
              </div>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
