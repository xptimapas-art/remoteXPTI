"""Separate installed client state from each source checkout's development state."""
import hashlib
import json
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


def get_device_file(filename: str) -> Path:
    """Read legacy device JSON once; all subsequent writes use the profile.

    Original files remain untouched as recovery copies. The DEV never imports
    client or checkout credentials implicitly.
    """
    from atomic_storage import write_json_atomic
    if filename not in ("doors_config.json", "session.json"):
        raise ValueError("Arquivo de dispositivo inválido.")
    target = get_profile_dir() / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    if is_development() or target.exists():
        return target
    for directory in (Path(sys.executable).resolve().parent, Path(__file__).resolve().parent):
        source = directory / filename
        if source == target or not source.is_file():
            continue
        try:
            data = json.loads(source.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if filename == "doors_config.json" and not isinstance(data.get("doors"), list):
            continue
        if filename == "session.json" and not isinstance(data.get("token_info"), dict):
            continue
        write_json_atomic(target, data, overwrite=False)
        break
    return target


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
