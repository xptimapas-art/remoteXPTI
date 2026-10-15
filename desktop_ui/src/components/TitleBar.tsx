import type { MouseEvent } from 'react';
import { Search, RotateCw, Ellipsis, DoorClosed, LayoutGrid, Map, Router, Plus } from 'lucide-react';
import { useDesktopWindow } from './desktopWindow';
import './TitleBar.css';

interface TitleBarProps {
  currentTab: 'servers' | 'map' | 'ajin' | 'doors';
  setCurrentTab: (tab: 'servers' | 'map' | 'ajin' | 'doors') => void;
  searchTerm: string; setSearchTerm: (term: string) => void;
  selectedGroup: string; setSelectedGroup: (group: string) => void; groups: string[];
  isDev: boolean; onRefresh: () => void; onAddServer: () => void; onOpenSettings: () => void;
  updateInfo?: { currentVersion: string; newVersion: string; updateReady: boolean; isApplying?: boolean; isDownloading?: boolean };
  onRestartUpdate?: () => void;
}
export function TitleBar({ currentTab, setCurrentTab, searchTerm, setSearchTerm, selectedGroup,
  setSelectedGroup, groups, isDev, onRefresh, onAddServer, onOpenSettings, updateInfo, onRestartUpdate }: TitleBarProps) {
  const { integrated, maximized, development, api } = useDesktopWindow();
  const interactive = (target: EventTarget) => (target as HTMLElement).closest('button,input,select,a,label');
  const drag = (event: MouseEvent<HTMLElement>) => {
    if (event.button === 0 && integrated && !interactive(event.target) && event.detail === 1) void api?.begin_drag().catch(console.error);
  };
  const maximize = (event: MouseEvent<HTMLElement>) => {
    if (integrated && !interactive(event.target)) void api?.toggle_maximize().catch(console.error);
  };
  const tabs = [{ id:'servers' as const,label:'Grade',Icon:LayoutGrid },{ id:'map' as const,label:'Mapa',Icon:Map },
    { id:'ajin' as const,label:'AJIN',Icon:Router },...(isDev ? [{ id:'doors' as const,label:'Portas e portões',Icon:DoorClosed }] : [])];
  return <>
    <header className={`xpti-titlebar ${integrated ? 'xpti-titlebar-integrated' : ''}`} onMouseDown={drag} onDoubleClick={maximize}>
      <span className="xpti-titlebar-network" aria-hidden="true" />
      <div className="xpti-brand"><img src="/imagens/xpti-facade-logo.svg" alt="XPTI · Tecnologias em Segurança" draggable={false} />
        <span className="xpti-product"><span className="xpti-product-name">RemoteXPTI</span>{development && <small>DEV</small>}</span></div>
      <nav className="xpti-tabs" aria-label="Navegação principal">{tabs.map(({id,label,Icon}) =>
        <button key={id} type="button" aria-current={currentTab === id ? 'page' : undefined} onClick={() => setCurrentTab(id)} title={label}>
          <Icon aria-hidden="true" /><span>{label}</span></button>)}</nav>
      <div className="xpti-titlebar-space" />
      <div className="xpti-titlebar-actions">
      {updateInfo?.updateReady ? <button className="xpti-update-ready" onClick={onRestartUpdate} disabled={updateInfo.isApplying}>
        {updateInfo.isApplying ? 'Instalando…' : `Reiniciar para ${updateInfo.newVersion}`}</button>
      : <button type="button" className="xpti-version" onClick={onOpenSettings} title={`v${updateInfo?.currentVersion || '—'}${isDev ? ' · Beta Tester' : ''}`}>
        {updateInfo?.isDownloading ? 'Baixando…' : `v${updateInfo?.currentVersion || '—'}`}</button>}
      <button type="button" className="xpti-settings" title="Configurações e Sincronização" aria-label="Configurações" onClick={onOpenSettings}><Ellipsis aria-hidden="true" /></button>
      </div>
      {integrated && <div className="xpti-window-controls" aria-label="Controles da janela">
        <button type="button" aria-label="Minimizar" title="Minimizar" onClick={() => void api?.minimize().catch(console.error)}><span className="xpti-system-icon" aria-hidden="true">{'\uE921'}</span></button>
        <button type="button" aria-label={maximized ? 'Restaurar janela' : 'Maximizar'} title={maximized ? 'Restaurar' : 'Maximizar'}
          onClick={() => void api?.toggle_maximize().catch(console.error)}><span className="xpti-system-icon" aria-hidden="true">{maximized ? '\uE923' : '\uE922'}</span></button>
        <button type="button" className="xpti-window-close" aria-label="Fechar janela" title="Fechar" onClick={() => void api?.close().catch(console.error)}><span className="xpti-system-icon" aria-hidden="true">{'\uE8BB'}</span></button>
      </div>}
    </header>
    {(currentTab === 'servers' || currentTab === 'map') && <div className="xpti-server-tools" aria-label="Ferramentas de servidores">
      <label className="xpti-search"><Search aria-hidden="true" /><input aria-label="Buscar servidor" placeholder="Buscar servidor, IP ou grupo…" value={searchTerm} onChange={event => setSearchTerm(event.target.value)} /></label>
      <select aria-label="Filtrar grupo" value={selectedGroup} onChange={event => setSelectedGroup(event.target.value)}>
        <option value="Todos os Grupos">Todos os Grupos</option>{groups.map(group => <option key={group} value={group}>{group}</option>)}</select>
      <div className="xpti-tools-spacer" />
      <button type="button" title="Atualizar Status Geral" aria-label="Atualizar Status Geral" onClick={onRefresh}><RotateCw aria-hidden="true" /></button>
      <button type="button" className="xpti-add-server" onClick={onAddServer}><Plus aria-hidden="true" />Novo servidor</button>
    </div>}
    {integrated && !maximized && <div className="xpti-resize-edges" aria-hidden="true">
      {['n','ne','e','se','s','sw','w','nw'].map(edge => <div key={edge} className={`xpti-resize-${edge}`}
        onMouseDown={event => { if(event.button === 0) {event.preventDefault();void api?.begin_resize(edge).catch(console.error);} }} />)}
    </div>}
  </>;
}
