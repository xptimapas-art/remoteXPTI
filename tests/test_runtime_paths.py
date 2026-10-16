import json
import os
import sys
import tempfile
import types
import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import runtime_paths as paths

# No user logs, profiles, or remote services are touched by these tests.
sys.modules.setdefault("logger", types.SimpleNamespace(log=MagicMock()))
from config_manager import ConfigManager, DEFAULT_SUPABASE_URL, DEFAULT_SUPABASE_KEY
from tuya_access_manager import TuyaAccessManager


class ProfileIsolationTests(unittest.TestCase):
    def test_fresh_frozen_install_writes_both_device_files_outside_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle, install, profile = root/"_MEI", root/"install", root/"profile"
            bundle.mkdir(); install.mkdir()
            with patch.object(paths,"__file__",str(bundle/"runtime_paths.py")), \
                    patch.object(sys,"executable",str(install/"RemoteXPTI.exe")), \
                    patch.object(sys,"frozen",True,create=True), \
                    patch("runtime_paths.get_profile_dir",return_value=profile):
                manager=object.__new__(TuyaAccessManager)
                config_path=manager._resolve_config_path()
                session_path=manager._resolve_session_path()
                self.assertEqual(config_path,profile/"doors_config.json")
                self.assertEqual(session_path,profile/"session.json")
                config_path.write_text(json.dumps({"doors":[{"id":"fixture"}]}))
                session_path.write_text(json.dumps({"token_info":{"access_token":"fixture"}}))
                shutil.rmtree(bundle)
                self.assertEqual(manager._resolve_config_path(),config_path)
                self.assertEqual(manager._resolve_session_path(),session_path)
                self.assertEqual(json.loads(config_path.read_text())["doors"][0]["id"],"fixture")
                self.assertTrue(json.loads(session_path.read_text())["token_info"])

    def test_legacy_files_migrate_once_and_existing_profile_always_wins(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            bundle,install,profile=root/"_MEI",root/"install",root/"profile"
            bundle.mkdir();install.mkdir()
            for name,value in [("doors_config.json",{"doors":[{"id":"installed"}]}),("session.json",{"token_info":{"access_token":"fixture"}})]:
                (install/name).write_text(json.dumps(value))
                (bundle/name).write_text(json.dumps({"doors":[{"id":"old-bundle"}]}))
            with patch.object(paths,"__file__",str(bundle/"runtime_paths.py")), \
                    patch.object(sys,"executable",str(install/"RemoteXPTI.exe")), \
                    patch.object(sys,"frozen",True,create=True), \
                    patch("runtime_paths.get_profile_dir",return_value=profile):
                for name in ("doors_config.json","session.json"):
                    target=paths.get_device_file(name)
                    self.assertEqual(json.loads(target.read_text()),json.loads((install/name).read_text()))
                    self.assertTrue((install/name).is_file())
                (profile/"doors_config.json").write_text(json.dumps({"doors":[]}))
                self.assertEqual(json.loads(paths.get_device_file("doors_config.json").read_text()),{"doors":[]})
                self.assertEqual(json.loads((install/"doors_config.json").read_text())["doors"][0]["id"],"installed")

    def test_invalid_legacy_config_is_skipped_and_failed_migration_never_removes_source(self):
        from atomic_storage import PersistenceError
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); install=root/"install";bundle=root/"_MEI";profile=root/"profile"
            install.mkdir();bundle.mkdir()
            source=bundle/"doors_config.json";source.write_text(json.dumps({"doors":[]}))
            (install/"doors_config.json").write_text("invalid")
            with patch.object(paths,"__file__",str(bundle/"runtime_paths.py")), \
                    patch.object(sys,"executable",str(install/"RemoteXPTI.exe")), \
                    patch.object(sys,"frozen",True,create=True), \
                    patch("runtime_paths.get_profile_dir",return_value=profile):
                with patch("atomic_storage.os.link",side_effect=PermissionError("fixture")):
                    with self.assertRaises(PersistenceError):
                        paths.get_device_file("doors_config.json")
                self.assertTrue(source.is_file())
                self.assertFalse((profile/"doors_config.json").exists())
                self.assertEqual(json.loads(paths.get_device_file("doors_config.json").read_text()),{"doors":[]})

    def test_development_never_uses_legacy_device_files_from_checkout(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict(os.environ, {"LOCALAPPDATA": temp}), \
                patch.object(sys, "frozen", False, create=True):
            manager = object.__new__(TuyaAccessManager)
            manager.config_path = manager._resolve_config_path()
            self.assertEqual(manager.config_path, paths.get_profile_dir() / "doors_config.json")
            self.assertEqual(manager._resolve_session_path(), paths.get_profile_dir() / "session.json")
            config = manager.load_config()
            self.assertFalse(config["enabled"])
            self.assertEqual(config["doors"], [])

    def test_client_and_development_never_share_paths_or_window_identity(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": str(Path("test-local"))}):
            with patch.object(sys, "frozen", False, create=True):
                dev = (paths.get_profile_dir(), paths.get_data_dir(), paths.get_window_title(),
                       paths.get_mutex_name(), paths.get_app_user_model_id())
                self.assertIn("RemoteXPTI-Dev", str(dev[0]))
                self.assertEqual(dev[0], dev[1])
            with patch.object(sys, "frozen", True, create=True):
                client = (paths.get_profile_dir(), paths.get_data_dir(), paths.get_window_title(),
                          paths.get_mutex_name(), paths.get_app_user_model_id())
                self.assertEqual(client[0], Path("test-local") / "RemoteXPTI")
                self.assertEqual(client[1], Path(sys.executable).resolve().parent)
                self.assertEqual(client[3], "RemoteXPTI_SingleInstance_Mutex")
            for dev_value, client_value in zip(dev, client):
                self.assertNotEqual(dev_value, client_value)

    def test_cloud_opt_out_survives_defaults_migration_and_config_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "config.json"
            target.write_text(json.dumps({"cloud_sync_enabled": False}), encoding="utf-8")
            manager = object.__new__(ConfigManager)
            manager.file_path = target
            manager.data = {"supabase_url": DEFAULT_SUPABASE_URL,
                            "supabase_key": DEFAULT_SUPABASE_KEY, "cloud_sync_enabled": True}
            manager.load()
            self.assertFalse(manager.get_supabase_config()["enabled"])
            self.assertFalse(json.loads(target.read_text())["cloud_sync_enabled"])

    def test_development_cloud_sync_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict(os.environ, {"LOCALAPPDATA": temp}), \
                patch.object(sys, "frozen", False, create=True):
            manager = object.__new__(ConfigManager)
            manager._init()
            self.assertFalse(manager.get_supabase_config()["enabled"])
            self.assertTrue(manager.get_supabase_config()["server_pull_enabled"])
            self.assertEqual(manager.file_path.parent, paths.get_profile_dir())

    def test_installed_client_keeps_cloud_sync_default(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.dict(os.environ, {"LOCALAPPDATA": temp}), \
                patch.object(sys, "frozen", True, create=True):
            manager = object.__new__(ConfigManager)
            manager._init()
            self.assertTrue(manager.get_supabase_config()["enabled"])


if __name__ == "__main__":
    unittest.main()
