import ctypes
import ast
from ctypes import wintypes as w
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from windows_single_instance import WindowsSingleInstance


class SingleInstanceTests(unittest.TestCase):
    def setUp(self):
        self.kernel = MagicMock()
        self.user = MagicMock()
        self.kernel.CreateMutexW.return_value = 0x123456789
        self.patches = [patch('ctypes.WinDLL', side_effect=[self.kernel, self.user]),
                        patch('ctypes.set_last_error'), patch('ctypes.get_last_error', return_value=0)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.guard = WindowsSingleInstance('test-only-mutex')
        self.addCleanup(self.guard.close)

    def windows(self, definitions):
        # definitions: handle, title, pid, executable (None means inaccessible).
        def enum(callback, _):
            for hwnd, *_ in definitions:
                if not callback(hwnd, 0):
                    break
            return True
        self.user.EnumWindows.side_effect = enum
        by_hwnd = {entry[0]: entry[1:] for entry in definitions}

        def text(hwnd, buffer, size):
            buffer.value = by_hwnd[hwnd][0][:size - 1]
            return len(buffer.value)
        self.user.GetWindowTextW.side_effect = text

        def pid(hwnd, pointer):
            ctypes.cast(pointer, ctypes.POINTER(w.DWORD))[0] = by_hwnd[hwnd][1]
            return 1
        self.user.GetWindowThreadProcessId.side_effect = pid
        paths = {entry[2]: entry[3] for entry in definitions}
        self.kernel.OpenProcess.side_effect = lambda access, inherit, pid: pid if paths[pid] else 0

        def image(process, flags, buffer, size):
            buffer.value = paths[process]
            return True
        self.kernel.QueryFullProcessImageNameW.side_effect = image

    def test_mutex_is_primary_even_when_explorer_has_same_window_title(self):
        self.windows([(1, 'RemoteXPTI', os.getpid() + 1, r'C:\Windows\explorer.exe')])
        self.assertFalse(self.guard.already_running)
        self.assertFalse(self.guard.focus('RemoteXPTI'))
        self.user.ShowWindow.assert_not_called()

    def test_find_real_app_after_shell_proxy_and_restore_hidden_window(self):
        self.windows([(1, 'RemoteXPTI', os.getpid() + 1, r'C:\Windows\explorer.exe'),
                      (0x123456788, 'RemoteXPTI', os.getpid() + 2, sys.executable)])
        self.assertTrue(self.guard.focus('RemoteXPTI'))
        self.user.ShowWindow.assert_called_once_with(0x123456788, 9)
        self.user.SetForegroundWindow.assert_called_once_with(0x123456788)

    def test_ignore_current_process_and_inaccessible_or_other_titles(self):
        self.windows([(1, 'RemoteXPTI', os.getpid(), sys.executable),
                      (2, 'RemoteXPTI', os.getpid() + 1, None),
                      (3, 'RemoteXPTI DEV', os.getpid() + 2, sys.executable)])
        self.assertFalse(self.guard.focus('RemoteXPTI'))

    def test_tray_restore_only_targets_current_process(self):
        self.windows([(1, 'RemoteXPTI', os.getpid() + 1, sys.executable),
                      (2, 'RemoteXPTI', os.getpid(), sys.executable)])
        self.assertTrue(self.guard.focus('RemoteXPTI', current_only=True))
        self.user.ShowWindow.assert_called_once_with(2, 9)
        self.kernel.OpenProcess.assert_not_called()

    def test_preserve_64_bit_handle_and_release_once(self):
        self.assertIs(self.kernel.CreateMutexW.restype, w.HANDLE)
        self.assertIs(self.kernel.OpenProcess.restype, w.HANDLE)
        self.guard.close()
        self.guard.close()
        self.kernel.CloseHandle.assert_called_once_with(0x123456789)

    def test_existing_mutex_is_detected_from_its_create_call(self):
        with patch('ctypes.WinDLL', side_effect=[self.kernel, self.user]), \
                patch('ctypes.get_last_error', return_value=183):
            second = WindowsSingleInstance('test-only-mutex')
        self.assertTrue(second.already_running)
        second.close()

    def test_process_query_failure_closes_handle_without_focusing(self):
        self.windows([(1, 'RemoteXPTI', os.getpid() + 1, sys.executable)])
        self.kernel.QueryFullProcessImageNameW.side_effect = None
        self.kernel.QueryFullProcessImageNameW.return_value = False
        self.assertFalse(self.guard.focus('RemoteXPTI'))
        self.kernel.CloseHandle.assert_called_once_with(os.getpid() + 1)


class LauncherInstanceTests(unittest.TestCase):
    def launcher(self, running, development=True):
        source = Path(__file__).resolve().parents[1] / 'launch_modern_desktop.py'
        tree = ast.parse(source.read_text('utf-8'))
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        guard = MagicMock(already_running=running)
        namespace = {'WindowsSingleInstance': MagicMock(return_value=guard),
                     'get_mutex_name': lambda: 'fixture', 'get_window_title': lambda: 'fixture',
                     'get_app_user_model_id': lambda: 'fixture', '_dbg': MagicMock(),
                     'ctypes': MagicMock(), 'webview': MagicMock(), 'is_backend_running': lambda: True,
                     'is_development': lambda: development, 'stop_tray_icon': MagicMock(),
                     'URL': 'http://127.0.0.1:1'}
        exec(compile(ast.Module(body=[main], type_ignores=[]), str(source), 'exec'), namespace)
        return namespace, guard

    def test_primary_launch_creates_window_without_title_only_exit(self):
        namespace, guard = self.launcher(False)
        namespace['webview'].create_window.side_effect = SystemExit('window requested')
        with self.assertRaisesRegex(SystemExit, 'window requested'):
            namespace['main']()
        namespace['webview'].create_window.assert_called_once()
        guard.focus.assert_not_called()
        guard.close.assert_called_once()

    def test_duplicate_launch_only_restores_existing_window(self):
        namespace, guard = self.launcher(True)
        namespace['main']()
        guard.focus.assert_called_once_with('fixture')
        namespace['webview'].create_window.assert_not_called()
        guard.close.assert_called_once()

    def test_installed_client_and_development_use_the_same_integrated_frame(self):
        for development in (False, True):
            with self.subTest(development=development):
                namespace, guard = self.launcher(False, development)
                namespace['webview'].create_window.side_effect = SystemExit('window requested')
                with self.assertRaisesRegex(SystemExit, 'window requested'):
                    namespace['main']()
                options = namespace['webview'].create_window.call_args.kwargs
                self.assertTrue(options['frameless'])
                self.assertIsNotNone(options['js_api'])
                self.assertEqual(options['js_api'].window_state()['development'], development)


if __name__ == '__main__':
    unittest.main()
