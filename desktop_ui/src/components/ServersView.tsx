import React, { useMemo } from 'react';
import { Play, Globe, Clock, Server } from 'lucide-react';

interface ServerItem {
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
  servers: ServerItem[];
  searchTerm: string;
  selectedGroup: string;
  onConnect: (serverId: string) => void;
}

export const ServersView: React.FC<ServersViewProps> = ({
  servers,
  searchTerm,
  selectedGroup,
  onConnect,
}) => {
  const filteredServers = useMemo(() => {
    const term = searchTerm.toLowerCase().trim();
    return servers.filter((s) => {
      if (
        selectedGroup &&
        selectedGroup !== 'Todos os Grupos' &&
        selectedGroup !== 'Todos' &&
        s.group !== selectedGroup
      ) {
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
    <div className="flex-1 flex flex-col p-4 bg-[#0d1117] overflow-hidden">
      {/* Informações da Grade */}
      <div className="flex items-center justify-between pb-3 text-xs text-slate-400">
        <span className="font-semibold text-slate-300">
          Mostrando {filteredServers.length} de {servers.length} servidores
        </span>
        {selectedGroup && selectedGroup !== 'Todos os Grupos' && (
          <span className="px-2 py-0.5 rounded bg-blue-900/50 text-blue-300 border border-blue-700/50 text-[11px]">
            Filtro ativo: {selectedGroup}
          </span>
        )}
      </div>

      {/* Grid de Cards dos Servidores */}
      <div className="flex-1 overflow-y-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-3.5 pr-1">
        {filteredServers.map((s) => (
          <div
            key={s.id}
            className="bg-[#16171d] border border-[#2e323e] hover:border-blue-500/60 rounded-xl p-4 flex flex-col justify-between shadow-md hover:shadow-xl transition-all group"
          >
            <div>
              {/* Card Header: Group & Status */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-blue-950/80 text-blue-300 border border-blue-800/50">
                  {s.group || 'BEMTEVI'}
                </span>
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  Online
                </span>
              </div>

              {/* Title & Host */}
              <h3 className="font-bold text-white text-sm tracking-tight group-hover:text-blue-400 transition-colors">
                {s.name}
              </h3>
              <div className="text-xs font-mono text-slate-400 mt-1 flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-slate-500" />
                <span>
                  {s.host}:{s.port || 3389}
                </span>
              </div>

              {s.notes && (
                <p className="text-[11px] text-slate-400 mt-2 line-clamp-2 italic">
                  {s.notes}
                </p>
              )}
            </div>

            {/* Card Footer: Last Connection & Connect Button */}
            <div className="pt-3 border-t border-[#262832] mt-3 flex items-center justify-between">
              <span className="text-[10px] text-slate-500 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {s.last_connected ? 'Conectado recentemente' : 'Pronto'}
              </span>

              <button
                onClick={() => onConnect(s.id)}
                className="px-3.5 py-1.5 bg-[#0066cc] hover:bg-[#0052a3] text-white rounded-lg text-xs font-bold flex items-center gap-1.5 shadow-sm transition-transform active:scale-95 cursor-pointer"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Conectar</span>
              </button>
            </div>
          </div>
        ))}

        {filteredServers.length === 0 && (
          <div className="col-span-full flex flex-col items-center justify-center p-12 text-center text-slate-500 space-y-2">
            <Server className="w-10 h-10 stroke-1 text-slate-600" />
            <p className="text-sm font-medium text-slate-400">Nenhum servidor encontrado</p>
            <p className="text-xs">Tente ajustar a busca ou o filtro de grupo selecionado.</p>
          </div>
        )}
      </div>
    </div>
  );
};
