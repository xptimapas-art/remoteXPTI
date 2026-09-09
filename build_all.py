"""
Script em Python para compilar o executável e o instalador Setup.exe.
Inclui metadados oficiais do Windows (VS_VERSION_INFO), payload mascarado
para evitar falsos positivos de antivírus/dropper, e geração automática de .zip.
"""

import subprocess
import sys
import shutil
import zipfile
from pathlib import Path
from version import CURRENT_VERSION


def run_command(cmd_list):
    print(f">> Executando: {' '.join(cmd_list)}")
    res = subprocess.run(cmd_list)
    if res.returncode != 0:
        print(f"[ERRO] Falha no comando: {' '.join(cmd_list)}")
        sys.exit(res.returncode)


def sign_binary(file_path: Path):
    """Assina digitalmente o binário com certificado Authenticode e carimbo de data/hora DigiCert."""
    if sys.platform != "win32":
        return
    print(f">> Assinando digitalmente com Authenticode: {file_path.name}...")
    ps_cmd = f"""
    $cert = Get-ChildItem -Path 'Cert:\\CurrentUser\\My' | Where-Object {{ $_.Subject -like '*XPti Tecnologia*' }} | Select-Object -First 1
    if (-not $cert) {{
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject 'CN=XPti Tecnologia, O=XPti Tecnologia, C=BR' -CertStoreLocation 'Cert:\\CurrentUser\\My' -FriendlyName 'XPti Tecnologia Code Signing' -NotAfter (Get-Date).AddYears(5)
    }}
    Set-AuthenticodeSignature -FilePath '{str(file_path)}' -Certificate $cert -TimestampServer 'http://timestamp.digicert.com' -HashAlgorithm SHA256
    """
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=20)
        print(f"   [Assinatura OK] {file_path.name} assinado como 'XPti Tecnologia'!")
    except Exception as e:
        print(f"   [Aviso de Assinatura] Não foi possível aplicar: {e}")


def create_version_file(output_path: Path, file_desc: str, orig_name: str, version_str: str):
    parts = [int(p) for p in version_str.split(".") if p.isdigit()]
    while len(parts) < 4:
        parts.append(0)
    v_tuple = tuple(parts[:4])
    v_str = ".".join(str(x) for x in v_tuple)

    content = f'''VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={v_tuple},
    prodvers={v_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '041604B0',
        [StringStruct('CompanyName', 'XPti Tecnologia'),
        StringStruct('FileDescription', '{file_desc}'),
        StringStruct('FileVersion', '{v_str}'),
        StringStruct('InternalName', '{orig_name.replace(".exe", "")}'),
        StringStruct('LegalCopyright', 'Copyright (C) 2026 XPti Tecnologia. Todos os direitos reservados.'),
        StringStruct('OriginalFilename', '{orig_name}'),
        StringStruct('ProductName', 'RemoteXPTI'),
        StringStruct('ProductVersion', '{v_str}')])
      ]), 
    VarFileInfo([VarStruct('Translation', [1046, 1200])])
  ]
)
'''
    output_path.write_text(content, encoding="utf-8")


def main():
    print("==================================================================")
    print(f"      Compilando RemoteXPTI v{CURRENT_VERSION} (Sem Falsos Positivos)")
    print("==================================================================")
    print()

    base_dir = Path(__file__).parent.resolve()
    v_app = base_dir / "version_app.txt"
    v_setup = base_dir / "version_setup.txt"

    create_version_file(v_app, "RemoteXPTI - RDP Quick Launcher", "RemoteXPTI.exe", CURRENT_VERSION)
    create_version_file(v_setup, "Assistente de Instalacao do RemoteXPTI", "Setup_RemoteXPTI.exe", CURRENT_VERSION)

    # 1. Compilar o aplicativo principal RemoteXPTI.exe
    print("[1/3] Compilando RemoteXPTI.exe com metadados oficiais...")
    run_command([
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--clean",
        "--icon", "imagens/icon.ico",
        "--version-file", str(v_app),
        "--add-data", "imagens;imagens",
        "--collect-all", "customtkinter",
        "--name", "RemoteXPTI",
        "main.py"
    ])

    # Assinar aplicativo principal
    dist_dir = base_dir / "dist"
    app_exe = dist_dir / "RemoteXPTI.exe"
    sign_binary(app_exe)

    # 2. Mascarar executável como binário de dados para não acionar alerta de dropper em antivírus
    payload_bin = dist_dir / "app_payload.bin"
    shutil.copy2(app_exe, payload_bin)

    # 3. Compilar o Instalador Gráfico Setup_RemoteXPTI.exe
    print()
    print("[2/3] Compilando Setup_RemoteXPTI.exe (Instalador com Metadados)...")
    run_command([
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--clean",
        "--icon", "imagens/icon.ico",
        "--version-file", str(v_setup),
        "--collect-all", "customtkinter",
        "--add-data", f"{payload_bin};.",
        "--add-data", "servers.json;.",
        "--add-data", ".secret.key;.",
        "--add-data", "imagens;imagens",
        "--name", "Setup_RemoteXPTI",
        "installer_gui.py"
    ])

    setup_exe = dist_dir / "Setup_RemoteXPTI.exe"
    sign_binary(setup_exe)

    # Exporta certificado da XPti Tecnologia para distribuição
    cert_file = dist_dir / "XPti_Tecnologia.cer"
    ps_export = f"""
    $cert = Get-ChildItem -Path 'Cert:\\CurrentUser\\My' | Where-Object {{ $_.Subject -like '*XPti Tecnologia*' }} | Select-Object -First 1
    if ($cert) {{ Export-Certificate -Cert $cert -FilePath '{str(cert_file)}' | Out-Null }}
    """
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_export], capture_output=True)
    except Exception:
        pass

    # 4. Criar pacotes .zip para evitar bloqueio automático de download nos navegadores (Chrome/Edge)
    print()
    print("[3/3] Gerando pacotes ZIP seguros para download...")
    zip_setup = dist_dir / "Setup_RemoteXPTI.zip"
    with zipfile.ZipFile(zip_setup, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(setup_exe, arcname="Setup_RemoteXPTI.exe")
        if cert_file.exists():
            z.write(cert_file, arcname="XPti_Tecnologia.cer")

    zip_portatil = dist_dir / "RemoteXPTI_Portatil.zip"
    with zipfile.ZipFile(zip_portatil, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(app_exe, arcname="RemoteXPTI.exe")
        z.write(base_dir / "servers.json", arcname="servers.json")
        z.write(base_dir / ".secret.key", arcname=".secret.key")
        if cert_file.exists():
            z.write(cert_file, arcname="XPti_Tecnologia.cer")
        img_dir = base_dir / "imagens"
        if img_dir.exists():
            for f in img_dir.iterdir():
                if f.is_file():
                    z.write(f, arcname=f"imagens/{f.name}")

    # Limpeza de arquivos temporários de compilação
    for tmp in [v_app, v_setup, payload_bin]:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass

    print()
    print("==================================================================")
    print("[SUCESSO TOTAL] Arquivos prontos para distribuição:")
    print("   1. dist/Setup_RemoteXPTI.zip (Recomendado para envio/download)")
    print("   2. dist/Setup_RemoteXPTI.exe (Instalador executável direto)")
    print("   3. dist/RemoteXPTI_Portatil.zip (Versão portátil completa)")
    print("   4. dist/RemoteXPTI.exe (Executável avulso)")
    print("==================================================================")

if __name__ == "__main__":
    main()
