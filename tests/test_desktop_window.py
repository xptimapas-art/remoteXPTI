import ctypes
from ctypes import wintypes as w
import unittest
from unittest.mock import MagicMock
from desktop_window import DesktopWindow, _MINMAXINFO, _MONITORINFO


class DesktopDragTests(unittest.TestCase):
    def test_integrated_frame_does_not_label_installed_clients_as_development(self):
        for development in (False, True):
            state = DesktopWindow(development=development).window_state()
            self.assertTrue(state['integrated'])
            self.assertEqual(state['development'], development)

    def test_native_drag_uses_clicked_screen_position_including_negative_monitors(self):
        for x, y in [(350, 180), (-1920, 120), (40, -600)]:
            with self.subTest(x=x, y=y):
                bridge = DesktopWindow()
                bridge._user = MagicMock()
                bridge._hwnd = 0x123456789
                bridge._on_ui = lambda action: action()
                def cursor(pointer):
                    point = ctypes.cast(pointer, ctypes.POINTER(w.POINT))
                    point.contents.x, point.contents.y = x, y
                    return True
                bridge._user.GetCursorPos.side_effect = cursor
                bridge.begin_drag()
                bridge._user.PostMessageW.assert_called_once_with(bridge._hwnd, 0xA1, 2, (x & 0xFFFF) | ((y & 0xFFFF) << 16))

    def test_failed_cursor_query_does_not_start_drag_or_capture_mouse(self):
        bridge = DesktopWindow()
        bridge._user = MagicMock()
        bridge._user.GetCursorPos.return_value = False
        bridge._on_ui = lambda action: action()
        bridge.begin_drag()
        bridge._user.ReleaseCapture.assert_not_called()
        bridge._user.PostMessageW.assert_not_called()


class DesktopMaximizeTests(unittest.TestCase):
    def make_bridge(self, monitor_bounds, work_area):
        bridge = DesktopWindow()
        bridge._user = MagicMock()
        bridge._hwnd = 0x123456789
        bridge._user.MonitorFromWindow.return_value = 0x987654321
        def monitor_info(handle, pointer):
            info = ctypes.cast(pointer, ctypes.POINTER(_MONITORINFO)).contents
            self.assertEqual(info.cbSize, ctypes.sizeof(_MONITORINFO))
            info.rcMonitor = w.RECT(*monitor_bounds)
            info.rcWork = w.RECT(*work_area)
            return True
        bridge._user.GetMonitorInfoW.side_effect = monitor_info
        return bridge

    def test_maximize_stays_in_current_monitor_and_outside_taskbar(self):
        layouts = [
            ((0, 0, 1920, 1080), (0, 0, 1920, 1040)),
            ((1920, 0, 3840, 1080), (1920, 0, 3840, 1040)),
            ((-1920, 0, 0, 1080), (-1920, 0, 0, 1040)),
            ((0, -1440, 2560, 0), (0, -1440, 2560, -48)),
            ((-2560, -320, 0, 1120), (-2512, -320, 0, 1120)),
            ((1920, 240, 4480, 1680), (1920, 288, 4480, 1680)),
            ((3840, -640, 7680, 1520), (3840, -640, 7680, 1440)),
        ]
        for bounds, work in layouts:
            with self.subTest(bounds=bounds, work=work):
                bridge = self.make_bridge(bounds, work)
                limits = _MINMAXINFO()
                # WinForms supplies the window's existing resize restrictions.
                limits.ptMinTrackSize = w.POINT(940, 620)
                limits.ptMaxTrackSize = w.POINT(10000, 10000)
                bridge._constrain_maximize(bridge._hwnd, ctypes.addressof(limits))
                left = bounds[0] + limits.ptMaxPosition.x
                top = bounds[1] + limits.ptMaxPosition.y
                self.assertEqual((left, top, left + limits.ptMaxSize.x,
                                  top + limits.ptMaxSize.y), work)
                self.assertEqual((limits.ptMinTrackSize.x, limits.ptMinTrackSize.y), (940, 620))
                self.assertEqual((limits.ptMaxTrackSize.x, limits.ptMaxTrackSize.y), (10000, 10000))
                bridge._user.MonitorFromWindow.assert_called_once_with(bridge._hwnd, 2)

    def test_monitor_is_requeried_when_window_moves_to_another_display(self):
        bridge = self.make_bridge((0, 0, 1920, 1080), (0, 0, 1920, 1040))
        limits = _MINMAXINFO()
        bridge._constrain_maximize(bridge._hwnd, ctypes.addressof(limits))
        bridge._user.GetMonitorInfoW.side_effect = self.make_bridge(
            (-2560, -320, 0, 1120), (-2560, -280, 0, 1120)
        )._user.GetMonitorInfoW.side_effect
        bridge._constrain_maximize(bridge._hwnd, ctypes.addressof(limits))
        self.assertEqual((limits.ptMaxPosition.x, limits.ptMaxPosition.y), (0, 40))
        self.assertEqual((limits.ptMaxSize.x, limits.ptMaxSize.y), (2560, 1400))
        self.assertEqual(bridge._user.MonitorFromWindow.call_count, 2)

    def test_failed_monitor_query_keeps_native_maximize_limits(self):
        for failure in ('missing', 'query', 'invalid'):
            with self.subTest(failure=failure):
                bridge = self.make_bridge((0, 0, 1920, 1080), (0, 0, 0, 0))
                if failure == 'missing':
                    bridge._user.MonitorFromWindow.return_value = None
                elif failure == 'query':
                    bridge._user.GetMonitorInfoW.side_effect = None
                    bridge._user.GetMonitorInfoW.return_value = False
                limits = _MINMAXINFO()
                limits.ptMaxPosition = w.POINT(3, 4)
                limits.ptMaxSize = w.POINT(1920, 1080)
                before = bytes(limits)
                bridge._constrain_maximize(bridge._hwnd, ctypes.addressof(limits))
                self.assertEqual(bytes(limits), before)

    def test_queued_toggle_reads_window_state_on_ui_thread(self):
        bridge = DesktopWindow()
        bridge._window = MagicMock()
        bridge._user = MagicMock()
        bridge._user.IsZoomed.return_value = False
        pending = []
        bridge._on_ui = pending.append
        bridge.toggle_maximize()
        bridge._user.IsZoomed.return_value = True
        pending.pop()()
        bridge._window.restore.assert_called_once()
        bridge._window.maximize.assert_not_called()


if __name__ == '__main__':
    unittest.main()
