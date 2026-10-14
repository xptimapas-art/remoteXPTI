import ctypes
from ctypes import wintypes as w
import unittest
from unittest.mock import MagicMock
from desktop_window import DesktopWindow


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


if __name__ == '__main__':
    unittest.main()
