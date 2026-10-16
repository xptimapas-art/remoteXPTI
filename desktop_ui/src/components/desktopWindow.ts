import { useEffect, useState } from 'react';

interface WindowState { integrated: boolean; maximized: boolean; development: boolean }
interface NativeWindowApi {
  window_state(): Promise<WindowState>;
  minimize(): Promise<void>;
  toggle_maximize(): Promise<void>;
  close(): Promise<void>;
  begin_drag(): Promise<void>;
  begin_resize(edge: string): Promise<void>;
}
declare global {
  interface Window { pywebview?: { api: NativeWindowApi } }
}

export function useDesktopWindow() {
  const [state, setState] = useState<WindowState>({ integrated: false, maximized: false, development: false });
  useEffect(() => {
    let active = true;
    const ready = () => {
      const native = window.pywebview?.api;
      if (typeof native?.window_state === 'function') native.window_state().then(value => { if (active) setState(value); }).catch(console.error);
    };
    const update = (event: Event) => setState((event as CustomEvent<WindowState>).detail);
    window.addEventListener('pywebviewready', ready);
    window.addEventListener('desktopWindowState', update);
    ready();
    return () => { active = false; window.removeEventListener('pywebviewready', ready); window.removeEventListener('desktopWindowState', update); };
  }, []);
  return { ...state, api: window.pywebview?.api };
}
