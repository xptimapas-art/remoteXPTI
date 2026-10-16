"""
Módulo de Atalhos Globais Nativos para Windows (RemoteXPTI).
Utiliza GetAsyncKeyState da API Win32 para detecção de teclas no nível do hardware.
Totalmente independente de drivers, DLLs e hooks frágeis (WH_KEYBOARD_LL).
"""

import sys
import time
import ctypes
import threading
from typing import Dict, Any, List, Optional, Callable, Tuple

from logger import log
from config_manager import ConfigManager

# Mapeamento completo de nomes de teclas amigáveis para Virtual-Key Codes (Win32)
VK_MAP: Dict[str, int] = {
    # Teclas de navegação e edição
    "PAGEUP": 0x21,
    "PAGE UP": 0x21,
    "PRIOR": 0x21,
    "PAGEDOWN": 0x22,
    "PAGE DOWN": 0x22,
    "NEXT": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "ARROWLEFT": 0x25,
    "UP": 0x26,
    "ARROWUP": 0x26,
    "RIGHT": 0x27,
    "ARROWRIGHT": 0x27,
    "DOWN": 0x28,
    "ARROWDOWN": 0x28,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "DEL": 0x2E,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "SPACE": 0x20,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "RETURN": 0x0D,
    "BACKSPACE": 0x08,
    "PRINTSCREEN": 0x2C,
    "PRINTSCRN": 0x2C,
    "PRTSCR": 0x2C,
    "PAUSE": 0x13,
    "NUMLOCK": 0x90,
    "SCROLLLOCK": 0x91,
}

# F1 até F24
for i in range(1, 25):
    VK_MAP[f"F{i}"] = 0x6F + i

# Numpad 0-9
for i in range(10):
    VK_MAP[f"NUMPAD{i}"] = 0x60 + i
    VK_MAP[f"NUM{i}"] = 0x60 + i


def parse_hotkey(hotkey_str: str) -> Tuple[Optional[int], Dict[str, bool]]:
    """
    Interpreta uma string de atalho (ex: 'PageDown', 'F7', 'Ctrl+Alt+F12')
    e retorna (vk_code, {'ctrl': bool, 'alt': bool, 'shift': bool}).
    """
    if not hotkey_str:
        return None, {"ctrl": False, "alt": False, "shift": False}

    parts = [p.strip().upper() for p in hotkey_str.split("+") if p.strip()]
    mods = {"ctrl": False, "alt": False, "shift": False}
    main_vk: Optional[int] = None

    for p in parts:
        clean = p.replace(" ", "").replace("_", "").replace("-", "")
        if clean in ("CTRL", "CONTROL"):
            mods["ctrl"] = True
        elif clean in ("ALT", "MENU"):
            mods["alt"] = True
        elif clean in ("SHIFT",):
            mods["shift"] = True
        elif clean in VK_MAP:
            main_vk = VK_MAP[clean]
        elif p in VK_MAP:
            main_vk = VK_MAP[p]
        elif len(clean) == 1 and ("A" <= clean <= "Z" or "0" <= clean <= "9"):
            main_vk = ord(clean)

    return main_vk, mods


class NativeHotkeyManager:
    """
    Monitor global de teclas em background utilizando polling ultra-leve de GetAsyncKeyState.
    - Intervalo de 25ms (40Hz): Consumo de CPU imperceptível (~0.0%).
    - Edge-triggering: Dispara apenas no momento em que a tecla é pressionada (transição UP -> DOWN).
    - Validação de sessão DEV: Garante que apenas usuários autenticados no modo DEV acionem as portas.
    - Cooldown anti-repetição de 2.5s por porta.
    """

    def __init__(self, on_trigger_callback: Callable[[str, str], Any]):
        self.on_trigger = on_trigger_callback
        self.bindings: List[Dict[str, Any]] = []
        self._last_trigger_time: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def update_bindings(self, doors: List[Dict[str, Any]]):
        """Atualiza os atalhos ativos em memória a partir da lista de portas."""
        with self._lock:
            self.bindings.clear()
            for door in doors:
                raw_hk = (door.get("hotkey") or "").strip()
                door_id = door.get("id")
                is_enabled = door.get("enabled", True)

                if raw_hk and door_id and is_enabled:
                    vk, mods = parse_hotkey(raw_hk)
                    if vk is not None:
                        self.bindings.append({
                            "door_id": door_id,
                            "name": door.get("name", "Porta"),
                            "hotkey": raw_hk,
                            "vk": vk,
                            "mods": mods,
                            "was_down": False
                        })
                        mod_names = [k.upper() for k, v in mods.items() if v]
                        mod_str = (" + ".join(mod_names) + " + ") if mod_names else ""
                        log.info(
                            f"[NativeHotkeys] Atalho registrado: {mod_str}VK_0x{vk:02X} "
                            f"(origem: '{raw_hk}') para '{door.get('name')}'."
                        )
                    else:
                        log.warning(f"[NativeHotkeys] Tecla não reconhecida: '{raw_hk}' para porta '{door.get('name')}'.")

    def start(self):
        """Inicia a thread de monitoramento caso ainda não esteja rodando."""
        if self._running:
            return
        if sys.platform != "win32":
            log.warning("[NativeHotkeys] Sistema operacional não é Windows. Atalhos desabilitados.")
            return

        self._running = True
        self._thread = threading.Thread(target=self._loop, name="NativeHotkeyPoller", daemon=True)
        self._thread.start()
        log.info("[NativeHotkeys] Thread de monitoramento nativo Win32 iniciada.")

    def stop(self):
        """Para a thread de monitoramento."""
        self._running = False

    def _loop(self):
        user32 = ctypes.windll.user32
        VK_CONTROL = 0x11
        VK_MENU = 0x12  # Alt
        VK_SHIFT = 0x10

        while self._running:
            try:
                # Consulta estado dos modificadores globais
                ctrl_down = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                alt_down = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
                shift_down = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)

                with self._lock:
                    for b in self.bindings:
                        vk = b["vk"]
                        key_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)

                        if key_down:
                            mods = b["mods"]
                            mods_match = (
                                mods["ctrl"] == ctrl_down and
                                mods["alt"] == alt_down and
                                mods["shift"] == shift_down
                            )

                            if mods_match:
                                if not b["was_down"]:
                                    b["was_down"] = True
                                    self._handle_press(b["door_id"], b["hotkey"], b["name"])
                            else:
                                b["was_down"] = False
                        else:
                            b["was_down"] = False

            except Exception as e:
                log.debug(f"[NativeHotkeys] Exceção no loop de atalhos: {e}")

            time.sleep(0.025)

    def _handle_press(self, door_id: str, hotkey: str, door_name: str):
        """Valida autenticação DEV e cooldown antes de disparar o callback."""
        config_mgr = ConfigManager()
        if not config_mgr.is_dev_authenticated():
            log.info(f"[NativeHotkeys] Tecla [{hotkey}] pressionada, mas ignorada: Modo DEV inativo.")
            return

        now = time.time()
        last_t = self._last_trigger_time.get(door_id, 0)
        if now - last_t < 2.5:
            log.info(f"[NativeHotkeys] Tecla [{hotkey}] ignorada por cooldown ({now - last_t:.1f}s).")
            return
        self._last_trigger_time[door_id] = now

        log.info(f"[NativeHotkeys] 🚀 Atalho FÍSICO [{hotkey}] detectado para '{door_name}'! Acionando...")
        try:
            threading.Thread(
                target=self.on_trigger,
                args=(door_id, f"Atalho Físico ({hotkey})"),
                daemon=True
            ).start()
        except Exception as e:
            log.error(f"[NativeHotkeys] Erro ao disparar callback: {e}")
