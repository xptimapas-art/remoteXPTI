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
from ajin_view import AjinView

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CARD_WIDTH = 276
CARD_HEIGHT = 180

class ServerCard(ctk.CTkLabel):
    """Componente de Card de Alta Performance no padrão visual e interativo do AnyDesk."""

    def __init__(
        self,
        parent,
        server: Dict[str, Any],
        on_connect,
        on_edit,
        initial_status: Optional[Tuple[bool, str]] = None
    ):
        self.server = server
        self.on_connect = on_connect
        self.on_edit = on_edit
        self.is_online = initial_status[0] if initial_status is not None else None
        self.is_fav = bool(server.get("favorite", False))
        self._is_hovering = False

        self._load_images()

        super().__init__(
            parent,
            text="",
            image=self.img_normal,
            width=CARD_WIDTH,
            height=CARD_HEIGHT,
            corner_radius=4,
            fg_color="#181a20",
            cursor="hand2"
        )

        self._bind_events()

    def _load_images(self):
        """Carrega a imagem normal imediatamente e deixa a imagem hover para sob demanda (0ms no startup)."""
        scope = self.server.get("scope", "corporate")
        self.img_normal = PreviewManager.get_card_ctk(
            server_id=self.server["id"],
            name=self.server.get("name", "Servidor"),
            host=self.server.get("host", "0.0.0.0"),
            is_online=self.is_online,
            width=CARD_WIDTH,
            height=CARD_HEIGHT,
            is_fav=self.is_fav,
            is_hover=False,
            scope=scope
        )
        self.img_hover = None  # Carregamento sob demanda (lazy) ao passar o mouse

    def _bind_events(self):
        self.bind("<Button-1>", self._on_card_click)
        self.bind("<Button-3>", lambda e: self.on_edit(self.server))
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))

    def _on_card_click(self, event):
        x = event.x
        y = event.y

        w = self.winfo_width()
        h = self.winfo_height()
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
            scope = self.server.get("scope", "corporate")
            self.img_hover = PreviewManager.get_card_ctk(
                server_id=self.server["id"],
                name=self.server.get("name", "Servidor"),
                host=self.server.get("host", "0.0.0.0"),
                is_online=self.is_online,
                width=CARD_WIDTH,
                height=CARD_HEIGHT,
                is_fav=self.is_fav,
                is_hover=True,
                scope=scope
            )
        self.configure(image=self.img_hover if is_hover else self.img_normal)

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

    def update_server_data(self, server: Dict[str, Any]):
        """Atualiza os dados do servidor e recarrega a renderização se algo mudou."""
        if self.server != server:
            self.server = server
            self.is_fav = bool(server.get("favorite", False))
            self.reload_thumbnail()

    def reload_thumbnail(self):
        """Atualiza a imagem do card na tela mantendo o estado de hover se ativo."""
        self._load_images()
        self.configure(image=self.img_hover if self._is_hovering else self.img_normal)


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


def setup_global_smooth_scroll(app):
    """
    Substitui a rolagem bruta e sem controle do CustomTkinter por um despachante suave a 60 FPS (16ms).
    Acumula rajadas de eventos de MouseWheel do Windows e sincroniza com o timer do Tkinter,
    eliminando completamente o tearing, sobreposicoes e o aspecto 'embaralhado' durante a rolagem
    em toda a aplicacao (Grade de Servidores, Ajin, Menus e Dialogos).
    """
    if sys.platform != "win32":
        return

    scroll_state = {
        "target_canvas": None,
        "delta": 0,
        "is_shift": False,
        "job": None
    }

    def _perform_scroll():
        scroll_state["job"] = None
        canvas = scroll_state["target_canvas"]
        delta = scroll_state["delta"]
        is_shift = scroll_state["is_shift"]
        scroll_state["delta"] = 0
        scroll_state["target_canvas"] = None
        if not canvas:
            return
        try:
            if canvas.winfo_exists():
                units = -int(delta / 6)
                if units != 0:
                    if is_shift:
                        if canvas.xview() != (0.0, 1.0):
                            canvas.xview("scroll", units, "units")
                    else:
                        if canvas.yview() != (0.0, 1.0):
                            canvas.yview("scroll", units, "units")
        except Exception:
            pass

    def _on_smooth_mouse_wheel(event):
        curr = event.widget
        target_sf = None
        while curr is not None:
            if isinstance(curr, ctk.CTkScrollableFrame):
                target_sf = curr
                break
            curr = getattr(curr, "master", None)

        if not target_sf:
            return

        canvas = getattr(target_sf, "_parent_canvas", None)
        if not canvas:
            return

        if scroll_state["target_canvas"] != canvas:
            scroll_state["target_canvas"] = canvas
            scroll_state["delta"] = 0

        scroll_state["delta"] += event.delta
        scroll_state["is_shift"] = bool(event.state & 0x1) or getattr(target_sf, "_shift_pressed", False)

        if scroll_state["job"] is None:
            try:
                scroll_state["job"] = app.after(16, _perform_scroll)
            except Exception:
                pass
        return "break"

    try:
        app.bind_all("<MouseWheel>", _on_smooth_mouse_wheel, add=False)
        log.info("[RemoteXPTI] Despachante de rolagem suave a 60 FPS ativado globalmente.")
    except Exception as e:
        log.warning(f"[RemoteXPTI] Falha ao configurar scroll suave: {e}")


def setup_win32_drag_optimizer(app):
    """
    Subclassing nativo Win32 (64-bit seguro) do procedimento de janela (WndProc)
    do frame de topo do Windows.
    
    Isola 100% o loop modal de movimentação do mouse do Windows (SC_MOVE) do Tkinter.
    Durante o arrasto da janela (WM_ENTERSIZEMOVE até WM_EXITSIZEMOVE), filtra e desvia
    rajadas de mensagens de alta frequência (mouses de 500Hz/1000Hz) diretamente para o DefWindowProc,
    permitindo que o DWM do Windows mova a textura da janela a 144Hz/240Hz com aceleração pura de hardware
    sem que o Tkinter gere eventos virtuais, recalcule layouts ou sature a fila de mensagens do mouse.
    """
    if sys.platform != "win32":
        return

    try:
        user32 = ctypes.windll.user32

        LRESULT = ctypes.c_int64
        WPARAM = ctypes.c_uint64
        LPARAM = ctypes.c_int64
        HWND = ctypes.c_void_p
        UINT = ctypes.c_uint

        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)

        user32.SetWindowLongPtrW.argtypes = [HWND, ctypes.c_int, ctypes.c_void_p]
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p

        user32.CallWindowProcW.argtypes = [ctypes.c_void_p, HWND, UINT, WPARAM, LPARAM]
        user32.CallWindowProcW.restype = LRESULT

        user32.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
        user32.DefWindowProcW.restype = LRESULT

        GWLP_WNDPROC = -4
        WM_ENTERSIZEMOVE = 0x0231
        WM_EXITSIZEMOVE = 0x0232
        WM_WINDOWPOSCHANGING = 0x0046
        WM_WINDOWPOSCHANGED = 0x0047
        WM_MOVE = 0x0003
        WM_MOVING = 0x0216
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010

        class WINDOWPOS(ctypes.Structure):
            _fields_ = [
                ("hwnd", HWND),
                ("hwndInsertAfter", HWND),
                ("x", ctypes.c_int),
                ("y", ctypes.c_int),
                ("cx", ctypes.c_int),
                ("cy", ctypes.c_int),
                ("flags", ctypes.c_uint),
            ]

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        frame_hwnd = int(app.wm_frame(), 16)
        client_hwnd = app.winfo_id()

        state = {
            "in_drag": False,
            "old_frame_proc": None,
            "old_client_proc": None,
            "c_proc": None
        }

        def smooth_wndproc(hwnd, msg, wp, lp):
            if msg == WM_ENTERSIZEMOVE:
                state["in_drag"] = True
            elif msg == WM_EXITSIZEMOVE:
                state["in_drag"] = False
                old_p = state["old_frame_proc"] if hwnd == frame_hwnd else state["old_client_proc"]
                if old_p and hwnd == frame_hwnd:
                    try:
                        rect = RECT()
                        user32.GetWindowRect(frame_hwnd, ctypes.byref(rect))
                        wp_final = WINDOWPOS()
                        wp_final.hwnd = frame_hwnd
                        wp_final.hwndInsertAfter = None
                        wp_final.x = rect.left
                        wp_final.y = rect.top
                        wp_final.cx = rect.right - rect.left
                        wp_final.cy = rect.bottom - rect.top
                        wp_final.flags = SWP_NOZORDER | SWP_NOACTIVATE
                        user32.CallWindowProcW(old_p, frame_hwnd, WM_WINDOWPOSCHANGED, 0, ctypes.addressof(wp_final))
                    except Exception:
                        pass
                res = 0
                if old_p:
                    res = user32.CallWindowProcW(old_p, hwnd, msg, wp, lp)
                try:
                    app.after(10, app._check_column_recalculation)
                except Exception:
                    pass
                return res
            elif state["in_drag"]:
                if msg in (WM_MOVE, WM_MOVING):
                    return 0
                elif msg == WM_WINDOWPOSCHANGED and lp:
                    try:
                        wp_struct = WINDOWPOS.from_address(lp)
                        if wp_struct.flags & SWP_NOSIZE:
                            return user32.DefWindowProcW(hwnd, msg, wp, lp)
                    except Exception:
                        pass

            old_p = state["old_frame_proc"]
            if old_p:
                return user32.CallWindowProcW(old_p, hwnd, msg, wp, lp)
            return user32.DefWindowProcW(hwnd, msg, wp, lp)

        state["c_proc"] = WNDPROC(smooth_wndproc)
        state["old_frame_proc"] = user32.SetWindowLongPtrW(
            frame_hwnd, GWLP_WNDPROC, ctypes.cast(state["c_proc"], ctypes.c_void_p)
        )

        log.info("[RemoteXPTI] Otimizador nativo de arrasto Win32 ativado com sucesso.")

        def cleanup():
            try:
                if state["old_frame_proc"]:
                    user32.SetWindowLongPtrW(frame_hwnd, GWLP_WNDPROC, state["old_frame_proc"])
                    state["old_frame_proc"] = None
            except Exception:
                pass

        app._win32_drag_cleanup = cleanup
    except Exception as e:
        log.warning(f"[RemoteXPTI] Falha ao configurar Win32DragOptimizer: {e}")


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
        self._last_window_size = None
        self._last_map_container_size = None
        self._resize_timer = None
        self._auto_ping_timer = None
        self._search_debounce_timer = None
        self._is_checking_status = False
        self._status_executor = ThreadPoolExecutor(max_workers=10)
        self._action_queue = queue.Queue()
        self._is_drawer_open = False
        self.settings_drawer = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_header()
        self._build_main_view()
        self._build_statusbar()
        self._process_action_queue()

        # Substitui os manipuladores padrão do CustomTkinter e do app por um único despachante de alta performance
        self.bind("<Configure>", self._unified_configure_handler)
        self.bind("<FocusIn>", self._on_window_focus, add="+")
        self.bind("<Unmap>", lambda e: self.close_settings_drawer() if e.widget == self else None, add="+")
        self.bind("<Button-1>", self._on_parent_click_dismiss, add="+")
        self.bind("<Escape>", lambda e: self.close_settings_drawer() if getattr(self, "_is_drawer_open", False) else None)

        setup_global_smooth_scroll(self)

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
        self._schedule_cloud_sync()
        
        # Sistema de atualização silenciosa em background (estilo Antigravity)
        self.updater = SilentAutoUpdater(
            on_ready_callback=self._on_update_ready,
            on_status_callback=self._on_update_status,
            cleanup_callback=self._prepare_for_restart
        )
        self.after(3500, self.updater.start_background_check)
        self._schedule_periodic_update_check()

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
        setup_win32_drag_optimizer(self)
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

        # Alternador de Modo de Exibição (Grade AnyDesk / Mapa Interativo / AJIN)
        icon_grid_path = get_resource_path("imagens/icon_grid.png")
        icon_map_path = get_resource_path("imagens/icon_map.png")
        icon_ajin_path = get_resource_path("imagens/icon_ajin.png")
        self.img_seg_grid = None
        self.img_seg_map = None
        self.img_seg_ajin = None
        if icon_grid_path.exists():
            try:
                pil_g = Image.open(icon_grid_path)
                self.img_seg_grid = ctk.CTkImage(light_image=pil_g, dark_image=pil_g, size=(18, 18))
            except Exception:
                pass
        if icon_map_path.exists():
            try:
                pil_m = Image.open(icon_map_path)
                self.img_seg_map = ctk.CTkImage(light_image=pil_m, dark_image=pil_m, size=(18, 18))
            except Exception:
                pass
        if icon_ajin_path.exists():
            try:
                pil_a = Image.open(icon_ajin_path)
                self.img_seg_ajin = ctk.CTkImage(light_image=pil_a, dark_image=pil_a, size=(18, 18))
            except Exception:
                pass

        self.seg_view = ctk.CTkSegmentedButton(
            actions_box,
            values=["Grade", "Mapa", "AJIN"],
            width=255,
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
        if self.img_seg_ajin and "AJIN" in getattr(self.seg_view, "_buttons_dict", {}):
            self.seg_view._buttons_dict["AJIN"].configure(image=self.img_seg_ajin, compound="left")

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

        # 3. Modo ONUs Ajin (Monitoramento de Rede NOC Nativo)
        # Carregamento Lazy sob demanda: economiza 780+ widgets e 1500+ HWNDs no startup,
        # garantindo que a movimentação da janela seja instantânea e ultra-suave.
        self.ajin_container = None
        self.ajin_view = None

        # Inicia exibindo a grade por padrão com isolamento de containers
        self.map_container.grid_remove()
        self.scroll_frame.grid(row=0, column=0, sticky="nsew")
        self.scroll_frame.tkraise()

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
            if remote is not None:
                changed, added, updated = self.storage.merge_cloud_servers(remote)
                if changed:
                    PreviewManager.invalidate_cache()
                    self._action_queue.put(self._on_cloud_sync_applied)
                    log.info(f"[RemoteXPTI] Nuvem sincronizada com sucesso: {added} adicionados, {updated} atualizados.")
        except Exception as e:
            log.warning(f"[RemoteXPTI] Erro na sincronização com Supabase: {e}")

    def _on_cloud_sync_applied(self):
        """Aplica alterações da nuvem na interface instantaneamente e re-checa pings."""
        for card in list(self.card_widgets.values()):
            try:
                card.destroy()
            except Exception:
                pass
        self.card_widgets.clear()
        self.refresh_servers()
        self.start_status_checker(is_manual=False)
        self.set_message("☁️ Servidores sincronizados com a nuvem em tempo real.", duration_sec=4)

    def _ensure_settings_drawer(self):
        """Garante que a instância do SettingsDrawer embutido esteja criada."""
        if not getattr(self, "settings_drawer", None) or not self.settings_drawer.winfo_exists():
            self.settings_drawer = SettingsDrawer(
                parent=self,
                current_version=CURRENT_VERSION,
                on_close=self._on_settings_drawer_closed,
                on_check_updates=self.check_for_updates_manual,
                on_clean_thumbnails=self._clean_thumbnails_cache,
                on_clean_credentials=self._clean_credentials_manual,
                on_uninstall=self.confirm_uninstall_app
            )
        return self.settings_drawer

    def toggle_settings_drawer(self):
        """Alterna a abertura/fechamento do menu lateral embutido de configurações."""
        if getattr(self, "_is_drawer_open", False):
            self.close_settings_drawer()
        else:
            self.open_settings_drawer()

    def open_settings_drawer(self):
        """Abre o menu lateral gaveta ancorado na lateral direita da janela principal."""
        self._is_drawer_open = True
        self.btn_settings.configure(
            fg_color="#0066cc",
            hover_color="#0052a3",
            text_color="#ffffff"
        )
        drawer = self._ensure_settings_drawer()
        drawer.show()

        # Se estiver no modo Mapa, ajusta o Edge para não colidir com o menu
        if self.view_mode == "mapa" and getattr(self, "web_map", None):
            self.web_map.set_drawer_offset(452)

    def _is_widget_child_of(self, child, parent):
        """Verifica se um widget é filho ou descendente de outro widget."""
        try:
            if child == parent:
                return True
            str_child = str(child)
            str_parent = str(parent)
            if str_child == str_parent or str_child.startswith(str_parent + ".") or str_child.startswith(str_parent):
                return True
            curr = child
            while curr is not None:
                if curr == parent:
                    return True
                curr = getattr(curr, "master", None)
        except Exception:
            pass
        return False

    def _on_parent_click_dismiss(self, event):
        """Fecha o menu lateral ao clicar em qualquer área externa da janela principal."""
        if not getattr(self, "_is_drawer_open", False):
            return
        if not getattr(self, "settings_drawer", None) or not self.settings_drawer.winfo_ismapped():
            return

        # Se o clique ocorreu dentro do botão de configurações, o toggle se encarrega
        if getattr(self, "btn_settings", None):
            if event.widget == self.btn_settings or self._is_widget_child_of(event.widget, self.btn_settings):
                return

        # Se o clique ocorreu dentro do próprio menu lateral ou qualquer filho seu, NÃO fecha
        if event.widget == self.settings_drawer or self._is_widget_child_of(event.widget, self.settings_drawer):
            return

        # Clique foi fora: fecha o drawer
        self.close_settings_drawer()

    def _on_settings_drawer_closed(self):
        """Atualiza estado interno e botões quando o drawer for fechado."""
        self._is_drawer_open = False
        self.btn_settings.configure(
            fg_color=("#dce0e8", "#262832"),
            hover_color=("#ccd2dc", "#343644"),
            text_color=("gray10", "#ffffff")
        )
        if getattr(self, "web_map", None):
            self.web_map.set_drawer_offset(0)

    def close_settings_drawer(self):
        """Fecha o menu lateral embutido de configurações."""
        self._on_settings_drawer_closed()
        if getattr(self, "settings_drawer", None) and self.settings_drawer.winfo_exists():
            self.settings_drawer.place_forget()

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

    def _prepare_for_restart(self):
        """Encerra de forma limpa e graciosa todos os subsistemas antes do restart pelo updater."""
        log.info("[RemoteXPTI] _prepare_for_restart: Encerrando conexões, timers e subsistema Edge...")
        if getattr(self, "_auto_ping_timer", None):
            try:
                self.after_cancel(self._auto_ping_timer)
            except Exception:
                pass
        if getattr(self, "_cloud_sync_timer", None):
            try:
                self.after_cancel(self._cloud_sync_timer)
            except Exception:
                pass
        if getattr(self, "_auto_update_timer", None):
            try:
                self.after_cancel(self._auto_update_timer)
            except Exception:
                pass
        if hasattr(self, "splash_manager") and self.splash_manager:
            try:
                self.splash_manager.close_now()
            except Exception:
                pass
        if hasattr(self, "web_map") and self.web_map:
            try:
                self.web_map.shutdown()
            except Exception:
                pass
        if hasattr(self, "_status_executor"):
            try:
                self._status_executor.shutdown(wait=False)
            except Exception:
                pass

    def _on_update_ready(self, new_version: str):
        """Chamado quando o update terminou de baixar: muda discretamente o botão de versão para Restart."""
        def show():
            self.lbl_version_btn.configure(
                text=f"🔄 Restart para Atualizar (v{new_version})",
                fg_color="#0066cc",
                hover_color="#0052a3",
                text_color="#ffffff",
                command=lambda: self.updater.apply_update_and_restart(cleanup_func=self._prepare_for_restart)
            )
            self.set_message(f"🚀 Versão {new_version} pronta! Clique em 'Restart para Atualizar' abaixo.", duration_sec=10)
        self.after(0, show)

    def _unified_configure_handler(self, event):
        if event.widget != self:
            return

        w = event.width
        h = event.height
        cur_size = (w, h)
        if cur_size == getattr(self, "_last_window_size", None):
            return
        self._last_window_size = cur_size

        # Sincroniza dimensões internas do CustomTkinter sem queries Tcl redundantes
        try:
            self._current_width = self._reverse_window_scaling(w)
            self._current_height = self._reverse_window_scaling(h)
        except Exception:
            pass

        if getattr(self, "view_mode", "grade") == "grade":
            if getattr(self, "_resize_timer", None):
                self.after_cancel(self._resize_timer)
            self._resize_timer = self.after(150, self._check_column_recalculation)

    def _calculate_columns(self) -> int:
        """
        Calcula o número de colunas ideal considerando o DPI Scaling do Windows.
        Baseia-se estritamente na largura física do container visível (content_area),
        evitando oscilações causadas pelo crescimento do frame interno de rolagem.
        """
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        slot_w_phys = (CARD_WIDTH + 10) * scale

        avail_w = 0
        if hasattr(self, "content_area") and self.content_area.winfo_exists():
            avail_w = self.content_area.winfo_width()
        if avail_w <= 200:
            win_w = self.winfo_width()
            avail_w = (win_w - (32 * scale)) if win_w > 200 else ((1100 - 32) * scale)

        usable_w = avail_w - int(24 * scale)
        return max(1, int(usable_w // slot_w_phys))

    def _check_column_recalculation(self):
        w = self.winfo_width()
        if w <= 200:
            try:
                import win32gui
                rect = win32gui.GetWindowRect(self.winfo_id())
                w = rect[2] - rect[0]
            except Exception:
                pass
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
        if getattr(self, "_auto_ping_timer", None):
            try:
                self.after_cancel(self._auto_ping_timer)
            except Exception:
                pass
        if getattr(self, "_cloud_sync_timer", None):
            try:
                self.after_cancel(self._cloud_sync_timer)
            except Exception:
                pass
        if getattr(self, "_auto_update_timer", None):
            try:
                self.after_cancel(self._auto_update_timer)
            except Exception:
                pass
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
        if getattr(self, "settings_drawer", None) and self.settings_drawer.winfo_exists():
            try:
                self.settings_drawer.destroy()
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
        if hasattr(self, "_win32_drag_cleanup") and self._win32_drag_cleanup:
            try:
                self._win32_drag_cleanup()
            except Exception:
                pass
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
        if self.view_mode != "mapa" or not self.web_map:
            return
        if event:
            cur_size = (event.width, event.height)
            if cur_size == getattr(self, "_last_map_container_size", None):
                return
            self._last_map_container_size = cur_size
        self.web_map.resize()

    def _ensure_ajin_view(self):
        """Inicializa a visualização do Ajin sob demanda, poupando centenas de widgets no startup."""
        if self.ajin_container is None:
            log.info("[RemoteXPTI] Inicializando AjinView sob demanda...")
            self.ajin_container = ctk.CTkFrame(self.content_area, fg_color=("#f0f2f5", "#10121a"))
            self.ajin_container.grid(row=0, column=0, sticky="nsew")
            self.ajin_view = AjinView(self.ajin_container)
            self.ajin_view.pack(fill="both", expand=True)

    def _on_view_mode_changed(self, mode: str):
        log.info(f"[RemoteXPTI] Alternando modo de visualização para: {mode}")
        m_lower = mode.lower()
        if "ajin" in m_lower:
            self.view_mode = "ajin"
            if self.web_map:
                self.web_map.hide()
            if hasattr(self, "map_container"):
                self.map_container.grid_remove()
            if hasattr(self, "scroll_frame"):
                self.scroll_frame.grid_remove()

            self._ensure_ajin_view()
            self.ajin_container.grid(row=0, column=0, sticky="nsew")
            self.ajin_container.tkraise()
            if hasattr(self, "ajin_view") and self.ajin_view:
                self.ajin_view.mgr.fetch_telemetry_async(force=True)
                self.ajin_view._handle_table_resize()
            if getattr(self, "settings_drawer", None) and self.settings_drawer.winfo_exists() and self._is_drawer_open:
                self.settings_drawer.lift()

        elif "mapa" in m_lower:
            self.view_mode = "mapa"
            if hasattr(self, "ajin_container") and self.ajin_container:
                self.ajin_container.grid_remove()
            if hasattr(self, "scroll_frame"):
                self.scroll_frame.grid_remove()

            self.map_container.grid(row=0, column=0, sticky="nsew")
            self.map_container.tkraise()
            self.filter_servers()
            if self.web_map:
                if getattr(self, "_is_drawer_open", False):
                    self.web_map.set_drawer_offset(452)
                else:
                    self.web_map.set_drawer_offset(0)
                self.web_map.show()
                self.web_map.resize()
            if getattr(self, "settings_drawer", None) and self.settings_drawer.winfo_exists() and self._is_drawer_open:
                self.settings_drawer.lift()

        else:
            self.view_mode = "grade"
            if hasattr(self, "ajin_container") and self.ajin_container:
                self.ajin_container.grid_remove()
            if self.web_map:
                self.web_map.set_drawer_offset(0)
                self.web_map.hide()
            if hasattr(self, "map_container"):
                self.map_container.grid_remove()

            self.scroll_frame.grid(row=0, column=0, sticky="nsew")
            self.scroll_frame.tkraise()
            self._check_column_recalculation()
            if getattr(self, "settings_drawer", None) and self.settings_drawer.winfo_exists() and self._is_drawer_open:
                self.settings_drawer.lift()
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

        # Limpa apenas as colunas que deixaram de ser utilizadas
        prev_cols = getattr(self, "_configured_grid_cols", 0)
        if prev_cols > cols:
            for i in range(cols, prev_cols + 1):
                self.scroll_frame.grid_columnconfigure(i, weight=0, minsize=0)

        # Configura colunas ativas para expandir proporcionalmente e preencher toda a largura
        for i in range(cols):
            self.scroll_frame.grid_columnconfigure(i, weight=1, minsize=int(CARD_WIDTH + 10))
        self._configured_grid_cols = cols

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
                card.update_server_data(server)
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
        if self.view_mode == "ajin":
            if hasattr(self, "ajin_view"):
                self.ajin_view.mgr.fetch_telemetry_async(force=True)
            return
        self.start_status_checker(is_manual=True)
        if hasattr(self, "updater") and self.updater:
            self.updater.start_background_check()
        if CloudSyncManager.is_configured():
            threading.Thread(target=self._sync_servers_from_cloud, daemon=True).start()

    def _schedule_periodic_ping(self):
        """Verifica a conectividade dos servidores periodicamente em segundo plano."""
        self.start_status_checker(is_manual=False)
        self._auto_ping_timer = self.after(35000, self._schedule_periodic_ping)

    def _schedule_periodic_update_check(self):
        """Checa atualizações em segundo plano a cada 45 minutos."""
        if hasattr(self, "updater") and self.updater:
            self.updater.start_background_check()
        self._auto_update_timer = self.after(2700000, self._schedule_periodic_update_check)

    def _schedule_cloud_sync(self):
        """Sincroniza servidores corporativos da nuvem em segundo plano com intervalo adaptativo."""
        if CloudSyncManager.is_configured():
            threading.Thread(target=self._sync_servers_from_cloud, daemon=True).start()
        try:
            is_minimized = self.state() == "iconic"
        except Exception:
            is_minimized = False
        delay = 90000 if is_minimized else 60000
        self._cloud_sync_timer = self.after(delay, self._schedule_cloud_sync)

    def _on_window_focus(self, event=None):
        """Dispara verificação na nuvem quando a janela ganha foco (máximo 1x por minuto)."""
        now = time.time()
        if now - getattr(self, "_last_focus_sync", 0) > 60:
            self._last_focus_sync = now
            if CloudSyncManager.is_configured():
                threading.Thread(target=self._sync_servers_from_cloud, daemon=True).start()

    def open_add_dialog(self):
        is_admin = ConfigManager().is_dev_authenticated()

        def on_save(data):
            new_s = self.storage.add_server(data)
            server_id = new_s["id"]
            log.info(f"[RemoteXPTI] Servidor adicionado com sucesso: '{new_s['name']}' (ID={server_id}, Scope={new_s.get('scope')}, Host={new_s.get('host')}:{new_s.get('port')})")
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
            self.start_status_checker(is_manual=False)

            # Se for servidor corporativo criado por admin, publica automaticamente na nuvem
            if new_s.get("scope") == "corporate" and is_admin:
                def do_auto_push():
                    ok, msg = CloudSyncManager.push_single_server(new_s)
                    if ok:
                        self.set_message(f"Servidor '{new_s['name']}' salvo e publicado para toda a empresa!")
                    else:
                        self.set_message(f"Servidor '{new_s['name']}' salvo localmente ({msg}).")
                threading.Thread(target=do_auto_push, daemon=True).start()
            else:
                self.set_message(f"Servidor '{new_s['name']}' adicionado com sucesso!")

        ServerDialog(
            parent=self,
            existing_groups=self.storage.get_groups(),
            on_save=on_save
        )

    def open_edit_dialog(self, server: Dict[str, Any]):
        full_server = self.storage.get_server(server["id"])
        if not full_server:
            full_server = server

        is_admin = ConfigManager().is_dev_authenticated()
        is_corporate = (full_server.get("scope", "corporate") == "corporate")

        # Se for corporativo e o usuário NÃO for administrador, abre exclusivamente em modo leitura
        if is_corporate and not is_admin:
            ServerDialog(
                parent=self,
                server_data=full_server,
                existing_groups=self.storage.get_groups(),
                read_only=True
            )
            return

        def on_save(data):
            self.storage.update_server(server["id"], data)
            server_id = server["id"]
            log.info(f"[RemoteXPTI] Servidor editado e salvo: '{data['name']}' (ID={server_id}, Scope={data.get('scope')}, Host={data.get('host')}:{data.get('port')})")
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
            self.start_status_checker(is_manual=False)

            # Se for servidor corporativo e admin, publica automaticamente na nuvem
            if data.get("scope") == "corporate" and is_admin:
                updated_s = self.storage.get_server(server_id)
                if updated_s:
                    def do_auto_push():
                        ok, msg = CloudSyncManager.push_single_server(updated_s)
                        if ok:
                            self.set_message(f"Servidor '{data['name']}' atualizado e publicado na nuvem para toda a empresa!")
                        else:
                            self.set_message(f"Servidor '{data['name']}' atualizado localmente ({msg}).")
                    threading.Thread(target=do_auto_push, daemon=True).start()
            else:
                self.set_message(f"Servidor '{data['name']}' atualizado com sucesso!")

        def on_delete():
            self.confirm_delete_server(server)

        ServerDialog(
            parent=self,
            server_data=full_server,
            existing_groups=self.storage.get_groups(),
            on_save=on_save,
            on_delete=on_delete,
            read_only=False
        )

    def confirm_delete_server(self, server: Dict[str, Any]):
        is_admin = ConfigManager().is_dev_authenticated()
        is_corporate = (server.get("scope", "corporate") == "corporate")

        if is_corporate and not is_admin:
            self.set_message("Aviso: Servidores corporativos só podem ser excluídos pelo Administrador.")
            return

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

            # Se for corporativo e admin, remove do Supabase
            if is_corporate and is_admin:
                threading.Thread(target=lambda: CloudSyncManager.delete_remote_server(server_id), daemon=True).start()
                self.set_message(f"Servidor '{name}' excluído e removido da nuvem da empresa.")
            else:
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
