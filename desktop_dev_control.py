"""Private Windows messages for reloading/stopping this checkout's DEV only."""
import ctypes
from ctypes import wintypes as w
import os
from pathlib import Path
import sys

from runtime_paths import development_id, get_window_title, is_development


def message_name(action):
    if action not in ('reload', 'stop'):
        raise ValueError('Comando DEV inválido')
    return f'XPTI.RemoteXPTI.Dev.{development_id()}.{action}'


def send_command(action, pid):
    name = message_name(action)
    if not is_development() or pid <= 0:
        raise ValueError('Controle disponível somente para um PID DEV válido')
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    for function, arguments, result in (
        (user.EnumWindows, [callback_type, w.LPARAM], w.BOOL),
        (user.GetWindowTextW, [w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
        (user.GetWindowThreadProcessId, [w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
        (user.RegisterWindowMessageW, [w.LPCWSTR], w.UINT),
        (user.PostMessageW, [w.HWND, w.UINT, w.WPARAM, w.LPARAM], w.BOOL),
        (kernel.OpenProcess, [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        (kernel.QueryFullProcessImageNameW, [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)], w.BOOL),
        (kernel.CloseHandle, [w.HANDLE], w.BOOL),
    ):
        function.argtypes, function.restype = arguments, result
    # Reject a reused PID, installed CLIENT or another Python installation.
    process = kernel.OpenProcess(0x1000, False, pid)
    if not process:
        return False
    try:
        executable = ctypes.create_unicode_buffer(32768)
        length = w.DWORD(len(executable))
        if not kernel.QueryFullProcessImageNameW(process, 0, executable, ctypes.byref(length)):
            return False
        path = Path(executable.value)
        if path.name.lower() not in ('python.exe', 'pythonw.exe') or os.path.normcase(str(path.parent)) != os.path.normcase(str(Path(sys.executable).parent)):
            return False
    finally:
        kernel.CloseHandle(process)
    found = []

    @callback_type
    def visit(hwnd, _):
        owner = w.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            title = ctypes.create_unicode_buffer(256)
            user.GetWindowTextW(hwnd, title, len(title))
            if title.value == get_window_title():
                found.append(hwnd)
                return False
        return True

    user.EnumWindows(visit, 0)
    if not found:
        return False
    message = user.RegisterWindowMessageW(name)
    if not message:
        raise ctypes.WinError(ctypes.get_last_error())
    return bool(user.PostMessageW(found[0], message, 0, 0))
