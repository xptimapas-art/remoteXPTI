import subprocess
import socket
import sys
import tempfile
from pathlib import Path
from typing import Tuple, Optional
from logger import log

class RDPManager:
    """Gerencia conexões RDP, injeção de credenciais via cmdkey e testes de conectividade."""

    @staticmethod
    def is_windows() -> bool:
        return sys.platform == "win32"

    @staticmethod
    def check_connection(host: str, port: int = 3389, timeout: float = 1.2) -> Tuple[bool, str]:
        """
        Testa rapidamente se a porta RDP do servidor está respondendo.
        Retorna (is_online, mensagem).
        """
        if not host:
            return False, "Host vazio"

        # Se o host vier no formato host:porta, separar
        clean_host = host
        target_port = port
        if ":" in host:
            parts = host.split(":", 1)
            clean_host = parts[0]
            try:
                target_port = int(parts[1])
            except ValueError:
                target_port = port

        try:
            # Resolve DNS ou conecta direto via IPv4/IPv6
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((clean_host, target_port))
            sock.close()
            if result == 0:
                return True, f"Online ({clean_host}:{target_port})"
            else:
                return False, f"Porta {target_port} fechada ou filtrada"
        except socket.gaierror:
            return False, "Falha ao resolver DNS"
        except socket.timeout:
            return False, "Tempo de resposta esgotado (Timeout)"
        except Exception as e:
            return False, f"Erro de rede: {str(e)}"

    @staticmethod
    def set_windows_credential(host: str, port: int, username: str, password: str) -> Tuple[bool, str]:
        """
        Injeta a credencial no Windows Credential Manager usando cmdkey.
        Registra tanto como Senha do Domínio (/add:) para NLA/CredSSP
        quanto como Genérico (/generic:) para compatibilidade total.
        """
        if not RDPManager.is_windows():
            return False, "Sistema operacional não é Windows"

        clean_host = host
        if ":" in host:
            clean_host = host.split(":", 1)[0]

        targets = [f"TERMSRV/{clean_host}"]
        if port and port != 3389:
            targets.append(f"TERMSRV/{clean_host}:{port}")

        creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

        success = True
        err_msgs = []

        safe_user = username.replace('"', '')
        safe_pass = password.replace('"', '')

        for target in targets:
            try:
                # 1. Limpa credencial antiga para evitar conflitos de cache
                subprocess.run(
                    f'cmdkey /delete:{target}',
                    shell=True,
                    capture_output=True,
                    creationflags=creation_flags
                )

                # 2. Registra como Senha do Domínio (/add:) - Requisito fundamental do NLA/CredSSP do mstsc
                cmd_add = f'cmdkey /add:{target} /user:"{safe_user}" /pass:"{safe_pass}"'
                res_add = subprocess.run(
                    cmd_add,
                    shell=True,
                    capture_output=True,
                    text=True,
                    creationflags=creation_flags
                )

                # 3. Registra também como Genérica (/generic:) para fallbacks de RDP legado
                cmd_gen = f'cmdkey /generic:{target} /user:"{safe_user}" /pass:"{safe_pass}"'
                res_gen = subprocess.run(
                    cmd_gen,
                    shell=True,
                    capture_output=True,
                    text=True,
                    creationflags=creation_flags
                )

                if res_add.returncode != 0 and res_gen.returncode != 0:
                    success = False
                    err_msgs.append(res_add.stderr.strip() or res_add.stdout.strip())
            except Exception as e:
                success = False
                err_msgs.append(str(e))

        if success:
            return True, "Credencial registrada com sucesso"
        return False, "; ".join(err_msgs)

    @staticmethod
    def clear_windows_credential(host: str, port: int = 3389) -> bool:
        """Remove as credenciais registradas para o host."""
        if not RDPManager.is_windows():
            return False

        clean_host = host.split(":", 1)[0] if ":" in host else host
        targets = [f"TERMSRV/{clean_host}"]
        if port and port != 3389:
            targets.append(f"TERMSRV/{clean_host}:{port}")

        creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

        for target in targets:
            try:
                subprocess.run(["cmdkey", f"/delete:{target}"], capture_output=True, creationflags=creation_flags)
                subprocess.run(["cmdkey", f"/delete:{target}"], capture_output=True, creationflags=creation_flags)
            except Exception:
                pass
        return True

    @staticmethod
    def launch_rdp(
        host: str,
        port: int = 3389,
        username: str = "",
        password: str = "",
        fullscreen: bool = True,
        admin_mode: bool = False,
        multimon: bool = False
    ) -> Tuple[bool, str]:
        """
        Configura a credencial e abre o mstsc.exe diretamente.
        """
        if not RDPManager.is_windows():
            return False, "O cliente nativo mstsc só está disponível no Windows."

        if not host:
            return False, "Endereço de host inválido."

        # Monta o destino para o mstsc (se a porta não for padrão, inclui :porta)
        clean_host = host.split(":", 1)[0] if ":" in host else host
        target_v = clean_host
        if port and port != 3389:
            target_v = f"{clean_host}:{port}"

        log.info(f"[RDPManager] Disparando conexão RDP para {target_v} (Usuário: '{username}', Tela cheia: {fullscreen}, Admin: {admin_mode})")

        # Se houver usuário e senha, salva no Credential Manager
        if username and password:
            ok, msg = RDPManager.set_windows_credential(clean_host, port, username, password)
            if not ok:
                log.warning(f"[RDPManager] Falha ao registrar credencial no cmdkey: {msg}")
            else:
                log.info(f"[RDPManager] Credencial registrada no Windows para {clean_host}:{port} ({username})")

        # Monta parâmetros do mstsc usando perfil temporário .rdp
        # Isso garante que o mstsc saiba EXATAMENTE qual é o usuário solicitado
        # e desative o prompt de login manual ('prompt for credentials:i:0')
        rdp_lines = [
            f"full address:s:{target_v}",
            f"prompt for credentials:i:0",
            f"administrative session:i:{1 if admin_mode else 0}",
            f"screen mode id:i:{2 if fullscreen else 1}",
            f"use multimon:i:{1 if multimon else 0}",
            f"audiomode:i:0",
            f"redirectclipboard:i:1",
            f"redirectprinters:i:1",
            f"autoreconnection enabled:i:1",
            f"authentication level:i:0",
            f"promptcredentialonce:i:1",
            f"negotiate security layer:i:1",
            f"enablecredsspsupport:i:1"
        ]

        if username:
            if "\\" in username:
                dom, usr = username.split("\\", 1)
                rdp_lines.append(f"domain:s:{dom.strip()}")
                rdp_lines.append(f"username:s:{usr.strip()}")
            else:
                rdp_lines.append(f"username:s:{username.strip()}")

        temp_dir = Path(tempfile.gettempdir())
        clean_name = clean_host.replace(".", "_").replace(":", "_")
        rdp_file = temp_dir / f"remotexpti_{clean_name}.rdp"
        try:
            rdp_file.write_text("\r\n".join(rdp_lines) + "\r\n", encoding="utf-16")
            cmd = ["mstsc", str(rdp_file)]
        except Exception:
            cmd = ["mstsc", f"/v:{target_v}"]

        if fullscreen:
            cmd.append("/f")
        if admin_mode:
            cmd.append("/admin")
        if multimon:
            cmd.append("/multimon")

        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.Popen(cmd, creationflags=creation_flags)
            log.info(f"[RDPManager] Cliente mstsc iniciado com sucesso para {target_v}")
            return True, f"Conexão iniciada com {target_v}"
        except Exception as e:
            log.error(f"[RDPManager] Erro ao iniciar mstsc para {target_v}: {e}", exc_info=True)
            return False, f"Falha ao executar mstsc: {str(e)}"
