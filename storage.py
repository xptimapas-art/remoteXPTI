import json
import uuid
import threading
from copy import deepcopy
from functools import wraps
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

from logger import log
from runtime_paths import get_data_dir
from atomic_storage import PersistenceError, write_json_atomic
from server_snapshot import CompleteServerSnapshot, SyncConflictError
from server_groups import DEFAULT_GROUPS, group_key, group_name
from server_location import resolve_location, location_update


def _locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return call


def _atomic_edit(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            previous = deepcopy(self._servers)
            previous_groups = self._groups.copy()
            revision = self._revision
            try:
                result = method(self, *args, **kwargs)
                if (self._servers != previous or self._groups != previous_groups) and self._revision == revision:
                    self._revision += 1
                return result
            except Exception:
                self._servers = previous
                self._groups = previous_groups
                self._revision = revision
                raise
    return call

def get_app_dir() -> Path:
    app_dir = get_data_dir()
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir

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

        # Se não existe ou chave corrompida, gera uma chave única
        try:
            new_key = Fernet.generate_key()
            self.key_path.write_bytes(new_key)
            self.cipher = Fernet(new_key)
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
    def __init__(self, data_file: Path = DATA_FILE, vault=None):
        self.data_file = data_file
        self._lock = threading.RLock()
        self._revision = 0
        self.vault = vault if vault is not None else CredentialVault()
        self._servers: List[Dict[str, Any]] = []
        self._groups = list(DEFAULT_GROUPS)
        self.load()

    @property
    def servers(self):
        with self._lock:
            return deepcopy(self._servers)

    @property
    def revision(self):
        with self._lock:
            return self._revision

    @_atomic_edit
    def toggle_favorite(self, server_id):
        for server in self._servers:
            if server["id"] == server_id:
                server["favorite"] = not bool(server.get("favorite", False))
                self.save()
                return server["favorite"]
        return None

    @_atomic_edit
    def load(self) -> List[Dict[str, Any]]:
        if not self.data_file.exists():
            self._servers = self._get_initial_templates()
            self.save()
            return deepcopy(self._servers)

        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict) or not isinstance(data.get("servers"), list):
                    raise ValueError("Formato de servidores inválido.")
                if any(not isinstance(row, dict) or not row.get("id") for row in data["servers"]):
                    raise ValueError("Registro de servidor inválido.")
                self._servers = data.get("servers", [])
                saved_groups = data.get("groups", list(DEFAULT_GROUPS))
                if not isinstance(saved_groups, list) or any(not isinstance(value, str) or not value.strip() for value in saved_groups):
                    raise ValueError("Formato de grupos inválido.")
                self._groups = list(dict.fromkeys(value.strip() for value in saved_groups))
        except (OSError, ValueError, TypeError) as error:
            raise PersistenceError("Não foi possível ler os servidores salvos. O arquivo original foi preservado.") from error

        # Garante que servidores legados possuam scope ('corporate' por padrão da empresa)
        for s in self._servers:
            if "scope" not in s:
                s["scope"] = "corporate"
                s["is_shared"] = True
            else:
                s["is_shared"] = (s.get("scope") == "corporate")

        self._sync_coordinates()
        return deepcopy(self._servers)

    @_atomic_edit
    def _sync_coordinates(self):
        """Sincroniza automaticamente as coordenadas geográficas dos servidores que não possuem."""
        try:
            from map_manager import resolve_server_coordinates
            changed = False
            candidate = deepcopy(self._servers)
            for s in candidate:
                if "location_source" in s:
                    continue
                if s.get("latitude") is None or s.get("longitude") is None:
                    coords = resolve_server_coordinates(s)
                    if coords:
                        s["latitude"] = coords[0]
                        s["longitude"] = coords[1]
                        changed = True
            if changed:
                self._servers = candidate
                self.save()
        except PersistenceError:
            raise
        except Exception as e:
            try:
                from logger import log
                log.warning(f"[StorageManager] Erro ao sincronizar coordenadas: {e}")
            except Exception:
                pass

    @_locked
    def save(self):
        """Commit under the same lock as the mutation; never hide a failed save."""
        write_json_atomic(self.data_file, {"servers": self._servers, "groups": self.get_groups(), "version": "1.0"})
        self._revision += 1

    def _get_initial_templates(self) -> List[Dict[str, Any]]:
        """Gera um servidor de exemplo caso o arquivo seja novo."""
        return [
            {
                "id": str(uuid.uuid4()),
                "name": "Servidor Exemplo (Localhost)",
                "host": "127.0.0.1",
                "port": 3389,
                "username": "Administrador",
                "password": self.vault.encrypt(""),
                "group": "Demonstração",
                "fullscreen": True,
                "admin_mode": False,
                "multimon": False,
                "notes": "Servidor de exemplo criado automaticamente.",
                "created_at": datetime.now().isoformat(),
                "latitude": None,
                "longitude": None
            }
        ]

    @_atomic_edit
    def add_server(self, data: Dict[str, Any]) -> Dict[str, Any]:
        server_id = str(uuid.uuid4())
        plain_password = data.get("password", "")
        
        lat = data.get("latitude")
        lon = data.get("longitude")
        location = {}
        if {"city", "state", "location_source"} & data.keys():
            location = resolve_location(data)
            lat, lon = location["latitude"], location["longitude"]
        elif lat is None or lon is None:
            try:
                from map_manager import resolve_server_coordinates
                coords = resolve_server_coordinates({"name": data.get("name", ""), "group": data.get("group", "")})
                if coords:
                    lat, lon = coords
            except Exception:
                pass

        scope = (data.get("scope") or "corporate").strip().lower()
        if scope not in ("corporate", "local"):
            scope = "corporate"

        new_server = {
            "id": server_id,
            "name": data.get("name", "Sem Nome").strip(),
            "host": data.get("host", "").strip(),
            "port": int(data.get("port", 3389)),
            "username": data.get("username", "").strip(),
            "password": self.vault.encrypt(plain_password),
            "group": (data.get("group") or "BEMTEVI").strip(),
            "scope": scope,
            "is_shared": (scope == "corporate"),
            "fullscreen": bool(data.get("fullscreen", True)),
            "admin_mode": bool(data.get("admin_mode", False)),
            "multimon": bool(data.get("multimon", False)),
            "notes": data.get("notes", "").strip(),
            "created_at": datetime.now().isoformat(),
            "last_connected": None,
            "latitude": lat,
            "longitude": lon
        }
        requested_group = group_name(new_server["group"])
        new_server["group"] = next((name for name in self.get_groups()
                                     if group_key(name) == group_key(requested_group)), requested_group)
        new_server.update(location)
        self._servers.append(new_server)
        self.save()
        return deepcopy(new_server)

    @_atomic_edit
    def update_server(self, server_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for s in self._servers:
            if s["id"] == server_id:
                location = location_update(s, data)
                s["name"] = data.get("name", s["name"]).strip()
                s["host"] = data.get("host", s["host"]).strip()
                s["port"] = int(data.get("port", s.get("port", 3389)))
                s["username"] = data.get("username", s["username"]).strip()
                
                # Atualiza senha APENAS se uma nova senha não vazia for fornecida
                new_pwd = data.get("password")
                if new_pwd and str(new_pwd).strip():
                    s["password"] = self.vault.encrypt(str(new_pwd))
                
                s["group"] = (data.get("group") or s.get("group", "BEMTEVI")).strip()
                s["fullscreen"] = bool(data.get("fullscreen", s.get("fullscreen", True)))
                s["admin_mode"] = bool(data.get("admin_mode", s.get("admin_mode", False)))
                s["multimon"] = bool(data.get("multimon", s.get("multimon", False)))
                s["notes"] = data.get("notes", s.get("notes", "")).strip()
                if "favorite" in data:
                    s["favorite"] = bool(data["favorite"])

                if "scope" in data:
                    sc = str(data["scope"]).strip().lower()
                    if sc in ("corporate", "local"):
                        s["scope"] = sc
                        s["is_shared"] = (sc == "corporate")

                # Atualiza coordenadas se fornecidas
                if "latitude" in data:
                    s["latitude"] = data["latitude"]
                if "longitude" in data:
                    s["longitude"] = data["longitude"]
                s.update(location)
                
                self.save()
                return deepcopy(s)
        return None

    @_atomic_edit
    def delete_server(self, server_id: str) -> bool:
        initial_len = len(self._servers)
        self._servers = [s for s in self._servers if s["id"] != server_id]
        if len(self._servers) < initial_len:
            self.save()
            return True
        return False

    @_locked
    def get_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        for s in self._servers:
            if s["id"] == server_id:
                server_copy = deepcopy(s)
                server_copy["password_plain"] = self.vault.decrypt(s.get("password", ""))
                return server_copy
        return None

    @_atomic_edit
    def record_connection(self, server_id: str):
        for s in self._servers:
            if s["id"] == server_id:
                s["last_connected"] = datetime.now().isoformat()
                self.save()
                break

    @_locked
    def get_groups(self) -> List[str]:
        groups = {group_key(name):name for name in self._groups}
        for s in self._servers:
            grp = s.get("group")
            if grp:
                groups.setdefault(group_key(grp), grp)
        return sorted(groups.values(), key=group_key)

    @_locked
    def group_details(self, *, allow_corporate=True):
        details = []
        for name in self.get_groups():
            members = [row for row in self._servers if group_key(row.get("group") or "") == group_key(name)]
            corporate = any(row.get("scope", "corporate") == "corporate" for row in members)
            details.append({"name":name, "server_count":len(members),
                            "rename_allowed":allow_corporate or not corporate,
                            "delete_allowed":not members})
        return details

    @_atomic_edit
    def add_group(self, name):
        name = group_name(name)
        if any(group_key(item) == group_key(name) for item in self.get_groups()):
            raise ValueError("Já existe um grupo com esse nome.")
        self._groups.append(name)
        self.save()
        return name

    @_atomic_edit
    def rename_group(self, name, new_name, *, allow_corporate=True):
        name, new_name = group_name(name), group_name(new_name)
        groups = self.get_groups()
        if not any(group_key(item) == group_key(name) for item in groups):
            raise KeyError(name)
        if any(group_key(item) == group_key(new_name) and group_key(item) != group_key(name) for item in groups):
            raise ValueError("Já existe um grupo com esse nome.")
        members = [row for row in self._servers if group_key(row.get("group") or "") == group_key(name)]
        if not allow_corporate and any(row.get("scope", "corporate") == "corporate" for row in members):
            raise PermissionError("No DEV, grupos usados por servidores da empresa são somente leitura.")
        self._groups = [new_name if group_key(item) == group_key(name) else item for item in groups]
        for row in members:
            row["group"] = new_name
        self.save()
        return new_name

    @_atomic_edit
    def delete_group(self, name):
        name = group_name(name)
        if not any(group_key(item) == group_key(name) for item in self.get_groups()):
            raise KeyError(name)
        if any(group_key(row.get("group") or "") == group_key(name) for row in self._servers):
            raise ValueError("O grupo contém servidores. Mova-os para outro grupo antes de excluir.")
        self._groups = [item for item in self.get_groups() if group_key(item) != group_key(name)]
        self.save()

    @_locked
    def get_corporate_servers(self) -> List[Dict[str, Any]]:
        """Retorna apenas os servidores corporativos compartilhados da empresa."""
        return deepcopy([s for s in self._servers if s.get("scope", "corporate") == "corporate"])

    @_locked
    def get_local_servers(self) -> List[Dict[str, Any]]:
        """Retorna apenas os servidores particulares cadastrados localmente pelo usuário."""
        return deepcopy([s for s in self._servers if s.get("scope") == "local"])

    @_locked
    def is_corporate(self, server_id: str) -> bool:
        """Informa se o servidor é corporativo (gerenciado pela empresa)."""
        for s in self._servers:
            if s["id"] == server_id:
                return s.get("scope", "corporate") == "corporate"
        return False

    @_atomic_edit
    def merge_cloud_servers(self, cloud_servers, *, expected_revision=None) -> Tuple[bool, int, int]:
        """
        Mescla a lista de servidores corporativos obtidos da nuvem (Supabase).
        - Atualiza ou insere servidores corporativos.
        - Remove servidores corporativos locais se foram excluídos na nuvem.
        - Preserva 100% dos servidores particulares com scope == 'local'.
        - Retorna uma tupla (houve_alteracao, qtd_inseridos, qtd_atualizados).
        """
        if expected_revision is not None and expected_revision != self._revision:
            raise SyncConflictError("Os servidores foram alterados durante a sincronização. Tente atualizar novamente.")
        complete = isinstance(cloud_servers, CompleteServerSnapshot)
        cloud_servers = list(cloud_servers.rows) if complete else list(cloud_servers)
        cloud_ids = [s.get("id") for s in cloud_servers if isinstance(s, dict)]
        if (len(cloud_ids) != len(cloud_servers) or
                any(not isinstance(sid, str) or not sid.strip() for sid in cloud_ids) or
                len(set(cloud_ids)) != len(cloud_ids)):
            raise ValueError("Lista de servidores inválida ou com IDs duplicados.")
        if not cloud_servers and not any(s.get("scope", "corporate") == "corporate" for s in self._servers):
            return False, 0, 0

        changed = False
        added_count = 0
        updated_count = 0

        cloud_ids = {str(cs.get("id")) for cs in cloud_servers if cs.get("id")}

        # 1. Remove servidores corporativos locais que foram excluídos da nuvem
        surviving_servers = []
        for s in self._servers:
            sid = str(s.get("id"))
            if complete and s.get("scope", "corporate") == "corporate" and sid not in cloud_ids:
                changed = True
            else:
                surviving_servers.append(s)
        if len(surviving_servers) != len(self._servers):
            write_json_atomic(self.data_file.with_name(self.data_file.name + ".pre-sync.bak"),
                              {"servers": self._servers, "version": "1.0"})
        self._servers = surviving_servers

        local_map = {str(s["id"]): s for s in self._servers}

        # 2. Atualiza existentes ou insere novos vindos da nuvem
        for cs in cloud_servers:
            cid = str(cs.get("id"))
            if not cid:
                continue

            if cid in local_map:
                loc = local_map[cid]
                if loc.get("scope", "corporate") == "corporate":
                    server_changed = False
                    for fld in ("name", "host", "port", "username", "group", "latitude", "longitude",
                                "admin_mode", "multimon", "fullscreen", "notes"):
                        val_cs = cs.get(fld)
                        val_loc = loc.get(fld)
                        if fld == "port" and val_cs is not None and val_loc is not None:
                            val_cs = int(val_cs)
                            val_loc = int(val_loc)
                        elif isinstance(val_cs, str):
                            val_cs = val_cs.strip()
                            val_loc = str(val_loc).strip() if val_loc is not None else ""
                        elif isinstance(val_cs, bool):
                            val_loc = bool(val_loc)

                        if val_cs is not None and val_cs != val_loc:
                            loc[fld] = cs[fld]
                            server_changed = True

                    if cs.get("password") and cs.get("password") != loc.get("password"):
                        loc["password"] = cs["password"]
                        server_changed = True

                    if server_changed:
                        changed = True
                        updated_count += 1
                    loc["scope"] = "corporate"
                    loc["is_shared"] = True
            else:
                # Novo servidor corporativo recebido da nuvem
                new_entry = {
                    "id": cid,
                    "name": str(cs.get("name", "Servidor")).strip(),
                    "host": str(cs.get("host", "")).strip(),
                    "port": int(cs.get("port", 3389)),
                    "username": str(cs.get("username", "")).strip(),
                    "password": cs.get("password", ""),
                    "group": str(cs.get("group", "BEMTEVI")).strip(),
                    "scope": "corporate",
                    "is_shared": True,
                    "fullscreen": bool(cs.get("fullscreen", True)),
                    "admin_mode": bool(cs.get("admin_mode", False)),
                    "multimon": bool(cs.get("multimon", False)),
                    "notes": str(cs.get("notes", "")).strip(),
                    "created_at": cs.get("created_at", datetime.now().isoformat()),
                    "last_connected": None,
                    "latitude": cs.get("latitude"),
                    "longitude": cs.get("longitude")
                }
                self._servers.append(new_entry)
                changed = True
                added_count += 1

        if changed:
            self.save()

        return changed, added_count, updated_count
