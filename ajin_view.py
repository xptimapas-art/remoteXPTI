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
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).parent / relative_path


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

        # 1. Campo de Busca
        self.entry_search = ctk.CTkEntry(
            ctrl_frame,
            placeholder_text="🔍 Pesquisar por Nome, Serial / MAC...",
            width=230,
            height=34,
            fg_color="#181c26",
            border_color="#2e3547",
            text_color="#ffffff"
        )
        self.entry_search.pack(side="left", padx=(0, 6))
        self.entry_search.bind("<KeyRelease>", lambda e: self._apply_filters())

        # 2. Filtro de Portas PON
        self.combo_pon = ctk.CTkComboBox(
            ctrl_frame,
            values=["Todas as Portas PON", "Slot1-PON1", "Slot1-PON2", "Slot2-PON1", "Slot2-PON2"],
            width=140,
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
            text="🔄 Câmeras",
            width=115,
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
            text="🔍 Scanner",
            width=115,
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
            text="⚠️ Incidentes (0)",
            width=140,
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

        # Cabeçalho Fixo com as 8 Colunas Exatas
        self.header_frame = ctk.CTkFrame(
            self.table_container,
            height=36,
            corner_radius=0,
            fg_color="#1a1e2b"
        )
        self.header_frame.grid(row=0, column=0, sticky="ew")
        self.header_frame.grid_propagate(False)

        headers = [
            ("Nome (Ponto)", 135, "name"),
            ("Status", 115, "status"),
            ("Endereço / Serial", 135, "serial"),
            ("Descrição (Rua / Local)", 225, "desc"),
            ("Fabricante", 100, "vendor"),
            ("Tempo no Status", 110, "uptime"),
            ("Canal OLT", 120, "port"),
            ("Ações", 80, None)
        ]

        self._header_buttons = {}
        for text, width, sort_key in headers:
            if sort_key:
                initial_text = f"{text} ▲" if sort_key == self._sort_col else text
                initial_color = "#38bdf8" if sort_key == self._sort_col else "#94a3b8"
                btn = ctk.CTkButton(
                    self.header_frame,
                    text=initial_text,
                    width=width,
                    height=32,
                    fg_color="transparent",
                    text_color=initial_color,
                    hover_color="#252c3d",
                    anchor="w",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    command=lambda k=sort_key: self._on_column_sort(k)
                )
                btn._base_title = text
                btn.pack(side="left", padx=4)
                self._header_buttons[sort_key] = btn
            else:
                lbl = ctk.CTkLabel(
                    self.header_frame,
                    text=text,
                    width=width,
                    anchor="w",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="#94a3b8"
                )
                lbl.pack(side="left", padx=4)

        # Área de rolagem das linhas
        self.scroll_table = ctk.CTkScrollableFrame(self.table_container, fg_color="transparent")
        self.scroll_table.grid(row=1, column=0, sticky="nsew", padx=2, pady=2)
        self.scroll_table.grid_columnconfigure(0, weight=1)

        # Cache de widgets de linhas para atualização instantânea sem lag
        self._row_frames: List[ctk.CTkFrame] = []

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
        """Divisor horizontal sutil de 1px entre seções no padrão clean."""
        div = ctk.CTkFrame(parent, height=1, fg_color="#4f8ecc", corner_radius=0)
        div.pack(fill="x", padx=12, pady=1)
        return div

    def _create_noc_stat_section(self, parent, icon_img, val_str, label_str):
        """Cria uma seção de métrica clean: ícone à esquerda, número grande e rótulo à direita."""
        sec = ctk.CTkFrame(parent, fg_color="transparent")
        sec.pack(fill="x", padx=10, pady=(6, 5))

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

        return lbl_val, lbl_sub

    def _build_sidebar_noc(self):
        # Painel lateral azul (#2870c2) com bordas arredondadas e responsividade
        self.sidebar_frame = ctk.CTkFrame(
            self,
            width=240,
            corner_radius=12,
            fg_color="#2870c2",
            border_width=0
        )
        self.sidebar_frame.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=(4, 6))
        self.sidebar_frame.grid_propagate(False)

        # Pré-carrega os ícones nativos
        self._img_router = self._load_noc_icon("noc_router", (34, 30))
        self._img_check = self._load_noc_icon("noc_check", (34, 34))
        self._img_cross = self._load_noc_icon("noc_cross", (34, 34))
        self._img_cam = self._load_noc_icon("noc_cam", (34, 24))
        self._img_pon = self._load_noc_icon("noc_pon", (26, 26))
        self._img_clock = self._load_noc_icon("noc_clock", (32, 32))
        self._img_globe = self._load_noc_icon("noc_globe", (30, 31))
        self._img_db = self._load_noc_icon("noc_db", (26, 28))

        # Área de Conteúdo Rolável Responsiva (Adapta-se a qualquer resolução de tela ou redimensionamento)
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
        self.scroll_noc.pack(side="top", fill="both", expand=True, padx=4, pady=4)

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

        # 4. Portas PON
        sec_pon = ctk.CTkFrame(self.scroll_noc, fg_color="transparent")
        sec_pon.pack(fill="x", padx=10, pady=(3, 2))

        top_pon = ctk.CTkFrame(sec_pon, fg_color="transparent")
        top_pon.pack(fill="x", pady=(0, 2))

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

        self._add_noc_divider(self.scroll_noc)

        # 5. Última Coleta
        sec_coleta = ctk.CTkFrame(self.scroll_noc, fg_color="transparent")
        sec_coleta.pack(fill="x", padx=10, pady=(3, 2))

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

        # Switch de Auto-Refresh na Sidebar
        row_refresh = ctk.CTkFrame(self.scroll_noc, fg_color="transparent")
        row_refresh.pack(fill="x", padx=12, pady=(0, 4))

        self.chk_autorefresh = ctk.CTkSwitch(
            row_refresh,
            text="Auto-refresh (10s)",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#ffffff",
            progress_color="#2fe091",
            button_color="#ffffff",
            button_hover_color="#e0e0e0",
            switch_width=32,
            switch_height=16,
            command=self._on_autorefresh_toggle
        )
        self.chk_autorefresh.select()
        self.chk_autorefresh.pack(side="right")

        self._add_noc_divider(self.scroll_noc)

        # 6. Servidor Coletor (Status da Coleta)
        sec_srv = ctk.CTkFrame(self.scroll_noc, fg_color="transparent")
        sec_srv.pack(fill="x", padx=10, pady=(3, 2))

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

        self._add_noc_divider(self.scroll_noc)

        # 7. OLT Principal
        sec_olt = ctk.CTkFrame(self.scroll_noc, fg_color="transparent")
        sec_olt.pack(fill="x", padx=10, pady=(3, 2))

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

        # Aliases para compatibilidade legada
        self.card_total = self.lbl_total_val
        self.card_online = self.lbl_status_online
        self.card_offline = self.lbl_status_offline
        self.card_cams = None
        self.lbl_cams_val = None
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
                self.lbl_server_stt.configure(text="Sem Ping", text_color="#ff5252")
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
        self.btn_events.configure(text=f"⚠️ Incidentes ({active_count})")

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

    def _render_table_rows(self):
        # Limpa linhas anteriores
        for rf in self._row_frames:
            rf.destroy()
        self._row_frames.clear()

        show_cams = False
        show_olt = True

        for idx, r in enumerate(self._filtered_rows):
            is_even = (idx % 2 == 0)
            row_bg = "#181c27" if is_even else "#141721"

            row_frame = ctk.CTkFrame(self.scroll_table, height=38, corner_radius=4, fg_color=row_bg)
            row_frame.pack(fill="x", pady=1)
            row_frame.pack_propagate(False)

            # Coluna 1: Nome (Ponto) + Badge 2P + Lápis ✏️ (width 135)
            c1 = ctk.CTkFrame(row_frame, width=135, fg_color="transparent")
            c1.pack(side="left", padx=4)
            c1.pack_propagate(False)

            p_name = r.get("name") or "--"
            lbl_p = ctk.CTkLabel(
                c1,
                text=f"🖧 {p_name}",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#ffffff"
            )
            lbl_p.pack(side="left", padx=(0, 4))

            if r.get("multi_llid"):
                badge_2p = ctk.CTkLabel(
                    c1,
                    text="2P",
                    font=ctk.CTkFont(size=9, weight="bold"),
                    text_color="#38bdf8",
                    fg_color="#0f2b48",
                    corner_radius=3,
                    width=22,
                    height=16
                )
                badge_2p.pack(side="left", padx=(0, 4))

            btn_edit_name = ctk.CTkButton(
                c1,
                text="✏️",
                width=20,
                height=20,
                fg_color="transparent",
                hover_color="#282f42",
                font=ctk.CTkFont(size=10),
                command=lambda row=r: self._open_edit_dialog(row)
            )
            btn_edit_name.pack(side="left")

            # Coluna 2: Status (width 115) - Badge Profissional NOC Clean
            c2 = ctk.CTkFrame(row_frame, width=115, fg_color="transparent")
            c2.pack(side="left", padx=4)
            c2.pack_propagate(False)

            is_online = (r.get("status") == "Online")
            if is_online:
                lbl_stt = ctk.CTkLabel(
                    c2,
                    text="● Online",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="#4ade80",
                    fg_color="#0d2e1c",
                    corner_radius=10,
                    width=68,
                    height=22
                )
            else:
                lbl_stt = ctk.CTkLabel(
                    c2,
                    text="● Offline",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="#f87171",
                    fg_color="#3c1418",
                    corner_radius=10,
                    width=70,
                    height=22
                )
            lbl_stt.pack(side="left")

            # Coluna 3: Endereço / Serial (MAC) (width 135)
            c3 = ctk.CTkFrame(row_frame, width=135, fg_color="transparent")
            c3.pack(side="left", padx=4)
            c3.pack_propagate(False)
            lbl_ser = ctk.CTkLabel(
                c3,
                text=r.get("serial", "-"),
                font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                text_color="#cbd5e1"
            )
            lbl_ser.pack(side="left")

            # Coluna 4: Descrição (Rua / Local) + Lápis ✏️ (width 225)
            c4 = ctk.CTkFrame(row_frame, width=225, fg_color="transparent")
            c4.pack(side="left", padx=4)
            c4.pack_propagate(False)

            p_desc = r.get("desc") or ""
            if not p_desc:
                lbl_desc = ctk.CTkLabel(
                    c4,
                    text="+ adicionar rua",
                    font=ctk.CTkFont(size=10, slant="italic"),
                    text_color="#64748b"
                )
            else:
                lbl_desc = ctk.CTkLabel(
                    c4,
                    text=p_desc,
                    font=ctk.CTkFont(size=11),
                    text_color="#f1f5f9"
                )
            lbl_desc.pack(side="left", padx=(0, 4))

            btn_edit_desc = ctk.CTkButton(
                c4,
                text="✏️",
                width=20,
                height=20,
                fg_color="transparent",
                hover_color="#282f42",
                font=ctk.CTkFont(size=10),
                command=lambda row=r: self._open_edit_dialog(row)
            )
            btn_edit_desc.pack(side="left")

            # Coluna 5: Fabricante (width 100)
            c5 = ctk.CTkFrame(row_frame, width=100, fg_color="transparent")
            c5.pack(side="left", padx=4)
            c5.pack_propagate(False)

            lbl_vendor = ctk.CTkLabel(
                c5,
                text=r.get("vendor", "-"),
                font=ctk.CTkFont(size=11),
                text_color="#94a3b8"
            )
            lbl_vendor.pack(side="left")

            # Coluna 6: Tempo no Status (width 110)
            c6 = ctk.CTkFrame(row_frame, width=110, fg_color="transparent")
            c6.pack(side="left", padx=4)
            c6.pack_propagate(False)

            upt_txt = r.get("uptime") or "-"
            upt_col = "#f87171" if not is_online else "#94a3b8"
            upt_weight = "bold" if not is_online else "normal"
            lbl_upt = ctk.CTkLabel(
                c6,
                text=upt_txt,
                font=ctk.CTkFont(size=11, weight=upt_weight),
                text_color=upt_col
            )
            lbl_upt.pack(side="left")

            # Coluna 7: Canal OLT (width 120)
            c7 = ctk.CTkFrame(row_frame, width=120, fg_color="transparent")
            c7.pack(side="left", padx=4)
            c7.pack_propagate(False)

            canal_txt = f"{r.get('port')}_{str(r.get('id')).zfill(3)}" if show_olt else "--"
            lbl_canal = ctk.CTkLabel(
                c7,
                text=canal_txt,
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color="#cbd5e1"
            )
            lbl_canal.pack(side="left")

            # Coluna 8: Ações (width 80)
            c8 = ctk.CTkFrame(row_frame, width=80, fg_color="transparent")
            c8.pack(side="left", padx=4)
            c8.pack_propagate(False)

            btn_menu = ctk.CTkButton(
                c8,
                text="Menu",
                width=50,
                height=24,
                fg_color="#222736",
                hover_color="#30384c",
                border_width=1,
                border_color="#374151",
                text_color="#f1f5f9",
                font=ctk.CTkFont(size=10, weight="bold"),
                command=lambda row=r: self._open_menu_dialog(row)
            )
            btn_menu.pack(side="left", padx=(0, 4))

            btn_del = ctk.CTkButton(
                c8,
                text="🗑️",
                width=22,
                height=24,
                fg_color="transparent",
                hover_color="#3d1418",
                text_color="#f87171",
                font=ctk.CTkFont(size=11),
                command=lambda row=r: self._on_delete_onu(row)
            )
            btn_del.pack(side="left")

            self._row_frames.append(row_frame)

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
            self.after(0, lambda: self.btn_sync_cams.configure(text="🔄 Atualizar Câmeras", state="normal"))
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
