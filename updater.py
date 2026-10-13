"""Compatibilidade da UI legada com o novo mecanismo de atualização."""
try:
    import customtkinter as ctk
except ImportError:
    ctk = None
from update_engine import (SilentAutoUpdater, parse_version, is_public_version, is_beta_tester_version)

if ctk is not None:
    class UpdatePromptBanner(ctk.CTkFrame):
        """Banner visual no topo do app avisando que o update está baixado e pronto para reiniciar."""

        def __init__(self, parent, new_version: str, on_restart_command, on_dismiss=None):
            super().__init__(
                parent,
                height=42,
                corner_radius=8,
                fg_color=("#0052a3", "#123456"),
                border_width=1,
                border_color="#0080ff"
            )
            self.pack_propagate(False)

            lbl = ctk.CTkLabel(
                self,
                text="Atualização pronta. Reinicie quando quiser.",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#ffffff"
            )
            lbl.pack(side="left", padx=16)

            # Botão Fechar / Mais tarde
            btn_close = ctk.CTkButton(
                self,
                text="✕",
                width=28,
                height=26,
                fg_color="transparent",
                hover_color=("#003d7a", "#1a4670"),
                text_color="#ffffff",
                font=ctk.CTkFont(size=11, weight="bold"),
                command=on_dismiss or self.destroy
            )
            btn_close.pack(side="right", padx=(4, 10))

            # Botão Reiniciar Agora
            btn_restart = ctk.CTkButton(
                self,
                text="🔄 Reiniciar para Atualizar",
                height=28,
                fg_color="#00a8ff",
                hover_color="#0088cc",
                text_color="#ffffff",
                font=ctk.CTkFont(size=11, weight="bold"),
                command=on_restart_command
            )
            btn_restart.pack(side="right", padx=6)
else:
    class UpdatePromptBanner:
        pass
