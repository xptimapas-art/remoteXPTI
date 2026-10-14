"""Valida os arquivos gerados sem executar o app ou o instalador."""
import hashlib
import json
import sys
import types
import zipfile
import subprocess
import tempfile
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader


def verify_release(directory):
    app, setup = directory / 'RemoteXPTI.exe', directory / 'Setup_RemoteXPTI.exe'
    manifest = json.loads((directory / 'update-manifest.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256(app.read_bytes()).hexdigest()
    if digest != manifest['sha256'] or app.stat().st_size != manifest['size']:
        raise RuntimeError('O manifesto não corresponde ao EXE final.')
    forbidden = {'.secret.key', 'session.json', 'doors_config.json', 'tuya_vault.bin', 'camera-test-targets.json'}
    for binary in (app, setup):
        archive = CArchiveReader(str(binary))
        names = {name.replace('\\', '/') for name in archive.toc}
        if any(name.split('/')[-1] in forbidden for name in names):
            raise RuntimeError(f'{binary.name} contém arquivos locais de credenciais.')
        pyz = archive.open_embedded_archive('PYZ.pyz')
        if binary == app:
            required = {'desktop_backend', 'update_engine', 'update_bootstrap', 'local_api_security',
                        'tuya_devices', 'runtime_paths', 'windows_single_instance', 'connection_health', 'camera_snapshots', 'camera_streams', 'av', 'hotkey_capture', 'video_runtime_check'}
            if not required.issubset(pyz.toc) or 'update_helper.ps1' not in names or 'desktop_ui/dist/index.html' not in names:
                raise RuntimeError('Recursos do app/updater ausentes no pacote.')
            functions = {c.co_name for c in pyz.extract('update_engine').co_consts if isinstance(c, types.CodeType)}
            if 'launch_independent_process' not in functions:
                raise RuntimeError('EXE gerado não contém a versão final do updater.')
            if manifest['version'] not in pyz.extract('version').co_consts:
                raise RuntimeError('A versão embutida não corresponde ao manifesto.')
            session_helpers = {c.co_name for c in pyz.extract('tuya_devices').co_consts if isinstance(c, types.CodeType)}
            if not {'session_expires_at', 'session_timestamp', 'valid_session'}.issubset(session_helpers):
                raise RuntimeError('EXE gerado não contém a correção da sessão Tuya compartilhada.')
            if not any(name.startswith('av.libs/') and name.lower().endswith('.dll') for name in names):
                raise RuntimeError('Bibliotecas nativas de vídeo não foram incluídas no EXE.')
            # Exercise the actual packaged filter, without networking or client profiles.
            health = types.ModuleType('release_connection_health')
            sys.modules[health.__name__] = health
            try:
                exec(pyz.extract('connection_health'), health.__dict__)
                clock = [0.0]
                monitor = health.ConnectionHealthMonitor(clock=lambda: clock[0], wall_clock=lambda: 1000 + clock[0])
                for timestamp, reachable, online in ((0, False, True), (30, False, True),
                                                       (60, False, False), (90, True, False),
                                                       (120, True, True)):
                    clock[0] = timestamp
                    status, _ = monitor.observe('fixture', reachable, 'probe')
                    if status['is_online'] != online:
                        raise RuntimeError('Filtro de falsos alertas incorreto no EXE final.')
            finally:
                sys.modules.pop(health.__name__, None)
            frontend = directory.parent / 'desktop_ui' / 'dist'
            for path in frontend.rglob('*'):
                if not path.is_file():
                    continue
                name = 'desktop_ui/dist/' + path.relative_to(frontend).as_posix()
                original = next((key for key in archive.toc if key.replace('\\', '/') == name), None)
                if original is None or archive.extract(original) != path.read_bytes():
                    raise RuntimeError('A interface empacotada não corresponde ao build final: ' + name)
        else:
            if not {'tkinter', 'customtkinter', 'install_safety'}.issubset(pyz.toc) or '_tcl_data/init.tcl' not in names or '_tk_data/tk.tcl' not in names:
                raise RuntimeError('Instalador incompleto: Tcl/Tk não foi incluído.')
            if json.loads(archive.extract('servers.json'))['servers']:
                raise RuntimeError('Instalador contém lista de servidores de produção.')
            if hashlib.sha256(archive.extract('app_payload.bin')).hexdigest() != digest:
                raise RuntimeError('O instalador contém outro EXE.')
    with zipfile.ZipFile(directory / 'RemoteXPTI_Portatil.zip') as package:
        if forbidden.intersection(package.namelist()) or json.loads(package.read('servers.json'))['servers']:
            raise RuntimeError('ZIP portátil contém dados locais de produção.')
        if hashlib.sha256(package.read('RemoteXPTI.exe')).hexdigest() != digest:
            raise RuntimeError('O ZIP contém outro EXE.')
    # Run an offline branch before any GUI, profile, cloud or device initialization.
    with tempfile.TemporaryDirectory(prefix='remotexpti-video-check-') as temp:
        result_path = Path(temp) / 'video-runtime.json'
        completed = subprocess.run([str(app), '--verify-video-runtime', str(result_path)], timeout=40)
        result = json.loads(result_path.read_text('utf-8')) if result_path.exists() else {}
        if completed.returncode != 0 or not result.get('success') or result.get('version') != manifest['version'] \
                or result.get('h264_decoder') != 'h264' or not result.get('rtsp_input') or not result.get('mp4_output'):
            raise RuntimeError('O EXE final não carregou o decoder H.264 e os formatos RTSP/MP4 empacotados.')
        print('Vídeo no EXE: bibliotecas nativas, H.264, RTSP e MP4 carregados sem acessar dispositivos.')
    print(f'Release {manifest["version"]}: manifesto, EXEs, Tcl/Tk e pacote portátil verificados.')


if __name__ == '__main__':
    verify_release(Path(sys.argv[1] if len(sys.argv) > 1 else 'dist').resolve())
