"""
Módulo de Sincronização em Nuvem (Supabase) do RemoteXPTI.
Permite sincronizar servidores e configurações entre a central e os clientes.
Funciona via HTTPS REST padrão com urllib.request (zero dependências pesadas).
"""

import json
import urllib.request
import urllib.error
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
from config_manager import ConfigManager
from logger import log


class CloudSyncManager:
    """Gerenciador de sincronização com o banco de dados Supabase."""

    @staticmethod
    def is_configured() -> bool:
        cfg = ConfigManager().get_supabase_config()
        return bool(cfg.get("enabled") and cfg.get("url") and cfg.get("key"))

    @staticmethod
    def can_share_doors() -> bool:
        manager = ConfigManager()
        cfg = manager.get_supabase_config()
        return bool(cfg.get("doors_sync_enabled") and manager.get_doors_sync_key())

    @classmethod
    def _read_doors_notes(cls, cfg):
        url = f"{cls._clean_base_url(cfg['url'])}/rest/v1/servers?id=eq.eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee&select=notes"
        req = urllib.request.Request(url, headers=cls._get_headers(cfg["key"]))
        with urllib.request.urlopen(req, timeout=8.0) as response:
            rows = json.loads(response.read().decode("utf-8"))
        return rows[0].get("notes") if rows else None

    @classmethod
    def _push_shared_doors(cls, config, cfg):
        from shared_doors import FIELD, decrypt_config, encrypt_config, revision, shared_config
        key = ConfigManager().get_doors_sync_key()
        if not key:
            return False
        try:
            previous = cls._read_doors_notes(cfg)
            old = json.loads(previous) if previous else {}
            if FIELD in old:
                existing = decrypt_config(old, key)
                if existing == shared_config(config):
                    config["_shared_revision"] = revision(previous)
                    return True
                if config.get("_shared_revision") != revision(previous):
                    raise ValueError("As portas foram alteradas em outro PC. Atualize antes de salvar.")
            # Old clients keep their Tuya scenes; private camera/facial settings
            # are present only inside the authenticated encrypted payload.
            safe_fields = ("id", "name", "mode", "home_id", "scene_id", "scene_name", "device_id", "device_name", "hotkey")
            envelope = {"doors": [{k:d[k] for k in safe_fields if k in d}
                       for d in config.get("doors", []) if d.get("mode") == "cloud_scene"],
                        FIELD: encrypt_config(config, key)}
            notes = json.dumps(envelope, ensure_ascii=False)
            if previous is None:
                raise ValueError("Registro compartilhado de portas ausente.")
            filters = urllib.parse.urlencode({"id":"eq.eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", "notes":"eq."+previous})
            url = f"{cls._clean_base_url(cfg['url'])}/rest/v1/servers?{filters}"
            headers = {**cls._get_headers(cfg["key"]), "Prefer":"return=representation"}
            req = urllib.request.Request(url, data=json.dumps({"notes":notes}).encode(), headers=headers, method="PATCH")
            with urllib.request.urlopen(req, timeout=8.0) as response:
                updated = json.loads(response.read().decode("utf-8"))
            if len(updated) != 1:
                raise ValueError("As portas mudaram durante o envio. Atualize antes de salvar.")
            config["_shared_revision"] = revision(notes)
            return True
        except ValueError:
            raise
        except Exception as error:
            log.warning(f"[CloudSync] Falha na sincronização de portas: {type(error).__name__}")
            raise ValueError("Não foi possível enviar as portas. Verifique a conexão e tente novamente.") from None

    @staticmethod
    def _get_headers(key: str) -> Dict[str, str]:
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "RemoteXPTI-CloudSync/1.1"
        }

    @staticmethod
    def _clean_base_url(url: str) -> str:
        u = (url or "").strip().rstrip("/")
        if u.endswith("/rest/v1"):
            u = u[:-8].rstrip("/")
        return u

    @classmethod
    def test_connection(cls, url: str, key: str) -> Tuple[bool, str]:
        """Testa se as credenciais do Supabase estão ativas e alcançáveis."""
        if not url or not key:
            return False, "URL e Chave da API são obrigatórios."

        clean_url = cls._clean_base_url(url)
        headers = cls._get_headers(key)

        # Testa consulta na tabela servers
        endpoint = f"{clean_url}/rest/v1/servers?select=id&limit=1"
        try:
            req = urllib.request.Request(endpoint, headers=headers)
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                if resp.status == 200:
                    return True, "Conexão com Supabase e tabela 'servers' estabelecida com sucesso!"
                return False, f"Resposta inesperada do servidor: {resp.status}"
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            if e.code in (401, 403):
                return False, "Chave de API inválida ou sem permissão."
            elif e.code == 404 and "PGRST205" in err_body:
                return True, "Conectado ao Supabase com sucesso! (Aguardando criação da tabela 'servers' no SQL Editor)."
            return True, f"API do Supabase respondeu (HTTP {e.code})."
        except Exception as ex:
            return False, f"Falha ao conectar: {str(ex)}"

    @classmethod
    def fetch_servers(cls) -> Optional[List[Dict[str, Any]]]:
        """Busca a lista de servidores atualizada no Supabase."""
        cfg = ConfigManager().get_supabase_config()
        if not cfg.get("enabled") or not cfg.get("url") or not cfg.get("key"):
            return None

        clean_url = cls._clean_base_url(cfg["url"])
        url = f"{clean_url}/rest/v1/servers?select=*"
        headers = cls._get_headers(cfg["key"])

        try:
            log.info(f"[CloudSync] Consultando servidores remotos no Supabase: {url}")
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    # Filtra o servidor fake usado para armazenar a config do Tuya e doors_config
                    data = [s for s in data if s.get("id") not in ("ffffffff-ffff-ffff-ffff-ffffffffffff", "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")]
                    log.info(f"[CloudSync] {len(data)} servidores obtidos com sucesso do Supabase.")
                    return data
        except Exception as e:
            log.warning(f"[CloudSync] Falha ao sincronizar servidores com Supabase: {e}")
            return None
        return None

    @classmethod
    def push_servers(cls, servers: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """Envia / atualiza a lista de servidores corporativos para o Supabase (Upsert)."""
        cfg = ConfigManager().get_supabase_config()
        if not cfg.get("enabled") or not cfg.get("url") or not cfg.get("key"):
            log.info("[CloudSync] Supabase não configurado ou desabilitado. Operação mantida apenas localmente.")
            return False, "Supabase não configurado ou desabilitado."

        clean_url = cls._clean_base_url(cfg["url"])
        url = f"{clean_url}/rest/v1/servers"
        headers = cls._get_headers(cfg["key"])
        headers["Prefer"] = "resolution=merge-duplicates"

        # Prepara payload filtrando apenas corporativos e incluindo credenciais protegidas
        payload = []
        for s in servers:
            if s.get("scope", "corporate") != "corporate":
                continue
            entry = {
                "id": str(s.get("id")),
                "name": s.get("name", "Servidor"),
                "host": s.get("host", ""),
                "port": int(s.get("port", 3389)),
                "username": s.get("username", ""),
                "password": s.get("password", ""),  # Criptografado com MASTER_KEY
                "group": s.get("group", "BEMTEVI"),
                "scope": "corporate",
                "latitude": s.get("latitude"),
                "longitude": s.get("longitude"),
                "favorite": bool(s.get("favorite", False)),
                "admin_mode": bool(s.get("admin_mode", False)),
                "multimon": bool(s.get("multimon", False)),
                "fullscreen": bool(s.get("fullscreen", True)),
                "notes": s.get("notes", "")
            }
            payload.append(entry)

        if not payload:
            return True, "Nenhum servidor corporativo para sincronizar."

        try:
            json_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=json_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status in (200, 201):
                    log.info(f"[CloudSync] {len(payload)} servidores corporativos enviados com sucesso para o Supabase.")
                    return True, f"{len(payload)} servidores sincronizados na nuvem!"
                return False, f"Servidor retornou status {resp.status}."
        except Exception as e:
            log.error(f"[CloudSync] Erro ao enviar servidores para o Supabase: {e}")
            return False, str(e)

    @classmethod
    def push_single_server(cls, server: Dict[str, Any]) -> Tuple[bool, str]:
        """Publica ou atualiza um único servidor corporativo no Supabase automaticamente."""
        if server.get("scope", "corporate") != "corporate":
            return True, "Servidor local: não enviado para a nuvem."
        return cls.push_servers([server])

    @classmethod
    def fetch_tuya_session(cls) -> Optional[str]:
        """Busca a sessão Tuya atualizada no Supabase (embutida na tabela servers)."""
        cfg = ConfigManager().get_supabase_config()
        if not cfg.get("session_sync_enabled", cfg.get("enabled")) or not cfg.get("url") or not cfg.get("key"):
            return None

        clean_url = cls._clean_base_url(cfg["url"])
        # Lê da tabela servers usando o UUID reservado
        url = f"{clean_url}/rest/v1/servers?id=eq.ffffffff-ffff-ffff-ffff-ffffffffffff&select=notes"
        headers = cls._get_headers(cfg["key"])

        try:
            log.info("[CloudSync] Consultando tuya_config no Supabase (via servers)...")
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data and isinstance(data, list) and len(data) > 0:
                        log.info("[CloudSync] tuya_config obtido com sucesso.")
                        return data[0].get("notes")
        except Exception as e:
            log.warning(f"[CloudSync] Falha ao buscar tuya_config do Supabase: {e}")
        return None

    @classmethod
    def push_tuya_session(cls, session_json_str: str) -> bool:
        """Envia a sessão Tuya atualizada para o Supabase (usando a tabela servers)."""
        cfg = ConfigManager().get_supabase_config()
        if not cfg.get("session_sync_enabled", cfg.get("enabled")) or not cfg.get("url") or not cfg.get("key"):
            return False

        from tuya_devices import valid_session, session_timestamp
        try:
            incoming = json.loads(session_json_str)
            if not valid_session(incoming):
                return False
            previous = cls.fetch_tuya_session()
            if previous:
                current = json.loads(previous)
                if session_timestamp(current) > session_timestamp(incoming):
                    log.info("[CloudSync] Sessão local antiga: mantida a sessão Tuya mais nova na nuvem.")
                    return False
                if current == incoming:
                    return True
                # Conditional update: another client's renewal cannot be overwritten
                # between this read and write. Only the session record is touched.
                filters = urllib.parse.urlencode({
                    "id": "eq.ffffffff-ffff-ffff-ffff-ffffffffffff", "notes": "eq." + previous,
                })
                url = f"{cls._clean_base_url(cfg['url'])}/rest/v1/servers?{filters}"
                headers = cls._get_headers(cfg["key"])
                headers["Prefer"] = "return=representation"
                req = urllib.request.Request(url, data=json.dumps({"notes": session_json_str}).encode("utf-8"),
                                             headers=headers, method="PATCH")
                with urllib.request.urlopen(req, timeout=8.0) as response:
                    updated = json.loads(response.read().decode("utf-8"))
                    return response.status == 200 and isinstance(updated, list) and len(updated) == 1
        except Exception as error:
            log.warning(f"[CloudSync] Falha ao atualizar sessão Tuya compartilhada: {type(error).__name__}")
            return False

        clean_url = cls._clean_base_url(cfg["url"])
        url = f"{clean_url}/rest/v1/servers?on_conflict=id"
        headers = cls._get_headers(cfg["key"])
        headers["Prefer"] = "resolution=ignore-duplicates,return=representation"

        # Usa a tabela de servidores existente para não precisar criar tabela nova
        payload = {
            "id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "name": "TUYA_CONFIG",
            "host": "0.0.0.0",
            "port": 0,
            "username": "",
            "password": "",
            "group": "",
            "scope": "corporate",
            "latitude": 0.0,
            "longitude": 0.0,
            "favorite": False,
            "admin_mode": False,
            "multimon": False,
            "fullscreen": False,
            "notes": session_json_str
        }

        try:
            json_data = json.dumps([payload], ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=json_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                inserted = json.loads(resp.read().decode("utf-8"))
                if resp.status in (200, 201) and isinstance(inserted, list) and len(inserted) == 1:
                    log.info("[CloudSync] tuya_config atualizado com sucesso no Supabase.")
                    return True
        except Exception as e:
            log.warning(f"[CloudSync] Falha ao atualizar tuya_config no Supabase: {e}")
        return False

    @classmethod
    def fetch_doors_config(cls) -> Optional[str]:
        """Busca a configuração de portas atualizada no Supabase (embutida na tabela servers)."""
        cfg = ConfigManager().get_supabase_config()
        if cfg.get("doors_sync_enabled"):
            if not cls.can_share_doors():
                return None
            from shared_doors import FIELD, decrypt_config, revision
            try:
                notes = cls._read_doors_notes(cfg)
                if not notes:
                    return None
                envelope = json.loads(notes)
                if FIELD not in envelope:
                    return None  # First encrypted publish keeps the author's local cameras.
                data = decrypt_config(envelope, ConfigManager().get_doors_sync_key())
                data["_shared_revision"] = revision(notes)
                return json.dumps(data)
            except Exception as error:
                log.warning(f"[CloudSync] Falha ao ler portas compartilhadas: {type(error).__name__}")
                return None
        if not cfg.get("enabled") or not cfg.get("url") or not cfg.get("key"):
            return None

        clean_url = cls._clean_base_url(cfg["url"])
        url = f"{clean_url}/rest/v1/servers?id=eq.eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee&select=notes"
        headers = cls._get_headers(cfg["key"])

        try:
            log.info("[CloudSync] Consultando doors_config no Supabase (via servers)...")
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data and isinstance(data, list) and len(data) > 0:
                        log.info("[CloudSync] doors_config obtido com sucesso.")
                        return data[0].get("notes")
        except Exception as e:
            log.warning(f"[CloudSync] Falha ao buscar doors_config do Supabase: {e}")
        return None

    @classmethod
    def push_doors_config(cls, config_dict: dict) -> bool:
        """Envia a configuração de portas para o Supabase (usando a tabela servers)."""
        cfg = ConfigManager().get_supabase_config()
        if cfg.get("doors_sync_enabled"):
            return cls._push_shared_doors(config_dict, cfg)
        if not cfg.get("enabled") or not cfg.get("url") or not cfg.get("key"):
            return False

        clean_url = cls._clean_base_url(cfg["url"])
        url = f"{clean_url}/rest/v1/servers?on_conflict=id"
        headers = cls._get_headers(cfg["key"])
        headers["Prefer"] = "resolution=merge-duplicates"

        # Portas de rede local (ex: Facial Hikvision ISAPI de rede local)
        # são restritas a esta empresa/máquina e NÃO devem ser enviadas para o Supabase
        clean_config = dict(config_dict)
        for local_preference in ("enabled", "hotkeys_enabled", "feedback_sound", "feedback_notification"):
            clean_config.pop(local_preference, None)
        if "doors" in clean_config and isinstance(clean_config["doors"], list):
            clean_config["doors"] = [
                d for d in clean_config["doors"]
                if d.get("mode") not in ("hikvision", "facial", "isapi") and not d.get("is_local")
            ]

        payload = {
            "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
            "name": "DOORS_CONFIG",
            "host": "0.0.0.0",
            "port": 0,
            "username": "",
            "password": "",
            "group": "",
            "scope": "corporate",
            "latitude": 0.0,
            "longitude": 0.0,
            "favorite": False,
            "admin_mode": False,
            "multimon": False,
            "fullscreen": False,
            "notes": json.dumps(clean_config, ensure_ascii=False)
        }

        try:
            json_data = json.dumps([payload], ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=json_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                if resp.status in (200, 201):
                    log.info("[CloudSync] doors_config atualizado com sucesso no Supabase.")
                    return True
        except Exception as e:
            log.warning(f"[CloudSync] Falha ao atualizar doors_config no Supabase: {e}")
        return False

    @classmethod
    def delete_remote_server(cls, server_id: str) -> Tuple[bool, str]:
        """Remove um servidor corporativo do banco Supabase ao ser excluído pelo admin."""
        cfg = ConfigManager().get_supabase_config()
        if not cfg.get("enabled") or not cfg.get("url") or not cfg.get("key"):
            return False, "Supabase não configurado."

        clean_url = cls._clean_base_url(cfg["url"])
        url = f"{clean_url}/rest/v1/servers?id=eq.{server_id}"
        headers = cls._get_headers(cfg["key"])

        try:
            req = urllib.request.Request(url, headers=headers, method="DELETE")
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                if resp.status in (200, 204):
                    log.info(f"[CloudSync] Servidor {server_id} excluído com sucesso do Supabase.")
                    return True, "Servidor excluído da nuvem com sucesso."
                return False, f"Falha ao excluir na nuvem: HTTP {resp.status}"
        except Exception as e:
            log.error(f"[CloudSync] Erro ao excluir servidor {server_id} do Supabase: {e}")
            return False, str(e)
