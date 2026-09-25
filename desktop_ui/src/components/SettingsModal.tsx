import React from 'react';
import { X, Settings, Cloud, Database, Cpu, Info } from 'lucide-react';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  serverCount: number;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  serverCount,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 backdrop-blur-xs p-4">
      <div className="bg-[#16171d] border border-[#2e323e] rounded-xl shadow-2xl w-full max-w-md overflow-hidden flex flex-col text-slate-200 animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#262832]">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400">
              <Settings className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white leading-tight">Configurações Gerais</h3>
              <p className="text-[11px] text-[#8e92a0]">Painel Operacional RemoteXPTI</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-white hover:bg-[#262832] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 text-xs">
          <div className="p-3.5 bg-[#1a1c23] border border-[#262832] rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1.5 font-medium">
                <Database className="w-3.5 h-3.5 text-blue-400" /> Servidores Cadastrados:
              </span>
              <span className="font-bold text-white font-mono">{serverCount} servidores</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1.5 font-medium">
                <Cloud className="w-3.5 h-3.5 text-emerald-400" /> Sincronização em Nuvem:
              </span>
              <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-semibold text-[10px] border border-emerald-500/30">
                Supabase Online
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1.5 font-medium">
                <Cpu className="w-3.5 h-3.5 text-indigo-400" /> Motor Gráfico:
              </span>
              <span className="font-medium text-slate-300">Microsoft Edge WebView2</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-1.5 font-medium">
                <Info className="w-3.5 h-3.5 text-cyan-400" /> Versão da Plataforma:
              </span>
              <span className="font-bold text-white font-mono">v1.6.30</span>
            </div>
          </div>

          <div className="p-3 bg-blue-600/10 border border-blue-500/20 rounded-xl text-blue-300 text-[11px] leading-relaxed">
            💡 Todas as credenciais e conexões RDP locais continuam utilizando a criptografia de disco Fernet e o motor nativo do Windows MSTSC.
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end px-5 py-3 border-t border-[#262832] bg-[#14151a]">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-[#0066cc] hover:bg-[#0052a3] text-white text-xs font-bold transition-colors"
          >
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
};
