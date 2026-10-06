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
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from logger import log
from config_manager import ConfigManager, get_config_dir
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
        self._lock = threading.Lock()
        self._manager = None
        self._cloud_connected = False
        self._access_logs: List[Dict[str, Any]] = []
        self._last_hotkey_time: Dict[str, float] = {}
        self._registered_hotkeys: List[Any] = []
        self._polling_qr_thread: Optional[threading.Thread] = None
        self._native_hotkeys = NativeHotkeyManager(on_trigger_callback=self._on_native_hotkey_trigger)

        self.config_path = self._resolve_config_path()
        self.session_path = self._resolve_session_path()
        self.config = self.load_config()

        # Inicializa cliente da nuvem e listener de teclas
        self._init_cloud_manager()
        self.start_hotkey_listener()

    def _resolve_config_path(self) -> Path:
        """Localiza o arquivo doors_config.json em %LOCALAPPDATA% ou na pasta do app."""
        appdata_path = get_config_dir() / CONFIG_FILENAME
        local_path = Path(__file__).parent / CONFIG_FILENAME
        if appdata_path.exists():
            return appdata_path
        if local_path.exists():
            return local_path
        return local_path

    def _resolve_session_path(self) -> Path:
        """Localiza session.json com credenciais da Tuya."""
        appdata_path = get_config_dir() / SESSION_FILENAME
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
                    return json.load(f)
            except Exception as e:
                log.error(f"[TuyaAccess] Erro ao carregar {self.config_path}: {e}")

        # Configuração padrão caso não exista arquivo
        default_cfg = {
            "enabled": True,
            "feedback_sound": True,
            "feedback_notification": True,
            "user_code": DEFAULT_USER_CODE,
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
                }
            ]
        }
        return default_cfg

    def save_config(self, new_config: Optional[Dict[str, Any]] = None):
        """Salva a configuração atualizada e recarrega listeners."""
        with self._lock:
            if new_config:
                self.config.update(new_config)
            try:
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                log.info(f"[TuyaAccess] Configuração de portas salva em {self.config_path}")
            except Exception as e:
                log.error(f"[TuyaAccess] Erro ao salvar config: {e}")

        # Recarrega os atalhos de teclado conforme a nova configuração
        self.reload_hotkeys()

    def _init_cloud_manager(self):
        """Inicializa e mantém em cache o cliente da Nuvem Tuya."""
        if not self.session_path.exists():
            log.warning(f"[TuyaAccess] session.json não encontrado em {self.session_path}")
            self._cloud_connected = False
            return

        try:
            import tuya_devices
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
        if has_session:
            try:
                with open(self.session_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
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
            "has_session_file": has_session,
            "session_info": session_info,
            "total_doors": len(self.config.get("doors", [])),
            "global_enabled": bool(self.config.get("enabled", True)),
        }

    def get_doors(self) -> List[Dict[str, Any]]:
        """Retorna a lista de portas com status em tempo real."""
        doors = []
        for d in self.config.get("doors", []):
            door_copy = dict(d)
            door_copy["cloud_online"] = self._cloud_connected
            doors.append(door_copy)
        return doors

    def get_door(self, door_id: str) -> Optional[Dict[str, Any]]:
        for d in self.config.get("doors", []):
            if d.get("id") == door_id:
                return dict(d)
        return None

    def open_door(self, door_id: str, source: str = "Painel DEV") -> Tuple[bool, str]:
        """
        Executa a abertura da porta/portão na Nuvem Tuya.
        Retorna (sucesso, mensagem).
        """
        door = self.get_door(door_id)
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
            log.warning(f"[TuyaAccess] Falha no primeiro disparo da cena '{scene_name}': {e}. Tentando reconectar...")
            # Tentativa de auto-recovery da sessão
            try:
                self._init_cloud_manager()
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
                err_msg = f"Erro no acionamento da Nuvem Tuya: {e2}"
                log.error(f"[TuyaAccess] ❌ {err_msg}")
                self._log_access(door_id, door.get("name", ""), source, False, str(e2))
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
            if not self.config.get("enabled", True):
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
            except Exception as e:
                log.warning(f"[TuyaAccess] Polling do QR Code finalizado ou expirado: {e}")

        if self._polling_qr_thread and self._polling_qr_thread.is_alive():
            pass  # Já existe uma thread rodando
        else:
            self._polling_qr_thread = threading.Thread(target=_poll_worker, daemon=True)
            self._polling_qr_thread.start()
