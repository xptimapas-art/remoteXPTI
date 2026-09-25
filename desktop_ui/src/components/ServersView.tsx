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
      {/* Sub-header de contagem */}
      <div className="flex items-center justify-between pb-3 text-xs text-slate-400">
        <span className="font-semibold text-slate-300">
          Grade de Acesso RDP • {filteredServers.length} de {servers.length} servidores
        </span>
        {selectedGroup && selectedGroup !== 'Todos os Grupos' && (
          <span className="px-2 py-0.5 rounded bg-blue-900/50 text-blue-300 border border-blue-700/50 text-[11px]">
            Grupo: {selectedGroup}
          </span>
        )}
      </div>

      {/* Grid de Cards dos Servidores no padrão AnyDesk */}
      <div className="flex-1 overflow-y-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-3.5 pr-1">
        {filteredServers.map((s) => (
          <div
            key={s.id}
            onClick={() => onConnect(s.id)}
            className="bg-[#16171d] border border-[#2e323e] hover:border-[#0066cc] rounded-xl overflow-hidden flex flex-col justify-between shadow-md hover:shadow-2xl transition-all group cursor-pointer"
          >
            {/* Preview Banner com suporte a miniaturas e gradiente escuro AnyDesk */}
            <div className="h-28 w-full bg-gradient-to-br from-[#1c2430] via-[#16171d] to-[#0f1117] relative flex items-center justify-center border-b border-[#262832] overflow-hidden">
              <img
                src={`http://127.0.0.1:8765/thumbnails/${s.id}.png`}
                alt=""
                className="absolute inset-0 w-full h-full object-cover opacity-75 group-hover:scale-105 transition-transform duration-300"
                onError={(e) => {
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />
              <div className="absolute inset-0 bg-gradient-to-t from-[#16171d] via-transparent to-transparent pointer-events-none" />

              {/* Tag de Grupo */}
              <span className="absolute top-2.5 left-2.5 text-[9px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-black/70 text-blue-300 border border-blue-500/30 backdrop-blur-xs">
                {s.group || 'BEMTEVI'}
              </span>

              {/* Badge de Status Online */}
              <span className="absolute top-2.5 right-2.5 inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-400 bg-black/70 px-2 py-0.5 rounded border border-emerald-500/30 backdrop-blur-xs">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                Online
              </span>

              {/* Ícone de Computador Central se não houver foto */}
              <div className="w-12 h-12 rounded-xl bg-blue-600/10 border border-blue-500/20 flex items-center justify-center text-blue-400 group-hover:scale-110 transition-transform">
                <Server className="w-6 h-6 stroke-1.5" />
              </div>
            </div>

            {/* Informações do Servidor */}
            <div className="p-3.5 flex flex-col justify-between flex-1">
              <div>
                <h3 className="font-bold text-white text-xs tracking-tight group-hover:text-blue-400 transition-colors line-clamp-1">
                  {s.name}
                </h3>
                <div className="text-[11px] font-mono text-slate-400 mt-1 flex items-center gap-1.5">
                  <Globe className="w-3 h-3 text-slate-500" />
                  <span>
                    {s.host}:{s.port || 3389}
                  </span>
                </div>

                {s.notes && (
                  <p className="text-[10px] text-slate-400 mt-1.5 line-clamp-2 italic">
                    {s.notes}
                  </p>
                )}
              </div>

              {/* Rodapé do Card com Botão Conectar */}
              <div className="pt-2.5 border-t border-[#262832] mt-2.5 flex items-center justify-between">
                <span className="text-[10px] text-slate-500 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {s.last_connected ? 'Conectado recente' : 'Pronto'}
                </span>

                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onConnect(s.id);
                  }}
                  className="px-3.5 py-1 bg-[#0066cc] hover:bg-[#0052a3] text-white rounded-md text-[11px] font-bold flex items-center gap-1.5 shadow-sm transition-transform active:scale-95 cursor-pointer"
                >
                  <Play className="w-3 h-3 fill-current" />
                  <span>Conectar</span>
                </button>
              </div>
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
