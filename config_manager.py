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
from pathlib import Path
from typing import Dict, Any, Optional
from logger import log

# Salt fixo seguro do projeto para PBKDF2
DEV_SALT = "RemoteXPTI_Salt_2026"
# Hash PBKDF2 (100.000 iterações) da senha mestre do desenvolvedor: XPT1%1414
DEV_PASSWORD_HASH = "d1a5398d82dbca928e51e31b09bd91707750ba9037888529b8f892721086b1cb"


def get_config_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    c_dir = Path(local_appdata) / "RemoteXPTI"
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
        self.file_path = get_config_file()
        self.data: Dict[str, Any] = {
            "update_channel": "public",      # "public" (1.x.0) ou "beta_tester" (1.1.x)
            "dev_authenticated": False,       # Se a sessão dev está ativa
            "dev_session_token": "",          # Token de sessão persistente
            "supabase_url": "",               # URL do projeto Supabase (opcional)
            "supabase_key": "",               # Anon key do Supabase (opcional)
            "cloud_sync_enabled": False,      # Se sincronização em nuvem está ativa
        }
        self.load()

    def load(self):
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.data.update(saved)
            except Exception as e:
                log.warning(f"[ConfigManager] Erro ao carregar {self.file_path}: {e}")

        # Valida token de sessão existente se houver
        if self.data.get("dev_authenticated") and self.data.get("dev_session_token"):
            expected_token = self._generate_session_token()
            if not secrets.compare_digest(self.data["dev_session_token"], expected_token):
                self.data["dev_authenticated"] = False
                self.data["dev_session_token"] = ""
                self.save()

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"[ConfigManager] Erro ao salvar config: {e}")

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
            self.data["dev_authenticated"] = True
            self.data["dev_session_token"] = self._generate_session_token()
            self.data["update_channel"] = "beta_tester"
            self.save()
            log.info("[ConfigManager] Autenticação de desenvolvedor bem-sucedida! Canal alterado para 'beta_tester'.")
            return True
        else:
            log.warning("[ConfigManager] Tentativa de login de desenvolvedor com senha incorreta.")
            return False

    def logout_dev(self):
        """Encerra a sessão de desenvolvedor e retorna ao canal público padrão."""
        self.data["dev_authenticated"] = False
        self.data["dev_session_token"] = ""
        self.data["update_channel"] = "public"
        self.save()
        log.info("[ConfigManager] Sessão de desenvolvedor encerrada. Retornado para canal 'public'.")

    def is_dev_authenticated(self) -> bool:
        return bool(self.data.get("dev_authenticated", False))

    def get_update_channel(self) -> str:
        # Se não for dev autenticado, força estritamente 'public'
        if not self.is_dev_authenticated():
            return "public"
        return self.data.get("update_channel", "public")

    def set_update_channel(self, channel: str):
        if not self.is_dev_authenticated() and channel != "public":
            log.warning("[ConfigManager] Tentativa de alterar canal para beta_tester sem autenticação.")
            return
        if channel in ("public", "beta_tester"):
            self.data["update_channel"] = channel
            self.save()
            log.info(f"[ConfigManager] Canal de atualização definido para: {channel}")

    def get_supabase_config(self) -> Dict[str, str]:
        return {
            "url": self.data.get("supabase_url", "").strip(),
            "key": self.data.get("supabase_key", "").strip(),
            "enabled": bool(self.data.get("cloud_sync_enabled", False))
        }

    def set_supabase_config(self, url: str, key: str, enabled: bool = True):
        self.data["supabase_url"] = url.strip()
        self.data["supabase_key"] = key.strip()
        self.data["cloud_sync_enabled"] = enabled and bool(url.strip() and key.strip())
        self.save()
        log.info(f"[ConfigManager] Configuração do Supabase atualizada (enabled={self.data['cloud_sync_enabled']}).")
