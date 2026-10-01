import React, { useState, useEffect } from 'react';
import {
  X,
  Settings,
  Cloud,
  Database,
  Cpu,
  Info,
  ShieldCheck,
  Key,
  RefreshCw,
  AlertTriangle,
  ArrowDownCircle,
  Rocket,
  CheckCircle2,
  Radio,
} from 'lucide-react';

interface UpdateInfo {
  currentVersion: string;
  newVersion: string;
  updateReady: boolean;
  isChecking: boolean;
  isDownloading: boolean;
  channel: string;
  statusMessage: string;
}

interface ReleaseItem {
  tag: string;
  name: string;
  published: string;
  is_public: boolean;
  is_prerelease: boolean;
  channel_label: string;
  download_url: string;
}

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  serverCount: number;
  isDev: boolean;
  onDevStatusChanged: (isDev: boolean) => void;
  onServersReload: () => void;
  updateInfo?: UpdateInfo;
  onCheckUpdates?: () => void;
  onRestartUpdate?: () => void;
  onChannelChange?: (channel: string) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  serverCount,
  isDev,
  onDevStatusChanged,
  onServersReload,
  updateInfo,
  onCheckUpdates,
  onRestartUpdate,
  onChannelChange,
}) => {
  const [devPassword, setDevPassword] = useState('');
  const [devLoading, setDevLoading] = useState(false);
  const [devError, setDevError] = useState('');
  const [syncLoading, setSyncLoading] = useState(false);
  const [syncMessage, setSyncMessage] = useState('');

  // Estados do Seletor de Versões do GitHub (Modo DEV)
  const [releases, setReleases] = useState<ReleaseItem[]>([]);
  const [loadingReleases, setLoadingReleases] = useState(false);
  const [selectedTag, setSelectedTag] = useState('');
  const [installingVersion, setInstallingVersion] = useState(false);
  const [installStatus, setInstallStatus] = useState('');

  useEffect(() => {
    if (!isOpen) {
      setDevPassword('');
      setDevError('');
      setSyncMessage('');
      setInstallStatus('');
    } else if (isDev && releases.length === 0) {
      fetchReleasesList();
    }
  }, [isOpen, isDev]);

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
        fetchReleasesList();
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

  const fetchReleasesList = async () => {
    setLoadingReleases(true);
    try {
      const res = await fetch('http://127.0.0.1:8765/api/update/releases');
      if (res.ok) {
        const data = await res.json();
        const list: ReleaseItem[] = data.releases || [];
        setReleases(list);
        if (list.length > 0 && !selectedTag) {
          setSelectedTag(list[0].tag);
        }
      }
    } catch (err) {
      console.error('Erro ao listar releases:', err);
    } finally {
      setLoadingReleases(false);
    }
  };

  const handleInstallSelectedVersion = async () => {
    if (!selectedTag) return;
    const target = releases.find((r) => r.tag === selectedTag);
    if (!target) return;

    if (!confirm(`Deseja baixar e instalar a versão ${selectedTag}?\nO aplicativo será reiniciado para aplicar a versão selecionada.`)) {
      return;
    }

    setInstallingVersion(true);
    setInstallStatus(`⬇️ Baixando ${selectedTag}...`);
    try {
      const res = await fetch('http://127.0.0.1:8765/api/update/install_version', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag: target.tag, download_url: target.download_url }),
      });
      if (res.ok) {
        setInstallStatus(`✅ Download iniciado! Acompanhe o progresso ou aguarde a reinicialização.`);
      } else {
        setInstallStatus(`❌ Falha ao iniciar download de ${selectedTag}.`);
      }
    } catch (err) {
      setInstallStatus(`❌ Erro de comunicação com o servidor.`);
    } finally {
      setInstallingVersion(false);
    }
  };

  const activeChannel = updateInfo?.channel || (isDev ? 'beta_tester' : 'public');

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
              <span className="font-bold text-white font-mono flex items-center gap-1.5">
                v{updateInfo?.currentVersion || '1.6.30'}
                {isDev ? (
                  <span className="text-emerald-400 font-sans text-[10px] bg-emerald-950/80 border border-emerald-800/60 px-1.5 py-0.2 rounded font-bold">
                    [BETA TESTER]
                  </span>
                ) : (
                  <span className="text-blue-300 font-sans text-[10px] bg-blue-950/80 border border-blue-800/60 px-1.5 py-0.2 rounded font-bold">
                    [PÚBLICO]
                  </span>
                )}
              </span>
            </div>
          </div>

          {/* Seção Sistema de Atualizações (Auto-Update) */}
          <div className="p-3.5 bg-[#1a1c23] border border-[#262832] rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Rocket className="w-4 h-4 text-cyan-400" />
                <span className="font-bold text-white text-xs">Atualizações do Sistema</span>
              </div>
              <button
                type="button"
                onClick={onCheckUpdates}
                disabled={updateInfo?.isChecking || updateInfo?.isDownloading}
                className="px-3 py-1.5 bg-[#1f2432] hover:bg-[#2b3346] text-cyan-300 hover:text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer border border-cyan-500/30 disabled:opacity-50"
              >
                <RefreshCw
                  className={`w-3 h-3 ${updateInfo?.isChecking || updateInfo?.isDownloading ? 'animate-spin text-cyan-400' : ''}`}
                />
                <span>
                  {updateInfo?.isChecking
                    ? 'Verificando...'
                    : updateInfo?.isDownloading
                    ? 'Baixando...'
                    : 'Verificar Atualizações'}
                </span>
              </button>
            </div>

            {/* Mensagem de Status do Updater */}
            {updateInfo?.statusMessage && (
              <div className="p-2 rounded-lg bg-[#14151a] border border-[#2e323e] text-[11px] text-slate-300 flex items-center gap-2">
                {updateInfo.updateReady ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                ) : updateInfo.isDownloading ? (
                  <ArrowDownCircle className="w-3.5 h-3.5 text-cyan-400 shrink-0 animate-bounce" />
                ) : (
                  <Info className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                )}
                <span>{updateInfo.statusMessage}</span>
              </div>
            )}

            {/* Card de Atualização Pronta */}
            {updateInfo?.updateReady && (
              <div className="p-3 rounded-lg bg-blue-950/40 border border-blue-500/40 flex items-center justify-between gap-3 animate-in fade-in duration-150">
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-white flex items-center gap-1.5">
                    <span>🚀</span> Nova versão v{updateInfo.newVersion} pronta!
                  </span>
                  <span className="text-[10px] text-blue-200 mt-0.5">
                    Reinicie agora para aplicar as melhorias e novos recursos.
                  </span>
                </div>
                <button
                  type="button"
                  onClick={onRestartUpdate}
                  className="px-3 py-1.5 bg-[#0066cc] hover:bg-[#0052a3] text-white rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all shadow-md cursor-pointer shrink-0"
                >
                  <RefreshCw className="w-3 h-3" />
                  <span>Reiniciar Agora</span>
                </button>
              </div>
            )}
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

          {/* Seção Modo Desenvolvedor (DEV Login & Opções Avançadas) */}
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
              <div className="space-y-3.5">
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  Você está autenticado como <strong>Desenvolvedor / Administrador</strong>. Servidores corporativos criados ou editados são publicados automaticamente para todos os nós da empresa no Supabase.
                </p>

                {/* 1. Seletor de Canal de Atualização */}
                <div className="p-2.5 rounded-lg bg-[#14151a] border border-[#262832] space-y-2">
                  <span className="text-[11px] font-bold text-slate-300 flex items-center gap-1.5">
                    <Radio className="w-3.5 h-3.5 text-cyan-400" /> Canal de Atualização:
                  </span>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => onChannelChange?.('public')}
                      className={`py-1.5 px-2 rounded-lg text-xs font-semibold border transition-all cursor-pointer ${
                        activeChannel === 'public'
                          ? 'bg-blue-600 border-blue-400 text-white shadow-sm'
                          : 'bg-[#1a1c23] border-[#2e323e] text-slate-400 hover:text-white'
                      }`}
                    >
                      Público (1.x.0)
                    </button>
                    <button
                      type="button"
                      onClick={() => onChannelChange?.('beta_tester')}
                      className={`py-1.5 px-2 rounded-lg text-xs font-semibold border transition-all cursor-pointer ${
                        activeChannel === 'beta_tester'
                          ? 'bg-emerald-600 border-emerald-400 text-white shadow-sm'
                          : 'bg-[#1a1c23] border-[#2e323e] text-slate-400 hover:text-white'
                      }`}
                    >
                      Beta Tester (1.x.y)
                    </button>
                  </div>
                </div>

                {/* 2. Seletor de Versões do GitHub (Rollback / Build Específico) */}
                <div className="p-2.5 rounded-lg bg-[#14151a] border border-[#262832] space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-slate-300 flex items-center gap-1.5">
                      <ArrowDownCircle className="w-3.5 h-3.5 text-amber-400" /> Seletor de Versões (GitHub Releases):
                    </span>
                    <button
                      type="button"
                      onClick={fetchReleasesList}
                      disabled={loadingReleases}
                      className="px-2 py-0.5 rounded bg-[#262832] hover:bg-[#343644] text-[10px] font-bold text-slate-300 flex items-center gap-1 cursor-pointer disabled:opacity-50"
                    >
                      <RefreshCw className={`w-2.5 h-2.5 ${loadingReleases ? 'animate-spin' : ''}`} />
                      <span>{loadingReleases ? 'Buscando...' : 'Listar'}</span>
                    </button>
                  </div>

                  <div className="flex items-center gap-2">
                    <select
                      value={selectedTag}
                      onChange={(e) => setSelectedTag(e.target.value)}
                      className="flex-1 bg-[#1f2129] border border-[#2e323e] rounded-lg px-2.5 py-1.5 text-xs text-white outline-none cursor-pointer"
                    >
                      {releases.length === 0 ? (
                        <option value="">Nenhuma versão carregada</option>
                      ) : (
                        releases.map((rel) => (
                          <option key={rel.tag} value={rel.tag}>
                            {rel.tag} • [{rel.channel_label}] {rel.name}
                          </option>
                        ))
                      )}
                    </select>

                    <button
                      type="button"
                      onClick={handleInstallSelectedVersion}
                      disabled={installingVersion || !selectedTag}
                      className="px-3 py-1.5 bg-[#0066cc] hover:bg-[#0052a3] text-white rounded-lg text-xs font-bold transition-all cursor-pointer disabled:opacity-50 shrink-0"
                    >
                      {installingVersion ? 'Baixando...' : 'Instalar Versão'}
                    </button>
                  </div>

                  {installStatus && (
                    <div className="p-1.5 rounded bg-[#161822] text-[11px] text-cyan-300 font-mono">
                      {installStatus}
                    </div>
                  )}
                </div>

                <div className="pt-1">
                  <button
                    type="button"
                    onClick={handleDevLogout}
                    disabled={devLoading}
                    className="px-3 py-1.5 bg-[#262832] hover:bg-[#343644] text-rose-300 hover:text-rose-200 rounded-lg text-xs font-semibold transition-colors cursor-pointer border border-[#353846]"
                  >
                    {devLoading ? 'Encerrando...' : 'Sair do Modo Desenvolvedor'}
                  </button>
                </div>
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

export default SettingsModal;
