import os
import sys
import time
import struct
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import customtkinter as ctk

def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.resolve()

def get_thumbnails_dir() -> Path:
    base = get_app_dir() / "thumbnails"
    try:
        base.mkdir(parents=True, exist_ok=True)
        return base
    except Exception:
        import tempfile
        fallback = Path(tempfile.gettempdir()) / "remotexpti_thumbnails"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

THUMBNAILS_DIR = get_thumbnails_dir()

PALETTES = [
    (32, 70, 130),   # AnyDesk Classic Blue
    (40, 44, 54),    # Dark Graphite / Carbon
    (45, 80, 55),    # Forest Green
    (125, 85, 45),   # Warm Amber / Ochre
    (125, 45, 52),   # Crimson / Ruby
    (55, 50, 110),   # Royal Indigo
    (35, 85, 105),   # Teal Cyan
]

class PreviewManager:
    """Gerencia captura, geração e exibição de miniaturas estilo AnyDesk autêntico."""

    _cache: dict = {}

    @classmethod
    def invalidate_cache(cls, server_id: Optional[str] = None):
        """Invalida o cache de miniaturas de um servidor ou de todos."""
        if server_id:
            to_del = [k for k in cls._cache if k.startswith(f"{server_id}_")]
            for k in to_del:
                cls._cache.pop(k, None)
        else:
            cls._cache.clear()

    @staticmethod
    def get_thumbnail_path(server_id: str) -> Path:
        return THUMBNAILS_DIR / f"{server_id}.png"

    @classmethod
    def generate_anydesk_card(
        cls,
        server_id: str,
        name: str,
        host: str,
        is_online: Optional[bool] = None,
        width: int = 240,
        height: int = 160,
        is_fav: bool = False
    ) -> Image.Image:
        """
        Gera o card completo no padrão exato do AnyDesk:
        - Wallpaper de fundo em tela cheia (print real capturado ou ondas AnyDesk em tons variados).
        - Gradiente escuro inferior para máxima legibilidade de texto.
        - Círculo de status no canto superior esquerdo (🟢 online, 🚫 offline, ⚪ checando).
        - Estrela de favoritos no canto superior direito.
        - Ícone de monitor + Nome em negrito + IP no canto inferior esquerdo.
        - 3 pontos verticais (menu de opções) no canto inferior direito.
        """
        import math
        thumb_file = cls.get_thumbnail_path(server_id)

        # 1. Base do Card (Print real se existir, ou Ondas AnyDesk)
        if thumb_file.exists():
            try:
                base_img = Image.open(thumb_file).convert("RGBA")
                img = base_img.resize((width, height), Image.Resampling.LANCZOS)
            except Exception:
                img = None
        else:
            img = None

        if img is None:
            # Seleção de paleta baseada no ID do servidor
            h_idx = abs(hash(server_id)) % len(PALETTES)
            base_rgb = PALETTES[h_idx]

            img = Image.new("RGBA", (width, height), (*base_rgb, 255))
            draw = ImageDraw.Draw(img)

            for y in range(height):
                ratio = y / height
                r = int(base_rgb[0] * (1.12 - 0.42 * ratio))
                g = int(base_rgb[1] * (1.12 - 0.42 * ratio))
                b = int(base_rgb[2] * (1.12 - 0.42 * ratio))
                draw.line([(0, y), (width, y)], fill=(min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, b)), 255))

            # Ondas estilizadas suaves do AnyDesk
            wave_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            wdraw = ImageDraw.Draw(wave_img)
            wdraw.arc([int(width * 0.1), int(-height * 0.5), int(width * 1.6), int(height * 1.8)], start=160, end=270, fill=(255, 255, 255, 36), width=16)
            wdraw.arc([int(width * 0.25), int(-height * 0.3), int(width * 1.7), int(height * 1.7)], start=160, end=260, fill=(255, 255, 255, 44), width=10)
            wdraw.arc([int(width * 0.4), int(-height * 0.1), int(width * 1.8), int(height * 1.6)], start=165, end=255, fill=(255, 255, 255, 28), width=5)
            wave_img = wave_img.filter(ImageFilter.GaussianBlur(radius=5))
            img = Image.alpha_composite(img, wave_img)

        # 2. Gradiente escuro no rodapé para garantir contraste das legendas
        start_y = int(height * 0.46)
        grad_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(grad_overlay)
        for y in range(start_y, height):
            ratio = (y - start_y) / (height - start_y)
            alpha = int(210 * (ratio ** 1.25))
            gdraw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
        img = Image.alpha_composite(img, grad_overlay)

        draw = ImageDraw.Draw(img)

        # 3. Indicador de Status (Canto Superior Esquerdo)
        if is_online is True:
            draw.ellipse([(13, 12), (25, 24)], fill=(0, 204, 102, 255))
        elif is_online is False:
            draw.ellipse([(13, 12), (25, 24)], fill=(235, 60, 60, 255))
            draw.line([(15, 22), (23, 14)], fill=(255, 255, 255, 230), width=2)
        else:
            draw.ellipse([(13, 12), (25, 24)], fill=(160, 160, 160, 255))

        # 4. Estrela de Favoritos (Canto Superior Direito)
        def draw_star(cx, cy, r_out=7, r_in=3):
            pts = []
            for i in range(10):
                r = r_out if i % 2 == 0 else r_in
                ang = i * math.pi / 5 - math.pi / 2
                pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
            outline_col = (255, 205, 50, 255) if is_fav else (220, 225, 235, 200)
            fill_col = (255, 205, 50, 255) if is_fav else None
            draw.polygon(pts, fill=fill_col, outline=outline_col)

        draw_star(width - 20, 18)

        # 5. Ícone de Monitor (Canto Inferior Esquerdo)
        mx, my = 14, height - 38
        mw, mh = 19, 13
        draw.rounded_rectangle([(mx, my), (mx + mw, my + mh)], radius=2, outline=(255, 255, 255, 230), width=1)
        draw.line([(mx + mw // 2, my + mh), (mx + mw // 2, my + mh + 3)], fill=(255, 255, 255, 230), width=1)
        draw.line([(mx + mw // 2 - 4, my + mh + 3), (mx + mw // 2 + 4, my + mh + 3)], fill=(255, 255, 255, 230), width=1)

        # 6. Textos: Nome do Servidor e Host
        try:
            font_name = ImageFont.truetype("segoeuib.ttf", 12)
            font_host = ImageFont.truetype("segoeui.ttf", 10)
        except Exception:
            font_name = ImageFont.load_default()
            font_host = ImageFont.load_default()

        display_name = name if len(name) <= 20 else name[:18] + "..."
        tx = mx + mw + 8
        draw.text((tx, my - 4), display_name, fill=(255, 255, 255, 255), font=font_name)
        draw.text((tx, my + 12), host, fill=(200, 205, 220, 230), font=font_host)

        # 7. Três Pontos Verticais ⋮ (Canto Inferior Direito)
        cx = width - 16
        for dy in [my + 2, my + 7, my + 12]:
            draw.ellipse([(cx, dy), (cx + 2, dy + 2)], fill=(255, 255, 255, 220))

        return img

    @classmethod
    def get_card_ctk(
        cls,
        server_id: str,
        name: str,
        host: str,
        is_online: Optional[bool] = None,
        width: int = 240,
        height: int = 160,
        is_fav: bool = False
    ) -> ctk.CTkImage:
        """Retorna o CTkImage completo do card no estilo AnyDesk com cache inteligente."""
        cache_key = f"{server_id}_{width}_{height}_{is_online}_{is_fav}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        pil_img = cls.generate_anydesk_card(server_id, name, host, is_online, width, height, is_fav)
        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(width, height))
        cls._cache[cache_key] = ctk_img
        return ctk_img

    @classmethod
    def get_thumbnail_ctk(cls, server_id: str, name: str, host: str, width: int = 240, height: int = 160) -> ctk.CTkImage:
        """Alias para compatibilidade retroativa."""
        return cls.get_card_ctk(server_id, name, host, None, width, height)

    @staticmethod
    def capture_rdp_window(server_id: str, host: str) -> bool:
        """
        Localiza a janela do Remote Desktop (mstsc.exe) e tira um print da tela remota.
        Salva em thumbnails/{server_id}.png.
        """
        if sys.platform != "win32":
            return False

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        clean_host = host.split(":", 1)[0] if ":" in host else host

        found_hwnd = None

        # Enumera janelas para encontrar a do mstsc
        def enum_windows_callback(hwnd, extra):
            nonlocal found_hwnd
            if not user32.IsWindowVisible(hwnd):
                return True

            # Obtém nome da classe da janela
            class_name = (ctypes.c_wchar * 256)()
            user32.GetClassNameW(hwnd, class_name, 256)

            # Obtém título da janela
            title_len = user32.GetWindowTextLengthW(hwnd)
            title = (ctypes.c_wchar * (title_len + 1))()
            user32.GetWindowTextW(hwnd, title, title_len + 1)

            # TscShellContainerClass é a classe oficial da janela do cliente RDP da Microsoft
            if "TscShellContainerClass" in class_name.value:
                # Verifica se o título corresponde ou se é a única janela RDP aberta
                if clean_host.lower() in title.value.lower() or not found_hwnd:
                    found_hwnd = hwnd
                    return False

            if clean_host.lower() in title.value.lower() and ("área de trabalho remota" in title.value.lower() or "remote desktop" in title.value.lower()):
                found_hwnd = hwnd
                return False

            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)

        if not found_hwnd:
            return False

        # Tira print do HWND usando GDI PrintWindow
        try:
            rect = wintypes.RECT()
            user32.GetWindowRect(found_hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            if w < 100 or h < 100:
                return False

            hwnd_dc = user32.GetWindowDC(found_hwnd)
            mfc_dc = gdi32.CreateCompatibleDC(hwnd_dc)
            save_bit_map = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
            gdi32.SelectObject(mfc_dc, save_bit_map)

            # 2 = PW_RENDERFULLCONTENT
            user32.PrintWindow(found_hwnd, mfc_dc, 2)

            bmpinfo = bytearray(40)
            struct.pack_into('<LllHHLLllLL', bmpinfo, 0, 40, w, -h, 1, 32, 0, w * h * 4, 0, 0, 0, 0)

            buffer = bytearray(w * h * 4)
            gdi32.GetDIBits(
                mfc_dc,
                save_bit_map,
                0,
                h,
                (ctypes.c_char * len(buffer)).from_buffer(buffer),
                (ctypes.c_char * 40).from_buffer(bmpinfo),
                0
            )

            gdi32.DeleteObject(save_bit_map)
            gdi32.DeleteDC(mfc_dc)
            user32.ReleaseDC(found_hwnd, hwnd_dc)

            img = Image.frombuffer('RGBA', (w, h), bytes(buffer), 'raw', 'BGRA', 0, 1)
            
            # Converte e salva redimensionado
            thumb_path = PreviewManager.get_thumbnail_path(server_id)
            img.convert("RGB").save(thumb_path, "PNG")
            PreviewManager.invalidate_cache(server_id)
            print(f"[Preview] Captura de tela salva para {server_id} ({host}) em {thumb_path}")
            return True
        except Exception as e:
            print(f"[Erro] Falha ao capturar janela RDP: {e}")
            return False

    @staticmethod
    def auto_capture_after_launch(server_id: str, host: str, delay_seconds: float = 6.0, callback=None):
        """
        Executa em thread para aguardar o mstsc abrir e capturar automaticamente o preview.
        """
        time.sleep(delay_seconds)
        
        # Tenta capturar repetidamente por até 25 segundos (aguardando login carregar a área de trabalho)
        for _ in range(8):
            success = PreviewManager.capture_rdp_window(server_id, host)
            if success:
                if callback:
                    callback(server_id)
                break
            time.sleep(3.0)
