export interface ONUItem {
  id: string | number;
  port: string;
  /** Geographic catalog identity, never sent to ONU control/registration endpoints. */
  catalog_number?: number;
  name?: string;
  desc?: string;
  notes?: string;
  map_enabled?: boolean;
  serial?: string;
  status?: string;
  uptime?: string;
  uptime_seconds?: number;
  uptime_detailed?: string;
  status_since?: string;
  vendor?: string;
  rx_power?: string | number;
  signal?: string;
  latitude?: number | null;
  longitude?: number | null;
  cameras?: { ip?: string; name?: string; status?: string; online?: boolean }[];
}

export interface InactivePoint {
  number: number;
  address: string;
  region?: string;
  latitude: number;
  longitude: number;
  map_enabled: false;
}

export interface AjinTelemetry {
  total: number; online: number; offline: number;
  total_cameras: number; active_problems: number | AjinEvent[];
  coleta_formatted: string;
  server?: { online: boolean; ip: string; checked_at: string };
  olt?: { modelo?: string; ip?: string };
  collector?: { status: 'connecting' | 'online' | 'unavailable'; endpoint: string; checked_at?: string };
  ports: { port: string; online: number; total: number }[] | Record<string, { online: number; total: number; label?: string }>;
  stale?: boolean;
  rows: ONUItem[];
  inactive_points?: InactivePoint[];
  events_history?: AjinEvent[];
  events?: AjinEvent[];
}

export interface AjinEvent {
  id?: string; port?: string; onu_id?: string | number; serial?: string;
  point_name?: string; name?: string; street_desc?: string; desc?: string;
  timestamp?: string; datetime?: string; since?: string;
  type?: string; status?: string;
  duration?: string; duration_seconds?: number;
  downtime_seconds?: number; downtime_formatted?: string;
}
export interface DiscoveredONU extends ONUItem {
  is_registered: boolean;
  is_unregistered?: boolean;
  point_name?: string;
  street_desc?: string;
}
export interface AjinScan {
  devices: DiscoveredONU[];
  total_found?: number;
  unregistered_count?: number;
}
export interface Registration {
  port: string; id: string; serial: string; name: string; desc: string;
}
export interface Incident {
  key: string; port: string; onuId: string; serial: string; name: string; address: string;
  opened: number | null; recovered: number | null;
  status: 'open' | 'resolved' | 'unconfirmed';
  durationSeconds?: number; durationLabel?: string;
}

export type StatusFilter = 'active' | 'all' | 'online' | 'offline' | 'disabled';
export type ONUStatus = 'online' | 'offline' | 'unknown' | 'disabled';
export type SortField = 'status' | 'name' | 'desc' | 'serial' | 'port' | 'vendor' | 'signal' | 'uptime';
const collator = new Intl.Collator('pt-BR', { numeric: true, sensitivity: 'base' });
export const pointName = (row: ONUItem) => String(row.name || '').trim() || `Ponto ${row.id}`;
export function onuStatus(row: ONUItem): ONUStatus {
  if (row.catalog_number !== undefined || row.map_enabled === false) return 'disabled';
  const status = String(row.status || '').trim().toLowerCase();
  return status === 'online' ? 'online' : status === 'offline' ? 'offline' : 'unknown';
}
export function hasCoordinates(row: { latitude?: number | null; longitude?: number | null }): boolean {
  return typeof row.latitude === 'number' && Number.isFinite(row.latitude) && Math.abs(row.latitude) <= 90
    && typeof row.longitude === 'number' && Number.isFinite(row.longitude) && Math.abs(row.longitude) <= 180;
}
export function canShowOnMap(row: ONUItem): boolean {
  return hasCoordinates(row);
}
/** UI projection only: catalog IDs do not represent physical ONUs. */
export function ajinRows(data: Pick<AjinTelemetry, 'rows' | 'inactive_points'>): ONUItem[] {
  const known = new Set(data.rows.map(row => String(row.name || '').trim().match(/^ponto\s+0*(\d+)$/i)?.[1]).filter(Boolean).map(Number));
  return [...data.rows, ...(data.inactive_points || []).filter(point => !known.has(point.number)).map(point => ({
    catalog_number:point.number, id:`catalog-${point.number}`, port:'', name:`Ponto ${String(point.number).padStart(2, '0')}`,
    desc:point.address, latitude:point.latitude, longitude:point.longitude, map_enabled:false, status:'Desativado',
  }))];
}
export function signalValue(row: ONUItem): string {
  const value = row.signal ?? row.rx_power;
  return value == null || String(value).trim() === '' ? '—' : String(value);
}
const normalize = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
export function matchesSearch(term: string, values: unknown[]) {
  return normalize(values.join(' ')).includes(normalize(term.trim()));
}
export const onuKey = (row: { port: string; id: string | number }) => JSON.stringify([row.port, String(row.id)]);
export function timestamp(value?: string): number | null {
  if (!value) return null;
  const br = value.match(/^(\d{2})\/(\d{2})\/(\d{4})(?: às)?[ T](\d{2}):(\d{2})(?::(\d{2}))?$/);
  const result = br ? new Date(Number(br[3]), Number(br[2]) - 1, Number(br[1]), Number(br[4]), Number(br[5]), Number(br[6] || 0)).getTime()
    : /^\d{4}-\d{2}-\d{2}T/.test(value) ? Date.parse(value) : NaN;
  return Number.isFinite(result) ? result : null;
}
export function formatStamp(value: number | null): string {
  return value === null ? '—' : new Date(value).toLocaleString('pt-BR').replace(',', '');
}
export function duration(seconds?: number): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—';
  const value = Math.floor(seconds), days = Math.floor(value / 86400), hours = Math.floor(value % 86400 / 3600), minutes = Math.floor(value % 3600 / 60);
  return days ? `${days}d ${hours}h` : hours ? `${hours}h ${minutes}min` : minutes ? `${minutes}min ${value % 60}s` : `${value}s`;
}

/** Pair collector transitions into outages. Current problems, not old falls, determine what is open. */
export function incidentHistory(data: AjinTelemetry): Incident[] {
  const rows = new Map(data.rows.map(row => [onuKey(row), row]));
  const incidents: Incident[] = [], pending = new Map<string, Incident>(), seen = new Set<string>();
  const eventIdentity = (event: AjinEvent) => JSON.stringify([event.port || '', String(event.onu_id ?? ''), (event.serial || '').replace(/[:-]/g, '').toUpperCase()]);
  const make = (event: AjinEvent, key: string): Incident => {
    const row = rows.get(onuKey({port:event.port || '', id:event.onu_id ?? ''}));
    return {key, port:event.port || '', onuId:String(event.onu_id ?? ''), serial:event.serial || row?.serial || '',
      name:event.point_name || event.name || (row ? pointName(row) : `Ponto ${event.onu_id ?? '—'}`),
      address:event.street_desc || event.desc || row?.desc || '', opened:null, recovered:null, status:'unconfirmed'};
  };
  const history = Array.isArray(data.events_history) ? data.events_history : Array.isArray(data.events) ? data.events : [];
  const events = history.filter(event => event && typeof event === 'object')
    .map(event => ({event, time:timestamp(event.timestamp) ?? timestamp(event.datetime)}))
    .sort((a, b) => (a.time ?? 0) - (b.time ?? 0));
  for (const {event, time} of events) {
    if (!event.port || event.onu_id == null) continue;
    const identity = eventIdentity(event), resolved = event.type === 'rose' || event.status === 'RESOLVED';
    if (!resolved && event.type !== 'fell' && event.status !== 'PROBLEM') continue;
    const unique = JSON.stringify([identity, event.type || event.status, event.timestamp || event.datetime || event.id]);
    if (seen.has(unique)) continue;
    seen.add(unique);
    if (!resolved) {
      // Repeated falls without recovery are one outage, even with different event IDs.
      if (!pending.has(identity)) {
        const incident = {...make(event, unique), opened:time};
        pending.set(identity, incident); incidents.push(incident);
      }
    } else {
      let incident = pending.get(identity);
      if (!incident || time === null || incident.opened === null || time < incident.opened) {
        incident = make(event, unique);
        if (time !== null && Number.isFinite(event.downtime_seconds) && event.downtime_seconds! > 0) incident.opened = time - event.downtime_seconds! * 1000;
        incidents.push(incident);
      } else pending.delete(identity);
      incident.status = 'resolved'; incident.recovered = time;
      incident.durationSeconds = time !== null && incident.opened !== null ? (time - incident.opened) / 1000
        : event.downtime_seconds && event.downtime_seconds > 0 ? event.downtime_seconds : undefined;
      incident.durationLabel = incident.durationSeconds === undefined && event.downtime_formatted !== '-' ? event.downtime_formatted : undefined;
    }
  }
  const active: AjinEvent[] = Array.isArray(data.active_problems) ? data.active_problems
    : data.rows.filter(row => onuStatus(row) === 'offline').map(row => ({port:row.port, onu_id:row.id, serial:row.serial, point_name:row.name,
      street_desc:row.desc, since:row.status_since, duration:row.uptime, duration_seconds:row.uptime_seconds}));
  for (const event of active) {
    if (!event || !event.port || event.onu_id == null) continue;
    const row = rows.get(onuKey({port:event.port, id:event.onu_id}));
    if (row && onuStatus(row) === 'disabled') continue;
    const identity = eventIdentity(event), opened = timestamp(event.since) ?? timestamp(event.timestamp);
    const existing = pending.get(identity);
    const compatible = existing && (opened === null || existing.opened === null || Math.abs(opened - existing.opened) <= 1000);
    const incident = compatible ? existing : make(event, 'active:' + identity);
    if (!compatible) incidents.push(incident);
    incident.opened = opened ?? incident.opened; incident.status = 'open';
    incident.durationSeconds = event.duration_seconds;
    incident.durationLabel = event.duration;
  }
  return incidents.sort((a, b) => (b.opened ?? b.recovered ?? 0) - (a.opened ?? a.recovered ?? 0));
}
export function filterRows(rows: ONUItem[], term: string, pon: string, status: StatusFilter, field: SortField, ascending: boolean) {
  const search = normalize(term.trim());
  return rows.filter(row => (!pon || (row.port || 'Sem porta') === pon) && (status === 'all' || (status === 'active' ? ['online', 'offline'].includes(onuStatus(row)) : onuStatus(row) === status))
    && (!search || normalize([pointName(row), row.desc, row.serial, row.port, row.vendor].join(' ')).includes(search)))
    .sort((a, b) => {
      let comparison: number;
      if (field === 'uptime' && Number.isFinite(a.uptime_seconds) && Number.isFinite(b.uptime_seconds)) {
        comparison = a.uptime_seconds! - b.uptime_seconds!;
      } else if (field === 'signal' && Number.isFinite(Number.parseFloat(signalValue(a))) && Number.isFinite(Number.parseFloat(signalValue(b)))) {
        comparison = Number.parseFloat(signalValue(a)) - Number.parseFloat(signalValue(b));
      } else {
        const value = (row: ONUItem) => field === 'name' ? pointName(row) : field === 'status' ? onuStatus(row) : field === 'signal' ? signalValue(row) : String(row[field] ?? '');
        comparison = collator.compare(value(a), value(b));
      }
      return (comparison || collator.compare(`${a.port}-${a.id}`, `${b.port}-${b.id}`)) * (ascending ? 1 : -1);
    });
}
export function portSummary(rows: ONUItem[]) {
  const ports = new Map<string, { port: string; total: number; online: number; offline: number }>();
  for (const row of rows) {
    const port = row.port || 'Sem porta';
    const counts = ports.get(port) || { port, total: 0, online: 0, offline: 0 };
    counts.total++;
    if (onuStatus(row) === 'online') counts.online++;
    if (onuStatus(row) === 'offline') counts.offline++;
    ports.set(port, counts);
  }
  return [...ports.values()].sort((a, b) => collator.compare(a.port, b.port));
}
export function parseCoordinates(latitude: string, longitude: string) {
  const lat = latitude.trim(), lon = longitude.trim();
  if (!lat && !lon) return { latitude: null, longitude: null };
  const decimal = /^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)$/;
  if (!decimal.test(lat) || !decimal.test(lon)) throw new Error('Use valores decimais para latitude e longitude.');
  const result = { latitude: Number(lat.replace(',', '.')), longitude: Number(lon.replace(',', '.')) };
  if (!lat || !lon || !hasCoordinates(result)) throw new Error('Informe latitude de −90 a 90 e longitude de −180 a 180, ou deixe ambas vazias.');
  return result;
}
export function telemetryCSV(rows: ONUItem[]): string {
  const cell = (value: unknown) => {
    let text = String(value ?? '');
    if (/^[\s]*[=+@-]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  };
  const values: unknown[][] = [['Status', 'ONU / Ponto', 'MAC / Serial', 'Descrição (Rua / Local)', 'Fabricante', 'Sinal', 'Tempo no status', 'Canal OLT']];
  for (const row of rows) values.push([row.status || 'Desconhecido', pointName(row), row.serial, row.desc, row.vendor, signalValue(row), row.uptime, row.port]);
  return '\uFEFF' + values.map(row => row.map(cell).join(';')).join('\r\n');
}
export async function readAjinResponse(response: Response): Promise<AjinTelemetry> {
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Não foi possível concluir a operação na AJIN.');
  if (!data.telemetry || !Array.isArray(data.telemetry.rows)) throw new Error('Resposta inválida do aplicativo. Tente atualizar novamente.');
  return data.telemetry;
}
