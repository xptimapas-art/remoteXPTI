import React, { useState, useMemo } from 'react';
import {
  Search,
  RefreshCw,
  Camera,
  Download,
  AlertTriangle,
  Radio,
  CheckCircle2,
  XCircle,
  Clock,
  Globe,
  Database,
  Pencil,
  Trash2,
  Activity,
} from 'lucide-react';

interface ONUItem {
  id: string | number;
  port: string;
  name?: string;
  desc?: string;
  serial?: string;
  status: 'Online' | 'Offline' | string;
  uptime?: string;
  vendor?: string;
  rx_power?: string;
  signal?: string;
}

interface TelemetryData {
  total: number;
  online: number;
  offline: number;
  total_cameras: number;
  active_problems: number;
  coleta_formatted: string;
  server: { online: boolean; ip: string; checked_at: string };
  olt: { modelo: string; ip: string };
  ports: Record<string, { online: number; total: number; label: string }>;
  rows: ONUItem[];
}

interface AjinViewProps {
  telemetry: TelemetryData;
  countdown: number;
  currentTime: string;
  onRefresh: () => void;
  onSaveLabel: (port: string, onuId: string, name: string, desc: string) => void;
}

export const AjinView: React.FC<AjinViewProps> = ({
  telemetry,
  countdown,
  currentTime,
  onRefresh,
  onSaveLabel,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedPon, setSelectedPon] = useState('Todas as Portas PON');
  const [selectedStatus, setSelectedStatus] = useState('Todos os Status');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [sortField, setSortField] = useState<string>('name');
  const [sortAsc, setSortAsc] = useState<boolean>(true);

  // Modal de Edição
  const [editingItem, setEditingItem] = useState<ONUItem | null>(null);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');

  // Filtragem e Ordenação de Alta Performance
  const filteredRows = useMemo(() => {
    const term = searchTerm.toLowerCase().trim();
    return (telemetry.rows || []).filter((r) => {
      if (term) {
        const pName = (r.name || `Ponto ${r.id}`).toLowerCase();
        const pDesc = (r.desc || '').toLowerCase();
        const pSer = (r.serial || '').toLowerCase();
        const pPort = (r.port || '').toLowerCase();
        if (!pName.includes(term) && !pDesc.includes(term) && !pSer.includes(term) && !pPort.includes(term)) {
          return false;
        }
      }

      if (selectedPon !== 'Todas as Portas PON' && r.port !== selectedPon) {
        return false;
      }

      if (selectedStatus === 'Em Funcionamento (Online)' && r.status !== 'Online') {
        return false;
      }
      if (selectedStatus === 'Fora de Funcionamento (Offline)' && r.status === 'Online') {
        return false;
      }

      return true;
    }).sort((a, b) => {
      let va = (a as any)[sortField] || '';
      let vb = (b as any)[sortField] || '';
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return 0;
    });
  }, [telemetry.rows, searchTerm, selectedPon, selectedStatus, sortField, sortAsc]);

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  const openEditModal = (item: ONUItem) => {
    setEditingItem(item);
    setEditName(item.name || `Ponto ${item.id}`);
    setEditDesc(item.desc || '');
  };

  const saveEdit = () => {
    if (editingItem) {
      onSaveLabel(editingItem.port, String(editingItem.id), editName, editDesc);
      setEditingItem(null);
    }
  };

  return (
    <div className="flex-1 flex overflow-hidden bg-[#0d1117] p-3 gap-3">
      {/* PAINEL ESQUERDO: CONTROLES E TABELA DE ONUs */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#161b22] rounded-xl border border-[#30363d] overflow-hidden shadow-lg">
        {/* Barra Superior de Filtros */}
        <div className="p-3 border-b border-[#30363d] flex items-center justify-between gap-3 bg-[#11151c]">
          <div className="flex items-center gap-2 flex-1 max-w-md">
            <div className="relative w-full">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Buscar por ponto, rua, MAC ou porta..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg pl-9 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>

            <select
              value={selectedPon}
              onChange={(e) => setSelectedPon(e.target.value)}
              className="bg-[#0d1117] border border-[#30363d] rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500"
            >
              <option>Todas as Portas PON</option>
              <option>Slot1-PON1</option>
              <option>Slot2-PON1</option>
              <option>Slot2-PON2</option>
            </select>

            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="bg-[#0d1117] border border-[#30363d] rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500"
            >
              <option>Todos os Status</option>
              <option>Em Funcionamento (Online)</option>
              <option>Fora de Funcionamento (Offline)</option>
            </select>
          </div>

          {/* Botões de Ação */}
          <div className="flex items-center gap-2">
            <button
              onClick={onRefresh}
              className="px-2.5 py-1.5 bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] text-slate-200 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5 text-blue-400" />
              <span>Atualizar</span>
            </button>

            <button className="px-2.5 py-1.5 bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] text-slate-200 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors">
              <Camera className="w-3.5 h-3.5 text-sky-400" />
              <span>Câmeras</span>
            </button>

            <button className="px-2.5 py-1.5 bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] text-slate-200 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors">
              <Download className="w-3.5 h-3.5 text-emerald-400" />
              <span>CSV</span>
            </button>

            <button className="px-2.5 py-1.5 bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] text-slate-200 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              <span>Incidentes</span>
            </button>
          </div>
        </div>

        {/* Tabela de ONUs */}
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 bg-[#161b22] border-b border-[#30363d] text-[11px] font-bold text-slate-400 uppercase tracking-wider select-none z-10">
              <tr>
                <th onClick={() => handleSort('status')} className="py-2.5 px-3 cursor-pointer hover:text-white w-28">
                  Status
                </th>
                <th onClick={() => handleSort('name')} className="py-2.5 px-3 cursor-pointer hover:text-white w-32">
                  ONU / Ponto
                </th>
                <th onClick={() => handleSort('serial')} className="py-2.5 px-3 cursor-pointer hover:text-white w-36">
                  MAC / Serial
                </th>
                <th onClick={() => handleSort('desc')} className="py-2.5 px-3 cursor-pointer hover:text-white">
                  Descrição (Rua / Local)
                </th>
                <th onClick={() => handleSort('vendor')} className="py-2.5 px-3 cursor-pointer hover:text-white w-28">
                  Fabricante
                </th>
                <th onClick={() => handleSort('uptime')} className="py-2.5 px-3 cursor-pointer hover:text-white w-28">
                  Sinal / Uptime
                </th>
                <th onClick={() => handleSort('port')} className="py-2.5 px-3 cursor-pointer hover:text-white w-28 text-right">
                  Canal OLT
                </th>
                <th className="py-2.5 px-3 w-20 text-center">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#21262d] text-xs">
              {filteredRows.map((row) => {
                const isOnline = row.status === 'Online';
                return (
                  <tr
                    key={`${row.port}-${row.id}`}
                    className="hover:bg-[#1f242c] transition-colors group"
                  >
                    {/* Status Badge */}
                    <td className="py-2 px-3">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                          isOnline
                            ? 'bg-emerald-950/70 text-emerald-400 border border-emerald-800/60 shadow-[0_0_8px_rgba(16,185,129,0.2)]'
                            : 'bg-rose-950/70 text-rose-400 border border-rose-800/60 shadow-[0_0_8px_rgba(244,63,94,0.2)]'
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            isOnline ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'
                          }`}
                        />
                        {isOnline ? 'Online' : 'Offline'}
                      </span>
                    </td>

                    {/* Nome do Ponto */}
                    <td className="py-2 px-3 font-semibold text-white">
                      <div className="flex items-center gap-1.5">
                        <span>{row.name || `Ponto ${row.id}`}</span>
                        <button
                          onClick={() => openEditModal(row)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 text-slate-400 hover:text-blue-400"
                        >
                          <Pencil className="w-3 h-3" />
                        </button>
                      </div>
                    </td>

                    {/* Serial / MAC */}
                    <td className="py-2 px-3 font-mono text-[11px] text-slate-300">
                      {row.serial || '-'}
                    </td>

                    {/* Descrição */}
                    <td className="py-2 px-3 text-slate-200">
                      {row.desc || <span className="text-slate-500 italic">+ adicionar rua</span>}
                    </td>

                    {/* Fabricante */}
                    <td className="py-2 px-3 text-slate-400 text-[11px]">
                      {row.vendor || 'C-Data'}
                    </td>

                    {/* Sinal / Uptime */}
                    <td className="py-2 px-3 text-slate-300 font-mono text-[11px]">
                      {row.signal || row.uptime || '-21.4 dBm'}
                    </td>

                    {/* Porta PON */}
                    <td className="py-2 px-3 text-right font-mono text-[11px] text-slate-400">
                      {row.port}
                    </td>

                    {/* Ações */}
                    <td className="py-2 px-3 text-center">
                      <div className="flex items-center justify-center gap-1">
                        <button
                          onClick={() => openEditModal(row)}
                          className="px-2 py-1 bg-[#21262d] hover:bg-[#30363d] text-slate-300 rounded text-[10px] font-bold border border-[#30363d] transition-colors"
                        >
                          Menu
                        </button>
                        <button className="p-1 text-slate-500 hover:text-rose-400 transition-colors">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Rodapé da Tabela */}
        <div className="p-2.5 bg-[#11151c] border-t border-[#30363d] flex items-center justify-between text-xs text-slate-400">
          <div>
            Exibindo <span className="font-bold text-white">{filteredRows.length}</span> de{' '}
            <span className="font-bold text-white">{telemetry.rows?.length || 0}</span> ONUs cadastradas
          </div>
          <div className="flex items-center gap-3 font-mono">
            <span>Hora: {currentTime}</span>
            <span>|</span>
            <span className="text-blue-400">Próximo refresh: {countdown}s</span>
          </div>
        </div>
      </div>

      {/* PAINEL LATERAL DIREITO: SIDEBAR NOC (LARGURA FIXA 304px DE REFERÊNCIA) */}
      <aside className="w-[304px] flex-shrink-0 bg-[#2870c2] rounded-xl flex flex-col shadow-xl overflow-hidden text-white select-none">
        {/* Métricas Roláveis */}
        <div className="flex-1 overflow-y-auto divide-y divide-white/20">
          {/* 1. Total */}
          <div className="p-4 flex items-center justify-between hover:bg-[#307cd1] transition-colors">
            <Radio className="w-8 h-8 opacity-90" />
            <div className="text-right">
              <div className="text-3xl font-extrabold tracking-tight">{telemetry.total || 39}</div>
              <div className="text-xs font-bold uppercase tracking-wider opacity-90">Total</div>
            </div>
          </div>

          {/* 2. Em Funcionamento */}
          <div className="p-4 flex items-center justify-between hover:bg-[#307cd1] transition-colors">
            <CheckCircle2 className="w-8 h-8 opacity-90" />
            <div className="text-right">
              <div className="text-3xl font-extrabold tracking-tight">{telemetry.online || 36}</div>
              <div className="text-xs font-bold uppercase tracking-wider opacity-90">Em Funcionamento</div>
            </div>
          </div>

          {/* 3. Fora de Funcionamento (Sem quebras de linha com 304px!) */}
          <div className="p-4 flex items-center justify-between hover:bg-[#307cd1] transition-colors">
            <XCircle className="w-8 h-8 opacity-90" />
            <div className="text-right">
              <div className="text-3xl font-extrabold tracking-tight">{telemetry.offline || 3}</div>
              <div className="text-xs font-bold uppercase tracking-wider opacity-90 whitespace-nowrap">
                Fora de Funcionamento
              </div>
            </div>
          </div>

          {/* 4. Câmeras Mapeadas */}
          <div className="p-4 flex items-center justify-between hover:bg-[#307cd1] transition-colors">
            <Camera className="w-8 h-8 opacity-90" />
            <div className="text-right">
              <div className="text-3xl font-extrabold tracking-tight">{telemetry.total_cameras || 64}</div>
              <div className="text-xs font-bold uppercase tracking-wider opacity-90">Câmeras Mapeadas</div>
            </div>
          </div>

          {/* 5. Portas PON */}
          <div className="p-4 hover:bg-[#307cd1] transition-colors">
            <div className="flex items-center justify-between mb-2">
              <Activity className="w-6 h-6 opacity-90" />
              <span className="text-xs font-bold uppercase tracking-wider opacity-90">Portas PON</span>
            </div>
            <div className="space-y-1.5 text-xs font-mono">
              <div className="flex justify-between">
                <span className="opacity-90">Slot1-PON1</span>
                <span className="font-bold">11 / 11</span>
              </div>
              <div className="flex justify-between">
                <span className="opacity-90">Slot2-PON1</span>
                <span className="font-bold">10 / 11</span>
              </div>
              <div className="flex justify-between">
                <span className="opacity-90">Slot2-PON2</span>
                <span className="font-bold">15 / 17</span>
              </div>
            </div>
          </div>

          {/* 6. Última Coleta */}
          <div className="p-4 flex items-center justify-between hover:bg-[#307cd1] transition-colors">
            <Clock className="w-7 h-7 opacity-90" />
            <div className="text-right">
              <div className="text-base font-bold font-mono">{telemetry.coleta_formatted?.split(' ')[1] || currentTime}</div>
              <div className="text-[11px] opacity-80">{telemetry.coleta_formatted?.split(' ')[0] || '25/09/2026'}</div>
              <div className="text-[10px] font-bold uppercase tracking-wider opacity-90">Última Coleta</div>
            </div>
          </div>

          {/* 7. Servidor Coletor */}
          <div className="p-4 flex items-center justify-between hover:bg-[#307cd1] transition-colors">
            <Globe className="w-7 h-7 text-emerald-300" />
            <div className="text-right">
              <div className="text-xs font-bold text-emerald-300">Ping OK</div>
              <div className="text-[11px] font-mono opacity-90">192.168.190.187</div>
              <div className="text-[10px] font-bold uppercase tracking-wider opacity-90">Servidor Coletor</div>
            </div>
          </div>

          {/* 8. OLT Principal */}
          <div className="p-4 flex items-center justify-between hover:bg-[#307cd1] transition-colors">
            <Database className="w-7 h-7 opacity-90" />
            <div className="text-right">
              <div className="text-xs font-bold">C-Data FD1108S</div>
              <div className="text-[11px] font-mono opacity-90">192.168.1.100</div>
              <div className="text-[10px] font-bold uppercase tracking-wider opacity-90">OLT Principal</div>
            </div>
          </div>
        </div>

        {/* Rodapé da Sidebar: Auto-refresh Toggle */}
        <div className="p-3 bg-[#1d5b9f] border-t border-white/20 flex items-center justify-between">
          <label className="flex items-center gap-2.5 cursor-pointer text-xs font-bold">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="w-4 h-4 rounded text-blue-600 focus:ring-0 bg-white"
            />
            <span>Auto-refresh ({countdown}s)</span>
          </label>
          <span className="text-[10px] font-mono opacity-80">{currentTime}</span>
        </div>
      </aside>

      {/* MODAL DE EDIÇÃO */}
      {editingItem && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-5 w-full max-w-md shadow-2xl space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Pencil className="w-4 h-4 text-blue-400" />
              Editar Identificação da ONU ({editingItem.port})
            </h3>

            <div className="space-y-3">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Nome do Ponto</label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Descrição (Rua / Referência)</label>
                <input
                  type="text"
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-[#30363d]">
              <button
                onClick={() => setEditingItem(null)}
                className="px-3 py-1.5 text-xs text-slate-400 hover:text-white rounded-lg transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={saveEdit}
                className="px-3 py-1.5 text-xs font-bold text-white bg-blue-600 hover:bg-blue-500 rounded-lg shadow transition-colors"
              >
                Salvar Alterações
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
