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
    <div className="flex-1 flex flex-col bg-[#0d1117] overflow-hidden select-none">
      {/* Sub-header de contagem */}
      <div className="flex items-center justify-between px-5 pt-3 pb-2 text-xs text-slate-400 shrink-0">
        <span className="font-semibold text-slate-300">
          Grade de Acesso RDP • {filteredServers.length} de {servers.length} servidores
        </span>
        {selectedGroup && selectedGroup !== 'Todos os Grupos' && (
          <span className="px-2.5 py-0.5 rounded bg-blue-900/50 text-blue-300 border border-blue-700/50 text-[11px] font-medium">
            Filtro: {selectedGroup}
          </span>
        )}
      </div>

      {/* Grid de Cards dos Servidores com dimensões fixas no padrão AnyDesk */}
      <div
        className="flex-1 overflow-y-auto px-5 pb-6"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gridAutoRows: '200px',
          gap: '16px',
        }}
      >
        {filteredServers.map((s) => (
          <div
            key={s.id}
            onClick={() => onConnect(s.id)}
            style={{
              height: '200px',
              backgroundColor: '#16171d',
              border: '1px solid #2e323e',
              borderRadius: '12px',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
            }}
            className="hover:border-[#0066cc] hover:-translate-y-1 hover:shadow-xl group"
          >
            {/* Top Banner / Preview AnyDesk */}
            <div
              style={{
                height: '112px',
                position: 'relative',
                background: 'linear-gradient(135deg, #1d2535 0%, #151822 50%, #0e1017 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderBottom: '1px solid #262832',
                overflow: 'hidden',
              }}
            >
              {/* Miniatura do servidor se existir */}
              <img
                src={`http://127.0.0.1:8765/thumbnails/${s.id}.png`}
                alt=""
                style={{
                  position: 'absolute',
                  inset: 0,
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                  opacity: 0.8,
                }}
                onError={(e) => {
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />

              {/* Tag de Grupo (Canto Superior Esquerdo) */}
              <span
                style={{
                  position: 'absolute',
                  top: '8px',
                  left: '8px',
                  fontSize: '9px',
                  fontWeight: 'bold',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(0, 0, 0, 0.75)',
                  color: '#60a5fa',
                  border: '1px solid rgba(59, 130, 246, 0.3)',
                  zIndex: 2,
                }}
              >
                {s.group || 'BEMTEVI'}
              </span>

              {/* Status Online (Canto Superior Direito) */}
              <span
                style={{
                  position: 'absolute',
                  top: '8px',
                  right: '8px',
                  fontSize: '10px',
                  fontWeight: '600',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(0, 0, 0, 0.75)',
                  color: '#34d399',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  zIndex: 2,
                }}
              >
                <span
                  style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: '#34d399',
                  }}
                />
                Online
              </span>

              {/* Ícone Central de Servidor */}
              <div
                style={{
                  width: '44px',
                  height: '44px',
                  borderRadius: '10px',
                  backgroundColor: 'rgba(0, 102, 204, 0.15)',
                  border: '1px solid rgba(0, 102, 204, 0.3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#60a5fa',
                  zIndex: 1,
                }}
                className="group-hover:scale-110 transition-transform"
              >
                <Server style={{ width: '22px', height: '22px' }} />
              </div>
            </div>

            {/* Bottom Info & Connect Button */}
            <div
              style={{
                height: '88px',
                padding: '10px 14px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <h3
                  style={{
                    fontSize: '13px',
                    fontWeight: 'bold',
                    color: '#ffffff',
                    margin: 0,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  className="group-hover:text-blue-400 transition-colors"
                >
                  {s.name}
                </h3>
                <div
                  style={{
                    fontSize: '11px',
                    fontFamily: 'monospace',
                    color: '#94a3b8',
                    marginTop: '2px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <Globe style={{ width: '12px', height: '12px', color: '#64748b' }} />
                  <span>
                    {s.host}:{s.port || 3389}
                  </span>
                </div>
              </div>

              {/* Rodapé com Conectar */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingTop: '6px',
                  borderTop: '1px solid #262832',
                }}
              >
                <span
                  style={{
                    fontSize: '10px',
                    color: '#64748b',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  <Clock style={{ width: '11px', height: '11px' }} />
                  {s.last_connected ? 'Conectado recente' : 'Pronto'}
                </span>

                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onConnect(s.id);
                  }}
                  style={{
                    backgroundColor: '#0066cc',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '6px',
                    padding: '4px 10px',
                    fontSize: '11px',
                    fontWeight: 'bold',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '5px',
                    cursor: 'pointer',
                    boxShadow: '0 2px 6px rgba(0, 102, 204, 0.4)',
                  }}
                  className="hover:bg-[#0052a3] active:scale-95 transition-all"
                >
                  <Play style={{ width: '11px', height: '11px', fill: 'currentColor' }} />
                  <span>Conectar</span>
                </button>
              </div>
            </div>
          </div>
        ))}

        {filteredServers.length === 0 && (
          <div
            style={{
              gridColumn: '1 / -1',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '60px 20px',
              textAlign: 'center',
              color: '#64748b',
            }}
          >
            <Server style={{ width: '40px', height: '40px', strokeWidth: 1.5, color: '#475569' }} />
            <p style={{ marginTop: '12px', fontSize: '14px', fontWeight: '600', color: '#94a3b8' }}>
              Nenhum servidor encontrado
            </p>
            <p style={{ marginTop: '4px', fontSize: '12px' }}>
              Tente ajustar o termo da busca ou o filtro de grupo selecionado.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
