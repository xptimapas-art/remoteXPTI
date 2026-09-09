import sys
from pathlib import Path
import customtkinter as ctk
import tkinter as tk
from typing import List, Dict, Any, Optional, Tuple
import threading
import time
import shutil
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from storage import StorageManager
from rdp_manager import RDPManager
from preview_manager import PreviewManager
from dialogs import ServerDialog, ConfirmDialog, UpdateMenuDialog
from version import CURRENT_VERSION
from updater import SilentAutoUpdater
from uninstaller import Uninstaller

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CARD_WIDTH = 250
CARD_HEIGHT = 245
THUMB_WIDTH = 230
THUMB_HEIGHT = 130

class ServerCard(ctk.CTkFrame):
    """Componente de Card individual limpo, compacto e minimalista estilo AnyDesk."""

    def __init__(
        self,
        parent,
        server: Dict[str, Any],
        on_connect,
        on_edit,
        initial_status: Optional[Tuple[bool, str]] = None
    ):
        super().__init__(
            parent,
            width=CARD_WIDTH,
            height=CARD_HEIGHT,
            corner_radius=10,
            fg_color=("#e6e8ec", "#1f2026"),
            border_width=1,
            border_color=("#d0d4dc", "#2c2d36")
        )
        self.server = server
        self.on_connect = on_connect
        self.on_edit = on_edit

        self.pack_propagate(False)
        self.grid_propagate(False)

        self._build_ui(initial_status)
        self._bind_events()

    def _build_ui(self, initial_status: Optional[Tuple[bool, str]]):
        # 1. Linha Superior: Status (Esquerda) e Engrenagem + Grupo (Direita)
        top_row = ctk.CTkFrame(self, fg_color="transparent", height=26)
        top_row.pack(fill="x", padx=10, pady=(8, 4))

        # Status inicial baseado no cache (não volta para 'Checando' se já conhecido)
        if initial_status is not None:
            is_online, _ = initial_status
            status_text = "🟢 Online" if is_online else "🔴 Offline"
            status_color = "#00cc66" if is_online else "#ff4d4d"
        else:
            status_text = "⚪ Checando..."
            status_color = "#888888"

        self.lbl_status = ctk.CTkLabel(
            top_row,
            text=status_text,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=status_color
        )
        self.lbl_status.pack(side="left")

        # Badge do Grupo (Pill)
        group_name = self.server.get("group", "Geral")
        lbl_group = ctk.CTkLabel(
            top_row,
            text=f" {group_name} ",
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color=("#cfd4de", "#2a2c36"),
            text_color=("gray20", "#b0b4c2"),
            corner_radius=4
        )
        lbl_group.pack(side="right")

        # Botão de Engrenagem (Único botão de configurações/edição)
        self.btn_edit = ctk.CTkButton(
            top_row,
            text="⚙️",
            width=26,
            height=24,
            fg_color=("#d6dae2", "#2e303b"),
            hover_color=("#c2c7d2", "#3a3c4a"),
            text_color=("gray10", "#ffffff"),
            font=ctk.CTkFont(size=11),
            command=lambda: self.on_edit(self.server)
        )
        self.btn_edit.pack(side="right", padx=(0, 6))

        # 2. Miniatura / Preview de Tela (16:9 ajustado)
        self.preview_container = ctk.CTkFrame(
            self,
            width=THUMB_WIDTH,
            height=THUMB_HEIGHT,
            corner_radius=6,
            fg_color=("#d2d6df", "#14151a"),
            cursor="hand2"
        )
        self.preview_container.pack(padx=10, pady=(0, 4))
        self.preview_container.pack_propagate(False)

        self.current_thumb_img = PreviewManager.get_thumbnail_ctk(
            self.server["id"],
            self.server.get("name", ""),
            self.server.get("host", ""),
            width=THUMB_WIDTH,
            height=THUMB_HEIGHT
        )
        self.lbl_preview = ctk.CTkLabel(
            self.preview_container,
            text="",
            image=self.current_thumb_img,
            cursor="hand2"
        )
        self.lbl_preview.pack(fill="both", expand=True)

        # 3. Informações do Servidor
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="x", padx=12, pady=(1, 6))

        # Nome em destaque
        name_text = self.server.get("name", "Servidor Sem Nome")
        if len(name_text) > 22:
            name_text = name_text[:20] + "..."
        self.lbl_name = ctk.CTkLabel(
            self.content_frame,
            text=name_text,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("gray10", "#ffffff"),
            anchor="w"
        )
        self.lbl_name.pack(fill="x")

        # IP e Porta
        host = self.server.get("host", "0.0.0.0")
        port = self.server.get("port", 3389)
        self.display_host = f"{host}:{port}" if port and port != 3389 else host
        self.lbl_host = ctk.CTkLabel(
            self.content_frame,
            text=f"🌐 {self.display_host}",
            font=ctk.CTkFont(size=11),
            text_color=("gray30", "#8e92a0"),
            anchor="w"
        )
        self.lbl_host.pack(fill="x")

        # Usuário
        user = self.server.get("username", "")
        display_user = f"👤 {user}" if user else "👤 (Padrão)"
        self.lbl_user = ctk.CTkLabel(
            self.content_frame,
            text=display_user,
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "#767986"),
            anchor="w"
        )
        self.lbl_user.pack(fill="x")

    def _bind_events(self):
        # Todo o card vira um botão de conexão (com cursor de mão e efeito hover sutil)
        clickable_widgets = [
            self,
            self.preview_container,
            self.lbl_preview,
            self.content_frame,
            self.lbl_name,
            self.lbl_host,
            self.lbl_user
        ]

        for w in clickable_widgets:
            w.configure(cursor="hand2")
            w.bind("<Button-1>", lambda e: self.on_connect(self.server))
            w.bind("<Enter>", lambda e: self._set_hover(True))
            w.bind("<Leave>", lambda e: self._set_hover(False))

    def _set_hover(self, is_hover: bool):
        if is_hover:
            self.configure(border_color="#0066cc", fg_color=("#dfe4ec", "#262832"))
        else:
            self.configure(border_color=("#d0d4dc", "#2c2d36"), fg_color=("#e6e8ec", "#1f2026"))

    def update_status(self, is_online: bool, message: str = ""):
        """Atualiza o status sem piscar ou resetar."""
        if is_online:
            self.lbl_status.configure(text="🟢 Online", text_color="#00cc66")
        else:
            self.lbl_status.configure(text="🔴 Offline", text_color="#ff4d4d")

    def reload_thumbnail(self):
        """Atualiza a imagem do preview na tela."""
        self.current_thumb_img = PreviewManager.get_thumbnail_ctk(
            self.server["id"],
            self.server.get("name", ""),
            self.server.get("host", ""),
            width=THUMB_WIDTH,
            height=THUMB_HEIGHT
        )
        self.lbl_preview.configure(image=self.current_thumb_img)


def get_resource_path(relative_path: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / relative_path
        if p.exists():
            return p
    if getattr(sys, "frozen", False):
        p = Path(sys.executable).parent / relative_path
        if p.exists():
            return p
    return Path(__file__).parent.resolve() / relative_path

class RemoteXPTIApp(ctk.CTk):
    """Janela principal da aplicação RemoteXPTI."""

    def __init__(self):
        super().__init__()

        self.title("RemoteXPTI - RDP Quick Launcher")
        self.geometry("1100x720")
        self.minsize(700, 480)

        # Ícone oficial da janela e barra de tarefas / bandeja
        icon_path = get_resource_path("imagens/icon.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        icon_png_path = get_resource_path("imagens/app_icon.png")
        if icon_png_path.exists():
            try:
                self._app_icon_photo = tk.PhotoImage(file=str(icon_png_path))
                self.wm_iconphoto(True, self._app_icon_photo)
            except Exception:
                pass

        self.storage = StorageManager()
        self.card_widgets: Dict[str, ServerCard] = {}
        
        # Cache persistente do status para NUNCA piscar 'Checando' desnecessariamente
        self.server_status: Dict[str, Tuple[bool, str]] = {}
        
        self.last_cols = 4
        self._resize_timer = None
        self._auto_ping_timer = None
        self._search_debounce_timer = None
        self._status_executor = ThreadPoolExecutor(max_workers=10)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_header()
        self._build_main_view()
        self._build_statusbar()

        self.refresh_servers()
        
        # Inicia a checagem inicial de status
        self.start_status_checker(is_manual=False)
        self._schedule_periodic_ping()
        
        # Sistema de atualização silenciosa em background (estilo Antigravity)
        self.updater = SilentAutoUpdater(
            on_ready_callback=self._on_update_ready,
            on_status_callback=self._on_update_status
        )
        self.after(3500, self.updater.start_background_check)

        self.bind("<Configure>", self._on_window_configure)

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, height=64, corner_radius=0, fg_color=("#f0f2f5", "#16171d"))
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)

        # Título e Logo Oficial XPti
        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=16, pady=8)

        logo_path = get_resource_path("imagens/XPti_negativo_color.png")
        if logo_path.exists():
            try:
                pil_logo = Image.open(logo_path)
                self.logo_header_img = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(92, 38))
                lbl_logo = ctk.CTkLabel(title_box, image=self.logo_header_img, text="")
                lbl_logo.pack(side="left", padx=(0, 10))
            except Exception as e:
                print(f"[Aviso] Falha ao carregar logo: {e}")

        text_box = ctk.CTkFrame(title_box, fg_color="transparent")
        text_box.pack(side="left")

        lbl_app_name = ctk.CTkLabel(
            text_box,
            text="RemoteXPTI",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=("gray10", "#ffffff")
        )
        lbl_app_name.pack(anchor="w")

        lbl_app_sub = ctk.CTkLabel(
            text_box,
            text="RDP Quick Launcher",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "#8e92a0")
        )
        lbl_app_sub.pack(anchor="w")

        # Ações do Topo: Busca, Filtro de Grupo, Botões
        actions_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        actions_box.pack(side="right", padx=16, pady=10)

        # Campo de Busca
        self.entry_search = ctk.CTkEntry(
            actions_box,
            placeholder_text="🔍 Buscar servidor, IP ou grupo...",
            width=230,
            height=34
        )
        self.entry_search.pack(side="left", padx=(0, 8))
        self.entry_search.bind("<KeyRelease>", self._on_search_keypress)

        # Filtro de Grupos
        self.combo_filter_group = ctk.CTkComboBox(
            actions_box,
            values=["Todos os Grupos"],
            width=140,
            height=34,
            command=lambda val: self.filter_servers()
        )
        self.combo_filter_group.set("Todos os Grupos")
        self.combo_filter_group.pack(side="left", padx=(0, 8))

        # Botão Atualizar Status Manual
        self.btn_refresh = ctk.CTkButton(
            actions_box,
            text="🔄",
            width=36,
            height=34,
            fg_color=("#dce0e8", "#262832"),
            text_color=("gray10", "#ffffff"),
            hover_color=("#ccd2dc", "#343644"),
            command=self._on_manual_refresh
        )
        self.btn_refresh.pack(side="left", padx=(0, 8))

        # Botão + Novo Servidor
        self.btn_add = ctk.CTkButton(
            actions_box,
            text="+ Novo Servidor",
            height=34,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.open_add_dialog
        )
        self.btn_add.pack(side="left")

    def _build_main_view(self):
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=12, pady=10)

        self.empty_label = ctk.CTkLabel(
            self.scroll_frame,
            text="Nenhum servidor cadastrado.\nClique no botão '+ Novo Servidor' acima para começar.",
            font=ctk.CTkFont(size=14),
            text_color=("gray40", "#767986"),
            justify="center"
        )

    def _build_statusbar(self):
        self.status_bar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color=("#eaecef", "#121318"))
        self.status_bar.pack(fill="x", side="bottom")
        self.status_bar.pack_propagate(False)

        self.lbl_status_msg = ctk.CTkLabel(
            self.status_bar,
            text="Pronto.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "#8e92a0")
        )
        self.lbl_status_msg.pack(side="left", padx=16)

        self.lbl_server_count = ctk.CTkLabel(
            self.status_bar,
            text="0 servidores",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "#8e92a0")
        )
        self.lbl_server_count.pack(side="right", padx=(0, 16))

        # Indicador de versão discreto no rodapé (clique abre menu de atualização e opções)
        self.lbl_version_btn = ctk.CTkButton(
            self.status_bar,
            text=f"v{CURRENT_VERSION}",
            height=22,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="transparent",
            hover_color=("#d6dae4", "#20232e"),
            text_color=("gray35", "#8e92a0"),
            command=self.open_version_menu
        )
        self.lbl_version_btn.pack(side="right", padx=(0, 12))

    def open_version_menu(self):
        """Abre o menu discreto de opções e atualizações ao clicar na versão."""
        UpdateMenuDialog(
            self,
            CURRENT_VERSION,
            self.check_for_updates_manual,
            self.confirm_uninstall_app
        )

    def check_for_updates_manual(self):
        self.set_message("🔍 Verificando atualizações no GitHub...")
        if hasattr(self, "updater") and self.updater:
            self.updater.start_background_check(is_manual=True)

    def _on_update_status(self, message: str):
        def show():
            self.set_message(message, duration_sec=7)
        self.after(0, show)

    def _on_update_ready(self, new_version: str):
        """Chamado quando o update terminou de baixar: muda discretamente o botão de versão para Restart."""
        def show():
            self.lbl_version_btn.configure(
                text=f"🔄 Restart para Atualizar (v{new_version})",
                fg_color="#0066cc",
                hover_color="#0052a3",
                text_color="#ffffff",
                command=self.updater.apply_update_and_restart
            )
            self.set_message(f"🚀 Versão {new_version} pronta! Clique em 'Restart para Atualizar' abaixo.", duration_sec=10)
        self.after(0, show)

    def _on_window_configure(self, event):
        if event.widget != self:
            return
        if self._resize_timer:
            self.after_cancel(self._resize_timer)
        self._resize_timer = self.after(150, self._check_column_recalculation)

    def _check_column_recalculation(self):
        w = self.scroll_frame.winfo_width()
        if w <= 200:
            w = self.winfo_width()
        if w <= 200:
            return

        slot_w = CARD_WIDTH + 14
        available_w = max(280, w - 24)
        new_cols = max(1, available_w // slot_w)

        # Reorganiza os cards apenas se o número de colunas mudou de fato
        if new_cols != self.last_cols:
            self.last_cols = new_cols
            self.filter_servers()

    def set_message(self, text: str, duration_sec: int = 5):
        self.lbl_status_msg.configure(text=text)
        if duration_sec > 0:
            self.after(duration_sec * 1000, lambda: self.lbl_status_msg.configure(text="Pronto."))

    def _on_search_keypress(self, event=None):
        """Aplica debounce de 90ms para digitação fluida sem engasgos na interface."""
        if self._search_debounce_timer:
            self.after_cancel(self._search_debounce_timer)
        self._search_debounce_timer = self.after(90, self.filter_servers)

    def _on_close(self):
        """Encerra a aplicação de forma limpa, finalizando o pool de threads em segundo plano."""
        try:
            if hasattr(self, "_status_executor"):
                self._status_executor.shutdown(wait=False)
        except Exception:
            pass
        self.destroy()

    def refresh_servers(self):
        self.storage.load()
        groups = ["Todos os Grupos"] + self.storage.get_groups()
        self.combo_filter_group.configure(values=groups)

        # Remove cards de servidores que não existem mais
        current_ids = {s["id"] for s in self.storage.servers}
        for s_id in list(self.card_widgets.keys()):
            if s_id not in current_ids:
                self.card_widgets[s_id].destroy()
                del self.card_widgets[s_id]

        self.filter_servers()

    def filter_servers(self):
        query = self.entry_search.get().strip().lower()
        selected_group = self.combo_filter_group.get()

        filtered = []
        for s in self.storage.servers:
            name_match = query in s.get("name", "").lower()
            host_match = query in s.get("host", "").lower()
            grp_match = query in s.get("group", "").lower()

            if query and not (name_match or host_match or grp_match):
                continue

            if selected_group != "Todos os Grupos" and s.get("group", "Geral") != selected_group:
                continue

            filtered.append(s)

        self._render_cards(filtered)

    def _render_cards(self, servers: List[Dict[str, Any]]):
        count = len(servers)
        self.lbl_server_count.configure(text=f"{count} {'servidor' if count == 1 else 'servidores'}")

        if not servers:
            for card in self.card_widgets.values():
                card.grid_forget()
            self.empty_label.pack(pady=60)
            return
        else:
            self.empty_label.pack_forget()

        w = self.scroll_frame.winfo_width()
        if w <= 200:
            w = self.winfo_width()
        if w <= 200:
            w = 1100

        slot_w = CARD_WIDTH + 14
        available_w = max(280, w - 24)
        cols = max(1, available_w // slot_w)
        self.last_cols = cols

        for i in range(25):
            self.scroll_frame.grid_columnconfigure(i, weight=0, minsize=0)

        for i in range(cols):
            self.scroll_frame.grid_columnconfigure(i, weight=0, minsize=slot_w)

        visible_ids = {s["id"] for s in servers}

        # 1. Oculta instantaneamente com grid_forget (sem destruir widgets!)
        for s_id, card in self.card_widgets.items():
            if s_id not in visible_ids:
                card.grid_forget()

        # 2. Reutiliza cards já criados em cache (0ms) ou instancia se for novo
        for index, server in enumerate(servers):
            s_id = server["id"]
            row = index // cols
            col = index % cols

            if s_id in self.card_widgets:
                card = self.card_widgets[s_id]
            else:
                cached_status = self.server_status.get(s_id)
                card = ServerCard(
                    self.scroll_frame,
                    server=server,
                    on_connect=self.connect_to_server,
                    on_edit=self.open_edit_dialog,
                    initial_status=cached_status
                )
                self.card_widgets[s_id] = card

            card.grid(row=row, column=col, padx=7, pady=7, sticky="nw")

    def connect_to_server(self, server: Dict[str, Any]):
        server_id = server["id"]
        full_server = self.storage.get_server(server_id)
        if not full_server:
            full_server = server

        host = full_server.get("host", "")
        port = int(full_server.get("port", 3389))
        user = full_server.get("username", "")
        password = full_server.get("password_plain", "")
        fullscreen = full_server.get("fullscreen", True)
        admin_mode = full_server.get("admin_mode", False)
        multimon = full_server.get("multimon", False)

        self.set_message(f"Injetando credenciais e conectando a {host}...")

        def launch_thread():
            ok, msg = RDPManager.launch_rdp(
                host=host,
                port=port,
                username=user,
                password=password,
                fullscreen=fullscreen,
                admin_mode=admin_mode,
                multimon=multimon
            )
            def on_done():
                if ok:
                    self.set_message(f"Conectado a {host}! Aguardando tela remota...")
                    self.storage.record_connection(server_id)

                    def on_captured(s_id):
                        self.after(0, lambda: self._update_card_preview(s_id))

                    threading.Thread(
                        target=PreviewManager.auto_capture_after_launch,
                        args=(server_id, host, 6.0, on_captured),
                        daemon=True
                    ).start()
                else:
                    self.set_message(f"Erro ao conectar: {msg}", duration_sec=8)
            self.after(0, on_done)

        threading.Thread(target=launch_thread, daemon=True).start()

    def _update_card_preview(self, server_id: str):
        if server_id in self.card_widgets:
            self.card_widgets[server_id].reload_thumbnail()

    def start_status_checker(self, is_manual: bool = False):
        """
        Verifica a conectividade silenciosamente em background.
        NUNCA reseta os badges para 'Checando...' durante a verificação.
        """
        if is_manual:
            self.set_message("Verificando status dos servidores...")

        def check_worker(server_id: str, host: str, port: int):
            is_online, msg = RDPManager.check_connection(host, port, timeout=1.5)
            # Salva no cache
            self.server_status[server_id] = (is_online, msg)
            
            # Atualiza o card suavemente apenas quando o resultado chegar
            def update_card():
                if server_id in self.card_widgets:
                    self.card_widgets[server_id].update_status(is_online, msg)
            self.after(0, update_card)

        if not hasattr(self, "_status_executor") or self._status_executor._shutdown:
            self._status_executor = ThreadPoolExecutor(max_workers=10)

        for server in self.storage.servers:
            s_id = server["id"]
            s_host = server.get("host", "")
            s_port = int(server.get("port", 3389))
            if s_host:
                self._status_executor.submit(check_worker, s_id, s_host, s_port)

    def _on_manual_refresh(self):
        self.start_status_checker(is_manual=True)
        if hasattr(self, "updater") and self.updater:
            self.updater.start_background_check()

    def _schedule_periodic_ping(self):
        """Verifica os servidores e checa atualizações em segundo plano."""
        self.start_status_checker(is_manual=False)
        # Também checa atualizações silenciosamente a cada ciclo
        if hasattr(self, "updater") and self.updater:
            self.updater.start_background_check()
        self._auto_ping_timer = self.after(45000, self._schedule_periodic_ping)

    def open_add_dialog(self):
        def on_save(data):
            new_s = self.storage.add_server(data)
            server_id = new_s["id"]
            if data.get("custom_image"):
                try:
                    img = Image.open(data["custom_image"])
                    img.convert("RGB").save(PreviewManager.get_thumbnail_path(server_id), "PNG")
                except Exception as e:
                    print(f"Erro ao salvar imagem customizada: {e}")
            elif data.get("reset_thumb"):
                tpath = PreviewManager.get_thumbnail_path(server_id)
                if tpath.exists():
                    tpath.unlink()

            self.refresh_servers()
            self.set_message(f"Servidor '{new_s['name']}' adicionado com sucesso!")
            self.start_status_checker(is_manual=False)

        ServerDialog(
            parent=self,
            existing_groups=self.storage.get_groups(),
            on_save=on_save
        )

    def open_edit_dialog(self, server: Dict[str, Any]):
        full_server = self.storage.get_server(server["id"])
        if not full_server:
            full_server = server

        def on_save(data):
            self.storage.update_server(server["id"], data)
            server_id = server["id"]
            PreviewManager.invalidate_cache(server_id)
            if data.get("custom_image"):
                try:
                    img = Image.open(data["custom_image"])
                    img.convert("RGB").save(PreviewManager.get_thumbnail_path(server_id), "PNG")
                except Exception as e:
                    print(f"Erro ao salvar imagem customizada: {e}")
            elif data.get("reset_thumb"):
                tpath = PreviewManager.get_thumbnail_path(server_id)
                if tpath.exists():
                    tpath.unlink()

            # Destrói apenas o card deste servidor para recriação com novos dados
            if server_id in self.card_widgets:
                self.card_widgets[server_id].destroy()
                del self.card_widgets[server_id]

            self.refresh_servers()
            self.set_message(f"Servidor '{data['name']}' atualizado com sucesso!")
            self.start_status_checker(is_manual=False)

        def on_delete():
            self.confirm_delete_server(server)

        ServerDialog(
            parent=self,
            server_data=full_server,
            existing_groups=self.storage.get_groups(),
            on_save=on_save,
            on_delete=on_delete
        )

    def confirm_delete_server(self, server: Dict[str, Any]):
        name = server.get("name", "este servidor")
        def do_delete():
            server_id = server["id"]
            self.storage.delete_server(server_id)
            PreviewManager.invalidate_cache(server_id)
            thumb_path = PreviewManager.get_thumbnail_path(server_id)
            if thumb_path.exists():
                try:
                    thumb_path.unlink()
                except Exception:
                    pass
            # Remove do cache de status
            self.server_status.pop(server_id, None)
            
            # Destrói o card da interface
            if server_id in self.card_widgets:
                self.card_widgets[server_id].destroy()
                del self.card_widgets[server_id]
                
            self.refresh_servers()
            self.set_message(f"Servidor '{name}' excluído com sucesso.")

        ConfirmDialog(
            parent=self,
            title="Excluir Servidor",
            message=f"Tem certeza que deseja excluir '{name}'?\nEsta ação não pode ser desfeita.",
            on_confirm=do_delete
        )

    def confirm_uninstall_app(self):
        """Abre modal de confirmação para desinstalar o RemoteXPTI por completo."""
        message = (
            "Deseja desinstalar o RemoteXPTI por completo do computador?\n\n"
            "⚠️ Esta ação irá:\n"
            "• Remover o aplicativo e todos os arquivos instalados\n"
            "• Apagar os atalhos da Área de Trabalho e Menu Iniciar\n"
            "• Limpar todas as credenciais salvas no Windows (TERMSRV)\n"
            "• Excluir os perfis temporários de conexão RDP"
        )

        def do_uninstall():
            self.set_message("Desinstalando RemoteXPTI e limpando credenciais...")
            Uninstaller.execute_complete_uninstallation()

        ConfirmDialog(
            parent=self,
            title="Desinstalação Completa do RemoteXPTI",
            message=message,
            confirm_text="Sim, Desinstalar Tudo",
            confirm_color="#cc0000",
            height=240,
            on_confirm=do_uninstall
        )


if __name__ == "__main__":
    app = RemoteXPTIApp()
    app.mainloop()
