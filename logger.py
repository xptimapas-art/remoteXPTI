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
import platform

class StreamToLogger:
    """Redireciona saídas padrão (print / stdout / stderr) diretamente para o logger."""
    def __init__(self, logger_instance: logging.Logger, level: int):
        self.logger = logger_instance
        self.level = level
        self._in_write = False

    def write(self, buf):
        if self._in_write:
            return
        self._in_write = True
        try:
            for line in buf.rstrip().splitlines():
                msg = line.rstrip()
                if msg:
                    self.logger.log(self.level, msg)
        except Exception:
            pass
        finally:
            self._in_write = False

    def flush(self):
        pass

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

    # Rotação de logs: máximo 5MB por arquivo, até 3 cópias de backup (máximo 20MB total)
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

    # Em modo desenvolvimento (console aberto), mantém cópia no terminal usando __stdout__ de forma segura contra encoding
    if not getattr(sys, "frozen", False) and hasattr(sys, "__stdout__") and sys.__stdout__:
        try:
            if hasattr(sys.__stdout__, "reconfigure"):
                try:
                    sys.__stdout__.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass

            class SafeConsoleHandler(logging.StreamHandler):
                def emit(self, record):
                    try:
                        msg = self.format(record)
                        stream = self.stream
                        try:
                            stream.write(msg + self.terminator)
                            self.flush()
                        except (UnicodeEncodeError, UnicodeError):
                            safe_msg = msg.encode("ascii", errors="replace").decode("ascii")
                            stream.write(safe_msg + self.terminator)
                            self.flush()
                    except Exception:
                        pass

            console_handler = SafeConsoleHandler(sys.__stdout__)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            logger.addHandler(console_handler)
        except Exception:
            pass

    # Redireciona sys.stdout e sys.stderr para o logger
    # Assim, TODO print() e qualquer aviso/erro de biblioteca vai para remotexpti.log
    sys.stdout = StreamToLogger(logger, logging.INFO)
    sys.stderr = StreamToLogger(logger, logging.ERROR)

    # Intercepta exceções não tratadas de threads Python
    def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("❌ EXCEÇÃO NÃO TRATADA CAPTURADA:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_unhandled_exception

    return logger

log = setup_logger()

def log_system_diagnostics(version_str: str):
    """Grava cabeçalho com informações completas de ambiente e hardware do cliente."""
    try:
        log.info("=" * 70)
        log.info(f"⚡ INICIANDO REMOTEXPTI v{version_str}")
        log.info("=" * 70)
        log.info(f"Sistema Operacional: {platform.platform()} ({platform.machine()})")
        log.info(f"Windows Version: {platform.win32_ver()}")
        log.info(f"Python Runtime: {platform.python_version()} (Frozen: {getattr(sys, 'frozen', False)})")
        log.info(f"Executável: {sys.executable}")
        log.info(f"Diretório Base: {Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent}")
        log.info(f"LOCALAPPDATA: {os.environ.get('LOCALAPPDATA', 'Não definido')}")
        log.info(f"USERPROFILE: {os.environ.get('USERPROFILE', 'Não definido')}")
        log.info(f"Arquivo de Log: {get_log_file_path()}")
        log.info("-" * 70)
    except Exception as e:
        log.error(f"Erro ao registrar diagnóstico de sistema: {e}")

def hook_tkinter_exceptions(app):
    """Instala captura de exceções em callbacks do Tkinter/CustomTkinter."""
    def report_callback_exception(exc_type, exc_value, exc_traceback):
        log.error("❌ ERRO EM CALLBACK DO TKINTER/UI:", exc_info=(exc_type, exc_value, exc_traceback))

    try:
        app.report_callback_exception = report_callback_exception
    except Exception:
        pass

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
