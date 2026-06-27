"""Shared hook runtime hash calculation for manifest stamping and validation."""

import hashlib
import os
from pathlib import Path

from sage.asset_paths import hook_runtime_files


def _hash_group(root: str, paths: list[str]) -> str:
    h = hashlib.sha256()
    # Sort paths so callers can pass sets/lists without changing the digest order.
    for path in sorted(paths):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(Path(path).read_bytes())
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


def calculate_hook_runtime_hash(root: str) -> tuple[dict[str, str], list[str]]:
    """Return ({shared, claude, codex}, missing_paths) for hook runtime files.

    The relative file path is part of the digest so two files with swapped contents cannot collide
    at the group level. Absolute project paths are excluded to keep hashes stable across installs.
    """
    groups = hook_runtime_files(root)
    missing = [p for paths in groups.values() for p in paths if not os.path.exists(p)]
    if missing:
        return {}, missing
    return {name: _hash_group(root, paths) for name, paths in groups.items()}, []
