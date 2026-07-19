"""Integrity-bound PDCA context packets for explicit cross-session resume."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any

import yaml

from sage import _resources
from sage.runtime_hosts import active_host, configured_hosts, profile_issues as runtime_profile_issues


SCHEMA_VERSION = 1
DEFAULT_MAX_SNAPSHOT_BYTES = 1024 * 1024
MIN_MAX_SNAPSHOT_BYTES = 1024
MAX_MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
PRESERVE_SOURCES = {
    "architectural_decisions": ("02",),
    "open_bugs": ("04", "05"),
    "file_ownership": ("03",),
    "pending_verifications": ("03", "04", "05"),
}


class ContextError(ValueError):
    """A controlled fail-closed error for snapshot or restore input."""


def profile_issues(profile: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Validate context settings without depending on optional jsonschema."""
    if not isinstance(profile, dict):
        return []
    context = profile.get("context_management")
    if context is None:
        return []
    if not isinstance(context, dict):
        return [("FAIL", "context_management 는 매핑(object)이어야 함")]
    issues = []
    unknown = sorted(set(context) - {"compaction"}, key=str)
    if unknown:
        issues.append(("FAIL", f"context_management 에 미지 키 {unknown}"))
    compaction = context.get("compaction")
    if compaction is None:
        return issues
    if not isinstance(compaction, dict):
        return issues + [("FAIL", "context_management.compaction 은 매핑(object)이어야 함")]
    unknown = sorted(set(compaction) - {"enabled", "preserve", "max_snapshot_bytes"}, key=str)
    if unknown:
        issues.append(("FAIL", f"context_management.compaction 에 미지 키 {unknown}"))

    enabled = compaction.get("enabled")
    if not isinstance(enabled, bool):
        issues.append(("FAIL", "context_management.compaction.enabled 는 bool(true/false)이어야 함"))

    preserve = compaction.get("preserve")
    if not isinstance(preserve, list):
        issues.append(("FAIL", "context_management.compaction.preserve 는 리스트여야 함"))
    else:
        if enabled is True and not preserve:
            issues.append(("FAIL", "compaction.enabled=true 이면 preserve 는 비어 있을 수 없음"))
        if any(not isinstance(item, str) or item not in PRESERVE_SOURCES for item in preserve):
            issues.append(("FAIL", "context_management.compaction.preserve 에 지원하지 않는 항목이 있음 — "
                                   f"허용: {sorted(PRESERVE_SOURCES)}"))
        if len(preserve) != len(set(item for item in preserve if isinstance(item, str))):
            issues.append(("FAIL", "context_management.compaction.preserve 는 중복을 허용하지 않음"))

    limit = compaction.get("max_snapshot_bytes", DEFAULT_MAX_SNAPSHOT_BYTES)
    if (isinstance(limit, bool) or not isinstance(limit, int)
            or limit < MIN_MAX_SNAPSHOT_BYTES or limit > MAX_MAX_SNAPSHOT_BYTES):
        issues.append(("FAIL", "context_management.compaction.max_snapshot_bytes 는 "
                               f"{MIN_MAX_SNAPSHOT_BYTES}..{MAX_MAX_SNAPSHOT_BYTES} 정수여야 함"))
    return issues


def _config(profile: dict[str, Any]) -> dict[str, Any]:
    issues = profile_issues(profile)
    if issues:
        raise ContextError(issues[0][1])
    compaction = ((profile.get("context_management") or {}).get("compaction") or {})
    if compaction.get("enabled") is not True:
        raise ContextError("context snapshot is disabled: context_management.compaction.enabled=true is required")
    return {
        "preserve": list(compaction["preserve"]),
        "max_snapshot_bytes": compaction.get("max_snapshot_bytes", DEFAULT_MAX_SNAPSHOT_BYTES),
    }


def _profile_contract(profile: dict[str, Any]) -> dict[str, Any]:
    project = profile.get("project")
    if not isinstance(project, dict):
        raise ContextError("project profile project section must be a mapping")
    failures = [message for severity, message in runtime_profile_issues(profile) if severity == "FAIL"]
    if failures:
        raise ContextError(f"project profile runtime contract failed: {failures[0]}")
    return project


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContextError("context-bound profile and packet values must be JSON-compatible") from exc
    return encoded.encode("utf-8")


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _root_path(root: str | os.PathLike[str]) -> Path:
    path = Path(root).expanduser().absolute()
    if not path.is_dir():
        raise ContextError(f"project root is not a directory: {path}")
    return path.resolve(strict=True)


def _assert_confined(root: Path, path: Path, label: str) -> None:
    try:
        relative = path.absolute().relative_to(root)
    except ValueError as exc:
        raise ContextError(f"{label} escapes project root: {path}") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink():
                raise ContextError(f"{label} uses a symlink path: {current}")
    if path.exists() and not path.resolve(strict=True).is_relative_to(root):
        raise ContextError(f"{label} resolves outside project root: {path}")


def _read_regular(root: Path, path: Path, label: str, limit: int) -> bytes:
    _assert_confined(root, path, label)
    try:
        relative = path.absolute().relative_to(root)
    except ValueError as exc:
        raise ContextError(f"{label} escapes project root: {path}") from exc
    if not relative.parts:
        raise ContextError(f"{label} must name a file below project root: {path}")

    fd = None
    directory_fd = None
    try:
        directory_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                           | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
        directory_fd = os.open(root, directory_flags)
        for part in relative.parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd

        leaf = relative.parts[-1]
        before = os.stat(leaf, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise ContextError(f"{label} is not a regular file: {path}")
        if before.st_size > limit:
            raise ContextError(f"{label} exceeds byte budget ({before.st_size} > {limit})")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(leaf, flags, dir_fd=directory_fd)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ContextError(f"{label} is not a regular file: {path}")
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ContextError(f"{label} changed during secure open: {path}")
        if opened.st_size > limit:
            raise ContextError(f"{label} exceeds byte budget ({opened.st_size} > {limit})")
        chunks = []
        total = 0
        while total <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > limit:
            raise ContextError(f"{label} exceeds byte budget ({total} > {limit})")
        after = os.fstat(fd)
        if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (
                opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns):
            raise ContextError(f"{label} changed while being read: {path}")
        return b"".join(chunks)
    except ContextError:
        raise
    except OSError as exc:
        raise ContextError(f"{label} secure read failed: {path}: {exc}") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _load_profile(root: Path) -> tuple[dict[str, Any], bytes]:
    path = root / "sage" / "project-profile.yaml"
    raw = _read_regular(root, path, "project profile", MAX_MAX_SNAPSHOT_BYTES)
    try:
        profile = yaml.safe_load(raw.decode("utf-8"))
    except Exception as exc:
        raise ContextError(f"project profile load failed: {type(exc).__name__}: {exc}") from exc
    if not isinstance(profile, dict):
        raise ContextError("project profile must be a mapping")
    return profile, raw


def _semantic_profile(profile: dict[str, Any]) -> dict[str, Any]:
    semantic = copy.deepcopy(profile)
    runtime = semantic.get("runtime")
    if isinstance(runtime, dict):
        runtime.pop("active_host", None)
        runtime.pop("host", None)
    return semantic


def _cycle_binding():
    hooks = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks")
    import sys
    if hooks not in sys.path:
        sys.path.insert(0, hooks)
    import cycle_binding
    return cycle_binding


def _safe_glob(pattern: Any) -> str:
    if (not isinstance(pattern, str) or not pattern.strip() or os.path.isabs(pattern)
            or ".." in pattern.replace("\\", "/").split("/")):
        raise ContextError(f"unsafe PDCA phase glob: {pattern!r}")
    return pattern


def _phase_contract(profile: dict[str, Any], completed_phase: str) -> tuple[list[dict[str, Any]], int]:
    pdca = profile.get("pdca")
    phases = pdca.get("phases") if isinstance(pdca, dict) else None
    if not isinstance(phases, list) or not phases:
        raise ContextError("profile pdca.phases is required for context snapshot")
    normalized = []
    seen = set()
    for item in phases:
        if not isinstance(item, dict):
            raise ContextError("each pdca phase must be a mapping")
        phase_id = str(item.get("id") or "")
        if not phase_id or phase_id in seen:
            raise ContextError(f"invalid or duplicate PDCA phase id: {phase_id!r}")
        seen.add(phase_id)
        normalized.append({"id": phase_id, "glob": _safe_glob(item.get("glob"))})
    try:
        index = next(i for i, item in enumerate(normalized) if item["id"] == str(completed_phase))
    except StopIteration as exc:
        raise ContextError(f"completed phase is not declared in profile: {completed_phase!r}") from exc
    return normalized, index


def _load_phase_docs(root: Path, phases: list[dict[str, Any]], completed_index: int,
                     stem: str, limit: int) -> list[dict[str, Any]]:
    binding = _cycle_binding()
    total = 0
    selected = []
    for item in phases[:completed_index + 1]:
        docs = []
        for raw_path in sorted(glob.glob(str(root / item["glob"]), recursive=True)):
            path = Path(raw_path).absolute()
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError as exc:
                raise ContextError(f"phase glob escaped project root: {path}") from exc
            if binding.path_stem(relative) != stem:
                continue
            remaining = limit - total
            if remaining < 0:
                raise ContextError("phase documents exceed context byte budget")
            raw = _read_regular(root, path, f"phase {item['id']} document", remaining)
            total += len(raw)
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ContextError(f"phase {item['id']} document must be UTF-8: {relative}") from exc
            docs.append({"path": relative, "content": content, "raw": raw})
        if not docs:
            raise ContextError(f"phase document missing through completed boundary for "
                               f"Cycle-Stem {stem!r}: {item['id']}")
        doc, error = binding.select_document(docs, stem)
        if error:
            raise ContextError(f"phase {item['id']} exact cycle selection failed: {error}")
        selected.append({
            "phase": item["id"],
            "path": doc["path"],
            "sha256": _digest(doc["raw"]),
            "size": len(doc["raw"]),
        })
    return selected


def _manifest_binding(root: Path, limit: int) -> dict[str, Any]:
    path = root / "docs" / "sage_harness" / ".manifest.json"
    if not path.exists() and not path.is_symlink():
        return {"path": "docs/sage_harness/.manifest.json", "present": False, "sha256": None}
    raw = _read_regular(root, path, "manifest", limit)
    return {"path": "docs/sage_harness/.manifest.json", "present": True, "sha256": _digest(raw)}


def _ensure_directory(root: Path, relative: str, label: str) -> Path:
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_dir():
                raise ContextError(f"{label} uses an unsafe existing path: {path}")
        else:
            path.mkdir(mode=0o700)
    _assert_confined(root, path, label)
    return path


def _atomic_write(path: Path, data: bytes) -> None:
    fd, temp_path = tempfile.mkstemp(prefix=".sage-context-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


def _created_at(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContextError(f"created_at must be ISO-8601 UTC: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContextError(f"created_at must be ISO-8601 UTC: {value!r}")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def create_snapshot(root: str | os.PathLike[str], cycle_stem: str, completed_phase: str,
                    *, created_at: str | None = None) -> dict[str, Any]:
    """Create a corruption-detecting packet bound to live repository sources at restore."""
    project_root = _root_path(root)
    profile, profile_raw = _load_profile(project_root)
    project = _profile_contract(profile)
    config = _config(profile)
    binding = _cycle_binding()
    stem = binding.normalize_stem(cycle_stem)
    if stem is None:
        raise ContextError(f"invalid Cycle-Stem: {cycle_stem!r}")
    phases, completed_index = _phase_contract(profile, str(completed_phase))
    docs = _load_phase_docs(project_root, phases, completed_index, stem, config["max_snapshot_bytes"])
    manifest = _manifest_binding(project_root, config["max_snapshot_bytes"])
    full_profile_hash = _digest(profile_raw)
    semantic_profile_hash = _digest(_canonical(_semantic_profile(profile)))
    next_phase = phases[completed_index + 1]["id"] if completed_index + 1 < len(phases) else None
    payload = {
        "project": {
            "name": str(project.get("name") or ""),
            "prefix": str(project.get("prefix") or ""),
        },
        "cycle": {"stem": stem, "completed_phase": str(completed_phase), "next_phase": next_phase},
        "runtime": {"active_host": active_host(profile), "installed_hosts": configured_hosts(profile)},
        "profile": {
            "path": "sage/project-profile.yaml",
            "sha256": full_profile_hash,
            "semantic_sha256": semantic_profile_hash,
        },
        "manifest": manifest,
        "phase_docs": docs,
        "compaction": config,
    }
    core = {"schema_version": SCHEMA_VERSION, "created_at": _created_at(created_at), "payload": payload}
    digest = _digest(_canonical(core))
    snapshot_id = "ctx-" + digest.split(":", 1)[1][:16]
    envelope = {**core, "snapshot_id": snapshot_id, "integrity_sha256": digest}
    data = json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if len(data) > config["max_snapshot_bytes"]:
        raise ContextError(f"snapshot packet exceeds byte budget ({len(data)} > {config['max_snapshot_bytes']})")
    directory = _ensure_directory(project_root, f".sage/context/snapshots/{stem}", "snapshot directory")
    path = directory / f"{completed_phase}-{snapshot_id}.json"
    _assert_confined(project_root, path, "snapshot path")
    _atomic_write(path, data)
    return {"path": str(path), "snapshot_id": snapshot_id, "envelope": envelope}


def _expect_mapping(value: Any, label: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ContextError(f"malformed context packet {label}")
    return value


def _load_packet(root: Path, snapshot_path: str | os.PathLike[str], limit: int) -> tuple[dict[str, Any], Path]:
    path = Path(snapshot_path).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.absolute()
    managed = root / ".sage" / "context" / "snapshots"
    try:
        path.relative_to(managed)
    except ValueError as exc:
        raise ContextError(f"snapshot must be inside managed snapshot directory: {managed}") from exc
    raw = _read_regular(root, path, "snapshot packet", limit)
    try:
        packet = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ContextError(f"snapshot packet JSON is invalid: {type(exc).__name__}") from exc
    packet = _expect_mapping(packet, "envelope", {
        "schema_version", "created_at", "snapshot_id", "payload", "integrity_sha256",
    })
    if packet["schema_version"] != SCHEMA_VERSION:
        raise ContextError(f"unsupported context packet schema_version: {packet['schema_version']!r}")
    core = {key: packet[key] for key in ("schema_version", "created_at", "payload")}
    digest = _digest(_canonical(core))
    expected_id = "ctx-" + digest.split(":", 1)[1][:16]
    if packet["integrity_sha256"] != digest or packet["snapshot_id"] != expected_id:
        raise ContextError("context packet integrity verification failed")
    payload = _expect_mapping(packet["payload"], "payload", {
        "project", "cycle", "runtime", "profile", "manifest", "phase_docs", "compaction",
    })
    cycle = _expect_mapping(payload["cycle"], "cycle", {"stem", "completed_phase", "next_phase"})
    binding = _cycle_binding()
    if (not isinstance(cycle["stem"], str) or binding.normalize_stem(cycle["stem"]) != cycle["stem"]
            or not isinstance(cycle["completed_phase"], str) or not cycle["completed_phase"]
            or (cycle["next_phase"] is not None
                and (not isinstance(cycle["next_phase"], str) or not cycle["next_phase"]))):
        raise ContextError("malformed context packet cycle")
    expected_path = managed / cycle["stem"] / f"{cycle['completed_phase']}-{packet['snapshot_id']}.json"
    if path != expected_path:
        raise ContextError("context packet path does not match its cycle, phase, and snapshot id")
    return packet, path


def _verify_profile_binding(profile: dict[str, Any], raw: bytes, expected: dict[str, Any]) -> None:
    expected = _expect_mapping(expected, "profile binding", {"path", "sha256", "semantic_sha256"})
    if expected["path"] != "sage/project-profile.yaml":
        raise ContextError("malformed context packet profile path")
    if _digest(raw) == expected["sha256"]:
        return
    if _digest(_canonical(_semantic_profile(profile))) != expected["semantic_sha256"]:
        raise ContextError("profile semantic binding changed since snapshot")


def _verify_manifest_binding(root: Path, expected: dict[str, Any], limit: int) -> None:
    expected = _expect_mapping(expected, "manifest binding", {"path", "present", "sha256"})
    if expected["path"] != "docs/sage_harness/.manifest.json" or not isinstance(expected["present"], bool):
        raise ContextError("malformed context packet manifest binding")
    current = _manifest_binding(root, limit)
    if current != expected:
        raise ContextError("manifest binding changed since snapshot")


def _verify_phase_bindings(root: Path, docs: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(docs, list) or not docs:
        raise ContextError("malformed context packet phase document bindings")
    verified = []
    total = 0
    seen_phases = set()
    for item in docs:
        item = _expect_mapping(item, "phase document", {"phase", "path", "sha256", "size"})
        if (not isinstance(item["phase"], str) or item["phase"] in seen_phases
                or not isinstance(item["path"], str) or os.path.isabs(item["path"])
                or ".." in item["path"].replace("\\", "/").split("/")
                or isinstance(item["size"], bool) or not isinstance(item["size"], int) or item["size"] < 0):
            raise ContextError("malformed context packet phase document binding")
        seen_phases.add(item["phase"])
        remaining = limit - total
        raw = _read_regular(root, root / item["path"], f"phase {item['phase']} document", remaining)
        total += len(raw)
        if len(raw) != item["size"] or _digest(raw) != item["sha256"]:
            raise ContextError(f"phase document binding changed since snapshot: {item['path']}")
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContextError(f"phase document is not UTF-8: {item['path']}") from exc
        verified.append({**item, "content": content})
    return verified


def _fence(content: str) -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"~+", content)), default=0)
    return "~" * max(4, longest + 1)


def _render_briefing(packet: dict[str, Any], profile: dict[str, Any], docs: list[dict[str, Any]]) -> str:
    payload = packet["payload"]
    cycle = payload["cycle"]
    from_host = payload["runtime"]["active_host"]
    to_host = active_host(profile)
    by_phase = {item["phase"]: item for item in docs}
    selected_phases = {cycle["completed_phase"]}
    preserve = payload["compaction"]["preserve"]
    lines = [
        "# SAGE Restored Context",
        "",
        f"Snapshot-ID: `{packet['snapshot_id']}`",
        f"Cycle-Stem: `{cycle['stem']}`",
        f"Completed-Phase: `{cycle['completed_phase']}`",
        f"Next-Phase: `{cycle['next_phase'] or 'N/A'}`",
        f"Host-Handoff: `{from_host} -> {to_host}`",
        "",
        "This briefing was materialized from an integrity-checked packet and current hash-matched repository files.",
        "It does not restore hidden model conversation state.",
        "",
        "## Preserved Context Index",
        "",
    ]
    for key in preserve:
        phases = [phase for phase in PRESERVE_SOURCES[key] if phase in by_phase]
        selected_phases.update(phases)
        sources = ", ".join(f"{phase}:{by_phase[phase]['path']}" for phase in phases) or "N/A"
        lines.append(f"- `{key}`: {sources}")
    lines.extend(["", "## Bound Source Documents", ""])
    for item in docs:
        if item["phase"] not in selected_phases:
            continue
        fence = _fence(item["content"])
        lines.extend([
            f"### Phase {item['phase']} - `{item['path']}`",
            "",
            f"source_sha256: `{item['sha256']}`",
            "",
            f"{fence}markdown",
            item["content"].rstrip("\n"),
            fence,
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def restore_snapshot(root: str | os.PathLike[str], snapshot_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Verify a packet and materialize a briefing for a resumed SAGE skill."""
    project_root = _root_path(root)
    profile, profile_raw = _load_profile(project_root)
    _profile_contract(profile)
    config = _config(profile)
    packet, _ = _load_packet(project_root, snapshot_path, config["max_snapshot_bytes"])
    payload = packet["payload"]
    cycle = payload["cycle"]
    phases, completed_index = _phase_contract(profile, cycle["completed_phase"])
    expected_phases = [item["id"] for item in phases[:completed_index + 1]]
    expected_next = phases[completed_index + 1]["id"] if completed_index + 1 < len(phases) else None
    if cycle["next_phase"] != expected_next:
        raise ContextError("context packet next phase does not match the profile phase boundary")
    _verify_profile_binding(profile, profile_raw, payload["profile"])
    _verify_manifest_binding(project_root, payload["manifest"], config["max_snapshot_bytes"])
    docs = _verify_phase_bindings(project_root, payload["phase_docs"], config["max_snapshot_bytes"])
    if [item["phase"] for item in docs] != expected_phases:
        raise ContextError("context packet phase sequence does not match the completed profile boundary")
    binding = _cycle_binding()
    for item, phase in zip(docs, phases[:completed_index + 1]):
        if (not binding.matches_glob(item["path"], phase["glob"])
                or binding.path_stem(item["path"]) != cycle["stem"]):
            raise ContextError(f"context packet phase path binding is invalid: {item['path']}")

    runtime = _expect_mapping(payload["runtime"], "runtime", {"active_host", "installed_hosts"})
    snapshot_hosts = runtime["installed_hosts"]
    if (runtime["active_host"] not in ("claude", "codex")
            or not isinstance(snapshot_hosts, list) or not snapshot_hosts
            or any(host not in ("claude", "codex") for host in snapshot_hosts)
            or len(snapshot_hosts) != len(set(snapshot_hosts))
            or runtime["active_host"] not in snapshot_hosts
            or active_host(profile) not in configured_hosts(profile)
            or set(snapshot_hosts) != set(configured_hosts(profile))):
        raise ContextError("runtime host binding changed or is malformed")
    compaction = _expect_mapping(payload["compaction"], "compaction", {"preserve", "max_snapshot_bytes"})
    if compaction != config:
        raise ContextError("compaction binding changed since snapshot")
    project = _expect_mapping(payload["project"], "project", {"name", "prefix"})
    current_project = profile.get("project") if isinstance(profile.get("project"), dict) else {}
    if project != {"name": str(current_project.get("name") or ""),
                   "prefix": str(current_project.get("prefix") or "")}:
        raise ContextError("project identity binding changed since snapshot")

    briefing = _render_briefing(packet, profile, docs).encode("utf-8")
    if len(briefing) > config["max_snapshot_bytes"]:
        raise ContextError(f"restored briefing exceeds byte budget ({len(briefing)} > {config['max_snapshot_bytes']})")
    directory = _ensure_directory(project_root, ".sage/context/restored", "restore directory")
    path = directory / f"{cycle['stem']}-{packet['snapshot_id']}.md"
    _assert_confined(project_root, path, "restore path")
    _atomic_write(path, briefing)
    from_host = runtime["active_host"]
    to_host = active_host(profile)
    return {
        "path": str(path),
        "snapshot_id": packet["snapshot_id"],
        "from_host": from_host,
        "to_host": to_host,
        "host_handoff": from_host != to_host,
        "next_phase": cycle["next_phase"],
    }
