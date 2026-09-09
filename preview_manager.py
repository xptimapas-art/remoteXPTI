import os
import sys
import time
import struct
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import customtkinter as ctk

def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.resolve()

THUMBNAILS_DIR = get_app_dir() / "thumbnails"
THUMBNAILS_DIR.mkdir(exist_ok=True)

class PreviewManager:
    """Gerencia captura, geração e exibição de miniaturas (previews) estilo AnyDesk."""

    @staticmethod
    def get_thumbnail_path(server_id: str) -> Path:
        return THUMBNAILS_DIR / f"{server_id}.png"

    @staticmethod
    def generate_default_preview(
        name: str,
        host: str,
        width: int = 260,
        height: int = 145
    ) -> Image.Image:
        """Gera uma miniatura estilizada simulando uma tela de servidor/desktop moderno."""
        img = Image.new("RGBA", (width, height), (24, 25, 32, 255))
        draw = ImageDraw.Draw(img)

        # 1. Gradiente de fundo suave
        for y in range(height):
            ratio = y / height
            r = int(22 * (1 - ratio) + 14 * ratio)
            g = int(26 * (1 - ratio) + 18 * ratio)
            b = int(38 * (1 - ratio) + 26 * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        # 2. Borda sutil de monitor
        draw.rounded_rectangle(
            [(2, 2), (width - 3, height - 3)],
            radius=8,
            outline=(50, 54, 68, 255),
            width=1
        )

        # 3. Barra de tarefas simulada no rodapé (estilo Windows 11)
        taskbar_h = 16
        draw.rectangle(
            [(2, height - taskbar_h - 2), (width - 3, height - 3)],
            fill=(16, 17, 22, 230)
        )
        # Ícones da barra de tarefas (pequenos pontos no centro)
        cx = width // 2
        for offset in [-16, -6, 4, 14]:
            draw.rounded_rectangle(
                [(cx + offset, height - taskbar_h + 3), (cx + offset + 6, height - 5)],
                radius=1,
                fill=(0, 120, 215, 220) if offset == -16 else (160, 165, 180, 180)
            )

        # 4. Ícone central de Desktop / Monitor
        center_x = width // 2
        center_y = (height - taskbar_h) // 2 - 8
        
        # Desenha silhueta de monitor
        mon_w, mon_h = 44, 30
        draw.rounded_rectangle(
            [(center_x - mon_w // 2, center_y - mon_h // 2), (center_x + mon_w // 2, center_y + mon_h // 2)],
            radius=4,
            outline=(0, 130, 230, 200),
            width=2,
            fill=(28, 32, 46, 220)
        )
        # Base do monitor
        draw.rectangle(
            [(center_x - 3, center_y + mon_h // 2), (center_x + 3, center_y + mon_h // 2 + 5)],
            fill=(0, 130, 230, 200)
        )
        draw.rectangle(
            [(center_x - 10, center_y + mon_h // 2 + 5), (center_x + 10, center_y + mon_h // 2 + 7)],
            fill=(0, 130, 230, 200)
        )

        # 5. Texto com Nome e IP na miniatura
        try:
            # Tenta usar fonte padrão do Windows se disponível
            font_title = ImageFont.truetype("segoeui.ttf", 11)
            font_sub = ImageFont.truetype("segoeui.ttf", 9)
        except Exception:
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()

        # Texto do host
        text_host = host if len(host) <= 24 else host[:22] + "..."
        bbox = draw.textbbox((0, 0), text_host, font=font_sub)
        tw = bbox[2] - bbox[0]
        draw.text(
            (center_x - tw // 2, center_y + mon_h // 2 + 10),
            text_host,
            fill=(150, 160, 180, 220),
            font=font_sub
        )

        return img

    @staticmethod
    def get_thumbnail_ctk(
        server_id: str,
        name: str,
        host: str,
        width: int = 260,
        height: int = 145
    ) -> ctk.CTkImage:
        """Retorna o CTkImage da miniatura (real se existir, ou mockup padrão)."""
        thumb_file = PreviewManager.get_thumbnail_path(server_id)
        
        if thumb_file.exists():
            try:
                pil_img = Image.open(thumb_file)
                pil_img = pil_img.resize((width, height), Image.Resampling.LANCZOS)
                return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(width, height))
            except Exception as e:
                print(f"[Aviso] Falha ao abrir miniatura {thumb_file}: {e}")

        # Se não existe print real salvo, gera o mockup elegante
        default_img = PreviewManager.generate_default_preview(name, host, width, height)
        return ctk.CTkImage(light_image=default_img, dark_image=default_img, size=(width, height))

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
