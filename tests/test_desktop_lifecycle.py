import unittest
import ctypes
from ctypes import wintypes as w
from unittest.mock import MagicMock, PropertyMock, patch

from desktop_lifecycle import stop_tray_icon
from desktop_dev_control import message_name, send_command


class TrayLifecycleTests(unittest.TestCase):
    def test_icon_is_hidden_synchronously_before_stopping_message_loop(self):
        actions = []
        icon = MagicMock()
        visible = PropertyMock(side_effect=lambda *args: actions.append(('visible', args)))
        type(icon).visible = visible
        icon.stop.side_effect = lambda: actions.append(('stop', ()))
        stop_tray_icon(icon)
        self.assertEqual(actions, [('visible', (False,)), ('stop', ())])

    def test_stop_is_still_attempted_if_shell_rejects_hide(self):
        icon = MagicMock()
        type(icon).visible = PropertyMock(side_effect=OSError('fixture'))
        with patch('desktop_lifecycle.logging.getLogger'):
            stop_tray_icon(icon)
        icon.stop.assert_called_once()

    def test_missing_tray_and_stop_failure_do_not_prevent_app_cleanup(self):
        stop_tray_icon(None)
        icon = MagicMock()
        icon.stop.side_effect = OSError('fixture')
        with patch('desktop_lifecycle.logging.getLogger'):
            stop_tray_icon(icon)

    def test_dev_messages_are_scoped_to_checkout_and_action(self):
        with patch('desktop_dev_control.development_id', return_value='fixture-a'):
            reload_a = message_name('reload')
            stop_a = message_name('stop')
        with patch('desktop_dev_control.development_id', return_value='fixture-b'):
            reload_b = message_name('reload')
        self.assertEqual(len({reload_a, stop_a, reload_b}), 3)
        with self.assertRaises(ValueError):
            message_name('arbitrary')


class DevCommandOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.user, self.kernel = MagicMock(), MagicMock()
        self.kernel.OpenProcess.return_value = 987
        self.user.RegisterWindowMessageW.return_value = 0xC001
        self.user.PostMessageW.return_value = True
        self.path = r'C:\Python312\pythonw.exe'
        self.title = 'RemoteXPTI DEV - RDP Quick Launcher'
        self.owner = 77
        def executable(handle, flags, buffer, size):
            buffer.value = self.path
            return True
        self.kernel.QueryFullProcessImageNameW.side_effect = executable
        self.user.EnumWindows.side_effect = lambda callback, _: callback(0x123456789, 0)
        def owner(hwnd, pointer):
            ctypes.cast(pointer, ctypes.POINTER(w.DWORD))[0] = self.owner
            return 1
        self.user.GetWindowThreadProcessId.side_effect = owner
        def title(hwnd, buffer, length):
            buffer.value = self.title
            return len(buffer.value)
        self.user.GetWindowTextW.side_effect = title
        for patcher in (
            patch('desktop_dev_control.ctypes.WinDLL', side_effect=[self.user, self.kernel]),
            patch('desktop_dev_control.sys.executable', r'C:\Python312\python.exe'),
            patch('desktop_dev_control.get_window_title', return_value=self.title),
            patch('desktop_dev_control.is_development', return_value=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_only_matching_pid_dev_title_and_interpreter_receive_command(self):
        self.assertTrue(send_command('reload', 77))
        self.user.PostMessageW.assert_called_once_with(0x123456789, 0xC001, 0, 0)
        self.kernel.CloseHandle.assert_called_once_with(987)

    def test_installed_client_executable_is_rejected_before_any_message(self):
        self.path = r'C:\Programs\RemoteXPTI\RemoteXPTI.exe'
        self.assertFalse(send_command('stop', 77))
        self.user.EnumWindows.assert_not_called()
        self.user.PostMessageW.assert_not_called()

    def test_wrong_owner_or_client_title_cannot_receive_message(self):
        self.owner = 78
        self.assertFalse(send_command('reload', 77))
        self.user.PostMessageW.assert_not_called()

    def test_installed_client_title_is_rejected(self):
        self.title = 'RemoteXPTI - RDP Quick Launcher'
        self.assertFalse(send_command('stop', 77))
        self.user.PostMessageW.assert_not_called()


if __name__ == '__main__':
    unittest.main()
