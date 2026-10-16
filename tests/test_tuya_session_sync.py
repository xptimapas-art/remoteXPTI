import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("logger", types.SimpleNamespace(log=MagicMock()))
from cloud_sync import CloudSyncManager
from tuya_access_manager import TuyaAccessManager
from config_manager import ConfigManager
import tuya_devices


def session(timestamp=2000000000000):
    return {"client_id": "fixture", "user_code": "fixture", "terminal_id": "fixture",
            "endpoint": "https://fixture.invalid", "token_info": {"t": timestamp, "expire_time": 7200,
            "access_token": "fixture-access", "refresh_token": "fixture-refresh"}}


class CloudSessionTests(unittest.TestCase):
    def setUp(self):
        config = patch("cloud_sync.ConfigManager")
        self.cfg = config.start()
        self.addCleanup(config.stop)
        self.cfg.return_value.get_supabase_config.return_value = {
            "url": "https://fixture.invalid", "key": "fixture", "enabled": False, "session_sync_enabled": True}

    def response(self, body, status=200):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(body).encode()
        response.status = status
        return response

    def test_development_can_share_sessions_while_configuration_sync_is_off(self):
        with patch("cloud_sync.urllib.request.urlopen", return_value=self.response([{"notes": json.dumps(session())}])):
            self.assertIsNotNone(CloudSyncManager.fetch_tuya_session())
        self.assertFalse(CloudSyncManager.is_configured())

    def test_older_session_never_overwrites_newer_cloud_login(self):
        with patch.object(CloudSyncManager, "fetch_tuya_session", return_value=json.dumps(session(3000000000000))), \
                patch("cloud_sync.urllib.request.urlopen") as request:
            self.assertFalse(CloudSyncManager.push_tuya_session(json.dumps(session())))
        request.assert_not_called()

    def test_conflicting_concurrent_renewal_is_not_overwritten(self):
        with patch.object(CloudSyncManager, "fetch_tuya_session", return_value=json.dumps(session(1000000000000))), \
                patch("cloud_sync.urllib.request.urlopen", return_value=self.response([])) as request:
            self.assertFalse(CloudSyncManager.push_tuya_session(json.dumps(session())))
        sent = request.call_args.args[0]
        self.assertEqual(sent.method, "PATCH")
        self.assertIn("notes=eq.", sent.full_url)
        self.assertEqual(set(json.loads(sent.data)), {"notes"})

    def test_same_session_does_not_create_a_sync_loop(self):
        with patch.object(CloudSyncManager, "fetch_tuya_session", return_value=json.dumps(session())), \
                patch("cloud_sync.urllib.request.urlopen") as request:
            self.assertTrue(CloudSyncManager.push_tuya_session(json.dumps(session())))
        request.assert_not_called()

    def test_unknown_cloud_state_only_allows_insert_without_overwriting(self):
        with patch.object(CloudSyncManager, "fetch_tuya_session", return_value=None), \
                patch("cloud_sync.urllib.request.urlopen", return_value=self.response([])) as request:
            self.assertFalse(CloudSyncManager.push_tuya_session(json.dumps(session())))
        self.assertIn("ignore-duplicates", request.call_args.args[0].get_header("Prefer"))

    def test_explicit_session_opt_out_prevents_network_calls(self):
        self.cfg.return_value.get_supabase_config.return_value["session_sync_enabled"] = False
        with patch("cloud_sync.urllib.request.urlopen") as request:
            self.assertIsNone(CloudSyncManager.fetch_tuya_session())
            self.assertFalse(CloudSyncManager.push_tuya_session(json.dumps(session())))
        request.assert_not_called()

    def test_development_defaults_keep_shared_login_but_isolate_configurations(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("config_manager.get_config_file", return_value=Path(directory)/"config.json"), \
                patch("config_manager.is_development", return_value=True):
            config = object.__new__(ConfigManager)
            config._init()
        self.assertFalse(config.get_supabase_config()["enabled"])
        self.assertTrue(config.get_supabase_config()["session_sync_enabled"])

    def test_device_sync_cannot_publish_local_disable_switches(self):
        self.cfg.return_value.get_supabase_config.return_value["enabled"] = True
        cfg = {"enabled": False, "hotkeys_enabled": False, "feedback_sound": False,
               "doors": [{"id": "a", "mode": "cloud_scene"}, {"id": "b", "mode": "hikvision", "password": "local-only"}]}
        with patch("cloud_sync.urllib.request.urlopen", return_value=self.response({})) as request:
            self.assertTrue(CloudSyncManager.push_doors_config(cfg))
        published = json.loads(json.loads(request.call_args.args[0].data)[0]["notes"])
        self.assertEqual(published, {"doors": [{"id": "a", "mode": "cloud_scene"}]})


class DoorSessionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = object.__new__(TuyaAccessManager)
        self.manager._lock = threading.RLock()
        self.manager._cloud_lock = threading.RLock()
        self.manager._door_trigger_lock = threading.Lock()
        self.manager.session_path = Path(self.temp.name) / "session.json"
        self.manager.session_path.write_text(json.dumps(session()), encoding="utf-8")
        self.manager._first_init = True
        self.manager._access_logs = []
        self.manager.config = {"enabled": True, "feedback_sound": False,
                               "doors": [{"id": "a", "name": "fixture", "scene_id": "fixture", "home_id": "fixture"}]}
        self.manager._manager = self.sdk()
        callback = tuya_devices.on_session_saved
        self.addCleanup(setattr, tuya_devices, "on_session_saved", callback)

    def sdk(self):
        return types.SimpleNamespace(trigger_scene=MagicMock(),
            customer_api=types.SimpleNamespace(token_info=types.SimpleNamespace(expire_time=(time.time()+3600)*1000)))

    def test_tuya_expiration_uses_timestamp_plus_lifetime(self):
        self.assertEqual(tuya_devices.session_expires_at(session()), 2000000000+7200)

    def test_old_cloud_session_cannot_replace_valid_local_session(self):
        with patch.object(CloudSyncManager, "fetch_tuya_session", return_value=json.dumps(session(1000000000000))), \
                patch.object(tuya_devices, "build_manager") as build:
            self.manager._init_cloud_manager(force_sync=True)
        self.assertEqual(build.call_args.args[0], session())
        self.assertEqual(json.loads(self.manager.session_path.read_text()), session())

    def test_received_newer_session_is_atomic_and_not_pushed_back(self):
        newer = session(3000000000000)
        with patch.object(CloudSyncManager, "fetch_tuya_session", return_value=json.dumps(newer)), \
                patch.object(CloudSyncManager, "push_tuya_session") as push, \
                patch.object(tuya_devices, "build_manager"):
            self.manager._init_cloud_manager(force_sync=True)
        self.assertEqual(json.loads(self.manager.session_path.read_text()), newer)
        push.assert_not_called()

    def test_invalid_remote_session_does_not_destroy_local_credentials(self):
        with patch.object(CloudSyncManager, "fetch_tuya_session", return_value='{"token_info":"broken"}'), \
                patch.object(tuya_devices, "build_manager") as build:
            self.manager._init_cloud_manager(force_sync=True)
        self.assertEqual(build.call_args.args[0], session())

    def test_expiring_sdk_session_checks_shared_login_before_scene(self):
        self.manager._manager.customer_api.token_info.expire_time = (time.time()-1)*1000
        with patch.object(self.manager, "_init_cloud_manager") as init, patch("random.uniform", return_value=0):
            self.assertTrue(self.manager.open_door("a")[0])
        init.assert_called_once_with(force_sync=True)

    def test_timeout_never_automatically_repeats_a_physical_command(self):
        self.manager._manager.trigger_scene.side_effect = TimeoutError("fixture")
        with patch.object(self.manager, "_init_cloud_manager") as init:
            self.assertFalse(self.manager.open_door("a")[0])
        self.manager._manager.trigger_scene.assert_called_once()
        init.assert_not_called()

    def test_authentication_failure_can_recover_once_before_opening(self):
        self.manager._manager.trigger_scene.side_effect = [Exception("sign invalid"), None]
        with patch.object(self.manager, "_init_cloud_manager") as init, patch("random.uniform", return_value=0):
            self.assertTrue(self.manager.open_door("a")[0])
        init.assert_called_once_with(force_sync=True)
        self.assertEqual(self.manager._manager.trigger_scene.call_count, 2)

    def test_simultaneous_click_and_hotkey_do_not_queue_another_opening(self):
        self.manager._door_trigger_lock.acquire()
        try:
            self.assertFalse(self.manager.open_door("a")[0])
        finally:
            self.manager._door_trigger_lock.release()
        self.manager._manager.trigger_scene.assert_not_called()

    def test_qr_confirmation_uses_existing_poll_api_and_saves_session(self):
        self.manager._polling_qr_thread = None
        with patch.object(tuya_devices, "poll_login", return_value=session()) as poll, \
                patch.object(tuya_devices, "build_manager", return_value=self.sdk()), \
                patch.object(CloudSyncManager, "push_tuya_session", return_value=True) as push, \
                patch("tuya_access_manager.threading.Thread") as thread:
            self.manager._start_qr_polling("fixture-qr", "fixture-user")
            thread.call_args.kwargs["target"]()
        poll.assert_called_once_with("fixture-qr", "fixture-user")
        push.assert_called_once()
        self.assertTrue(self.manager._cloud_connected)


if __name__ == "__main__":
    unittest.main()
