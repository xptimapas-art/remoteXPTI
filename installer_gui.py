import os
import sys
import shutil
import time
import threading
import subprocess
from pathlib import Path
from PIL import Image
import customtkinter as ctk
from typing import Optional
from version import CURRENT_VERSION
from install_safety import validate_install_dir, close_installed_app

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

def create_windows_shortcut(target: Path, shortcut_dest: Path, description: str = "", icon_path: Optional[Path] = None):
    """Cria atalho .lnk no Windows com o ícone oficial estilizado (squircle escuro + X)."""
    if not icon_path or not icon_path.exists():
        icon_path = target
    ps_literal = lambda value: str(value).replace("'", "''")
    script = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut('{ps_literal(shortcut_dest)}')
    $Shortcut.TargetPath = '{ps_literal(target)}'
    $Shortcut.WorkingDirectory = '{ps_literal(target.parent)}'
    $Shortcut.Description = '{ps_literal(description)}'
    $Shortcut.IconLocation = '{ps_literal(icon_path)},0'
    $Shortcut.Save()
    """
    creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-Command", script],
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

        # Ícone da janela do instalador
        icon_path = get_bundle_resource("imagens/icon.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        icon_png_path = get_bundle_resource("imagens/app_icon.png")
        if icon_png_path.exists():
            try:
                import tkinter as tk
                self._app_icon_photo = tk.PhotoImage(file=str(icon_png_path))
                self.wm_iconphoto(True, self._app_icon_photo)
            except Exception:
                pass

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
            text=f"RemoteXPTI - Gerenciador RDP Ágil v{CURRENT_VERSION}",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "#8e92a0")
        ).pack(anchor="w")

        # Logo Oficial XPti no cabeçalho
        logo_path = get_bundle_resource("imagens/XPti_negativo_color.png")
        if logo_path.exists():
            try:
                pil_logo = Image.open(logo_path)
                self.logo_header_img = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(92, 38))
                lbl_logo = ctk.CTkLabel(header, image=self.logo_header_img, text="")
                lbl_logo.pack(side="right", padx=20, pady=12)
            except Exception:
                pass

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

        self.chk_servers = ctk.CTkCheckBox(opts_box, text="Criar configuração inicial de servidores", font=ctk.CTkFont(size=12))
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
        try:
            target_dir = validate_install_dir(self.entry_dir.get())
            self.lbl_progress.configure(text="Passo 1: Fechando esta instalação do RemoteXPTI...")
            close_installed_app(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)

            # 2. Copia RemoteXPTI.exe embutido (com retry caso o Windows demore a liberar o processo)
            self.lbl_progress.configure(text="Passo 3: Copiando arquivos atualizados...")
            source_exe = get_bundle_resource("app_payload.bin")
            if not source_exe.exists():
                source_exe = get_bundle_resource("RemoteXPTI.exe")
            dest_exe = target_dir / "RemoteXPTI.exe"
            
            if not source_exe.exists():
                raise FileNotFoundError(f"Arquivo executável não encontrado: {source_exe}")

            staged_exe = target_dir / "RemoteXPTI.installing.exe"
            shutil.copy2(source_exe, staged_exe)
            with staged_exe.open("rb") as stream:
                if stream.read(2) != b"MZ":
                    raise ValueError("O pacote não contém um executável Windows válido.")
            if dest_exe.exists():
                shutil.copy2(dest_exe, target_dir / "RemoteXPTI.previous.exe")
            for attempt in range(4):
                try:
                    staged_exe.replace(dest_exe)
                    break
                except PermissionError:
                    if attempt == 3:
                        raise PermissionError("Feche esta instalação do RemoteXPTI e tente novamente.")
                    close_installed_app(target_dir)
                    time.sleep(0.8)

            # Pacotes novos contêm somente um template vazio, nunca credenciais.
            if self.chk_servers.get():
                source_json = get_bundle_resource("servers.json")
                dest_json = target_dir / "servers.json"
                if source_json.exists() and not dest_json.exists():
                    shutil.copy2(source_json, dest_json)

            # Copia pasta de imagens oficiais
            source_imagens = get_bundle_resource("imagens")
            dest_imagens = target_dir / "imagens"
            if source_imagens.exists() and source_imagens.is_dir():
                dest_imagens.mkdir(parents=True, exist_ok=True)
                for item in source_imagens.iterdir():
                    if item.is_file():
                        try:
                            shutil.copy2(item, dest_imagens / item.name)
                        except Exception:
                            pass

            # 4. Cria atalhos
            self.lbl_progress.configure(text="Passo 5: Criando atalhos no Windows...")
            
            dest_ico = dest_imagens / "app_icon.ico"
            if not dest_ico.exists():
                dest_ico = dest_imagens / "icon.ico"
            shortcut_icon = dest_ico if dest_ico.exists() else dest_exe

            # Atalho Desktop
            userprofile = Path(os.environ.get("USERPROFILE", str(Path.home())))
            desktop_candidates = [
                userprofile / "Desktop",
                userprofile / "OneDrive" / "Desktop",
                userprofile / "OneDrive" / "Área de Trabalho",
                userprofile / "Área de Trabalho",
                Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
            ]
            real_desktop = None
            try:
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                    capture_output=True, text=True, timeout=10, creationflags=creation_flags
                ).stdout.strip()
                if out and Path(out).is_dir():
                    real_desktop = Path(out)
            except Exception:
                pass

            # Remove atalhos antigos/duplicados (ex.: V1 apontando para pythonw.exe)
            for d in ([real_desktop] if real_desktop else []) + desktop_candidates:
                try:
                    if d and d.is_dir():
                        for lnk in d.glob("RemoteXPTI*.lnk"):
                            try:
                                lnk.unlink()
                            except Exception:
                                pass
                except Exception:
                    pass

            if self.chk_desktop.get():
                targets = [real_desktop] if real_desktop else [d for d in desktop_candidates[:4] if d.is_dir()][:1]
                for d in targets:
                    create_windows_shortcut(dest_exe, d / "RemoteXPTI.lnk", "RemoteXPTI - RDP Quick Launcher", shortcut_icon)

            # Atalho Menu Iniciar
            if self.chk_startmenu.get():
                appdata = os.environ.get("APPDATA", "")
                start_menu = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                if start_menu.exists():
                    create_windows_shortcut(dest_exe, start_menu / "RemoteXPTI.lnk", "RemoteXPTI - RDP Quick Launcher", shortcut_icon)

            try:
                import ctypes
                ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
            except Exception:
                pass

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
            error_message = str(e)
            def on_error():
                self.progress_bar.stop()
                self.lbl_progress.configure(text=f"Erro: {error_message}", text_color="#ff5555")
                self.btn_install.configure(state="normal", text="Tentar Novamente")
                self.btn_cancel.configure(state="normal")

            self.after(0, on_error)

    def _finish_and_launch(self, exe_path: Path):
        try:
            clean_env = {
                k: v for k, v in os.environ.items()
                if not k.startswith("_MEI") and not k.startswith("PYI_") and not k.startswith("_PYI_")
            }
            clean_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
            subprocess.Popen(
                [str(exe_path)],
                cwd=str(exe_path.parent),
                env=clean_env
            )
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("xpti.remotexpti.setup")
    except Exception:
        pass
    app = SetupApp()
    app.mainloop()
