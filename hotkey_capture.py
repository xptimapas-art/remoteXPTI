"""Capture one explicitly requested shortcut, swallowing its key before global hotkeys see it."""
import ctypes
from ctypes import wintypes
import sys
import threading
import time
import uuid

from native_hotkeys import VK_MAP

MODIFIERS = {0x10: 'shift', 0xA0: 'shift', 0xA1: 'shift',
             0x11: 'ctrl', 0xA2: 'ctrl', 0xA3: 'ctrl',
             0x12: 'alt', 0xA4: 'alt', 0xA5: 'alt'}
KEY_NAMES = {value: name for name, value in reversed(list(VK_MAP.items()))}
KEY_NAMES.update({0x21: 'PageUp', 0x22: 'PageDown', 0x1B: 'Esc', 0x20: 'Space',
                  0x0D: 'Enter', 0x09: 'Tab', 0x08: 'Backspace', 0x24: 'Home', 0x23: 'End'})


class CaptureKeys:
    """Pure key state machine. No key is logged and only the selected shortcut is retained."""
    def __init__(self, modifiers=()):
        self.modifiers = set(modifiers)
        self.selected_key = None
        self.hotkey = ''
        self.state = 'recording'
        self.error = ''

    def event(self, vk, down):
        if vk in MODIFIERS:
            if down:
                self.modifiers.add(MODIFIERS[vk])
            else:
                self.modifiers.discard(MODIFIERS[vk])
            return False
        if self.selected_key is None and down:
            self.selected_key = vk
            name = KEY_NAMES.get(vk) or (chr(vk) if 0x30 <= vk <= 0x5A and chr(vk).isalnum() else None)
            if vk == 0x1B:
                self.state = 'cancelling'
            elif name is None:
                self.state = 'invalid'
                self.error = 'Esta tecla não é suportada. Escolha outra tecla.'
            else:
                parts = [label for modifier, label in [('ctrl', 'Ctrl'), ('alt', 'Alt'), ('shift', 'Shift')] if modifier in self.modifiers]
                self.hotkey = '+'.join(parts + [name])
                self.state = 'releasing'
        if self.selected_key == vk and not down:
            self.state = 'cancelled' if self.state == 'cancelling' else 'error' if self.state == 'invalid' else 'completed'
        return True


class HotkeyCapture:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self._id = ''
        self._result = {'state': 'idle'}

    def start(self):
        if sys.platform != 'win32':
            raise RuntimeError('A gravação de atalhos requer Windows.')
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError('Já existe uma gravação de atalho em andamento.')
            self._id = uuid.uuid4().hex
            self._stop = threading.Event()
            self._ready = threading.Event()
            self._result = {'state': 'starting'}
            self._thread = threading.Thread(target=self._run, name='ShortcutCapture', daemon=True)
            self._thread.start()
        if not self._ready.wait(2):
            self._stop.set()
            raise RuntimeError('Não foi possível iniciar a gravação de atalho.')
        result = self.status(self._id)
        if result['state'] == 'error':
            raise RuntimeError(result.get('error', 'Falha ao iniciar a gravação.'))
        return result

    def status(self, capture_id):
        with self._lock:
            if capture_id != self._id:
                return {'capture_id': capture_id, 'state': 'cancelled'}
            return {'capture_id': self._id, **self._result}

    def cancel(self, capture_id):
        with self._lock:
            if capture_id == self._id:
                self._stop.set()

    def _set_result(self, state, **data):
        with self._lock:
            self._result = {'state': state, **data}

    def _run(self):
        # Microsoft documents WH_KEYBOARD_LL as running before GetAsyncKeyState updates.
        # Swallowing the selected key protects other installed instances as well.
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        lresult = ctypes.c_ssize_t
        callback_type = ctypes.WINFUNCTYPE(lresult, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        class KeyboardEvent(ctypes.Structure):
            _fields_ = [('vkCode', wintypes.DWORD), ('scanCode', wintypes.DWORD),
                        ('flags', wintypes.DWORD), ('time', wintypes.DWORD), ('extra', ctypes.c_size_t)]

        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HANDLE
        user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = lresult
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        user32.GetForegroundWindow.restype = wintypes.HWND
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        owner_window = user32.GetForegroundWindow()
        keys = CaptureKeys(modifier for vk, modifier in [(0x11, 'ctrl'), (0x12, 'alt'), (0x10, 'shift')]
                           if user32.GetAsyncKeyState(vk) & 0x8000)
        handle = None

        @callback_type
        def callback(code, message, pointer):
            if code < 0 or self._stop.is_set() or user32.GetForegroundWindow() != owner_window:
                return user32.CallNextHookEx(handle, code, message, pointer)
            if message not in (0x100, 0x101, 0x104, 0x105):
                return user32.CallNextHookEx(handle, code, message, pointer)
            event = ctypes.cast(pointer, ctypes.POINTER(KeyboardEvent)).contents
            # Keep the callback fast: no networking, persistence, logging or UI work.
            if keys.event(event.vkCode, message in (0x100, 0x104)):
                return 1
            return user32.CallNextHookEx(handle, code, message, pointer)

        try:
            handle = user32.SetWindowsHookExW(13, callback, kernel32.GetModuleHandleW(None), 0)
            if not handle:
                raise OSError('Falha ao registrar o gravador de teclado.')
            self._set_result('recording')
            self._ready.set()
            deadline = time.monotonic() + 30
            message = wintypes.MSG()
            while not self._stop.is_set() and time.monotonic() < deadline:
                if user32.GetForegroundWindow() != owner_window:
                    break
                while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                    user32.TranslateMessage(ctypes.byref(message))
                    user32.DispatchMessageW(ctypes.byref(message))
                if keys.state in ('completed', 'cancelled', 'error'):
                    break
                self._stop.wait(0.01)
            # Unhook before publishing completion, so the form cannot start a new recorder too early.
            user32.UnhookWindowsHookEx(handle)
            handle = None
            if keys.state == 'completed':
                self._set_result('completed', hotkey=keys.hotkey)
            elif keys.state == 'error':
                self._set_result('error', error=keys.error)
            else:
                self._set_result('cancelled')
        except Exception:
            self._set_result('error', error='Não foi possível capturar a tecla no Windows. Tente novamente.')
        finally:
            if handle:
                user32.UnhookWindowsHookEx(handle)
            self._ready.set()
