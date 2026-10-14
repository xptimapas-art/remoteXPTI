import { useEffect, useRef, useState } from 'react';
import { QrCode } from 'lucide-react';
import { AccessDialog } from './AccessDialog';
import { HotkeyRecorder } from './HotkeyRecorder';
import { isFacialDoor, readResponse } from './doors';
import type { CameraConfig, CloudStatus, DoorConfig, DoorsConfig } from './doors';

interface Props { isOpen: boolean; doorId?: string | null; onClose: () => void; onSaved?: () => void }
interface ConfigResponse { config: DoorsConfig; cloud_status: CloudStatus }


export function DoorsSettingsModal({ isOpen, doorId = null, onClose, onSaved }: Props) {
  const [config, setConfig] = useState<DoorsConfig>({});
  const [cloud, setCloud] = useState<CloudStatus>({});
  const [door, setDoor] = useState<DoorConfig | null>(null);
  const [original, setOriginal] = useState<DoorConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [qrLoading, setQrLoading] = useState(false);
  const [syncPassword, setSyncPassword] = useState('');
  const [unlocking, setUnlocking] = useState(false);
  const [qr, setQr] = useState<{ qr_image_data?: string; instructions?: string; session_revision?: string } | null>(null);
  const lifecycle = useRef<AbortController | null>(null);
  const isNew = doorId === 'new';
  const isDoorEditor = doorId !== null;

  useEffect(() => {
    if (!isOpen) return;
    const controller = new AbortController(); lifecycle.current = controller;
    setLoading(true); setError(''); setDeleting(false); setQr(null); setDoor(null); setOriginal(null); setSyncPassword('');
    fetch('/api/doors/config', { signal: controller.signal }).then(readResponse<ConfigResponse>).then(data => {
      if (controller.signal.aborted) return;
      setConfig(data.config || {}); setCloud(data.cloud_status || {});
      if (doorId === 'new') setDoor({ id: crypto.randomUUID(), name: '', mode: 'hikvision', enabled: true, hotkey: '', camera: { source: 'none' } });
      else if (doorId) {
        const existing = data.config.doors?.find(item => item.id === doorId);
        if (!existing) throw new Error('Este acesso não existe mais. Feche e atualize a lista.');
        setOriginal(existing); setDoor(existing);
      }
    }).catch(exception => { if (!controller.signal.aborted) setError(exception.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); lifecycle.current = null; };
  }, [isOpen, doorId]);

  useEffect(() => {
    if (!isOpen || !qr) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      fetch('/api/doors/config', { signal: controller.signal }).then(readResponse<ConfigResponse>).then(data => {
        if (controller.signal.aborted) return;
        setCloud(data.cloud_status || {});
        if (data.cloud_status?.connected && data.cloud_status.session_revision !== qr.session_revision) {
          setQr(null); window.dispatchEvent(new Event('doorsUpdated'));
        }
      }).catch(() => { /* Mantém o QR visível para tentar a consulta novamente. */ });
    }, 3000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [isOpen, qr]);

  const change = <K extends keyof DoorConfig>(key: K, value: DoorConfig[K]) => setDoor(current => current && ({ ...current, [key]: value }));
  const cameraChange = <K extends keyof CameraConfig>(key: K, value: CameraConfig[K]) => setDoor(current => current && ({ ...current, camera: { ...current.camera, [key]: value } }));
  const save = async (remove = false) => {
    if (saving || loading || recording) return;
    setError('');
    if (isDoorEditor && !door) return;
    if (!remove && door) {
      if (!door.name.trim()) { setError('Informe o nome do acesso.'); return; }
      if (isNew && isFacialDoor(door) && !door.host?.trim()) { setError('Informe o endereço do equipamento em Dados de conexão.'); return; }
      if (!isFacialDoor(door) && !door.scene_id?.trim()) { setError('Informe o ID da cena Tuya em Dados de conexão.'); return; }
      if (door.camera?.source === 'external' && !door.camera.host?.trim()) { setError('Informe o endereço da câmera Hikvision.'); return; }
      const sameShortcut = (config.doors || []).some(item => item.id !== door.id && item.enabled !== false && item.hotkey && item.hotkey.toLowerCase() === door.hotkey?.toLowerCase());
      if (door.enabled !== false && sameShortcut) { setError('Este atalho já está em uso por outro acesso.'); return; }
    }
    setSaving(true);
    const signal = lifecycle.current?.signal;
    try {
      const payload = isDoorEditor && door ? { door: { ...door, name: door.name.trim() }, original, delete: remove }
        : { enabled: config.enabled !== false, hotkeys_enabled: config.hotkeys_enabled !== false, feedback_sound: config.feedback_sound !== false, feedback_notification: config.feedback_notification !== false, user_code: config.user_code || '' };
      const url = isDoorEditor && door ? `/api/doors/${encodeURIComponent(door.id)}/config` : '/api/doors/config';
      await fetch(url, { method: isDoorEditor ? 'PUT' : 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(readResponse);
      if (signal?.aborted) return;
      window.dispatchEvent(new Event('doorsUpdated')); onSaved?.(); onClose();
    } catch (exception) { if (!signal?.aborted) setError(exception instanceof Error ? exception.message : 'Falha ao salvar.'); }
    finally { setSaving(false); }
  };
  const generateQr = async () => {
    if (qrLoading) return;
    setQrLoading(true); setError('');
    const signal = lifecycle.current?.signal;
    try {
      const data = await fetch('/api/doors/qr-login', { method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_code: config.user_code || undefined }) }).then(readResponse<{ qr_image_data?: string; instructions?: string }>);
      if (!signal?.aborted) setQr({ ...data, session_revision: cloud.session_revision });
    } catch (exception) { if (!signal?.aborted) setError(exception instanceof Error ? exception.message : 'Falha ao gerar QR Code.'); }
    finally { setQrLoading(false); }
  };
  const unlockSync = async () => {
    if (unlocking || !syncPassword) return;
    setUnlocking(true); setError('');
    try {
      const data = await fetch('/api/doors/shared-sync', { method:'POST', signal:lifecycle.current?.signal,
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({password:syncPassword}) }).then(readResponse<ConfigResponse>);
      setCloud(data.cloud_status); setConfig(data.config); setSyncPassword('');
      window.dispatchEvent(new Event('doorsUpdated'));
    } catch (exception) { setError(exception instanceof Error ? exception.message : 'Não foi possível habilitar a sincronização.'); }
    finally { setUnlocking(false); }
  };
  if (!isOpen) return null;
  const field = (label: string, key: 'host' | 'username' | 'password' | 'scene_id' | 'home_id' | 'device_id', type = 'text') => <label className="xa-field"><span>{label}</span>
    <input type={type} autoComplete={type === 'password' ? 'new-password' : 'off'} value={String(door?.[key] || '')} onChange={event => change(key, event.target.value)} /></label>;
  const cameraField = (label: string, key: 'host' | 'username' | 'password', type = 'text') => <label className="xa-field"><span>{label}</span>
    <input type={type} autoComplete={type === 'password' ? 'new-password' : 'off'} value={door?.camera?.[key] || ''} onChange={event => cameraChange(key, event.target.value)} /></label>;
  return <AccessDialog title={isDoorEditor ? isNew ? 'Adicionar acesso' : `Configurar ${original?.name || 'acesso'}` : 'Configurações de acessos'} onClose={onClose} busy={saving || qrLoading || recording}
    footer={<>
      {isDoorEditor && !isNew && door && <button className="xa-delete" disabled={saving || loading} onClick={() => setDeleting(!deleting)}>{deleting ? 'Manter acesso' : 'Excluir acesso'}</button>}
      <button type="button" disabled={saving || qrLoading || recording} onClick={onClose}>Cancelar</button>
      <button className="xa-save" type="submit" form="xa-config-form" disabled={saving || qrLoading || recording || loading || (isDoorEditor && !door)}>{saving ? 'Salvando…' : 'Salvar'}</button>
    </>}>
    <form id="xa-config-form" onSubmit={event => { event.preventDefault(); void save(); }}>
      <fieldset disabled={saving || loading || qrLoading} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        {loading ? <p role="status">Carregando configurações…</p> : isDoorEditor && door ? <>
          <div className="xa-fields">
            <label className="xa-field xa-full"><span>Nome do acesso</span><input autoFocus maxLength={100} value={door.name} onChange={event => change('name', event.target.value)} /></label>
            <label className="xa-field"><span>Equipamento</span><select aria-label="Equipamento" value={isFacialDoor(door) ? 'hikvision' : 'cloud_scene'} onChange={event => setDoor(current => current && ({ ...current, mode: event.target.value, camera: current.camera?.source === 'door' && event.target.value !== 'hikvision' ? { ...current.camera, source: 'none' } : current.camera }))}>
              <option value="hikvision">Facial / biometria Hikvision</option><option value="cloud_scene">Tuya (cena)</option></select></label>
            <div className="xa-field"><span>Atalho</span><HotkeyRecorder value={door.hotkey || ''} onChange={value => change('hotkey', value)} onRecordingChange={setRecording} /></div>
            <label className="xa-field xa-full"><span>Câmera</span><select aria-label="Câmera" value={door.camera?.source || 'none'} onChange={event => cameraChange('source', event.target.value as CameraConfig['source'])}>
              <option value="none">Sem câmera vinculada</option>{isFacialDoor(door) && <option value="door">Câmera do próprio equipamento</option>}<option value="external">Outra câmera Hikvision</option></select></label>
          </div>
          {door.camera?.source === 'door' && <p className="xa-hint">Usa o stream secundário do equipamento para exibir vídeo contínuo.</p>}
          {door.camera?.source === 'external' && <details open><summary>Conexão da câmera</summary><div className="xa-fields">
            {cameraField('IP ou endereço', 'host')}{cameraField('Usuário', 'username')}{cameraField('Senha', 'password', 'password')}
            <label className="xa-field"><span>Canal</span><input type="number" min={1} max={9999} value={door.camera.channel ?? 1} onChange={event => cameraChange('channel', Number(event.target.value))} /></label>
            <label className="xa-field"><span>Protocolo</span><select value={door.camera.protocol || 'http'} onChange={event => cameraChange('protocol', event.target.value)}><option value="http">HTTP</option><option value="https">HTTPS</option></select></label>
            <label className="xa-field"><span>Porta</span><input type="number" min={1} max={65535} value={door.camera.port ?? (door.camera.protocol === 'https' ? 443 : 80)} onChange={event => cameraChange('port', Number(event.target.value))} /></label>
            <label className="xa-field"><span>Porta RTSP</span><input type="number" min={1} max={65535} value={door.camera.rtsp_port ?? 554} onChange={event => cameraChange('rtsp_port', Number(event.target.value))} /></label>
          </div><p className="xa-hint">Usa o stream secundário H.264 desta câmera para exibir vídeo contínuo.</p></details>}
          <details open={isNew}><summary>Dados de conexão</summary><div className="xa-fields">
            {isFacialDoor(door) ? <>
              {field('IP ou endereço', 'host')}{field('Usuário', 'username')}{field('Senha', 'password', 'password')}
              <label className="xa-field"><span>Número da porta</span><input type="number" min={1} max={255} value={door.door_id ?? 1} onChange={event => change('door_id', Number(event.target.value))} /></label>
              <label className="xa-field"><span>Protocolo</span><select value={door.protocol || 'http'} onChange={event => change('protocol', event.target.value)}><option value="http">HTTP</option><option value="https">HTTPS</option></select></label>
              <label className="xa-field"><span>Porta de conexão</span><input type="number" min={1} max={65535} value={door.port ?? (door.protocol === 'https' ? 443 : 80)} onChange={event => change('port', Number(event.target.value))} /></label>
            </> : <>{field('ID da cena', 'scene_id')}{field('ID da casa', 'home_id')}{field('ID do dispositivo (opcional)', 'device_id')}</>}
          </div></details>
          <label className="xa-check"><input type="checkbox" checked={door.enabled !== false} onChange={event => change('enabled', event.target.checked)} />Acesso habilitado</label>
          {deleting && <div className="xa-section"><p>Excluir este acesso e seu atalho?</p><button type="button" className="xa-delete" onClick={() => void save(true)}>Confirmar exclusão</button></div>}
        </> : !isDoorEditor ? <>
          <label className="xa-check"><input type="checkbox" checked={config.enabled !== false} onChange={event => setConfig(current => ({ ...current, enabled: event.target.checked }))} />Habilitar acionamentos</label>
          <label className="xa-check"><input type="checkbox" checked={config.hotkeys_enabled !== false} onChange={event => setConfig(current => ({ ...current, hotkeys_enabled: event.target.checked }))} />Atalhos globais de teclado</label>
          <label className="xa-check"><input type="checkbox" checked={config.feedback_sound !== false} onChange={event => setConfig(current => ({ ...current, feedback_sound: event.target.checked }))} />Som de confirmação</label>
          <label className="xa-check"><input type="checkbox" checked={config.feedback_notification !== false} onChange={event => setConfig(current => ({ ...current, feedback_notification: event.target.checked }))} />Notificação de acionamento</label>
          <div className="xa-section"><h3>Portas e câmeras da empresa</h3>
            <p>{cloud.config_sync_unlocked ? 'Sincronização habilitada. As alterações salvas serão compartilhadas com os PCs autorizados.' : 'Confirme a senha DEV uma vez neste PC para compartilhar e receber portas e câmeras.'}</p>
            {!cloud.config_sync_unlocked && <><label className="xa-field"><span>Senha DEV</span><input type="password" autoComplete="off" value={syncPassword} onChange={event=>setSyncPassword(event.target.value)} /></label>
              <button type="button" disabled={unlocking || !syncPassword} onClick={()=>void unlockSync()}>{unlocking ? 'Habilitando…' : 'Habilitar sincronização'}</button></>}
          </div>
          <div className="xa-section"><h3>Conta Tuya</h3><p>Conta {cloud.connected ? 'conectada' : 'desconectada'}</p>
            <details><summary>Conectar ou trocar conta</summary><label className="xa-field"><span>Código do usuário Tuya</span><input autoComplete="off" value={config.user_code || ''} onChange={event => setConfig(current => ({ ...current, user_code: event.target.value }))} /></label>
              <p className="xa-hint">Informe o código da conta e escaneie o QR Code no Tuya Smart.</p><button type="button" onClick={() => void generateQr()}><QrCode />{qrLoading ? 'Gerando…' : 'Gerar QR Code'}</button>
              {qr?.qr_image_data && <img className="xa-qr" src={qr.qr_image_data} alt="QR Code para login na Tuya" />}{qr && <p className="xa-hint">{qr.instructions || 'Escaneie com o Tuya Smart e confirme o login.'}</p>}
            </details>
          </div>
        </> : null}
      </fieldset>
      {error && <p className="xa-error" role="alert">{error}</p>}
    </form>
  </AccessDialog>;
}
