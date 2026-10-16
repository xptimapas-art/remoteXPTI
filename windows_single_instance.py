"""Use a named mutex for exclusivity and verify ownership before focusing a window."""
import ctypes
from ctypes import wintypes as w
import os
import sys


class WindowsSingleInstance:
    def __init__(self, name):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        signatures = (
            (self.kernel.CreateMutexW, [w.LPVOID, w.BOOL, w.LPCWSTR], w.HANDLE),
            (self.kernel.CloseHandle, [w.HANDLE], w.BOOL),
            (self.kernel.OpenProcess, [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            (self.kernel.QueryFullProcessImageNameW,
             [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)], w.BOOL),
            (self.user.EnumWindows, [self.callback_type, w.LPARAM], w.BOOL),
            (self.user.GetWindowTextW, [w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
            (self.user.GetWindowThreadProcessId, [w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
            (self.user.ShowWindow, [w.HWND, ctypes.c_int], w.BOOL),
            (self.user.SetForegroundWindow, [w.HWND], w.BOOL),
        )
        for function, args, result in signatures:
            function.argtypes = args
            function.restype = result
        ctypes.set_last_error(0)
        self.handle = self.kernel.CreateMutexW(None, False, name)
        error = ctypes.get_last_error()
        if not self.handle:
            raise ctypes.WinError(error)
        self.already_running = error == 183  # ERROR_ALREADY_EXISTS

    def _owns_window(self, hwnd, title, current_only):
        text = ctypes.create_unicode_buffer(len(title) + 2)
        if not self.user.GetWindowTextW(hwnd, text, len(text)) or text.value != title:
            return False
        pid = w.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if current_only:
            return pid.value == os.getpid()
        if not pid.value or pid.value == os.getpid():
            return False
        process = self.kernel.OpenProcess(0x1000, False, pid.value)
        if not process:
            return False
        try:
            path = ctypes.create_unicode_buffer(32768)
            size = w.DWORD(len(path))
            if not self.kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
                return False
            normalize = lambda value: os.path.normcase(os.path.abspath(value))
            return normalize(path.value) == normalize(sys.executable)
        finally:
            self.kernel.CloseHandle(process)

    def focus(self, title, current_only=False):
        found = []

        @self.callback_type
        def visit(hwnd, _):
            # Never let an exception escape a ctypes callback.
            try:
                if self._owns_window(hwnd, title, current_only):
                    found.append(hwnd)
                    return False
            except (OSError, ValueError):
                pass
            return True

        self.user.EnumWindows(visit, 0)
        if not found:
            return False
        self.user.ShowWindow(found[0], 9)  # SW_RESTORE
        self.user.SetForegroundWindow(found[0])
        return True

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
