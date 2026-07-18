"""Pure server-side authority decision and HMAC attestation primitives.

The caller supplies already-materialized git data. This module never invokes git,
executes project code, or reads local SAGE override/waiver audit files.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import json
import os
import posixpath
import re
import sys
import time
from typing import Any, Callable

from sage import _resources

ATTESTATION_VERSION = 1
MAX_ATTESTATION_TTL = 3600
MAX_TOKEN_BYTES = 16384
_RISKS = ("none", "L0", "L1", "L2", "L3", "DESKTOP_BLOCK")
_RANK = {risk: rank for rank, risk in enumerate(_RISKS)}
_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_.:-]{16,160}$")


class AuthorityError(ValueError):
    """Fail-closed authority contract violation."""


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise AuthorityError("invalid base64url segment")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, UnicodeError) as exc:
        raise AuthorityError("invalid base64url encoding") from exc


def _strict_object(raw: bytes) -> dict[str, Any]:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise AuthorityError(f"duplicate JSON claim: {key}")
            out[key] = value
        return out

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except AuthorityError:
        raise
    except (UnicodeError, ValueError) as exc:
        raise AuthorityError("attestation payload is not canonical JSON data") from exc
    if not isinstance(value, dict):
        raise AuthorityError("attestation payload must be an object")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _clean_claims(claims: dict[str, Any]) -> dict[str, Any]:
    required = {
        "version", "issuer", "repository", "base_sha", "head_sha", "diff_sha256",
        "cycle_stem", "risk", "reviewer", "verdict", "nonce", "issued_at", "expires_at",
    }
    if not isinstance(claims, dict) or set(claims) != required:
        missing = sorted(required - set(claims or {})) if isinstance(claims, dict) else sorted(required)
        extra = sorted(set(claims or {}) - required) if isinstance(claims, dict) else []
        raise AuthorityError(f"attestation claims mismatch: missing={missing}, extra={extra}")
    string_fields = ("issuer", "repository", "base_sha", "head_sha", "diff_sha256",
                     "cycle_stem", "risk", "reviewer", "verdict", "nonce")
    for field in string_fields:
        if not isinstance(claims[field], str) or not claims[field].strip():
            raise AuthorityError(f"claim {field} must be a non-empty string")
    if claims["version"] != ATTESTATION_VERSION:
        raise AuthorityError("unsupported attestation version")
    if not _REPOSITORY_RE.fullmatch(claims["repository"]):
        raise AuthorityError("repository must be owner/name")
    for field, limit in (("issuer", 200), ("reviewer", 200), ("cycle_stem", 160)):
        value = claims[field]
        if len(value) > limit or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise AuthorityError(f"claim {field} contains unsafe or oversized text")
    if "/" in claims["cycle_stem"] or "\\" in claims["cycle_stem"]:
        raise AuthorityError("claim cycle_stem must be a single safe path stem")
    if not _SHA_RE.fullmatch(claims["base_sha"]) or not _SHA_RE.fullmatch(claims["head_sha"]):
        raise AuthorityError("base_sha/head_sha must be full git object ids")
    if not _DIGEST_RE.fullmatch(claims["diff_sha256"]):
        raise AuthorityError("diff_sha256 must be 64 lowercase hex")
    if claims["risk"] not in _RANK:
        raise AuthorityError(f"unsupported risk: {claims['risk']!r}")
    if claims["verdict"] != "APPROVED":
        raise AuthorityError("attestation verdict must be APPROVED")
    if not _NONCE_RE.fullmatch(claims["nonce"]):
        raise AuthorityError("nonce must be 16-160 safe characters")
    if (not isinstance(claims["issued_at"], int)
            or isinstance(claims["issued_at"], bool)
            or not isinstance(claims["expires_at"], int)
            or isinstance(claims["expires_at"], bool)):
        raise AuthorityError("issued_at/expires_at must be integer epoch seconds")
    ttl = claims["expires_at"] - claims["issued_at"]
    if ttl <= 0 or ttl > MAX_ATTESTATION_TTL:
        raise AuthorityError("attestation TTL must be positive and at most one hour")
    return dict(claims)


def issue_attestation(claims: dict[str, Any], key: bytes) -> str:
    """Sign exact claims with HMAC-SHA256. Intended for a protected CI issuer."""
    if not isinstance(key, bytes) or len(key) < 32:
        raise AuthorityError("attestation key must contain at least 32 bytes")
    clean = _clean_claims(claims)
    payload = _b64_encode(_canonical(clean))
    signature = hmac.new(key, payload.encode("ascii"), hashlib.sha256).digest()
    token = payload + "." + _b64_encode(signature)
    if len(token.encode("utf-8")) > MAX_TOKEN_BYTES:
        raise AuthorityError("attestation token is oversized")
    return token


def verify_attestation(token: str, key: bytes, expected: dict[str, Any], now: int | None = None,
                       clock_skew: int = 30) -> dict[str, Any]:
    """Verify signature, exact protected bindings, time window, and canonical payload."""
    if not isinstance(key, bytes) or len(key) < 32:
        raise AuthorityError("protected attestation key is unavailable or too short")
    if not isinstance(token, str) or len(token.encode("utf-8", errors="ignore")) > MAX_TOKEN_BYTES:
        raise AuthorityError("attestation token is missing or oversized")
    parts = token.strip().split(".")
    if len(parts) != 2:
        raise AuthorityError("attestation token must have payload.signature")
    payload_segment, signature_segment = parts
    supplied = _b64_decode(signature_segment)
    calculated = hmac.new(key, payload_segment.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(supplied, calculated):
        raise AuthorityError("attestation signature mismatch")
    payload_raw = _b64_decode(payload_segment)
    claims = _clean_claims(_strict_object(payload_raw))
    if _canonical(claims) != payload_raw:
        raise AuthorityError("attestation payload must use canonical JSON serialization")
    allowed_expected = {"issuer", "repository", "base_sha", "head_sha", "diff_sha256",
                        "cycle_stem", "risk", "verdict"}
    unknown = sorted(set(expected or {}) - allowed_expected)
    if unknown:
        raise AuthorityError(f"unsupported expected claims: {unknown}")
    for field, value in (expected or {}).items():
        if claims.get(field) != value:
            raise AuthorityError(f"attestation {field} binding mismatch")
    current = int(time.time()) if now is None else int(now)
    if claims["issued_at"] > current + clock_skew:
        raise AuthorityError("attestation issued_at is in the future")
    if claims["expires_at"] < current - clock_skew:
        raise AuthorityError("attestation expired")
    return claims


def _trusted_gate_modules():
    hooks = _resources.hooks_src_dir()
    runtime = os.path.join(hooks, "runtime")
    for path in (hooks, runtime):
        if path not in sys.path:
            sys.path.insert(0, path)
    return importlib.import_module("pre_implementation_gate_core"), importlib.import_module("cycle_binding")


def diff_digest(changes: list[dict[str, Any]]) -> str:
    """Digest the structured diff including paths, blob ids, and actual content hashes."""
    rows = []
    for change in changes or []:
        if not isinstance(change, dict):
            raise AuthorityError("every change must be an object")
        row = {}
        op = change.get("op") or ""
        if op not in ("add", "modify", "delete", "rename"):
            raise AuthorityError(f"unsupported structured change op: {op!r}")
        for field in ("op", "path", "old_path", "base_oid", "head_oid"):
            value = change.get(field) or ""
            if not isinstance(value, str):
                raise AuthorityError(f"change.{field} must be a string")
            row[field] = value
        if not row["path"] or "\x00" in row["path"]:
            raise AuthorityError("change.path must be a non-empty git path")
        for field in ("path", "old_path"):
            value = row[field]
            if value and (value.startswith("/") or posixpath.normpath(value) != value
                          or any(part in ("", ".", "..") for part in value.split("/"))):
                raise AuthorityError(f"change.{field} must be a canonical repository-relative path")
        for field in ("base_oid", "head_oid"):
            if row[field] and not _SHA_RE.fullmatch(row[field]):
                raise AuthorityError(f"change.{field} must be a full git object id")
        for field in ("base_content", "head_content"):
            value = change.get(field) or ""
            if not isinstance(value, str):
                raise AuthorityError(f"change.{field} must be text")
            row[field + "_sha256"] = hashlib.sha256(value.encode("utf-8")).hexdigest()
        if op == "add" and (row["old_path"] or row["base_oid"] or change.get("base_content")):
            raise AuthorityError("add change must not claim a base object")
        if op == "delete" and (not row["base_oid"] or row["head_oid"] or change.get("head_content")):
            raise AuthorityError("delete change must bind only a base object")
        if op == "modify" and (not row["base_oid"] or not row["head_oid"]
                               or row["old_path"] not in ("", row["path"])):
            raise AuthorityError("modify change must bind base/head objects at one path")
        if op == "rename" and (not row["old_path"] or row["old_path"] == row["path"]
                               or not row["base_oid"] or not row["head_oid"]):
            raise AuthorityError("rename change must bind distinct source/destination objects")
        rows.append(row)
    rows.sort(key=lambda row: (row["path"], row["old_path"], row["op"]))
    return hashlib.sha256(_canonical(rows)).hexdigest()


def _classification_changes(changes: list[dict[str, Any]]) -> list[dict[str, str]]:
    expanded = []
    for change in changes or []:
        op = change.get("op") or ""
        path = change.get("path") or ""
        old_path = change.get("old_path") or path
        base = change.get("base_content") or ""
        head = change.get("head_content") or ""
        if op in ("delete", "rename") and old_path:
            expanded.append({"path": old_path, "op": "delete" if op == "delete" else "rename-source",
                             "content": base, "removed_content": base, "full_content": True})
        if op == "modify" and path:
            expanded.append({"path": path, "op": "modify-base", "content": base,
                             "removed_content": base, "full_content": True})
        if op != "delete" and path:
            expanded.append({"path": path, "op": "add" if op == "add" else op,
                             "content": head, "removed_content": base, "full_content": True})
    return expanded


def _classify(profile: dict[str, Any], changes: list[dict[str, Any]], classifier: Callable | None):
    if not isinstance(profile, dict):
        raise AuthorityError("base/head profile must be an object")
    core, _ = _trusted_gate_modules()
    fn = classifier or core.classify_risk
    try:
        result = fn({"changes": _classification_changes(changes), "declared_max": None}, profile)
    except Exception as exc:
        raise AuthorityError(f"risk classifier failed closed: {type(exc).__name__}: {exc}") from exc
    risk = result.get("risk") if isinstance(result, dict) else None
    if risk not in _RANK:
        raise AuthorityError(f"classifier returned invalid risk: {risk!r}")
    return result


def _selected_phases(phase_docs: dict[str, Any], cycle_stem: str, cycle_binding):
    selected, errors = {}, []
    for phase in ("00", "01", "02", "03", "04", "05"):
        docs = phase_docs.get(phase) if isinstance(phase_docs, dict) else None
        doc, error = cycle_binding.select_document(docs or [], cycle_stem)
        if error:
            errors.append(f"Phase {phase}: {error}")
        else:
            selected[phase] = doc
    return selected, errors


def _declared_risk(selected: dict[str, dict[str, Any]], cycle_binding, core):
    found = []
    for doc in selected.values():
        for line in cycle_binding.non_fenced_lines(doc.get("content") or ""):
            parsed = core._parse_risk_declaration(line)
            if parsed is None:
                continue
            if parsed == "unknown":
                return "unknown"
            found.append(parsed)
    return max(found, key=_RANK.get) if found else None


def _acceptance_evidence(selected: dict[str, dict[str, Any]], core):
    matrix = core._acceptance_matrix(selected["01"].get("content") or "")
    if matrix.get("invalid") or matrix.get("duplicates") or not matrix.get("all"):
        return ["Phase 01 acceptance matrix is missing, malformed, or duplicated"]
    rows = core._acceptance_evidence_rows(selected["04"].get("content") or "")
    by_id = {}
    errors = []
    for row in rows:
        rid = row.get("id") or ""
        if not rid or rid in by_id:
            errors.append(f"Phase 04 duplicate/invalid acceptance ID: {rid or '<missing>'}")
            continue
        by_id[rid] = row
    for rid in matrix.get("required") or []:
        row = by_id.get(rid)
        if not row:
            errors.append(f"Phase 04 missing required acceptance ID: {rid}")
            continue
        status = (row.get("status") or "").upper()
        if status == "PASS":
            continue
        if status == "N/A" and core._has_na_reason(row.get("reason")):
            continue
        errors.append(f"server authority unresolved acceptance: {rid}={status or '<missing>'}")
    unknown = sorted(set(by_id) - set(matrix.get("all") or []))
    if unknown:
        errors.append(f"Phase 04 contains unknown acceptance IDs: {unknown}")
    return errors


def analyze(request: dict[str, Any], classifier: Callable | None = None) -> dict[str, Any]:
    """Pure deterministic diff, policy, and current-cycle evidence analysis."""
    reasons = []
    if not isinstance(request, dict):
        return {"status": "BLOCK", "exit_code": 2, "risk": "unknown",
                "reasons": ["authority request must be an object"]}
    changes = request.get("changes")
    if not isinstance(changes, list) or not changes:
        reasons.append("structured base/head diff is missing")
        changes = []
    try:
        digest = diff_digest(changes)
        base_result = _classify(request.get("base_profile"), changes, classifier)
        head_result = _classify(request.get("head_profile"), changes, classifier)
    except AuthorityError as exc:
        return {"status": "BLOCK", "exit_code": 2, "risk": "unknown", "diff_sha256": "",
                "reasons": [str(exc)]}
    risk = max((base_result["risk"], head_result["risk"]), key=_RANK.get)
    selected = {}
    if risk == "DESKTOP_BLOCK":
        reasons.append("desktop/generated protected path changed")
    core, cycle_binding = _trusted_gate_modules()
    cycle_stem = cycle_binding.normalize_stem(request.get("cycle_stem"))
    if cycle_stem is None:
        reasons.append("explicit safe cycle_stem is required")
    else:
        selected, phase_errors = _selected_phases(request.get("phase_docs") or {}, cycle_stem, cycle_binding)
        try:
            declared = _declared_risk(selected, cycle_binding, core)
            if declared == "unknown":
                risk = "L3"
            elif declared and _RANK[declared] > _RANK[risk]:
                risk = declared
        except AuthorityError as exc:
            reasons.append(str(exc))
        if risk in ("L2", "L3"):
            reasons.extend(phase_errors)
        if not phase_errors:
            if risk == "L3":
                status, error = core._final_status(selected["05"].get("content") or "")
                if error or status != "APPROVED":
                    reasons.append(f"Phase 05 is not exactly APPROVED: {error or status}")
                reasons.extend(_acceptance_evidence(selected, core))
    return {
        "status": "BLOCK" if reasons else "PASS",
        "exit_code": 2 if reasons else 0,
        "risk": risk,
        "base_risk": base_result["risk"],
        "head_risk": head_result["risk"],
        "diff_sha256": digest,
        "cycle_stem": cycle_stem,
        "selected_phases": {phase: doc.get("path") for phase, doc in selected.items()},
        "reasons": reasons,
    }


def evaluate(request: dict[str, Any], classifier: Callable | None = None) -> dict[str, Any]:
    """Analyze and require a protected attestation exactly bound to this diff."""
    result = analyze(request, classifier=classifier)
    if result["status"] != "PASS":
        return result
    expected = {
        "issuer": request.get("expected_issuer"),
        "repository": request.get("repository"),
        "base_sha": request.get("base_sha"),
        "head_sha": request.get("head_sha"),
        "diff_sha256": result["diff_sha256"],
        "cycle_stem": result["cycle_stem"],
        "risk": result["risk"],
        "verdict": "APPROVED",
    }
    try:
        claims = verify_attestation(request.get("attestation_token") or "",
                                    request.get("attestation_key") or b"",
                                    expected, now=request.get("now"))
    except (AuthorityError, TypeError, ValueError) as exc:
        result.update(status="BLOCK", exit_code=2,
                      reasons=[*result.get("reasons", []), f"attestation rejected: {exc}"])
        return result
    result["attestation"] = {key: claims[key] for key in (
        "issuer", "reviewer", "nonce", "issued_at", "expires_at")}
    return result
