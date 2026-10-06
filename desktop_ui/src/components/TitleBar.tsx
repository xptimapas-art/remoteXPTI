import React from 'react';
import { Search, ChevronDown, RotateCw, Settings, DoorClosed } from 'lucide-react';

interface TitleBarProps {
  currentTab: 'servers' | 'map' | 'ajin' | 'doors';
  setCurrentTab: (tab: 'servers' | 'map' | 'ajin' | 'doors') => void;
  searchTerm: string;
  setSearchTerm: (term: string) => void;
  selectedGroup: string;
  setSelectedGroup: (group: string) => void;
  groups: string[];
  isDev: boolean;
  onRefresh: () => void;
  onAddServer: () => void;
  onOpenSettings: () => void;
  updateInfo?: {
    currentVersion: string;
    newVersion: string;
    updateReady: boolean;
    isDownloading?: boolean;
  };
  onRestartUpdate?: () => void;
}

export const TitleBar: React.FC<TitleBarProps> = ({
  currentTab,
  setCurrentTab,
  searchTerm,
  setSearchTerm,
  selectedGroup,
  setSelectedGroup,
  groups,
  isDev,
  onRefresh,
  onAddServer,
  onOpenSettings,
  updateInfo,
  onRestartUpdate,
}) => {
  return (
    <header className="h-16 bg-[#16171d] border-b border-[#252836] flex items-center justify-between px-4 select-none z-50 shrink-0">
      {/* Brand: Logo Oficial XPti + Título e Subtítulo */}
      <div className="flex items-center space-x-3">
        <img
          src="/imagens/XPti_negativo_color.png"
          alt="XPti Logo"
          className="h-[38px] w-auto object-contain"
        />
        <div className="flex flex-col justify-center leading-none">
          <div className="flex items-center space-x-2">
            <span className="text-[17px] font-bold text-white tracking-normal font-sans">
              RemoteXPTI
            </span>
            {updateInfo?.updateReady ? (
              <button
                onClick={onRestartUpdate}
                title={`Nova versão v${updateInfo.newVersion} pronta! Clique para reiniciar e atualizar.`}
                className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-md bg-[#0066cc] hover:bg-[#0052a3] text-white border border-blue-400 shadow-[0_0_10px_rgba(0,102,204,0.6)] flex items-center gap-1 cursor-pointer animate-pulse transition-all"
              >
                <span>🔄 Restart p/ v{updateInfo.newVersion}</span>
              </button>
            ) : updateInfo?.isDownloading ? (
              <button
                onClick={onOpenSettings}
                title="Baixando atualização em segundo plano..."
                className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-blue-900/50 text-cyan-300 border border-blue-500/40 flex items-center gap-1 cursor-pointer"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping" />
                <span>Baixando...</span>
              </button>
            ) : (
              <button
                onClick={onOpenSettings}
                title={isDev ? 'Modo Desenvolvedor Ativo (BETA TESTER)' : 'Clique para Configurações & Login DEV'}
                className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded cursor-pointer transition-all ${
                  isDev
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 hover:bg-emerald-500/30'
                    : 'bg-[#1f2129] text-[#8e92a0] border border-[#2e323e] hover:text-white'
                }`}
              >
                v{updateInfo?.currentVersion || '1.6.30'} {isDev ? '[TESTER]' : ''}
              </button>
            )}
          </div>
          <span className="text-[10px] text-[#8e92a0] mt-0.5 tracking-wide">
            RDP Quick Launcher
          </span>
        </div>
      </div>

      {/* Ações do Topo: Busca, Filtro de Grupo, Segmented View, Refresh, + Novo Servidor, Settings */}
      <div className="flex items-center space-x-2">
        {/* Campo de Busca */}
        <div className="relative flex items-center">
          <Search className="w-3.5 h-3.5 text-[#8e92a0] absolute left-3 pointer-events-none" />
          <input
            type="text"
            placeholder="Buscar servidor, IP ou grupo..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-[230px] h-[34px] bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-md pl-8 pr-3 text-xs text-white placeholder-[#8e92a0] outline-none transition-colors"
          />
        </div>

        {/* Filtro de Grupos */}
        <div className="relative flex items-center">
          <select
            value={selectedGroup}
            onChange={(e) => setSelectedGroup(e.target.value)}
            className="h-[34px] min-w-[135px] max-w-[180px] bg-[#1f2129] border border-[#2e323e] focus:border-[#0066cc] rounded-md pl-3 pr-7 text-xs text-white outline-none cursor-pointer appearance-none font-medium"
          >
            <option value="Todos os Grupos">Todos os Grupos</option>
            {groups.map((grp) => (
              <option key={grp} value={grp}>
                {grp}
              </option>
            ))}
          </select>
          <ChevronDown className="w-3.5 h-3.5 text-[#8e92a0] absolute right-2 pointer-events-none" />
        </div>

        {/* Alternador Segmentado de Modo de Exibição (Grade AnyDesk / Mapa / AJIN) */}
        <div className="flex items-center h-[34px] bg-[#1a1c23] border border-[#2e323e] rounded-md p-0.5 space-x-0.5">
          <button
            onClick={() => setCurrentTab('servers')}
            title="Grade de Servidores"
            className={`h-full px-3.5 rounded flex items-center space-x-1.5 text-xs font-bold transition-all ${
              currentTab === 'servers'
                ? 'bg-[#0066cc] text-white shadow-sm'
                : 'text-[#a0a5b5] hover:text-white hover:bg-[#252836]'
            }`}
          >
            <img
              src="/imagens/icon_grid.png"
              alt=""
              className="w-3.5 h-3.5 object-contain brightness-110"
              onError={(e) => {
                (e.target as HTMLElement).style.display = 'none';
              }}
            />
            <span>Grade</span>
          </button>

          <button
            onClick={() => setCurrentTab('map')}
            title="Mapa Interativo"
            className={`h-full px-3.5 rounded flex items-center space-x-1.5 text-xs font-bold transition-all ${
              currentTab === 'map'
                ? 'bg-[#0066cc] text-white shadow-sm'
                : 'text-[#a0a5b5] hover:text-white hover:bg-[#252836]'
            }`}
          >
            <img
              src="/imagens/icon_map.png"
              alt=""
              className="w-3.5 h-3.5 object-contain brightness-110"
              onError={(e) => {
                (e.target as HTMLElement).style.display = 'none';
              }}
            />
            <span>Mapa</span>
          </button>

          <button
            onClick={() => setCurrentTab('ajin')}
            title="Telemetria e Monitoramento AJIN"
            className={`h-full px-3.5 rounded flex items-center space-x-1.5 text-xs font-bold transition-all ${
              currentTab === 'ajin'
                ? 'bg-[#0066cc] text-white shadow-sm'
                : 'text-[#a0a5b5] hover:text-white hover:bg-[#252836]'
            }`}
          >
            <img
              src="/imagens/icon_ajin.png"
              alt=""
              className="w-3.5 h-3.5 object-contain brightness-110"
              onError={(e) => {
                (e.target as HTMLElement).style.display = 'none';
              }}
            />
            <span>AJIN</span>
          </button>

          {/* Modo DEV Exclusivo: Controle de Portões e Acesso Tuya */}
          {isDev && (
            <button
              onClick={() => setCurrentTab('doors')}
              title="Controle de Portões"
              className={`h-full px-3.5 rounded flex items-center space-x-1.5 text-xs font-bold transition-all ${
                currentTab === 'doors'
                  ? 'bg-[#0066cc] text-white shadow-sm'
                  : 'text-[#a0a5b5] hover:text-white hover:bg-[#252836]'
              }`}
            >
              <DoorClosed className="w-3.5 h-3.5" />
              <span>Portões</span>
            </button>
          )}
        </div>

        {/* Botão Atualizar Status Manual */}
        <button
          title="Atualizar Status Geral"
          onClick={onRefresh}
          className="w-[36px] h-[34px] bg-[#262832] hover:bg-[#343644] active:bg-[#1f2129] text-white rounded-md flex items-center justify-center transition-colors border border-[#353846]"
        >
          <RotateCw className="w-4 h-4 text-slate-300 hover:text-white" />
        </button>

        {/* Botão + Novo Servidor */}
        <button
          onClick={onAddServer}
          className="h-[34px] px-3.5 bg-[#0066cc] hover:bg-[#0052a3] active:bg-[#004080] text-white text-xs font-bold rounded-md flex items-center space-x-1 transition-colors shadow-sm"
        >
          <span>+ Novo Servidor</span>
        </button>

        {/* Botão Engrenagem de Configurações Gerais */}
        <button
          title="Configurações e Sincronização"
          onClick={onOpenSettings}
          className="w-[36px] h-[34px] bg-[#262832] hover:bg-[#343644] active:bg-[#1f2129] text-white rounded-md flex items-center justify-center transition-colors border border-[#353846]"
        >
          <Settings className="w-4 h-4 text-slate-300 hover:text-white" />
        </button>
      </div>
    </header>
  );
};
