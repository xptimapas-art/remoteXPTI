import customtkinter as ctk
from typing import Optional, Dict, Any, Callable, List
import threading
from pathlib import Path
from tkinter import filedialog
from rdp_manager import RDPManager
from preview_manager import PreviewManager

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
        self.existing_groups = existing_groups or ["Geral", "Produção", "Filiais", "Clientes"]
        if "Geral" not in self.existing_groups:
            self.existing_groups.insert(0, "Geral")
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
        self.combo_group.set("Geral")
        self.combo_group.pack(fill="x", padx=10, pady=(0, 10))

        # 4. Usuário
        ctk.CTkLabel(form_frame, text="Usuário RDP", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(0, 2))
        self.entry_user = ctk.CTkEntry(form_frame, placeholder_text="Ex: Administrador ou DOMINIO\\usuario", height=38)
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
        
        grp = self.server_data.get("group", "Geral")
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
            "reset_thumb": self.should_reset_thumb
        }

        if self.on_save:
            self.on_save(payload)

        self.destroy()


class ConfirmDialog(ctk.CTkToplevel):
    """Janela de confirmação para ações destrutivas (excluir servidor)."""
    def __init__(self, parent, title: str, message: str, on_confirm: Callable[[], None]):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x190")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        frame = ctk.CTkFrame(self, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        lbl = ctk.CTkLabel(frame, text=message, font=ctk.CTkFont(size=14), wraplength=350)
        lbl.pack(pady=(20, 20), padx=10)

        btn_box = ctk.CTkFrame(frame, fg_color="transparent")
        btn_box.pack(fill="x", padx=10)

        btn_no = ctk.CTkButton(
            btn_box,
            text="Cancelar",
            width=100,
            fg_color=("gray70", "#32323f"),
            command=self.destroy
        )
        btn_no.pack(side="right", padx=(8, 0))

        def confirm_and_close():
            on_confirm()
            self.destroy()

        btn_yes = ctk.CTkButton(
            btn_box,
            text="Sim, excluir",
            width=110,
            fg_color="#cc3333",
            hover_color="#aa2222",
            command=confirm_and_close
        )
        btn_yes.pack(side="right")
