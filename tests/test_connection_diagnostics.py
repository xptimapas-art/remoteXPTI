import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from connection_diagnostics import ConnectionScanHistory, summarize_scan


class DiagnosticsTests(unittest.TestCase):
    def test_forty_nine_failures_are_correlated_but_not_suppressed(self):
        servers = [dict(id=str(index),host='10.189.1.10' if index < 48 else
                        '10.215.1.10' if index == 48 else '192.168.12.10',
                        username='secret-user',password='secret-password') for index in range(59)]
        previous = {row['id']:{'is_online':True} for row in servers}
        results = [({'is_online':index>=49,'last_probe_online':index>=49,'msg':'timeout'}, True)
                   for index in range(59)]
        summary = summarize_scan(servers, results, previous, started_at=1000, elapsed=3)
        self.assertTrue(summary['mass_failure'])
        self.assertEqual(summary['failed'],49)
        self.assertEqual(summary['confirmed_offline'],49)
        self.assertEqual(summary['responded'],10)
        self.assertEqual(len(summary['new_offline_ids']),49)
        self.assertEqual(summary['affected_networks'],{'10.189.0.0/16':48,'10.215.0.0/16':1})
        self.assertNotIn('secret',json.dumps(summary))

    def test_inconclusive_local_measurements_are_not_remote_failures(self):
        rows = [dict(id=str(index),host='fixture') for index in range(59)]
        results = [({'is_online':True,'last_probe_online':None,'msg':'local error'},False)] * 59
        summary = summarize_scan(rows,results,{},started_at=1000,elapsed=2)
        self.assertFalse(summary['mass_failure'])
        self.assertEqual(summary['inconclusive'],59)
        self.assertEqual(summary['failed'],0)
        self.assertEqual(summary['confirmed_offline'],0)

    def test_discarded_targets_do_not_appear_as_current_results(self):
        summary = summarize_scan([dict(id='a',host='fixture')],[({},False)],{},
                                 started_at=1000,elapsed=1)
        self.assertEqual(summary['total'],0)
        self.assertFalse(summary['mass_failure'])

    def test_bounded_history_survives_restart_and_returns_copies(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'scans.json'
            history = ConnectionScanHistory(path,limit=2)
            for index in range(4):
                history.append({'started_at':index})
            stored = json.loads(path.read_text())['scans']
            self.assertEqual(len(stored),2)
            self.assertEqual(ConnectionScanHistory(path,limit=2).latest(),{'started_at':3})
            history.latest()['started_at']=99
            self.assertEqual(history.latest()['started_at'],3)

    def test_failed_optional_write_keeps_last_saved_history(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'scans.json'
            history = ConnectionScanHistory(path)
            history.append({'started_at':1})
            with patch('connection_diagnostics.write_json_atomic',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    history.append({'started_at':2})
            self.assertEqual(ConnectionScanHistory(path).latest(),{'started_at':1})
            self.assertEqual(history.latest(),{'started_at':2})

    def test_corrupt_history_does_not_prevent_new_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'scans.json'
            path.write_text('{')
            history = ConnectionScanHistory(path)
            self.assertIsNone(history.latest())
            history.append({'started_at':1})
            self.assertEqual(history.latest(),{'started_at':1})


if __name__ == '__main__':
    unittest.main()
