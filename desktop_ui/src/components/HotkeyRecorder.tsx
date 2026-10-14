import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { readResponse } from './doors';

interface CaptureResult { capture_id: string; state: string; hotkey?: string; error?: string }
export function HotkeyRecorder({ value, onChange, onRecordingChange }: {
  value: string; onChange: (value: string) => void; onRecordingChange: (recording: boolean) => void;
}) {
  const [captureId, setCaptureId] = useState('');
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const alive = useRef(true);
  const currentId = useRef('');
  const callbacks = useRef({ onChange, onRecordingChange });
  useEffect(() => { callbacks.current = { onChange, onRecordingChange }; }, [onChange, onRecordingChange]);
  const recording = starting || Boolean(captureId);
  const cancelRequest = (id: string) => fetch(`/api/doors/hotkey-capture/${encodeURIComponent(id)}`, { method: 'DELETE', keepalive: true }).catch(() => {});
  const cancel = () => {
    if (currentId.current) void cancelRequest(currentId.current);
    currentId.current = ''; setCaptureId(''); setStarting(false); callbacks.current.onRecordingChange(false);
  };
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; if (currentId.current) void cancelRequest(currentId.current); callbacks.current.onRecordingChange(false); };
  }, []);
  useEffect(() => {
    if (!captureId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    const poll = async () => {
      try {
        const result = await fetch(`/api/doors/hotkey-capture/${encodeURIComponent(captureId)}`, { signal: controller.signal }).then(readResponse<CaptureResult>);
        if (disposed) return;
        if (result.state === 'completed' || result.state === 'cancelled' || result.state === 'error') {
          if (result.state === 'completed' && result.hotkey) callbacks.current.onChange(result.hotkey);
          if (result.state === 'error') setError(result.error || 'Falha ao gravar a tecla.');
          currentId.current = ''; setCaptureId(''); callbacks.current.onRecordingChange(false);
        } else timer = setTimeout(() => void poll(), 150);
      } catch (exception) {
        if (!disposed) { setError(exception instanceof Error ? exception.message : 'Falha ao gravar a tecla.'); cancel(); }
      }
    };
    const blur = () => cancel();
    const keydown = (event: KeyboardEvent) => event.preventDefault();
    void poll(); window.addEventListener('blur', blur); document.addEventListener('keydown', keydown, true);
    return () => {
      disposed = true; controller.abort(); clearTimeout(timer);
      window.removeEventListener('blur', blur); document.removeEventListener('keydown', keydown, true);
    };
  }, [captureId]);
  const start = async () => {
    if (recording) { cancel(); return; }
    setError(''); setStarting(true); callbacks.current.onRecordingChange(true);
    try {
      // Do not abort this request: a late response must still cancel its native hook on unmount.
      const result = await fetch('/api/doors/hotkey-capture', { method: 'POST' }).then(readResponse<CaptureResult>);
      if (!alive.current) { void cancelRequest(result.capture_id); return; }
      currentId.current = result.capture_id; setCaptureId(result.capture_id);
    } catch (exception) {
      if (alive.current) { setError(exception instanceof Error ? exception.message : 'Falha ao iniciar a gravação.'); callbacks.current.onRecordingChange(false); }
    } finally { if (alive.current) setStarting(false); }
  };
  return <>
    <div className="xa-hotkey-control"><button type="button" aria-label="Gravar atalho" disabled={starting} onClick={() => void start()}>
      {starting ? 'Preparando…' : captureId ? 'Pressione a tecla…' : value || 'Clique para gravar'}</button>
      <button type="button" className="xa-icon" aria-label={recording ? 'Cancelar gravação' : 'Remover atalho'} disabled={starting} onClick={() => recording ? cancel() : onChange('')}><X /></button></div>
    {recording && <p className="xa-hint" role="status">Pressione a tecla ou combinação. Esc cancela.</p>}
    {error && <p className="xa-error" role="alert">{error}</p>}
  </>;
}
