import type { KeyboardEvent } from 'react';

export const BRAZIL_STATES = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' ');
export interface ServerDraft {
  name: string; host: string; port: string; username: string; password: string; group: string;
  city: string; state: string; latitude: string; longitude: string; notes: string;
  fullscreen: boolean; admin_mode: boolean; multimon: boolean;
}
export const emptyServerDraft = (): ServerDraft => ({
  name: '', host: '', port: '3389', username: '', password: '', group: 'BEMTEVI',
  city: '', state: '', latitude: '', longitude: '', notes: '',
  fullscreen: true, admin_mode: false, multimon: false,
});
export interface ServerGroup {
  name: string; server_count: number; rename_allowed: boolean; delete_allowed: boolean;
}
export function parseCoordinate(value: string, limit: number): number | null {
  if (!/^[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)$/.test(value.trim())) return null;
  const number = Number(value.trim().replace(',', '.'));
  return Number.isFinite(number) && Math.abs(number) <= limit ? number : null;
}
export function pastedCoordinates(text: string): [string, string] | null {
  const pair = text.match(/^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*,\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*$/)
    || text.match(/^\s*([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))\s*[;\n]\s*([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))\s*$/);
  return pair ? [pair[1], pair[2]] : null;
}
export function serverPayload(draft: ServerDraft) {
  const name = draft.name.trim(), host = draft.host.trim(), port = Number(draft.port);
  if (!name || !host) throw new Error('Nome e IP/hostname são obrigatórios.');
  if (!draft.port.trim() || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Informe uma porta entre 1 e 65535.');
  if (!draft.group.trim()) throw new Error('Selecione ou crie um grupo.');
  let latitude: number | null = null, longitude: number | null = null;
  if (draft.latitude.trim() || draft.longitude.trim()) {
    latitude = parseCoordinate(draft.latitude, 90);
    longitude = parseCoordinate(draft.longitude, 180);
    if (latitude === null || longitude === null) throw new Error('Informe latitude (-90 a 90) e longitude (-180 a 180) válidas.');
  } else if (Boolean(draft.city.trim()) !== Boolean(draft.state)) {
    throw new Error('Informe cidade e estado juntos para usar uma localização aproximada.');
  }
  return { ...draft, name, host, port, username: draft.username.trim(), group: draft.group.trim(),
    city: draft.city.trim(), state: draft.state, latitude, longitude, notes: draft.notes.trim() };
}
export async function serverRequest(path: string, method = 'GET', body?: unknown): Promise<Record<string, unknown>> {
  const response = await fetch(path, { method, headers: { 'Content-Type': 'application/json' },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(15000) });
  let data: unknown;
  try { data = await response.json(); }
  catch { throw new Error('Não foi possível confirmar a operação. Atualize a lista antes de repetir.'); }
  if (!data || typeof data !== 'object') throw new Error('O app não confirmou a operação. Atualize a lista antes de repetir.');
  const result = data as Record<string, unknown>;
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Não foi possível salvar. Confira os dados e tente novamente.');
  return result;
}
export function readServerGroups(data: Record<string, unknown>): ServerGroup[] {
  if (!Array.isArray(data.groups) || data.groups.some(item => !item || typeof item.name !== 'string'
    || !Number.isInteger(item.server_count) || item.server_count < 0
    || typeof item.rename_allowed !== 'boolean' || typeof item.delete_allowed !== 'boolean')) {
    throw new Error('O app não confirmou a lista de grupos.');
  }
  return data.groups as ServerGroup[];
}
export function containDialogFocus(event: KeyboardEvent<HTMLElement>) {
  if (event.key !== 'Tab') return;
  const focusable = [...event.currentTarget.querySelectorAll<HTMLElement>(
    'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary',
  )].filter(element => element.getClientRects().length && !element.closest('[inert]'));
  const first = focusable[0], last = focusable.at(-1);
  if (event.shiftKey && (document.activeElement === first || !event.currentTarget.contains(document.activeElement))) {
    event.preventDefault(); last?.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault(); first?.focus();
  }
}
