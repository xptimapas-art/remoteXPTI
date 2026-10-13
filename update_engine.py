"""Download persistente e aplicação de updates fora do processo do app."""
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote
from packaging.version import InvalidVersion, Version
from version import APP_NAME, CURRENT_VERSION, GITHUB_REPO
from logger import log


def release_version(value):
    return Version(value.strip().removeprefix('v').removeprefix('V'))


def parse_version(value):
    return release_version(value).release


def is_public_version(value):
    try:
        v = release_version(value)
        return not (v.is_prerelease or v.is_devrelease)
    except InvalidVersion:
        return False


def is_beta_tester_version(value):
    try:
        return release_version(value).is_prerelease or release_version(value).is_devrelease
    except InvalidVersion:
        return False


def release_url(tag, asset):
    release_version(tag)
    return f'https://github.com/{GITHUB_REPO}/releases/download/{quote(tag, safe="")}/{asset}'


def validate_download_url(url, tag):
    if url != release_url(tag, f'{APP_NAME}.exe'):
        raise ValueError('O arquivo precisa pertencer à release oficial do RemoteXPTI.')


def read_json_url(url):
    req = urllib.request.Request(url, headers={'User-Agent': f'{APP_NAME}-Updater', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read(2 * 1024 * 1024).decode('utf-8-sig'))


def write_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def validate_manifest(data, tag):
    if release_version(str(data.get('version', ''))) != release_version(tag):
        raise ValueError('A versão do manifesto não corresponde à release.')
    if data.get('update_protocol') != 1 or data.get('asset') != f'{APP_NAME}.exe':
        raise ValueError('Release incompatível com instalação e recuperação automática.')
    size, digest = data.get('size'), data.get('sha256', '')
    if not isinstance(size, int) or isinstance(size, bool) or size < 1024:
        raise ValueError('Tamanho inválido no manifesto.')
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest.lower()):
        raise ValueError('SHA-256 inválido no manifesto.')
    return {**data, 'sha256': digest.lower()}


def validate_binary(path, size, digest):
    if path.stat().st_size != size:
        raise ValueError('Download incompleto: tamanho diferente do manifesto.')
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('O download não é um executável Windows.')
        stream.seek(0)
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
    if not secrets.compare_digest(hasher.hexdigest(), digest):
        raise ValueError('SHA-256 diferente do manifesto. Atualização rejeitada.')


def launch_independent_process(command, env, cwd):
    """O processo auxiliar não deve herdar o diretório de DLLs do onefile."""
    dll_dir = getattr(sys, '_MEIPASS', None) if sys.platform == 'win32' else None
    if dll_dir:
        import ctypes
        set_dll_dir = ctypes.windll.kernel32.SetDllDirectoryW
        set_dll_dir.argtypes = [ctypes.c_wchar_p]
        set_dll_dir(None)
    try:
        return subprocess.Popen(command, env=env, cwd=cwd,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    finally:
        if dll_dir:
            set_dll_dir(str(dll_dir))


class SilentAutoUpdater:
    def __init__(self, on_ready_callback=None, on_status_callback=None, cleanup_callback=None, staging_dir=None):
        self.on_ready_callback, self.on_status_callback = on_ready_callback, on_status_callback
        self.cleanup_callback = cleanup_callback
        self._lock = threading.RLock()
        self.is_checking = self.is_downloading = self.is_applying = self.update_ready = False
        self.new_version, self.downloaded_file, self._manifest = '', None, None
        self.enabled = bool(getattr(sys, 'frozen', False))
        self.state = 'idle' if self.enabled else 'disabled'
        self.status_message = 'Pronto' if self.enabled else 'Atualização automática disponível no aplicativo instalado. Execução pelo Python não instala versões.'
        identity = hashlib.sha256(str(Path(sys.executable).resolve()).casefold().encode()).hexdigest()[:16]
        local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
        self.staging_dir = staging_dir or local / APP_NAME / 'updates' / identity
        self.pending_path = self.staging_dir / 'pending.json'
        if self.enabled:
            self._restore_pending()

    def snapshot(self):
        with self._lock:
            return {'current_version': CURRENT_VERSION, 'new_version': self.new_version,
                    'is_checking': self.is_checking, 'is_downloading': self.is_downloading,
                    'is_applying': self.is_applying, 'update_ready': self.update_ready,
                    'enabled': self.enabled, 'state': self.state, 'status_message': self.status_message}

    def notify_status(self, message):
        self.status_message = message
        if self.on_status_callback:
            try:
                self.on_status_callback(message)
            except Exception:
                log.exception('[Updater] Falha ao publicar status')

    def _restore_pending(self):
        try:
            result_path = self.staging_dir / 'result.json'
            if result_path.exists():
                result = json.loads(result_path.read_text(encoding='utf-8-sig'))
                if result.get('status') == 'failed':
                    self.state = 'failed'
                    self.status_message = f"A atualização anterior falhou: {result.get('message', 'consulte os logs')}"
            if not self.pending_path.exists():
                return
            pending = json.loads(self.pending_path.read_text(encoding='utf-8'))
            manifest = validate_manifest(pending['manifest'], pending['tag'])
            if pending.get('target') != str(Path(sys.executable).resolve()):
                raise ValueError('Atualização pendente de outra instalação.')
            if release_version(pending['tag']) <= release_version(CURRENT_VERSION) and not pending.get('specific'):
                return
            file = self.staging_dir / 'pending.exe'
            validate_binary(file, manifest['size'], manifest['sha256'])
            self._manifest, self.downloaded_file = manifest, file
            self.new_version = pending['tag'].lstrip('vV')
            self.update_ready, self.state = True, 'ready'
            self.status_message = f'Versão {self.new_version} baixada e validada. Reinicie para instalar.'
        except Exception as exc:
            self.state = 'failed'
            self.status_message = f'Atualização pendente inválida: {exc}'
            log.warning('[Updater] %s', self.status_message)

    @staticmethod
    def fetch_all_releases():
        releases = []
        try:
            data = read_json_url(f'https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=100')
            for item in data:
                tag = item.get('tag_name', '')
                try:
                    release_version(tag)
                except InvalidVersion:
                    continue
                if item.get('draft'):
                    continue
                asset = next((a for a in item.get('assets', []) if a.get('name') == f'{APP_NAME}.exe'), None)
                public = not item.get('prerelease', False) and is_public_version(tag)
                releases.append({'tag': tag, 'name': item.get('name') or tag,
                                 'published': (item.get('published_at') or '')[:10],
                                 'is_public': public, 'is_prerelease': not public,
                                 'channel_label': 'Público' if public else 'Beta Tester',
                                 'download_url': asset.get('browser_download_url', '') if asset else ''})
            return sorted(releases, key=lambda r: release_version(r['tag']), reverse=True)
        except Exception as exc:
            log.warning('[Updater] API indisponível, consultando feed: %s', exc)
        # Atom não informa prerelease. /latest comprova qual release é pública.
        latest_tag = ''
        try:
            req = urllib.request.Request(f'https://github.com/{GITHUB_REPO}/releases/latest', headers={'User-Agent': APP_NAME})
            with urllib.request.urlopen(req, timeout=15) as response:
                prefix = f'https://github.com/{GITHUB_REPO}/releases/tag/'
                if response.geturl().startswith(prefix):
                    latest_tag = response.geturl()[len(prefix):]
        except Exception as exc:
            log.warning('[Updater] Não foi possível confirmar /latest: %s', exc)
        try:
            req = urllib.request.Request(f'https://github.com/{GITHUB_REPO}/releases.atom', headers={'User-Agent': APP_NAME})
            with urllib.request.urlopen(req, timeout=15) as response:
                root = ET.fromstring(response.read(2 * 1024 * 1024))
            ns = {'a': 'http://www.w3.org/2005/Atom'}
            for entry in root.findall('a:entry', ns):
                link = entry.find('a:link', ns)
                if link is None:
                    continue
                tag = link.get('href', '').split('/releases/tag/')[-1]
                try:
                    release_version(tag)
                except InvalidVersion:
                    continue
                public = tag == latest_tag and is_public_version(tag)
                releases.append({'tag': tag, 'name': entry.findtext('a:title', tag, ns),
                                 'published': entry.findtext('a:updated', '', ns)[:10],
                                 'is_public': public, 'is_prerelease': not public,
                                 'channel_label': 'Público' if public else 'Beta Tester',
                                 'download_url': release_url(tag, f'{APP_NAME}.exe')})
        except Exception as exc:
            log.warning('[Updater] Falha no feed: %s', exc)
        if latest_tag and is_public_version(latest_tag) and not any(r['tag'] == latest_tag for r in releases):
            releases.append({'tag': latest_tag, 'name': latest_tag, 'published': '', 'is_public': True,
                             'is_prerelease': False, 'channel_label': 'Público',
                             'download_url': release_url(latest_tag, f'{APP_NAME}.exe')})
        return sorted(releases, key=lambda r: release_version(r['tag']), reverse=True)

    def _get_latest_release_info(self):
        from config_manager import ConfigManager
        channel = ConfigManager().get_update_channel()
        for release in self.fetch_all_releases():
            if release['download_url'] and (channel == 'beta_tester' or release['is_public']):
                return release['tag'], release['download_url']
        return '', ''

    def start_background_check(self, is_manual=False):
        with self._lock:
            if not self.enabled or self.is_checking or self.is_downloading or self.is_applying or self.update_ready:
                if is_manual:
                    self.notify_status(self.status_message)
                return False
            self.is_checking, self.state = True, 'checking'
        threading.Thread(target=self._worker, daemon=True).start()
        return True

    def _worker(self, is_manual=False):
        self.notify_status('Verificando atualizações...')
        try:
            tag, url = self._get_latest_release_info()
            if not tag:
                raise ValueError('Nenhuma release disponível no canal selecionado.')
            if release_version(tag) <= release_version(CURRENT_VERSION):
                self.state = 'idle'
                self.status_message = f'Você está na versão mais recente ({CURRENT_VERSION}).'
                return
            self.new_version = tag.lstrip('vV')
            self._download_update_silent(url, tag)
        except Exception as exc:
            self.state, self.status_message = 'failed', f'Não foi possível atualizar: {exc}'
            log.exception('[Updater] Verificação falhou')
        finally:
            self.is_checking = False
            self.notify_status(self.status_message)

    def download_and_install_specific(self, tag_name, download_url='', on_status=None):
        if not self.enabled:
            raise ValueError(self.status_message)
        release_version(tag_name)
        if download_url:
            validate_download_url(download_url, tag_name)
        with self._lock:
            if self.is_checking or self.is_downloading or self.is_applying:
                raise ValueError('Outra operação de atualização está em andamento.')
            self.is_checking, self.update_ready, self.state = True, False, 'checking'
        def worker():
            try:
                self.new_version = tag_name.lstrip('vV')
                self._download_update_silent(release_url(tag_name, f'{APP_NAME}.exe'), tag_name, specific=True)
                if on_status:
                    on_status(self.status_message)
            except Exception as exc:
                self.state, self.status_message = 'failed', f'Não foi possível baixar a versão: {exc}'
                log.exception('[Updater] Versão específica falhou')
            finally:
                self.is_checking = False
                self.notify_status(self.status_message)
        threading.Thread(target=worker, daemon=True).start()

    def _download_update_silent(self, download_url, tag='', specific=False):
        tag = tag or f'v{self.new_version}'
        validate_download_url(download_url, tag)
        self.is_downloading, self.update_ready, self.state = True, False, 'downloading'
        self.notify_status(f'Baixando e validando a versão {tag}...')
        partial = self.staging_dir / 'pending.part'
        try:
            try:
                manifest = validate_manifest(read_json_url(release_url(tag, 'update-manifest.json')), tag)
            except Exception as exc:
                raise ValueError('Release sem manifesto válido. Publique EXE e update-manifest.json pelo novo build.') from exc
            self.staging_dir.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(download_url, headers={'User-Agent': APP_NAME})
            downloaded = 0
            with urllib.request.urlopen(req, timeout=60) as response, partial.open('wb') as output:
                length = response.headers.get('Content-Length')
                if length is not None and int(length) != manifest['size']:
                    raise ValueError('Tamanho anunciado pelo servidor difere do manifesto.')
                while True:
                    block = response.read(65536)
                    if not block:
                        break
                    downloaded += len(block)
                    if downloaded > manifest['size']:
                        raise ValueError('Servidor enviou dados além do tamanho esperado.')
                    output.write(block)
            validate_binary(partial, manifest['size'], manifest['sha256'])
            destination = self.staging_dir / 'pending.exe'
            partial.replace(destination)
            write_json_atomic(self.pending_path, {'tag': tag, 'manifest': manifest, 'specific': specific,
                                                  'target': str(Path(sys.executable).resolve())})
            self._manifest, self.downloaded_file = manifest, destination
            self.update_ready, self.state = True, 'ready'
            self.status_message = f'Versão {self.new_version} baixada e validada. Reinicie para instalar.'
        finally:
            self.is_downloading = False
            if partial.exists():
                partial.unlink()
            self.notify_status(self.status_message)
        if self.update_ready and self.on_ready_callback:
            try:
                self.on_ready_callback(self.new_version)
            except Exception:
                log.exception('[Updater] Falha ao publicar download pronto')

    def prepare_install(self):
        """Valida antes da resposta HTTP. Somente o helper altera o EXE."""
        with self._lock:
            if not self.enabled:
                raise ValueError(self.status_message)
            if self.is_applying:
                raise ValueError('A instalação já foi iniciada.')
            if not self.update_ready or not self.downloaded_file or not self._manifest:
                raise ValueError('Nenhuma atualização validada está pronta.')
            validate_binary(self.downloaded_file, self._manifest['size'], self._manifest['sha256'])
            helper_source = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'update_helper.ps1'
            if not helper_source.is_file():
                raise ValueError('Helper de atualização não foi incluído neste build.')
            helper = self.staging_dir / 'update_helper.ps1'
            shutil.copyfile(helper_source, helper)
            target = Path(sys.executable).resolve()
            if target.name != f'{APP_NAME}.exe':
                raise ValueError('Mantenha o nome RemoteXPTI.exe para usar a atualização automática.')
            job = {'pid': os.getpid(), 'target': str(target), 'source': str(self.downloaded_file),
                   'backup': str(target.with_name(f'{target.stem}.previous.exe')),
                   'receipt': str(self.staging_dir / 'receipt.json'), 'result': str(self.staging_dir / 'result.json'),
                   'pending': str(self.pending_path), 'helper_ready': str(self.staging_dir / 'helper-ready.json'),
                   'sha256': self._manifest['sha256'], 'size': self._manifest['size'],
                   'version': self._manifest['version'], 'token': secrets.token_hex(32)}
            for key in ('receipt', 'result', 'helper_ready'):
                path = Path(job[key])
                if path.exists():
                    path.unlink()
            job_path = self.staging_dir / 'job.json'
            write_json_atomic(job_path, job)
            self.is_applying, self.state = True, 'applying'
            return {'helper': helper, 'job_path': job_path, 'job': job}

    def launch_install(self, prepared, cleanup_func=None):
        import time
        helper_process = None
        try:
            env = {k: v for k, v in os.environ.items() if not k.startswith(('_PYI_', '_MEI', 'PYI_'))}
            env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
            powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
            helper_process = launch_independent_process([str(powershell), '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
                              '-ExecutionPolicy', 'Bypass', '-File', str(prepared['helper']),
                              '-JobPath', str(prepared['job_path'])], env=env, cwd=str(self.staging_dir))
            ready, deadline = Path(prepared['job']['helper_ready']), time.monotonic() + 10
            while time.monotonic() < deadline:
                if ready.exists():
                    data = json.loads(ready.read_text(encoding='utf-8-sig'))
                    if data.get('token') == prepared['job']['token']:
                        break
                time.sleep(0.1)
            else:
                raise RuntimeError('O helper não iniciou. O aplicativo continua aberto.')
            self.notify_status('Instalando atualização e reiniciando...')
            cleanup = cleanup_func or self.cleanup_callback
            if cleanup:
                cleanup()
            os._exit(0)
        except Exception as exc:
            # O app ainda está vivo: cancela somente o helper lançado nesta tentativa.
            if helper_process and helper_process.poll() is None:
                helper_process.terminate()
                try:
                    helper_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    helper_process.kill()
            self.is_applying, self.state = False, 'failed'
            self.notify_status(f'Falha ao iniciar instalação: {exc}')
            log.exception('[Updater] Instalação não iniciada')

    def apply_update_and_restart(self, cleanup_func=None):
        try:
            prepared = self.prepare_install()
        except Exception as exc:
            self.notify_status(f'Não foi possível instalar: {exc}')
            return
        self.launch_install(prepared, cleanup_func)
