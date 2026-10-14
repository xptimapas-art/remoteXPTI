import ast
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

from connection_health import ConnectionHealthMonitor, PROBE_TIMEOUT_SECONDS


class FakeClock:
    now = 0.0
    wall = 1000.0

    def advance(self, seconds):
        self.now += seconds
        self.wall += seconds


class ConnectionHealthTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.monitor = ConnectionHealthMonitor(clock=lambda: self.clock.now,
                                               wall_clock=lambda: self.clock.wall)

    def probe(self, online, target=('fixture', 3389)):
        return self.monitor.observe('a', online, 'probe', target=target)

    def test_single_loss_and_two_losses_never_create_incident(self):
        self.assertTrue(self.probe(False)[0]['is_online'])
        self.clock.advance(30)
        self.assertTrue(self.probe(False)[0]['is_online'])
        self.clock.advance(30)
        self.assertTrue(self.probe(True)[0]['is_online'])
        self.assertEqual(self.monitor.downtime(), {})

    def test_persistent_outage_is_confirmed_and_timed_from_first_failure(self):
        self.probe(False)
        self.clock.advance(30)
        self.probe(False)
        self.clock.advance(30)
        status, changed = self.probe(False)
        self.assertTrue(changed)
        self.assertFalse(status['is_online'])
        self.assertEqual(status['offline_since'], 1000)
        self.assertEqual(status['duration_seconds'], 60)

    def test_three_fast_failures_still_require_sixty_seconds(self):
        for _ in range(3):
            self.probe(False)
            self.clock.advance(10)
        self.assertEqual(self.monitor.downtime(), {})
        self.clock.advance(30)
        self.assertFalse(self.probe(False)[0]['is_online'])

    def test_rapid_manual_retries_do_not_add_confirmation_votes(self):
        for _ in range(20):
            self.probe(False)
        self.clock.advance(60)
        self.assertTrue(self.probe(False)[0]['is_online'])
        self.clock.advance(10)
        self.assertFalse(self.probe(False)[0]['is_online'])

    def test_any_success_resets_pending_failure_sequence(self):
        self.probe(False)
        self.clock.advance(30)
        self.probe(False)
        self.clock.advance(1)
        self.probe(True)
        self.clock.advance(29)
        self.assertTrue(self.probe(False)[0]['is_online'])
        self.clock.advance(30)
        self.assertTrue(self.probe(False)[0]['is_online'])
        self.assertEqual(self.monitor.downtime(), {})

    def test_single_success_does_not_clear_confirmed_outage(self):
        self.monitor.restore({'a': 200})
        self.assertEqual(self.probe(True)[0]['health_state'], 'recovering')
        self.clock.advance(30)
        status, changed = self.probe(False)
        self.assertFalse(changed)
        self.assertFalse(status['is_online'])
        self.assertEqual(status['offline_since'], 200)

    def test_recovery_requires_two_separated_successes(self):
        self.monitor.restore({'a': 200})
        self.probe(True)
        for _ in range(20):
            self.assertFalse(self.probe(True)[0]['is_online'])
        self.clock.advance(10)
        status, changed = self.probe(True)
        self.assertTrue(changed)
        self.assertTrue(status['is_online'])
        self.assertEqual(self.monitor.downtime(), {})

    def test_restart_preserves_old_outage_and_new_target_resets_history(self):
        self.monitor.restore({'a': 200})
        self.assertEqual(self.probe(False)[0]['offline_since'], 200)
        status, changed = self.probe(False, target=('replacement', 3389))
        self.assertTrue(changed)
        self.assertTrue(status['is_online'])
        self.assertIsNone(status['offline_since'])

    def test_wall_clock_change_does_not_confirm_outage_early(self):
        self.probe(False)
        self.clock.wall += 86400
        self.clock.advance(10)
        self.probe(False)
        self.clock.advance(10)
        self.assertTrue(self.probe(False)[0]['is_online'])

    def test_bad_history_entries_are_ignored_without_losing_valid_history(self):
        self.monitor.restore({'a': 200, 'b': 'bad', 'c': None, 'd': float('nan'), 'e': -1})
        self.assertEqual(self.monitor.downtime(), {'a': 200})
        self.monitor.forget('a')
        self.assertEqual(self.monitor.downtime(), {})


class BackendStatusIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Execute the real status handlers with fake storage/probes. No backend import,
        # live configuration, actual hosts, cloud, devices, or user files are touched.
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'desktop_backend.py').read_text('utf-8'))
        selected = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in {
                    '_check_server_status', 'check_all_servers_status', 'check_single_server'}:
                node.decorator_list = []
                selected.append(node)
        self.clock = FakeClock()
        self.server = {'id': 'a', 'host': 'fixture', 'port': 3389}
        self.probes = MagicMock(return_value=(False, 'timeout'))
        self.context = {
            'health_monitor': ConnectionHealthMonitor(clock=lambda: self.clock.now,
                                                      wall_clock=lambda: self.clock.wall),
            'status_lock': threading.RLock(), 'status_scan_lock': threading.Lock(),
            'server_probe_locks': {}, 'server_status_cache': {}, 'server_downtime': {},
            'threading': threading, 'ThreadPoolExecutor': ThreadPoolExecutor,
            'storage_mgr': types.SimpleNamespace(servers=[self.server],
                                                get_server=lambda key: self.server),
            'RDPManager': types.SimpleNamespace(check_connection=self.probes),
            'PROBE_TIMEOUT_SECONDS': PROBE_TIMEOUT_SECONDS,
            '_save_downtime_history': MagicMock(), 'broadcast_ws': MagicMock(),
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]), '<status-handlers>', 'exec'), self.context)

    def test_manual_and_background_checks_share_confirmation_and_recovery(self):
        check = self.context['check_single_server']
        scan = self.context['check_all_servers_status']
        self.assertTrue(check('a')['is_online'])
        self.clock.advance(30)
        scan()
        self.assertEqual(self.context['server_downtime'], {})
        self.clock.advance(30)
        self.assertFalse(check('a')['is_online'])
        self.assertEqual(self.context['server_downtime'], {'a': 1000})
        self.probes.return_value = (True, 'online')
        self.clock.advance(30)
        self.assertFalse(check('a')['is_online'])
        self.clock.advance(30)
        scan()
        self.assertEqual(self.context['server_downtime'], {})
        self.assertTrue(self.context['server_status_cache']['a']['is_online'])
        self.probes.assert_called_with('fixture', 3389, timeout=3.0)

    def test_overlapping_scan_is_skipped(self):
        self.context['status_scan_lock'].acquire()
        try:
            self.context['check_all_servers_status']()
        finally:
            self.context['status_scan_lock'].release()
        self.probes.assert_not_called()

    def test_result_for_server_edited_during_probe_is_discarded(self):
        def edited(*args, **kwargs):
            self.context['storage_mgr'].get_server = lambda key: {'id': 'a', 'host': 'new-host'}
            return False, 'timeout'
        self.probes.side_effect = edited
        self.context['_check_server_status'](self.server)
        self.assertEqual(self.context['server_status_cache'], {})
        self.assertEqual(self.context['server_downtime'], {})


if __name__ == '__main__':
    unittest.main()
