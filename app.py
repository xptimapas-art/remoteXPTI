import os
import sys
import ctypes
import subprocess
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
from dialogs import ServerDialog, ConfirmDialog, SettingsDialog, UninstallProgressDialog
from version import CURRENT_VERSION
from updater import SilentAutoUpdater
from uninstaller import Uninstaller
import math
from tkintermapview import TkinterMapView
from map_manager import (
    resolve_server_coordinates,
    DEFAULT_MAP_CENTER,
    DEFAULT_MAP_ZOOM,
    TILE_SERVERS,
    get_map_cache_path
)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CARD_WIDTH = 276
CARD_HEIGHT = 180

class ServerCard(ctk.CTkFrame):
    """Componente de Card 100% no padrão visual e interativo do AnyDesk."""

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
            corner_radius=4,
            fg_color="#181a20",
            border_width=0,
            cursor="hand2"
        )
        self.server = server
        self.on_connect = on_connect
        self.on_edit = on_edit
        self.is_online = initial_status[0] if initial_status is not None else None
        self.is_fav = bool(server.get("favorite", False))
        self._is_hovering = False

        self.pack_propagate(False)
        self.grid_propagate(False)

        self._build_ui()
        self._bind_events()

    def _load_images(self):
        """Pré-carrega as imagens normal e hover para transição instantânea a 0ms."""
        self.img_normal = PreviewManager.get_card_ctk(
            server_id=self.server["id"],
            name=self.server.get("name", "Servidor"),
            host=self.server.get("host", "0.0.0.0"),
            is_online=self.is_online,
            width=CARD_WIDTH,
            height=CARD_HEIGHT,
            is_fav=self.is_fav,
            is_hover=False
        )
        self.img_hover = PreviewManager.get_card_ctk(
            server_id=self.server["id"],
            name=self.server.get("name", "Servidor"),
            host=self.server.get("host", "0.0.0.0"),
            is_online=self.is_online,
            width=CARD_WIDTH,
            height=CARD_HEIGHT,
            is_fav=self.is_fav,
            is_hover=True
        )

    def _build_ui(self):
        # Imagem de fundo completa estilo AnyDesk (renderiza 100% dos ícones e textos sem caixas pretas)
        self._load_images()
        self.lbl_card = ctk.CTkLabel(
            self,
            text="",
            image=self.img_normal,
            width=CARD_WIDTH,
            height=CARD_HEIGHT,
            cursor="hand2"
        )
        self.lbl_card.place(x=0, y=0)

    def _bind_events(self):
        clickable = [self, self.lbl_card]
        for w in clickable:
            w.bind("<Button-1>", self._on_card_click)
            w.bind("<Button-3>", lambda e: self.on_edit(self.server))
            w.bind("<Enter>", lambda e: self._set_hover(True))
            w.bind("<Leave>", lambda e: self._set_hover(False))

    def _on_card_click(self, event):
        x = event.x
        y = event.y

        w = self.lbl_card.winfo_width()
        h = self.lbl_card.winfo_height()
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        hit_w = int(48 * scale)
        hit_h = int(48 * scale)

        # Canto Superior Direito: Estrela de favoritos (área adaptativa ao DPI)
        if x >= w - hit_w and y <= hit_h:
            self._toggle_favorite()
            return

        # Canto Inferior Direito: 3 pontos de edição/opções (área adaptativa ao DPI)
        if x >= w - hit_w and y >= h - hit_h:
            self.on_edit(self.server)
            return

        # Clique no restante do card: Conexão direta RDP
        self.on_connect(self.server)

    def _set_hover(self, is_hover: bool):
        self._is_hovering = is_hover
        self.lbl_card.configure(image=self.img_hover if is_hover else self.img_normal)

    def _toggle_favorite(self):
        self.is_fav = not self.is_fav
        self.server["favorite"] = self.is_fav
        top = self.winfo_toplevel()
        if hasattr(top, "storage"):
            top.storage.update_server(self.server["id"], {"favorite": self.is_fav})
        self.reload_thumbnail()

    def update_status(self, is_online: bool, message: str = ""):
        """Atualiza o status sem piscar ou resetar."""
        self.is_online = is_online
        self.reload_thumbnail()

    def reload_thumbnail(self):
        """Atualiza a imagem do card na tela mantendo o estado de hover se ativo."""
        self._load_images()
        self.lbl_card.configure(image=self.img_hover if self._is_hovering else self.img_normal)


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

def sync_windows_shortcuts_icon():
    """
    Garante que os atalhos existentes na Área de Trabalho e Menu Iniciar
    usem o ícone oficial moderno (squircle escuro arredondado com o X estilizado),
    notificando o Windows Shell para atualizar a exibição imediatamente.
    """
    if sys.platform != "win32":
        return

    try:
        current_exe = Path(sys.executable).resolve()
        app_dir = current_exe.parent
        icon_file = app_dir / "imagens" / "app_icon.ico"
        if not icon_file.exists():
            icon_file = app_dir / "imagens" / "icon.ico"
        if not icon_file.exists():
            icon_file = current_exe

        userprofile = Path(os.environ.get("USERPROFILE", str(Path.home())))
        appdata = Path(os.environ.get("APPDATA", ""))

        candidates = [
            userprofile / "Desktop" / "RemoteXPTI.lnk",
            userprofile / "OneDrive" / "Desktop" / "RemoteXPTI.lnk",
            userprofile / "OneDrive" / "Área de Trabalho" / "RemoteXPTI.lnk",
            userprofile / "Área de Trabalho" / "RemoteXPTI.lnk",
            appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "RemoteXPTI.lnk"
        ]

        found_any = False
        ps_lines = ["$w = New-Object -ComObject WScript.Shell"]
        for sc in candidates:
            if sc.exists():
                found_any = True
                ps_lines.append(f"""
                $s = $w.CreateShortcut('{str(sc)}')
                $s.TargetPath = '{str(current_exe)}'
                $s.WorkingDirectory = '{str(app_dir)}'
                $s.IconLocation = '{str(icon_file)},0'
                $s.Save()
                """)

        if found_any:
            ps_script = "\n".join(ps_lines)
            creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True,
                creationflags=creation_flags
            )
            # Notifica o Explorer para recarregar o cache de ícones
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        pass


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

        # Sincroniza atalhos da Área de Trabalho e Menu Iniciar com o novo ícone oficial
        threading.Thread(target=sync_windows_shortcuts_icon, daemon=True).start()

        self.storage = StorageManager()
        self.card_widgets: Dict[str, ServerCard] = {}
        
        # Cache persistente do status para NUNCA piscar 'Checando' desnecessariamente
        self.server_status: Dict[str, Tuple[bool, str]] = {}
        self.view_mode = "grade"
        self.map_markers: Dict[str, Any] = {}
        self.current_selected_marker_server: Optional[Dict[str, Any]] = None
        
        self.last_cols = -1
        self._resize_timer = None
        self._auto_ping_timer = None
        self._search_debounce_timer = None
        self._is_checking_status = False
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

        self.bind("<Configure>", self._on_window_configure, add="+")
        self.after(50, self._check_column_recalculation)
        self.after(150, self._check_column_recalculation)
        self.after(350, self._check_column_recalculation)

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
            width=135,
            height=34,
            command=lambda val: self.filter_servers()
        )
        self.combo_filter_group.set("Todos os Grupos")
        self.combo_filter_group.pack(side="left", padx=(0, 8))

        # Alternador de Modo de Exibição (Grade AnyDesk / Mapa Interativo)
        self.seg_view = ctk.CTkSegmentedButton(
            actions_box,
            values=["⊞ Grade", "🗺️ Mapa"],
            height=34,
            selected_color="#0066cc",
            selected_hover_color="#0052a3",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_view_mode_changed
        )
        self.seg_view.set("⊞ Grade")
        self.seg_view.pack(side="left", padx=(0, 8))

        # Botão Atualizar Status Manual
        self.btn_refresh = ctk.CTkButton(
            actions_box,
            text="🔄",
            width=36,
            height=34,
            fg_color=("#dce0e8", "#262832"),
            text_color=("gray10", "#ffffff"),
            hover_color=("#ccd2dc", "#343644"),
            font=ctk.CTkFont(family="Segoe UI Emoji", size=13),
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

        # Botão Engrenagem de Configurações Gerais
        self.btn_settings = ctk.CTkButton(
            actions_box,
            text="⚙️",
            width=36,
            height=34,
            fg_color=("#dce0e8", "#262832"),
            text_color=("gray10", "#ffffff"),
            hover_color=("#ccd2dc", "#343644"),
            font=ctk.CTkFont(family="Segoe UI Emoji", size=14),
            command=self.open_settings_dialog
        )
        self.btn_settings.pack(side="left", padx=(8, 0))

    def _build_main_view(self):
        # 1. Modo Grade (AnyDesk Cards)
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=12, pady=10)
        self.scroll_frame.bind("<Configure>", self._on_scroll_frame_configure, add="+")

        self.empty_label = ctk.CTkLabel(
            self.scroll_frame,
            text="Nenhum servidor cadastrado.\nClique no botão '+ Novo Servidor' acima para começar.",
            font=ctk.CTkFont(size=14),
            text_color=("gray40", "#767986"),
            justify="center"
        )

        # 2. Modo Mapa Interativo
        self.map_container = ctk.CTkFrame(self, fg_color="#181a20", corner_radius=8)

        # Mini toolbar superior do mapa
        self.map_toolbar = ctk.CTkFrame(self.map_container, height=44, fg_color="#20222a", corner_radius=6)
        self.map_toolbar.pack(fill="x", padx=8, pady=(8, 4))
        self.map_toolbar.pack_propagate(False)

        self.lbl_map_title = ctk.CTkLabel(
            self.map_toolbar,
            text="🗺️ Mapa de Acessos",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#ffffff"
        )
        self.lbl_map_title.pack(side="left", padx=12)

        self.lbl_map_info = ctk.CTkLabel(
            self.map_toolbar,
            text="Clique em um marcador para ver detalhes e conectar",
            font=ctk.CTkFont(size=11),
            text_color="#8e92a0"
        )
        self.lbl_map_info.pack(side="left", padx=6)

        # Botão Centralizar SC
        self.btn_center_sc = ctk.CTkButton(
            self.map_toolbar,
            text="📍 Centralizar SC",
            width=115,
            height=28,
            fg_color="#2c303c",
            hover_color="#3a3f4e",
            font=ctk.CTkFont(size=11),
            command=self._center_map_sc
        )
        self.btn_center_sc.pack(side="right", padx=(4, 10))

        # Seletor de Camadas (Tiles)
        self.combo_map_layer = ctk.CTkComboBox(
            self.map_toolbar,
            values=list(TILE_SERVERS.keys()),
            width=175,
            height=28,
            font=ctk.CTkFont(size=11),
            dropdown_font=ctk.CTkFont(size=11),
            command=self._on_tile_server_changed
        )
        self.combo_map_layer.set("CartoDB Dark (Padrão)")
        self.combo_map_layer.pack(side="right", padx=(4, 6))

        ctk.CTkLabel(
            self.map_toolbar,
            text="Camada:",
            font=ctk.CTkFont(size=11),
            text_color="#8e92a0"
        ).pack(side="right", padx=(6, 2))

        # Widget TkinterMapView
        self.map_widget = TkinterMapView(
            self.map_container,
            corner_radius=8,
            database_path=str(get_map_cache_path())
        )
        self.map_widget.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.map_widget.set_tile_server(TILE_SERVERS["CartoDB Dark (Padrão)"], max_zoom=19)
        self.map_widget.set_position(DEFAULT_MAP_CENTER[0], DEFAULT_MAP_CENTER[1])
        self.map_widget.set_zoom(DEFAULT_MAP_ZOOM)

        # Card Flutuante de Detalhes do Servidor selecionado no mapa
        self.map_card = ctk.CTkFrame(
            self.map_container,
            height=90,
            fg_color="#1a1d24",
            border_color="#303542",
            border_width=1,
            corner_radius=10
        )
        self.map_card.pack_propagate(False)

        card_top = ctk.CTkFrame(self.map_card, fg_color="transparent")
        card_top.pack(fill="x", padx=14, pady=(8, 2))

        self.map_card_name = ctk.CTkLabel(
            card_top,
            text="Nome do Servidor",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ffffff"
        )
        self.map_card_name.pack(side="left")

        self.map_card_status = ctk.CTkLabel(
            card_top,
            text="🟢 Online",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#2ebd59"
        )
        self.map_card_status.pack(side="left", padx=10)

        btn_close_card = ctk.CTkButton(
            card_top,
            text="✕",
            width=24,
            height=24,
            fg_color="transparent",
            hover_color="#343846",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#8e92a0",
            command=self._hide_map_card
        )
        btn_close_card.pack(side="right")

        card_bottom = ctk.CTkFrame(self.map_card, fg_color="transparent")
        card_bottom.pack(fill="x", padx=14, pady=(2, 8))

        self.map_card_details = ctk.CTkLabel(
            card_bottom,
            text="🌐 10.0.0.1:3389   |   📁 Geral   |   👤 Padrão",
            font=ctk.CTkFont(size=12),
            text_color="#a0a5b5"
        )
        self.map_card_details.pack(side="left", pady=4)

        self.map_card_btn_connect = ctk.CTkButton(
            card_bottom,
            text="🚀 Conectar Agora (RDP)",
            height=32,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._connect_selected_map_server
        )
        self.map_card_btn_connect.pack(side="right", padx=(8, 0))

        self.map_card_btn_edit = ctk.CTkButton(
            card_bottom,
            text="⚙️ Editar",
            width=80,
            height=32,
            fg_color="#2c303c",
            hover_color="#3a3f4e",
            font=ctk.CTkFont(size=12),
            command=self._edit_selected_map_server
        )
        self.map_card_btn_edit.pack(side="right")

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

        # Indicador de versão discreto no rodapé (clique abre configurações/atualizações)
        self.lbl_version_btn = ctk.CTkButton(
            self.status_bar,
            text=f"v{CURRENT_VERSION}",
            height=22,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="transparent",
            hover_color=("#d6dae4", "#20232e"),
            text_color=("gray35", "#8e92a0"),
            command=self.open_settings_dialog
        )
        self.lbl_version_btn.pack(side="right", padx=(0, 12))

    def open_settings_dialog(self):
        """Abre a janela modal de configurações e preferências do sistema."""
        SettingsDialog(
            parent=self,
            current_version=CURRENT_VERSION,
            on_check_updates=self.check_for_updates_manual,
            on_clean_thumbnails=self._clean_thumbnails_cache,
            on_clean_credentials=self._clean_credentials_manual,
            on_uninstall=self.confirm_uninstall_app
        )

    def open_version_menu(self):
        self.open_settings_dialog()

    def _clean_thumbnails_cache(self):
        PreviewManager.invalidate_cache()
        t_dir = PreviewManager.get_thumbnail_path("dummy").parent
        if t_dir.exists():
            for f in t_dir.glob("*.png"):
                try:
                    f.unlink()
                except Exception:
                    pass
        self.refresh_servers()
        self.set_message("Cache de miniaturas limpo com sucesso!")

    def _clean_credentials_manual(self):
        Uninstaller.cleanup_windows_credentials()
        self.set_message("Credenciais do Windows (TERMSRV) limpas com sucesso!")

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
        if getattr(self, "_resize_timer", None):
            self.after_cancel(self._resize_timer)
        self._resize_timer = self.after(20, self._check_column_recalculation)

    def _on_scroll_frame_configure(self, event=None):
        if getattr(self, "_resize_timer", None):
            self.after_cancel(self._resize_timer)
        self._resize_timer = self.after(20, self._check_column_recalculation)

    def _calculate_columns(self) -> int:
        """
        Calcula o número de colunas ideal considerando o DPI Scaling do Windows.
        Garante que cards fiquem próximos, bem distribuídos e responsivos ao maximizar.
        """
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        slot_w_phys = (CARD_WIDTH + 8) * scale

        win_w = self.winfo_width()
        scroll_w = self.scroll_frame.winfo_width() if hasattr(self, "scroll_frame") else 0

        # Largura física real disponível para a grade de cards
        if win_w > 200:
            avail_w = win_w - (44 * scale)
        elif scroll_w > 200:
            avail_w = scroll_w - (24 * scale)
        else:
            avail_w = (1100 - 44) * scale

        if scroll_w > 200 and (scroll_w - 24) > avail_w:
            avail_w = scroll_w - 24

        return max(1, int(avail_w // slot_w_phys))

    def _check_column_recalculation(self):
        w = self.winfo_width()
        if w <= 200:
            return

        new_cols = self._calculate_columns()
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

    def _on_view_mode_changed(self, mode: str):
        if "Mapa" in mode:
            self.view_mode = "mapa"
            self.scroll_frame.pack_forget()
            self.map_container.pack(fill="both", expand=True, padx=12, pady=10)
            self.filter_servers()
        else:
            self.view_mode = "grade"
            self.map_container.pack_forget()
            self.scroll_frame.pack(fill="both", expand=True, padx=12, pady=10)
            self.filter_servers()

    def _center_map_sc(self):
        self.map_widget.set_position(DEFAULT_MAP_CENTER[0], DEFAULT_MAP_CENTER[1])
        self.map_widget.set_zoom(DEFAULT_MAP_ZOOM)

    def _on_tile_server_changed(self, choice: str):
        url = TILE_SERVERS.get(choice)
        if url:
            self.map_widget.set_tile_server(url, max_zoom=19)

    def _hide_map_card(self):
        self.current_selected_marker_server = None
        self.map_card.place_forget()

    def _on_marker_clicked(self, marker):
        server = getattr(marker, "data", None)
        if not server:
            return
        self.current_selected_marker_server = server
        self.map_card_name.configure(text=server.get("name", "Servidor"))

        host = server.get("host", "")
        port = server.get("port", 3389)
        group = server.get("group", "Geral")
        user = server.get("username", "") or "Padrão"

        self.map_card_details.configure(
            text=f"🌐 {host}:{port}   |   📁 {group}   |   👤 {user}"
        )

        status_info = self.server_status.get(server["id"])
        if status_info:
            is_online, _ = status_info
            if is_online:
                self.map_card_status.configure(text="🟢 Online", text_color="#2ebd59")
            else:
                self.map_card_status.configure(text="🔴 Offline", text_color="#f04438")
        else:
            self.map_card_status.configure(text="⚪ Verificando...", text_color="#94a3b8")

        self.map_card.place(relx=0.5, rely=0.96, anchor="s", relwidth=0.88)

    def _connect_selected_map_server(self):
        if self.current_selected_marker_server:
            self.connect_to_server(self.current_selected_marker_server)

    def _edit_selected_map_server(self):
        if self.current_selected_marker_server:
            self.open_edit_dialog(self.current_selected_marker_server)

    def _render_map_markers(self, servers: List[Dict[str, Any]]):
        # Limpa marcadores anteriores
        for marker in list(self.map_markers.values()):
            try:
                marker.delete()
            except Exception:
                pass
        self.map_markers.clear()
        self._hide_map_card()

        # Agrupa servidores com coordenadas idênticas para distribuir em pequeno raio
        coord_groups: Dict[Tuple[float, float], List[Dict[str, Any]]] = {}
        for s in servers:
            coords = resolve_server_coordinates(s)
            if coords:
                key = (round(coords[0], 4), round(coords[1], 4))
                coord_groups.setdefault(key, []).append(s)

        mapped_count = 0
        for (base_lat, base_lon), s_list in coord_groups.items():
            count = len(s_list)
            for i, server in enumerate(s_list):
                if count == 1:
                    lat, lon = base_lat, base_lon
                else:
                    angle = i * (2 * math.pi / count)
                    radius = 0.006  # Leve espaçamento (~600m) para não sobrepor marcadores
                    lat = base_lat + radius * math.cos(angle)
                    lon = base_lon + radius * math.sin(angle)

                status_info = self.server_status.get(server["id"])
                if status_info is not None:
                    circle_color = "#2ebd59" if status_info[0] else "#f04438"
                else:
                    circle_color = "#94a3b8"

                marker = self.map_widget.set_marker(
                    lat,
                    lon,
                    text=server.get("name", ""),
                    command=self._on_marker_clicked,
                    marker_color_circle=circle_color,
                    marker_color_outside="#181a20",
                    text_color="#ffffff",
                    data=server
                )
                self.map_markers[server["id"]] = marker
                mapped_count += 1

        self.lbl_server_count.configure(
            text=f"{mapped_count} {'servidor' if mapped_count == 1 else 'servidores'} no mapa"
        )
        self.lbl_map_info.configure(
            text=f"{mapped_count} servidores posicionados no mapa"
        )

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

        if self.view_mode == "grade":
            self._render_cards(filtered)
        else:
            self._render_map_markers(filtered)

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

        cols = self._calculate_columns()
        self.last_cols = cols

        # Limpa configurações de colunas anteriores
        for i in range(35):
            self.scroll_frame.grid_columnconfigure(i, weight=0, minsize=0)

        # Configura colunas ativas para expandir proporcionalmente e preencher toda a largura
        for i in range(cols):
            self.scroll_frame.grid_columnconfigure(i, weight=1, minsize=int(CARD_WIDTH + 10))

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

            card.grid(row=row, column=col, padx=5, pady=5)

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
        if getattr(self, "_is_checking_status", False):
            if is_manual:
                self.set_message("Verificação de status já em andamento...")
            return

        self._is_checking_status = True
        if is_manual:
            self.set_message("Verificando status dos servidores...")

        pending = [len(self.storage.servers)]

        def check_worker(server_id: str, host: str, port: int):
            try:
                is_online, msg = RDPManager.check_connection(host, port, timeout=1.5)
                # Salva no cache
                self.server_status[server_id] = (is_online, msg)
                
                # Atualiza o card, marcador do mapa e card flutuante suavemente apenas quando o resultado chegar
                def update_ui():
                    if server_id in self.card_widgets:
                        self.card_widgets[server_id].update_status(is_online, msg)
                    if server_id in self.map_markers:
                        m = self.map_markers[server_id]
                        m.marker_color_circle = "#2ebd59" if is_online else "#f04438"
                        try:
                            m.draw()
                        except Exception:
                            pass
                    if self.current_selected_marker_server and self.current_selected_marker_server.get("id") == server_id:
                        if is_online:
                            self.map_card_status.configure(text="🟢 Online", text_color="#2ebd59")
                        else:
                            self.map_card_status.configure(text="🔴 Offline", text_color="#f04438")
                self.after(0, update_ui)
            finally:
                pending[0] -= 1
                if pending[0] <= 0:
                    self._is_checking_status = False

        if not hasattr(self, "_status_executor") or self._status_executor._shutdown:
            self._status_executor = ThreadPoolExecutor(max_workers=10)

        servers_to_check = list(self.storage.servers)
        if not servers_to_check:
            self._is_checking_status = False
            return

        for server in servers_to_check:
            s_id = server["id"]
            s_host = server.get("host", "")
            s_port = int(server.get("port", 3389))
            if s_host:
                self._status_executor.submit(check_worker, s_id, s_host, s_port)
            else:
                pending[0] -= 1
                if pending[0] <= 0:
                    self._is_checking_status = False

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
            UninstallProgressDialog(self)

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
