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


def source_core_content_snapshot():
    """(집계 해시, {논리경로: 파일 해시}) — 한 번의 pass 로 둘 다 만든다.

    집계 해시는 설치된 프로젝트 manifest 의 `source_core_content_hash` 로 박히는 값이라
    **알고리즘을 바꾸면 전 소비자가 drift 로 오판된다.** 논리경로 맵은 그 값이 달라졌을 때
    *어느 파일이* 달라졌는지 지목하기 위한 부가 정보이며 집계 해시에는 들어가지 않는다.
    """
    digest = hashlib.sha256()
    per_file = {}
    for logical, path in _inventory():
        data = path.read_bytes()
        digest.update(logical.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
        per_file[logical] = hashlib.sha256(data).hexdigest()
    return "sha256:" + digest.hexdigest(), per_file


def source_core_content_hash():
    return source_core_content_snapshot()[0]


def describe_content_drift(before, after):
    """두 snapshot 맵의 차이를 사람이 읽을 한 줄로. 같은 내용이면 "".

    "소스가 바뀌었다"까지만 말하는 진단은 원인 특정에 가설 배제 작업을 강요한다. 인벤토리는
    150여 개라 논리경로 단위 비교 비용이 무시할 수준이고, 대부분의 실제 원인(변이 테스트나
    리뷰어가 hooks 트리를 제자리에서 고쳤다 되돌림)은 경로 이름만 보면 즉시 끝난다.
    """
    before = before or {}
    after = after or {}
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    parts = []
    for label, paths in (("변경", changed), ("추가", added), ("삭제", removed)):
        if paths:
            shown = ", ".join(paths[:5])
            more = f" 외 {len(paths) - 5}건" if len(paths) > 5 else ""
            parts.append(f"{label} {len(paths)}건: {shown}{more}")
    return " | ".join(parts)


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
