import os
import sys
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.resolve()

DATA_FILE = get_app_dir() / "servers.json"
KEY_FILE = get_app_dir() / ".secret.key"
MASTER_KEY = b"myJFkZlC1kOdsKoL0Glf120KMwUIfyjj09Waqem33TQ="

class CredentialVault:
    """Gerenciador de criptografia local para senhas."""
    def __init__(self, key_path: Path = KEY_FILE):
        self.key_path = key_path
        self.cipher = None
        self._init_cipher()

    def _init_cipher(self):
        if not HAS_CRYPTO:
            return
        
        if self.key_path.exists():
            try:
                key = self.key_path.read_bytes().strip()
                if key:
                    self.cipher = Fernet(key)
                    return
            except Exception:
                pass

        # Se não existe ou chave corrompida, grava e usa a MASTER_KEY do projeto
        try:
            self.key_path.write_bytes(MASTER_KEY)
            self.cipher = Fernet(MASTER_KEY)
        except Exception:
            self.cipher = Fernet(MASTER_KEY)

    def encrypt(self, text: str) -> str:
        if not text:
            return ""
        if not self.cipher:
            return text
        return self.cipher.encrypt(text.encode("utf-8")).decode("utf-8")

    def decrypt(self, encrypted_text: str) -> str:
        if not encrypted_text:
            return ""
        if not self.cipher:
            return encrypted_text
        try:
            return self.cipher.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")
        except Exception:
            # Se a chave do cliente for diferente, tenta com a MASTER_KEY e ressincroniza a chave
            try:
                master_cipher = Fernet(MASTER_KEY)
                decrypted = master_cipher.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")
                try:
                    self.key_path.write_bytes(MASTER_KEY)
                    self.cipher = master_cipher
                except Exception:
                    pass
                return decrypted
            except Exception:
                # Fallback se for texto legado ou chave alterada
                return encrypted_text


class StorageManager:
    """Gerenciador de persistência dos servidores."""
    def __init__(self, data_file: Path = DATA_FILE):
        self.data_file = data_file
        self.vault = CredentialVault()
        self.servers: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> List[Dict[str, Any]]:
        if not self.data_file.exists():
            self.servers = self._get_initial_templates()
            self.save()
            return self.servers

        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.servers = data.get("servers", [])
        except Exception as e:
            print(f"Erro ao carregar {self.data_file}: {e}")
            self.servers = []

        self._sync_official_groups_and_users()
        self._sync_coordinates()
        return self.servers

    def _sync_coordinates(self):
        """Sincroniza automaticamente as coordenadas geográficas dos servidores que não possuem."""
        try:
            from map_manager import resolve_server_coordinates
            changed = False
            for s in self.servers:
                if s.get("latitude") is None or s.get("longitude") is None:
                    coords = resolve_server_coordinates(s)
                    if coords:
                        s["latitude"] = coords[0]
                        s["longitude"] = coords[1]
                        changed = True
            if changed:
                self.save()
        except Exception as e:
            print(f"[StorageManager] Erro ao sincronizar coordenadas: {e}")

    def _sync_official_groups_and_users(self):
        """Sincroniza automaticamente as tags oficiais (SEJURI e BEMTEVI) e o usuário padrão bemtevi.net\\xpti."""
        sejuri_hosts = {
            "192.168.190.61",  # Feminino Chapeco
            "192.168.190.63",  # Joinville
            "192.168.190.64",  # UMAX
            "192.168.190.65",  # Industrial SCS
        }
        changed = False
        for s in self.servers:
            host = s.get("host", "").strip()
            if host in sejuri_hosts:
                if s.get("group") != "SEJURI":
                    s["group"] = "SEJURI"
                    changed = True
            else:
                if s.get("group") != "BEMTEVI":
                    s["group"] = "BEMTEVI"
                    changed = True
                if s.get("username") != r"bemtevi.net\xpti":
                    s["username"] = r"bemtevi.net\xpti"
                    changed = True

        if changed:
            self.save()

    def save(self):
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump({"servers": self.servers, "version": "1.0"}, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Erro ao salvar {self.data_file}: {e}")

    def _get_initial_templates(self) -> List[Dict[str, Any]]:
        """Gera um servidor de exemplo caso o arquivo seja novo."""
        return [
            {
                "id": str(uuid.uuid4()),
                "name": "Servidor Exemplo (Localhost)",
                "host": "127.0.0.1",
                "port": 3389,
                "username": "Administrador",
                "password": self.vault.encrypt("123456"),
                "group": "Demonstração",
                "fullscreen": True,
                "admin_mode": False,
                "multimon": False,
                "notes": "Servidor de exemplo criado automaticamente.",
                "created_at": datetime.now().isoformat()
            }
        ]

    def add_server(self, data: Dict[str, Any]) -> Dict[str, Any]:
        server_id = str(uuid.uuid4())
        plain_password = data.get("password", "")
        
        new_server = {
            "id": server_id,
            "name": data.get("name", "Sem Nome").strip(),
            "host": data.get("host", "").strip(),
            "port": int(data.get("port", 3389)),
            "username": data.get("username", "").strip(),
            "password": self.vault.encrypt(plain_password),
            "group": (data.get("group") or "BEMTEVI").strip(),
            "fullscreen": bool(data.get("fullscreen", True)),
            "admin_mode": bool(data.get("admin_mode", False)),
            "multimon": bool(data.get("multimon", False)),
            "notes": data.get("notes", "").strip(),
            "created_at": datetime.now().isoformat(),
            "last_connected": None
        }
        self.servers.append(new_server)
        self.save()
        return new_server

    def update_server(self, server_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for s in self.servers:
            if s["id"] == server_id:
                s["name"] = data.get("name", s["name"]).strip()
                s["host"] = data.get("host", s["host"]).strip()
                s["port"] = int(data.get("port", s.get("port", 3389)))
                s["username"] = data.get("username", s["username"]).strip()
                
                # Atualiza senha apenas se fornecida
                if "password" in data and data["password"] is not None:
                    s["password"] = self.vault.encrypt(data["password"])
                
                s["group"] = (data.get("group") or "BEMTEVI").strip()
                s["fullscreen"] = bool(data.get("fullscreen", s.get("fullscreen", True)))
                s["admin_mode"] = bool(data.get("admin_mode", s.get("admin_mode", False)))
                s["multimon"] = bool(data.get("multimon", s.get("multimon", False)))
                s["notes"] = data.get("notes", s.get("notes", "")).strip()
                
                self.save()
                return s
        return None

    def delete_server(self, server_id: str) -> bool:
        initial_len = len(self.servers)
        self.servers = [s for s in self.servers if s["id"] != server_id]
        if len(self.servers) < initial_len:
            self.save()
            return True
        return False

    def get_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        for s in self.servers:
            if s["id"] == server_id:
                server_copy = s.copy()
                server_copy["password_plain"] = self.vault.decrypt(s.get("password", ""))
                return server_copy
        return None

    def record_connection(self, server_id: str):
        for s in self.servers:
            if s["id"] == server_id:
                s["last_connected"] = datetime.now().isoformat()
                self.save()
                break

    def get_groups(self) -> List[str]:
        groups = set()
        for s in self.servers:
            grp = s.get("group")
            if grp:
                groups.add(grp)
        return sorted(list(groups))
