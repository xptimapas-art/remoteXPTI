r"""
Módulo de Tela de Carregamento (Splash Screen) com animação Motion do 'X' da XPti.
Exibe uma janela moderna, sem bordas, com efeitos de rotação orbital, pulso e progresso fluido,
ocultando todo o processo de inicialização, montagem de layout e alinhamento de componentes da aplicação.
"""

import sys
import time
import math
import tkinter as tk
from pathlib import Path
from typing import Optional, Callable
from PIL import Image, ImageTk

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


class SplashScreen:
    """
    Gerencia a tela de splash animada com o 'X' da XPti.
    Executa animação orbital neon suave a 50 FPS com suporte a fade-in e fade-out.
    """

    WIDTH = 480
    HEIGHT = 320

    def __init__(
        self,
        parent: tk.Tk,
        current_version: str = "1.1.2",
        title: str = "RemoteXPTI",
        subtitle: Optional[str] = None,
        initial_status: str = "Iniciando..."
    ):
        self.parent = parent
        self.current_version = current_version
        self.title_text = title
        self.subtitle_text = subtitle or f"XPti Tecnologia  •  v{current_version} Beta"
        self.initial_status = initial_status
        self.start_time = time.time()
        self._is_finishing = False
        self._anim_timer = None
        self._fade_timer = None

        self.window = tk.Toplevel(parent)
        self.window.overrideredirect(True)
        self.window.configure(bg="#121318")

        # Centraliza na tela
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        x = max(0, (sw - self.WIDTH) // 2)
        y = max(0, (sh - self.HEIGHT) // 2)
        self.window.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

        # Configura atributos da janela
        try:
            self.window.attributes("-topmost", True)
            self.window.attributes("-alpha", 0.0)  # Inicia transparente para fade-in
        except Exception:
            pass

        # Ícone na barra de tarefas se disponível
        icon_path = get_resource_path("imagens/app_icon.png")
        if icon_path.exists():
            try:
                self._photo_icon = tk.PhotoImage(file=str(icon_path))
                self.window.iconphoto(True, self._photo_icon)
            except Exception:
                self._photo_icon = None

        self.canvas = tk.Canvas(
            self.window,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg="#121318",
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        self._build_ui()
        self._fade_in()
        self._start_animation()

    def _build_ui(self):
        w, h = self.WIDTH, self.HEIGHT
        cx, cy = w // 2, 102

        # 1. Borda externa suave
        self.canvas.create_rectangle(1, 1, w - 2, h - 2, outline="#242630", width=1.5)
        self.canvas.create_rectangle(2, 2, w - 3, h - 3, outline="#16171e", width=1.0)

        # 2. Carrega imagem do 'X' da XPti
        self.icon_radius = 58
        self.cx, self.cy = cx, cy

        icon_path = get_resource_path("imagens/app_icon.png")
        if icon_path.exists():
            try:
                pil_icon = Image.open(icon_path).convert("RGBA").resize((98, 98), Image.Resampling.LANCZOS)
                self.icon_img = ImageTk.PhotoImage(pil_icon)
            except Exception as e:
                log.warning(f"[Splash] Falha ao carregar ícone: {e}")
                self.icon_img = None
        else:
            self.icon_img = None

        # 3. Elementos do Motion em torno do 'X':
        # Halo de pulso (respiração externa)
        self.pulse_halo = self.canvas.create_oval(
            cx - 62, cy - 62, cx + 62, cy + 62,
            outline="#2a080c", width=1.5
        )

        # Trilho base circular discreto
        self.ring_track = self.canvas.create_oval(
            cx - self.icon_radius, cy - self.icon_radius,
            cx + self.icon_radius, cy + self.icon_radius,
            outline="#1c1e28", width=2.5
        )

        # Arcos orbitais giratórios (Neon Red XPti)
        self.arc_primary = self.canvas.create_arc(
            cx - self.icon_radius, cy - self.icon_radius,
            cx + self.icon_radius, cy + self.icon_radius,
            start=0, extent=75, style="arc", outline="#df0209", width=3.2
        )
        self.arc_secondary = self.canvas.create_arc(
            cx - self.icon_radius, cy - self.icon_radius,
            cx + self.icon_radius, cy + self.icon_radius,
            start=180, extent=42, style="arc", outline="#ff4757", width=2.2
        )
        self.arc_spark = self.canvas.create_arc(
            cx - self.icon_radius, cy - self.icon_radius,
            cx + self.icon_radius, cy + self.icon_radius,
            start=290, extent=15, style="arc", outline="#ff8585", width=2.5
        )

        # Imagem do 'X' centralizada
        if self.icon_img:
            self.canvas.create_image(cx, cy, image=self.icon_img)
        else:
            # Fallback caso imagem não exista
            self.canvas.create_text(cx, cy, text="X", fill="#df0209", font=("Segoe UI", 36, "bold"))

        # 4. Título & Subtítulo da Aplicação
        self.canvas.create_text(
            cx, 190,
            text=self.title_text,
            fill="#ffffff",
            font=("Segoe UI", 18, "bold")
        )

        self.canvas.create_text(
            cx, 214,
            text=self.subtitle_text,
            fill="#7e8394",
            font=("Segoe UI", 10)
        )

        # 5. Barra de progresso indeterminada moderna
        self.bar_w = 210
        self.bar_h = 3
        self.bar_x1 = cx - self.bar_w // 2
        self.bar_y1 = 250
        self.bar_x2 = cx + self.bar_w // 2
        self.bar_y2 = self.bar_y1 + self.bar_h

        # Fundo da barra
        self.canvas.create_rectangle(
            self.bar_x1, self.bar_y1, self.bar_x2, self.bar_y2,
            fill="#1c1e28", outline=""
        )

        # Slider dinâmico
        self.slider_w = 60
        self.slider_pos = self.bar_x1
        self.slider_dir = 2.8
        self.slider_id = self.canvas.create_rectangle(
            self.bar_x1, self.bar_y1, self.bar_x1 + self.slider_w, self.bar_y2,
            fill="#df0209", outline=""
        )

        # 6. Texto dinâmico de status
        self.status_id = self.canvas.create_text(
            cx, 274,
            text=self.initial_status,
            fill="#64687a",
            font=("Segoe UI", 9)
        )

        self.anim_angle = 0
        self.pulse_phase = 0.0

    def _fade_in(self):
        """Suave transição de fade-in da opacidade da janela."""
        current_alpha = 0.0

        def step():
            nonlocal current_alpha
            current_alpha += 0.14
            if current_alpha >= 1.0:
                try:
                    self.window.attributes("-alpha", 1.0)
                except Exception:
                    pass
                return
            try:
                self.window.attributes("-alpha", current_alpha)
                self.window.after(16, step)
            except Exception:
                pass

        step()

    def _start_animation(self):
        """Loop de animação a ~50 FPS."""
        if self._is_finishing or not self.window.winfo_exists():
            return

        # 1. Rotação dos arcos de neon
        self.anim_angle = (self.anim_angle + 4.8) % 360
        angle2 = (self.anim_angle * 1.35 + 160) % 360
        angle3 = (self.anim_angle * 0.85 + 280) % 360

        self.canvas.itemconfigure(self.arc_primary, start=self.anim_angle)
        self.canvas.itemconfigure(self.arc_secondary, start=angle2)
        self.canvas.itemconfigure(self.arc_spark, start=angle3)

        # 2. Pulso de respiração do halo externo
        self.pulse_phase += 0.08
        pulse_delta = math.sin(self.pulse_phase) * 3.5
        pr = 62 + pulse_delta
        self.canvas.coords(
            self.pulse_halo,
            self.cx - pr, self.cy - pr,
            self.cx + pr, self.cy + pr
        )

        # 3. Movimento do slider da barra de progresso
        self.slider_pos += self.slider_dir
        if self.slider_pos + self.slider_w >= self.bar_x2:
            self.slider_pos = self.bar_x2 - self.slider_w
            self.slider_dir = -abs(self.slider_dir)
        elif self.slider_pos <= self.bar_x1:
            self.slider_pos = self.bar_x1
            self.slider_dir = abs(self.slider_dir)

        self.canvas.coords(
            self.slider_id,
            self.slider_pos, self.bar_y1,
            self.slider_pos + self.slider_w, self.bar_y2
        )

        self._anim_timer = self.window.after(20, self._start_animation)

    def set_status(self, text: str):
        """Atualiza a mensagem de status da splash screen com atualização imediata."""
        if not self._is_finishing and self.window.winfo_exists():
            try:
                self.canvas.itemconfigure(self.status_id, text=text)
                self.window.update_idletasks()
            except Exception:
                pass

    def finish(self, on_finished: Optional[Callable[[], None]] = None):
        """
        Executa um fade-out suave, encerra os timers e chama o callback ao finalizar.
        """
        if self._is_finishing:
            return
        self._is_finishing = True

        self.set_status("Pronto!")

        # Cancela timer de animação
        if self._anim_timer:
            try:
                self.window.after_cancel(self._anim_timer)
            except Exception:
                pass

        current_alpha = 1.0

        def step_fade():
            nonlocal current_alpha
            current_alpha -= 0.18
            if current_alpha <= 0.0:
                try:
                    self.window.destroy()
                except Exception:
                    pass
                if on_finished:
                    on_finished()
                return

            try:
                self.window.attributes("-alpha", max(0.0, current_alpha))
                self.window.after(16, step_fade)
            except Exception:
                try:
                    self.window.destroy()
                except Exception:
                    pass
                if on_finished:
                    on_finished()

        step_fade()
