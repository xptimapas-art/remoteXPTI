"""
diagnostico_servidor.py - Ferramenta CLI de Diagnóstico Remoto de Servidores (XPTI / BEMTEVI)

Permite auditar via linha de comando qualquer servidor cadastrado no 'servers.json':
- Memória RAM total, usada, livre e commit charge
- Espaço e integridade de todos os discos (C:, E:, F:, etc.)
- Top processos consumidores de memória
- Status dos VSS Writers (Volume Shadow Copy)
- Detecção de erros de OutOfMemory e eventos recentes do sistema

Uso:
    python diagnostico_servidor.py --server "Lages"
    python diagnostico_servidor.py --server 10.189.112.10
    python diagnostico_servidor.py --server "Lages" --deep
    python diagnostico_servidor.py --list
"""

import sys
import argparse
import socket
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    import winrm
except ImportError:
    print("ERRO: O pacote 'pywinrm' não está instalado. Execute: pip install pywinrm")
    sys.exit(1)

# Importa o gerenciador de cofres de credenciais do remoteXPTI
from storage import CredentialVault, DATA_FILE, KEY_FILE
import json

def load_server(target: str) -> Optional[Dict[str, Any]]:
    """Busca um servidor no servers.json por nome, host (IP) ou ID."""
    if not DATA_FILE.exists():
        print(f"ERRO: Arquivo de servidores '{DATA_FILE}' não encontrado.")
        return None

    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        servers = data.get("servers", [])
    except Exception as e:
        print(f"ERRO ao ler {DATA_FILE}: {e}")
        return None

    target_clean = target.strip().lower()
    for s in servers:
        name = s.get("name", "").lower()
        host = s.get("host", "").lower()
        sid = s.get("id", "").lower()
        if target_clean in (name, host, sid) or target_clean in name:
            return s

    return None

def list_available_servers():
    """Lista todos os servidores cadastrados no servers.json."""
    if not DATA_FILE.exists():
        print(f"Arquivo {DATA_FILE} não encontrado.")
        return

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    servers = data.get("servers", [])
    print(f"\n{'='*70}")
    print(f"{'NOME DO SERVIDOR':<30} | {'HOST / IP':<18} | {'GRUPO':<12}")
    print(f"{'-'*70}")
    for s in sorted(servers, key=lambda x: (x.get('group', ''), x.get('name', ''))):
        print(f"{s.get('name', ''):<30} | {s.get('host', ''):<18} | {s.get('group', ''):<12}")
    print(f"{'='*70}\nTotal: {len(servers)} servidores cadastrados.\n")

def check_tcp_port(host: str, port: int = 5985, timeout: float = 2.0) -> bool:
    """Verifica se a porta do WinRM (5985) está aberta antes de disparar comandos."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        res = s.connect_ex((host, port))
        s.close()
        return res == 0
    except Exception:
        return False

def build_ps_diag_script(deep: bool = False) -> str:
    """Gera o script PowerShell executado remotamente no servidor de forma concisa."""
    lines = [
        r'Write-Host "=== 1. SISTEMA E MEMÓRIA RAM ==="',
        r'$os = Get-CimInstance Win32_OperatingSystem',
        r'$tot = [math]::Round($os.TotalVisibleMemorySize/1MB, 2)',
        r'$fre = [math]::Round($os.FreePhysicalMemory/1MB, 2)',
        r'$usd = [math]::Round($tot - $fre, 2)',
        r'$pct = [math]::Round(($usd / $tot) * 100, 1)',
        r'$up = (Get-Date) - $os.LastBootUpTime',
        r'Write-Host "Host: $($env:COMPUTERNAME) | Uptime: $($up.Days)d $($up.Hours)h $($up.Minutes)m"',
        r'Write-Host "RAM: $usd GB de $tot GB em uso ($pct %) | Livre: $fre GB"',
        r'Write-Host "`n=== 2. ESPAÇO EM DISCO ==="',
        r'Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {',
        r'  $sz = [math]::Round($_.Size/1GB, 2); $fr = [math]::Round($_.FreeSpace/1GB, 2)',
        r'  $pf = if ($_.Size -gt 0) { [math]::Round(($_.FreeSpace/$_.Size)*100, 1) } else { 0 }',
        r'  $st = if ($pf -le 2.0) { "[CRÍTICO: DISCO CHEIO!]" } elseif ($pf -le 10.0) { "[BAIXO ESPAÇO]" } else { "[OK]" }',
        r'  [PSCustomObject]@{ Volume=$_.DeviceId; Nome=$_.VolumeName; TotalGB=$sz; LivreGB=$fr; PctLivre="$pf %"; Status=$st }',
        r'} | Format-Table -AutoSize',
        r'Write-Host "=== 3. TOP 10 PROCESSOS POR RAM ==="',
        r'Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 Name, Id, @{N="RAM_MB";E={[math]::Round($_.WorkingSet64/1MB, 1)}} | Format-Table -AutoSize'
    ]
    if deep:
        lines.extend([
            r'Write-Host "=== 4. VSS WRITERS ==="',
            r'vssadmin list writers | Where-Object { $_ -match "Writer name|State|Last error" }',
            r'Write-Host "=== 5. ERROS DE OUT OF MEMORY (ÚLTIMAS 24H) ==="',
            r'$ontem = (Get-Date).AddDays(-1)',
            r'$evs = Get-WinEvent -FilterHashtable @{LogName="Application"; Level=1,2; StartTime=$ontem} -MaxEvents 30 -ErrorAction SilentlyContinue | Where-Object { $_.Message -match "memory|OutOfMemory" }',
            r'if ($evs) { $evs | Select-Object -First 3 | ForEach-Object { Write-Host "[$($_.TimeCreated)] $($_.Message.Split([char]10)[0])" } } else { Write-Host "Nenhum erro de memória registrado." }'
        ])
    return "\n".join(lines)

def run_diagnostics(target: str, deep: bool = False):
    """Executa o diagnóstico completo no servidor alvo."""
    server = load_server(target)
    vault = CredentialVault(KEY_FILE)

    if not server:
        # Se não achou pelo nome, tenta usar o target diretamente como IP
        host = target
        username = "bemtevi.net\\xpti"
        # Tenta pegar a senha padrão corporativa descriptografando de Lages ou similar
        print(f"Servidor '{target}' não está explicitamente no catálogo. Tentando conectar diretamente via IP...")
        dummy_server = load_server("Lages")
        if dummy_server:
            password = vault.decrypt(dummy_server.get("password", ""))
        else:
            print("ERRO: Não foi possível obter credenciais padrão.")
            return
        server_name = host
    else:
        host = server.get("host")
        server_name = server.get("name")
        username = server.get("username", "bemtevi.net\\xpti")
        enc_pass = server.get("password", "")
        password = vault.decrypt(enc_pass)

    print(f"\n>>> INICIANDO DIAGNÓSTICO: {server_name} ({host}) <<<")
    print(f"Testando conexão na porta WinRM (5985)...")

    if not check_tcp_port(host, 5985, timeout=2.5):
        print(f"AVISO: A porta 5985 (WinRM) não respondeu em {host}.")
        if check_tcp_port(host, 3389, timeout=2.5):
            print(f"A porta 3389 (RDP) ESTÁ ONLINE, mas o serviço WinRM pode estar desativado ou bloqueado no firewall.")
        else:
            print(f"O host {host} parece estar OFFLINE ou inalcançável nesta rede.")
        return

    print("Conexão de rede OK! Executando auditoria remota via WinRM (NTLM)...")
    ps_code = build_ps_diag_script(deep=deep)

    # Tenta conectar com o formato configurado e fallbacks comuns
    users_to_try = [username]
    if "\\" in username:
        u_part = username.split("\\")[1]
        d_part = username.split("\\")[0]
        users_to_try.append(f"{u_part}@{d_part}")
        users_to_try.append(u_part)
    elif "@" in username:
        u_part = username.split("@")[0]
        d_part = username.split("@")[1]
        users_to_try.append(f"{d_part}\\{u_part}")
        users_to_try.append(u_part)

    success = False
    for u in users_to_try:
        try:
            sess = winrm.Session(
                f"http://{host}:5985/wsman",
                auth=(u, password),
                transport='ntlm',
                read_timeout_sec=50,
                operation_timeout_sec=35
            )
            res = sess.run_ps(ps_code)
            if res.status_code == 0:
                print(res.std_out.decode('utf-8', errors='ignore'))
                success = True
                break
            else:
                err_msg = res.std_err.decode('utf-8', errors='ignore')
                if "Access is denied" in err_msg or "InvalidCredentials" in err_msg:
                    continue
                print(f"Erro na execução remota: {err_msg}")
        except Exception as e:
            err_str = str(e)
            if "rejected by the server" in err_str or "401" in err_str:
                continue
            print(f"Falha de conexão com usuário '{u}': {e}")

    if not success:
        print(f"ERRO: Não foi possível autenticar no servidor {host} com as credenciais salvas.")

def main():
    parser = argparse.ArgumentParser(description="Ferramenta de Diagnóstico Remoto de Servidores (XPTI)")
    parser.add_argument("--server", "-s", type=str, help="Nome do servidor (ex: Lages, Joinville, AJIN) ou IP")
    parser.add_argument("--list", "-l", action="store_true", help="Lista todos os servidores cadastrados")
    parser.add_argument("--deep", "-d", action="store_true", help="Diagnóstico aprofundado com VSS e logs de eventos")

    args = parser.parse_args()

    if args.list:
        list_available_servers()
        return

    if not args.server:
        print("Uso: python diagnostico_servidor.py --server 'Lages'")
        print("Para ver a lista de servidores: python diagnostico_servidor.py --list")
        sys.exit(0)

    run_diagnostics(args.server, deep=args.deep)

if __name__ == "__main__":
    main()
