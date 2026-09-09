import os
import sys
import shutil
import time
import threading
import subprocess
from pathlib import Path
import customtkinter as ctk

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def get_bundle_resource(filename: str) -> Path:
    """Obtém o caminho dos arquivos embutidos no instalador."""
    if hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent.resolve()
        # Se estiver em dev e procurando o exe, checa na pasta dist
        if filename.endswith(".exe") and not (base_path / filename).exists():
            if (base_path / "dist" / filename).exists():
                return base_path / "dist" / filename
    return base_path / filename

def create_windows_shortcut(target: Path, shortcut_dest: Path, description: str = ""):
    """Cria atalho .lnk no Windows sem necessidade de dependências externas."""
    script = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut('{str(shortcut_dest)}')
    $Shortcut.TargetPath = '{str(target)}'
    $Shortcut.WorkingDirectory = '{str(target.parent)}'
    $Shortcut.Description = '{description}'
    $Shortcut.IconLocation = 'imageres.dll,24'
    $Shortcut.Save()
    """
    creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    subprocess.run(
        ["powershell", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        creationflags=creation_flags
    )


class SetupApp(ctk.CTk):
    """Assistente Gráfico de Instalação (Setup.exe) do RemoteXPTI."""

    def __init__(self):
        super().__init__()

        self.title("Instalação do RemoteXPTI")
        self.geometry("520x420")
        self.minsize(520, 420)
        self.resizable(False, False)

        # Pasta padrão: %LOCALAPPDATA%\Programs\RemoteXPTI (dispensa admin)
        local_appdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        self.default_install_dir = Path(local_appdata) / "Programs" / "RemoteXPTI"

        self._build_ui()

    def _build_ui(self):
        # 1. Cabeçalho Visual
        header = ctk.CTkFrame(self, height=76, corner_radius=0, fg_color=("#f0f2f5", "#16171d"))
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", padx=20, pady=12)

        ctk.CTkLabel(
            title_box,
            text="⚡ Assistente de Instalação",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=("gray10", "#ffffff")
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box,
            text="RemoteXPTI - Gerenciador RDP Ágil v1.0.0",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "#8e92a0")
        ).pack(anchor="w")

        # 2. Conteúdo Central
        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=24, pady=16)

        ctk.CTkLabel(
            self.content,
            text="O assistente irá configurar o RemoteXPTI no seu computador:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("gray15", "#e0e4ee")
        ).pack(anchor="w", pady=(0, 10))

        # Pasta de Destino
        ctk.CTkLabel(
            self.content,
            text="Pasta de Instalação:",
            font=ctk.CTkFont(size=11),
            text_color=("gray30", "#8e92a0")
        ).pack(anchor="w", pady=(0, 2))

        self.entry_dir = ctk.CTkEntry(self.content, height=34, font=ctk.CTkFont(size=11))
        self.entry_dir.insert(0, str(self.default_install_dir))
        self.entry_dir.configure(state="readonly")
        self.entry_dir.pack(fill="x", pady=(0, 14))

        # Opções de Instalação
        opts_box = ctk.CTkFrame(self.content, corner_radius=8, fg_color=("#e6e8ec", "#1f2027"))
        opts_box.pack(fill="x", pady=(0, 14), ipady=6)

        self.chk_desktop = ctk.CTkCheckBox(opts_box, text="Criar atalho na Área de Trabalho", font=ctk.CTkFont(size=12))
        self.chk_desktop.select()
        self.chk_desktop.pack(anchor="w", padx=16, pady=6)

        self.chk_startmenu = ctk.CTkCheckBox(opts_box, text="Criar atalho no Menu Iniciar", font=ctk.CTkFont(size=12))
        self.chk_startmenu.select()
        self.chk_startmenu.pack(anchor="w", padx=16, pady=6)

        self.chk_servers = ctk.CTkCheckBox(opts_box, text="Importar lista de servidores pré-configurados", font=ctk.CTkFont(size=12))
        self.chk_servers.select()
        self.chk_servers.pack(anchor="w", padx=16, pady=6)

        # Barra de Progresso (oculta inicialmente)
        self.lbl_progress = ctk.CTkLabel(
            self.content,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#00a8ff"
        )
        self.lbl_progress.pack(anchor="w", pady=(2, 2))

        self.progress_bar = ctk.CTkProgressBar(self.content, height=8)
        self.progress_bar.set(0)

        # 3. Rodapé com Botões
        footer = ctk.CTkFrame(self, height=56, corner_radius=0, fg_color=("#eaecef", "#121318"))
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self.btn_cancel = ctk.CTkButton(
            footer,
            text="Cancelar",
            width=90,
            height=34,
            fg_color=("gray75", "#2a2c36"),
            hover_color=("gray65", "#383a48"),
            text_color=("gray10", "#ffffff"),
            command=self.destroy
        )
        self.btn_cancel.pack(side="right", padx=16, pady=11)

        self.btn_install = ctk.CTkButton(
            footer,
            text="Instalar Agora",
            width=130,
            height=34,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(weight="bold"),
            command=self._start_installation
        )
        self.btn_install.pack(side="right")

    def _start_installation(self):
        self.btn_install.configure(state="disabled", text="Instalando...")
        self.btn_cancel.configure(state="disabled")
        self.progress_bar.pack(fill="x", pady=(2, 0))
        self.progress_bar.start()
        self.lbl_progress.configure(text="Preparando arquivos...")

        threading.Thread(target=self._run_install_steps, daemon=True).start()

    def _run_install_steps(self):
        target_dir = Path(self.entry_dir.get())
        
        try:
            # 0. Encerra qualquer instância aberta do RemoteXPTI para liberar o arquivo executável
            self.lbl_progress.configure(text="Fechando instâncias abertas do RemoteXPTI...")
            creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.run(["taskkill", "/F", "/IM", "RemoteXPTI.exe"], capture_output=True, creationflags=creation_flags)
            time.sleep(0.5)

            # 1. Cria diretório de instalação se não existir
            self.lbl_progress.configure(text="Preparando diretório de instalação...")
            target_dir.mkdir(parents=True, exist_ok=True)
            time.sleep(0.2)

            # 2. Copia RemoteXPTI.exe embutido (com retry caso o Windows demore a liberar o processo)
            self.lbl_progress.configure(text="Atualizando RemoteXPTI.exe...")
            source_exe = get_bundle_resource("RemoteXPTI.exe")
            dest_exe = target_dir / "RemoteXPTI.exe"
            
            if not source_exe.exists():
                raise FileNotFoundError(f"Arquivo executável não encontrado: {source_exe}")

            copied = False
            for attempt in range(4):
                try:
                    shutil.copy2(source_exe, dest_exe)
                    copied = True
                    break
                except PermissionError:
                    time.sleep(0.8)
                    subprocess.run(["taskkill", "/F", "/IM", "RemoteXPTI.exe"], capture_output=True, creationflags=creation_flags)

            if not copied:
                raise PermissionError("Não foi possível sobrescrever o RemoteXPTI.exe. Verifique se o aplicativo está fechado.")

            time.sleep(0.3)

            # 3. Copia lista de servidores e chave de segurança (se solicitado)
            if self.chk_servers.get():
                source_json = get_bundle_resource("servers.json")
                dest_json = target_dir / "servers.json"
                source_key = get_bundle_resource(".secret.key")
                dest_key = target_dir / ".secret.key"

                if source_json.exists():
                    self.lbl_progress.configure(text="Atualizando lista de servidores...")
                    # Se não existir, copia direto
                    if not dest_json.exists():
                        shutil.copy2(source_json, dest_json)
                    else:
                        # Se já existir, mescla novos servidores que não estavam cadastrados
                        try:
                            import json
                            with open(source_json, "r", encoding="utf-8") as f_src:
                                src_data = json.load(f_src)
                            with open(dest_json, "r", encoding="utf-8") as f_dst:
                                dst_data = json.load(f_dst)

                            existing_hosts = {s.get("host") for s in dst_data.get("servers", [])}
                            for s in src_data.get("servers", []):
                                if s.get("host") not in existing_hosts:
                                    dst_data.setdefault("servers", []).append(s)

                            with open(dest_json, "w", encoding="utf-8") as f_dst:
                                json.dump(dst_data, f_dst, indent=4, ensure_ascii=False)
                        except Exception:
                            pass

                if source_key.exists() and not dest_key.exists():
                    shutil.copy2(source_key, dest_key)

            # 4. Cria atalhos
            self.lbl_progress.configure(text="Criando atalhos no Windows...")
            
            # Atalho Desktop
            if self.chk_desktop.get():
                desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
                if desktop.exists():
                    create_windows_shortcut(dest_exe, desktop / "RemoteXPTI.lnk", "RemoteXPTI - RDP Quick Launcher")

            # Atalho Menu Iniciar
            if self.chk_startmenu.get():
                appdata = os.environ.get("APPDATA", "")
                start_menu = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                if start_menu.exists():
                    create_windows_shortcut(dest_exe, start_menu / "RemoteXPTI.lnk", "RemoteXPTI - RDP Quick Launcher")

            time.sleep(0.4)

            # 5. Conclusão
            def on_finished():
                self.progress_bar.stop()
                self.progress_bar.set(1.0)
                self.lbl_progress.configure(
                    text="✅ Instalação concluída com sucesso!",
                    text_color="#00cc66"
                )
                self.btn_cancel.destroy()
                self.btn_install.configure(
                    state="normal",
                    text="Concluir e Abrir",
                    command=lambda: self._finish_and_launch(dest_exe)
                )

            self.after(0, on_finished)

        except Exception as e:
            def on_error():
                self.progress_bar.stop()
                self.lbl_progress.configure(text=f"Erro: {str(e)}", text_color="#ff5555")
                self.btn_install.configure(state="normal", text="Tentar Novamente")
                self.btn_cancel.configure(state="normal")

            self.after(0, on_error)

    def _finish_and_launch(self, exe_path: Path):
        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.Popen([str(exe_path)], creationflags=creation_flags)
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = SetupApp()
    app.mainloop()
