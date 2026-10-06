import React, { useState, useEffect } from 'react';
import {
  X,
  DoorClosed,
  Volume2,
  Bell,
  Plus,
  Trash2,
  QrCode,
  CheckCircle2,
  RefreshCw,
  Save,
  HelpCircle,
} from 'lucide-react';

interface DoorConfig {
  id: string;
  name: string;
  device_name?: string;
  device_id?: string;
  home_id?: string;
  scene_id?: string;
  scene_name?: string;
  mode?: string;
  hotkey?: string;
  enabled?: boolean;
}

interface DoorsSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

const API_BASE = 'http://127.0.0.1:8765';

export const DoorsSettingsModal: React.FC<DoorsSettingsModalProps> = ({
  isOpen,
  onClose,
  onSaved,
}) => {
  const [activeTab, setActiveTab] = useState<'doors' | 'prefs' | 'account'>('doors');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // Estados de Configuração
  const [enabled, setEnabled] = useState(true);
  const [feedbackSound, setFeedbackSound] = useState(true);
  const [feedbackNotification, setFeedbackNotification] = useState(true);
  const [userCode, setUserCode] = useState('BxLxxMC');
  const [doors, setDoors] = useState<DoorConfig[]>([]);
  const [cloudStatus, setCloudStatus] = useState<any>({});

  // Gravador de Hotkey
  const [recordingDoorId, setRecordingDoorId] = useState<string | null>(null);

  // QR Code Login
  const [qrLoading, setQrLoading] = useState(false);
  const [qrData, setQrData] = useState<{ image?: string; instructions?: string } | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadConfig();
      setSaveSuccess(false);
      setErrorMsg('');
      setRecordingDoorId(null);
      setQrData(null);
    }
  }, [isOpen]);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/doors/config`);
      if (res.ok) {
        const data = await res.json();
        const cfg = data.config || {};
        setEnabled(cfg.enabled !== false);
        setFeedbackSound(cfg.feedback_sound !== false);
        setFeedbackNotification(cfg.feedback_notification !== false);
        setUserCode(cfg.user_code || 'BxLxxMC');
        setDoors(cfg.doors || []);
        setCloudStatus(data.cloud_status || {});
      }
    } catch (e: any) {
      setErrorMsg('Falha ao carregar configurações: ' + e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setErrorMsg('');
    try {
      const payload = {
        enabled,
        feedback_sound: feedbackSound,
        feedback_notification: feedbackNotification,
        user_code: userCode,
        doors,
      };

      const res = await fetch(`${API_BASE}/api/doors/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 2500);
        onSaved?.();
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || 'Erro ao salvar configuração.');
      }
    } catch (e: any) {
      setErrorMsg(e.message || 'Erro de conexão.');
    } finally {
      setSaving(false);
    }
  };

  const handleAddDoor = () => {
    const newId = `door_${Date.now()}`;
    const newDoor: DoorConfig = {
      id: newId,
      name: `Nova Porta ${doors.length + 1}`,
      device_name: 'Fechadura Tuya',
      home_id: '100383937',
      scene_id: '',
      scene_name: 'Cena Tuya',
      mode: 'cloud_scene',
      hotkey: '',
      enabled: true,
    };
    setDoors([...doors, newDoor]);
  };

  const handleRemoveDoor = (id: string) => {
    setDoors(doors.filter((d) => d.id !== id));
  };

  const handleDoorChange = (id: string, field: keyof DoorConfig, value: any) => {
    setDoors(doors.map((d) => (d.id === id ? { ...d, [field]: value } : d)));
  };

  // Gravador de Hotkey
  useEffect(() => {
    if (!recordingDoorId) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();

      // Teclas especiais / modificadoras sozinhas não finalizam a gravação
      if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return;

      const keys: string[] = [];
      if (e.ctrlKey) keys.push('Ctrl');
      if (e.altKey) keys.push('Alt');
      if (e.shiftKey) keys.push('Shift');

      let mainKey = e.key;
      if (e.key === 'PageUp') mainKey = 'PageUp';
      else if (e.key === 'PageDown') mainKey = 'PageDown';
      else if (e.key === 'ArrowUp') mainKey = 'Up';
      else if (e.key === 'ArrowDown') mainKey = 'Down';
      else if (e.key === 'ArrowLeft') mainKey = 'Left';
      else if (e.key === 'ArrowRight') mainKey = 'Right';
      else if (e.key === 'Escape') mainKey = 'Esc';
      else if (e.key.startsWith('F') && !isNaN(Number(e.key.replace('F', '')))) mainKey = e.key.toUpperCase();
      else if (e.code.startsWith('Key')) mainKey = e.code.replace('Key', '');
      else if (e.code.startsWith('Digit')) mainKey = e.code.replace('Digit', '');
      else mainKey = e.key.toUpperCase();

      keys.push(mainKey);
      const hotkeyStr = keys.join('+');

      handleDoorChange(recordingDoorId, 'hotkey', hotkeyStr);
      setRecordingDoorId(null);
    };

    window.addEventListener('keydown', handleKeyDown, true);
    return () => window.removeEventListener('keydown', handleKeyDown, true);
  }, [recordingDoorId]);

  // Gerar QR Code Tuya
  const handleGenerateQr = async () => {
    setQrLoading(true);
    setQrData(null);
    try {
      const res = await fetch(`${API_BASE}/api/doors/qr-login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_code: userCode }),
      });

      const data = await res.json();
      if (res.ok && data.success) {
        setQrData({
          image: data.qr_image_data,
          instructions: data.instructions,
        });
      } else {
        setErrorMsg(data.detail || 'Falha ao gerar QR Code.');
      }
    } catch (e: any) {
      setErrorMsg(e.message || 'Erro ao conectar com API.');
    } finally {
      setQrLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[150] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 select-none animate-in fade-in duration-200">
      <div className="bg-[#151722] border border-[#272b3c] w-full max-w-2xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Topo do Modal */}
        <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-[#191c2a]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400">
              <DoorClosed className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-extrabold text-white leading-tight">
                  Configurações de Portões & Acessos
                </h2>
                {loading && <RefreshCw className="w-3.5 h-3.5 text-amber-400 animate-spin" />}
              </div>
              <span className="text-[11px] text-slate-400">
                Atalhos globais, vinculação de cenas Tuya e preferências
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/5 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Abas Internas */}
        <div className="flex border-b border-white/5 bg-[#141620] px-6">
          <button
            onClick={() => setActiveTab('doors')}
            className={`py-3 px-4 text-xs font-bold border-b-2 transition-all cursor-pointer ${
              activeTab === 'doors'
                ? 'border-amber-500 text-amber-300'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            Portas & Atalhos
          </button>
          <button
            onClick={() => setActiveTab('prefs')}
            className={`py-3 px-4 text-xs font-bold border-b-2 transition-all cursor-pointer ${
              activeTab === 'prefs'
                ? 'border-amber-500 text-amber-300'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            Preferências & Sons
          </button>
          <button
            onClick={() => setActiveTab('account')}
            className={`py-3 px-4 text-xs font-bold border-b-2 transition-all cursor-pointer ${
              activeTab === 'account'
                ? 'border-amber-500 text-amber-300'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            Conta Tuya & Sessão
          </button>
        </div>

        {/* Mensagens de Alerta */}
        {errorMsg && (
          <div className="mx-6 mt-4 p-3 rounded-xl bg-rose-950/80 border border-rose-800 text-rose-300 text-xs font-medium">
            ⚠️ {errorMsg}
          </div>
        )}

        {saveSuccess && (
          <div className="mx-6 mt-4 p-3 rounded-xl bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-xs font-bold flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            Configurações salvas e atalhos recarregados com sucesso!
          </div>
        )}

        {/* Conteúdo com Scroll */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1">
          {/* ABA 1: PORTAS E ATALHOS */}
          {activeTab === 'doors' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400 font-semibold">
                  Portas e Motores Cadastrados ({doors.length})
                </span>
                <button
                  onClick={handleAddDoor}
                  className="px-3 py-1.5 rounded-lg bg-amber-600/20 hover:bg-amber-600/30 border border-amber-500/40 text-amber-300 text-xs font-bold flex items-center gap-1.5 transition-all cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Adicionar Porta</span>
                </button>
              </div>

              <div className="space-y-3">
                {doors.map((door) => (
                  <div
                    key={door.id}
                    className="bg-[#1b1e2c] border border-white/10 rounded-xl p-4 space-y-3 shadow-md"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex-1">
                        <label className="text-[11px] text-slate-400 font-semibold block mb-1">
                          Nome da Porta / Portão
                        </label>
                        <input
                          type="text"
                          value={door.name}
                          onChange={(e) => handleDoorChange(door.id, 'name', e.target.value)}
                          className="w-full bg-[#141620] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white outline-none focus:border-amber-500"
                        />
                      </div>

                      <div className="w-36">
                        <label className="text-[11px] text-slate-400 font-semibold block mb-1">
                          Atalho de Teclado
                        </label>
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() =>
                              setRecordingDoorId(recordingDoorId === door.id ? null : door.id)
                            }
                            className={`flex-1 py-1.5 px-2 rounded-lg text-xs font-mono font-bold border transition-all text-center cursor-pointer ${
                              recordingDoorId === door.id
                                ? 'bg-amber-500 text-black border-white animate-pulse'
                                : door.hotkey
                                ? 'bg-amber-950/60 text-amber-300 border-amber-600/50'
                                : 'bg-[#141620] text-slate-400 border-white/10 hover:border-white/20'
                            }`}
                          >
                            {recordingDoorId === door.id
                              ? 'Pressione Tecla...'
                              : door.hotkey || 'Gravar Tecla'}
                          </button>
                          {door.hotkey && (
                            <button
                              onClick={() => handleDoorChange(door.id, 'hotkey', '')}
                              title="Remover atalho"
                              className="text-slate-500 hover:text-rose-400 p-1"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </div>

                      <button
                        onClick={() => handleRemoveDoor(door.id)}
                        title="Remover porta"
                        className="text-slate-500 hover:text-rose-400 p-2 rounded-lg hover:bg-rose-500/10 transition-colors mt-5 cursor-pointer"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-3 pt-2 border-t border-white/5">
                      <div>
                        <label className="text-[10px] text-slate-400 block mb-1">
                          ID da Cena Tuya (Tap-to-Run)
                        </label>
                        <input
                          type="text"
                          value={door.scene_id || ''}
                          placeholder="Ex: o34EQAoAQQniX6Vk"
                          onChange={(e) => handleDoorChange(door.id, 'scene_id', e.target.value)}
                          className="w-full bg-[#141620] border border-white/10 rounded-lg px-2.5 py-1 text-xs text-white font-mono outline-none focus:border-amber-500"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-slate-400 block mb-1">
                          ID da Casa Tuya (Home ID)
                        </label>
                        <input
                          type="text"
                          value={door.home_id || ''}
                          placeholder="Ex: 100383937"
                          onChange={(e) => handleDoorChange(door.id, 'home_id', e.target.value)}
                          className="w-full bg-[#141620] border border-white/10 rounded-lg px-2.5 py-1 text-xs text-white font-mono outline-none focus:border-amber-500"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ABA 2: PREFERÊNCIAS E SONS */}
          {activeTab === 'prefs' && (
            <div className="space-y-4">
              <div className="bg-[#1b1e2c] border border-white/10 rounded-xl p-4 flex items-center justify-between">
                <div>
                  <span className="text-xs font-bold text-white block">
                    Módulo de Portões Habilitado
                  </span>
                  <span className="text-[11px] text-slate-400">
                    Ativa ou desativa todo o funcionamento do módulo e listeners globais
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                  className="w-4 h-4 accent-amber-500 cursor-pointer"
                />
              </div>

              <div className="bg-[#1b1e2c] border border-white/10 rounded-xl p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Volume2 className="w-5 h-5 text-amber-400" />
                  <div>
                    <span className="text-xs font-bold text-white block">
                      Feedback Sonoro (Bipe do Windows)
                    </span>
                    <span className="text-[11px] text-slate-400">
                      Toca um bipe sonoro suave no alto-falante ao confirmar a abertura
                    </span>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={feedbackSound}
                  onChange={(e) => setFeedbackSound(e.target.checked)}
                  className="w-4 h-4 accent-amber-500 cursor-pointer"
                />
              </div>

              <div className="bg-[#1b1e2c] border border-white/10 rounded-xl p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Bell className="w-5 h-5 text-amber-400" />
                  <div>
                    <span className="text-xs font-bold text-white block">
                      Notificações Toast na Interface
                    </span>
                    <span className="text-[11px] text-slate-400">
                      Exibe aviso flutuante de sucesso no canto da tela
                    </span>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={feedbackNotification}
                  onChange={(e) => setFeedbackNotification(e.target.checked)}
                  className="w-4 h-4 accent-amber-500 cursor-pointer"
                />
              </div>

              <div className="bg-[#1b1e2c] border border-white/10 rounded-xl p-4 space-y-2">
                <label className="text-xs font-bold text-white block">
                  Código de Usuário Tuya (User Code)
                </label>
                <input
                  type="text"
                  value={userCode}
                  onChange={(e) => setUserCode(e.target.value)}
                  className="w-full bg-[#141620] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white font-mono outline-none focus:border-amber-500"
                />
                <span className="text-[10px] text-slate-400 block">
                  Código identificador da conta no gateway oficial Tuya (Padrão: BxLxxMC).
                </span>
              </div>
            </div>
          )}

          {/* ABA 3: CONTA TUYA & REAUTENTICAÇÃO */}
          {activeTab === 'account' && (
            <div className="space-y-4">
              <div className="bg-[#1b1e2c] border border-white/10 rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-white">Status da Conexão Nuvem</span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      cloudStatus.connected
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/50'
                        : 'bg-rose-950 text-rose-300 border border-rose-700/50'
                    }`}
                  >
                    {cloudStatus.connected ? '🟢 Conectado' : '🔴 Desconectado'}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 space-y-1 pt-1 font-mono">
                  <div>Endpoint: {cloudStatus.session_info?.endpoint || 'https://apigw.tuyaus.com'}</div>
                  <div>User Code: {cloudStatus.session_info?.user_code || userCode}</div>
                </div>
              </div>

              {/* Box de QR Code Login */}
              <div className="bg-[#1b1e2c] border border-amber-500/30 rounded-xl p-5 text-center space-y-4">
                <div>
                  <h3 className="text-sm font-bold text-white mb-1 flex items-center justify-center gap-2">
                    <QrCode className="w-4 h-4 text-amber-400" />
                    <span>Reautenticação Tuya Smart via QR Code</span>
                  </h3>
                  <p className="text-xs text-slate-400 max-w-md mx-auto">
                    Caso a sessão do aplicativo expire ou necessite de novo acesso, gere um QR Code e aponte o app Tuya Smart do seu celular.
                  </p>
                </div>

                {qrLoading && (
                  <div className="py-8 flex flex-col items-center justify-center gap-2 text-slate-400 text-xs">
                    <RefreshCw className="w-6 h-6 animate-spin text-amber-400" />
                    <span>Gerando QR Code seguro com a Tuya...</span>
                  </div>
                )}

                {qrData?.image && (
                  <div className="p-4 bg-white rounded-2xl w-fit mx-auto shadow-2xl space-y-3">
                    <img
                      src={qrData.image}
                      alt="QR Code Tuya Smart"
                      className="w-56 h-56 object-contain mx-auto"
                    />
                    <div className="text-[11px] text-slate-800 font-sans font-semibold leading-tight text-center">
                      1. Abra o Tuya Smart no celular<br />
                      2. Toque no '+' topo direito -&gt; Escanear<br />
                      3. Confirme o Login
                    </div>
                  </div>
                )}

                {!qrLoading && !qrData?.image && (
                  <button
                    onClick={handleGenerateQr}
                    className="px-4 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2 mx-auto cursor-pointer"
                  >
                    <QrCode className="w-4 h-4" />
                    <span>Gerar QR Code Agora</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Rodapé do Modal */}
        <div className="px-6 py-3.5 border-t border-white/10 bg-[#191c2a] flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <HelpCircle className="w-3.5 h-3.5" />
            <span>Atalhos globais exigem que o usuário esteja autenticado no Modo DEV.</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-[#232738] hover:bg-[#2d3248] text-slate-300 text-xs font-semibold transition-colors cursor-pointer"
            >
              Cancelar
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 rounded-xl bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white text-xs font-bold transition-all shadow-lg flex items-center gap-1.5 cursor-pointer"
            >
              <Save className="w-3.5 h-3.5" />
              <span>{saving ? 'Salvando...' : 'Salvar Alterações'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
