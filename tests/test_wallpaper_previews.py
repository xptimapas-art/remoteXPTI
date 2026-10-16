"""Click-scoped, bounded wallpaper reads, cache integrity and transport isolation."""
import ast
import base64
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from wallpaper_previews import WallpaperPreviews, identity, thumbnail, REFRESH_SECONDS
from wallpaper_transport import WallpaperError, normalize_host, read_wallpaper


def image_bytes():
    output = io.BytesIO()
    Image.new('RGB', (1000, 600), '#28556a').save(output, 'JPEG')
    return output.getvalue()


def server(key='one'):
    return dict(id=key, host='192.0.2.20', port=3389, username='fixture',
                password_plain='test-only-password')


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1000000
        self.fetch = MagicMock(return_value=image_bytes())
        self.ready = MagicMock()
        self.current = {'one': server(), 'two': server('two'), 'three': server('three')}
        self.manager = WallpaperPreviews(self.root / 'images', self.root / 'cache.json',
                                        enabled=True, fetch=self.fetch, clock=lambda: self.now,
                                        current_server=lambda key: self.current.get(key),
                                        on_ready=self.ready)
        self.addCleanup(self.manager.stop)

    def drain(self):
        deadline = time.monotonic() + 4
        while self.manager._pending and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.manager._pending)

    def launch(self, key='one'):
        result = self.manager.request(self.current[key])
        self.drain()
        return result

    def test_no_sweep_on_creation_listing_or_time_change(self):
        for item in self.current.values():
            self.assertIsNone(self.manager.image_url(item))
        self.now += REFRESH_SECONDS * 10
        self.fetch.assert_not_called()
        self.assertTrue(self.launch())
        self.assertEqual([call.args[0]['id'] for call in self.fetch.call_args_list], ['one'])

    def test_channel_change_is_checked_at_click_without_restarting_or_sweeping(self):
        allowed = [False]
        self.manager.enabled = lambda: allowed[0]
        self.assertFalse(self.launch())
        self.fetch.assert_not_called()
        allowed[0] = True
        self.fetch.assert_not_called()
        self.assertTrue(self.launch())
        allowed[0] = False
        self.now += REFRESH_SECONDS + 1
        self.assertFalse(self.launch())
        self.assertEqual(self.fetch.call_count, 1)

    def test_disabling_channel_during_fetch_does_not_commit_or_notify(self):
        allowed = [True]
        self.manager.enabled = lambda: allowed[0]
        def disable(item):
            allowed[0] = False
            return image_bytes()
        self.fetch.side_effect = disable
        self.launch()
        self.assertIsNone(self.manager.image_url(server()))
        self.ready.assert_not_called()
        self.assertFalse((self.root / 'images').exists())

    def test_freshness_is_checked_only_on_access_and_survives_restart(self):
        self.assertTrue(self.launch())
        url = self.manager.image_url(server())
        self.assertIn('?v=', url)
        self.assertFalse(self.launch())
        self.now += REFRESH_SECONDS + 1
        self.assertEqual(self.fetch.call_count, 1)
        self.manager = WallpaperPreviews(self.root / 'images', self.root / 'cache.json',
                                        enabled=True, fetch=self.fetch, clock=lambda: self.now)
        self.assertTrue(self.launch())
        self.assertEqual(self.fetch.call_count, 2)

    def test_failure_keeps_old_image_and_retries_only_on_later_click(self):
        self.launch()
        old_url = self.manager.image_url(server())
        self.now += REFRESH_SECONDS + 1
        self.fetch.side_effect = WallpaperError('unavailable')
        self.assertTrue(self.launch())
        self.assertEqual(self.manager.image_url(server()), old_url)
        self.assertFalse(self.launch())
        self.now += 601
        self.fetch.assert_called()
        self.assertEqual(self.fetch.call_count, 2)
        self.assertTrue(self.launch())

    def test_authentication_failure_has_long_cooldown(self):
        self.fetch.side_effect = WallpaperError('authentication')
        self.assertTrue(self.launch())
        self.now += 601
        self.assertFalse(self.launch())
        self.now += REFRESH_SECONDS
        self.assertTrue(self.launch())
        self.assertEqual(self.fetch.call_count, 2)

    def test_pending_deduplicated_and_max_two_reads(self):
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        def fetch(item):
            entered.set()
            release.wait(3)
            return image_bytes()
        self.fetch.side_effect = fetch
        self.assertTrue(self.manager.request(server()))
        self.assertTrue(entered.wait(1))
        self.assertFalse(self.manager.request(server()))
        self.assertTrue(self.manager.request(server('two')))
        self.assertFalse(self.manager.request(server('three')))
        release.set()
        self.drain()
        self.assertEqual(self.fetch.call_count, 2)

    def test_changed_or_deleted_server_cannot_receive_stale_wallpaper(self):
        def change(item):
            self.current['one']['host'] = '192.0.2.99'
            return image_bytes()
        self.fetch.side_effect = change
        self.launch()
        self.assertIsNone(self.manager.image_url(self.current['one']))
        self.ready.assert_not_called()
        self.assertFalse((self.root / 'images').exists())

    def test_invalid_image_preserves_legacy_and_no_credentials_persist(self):
        (self.root / 'images').mkdir()
        (self.root / 'images/one.png').write_bytes(image_bytes())
        self.fetch.return_value = b'not an image'
        self.launch()
        self.assertIn('/thumbnails/one.png?', self.manager.image_url(server()))
        metadata = (self.root / 'cache.json').read_text()
        self.assertNotIn('test-only-password', metadata)
        self.assertNotIn('fixture', metadata)
        self.assertNotIn('192.0.2.20', metadata)
        self.ready.assert_not_called()

    def test_save_failure_keeps_legacy_and_releases_slot(self):
        (self.root / 'images').mkdir()
        (self.root / 'images/one.png').write_bytes(image_bytes())
        with patch('wallpaper_previews.write_json_atomic', side_effect=OSError('disk full')):
            self.assertTrue(self.launch())
        self.assertIn('/thumbnails/one.png?', self.manager.image_url(server()))
        self.ready.assert_not_called()
        self.now += 601
        self.assertTrue(self.launch())
        self.assertIn('-wallpaper-', self.manager.image_url(server()))

    def test_target_change_hides_previous_account_image(self):
        self.launch()
        changed = dict(server(), username='different-account')
        self.assertIsNone(self.manager.image_url(changed))

    def test_callback_failure_does_not_invalidate_success(self):
        self.ready.side_effect = RuntimeError('UI disconnected')
        self.assertTrue(self.launch())
        self.assertEqual(self.manager._state['one']['result'], 'ok')
        self.assertFalse(self.launch())

    def test_disabled_and_stopped_never_read(self):
        self.manager.enabled = False
        self.assertFalse(self.launch())
        self.manager.enabled = True
        self.manager.stop()
        self.assertFalse(self.launch())
        self.fetch.assert_not_called()

    def test_thumbnail_size_and_rejects_oversize(self):
        with Image.open(io.BytesIO(thumbnail(image_bytes()))) as result:
            self.assertLessEqual(result.width, 640)
            self.assertLessEqual(result.height, 360)
            self.assertEqual(result.format, 'PNG')
        with self.assertRaises(WallpaperError):
            thumbnail(b'x' * 524289)
        self.assertFalse(self.manager.request(dict(server(), id='../outside')))
        self.fetch.assert_not_called()


class TransportTests(unittest.TestCase):
    @patch('wallpaper_transport.socket.create_connection')
    @patch('wallpaper_transport.winrm.Session')
    def test_existing_winrm_exact_credentials_encrypted_and_closed(self, session, connect):
        data = image_bytes()
        session.return_value.run_ps.return_value = types.SimpleNamespace(
            status_code=0, std_out=json.dumps(dict(status='ok', image=base64.b64encode(data).decode())).encode())
        self.assertEqual(read_wallpaper(server()), data)
        session.assert_called_once_with('https://192.0.2.20:5986/wsman',
                                       auth=('fixture', 'test-only-password'), transport='ntlm',
                                       proxy=None, server_cert_validation='validate',
                                       message_encryption='always', operation_timeout_sec=8, read_timeout_sec=12)
        session.return_value.protocol.transport.session.close.assert_called_once()

    @patch('wallpaper_transport.socket.create_connection', side_effect=OSError)
    @patch('wallpaper_transport.winrm.Session')
    def test_no_open_service_means_no_authentication(self, session, connect):
        with self.assertRaises(WallpaperError):
            read_wallpaper(server())
        session.assert_not_called()
        self.assertEqual(connect.call_count, 2)

    @patch('wallpaper_transport.socket.create_connection')
    @patch('wallpaper_transport.winrm.Session')
    def test_authentication_not_retried_or_leaked(self, session, connect):
        from winrm.exceptions import InvalidCredentialsError
        session.return_value.run_ps.side_effect = InvalidCredentialsError('test-only-password')
        with self.assertRaisesRegex(WallpaperError, '^authentication$'):
            read_wallpaper(server())
        session.assert_called_once()
        session.return_value.run_ps.assert_called_once()

    def test_target_rejects_urls_and_injection(self):
        self.assertEqual(normalize_host('192.0.2.20:3390'), '192.0.2.20')
        self.assertEqual(normalize_host('[2001:db8::1]:3390'), '2001:db8::1')
        for value in ('https://example.test', 'host;command', 'user@host', '../path', ''):
            with self.assertRaises(WallpaperError):
                normalize_host(value)


class ConnectRouteTests(unittest.TestCase):
    def test_only_successful_access_requests_that_servers_wallpaper(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'desktop_backend.py').read_text(encoding='utf-8-sig'))
        route = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'connect_server')
        route = deepcopy(route)
        route.decorator_list = []
        namespace = {'ConnectRequest': object, 'HTTPException': RuntimeError,
                     'storage_mgr': MagicMock(), 'RDPManager': MagicMock(),
                     'wallpaper_previews': MagicMock(), 'log': MagicMock(),
                     'threading': types.SimpleNamespace(Thread=lambda target, **kwargs: types.SimpleNamespace(start=target))}
        exec(compile(ast.Module(body=[route], type_ignores=[]), '<connect route>', 'exec'), namespace)
        namespace['storage_mgr'].get_server.return_value = server()
        namespace['RDPManager'].launch_rdp.return_value = (True, 'ok')
        namespace['connect_server'](types.SimpleNamespace(server_id='one'))
        namespace['wallpaper_previews'].request.assert_called_once_with(server())
        namespace['wallpaper_previews'].reset_mock()
        namespace['RDPManager'].launch_rdp.return_value = (False, 'failed')
        namespace['connect_server'](types.SimpleNamespace(server_id='one'))
        namespace['wallpaper_previews'].request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
