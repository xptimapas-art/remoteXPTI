import customtkinter as ctk
from typing import Optional, Dict, Any, Callable, List
import threading
import time
from pathlib import Path
from tkinter import filedialog
from rdp_manager import RDPManager
from preview_manager import PreviewManager
from uninstaller import Uninstaller
from logger import open_logs_folder, log
from config_manager import ConfigManager
from cloud_sync import CloudSyncManager
from updater import SilentAutoUpdater

class ServerDialog(ctk.CTkToplevel):
    """Janela modal para criação ou edição de perfil de servidor RDP."""

    def __init__(
        self,
        parent,
        server_data: Optional[Dict[str, Any]] = None,
        existing_groups: Optional[List[str]] = None,
        on_save: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_delete: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.parent = parent
        self.server_data = server_data or {}
        self.existing_groups = existing_groups or ["BEMTEVI", "SEJURI"]
        if not self.existing_groups:
            self.existing_groups = ["BEMTEVI", "SEJURI"]
        self.on_save = on_save
        self.on_delete = on_delete
        self.is_edit = bool(server_data and "id" in server_data)

        self.title("Editar Servidor" if self.is_edit else "Novo Servidor RDP")
        self.geometry("540x680")
        self.minsize(500, 640)
        self.resizable(False, False)

        # Configurações do modal
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        self._show_password = False
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        # Container principal com padding
        main_frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("gray92", "#1e1e24"))
        main_frame.pack(fill="both", expand=True, padx=16, pady=16)

        # Header com título estilizado
        header_text = "⚙️ Editar Configurações RDP" if self.is_edit else "🖥️ Adicionar Novo Servidor"
        lbl_title = ctk.CTkLabel(
            main_frame,
            text=header_text,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=("gray10", "#ffffff")
        )
        lbl_title.pack(anchor="w", padx=20, pady=(15, 5))

        lbl_subtitle = ctk.CTkLabel(
            main_frame,
            text="Configure os dados de acesso e credenciais de login automático.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "#a0a0a0")
        )
        lbl_subtitle.pack(anchor="w", padx=20, pady=(0, 15))

        # Formulário em ScrollableFrame para caber com elegância em qualquer resolução
        form_frame = ctk.CTkScrollableFrame(main_frame, fg_color="transparent")
        form_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 1. Nome Amigável
        ctk.CTkLabel(form_frame, text="Nome do Servidor *", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(5, 2))
        self.entry_name = ctk.CTkEntry(form_frame, placeholder_text="Ex: Servidor Principal / Banco ERP", height=38)
        self.entry_name.pack(fill="x", padx=10, pady=(0, 10))

        # 2. Host e Porta em linha
        row_host = ctk.CTkFrame(form_frame, fg_color="transparent")
        row_host.pack(fill="x", padx=10, pady=(0, 10))

        col_host = ctk.CTkFrame(row_host, fg_color="transparent")
        col_host.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkLabel(col_host, text="Endereço IP ou Hostname *", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 2))
        self.entry_host = ctk.CTkEntry(col_host, placeholder_text="192.168.1.100 ou srv.meudominio.com", height=38)
        self.entry_host.pack(fill="x")

        col_port = ctk.CTkFrame(row_host, fg_color="transparent")
        col_port.pack(side="right", padx=(6, 0))
        ctk.CTkLabel(col_port, text="Porta", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 2))
        self.entry_port = ctk.CTkEntry(col_port, placeholder_text="3389", width=90, height=38)
        self.entry_port.insert(0, "3389")
        self.entry_port.pack()

        # 3. Grupo / Categoria
        ctk.CTkLabel(form_frame, text="Grupo / Categoria", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(0, 2))
        self.combo_group = ctk.CTkComboBox(form_frame, values=self.existing_groups, height=38)
        self.combo_group.set(self.existing_groups[0] if self.existing_groups else "BEMTEVI")
        self.combo_group.pack(fill="x", padx=10, pady=(0, 10))

        # 4. Usuário
        ctk.CTkLabel(form_frame, text="Usuário RDP", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(0, 2))
        self.entry_user = ctk.CTkEntry(form_frame, placeholder_text=r"Ex: bemtevi.net\xpti", height=38)
        self.entry_user.pack(fill="x", padx=10, pady=(0, 10))

        # 5. Senha com botão de alternar visibilidade
        ctk.CTkLabel(form_frame, text="Senha RDP", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(0, 2))
        pwd_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        pwd_row.pack(fill="x", padx=10, pady=(0, 10))

        self.entry_password = ctk.CTkEntry(pwd_row, placeholder_text="Senha de acesso ao Windows", show="*", height=38)
        self.entry_password.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_toggle_pwd = ctk.CTkButton(
            pwd_row,
            text="👁️",
            width=46,
            height=38,
            fg_color=("gray75", "#2b2b36"),
            text_color=("gray10", "#ffffff"),
            hover_color=("gray65", "#3a3a48"),
            command=self._toggle_password_visibility
        )
        self.btn_toggle_pwd.pack(side="right")

        # 6. Opções adicionais (Checkboxes)
        opts_frame = ctk.CTkFrame(form_frame, corner_radius=8, fg_color=("gray85", "#25252e"))
        opts_frame.pack(fill="x", padx=10, pady=(5, 10), ipady=6)

        self.chk_fullscreen = ctk.CTkCheckBox(opts_frame, text="Iniciar em Tela Cheia (/f)")
        self.chk_fullscreen.select()
        self.chk_fullscreen.pack(anchor="w", padx=14, pady=4)

        self.chk_admin = ctk.CTkCheckBox(opts_frame, text="Sessão de Console / Administrador (/admin)")
        self.chk_admin.pack(anchor="w", padx=14, pady=4)

        self.chk_multimon = ctk.CTkCheckBox(opts_frame, text="Usar Múltiplos Monitores (/multimon)")
        self.chk_multimon.pack(anchor="w", padx=14, pady=4)

        # 7. Botão Testar Conexão Rápida
        test_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        test_row.pack(fill="x", padx=10, pady=(5, 5))

        self.btn_test = ctk.CTkButton(
            test_row,
            text="⚡ Testar Conectividade de Rede",
            height=32,
            fg_color="transparent",
            border_width=1,
            border_color=("gray60", "#4a4a5a"),
            text_color=("gray20", "#d0d0d0"),
            hover_color=("gray80", "#2c2c36"),
            command=self._test_connection
        )
        self.btn_test.pack(side="left")

        self.lbl_test_result = ctk.CTkLabel(test_row, text="", font=ctk.CTkFont(size=12))
        self.lbl_test_result.pack(side="left", padx=10)

        # 8. Miniatura / Preview Personalizado
        preview_box = ctk.CTkFrame(form_frame, corner_radius=8, fg_color=("gray85", "#25252e"))
        preview_box.pack(fill="x", padx=10, pady=(10, 10), ipady=6)

        ctk.CTkLabel(
            preview_box,
            text="🖼️ Miniatura / Preview da Tela Remota",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=14, pady=(4, 2))

        ctk.CTkLabel(
            preview_box,
            text="O app captura a tela automaticamente ao conectar, ou você pode escolher uma imagem.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "#a0a0a0")
        ).pack(anchor="w", padx=14, pady=(0, 8))

        preview_btn_row = ctk.CTkFrame(preview_box, fg_color="transparent")
        preview_btn_row.pack(fill="x", padx=14, pady=(0, 4))

        self.btn_choose_img = ctk.CTkButton(
            preview_btn_row,
            text="Selecionar Imagem (.png/.jpg)...",
            height=30,
            fg_color=("#d0d4dc", "#343644"),
            hover_color=("#c0c5d0", "#424556"),
            text_color=("gray10", "#ffffff"),
            command=self._choose_custom_image
        )
        self.btn_choose_img.pack(side="left", padx=(0, 8))

        self.btn_reset_thumb = ctk.CTkButton(
            preview_btn_row,
            text="Restaurar Padrão",
            height=30,
            fg_color="transparent",
            border_width=1,
            border_color=("gray60", "#4a4a5a"),
            text_color=("gray20", "#d0d0d0"),
            hover_color=("gray80", "#2c2c36"),
            command=self._reset_thumbnail
        )
        self.btn_reset_thumb.pack(side="left")

        self.lbl_custom_img_status = ctk.CTkLabel(preview_box, text="", font=ctk.CTkFont(size=11))
        self.lbl_custom_img_status.pack(anchor="w", padx=14, pady=(4, 0))

        self.selected_custom_image = None
        self.should_reset_thumb = False

        # 9. Geolocalização para o Mapa Interativo
        geo_box = ctk.CTkFrame(form_frame, corner_radius=8, fg_color=("gray85", "#25252e"))
        geo_box.pack(fill="x", padx=10, pady=(5, 10), ipady=6)

        ctk.CTkLabel(
            geo_box,
            text="📍 Localização no Mapa Interativo",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=14, pady=(4, 2))

        ctk.CTkLabel(
            geo_box,
            text="Coordenadas para exibir o marcador deste servidor no mapa.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "#a0a0a0")
        ).pack(anchor="w", padx=14, pady=(0, 6))

        geo_row = ctk.CTkFrame(geo_box, fg_color="transparent")
        geo_row.pack(fill="x", padx=14, pady=(0, 4))

        col_lat = ctk.CTkFrame(geo_row, fg_color="transparent")
        col_lat.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkLabel(col_lat, text="Latitude", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.entry_lat = ctk.CTkEntry(col_lat, placeholder_text="-27.2000", height=32)
        self.entry_lat.pack(fill="x")

        col_lon = ctk.CTkFrame(geo_row, fg_color="transparent")
        col_lon.pack(side="left", fill="x", expand=True, padx=(6, 6))
        ctk.CTkLabel(col_lon, text="Longitude", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.entry_lon = ctk.CTkEntry(col_lon, placeholder_text="-50.2000", height=32)
        self.entry_lon.pack(fill="x")

        self.btn_auto_geo = ctk.CTkButton(
            geo_row,
            text="📍 Auto-detectar",
            width=110,
            height=32,
            fg_color=("#d0d4dc", "#343644"),
            hover_color=("#c0c5d0", "#424556"),
            text_color=("gray10", "#ffffff"),
            command=self._auto_detect_coordinates
        )
        self.btn_auto_geo.pack(side="right", padx=(6, 0), pady=(18, 0))

        # Rodapé com Botões de Ação
        footer_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        footer_frame.pack(fill="x", padx=10, pady=(10, 5))

        self.lbl_error = ctk.CTkLabel(footer_frame, text="", text_color="#ff5555", font=ctk.CTkFont(size=12))
        self.lbl_error.pack(anchor="w", pady=(0, 6))

        btn_box = ctk.CTkFrame(footer_frame, fg_color="transparent")
        btn_box.pack(fill="x")

        # Se for edição, exibe botão Excluir no canto esquerdo
        if self.is_edit and self.on_delete:
            self.btn_delete = ctk.CTkButton(
                btn_box,
                text="🗑️ Excluir Servidor",
                height=38,
                fg_color="#381e22",
                hover_color="#54252b",
                text_color="#ff6666",
                font=ctk.CTkFont(weight="bold"),
                command=self._confirm_and_delete
            )
            self.btn_delete.pack(side="left")

        self.btn_cancel = ctk.CTkButton(
            btn_box,
            text="Cancelar",
            height=38,
            fg_color=("gray75", "#32323f"),
            hover_color=("gray65", "#404050"),
            text_color=("gray10", "#ffffff"),
            command=self.destroy
        )
        self.btn_cancel.pack(side="right", padx=(8, 0))

        self.btn_save = ctk.CTkButton(
            btn_box,
            text="Salvar Alterações" if self.is_edit else "Salvar Servidor",
            height=38,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(weight="bold"),
            command=self._handle_save
        )
        self.btn_save.pack(side="right")

    def _confirm_and_delete(self):
        self.destroy()
        if self.on_delete:
            self.on_delete()

    def _toggle_password_visibility(self):
        self._show_password = not self._show_password
        if self._show_password:
            self.entry_password.configure(show="")
            self.btn_toggle_pwd.configure(text="🔒")
        else:
            self.entry_password.configure(show="*")
            self.btn_toggle_pwd.configure(text="👁️")

    def _load_data(self):
        if not self.server_data:
            return
        
        self.entry_name.insert(0, self.server_data.get("name", ""))
        self.entry_host.insert(0, self.server_data.get("host", ""))
        self.entry_port.delete(0, "end")
        self.entry_port.insert(0, str(self.server_data.get("port", 3389)))
        
        grp = self.server_data.get("group", "BEMTEVI")
        if grp not in self.existing_groups:
            self.existing_groups.append(grp)
            self.combo_group.configure(values=self.existing_groups)
        self.combo_group.set(grp)

        self.entry_user.insert(0, self.server_data.get("username", ""))
        
        # Carrega senha descriptografada
        pwd = self.server_data.get("password_plain", "")
        if pwd:
            self.entry_password.insert(0, pwd)

        if not self.server_data.get("fullscreen", True):
            self.chk_fullscreen.deselect()

        if self.server_data.get("admin_mode", False):
            self.chk_admin.select()

        if self.server_data.get("multimon", False):
            self.chk_multimon.select()

        if self.server_data.get("latitude") is not None:
            self.entry_lat.delete(0, "end")
            self.entry_lat.insert(0, str(self.server_data.get("latitude")))
        if self.server_data.get("longitude") is not None:
            self.entry_lon.delete(0, "end")
            self.entry_lon.insert(0, str(self.server_data.get("longitude")))

    def _auto_detect_coordinates(self):
        from map_manager import resolve_server_coordinates
        name = self.entry_name.get().strip()
        group = self.combo_group.get().strip()
        coords = resolve_server_coordinates({"name": name, "group": group})
        if coords:
            self.entry_lat.delete(0, "end")
            self.entry_lat.insert(0, str(coords[0]))
            self.entry_lon.delete(0, "end")
            self.entry_lon.insert(0, str(coords[1]))
            self.lbl_error.configure(text=f"✅ Localização detectada: {coords[0]}, {coords[1]}", text_color="#00cc66")
        else:
            self.lbl_error.configure(text="⚠️ Não foi possível identificar a cidade automaticamente.", text_color="#ffaa00")

    def _test_connection(self):
        host = self.entry_host.get().strip()
        port_str = self.entry_port.get().strip() or "3389"

        if not host:
            self.lbl_test_result.configure(text="⚠️ Informe o IP primeiro", text_color="#ffaa00")
            return

        try:
            port = int(port_str)
        except ValueError:
            self.lbl_test_result.configure(text="⚠️ Porta inválida", text_color="#ff5555")
            return

        self.lbl_test_result.configure(text="⏳ Testando...", text_color="#a0a0a0")
        self.btn_test.configure(state="disabled")

        def run_test():
            is_online, msg = RDPManager.check_connection(host, port, timeout=2.0)
            def update_ui():
                self.btn_test.configure(state="normal")
                if is_online:
                    self.lbl_test_result.configure(text=f"🟢 {msg}", text_color="#00cc66")
                else:
                    self.lbl_test_result.configure(text=f"🔴 {msg}", text_color="#ff5555")
            self.after(0, update_ui)

        threading.Thread(target=run_test, daemon=True).start()

    def _choose_custom_image(self):
        filetypes = [
            ("Imagens", "*.png *.jpg *.jpeg *.bmp *.webp"),
            ("Todos os arquivos", "*.*")
        ]
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Selecione a Imagem de Preview",
            filetypes=filetypes
        )
        if chosen:
            self.selected_custom_image = chosen
            self.should_reset_thumb = False
            filename = Path(chosen).name
            self.lbl_custom_img_status.configure(
                text=f"✅ Imagem selecionada: {filename}",
                text_color="#00cc66"
            )

    def _reset_thumbnail(self):
        self.selected_custom_image = None
        self.should_reset_thumb = True
        self.lbl_custom_img_status.configure(
            text="🔄 A miniatura será redefinida para o padrão.",
            text_color="#ffaa00"
        )

    def _handle_save(self):
        name = self.entry_name.get().strip()
        host = self.entry_host.get().strip()
        port_str = self.entry_port.get().strip() or "3389"
        group = self.combo_group.get().strip() or "Geral"
        username = self.entry_user.get().strip()
        password = self.entry_password.get()

        if not name:
            self.lbl_error.configure(text="Por favor, dê um nome para o servidor.")
            self.entry_name.focus()
            return

        if not host:
            self.lbl_error.configure(text="Por favor, informe o IP ou Hostname.")
            self.entry_host.focus()
            return

        try:
            port = int(port_str)
            if port <= 0 or port > 65535:
                raise ValueError()
        except ValueError:
            self.lbl_error.configure(text="A porta precisa ser um número entre 1 e 65535.")
            self.entry_port.focus()
            return

        lat_str = self.entry_lat.get().strip()
        lon_str = self.entry_lon.get().strip()
        lat_val = None
        lon_val = None
        if lat_str and lon_str:
            try:
                lat_val = float(lat_str)
                lon_val = float(lon_str)
            except ValueError:
                pass

        if lat_val is None or lon_val is None:
            from map_manager import resolve_server_coordinates
            auto_coords = resolve_server_coordinates({"name": name, "group": group})
            if auto_coords:
                lat_val, lon_val = auto_coords

        payload = {
            "name": name,
            "host": host,
            "port": port,
            "group": group,
            "username": username,
            "password": password,
            "fullscreen": bool(self.chk_fullscreen.get()),
            "admin_mode": bool(self.chk_admin.get()),
            "multimon": bool(self.chk_multimon.get()),
            "custom_image": self.selected_custom_image,
            "reset_thumb": self.should_reset_thumb,
            "latitude": lat_val,
            "longitude": lon_val
        }

        if self.on_save:
            self.on_save(payload)

        self.destroy()


class ConfirmDialog(ctk.CTkToplevel):
    """Janela de confirmação para ações destrutivas (excluir servidor, desinstalar app)."""
    def __init__(
        self,
        parent,
        title: str,
        message: str,
        on_confirm: Callable[[], None],
        confirm_text: str = "Sim, excluir",
        confirm_color: str = "#cc3333",
        height: int = 200
    ):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"440x{height}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        frame = ctk.CTkFrame(self, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        lbl = ctk.CTkLabel(frame, text=message, font=ctk.CTkFont(size=13), wraplength=390, justify="center")
        lbl.pack(pady=(15, 15), padx=10)

        btn_box = ctk.CTkFrame(frame, fg_color="transparent")
        btn_box.pack(fill="x", padx=10, side="bottom", pady=(0, 5))

        btn_no = ctk.CTkButton(
            btn_box,
            text="Cancelar",
            width=100,
            fg_color=("gray70", "#32323f"),
            command=self.destroy
        )
        btn_no.pack(side="right", padx=(8, 0))

        def confirm_and_close():
            self.destroy()
            on_confirm()

        btn_yes = ctk.CTkButton(
            btn_box,
            text=confirm_text,
            width=160,
            fg_color=confirm_color,
            hover_color="#990000",
            command=confirm_and_close
        )
        btn_yes.pack(side="right")


class DevLoginDialog(ctk.CTkToplevel):
    """Janela modal para autenticação do desenvolvedor / beta tester."""
    def __init__(self, parent, on_success: Callable[[], None]):
        super().__init__(parent)
        self.title("Acesso do Desenvolvedor")
        self.geometry("380x280")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.focus_force()
        self.on_success = on_success

        frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("gray92", "#18191f"))
        frame.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(
            frame,
            text="🔐 Acesso do Desenvolvedor",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=("gray10", "#ffffff")
        ).pack(anchor="w", padx=14, pady=(12, 2))

        ctk.CTkLabel(
            frame,
            text="Digite a senha mestre para desbloquear os canais de teste, seletor de versões e sincronização.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "#8e92a0"),
            wraplength=320,
            justify="left"
        ).pack(anchor="w", padx=14, pady=(0, 14))

        self.entry_pwd = ctk.CTkEntry(
            frame,
            placeholder_text="Senha de Desenvolvedor...",
            show="*",
            height=36
        )
        self.entry_pwd.pack(fill="x", padx=14, pady=(0, 8))
        self.entry_pwd.bind("<Return>", lambda e: self._submit())
        self.entry_pwd.focus()

        self.lbl_error = ctk.CTkLabel(
            frame,
            text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ff4d4d"
        )
        self.lbl_error.pack(anchor="w", padx=14, pady=(0, 8))

        btn_box = ctk.CTkFrame(frame, fg_color="transparent")
        btn_box.pack(fill="x", padx=14, side="bottom", pady=(0, 6))

        btn_cancel = ctk.CTkButton(
            btn_box,
            text="Cancelar",
            width=90,
            height=32,
            fg_color=("gray75", "#2e303b"),
            command=self.destroy
        )
        btn_cancel.pack(side="left")

        btn_ok = ctk.CTkButton(
            btn_box,
            text="Entrar",
            width=110,
            height=32,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._submit
        )
        btn_ok.pack(side="right")

    def _submit(self):
        pwd = self.entry_pwd.get().strip()
        if not pwd:
            self.lbl_error.configure(text="Digite a senha de desenvolvedor.")
            return
        if ConfigManager().authenticate_dev(pwd):
            self.destroy()
            self.on_success()
        else:
            self.lbl_error.configure(text="Senha incorreta. Tente novamente.")
            self.entry_pwd.delete(0, "end")


class SupabaseConfigDialog(ctk.CTkToplevel):
    """Janela modal para configurar a sincronização em nuvem com Supabase."""
    def __init__(self, parent, on_saved: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.parent = parent
        self.on_saved = on_saved
        self.title("Sincronização em Nuvem (Supabase)")
        self.geometry("490x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        cfg = ConfigManager().get_supabase_config()

        frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("gray92", "#18191f"))
        frame.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(
            frame,
            text="☁️ Configuração do Supabase",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=("gray10", "#ffffff")
        ).pack(anchor="w", padx=14, pady=(12, 2))

        ctk.CTkLabel(
            frame,
            text="Sincronize servidores e configurações automaticamente com os clientes.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "#8e92a0"),
            justify="left"
        ).pack(anchor="w", padx=14, pady=(0, 12))

        ctk.CTkLabel(frame, text="URL do Projeto Supabase:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=14, pady=(2, 2))
        self.entry_url = ctk.CTkEntry(frame, placeholder_text="https://xyzcompany.supabase.co", height=34)
        self.entry_url.insert(0, cfg.get("url", ""))
        self.entry_url.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(frame, text="Chave de API (Anon Key):", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=14, pady=(2, 2))
        self.entry_key = ctk.CTkEntry(frame, placeholder_text="eyJhbGciOi...", show="*", height=34)
        self.entry_key.insert(0, cfg.get("key", ""))
        self.entry_key.pack(fill="x", padx=14, pady=(0, 10))

        self.sw_enable = ctk.CTkSwitch(frame, text="Ativar Sincronização em Nuvem", font=ctk.CTkFont(size=11))
        if cfg.get("enabled"):
            self.sw_enable.select()
        else:
            self.sw_enable.deselect()
        self.sw_enable.pack(anchor="w", padx=14, pady=(0, 10))

        self.lbl_status = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(size=11))
        self.lbl_status.pack(anchor="w", padx=14, pady=(0, 8))

        btn_box = ctk.CTkFrame(frame, fg_color="transparent")
        btn_box.pack(fill="x", padx=14, side="bottom", pady=(0, 6))

        btn_test = ctk.CTkButton(
            btn_box,
            text="🔌 Testar Conexão",
            height=32,
            fg_color=("#d6dae2", "#2e303b"),
            command=self._test_conn
        )
        btn_test.pack(side="left")

        btn_save = ctk.CTkButton(
            btn_box,
            text="Salvar Configuração",
            height=32,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._save
        )
        btn_save.pack(side="right")

    def _test_conn(self):
        url = self.entry_url.get().strip()
        key = self.entry_key.get().strip()
        self.lbl_status.configure(text="Testando conexão com Supabase...", text_color="#0080ff")
        self.update()
        ok, msg = CloudSyncManager.test_connection(url, key)
        color = "#00cc66" if ok else "#ff4d4d"
        self.lbl_status.configure(text=msg, text_color=color)

    def _save(self):
        url = self.entry_url.get().strip()
        key = self.entry_key.get().strip()
        enabled = self.sw_enable.get() == 1
        ConfigManager().set_supabase_config(url, key, enabled)
        if self.on_saved:
            self.on_saved()
        self.destroy()


class SettingsDialog(ctk.CTkToplevel):
    """Janela modal de Configurações Gerais, Manutenção e Painel do Desenvolvedor do RemoteXPTI."""

    def __init__(
        self,
        parent,
        current_version: str,
        on_check_updates: Callable[[], None],
        on_clean_thumbnails: Optional[Callable[[], None]] = None,
        on_clean_credentials: Optional[Callable[[], None]] = None,
        on_uninstall: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.parent = parent
        self.current_version = current_version
        self.on_check_updates = on_check_updates
        self.on_clean_thumbnails = on_clean_thumbnails
        self.on_clean_credentials = on_clean_credentials
        self.on_uninstall = on_uninstall
        self._fetched_releases = []

        self.title("Configurações - RemoteXPTI")
        self.geometry("500x620")
        self.minsize(460, 520)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.main_frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("gray92", "#18191f"))
        self.main_frame.pack(fill="both", expand=True, padx=14, pady=14)

        # 1. Cabeçalho
        lbl_title = ctk.CTkLabel(
            self.main_frame,
            text="⚙️ Configurações do Sistema",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=("gray10", "#ffffff")
        )
        lbl_title.pack(anchor="w", padx=16, pady=(14, 2))

        lbl_sub = ctk.CTkLabel(
            self.main_frame,
            text=f"RemoteXPTI v{current_version} • Gestão de Preferências, Canais e Manutenção",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "#8e92a0")
        )
        lbl_sub.pack(anchor="w", padx=16, pady=(0, 10))

        # 2. Container Scrollável de Seções
        self.scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        self._build_sections()

        # 3. Rodapé
        btn_close = ctk.CTkButton(
            self.main_frame,
            text="Fechar",
            height=32,
            fg_color=("gray75", "#282a33"),
            hover_color=("gray65", "#353742"),
            text_color=("gray10", "#ffffff"),
            command=self.destroy
        )
        btn_close.pack(fill="x", padx=12, pady=(0, 6))

    def _reload_sections(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._build_sections()
        if hasattr(self.parent, "refresh_servers"):
            try:
                self.parent.refresh_servers()
            except Exception:
                pass

    def _build_sections(self):
        cfg = ConfigManager()
        is_dev = cfg.is_dev_authenticated()
        active_channel = cfg.get_update_channel()

        # --- SEÇÃO 1: Atualizações de Software ---
        card_update = ctk.CTkFrame(self.scroll, corner_radius=8, fg_color=("gray86", "#21232b"))
        card_update.pack(fill="x", padx=4, pady=6)

        ctk.CTkLabel(
            card_update,
            text="🔄 Atualizações de Software",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray15", "#e0e4ee")
        ).pack(anchor="w", padx=14, pady=(10, 2))

        channel_text = "Canal Beta Tester (1.x.y)" if active_channel == "beta_tester" else "Canal Beta Público (1.x.0)"
        ctk.CTkLabel(
            card_update,
            text=f"Versão atual: v{self.current_version} • {channel_text}\nO app verifica e baixa novas versões automaticamente em segundo plano.",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "#8e92a0"),
            justify="left"
        ).pack(anchor="w", padx=14, pady=(0, 8))

        btn_check = ctk.CTkButton(
            card_update,
            text="🔍 Verificar Atualizações no GitHub",
            height=32,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: (self.destroy(), self.on_check_updates())
        )
        btn_check.pack(fill="x", padx=14, pady=(0, 12))

        # --- SEÇÃO 2: Área do Desenvolvedor & Beta Tester ---
        card_dev = ctk.CTkFrame(self.scroll, corner_radius=8, fg_color=("gray86", "#21232b"))
        card_dev.pack(fill="x", padx=4, pady=6)

        if not is_dev:
            ctk.CTkLabel(
                card_dev,
                text="🔐 Área do Desenvolvedor",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("gray15", "#e0e4ee")
            ).pack(anchor="w", padx=14, pady=(10, 2))

            ctk.CTkLabel(
                card_dev,
                text="Acesso restrito para alternar canais de atualização, testar builds intermediários e gerenciar nuvem.",
                font=ctk.CTkFont(size=10),
                text_color=("gray40", "#8e92a0"),
                justify="left"
            ).pack(anchor="w", padx=14, pady=(0, 8))

            btn_dev_login = ctk.CTkButton(
                card_dev,
                text="🔑 Acessar Modo Desenvolvedor...",
                height=32,
                fg_color=("#d6dae2", "#2e303b"),
                hover_color=("#c4c8d2", "#3b3d4a"),
                text_color=("gray10", "#ffffff"),
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda: DevLoginDialog(self, on_success=self._reload_sections)
            )
            btn_dev_login.pack(fill="x", padx=14, pady=(0, 12))
        else:
            # Painel Ativo de Desenvolvedor
            dev_header = ctk.CTkFrame(card_dev, fg_color="transparent")
            dev_header.pack(fill="x", padx=14, pady=(10, 4))

            ctk.CTkLabel(
                dev_header,
                text="🟢 Painel do Desenvolvedor Ativo",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#00cc66"
            ).pack(side="left")

            btn_logout = ctk.CTkButton(
                dev_header,
                text="🚪 Sair",
                width=65,
                height=24,
                font=ctk.CTkFont(size=10),
                fg_color=("#ffdddd", "#381a1e"),
                hover_color=("#ffc2c2", "#522228"),
                text_color=("#cc0000", "#ff6b6b"),
                command=lambda: (cfg.logout_dev(), self._reload_sections())
            )
            btn_logout.pack(side="right")

            # 1. Alternador de Canal
            ctk.CTkLabel(
                card_dev,
                text="Canal de Distribuição Selecionado:",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray20", "#d0d4e0")
            ).pack(anchor="w", padx=14, pady=(4, 2))

            def on_channel_changed(val):
                new_ch = "public" if "Público" in val else "beta_tester"
                cfg.set_update_channel(new_ch)
                self._reload_sections()

            seg_channel = ctk.CTkSegmentedButton(
                card_dev,
                values=["Canal Beta Público (1.x.0)", "Canal Beta Tester (1.x.y)"],
                command=on_channel_changed
            )
            seg_channel.set("Canal Beta Tester (1.x.y)" if active_channel == "beta_tester" else "Canal Beta Público (1.x.0)")
            seg_channel.pack(fill="x", padx=14, pady=(0, 8))

            # 2. Seletor de Versões do GitHub
            ctk.CTkLabel(
                card_dev,
                text="Seletor de Versões do GitHub (Instalação / Rollback):",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray20", "#d0d4e0")
            ).pack(anchor="w", padx=14, pady=(4, 2))

            row_sel = ctk.CTkFrame(card_dev, fg_color="transparent")
            row_sel.pack(fill="x", padx=14, pady=(0, 6))

            self.combo_versions = ctk.CTkComboBox(
                row_sel,
                values=["Clique em 'Listar Versões'..."],
                height=30
            )
            self.combo_versions.pack(side="left", fill="x", expand=True, padx=(0, 6))

            btn_fetch = ctk.CTkButton(
                row_sel,
                text="🔄 Listar",
                width=65,
                height=30,
                fg_color=("#d6dae2", "#2e303b"),
                command=self._fetch_releases_list
            )
            btn_fetch.pack(side="right")

            self.btn_install_custom = ctk.CTkButton(
                card_dev,
                text="⬇️ Instalar Versão Selecionada",
                height=30,
                fg_color="#0066cc",
                hover_color="#0052a3",
                font=ctk.CTkFont(size=11, weight="bold"),
                command=self._install_selected_version
            )
            self.btn_install_custom.pack(fill="x", padx=14, pady=(0, 8))

            self.lbl_custom_status = ctk.CTkLabel(card_dev, text="", font=ctk.CTkFont(size=10))
            self.lbl_custom_status.pack(anchor="w", padx=14, pady=(0, 6))

            # 3. Sincronização em Nuvem (Supabase)
            ctk.CTkLabel(
                card_dev,
                text="Sincronização em Nuvem (Supabase):",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray20", "#d0d4e0")
            ).pack(anchor="w", padx=14, pady=(6, 2))

            row_cloud = ctk.CTkFrame(card_dev, fg_color="transparent")
            row_cloud.pack(fill="x", padx=14, pady=(0, 10))

            btn_cfg_cloud = ctk.CTkButton(
                row_cloud,
                text="☁️ Configurar Supabase",
                height=28,
                fg_color=("#d6dae2", "#2e303b"),
                command=lambda: SupabaseConfigDialog(self, on_saved=self._reload_sections)
            )
            btn_cfg_cloud.pack(side="left", fill="x", expand=True, padx=(0, 4))

            btn_push_cloud = ctk.CTkButton(
                row_cloud,
                text="📤 Enviar p/ Nuvem",
                height=28,
                fg_color=("#d6dae2", "#2e303b"),
                command=self._push_servers_to_cloud
            )
            btn_push_cloud.pack(side="right", fill="x", expand=True, padx=(4, 0))

            # Carrega automaticamente a lista de versões disponíveis do GitHub
            self.after(60, self._fetch_releases_list)

        # --- SEÇÃO 3: Manutenção e Diagnóstico ---
        card_maint = ctk.CTkFrame(self.scroll, corner_radius=8, fg_color=("gray86", "#21232b"))
        card_maint.pack(fill="x", padx=4, pady=6)

        ctk.CTkLabel(
            card_maint,
            text="🧹 Manutenção e Diagnóstico",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray15", "#e0e4ee")
        ).pack(anchor="w", padx=14, pady=(10, 2))

        if self.on_clean_thumbnails:
            btn_clean_thumbs = ctk.CTkButton(
                card_maint,
                text="🖼️ Limpar Cache de Miniaturas",
                height=30,
                fg_color=("#d6dae2", "#2e303b"),
                hover_color=("#c4c8d2", "#3b3d4a"),
                text_color=("gray10", "#ffffff"),
                font=ctk.CTkFont(size=11),
                command=lambda: (self.destroy(), self.on_clean_thumbnails())
            )
            btn_clean_thumbs.pack(fill="x", padx=14, pady=(0, 6))

        if self.on_clean_credentials:
            btn_clean_creds = ctk.CTkButton(
                card_maint,
                text="🔐 Limpar Credenciais do Windows (TERMSRV)",
                height=30,
                fg_color=("#d6dae2", "#2e303b"),
                hover_color=("#c4c8d2", "#3b3d4a"),
                text_color=("gray10", "#ffffff"),
                font=ctk.CTkFont(size=11),
                command=lambda: (self.destroy(), self.on_clean_credentials())
            )
            btn_clean_creds.pack(fill="x", padx=14, pady=(0, 6))

        btn_logs = ctk.CTkButton(
            card_maint,
            text="📁 Abrir Pasta de Logs de Diagnóstico",
            height=30,
            fg_color=("#d6dae2", "#2e303b"),
            hover_color=("#c4c8d2", "#3b3d4a"),
            text_color=("gray10", "#ffffff"),
            font=ctk.CTkFont(size=11),
            command=open_logs_folder
        )
        btn_logs.pack(fill="x", padx=14, pady=(0, 12))

        # --- SEÇÃO 4: Desinstalação ---
        if self.on_uninstall:
            card_uninst = ctk.CTkFrame(self.scroll, corner_radius=8, fg_color=("gray86", "#21232b"))
            card_uninst.pack(fill="x", padx=4, pady=6)

            ctk.CTkLabel(
                card_uninst,
                text="🗑️ Desinstalação do Aplicativo",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("gray15", "#e0e4ee")
            ).pack(anchor="w", padx=14, pady=(10, 2))

            btn_uninst = ctk.CTkButton(
                card_uninst,
                text="Desinstalar RemoteXPTI por Completo...",
                height=32,
                fg_color=("#ffdddd", "#381a1e"),
                hover_color=("#ffc2c2", "#522228"),
                text_color=("#cc0000", "#ff6b6b"),
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda: (self.destroy(), self.on_uninstall())
            )
            btn_uninst.pack(fill="x", padx=14, pady=(0, 12))

    def _fetch_releases_list(self):
        if not hasattr(self, "combo_versions") or not self.combo_versions.winfo_exists():
            return
        self.combo_versions.set("Buscando versões disponíveis...")
        self.lbl_custom_status.configure(text="Consultando lançamentos no GitHub...", text_color="#0080ff")

        result_holder = []

        def worker():
            try:
                releases = SilentAutoUpdater.fetch_all_releases()
                result_holder.append(releases)
            except Exception as e:
                log.error(f"[SettingsDialog] Erro na busca de releases: {e}")
                result_holder.append([])

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            if not self.winfo_exists():
                return
            if result_holder:
                releases = result_holder[0]
                self._fetched_releases = releases
                options = []
                for r in releases:
                    options.append(f"{r['tag']} • [{r['channel_label']}] {r['name']}")

                if options:
                    self.combo_versions.configure(values=options)
                    self.combo_versions.set(options[0])
                    self.lbl_custom_status.configure(
                        text=f"✅ {len(options)} versões disponíveis encontradas.",
                        text_color="#00cc66"
                    )
                else:
                    self.combo_versions.set("Nenhuma versão encontrada.")
                    self.lbl_custom_status.configure(
                        text="⚠️ Nenhuma versão localizada no momento.",
                        text_color="#ff4d4d"
                    )
            else:
                self.after(100, poll)

        self.after(100, poll)

    def _install_selected_version(self):
        selected_text = self.combo_versions.get()
        if not selected_text or not hasattr(self, "_fetched_releases") or not self._fetched_releases:
            self.lbl_custom_status.configure(text="Aguarde o carregamento das versões ou clique em 🔄 Listar.", text_color="#ff4d4d")
            return
        tag = selected_text.split(" • ")[0].strip()
        matched = next((r for r in self._fetched_releases if r["tag"] == tag), None)
        if not matched or not matched.get("download_url"):
            self.lbl_custom_status.configure(text=f"Link de download não localizado para {tag}.", text_color="#ff4d4d")
            return

        def do_install():
            from splash_screen import SplashScreen
            # Fecha a janela de configurações e exibe a tela animada com o motion do X
            self.destroy()

            parent_window = self.parent if hasattr(self, "parent") and self.parent else None
            update_splash = SplashScreen(
                parent=parent_window,
                title="Atualizando RemoteXPTI",
                subtitle=f"XPti Tecnologia  •  Instalando {tag}",
                initial_status=f"Baixando {tag} do GitHub..."
            )

            status_queue = []

            def on_status_bg(msg):
                status_queue.append(msg)

            def poll_status():
                if hasattr(update_splash, "window") and update_splash.window.winfo_exists():
                    while status_queue:
                        msg = status_queue.pop(0)
                        update_splash.set_status(msg)
                    if getattr(updater, "update_ready", False):
                        update_splash.set_status(f"Versão {tag} pronta! Reiniciando...")
                    else:
                        parent_window.after(150, poll_status)

            parent_window.after(150, poll_status)

            updater = getattr(parent_window, "updater", None) or SilentAutoUpdater()
            updater.download_and_install_specific(matched["tag"], matched["download_url"], on_status=on_status_bg)

        ConfirmDialog(
            parent=self,
            title=f"Instalar Versão {tag}",
            message=f"Deseja baixar e instalar a versão {tag}?\n\nO RemoteXPTI exibirá o progresso com a animação de atualização e será reiniciado automaticamente.",
            confirm_text="Sim, Instalar Agora",
            confirm_color="#0066cc",
            on_confirm=do_install
        )

    def _push_servers_to_cloud(self):
        if not CloudSyncManager.is_configured():
            SupabaseConfigDialog(self, on_saved=self._reload_sections)
            return

        servers = getattr(self.parent, "storage", None)
        if servers and hasattr(servers, "servers"):
            ok, msg = CloudSyncManager.push_servers(servers.servers)
            color = "#00cc66" if ok else "#ff4d4d"
            self.lbl_custom_status.configure(text=msg, text_color=color)



# Alias de compatibilidade
UpdateMenuDialog = SettingsDialog


class UninstallProgressDialog(ctk.CTkToplevel):
    """Janela modal com barra de progresso em tempo real para desinstalação completa."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Desinstalando RemoteXPTI")
        self.geometry("460x240")
        self.minsize(460, 240)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        # Design do card
        main_frame = ctk.CTkFrame(self, corner_radius=12, fg_color=("gray92", "#18191f"))
        main_frame.pack(fill="both", expand=True, padx=16, pady=16)

        lbl_title = ctk.CTkLabel(
            main_frame,
            text="🗑️ Desinstalando o RemoteXPTI",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=("gray10", "#ffffff")
        )
        lbl_title.pack(anchor="w", padx=16, pady=(16, 4))

        self.lbl_subtitle = ctk.CTkLabel(
            main_frame,
            text="Aguarde enquanto removemos todos os arquivos e configurações...",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "#8e92a0")
        )
        self.lbl_subtitle.pack(anchor="w", padx=16, pady=(0, 16))

        # Barra de Progresso
        self.pbar = ctk.CTkProgressBar(main_frame, height=14, corner_radius=7)
        self.pbar.pack(fill="x", padx=16, pady=(0, 10))
        self.pbar.set(0.05)

        # Status detalhado
        self.lbl_status = ctk.CTkLabel(
            main_frame,
            text="Iniciando procedimentos de desinstalação...",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#0080ff"
        )
        self.lbl_status.pack(anchor="w", padx=16, pady=(0, 14))

        # Botão Concluir (inicialmente desabilitado)
        self.btn_done = ctk.CTkButton(
            main_frame,
            text="Aguarde...",
            height=32,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(size=12, weight="bold"),
            state="disabled",
            command=self._on_done_clicked
        )
        self.btn_done.pack(fill="x", padx=16, pady=(0, 8))

        # Inicia a thread de desinstalação silenciosa
        threading.Thread(target=self._run_uninstallation, daemon=True).start()

    def _run_uninstallation(self):
        def update_ui(prog: float, text: str, color: str = "#0080ff"):
            self.after(0, lambda: (
                self.pbar.set(prog),
                self.lbl_status.configure(text=text, text_color=color)
            ))

        time.sleep(0.4)
        # Etapa 1: Limpar credenciais do Windows (TERMSRV)
        update_ui(0.30, "🔐 Limpando credenciais do Windows (TERMSRV)...")
        Uninstaller.cleanup_windows_credentials()
        time.sleep(0.5)

        # Etapa 2: Remover atalhos
        update_ui(0.60, "🗑️ Removendo atalhos da Área de Trabalho e Menu Iniciar...")
        Uninstaller.remove_shortcuts()
        time.sleep(0.5)

        # Etapa 3: Excluir cache e arquivos de dados
        update_ui(0.85, "🧹 Excluindo miniaturas, perfis temporários e configurações...")
        Uninstaller.remove_data_and_temp_files()
        time.sleep(0.5)

        # Etapa 4: Concluído
        def on_finished():
            self.pbar.set(1.0)
            self.pbar.configure(progress_color="#00cc66")
            self.lbl_status.configure(text="✅ Desinstalação concluída com sucesso!", text_color="#00cc66")
            self.lbl_subtitle.configure(text="Todos os arquivos, atalhos e credenciais foram removidos.")
            self.btn_done.configure(state="normal", text="Concluir e Fechar")
            # Auto-fecha em 2.5 segundos
            self.after(2500, self._on_done_clicked)

        self.after(0, on_finished)

    def _on_done_clicked(self):
        Uninstaller.finalize_self_delete_and_exit()

