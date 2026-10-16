"""Bounded local scan history. No credentials, remote changes or extra probes."""
from collections import Counter
from copy import deepcopy
import ipaddress
import json
from pathlib import Path
import threading

from atomic_storage import write_json_atomic


def summarize_scan(servers, results, previous, *, started_at, elapsed):
    samples = []
    networks = Counter()
    offline, recovered = [], []
    confirmed_offline = 0
    for server, (status, _) in zip(servers, results):
        if 'last_probe_online' not in status:
            continue  # Deleted/edited targets were discarded during the scan.
        key = server['id']
        value = status['last_probe_online']
        result = 'inconclusive' if value is None else 'responded' if value else 'failed'
        sample = {'id':key, 'result':result}
        if value is not True:
            sample['message'] = str(status.get('msg', ''))[:240]
            try:
                address = ipaddress.ip_address(server.get('host', ''))
                network = str(ipaddress.ip_network(f'{address}/{16 if address.version == 4 else 48}', strict=False))
            except ValueError:
                network = 'hostname'
            networks[network] += 1
        samples.append(sample)
        if not status['is_online']:
            confirmed_offline += 1
            if previous.get(key, {}).get('is_online') is True:
                offline.append(key)
        elif previous.get(key, {}).get('is_online') is False:
            recovered.append(key)
    counts = Counter(item['result'] for item in samples)
    return {
        'started_at':started_at, 'duration_ms':round(elapsed * 1000),
        'total':len(samples), 'responded':counts['responded'], 'failed':counts['failed'],
        'inconclusive':counts['inconclusive'], 'confirmed_offline':confirmed_offline,
        'new_offline_ids':offline, 'recovered_ids':recovered,
        'mass_failure':counts['failed'] >= 5 and counts['failed'] * 2 >= len(samples),
        'affected_networks':dict(networks), 'samples':samples,
    }


class ConnectionScanHistory:
    def __init__(self, path, limit=120):
        self.path, self.limit = Path(path), limit
        self._lock = threading.RLock()
        self._scans = []
        try:
            if self.path.stat().st_size <= 4_000_000:
                stored = json.loads(self.path.read_text(encoding='utf-8'))
                if isinstance(stored, dict) and stored.get('format') == 1 and isinstance(stored.get('scans'), list):
                    self._scans = [row for row in stored['scans'] if isinstance(row, dict)][-limit:]
        except (OSError, ValueError):
            pass

    def append(self, summary):
        with self._lock:
            self._scans = (self._scans + [deepcopy(summary)])[-self.limit:]
            # Optional evidence: caller catches a disk error without changing health.
            write_json_atomic(self.path, {'format':1, 'scans':self._scans})

    def latest(self):
        with self._lock:
            return deepcopy(self._scans[-1]) if self._scans else None
