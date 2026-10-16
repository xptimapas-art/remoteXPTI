import ast
import json
import sys
import tempfile
import threading
import types
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.modules.setdefault('logger', types.SimpleNamespace(log=MagicMock()))
from tuya_access_manager import TuyaAccessManager


class DoorConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = object.__new__(TuyaAccessManager)
        self.manager._lock = threading.RLock()
        self.manager._cloud_lock = threading.RLock()
        self.manager._door_trigger_lock = threading.Lock()
        self.manager.config_path = Path(self.temp.name) / 'doors_config.json'
        self.manager.config = {
            'enabled': True, 'feedback_sound': False, 'unknown_preference': 'keep',
            'doors': [
                {'id': 'a', 'name': 'Biometria', 'mode': 'hikvision', 'hotkey': 'F7', 'password': 'test-only', 'legacy': {'keep': True}},
                {'id': 'b', 'name': 'Portão', 'hotkey': 'F8', 'scene_id': 'test-scene', 'camera': {'source': 'external', 'password': 'dummy'}},
            ],
        }
        self.manager.config_path.write_text(json.dumps(self.manager.config), encoding='utf-8')
        self.manager.reload_hotkeys = MagicMock()
        # Prevent threads and remote synchronization; only local fixture files are used.
        self.start = patch('tuya_access_manager.threading.Thread').start()
        patch('cloud_sync.CloudSyncManager.can_share_doors', return_value=False).start()
        self.addCleanup(patch.stopall)

    def edit(self, change=None, original=None, delete=False):
        base = deepcopy(self.manager.config['doors'][0])
        self.manager.save_door_config('a', {**base, **(change or {})}, base if original is None else original, delete=delete)

    def test_camera_binding_preserves_credentials_other_doors_and_preferences(self):
        before = deepcopy(self.manager.config)
        self.edit({'camera': {'source': 'door'}, 'name': 'Nova biometria'})
        saved = json.loads(self.manager.config_path.read_text(encoding='utf-8'))
        self.assertEqual(saved['doors'][1], before['doors'][1])
        self.assertEqual(saved['doors'][0]['password'], 'test-only')
        self.assertEqual(saved['doors'][0]['legacy'], {'keep': True})
        self.assertEqual(saved['doors'][0]['camera'], {'source': 'door'})
        self.assertFalse(saved['feedback_sound'])
        self.assertEqual(saved['unknown_preference'], 'keep')
        self.manager.reload_hotkeys.assert_called_once()

    def test_stale_form_cannot_overwrite_another_edit(self):
        stale = deepcopy(self.manager.config['doors'][0])
        self.edit({'name': 'Changed'})
        with self.assertRaisesRegex(ValueError, 'outra janela'):
            self.edit({'name': 'Stale'}, original=stale)
        self.assertEqual(self.manager.config['doors'][0]['name'], 'Changed')

    def test_disk_failure_preserves_file_and_memory(self):
        before = deepcopy(self.manager.config)
        disk = self.manager.config_path.read_bytes()
        with patch('tuya_access_manager.os.replace', side_effect=PermissionError('fixture read-only')):
            with self.assertRaises(PermissionError):
                self.edit({'name': 'Must not persist'})
        self.assertEqual(self.manager.config, before)
        self.assertEqual(self.manager.config_path.read_bytes(), disk)
        self.assertEqual(list(self.manager.config_path.parent.glob('.doors-*.tmp')), [])
        self.manager.reload_hotkeys.assert_not_called()

    def test_duplicate_shortcut_rejected(self):
        with self.assertRaisesRegex(ValueError, 'atalho'):
            self.edit({'hotkey': 'f8'})

    def test_disabled_door_can_keep_a_shared_shortcut(self):
        self.edit({'hotkey': 'F8', 'enabled': False})
        self.assertFalse(self.manager.config['doors'][0]['enabled'])

    def test_new_door_and_delete_preserve_existing_entries(self):
        previous = deepcopy(self.manager.config['doors'])
        new = {'id': 'c', 'name': '  Test door  ', 'camera': {'source': 'none'}}
        self.manager.save_door_config('c', new, None)
        self.assertEqual(self.manager.config['doors'][:2], previous)
        self.assertEqual(self.manager.config['doors'][2]['name'], 'Test door')
        self.edit(delete=True)
        self.assertEqual([d['id'] for d in self.manager.config['doors']], ['b', 'c'])

    def test_existing_id_cannot_be_recreated(self):
        with self.assertRaises(ValueError):
            self.manager.save_door_config('a', {'id': 'a', 'name': 'Duplicate'}, None)

    def test_preferences_do_not_replace_doors(self):
        previous = deepcopy(self.manager.config['doors'])
        self.manager.save_config({'feedback_sound': True}, push_to_cloud=False)
        self.assertEqual(self.manager.config['doors'], previous)

    def test_global_disable_blocks_both_facial_and_tuya_without_network(self):
        self.manager.config['enabled'] = False
        self.manager._open_hikvision_door = MagicMock()
        self.manager._init_cloud_manager = MagicMock()
        for door_id in ('a', 'b'):
            success, message = self.manager.open_door(door_id)
            self.assertFalse(success)
            self.assertIn('desativados', message)
        self.manager._open_hikvision_door.assert_not_called()
        self.manager._init_cloud_manager.assert_not_called()

    def test_runtime_trigger_does_not_invalidate_or_overwrite_form(self):
        original = deepcopy(self.manager.config['doors'][0])
        self.manager.config['doors'][0]['last_triggered'] = 'newer-runtime-value'
        self.manager.save_door_config('a', {**original, 'name': 'Updated'}, original)
        self.assertEqual(self.manager.config['doors'][0]['last_triggered'], 'newer-runtime-value')

    def test_active_qr_cannot_be_replaced_with_an_unpolled_token(self):
        self.manager._polling_qr_thread = MagicMock()
        self.manager._polling_qr_thread.is_alive.return_value = True
        self.assertFalse(self.manager.generate_qr_login()['success'])

    def test_status_reports_session_revision_without_credentials(self):
        self.manager.session_path = Path(self.temp.name) / 'session.json'
        self.manager.session_path.write_text(json.dumps({'user_code': 'fixture', 'password': 'dummy', 'token_info': {'access_token': 'secret-fixture'}}))
        self.manager._cloud_connected = True
        status = self.manager.get_cloud_status()
        self.assertTrue(status['session_revision'])
        self.assertNotIn('dummy', json.dumps(status))
        self.assertNotIn('secret-fixture', json.dumps(status))


class DoorEndpointTests(unittest.TestCase):
    def setUp(self):
        from fastapi import HTTPException
        self.HTTPException = HTTPException
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'desktop_backend.py').read_text('utf-8'))
        handler = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'save_single_door_config')
        handler.decorator_list = []
        self.manager = MagicMock()
        self.gate = MagicMock()
        self.broadcast = MagicMock()
        context = {'tuya_mgr': self.manager, 'require_dev_access': self.gate, 'broadcast_ws': self.broadcast,
                   'HTTPException': HTTPException, 'DoorEditRequest': object}
        exec(compile(ast.Module(body=[handler], type_ignores=[]), '<door-endpoint>', 'exec'), context)
        self.handler = context['save_single_door_config']
        self.request = types.SimpleNamespace(door={'id': 'a', 'name': 'Fixture'}, original=None, delete=False)

    def test_authentication_required_before_editing(self):
        self.gate.side_effect = self.HTTPException(status_code=403)
        with self.assertRaises(self.HTTPException):
            self.handler('a', self.request)
        self.manager.save_door_config.assert_not_called()

    def test_write_failure_is_not_reported_as_success(self):
        self.manager.save_door_config.side_effect = PermissionError('fixture')
        with self.assertRaises(self.HTTPException) as error:
            self.handler('a', self.request)
        self.assertEqual(error.exception.status_code, 500)
        self.broadcast.assert_not_called()

    def test_stale_config_returns_conflict(self):
        self.manager.save_door_config.side_effect = ValueError('stale fixture')
        with self.assertRaises(self.HTTPException) as error:
            self.handler('a', self.request)
        self.assertEqual(error.exception.status_code, 409)
        self.broadcast.assert_not_called()

    def test_success_updates_all_connected_views(self):
        self.assertTrue(self.handler('a', self.request)['success'])
        self.broadcast.assert_called_once_with({'type': 'doors_updated'})


if __name__ == '__main__':
    unittest.main()
