import ast
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Importar o updater não deve abrir os gerenciadores nem escrever logs do usuário.
sys.modules.setdefault('logger', types.SimpleNamespace(log=MagicMock()))
import update_engine as engine
from install_safety import validate_install_dir, close_installed_app
from local_api_security import allow_local_request
from update_bootstrap import confirm_update_startup
from version import CURRENT_VERSION

ROOT = Path(__file__).resolve().parents[1]


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='remotexpti-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = b'MZ' + b'fixture' * 256
        self.manifest = {'version': '99.1.8', 'asset': 'RemoteXPTI.exe', 'update_protocol': 1,
                         'size': len(self.payload), 'sha256': hashlib.sha256(self.payload).hexdigest()}

    def updater(self):
        return engine.SilentAutoUpdater(staging_dir=self.root / 'stage')

    def download(self, updater, payload=None, manifest=None):
        response = io.BytesIO(self.payload if payload is None else payload)
        response.headers = {}
        updater.new_version = '99.1.8'
        with patch.object(engine, 'read_json_url', return_value=manifest or self.manifest), \
                patch.object(engine.urllib.request, 'urlopen', return_value=response):
            updater._download_update_silent(engine.release_url('v99.1.8', 'RemoteXPTI.exe'), 'v99.1.8')

    def test_patch_versions_and_prerelease_order(self):
        self.assertTrue(engine.is_public_version('v2.1.8'))
        self.assertFalse(engine.is_public_version('2.1.9-beta.1'))
        self.assertLess(engine.release_version('2.1.9-beta.1'), engine.release_version('2.1.9'))
        self.assertFalse(engine.is_public_version('release-not-a-version'))

    def test_releases_sorted_filtered_and_assets_exact(self):
        rows = [{'tag_name': 'v2.1.8', 'prerelease': False, 'assets': [{'name': 'RemoteXPTI.exe', 'browser_download_url': 'good'}]},
                {'tag_name': 'v2.1.9-beta.1', 'prerelease': True, 'assets': []},
                {'tag_name': 'v2.1.9', 'draft': True}, {'tag_name': 'bad-tag'},
                {'tag_name': 'v2.1.7', 'assets': [{'name': 'Setup_RemoteXPTI.exe'}]}]
        with patch.object(engine, 'read_json_url', return_value=rows):
            releases = engine.SilentAutoUpdater.fetch_all_releases()
        self.assertEqual([r['tag'] for r in releases], ['v2.1.9-beta.1', 'v2.1.8', 'v2.1.7'])
        self.assertTrue(releases[1]['is_public'])
        self.assertFalse(releases[0]['is_public'])
        self.assertEqual(releases[2]['download_url'], '')

    def test_development_never_downloads_or_edits_version(self):
        updater = self.updater()
        original = (ROOT / 'version.py').read_bytes()
        with patch.object(engine.threading, 'Thread') as thread:
            self.assertFalse(updater.start_background_check(True))
            thread.assert_not_called()
        with self.assertRaises(ValueError):
            updater.prepare_install()
        self.assertEqual((ROOT / 'version.py').read_bytes(), original)
        self.assertEqual(updater.state, 'disabled')

    def test_external_download_rejected(self):
        with self.assertRaises(ValueError):
            engine.validate_download_url('https://example.com/RemoteXPTI.exe', 'v2.1.9')
        with self.assertRaises(ValueError):
            engine.release_url('../../evil', 'RemoteXPTI.exe')

    def test_manifest_rejects_wrong_version_hash_size_protocol(self):
        for key, value in [('version', '2.0.0'), ('sha256', 'x' * 64), ('size', True), ('update_protocol', 0), ('asset', 'Setup.exe')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                engine.validate_manifest({**self.manifest, key: value}, 'v99.1.8')

    def test_download_preserves_installed_exe_and_restores_pending(self):
        target = self.root / 'RemoteXPTI.exe'
        target.write_bytes(b'old executable')
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(target)):
            updater = self.updater()
            self.download(updater)
            self.assertEqual(target.read_bytes(), b'old executable')
            self.assertTrue(updater.update_ready)
            recovered = self.updater()
            self.assertTrue(recovered.update_ready)
            self.assertEqual(recovered.new_version, '99.1.8')

    def test_partial_and_corrupt_downloads_not_ready(self):
        for payload in [self.payload[:-3], b'ZZ' + self.payload[2:], self.payload[:-1] + b'X']:
            with self.subTest(size=len(payload)):
                updater = self.updater()
                with self.assertRaises(ValueError):
                    self.download(updater, payload)
                self.assertFalse(updater.update_ready)
                self.assertFalse(updater.is_downloading)
                self.assertFalse((updater.staging_dir / 'pending.part').exists())

    def test_restart_missing_or_tampered_download_never_launches(self):
        target = self.root / 'RemoteXPTI.exe'
        target.write_bytes(b'old')
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(target)):
            updater = self.updater()
            self.download(updater)
            updater.downloaded_file.unlink()
            with self.assertRaises(OSError), patch.object(engine.subprocess, 'Popen') as launch:
                updater.prepare_install()
            launch.assert_not_called()
            self.assertEqual(target.read_bytes(), b'old')

    def test_only_one_concurrent_check_starts(self):
        with patch.object(sys, 'frozen', True, create=True):
            updater = self.updater()
            real_thread = threading.Thread
            with patch.object(engine.threading, 'Thread') as spawn:
                calls = [real_thread(target=updater.start_background_check) for _ in range(20)]
                for call in calls: call.start()
                for call in calls: call.join()
                self.assertEqual(spawn.call_count, 1)

    def test_final_notification_has_cleared_checking(self):
        updater = self.updater()
        updater.is_checking = True
        states = []
        updater.on_status_callback = lambda _: states.append(updater.is_checking)
        with patch.object(updater, '_get_latest_release_info', return_value=('v' + CURRENT_VERSION, 'unused')):
            updater._worker()
        self.assertFalse(states[-1])

    @unittest.skipUnless(sys.platform == 'win32', 'Diretório de DLLs do Windows')
    def test_frozen_helper_resets_and_restores_dll_directory(self):
        import ctypes
        with patch.object(sys, '_MEIPASS', str(self.root), create=True), \
                patch.object(ctypes.windll.kernel32, 'SetDllDirectoryW') as directory, \
                patch.object(engine.subprocess, 'Popen') as process:
            engine.launch_independent_process(['powershell.exe'], {'PYINSTALLER_RESET_ENVIRONMENT': '1'}, str(self.root))
            self.assertEqual(directory.call_args_list[0].args, (None,))
            self.assertEqual(directory.call_args_list[1].args, (str(self.root),))
            process.assert_called_once()

    def test_frontend_receipt_checks_actual_version(self):
        target = self.root / 'RemoteXPTI.exe'
        receipt = self.root / 'receipt.json'
        job = {'target': str(target), 'receipt': str(receipt), 'token': 'secret', 'version': CURRENT_VERSION}
        engine.write_json_atomic(self.root / 'job.json', job)
        argv = ['RemoteXPTI.exe', '--update-receipt', str(receipt), '--update-token', 'secret']
        with patch.object(sys, 'executable', str(target)):
            self.assertTrue(confirm_update_startup(argv))
            self.assertEqual(json.loads(receipt.read_text())['version'], CURRENT_VERSION)
            job['version'] = '0.0.1'
            engine.write_json_atomic(self.root / 'job.json', job)
            with self.assertRaises(ValueError): confirm_update_startup(argv)

    def test_install_job_uses_manifest_version_and_does_not_swap(self):
        target = self.root / 'RemoteXPTI.exe'
        target.write_bytes(b'original')
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(target)):
            updater = self.updater()
            self.download(updater)
            updater.new_version = '99.1.8-alias-for-display'
            prepared = updater.prepare_install()
            self.assertEqual(prepared['job']['version'], self.manifest['version'])
            self.assertEqual(target.read_bytes(), b'original')
            self.assertTrue(updater.is_applying)
            with self.assertRaises(ValueError): updater.prepare_install()

    def test_installer_requires_dedicated_absolute_dir(self):
        self.assertEqual(validate_install_dir(self.root / 'RemoteXPTI'), self.root / 'RemoteXPTI')
        for path in ['.', 'RemoteXPTI', self.root, Path('C:/')]:
            with self.subTest(path=path), self.assertRaises(ValueError): validate_install_dir(path)

    def test_installer_never_terminates_unrelated_python(self):
        own = MagicMock(pid=123, info={'exe': str(self.root / 'RemoteXPTI' / 'RemoteXPTI.exe')})
        unrelated = MagicMock(pid=124, info={'exe': str(self.root / 'python.exe')})
        with patch('psutil.process_iter', return_value=[own, unrelated]), patch('psutil.wait_procs', return_value=([], [])):
            close_installed_app(self.root / 'RemoteXPTI')
        own.terminate.assert_called_once()
        unrelated.terminate.assert_not_called()

    def test_local_api_rejects_foreign_websites_and_hosts(self):
        self.assertTrue(allow_local_request('127.0.0.1:9000', 'http://127.0.0.1:9000'))
        self.assertTrue(allow_local_request('127.0.0.1:9000'))
        for args in [('evil.test:9000', None), ('127.0.0.1:9000', 'https://evil.test'),
                     ('127.0.0.1:9000', 'null'), ('127.0.0.1:9000', 'http://127.0.0.1:5173'),
                     ('127.0.0.1:9000', None, 'cross-site')]:
            with self.subTest(args=args): self.assertFalse(allow_local_request(*args))

    def test_backend_restart_rejects_before_spawning(self):
        tree = ast.parse((ROOT / 'desktop_backend.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'apply_update_restart')
        node.decorator_list = []
        from fastapi import HTTPException
        updater = MagicMock()
        updater.prepare_install.side_effect = ValueError('missing download')
        env = {'updater_instance': updater, 'HTTPException': HTTPException, 'threading': MagicMock()}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'endpoint', 'exec'), env)
        with self.assertRaises(HTTPException) as error: env['apply_update_restart']()
        self.assertEqual(error.exception.status_code, 409)
        env['threading'].Thread.assert_not_called()

    @unittest.skipUnless(sys.platform == 'win32', 'Helper específico do Windows')
    def test_helper_real_copy_success_and_rollback(self):
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
                                 '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'tests/helper_integration.ps1'),
                                 '-TestRoot', str(self.root), '-HelperPath', str(ROOT / 'update_helper.ps1')],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
