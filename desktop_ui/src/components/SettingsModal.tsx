import React, { useState, useEffect } from 'react';
import { X, Settings, Cloud, Database, Cpu, Info, ShieldCheck, Key, RefreshCw, AlertTriangle } from 'lucide-react';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  serverCount: number;
  isDev: boolean;
  onDevStatusChanged: (isDev: boolean) => void;
  onServersReload: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  serverCount,
  isDev,
  onDevStatusChanged,
  onServersReload,
}) => {
  const [devPassword, setDevPassword] = useState('');
  const [devLoading, setDevLoading] = useState(false);
  const [devError, setDevError] = useState('');
  const [syncLoading, setSyncLoading] = useState(false);
  const [syncMessage, setSyncMessage] = useState('');

  useEffect(() => {
    if (!isOpen) {
      setDevPassword('');
      setDevError('');
      setSyncMessage('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleDevLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!devPassword.trim()) {
      setDevError('Digite a senha de desenvolvedor.');
      return;
    }

    setDevLoading(true);
    setDevError('');

    try {
      const res = await fetch('http://127.0.0.1:8765/api/dev/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: devPassword }),
      });
      const data = await res.json();
      if (data.success) {
        onDevStatusChanged(true);
        setDevPassword('');
      } else {
        setDevError('Senha de desenvolvedor incorreta.');
      }
    } catch (err: any) {
      setDevError('Erro de comunicação com o servidor.');
    } finally {
      setDevLoading(false);
    }
  };

  const handleDevLogout = async () => {
    setDevLoading(true);
    try {
      await fetch('http://127.0.0.1:8765/api/dev/logout', { method: 'POST' });
      onDevStatusChanged(false);
    } catch (err) {
      console.error('Erro ao sair do modo DEV:', err);
    } finally {
      setDevLoading(false);
    }
  };

  const handleManualSync = async () => {
    setSyncLoading(true);
    setSyncMessage('');
    try {
      const res = await fetch('http://127.0.0.1:8765/api/sync/supabase', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        setSyncMessage(`✅ ${data.message || 'Sincronizado com sucesso!'}`);
        onServersReload();
      } else {
        setSyncMessage(`⚠️ ${data.message || 'Falha na sincronização.'}`);
      }
    } catch (err) {
      setSyncMessage('❌ Erro ao conectar ao Supabase.');
    } finally {
      setSyncLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/80 backdrop-blur-xs p-4">
      <div className="bg-[#16171d] border border-[#2e323e] rounded-xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col text-slate-200 animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#262832]">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400">
              <Settings className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white leading-tight">Configurações Gerais</h3>
              <p className="text-[11px] text-[#8e92a0]">Painel Operacional & Nuvem RemoteXPTI</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-white hover:bg-[#262832] transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 text-xs overflow-y-auto max-h-[75vh]">
          {/* Status Geral */}
          <div className="p-3.5 bg-[#1a1c23] border border-[#262832] rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1.5 font-medium">
                <Database className="w-3.5 h-3.5 text-blue-400" /> Servidores Cadastrados:
              </span>
              <span className="font-bold text-white font-mono">{serverCount} servidores</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1.5 font-medium">
                <Cloud className="w-3.5 h-3.5 text-emerald-400" /> Nuvem Supabase:
              </span>
              <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-semibold text-[10px] border border-emerald-500/30">
                Conectado (Sync Ativo)
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1.5 font-medium">
                <Cpu className="w-3.5 h-3.5 text-indigo-400" /> Aceleração:
              </span>
              <span className="font-medium text-slate-300">Microsoft Edge WebView2 (GPU)</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1.5 font-medium">
                <Info className="w-3.5 h-3.5 text-cyan-400" /> Versão da Plataforma:
              </span>
              <span className="font-bold text-white font-mono">
                v1.6.30 {isDev ? <span className="text-emerald-400">[TESTER]</span> : ''}
              </span>
            </div>
          </div>

          {/* Seção Sincronização Supabase */}
          <div className="p-3.5 bg-[#1a1c23] border border-[#262832] rounded-xl space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Cloud className="w-4 h-4 text-blue-400" />
                <span className="font-bold text-white text-xs">Sincronização em Nuvem</span>
              </div>
              <button
                type="button"
                onClick={handleManualSync}
                disabled={syncLoading}
                className="px-3 py-1.5 bg-[#0066cc] hover:bg-[#0052a3] text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50"
              >
                <RefreshCw className={`w-3 h-3 ${syncLoading ? 'animate-spin' : ''}`} />
                <span>{syncLoading ? 'Sincronizando...' : 'Sincronizar com Supabase'}</span>
              </button>
            </div>
            <p className="text-[11px] text-[#8e92a0]">
              Endpoint corporativo oficial: <span className="font-mono text-slate-300">https://rdxrxkoivbzfzncjfrkn.supabase.co</span>
            </p>
            {syncMessage && (
              <div className="p-2 rounded-lg bg-[#14151a] border border-[#2e323e] text-[11px] font-medium text-slate-200">
                {syncMessage}
              </div>
            )}
          </div>

          {/* Seção Modo Desenvolvedor (DEV Login) */}
          <div className="p-3.5 bg-[#1a1c23] border border-[#262832] rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Key className="w-4 h-4 text-amber-400" />
                <span className="font-bold text-white text-xs">Modo Desenvolvedor (DEV)</span>
              </div>
              {isDev && (
                <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold text-[10px] border border-emerald-500/30 flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3" />
                  Ativo (BETA TESTER)
                </span>
              )}
            </div>

            {isDev ? (
              <div className="space-y-2.5">
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  Você está autenticado como <strong>Desenvolvedor / Administrador</strong>. Servidores corporativos criados ou editados são publicados automaticamente para todos os nós da empresa no Supabase.
                </p>
                <button
                  type="button"
                  onClick={handleDevLogout}
                  disabled={devLoading}
                  className="px-3 py-1.5 bg-[#262832] hover:bg-[#343644] text-rose-300 hover:text-rose-200 rounded-lg text-xs font-semibold transition-colors cursor-pointer border border-[#353846]"
                >
                  {devLoading ? 'Encerrando...' : 'Sair do Modo Desenvolvedor'}
                </button>
              </div>
            ) : (
              <form onSubmit={handleDevLogin} className="space-y-2.5">
                <p className="text-[11px] text-[#8e92a0]">
                  Insira a chave mestra de desenvolvedor para desbloquear a edição e publicação de servidores corporativos na nuvem.
                </p>
                {devError && (
                  <div className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-medium flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                    <span>{devError}</span>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <input
                    type="password"
                    placeholder="Senha de Desenvolvedor..."
                    value={devPassword}
                    onChange={(e) => setDevPassword(e.target.value)}
                    className="flex-1 bg-[#1f2129] border border-[#2e323e] focus:border-amber-400 rounded-lg px-3 py-1.5 text-xs text-white outline-none"
                  />
                  <button
                    type="submit"
                    disabled={devLoading}
                    className="px-4 py-1.5 bg-amber-500 hover:bg-amber-600 text-black font-bold rounded-lg text-xs transition-colors cursor-pointer disabled:opacity-50"
                  >
                    {devLoading ? 'Verificando...' : 'Entrar como DEV'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end px-5 py-3 border-t border-[#262832] bg-[#14151a]">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-[#0066cc] hover:bg-[#0052a3] text-white text-xs font-bold transition-colors cursor-pointer"
          >
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
};
