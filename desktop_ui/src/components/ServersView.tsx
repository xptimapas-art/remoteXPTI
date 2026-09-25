import React, { useMemo } from 'react';
import { Monitor, Star } from 'lucide-react';

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
  favorite?: boolean;
  is_online?: boolean;
  status_msg?: string;
  offline_since?: number | null;
  duration_seconds?: number;
}

interface ServersViewProps {
  servers: ServerItem[];
  searchTerm: string;
  selectedGroup: string;
  onConnect: (serverId: string) => void;
  onEdit: (serverId: string) => void;
  onToggleFavorite?: (serverId: string) => void;
}

const PALETTES = [
  'linear-gradient(135deg, #204682 0%, #152c52 100%)', // AnyDesk Classic Blue
  'linear-gradient(135deg, #282c36 0%, #181a20 100%)', // Dark Graphite
  'linear-gradient(135deg, #2d5037 0%, #1a3021 100%)', // Forest Green
  'linear-gradient(135deg, #7d552d 0%, #4a321a 100%)', // Warm Amber
  'linear-gradient(135deg, #7d2d34 0%, #4a1a1f 100%)', // Crimson Ruby
  'linear-gradient(135deg, #37326e 0%, #211e42 100%)', // Royal Indigo
  'linear-gradient(135deg, #235569 0%, #15333f 100%)', // Teal Cyan
];

function formatLossDuration(sec?: number): string {
  if (!sec || sec <= 0) return 'OFFLINE';
  sec = Math.max(0, Math.floor(sec));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m < 60) return `${m}m ${s < 10 ? '0' : ''}${s}s`;
  const h = Math.floor(m / 60);
  const remM = m % 60;
  if (h < 24) return `${h}h ${remM < 10 ? '0' : ''}${remM}m`;
  const d = Math.floor(h / 24);
  const remH = h % 24;
  return `${d}d ${remH}h`;
}

function getPaletteForId(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash << 5) - hash + id.charCodeAt(i);
    hash |= 0;
  }
  return PALETTES[Math.abs(hash) % PALETTES.length];
}

export const ServersView: React.FC<ServersViewProps> = ({
  servers,
  searchTerm,
  selectedGroup,
  onConnect,
  onEdit,
  onToggleFavorite,
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
        <div className="flex items-center gap-2.5">
          <span className="font-semibold text-slate-300">
            Grade de Acesso RDP • {filteredServers.length} de {servers.length} servidores
          </span>
          {servers.some((s) => s.is_online === false) && (
            <span className="px-2 py-0.5 rounded bg-red-950/70 text-red-300 border border-red-800/60 text-[11px] font-medium flex items-center gap-1.5 animate-pulse">
              <span className="w-2 h-2 rounded-full bg-red-500 inline-block shadow-[0_0_6px_rgba(239,68,68,0.9)]" />
              {servers.filter((s) => s.is_online === false).length} em falha (LOSS)
            </span>
          )}
        </div>
        {selectedGroup && selectedGroup !== 'Todos os Grupos' && (
          <span className="px-2.5 py-0.5 rounded bg-blue-900/50 text-blue-300 border border-blue-700/50 text-[11px] font-medium">
            Filtro: {selectedGroup}
          </span>
        )}
      </div>

      {/* Grid de Cards dos Servidores com padrão AnyDesk foto cheia */}
      <div
        className="flex-1 overflow-y-auto px-5 pb-6"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gridAutoRows: '180px',
          gap: '16px',
        }}
      >
        {filteredServers.map((s) => {
          const bgGradient = getPaletteForId(s.id);
          const isOffline = s.is_online === false;

          return (
            <div
              key={s.id}
              onClick={() => onConnect(s.id)}
              onContextMenu={(e) => {
                e.preventDefault();
                onEdit(s.id);
              }}
              style={{
                height: '180px',
                position: 'relative',
                borderRadius: '8px',
                overflow: 'hidden',
                cursor: 'pointer',
                boxShadow: '0 4px 14px rgba(0, 0, 0, 0.45)',
                border: isOffline ? '1.5px solid rgba(239, 68, 68, 0.55)' : '1.5px solid #262933',
                transition: 'all 0.18s cubic-bezier(0.4, 0, 0.2, 1)',
                background: bgGradient,
              }}
              className={`${isOffline ? 'hover:border-[#ef4444]' : 'hover:border-[#0082f0]'} hover:scale-[1.02] hover:shadow-2xl group select-none`}
            >
              {/* Foto Cheia (100% da área do Card) */}
              <img
                src={`http://127.0.0.1:8765/thumbnails/${s.id}.png`}
                alt=""
                style={{
                  position: 'absolute',
                  inset: 0,
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                  zIndex: 1,
                  transition: 'transform 0.3s ease',
                }}
                className="group-hover:scale-105"
                onError={(e) => {
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />

              {/* Ondas AnyDesk em SVG caso não haja print capturado */}
              <svg
                style={{
                  position: 'absolute',
                  inset: 0,
                  width: '100%',
                  height: '100%',
                  opacity: 0.22,
                  zIndex: 0,
                  pointerEvents: 'none',
                }}
                viewBox="0 0 276 180"
                preserveAspectRatio="none"
              >
                <path
                  d="M-20,135 C50,60 170,195 300,90 L300,180 L-20,180 Z"
                  fill="white"
                  opacity="0.35"
                />
                <path
                  d="M-20,155 C70,95 190,215 300,120 L300,180 L-20,180 Z"
                  fill="white"
                  opacity="0.25"
                />
              </svg>

              {/* Gradiente Escuro Inferior para máxima legibilidade do nome e IP sobre a foto */}
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  background:
                    'linear-gradient(to top, rgba(10, 12, 16, 0.94) 0%, rgba(10, 12, 16, 0.72) 42%, rgba(10, 12, 16, 0.12) 72%, transparent 100%)',
                  zIndex: 2,
                  pointerEvents: 'none',
                }}
              />

              {/* Canto Superior: Status LED + Tag do Grupo + LOSS badge à esquerda, Estrela à direita */}
              <div
                style={{
                  position: 'absolute',
                  top: '10px',
                  left: '12px',
                  right: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  zIndex: 3,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                  {/* Status LED Redondo com Glow AnyDesk (Verde Online / Vermelho Pulsante Offline) */}
                  <span
                    title={isOffline ? `Offline: ${s.status_msg || 'Porta fechada/filtrada'}` : 'Online'}
                    style={{
                      width: '10px',
                      height: '10px',
                      borderRadius: '50%',
                      backgroundColor: isOffline ? '#ef4444' : '#22c55e',
                      boxShadow: isOffline ? '0 0 10px rgba(239, 68, 68, 0.95)' : '0 0 8px rgba(34, 197, 94, 0.9)',
                      border: '1.5px solid rgba(255, 255, 255, 0.85)',
                      display: 'inline-block',
                      flexShrink: 0,
                    }}
                    className={isOffline ? 'animate-pulse' : ''}
                  />

                  {/* Pílula do Grupo */}
                  <span
                    style={{
                      fontSize: '9px',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      backgroundColor: 'rgba(0, 0, 0, 0.65)',
                      color: '#93c5fd',
                      border: '1px solid rgba(59, 130, 246, 0.35)',
                      backdropFilter: 'blur(4px)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {s.group || 'BEMTEVI'}
                  </span>

                  {/* Badge de LOSS em Destaque Vermelho quando Offline */}
                  {isOffline && (
                    <span
                      title={`Offline há ${formatLossDuration(s.duration_seconds)} (${s.status_msg || ''})`}
                      style={{
                        fontSize: '9px',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.04em',
                        padding: '2px 7px',
                        borderRadius: '4px',
                        backgroundColor: 'rgba(153, 27, 27, 0.88)',
                        color: '#fef2f2',
                        border: '1px solid rgba(248, 113, 113, 0.7)',
                        backdropFilter: 'blur(4px)',
                        boxShadow: '0 2px 6px rgba(185, 28, 28, 0.4)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      ⚠️ LOSS {formatLossDuration(s.duration_seconds)}
                    </span>
                  )}
                </div>

                {/* Estrela de Favorito */}
                <button
                  type="button"
                  title={s.favorite ? 'Remover dos favoritos' : 'Adicionar aos favoritos'}
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleFavorite?.(s.id);
                  }}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    color: '#facc15',
                    opacity: s.favorite ? 1 : 0.65,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '4px',
                    borderRadius: '4px',
                    flexShrink: 0,
                    transition: 'all 0.15s ease',
                  }}
                  className="hover:!opacity-100 hover:scale-125 active:scale-95"
                >
                  <Star style={{ width: '15px', height: '15px', fill: s.favorite ? '#facc15' : 'none', stroke: '#facc15' }} />
                </button>
              </div>

              {/* Canto Inferior: Ícone de Monitor + Nome em Negrito + IP à esquerda, Menu 3 pontos à direita */}
              <div
                style={{
                  position: 'absolute',
                  bottom: '12px',
                  left: '12px',
                  right: '12px',
                  display: 'flex',
                  alignItems: 'flex-end',
                  justifyContent: 'space-between',
                  zIndex: 3,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                  {/* Ícone de Monitor Estilizado AnyDesk */}
                  <div
                    style={{
                      width: '30px',
                      height: '22px',
                      borderRadius: '4px',
                      border: '1.5px solid rgba(255, 255, 255, 0.9)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      backgroundColor: 'rgba(0, 0, 0, 0.45)',
                      flexShrink: 0,
                    }}
                  >
                    <Monitor style={{ width: '15px', height: '15px', color: '#ffffff' }} />
                  </div>

                  {/* Textos: Nome do Servidor e Host */}
                  <div style={{ minWidth: 0 }}>
                    <h3
                      style={{
                        fontSize: '13px',
                        fontWeight: 700,
                        color: '#ffffff',
                        margin: 0,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        lineHeight: 1.25,
                      }}
                      className="group-hover:text-blue-300 transition-colors"
                    >
                      {s.name}
                    </h3>
                    <div
                      style={{
                        fontSize: '11px',
                        fontFamily: 'monospace',
                        color: '#cbd5e1',
                        marginTop: '2px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {s.host}:{s.port || 3389}
                    </div>
                  </div>
                </div>

                {/* Botão Três Pontos AnyDesk ⋮ para Editar Credenciais */}
                <button
                  type="button"
                  title="Editar credenciais e servidor"
                  onClick={(e) => {
                    e.stopPropagation();
                    onEdit(s.id);
                  }}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '2.5px',
                    padding: '5px',
                    borderRadius: '4px',
                    opacity: 0.75,
                    flexShrink: 0,
                    transition: 'all 0.15s ease',
                  }}
                  className="hover:opacity-100 hover:bg-white/20 active:scale-95"
                >
                  <span style={{ width: '3.5px', height: '3.5px', borderRadius: '50%', backgroundColor: '#ffffff' }} />
                  <span style={{ width: '3.5px', height: '3.5px', borderRadius: '50%', backgroundColor: '#ffffff' }} />
                  <span style={{ width: '3.5px', height: '3.5px', borderRadius: '50%', backgroundColor: '#ffffff' }} />
                </button>
              </div>

              {/* Borda Inferior Luminosa AnyDesk no Hover (Azul se Online, Vermelha se Offline) */}
              <div
                style={{
                  position: 'absolute',
                  bottom: 0,
                  left: 0,
                  right: 0,
                  height: '3px',
                  backgroundColor: isOffline ? '#ef4444' : '#0082f0',
                  opacity: 0,
                  zIndex: 4,
                  transition: 'opacity 0.2s ease',
                }}
                className="group-hover:!opacity-100"
              />
            </div>
          );
        })}

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
            <Monitor style={{ width: '40px', height: '40px', strokeWidth: 1.5, color: '#475569' }} />
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
