r"""
Módulo de Tela de Carregamento (Splash Screen) com animação Motion do 'X' da XPti.
Exibe uma janela moderna, sem bordas, com efeitos de rotação orbital, pulso e progresso fluido,
ocultando todo o processo de inicialização, montagem de layout e alinhamento de componentes da aplicação.
"""

import sys
import time
import math
import threading
import multiprocessing
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
        current_version: str = "1.2.0",
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
            self.window.attributes("-alpha", 1.0)  # Exibe 100% visível e nítida imediatamente (0ms de atraso)
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
        self.tick_motion()
        try:
            self.window.update()
        except Exception:
            pass
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

    def show_immediately(self):
        """Força a exibição imediata e elevação da janela na tela com pintura do quadro inicial."""
        try:
            self.window.attributes("-alpha", 1.0)
            self.window.deiconify()
            self.window.lift()
            self.window.focus_force()
            self.tick_motion()
            self.window.update()
        except Exception:
            pass

    def tick_motion(self):
        """Avança 1 quadro da animação orbital neon, pulso e barra de progresso."""
        if self._is_finishing or not hasattr(self, "canvas") or not self.window.winfo_exists():
            return

        try:
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
        except Exception:
            pass

    def _start_animation(self):
        """Loop contínuo de animação a ~50 FPS."""
        if self._is_finishing or not self.window.winfo_exists():
            return
        self.tick_motion()
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


def run_isolated_splash(
    msg_queue,
    current_version: str = "1.2.0",
    title: str = "RemoteXPTI",
    subtitle: Optional[str] = None
):
    """
    Executa a splash screen em um processo isolado e independente do SO.
    Garante taxa fixa de 60 FPS com os arcos girando e a barra deslizando
    SEM NUNCA CONGELAR, mesmo com carga pesada de inicialização no app principal.
    """
    WIDTH = 480
    HEIGHT = 320

    root = tk.Tk()
    root.overrideredirect(True)
    root.configure(bg="#121318")

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = max(0, (sw - WIDTH) // 2)
    y = max(0, (sh - HEIGHT) // 2)
    root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    try:
        root.attributes("-topmost", True)
        root.attributes("-alpha", 1.0)
    except Exception:
        pass

    icon_path = get_resource_path("imagens/app_icon.png")
    photo_icon = None
    if icon_path.exists():
        try:
            photo_icon = tk.PhotoImage(file=str(icon_path))
            root.iconphoto(True, photo_icon)
        except Exception:
            pass

    canvas = tk.Canvas(root, width=WIDTH, height=HEIGHT, bg="#121318", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    # 1. Borda externa suave
    canvas.create_rectangle(1, 1, WIDTH - 2, HEIGHT - 2, outline="#242630", width=1.5)
    canvas.create_rectangle(2, 2, WIDTH - 3, HEIGHT - 3, outline="#16171e", width=1.0)

    cx, cy = WIDTH // 2, 102
    r = 58

    # 2. Ícone squircle do 'X' da XPti
    icon_img = None
    if icon_path.exists():
        try:
            pil_icon = Image.open(icon_path).convert("RGBA").resize((98, 98), Image.Resampling.LANCZOS)
            icon_img = ImageTk.PhotoImage(pil_icon)
            canvas.create_image(cx, cy, image=icon_img)
        except Exception as e:
            log.warning(f"[SplashProcess] Falha ao desenhar ícone: {e}")

    # 3. Arcos orbitais de neon
    arc_primary = canvas.create_arc(
        cx - r, cy - r, cx + r, cy + r,
        start=0, extent=85,
        outline="#df0209", width=2.8, style="arc"
    )
    arc_secondary = canvas.create_arc(
        cx - (r + 7), cy - (r + 7), cx + (r + 7), cy + (r + 7),
        start=160, extent=65,
        outline="#ff4757", width=1.8, style="arc"
    )
    arc_spark = canvas.create_arc(
        cx - (r - 6), cy - (r - 6), cx + (r - 6), cy + (r - 6),
        start=280, extent=45,
        outline="#ff7675", width=1.4, style="arc"
    )

    pr = 62
    pulse_halo = canvas.create_oval(
        cx - pr, cy - pr, cx + pr, cy + pr,
        outline="#3d1419", width=1.5
    )

    # 4. Tipografia
    canvas.create_text(
        cx, 184,
        text=title,
        fill="#ffffff",
        font=("Segoe UI", 16, "bold")
    )
    canvas.create_text(
        cx, 212,
        text=subtitle or f"XPti Tecnologia  •  v{current_version} Beta",
        fill="#a2a7b8",
        font=("Segoe UI", 10)
    )

    # 5. Barra de progresso
    bar_w = 210
    bar_h = 3
    bar_x1 = cx - bar_w // 2
    bar_y1 = 250
    bar_x2 = cx + bar_w // 2
    bar_y2 = bar_y1 + bar_h
    canvas.create_rectangle(bar_x1, bar_y1, bar_x2, bar_y2, fill="#1c1e28", outline="")

    slider_w = 60
    slider_pos = bar_x1
    slider_dir = 2.8
    slider_id = canvas.create_rectangle(bar_x1, bar_y1, bar_x1 + slider_w, bar_y2, fill="#df0209", outline="")

    # 6. Status dinâmico
    status_id = canvas.create_text(cx, 274, text="Iniciando...", fill="#64687a", font=("Segoe UI", 9))

    anim_angle = 0
    pulse_phase = 0.0
    is_closing = False

    def anim_tick():
        nonlocal anim_angle, pulse_phase, slider_pos, slider_dir
        if is_closing:
            return

        anim_angle = (anim_angle + 4.8) % 360
        angle2 = (anim_angle * 1.35 + 160) % 360
        angle3 = (anim_angle * 0.85 + 280) % 360

        try:
            canvas.itemconfigure(arc_primary, start=anim_angle)
            canvas.itemconfigure(arc_secondary, start=angle2)
            canvas.itemconfigure(arc_spark, start=angle3)

            pulse_phase += 0.08
            p_delta = math.sin(pulse_phase) * 3.5
            curr_pr = 62 + p_delta
            canvas.coords(pulse_halo, cx - curr_pr, cy - curr_pr, cx + curr_pr, cy + curr_pr)

            slider_pos += slider_dir
            if slider_pos + slider_w >= bar_x2:
                slider_pos = bar_x2 - slider_w
                slider_dir = -abs(slider_dir)
            elif slider_pos <= bar_x1:
                slider_pos = bar_x1
                slider_dir = abs(slider_dir)
            canvas.coords(slider_id, slider_pos, bar_y1, slider_pos + slider_w, bar_y2)
        except Exception:
            pass

        root.after(16, anim_tick)  # Locked 60 FPS contínuo

    def poll_messages():
        nonlocal is_closing
        try:
            while not msg_queue.empty():
                msg = msg_queue.get_nowait()
                if msg in ("__CLOSE__", "__FINISH__"):
                    is_closing = True
                    fade_out()
                    return
                else:
                    canvas.itemconfigure(status_id, text=str(msg))
        except Exception:
            pass
        if not is_closing:
            root.after(25, poll_messages)

    def fade_out():
        alpha = 1.0
        try:
            canvas.itemconfigure(status_id, text="Pronto!")
        except Exception:
            pass
        def step():
            nonlocal alpha
            alpha -= 0.16
            if alpha <= 0.0:
                try:
                    root.destroy()
                except Exception:
                    pass
                return
            try:
                root.attributes("-alpha", max(0.0, alpha))
            except Exception:
                pass
            root.after(16, step)
        step()

    anim_tick()
    poll_messages()
    root.mainloop()


class SplashProcessManager:
    """
    Gerencia a execução da Splash Screen em um processo separado independente.
    Garante que a rotação e a barra de progresso NUNCA congelem ou travem,
    independentemente de qualquer trabalho pesado sendo executado no processo principal.
    """

    def __init__(self, current_version: str = "1.2.0"):
        import multiprocessing
        self.queue = multiprocessing.Queue()
        self.process = multiprocessing.Process(
            target=run_isolated_splash,
            args=(self.queue, current_version),
            daemon=True
        )
        self.start_time = time.time()
        self.min_duration = 3.5
        self._finished = False
        try:
            self.process.start()
        except Exception as e:
            log.warning(f"[SplashProcessManager] Falha ao iniciar processo de splash isolado: {e}")
            self.process = None

    def set_status(self, text: str):
        if self._finished or not self.process:
            return
        try:
            self.queue.put(text)
        except Exception:
            pass

    def finish(self, on_finished: Optional[Callable[[], None]] = None):
        if self._finished:
            if on_finished:
                on_finished()
            return
        self._finished = True
        if self.process:
            try:
                self.queue.put("__FINISH__")
                threading.Thread(target=lambda: self.process.join(timeout=2), daemon=True).start()
            except Exception:
                pass
        if on_finished:
            on_finished()

    def close_now(self):
        self._finished = True
        if self.process:
            try:
                self.queue.put("__CLOSE__")
                threading.Thread(target=lambda: self.process.join(timeout=1), daemon=True).start()
            except Exception:
                pass

