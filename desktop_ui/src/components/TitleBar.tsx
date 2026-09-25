import React from 'react';
import { Minus, Square, X, Activity } from 'lucide-react';

interface TitleBarProps {
  currentTab: 'servers' | 'map' | 'ajin';
  setCurrentTab: (tab: 'servers' | 'map' | 'ajin') => void;
  serverCount: number;
  onlineCount: number;
}

export const TitleBar: React.FC<TitleBarProps> = ({
  currentTab,
  setCurrentTab,
  serverCount,
  onlineCount,
}) => {
  return (
    <header className="h-11 bg-[#161b22] border-b border-[#30363d] flex items-center justify-between px-3 select-none z-50">
      {/* Brand & Tabs */}
      <div className="flex items-center space-x-4">
        <div className="flex items-center space-x-2 font-bold text-sm tracking-wide text-white">
          <div className="w-6 h-6 rounded bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white shadow-sm font-black text-xs">
            X
          </div>
          <span>Remote<span className="text-blue-400">XPTI</span></span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-900/50 text-blue-300 border border-blue-700/50 font-mono">
            v1.6.30
          </span>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex space-x-1 ml-4">
          <button
            onClick={() => setCurrentTab('servers')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              currentTab === 'servers'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-[#21262d]'
            }`}
          >
            🖥️ Servidores ({serverCount})
          </button>
          <button
            onClick={() => setCurrentTab('map')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              currentTab === 'map'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-[#21262d]'
            }`}
          >
            🗺️ Mapa Geográfico
          </button>
          <button
            onClick={() => setCurrentTab('ajin')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all flex items-center space-x-1.5 ${
              currentTab === 'ajin'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-[#21262d]'
            }`}
          >
            <span>📊 Monitoramento AJIN</span>
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          </button>
        </nav>
      </div>

      {/* Right Controls / Live Status */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2 text-xs text-slate-300 font-mono bg-[#0d1117] px-2.5 py-1 rounded border border-[#30363d]">
          <Activity className="w-3.5 h-3.5 text-emerald-400" />
          <span>Hub: {onlineCount}/{serverCount} OK</span>
        </div>

        <div className="flex items-center space-x-1 border-l border-[#30363d] pl-2">
          <button
            onClick={() => (window as any).pywebview?.api?.minimize()}
            className="w-7 h-7 flex items-center justify-center text-slate-400 hover:text-white hover:bg-[#21262d] rounded transition-colors"
          >
            <Minus className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => (window as any).pywebview?.api?.toggle_maximize()}
            className="w-7 h-7 flex items-center justify-center text-slate-400 hover:text-white hover:bg-[#21262d] rounded transition-colors"
          >
            <Square className="w-3 h-3" />
          </button>
          <button
            onClick={() => (window as any).pywebview?.api?.close()}
            className="w-7 h-7 flex items-center justify-center text-slate-400 hover:text-white hover:bg-rose-600 rounded transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </header>
  );
};
