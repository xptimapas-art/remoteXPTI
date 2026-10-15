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

    def test_all_concurrent_refresh_callers_receive_the_same_outcome(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        results = []
        def fetch():
            entered.set()
            self.assertTrue(release.wait(2))
            return self.snapshot()
        def callback(ok):
            results.append(ok)
            if len(results) == 5:
                finished.set()
        with patch.object(self.manager, '_fetch_from_hub', side_effect=fetch):
            self.manager.fetch_telemetry_async(force=True, callback=callback)
            self.assertTrue(entered.wait(1))
            for _ in range(4):
                self.manager.fetch_telemetry_async(force=True, callback=callback)
            release.set()
            self.assertTrue(finished.wait(2))
        self.assertEqual(results, [True] * 5)

    def test_missing_invalid_and_future_collection_dates_are_never_fresh(self):
        for value in ('-', 'invalid', '', (datetime.now() + timedelta(hours=1)).strftime('%d/%m/%Y %H:%M:%S')):
            snapshot = self.snapshot()
            snapshot['coleta_formatted'] = value
            self.assertTrue(self.fetch(snapshot))
            self.assertTrue(self.manager.get_data()['stale'])

    def test_acknowledged_label_stays_visible_until_hub_snapshot_catches_up(self):
        snapshot = self.snapshot()
        self.assertTrue(self.fetch(snapshot))
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'{"ok":true}'
        with patch.object(ajin.urllib.request, 'urlopen', return_value=response):
            self.assertTrue(self.manager.update_label('Slot1-PON1', '1', 'Nome novo', 'Rua nova'))
        self.assertEqual(self.manager.get_data()['rows'][0]['name'], 'Nome novo')
        self.assertTrue(self.fetch(snapshot))
        self.assertEqual(self.manager.get_data()['rows'][0]['name'], 'Nome novo')
        confirmed = self.snapshot([{'port':'Slot1-PON1', 'id':'1', 'status':'Online', 'name':'Nome novo', 'desc':'Rua nova'}])
        self.assertTrue(self.fetch(confirmed))
        self.assertFalse(self.manager._pending_labels)
        self.assertTrue(self.fetch(self.snapshot()))
        self.assertNotIn('name', self.manager.get_data()['rows'][0])

    def test_failed_label_acknowledgement_keeps_original_data(self):
        self.assertTrue(self.fetch(self.snapshot()))
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'{"ok":false}'
        with patch.object(ajin.urllib.request, 'urlopen', return_value=response):
            self.assertFalse(self.manager.update_label('Slot1-PON1', '1', 'Novo', 'Rua'))
        self.assertFalse(self.manager._pending_labels)
        self.assertNotIn('name', self.manager.get_data()['rows'][0])

    def test_shared_notes_require_explicit_ack_and_survive_delayed_snapshots(self):
        self.assertTrue(self.fetch(self.snapshot()))
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'{"ok":true}'
        with patch.object(ajin.urllib.request, 'urlopen', return_value=response):
            self.assertFalse(self.manager.update_label('Slot1-PON1','1','Nome','Rua',notes='Observação'))
        response.read.return_value = b'{"ok":true,"notes_saved":true}'
        with patch.object(ajin.urllib.request, 'urlopen', return_value=response) as request:
            self.assertTrue(self.manager.update_label('Slot1-PON1','1','Nome','Rua',notes='Observação\nSegunda linha'))
            self.assertTrue(request.call_args.args[0].full_url.endswith('/api/point_label'))
            self.assertEqual(json.loads(request.call_args.args[0].data)['notes'],'Observação\nSegunda linha')
        self.assertEqual(self.manager.get_data()['rows'][0]['notes'],'Observação\nSegunda linha')
        self.assertTrue(self.fetch(self.snapshot()))
        self.assertEqual(self.manager.get_data()['rows'][0]['notes'],'Observação\nSegunda linha')

    def test_map_visibility_requires_ack_and_preserves_false_in_snapshot_overlay(self):
        self.assertTrue(self.fetch(self.snapshot()))
        response=MagicMock()
        response.__enter__.return_value=response
        response.status=200
        response.read.return_value=b'{"ok":true,"notes_saved":true}'
        with patch.object(ajin.urllib.request,'urlopen',return_value=response):
            self.assertFalse(self.manager.update_label('Slot1-PON1','1','Nome','Rua',map_enabled=False))
        response.read.return_value=b'{"ok":true,"map_saved":true}'
        with patch.object(ajin.urllib.request,'urlopen',return_value=response) as request:
            self.assertTrue(self.manager.update_label('Slot1-PON1','1','Nome','Rua',map_enabled=False))
            self.assertFalse(json.loads(request.call_args.args[0].data)['map_enabled'])
            self.assertNotIn('notes',json.loads(request.call_args.args[0].data))
        self.assertFalse(self.manager.get_data()['rows'][0]['map_enabled'])
        self.assertTrue(self.fetch(self.snapshot()))
        self.assertFalse(self.manager.get_data()['rows'][0]['map_enabled'])

    def test_shared_coordinate_acknowledgement_is_required_and_nulls_remove_old_locations(self):
        self.assertTrue(self.fetch(self.snapshot()))
        response=MagicMock()
        response.__enter__.return_value=response
        response.status=200
        response.read.return_value=b'{"ok":true}'
        with patch.object(ajin.urllib.request,'urlopen',return_value=response):
            self.assertFalse(self.manager.update_label('Slot1-PON1','1','Nome','Rua',latitude=0,longitude=0))
        response.read.return_value=b'{"ok":true,"coordinates_saved":true}'
        with patch.object(ajin.urllib.request,'urlopen',return_value=response):
            self.assertTrue(self.manager.update_label('Slot1-PON1','1','Nome','Rua',latitude=None,longitude=None))
        row=self.manager.get_data()['rows'][0]
        self.assertIsNone(row['latitude'])
        self.assertTrue(row['coordinates_shared'])
        self.assertTrue(self.fetch(self.snapshot()))
        self.assertIsNone(self.manager.get_data()['rows'][0]['latitude'])

    def test_scan_preserves_registered_and_new_devices_and_rejects_malformed_results(self):
        scan = {'devices':[{'port':'PON-1','id':'1','serial':'AA','is_registered':False}]}
        with patch.object(self.manager, '_hub_json', return_value=scan):
            self.assertEqual(self.manager.scan_onus(), scan)
        for invalid in ({}, {'devices':None}, {'devices':[{}]}, {'devices':[{'port':'PON-1','id':1,'is_registered':'false'}]}):
            with patch.object(self.manager, '_hub_json', return_value=invalid), self.assertRaises(ValueError):
                self.manager.scan_onus()

    def test_delete_requires_positive_ack_and_does_not_mutate_inventory_on_failure(self):
        self.assertTrue(self.fetch(self.snapshot()))
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'{"ok":false}'
        with patch.object(ajin.urllib.request, 'urlopen', return_value=response):
            self.assertFalse(self.manager.delete_onu('Slot1-PON1','1'))
        self.assertEqual(len(self.manager.get_data()['rows']),1)
        self.assertFalse(self.manager._pending_deletions)

    def test_acknowledged_delete_does_not_reappear_during_snapshot_delay(self):
        original = self.snapshot()
        self.assertTrue(self.fetch(original))
        with patch.object(self.manager, '_hub_json', return_value={'ok':True}), patch.object(self.manager, 'fetch_telemetry_async'):
            self.assertTrue(self.manager.delete_onu('Slot1-PON1','1'))
        self.assertEqual(self.manager.get_data()['rows'],[])
        self.assertEqual(self.manager.get_data()['total'],0)
        self.assertTrue(self.fetch(original))
        self.assertEqual(self.manager.get_data()['rows'],[])

    def test_registration_rechecks_identity_and_rejects_reassigned_or_registered_onus(self):
        device = {'port':'PON-1','id':'1','serial':'AA','name':'Novo','desc':''}
        for current in ([], [{**device,'serial':'BB','is_registered':False}], [{**device,'is_registered':True}]):
            with patch.object(self.manager, 'scan_onus', return_value={'devices':current}), patch.object(self.manager, '_hub_json') as mutate:
                with self.assertRaises(ValueError):
                    self.manager.register_onus([device])
                mutate.assert_not_called()
        with patch.object(self.manager, 'scan_onus', return_value={'devices':[{**device,'is_registered':False}]}), patch.object(self.manager, '_hub_json', return_value={'ok':True}) as mutate, patch.object(self.manager, 'fetch_telemetry_async'):
            self.assertTrue(self.manager.register_onus([device]))
            mutate.assert_called_once_with('/api/add_devices',[device])

    def test_pending_label_overlay_expires_and_never_changes_device_status(self):
        snapshot = self.snapshot()
        self.manager._pending_labels[('Slot1-PON1', '1')] = ({'name':'Nome salvo'}, 100)
        with patch.object(ajin.time, 'monotonic', return_value=90):
            merged = self.manager._merge_pending_labels(snapshot)
        self.assertEqual(merged['rows'][0]['name'], 'Nome salvo')
        self.assertEqual(merged['rows'][0]['status'], 'Online')
        with patch.object(ajin.time, 'monotonic', return_value=101):
            merged = self.manager._merge_pending_labels(snapshot)
        self.assertNotIn('name', merged['rows'][0])
        self.assertFalse(self.manager._pending_labels)


if __name__ == "__main__":
    unittest.main()
