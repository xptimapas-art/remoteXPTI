"""
Sistema de Registro de Logs e Diagnóstico do RemoteXPTI.
Armazena logs rotativos em %LOCALAPPDATA%\\RemoteXPTI\\logs\\remotexpti.log
para diagnóstico rápido e seguro em máquinas de clientes.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import subprocess

def get_logs_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    logs_dir = Path(local_appdata) / "RemoteXPTI" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir

def get_log_file_path() -> Path:
    return get_logs_dir() / "remotexpti.log"

def setup_logger() -> logging.Logger:
    logger = logging.getLogger("RemoteXPTI")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    log_file = get_log_file_path()

    # Rotação de logs: máximo 5MB por arquivo, até 3 cópias de backup
    try:
        file_handler = RotatingFileHandler(
            str(log_file),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        pass

    # Se não for frozen (modo dev), adiciona saída no console
    if not getattr(sys, "frozen", False):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(console_handler)

    # Intercepta exceções não tratadas para gravar no arquivo de log
    def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Exceção não tratada capturada:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_unhandled_exception

    return logger

log = setup_logger()

def open_logs_folder():
    """Abre o diretório de logs no Windows Explorer para o cliente ou suporte técnico."""
    logs_dir = get_logs_dir()
    try:
        os.startfile(str(logs_dir))
    except Exception:
        try:
            subprocess.Popen(["explorer.exe", str(logs_dir)])
        except Exception:
            pass
