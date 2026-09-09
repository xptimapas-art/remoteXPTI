"""
Script em Python puro para compilar o executável e o instalador Setup.exe sem usar .bat
Execute com: python build_all.py
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd_list):
    print(f">> Executando: {' '.join(cmd_list)}")
    res = subprocess.run(cmd_list)
    if res.returncode != 0:
        print(f"[ERRO] Falha no comando: {' '.join(cmd_list)}")
        sys.exit(res.returncode)

def main():
    print("==================================================================")
    print("      Compilando RemoteXPTI e Gerando Setup.exe (Sem .bat)")
    print("==================================================================")
    print()

    # 1. Compilar o aplicativo principal RemoteXPTI.exe
    print("[1/2] Compilando RemoteXPTI.exe...")
    run_command([
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--clean",
        "--collect-all", "customtkinter",
        "--name", "RemoteXPTI",
        "main.py"
    ])

    # 2. Compilar o Instalador Gráfico Setup_RemoteXPTI.exe embutindo o aplicativo e os servidores
    print()
    print("[2/2] Compilando Setup_RemoteXPTI.exe (Instalador Único)...")
    run_command([
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--clean",
        "--collect-all", "customtkinter",
        "--add-data", "dist/RemoteXPTI.exe;.",
        "--add-data", "servers.json;.",
        "--add-data", ".secret.key;.",
        "--name", "Setup_RemoteXPTI",
        "installer_gui.py"
    ])

    print()
    print("==================================================================")
    print("[SUCESSO TOTAL] Instalador gerado:")
    print("   dist/Setup_RemoteXPTI.exe")
    print()
    print("Voce so precisa enviar esse arquivo .exe para o seu cliente!")
    print("==================================================================")

if __name__ == "__main__":
    main()
