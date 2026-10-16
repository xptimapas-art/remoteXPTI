export interface CameraConfig {
  source?: 'none' | 'door' | 'external'; host?: string; port?: number; protocol?: string;
  username?: string; password?: string; channel?: number; rtsp_port?: number;
}
export interface DoorConfig {
  id: string; name: string; device_name?: string; device_id?: string; home_id?: string;
  scene_id?: string; scene_name?: string; mode?: string; host?: string; port?: number;
  protocol?: string; username?: string; password?: string; door_id?: number; hotkey?: string;
  enabled?: boolean; is_local?: boolean; cloud_online?: boolean; camera?: CameraConfig;
  [key: string]: unknown;
}
export interface DoorsConfig {
  enabled?: boolean; hotkeys_enabled?: boolean; feedback_sound?: boolean; feedback_notification?: boolean;
  user_code?: string; doors?: DoorConfig[];
}
export interface CloudStatus { connected?: boolean; global_enabled?: boolean; hotkeys_enabled?: boolean; session_revision?: string; config_sync_unlocked?: boolean }
export const isFacialDoor = (door: DoorConfig) => ['hikvision', 'facial', 'isapi'].includes(door.mode || '');
export const openDoorLabel = (door: DoorConfig) => /port[aã]o|garagem/i.test(door.name) ? 'Abrir Portão' : 'Abrir Porta';
export async function readResponse<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || data.success === false) throw new Error(typeof data.detail === 'string' ? data.detail : 'Não foi possível concluir a operação.');
  return data as T;
}
