"""
Cofre da sessão Tuya para desenvolvedores.

A sessão da nuvem Tuya (session.json + doors_config.json) é embutida no executável
CRIPTOGRAFADA com uma chave derivada da senha DEV (PBKDF2). A senha nunca fica no
binário: só quem digita a senha DEV correta no app consegue abrir o cofre.

- Build:   python tuya_vault.py <senha_dev>   -> gera tuya_vault.bin
- Runtime: unlock_to_config_dir(senha)        -> grava os arquivos em %LOCALAPPDATA%\\RemoteXPTI
"""
import base64
import hashlib
import json
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

VAULT_FILENAME = "tuya_vault.bin"
_SALT = b"RemoteXPTI::tuya-vault::v1"
_ITERATIONS = 390_000
_FILES = ("session.json", "doors_config.json")


def _key_from_password(password: str) -> bytes:
    raw = hashlib.pbkdf2_hmac("sha256", password.strip().encode("utf-8"), _SALT, _ITERATIONS)
    return base64.urlsafe_b64encode(raw)


def build_vault(password: str, source_dir: Path, out_path: Path) -> bool:
    payload = {}
    for name in _FILES:
        p = source_dir / name
        if p.exists():
            payload[name] = p.read_text(encoding="utf-8")
    if "session.json" not in payload:
        return False
    token = Fernet(_key_from_password(password)).encrypt(json.dumps(payload).encode("utf-8"))
    out_path.write_bytes(token)
    return True


def _vault_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / VAULT_FILENAME


def unlock_to_config_dir(password: str, overwrite_session: bool = True) -> bool:
    """Abre o cofre com a senha DEV e grava a sessão Tuya na pasta de configuração."""
    from config_manager import get_config_dir
    from logger import log

    vault = _vault_path()
    if not vault.exists():
        log.info("[TuyaVault] Nenhum cofre de sessão Tuya embutido nesta build.")
        return False
    try:
        data = json.loads(Fernet(_key_from_password(password)).decrypt(vault.read_bytes()))
    except InvalidToken:
        log.warning("[TuyaVault] Senha não abre o cofre da sessão Tuya.")
        return False
    except Exception as e:
        log.error(f"[TuyaVault] Erro ao abrir cofre: {e}")
        return False

    cfg_dir = get_config_dir()
    for name, content in data.items():
        if name not in _FILES:
            continue
        dest = cfg_dir / name
        # doors_config.json só é criado se não existir, para não sobrescrever atalhos do usuário
        if dest.exists() and (name != "session.json" or not overwrite_session):
            continue
        dest.write_text(content, encoding="utf-8")
    log.info("[TuyaVault] Sessão da nuvem Tuya provisionada para o desenvolvedor.")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python tuya_vault.py <senha_dev>")
        sys.exit(1)
    pwd = sys.argv[1]
    from config_manager import ConfigManager, DEV_PASSWORD_HASH
    import secrets
    if not secrets.compare_digest(ConfigManager()._hash_password(pwd.strip()), DEV_PASSWORD_HASH):
        print("Senha DEV incorreta. Cofre NÃO gerado.")
        sys.exit(2)
    here = Path(__file__).parent
    ok = build_vault(pwd, here, here / VAULT_FILENAME)
    print("Cofre gerado: tuya_vault.bin" if ok else "session.json não encontrado. Cofre NÃO gerado.")
    sys.exit(0 if ok else 3)
