import React, { useState, useMemo } from 'react';
import { Search, Play, Globe, Clock } from 'lucide-react';

interface Server {
  id: string;
  name: string;
  host: string;
  port: number;
  group?: string;
  notes?: string;
  last_connected?: string;
  latitude?: number;
  longitude?: number;
}

interface ServersViewProps {
  servers: Server[];
  groups: string[];
  onConnect: (serverId: string) => void;
}

export const ServersView: React.FC<ServersViewProps> = ({ servers, groups, onConnect }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedGroup, setSelectedGroup] = useState('Todos');

  const filteredServers = useMemo(() => {
    const term = searchTerm.toLowerCase().trim();
    return servers.filter((s) => {
      if (selectedGroup !== 'Todos' && s.group !== selectedGroup) {
        return false;
      }
      if (term) {
        const nameMatch = s.name.toLowerCase().includes(term);
        const hostMatch = s.host.toLowerCase().includes(term);
        const groupMatch = (s.group || '').toLowerCase().includes(term);
        if (!nameMatch && !hostMatch && !groupMatch) return false;
      }
      return true;
    });
  }, [servers, searchTerm, selectedGroup]);

  return (
    <div className="flex-1 flex flex-col p-4 bg-[#0d1117] overflow-hidden space-y-4">
      {/* Top Filter and Search Bar */}
      <div className="flex items-center justify-between gap-4 bg-[#161b22] p-3 rounded-xl border border-[#30363d] shadow-sm">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Buscar por nome, IP ou cidade..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg pl-9 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* Group Filter Chips */}
        <div className="flex items-center gap-1.5 overflow-x-auto max-w-2xl py-0.5">
          <button
            onClick={() => setSelectedGroup('Todos')}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
              selectedGroup === 'Todos'
                ? 'bg-blue-600 text-white shadow'
                : 'bg-[#21262d] text-slate-300 hover:bg-[#30363d]'
            }`}
          >
            Todos ({servers.length})
          </button>
          {groups.map((grp) => (
            <button
              key={grp}
              onClick={() => setSelectedGroup(grp)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
                selectedGroup === grp
                  ? 'bg-blue-600 text-white shadow'
                  : 'bg-[#21262d] text-slate-300 hover:bg-[#30363d]'
              }`}
            >
              {grp}
            </button>
          ))}
        </div>
      </div>

      {/* Servers Cards Grid */}
      <div className="flex-1 overflow-y-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3.5 pr-1">
        {filteredServers.map((s) => (
          <div
            key={s.id}
            className="bg-[#161b22] border border-[#30363d] hover:border-blue-500/60 rounded-xl p-4 flex flex-col justify-between shadow-md hover:shadow-xl transition-all group"
          >
            <div>
              {/* Card Header: Group & Status */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-blue-950/80 text-blue-300 border border-blue-800/50">
                  {s.group || 'Geral'}
                </span>
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  Pronto
                </span>
              </div>

              {/* Title & Host */}
              <h3 className="font-bold text-white text-sm tracking-tight group-hover:text-blue-400 transition-colors">
                {s.name}
              </h3>
              <div className="text-xs font-mono text-slate-400 mt-1 flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-slate-500" />
                <span>{s.host}:{s.port || 3389}</span>
              </div>

              {s.notes && (
                <p className="text-[11px] text-slate-400 mt-2 line-clamp-2 italic">
                  {s.notes}
                </p>
              )}
            </div>

            {/* Card Footer: Last Connection & Connect Button */}
            <div className="pt-3 border-t border-[#21262d] mt-3 flex items-center justify-between">
              <span className="text-[10px] text-slate-500 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {s.last_connected ? 'Conectado recentemente' : 'Nunca conectado'}
              </span>

              <button
                onClick={() => onConnect(s.id)}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 shadow-sm transition-transform active:scale-95"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Conectar</span>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
