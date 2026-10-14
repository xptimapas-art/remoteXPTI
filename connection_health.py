"""Confirm RDP outages and recovery without treating a single probe as an incident."""
import math
import threading
import time
from dataclasses import dataclass
from typing import Optional

PROBE_TIMEOUT_SECONDS = 3.0


@dataclass
class _State:
    online: bool = True
    offline_since: Optional[float] = None
    target: Optional[tuple] = None
    failures: int = 0
    successes: int = 0
    failure_started: Optional[float] = None
    failure_wall_time: Optional[float] = None
    last_counted: Optional[float] = None


class ConnectionHealthMonitor:
    def __init__(self, failure_count=3, failure_seconds=60.0, recovery_count=2,
                 sample_seconds=10.0, clock=time.monotonic, wall_clock=time.time):
        self.failure_count = failure_count
        self.failure_seconds = failure_seconds
        self.recovery_count = recovery_count
        self.sample_seconds = sample_seconds
        self._clock, self._wall_clock = clock, wall_clock
        self._states = {}
        self._lock = threading.RLock()

    def restore(self, history):
        """Restore only confirmed outages, preserving their original start time."""
        with self._lock:
            for server_id, timestamp in history.items():
                try:
                    timestamp = float(timestamp)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(timestamp) and timestamp > 0:
                    self._states[str(server_id)] = _State(online=False, offline_since=timestamp)

    def forget(self, server_id):
        with self._lock:
            self._states.pop(server_id, None)

    def downtime(self):
        with self._lock:
            return {key: state.offline_since for key, state in self._states.items()
                    if state.offline_since is not None}

    def observe(self, server_id, reachable, message, target=None):
        """Return (stable status, outage changed). Rapid retries cannot add votes."""
        with self._lock:
            now, wall_now = self._clock(), self._wall_clock()
            state = self._states.setdefault(server_id, _State())
            old_outage = state.offline_since
            if state.target is not None and state.target != target:
                state = self._states[server_id] = _State()
            state.target = target

            if reachable:
                state.failures = 0
                state.failure_started = state.failure_wall_time = None
                if state.online:
                    state.successes = 0
                    state.last_counted = None
                else:
                    if state.successes == 0 or now - state.last_counted >= self.sample_seconds:
                        state.successes += 1
                        state.last_counted = now
                    if state.successes >= self.recovery_count:
                        state.online = True
                        state.offline_since = None
                        state.successes = 0
                        state.last_counted = None
            else:
                state.successes = 0
                if state.failures == 0:
                    state.failure_started, state.failure_wall_time = now, wall_now
                    state.failures = 1
                    state.last_counted = now
                elif now - state.last_counted >= self.sample_seconds:
                    state.failures += 1
                    state.last_counted = now
                if (state.online and state.failures >= self.failure_count
                        and now - state.failure_started >= self.failure_seconds):
                    state.online = False
                    state.offline_since = state.failure_wall_time

            phase = 'online' if state.online else 'offline'
            stable_message = message
            if state.online and not reachable:
                phase = 'suspect'
                stable_message = 'Falha pontual no teste RDP; aguardando confirmação.'
            elif not state.online and reachable:
                phase = 'recovering'
                stable_message = 'RDP respondeu; aguardando confirmação da recuperação.'
            status = {'is_online': state.online, 'msg': stable_message,
                      'health_state': phase, 'last_probe_online': bool(reachable),
                      'offline_since': state.offline_since,
                      'duration_seconds': max(0, int(wall_now - state.offline_since))
                      if state.offline_since is not None else 0}
            return status, old_outage != state.offline_since
