"""
Módulo de Sincronização em Nuvem (Supabase) do RemoteXPTI.
Permite sincronizar servidores e configurações entre a central e os clientes.
Funciona via HTTPS REST padrão com urllib.request (zero dependências pesadas).
"""

import json
import urllib.request
import urllib.error
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
