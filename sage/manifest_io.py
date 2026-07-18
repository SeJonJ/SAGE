"""Crash-safe writes for the SAGE manifest and related JSON receipts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any


def atomic_write_json(path: str | os.PathLike[str], value: Any) -> None:
    """Serialize JSON to a same-directory temp file and atomically replace the target."""
    target = Path(path)
    fd, staged = tempfile.mkstemp(prefix=".sage-manifest-", dir=str(target.parent))
    try:
        try:
            mode = stat.S_IMODE(os.stat(target, follow_symlinks=False).st_mode)
        except FileNotFoundError:
            mode = None
        fchmod = getattr(os, "fchmod", None)
        if mode is not None and callable(fchmod):
            fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, target)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(staged)
        except FileNotFoundError:
            pass
