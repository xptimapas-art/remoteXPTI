import json
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("logger", types.SimpleNamespace(log=MagicMock()))
import ajin_manager as ajin


class AjinTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        profile = patch.object(ajin, "get_profile_dir", return_value=Path(self.directory.name))
        profile.start()
        self.addCleanup(profile.stop)
        self.manager = object.__new__(ajin.AjinManager)
        self.manager._init()

    def snapshot(self, rows=None):
        return {"rows": rows if rows is not None else [{"port": "Slot1-PON1", "id": "1", "status": "Online"}],
                "coleta_formatted": datetime.now().strftime("%d/%m/%Y às %H:%M:%S")}

    def fetch(self, result=None, error=None):
        done = threading.Event()
        outcomes = []
        with patch.object(self.manager, "_fetch_from_hub", return_value=result, side_effect=error):
            self.manager.fetch_telemetry_async(force=True, callback=lambda ok: (outcomes.append(ok), done.set()))
            self.assertTrue(done.wait(2), "Telemetry worker did not finish")
        return outcomes[0]

    def test_failure_keeps_devices_and_notifies_ui_as_outdated_then_recovers(self):
        original = self.snapshot()
        self.assertTrue(self.fetch(original))
        updates = []
        self.manager.add_listener(lambda: updates.append(self.manager.get_data()))
        self.assertFalse(self.fetch(error=ConnectionRefusedError()))
        data = self.manager.get_data()
        self.assertEqual(data["rows"], original["rows"])
        self.assertEqual(data["collector"]["status"], "unavailable")
        self.assertTrue(data["stale"])
        self.assertTrue(updates[-1]["stale"])
        self.assertTrue(self.fetch(original))
        self.assertFalse(self.manager.get_data()["stale"])
        self.assertEqual(self.manager.get_data()["collector"]["status"], "online")

    def test_cache_on_start_is_never_presented_as_live(self):
        self.manager._cache_file.write_text(json.dumps(self.snapshot()), encoding="utf-8")
        self.manager._load_disk_cache()
        data = self.manager.get_data()
        self.assertEqual(len(data["rows"]), 1)
        self.assertTrue(data["stale"])

    def test_invalid_response_cannot_replace_saved_devices(self):
        snapshot = self.snapshot()
        self.assertTrue(self.fetch(snapshot))
        self.assertFalse(self.fetch({"error": "unavailable"}))
        self.assertEqual(self.manager.get_data()["rows"], snapshot["rows"])
        self.assertEqual(json.loads(self.manager._cache_file.read_text())["rows"], snapshot["rows"])

    def test_valid_empty_inventory_clears_old_devices(self):
        self.assertTrue(self.fetch(self.snapshot()))
        self.assertTrue(self.fetch(self.snapshot([])))
        self.assertEqual(self.manager.get_data()["rows"], [])
        self.assertFalse(self.manager.get_data()["stale"])

    def test_connected_hub_with_old_collection_remains_outdated(self):
        snapshot = self.snapshot()
        snapshot["coleta_formatted"] = (datetime.now() - timedelta(hours=1)).strftime("%d/%m/%Y às %H:%M:%S")
        self.assertTrue(self.fetch(snapshot))
        data = self.manager.get_data()
        self.assertTrue(data["stale"])
        self.assertEqual(data["collector"]["status"], "online")

    def test_concurrent_refreshes_share_one_worker(self):
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        def blocked_fetch():
            entered.set()
            release.wait(2)
            return self.snapshot()
        with patch.object(self.manager, "_fetch_from_hub", side_effect=blocked_fetch) as fetch:
            self.manager.fetch_telemetry_async(force=True, callback=lambda ok: done.set())
            self.assertTrue(entered.wait(1))
            for _ in range(20):
                self.manager.fetch_telemetry_async(force=True)
            release.set()
            self.assertTrue(done.wait(2))
            self.assertEqual(fetch.call_count, 1)

    def test_fallback_host_handles_subsequent_api_actions(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = json.dumps(self.snapshot()).encode()
        with patch.object(ajin.urllib.request, "urlopen", side_effect=[ConnectionRefusedError(), response]) as request:
            self.manager._fetch_from_hub()
        self.assertIn(ajin.DEFAULT_HUB_HOST, request.call_args_list[0].args[0].full_url)
        self.assertIn(ajin.FALLBACK_HUB_HOST, request.call_args_list[1].args[0].full_url)
        self.assertEqual(self.manager._hub_url("/label"), f"http://{ajin.FALLBACK_HUB_HOST}/label")


if __name__ == "__main__":
    unittest.main()
