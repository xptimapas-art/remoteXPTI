"""Hikvision secondary RTSP H.264 -> fragmented MP4 in memory, without re-encoding."""
import queue
import re
import threading
import time
from urllib.parse import quote

import av

from camera_snapshots import CameraError

# Never emit FFmpeg diagnostics containing an authenticated RTSP URL.
av.logging.set_level(None)
_STREAM_SLOTS = threading.BoundedSemaphore(8)


def secondary_rtsp_url(connection, channel=1, rtsp_port=554):
    host = str(connection.get('host', '')).strip()
    if not host or any(char in host for char in '/@?#\\') or any(ord(char) <= 32 for char in host):
        raise CameraError('Confira o endereço da câmera nas configurações.', 422)
    if not connection.get('username') or not connection.get('password'):
        raise CameraError('Informe o usuário e a senha da câmera.', 422)
    try:
        port, channel = int(rtsp_port), int(channel)
        if not 1 <= port <= 65535 or not 1 <= channel <= 9999:
            raise ValueError()
    except (ValueError, TypeError):
        raise CameraError('Porta RTSP ou canal inválido.', 422)
    stream_id = channel * 100 + 2 if channel < 100 else channel // 100 * 100 + 2
    if ':' in host and not host.startswith('['):
        host = f'[{host}]'
    user, password = quote(str(connection['username']), safe=''), quote(str(connection['password']), safe='')
    return f'rtsp://{user}:{password}@{host}:{port}/Streaming/Channels/{stream_id}'


def h264_mime(extradata):
    if extradata and len(extradata) >= 4 and extradata[0] == 1:
        codec = extradata[1:4]
    else:
        sps = next((part for part in re.split(b'\x00\x00(?:\x00)?\x01', extradata or b'')
                    if len(part) >= 4 and part[0] & 31 == 7), None)
        if sps is None:
            raise CameraError('O stream não informou um perfil H.264 compatível.')
        codec = sps[1:4]
    return f'video/mp4; codecs="avc1.{codec.hex()}"'


class CameraStream:
    def __init__(self, connection, channel=1, rtsp_port=554):
        self._url = secondary_rtsp_url(connection, channel, rtsp_port)
        self._queue = queue.Queue(maxsize=64)
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name='SecondaryCameraStream', daemon=True)
        self.mime = ''
        self.error = None
        self.packet_count = 0
        self._last_consumed = time.monotonic()

    def start(self, timeout=14):
        if not _STREAM_SLOTS.acquire(blocking=False):
            raise CameraError('Há muitas visualizações abertas. Feche algumas câmeras e tente novamente.', 429)
        try:
            self._thread.start()
        except Exception:
            _STREAM_SLOTS.release()
            raise CameraError('Não foi possível iniciar a visualização da câmera.')
        if not self._ready.wait(timeout) or self.error:
            self.stop()
            raise self.error or CameraError('A câmera demorou para iniciar o stream secundário.')
        return self

    def stop(self):
        # Only the worker closes the AV container. Cross-thread closing can crash native decoders.
        self._stop.set()

    def read(self, timeout=0.5):
        try:
            chunk = self._queue.get(timeout=timeout)
            self._last_consumed = time.monotonic()
            return chunk
        except queue.Empty:
            if self._stop.is_set() or self.error or not self._thread.is_alive():
                return b''
            return None

    def write(self, data):
        # AV's output file interface: bounded RAM/backpressure, no recordings on disk.
        if len(data) > 2 * 1024 * 1024:
            raise CameraError('O stream excedeu o tamanho permitido.')
        while not self._stop.is_set():
            if time.monotonic() - self._last_consumed > 18:
                self.stop()
                break
            try:
                self._queue.put(bytes(data), timeout=0.2)
                self._ready.set()
                return len(data)
            except queue.Full:
                continue
        raise OSError('Stream encerrado.')

    def writable(self):
        return True

    def seekable(self):
        return False

    def _run(self):
        try:
            with av.open(self._url, format='rtsp', options={'rtsp_transport': 'tcp', 'allowed_media_types': 'video',
                         'analyzeduration': '1000000', 'probesize': '131072'}, timeout=(10, 5)) as source:
                if not source.streams.video:
                    raise CameraError('Nenhum vídeo encontrado no stream secundário.')
                video = source.streams.video[0]
                if video.codec_context.name != 'h264':
                    raise CameraError('Selecione H.264 no stream secundário da câmera para esta visualização.')
                self.mime = h264_mime(video.codec_context.extradata)
                with av.open(self, mode='w', format='mp4', buffer_size=4096,
                             options={'movflags': 'empty_moov+default_base_moof+frag_keyframe+skip_trailer',
                                      'frag_duration': '200000', 'flush_packets': '1'}) as output:
                    target = output.add_stream_from_template(video)
                    base_dts = None
                    for packet in source.demux(video):
                        if self._stop.is_set() or time.monotonic() - self._last_consumed > 18:
                            break
                        if packet.dts is None or packet.pts is None:
                            continue
                        if base_dts is None:
                            if not packet.is_keyframe:
                                continue
                            base_dts = packet.dts
                        packet.dts -= base_dts
                        packet.pts -= base_dts
                        packet.stream = target
                        output.mux(packet)
                        self.packet_count += 1
        except CameraError as error:
            self.error = error
        except Exception:
            if not self._stop.is_set():
                self.error = CameraError('Não foi possível receber o stream secundário. Confira a rede, as credenciais e a porta RTSP.')
        finally:
            self._stop.set()
            self._ready.set()
            self._url = ''
            _STREAM_SLOTS.release()
