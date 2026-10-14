"""Separate installed client state from each source checkout's development state."""
import hashlib
import os
import sys
from pathlib import Path


def is_development() -> bool:
    return not bool(getattr(sys, "frozen", False))


def development_id() -> str:
    workspace = str(Path(__file__).resolve().parent).casefold()
    return hashlib.sha256(workspace.encode("utf-8")).hexdigest()[:12]


def get_profile_dir() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    if is_development():
        return local / "RemoteXPTI-Dev" / development_id()
    return local / "RemoteXPTI"


def get_data_dir() -> Path:
    if is_development():
        return get_profile_dir()
    return Path(sys.executable).resolve().parent


def get_window_title() -> str:
    name = "RemoteXPTI DEV" if is_development() else "RemoteXPTI"
    return f"{name} - RDP Quick Launcher"


def get_mutex_name() -> str:
    if is_development():
        return f"RemoteXPTI_Development_{development_id()}_Mutex"
    return "RemoteXPTI_SingleInstance_Mutex"


def get_app_user_model_id() -> str:
    if is_development():
        return f"XPTI.RemoteXPTI.Development.{development_id()}"
    return "XPTI.RemoteXPTI.Modern.App"
