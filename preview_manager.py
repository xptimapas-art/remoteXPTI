import os
import sys
import time
import struct
import ctypes
from ctypes import wintypes
from pathlib import Path
import math
from functools import lru_cache
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
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

@lru_cache(maxsize=16)
def get_base_palette_wallpaper(palette_idx: int, width: int = 276, height: int = 180, is_hover: bool = False) -> Image.Image:
    """Pré-calcula a base vetorial AnyDesk com ondas e gradiente inferior em cache de alta velocidade."""
    base_rgb = PALETTES[palette_idx % len(PALETTES)]
    img = Image.new("RGBA", (width, height), (*base_rgb, 255))
    draw = ImageDraw.Draw(img)

    for y in range(height):
        ratio = y / height
        r = int(base_rgb[0] * (1.14 - 0.44 * ratio))
        g = int(base_rgb[1] * (1.14 - 0.44 * ratio))
        b = int(base_rgb[2] * (1.14 - 0.44 * ratio))
        draw.line([(0, y), (width, y)], fill=(min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, b)), 255))

    # Ondas estilizadas suaves do AnyDesk
    wave_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    wdraw = ImageDraw.Draw(wave_img)
    wdraw.arc([int(width * 0.1), int(-height * 0.5), int(width * 1.6), int(height * 1.8)], start=160, end=270, fill=(255, 255, 255, 38), width=18)
    wdraw.arc([int(width * 0.25), int(-height * 0.3), int(width * 1.7), int(height * 1.7)], start=160, end=260, fill=(255, 255, 255, 45), width=12)
    wdraw.arc([int(width * 0.4), int(-height * 0.1), int(width * 1.8), int(height * 1.6)], start=165, end=255, fill=(255, 255, 255, 30), width=6)
    wave_img = wave_img.filter(ImageFilter.GaussianBlur(radius=5))
    img = Image.alpha_composite(img, wave_img)

    if is_hover:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.14)
        sheen = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(sheen)
        for y in range(int(height * 0.45)):
            alpha = int(35 * (1.0 - y / (height * 0.45)))
            sdraw.line([(0, y), (width, y)], fill=(255, 255, 255, alpha))
        tint = Image.new("RGBA", (width, height), (0, 120, 215, 22))
        sheen = Image.alpha_composite(sheen, tint)
        img = Image.alpha_composite(img, sheen)

    start_y = int(height * 0.40)
    grad_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad_overlay)
    for y in range(start_y, height):
        ratio = (y - start_y) / (height - start_y)
        alpha = int((210 if is_hover else 225) * (ratio ** 1.2))
        gdraw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, grad_overlay)

    return img


@lru_cache(maxsize=8)
def get_card_font(font_type: str, size: int):
    try:
        font_file = "segoeuib.ttf" if font_type == "bold" else "segoeui.ttf"
        return ImageFont.truetype(font_file, size)
    except Exception:
        return ImageFont.load_default()


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

    @staticmethod
    @lru_cache(maxsize=16)
    def _render_status_badge(is_online: Optional[bool], size: int = 18) -> Image.Image:
        """
        Renderiza indicador de status em altíssima definição com 4x supersampling (SSAA)
        e filtro Lanczos para bordas 100% perfeitas, acabamento vetorial e sombra suave.
        """
        scale = 4
        ss = size * scale
        pad = 2 * scale
        d = ss - pad * 2

        img = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))

        # 1. Sombra suave para destacar sobre qualquer papel de parede
        shadow = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        sdraw.ellipse([pad, pad + int(1.2 * scale), pad + d, pad + d + int(1.2 * scale)], fill=(0, 0, 0, 100))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=1.2 * scale))
        img = Image.alpha_composite(img, shadow)

        # 2. Badge principal
        badge = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
        bdraw = ImageDraw.Draw(badge)

        if is_online is True:
            # Verde vibrante estilo AnyDesk / Fluent (#2ebd59)
            bdraw.ellipse([pad, pad, pad + d, pad + d], fill=(46, 189, 89, 255))
            bdraw.ellipse([pad, pad, pad + d, pad + d], outline=(255, 255, 255, 110), width=scale)
        elif is_online is False:
            # Vermelho vibrante estilo AnyDesk (#f04438)
            bdraw.ellipse([pad, pad, pad + d, pad + d], fill=(240, 68, 56, 255))
            cx, cy = ss // 2, ss // 2
            r_line = int(d * 0.32)
            slash_w = int(2.4 * scale)
            bdraw.line([cx - r_line, cy + r_line, cx + r_line, cy - r_line],
                       fill=(255, 255, 255, 245), width=slash_w)
            bdraw.ellipse([pad, pad, pad + d, pad + d], outline=(255, 255, 255, 110), width=scale)
        else:
            # Neutro checando (#94a3b8)
            bdraw.ellipse([pad, pad, pad + d, pad + d], fill=(148, 163, 184, 255))
            bdraw.ellipse([pad, pad, pad + d, pad + d], outline=(255, 255, 255, 110), width=scale)

        img = Image.alpha_composite(img, badge)
        return img.resize((size, size), Image.Resampling.LANCZOS)

    @staticmethod
    @lru_cache(maxsize=8)
    def _render_star_icon(is_fav: bool, size: int = 20) -> Image.Image:
        """Renderiza estrela em alta definição com 4x supersampling."""
        scale = 4
        ss = size * scale
        img = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        cx, cy = ss / 2, ss / 2
        r_out = ss * 0.42
        r_in = ss * 0.19

        pts = []
        for i in range(10):
            r = r_out if i % 2 == 0 else r_in
            ang = i * math.pi / 5 - math.pi / 2
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))

        if is_fav:
            s_pts = [(x, y + scale) for x, y in pts]
            draw.polygon(s_pts, fill=(0, 0, 0, 80))
            draw.polygon(pts, fill=(255, 205, 40, 255), outline=(255, 235, 100, 255))
        else:
            s_pts = [(x, y + scale) for x, y in pts]
            draw.line(s_pts + [s_pts[0]], fill=(0, 0, 0, 70), width=int(2.2 * scale))
            draw.line(pts + [pts[0]], fill=(255, 255, 255, 235), width=int(1.8 * scale))

        return img.resize((size, size), Image.Resampling.LANCZOS)

    @classmethod
    def generate_anydesk_card(
        cls,
        server_id: str,
        name: str,
        host: str,
        is_online: Optional[bool] = None,
        width: int = 276,
        height: int = 180,
        is_fav: bool = False,
        is_hover: bool = False
    ) -> Image.Image:
        """
        Gera o card completo no padrão exato do AnyDesk:
        - Wallpaper de fundo em tela cheia (print real capturado ou ondas AnyDesk em tons variados).
        - Efeito hover dinâmico AnyDesk com iluminação ativa e borda azul vibrante.
        - Gradiente escuro inferior para máxima legibilidade de texto.
        - Círculo de status em alta definição (🟢 online, 🚫 offline com traço diagonal, ⚪ checando).
        - Estrela de favoritos em alta definição no canto superior direito.
        - Ícone de monitor + Nome em negrito + IP no canto inferior esquerdo.
        - 3 pontos verticais (menu de opções) no canto inferior direito.
        """
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
            # Seleção de paleta baseada no ID do servidor com base pré-renderizada ultra-rápida (0ms)
            h_idx = abs(hash(server_id)) % len(PALETTES)
            img = get_base_palette_wallpaper(h_idx, width, height, is_hover).copy()
        elif is_hover:
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(1.14)
            start_y = int(height * 0.40)
            grad_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            gdraw = ImageDraw.Draw(grad_overlay)
            for y in range(start_y, height):
                ratio = (y - start_y) / (height - start_y)
                alpha = int(210 * (ratio ** 1.2))
                gdraw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
            img = Image.alpha_composite(img, grad_overlay)

        # 4. Indicador de Status em Alta Resolução (Canto Superior Esquerdo)
        badge = cls._render_status_badge(is_online, size=18)
        img.paste(badge, (13, 13), badge)

        # 5. Estrela de Favoritos em Alta Resolução (Canto Superior Direito)
        star = cls._render_star_icon(is_fav, size=20)
        img.paste(star, (width - 33, 11), star)

        draw = ImageDraw.Draw(img)

        # 6. Ícone de Monitor (Canto Inferior Esquerdo)
        mx, my = 16, height - 44
        mw, mh = 24, 16
        draw.rounded_rectangle([(mx, my), (mx + mw, my + mh)], radius=2, outline=(255, 255, 255, 245), width=2)
        draw.line([(mx + mw // 2, my + mh), (mx + mw // 2, my + mh + 4)], fill=(255, 255, 255, 245), width=2)
        draw.line([(mx + mw // 2 - 5, my + mh + 4), (mx + mw // 2 + 5, my + mh + 4)], fill=(255, 255, 255, 245), width=2)

        # 7. Textos: Nome do Servidor e Host com Fontes em Cache
        font_name = get_card_font("bold", 13)
        font_host = get_card_font("regular", 11)

        display_name = name if len(name) <= 22 else name[:20] + "..."
        tx = mx + mw + 10
        draw.text((tx, my - 3), display_name, fill=(255, 255, 255, 255), font=font_name)
        draw.text((tx, my + 16), host, fill=(215, 225, 240, 245) if is_hover else (195, 205, 220, 240), font=font_host)

        # 8. Três Pontos Verticais ⋮ (Canto Inferior Direito)
        cx = width - 20
        for dy in [my + 2, my + 8, my + 14]:
            draw.ellipse([(cx - 1, dy - 1), (cx + 2, dy + 2)], fill=(255, 255, 255, 245))

        # 9. Borda do Card e Linha de Destaque
        if is_hover:
            # Borda luminosa AnyDesk Blue (#0082f0)
            draw.rounded_rectangle([(0, 0), (width - 1, height - 1)], radius=4, outline=(0, 130, 240, 255), width=2)
            # Glow interno sutil de 1px
            draw.rounded_rectangle([(2, 2), (width - 3, height - 3)], radius=3, outline=(0, 150, 255, 70), width=1)
            # Linha inferior de destaque AnyDesk vibrante
            draw.line([(2, height - 3), (width - 3, height - 3)], fill=(0, 160, 255, 255), width=3)
        else:
            # Borda sutil padrão AnyDesk
            draw.rounded_rectangle([(0, 0), (width - 1, height - 1)], radius=4, outline=(54, 58, 72, 200), width=1)
            draw.line([(1, height - 2), (width - 2, height - 2)], fill=(55, 95, 145, 255), width=2)

        return img

    @classmethod
    def get_card_ctk(
        cls,
        server_id: str,
        name: str,
        host: str,
        is_online: Optional[bool] = None,
        width: int = 276,
        height: int = 180,
        is_fav: bool = False,
        is_hover: bool = False
    ) -> ctk.CTkImage:
        """Retorna o CTkImage completo do card no estilo AnyDesk com cache inteligente."""
        cache_key = f"{server_id}_{width}_{height}_{is_online}_{is_fav}_{is_hover}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        pil_img = cls.generate_anydesk_card(server_id, name, host, is_online, width, height, is_fav, is_hover)
        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(width, height))
        cls._cache[cache_key] = ctk_img
        return ctk_img

    @classmethod
    def get_thumbnail_ctk(cls, server_id: str, name: str, host: str, width: int = 276, height: int = 180) -> ctk.CTkImage:
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
