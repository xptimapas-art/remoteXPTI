"""
Interface Nativa de Monitoramento de ONUs Ajin (RemoteXPTI).
100% Nativo CustomTkinter com consumo assíncrono via API do servidor da empresa.
Reprodução fiel das 8 colunas, barra lateral de métricas NOC e modais de operação.
"""

from datetime import datetime
import json
import os
from pathlib import Path
import re
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple
import webbrowser

import customtkinter as ctk
from PIL import Image
import sys

from ajin_manager import AjinManager
from logger import log


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
class AjinRowWidget:
    """Linha da tabela de ONUs de alta performance, estacionária e com zero lag."""

    def __init__(self, master, pos_idx: int, on_edit, on_menu, on_del, on_mousewheel=None):
        self.pos_idx = pos_idx
        self.on_edit = on_edit
        self.on_menu = on_menu
        self.on_del = on_del
        self.on_mousewheel = on_mousewheel
        self.current_data: Optional[Dict[str, Any]] = None
        self.is_even: bool = (pos_idx % 2 == 0)
        self.base_bg: str = "#181c27" if self.is_even else "#141721"
        self.hover_bg: str = "#222736"

        self.frame = ctk.CTkFrame(master, height=38, corner_radius=4, fg_color=self.base_bg)
        self.frame.pack(fill="x", pady=1)
        self.frame.pack_propagate(False)

        # Col 0: Nome (Ponto) - width 145
        self.c0 = tk.Frame(self.frame, width=145, height=38, bg=self.base_bg)
        self.c0.pack_propagate(False)
        self.c0.pack(side="left", padx=4)

        self.lbl_p = tk.Label(self.c0, text="", font=("Segoe UI", 10, "bold"), fg="#ffffff", bg=self.base_bg)
        self.lbl_p.pack(side="left", padx=(0, 4))

        self.badge_2p = tk.Label(
            self.c0, text="2P", font=("Segoe UI", 8, "bold"),
            fg="#38bdf8", bg="#0f2b48", padx=4, pady=1
        )
        self.btn_edit_name = ctk.CTkButton(
            self.c0, text="✏️", width=20, height=20, fg_color="transparent",
            hover_color="#282f42", font=ctk.CTkFont(size=10),
            command=self._handle_edit
        )
        self.btn_edit_name.pack(side="left")

        # Col 1: Status - width 110
        self.c1 = tk.Frame(self.frame, width=110, height=38, bg=self.base_bg)
        self.c1.pack_propagate(False)
        self.c1.pack(side="left", padx=4)

        self.lbl_stt = ctk.CTkLabel(
            self.c1, text="", font=ctk.CTkFont(size=10, weight="bold"),
            corner_radius=10, width=70, height=22
        )
        self.lbl_stt.pack(side="left")

        # Col 2: Endereço / Serial - width 135
        self.lbl_ser = tk.Label(
            self.frame, text="", font=("Consolas", 10, "bold"), fg="#cbd5e1", bg=self.base_bg,
            width=15, anchor="w"
        )
        self.lbl_ser.pack(side="left", padx=4)

        # Col 3: Descrição (Rua / Local) - EXPANSIVO!
        self.c3 = tk.Frame(self.frame, height=38, bg=self.base_bg)
        self.c3.pack(side="left", fill="x", expand=True, padx=4)

        self.lbl_desc = tk.Label(self.c3, text="", font=("Segoe UI", 10), fg="#f1f5f9", bg=self.base_bg, anchor="w")
        self.lbl_desc.pack(side="left", padx=(0, 4))

        self.btn_edit_desc = ctk.CTkButton(
            self.c3, text="✏️", width=20, height=20, fg_color="transparent",
            hover_color="#282f42", font=ctk.CTkFont(size=10),
            command=self._handle_edit
        )
        self.btn_edit_desc.pack(side="left")

        # Col 4: Fabricante - width 100
        self.lbl_vendor = tk.Label(
            self.frame, text="", font=("Segoe UI", 10), fg="#94a3b8", bg=self.base_bg,
            width=12, anchor="w"
        )
        self.lbl_vendor.pack(side="left", padx=4)

        # Col 5: Tempo no Status - width 115
        self.lbl_upt = tk.Label(
            self.frame, text="", font=("Segoe UI", 10), fg="#94a3b8", bg=self.base_bg,
            width=13, anchor="w"
        )
        self.lbl_upt.pack(side="left", padx=4)

        # Col 6: Canal OLT - width 125
        self.lbl_canal = tk.Label(
            self.frame, text="", font=("Consolas", 10), fg="#cbd5e1", bg=self.base_bg,
            width=14, anchor="w"
        )
        self.lbl_canal.pack(side="left", padx=4)

        # Col 7: Ações - width 85
        self.c7 = tk.Frame(self.frame, width=85, height=38, bg=self.base_bg)
        self.c7.pack_propagate(False)
        self.c7.pack(side="left", padx=4)

        self.btn_menu = ctk.CTkButton(
            self.c7, text="Menu", width=50, height=24, fg_color="#222736",
            hover_color="#30384c", border_width=1, border_color="#374151",
            text_color="#f1f5f9", font=ctk.CTkFont(size=10, weight="bold"),
            command=self._handle_menu
        )
        self.btn_menu.pack(side="left", padx=(0, 4))

        self.btn_del = ctk.CTkButton(
            self.c7, text="🗑️", width=22, height=24, fg_color="transparent",
            hover_color="#3d1418", text_color="#f87171", font=ctk.CTkFont(size=11),
            command=self._handle_del
        )
        self.btn_del.pack(side="left")

        # Efeito de hover suave instantâneo sem queries Win32
        for w in (self.frame, self.c0, self.lbl_p, self.c1, self.lbl_ser, self.c3, self.lbl_desc, self.lbl_vendor, self.lbl_upt, self.lbl_canal, self.c7):
            w.bind("<Enter>", lambda e: self._on_enter(), add="+")
            w.bind("<Leave>", lambda e: self._on_leave(), add="+")

        # Captura de rolagem por mousewheel em qualquer elemento da linha
        if self.on_mousewheel:
            for w in (self.frame, self.c0, self.lbl_p, self.badge_2p, self.btn_edit_name,
                      self.c1, self.lbl_stt, self.lbl_ser, self.c3, self.lbl_desc,
                      self.btn_edit_desc, self.lbl_vendor, self.lbl_upt, self.lbl_canal,
                      self.c7, self.btn_menu, self.btn_del):
                w.bind("<MouseWheel>", self.on_mousewheel, add="+")

    def _on_enter(self):
        self.frame.configure(fg_color=self.hover_bg)
        self._set_bg(self.hover_bg)

    def _on_leave(self):
        self.frame.configure(fg_color=self.base_bg)
        self._set_bg(self.base_bg)

    def _set_bg(self, color: str):
        self.c0.configure(bg=color)
        self.lbl_p.configure(bg=color)
        self.c1.configure(bg=color)
        self.lbl_ser.configure(bg=color)
        self.c3.configure(bg=color)
        self.lbl_desc.configure(bg=color)
        self.lbl_vendor.configure(bg=color)
        self.lbl_upt.configure(bg=color)
        self.lbl_canal.configure(bg=color)
        self.c7.configure(bg=color)

    def _handle_edit(self):
        if self.current_data and self.on_edit:
            self.on_edit(self.current_data)

    def _handle_menu(self):
        if self.current_data and self.on_menu:
            self.on_menu(self.current_data)

    def _handle_del(self):
        if self.current_data and self.on_del:
            self.on_del(self.current_data)

    def update_data(self, r: Dict[str, Any], show_olt: bool = True):
        self.current_data = r

        # 0. Nome
        p_name = r.get("name") or "--"
        self.lbl_p.configure(text=f"🖧 {p_name}")

        has_2p = bool(r.get("multi_llid"))
        if getattr(self, "_has_2p", None) != has_2p:
            self._has_2p = has_2p
            self.btn_edit_name.pack_forget()
            if has_2p:
                self.badge_2p.pack(side="left", padx=(0, 4))
            else:
                self.badge_2p.pack_forget()
            self.btn_edit_name.pack(side="left")

        # 1. Status
        is_online = (r.get("status") == "Online")
        if getattr(self, "_is_online", None) != is_online:
            self._is_online = is_online
            if is_online:
                self.lbl_stt.configure(text="● Online", text_color="#4ade80", fg_color="#0d2e1c")
            else:
                self.lbl_stt.configure(text="● Offline", text_color="#f87171", fg_color="#3c1418")

        # 2. Serial
        self.lbl_ser.configure(text=r.get("serial", "-"))

        # 3. Descrição
        p_desc = r.get("desc") or ""
        if p_desc != getattr(self, "_current_desc", None):
            self._current_desc = p_desc
            if not p_desc:
                self.lbl_desc.configure(text="+ adicionar rua", font=("Segoe UI", 9, "italic"), fg="#64748b")
            else:
                self.lbl_desc.configure(text=p_desc, font=("Segoe UI", 10), fg="#f1f5f9")

        # 4. Fabricante
        self.lbl_vendor.configure(text=r.get("vendor", "-"))

        # 5. Tempo
        upt_txt = r.get("uptime") or "-"
        upt_col = "#f87171" if not is_online else "#94a3b8"
        upt_font = ("Segoe UI", 10, "bold") if not is_online else ("Segoe UI", 10)
        self.lbl_upt.configure(text=upt_txt, fg=upt_col, font=upt_font)

        # 6. Canal OLT
        canal_txt = f"{r.get('port')}_{str(r.get('id')).zfill(3)}" if show_olt else "--"
        self.lbl_canal.configure(text=canal_txt)

        if not self.frame.winfo_ismapped():
            self.frame.pack(fill="x", pady=1)


class NocSidebarManager:
    """Controlador central de hover para a Sidebar NOC. Garante exclusividade de destaque e zero bugs."""

    def __init__(self):
        self.blocks: List['NocSectionBlock'] = []
        self.active_block: Optional['NocSectionBlock'] = None

    def register(self, block: 'NocSectionBlock'):
        self.blocks.append(block)

    def set_hover(self, block: 'NocSectionBlock'):
        if self.active_block == block:
            return
        for b in self.blocks:
            if b != block:
                b.set_normal()
        self.active_block = block
        if block:
            block.set_hover()

    def clear(self):
        for b in self.blocks:
            b.set_normal()
        self.active_block = None


class NocSectionBlock:
    """Bloco de métrica da Sidebar NOC com divisores contínuos e hover exclusivo (leve destaque)."""

    def __init__(self, master, manager: NocSidebarManager, base_bg: str = "#2870c2", hover_bg: str = "#4083d2"):
        self.manager = manager
        self.base_bg = base_bg
        self.hover_bg = hover_bg
        self.frame = ctk.CTkFrame(master, fg_color=self.base_bg, corner_radius=0)
        self.frame.pack(fill="x", padx=0, pady=0)
        self.manager.register(self)

    def set_normal(self):
        self.frame.configure(fg_color=self.base_bg)

    def set_hover(self):
        self.frame.configure(fg_color=self.hover_bg)

    def bind_recursive(self, w=None):
        target = w or self.frame
        target.bind("<Enter>", lambda e: self.manager.set_hover(self), add="+")
        for child in target.winfo_children():
            self.bind_recursive(child)


class AjinView(ctk.CTkFrame):
    """Componente principal da aba de monitoramento das ONUs Ajin."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.mgr = AjinManager()

        # Estado da UI
        self._raw_rows: List[Dict[str, Any]] = []
        self._filtered_rows: List[Dict[str, Any]] = []
        self._sort_ascending: bool = True
        self._sort_col: str = "status"
        self._auto_refresh_enabled: bool = True
        self._refresh_countdown: int = 10
        self._active_dialog = None
        self._noc_hover_mgr = NocSidebarManager()

        self._build_layout()

        # Registra listener no AjinManager para atualizações automáticas via evento thread-safe
        self.bind("<<AjinDataUpdated>>", lambda e: self._process_incoming_data())
        self.mgr.add_listener(self._on_data_updated)

        # Carrega dados iniciais do cache
        self._process_incoming_data()

        # Inicia loop de contagem regressiva da UI
        self._schedule_countdown()

    def _build_layout(self):
        # Grid com 2 colunas: Esquerda (Tabela e controles) e Direita (Sidebar NOC)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # -------------------------------------------------------------
        # COLUNA ESQUERDA: Controles, Tabela e Rodapé
        # -------------------------------------------------------------
        self.left_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.left_panel.grid_rowconfigure(1, weight=1)
        self.left_panel.grid_columnconfigure(0, weight=1)

        self._build_top_controls()
        self._build_table_view()
        self._build_bottom_bar()

        # -------------------------------------------------------------
        # COLUNA DIREITA: Sidebar NOC e Métricas em Tempo Real
        # -------------------------------------------------------------
        self._build_sidebar_noc()

    # =========================================================================
    # BARRA SUPERIOR DE CONTROLES E FILTROS
    # =========================================================================
    def _build_top_controls(self):
        ctrl_frame = ctk.CTkFrame(self.left_panel, height=44, fg_color="transparent")
        ctrl_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        # 1. Campo de Busca expansivo (ocupa todo o espaço restante)
        self.entry_search = ctk.CTkEntry(
            ctrl_frame,
            placeholder_text="🔍 Pesquisar por Nome, Serial / MAC (LAN 1 ou 2)...",
            height=34,
            fg_color="#181c26",
            border_color="#2e3547",
            text_color="#ffffff"
        )
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_search.bind("<KeyRelease>", lambda e: self._apply_filters())

        # 2. Filtro de Portas PON
        self.combo_pon = ctk.CTkComboBox(
            ctrl_frame,
            values=["Todas as Portas PON", "Slot1-PON1", "Slot1-PON2", "Slot2-PON1", "Slot2-PON2"],
            width=150,
            height=34,
            fg_color="#181c26",
            button_color="#242b3b",
            button_hover_color="#30384c",
            border_color="#2e3547",
            dropdown_fg_color="#1c202d",
            text_color="#ffffff",
            command=lambda val: self._apply_filters()
        )
        self.combo_pon.set("Todas as Portas PON")
        self.combo_pon.pack(side="left", padx=(0, 6))

        # 3. Filtro de Status
        self.combo_status = ctk.CTkComboBox(
            ctrl_frame,
            values=["Todos os Status", "Em Funcionamento (Online)", "Fora de Funcionamento (Offline)"],
            width=165,
            height=34,
            fg_color="#181c26",
            button_color="#242b3b",
            button_hover_color="#30384c",
            border_color="#2e3547",
            dropdown_fg_color="#1c202d",
            text_color="#ffffff",
            command=lambda val: self._apply_filters()
        )
        self.combo_status.set("Todos os Status")
        self.combo_status.pack(side="left", padx=(0, 8))

        # 4. Botão Atualizar Câmeras
        self.btn_sync_cams = ctk.CTkButton(
            ctrl_frame,
            text="📹 Atualizar Câmeras",
            width=140,
            height=34,
            fg_color="#222736",
            hover_color="#30384c",
            border_width=1,
            border_color="#374151",
            text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_sync_cameras_clicked
        )
        self.btn_sync_cams.pack(side="left", padx=(0, 6))

        # 5. Botão Scanner de ONUs
        self.btn_scanner = ctk.CTkButton(
            ctrl_frame,
            text="🔍 Scanner de ONUs",
            width=140,
            height=34,
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._open_scanner_dialog
        )
        self.btn_scanner.pack(side="left", padx=(0, 6))

        # 6. Botão Incidentes & Eventos (com badge)
        self.btn_events = ctk.CTkButton(
            ctrl_frame,
            text="⚠️ Incidentes & Eventos (0)",
            width=175,
            height=34,
            fg_color="#7f1d1d",
            hover_color="#991b1b",
            border_width=1,
            border_color="#b91c1c",
            text_color="#fecaca",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._open_events_dialog
        )
        self.btn_events.pack(side="left")

    # =========================================================================
    # TABELA PRINCIPAL DE DISPOSITIVOS (8 COLUNAS)
    # =========================================================================
    def _build_table_view(self):
        # Container da Tabela com acabamento Dark Mode Profissional (NOC Clean)
        self.table_container = ctk.CTkFrame(
            self.left_panel,
            corner_radius=8,
            fg_color="#13161f",
            border_width=1,
            border_color="#232838"
        )
        self.table_container.grid(row=1, column=0, sticky="nsew")
        self.table_container.grid_rowconfigure(1, weight=1)
        self.table_container.grid_columnconfigure(0, weight=1)

        # Cabeçalho Fixo com Coluna 3 Expansiva e margem para scrollbar
        self.header_frame = ctk.CTkFrame(
            self.table_container,
            height=36,
            corner_radius=0,
            fg_color="#1a1e2b"
        )
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=(2, 16))
        self.header_frame.pack_propagate(False)

        headers = [
            ("Nome (Ponto)", 145, "name"),
            ("Status", 110, "status"),
            ("Endereço / Serial", 135, "serial"),
            ("Descrição (Rua / Local)", None, "desc"),
            ("Fabricante", 100, "vendor"),
            ("Tempo no Status", 115, "uptime"),
            ("Canal OLT", 125, "port"),
            ("Ações", 85, None)
        ]

        self._header_buttons = {}
        for text, width, sort_key in headers:
            if width:
                f = ctk.CTkFrame(self.header_frame, width=width, height=36, fg_color="transparent")
                f.pack_propagate(False)
                f.pack(side="left", padx=4)
            else:
                f = ctk.CTkFrame(self.header_frame, height=36, fg_color="transparent")
                f.pack(side="left", fill="x", expand=True, padx=4)

            if sort_key:
                initial_text = f"{text} ▲" if sort_key == self._sort_col else text
                initial_color = "#38bdf8" if sort_key == self._sort_col else "#94a3b8"
                btn = ctk.CTkButton(
                    f,
                    text=initial_text,
                    height=32,
                    fg_color="transparent",
                    text_color=initial_color,
                    hover_color="#252c3d",
                    anchor="w",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    command=lambda k=sort_key: self._on_column_sort(k)
                )
                btn._base_title = text
                btn.pack(side="left", fill="both", expand=True)
                self._header_buttons[sort_key] = btn
            else:
                lbl = ctk.CTkLabel(
                    f,
                    text=text,
                    anchor="w",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="#94a3b8"
                )
                lbl.pack(side="left", fill="both", expand=True)

        # Container principal da tabela com linhas estacionárias e scrollbar nativo independente
        self.table_viewport_frame = ctk.CTkFrame(self.table_container, fg_color="transparent")
        self.table_viewport_frame.grid(row=1, column=0, sticky="nsew", padx=2, pady=2)
        self.table_viewport_frame.grid_rowconfigure(0, weight=1)
        self.table_viewport_frame.grid_columnconfigure(0, weight=1)

        self.table_rows_container = ctk.CTkFrame(self.table_viewport_frame, fg_color="transparent")
        self.table_rows_container.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.table_rows_container.grid_columnconfigure(0, weight=1)

        self.table_scrollbar = ctk.CTkScrollbar(
            self.table_viewport_frame,
            orientation="vertical",
            scrollbar_button_color="#2c3345",
            scrollbar_button_hover_color="#3d4760"
        )
        self.table_scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 2))

        self.ROW_HEIGHT = 40
        self.POOL_SIZE = 35
        self.VISIBLE_ROWS = 15
        self._scroll_offset = 0
        self._resize_debounce_job = None
        self.scroll_table = self.table_viewport_frame  # alias para compatibilidade

        # Pool fixo de linhas estacionárias reutilizáveis
        self._row_pool: List[AjinRowWidget] = []
        for i in range(self.POOL_SIZE):
            item = AjinRowWidget(
                self.table_rows_container,
                i,
                self._open_edit_dialog,
                self._open_menu_dialog,
                self._on_delete_onu,
                on_mousewheel=self._on_table_mousewheel
            )
            item.frame.pack_forget()
            self._row_pool.append(item)

        self.table_scrollbar.configure(command=self._on_scrollbar_command)
        self.table_viewport_frame.bind("<MouseWheel>", self._on_table_mousewheel, add="+")
        self.table_rows_container.bind("<MouseWheel>", self._on_table_mousewheel, add="+")
        self.table_viewport_frame.bind("<Configure>", self._on_table_resize, add="+")

    def _on_column_sort(self, col_key: str):
        if self._sort_col == col_key:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_col = col_key
            self._sort_ascending = True

        for k, btn in getattr(self, "_header_buttons", {}).items():
            base_t = getattr(btn, "_base_title", "")
            if k == self._sort_col:
                arr = "▲" if self._sort_ascending else "▼"
                btn.configure(text=f"{base_t} {arr}", text_color="#38bdf8")
            else:
                btn.configure(text=base_t, text_color="#94a3b8")

        self._apply_filters()

    # =========================================================================
    # RODAPÉ DE CONTROLE E CHECKBOXES
    # =========================================================================
    def _build_bottom_bar(self):
        bot_frame = ctk.CTkFrame(self.left_panel, height=36, fg_color="transparent")
        bot_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        # Contador de dispositivos
        self.lbl_counter = ctk.CTkLabel(
            bot_frame,
            text="0 de 0 dispositivos",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#94a3b8"
        )
        self.lbl_counter.pack(side="left", padx=(0, 14))

        # Botão Exportar CSV
        self.btn_export = ctk.CTkButton(
            bot_frame,
            text="Exportar",
            width=80,
            height=30,
            fg_color="#222736",
            text_color="#f1f5f9",
            hover_color="#30384c",
            border_width=1,
            border_color="#374151",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_export_clicked
        )
        self.btn_export.pack(side="left", padx=(0, 8))

        # Botão Atualizar Agora
        self.btn_refresh = ctk.CTkButton(
            bot_frame,
            text="Atualizar",
            width=80,
            height=30,
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_manual_refresh_clicked
        )
        self.btn_refresh.pack(side="left", padx=(0, 14))

        # Informações de Horário
        self.lbl_timer_status = ctk.CTkLabel(
            bot_frame,
            text="Hora: --:--:--",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        )
        self.lbl_timer_status.pack(side="right")

    # =========================================================================
    # SIDEBAR DIREITA: MÉTRICAS NOC CLEAN (PADRÃO AJIN)
    # =========================================================================
    def _load_noc_icon(self, name: str, size: Tuple[int, int]) -> Optional[ctk.CTkImage]:
        try:
            p = get_resource_path(f"imagens/{name}.png")
            if p.exists():
                pil_img = Image.open(str(p)).convert("RGBA")
                return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
        except Exception as e:
            log.warning(f"Erro ao carregar ícone NOC {name}: {e}")
        return None

    def _add_noc_divider(self, parent):
        """Divisor horizontal sutil e visível de 1px entre categorias no padrão da referência."""
        div = tk.Frame(parent, height=1, bg="#5d9ee6")
        div.pack(fill="x", padx=0, pady=0)
        div.pack_propagate(False)
        return div

    def _create_noc_stat_section(self, parent, icon_img, val_str, label_str):
        """Cria uma seção de métrica clean com divisor e hover suave exclusivo."""
        block = NocSectionBlock(parent, self._noc_hover_mgr)

        sec = ctk.CTkFrame(block.frame, fg_color="transparent")
        sec.pack(fill="x", padx=16, pady=(10, 10))

        if icon_img:
            lbl_ico = ctk.CTkLabel(sec, image=icon_img, text="")
        else:
            lbl_ico = ctk.CTkLabel(sec, text="●", font=ctk.CTkFont(size=20), text_color="#ffffff")
        lbl_ico.pack(side="left", anchor="center")

        r_box = ctk.CTkFrame(sec, fg_color="transparent")
        r_box.pack(side="right", anchor="e")

        lbl_val = ctk.CTkLabel(
            r_box,
            text=val_str,
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color="#ffffff",
            anchor="e"
        )
        lbl_val.pack(anchor="e")

        lbl_sub = ctk.CTkLabel(
            r_box,
            text=label_str,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ffffff",
            anchor="e"
        )
        lbl_sub.pack(anchor="e")

        block.bind_recursive()
        return lbl_val, lbl_sub

    def _build_sidebar_noc(self):
        # Painel lateral azul (#2870c2) com bordas arredondadas e divisores contínuos
        self.sidebar_frame = ctk.CTkFrame(
            self,
            width=260,
            corner_radius=12,
            fg_color="#2870c2",
            border_width=0
        )
        self.sidebar_frame.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(4, 6))
        self.sidebar_frame.grid_propagate(False)

        # Monitor de saída da sidebar para limpar o hover instantaneamente sem chamadas de Win32
        def _on_sidebar_leave(e):
            if getattr(e, "widget", None) == self.sidebar_frame:
                self._noc_hover_mgr.clear()

        self.sidebar_frame.bind("<Leave>", _on_sidebar_leave, add="+")

        # Pré-carrega os ícones nativos
        self._img_router = self._load_noc_icon("noc_router", (34, 30))
        self._img_check = self._load_noc_icon("noc_check", (34, 34))
        self._img_cross = self._load_noc_icon("noc_cross", (34, 34))
        self._img_cam = self._load_noc_icon("noc_cam", (34, 24))
        self._img_pon = self._load_noc_icon("noc_pon", (26, 26))
        self._img_clock = self._load_noc_icon("noc_clock", (32, 32))
        self._img_globe = self._load_noc_icon("noc_globe", (30, 31))
        self._img_db = self._load_noc_icon("noc_db", (26, 28))

        # Área de Conteúdo Rolável com divisor contínuo de ponta a ponta
        self.scroll_noc = ctk.CTkScrollableFrame(
            self.sidebar_frame,
            fg_color="transparent",
            corner_radius=10,
            scrollbar_fg_color="transparent",
            scrollbar_button_color="#4f8ecc",
            scrollbar_button_hover_color="#63a4e6"
        )
        try:
            self.scroll_noc._scrollbar.configure(width=4)
        except Exception:
            pass
        self.scroll_noc.pack(side="top", fill="both", expand=True, padx=0, pady=0)
        self.scroll_noc.bind("<Leave>", _on_sidebar_leave, add="+")

        # 1. Total
        self.lbl_total_val, _ = self._create_noc_stat_section(
            self.scroll_noc, self._img_router, "0", "Total"
        )
        self._add_noc_divider(self.scroll_noc)

        # 2. Em Funcionamento
        self.lbl_status_online, _ = self._create_noc_stat_section(
            self.scroll_noc, self._img_check, "0", "Em Funcionamento"
        )
        self._add_noc_divider(self.scroll_noc)

        # 3. Fora de Funcionamento
        self.lbl_status_offline, _ = self._create_noc_stat_section(
            self.scroll_noc, self._img_cross, "0", "Fora de Funcionamento"
        )
        self._add_noc_divider(self.scroll_noc)

        # 4. Câmeras Mapeadas (Referência Oficial)
        self.lbl_cams_val, _ = self._create_noc_stat_section(
            self.scroll_noc, self._img_cam, "0", "Câmeras Mapeadas"
        )
        self._add_noc_divider(self.scroll_noc)

        # 5. Portas PON
        block_pon = NocSectionBlock(self.scroll_noc, self._noc_hover_mgr)
        sec_pon = ctk.CTkFrame(block_pon.frame, fg_color="transparent")
        sec_pon.pack(fill="x", padx=16, pady=(10, 8))

        top_pon = ctk.CTkFrame(sec_pon, fg_color="transparent")
        top_pon.pack(fill="x", pady=(0, 4))

        if self._img_pon:
            lbl_pon_ico = ctk.CTkLabel(top_pon, image=self._img_pon, text="")
        else:
            lbl_pon_ico = ctk.CTkLabel(top_pon, text="🗄️", font=ctk.CTkFont(size=18), text_color="#ffffff")
        lbl_pon_ico.pack(side="left", anchor="w")

        lbl_pon_title = ctk.CTkLabel(
            top_pon,
            text="Portas PON",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ffffff"
        )
        lbl_pon_title.pack(side="right", anchor="e")

        # 3 linhas de portas
        self.lbl_p1_val = self._create_pon_row(sec_pon, "Slot1-PON1", "- / -")
        self.lbl_p2_val = self._create_pon_row(sec_pon, "Slot2-PON1", "- / -")
        self.lbl_p3_val = self._create_pon_row(sec_pon, "Slot2-PON2", "- / -")

        block_pon.bind_recursive()
        self._add_noc_divider(self.scroll_noc)

        # 6. Última Coleta
        block_col = NocSectionBlock(self.scroll_noc, self._noc_hover_mgr)
        sec_coleta = ctk.CTkFrame(block_col.frame, fg_color="transparent")
        sec_coleta.pack(fill="x", padx=16, pady=(10, 8))

        if self._img_clock:
            lbl_col_ico = ctk.CTkLabel(sec_coleta, image=self._img_clock, text="")
        else:
            lbl_col_ico = ctk.CTkLabel(sec_coleta, text="⏱️", font=ctk.CTkFont(size=18), text_color="#ffffff")
        lbl_col_ico.pack(side="left", anchor="center")

        box_col = ctk.CTkFrame(sec_coleta, fg_color="transparent")
        box_col.pack(side="right", anchor="e")

        self.lbl_coleta_time = ctk.CTkLabel(
            box_col,
            text="--:--:--",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#ffffff",
            anchor="e"
        )
        self.lbl_coleta_time.pack(anchor="e")

        self.lbl_coleta_date = ctk.CTkLabel(
            box_col,
            text="--/--/----",
            font=ctk.CTkFont(size=11),
            text_color="#ffffff",
            anchor="e"
        )
        self.lbl_coleta_date.pack(anchor="e")

        lbl_col_sub = ctk.CTkLabel(
            box_col,
            text="Última Coleta",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#ffffff",
            anchor="e"
        )
        lbl_col_sub.pack(anchor="e")

        block_col.bind_recursive()
        self._add_noc_divider(self.scroll_noc)

        # 7. Servidor Coletor (Status da Coleta)
        block_srv = NocSectionBlock(self.scroll_noc, self._noc_hover_mgr)
        sec_srv = ctk.CTkFrame(block_srv.frame, fg_color="transparent")
        sec_srv.pack(fill="x", padx=16, pady=(10, 8))

        if self._img_globe:
            lbl_srv_ico = ctk.CTkLabel(sec_srv, image=self._img_globe, text="")
        else:
            lbl_srv_ico = ctk.CTkLabel(sec_srv, text="🌐", font=ctk.CTkFont(size=18), text_color="#2fe091")
        lbl_srv_ico.pack(side="left", anchor="center")

        box_srv = ctk.CTkFrame(sec_srv, fg_color="transparent")
        box_srv.pack(side="right", anchor="e")

        self.lbl_server_stt = ctk.CTkLabel(
            box_srv,
            text="Ping OK",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#2fe091",
            anchor="e"
        )
        self.lbl_server_stt.pack(anchor="e")

        self.lbl_server_ip = ctk.CTkLabel(
            box_srv,
            text="192.168.190.187",
            font=ctk.CTkFont(size=11),
            text_color="#ffffff",
            anchor="e"
        )
        self.lbl_server_ip.pack(anchor="e")

        lbl_srv_sub = ctk.CTkLabel(
            box_srv,
            text="Servidor Coletor",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#ffffff",
            anchor="e"
        )
        lbl_srv_sub.pack(anchor="e")

        block_srv.bind_recursive()
        self._add_noc_divider(self.scroll_noc)

        # 8. OLT Principal
        block_olt = NocSectionBlock(self.scroll_noc, self._noc_hover_mgr)
        sec_olt = ctk.CTkFrame(block_olt.frame, fg_color="transparent")
        sec_olt.pack(fill="x", padx=16, pady=(10, 8))

        if self._img_db:
            lbl_olt_ico = ctk.CTkLabel(sec_olt, image=self._img_db, text="")
        else:
            lbl_olt_ico = ctk.CTkLabel(sec_olt, text="💾", font=ctk.CTkFont(size=18), text_color="#ffffff")
        lbl_olt_ico.pack(side="left", anchor="center")

        box_olt = ctk.CTkFrame(sec_olt, fg_color="transparent")
        box_olt.pack(side="right", anchor="e")

        self.lbl_olt_model = ctk.CTkLabel(
            box_olt,
            text="C-Data FD1108S",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff",
            anchor="e"
        )
        self.lbl_olt_model.pack(anchor="e")

        self.lbl_olt_ip = ctk.CTkLabel(
            box_olt,
            text="192.168.1.100",
            font=ctk.CTkFont(size=11),
            text_color="#ffffff",
            anchor="e"
        )
        self.lbl_olt_ip.pack(anchor="e")

        lbl_olt_sub = ctk.CTkLabel(
            box_olt,
            text="OLT Principal",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#ffffff",
            anchor="e"
        )
        lbl_olt_sub.pack(anchor="e")

        block_olt.bind_recursive()

        # Rodapé da Sidebar: Divisor e Auto-Refresh elegante
        self._add_noc_divider(self.sidebar_frame)

        self.noc_footer = ctk.CTkFrame(self.sidebar_frame, fg_color="#205fa8", corner_radius=8, height=32)
        self.noc_footer.pack(side="bottom", fill="x", padx=8, pady=(4, 6))
        self.noc_footer.pack_propagate(False)

        self.chk_autorefresh = ctk.CTkSwitch(
            self.noc_footer,
            text="Auto-refresh (10s)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ffffff",
            progress_color="#2fe091",
            button_color="#ffffff",
            button_hover_color="#e0e0e0",
            switch_width=34,
            switch_height=18,
            command=self._on_autorefresh_toggle
        )
        self.chk_autorefresh.select()
        self.chk_autorefresh.pack(side="left", padx=8)

        # Aliases para compatibilidade legada
        self.card_total = self.lbl_total_val
        self.card_online = self.lbl_status_online
        self.card_offline = self.lbl_status_offline
        self.card_cams = self.lbl_cams_val
        self.lbl_port_s1p1 = self.lbl_p1_val
        self.lbl_port_s2p1 = self.lbl_p2_val
        self.lbl_port_s2p2 = self.lbl_p3_val
        self.lbl_sidebar_time = None
        self.lbl_sidebar_refresh = None

    def _create_pon_row(self, parent, name: str, default_val: str):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        lbl_n = ctk.CTkLabel(row, text=name, font=ctk.CTkFont(size=11), text_color="#ffffff")
        lbl_n.pack(side="left")
        lbl_v = ctk.CTkLabel(row, text=default_val, font=ctk.CTkFont(size=12, weight="bold"), text_color="#ffffff")
        lbl_v.pack(side="right")
        return lbl_v

    # =========================================================================
    # ATUALIZAÇÃO E RENDERIZAÇÃO DOS DADOS
    # =========================================================================
    def _on_data_updated(self):
        """Disparado quando o AjinManager tem novos dados em cache/servidor."""
        try:
            self.event_generate("<<AjinDataUpdated>>", when="tail")
        except Exception:
            pass

    def _process_incoming_data(self):
        data = self.mgr.get_data()
        self._raw_rows = data.get("rows", [])
        
        # 1. Atualiza métricas da Sidebar
        total = data.get("total", len(self._raw_rows))
        online = data.get("online", 0)
        offline = data.get("offline", 0)
        cams = data.get("total_cameras", 0)

        self.lbl_total_val.configure(text=str(total))
        self.lbl_status_online.configure(text=str(online))
        self.lbl_status_offline.configure(text=str(offline))
        if getattr(self, "lbl_cams_val", None):
            self.lbl_cams_val.configure(text=str(cams))

        # Portas PON (converte lista de dicts da API em dict indexado)
        raw_ports = data.get("ports", [])
        if isinstance(raw_ports, list):
            ports = {p.get("port"): p for p in raw_ports if isinstance(p, dict)}
        elif isinstance(raw_ports, dict):
            ports = raw_ports
        else:
            ports = {}

        if "Slot1-PON1" in ports:
            p = ports["Slot1-PON1"]
            self.lbl_p1_val.configure(text=f"{p.get('online', 0)} / {p.get('total', 0)}")
        if "Slot2-PON1" in ports:
            p = ports["Slot2-PON1"]
            self.lbl_p2_val.configure(text=f"{p.get('online', 0)} / {p.get('total', 0)}")
        if "Slot2-PON2" in ports:
            p = ports["Slot2-PON2"]
            self.lbl_p3_val.configure(text=f"{p.get('online', 0)} / {p.get('total', 0)}")

        # Horário da última coleta
        coleta_str = str(data.get("coleta_formatted", ""))
        m = re.search(r"(\d{2}/\d{2}/\d{4}).*?(\d{2}:\d{2}:\d{2})", coleta_str)
        if m:
            d_part, t_part = m.group(1), m.group(2)
            self.lbl_coleta_time.configure(text=t_part)
            self.lbl_coleta_date.configure(text=d_part)
        elif coleta_str and coleta_str != "-":
            self.lbl_coleta_time.configure(text=coleta_str)

        # Status Hub e OLT (se os widgets estiverem ativos)
        srv_info = data.get("server", {})
        if isinstance(srv_info, dict) and hasattr(self, "lbl_server_stt") and self.lbl_server_stt:
            if srv_info.get("online"):
                self.lbl_server_stt.configure(text="Ping OK", text_color="#2fe091")
            else:
                self.lbl_server_stt.configure(text="Sem Ping", text_color="#ff8a80")
            if srv_info.get("ip") and self.lbl_server_ip:
                self.lbl_server_ip.configure(text=str(srv_info.get("ip")))

        olt_info = data.get("olt", {})
        if isinstance(olt_info, dict) and hasattr(self, "lbl_olt_model") and self.lbl_olt_model:
            if olt_info.get("modelo"):
                self.lbl_olt_model.configure(text=str(olt_info.get("modelo")))
            if olt_info.get("ip") and self.lbl_olt_ip:
                self.lbl_olt_ip.configure(text=str(olt_info.get("ip")))

        # Botão de incidentes
        active_raw = data.get("active_problems", offline)
        if isinstance(active_raw, list):
            active_count = len(active_raw)
        elif isinstance(active_raw, (int, float)):
            active_count = int(active_raw)
        else:
            active_count = offline
        self.btn_events.configure(text=f"⚠️ Incidentes & Eventos ({active_count})")

        # 2. Aplica filtros e renderiza linhas na tabela
        self._apply_filters()

    def _apply_filters(self):
        query = self.entry_search.get().strip().lower()
        selected_pon = self.combo_pon.get()
        selected_status = self.combo_status.get()
        offline_only = False

        filtered = []
        for r in self._raw_rows:
            # Filtro de busca textual (Nome, serial, rua, cameras)
            if query:
                name_match = query in str(r.get("name", "")).lower()
                ser_match = query in str(r.get("serial", "")).lower()
                desc_match = query in str(r.get("desc", "")).lower()
                cam_match = any(query in str(c.get("ip", "")).lower() for c in r.get("cameras", []))
                if not (name_match or ser_match or desc_match or cam_match):
                    continue

            # Filtro PON
            if selected_pon != "Todas as Portas PON":
                if r.get("port") != selected_pon:
                    continue

            # Filtro Status
            if selected_status == "Em Funcionamento (Online)" and r.get("status") != "Online":
                continue
            if selected_status == "Fora de Funcionamento (Offline)" and r.get("status") == "Online":
                continue
            if offline_only and r.get("status") == "Online":
                continue

            filtered.append(r)

        # Ordenação
        def _get_sort_val(row):
            k = self._sort_col
            if k == "status":
                # Offline primeiro quando ascendente (como no print)
                return 0 if row.get("status") != "Online" else 1
            if k == "name":
                return str(row.get("name") or "")
            if k == "uptime":
                return row.get("uptime_seconds", 0)
            return str(row.get(k, ""))

        filtered.sort(key=_get_sort_val, reverse=not self._sort_ascending)
        self._filtered_rows = filtered

        # Atualiza contador no rodapé
        self.lbl_counter.configure(text=f"{len(filtered)} de {len(self._raw_rows)} dispositivos")

        # Renderiza linhas da tabela
        self._render_table_rows()

    def _on_scrollbar_command(self, action, val, *args):
        total = len(self._filtered_rows)
        if total <= self.VISIBLE_ROWS:
            return
        if action == "moveto":
            target = int(round(float(val) * total))
            self._set_scroll_offset(target)
        elif action == "scroll":
            delta = int(val)
            self._set_scroll_offset(self._scroll_offset + delta)

    def _on_table_mousewheel(self, e):
        total = len(self._filtered_rows)
        if total <= self.VISIBLE_ROWS:
            return
        if hasattr(e, "delta") and e.delta:
            delta = -1 if e.delta > 0 else 1
        elif getattr(e, "num", None) == 4:
            delta = -1
        elif getattr(e, "num", None) == 5:
            delta = 1
        else:
            delta = 0
        self._set_scroll_offset(self._scroll_offset + (delta * 2))

    def _on_table_resize(self, e=None):
        if self._resize_debounce_job:
            try:
                self.after_cancel(self._resize_debounce_job)
            except Exception:
                pass
        self._resize_debounce_job = self.after(50, self._handle_table_resize)

    def _handle_table_resize(self):
        self._resize_debounce_job = None
        avail_h = self.table_viewport_frame.winfo_height()
        if avail_h > 50:
            new_visible = min(len(self._row_pool), max(5, avail_h // self.ROW_HEIGHT))
            if new_visible != self.VISIBLE_ROWS:
                self.VISIBLE_ROWS = new_visible
        self._render_table_rows()

    def _set_scroll_offset(self, target_offset: int):
        total = len(self._filtered_rows)
        if total <= self.VISIBLE_ROWS:
            target_offset = 0
        else:
            target_offset = max(0, min(target_offset, total - self.VISIBLE_ROWS))

        if target_offset == self._scroll_offset and getattr(self, "_rendered_once", False):
            return

        self._rendered_once = True
        self._scroll_offset = target_offset
        self._render_table_rows()

    def _render_table_rows(self):
        """Atualização pura de textos em rótulos nativos em < 0.1ms sem mover nenhum widget."""
        total = len(self._filtered_rows)
        max_offset = max(0, total - self.VISIBLE_ROWS)
        if self._scroll_offset > max_offset:
            self._scroll_offset = max_offset

        offset = self._scroll_offset
        display_count = min(self.VISIBLE_ROWS, total)

        for i in range(display_count):
            data_idx = offset + i
            item = self._row_pool[i]
            if data_idx < total:
                r = self._filtered_rows[data_idx]
                item.update_data(r, show_olt=True)
                if not item.frame.winfo_ismapped():
                    item.frame.pack(fill="x", pady=1)
            else:
                if item.frame.winfo_ismapped():
                    item.frame.pack_forget()

        # Oculta linhas excedentes do pool
        for i in range(display_count, len(self._row_pool)):
            item = self._row_pool[i]
            if item.frame.winfo_ismapped():
                item.frame.pack_forget()

        # Sincroniza barra de rolagem CustomTkinter
        if total <= self.VISIBLE_ROWS:
            self.table_scrollbar.set(0.0, 1.0)
        else:
            start = offset / total
            end = min(1.0, (offset + self.VISIBLE_ROWS) / total)
            self.table_scrollbar.set(start, end)

    # =========================================================================
    # DIÁLOGOS E MODAIS (EDIÇÃO, MENU, SCANNER, EVENTOS)
    # =========================================================================
    def _open_edit_dialog(self, row: Dict[str, Any]):
        """Diálogo nativo para editar Nome do Ponto e Rua."""
        port = row.get("port")
        oid = str(row.get("id"))
        cur_name = row.get("name") or ""
        cur_desc = row.get("desc") or ""

        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Editar ONU - {port} | ID {oid}")
        dlg.geometry("440x260")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        # Centraliza modal
        try:
            dlg.geometry("+%d+%d" % (self.winfo_rootx() + 100, self.winfo_rooty() + 80))
        except Exception:
            pass

        pad = 16
        lbl_info = ctk.CTkLabel(dlg, text=f"Configuração do Ponto ({row.get('serial')})", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_info.pack(anchor="w", padx=pad, pady=(pad, 10))

        # Nome do Ponto
        lbl_n = ctk.CTkLabel(dlg, text="Nome do Ponto:", font=ctk.CTkFont(size=12))
        lbl_n.pack(anchor="w", padx=pad)
        entry_name = ctk.CTkEntry(dlg, width=400, height=32)
        entry_name.insert(0, cur_name)
        entry_name.pack(padx=pad, pady=(2, 10))

        # Descrição da Rua
        lbl_d = ctk.CTkLabel(dlg, text="Rua / Local / Descrição:", font=ctk.CTkFont(size=12))
        lbl_d.pack(anchor="w", padx=pad)
        entry_desc = ctk.CTkEntry(dlg, width=400, height=32)
        entry_desc.insert(0, cur_desc)
        entry_desc.pack(padx=pad, pady=(2, 16))

        # Botões
        b_box = ctk.CTkFrame(dlg, fg_color="transparent")
        b_box.pack(fill="x", padx=pad)

        def _save():
            new_name = entry_name.get().strip()
            new_desc = entry_desc.get().strip()
            dlg.destroy()
            threading.Thread(target=lambda: self.mgr.update_label(port, oid, new_name, new_desc), daemon=True).start()

        btn_save = ctk.CTkButton(b_box, text="Salvar Alterações", fg_color="#0066cc", hover_color="#0052a3", command=_save)
        btn_save.pack(side="right")

        btn_cancel = ctk.CTkButton(b_box, text="Cancelar", fg_color="transparent", text_color=("gray20", "#bdc3c7"), command=dlg.destroy)
        btn_cancel.pack(side="right", padx=8)

    def _open_menu_dialog(self, row: Dict[str, Any]):
        """Diálogo do [🔍 Menu] detalhado com câmeras, ping e histórico."""
        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Detalhes da ONU - {row.get('name', 'Ponto')}")
        dlg.geometry("520x420")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        pad = 16
        lbl_t = ctk.CTkLabel(dlg, text=f"ONU: {row.get('name', '')} ({row.get('port')})", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_t.pack(anchor="w", padx=pad, pady=(pad, 4))

        lbl_s = ctk.CTkLabel(dlg, text=f"Serial: {row.get('serial')} | Fabricante: {row.get('vendor')} | Status: {row.get('status')}", font=ctk.CTkFont(size=11), text_color="#bdc3c7")
        lbl_s.pack(anchor="w", padx=pad, pady=(0, 10))

        # Detalhes de Uptime
        box_up = ctk.CTkFrame(dlg, fg_color=("#f1f5f9", "#181a22"), corner_radius=6)
        box_up.pack(fill="x", padx=pad, pady=(0, 10))
        lbl_u1 = ctk.CTkLabel(box_up, text=f"⏱️ Tempo Contínuo: {row.get('uptime_detailed', row.get('uptime', '-'))}", font=ctk.CTkFont(size=11))
        lbl_u1.pack(anchor="w", padx=10, pady=4)
        lbl_u2 = ctk.CTkLabel(box_up, text=f"📅 Desde: {row.get('status_since', '-')}", font=ctk.CTkFont(size=11), text_color="#95a5a6")
        lbl_u2.pack(anchor="w", padx=10, pady=(0, 4))

        # Câmeras Conectadas
        lbl_c_title = ctk.CTkLabel(dlg, text="📷 Câmeras Detectadas nas Portas LAN:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_c_title.pack(anchor="w", padx=pad, pady=(4, 4))

        cams = row.get("cameras", [])
        if not cams:
            lbl_no_cams = ctk.CTkLabel(dlg, text="Nenhuma câmera IP mapeada via ARP nesta ONU.", font=ctk.CTkFont(size=11, slant="italic"), text_color="#7f8c8d")
            lbl_no_cams.pack(anchor="w", padx=pad, pady=4)
        else:
            box_cams = ctk.CTkFrame(dlg, fg_color=("#f1f5f9", "#181a22"), corner_radius=6)
            box_cams.pack(fill="x", padx=pad, pady=4)
            for c in cams:
                c_ip = c.get("ip", "")
                c_mac = c.get("mac", "")
                c_row = ctk.CTkFrame(box_cams, fg_color="transparent")
                c_row.pack(fill="x", padx=10, pady=4)
                lbl_cip = ctk.CTkLabel(c_row, text=f"IP: {c_ip}  (MAC: {c_mac})", font=ctk.CTkFont(family="Consolas", size=11))
                lbl_cip.pack(side="left")

                def _ping(ip=c_ip):
                    ok = self.mgr.ping_camera(ip)
                    msg = f"Câmera {ip}: ONLINE ✅" if ok else f"Câmera {ip}: SEM RESPOSTA ❌"
                    messagebox.showinfo("Teste de Ping", msg, parent=dlg)

                btn_ping = ctk.CTkButton(c_row, text="Ping Test", width=70, height=22, font=ctk.CTkFont(size=10), command=_ping)
                btn_ping.pack(side="right")

        # Botão Fechar
        btn_close = ctk.CTkButton(dlg, text="Fechar", width=90, fg_color=("#e2e8f0", "#262832"), text_color=("gray10", "#ffffff"), command=dlg.destroy)
        btn_close.pack(side="bottom", pady=pad)

    def _open_scanner_dialog(self):
        """Diálogo do Scanner de ONUs (dispositivos descobertos)."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Scanner de ONUs - Rede Ajin")
        dlg.geometry("560x380")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        pad = 16
        lbl_t = ctk.CTkLabel(dlg, text="🔍 Scanner de Novos Dispositivos Ópticos", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_t.pack(anchor="w", padx=pad, pady=(pad, 4))

        lbl_sub = ctk.CTkLabel(dlg, text="Equipamentos conectados na fibra da OLT que ainda não foram homologados:", font=ctk.CTkFont(size=11), text_color="#bdc3c7")
        lbl_sub.pack(anchor="w", padx=pad, pady=(0, 10))

        data = self.mgr.get_data()
        scanner = data.get("unregistered", [])
        if not scanner:
            lbl_empty = ctk.CTkLabel(dlg, text="Nenhuma nova ONU detectada na fibra no momento. Tudo homologado! ✅", font=ctk.CTkFont(size=12), text_color="#2ecc71")
            lbl_empty.pack(pady=40)
        else:
            scroll = ctk.CTkScrollableFrame(dlg, height=220)
            scroll.pack(fill="both", expand=True, padx=pad, pady=4)
            for item in scanner:
                rf = ctk.CTkFrame(scroll, height=36, fg_color=("#f1f5f9", "#181a22"))
                rf.pack(fill="x", pady=2)
                rf.pack_propagate(False)

                p_str = f"{item.get('port')} (ID {item.get('id')})"
                lbl_it = ctk.CTkLabel(rf, text=f"{p_str} - MAC: {item.get('serial', '-')}", font=ctk.CTkFont(family="Consolas", size=11))
                lbl_it.pack(side="left", padx=10)

                def _homologar(it=item):
                    self._open_edit_dialog(it)
                    dlg.destroy()

                btn_hom = ctk.CTkButton(rf, text="+ Homologar", width=90, height=24, fg_color="#0066cc", hover_color="#0052a3", font=ctk.CTkFont(size=10, weight="bold"), command=_homologar)
                btn_hom.pack(side="right", padx=10)

        btn_close = ctk.CTkButton(dlg, text="Fechar", width=90, fg_color=("#e2e8f0", "#262832"), text_color=("gray10", "#ffffff"), command=dlg.destroy)
        btn_close.pack(side="bottom", pady=pad)

    def _open_events_dialog(self):
        """Diálogo de histórico de Incidentes & Eventos (NOC)."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Incidentes & Eventos Recentes - NOC Ajin")
        dlg.geometry("640x440")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        pad = 16
        lbl_t = ctk.CTkLabel(dlg, text="⚠️ Histórico de Quedas e Incidentes", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_t.pack(anchor="w", padx=pad, pady=(pad, 4))

        data = self.mgr.get_data()
        active_list = data.get("active_problems", [])
        if not isinstance(active_list, list):
            active_list = []
        events = data.get("events_history", data.get("events", []))
        if not isinstance(events, list):
            events = []

        if not active_list and not events:
            lbl_empty = ctk.CTkLabel(dlg, text="Nenhum incidente registrado recentemente. Rede estável! ✅", font=ctk.CTkFont(size=12), text_color="#2ecc71")
            lbl_empty.pack(pady=40)
        else:
            scroll = ctk.CTkScrollableFrame(dlg, height=290)
            scroll.pack(fill="both", expand=True, padx=pad, pady=4)

            # 1. Problemas ativos atualmente
            for a in active_list:
                rf = ctk.CTkFrame(scroll, height=38, fg_color=("#fee2e2", "#2e1818"))
                rf.pack(fill="x", pady=2)
                rf.pack_propagate(False)

                lbl_badge = ctk.CTkLabel(rf, text="🔴 Offline", font=ctk.CTkFont(size=10, weight="bold"), text_color="#e74c3c", width=70)
                lbl_badge.pack(side="left", padx=6)

                p_str = a.get("point_name") or a.get("label") or f"{a.get('port')}_{a.get('onu_id')}"
                dt_str = a.get("duration_detailed") or a.get("since") or a.get("duration", "ativo")
                lbl_info = ctk.CTkLabel(rf, text=f"{p_str} ({a.get('serial', '')}) - {dt_str}", font=ctk.CTkFont(size=11, weight="bold"))
                lbl_info.pack(side="left", padx=6)

            # 2. Histórico recente de quedas e retornos
            for e in events[:30]:
                rf = ctk.CTkFrame(scroll, height=38, fg_color=("#f1f5f9", "#181a22"))
                rf.pack(fill="x", pady=2)
                rf.pack_propagate(False)

                is_fall = (e.get("type") == "fell")
                badge_txt = "🔴 Queda" if is_fall else "🟢 Retorno"
                badge_col = "#e74c3c" if is_fall else "#2ecc71"
                lbl_badge = ctk.CTkLabel(rf, text=badge_txt, font=ctk.CTkFont(size=10, weight="bold"), text_color=badge_col, width=70)
                lbl_badge.pack(side="left", padx=6)

                p_str = e.get("name") or e.get("point_name") or f"{e.get('port')}_{e.get('id')}"
                dt_str = e.get("datetime") or e.get("time") or "-"
                lbl_info = ctk.CTkLabel(rf, text=f"{p_str} ({e.get('serial', '')}) - {dt_str}", font=ctk.CTkFont(size=11))
                lbl_info.pack(side="left", padx=6)

        btn_close = ctk.CTkButton(dlg, text="Fechar", width=90, fg_color=("#e2e8f0", "#262832"), text_color=("gray10", "#ffffff"), command=dlg.destroy)
        btn_close.pack(side="bottom", pady=pad)

    def _on_delete_onu(self, row: Dict[str, Any]):
        port = row.get("port")
        oid = str(row.get("id"))
        p_name = row.get("name") or f"{port}_{oid}"

        if messagebox.askyesno("Confirmar Exclusão", f"Deseja realmente ignorar/remover o '{p_name}' do monitoramento?", parent=self.winfo_toplevel()):
            threading.Thread(target=lambda: self.mgr.delete_onu(port, oid), daemon=True).start()

    def _on_sync_cameras_clicked(self):
        self.btn_sync_cams.configure(text="Sincronizando...", state="disabled")
        def _worker():
            self.mgr.trigger_camera_sync()
            self.after(0, lambda: self.btn_sync_cams.configure(text="📹 Atualizar Câmeras", state="normal"))
        threading.Thread(target=_worker, daemon=True).start()

    def _on_manual_refresh_clicked(self):
        self.btn_refresh.configure(text="...", state="disabled")
        self.mgr.fetch_telemetry_async(force=True, callback=lambda ok: self.after(0, lambda: self.btn_refresh.configure(text="Atualizar", state="normal")))

    def _on_export_clicked(self):
        filepath = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            initialfile=f"onus_ajin_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if filepath:
            ok = self.mgr.export_csv(filepath)
            if ok:
                messagebox.showinfo("Exportação Concluída", f"Relatório salvo com sucesso em:\n{filepath}", parent=self.winfo_toplevel())
            else:
                messagebox.showerror("Erro na Exportação", "Não foi possível exportar os dados para CSV.", parent=self.winfo_toplevel())

    def _on_autorefresh_toggle(self):
        self._auto_refresh_enabled = bool(self.chk_autorefresh.get())
        if not self._auto_refresh_enabled:
            self.chk_autorefresh.configure(text="Auto-refresh (Pausado)")
        else:
            self.chk_autorefresh.configure(text=f"Auto-refresh ({self._refresh_countdown}s)")

    def _schedule_countdown(self):
        """Atualiza o relógio da barra inferior e o contador do refresh a cada segundo."""
        now_str = datetime.now().strftime("%H:%M:%S")
        if self._auto_refresh_enabled:
            self._refresh_countdown -= 1
            if self._refresh_countdown <= 0:
                self._refresh_countdown = 10
                self.mgr.fetch_telemetry_async()
            if hasattr(self, "chk_autorefresh") and self.chk_autorefresh:
                self.chk_autorefresh.configure(text=f"Auto-refresh ({self._refresh_countdown}s)")
        else:
            if hasattr(self, "chk_autorefresh") and self.chk_autorefresh:
                self.chk_autorefresh.configure(text="Auto-refresh (Pausado)")

        if hasattr(self, "lbl_timer_status") and self.lbl_timer_status:
            self.lbl_timer_status.configure(text=f"Hora: {now_str}")

        self.after(1000, self._schedule_countdown)
