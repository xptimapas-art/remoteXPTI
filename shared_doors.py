"""Encrypted company access settings; no passwords or keys in cloud plaintext."""
import base64
import ctypes
from ctypes import wintypes
from copy import deepcopy
import hashlib
import json

from cryptography.fernet import Fernet

FIELD = "encrypted_doors_v1"


def password_key(password):
    derived = hashlib.pbkdf2_hmac("sha256", password.strip().encode(),
                                 b"RemoteXPTI/company-doors/v1", 300000, dklen=32)
    return base64.urlsafe_b64encode(derived)


def protect_key(key, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(key) if decrypt else key
    buffer = ctypes.create_string_buffer(raw)
    incoming = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        function = crypt.CryptUnprotectData
        description = None
    else:
        function = crypt.CryptProtectData
        description = "RemoteXPTI company doors"
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p if decrypt else wintypes.LPCWSTR,
                         ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(incoming), description, None, None, None, 1, ctypes.byref(outgoing)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        result = ctypes.string_at(outgoing.data, outgoing.size)
        return result if decrypt else base64.b64encode(result).decode()
    finally:
        kernel.LocalFree(outgoing.data)


def shared_config(config):
    doors = []
    for original in config.get("doors", []):
        if original.get("share_with_company", True) is False:
            continue
        door = deepcopy(original)
        for field in ("last_triggered", "cloud_online", "is_local", "_cloud_managed"):
            door.pop(field, None)
        doors.append(door)
    return {"doors": doors}


def encrypt_config(config, key):
    return Fernet(key).encrypt(json.dumps(shared_config(config), ensure_ascii=False).encode()).decode()


def decrypt_config(envelope, key):
    data = json.loads(Fernet(key).decrypt(envelope[FIELD].encode()))
    if not isinstance(data, dict) or not isinstance(data.get("doors"), list) or any(
        not isinstance(door, dict) or not door.get("id") for door in data["doors"]
    ):
        raise ValueError("Configuração compartilhada inválida.")
    return data


def revision(notes):
    return hashlib.sha256(notes.encode()).hexdigest()


def merge_config(local, remote):
    merged = deepcopy(local)
    previous = {door["id"]: door for door in local.get("doors", [])}
    incoming = []
    for original in remote.get("doors", []):
        door = deepcopy(original)
        old = previous.get(door["id"], {})
        for field in ("hotkey", "enabled", "last_triggered"):
            if field in old:
                door[field] = old[field]
        door["_cloud_managed"] = True
        incoming.append(door)
    received = {door["id"] for door in incoming}
    incoming.extend(deepcopy(door) for door in previous.values()
                    if door["id"] not in received and not door.get("_cloud_managed"))
    merged["doors"] = incoming
    if "_shared_revision" in remote:
        merged["_shared_revision"] = remote["_shared_revision"]
    return merged
