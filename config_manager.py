r"""
Módulo de Configurações e Autenticação do Desenvolvedor do RemoteXPTI.
Armazena preferências em %LOCALAPPDATA%\RemoteXPTI\config.json.
Controla o acesso restrito ao modo desenvolvedor e aos canais de versão.
"""

import os
import sys
import json
import hashlib
import secrets
import threading
from copy import deepcopy
from pathlib import Path
from typing import Dict, Any, Optional
from logger import log
from runtime_paths import get_profile_dir, is_development
from atomic_storage import PersistenceError, write_json_atomic

# Salt fixo seguro do projeto para PBKDF2
DEV_SALT = "RemoteXPTI_Salt_2026"
# Hash da credencial DEV legada; não incluir a senha no código.
DEV_PASSWORD_HASH = "d1a5398d82dbca928e51e31b09bd91707750ba9037888529b8f892721086b1cb"


# Credenciais oficiais padrão da nuvem corporativa (Supabase da XPti)
DEFAULT_SUPABASE_URL = "https://rdxrxkoivbzfzncjfrkn.supabase.co"
DEFAULT_SUPABASE_KEY = "sb_publishable_11nb3dWkWx2N8fY-bGK4Jw_YjVBJ3L1"


def get_config_dir() -> Path:
    c_dir = get_profile_dir()
    c_dir.mkdir(parents=True, exist_ok=True)
    return c_dir


def get_config_file() -> Path:
    return get_config_dir() / "config.json"


class ConfigManager:
    """Gerencia configurações de canais, sincronização e sessão de desenvolvedor."""

    _instance: Optional["ConfigManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._lock = threading.RLock()
        self.file_path = get_config_file()
        self.data: Dict[str, Any] = {
            "update_channel": "public",      # "public" (estável) ou "beta_tester" (inclui prerelease)
            "dev_authenticated": False,       # Se a sessão dev está ativa
            "dev_session_token": "",          # Token de sessão persistente
            "supabase_url": DEFAULT_SUPABASE_URL,
            "supabase_key": DEFAULT_SUPABASE_KEY,
            "cloud_sync_enabled": not is_development(),
            # The DEV uses the same Tuya login as clients. Token rotation must
            # propagate even while server/access configuration writes are off.
            "tuya_session_sync_enabled": True,
            "doors_config_sync_enabled": True,
        }
        self.load()

    def load(self):
        if not hasattr(self, "_lock"):
            self._lock = threading.RLock()
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if not isinstance(saved, dict):
                        raise ValueError("Configuração inválida.")
                    self.data.update(saved)
            except (OSError, ValueError, TypeError) as error:
                raise PersistenceError("Não foi possível ler as configurações salvas. O arquivo original foi preservado.") from error
        self._persisted_data = deepcopy(self.data)

        # Atualiza as credenciais padrão sem desfazer a opção de desligar a nuvem.
        cur_url = self.data.get("supabase_url", "").strip()
        cur_key = self.data.get("supabase_key", "").strip()
        if not cur_url or not cur_key or cur_url == DEFAULT_SUPABASE_URL:
            self.data["supabase_url"] = DEFAULT_SUPABASE_URL
            self.data["supabase_key"] = DEFAULT_SUPABASE_KEY
            self.save()

        # Valida token de sessão existente se houver
        if self.data.get("dev_authenticated") and self.data.get("dev_session_token"):
            expected_token = self._generate_session_token()
            if not secrets.compare_digest(self.data["dev_session_token"], expected_token):
                self.data["dev_authenticated"] = False
                self.data["dev_session_token"] = ""
                self.save()

    def save(self):
        with self._lock:
            try:
                write_json_atomic(self.file_path, self.data)
            except PersistenceError:
                self.data = deepcopy(self._persisted_data)
                raise
            self._persisted_data = deepcopy(self.data)

    def _settings_lock(self):
        if not hasattr(self, "_lock"):
            self._lock = threading.RLock()
        return self._lock

    def _update_settings(self, changes, remove=()):
        with self._settings_lock():
            updated = deepcopy(self.data)
            updated.update(changes)
            for field in remove:
                updated.pop(field, None)
            self.data = updated
            self.save()

    def _hash_password(self, password: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            DEV_SALT.encode("utf-8"),
            100000
        ).hex()

    def _generate_session_token(self) -> str:
        # Token derivado do hash da senha + salt de máquina
        machine_seed = os.environ.get("COMPUTERNAME", "XPTI_NODE") + os.environ.get("USERNAME", "USER")
        return hashlib.sha256(f"{DEV_PASSWORD_HASH}_{machine_seed}_{DEV_SALT}".encode("utf-8")).hexdigest()

    def authenticate_dev(self, password: str) -> bool:
        """Valida a senha de desenvolvedor e ativa a sessão persistente."""
        computed = self._hash_password(password.strip())
        if secrets.compare_digest(computed, DEV_PASSWORD_HASH):
            from shared_doors import password_key, protect_key
            changes = {"dev_authenticated": True, "dev_session_token": self._generate_session_token(),
                       "update_channel": "beta_tester"}
            try:
                changes["doors_sync_key"] = protect_key(password_key(password))
            except OSError:
                log.warning("[ConfigManager] Não foi possível proteger a chave de sincronização neste Windows.")
            self._update_settings(changes)
            log.info("[ConfigManager] Autenticação de desenvolvedor bem-sucedida! Canal alterado para 'beta_tester'.")
            return True
        else:
            log.warning("[ConfigManager] Tentativa de login de desenvolvedor com senha incorreta.")
            return False

    def logout_dev(self):
        """Encerra a sessão de desenvolvedor e retorna ao canal público padrão."""
        self._update_settings({"dev_authenticated": False, "dev_session_token": "", "update_channel": "public"},
                              remove=("doors_sync_key",))
        log.info("[ConfigManager] Sessão de desenvolvedor encerrada. Retornado para canal 'public'.")

    def is_dev_authenticated(self) -> bool:
        with self._settings_lock():
            return bool(self.data.get("dev_authenticated", False))

    def get_doors_sync_key(self):
        with self._settings_lock():
            if not self.is_dev_authenticated() or not self.data.get("doors_sync_key"):
                return None
            protected = self.data["doors_sync_key"]
        from shared_doors import protect_key
        try:
            return protect_key(protected, decrypt=True)
        except (OSError, ValueError):
            return None

    def get_update_channel(self) -> str:
        # Se não for dev autenticado, força estritamente 'public'
        with self._settings_lock():
            if not self.is_dev_authenticated():
                return "public"
            return self.data.get("update_channel", "public")

    def set_update_channel(self, channel: str):
        if not self.is_dev_authenticated() and channel != "public":
            log.warning("[ConfigManager] Tentativa de alterar canal para beta_tester sem autenticação.")
            return
        if channel in ("public", "beta_tester"):
            self._update_settings({"update_channel": channel})
            log.info(f"[ConfigManager] Canal de atualização definido para: {channel}")

    def get_supabase_config(self) -> Dict[str, str]:
        with self._settings_lock():
            data = deepcopy(self.data)
        url = data.get("supabase_url", "").strip() or DEFAULT_SUPABASE_URL
        key = data.get("supabase_key", "").strip() or DEFAULT_SUPABASE_KEY
        enabled = data.get("cloud_sync_enabled", True)
        return {
            "url": url,
            "key": key,
            "enabled": bool(enabled and url and key),
            # Source checkouts receive company data, independently of the old
            # bidirectional switch. Server writes have a separate hard guard.
            "server_pull_enabled": bool((is_development() or enabled) and url and key),
            "session_sync_enabled": bool(data.get("tuya_session_sync_enabled", enabled) and url and key),
            "doors_sync_enabled": bool(data.get("doors_config_sync_enabled", True) and url and key),
        }

    def set_supabase_config(self, url: str, key: str, enabled: bool = True):
        self._update_settings({"supabase_url": url.strip(), "supabase_key": key.strip(),
                               "cloud_sync_enabled": enabled and bool(url.strip() and key.strip())})
        log.info(f"[ConfigManager] Configuração do Supabase atualizada (enabled={self.data['cloud_sync_enabled']}).")
