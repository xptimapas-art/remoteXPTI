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
from typing import Any, Dict, List, Optional
import webbrowser

import customtkinter as ctk
from PIL import Image

from ajin_manager import AjinManager
from logger import log


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
            placeholder_text="🔍 Pesquisar por Nome, Serial / MAC (LAN 1 ou...",
            width=260,
            height=34
        )
        self.entry_search.pack(side="left", padx=(0, 6))
        self.entry_search.bind("<KeyRelease>", lambda e: self._apply_filters())

        # 2. Filtro de Portas PON
        self.combo_pon = ctk.CTkComboBox(
            ctrl_frame,
            values=["Todas as Portas PON", "Slot1-PON1", "Slot1-PON2", "Slot2-PON1", "Slot2-PON2"],
            width=150,
            height=34,
            command=lambda val: self._apply_filters()
        )
        self.combo_pon.set("Todas as Portas PON")
        self.combo_pon.pack(side="left", padx=(0, 6))

        # 3. Filtro de Status
        self.combo_status = ctk.CTkComboBox(
            ctrl_frame,
            values=["Todos os Status", "Em Funcionamento (Online)", "Fora de Funcionamento (Offline)"],
            width=175,
            height=34,
            command=lambda val: self._apply_filters()
        )
        self.combo_status.set("Todos os Status")
        self.combo_status.pack(side="left", padx=(0, 8))

        # 4. Botão Atualizar Câmeras
        self.btn_sync_cams = ctk.CTkButton(
            ctrl_frame,
            text="🔄 Atualizar Câmeras",
            width=135,
            height=34,
            fg_color=("#e2e8f0", "#262832"),
            text_color=("gray10", "#ffffff"),
            hover_color=("#cbd5e1", "#343644"),
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_sync_cameras_clicked
        )
        self.btn_sync_cams.pack(side="left", padx=(0, 6))

        # 5. Botão Scanner de ONUs
        self.btn_scanner = ctk.CTkButton(
            ctrl_frame,
            text="🔍 Scanner de ONUs",
            width=130,
            height=34,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._open_scanner_dialog
        )
        self.btn_scanner.pack(side="left", padx=(0, 6))

        # 6. Botão Incidentes & Eventos (com badge)
        self.btn_events = ctk.CTkButton(
            ctrl_frame,
            text="⚠️ Incidentes & Eventos (0)",
            width=165,
            height=34,
            fg_color="#a83232",
            hover_color="#8c2828",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._open_events_dialog
        )
        self.btn_events.pack(side="left")

    # =========================================================================
    # TABELA PRINCIPAL DE DISPOSITIVOS (8 COLUNAS)
    # =========================================================================
    def _build_table_view(self):
        # Container da Tabela
        self.table_container = ctk.CTkFrame(self.left_panel, corner_radius=6, fg_color=("#f8fafc", "#16181f"), border_width=1, border_color=("#e2e8f0", "#232630"))
        self.table_container.grid(row=1, column=0, sticky="nsew")
        self.table_container.grid_rowconfigure(1, weight=1)
        self.table_container.grid_columnconfigure(0, weight=1)

        # Cabeçalho Fixo com as 8 Colunas Exatas
        self.header_frame = ctk.CTkFrame(self.table_container, height=36, corner_radius=0, fg_color=("#eef2f6", "#1c1f28"))
        self.header_frame.grid(row=0, column=0, sticky="ew")
        self.header_frame.grid_propagate(False)

        headers = [
            ("Nome (Ponto)", 140, "name"),
            ("Em Funcionamento 🔼", 145, "status"),
            ("Endereço / Serial", 130, "serial"),
            ("Descrição (Rua / Local)", 240, "desc"),
            ("Fabricante", 110, "vendor"),
            ("Tempo no Status", 120, "uptime"),
            ("Canal OLT", 130, "port"),
            ("Ações", 100, None)
        ]

        for text, width, sort_key in headers:
            if sort_key:
                btn = ctk.CTkButton(
                    self.header_frame,
                    text=text,
                    width=width,
                    height=32,
                    fg_color="transparent",
                    text_color=("gray20", "#c5cad6"),
                    hover_color=("#e2e8f0", "#282c37"),
                    anchor="w",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    command=lambda k=sort_key: self._on_column_sort(k)
                )
                btn.pack(side="left", padx=4)
            else:
                lbl = ctk.CTkLabel(
                    self.header_frame,
                    text=text,
                    width=width,
                    anchor="w",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color=("gray20", "#c5cad6")
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
        self._apply_filters()

    # =========================================================================
    # RODAPÉ DE CONTROLE E CHECKBOXES
    # =========================================================================
    def _build_bottom_bar(self):
        bot_frame = ctk.CTkFrame(self.left_panel, height=38, fg_color="transparent")
        bot_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        # Checkboxes
        self.chk_offline_only = ctk.CTkCheckBox(bot_frame, text="Exibir fora de funcionamento", font=ctk.CTkFont(size=11), command=self._apply_filters)
        self.chk_offline_only.pack(side="left", padx=(0, 10))

        self.chk_show_cams = ctk.CTkCheckBox(bot_frame, text="Exibir Câmeras", font=ctk.CTkFont(size=11), command=self._apply_filters)
        self.chk_show_cams.pack(side="left", padx=(0, 10))

        self.chk_show_olt = ctk.CTkCheckBox(bot_frame, text="Exibir Canal OLT", font=ctk.CTkFont(size=11), command=self._apply_filters)
        self.chk_show_olt.select()
        self.chk_show_olt.pack(side="left", padx=(0, 10))

        self.chk_autorefresh = ctk.CTkCheckBox(bot_frame, text="Auto-refresh (10s)", font=ctk.CTkFont(size=11), command=self._on_autorefresh_toggle)
        self.chk_autorefresh.select()
        self.chk_autorefresh.pack(side="left", padx=(0, 14))

        # Contador de dispositivos
        self.lbl_counter = ctk.CTkLabel(bot_frame, text="0 de 0 dispositivos", font=ctk.CTkFont(size=11), text_color=("gray40", "#8e92a0"))
        self.lbl_counter.pack(side="left", padx=(0, 14))

        # Botão Exportar CSV
        self.btn_export = ctk.CTkButton(
            bot_frame,
            text="Exportar",
            width=80,
            height=30,
            fg_color=("#e2e8f0", "#262832"),
            text_color=("gray10", "#ffffff"),
            hover_color=("#cbd5e1", "#343644"),
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_export_clicked
        )
        self.btn_export.pack(side="left", padx=(0, 6))

        # Botão Atualizar Agora
        self.btn_refresh = ctk.CTkButton(
            bot_frame,
            text="Atualizar",
            width=80,
            height=30,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_manual_refresh_clicked
        )
        self.btn_refresh.pack(side="left", padx=(0, 14))

        # Informações de Horário e Timer
        self.lbl_timer_status = ctk.CTkLabel(
            bot_frame,
            text="Hora: --:--:-- | Refresh: 10s",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "#8e92a0")
        )
        self.lbl_timer_status.pack(side="right")

    # =========================================================================
    # SIDEBAR DIREITA: CARDS DE MÉTRICAS NOC MODULARES
    # =========================================================================
    def _create_card_container(self, parent):
        """Cria um card modular com estilo visual de console NOC."""
        card = ctk.CTkFrame(
            parent,
            fg_color="#0c2543",
            corner_radius=8,
            border_width=1,
            border_color="#184a7e"
        )
        card.pack(fill="x", padx=8, pady=4)
        return card

    def _build_sidebar_noc(self):
        # Painel lateral azul marinho escuro com cantos arredondados
        self.sidebar_frame = ctk.CTkFrame(
            self,
            width=245,
            corner_radius=10,
            fg_color="#081b33",
            border_width=1,
            border_color="#10335e"
        )
        self.sidebar_frame.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=(0, 2))
        self.sidebar_frame.grid_propagate(False)

        # 1. Card Total de ONUs
        card_total = self._create_card_container(self.sidebar_frame)
        lbl_tot_title = ctk.CTkLabel(
            card_total,
            text="TOTAL DE ONUs",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#7fa1c4"
        )
        lbl_tot_title.pack(anchor="w", padx=10, pady=(6, 1))

        self.lbl_total_val = ctk.CTkLabel(
            card_total,
            text="🖧  0",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#ffffff"
        )
        self.lbl_total_val.pack(anchor="w", padx=10, pady=(0, 1))

        lbl_tot_sub = ctk.CTkLabel(
            card_total,
            text="Dispositivos na OLT",
            font=ctk.CTkFont(size=9),
            text_color="#8da4be"
        )
        lbl_tot_sub.pack(anchor="w", padx=10, pady=(0, 6))

        # 2. Card Status Operacional (Online e Quedas lado a lado)
        card_status = self._create_card_container(self.sidebar_frame)
        lbl_st_title = ctk.CTkLabel(
            card_status,
            text="STATUS OPERACIONAL",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#7fa1c4"
        )
        lbl_st_title.pack(anchor="w", padx=10, pady=(6, 4))

        status_row = ctk.CTkFrame(card_status, fg_color="transparent")
        status_row.pack(fill="x", padx=8, pady=(0, 8))
        status_row.grid_columnconfigure(0, weight=1)
        status_row.grid_columnconfigure(1, weight=1)

        # Sub-box Online
        box_online = ctk.CTkFrame(
            status_row,
            fg_color="#0a321f",
            corner_radius=6,
            border_width=1,
            border_color="#196c44"
        )
        box_online.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        
        self.lbl_status_online = ctk.CTkLabel(
            box_online,
            text="🟢 0",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#2ecc71"
        )
        self.lbl_status_online.pack(pady=(4, 0))
        lbl_on_sub = ctk.CTkLabel(
            box_online,
            text="Online",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#7fe5b2"
        )
        lbl_on_sub.pack(pady=(0, 4))

        # Sub-box Quedas (Offline)
        box_offline = ctk.CTkFrame(
            status_row,
            fg_color="#361016",
            corner_radius=6,
            border_width=1,
            border_color="#7b222d"
        )
        box_offline.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        
        self.lbl_status_offline = ctk.CTkLabel(
            box_offline,
            text="🔴 0",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#ff5252"
        )
        self.lbl_status_offline.pack(pady=(4, 0))
        lbl_off_sub = ctk.CTkLabel(
            box_offline,
            text="Quedas",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#ff9999"
        )
        lbl_off_sub.pack(pady=(0, 4))

        # 3. Card Câmeras Mapeadas
        card_cams = self._create_card_container(self.sidebar_frame)
        lbl_cam_title = ctk.CTkLabel(
            card_cams,
            text="CÂMERAS IP (LAN)",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#7fa1c4"
        )
        lbl_cam_title.pack(anchor="w", padx=10, pady=(6, 1))

        self.lbl_cams_val = ctk.CTkLabel(
            card_cams,
            text="📷  0",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#38bdf8"
        )
        self.lbl_cams_val.pack(anchor="w", padx=10, pady=(0, 1))

        lbl_cam_sub = ctk.CTkLabel(
            card_cams,
            text="Câmeras ativas nas portas LAN",
            font=ctk.CTkFont(size=9),
            text_color="#8da4be"
        )
        lbl_cam_sub.pack(anchor="w", padx=10, pady=(0, 6))

        # 4. Card Quebra por Portas PON com mini barras de progresso
        card_ports = self._create_card_container(self.sidebar_frame)
        lbl_p_title = ctk.CTkLabel(
            card_ports,
            text="PORTAS PON (OLT)",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#7fa1c4"
        )
        lbl_p_title.pack(anchor="w", padx=10, pady=(6, 4))

        # Slot1-PON1
        p1_row = ctk.CTkFrame(card_ports, fg_color="transparent")
        p1_row.pack(fill="x", padx=10, pady=(2, 1))
        lbl_p1_name = ctk.CTkLabel(p1_row, text="Slot1-PON1", font=ctk.CTkFont(size=10, weight="bold"), text_color="#ecf0f1")
        lbl_p1_name.pack(side="left")
        self.lbl_p1_val = ctk.CTkLabel(p1_row, text="- / -", font=ctk.CTkFont(size=10, weight="bold"), text_color="#bdc3c7")
        self.lbl_p1_val.pack(side="right")
        self.bar_p1 = ctk.CTkProgressBar(card_ports, height=5, corner_radius=3, fg_color="#142e4e", progress_color="#2ecc71")
        self.bar_p1.set(0)
        self.bar_p1.pack(fill="x", padx=10, pady=(0, 5))

        # Slot2-PON1
        p2_row = ctk.CTkFrame(card_ports, fg_color="transparent")
        p2_row.pack(fill="x", padx=10, pady=(2, 1))
        lbl_p2_name = ctk.CTkLabel(p2_row, text="Slot2-PON1", font=ctk.CTkFont(size=10, weight="bold"), text_color="#ecf0f1")
        lbl_p2_name.pack(side="left")
        self.lbl_p2_val = ctk.CTkLabel(p2_row, text="- / -", font=ctk.CTkFont(size=10, weight="bold"), text_color="#bdc3c7")
        self.lbl_p2_val.pack(side="right")
        self.bar_p2 = ctk.CTkProgressBar(card_ports, height=5, corner_radius=3, fg_color="#142e4e", progress_color="#2ecc71")
        self.bar_p2.set(0)
        self.bar_p2.pack(fill="x", padx=10, pady=(0, 5))

        # Slot2-PON2
        p3_row = ctk.CTkFrame(card_ports, fg_color="transparent")
        p3_row.pack(fill="x", padx=10, pady=(2, 1))
        lbl_p3_name = ctk.CTkLabel(p3_row, text="Slot2-PON2", font=ctk.CTkFont(size=10, weight="bold"), text_color="#ecf0f1")
        lbl_p3_name.pack(side="left")
        self.lbl_p3_val = ctk.CTkLabel(p3_row, text="- / -", font=ctk.CTkFont(size=10, weight="bold"), text_color="#bdc3c7")
        self.lbl_p3_val.pack(side="right")
        self.bar_p3 = ctk.CTkProgressBar(card_ports, height=5, corner_radius=3, fg_color="#142e4e", progress_color="#2ecc71")
        self.bar_p3.set(0)
        self.bar_p3.pack(fill="x", padx=10, pady=(0, 7))

        # 5. Card Última Coleta & Sincronização
        card_coleta = self._create_card_container(self.sidebar_frame)
        lbl_col_title = ctk.CTkLabel(
            card_coleta,
            text="ÚLTIMA SINCRONIZAÇÃO",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#7fa1c4"
        )
        lbl_col_title.pack(anchor="w", padx=10, pady=(6, 2))

        self.lbl_coleta_time = ctk.CTkLabel(
            card_coleta,
            text="⏱️  --:--:--",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#ffffff"
        )
        self.lbl_coleta_time.pack(anchor="w", padx=10, pady=(0, 1))

        self.lbl_coleta_date = ctk.CTkLabel(
            card_coleta,
            text="Data: --/--/----",
            font=ctk.CTkFont(size=10),
            text_color="#8da4be"
        )
        self.lbl_coleta_date.pack(anchor="w", padx=10, pady=(0, 2))

        lbl_col_sub = ctk.CTkLabel(
            card_coleta,
            text="● Sincronizado a cada 10s",
            font=ctk.CTkFont(size=9),
            text_color="#2ecc71"
        )
        lbl_col_sub.pack(anchor="w", padx=10, pady=(0, 6))

        # 6. Card Infraestrutura (Hub e OLT)
        card_infra = self._create_card_container(self.sidebar_frame)
        lbl_inf_title = ctk.CTkLabel(
            card_infra,
            text="INFRAESTRUTURA DE REDE",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#7fa1c4"
        )
        lbl_inf_title.pack(anchor="w", padx=10, pady=(6, 4))

        # Linha Hub
        row_hub = ctk.CTkFrame(card_infra, fg_color="transparent")
        row_hub.pack(fill="x", padx=10, pady=(1, 2))
        lbl_hub_tag = ctk.CTkLabel(row_hub, text="🖥️ Hub XPTI", font=ctk.CTkFont(size=10, weight="bold"), text_color="#ecf0f1")
        lbl_hub_tag.pack(side="left")
        self.lbl_hub_ip = ctk.CTkLabel(row_hub, text="192.168.12.10", font=ctk.CTkFont(size=10), text_color="#2ecc71")
        self.lbl_hub_ip.pack(side="right")

        # Linha OLT
        row_olt = ctk.CTkFrame(card_infra, fg_color="transparent")
        row_olt.pack(fill="x", padx=10, pady=(1, 6))
        lbl_olt_tag = ctk.CTkLabel(row_olt, text="💾 FD1108S", font=ctk.CTkFont(size=10, weight="bold"), text_color="#ecf0f1")
        lbl_olt_tag.pack(side="left")
        self.lbl_olt_ip = ctk.CTkLabel(row_olt, text="192.168.1.100", font=ctk.CTkFont(size=10), text_color="#8da4be")
        self.lbl_olt_ip.pack(side="right")

        # Aliases para compatibilidade legada
        self.card_total = self.lbl_total_val
        self.card_online = self.lbl_status_online
        self.card_offline = self.lbl_status_offline
        self.card_cams = self.lbl_cams_val
        self.lbl_port_s1p1 = self.lbl_p1_val
        self.lbl_port_s2p1 = self.lbl_p2_val
        self.lbl_port_s2p2 = self.lbl_p3_val

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

        self.lbl_total_val.configure(text=f"🖧  {total}")
        self.lbl_status_online.configure(text=f"🟢 {online}")
        self.lbl_status_offline.configure(text=f"🔴 {offline}")
        self.lbl_cams_val.configure(text=f"📷  {cams}")

        # Portas PON (converte lista de dicts da API em dict indexado)
        raw_ports = data.get("ports", [])
        if isinstance(raw_ports, list):
            ports = {p.get("port"): p for p in raw_ports if isinstance(p, dict)}
        elif isinstance(raw_ports, dict):
            ports = raw_ports
        else:
            ports = {}

        def _update_pon_ui(port_key, lbl_widget, bar_widget):
            if port_key in ports:
                p = ports[port_key]
                on = p.get("online", 0)
                tot = p.get("total", 0)
                lbl_widget.configure(text=f"{on} / {tot}")
                if tot > 0:
                    ratio = max(0.0, min(1.0, on / tot))
                    bar_widget.set(ratio)
                    if ratio >= 1.0:
                        lbl_widget.configure(text_color="#2ecc71")
                        bar_widget.configure(progress_color="#2ecc71")
                    elif ratio >= 0.8:
                        lbl_widget.configure(text_color="#f39c12")
                        bar_widget.configure(progress_color="#f39c12")
                    else:
                        lbl_widget.configure(text_color="#e74c3c")
                        bar_widget.configure(progress_color="#e74c3c")
                else:
                    bar_widget.set(0)

        _update_pon_ui("Slot1-PON1", self.lbl_p1_val, self.bar_p1)
        _update_pon_ui("Slot2-PON1", self.lbl_p2_val, self.bar_p2)
        _update_pon_ui("Slot2-PON2", self.lbl_p3_val, self.bar_p3)

        # Horário da última coleta (trata "24/09/2026 às 12:07:40" com regex seguro)
        coleta_str = str(data.get("coleta_formatted", ""))
        m = re.search(r"(\d{2}/\d{2}/\d{4}).*?(\d{2}:\d{2}:\d{2})", coleta_str)
        if m:
            d_part, t_part = m.group(1), m.group(2)
            self.lbl_coleta_time.configure(text=f"⏱️  {t_part}")
            self.lbl_coleta_date.configure(text=f"Data: {d_part}")
        elif coleta_str and coleta_str != "-":
            self.lbl_coleta_time.configure(text=coleta_str)

        # Status Hub e OLT
        srv_info = data.get("server", {})
        if isinstance(srv_info, dict) and srv_info.get("online"):
            self.lbl_hub_ip.configure(text="192.168.12.10 (OK)", text_color="#2ecc71")
        else:
            self.lbl_hub_ip.configure(text="192.168.12.10", text_color="#2ecc71")

        olt_info = data.get("olt", {})
        if isinstance(olt_info, dict) and olt_info.get("ip"):
            self.lbl_olt_ip.configure(text=str(olt_info.get("ip", "192.168.1.100")))

        # Botão de incidentes
        events_hist = data.get("events_history", [])
        active_probs = data.get("active_problems", offline)
        self.btn_events.configure(text=f"⚠️ Incidentes & Eventos ({active_probs})")

        # 2. Aplica filtros e renderiza linhas na tabela
        self._apply_filters()

    def _apply_filters(self):
        query = self.entry_search.get().strip().lower()
        selected_pon = self.combo_pon.get()
        selected_status = self.combo_status.get()
        offline_only = self.chk_offline_only.get()

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

        show_cams = self.chk_show_cams.get()
        show_olt = self.chk_show_olt.get()

        for idx, r in enumerate(self._filtered_rows):
            is_even = (idx % 2 == 0)
            row_bg = ("#ffffff", "#181a22") if is_even else ("#f8fafc", "#14161c")

            row_frame = ctk.CTkFrame(self.scroll_table, height=36, corner_radius=3, fg_color=row_bg)
            row_frame.pack(fill="x", pady=1)
            row_frame.pack_propagate(False)

            # Coluna 1: Nome (Ponto) + Badge 2P + Lápis ✏️
            c1 = ctk.CTkFrame(row_frame, width=140, fg_color="transparent")
            c1.pack(side="left", padx=4)
            c1.pack_propagate(False)

            p_name = r.get("name") or "--"
            lbl_p = ctk.CTkLabel(c1, text=f"🖧 {p_name}", font=ctk.CTkFont(size=12, weight="bold"), text_color="#0066cc")
            lbl_p.pack(side="left", padx=(0, 4))

            if r.get("multi_llid"):
                badge_2p = ctk.CTkLabel(c1, text="2P", font=ctk.CTkFont(size=9, weight="bold"), text_color="#3498db", fg_color=("#e1f0fa", "#162e4a"), corner_radius=3, width=22, height=16)
                badge_2p.pack(side="left", padx=(0, 4))

            btn_edit_name = ctk.CTkButton(
                c1, text="✏️", width=20, height=20, fg_color="transparent",
                hover_color=("#e2e8f0", "#282c37"), font=ctk.CTkFont(size=10),
                command=lambda row=r: self._open_edit_dialog(row)
            )
            btn_edit_name.pack(side="left")

            # Coluna 2: Em Funcionamento (🔴 Não / 🟢 Sim)
            c2 = ctk.CTkFrame(row_frame, width=145, fg_color="transparent")
            c2.pack(side="left", padx=4)
            c2.pack_propagate(False)

            is_online = (r.get("status") == "Online")
            stt_icon = "🟢 Sim" if is_online else "🔴 Não"
            stt_color = "#27ae60" if is_online else "#e74c3c"
            lbl_stt = ctk.CTkLabel(c2, text=stt_icon, font=ctk.CTkFont(size=12, weight="bold"), text_color=stt_color)
            lbl_stt.pack(side="left")

            # Coluna 3: Endereço / Serial (MAC)
            c3 = ctk.CTkFrame(row_frame, width=130, fg_color="transparent")
            c3.pack(side="left", padx=4)
            c3.pack_propagate(False)
            lbl_ser = ctk.CTkLabel(c3, text=r.get("serial", "-"), font=ctk.CTkFont(family="Consolas", size=11), text_color=("gray20", "#c5cad6"))
            lbl_ser.pack(side="left")

            # Coluna 4: Descrição (Rua / Local) + Lápis ✏️
            c4 = ctk.CTkFrame(row_frame, width=240, fg_color="transparent")
            c4.pack(side="left", padx=4)
            c4.pack_propagate(False)

            p_desc = r.get("desc") or ""
            if not p_desc:
                lbl_desc = ctk.CTkLabel(c4, text="+ adicionar rua", font=ctk.CTkFont(size=11, slant="italic"), text_color=("gray50", "#7f8c8d"))
            else:
                lbl_desc = ctk.CTkLabel(c4, text=p_desc, font=ctk.CTkFont(size=11), text_color=("gray10", "#ecf0f1"))
            lbl_desc.pack(side="left", padx=(0, 4))

            btn_edit_desc = ctk.CTkButton(
                c4, text="✏️", width=20, height=20, fg_color="transparent",
                hover_color=("#e2e8f0", "#282c37"), font=ctk.CTkFont(size=10),
                command=lambda row=r: self._open_edit_dialog(row)
            )
            btn_edit_desc.pack(side="left")

            # Coluna 5: Fabricante
            c5 = ctk.CTkFrame(row_frame, width=110, fg_color="transparent")
            c5.pack(side="left", padx=4)
            c5.pack_propagate(False)

            vendor_pill = ctk.CTkLabel(
                c5, text=r.get("vendor", "-"),
                font=ctk.CTkFont(size=10),
                text_color=("gray20", "#bdc3c7"),
                fg_color=("#f1f5f9", "#1e222d"),
                corner_radius=4, padx=6, height=20
            )
            vendor_pill.pack(side="left")

            # Coluna 6: Tempo no Status (vermelho se offline)
            c6 = ctk.CTkFrame(row_frame, width=120, fg_color="transparent")
            c6.pack(side="left", padx=4)
            c6.pack_propagate(False)

            upt_txt = r.get("uptime") or "-"
            upt_col = "#e74c3c" if not is_online else ("gray10", "#ecf0f1")
            upt_weight = "bold" if not is_online else "normal"
            lbl_upt = ctk.CTkLabel(c6, text=upt_txt, font=ctk.CTkFont(size=11, weight=upt_weight), text_color=upt_col)
            lbl_upt.pack(side="left")

            # Coluna 7: Canal OLT
            c7 = ctk.CTkFrame(row_frame, width=130, fg_color="transparent")
            c7.pack(side="left", padx=4)
            c7.pack_propagate(False)

            canal_txt = f"{r.get('port')}_{str(r.get('id')).zfill(3)}" if show_olt else "--"
            lbl_canal = ctk.CTkLabel(c7, text=canal_txt, font=ctk.CTkFont(size=11), text_color=("gray30", "#95a5a6"))
            lbl_canal.pack(side="left")

            # Coluna 8: Ações ([🔍 Menu] e [🗑️])
            c8 = ctk.CTkFrame(row_frame, width=100, fg_color="transparent")
            c8.pack(side="left", padx=4)
            c8.pack_propagate(False)

            btn_menu = ctk.CTkButton(
                c8, text="🔍 Menu", width=60, height=24,
                fg_color=("#e2e8f0", "#262832"),
                text_color=("gray10", "#ffffff"),
                hover_color=("#cbd5e1", "#343644"),
                font=ctk.CTkFont(size=10, weight="bold"),
                command=lambda row=r: self._open_menu_dialog(row)
            )
            btn_menu.pack(side="left", padx=(0, 4))

            btn_del = ctk.CTkButton(
                c8, text="🗑️", width=24, height=24,
                fg_color="transparent",
                hover_color=("#fee2e2", "#3b1e1e"),
                text_color="#e74c3c",
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
        events = data.get("events_history", data.get("events", []))
        if not events:
            lbl_empty = ctk.CTkLabel(dlg, text="Nenhum incidente registrado recentemente. Rede estável! ✅", font=ctk.CTkFont(size=12), text_color="#2ecc71")
            lbl_empty.pack(pady=40)
        else:
            scroll = ctk.CTkScrollableFrame(dlg, height=280)
            scroll.pack(fill="both", expand=True, padx=pad, pady=4)
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

    def _schedule_countdown(self):
        """Atualiza o relógio da barra inferior e o contador do refresh a cada segundo."""
        now_str = datetime.now().strftime("%H:%M:%S")
        if self._auto_refresh_enabled:
            self._refresh_countdown -= 1
            if self._refresh_countdown <= 0:
                self._refresh_countdown = 10
                self.mgr.fetch_telemetry_async()
            self.lbl_timer_status.configure(text=f"Hora: {now_str} | Refresh: {self._refresh_countdown}s")
        else:
            self.lbl_timer_status.configure(text=f"Hora: {now_str} | Refresh: Pausado")

        self.after(1000, self._schedule_countdown)
