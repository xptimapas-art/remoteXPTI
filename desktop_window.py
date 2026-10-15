"""Private pywebview bridge for the shared client and DEV title bar."""
import ctypes
from ctypes import wintypes as w


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [('ptReserved', w.POINT), ('ptMaxSize', w.POINT),
                ('ptMaxPosition', w.POINT), ('ptMinTrackSize', w.POINT),
                ('ptMaxTrackSize', w.POINT)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', w.DWORD), ('rcMonitor', w.RECT),
                ('rcWork', w.RECT), ('dwFlags', w.DWORD)]


class DesktopWindow:
    def __init__(self, development=False):
        self._development = bool(development)
        self._window = None
        self._user = None
        self._procedure = None
        self._previous = None
        self._hwnd = None

    def _bind(self, window):
        self._window = window
        window.events.maximized += self._publish_state
        window.events.restored += self._publish_state

    def _on_ui(self, action):
        from System import Action
        def run():
            try:
                action()
            except Exception:
                import logging
                logging.getLogger('desktop_window').exception('Falha na operação da janela')
        self._window.native.BeginInvoke(Action(run))

    def _install_frame(self):
        def install():
            from System.Drawing import Rectangle
            native = self._window.native
            if self._procedure and self._hwnd == native.Handle.ToInt64():
                return
            self._hwnd = native.Handle.ToInt64()
            # Absolute screen coordinates in MaximizedBounds displace secondary
            # monitor windows. WM_GETMINMAXINFO below supplies monitor offsets.
            native.MaximizedBounds = Rectangle.Empty
            self._user = ctypes.WinDLL('user32', use_last_error=True)
            result = ctypes.c_ssize_t
            callback = ctypes.WINFUNCTYPE(result, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
            for function, arguments, returns in (
                (self._user.GetWindowLongPtrW, [w.HWND, ctypes.c_int], result),
                (self._user.SetWindowLongPtrW, [w.HWND, ctypes.c_int, result], result),
                (self._user.CallWindowProcW, [ctypes.c_void_p, w.HWND, w.UINT, w.WPARAM, w.LPARAM], result),
                (self._user.SetWindowPos, [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT], w.BOOL),
                (self._user.PostMessageW, [w.HWND, w.UINT, w.WPARAM, w.LPARAM], w.BOOL),
                (self._user.ReleaseCapture, [], w.BOOL),
                (self._user.GetCursorPos, [ctypes.POINTER(w.POINT)], w.BOOL),
                (self._user.IsZoomed, [w.HWND], w.BOOL),
                (self._user.MonitorFromWindow, [w.HWND, w.DWORD], w.HANDLE),
                (self._user.GetMonitorInfoW, [w.HANDLE, ctypes.POINTER(_MONITORINFO)], w.BOOL),
            ):
                function.argtypes, function.restype = arguments, returns

            @callback
            def procedure(hwnd, message, word, long):
                # Remove the non-client frame while retaining the Windows resize styles.
                if message == 0x0083 and word:  # WM_NCCALCSIZE
                    return 0
                value = self._user.CallWindowProcW(self._previous, hwnd, message, word, long)
                if message == 0x0024 and long:  # WM_GETMINMAXINFO
                    self._constrain_maximize(hwnd, long)
                return value

            self._procedure = procedure  # Keep the callback alive for the HWND's lifetime.
            ctypes.set_last_error(0)
            self._previous = self._user.SetWindowLongPtrW(self._hwnd, -4, ctypes.cast(procedure, ctypes.c_void_p).value)
            if not self._previous:
                raise ctypes.WinError(ctypes.get_last_error())
            style = self._user.GetWindowLongPtrW(self._hwnd, -16)
            style = (style | 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000) & ~0x00C00000
            self._user.SetWindowLongPtrW(self._hwnd, -16, style)
            self._user.SetWindowPos(self._hwnd, None, 0, 0, 0, 0, 0x27)  # FRAMECHANGED, NOMOVE, NOSIZE, NOZORDER
        self._on_ui(install)

    def _constrain_maximize(self, hwnd, address):
        # Use physical coordinates from one API for both rectangles, including
        # negative monitor origins and taskbars on any edge. Requery each time
        # Windows maximizes (button, double click, keyboard or drag to screen top).
        monitor = self._user.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        if not monitor:
            return
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if not self._user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return
        width = info.rcWork.right - info.rcWork.left
        height = info.rcWork.bottom - info.rcWork.top
        if width <= 0 or height <= 0:
            return
        limits = ctypes.cast(address, ctypes.POINTER(_MINMAXINFO)).contents
        limits.ptMaxPosition.x = info.rcWork.left - info.rcMonitor.left
        limits.ptMaxPosition.y = info.rcWork.top - info.rcMonitor.top
        limits.ptMaxSize.x, limits.ptMaxSize.y = width, height

    def window_state(self):
        return {'integrated': True, 'development': self._development,
                'maximized': bool(self._user and self._user.IsZoomed(self._hwnd))}

    def _publish_state(self):
        import json
        self._window.evaluate_js('window.dispatchEvent(new CustomEvent("desktopWindowState", {detail:'
                                 + json.dumps(self.window_state()) + '}));')

    def minimize(self):
        self._window.minimize()

    def toggle_maximize(self):
        def toggle():
            if self.window_state()['maximized']:
                self._window.restore()
            else:
                self._window.maximize()
        self._on_ui(toggle)

    def close(self):
        # Preserve the app's existing closing event and tray behavior.
        self._window.destroy()

    def begin_drag(self):
        self._begin_move(2)  # HTCAPTION

    def begin_resize(self, edge):
        edges = {'w':10, 'e':11, 'n':12, 'nw':13, 'ne':14, 's':15, 'sw':16, 'se':17}
        if edge not in edges:
            raise ValueError('Borda inválida.')
        if not self.window_state()['maximized']:
            self._begin_move(edges[edge])

    def _begin_move(self, hit):
        if not self._user:
            return
        def move():
            point = w.POINT()
            if not self._user.GetCursorPos(ctypes.byref(point)):
                return
            self._user.ReleaseCapture()
            coordinates = (point.x & 0xFFFF) | ((point.y & 0xFFFF) << 16)
            self._user.PostMessageW(self._hwnd, 0x00A1, hit, coordinates)  # WM_NCLBUTTONDOWN
        self._on_ui(move)
