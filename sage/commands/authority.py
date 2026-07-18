"""Protected-CI adapter for the pure SAGE authority decision core."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time
from typing import Any

import yaml

from sage import _resources
from sage import ci_authority
from sage.profile_compile import ProfileCompileError, materialize_profile
from sage.profile_validate import severity_of, validate_profile

_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_PHASE_IDS = ("00", "01", "02", "03", "04", "05")
_MAX_DIFF_CHANGES = 10_000
_MAX_BLOB_BYTES = 5 * 1024 * 1024
_MAX_PHASE_DOCS = 1_000
_MAX_TOKEN_BYTES = ci_authority.MAX_TOKEN_BYTES
_REGULAR_BLOB_MODES = frozenset({"100644", "100755"})


class AuthorityCliError(ValueError):
    """Controlled, fail-closed adapter error."""


def _is_regular_blob(entry: dict[str, str] | None) -> bool:
    return bool(entry and entry.get("kind") == "blob" and entry.get("mode") in _REGULAR_BLOB_MODES)


def register(sub):
    parser = sub.add_parser(
        "authority",
        help="보호된 CI에서 base/head 정책과 exact PDCA 증거를 검증합니다",
    )
    actions = parser.add_subparsers(dest="action", metavar="<action>")
    actions.required = True

    inspect = actions.add_parser("inspect", help="base/head git object를 읽어 권위 판정을 계산합니다")
    _add_inspection_args(inspect)
    inspect.set_defaults(func=_run_inspect)

    attest = actions.add_parser("attest", help="보호된 CI 판정 claims를 HMAC 서명합니다")
    attest.add_argument("--issuer", required=True)
    attest.add_argument("--repository", required=True)
    attest.add_argument("--base", required=True)
    attest.add_argument("--head", required=True)
    attest.add_argument("--diff-sha256", required=True)
    attest.add_argument("--cycle-stem", required=True)
    attest.add_argument("--risk", required=True)
    attest.add_argument("--reviewer", required=True)
    attest.add_argument("--nonce", default=None)
    attest.add_argument("--issued-at", type=int, default=None)
    attest.add_argument("--ttl", type=int, default=300)
    attest.set_defaults(func=_run_attest)

    gate = actions.add_parser("gate", help="권위 판정과 protected attestation 결속을 검증합니다")
    _add_inspection_args(gate)
    gate.add_argument("--attestation-file", required=True)
    gate.set_defaults(func=_run_gate)


def _add_inspection_args(parser: argparse.ArgumentParser):
    parser.add_argument("--root", default=".", help="base/head object가 존재하는 git repository")
    parser.add_argument("--base", required=True, help="full base commit SHA")
    parser.add_argument("--head", required=True, help="full head commit SHA")
    parser.add_argument("--repository", required=True, help="owner/name")
    parser.add_argument("--cycle-stem", required=True)
    parser.add_argument("--issuer", required=True, help="gate에서는 attestation expected issuer")


def _git(root: str, *args: str, max_output: int | None = None) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuthorityCliError(f"git command failed: {type(exc).__name__}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()[:400]
        raise AuthorityCliError(f"git {' '.join(args[:2])} rejected: {detail or completed.returncode}")
    if max_output is not None and len(completed.stdout) > max_output:
        raise AuthorityCliError(f"git object output exceeds {max_output} bytes")
    return completed.stdout


def _commit_sha(root: str, value: str, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise AuthorityCliError(f"{label} must be a full lowercase commit SHA")
    resolved = _git(root, "rev-parse", "--verify", f"{value}^{{commit}}", max_output=128)
    actual = resolved.decode("ascii", errors="strict").strip()
    if actual != value:
        raise AuthorityCliError(f"{label} does not resolve to the exact supplied commit")
    return actual


def _tree(root: str, sha: str) -> dict[str, dict[str, str]]:
    raw = _git(root, "ls-tree", "-r", "-z", "--full-tree", sha)
    entries = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            meta, path_raw = record.split(b"\t", 1)
            mode, kind, oid = meta.decode("ascii").split(" ", 2)
            path = path_raw.decode("utf-8", errors="surrogateescape")
        except (ValueError, UnicodeError) as exc:
            raise AuthorityCliError("malformed git ls-tree record") from exc
        if path in entries:
            raise AuthorityCliError(f"duplicate git tree path: {path!r}")
        entries[path] = {"mode": mode, "kind": kind, "oid": oid}
    return entries


def _blob(root: str, entry: dict[str, str] | None, *, label: str) -> bytes:
    if entry is None:
        return b""
    if entry.get("kind") != "blob":
        return b""
    oid = entry.get("oid") or ""
    if not _SHA_RE.fullmatch(oid):
        raise AuthorityCliError(f"invalid blob id for {label}")
    return _git(root, "cat-file", "blob", oid, max_output=_MAX_BLOB_BYTES)


def _text_blob(root: str, entry: dict[str, str] | None, *, label: str) -> str:
    raw = _blob(root, entry, label=label)
    return raw.decode("utf-8", errors="replace")


def _parse_name_status(raw: bytes) -> list[tuple[str, str, str]]:
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    changes = []
    index = 0
    while index < len(fields):
        status_raw = fields[index]
        index += 1
        try:
            status = status_raw.decode("ascii")
        except UnicodeError as exc:
            raise AuthorityCliError("malformed git diff status") from exc
        if not status:
            raise AuthorityCliError("empty git diff status")
        code = status[0]
        needed = 2 if code in ("R", "C") else 1
        if index + needed > len(fields):
            raise AuthorityCliError("truncated git diff name-status record")
        paths = [field.decode("utf-8", errors="surrogateescape")
                 for field in fields[index:index + needed]]
        index += needed
        if code == "A":
            changes.append(("add", "", paths[0]))
        elif code == "D":
            changes.append(("delete", paths[0], paths[0]))
        elif code in ("M", "T"):
            changes.append(("modify", paths[0], paths[0]))
        elif code == "R":
            changes.append(("rename", paths[0], paths[1]))
        elif code == "C":
            changes.append(("copy", paths[0], paths[1]))
        else:
            raise AuthorityCliError(f"unsupported git diff status: {status!r}")
        if len(changes) > _MAX_DIFF_CHANGES:
            raise AuthorityCliError(f"diff exceeds {_MAX_DIFF_CHANGES} changed paths")
    return changes


def _changes(root: str, base: str, head: str,
             base_tree: dict[str, dict[str, str]],
             head_tree: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    raw = _git(root, "diff", "--name-status", "-z", "-M", base, head)
    out = []
    for op, old_path, path in _parse_name_status(raw):
        effective_op = "add" if op == "copy" else op
        if op == "copy":
            old_path = ""
        base_entry = base_tree.get(old_path) if old_path else None
        head_entry = head_tree.get(path)
        required = []
        if effective_op in ("modify", "delete", "rename"):
            required.append(("base", old_path, base_entry))
        if effective_op in ("add", "modify", "rename"):
            required.append(("head", path, head_entry))
        for revision, required_path, entry in required:
            if entry is None or entry.get("kind") != "blob":
                raise AuthorityCliError(
                    f"changed {revision} object is missing or not a blob: {required_path!r}")
        out.append({
            "op": effective_op,
            "path": path,
            "old_path": old_path,
            "base_oid": (base_entry or {}).get("oid", ""),
            "head_oid": (head_entry or {}).get("oid", ""),
            "base_content": _text_blob(root, base_entry, label=f"base:{old_path}") if old_path else "",
            "head_content": _text_blob(root, head_entry, label=f"head:{path}") if effective_op != "delete" else "",
        })
    return out


def _profile(root: str, tree: dict[str, dict[str, str]], revision: str) -> dict[str, Any]:
    path = "sage/project-profile.yaml"
    entry = tree.get(path)
    if not _is_regular_blob(entry):
        raise AuthorityCliError(f"{revision} profile is missing or not a regular git file: {path}")
    raw = _blob(root, entry, label=f"{revision}:{path}")
    try:
        profile = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise AuthorityCliError(f"{revision} profile YAML is invalid: {exc}") from exc
    try:
        import jsonschema  # noqa: F401 - authority requires the schema extra, never WARN-only fallback
    except ImportError as exc:
        raise AuthorityCliError("protected authority requires the SAGE schema dependency") from exc
    issues = validate_profile(profile, _resources.sage_root())
    if severity_of(issues) == "FAIL":
        failures = [message for severity, message in issues if severity == "FAIL"]
        raise AuthorityCliError(f"{revision} profile validation failed: {'; '.join(failures[:4])}")
    try:
        return materialize_profile(profile)
    except ProfileCompileError as exc:
        raise AuthorityCliError(f"{revision} profile materialization failed: {exc}") from exc


def _phase_globs(profile: dict[str, Any]) -> dict[str, set[str]]:
    result = {phase: set() for phase in _PHASE_IDS}
    pdca = profile.get("pdca") if isinstance(profile, dict) else None
    phases = pdca.get("phases") if isinstance(pdca, dict) else None
    for item in phases if isinstance(phases, list) else []:
        if not isinstance(item, dict):
            continue
        phase = str(item.get("id") or "")
        pattern = item.get("glob")
        if phase in result and isinstance(pattern, str) and pattern:
            result[phase].add(pattern)
    return result


def _phase_docs(root: str, head_tree: dict[str, dict[str, str]],
                base_profile: dict[str, Any], head_profile: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    _, cycle_binding = ci_authority._trusted_gate_modules()
    patterns = _phase_globs(base_profile)
    for phase, values in _phase_globs(head_profile).items():
        patterns[phase].update(values)
    docs = {phase: [] for phase in _PHASE_IDS}
    count = 0
    for path, entry in head_tree.items():
        matched = [phase for phase in _PHASE_IDS
                   if any(cycle_binding.matches_glob(path, pattern) for pattern in patterns[phase])]
        if not matched:
            continue
        if not _is_regular_blob(entry):
            raise AuthorityCliError(f"phase evidence is not a regular git file: {path}")
        content = _text_blob(root, entry, label=f"head:{path}")
        for phase in matched:
            docs[phase].append({"path": path, "content": content})
            count += 1
            if count > _MAX_PHASE_DOCS:
                raise AuthorityCliError(f"phase evidence exceeds {_MAX_PHASE_DOCS} matched documents")
    return docs


def _request(args) -> dict[str, Any]:
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        raise AuthorityCliError(f"git root is not a directory: {root}")
    base = _commit_sha(root, args.base, "base")
    head = _commit_sha(root, args.head, "head")
    base_tree = _tree(root, base)
    head_tree = _tree(root, head)
    base_profile = _profile(root, base_tree, "base")
    head_profile = _profile(root, head_tree, "head")
    return {
        "base_profile": base_profile,
        "head_profile": head_profile,
        "changes": _changes(root, base, head, base_tree, head_tree),
        "phase_docs": _phase_docs(root, head_tree, base_profile, head_profile),
        "cycle_stem": args.cycle_stem,
        "repository": args.repository,
        "base_sha": base,
        "head_sha": head,
        "expected_issuer": args.issuer,
    }


def _key() -> bytes:
    value = os.environ.get("SAGE_ATTESTATION_KEY")
    if value is None:
        raise AuthorityCliError("SAGE_ATTESTATION_KEY protected secret is unavailable")
    key = value.encode("utf-8")
    if len(key) < 32:
        raise AuthorityCliError("SAGE_ATTESTATION_KEY must contain at least 32 bytes")
    return key


def _token(path_value: str) -> str:
    path = Path(path_value)
    try:
        info = path.lstat()
    except OSError as exc:
        raise AuthorityCliError(f"attestation file cannot be read: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise AuthorityCliError("attestation file must be a non-symlink regular file")
    if info.st_size > _MAX_TOKEN_BYTES:
        raise AuthorityCliError("attestation file is oversized")
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise AuthorityCliError(f"attestation file cannot be decoded: {exc}") from exc


def _print_result(result: dict[str, Any]) -> int:
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    return int(result.get("exit_code", 2))


def _run_inspect(args) -> int:
    try:
        return _print_result(ci_authority.analyze(_request(args)))
    except (AuthorityCliError, ci_authority.AuthorityError, OSError, ValueError) as exc:
        return _print_result({"status": "BLOCK", "exit_code": 2, "risk": "unknown",
                              "reasons": [f"authority adapter rejected input: {exc}"]})


def _run_attest(args) -> int:
    issued_at = int(time.time()) if args.issued_at is None else args.issued_at
    claims = {
        "version": ci_authority.ATTESTATION_VERSION,
        "issuer": args.issuer,
        "repository": args.repository,
        "base_sha": args.base,
        "head_sha": args.head,
        "diff_sha256": args.diff_sha256,
        "cycle_stem": args.cycle_stem,
        "risk": args.risk,
        "reviewer": args.reviewer,
        "verdict": "APPROVED",
        "nonce": args.nonce or secrets.token_urlsafe(24),
        "issued_at": issued_at,
        "expires_at": issued_at + args.ttl,
    }
    try:
        print(ci_authority.issue_attestation(claims, _key()))
        return 0
    except (AuthorityCliError, ci_authority.AuthorityError, OSError, ValueError) as exc:
        print(f"[sage authority] attestation rejected: {exc}", file=sys.stderr)
        return 2


def _run_gate(args) -> int:
    try:
        request = _request(args)
        request["attestation_token"] = _token(args.attestation_file)
        request["attestation_key"] = _key()
        return _print_result(ci_authority.evaluate(request))
    except (AuthorityCliError, ci_authority.AuthorityError, OSError, ValueError) as exc:
        return _print_result({"status": "BLOCK", "exit_code": 2, "risk": "unknown",
                              "reasons": [f"authority adapter rejected input: {exc}"]})
