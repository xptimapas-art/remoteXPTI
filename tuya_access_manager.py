"""
tuya_access_manager.py - Gerenciador Central de Acesso a Portas e Portões Tuya.
Integração com Tuya Cloud (cenas Tap-to-Run), atalhos de teclado globais,
histórico de acessos e sincronização de status restrita a desenvolvedores.
"""

import io
import os
import sys
import time
import json
import base64
import winsound
import threading
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from logger import log
from config_manager import ConfigManager, get_config_dir
from runtime_paths import is_development
from native_hotkeys import NativeHotkeyManager

# Arquivo de configuração de portas e sessão
CONFIG_FILENAME = "doors_config.json"
SESSION_FILENAME = "session.json"

DEFAULT_USER_CODE = "BxLxxMC"
DEFAULT_SCHEME = "tuyaSmart"


def normalize_hotkey_for_keyboard(hk: str) -> str:
    """Normaliza strings de teclas para o formato canônico esperado pelo Windows/keyboard."""
    if not hk:
        return ""
    mapping = {
        "PAGEUP": "page up",
        "PAGEDOWN": "page down",
        "ARROWUP": "up",
        "ARROWDOWN": "down",
        "ARROWLEFT": "left",
        "ARROWRIGHT": "right",
        "ESCAPE": "esc",
        "ESC": "esc",
        "PRINTSCREEN": "print screen",
        "PRINTSCRN": "print screen",
        "PRTSCR": "print screen",
        "SCROLLLOCK": "scroll lock",
        "CAPSLOCK": "caps lock",
        "NUMLOCK": "num lock",
        "CONTROL": "ctrl",
        "CTRL": "ctrl",
        "ALT": "alt",
        "SHIFT": "shift",
    }
    parts = [p.strip() for p in hk.split("+") if p.strip()]
    normalized = []
    for p in parts:
        clean = p.upper().replace(" ", "").replace("_", "").replace("-", "")
        matched = mapping.get(clean)
        if matched:
            normalized.append(matched)
        elif p.upper().startswith("F") and p[1:].isdigit():
            normalized.append(p.lower())
        else:
            normalized.append(p.lower())
    return "+".join(normalized)


class TuyaAccessManager:
    """Gerenciador de portas Tuya, controle de disparo, atalhos e histórico."""

    _instance: Optional["TuyaAccessManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TuyaAccessManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._lock = threading.RLock()
        self._manager = None
        self._cloud_connected = False
        self._access_logs: List[Dict[str, Any]] = []
        self._last_hotkey_time: Dict[str, float] = {}
        self._registered_hotkeys: List[Any] = []
        self._polling_qr_thread: Optional[threading.Thread] = None
        self._native_hotkeys = None

        self.config_path = self._resolve_config_path()
        self.session_path = self._resolve_session_path()
        self.config = self.load_config()

    def background_init(self, is_embedded: bool = False):
        self._init_cloud_manager()
        if not is_embedded:
            self._native_hotkeys = NativeHotkeyManager(on_trigger_callback=self._on_native_hotkey_trigger)
            self._native_hotkeys.start()
            self.reload_hotkeys()

    def _resolve_config_path(self) -> Path:
        """Localiza o arquivo doors_config.json em %LOCALAPPDATA% ou na pasta do app."""
        appdata_path = get_config_dir() / CONFIG_FILENAME
        if is_development():
            return appdata_path
        local_path = Path(__file__).parent / CONFIG_FILENAME
        if appdata_path.exists():
            return appdata_path
        if local_path.exists():
            return local_path
        return local_path

    def _resolve_session_path(self) -> Path:
        """Localiza session.json com credenciais da Tuya."""
        appdata_path = get_config_dir() / SESSION_FILENAME
        if is_development():
            return appdata_path
        local_path = Path(__file__).parent / SESSION_FILENAME
        vscode_test_path = Path("c:/Users/XPTI/Documents/vscode/abrir porta tuya/session.json")

        if appdata_path.exists():
            return appdata_path
        if local_path.exists():
            return local_path
        if vscode_test_path.exists():
            return vscode_test_path
        return local_path

    def load_config(self) -> Dict[str, Any]:
        """Carrega configurações de portas."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    # Migração única: se nunca foi inicializado com a porta facial, adiciona-a uma vez
                    if not cfg.get("facial_initialized"):
                        has_facial = any(
                            d.get("id") == "door_facial_hikvision" or d.get("mode") in ("hikvision", "facial")
                            for d in cfg.get("doors", [])
                        )
                        if not has_facial:
                            cfg.setdefault("doors", []).append({
                                "id": "door_facial_hikvision",
                                "name": "Portaria Facial",
                                "device_name": "Facial Hikvision (DS-K1T)",
                                "mode": "hikvision",
                                "host": "192.168.12.94",
                                "port": 80,
                                "protocol": "http",
                                "username": "admin",
                                "password": "",
                                "door_id": 1,
                                "hotkey": "",
                                "enabled": True,
                                "last_triggered": None
                            })
                        cfg["facial_initialized"] = True
                        try:
                            with open(self.config_path, "w", encoding="utf-8") as fw:
                                json.dump(cfg, fw, indent=2, ensure_ascii=False)
                        except Exception:
                            pass
                    return cfg
            except Exception as e:
                log.error(f"[TuyaAccess] Erro ao carregar {self.config_path}: {e}")

        # Configuração padrão caso não exista arquivo
        if is_development():
            return {"enabled": False, "feedback_sound": False,
                    "feedback_notification": False, "user_code": "",
                    "facial_initialized": True, "doors": []}
        default_cfg = {
            "enabled": True,
            "feedback_sound": True,
            "feedback_notification": True,
            "user_code": DEFAULT_USER_CODE,
            "facial_initialized": True,
            "doors": [
                {
                    "id": "door_operacional",
                    "name": "Porta Operacional",
                    "device_name": "Porta sala Operacional",
                    "device_id": "eb4b91aa4fcc8a2788lfde",
                    "home_id": "100383937",
                    "scene_id": "o34EQAoAQQniX6Vk",
                    "scene_name": "Porta operacional",
                    "mode": "cloud_scene",
                    "hotkey": "F7",
                    "enabled": True,
                    "last_triggered": None
                },
                {
                    "id": "door_facial_hikvision",
                    "name": "Portaria Facial",
                    "device_name": "Facial Hikvision (DS-K1T)",
                    "mode": "hikvision",
                    "host": "192.168.12.94",
                    "port": 80,
                    "protocol": "http",
                    "username": "admin",
                    "password": "",
                    "door_id": 1,
                    "hotkey": "",
                    "enabled": True,
                    "last_triggered": None
                }
            ]
        }
        return default_cfg

    def save_config(self, new_config: Optional[Dict[str, Any]] = None, push_to_cloud: bool = True):
        """Salva a configuração atualizada e recarrega listeners."""
        with self._lock:
            updated = deepcopy(self.config)
            if new_config:
                updated.update(deepcopy(new_config))
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.config_path.parent,
                                                 prefix=".doors-", suffix=".tmp", delete=False) as f:
                    temporary_path = f.name
                    json.dump(updated, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary_path, self.config_path)
                self.config = updated
                log.info(f"[TuyaAccess] Configuração de portas salva em {self.config_path}")
                
                if push_to_cloud:
                    cloud_snapshot = deepcopy(updated)
                    def _push():
                        try:
                            from cloud_sync import CloudSyncManager
                            CloudSyncManager.push_doors_config(cloud_snapshot)
                        except Exception as e:
                            log.error(f"[TuyaAccess] Falha ao fazer push da config de portas: {e}")
                    threading.Thread(target=_push, daemon=True).start()
            except Exception as e:
                log.error(f"[TuyaAccess] Erro ao salvar config: {e}")
                raise
            finally:
                if temporary_path and os.path.exists(temporary_path):
                    os.unlink(temporary_path)

        # Recarrega os atalhos de teclado conforme a nova configuração
        self.reload_hotkeys()

    def save_door_config(self, door_id: str, door: Dict[str, Any], original: Optional[Dict[str, Any]],
                         delete: bool = False):
        """Edita um acesso sem substituir os demais; rejeita formulários desatualizados."""
        with self._lock:
            doors = deepcopy(self.config.get("doors", []))
            existing = next((item for item in doors if item.get("id") == door_id), None)
            runtime_fields = {"last_triggered", "cloud_online", "is_local"}
            def editable(item):
                return {key: value for key, value in item.items() if key not in runtime_fields} if item is not None else None
            if editable(existing) != editable(original):
                raise ValueError("Este acesso foi alterado em outra janela. Feche e abra a configuração novamente.")
            if door.get("id") != door_id:
                raise ValueError("Identificador do acesso inválido.")
            if delete:
                if existing is None:
                    raise ValueError("Este acesso não existe mais.")
                doors.remove(existing)
            else:
                updated = {**(existing or {}), **deepcopy(editable(door))}
                updated["name"] = str(updated.get("name", "")).strip()
                if not updated["name"]:
                    raise ValueError("Informe o nome do acesso.")
                hotkey = normalize_hotkey_for_keyboard(str(updated.get("hotkey", "")))
                if hotkey and updated.get("enabled", True) and any(
                    item.get("id") != door_id and item.get("enabled", True)
                    and normalize_hotkey_for_keyboard(str(item.get("hotkey", ""))) == hotkey for item in doors
                ):
                    raise ValueError("Este atalho já está em uso por outro acesso.")
                if existing is None:
                    doors.append(updated)
                else:
                    doors[doors.index(existing)] = updated
            self.save_config({"doors": doors})

    def _init_cloud_manager(self, force_sync: bool = False):
        """Inicializa e mantém em cache o cliente da Nuvem Tuya."""
        from cloud_sync import CloudSyncManager

        # No boot ou erro de sign invalid, buscamos a versão mais nova na nuvem
        if force_sync or getattr(self, "_first_init", True):
            self._first_init = False
            remote_session = CloudSyncManager.fetch_tuya_session()
            if remote_session:
                try:
                    parsed = json.loads(remote_session)
                    with open(self.session_path, "w", encoding="utf-8") as f:
                        json.dump(parsed, f, indent=2)
                    log.info("[TuyaAccess] Sessão Tuya sincronizada com Supabase.")
                except Exception as e:
                    log.error(f"[TuyaAccess] Erro ao aplicar sessão do Supabase: {e}")

        if not self.session_path.exists():
            log.warning(f"[TuyaAccess] session.json não encontrado em {self.session_path}")
            self._cloud_connected = False
            return

        try:
            import tuya_devices
            tuya_devices.on_session_saved = CloudSyncManager.push_tuya_session
            
            with open(self.session_path, "r", encoding="utf-8") as f:
                sess_data = json.load(f)
            self._manager = tuya_devices.build_manager(sess_data, str(self.session_path))
            self._cloud_connected = True
            log.info("[TuyaAccess] Cliente da Nuvem Tuya inicializado com sucesso.")
        except Exception as e:
            self._cloud_connected = False
            log.warning(f"[TuyaAccess] Falha ao conectar à Nuvem Tuya: {e}")

    def get_cloud_status(self) -> Dict[str, Any]:
        """Retorna o status atual da conexão com a nuvem Tuya."""
        has_session = self.session_path.exists()
        session_info: Dict[str, Any] = {}
        session_revision = ""
        if has_session:
            try:
                with open(self.session_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    session_revision = str(os.fstat(f.fileno()).st_mtime_ns)
                    session_info = {
                        "user_code": data.get("user_code", DEFAULT_USER_CODE),
                        "endpoint": data.get("endpoint", ""),
                        "token_expire_time": data.get("token_info", {}).get("expire_time", 0),
                        "has_refresh_token": bool(data.get("token_info", {}).get("refresh_token")),
                    }
            except Exception:
                pass

        return {
            "connected": self._cloud_connected,
            "session_revision": session_revision,
            "has_session_file": has_session,
            "session_info": session_info,
            "total_doors": len(self.config.get("doors", [])),
            "global_enabled": bool(self.config.get("enabled", True)),
            "hotkeys_enabled": bool(self.config.get("hotkeys_enabled", True)),
        }

    def get_doors(self) -> List[Dict[str, Any]]:
        """Retorna a lista de portas com status em tempo real."""
        doors = []
        for d in self.config.get("doors", []):
            door_copy = dict(d)
            if door_copy.get("mode") in ("hikvision", "facial", "isapi"):
                door_copy["cloud_online"] = True
                door_copy["is_local"] = True
            else:
                door_copy["cloud_online"] = self._cloud_connected
            doors.append(door_copy)
        return doors

    def get_door(self, door_id: str) -> Optional[Dict[str, Any]]:
        for d in self.config.get("doors", []):
            if d.get("id") == door_id:
                return dict(d)
        return None

    def _get_hikvision_config(self, door: Dict[str, Any]) -> Dict[str, Any]:
        """Obtém as configurações de conexão Hikvision para a porta com fallbacks inteligentes."""
        h_cfg = door.get("hikvision") if isinstance(door.get("hikvision"), dict) else {}

        file_cfg = {}
        paths_to_try = [
            Path(r"C:\Users\XPTI\Documents\vscode\portaria facial hikvision tuya\config\config.json"),
            Path(r"C:\Users\XPTI\Documents\vscode\portaria facial hikvision tuya\config.json"),
        ]
        for p in paths_to_try:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if "hikvision" in data and isinstance(data["hikvision"], dict):
                            file_cfg = data["hikvision"]
                            break
                except Exception:
                    pass

        raw_host = door.get("host") or h_cfg.get("host") or file_cfg.get("host") or "192.168.12.94"
        raw_port = door.get("port") if door.get("port") not in (None, "") else (h_cfg.get("port") or file_cfg.get("port") or 80)
        raw_proto = door.get("protocol") or h_cfg.get("protocol") or file_cfg.get("protocol") or "http"
        raw_user = door.get("username") or h_cfg.get("username") or file_cfg.get("username") or "admin"
        raw_pwd = door.get("password") if door.get("password") not in (None, "") else (h_cfg.get("password") or file_cfg.get("password") or "")
        raw_target = door.get("door_no") if door.get("door_no") not in (None, "") else (door.get("door_id") or h_cfg.get("door_id") or file_cfg.get("door_id") or 1)

        try:
            port = int(raw_port)
        except (ValueError, TypeError):
            port = 80

        try:
            target_door = int(raw_target)
        except (ValueError, TypeError):
            target_door = 1

        return {
            "host": str(raw_host).strip(),
            "port": port,
            "protocol": str(raw_proto).strip().lower(),
            "username": str(raw_user).strip(),
            "password": str(raw_pwd),
            "door_id": target_door,
        }

    def _open_hikvision_door(self, door: Dict[str, Any], source: str = "Painel DEV") -> Tuple[bool, str]:
        """Dispara comando ISAPI PUT para abrir a porta conectada ao terminal facial Hikvision."""
        door_id = door.get("id", "")
        door_name = door.get("name", "Facial Hikvision")
        cfg = self._get_hikvision_config(door)

        url = f"{cfg['protocol']}://{cfg['host']}:{cfg['port']}/ISAPI/AccessControl/RemoteControl/door/{cfg['door_id']}"
        xml_payload = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<RemoteControlDoor xmlns="http://www.hikvision.com/ver20/XMLSchema" version="2.0">\n'
            '    <cmd>open</cmd>\n'
            '</RemoteControlDoor>'
        )
        headers = {"Content-Type": "application/xml"}

        log.info(f"[TuyaAccess] Disparando abertura Facial Hikvision '{door_name}' ({url}) via {source}...")

        try:
            import requests
            from requests.auth import HTTPDigestAuth
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            auth = HTTPDigestAuth(cfg["username"], cfg["password"])
            resp = requests.put(url, data=xml_payload, headers=headers, auth=auth, timeout=5, verify=False)

            if resp.status_code == 200:
                xml_text = resp.text.strip()
                # Verifica se o terminal retornou erro em formato XML apesar do status 200 OK
                if "<statusCode>" in xml_text and "<statusCode>1</statusCode>" not in xml_text:
                    import xml.etree.ElementTree as ET
                    err_detail = "Comando rejeitado pelo terminal"
                    try:
                        root = ET.fromstring(xml_text)
                        sub_msg = root.findtext(".//{http://www.hikvision.com/ver20/XMLSchema}statusString") or root.findtext(".//statusString")
                        sub_code = root.findtext(".//{http://www.hikvision.com/ver20/XMLSchema}subStatusCode") or root.findtext(".//subStatusCode")
                        if sub_msg or sub_code:
                            err_detail = f"{sub_msg or ''} ({sub_code or ''})".strip()
                    except Exception:
                        pass
                    err_msg = f"Terminal facial '{door_name}' rejeitou abertura: {err_detail}"
                    log.error(f"[TuyaAccess] ❌ {err_msg}")
                    self._log_access(door_id, door_name, source, False, err_msg)
                    return False, err_msg

                now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
                door["last_triggered"] = now_iso
                for d in self.config.get("doors", []):
                    if d.get("id") == door_id:
                        d["last_triggered"] = now_iso
                        break

                if self.config.get("feedback_sound", True):
                    try:
                        winsound.Beep(1400, 120)
                    except Exception:
                        pass

                msg = f"Terminal Facial '{door_name}' acionado com sucesso!"
                log.info(f"[TuyaAccess] ✅ {msg}")
                self._log_access(door_id, door_name, source, True, msg)
                return True, msg
            elif resp.status_code == 401:
                err_msg = f"Erro 401: Usuário ou senha incorretos para o terminal facial '{door_name}'."
                log.error(f"[TuyaAccess] ❌ {err_msg}")
                self._log_access(door_id, door_name, source, False, err_msg)
                return False, err_msg
            elif resp.status_code == 403:
                err_msg = f"Erro 403: Acesso negado. Usuário '{cfg['username']}' sem permissão na facial."
                log.error(f"[TuyaAccess] ❌ {err_msg}")
                self._log_access(door_id, door_name, source, False, err_msg)
                return False, err_msg
            else:
                err_msg = f"Resposta inesperada do terminal facial (HTTP {resp.status_code}): {resp.text.strip()[:100]}"
                log.error(f"[TuyaAccess] ❌ {err_msg}")
                self._log_access(door_id, door_name, source, False, err_msg)
                return False, err_msg

        except requests.exceptions.ConnectTimeout:
            err_msg = f"Tempo limite esgotado ao conectar no terminal facial ({cfg['host']}:{cfg['port']})."
            log.error(f"[TuyaAccess] 🔌 {err_msg}")
            self._log_access(door_id, door_name, source, False, err_msg)
            return False, err_msg
        except requests.exceptions.ConnectionError:
            err_msg = f"Não foi possível conectar ao terminal facial ({cfg['host']}:{cfg['port']}). Verifique a rede."
            log.error(f"[TuyaAccess] 🔌 {err_msg}")
            self._log_access(door_id, door_name, source, False, err_msg)
            return False, err_msg
        except Exception as e:
            err_msg = f"Erro inesperado ao acionar terminal facial: {e}"
            log.error(f"[TuyaAccess] ❌ {err_msg}")
            self._log_access(door_id, door_name, source, False, err_msg)
            return False, err_msg

    def open_door(self, door_id: str, source: str = "Painel DEV") -> Tuple[bool, str]:
        """
        Executa a abertura da porta/portão na Nuvem Tuya ou Terminal Facial Hikvision.
        Retorna (sucesso, mensagem).
        """
        door = self.get_door(door_id)
        if not self.config.get("enabled", True):
            return False, "Os acionamentos estão desativados nas configurações."
        if not door:
            msg = f"Porta '{door_id}' não encontrada nas configurações."
            log.error(f"[TuyaAccess] {msg}")
            self._log_access(door_id, door_id, source, False, msg)
            return False, msg

        if not door.get("enabled", True):
            msg = f"A porta '{door.get('name')}' está desabilitada nas configurações."
            log.warning(f"[TuyaAccess] {msg}")
            self._log_access(door_id, door.get("name", ""), source, False, msg)
            return False, msg

        # Se for terminal facial Hikvision ISAPI (rede local), dispara diretamente
        if door.get("mode") in ("hikvision", "facial", "isapi"):
            return self._open_hikvision_door(door, source)

        if not self._manager:
            self._init_cloud_manager()

        if not self._manager:
            msg = "Sessão Tuya Cloud não está ativa ou session.json é inválido."
            log.error(f"[TuyaAccess] {msg}")
            self._log_access(door_id, door.get("name", ""), source, False, msg)
            return False, msg

        home_id = str(door.get("home_id", "100383937"))
        scene_id = str(door.get("scene_id", ""))
        scene_name = door.get("scene_name", door.get("name", "Porta"))

        if not scene_id:
            msg = f"ID da cena não configurado para a porta '{door.get('name')}'."
            log.error(f"[TuyaAccess] {msg}")
            self._log_access(door_id, door.get("name", ""), source, False, msg)
            return False, msg

        # Proactive sync se o token local está expirado ou perto de expirar
        if self._manager and hasattr(self._manager, "token_info"):
            try:
                expire_time = int(self._manager.token_info.get("expire_time") or 0)
                if expire_time > 1_000_000_000_000:
                    expire_time = expire_time // 1000
                if expire_time > 0 and time.time() >= expire_time - 15:
                    log.info("[TuyaAccess] Token perto da expiração. Verificando a nuvem para evitar colisões de refresh...")
                    import random
                    time.sleep(random.uniform(0.0, 3.0))
                    self._init_cloud_manager(force_sync=True)
            except (ValueError, TypeError):
                pass

        try:
            log.info(f"[TuyaAccess] Disparando cena '{scene_name}' ({scene_id}) via {source}...")
            self._manager.trigger_scene(home_id, scene_id)

            # Atualiza último acionamento em memória
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
            door["last_triggered"] = now_iso
            for d in self.config.get("doors", []):
                if d.get("id") == door_id:
                    d["last_triggered"] = now_iso
                    break

            # Feedback sonoro
            if self.config.get("feedback_sound", True):
                try:
                    winsound.Beep(1400, 120)
                except Exception:
                    pass

            msg = f"Porta '{door.get('name')}' acionada com sucesso!"
            log.info(f"[TuyaAccess] ✅ {msg}")
            self._log_access(door_id, door.get("name", ""), source, True, msg)
            return True, msg

        except Exception as e:
            import random
            err_str = str(e).lower()
            if "sign invalid" in err_str or "sign_invalid" in err_str or "token" in err_str:
                log.warning(f"[TuyaAccess] Erro de token detectado ({e}). Aguardando possível colisão e sincronizando...")
            else:
                log.warning(f"[TuyaAccess] Falha no primeiro disparo da cena '{scene_name}': {e}. Sincronizando antes de reconectar...")

            # Jitter para evitar thundering herd no banco e na Tuya API
            time.sleep(random.uniform(0.5, 2.0))
            force_sync = True

            # Tentativa de auto-recovery da sessão
            try:
                self._init_cloud_manager(force_sync=force_sync)
                if self._manager:
                    self._manager.trigger_scene(home_id, scene_id)
                    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
                    door["last_triggered"] = now_iso
                    for d in self.config.get("doors", []):
                        if d.get("id") == door_id:
                            d["last_triggered"] = now_iso
                            break
                    if self.config.get("feedback_sound", True):
                        try:
                            winsound.Beep(1400, 120)
                        except Exception:
                            pass
                    msg = f"Porta '{door.get('name')}' acionada com sucesso após reconexão!"
                    log.info(f"[TuyaAccess] ✅ {msg}")
                    self._log_access(door_id, door.get("name", ""), source, True, msg)
                    return True, msg
            except Exception as e2:
                err_str = str(e2).lower()
                if "nameresolutionerror" in err_str or "getaddrinfo" in err_str or "gaierror" in err_str:
                    err_msg = "Sem conexão com a internet"
                else:
                    err_msg = f"Erro no acionamento da Nuvem Tuya: {e2}"
                log.error(f"[TuyaAccess] ❌ {err_msg}")
                self._log_access(door_id, door.get("name", ""), source, False, err_msg)
                return False, err_msg

        return False, "Erro desconhecido no acionamento da porta."

    def _log_access(self, door_id: str, door_name: str, source: str, success: bool, detail: str):
        """Registra histórico de acionamento em memória (últimos 50 eventos)."""
        entry = {
            "id": f"log_{int(time.time() * 1000)}",
            "door_id": door_id,
            "door_name": door_name,
            "source": source,
            "success": success,
            "detail": detail,
            "timestamp": time.strftime("%H:%M:%S"),
            "date": time.strftime("%d/%m/%Y"),
        }
        with self._lock:
            self._access_logs.insert(0, entry)
            if len(self._access_logs) > 50:
                self._access_logs = self._access_logs[:50]

    def get_access_logs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._access_logs)

    # -------------------------------------------------------------
    # GESTÃO DE ATALHOS GLOBAIS DE TECLADO (HOTKEYS NATIVOS WIN32)
    # -------------------------------------------------------------
    def _on_native_hotkey_trigger(self, door_id: str, hotkey: str):
        """Callback invocado pelo NativeHotkeyManager quando uma tecla configurada é detectada."""
        log.info(f"[TuyaAccess] Atalho nativo [{hotkey}] acionado no Modo DEV! Executando disparo...")
        threading.Thread(
            target=self.open_door,
            args=(door_id, f"Atalho Teclado ({hotkey})"),
            daemon=True
        ).start()

    def start_hotkey_listener(self):
        """Inicia e registra os atalhos globais das portas configuradas."""
        self._native_hotkeys.start()
        self.reload_hotkeys()

    def reload_hotkeys(self):
        """Recarrega os atalhos nativos Win32 com base na configuração do disco."""
        with self._lock:
            self.config = self.load_config()
            
            if not self._native_hotkeys:
                return
                
            if not self.config.get("enabled", True) or not self.config.get("hotkeys_enabled", True):
                self._native_hotkeys.update_bindings([])
                log.info("[TuyaAccess] Módulo de portas desabilitado. Atalhos suspensos.")
                return

            doors = self.config.get("doors", [])
            self._native_hotkeys.update_bindings(doors)
            log.info(f"[TuyaAccess] {len(self._native_hotkeys.bindings)} atalho(s) nativo(s) ativo(s) no sistema.")

    # -------------------------------------------------------------
    # GERAÇÃO DE QR CODE PARA REAUTENTICAÇÃO TUYA SMART
    # -------------------------------------------------------------
    def generate_qr_login(self, user_code: Optional[str] = None) -> Dict[str, Any]:
        """Gera um token novo e o QR Code em base64 para login visual."""
        if self._polling_qr_thread and self._polling_qr_thread.is_alive():
            return {"success": False, "error": "Já existe um QR Code aguardando confirmação. Use o código atual ou aguarde expirar."}
        code = user_code or self.config.get("user_code", DEFAULT_USER_CODE)
        try:
            import tuya_devices
            import qrcode

            token = tuya_devices.mint_qr_token(code)
            qr_content = f"{DEFAULT_SCHEME}--qrLogin?token={token}"

            qr = qrcode.QRCode(box_size=8, border=2)
            qr.add_data(qr_content)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            data_uri = f"data:image/png;base64,{img_b64}"

            # Inicia thread em background para aguardar escaneamento
            self._start_qr_polling(token, code)

            return {
                "success": True,
                "token": token,
                "qr_image_data": data_uri,
                "user_code": code,
                "instructions": "Abra o aplicativo Tuya Smart no celular, toque no '+' no canto superior direito -> Escanear e confirme o login."
            }
        except Exception as e:
            log.error(f"[TuyaAccess] Erro ao gerar QR Code Tuya: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _start_qr_polling(self, token: str, user_code: str):
        """Thread que aguarda confirmação do escaneamento do QR Code."""
        def _poll_worker():
            try:
                import tuya_devices
                log.info(f"[TuyaAccess] Aguardando confirmação do QR Code (token: {token[:8]}...)...")
                # tuya_devices.poll_qr_token bloqueia até autenticar ou expirar
                manager = tuya_devices.poll_qr_token(token, user_code)
                if manager:
                    self._manager = manager
                    self._cloud_connected = True
                    log.info("[TuyaAccess] ✅ Login Tuya via QR Code confirmado com sucesso!")
                    # Salva nova sessão
                    if hasattr(manager, "session"):
                        with open(self.session_path, "w", encoding="utf-8") as f:
                            json.dump(manager.session, f, indent=2)
                        try:
                            from cloud_sync import CloudSyncManager
                            CloudSyncManager.push_tuya_session(json.dumps(manager.session))
                        except Exception as sync_e:
                            log.error(f"[TuyaAccess] Falha ao enviar sessão QR para Supabase: {sync_e}")
            except Exception as e:
                log.warning(f"[TuyaAccess] Polling do QR Code finalizado ou expirado: {e}")

        if self._polling_qr_thread and self._polling_qr_thread.is_alive():
            pass  # Já existe uma thread rodando
        else:
            self._polling_qr_thread = threading.Thread(target=_poll_worker, daemon=True)
            self._polling_qr_thread.start()
