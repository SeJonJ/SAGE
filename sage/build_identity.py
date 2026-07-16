"""Stable identity for the SAGE resources copied into a project."""

import hashlib
import os
import subprocess
from pathlib import Path

from sage import _resources


def _inventory():
    roots = [
        ("engine", Path(__file__).resolve().parent),
        ("templates", _resources.templates_dir()),
        ("core", _resources.core_dir()),
        ("schema", _resources.schema_dir()),
        ("hooks", _resources.hooks_src_dir()),
        ("hook-specs", _resources.hook_specs_dir()),
    ]
    files = []
    for label, root in roots:
        if not os.path.isdir(root):
            continue
        for path in sorted(Path(root).rglob("*")):
            relative = path.relative_to(root)
            if not path.is_file() or "tests" in relative.parts or "__pycache__" in relative.parts:
                continue
            if label == "engine" and ("_bundle" in relative.parts or path.suffix != ".py"):
                continue
            if label == "templates" and relative.parts[0] == "core":
                continue
            files.append((f"{label}/{relative.as_posix()}", path))
    return files


def source_core_content_hash():
    digest = hashlib.sha256()
    for logical, path in _inventory():
        digest.update(logical.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def source_identity():
    root = _resources.sage_root()
    commit = "unknown"
    dirty = False
    try:
        commit = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", root, "status", "--porcelain",
                                     "--untracked-files=no"], capture_output=True,
                                    text=True, check=True).stdout.strip())
    except Exception:
        pass
    content_hash = source_core_content_hash()
    return {
        "sage_source_commit": commit,
        "source_core_content_hash": content_hash,
        "installed_core_content_hash": content_hash,
        "dirty_flag": dirty,
    }
