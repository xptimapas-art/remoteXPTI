"""
Componente de Interface de Usuário para Monitoramento de ONUs da Ajin (RemoteXPTI).
Design inspirado nas interfaces de segurança do Digifort e AnyDesk.
Alta performance gráfica com suporte a filtros instantâneos, edição de pontos e scanner de novos MACs.
"""

import os
import sys
import subprocess
import threading
import tkinter as tk
import customtkinter as ctk
from typing import Dict, Any, List, Optional, Callable

from ajin_manager import AjinManager
from logger import log


class EditLabelDialog(ctk.CTkToplevel):
    """Modal compacto para renomear ponto e rua de uma ONU em 1 clique."""

    def __init__(self, parent, onu_data: Dict[str, Any], on_saved: Callable[[str, str], None]):
        super().__init__(parent)
        self.onu = onu_data
        self.on_saved = on_saved

        self.title("Editar Identificação da ONU")
        self.geometry("440x360")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        # Fundo e Header
        self.configure(fg_color="#181a20")

        lbl_header = ctk.CTkLabel(
            self,
            text=f"✏️ Editar {self.onu.get('port')} #{self.onu.get('onu_id')}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#ffffff"
        )
        lbl_header.pack(padx=20, pady=(20, 4), anchor="w")

        lbl_mac = ctk.CTkLabel(
            self,
            text=f"MAC: {self.onu.get('mac', '-')} | Fabricante: {self.onu.get('vendor', '-')}",
            font=ctk.CTkFont(size=11),
            text_color="#8e92a0"
        )
        lbl_mac.pack(padx=20, pady=(0, 16), anchor="w")

        # Campo: Nome do Ponto
        lbl_ponto = ctk.CTkLabel(self, text="Nome do Ponto:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_ponto.pack(padx=20, anchor="w")
        self.entry_name = ctk.CTkEntry(
            self,
            placeholder_text="Ex: Ponto 10",
            height=36,
            fg_color="#121318",
            border_color="#343644"
        )
        self.entry_name.pack(fill="x", padx=20, pady=(4, 12))
        self.entry_name.insert(0, self.onu.get("name", ""))

        # Campo: Rua / Descrição
        lbl_desc = ctk.CTkLabel(self, text="Rua / Localização / Referência:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_desc.pack(padx=20, anchor="w")
        self.entry_desc = ctk.CTkEntry(
            self,
            placeholder_text="Ex: R. Tabaronas próx. ao trevo",
            height=36,
            fg_color="#121318",
            border_color="#343644"
        )
        self.entry_desc.pack(fill="x", padx=20, pady=(4, 20))
        self.entry_desc.insert(0, self.onu.get("description", ""))

        # Botões de Ação
        btn_box = ctk.CTkFrame(self, fg_color="transparent")
        btn_box.pack(fill="x", padx=20, pady=(0, 20))

        btn_cancel = ctk.CTkButton(
            btn_box,
            text="Cancelar",
            width=100,
            height=36,
            fg_color="#262832",
            hover_color="#343644",
            command=self.destroy
        )
        btn_cancel.pack(side="left")

        btn_save = ctk.CTkButton(
            btn_box,
            text="Salvar Alterações",
            width=140,
            height=36,
            fg_color="#0066cc",
            hover_color="#0052a3",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._do_save
        )
        btn_save.pack(side="right")

    def _do_save(self):
        new_name = self.entry_name.get().strip()
        new_desc = self.entry_desc.get().strip()
        self.on_saved(new_name, new_desc)
        self.destroy()


class ScannerModal(ctk.CTkToplevel):
    """Modal para visualização e homologação de novos MACs detectados pelo Scanner."""

    def __init__(self, parent, scanner_items: List[Dict[str, Any]], on_homologated: Callable[[], None]):
        super().__init__(parent)
        self.parent = parent
        self.scanner_items = scanner_items
        self.on_homologated = on_homologated

        self.title("🔍 Scanner de Novas ONUs Conectadas na Fibra")
        self.geometry("720x540")
        self.minsize(640, 480)
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        self.configure(fg_color="#121318")
        self._build_ui()

    def _build_ui(self):
        # Header
        head_box = ctk.CTkFrame(self, fg_color="#181a20", height=60, corner_radius=0)
        head_box.pack(fill="x", side="top")
        head_box.pack_propagate(False)

        lbl_title = ctk.CTkLabel(
            head_box,
            text=f"🔍 Scanner de Dispositivos Ópticos ({len(self.scanner_items)} novos MACs detectados)",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#ffffff"
        )
        lbl_title.pack(side="left", padx=20, pady=16)

        btn_close = ctk.CTkButton(
            head_box,
            text="✕ Fechar",
            width=80,
            height=32,
            fg_color="#262832",
            hover_color="#343644",
            command=self.destroy
        )
        btn_close.pack(side="right", padx=20, pady=14)

        # Informação descritiva
        lbl_info = ctk.CTkLabel(
            self,
            text="Dispositivos recém-conectados na OLT C-Data. Clique em '+ Homologar' para adicionar ao monitoramento ativo.",
            font=ctk.CTkFont(size=11),
            text_color="#8e92a0"
        )
        lbl_info.pack(padx=20, pady=(12, 6), anchor="w")

        # Container scrollável
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        if not self.scanner_items:
            empty = ctk.CTkLabel(
                scroll,
                text="Nenhuma nova ONU pendente de homologação na rede no momento.",
                font=ctk.CTkFont(size=13),
                text_color="#8e92a0"
            )
            empty.pack(pady=60)
            return

        for item in self.scanner_items:
            card = ctk.CTkFrame(scroll, fg_color="#181a20", corner_radius=6, border_width=1, border_color="#262832")
            card.pack(fill="x", pady=4, padx=2)

            left = ctk.CTkFrame(card, fg_color="transparent")
            left.pack(side="left", padx=14, pady=10)

            title = ctk.CTkLabel(
                left,
                text=f"{item.get('port')}  •  ONU #{item.get('onu_id')}",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#ffffff"
            )
            title.pack(anchor="w")

            meta = ctk.CTkLabel(
                left,
                text=f"MAC: {item.get('mac')}   |   Fabricante: {item.get('vendor')}   |   Status na OLT: {item.get('status')}",
                font=ctk.CTkFont(size=11),
                text_color="#8e92a0"
            )
            meta.pack(anchor="w")

            btn_homolog = ctk.CTkButton(
                card,
                text="+ Homologar",
                width=110,
                height=32,
                fg_color="#0066cc",
                hover_color="#0052a3",
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda it=item: self._open_homolog_dialog(it)
            )
            btn_homolog.pack(side="right", padx=14, pady=10)

    def _open_homolog_dialog(self, item: Dict[str, Any]):
        def on_saved(name, desc):
            ok, msg = AjinManager().homologate_onu(
                port=item.get("port"),
                onu_id=item.get("onu_id"),
                mac=item.get("mac"),
                name=name,
                desc=desc
            )
            if ok:
                self.on_homologated()
                self.destroy()

        EditLabelDialog(self, item, on_saved)


class AjinView(ctk.CTkFrame):
    """Tela completa de Supervisão das ONUs da Ajin com visual AnyDesk/Digifort."""

    def __init__(self, parent, on_view_map_point: Optional[Callable[[Dict[str, Any]], None]] = None):
        super().__init__(parent, fg_color="#121318")
        self.parent = parent
        self.on_view_map_point = on_view_map_point
        self.manager = AjinManager()
        self._search_timer = None
        self._row_widgets = []

        self._build_ui()
        self.manager.add_listener(self._on_telemetry_updated)

        # Dispara primeira busca assíncrona
        threading.Thread(target=self.refresh_data, daemon=True).start()

    def destroy(self):
        self.manager.remove_listener(self._on_telemetry_updated)
        super().destroy()

    def _build_ui(self):
        # 1. Faixa Superior: Cards de Métricas Consolidadas
        self.metrics_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.metrics_bar.pack(fill="x", padx=16, pady=(12, 10))

        # Card Online
        self.card_online = self._create_metric_card(
            parent=self.metrics_bar,
            title="EM OPERAÇÃO",
            badge_text="ONLINE",
            badge_color="#142219",
            text_color="#2ebd59",
            initial_val="--"
        )
        self.card_online.pack(side="left", fill="both", expand=True, padx=(0, 6))

        # Card Offline
        self.card_offline = self._create_metric_card(
            parent=self.metrics_bar,
            title="FORA DE OPERAÇÃO",
            badge_text="OFFLINE",
            badge_color="#261618",
            text_color="#f04438",
            initial_val="--"
        )
        self.card_offline.pack(side="left", fill="both", expand=True, padx=6)

        # Card Total
        self.card_total = self._create_metric_card(
            parent=self.metrics_bar,
            title="TOTAL HOMOLOGADAS",
            badge_text="PARQUE",
            badge_color="#162232",
            text_color="#38bdf8",
            initial_val="--"
        )
        self.card_total.pack(side="left", fill="both", expand=True, padx=6)

        # Card Disponibilidade
        self.card_avail = self._create_metric_card(
            parent=self.metrics_bar,
            title="DISPONIBILIDADE",
            badge_text="SAÚDE",
            badge_color="#221632",
            text_color="#a855f7",
            initial_val="--%"
        )
        self.card_avail.pack(side="left", fill="both", expand=True, padx=(6, 0))

        # 2. Barra de Filtros, Pesquisa e Scanner
        filter_bar = ctk.CTkFrame(self, fg_color="#181a20", height=50, corner_radius=6)
        filter_bar.pack(fill="x", padx=16, pady=(0, 10))
        filter_bar.pack_propagate(False)

        # Campo de Busca
        self.entry_search = ctk.CTkEntry(
            filter_bar,
            placeholder_text="🔍 Buscar por Ponto, Rua, MAC, IP de Câmera ou ID...",
            width=280,
            height=34,
            fg_color="#121318",
            border_color="#262832"
        )
        self.entry_search.pack(side="left", padx=(10, 8), pady=8)
        self.entry_search.bind("<KeyRelease>", self._on_search_keypress)

        # Filtro de Status
        self.seg_status = ctk.CTkSegmentedButton(
            filter_bar,
            values=["Todas", "Online", "Offline"],
            width=210,
            height=34,
            selected_color="#0066cc",
            selected_hover_color="#0052a3",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda v: self._apply_filters()
        )
        self.seg_status.set("Todas")
        self.seg_status.pack(side="left", padx=(0, 8), pady=8)

        # Filtro de Portas PON
        self.combo_pon = ctk.CTkComboBox(
            filter_bar,
            values=["Todas as PONs", "Slot1-PON1", "Slot1-PON2", "Slot2-PON1", "Slot2-PON2"],
            width=140,
            height=34,
            fg_color="#121318",
            border_color="#262832",
            command=lambda v: self._apply_filters()
        )
        self.combo_pon.set("Todas as PONs")
        self.combo_pon.pack(side="left", padx=(0, 8), pady=8)

        # Botão Scanner de Novos MACs (com badge)
        self.btn_scanner = ctk.CTkButton(
            filter_bar,
            text="🔍 Scanner (0)",
            height=34,
            fg_color="#262832",
            hover_color="#343644",
            text_color="#f59e0b",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.open_scanner_modal
        )
        self.btn_scanner.pack(side="right", padx=(0, 10), pady=8)

        # Botão Atualizar
        btn_refresh = ctk.CTkButton(
            filter_bar,
            text="🔄",
            width=36,
            height=34,
            fg_color="#262832",
            hover_color="#343644",
            command=lambda: threading.Thread(target=self.refresh_data, daemon=True).start()
        )
        btn_refresh.pack(side="right", padx=(0, 8), pady=8)

        # 3. Cabeçalho da Tabela
        tbl_header = ctk.CTkFrame(self, height=28, fg_color="#16171d", corner_radius=0)
        tbl_header.pack(fill="x", padx=16, pady=(0, 2))
        tbl_header.pack_propagate(False)

        h_status = ctk.CTkLabel(tbl_header, text="STATUS", width=80, anchor="w", font=ctk.CTkFont(size=10, weight="bold"), text_color="#767986")
        h_status.pack(side="left", padx=(14, 0))

        h_ponto = ctk.CTkLabel(tbl_header, text="PONTO / RUA", width=220, anchor="w", font=ctk.CTkFont(size=10, weight="bold"), text_color="#767986")
        h_ponto.pack(side="left", padx=(8, 0))

        h_pon = ctk.CTkLabel(tbl_header, text="PORTA & ID", width=110, anchor="w", font=ctk.CTkFont(size=10, weight="bold"), text_color="#767986")
        h_pon.pack(side="left", padx=(8, 0))

        h_mac = ctk.CTkLabel(tbl_header, text="MAC & FABRICANTE", width=170, anchor="w", font=ctk.CTkFont(size=10, weight="bold"), text_color="#767986")
        h_mac.pack(side="left", padx=(8, 0))

        h_cams = ctk.CTkLabel(tbl_header, text="CÂMERAS (IP)", width=150, anchor="w", font=ctk.CTkFont(size=10, weight="bold"), text_color="#767986")
        h_cams.pack(side="left", padx=(8, 0))

        h_uptime = ctk.CTkLabel(tbl_header, text="TEMPO NO ESTADO", width=130, anchor="w", font=ctk.CTkFont(size=10, weight="bold"), text_color="#767986")
        h_uptime.pack(side="left", padx=(8, 0))

        h_actions = ctk.CTkLabel(tbl_header, text="AÇÕES", width=80, anchor="e", font=ctk.CTkFont(size=10, weight="bold"), text_color="#767986")
        h_actions.pack(side="right", padx=(0, 14))

        # 4. Tabela de Conteúdo com Scroll
        self.scroll_table = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_table.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    def _create_metric_card(self, parent, title: str, badge_text: str, badge_color: str, text_color: str, initial_val: str):
        card = ctk.CTkFrame(parent, fg_color="#181a20", corner_radius=6, border_width=1, border_color="#262832", height=76)
        card.pack_propagate(False)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 0))

        lbl_t = ctk.CTkLabel(top, text=title, font=ctk.CTkFont(size=10, weight="bold"), text_color="#8e92a0")
        lbl_t.pack(side="left")

        badge = ctk.CTkLabel(
            top,
            text=f" {badge_text} ",
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color=badge_color,
            text_color=text_color,
            corner_radius=4
        )
        badge.pack(side="right")

        lbl_val = ctk.CTkLabel(
            card,
            text=initial_val,
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=text_color
        )
        lbl_val.pack(anchor="w", padx=12, pady=(0, 8))
        card._lbl_val = lbl_val
        return card

    def _on_search_keypress(self, event=None):
        if self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(90, self._apply_filters)

    def refresh_data(self):
        """Busca novos dados em background sem travar a interface."""
        try:
            self.manager.fetch_telemetry()
        except Exception as e:
            log.warning(f"[AjinView] Falha ao atualizar dados: {e}")

    def _on_telemetry_updated(self):
        """Disparado quando novos dados chegam ao AjinManager."""
        try:
            if self.winfo_exists():
                self.after(0, self._render_ui_updates)
        except Exception:
            pass

    def _render_ui_updates(self):
        summary = self.manager.get_summary()
        scanner = self.manager.get_scanner()

        # Atualiza métricas
        self.card_online._lbl_val.configure(text=str(summary.get("online", 0)))
        self.card_offline._lbl_val.configure(text=str(summary.get("offline", 0)))
        self.card_total._lbl_val.configure(text=str(summary.get("total", 0)))
        self.card_avail._lbl_val.configure(text=f"{summary.get('availability_pct', 0.0)}%")

        # Atualiza botão do Scanner
        scan_count = len(scanner)
        self.btn_scanner.configure(text=f"🔍 Scanner ({scan_count})")
        if scan_count > 0:
            self.btn_scanner.configure(fg_color="#3a2510", text_color="#fbbf24")
        else:
            self.btn_scanner.configure(fg_color="#262832", text_color="#8e92a0")

        self._apply_filters()

    def _apply_filters(self):
        query = self.entry_search.get().strip()
        status = self.seg_status.get()
        pon = self.combo_pon.get()

        onus = self.manager.get_onus(status_filter=status, port_filter=pon, search_query=query)
        self._render_table_rows(onus)

    def _render_table_rows(self, onus: List[Dict[str, Any]]):
        # Limpa widgets anteriores
        for w in self._row_widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._row_widgets.clear()

        if not onus:
            empty = ctk.CTkLabel(
                self.scroll_table,
                text="Nenhuma ONU encontrada com os filtros selecionados.",
                font=ctk.CTkFont(size=13),
                text_color="#8e92a0"
            )
            empty.pack(pady=40)
            self._row_widgets.append(empty)
            return

        for idx, onu in enumerate(onus):
            bg_col = "#181a20" if idx % 2 == 0 else "#14151b"
            row = ctk.CTkFrame(self.scroll_table, height=44, fg_color=bg_col, corner_radius=4)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            is_online = (onu.get("status") == "Online")
            st_color = "#2ebd59" if is_online else "#f04438"
            st_bg = "#142219" if is_online else "#261618"

            # 1. Status Pill
            status_box = ctk.CTkFrame(row, width=80, fg_color="transparent")
            status_box.pack(side="left", padx=(10, 0))
            status_box.pack_propagate(False)

            pill = ctk.CTkLabel(
                status_box,
                text=f" ● {onu.get('status')} ",
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color=st_bg,
                text_color=st_color,
                corner_radius=4
            )
            pill.pack(anchor="w")

            # 2. Ponto e Rua
            ponto_box = ctk.CTkFrame(row, width=220, fg_color="transparent")
            ponto_box.pack(side="left", padx=(8, 0))
            ponto_box.pack_propagate(False)

            lbl_name = ctk.CTkLabel(
                ponto_box,
                text=onu.get("name", "Ponto"),
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#ffffff",
                anchor="w"
            )
            lbl_name.pack(fill="x", anchor="w")

            lbl_desc = ctk.CTkLabel(
                ponto_box,
                text=onu.get("description") or "Sem descrição de rua",
                font=ctk.CTkFont(size=10),
                text_color="#8e92a0",
                anchor="w"
            )
            lbl_desc.pack(fill="x", anchor="w")

            # 3. Porta & ID
            pon_box = ctk.CTkFrame(row, width=110, fg_color="transparent")
            pon_box.pack(side="left", padx=(8, 0))
            pon_box.pack_propagate(False)

            lbl_pon = ctk.CTkLabel(
                pon_box,
                text=f"{onu.get('port')}\n#{onu.get('onu_id')}",
                font=ctk.CTkFont(size=10),
                text_color="#cbd5e1",
                justify="left",
                anchor="w"
            )
            lbl_pon.pack(anchor="w")

            # 4. MAC & Fabricante
            mac_box = ctk.CTkFrame(row, width=170, fg_color="transparent")
            mac_box.pack(side="left", padx=(8, 0))
            mac_box.pack_propagate(False)

            lbl_mac = ctk.CTkLabel(
                mac_box,
                text=onu.get("mac") or "-",
                font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                text_color="#93c5fd",
                anchor="w"
            )
            lbl_mac.pack(anchor="w")

            lbl_vend = ctk.CTkLabel(
                mac_box,
                text=onu.get("vendor") or "Desconhecido",
                font=ctk.CTkFont(size=10),
                text_color="#8e92a0",
                anchor="w"
            )
            lbl_vend.pack(anchor="w")

            # 5. Câmeras (IPs)
            cams_box = ctk.CTkFrame(row, width=150, fg_color="transparent")
            cams_box.pack(side="left", padx=(8, 0))
            cams_box.pack_propagate(False)

            cams = onu.get("cameras", [])
            if cams:
                ips_str = ", ".join(c.get("ip", "") for c in cams if c.get("ip"))
                lbl_cams = ctk.CTkLabel(
                    cams_box,
                    text=f"📷 {ips_str}",
                    font=ctk.CTkFont(size=10),
                    text_color="#38bdf8",
                    anchor="w"
                )
                lbl_cams.pack(anchor="w")
            else:
                lbl_cams = ctk.CTkLabel(
                    cams_box,
                    text="-",
                    font=ctk.CTkFont(size=10),
                    text_color="#555866",
                    anchor="w"
                )
                lbl_cams.pack(anchor="w")

            # 6. Tempo de Uptime/Downtime
            uptime_box = ctk.CTkFrame(row, width=130, fg_color="transparent")
            uptime_box.pack(side="left", padx=(8, 0))
            uptime_box.pack_propagate(False)

            lbl_upt = ctk.CTkLabel(
                uptime_box,
                text=onu.get("uptime_text") or "-",
                font=ctk.CTkFont(size=10),
                text_color="#8e92a0",
                anchor="w"
            )
            lbl_upt.pack(anchor="w")

            # 7. Ações
            actions_box = ctk.CTkFrame(row, width=80, fg_color="transparent")
            actions_box.pack(side="right", padx=(0, 10))

            btn_edit = ctk.CTkButton(
                actions_box,
                text="✏️",
                width=28,
                height=26,
                fg_color="#262832",
                hover_color="#343644",
                font=ctk.CTkFont(family="Segoe UI Emoji", size=11),
                command=lambda item=onu: self._open_edit_label(item)
            )
            btn_edit.pack(side="right", padx=2)

            self._row_widgets.append(row)

    def _open_edit_label(self, onu: Dict[str, Any]):
        def on_saved(new_name, new_desc):
            self.manager.update_onu_label(
                port=onu.get("port"),
                onu_id=onu.get("onu_id"),
                name=new_name,
                desc=new_desc
            )
        EditLabelDialog(self, onu, on_saved)

    def open_scanner_modal(self):
        ScannerModal(
            parent=self,
            scanner_items=self.manager.get_scanner(),
            on_homologated=self.refresh_data
        )
