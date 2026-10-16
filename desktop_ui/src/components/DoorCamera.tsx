import { useEffect, useRef, useState } from 'react';
import { Camera } from 'lucide-react';

function waitForEvent(target: EventTarget, name: string, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const cleanup = () => { target.removeEventListener(name, ready); target.removeEventListener('error', failed); signal.removeEventListener('abort', cancelled); };
    const ready = () => { cleanup(); resolve(); };
    const failed = () => { cleanup(); reject(new Error('Não foi possível reproduzir o stream secundário.')); };
    const cancelled = () => { cleanup(); reject(new DOMException('Stream encerrado', 'AbortError')); };
    if (signal.aborted) { cancelled(); return; }
    target.addEventListener(name, ready, { once: true }); target.addEventListener('error', failed, { once: true }); signal.addEventListener('abort', cancelled, { once: true });
  });
}

export function DoorCamera({ doorId, linked, active = true }: { doorId: string; linked: boolean; active?: boolean }) {
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const player = video.current;
    if (!linked || !active || !player) return;
    let disposed = false;
    let running = false;
    let retry: ReturnType<typeof setTimeout>;
    let request: AbortController | null = null;
    const connect = async () => {
      if (disposed || document.hidden || running) return;
      running = true; setError(''); setPlaying(false);
      const controller = new AbortController(); request = controller;
      let objectUrl = '';
      let watchdog: ReturnType<typeof setInterval> | undefined;
      let failure = '';
      try {
        if (typeof MediaSource === 'undefined') throw new Error('Este navegador não suporta a reprodução deste stream.');
        let lastData = performance.now();
        watchdog = setInterval(() => {
          if (performance.now() - lastData > 18000) { failure = 'O stream parou de responder. Reconectando…'; controller.abort(); }
        }, 1000);
        const response = await fetch(`/api/doors/${encodeURIComponent(doorId)}/camera/stream`, { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) {
          const data = await response.json();
          throw new Error(typeof data.detail === 'string' ? data.detail : 'Stream indisponível.');
        }
        if (disposed || controller.signal.aborted) return;
        const mime = response.headers.get('Content-Type') || '';
        if (!MediaSource.isTypeSupported(mime)) throw new Error('O perfil de vídeo da câmera não é compatível com este Windows.');
        if (!response.body) throw new Error('A câmera não enviou vídeo.');
        const media = new MediaSource();
        const opened = waitForEvent(media, 'sourceopen', controller.signal);
        objectUrl = URL.createObjectURL(media); player.src = objectUrl;
        await opened;
        const buffer = media.addSourceBuffer(mime);
        const reader = response.body.getReader();
        const append = async (bytes: Uint8Array) => {
          if (buffer.updating) await waitForEvent(buffer, 'updateend', controller.signal);
          const done = waitForEvent(buffer, 'updateend', controller.signal);
          const owned = new Uint8Array(bytes.byteLength); owned.set(bytes);
          try { buffer.appendBuffer(owned); await done; } catch (exception) { void done.catch(() => {}); throw exception; }
        };
        try {
          while (!disposed && !controller.signal.aborted) {
            const { done, value } = await reader.read();
            if (done) throw new Error('A câmera encerrou o stream. Reconectando…');
            lastData = performance.now();
            if (player.error) throw new Error('Não foi possível decodificar o vídeo da câmera.');
            await append(value);
            if (buffer.buffered.length) {
              const start = buffer.buffered.start(0), edge = buffer.buffered.end(buffer.buffered.length - 1);
              // Start with a short buffer; skip accumulated delay instead of replaying old footage.
              if (edge - start >= 0.6) {
                if (player.currentTime < start || edge - player.currentTime > 1.4) player.currentTime = Math.max(start, edge - 0.55);
                if (player.paused) void player.play().catch(() => {});
              }
              // Keep only a short playback window during long monitoring sessions.
              if (player.currentTime > 14 && start < player.currentTime - 12) {
                const removed = waitForEvent(buffer, 'updateend', controller.signal);
                try { buffer.remove(start, player.currentTime - 8); await removed; } catch (exception) { void removed.catch(() => {}); throw exception; }
              }
            }
          }
        } finally { await reader.cancel().catch(() => {}); }
      } catch (exception) {
        if (!disposed && !document.hidden) {
          if (failure) setError(failure);
          else if (!(exception instanceof DOMException && exception.name === 'AbortError')) setError(exception instanceof Error ? exception.message : 'Falha ao conectar o stream.');
          setPlaying(false);
        }
      } finally {
        clearInterval(watchdog); controller.abort();
        if (objectUrl && player.getAttribute('src') === objectUrl) { player.pause(); player.removeAttribute('src'); player.load(); }
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        request = null; running = false;
        if (!disposed && !document.hidden) retry = setTimeout(() => void connect(), 4000);
      }
    };
    const visibility = () => {
      clearTimeout(retry);
      if (document.hidden) { request?.abort(); player.pause(); }
      else void connect();
    };
    void connect(); document.addEventListener('visibilitychange', visibility);
    return () => { disposed = true; clearTimeout(retry); request?.abort(); player.pause(); document.removeEventListener('visibilitychange', visibility); };
  }, [doorId, linked, active]);
  return <div className="xa-camera-feed">
    {linked && <video ref={video} aria-label="Stream secundário da câmera" muted playsInline disablePictureInPicture
      onPlaying={() => setPlaying(true)} style={{ visibility: playing && active && !error ? 'visible' : 'hidden' }} />}
    {linked && playing && active && !error ? <span className="xa-camera-time">Ao vivo · secundário</span>
      : <div className="xa-camera-placeholder"><Camera /><span>{!linked ? 'Sem câmera' : !active ? 'Vídeo pausado' : error ? 'Vídeo indisponível' : 'Conectando stream…'}</span>
        <small>{!linked ? 'Vincule uma câmera nas configurações' : error || 'Stream secundário do equipamento'}</small></div>}
  </div>;
}
