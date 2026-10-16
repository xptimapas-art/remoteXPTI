import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import tempfile
import unittest
from unittest.mock import MagicMock, patch


class AjinHubCacheTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("ajin_hub_fixture", Path(__file__).resolve().parents[1] / "tools" / "run_ajin_hub.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"dashboard": types.SimpleNamespace()}):
            spec.loader.exec_module(self.module)
        self.initial = {"rows": [{"id": "1"}], "server": {"online": False}}
        self.reader = MagicMock(return_value=self.initial)
        self.app = types.SimpleNamespace(load_data=self.reader, server_ping_state={"online": True},
                                         server_ping_loop=MagicMock(), bench_ping_loop=MagicMock(),
                                         PORT=3000, Handler=MagicMock())

    def run_server(self, verify):
        server = MagicMock()
        server.__enter__.return_value.serve_forever.side_effect = verify
        with patch.object(self.module, "configure", return_value=self.app), \
                patch.object(self.module, "ThreadingHTTPServer", return_value=server), \
                patch.object(self.module.threading, "Thread") as thread, \
                patch.object(self.module.logging, "basicConfig"):
            self.threads = thread
            self.module.main()

    def test_inactive_points_persist_without_inflating_network_counts_or_events(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'inactive_points.json'
            points = [{'number':4, 'address':'Rua A x Rua B', 'latitude':-27.4, 'longitude':-48.5, 'map_enabled':False}]
            path.write_text(json.dumps(points), encoding='utf-8')
            data = {'rows':[{'name':'Ponto 01', 'status':'Online'}], 'total':1, 'online':1, 'offline':0, 'events':[]}
            overlay = self.module.InactivePoints(path).overlay(data)
            self.assertEqual(overlay['inactive_points'], points)
            for field in data:
                self.assertEqual(overlay[field], data[field])
            self.assertEqual(self.module.InactivePoints(path).overlay(data), overlay)
            self.assertTrue(overlay['features']['inactive_points'])

    def test_newly_registered_point_is_not_duplicated_in_inactive_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'inactive_points.json'
            path.write_text(json.dumps([{'number':4, 'address':'Rua A', 'latitude':0, 'longitude':0, 'map_enabled':False}]))
            store = self.module.InactivePoints(path)
            self.assertEqual(store.overlay({'rows':[{'name':'Ponto 004'}]})['inactive_points'], [])
            self.assertEqual(len(store.points), 1)

    def test_invalid_inactive_inventory_is_preserved_and_does_not_activate_points(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'inactive_points.json'
            valid = {'number':4, 'address':'Rua A', 'latitude':-27, 'longitude':-48, 'map_enabled':False}
            for values in ([valid, valid], [{**valid, 'map_enabled':True}], [{**valid, 'latitude':91}], [{**valid, 'longitude':None}], {'invalid':True}):
                source = json.dumps(values)
                path.write_text(source)
                with patch.object(self.module.logging, 'exception'):
                    store = self.module.InactivePoints(path)
                self.assertFalse(store.available)
                self.assertEqual(store.overlay({'rows':[]})['inactive_points'], [])
                self.assertEqual(path.read_text(), source)

    def test_many_client_requests_do_not_repeat_csv_history_processing(self):
        def verify():
            for _ in range(100):
                data = self.app.load_data()
                self.assertEqual(data["rows"], self.initial["rows"])
                self.assertTrue(data["server"]["online"])
            self.assertEqual(self.reader.call_count, 1)
            self.app.server_ping_state["online"] = False
            self.assertFalse(self.app.load_data()["server"]["online"])
        self.run_server(verify)

    def test_background_failure_preserves_the_last_successful_snapshot(self):
        self.reader.side_effect = [self.initial, ConnectionError("fixture")]
        def verify():
            refresh = self.threads.call_args_list[0].kwargs["target"]
            with patch.object(self.module.threading, "Event") as event, \
                    patch.object(self.module.logging, "exception") as logged:
                event.return_value.wait.side_effect = StopIteration
                with self.assertRaises(StopIteration):
                    refresh()
                self.assertTrue(logged.called)
            self.assertEqual(self.app.load_data()["rows"], self.initial["rows"])
        self.run_server(verify)

    def test_background_refresh_replaces_inventory_without_blocking_readers(self):
        newer = {"rows": [{"id": "1"}, {"id": "2"}]}
        self.reader.side_effect = [self.initial, newer]
        def verify():
            refresh = self.threads.call_args_list[0].kwargs["target"]
            with patch.object(self.module.threading, "Event") as event:
                event.return_value.wait.side_effect = StopIteration
                with self.assertRaises(StopIteration):
                    refresh()
            self.assertEqual(self.app.load_data()["rows"], newer["rows"])
        self.run_server(verify)

    def test_notes_persist_across_restart_are_shared_and_follow_the_device_serial(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'point_notes.json'
            store=self.module.PointNotes(path)
            data={'rows':[{'port':'PON-1','id':'1','serial':'AA:BB'}]}
            store.save('PON-1','1','AA-BB','Observação\nCom acentuação')
            self.assertEqual(store.overlay(data)['rows'][0]['notes'],'Observação\nCom acentuação')
            restarted=self.module.PointNotes(path)
            self.assertEqual(restarted.overlay(data)['rows'][0]['notes'],'Observação\nCom acentuação')
            replaced={'rows':[{'port':'PON-1','id':'1','serial':'CCDD'}]}
            self.assertEqual(restarted.overlay(replaced)['rows'][0]['notes'],'')
            restarted.save('PON-1','1','AABB','')
            self.assertEqual(self.module.PointNotes(path).overlay(data)['rows'][0]['notes'],'')

    def test_failed_notes_write_preserves_previous_file_and_in_memory_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'point_notes.json'
            store=self.module.PointNotes(path)
            store.save('PON-1','1','AABB','Anterior')
            original=path.read_bytes()
            with patch.object(Path,'replace',side_effect=OSError('fixture')), self.assertRaises(OSError):
                store.save('PON-1','1','AABB','Novo')
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(next(iter(store.values.values()))['text'],'Anterior')

    def test_corrupt_notes_are_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'point_notes.json'
            path.write_text('invalid json')
            with patch.object(self.module.logging,'exception'):
                store=self.module.PointNotes(path)
            self.assertFalse(store.available)
            with self.assertRaises(ValueError):
                store.save('PON-1','1','AABB','Novo')
            self.assertEqual(path.read_text(),'invalid json')

    def test_note_endpoint_acknowledges_persistence_and_leaves_legacy_labels_compatible(self):
        class Legacy:
            def do_POST(self):
                return 'legacy'
        with tempfile.TemporaryDirectory() as directory:
            store=self.module.PointNotes(Path(directory)/'notes.json')
            app=types.SimpleNamespace(save_label=MagicMock(),load_registered=lambda:{'PON-1|1':'AABB'})
            handler_type=self.module.notes_handler(Legacy,app,store,self.module.threading.RLock())
            handler=handler_type()
            handler.path='/label'
            self.assertEqual(handler.do_POST(),'legacy')
            def request(text):
                body=json.dumps({'port':'PON-1','id':'1','name':'Ponto','desc':'Rua','notes':text}).encode()
                handler.path='/api/point_label'; handler.headers={'Content-Length':str(len(body))}
                handler.rfile=io.BytesIO(body); handler._send=MagicMock()
                handler.do_POST()
                return json.loads(handler._send.call_args.args[0])
            self.assertEqual(request('Observação'),{'ok':True,'notes_saved':True,'map_saved':True,'coordinates_saved':True})
            app.save_label.assert_called_once_with('PON-1','1',name='Ponto',desc='Rua')
            self.assertEqual(next(iter(store.values.values()))['text'],'Observação')
            with patch.object(self.module.logging,'exception'):
                self.assertFalse(request('x'*4001)['ok'])

    def test_map_preference_persists_and_older_notes_clients_cannot_reset_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'notes.json'
            store=self.module.PointNotes(path)
            data={'rows':[{'port':'PON-1','id':'1','serial':'AABB'}]}
            self.assertTrue(store.overlay(data)['rows'][0]['map_enabled'])
            store.save('PON-1','1','AABB','Observação',False)
            self.assertFalse(self.module.PointNotes(path).overlay(data)['rows'][0]['map_enabled'])
            store.save('PON-1','1','AABB','Edição por versão anterior')
            row=store.overlay(data)['rows'][0]
            self.assertFalse(row['map_enabled'])
            self.assertEqual(row['notes'],'Edição por versão anterior')
            store.save('PON-1','1','AABB',None,True)
            row=self.module.PointNotes(path).overlay(data)['rows'][0]
            self.assertTrue(row['map_enabled'])
            self.assertEqual(row['notes'],'Edição por versão anterior')
            store.save('PON-1','1','AABB','',False)
            self.assertFalse(self.module.PointNotes(path).overlay(data)['rows'][0]['map_enabled'])
            self.assertTrue(store.overlay({'rows':[{'port':'PON-1','id':'1','serial':'CCDD'}]})['rows'][0]['map_enabled'])

    def test_shared_coordinates_persist_survive_legacy_edits_and_can_be_explicitly_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'notes.json'
            store=self.module.PointNotes(path)
            data={'rows':[{'port':'PON-1','id':'1','serial':'AA'}]}
            store.save('PON-1','1','AA','Observação',False,latitude=0,longitude=0)
            restarted=self.module.PointNotes(path)
            restarted.save('PON-1','1','AA','Novo texto')
            row=restarted.overlay(data)['rows'][0]
            self.assertEqual((row['latitude'],row['longitude']),(0,0))
            self.assertTrue(row['coordinates_shared'])
            self.assertFalse(row['map_enabled'])
            restarted.save('PON-1','1','AA',None,latitude=None,longitude=None)
            row=self.module.PointNotes(path).overlay(data)['rows'][0]
            self.assertIsNone(row['latitude'])
            self.assertTrue(row['coordinates_shared'])
            for lat,lon in [(91,0),(0,-181),(float('nan'),0),(True,0),(None,0)]:
                with self.assertRaises(ValueError):
                    restarted.save('PON-1','1','AA',None,latitude=lat,longitude=lon)
            self.assertNotIn('latitude',restarted.overlay({'rows':[{'port':'PON-1','id':'1','serial':'BB'}]})['rows'][0])


if __name__ == "__main__":
    unittest.main()
