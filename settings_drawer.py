import customtkinter as ctk
from typing import Optional, Callable
import threading
from pathlib import Path
from preview_manager import PreviewManager
from uninstaller import Uninstaller
from logger import open_logs_folder, log
from config_manager import ConfigManager
from cloud_sync import CloudSyncManager
from updater import SilentAutoUpdater
from dialogs import SupabaseConfigDialog, ConfirmDialog
try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

class SettingsDrawer(ctk.CTkToplevel):
    """
    Menu lateral flutuante em formato de Popup Card para Configurações Gerais,
    Área do Desenvolvedor, Troca de Canais e Diagnóstico.
    
    Aparece diretamente no canto superior direito sobre qualquer visualização
    (Grade, Mapa, etc.) sem reorganizar, redimensionar ou empurrar nenhum elemento de trás.
    """

    def __init__(
        self,
        parent,
        current_version: str,
        on_close: Callable[[], None],
        on_check_updates: Callable[[], None],
        on_clean_thumbnails: Optional[Callable[[], None]] = None,
        on_clean_credentials: Optional[Callable[[], None]] = None,
        on_uninstall: Optional[Callable[[], None]] = None,
        **kwargs
    ):
        super().__init__(parent, **kwargs)
        self.parent = parent
        self.current_version = current_version
        self.on_close_callback = on_close
        self.on_check_updates = on_check_updates
        self.on_clean_thumbnails = on_clean_thumbnails
        self.on_clean_credentials = on_clean_credentials
        self.on_uninstall = on_uninstall

        self._fetched_releases = []
        self._is_fetching_releases = False
        self._is_closing = False

        # Configurações de popup flutuante sobreposto
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.transient(parent)

        # Container principal com cantos arredondados e borda sutil AnyDesk
        self.main_container = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=("#f8f9fb", "#171922"),
            border_width=1,
            border_color=("#cfd4de", "#2e3142")
        )
        self.main_container.pack(fill="both", expand=True, padx=2, pady=2)

        # 1. Header do Menu
        header_frame = ctk.CTkFrame(self.main_container, height=50, corner_radius=10, fg_color=("#eef1f6", "#1f212c"))
        header_frame.pack(fill="x", side="top", padx=8, pady=(8, 4))
        header_frame.pack_propagate(False)

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=12, pady=6)

        lbl_title = ctk.CTkLabel(
            title_box,
            text="⚙️ Configurações",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("gray10", "#ffffff")
        )
        lbl_title.pack(anchor="w")

        lbl_sub = ctk.CTkLabel(
            title_box,
            text=f"RemoteXPTI v{self.current_version} • Gestão do Sistema",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "#8e92a0")
        )
        lbl_sub.pack(anchor="w")

        btn_close = ctk.CTkButton(
            header_frame,
            text="✕",
            width=28,
            height=28,
            fg_color="transparent",
            hover_color=("#dfe3ea", "#2c2f3e"),
            text_color=("gray20", "#a0a4b8"),
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.close
        )
        btn_close.pack(side="right", padx=8, pady=8)

        # 2. Rodapé com botão de fechar rápido
        footer_frame = ctk.CTkFrame(self.main_container, height=44, corner_radius=10, fg_color=("#eef1f6", "#1f212c"))
        footer_frame.pack(fill="x", side="bottom", padx=8, pady=(4, 8))
        footer_frame.pack_propagate(False)

        btn_footer_close = ctk.CTkButton(
            footer_frame,
            text="Fechar Menu",
            height=30,
            fg_color=("gray75", "#282a34"),
            hover_color=("gray65", "#353846"),
            text_color=("gray10", "#ffffff"),
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.close
        )
        btn_footer_close.pack(fill="x", padx=10, pady=7)

        # 3. Área Scrollável de Opções
        self.scroll = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=6, pady=4)

        self._build_sections()
        self.reposition()

        # Tecla Escape para fechar
        self.bind("<Escape>", lambda e: self.close())

    def reposition(self):
        """
        Posiciona o popup perfeitamente alinhado ao canto superior direito da janela principal.
        Utiliza Win32 GetWindowRect e SetWindowPos para precisão atômica de 60 FPS durante o redimensionamento.
        """
        try:
            if not self.winfo_exists() or not self.parent.winfo_exists():
                return

            scale = ctk.ScalingTracker.get_window_scaling(self.parent)

            # 1. Obter retângulo físico real do container/janela principal
            has_win32 = False
            if HAS_WIN32:
                try:
                    rect = win32gui.GetWindowRect(self.parent.winfo_id())
                    rx, ry = rect[0], rect[1]
                    rw = max(380, rect[2] - rect[0])
                    rh = max(300, rect[3] - rect[1])
                    has_win32 = True
                except Exception:
                    pass

            if not has_win32:
                rx = self.parent.winfo_rootx()
                ry = self.parent.winfo_rooty()
                rw = max(380, self.parent.winfo_width())
                rh = max(300, self.parent.winfo_height())

            # 2. Dimensões responsivas do menu
            # Em janelas normais ou maximizadas: 400px lógicos.
            # Em janelas muito estreitas (ex: tela dividida / laptop pequeno): adapta para caber sem sair da janela.
            popup_logical_w = min(400, max(280, int((rw - 30) / scale)))
            popup_phys_w = int(popup_logical_w * scale)

            header_phys_h = int(60 * scale)
            footer_phys_h = int(28 * scale)
            margin = int(10 * scale)

            # Posiciona no canto direito, respeitando a margem
            pos_x = int(rx + rw - popup_phys_w - margin)
            # Garante que pos_x nunca seja menor que rx + margem (evita vazar para a esquerda em janelas ultra estreitas)
            pos_x = max(int(rx + margin), pos_x)

            pos_y = int(ry + header_phys_h + margin)

            # Altura responsiva: cabe perfeitamente na janela sem vazar sobre a barra de status inferior
            avail_phys_h = rh - header_phys_h - footer_phys_h - (margin * 2)
            max_logical_h = 700
            popup_logical_h = min(max_logical_h, max(240, int(avail_phys_h / scale)))
            popup_phys_h = int(popup_logical_h * scale)

            # Atualiza o rastreador de tamanho lógico do CustomTkinter
            self._current_width = popup_logical_w
            self._current_height = popup_logical_h

            if has_win32:
                try:
                    top_hwnd = win32gui.GetParent(self.winfo_id())
                    if top_hwnd and win32gui.IsWindow(top_hwnd):
                        win32gui.SetWindowPos(
                            top_hwnd,
                            win32con.HWND_TOPMOST,
                            pos_x,
                            pos_y,
                            popup_phys_w,
                            popup_phys_h,
                            win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
                        )
                        return
                except Exception:
                    pass

            self.geometry(f"{popup_logical_w}x{popup_logical_h}+{pos_x}+{pos_y}")
            self.lift()
            self.attributes("-topmost", True)
        except Exception as e:
            log.warning(f"[SettingsDrawer] Erro ao reposicionar popup: {e}")

    def close(self):
        if self._is_closing:
            return
        self._is_closing = True
        if self.on_close_callback:
            try:
                self.on_close_callback()
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass

    def reload(self):
        """Recarrega os componentes internos preservando o estado da interface."""
        for w in self.scroll.winfo_children():
            w.destroy()
        self._build_sections()
        if hasattr(self.parent, "refresh_servers"):
            try:
                self.parent.refresh_servers()
            except Exception:
                pass
        if hasattr(self.parent, "_update_version_badge"):
            try:
                self.parent._update_version_badge()
            except Exception:
                pass

    def _build_sections(self):
        cfg = ConfigManager()
        is_dev = cfg.is_dev_authenticated()
        active_channel = cfg.get_update_channel()

        # ==========================================
        # SEÇÃO 1: Atualizações de Software
        # ==========================================
        card_update = ctk.CTkFrame(self.scroll, corner_radius=8, fg_color=("gray88", "#1f212a"))
        card_update.pack(fill="x", padx=4, pady=5)

        ctk.CTkLabel(
            card_update,
            text="🔄 Atualizações de Software",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray15", "#e0e4ee")
        ).pack(anchor="w", padx=12, pady=(10, 2))

        ch_desc = "Canal Beta Tester (1.x.y)" if active_channel == "beta_tester" else "Canal Beta Público (1.x.0)"
        ctk.CTkLabel(
            card_update,
            text=f"Versão: v{self.current_version} • {ch_desc}\nVerificações silenciosas em segundo plano ativas.",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "#8e92a0"),
            justify="left"
        ).pack(anchor="w", padx=12, pady=(0, 8))

        btn_check = ctk.CTkButton(
            card_update,
            text="🔍 Verificar Atualizações no GitHub",
            height=30,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.on_check_updates
        )
        btn_check.pack(fill="x", padx=12, pady=(0, 10))

        # ==========================================
        # SEÇÃO 2: Área do Desenvolvedor & Beta Tester
        # ==========================================
        card_dev = ctk.CTkFrame(self.scroll, corner_radius=8, fg_color=("gray88", "#1f212a"))
        card_dev.pack(fill="x", padx=4, pady=5)

        if not is_dev:
            ctk.CTkLabel(
                card_dev,
                text="🔐 Área do Desenvolvedor",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("gray15", "#e0e4ee")
            ).pack(anchor="w", padx=12, pady=(10, 2))

            ctk.CTkLabel(
                card_dev,
                text="Acesso restrito para alternar canais de atualização, testar compilações intermediárias e sincronizar em nuvem.",
                font=ctk.CTkFont(size=10),
                text_color=("gray40", "#8e92a0"),
                justify="left",
                wraplength=340
            ).pack(anchor="w", padx=12, pady=(0, 8))

            row_pwd = ctk.CTkFrame(card_dev, fg_color="transparent")
            row_pwd.pack(fill="x", padx=12, pady=(0, 6))

            self.entry_dev_pwd = ctk.CTkEntry(
                row_pwd,
                placeholder_text="Senha de Desenvolvedor...",
                show="*",
                height=30
            )
            self.entry_dev_pwd.pack(side="left", fill="x", expand=True, padx=(0, 6))

            def try_dev_login(event=None):
                pwd = self.entry_dev_pwd.get().strip()
                if not pwd:
                    self.lbl_dev_error.configure(text="Digite a senha de desenvolvedor.")
                    return
                if ConfigManager().authenticate_dev(pwd):
                    self.reload()
                else:
                    self.lbl_dev_error.configure(text="Senha incorreta. Tente novamente.")
                    self.entry_dev_pwd.delete(0, "end")

            self.entry_dev_pwd.bind("<Return>", try_dev_login)

            btn_login = ctk.CTkButton(
                row_pwd,
                text="Entrar",
                width=70,
                height=30,
                fg_color="#0066cc",
                hover_color="#0052a3",
                font=ctk.CTkFont(size=11, weight="bold"),
                command=try_dev_login
            )
            btn_login.pack(side="right")

            self.lbl_dev_error = ctk.CTkLabel(
                card_dev,
                text="",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="#ff4d4d"
            )
            self.lbl_dev_error.pack(anchor="w", padx=12, pady=(0, 6))
        else:
            # Modo Desenvolvedor Autenticado
            dev_header = ctk.CTkFrame(card_dev, fg_color="transparent")
            dev_header.pack(fill="x", padx=12, pady=(10, 4))

            ctk.CTkLabel(
                dev_header,
                text="🟢 Modo Desenvolvedor Ativo",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#00cc66"
            ).pack(side="left")

            btn_logout = ctk.CTkButton(
                dev_header,
                text="🚪 Sair",
                width=60,
                height=22,
                font=ctk.CTkFont(size=10),
                fg_color=("#ffdddd", "#381a1e"),
                hover_color=("#ffc2c2", "#522228"),
                text_color=("#cc0000", "#ff6b6b"),
                command=lambda: (cfg.logout_dev(), self.reload())
            )
            btn_logout.pack(side="right")

            # 1. Alternador de Canal
            ctk.CTkLabel(
                card_dev,
                text="Canal de Atualização:",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray20", "#d0d4e0")
            ).pack(anchor="w", padx=12, pady=(4, 2))

            def on_channel_changed(val):
                new_ch = "public" if "Público" in val else "beta_tester"
                cfg.set_update_channel(new_ch)
                self.reload()

            seg_channel = ctk.CTkSegmentedButton(
                card_dev,
                values=["Canal Beta Público (1.x.0)", "Canal Beta Tester (1.x.y)"],
                command=on_channel_changed
            )
            seg_channel.set("Canal Beta Tester (1.x.y)" if active_channel == "beta_tester" else "Canal Beta Público (1.x.0)")
            seg_channel.pack(fill="x", padx=12, pady=(0, 8))

            # 2. Seletor de Versões do GitHub
            ctk.CTkLabel(
                card_dev,
                text="Seletor de Versões (Rollback / Build Específico):",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray20", "#d0d4e0")
            ).pack(anchor="w", padx=12, pady=(4, 2))

            row_sel = ctk.CTkFrame(card_dev, fg_color="transparent")
            row_sel.pack(fill="x", padx=12, pady=(0, 6))

            self.combo_versions = ctk.CTkComboBox(
                row_sel,
                values=["Clique em 'Listar' para buscar..."],
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
            self.btn_install_custom.pack(fill="x", padx=12, pady=(0, 6))

            self.lbl_custom_status = ctk.CTkLabel(
                card_dev,
                text="",
                font=ctk.CTkFont(size=10),
                wraplength=340,
                justify="left"
            )
            self.lbl_custom_status.pack(anchor="w", padx=12, pady=(0, 6))

            # 3. Sincronização em Nuvem (Supabase)
            ctk.CTkLabel(
                card_dev,
                text="Sincronização em Nuvem (Supabase):",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray20", "#d0d4e0")
            ).pack(anchor="w", padx=12, pady=(6, 2))

            row_cloud = ctk.CTkFrame(card_dev, fg_color="transparent")
            row_cloud.pack(fill="x", padx=12, pady=(0, 10))

            btn_cfg_cloud = ctk.CTkButton(
                row_cloud,
                text="☁️ Configurar Supabase",
                height=28,
                fg_color=("#d6dae2", "#2e303b"),
                command=lambda: SupabaseConfigDialog(self.parent, on_saved=self.reload)
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

            # Carrega automaticamente a lista de releases
            self.after(80, self._fetch_releases_list)

        # ==========================================
        # SEÇÃO 3: Manutenção e Diagnóstico
        # ==========================================
        card_maint = ctk.CTkFrame(self.scroll, corner_radius=8, fg_color=("gray88", "#1f212a"))
        card_maint.pack(fill="x", padx=4, pady=5)

        ctk.CTkLabel(
            card_maint,
            text="🧹 Manutenção e Diagnóstico",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray15", "#e0e4ee")
        ).pack(anchor="w", padx=12, pady=(10, 2))

        if self.on_clean_thumbnails:
            btn_clean_thumbs = ctk.CTkButton(
                card_maint,
                text="🖼️ Limpar Cache de Miniaturas",
                height=28,
                fg_color=("#d6dae2", "#2e303b"),
                hover_color=("#c4c8d2", "#3b3d4a"),
                text_color=("gray10", "#ffffff"),
                font=ctk.CTkFont(size=11),
                command=self.on_clean_thumbnails
            )
            btn_clean_thumbs.pack(fill="x", padx=12, pady=(0, 6))

        if self.on_clean_credentials:
            btn_clean_creds = ctk.CTkButton(
                card_maint,
                text="🔐 Limpar Credenciais do Windows (TERMSRV)",
                height=28,
                fg_color=("#d6dae2", "#2e303b"),
                hover_color=("#c4c8d2", "#3b3d4a"),
                text_color=("gray10", "#ffffff"),
                font=ctk.CTkFont(size=11),
                command=self.on_clean_credentials
            )
            btn_clean_creds.pack(fill="x", padx=12, pady=(0, 6))

        btn_logs = ctk.CTkButton(
            card_maint,
            text="📁 Abrir Pasta de Logs de Diagnóstico",
            height=28,
            fg_color=("#d6dae2", "#2e303b"),
            hover_color=("#c4c8d2", "#3b3d4a"),
            text_color=("gray10", "#ffffff"),
            font=ctk.CTkFont(size=11),
            command=open_logs_folder
        )
        btn_logs.pack(fill="x", padx=12, pady=(0, 10))

        # ==========================================
        # SEÇÃO 4: Desinstalação do Aplicativo
        # ==========================================
        if self.on_uninstall:
            card_uninst = ctk.CTkFrame(self.scroll, corner_radius=8, fg_color=("gray88", "#1f212a"))
            card_uninst.pack(fill="x", padx=4, pady=5)

            ctk.CTkLabel(
                card_uninst,
                text="🗑️ Desinstalação",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("gray15", "#e0e4ee")
            ).pack(anchor="w", padx=12, pady=(10, 2))

            btn_uninst = ctk.CTkButton(
                card_uninst,
                text="Desinstalar RemoteXPTI por Completo...",
                height=30,
                fg_color=("#ffdddd", "#381a1e"),
                hover_color=("#ffc2c2", "#522228"),
                text_color=("#cc0000", "#ff6b6b"),
                font=ctk.CTkFont(size=11, weight="bold"),
                command=self.on_uninstall
            )
            btn_uninst.pack(fill="x", padx=12, pady=(0, 10))

    def _fetch_releases_list(self):
        if not hasattr(self, "combo_versions") or not self.combo_versions.winfo_exists():
            return
        if self._is_fetching_releases:
            return
        self._is_fetching_releases = True
        self.combo_versions.set("Buscando versões disponíveis...")
        self.lbl_custom_status.configure(text="Consultando lançamentos no GitHub...", text_color="#0080ff")

        result_holder = []

        def worker():
            try:
                releases = SilentAutoUpdater.fetch_all_releases()
                result_holder.append(releases)
            except Exception as e:
                log.error(f"[SettingsDrawer] Erro na busca de releases: {e}")
                result_holder.append([])

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            if not self.winfo_exists():
                return
            if result_holder:
                self._is_fetching_releases = False
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
            self.close()

            parent_window = self.parent
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
            parent=self.parent,
            title=f"Instalar Versão {tag}",
            message=f"Deseja baixar e instalar a versão {tag}?\n\nO RemoteXPTI exibirá o progresso com a animação de atualização e será reiniciado automaticamente.",
            confirm_text="Sim, Instalar Agora",
            confirm_color="#0066cc",
            on_confirm=do_install
        )

    def _push_servers_to_cloud(self):
        if not CloudSyncManager.is_configured():
            SupabaseConfigDialog(self.parent, on_saved=self.reload)
            return

        servers = getattr(self.parent, "storage", None)
        if servers and hasattr(servers, "servers"):
            ok, msg = CloudSyncManager.push_servers(servers.servers)
            color = "#00cc66" if ok else "#ff4d4d"
            self.lbl_custom_status.configure(text=msg, text_color=color)
