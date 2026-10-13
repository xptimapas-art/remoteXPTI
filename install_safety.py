"""Operações limitadas à instalação escolhida, sem limpeza de diretórios."""
import os
from pathlib import Path


def validate_install_dir(value):
    target = Path(value).expanduser()
    if not target.is_absolute() or target.name.casefold() != 'remotexpti':
        raise ValueError('Escolha uma pasta dedicada chamada RemoteXPTI, por exemplo C:\\Apps\\RemoteXPTI.')
    absolute = Path(os.path.abspath(target))
    if target.resolve() != absolute:
        raise ValueError('A pasta de instalação não pode redirecionar para outra pasta.')
    if target.exists() and not target.is_dir():
        raise ValueError('O destino não é uma pasta.')
    return absolute


def close_installed_app(target_dir):
    import psutil
    expected = (target_dir / 'RemoteXPTI.exe').resolve()
    processes = []
    for process in psutil.process_iter(['pid', 'exe']):
        try:
            if process.pid != os.getpid() and process.info['exe'] and Path(process.info['exe']).resolve() == expected:
                processes.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    for process in processes:
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(processes, timeout=10)
    if alive:
        raise RuntimeError('Feche o RemoteXPTI desta pasta e tente novamente.')
