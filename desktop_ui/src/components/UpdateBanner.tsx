import React from 'react';
import { Rocket, RotateCw, X } from 'lucide-react';

interface UpdateBannerProps {
  onDismiss: () => void;
  onRestart?: () => void;
}

export const UpdateBanner: React.FC<UpdateBannerProps> = ({
  onDismiss,
  onRestart,
}) => {
  return (
    <div className="bg-gradient-to-r from-[#00488f] via-[#0066cc] to-[#0052a3] border-b border-blue-400/40 text-white px-4 py-2 flex items-center justify-between shadow-lg z-40 shrink-0 animate-in slide-in-from-top-2 duration-200">
      <div className="flex items-center space-x-3 min-w-0">
        <div className="w-7 h-7 rounded-lg bg-white/15 flex items-center justify-center shrink-0 shadow-inner">
          <Rocket className="w-4 h-4 text-cyan-200 animate-bounce" />
        </div>
        <div className="flex items-baseline space-x-2 truncate">
          <span className="text-xs font-bold tracking-wide">
            Atualização pronta. Reinicie quando quiser.
          </span>
        </div>
      </div>

      <div className="flex items-center space-x-2 shrink-0">
        {onRestart && (
          <button
            onClick={onRestart}
            title="Reiniciar aplicação agora para aplicar nova versão"
            className="px-2.5 py-1 bg-white/20 hover:bg-white/30 active:bg-white/10 text-white text-[11px] font-bold rounded-md flex items-center space-x-1.5 transition-colors cursor-pointer border border-white/25"
          >
            <RotateCw className="w-3 h-3" />
            <span>Reiniciar Agora</span>
          </button>
        )}
        <button
          onClick={onDismiss}
          title="Fechar aviso por enquanto"
          className="w-6 h-6 rounded flex items-center justify-center text-blue-200 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
};
