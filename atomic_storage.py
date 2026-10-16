"""Small atomic JSON writer shared by persistent desktop settings."""
import json
import os
from pathlib import Path
import tempfile


class PersistenceError(OSError):
    """The last committed state remains valid; the proposed edit was not saved."""


def write_json_atomic(path, data, *, overwrite=True):
    path = Path(path)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # Migration must never replace a profile created by another process.
            try:
                os.link(temporary, path)
            except FileExistsError:
                return False
    except (OSError, ValueError, TypeError) as error:
        raise PersistenceError("Não foi possível salvar os dados. Verifique o espaço e a permissão da pasta e tente novamente.") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass  # A leftover temporary file must not hide the commit result.
    return True
