"""Snapshots Hikvision via ISAPI. Credentials and frame cache stay in the backend."""
import hashlib
import io
import json
import threading
import time

import requests
from PIL import Image, UnidentifiedImageError
from requests.auth import HTTPDigestAuth


class CameraError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


class CameraSnapshots:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._guard = threading.Lock()
        self._locks = {}
        self._cache = {}
        self._paths = {}

    def get(self, connection, channel=1):
        protocol = str(connection.get('protocol', 'http')).lower()
        host = str(connection.get('host', '')).strip()
        if protocol not in ('http', 'https') or not host or any(char in host for char in '/@?#\\'):
            raise CameraError('Confira o endereço da câmera nas configurações.', 422)
        try:
            port = int(connection.get('port', 443 if protocol == 'https' else 80))
            channel = int(channel)
            if not 1 <= port <= 65535 or not 1 <= channel <= 9999:
                raise ValueError()
        except (ValueError, TypeError):
            raise CameraError('Porta ou canal de câmera inválido.', 422)
        if not connection.get('username') or not connection.get('password'):
            raise CameraError('Informe o usuário e a senha da câmera nas configurações.', 422)
        key = hashlib.sha256(json.dumps([protocol, host, port, channel, connection['username'], connection['password']]).encode()).digest()
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            cached = self._cache.get(key)
            if cached and self._clock() < cached[0]:
                if isinstance(cached[1], CameraError):
                    raise cached[1]
                return cached[1]
            try:
                frame = self._fetch(protocol, host, port, connection, channel, key)
                self._cache[key] = (self._clock() + 1.5, frame)
                return frame
            except CameraError as error:
                self._cache[key] = (self._clock() + 6, error)
                raise

    def _fetch(self, protocol, host, port, connection, channel, key):
        ids = [channel * 100 + 1, channel] if channel < 100 else [channel]
        candidates = [self._paths[key]] if key in self._paths else list(dict.fromkeys(ids))
        # Device URLs are built from configuration, never accepted from a browser request.
        address = f'{protocol}://{host}:{port}'
        auth = HTTPDigestAuth(connection['username'], connection['password'])
        with requests.Session() as session:
            session.trust_env = False
            for camera_id in candidates:
                try:
                    with session.get(f'{address}/ISAPI/Streaming/channels/{camera_id}/picture',
                                     auth=auth, timeout=(3, 4), allow_redirects=False, stream=True) as response:
                        if response.status_code in (401, 403):
                            raise CameraError('A câmera recusou o acesso. Confira usuário, senha e permissão de imagem.')
                        if response.status_code in (400, 404, 405, 501):
                            self._paths.pop(key, None)
                            continue
                        if response.status_code != 200:
                            raise CameraError('A câmera está indisponível neste momento.')
                        chunks, size = [], 0
                        for chunk in response.iter_content(65536):
                            size += len(chunk)
                            if size > 4 * 1024 * 1024:
                                raise CameraError('A imagem recebida excedeu o tamanho permitido.')
                            chunks.append(chunk)
                        frame = b''.join(chunks)
                        try:
                            with Image.open(io.BytesIO(frame)) as image:
                                if image.format != 'JPEG' or image.width * image.height > 12000000:
                                    raise CameraError('A câmera não retornou uma imagem JPEG válida.')
                                image.verify()
                        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                            raise CameraError('A câmera não retornou uma imagem JPEG válida.')
                        self._paths[key] = camera_id
                        return frame
                except requests.Timeout:
                    raise CameraError('A câmera demorou para responder. Tentando novamente…')
                except requests.RequestException:
                    raise CameraError('Não foi possível conectar à câmera. Confira a rede e o endereço.')
        raise CameraError('Este canal não disponibilizou imagem. Confira o canal e a configuração ISAPI.')
