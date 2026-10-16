"""Click-triggered wallpaper cache. No polling, discovery sweep or remote agent."""
from copy import deepcopy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time

from PIL import Image, UnidentifiedImageError

from atomic_storage import write_json_atomic
from logger import log
from wallpaper_transport import WallpaperError, normalize_host, read_wallpaper

REFRESH_SECONDS = 24 * 60 * 60
RETRY_SECONDS = 10 * 60
AUTH_RETRY_SECONDS = 24 * 60 * 60


def identity(server):
    target = (normalize_host(server.get('host')), int(server.get('port', 3389)), str(server.get('username', '')).casefold())
    return hashlib.sha256(json.dumps(target).encode()).hexdigest()[:24]


def safe_id(value):
    value = str(value)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise WallpaperError('invalid_target')
    return value


def thumbnail(image):
    if len(image) > 524288:
        raise WallpaperError('invalid_image')
    try:
        with Image.open(io.BytesIO(image)) as source:
            if source.format not in ('JPEG', 'PNG') or source.width * source.height > 40000000:
                raise WallpaperError('invalid_image')
            source.load()
            source.thumbnail((640, 360), Image.Resampling.LANCZOS)
            result = io.BytesIO()
            source.convert('RGB').save(result, 'PNG', optimize=True)
            return result.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise WallpaperError('invalid_image') from None


class WallpaperPreviews:
    def __init__(self, directory, state_file, *, enabled=False, current_server=None,
                 on_ready=None, fetch=read_wallpaper, clock=time.time):
        self.directory, self.state_file = Path(directory), Path(state_file)
        self.enabled, self.current_server, self.on_ready = enabled, current_server, on_ready
        self.fetch, self.clock = fetch, clock
        self._lock = threading.RLock()
        self._slots = threading.BoundedSemaphore(2)
        self._pending = set()
        self._stop = threading.Event()
        self._state = {}
        try:
            data = json.loads(self.state_file.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                self._state = {key:value for key,value in data.items() if isinstance(value, dict)}
        except (OSError, ValueError):
            pass  # Disposable cache metadata; source images/configuration stay intact.

    def image_url(self, server):
        try:
            key, target = safe_id(server['id']), identity(server)
            with self._lock:
                entry = self._state.get(key, {})
                if entry.get('image_identity'):
                    if entry['image_identity'] != target:
                        return None
                    filename = entry.get('image_file', '')
                    if filename != f'{key}-wallpaper-{target}.png':
                        return None
                else:
                    filename = f'{key}.png'  # Retain existing screenshots until a wallpaper succeeds.
                file = self.directory / filename
                return f'/thumbnails/{filename}?v={file.stat().st_mtime_ns}' if file.is_file() else None
        except (OSError, ValueError, KeyError, WallpaperError):
            return None

    def _enabled(self):
        return bool(self.enabled() if callable(self.enabled) else self.enabled)

    def request(self, server):
        """Called only after the user launches this server's RDP connection."""
        try:
            if not self._enabled() or self._stop.is_set():
                return False
            key, target, now = safe_id(server['id']), identity(server), self.clock()
            with self._lock:
                if key in self._pending:
                    return False
                entry = self._state.get(key, {})
                updated = entry.get('updated_at', 0)
                attempted = entry.get('attempted_at', 0)
                if not isinstance(updated, (float, int)) or not math.isfinite(updated):
                    updated = 0
                if not isinstance(attempted, (float, int)) or not math.isfinite(attempted):
                    attempted = 0
                if entry.get('image_identity') == target and self.image_url(server) and 0 <= now - updated < REFRESH_SECONDS:
                    return False
                cooldown = AUTH_RETRY_SECONDS if entry.get('result') == 'authentication' else RETRY_SECONDS
                if entry.get('result') != 'ok' and entry.get('attempt_identity') == target and 0 <= now - attempted < cooldown:
                    return False
                if not self._slots.acquire(blocking=False):
                    return False
                self._pending.add(key)
                thread = threading.Thread(target=self._collect, args=(deepcopy(server), key, target),
                                          name='WallpaperPreview', daemon=True)
                try:
                    thread.start()
                except Exception:
                    self._pending.remove(key)
                    self._slots.release()
                    raise
            return True
        except Exception as error:
            log.warning(f'[Wallpaper] Coleta não agendada ({type(error).__name__}).')
            return False

    def _is_current(self, server, target):
        if self._stop.is_set() or not self._enabled():
            return False
        current = self.current_server(server['id']) if self.current_server else server
        return bool(current) and identity(current) == target

    def _collect(self, server, key, target):
        temporary = None
        try:
            if not self._is_current(server, target):
                return
            image = thumbnail(self.fetch(server))
            if not self._is_current(server, target):
                return
            self.directory.mkdir(parents=True, exist_ok=True)
            filename = f'{key}-wallpaper-{target}.png'
            with tempfile.NamedTemporaryFile(dir=self.directory, prefix='.wallpaper-', suffix='.tmp', delete=False) as output:
                temporary = Path(output.name)
                output.write(image)
                output.flush()
                os.fsync(output.fileno())
            with self._lock:
                if not self._is_current(server, target):
                    return
                os.replace(temporary, self.directory / filename)
                now = self.clock()
                updated = deepcopy(self._state)
                updated[key] = {'image_identity':target, 'image_file':filename, 'updated_at':now,
                                'attempt_identity':target, 'attempted_at':now, 'result':'ok'}
                write_json_atomic(self.state_file, updated)
                self._state = updated
            log.info(f'[Wallpaper] Miniatura atualizada: {key}.')
            if self.on_ready:
                try:
                    self.on_ready(key)
                except Exception:
                    log.warning('[Wallpaper] Não foi possível notificar a interface.')
        except Exception as error:
            code = error.code if isinstance(error, WallpaperError) else 'unavailable'
            with self._lock:
                updated = deepcopy(self._state)
                updated.setdefault(key, {}).update(attempt_identity=target, attempted_at=self.clock(), result=code)
                try:
                    write_json_atomic(self.state_file, updated)
                    self._state = updated
                except OSError:
                    pass  # Keep the previous successful image; cache must not break RDP.
            log.info(f'[Wallpaper] Miniatura anterior preservada: {key} ({code}).')
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            with self._lock:
                self._pending.discard(key)
            self._slots.release()

    def stop(self):
        self._stop.set()
