"""Offline diagnostic for the packaged video libraries; does not load application profiles."""
import json
from pathlib import Path


def check_video_runtime(output):
    path = Path(output).resolve()
    if path.name != 'video-runtime.json':
        raise ValueError('Nome de diagnóstico inválido.')
    try:
        import av
        from version import CURRENT_VERSION
        decoder = av.CodecContext.create('h264', 'r')
        decoder.open()
        result = {'success': True, 'version': CURRENT_VERSION, 'pyav': av.__version__,
                  'h264_decoder': decoder.name, 'rtsp_input': av.ContainerFormat('rtsp').is_input,
                  'mp4_output': av.ContainerFormat('mp4').is_output}
    except Exception as error:
        result = {'success': False, 'error_type': type(error).__name__}
    path.write_text(json.dumps(result), encoding='utf-8')
    return result['success']
