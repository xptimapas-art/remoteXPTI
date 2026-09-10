import os
import sys
import json
import ctypes
import subprocess
import queue
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
from settings_drawer import SettingsDrawer
from version import CURRENT_VERSION
from updater import SilentAutoUpdater
from uninstaller import Uninstaller
from web_map_manager import WebMapManager
from logger import log
from config_manager import ConfigManager
from cloud_sync import CloudSyncManager
from splash_screen import SplashScreen, SplashProcessManager

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
        """Carrega a imagem normal imediatamente e deixa a imagem hover para sob demanda (0ms no startup)."""
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
        self.img_hover = None  # Carregamento sob demanda (lazy) ao passar o mouse

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
        if is_hover and self.img_hover is None:
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
        if getattr(sys, "frozen", False):
            current_exe = Path(sys.executable).resolve()
            app_dir = current_exe.parent
        else:
            # Em modo de desenvolvimento/testes, nunca aponte atalhos para python.exe
            local_installed = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "RemoteXPTI" / "RemoteXPTI.exe"
            if local_installed.exists():
                current_exe = local_installed
                app_dir = local_installed.parent
            else:
                return  # Não altera atalhos em modo dev sem app instalado

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

        import win32com.client
        w = win32com.client.Dispatch("WScript.Shell")
        for sc in candidates:
            if sc.exists():
                try:
                    s = w.CreateShortcut(str(sc))
                    s.TargetPath = str(current_exe)
                    s.WorkingDirectory = str(app_dir)
                    s.IconLocation = f"{str(icon_file)},0"
                    s.Save()
                except Exception:
                    pass
        # Notifica o Explorer para recarregar o cache de ícones
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        pass


class RemoteXPTIApp(ctk.CTk):
    """Janela principal da aplicação RemoteXPTI."""

    def __init__(self):
        super().__init__()

        # Oculta imediatamente a janela principal para exibir a tela de carregamento (Splash)
        # e evitar qualquer flickering, renderização parcial ou botões se alinhando na tela
        self.withdraw()

        self.title("RemoteXPTI - RDP Quick Launcher")
        self.geometry("1100x720")
        self.minsize(700, 480)

        # Centraliza a janela principal no monitor para quando for exibida
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            win_w, win_h = 1100, 720
            win_x = max(0, (sw - win_w) // 2)
            win_y = max(0, (sh - win_h) // 2)
            self.geometry(f"{win_w}x{win_h}+{win_x}+{win_y}")
        except Exception:
            pass

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

        # Inicia a Splash Screen em PROCESSO DEDICADO ISOLADO
        # A rotação dos arcos e o slider da barra de progresso NUNCA congelam, rodando a 60 FPS dedicados!
        self.splash_manager = SplashProcessManager(current_version=CURRENT_VERSION)
        self.splash_min_duration = 3.5  # Duração garantida de 3.5 segundos reais de animação visível
        self.splash_start_time = time.time()
        self._splash_closed = False
        self._warmup_done = False
        self._main_window_revealed = False

        log.info(f"[RemoteXPTI] Inicializando RemoteXPTIApp v{CURRENT_VERSION}...")

        self.storage = StorageManager()
        log.info(f"[RemoteXPTI] Servidores carregados do storage local: {len(self.storage.servers)}")
        self.card_widgets: Dict[str, ServerCard] = {}
        
        # Cache persistente do status para NUNCA piscar 'Checando' desnecessariamente
        self.server_status: Dict[str, Tuple[bool, str]] = {}
        # Rastreamento de tempo de inatividade (loss/offline) por servidor: server_id -> timestamp float
        self.server_downtime: Dict[str, float] = {}
        self._load_downtime_history()
        self.view_mode = "grade"
        self.filtered_servers: List[Dict[str, Any]] = list(self.storage.servers)
        self.web_map: Optional[WebMapManager] = None
        
        self.last_cols = -1
        self._resize_timer = None
        self._auto_ping_timer = None
        self._search_debounce_timer = None
        self._is_checking_status = False
        self._status_executor = ThreadPoolExecutor(max_workers=10)
        self._action_queue = queue.Queue()
        self._is_drawer_open = False
        self._drawer_anim_id = None
        self.settings_drawer = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_header()
        self._build_main_view()
        self._build_statusbar()
        self._process_action_queue()

        self.bind("<Configure>", self._on_window_configure, add="+")
        self.bind("<Escape>", lambda e: self.close_settings_drawer() if getattr(self, "_is_drawer_open", False) else None)

        # Inicia o warmup em estágios progressivos
        self.after(30, self._start_staged_warmup)

    def _start_staged_warmup(self):
        """Executa a inicialização em estágios para manter a animação orbital a 50 FPS sem nenhum travamento."""
        self.splash_manager.set_status("Carregando credenciais e dados locais...")
        threading.Thread(target=sync_windows_shortcuts_icon, daemon=True).start()
        
        # Etapa 2: Subsistema gráfico e mapa Edge
        self.after(150, self._warmup_step2_map)

    def _warmup_step2_map(self):
        if self._splash_closed:
            return
        self.splash_manager.set_status("Inicializando acelerador gráfico...")
        
        # Inicializa o mapa web Leaflet com aceleração de GPU
        try:
            self.web_map = WebMapManager(
                container_widget=self.map_container,
                get_servers_func=lambda: self.filtered_servers if self.filtered_servers is not None else self.storage.servers,
                get_status_func=lambda: self.server_status,
                get_incidents_func=self.get_active_incidents,
                on_connect_func=self.connect_to_server_by_id,
                on_edit_func=self.open_edit_dialog_by_id,
            )
            self.web_map.start()
        except Exception as e:
            log.warning(f"[RemoteXPTI] Falha ao iniciar WebMapManager: {e}")

        # Etapa 3: Organização de servidores e layout
        self.after(200, self._warmup_step3_layout)

    def _warmup_step3_layout(self):
        if self._splash_closed:
            return
        self.splash_manager.set_status("Organizando servidores e layout...")
        self.refresh_servers()
        self.update_idletasks()
        self._check_column_recalculation()

        # Etapa 4: Conexões de rede e checagem de atualizações
        self.after(150, self._warmup_step4_network)

    def _warmup_step4_network(self):
        if self._splash_closed:
            return
        self.splash_manager.set_status("Otimizando conexões de rede...")
        
        # Inicia a checagem inicial de status
        self.start_status_checker(is_manual=False)
        self._schedule_periodic_ping()
        
        # Sistema de atualização silenciosa em background (estilo Antigravity)
        self.updater = SilentAutoUpdater(
            on_ready_callback=self._on_update_ready,
            on_status_callback=self._on_update_status
        )
        self.after(3500, self.updater.start_background_check)

        # Sincronização em nuvem automática com Supabase se configurado
        if CloudSyncManager.is_configured():
            threading.Thread(target=self._sync_servers_from_cloud, daemon=True).start()

        self._warmup_done = True
        self.after(50, self._check_splash_ready)

    def _check_splash_ready(self):
        """Verifica se a aplicação concluiu seu warmup e se o tempo mínimo da animação decorreu."""
        if getattr(self, "_main_window_revealed", False):
            return
        elapsed = time.time() - self.splash_start_time
        if elapsed < self.splash_min_duration or not getattr(self, "_warmup_done", False):
            remaining_ms = max(40, int((self.splash_min_duration - elapsed) * 1000)) if elapsed < self.splash_min_duration else 50
            self.after(remaining_ms, self._check_splash_ready)
            return

        # Animação e carregamento completos: revela a janela principal e fecha a splash
        self._reveal_main_window()

    def _reveal_main_window(self):
        """Revela a janela principal perfeitamente montada, calculada e sem nenhum flickering."""
        if getattr(self, "_main_window_revealed", False):
            return
        self._main_window_revealed = True
        self.deiconify()
        self.lift()
        self.focus_force()
        self._check_column_recalculation()
        if hasattr(self, "splash_manager") and self.splash_manager:
            self.splash_manager.finish()
        log.info("[RemoteXPTI] Splash finalizada com sucesso. Janela principal revelada.")

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
        icon_grid_path = get_resource_path("imagens/icon_grid.png")
        icon_map_path = get_resource_path("imagens/icon_map.png")
        self.img_seg_grid = None
        self.img_seg_map = None
        if icon_grid_path.exists():
            try:
                pil_g = Image.open(icon_grid_path)
                self.img_seg_grid = ctk.CTkImage(light_image=pil_g, dark_image=pil_g, size=(16, 16))
            except Exception:
                pass
        if icon_map_path.exists():
            try:
                pil_m = Image.open(icon_map_path)
                self.img_seg_map = ctk.CTkImage(light_image=pil_m, dark_image=pil_m, size=(16, 16))
            except Exception:
                pass

        self.seg_view = ctk.CTkSegmentedButton(
            actions_box,
            values=["Grade", "Mapa"],
            width=165,
            height=34,
            selected_color="#0066cc",
            selected_hover_color="#0052a3",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_view_mode_changed
        )
        self.seg_view.set("Grade")
        self.seg_view.pack(side="left", padx=(0, 8))

        if self.img_seg_grid and "Grade" in getattr(self.seg_view, "_buttons_dict", {}):
            self.seg_view._buttons_dict["Grade"].configure(image=self.img_seg_grid, compound="left")
        if self.img_seg_map and "Mapa" in getattr(self.seg_view, "_buttons_dict", {}):
            self.seg_view._buttons_dict["Mapa"].configure(image=self.img_seg_map, compound="left")

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
        # Container unificado com layout grid permanente (evita unmap/pack_forget de HWNDs Win32)
        self.content_area = ctk.CTkFrame(self, fg_color="transparent")
        self.content_area.pack(fill="both", expand=True, padx=12, pady=10)
        self.content_area.grid_rowconfigure(0, weight=1)
        self.content_area.grid_columnconfigure(0, weight=1)

        # 1. Modo Grade (AnyDesk Cards)
        self.scroll_frame = ctk.CTkScrollableFrame(self.content_area, fg_color="transparent")
        self.scroll_frame.grid(row=0, column=0, sticky="nsew")
        self.scroll_frame.bind("<Configure>", self._on_scroll_frame_configure, add="+")

        self.empty_label = ctk.CTkLabel(
            self.scroll_frame,
            text="Nenhum servidor cadastrado.\nClique no botão '+ Novo Servidor' acima para começar.",
            font=ctk.CTkFont(size=14),
            text_color=("gray40", "#767986"),
            justify="center"
        )

        # 2. Modo Mapa Interativo (Container GPU do Edge / Leaflet nativo)
        self.map_container = tk.Frame(self.content_area, bg="#121318")
        self.map_container.grid(row=0, column=0, sticky="nsew")
        self.map_container.bind("<Configure>", self._on_map_container_configure, add="+")

        # Inicia exibindo a grade por padrão
        self.map_container.lower()
        if hasattr(self.scroll_frame, "_parent_frame"):
            self.scroll_frame._parent_frame.tkraise()
        else:
            self.scroll_frame.tkraise()

        # Menu lateral deslizante e flutuante de configurações (Drawer)
        self.settings_drawer = SettingsDrawer(
            parent=self,
            current_version=CURRENT_VERSION,
            on_close=self.close_settings_drawer,
            on_check_updates=self.check_for_updates_manual,
            on_clean_thumbnails=self._clean_thumbnails_cache,
            on_clean_credentials=self._clean_credentials_manual,
            on_uninstall=self.confirm_uninstall_app
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
        self._update_version_badge()

    def _update_version_badge(self):
        cfg = ConfigManager()
        if cfg.is_dev_authenticated():
            ch = "TESTER" if cfg.get_update_channel() == "beta_tester" else "BETA"
            badge = f"v{CURRENT_VERSION} [{ch}]"
            color = "#00cc66"
        else:
            badge = f"v{CURRENT_VERSION}"
            color = ("gray35", "#8e92a0")
        if hasattr(self, "lbl_version_btn"):
            self.lbl_version_btn.configure(text=badge, text_color=color)

    def _sync_servers_from_cloud(self):
        try:
            remote = CloudSyncManager.fetch_servers()
            if remote:
                log.info(f"[RemoteXPTI] Recebidos {len(remote)} servidores do Supabase. Sincronizando com storage...")
                local_map = {s["id"]: s for s in self.storage.servers}
                changed = False
                for r in remote:
                    r_id = r.get("id")
                    if r_id not in local_map:
                        self.storage.servers.append(r)
                        changed = True
                    else:
                        local = local_map[r_id]
                        for fld in ("name", "host", "port", "username", "group", "latitude", "longitude"):
                            if r.get(fld) is not None and r.get(fld) != local.get(fld):
                                local[fld] = r[fld]
                                changed = True
                if changed:
                    self.storage.save()
                    self._action_queue.put(self.refresh_servers)
        except Exception as e:
            log.warning(f"[RemoteXPTI] Erro na sincronização com Supabase: {e}")

    def toggle_settings_drawer(self):
        """Alterna a abertura/fechamento do menu lateral flutuante de configurações."""
        if getattr(self, "_is_drawer_open", False):
            self.close_settings_drawer()
        else:
            self.open_settings_drawer()

    def open_settings_drawer(self):
        """Abre o menu lateral flutuante sobre a janela sem desalinhar os cards da grade."""
        if getattr(self, "_is_drawer_open", False):
            return
        self._is_drawer_open = True

        # Destaca o botão de engrenagem na barra superior
        self.btn_settings.configure(
            fg_color="#0066cc",
            hover_color="#0052a3",
            text_color="#ffffff"
        )

        # Se estiver no modo mapa, ajusta margem para não sobrepor o Edge
        if self.view_mode == "mapa" and hasattr(self, "web_map") and self.web_map:
            self.web_map.set_margin_right(420)

        win_w = self.winfo_width()
        win_h = self.winfo_height()
        drawer_w = 420
        drawer_h = max(200, win_h - 64 - 28)

        if getattr(self, "_drawer_anim_id", None):
            self.after_cancel(self._drawer_anim_id)
            self._drawer_anim_id = None

        start_x = win_w
        target_x = win_w - drawer_w

        self.settings_drawer.configure(width=drawer_w, height=drawer_h)
        self.settings_drawer.place(x=start_x, y=64)
        self.settings_drawer.tkraise()

        steps = 8
        current_step = [0]

        def anim_step():
            if not self._is_drawer_open:
                return
            current_step[0] += 1
            progress = current_step[0] / steps
            cur_x = int(start_x + (target_x - start_x) * (1 - (1 - progress) ** 2))
            cur_w = self.winfo_width()
            cur_h = self.winfo_height()
            self.settings_drawer.configure(width=drawer_w, height=max(200, cur_h - 64 - 28))
            self.settings_drawer.place(x=cur_x, y=64)
            self.settings_drawer.tkraise()
            if current_step[0] < steps:
                self._drawer_anim_id = self.after(12, anim_step)
            else:
                self.settings_drawer.configure(width=drawer_w, height=max(200, cur_h - 64 - 28))
                self.settings_drawer.place(x=cur_w - drawer_w, y=64)
                self.settings_drawer.tkraise()
                self._drawer_anim_id = None

        anim_step()

    def close_settings_drawer(self):
        """Fecha com animação de deslizamento para a direita."""
        if not getattr(self, "_is_drawer_open", False):
            return
        self._is_drawer_open = False

        self.btn_settings.configure(
            fg_color=("#dce0e8", "#262832"),
            hover_color=("#ccd2dc", "#343644"),
            text_color=("gray10", "#ffffff")
        )

        if hasattr(self, "web_map") and self.web_map:
            self.web_map.set_margin_right(0)

        win_w = self.winfo_width()
        win_h = self.winfo_height()
        drawer_w = 420
        drawer_h = max(200, win_h - 64 - 28)

        if getattr(self, "_drawer_anim_id", None):
            self.after_cancel(self._drawer_anim_id)
            self._drawer_anim_id = None

        start_x = self.settings_drawer.winfo_x() if (self.settings_drawer and self.settings_drawer.winfo_ismapped()) else (win_w - drawer_w)
        target_x = win_w

        steps = 6
        current_step = [0]

        def anim_step():
            if self._is_drawer_open:
                return
            current_step[0] += 1
            progress = current_step[0] / steps
            cur_x = int(start_x + (target_x - start_x) * (progress ** 2))
            cur_h = self.winfo_height()
            if self.settings_drawer:
                self.settings_drawer.configure(width=drawer_w, height=max(200, cur_h - 64 - 28))
                self.settings_drawer.place(x=cur_x, y=64)
            if current_step[0] < steps:
                self._drawer_anim_id = self.after(12, anim_step)
            else:
                if self.settings_drawer:
                    self.settings_drawer.place_forget()
                self._drawer_anim_id = None

        anim_step()

    def open_settings_dialog(self):
        """Abre/fecha o menu lateral deslizante de configurações."""
        self.toggle_settings_drawer()

    def open_version_menu(self):
        self.toggle_settings_drawer()

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
        if getattr(self, "_is_drawer_open", False) and getattr(self, "settings_drawer", None):
            win_w = self.winfo_width()
            win_h = self.winfo_height()
            drawer_w = 420
            drawer_h = max(200, win_h - 64 - 28)
            self.settings_drawer.configure(width=drawer_w, height=drawer_h)
            self.settings_drawer.place(x=win_w - drawer_w, y=64)
            self.settings_drawer.tkraise()
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
        """Encerra a aplicação de forma limpa, finalizando o Edge e o pool de threads em segundo plano."""
        log.info("[RemoteXPTI] Encerrando aplicação (WM_DELETE_WINDOW)...")
        if hasattr(self, "splash_manager") and self.splash_manager:
            try:
                self.splash_manager.close_now()
            except Exception:
                pass
        if hasattr(self, "splash") and self.splash:
            try:
                if hasattr(self.splash, "window") and self.splash.window.winfo_exists():
                    self.splash.window.destroy()
            except Exception:
                pass
        try:
            if hasattr(self, "web_map") and self.web_map:
                self.web_map.shutdown()
        except Exception as e:
            log.warning(f"[RemoteXPTI] Erro ao encerrar web_map: {e}")
        try:
            if hasattr(self, "_status_executor"):
                self._status_executor.shutdown(wait=False)
        except Exception as e:
            log.warning(f"[RemoteXPTI] Erro ao desligar executor de status: {e}")
        self.destroy()
        log.info("[RemoteXPTI] Aplicação finalizada.")

    def refresh_servers(self):
        self._update_version_badge()
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

    def _on_map_container_configure(self, event=None):
        if self.view_mode == "mapa" and self.web_map:
            self.web_map.resize()

    def _on_view_mode_changed(self, mode: str):
        log.info(f"[RemoteXPTI] Alternando modo de visualização para: {mode}")
        if "Mapa" in mode:
            self.view_mode = "mapa"
            if hasattr(self.scroll_frame, "_parent_frame"):
                self.scroll_frame._parent_frame.lower()
            else:
                self.scroll_frame.lower()
            self.map_container.tkraise()
            self.filter_servers()
            if self.web_map:
                if getattr(self, "_is_drawer_open", False):
                    self.web_map.set_margin_right(420)
                else:
                    self.web_map.set_margin_right(0)
                self.web_map.show()
            if getattr(self, "_is_drawer_open", False) and getattr(self, "settings_drawer", None):
                self.settings_drawer.tkraise()
        else:
            self.view_mode = "grade"
            if self.web_map:
                self.web_map.hide()
            self.map_container.lower()
            if hasattr(self.scroll_frame, "_parent_frame"):
                self.scroll_frame._parent_frame.tkraise()
            else:
                self.scroll_frame.tkraise()
            if getattr(self, "_is_drawer_open", False) and getattr(self, "settings_drawer", None):
                self.settings_drawer.tkraise()
            self.filter_servers()

    def _process_action_queue(self):
        """Processa com total segurança requisições vindas de threads secundárias (como o servidor web do mapa)."""
        try:
            while True:
                action = self._action_queue.get_nowait()
                try:
                    action()
                except Exception as e:
                    print(f"[RemoteXPTI] Erro ao executar ação da fila: {e}")
        except queue.Empty:
            pass
        self.after(50, self._process_action_queue)

    def connect_to_server_by_id(self, server_id: str):
        server = self.storage.get_server(server_id)
        if server:
            print(f"[RemoteXPTI] Conectando ao servidor via Mapa: {server.get('name')} ({server.get('host')})")
            self._action_queue.put(lambda: self.connect_to_server(server))
        else:
            print(f"[RemoteXPTI] Servidor ID '{server_id}' não encontrado no storage local.")

    def open_edit_dialog_by_id(self, server_id: str):
        server = self.storage.get_server(server_id)
        if server:
            print(f"[RemoteXPTI] Abrindo edição para servidor: {server.get('name')}")
            self._action_queue.put(lambda: self.open_edit_dialog(server))
        else:
            print(f"[RemoteXPTI] Servidor ID '{server_id}' não encontrado para edição.")

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

        self.filtered_servers = filtered

        if self.view_mode == "grade":
            self._render_cards(filtered)
        else:
            count = len(filtered)
            self.lbl_server_count.configure(text=f"{count} {'servidor' if count == 1 else 'servidores'} no mapa")

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

        log.info(f"[RemoteXPTI] Usuário solicitou conexão com servidor '{full_server.get('name')}' ({host}:{port}, user='{user}')")
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
                    log.info(f"[RemoteXPTI] Processo RDP para '{full_server.get('name')}' disparado com sucesso.")
                    self.set_message(f"Conectado a {host}! Aguardando tela remota...")
                    self.storage.record_connection(server_id)

                    def on_captured(s_id):
                        self._action_queue.put(lambda: self._update_card_preview(s_id))

                    threading.Thread(
                        target=PreviewManager.auto_capture_after_launch,
                        args=(server_id, host, 6.0, on_captured),
                        daemon=True
                    ).start()
                else:
                    log.error(f"[RemoteXPTI] Falha ao conectar em '{full_server.get('name')}': {msg}")
                    self.set_message(f"Erro ao conectar: {msg}", duration_sec=8)
            self._action_queue.put(on_done)

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
        log.info(f"[RemoteXPTI] Iniciando checagem de status dos servidores (manual={is_manual}, total={len(self.storage.servers)})...")
        if is_manual:
            self.set_message("Verificando status dos servidores...")

        pending = [len(self.storage.servers)]

        def check_worker(server_id: str, host: str, port: int):
            try:
                is_online, msg = RDPManager.check_connection(host, port, timeout=1.5)
                # Salva no cache de status
                self.server_status[server_id] = (is_online, msg)
                
                # Gerencia o rastreador de tempo de loss / downtime com persistência em disco
                changed = False
                if not is_online:
                    if server_id not in self.server_downtime:
                        self.server_downtime[server_id] = time.time()
                        changed = True
                else:
                    if server_id in self.server_downtime:
                        self.server_downtime.pop(server_id, None)
                        changed = True
                if changed:
                    self._save_downtime_history()
                
                # Atualiza o card da grade suavemente apenas quando o resultado chegar
                def update_ui():
                    if server_id in self.card_widgets:
                        self.card_widgets[server_id].update_status(is_online, msg)
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

    def get_active_incidents(self) -> List[Dict[str, Any]]:
        """
        Retorna a lista de servidores atualmente em falha (loss/offline),
        ordenados estritamente pelo maior tempo de inatividade no topo.
        """
        now = time.time()
        incidents = []
        server_map = {s["id"]: s for s in self.storage.servers}
        
        for s_id, offline_since in list(self.server_downtime.items()):
            srv = server_map.get(s_id)
            if not srv:
                continue
            duration = max(0, int(now - offline_since))
            from map_manager import resolve_server_coordinates
            coords = resolve_server_coordinates(srv)
            incidents.append({
                "id": s_id,
                "name": srv.get("name", "Servidor"),
                "host": srv.get("host", ""),
                "port": srv.get("port", 3389),
                "offline_since": offline_since,
                "duration_seconds": duration,
                "latitude": coords[0] if coords else None,
                "longitude": coords[1] if coords else None,
            })
            
        # Ordenação estrita: maior tempo offline primeiro, menores abaixo
        incidents.sort(key=lambda x: x["duration_seconds"], reverse=True)
        return incidents

    def _load_downtime_history(self):
        """Carrega o histórico persistente de inatividade de servidores do disco."""
        try:
            from config_manager import get_config_dir
            hist_file = get_config_dir() / "downtime_history.json"
            if hist_file.exists():
                with open(hist_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.server_downtime = {str(k): float(v) for k, v in data.items()}
                        log.info(f"[RemoteXPTI] Histórico de downtime carregado do disco: {len(self.server_downtime)} servidores em falha.")
        except Exception as e:
            log.warning(f"[RemoteXPTI] Falha ao carregar downtime_history.json: {e}")

    def _save_downtime_history(self):
        """Persiste o histórico de downtime no disco para sobreviver a reinicializações do app."""
        try:
            from config_manager import get_config_dir
            hist_file = get_config_dir() / "downtime_history.json"
            with open(hist_file, "w", encoding="utf-8") as f:
                json.dump(self.server_downtime, f, indent=2)
        except Exception as e:
            log.warning(f"[RemoteXPTI] Falha ao salvar downtime_history.json: {e}")

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
            log.info(f"[RemoteXPTI] Servidor adicionado com sucesso: '{new_s['name']}' (ID={server_id}, Host={new_s.get('host')}:{new_s.get('port')})")
            if data.get("custom_image"):
                try:
                    img = Image.open(data["custom_image"])
                    img.convert("RGB").save(PreviewManager.get_thumbnail_path(server_id), "PNG")
                except Exception as e:
                    log.warning(f"Erro ao salvar imagem customizada: {e}")
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
            log.info(f"[RemoteXPTI] Servidor editado e salvo: '{data['name']}' (ID={server_id}, Host={data.get('host')}:{data.get('port')})")
            PreviewManager.invalidate_cache(server_id)
            if data.get("custom_image"):
                try:
                    img = Image.open(data["custom_image"])
                    img.convert("RGB").save(PreviewManager.get_thumbnail_path(server_id), "PNG")
                except Exception as e:
                    log.warning(f"Erro ao salvar imagem customizada: {e}")
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
            log.info(f"[RemoteXPTI] Excluindo servidor '{name}' (ID={server_id})")
            self.storage.delete_server(server_id)
            PreviewManager.invalidate_cache(server_id)
            thumb_path = PreviewManager.get_thumbnail_path(server_id)
            if thumb_path.exists():
                try:
                    thumb_path.unlink()
                except Exception:
                    pass
            # Remove do cache de status e histórico de downtime
            self.server_status.pop(server_id, None)
            if server_id in self.server_downtime:
                self.server_downtime.pop(server_id, None)
                self._save_downtime_history()
            
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
    import multiprocessing
    multiprocessing.freeze_support()
    app = RemoteXPTIApp()
    app.mainloop()
