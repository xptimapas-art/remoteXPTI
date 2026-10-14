import importlib.util
from pathlib import Path
import sys
import types
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


if __name__ == "__main__":
    unittest.main()
