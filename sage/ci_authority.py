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
# 사이클 선언으로 인정하는 tier. `_RANK` 는 분류 결과(none/L0/DESKTOP_BLOCK 포함)까지 담는 넓은
# 집합이라 선언 검증에 그대로 쓰면 `Risk Level: L0` 이 정상 선언으로 통과한다.
_CYCLE_TIERS = ("L1", "L2", "L3")
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
    return (importlib.import_module("pre_implementation_gate_core"),
            importlib.import_module("cycle_binding"),
            importlib.import_module("risk_declaration"))


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
    core, _binding, _risk = _trusted_gate_modules()
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


def _expand_fast_phase_docs(phase_docs: dict[str, Any]):
    """Project composite 00 documents into virtual 01..04 using the shared parser."""
    expanded = {phase: list(docs or []) for phase, docs in (phase_docs or {}).items()}
    for phase in ("00", "01", "02", "03", "04", "05"):
        expanded.setdefault(phase, [])
    issues = []
    try:
        from sage.fast_cycle_contract import parse_fast_plan
        for doc in list(expanded["00"]):
            plan, parse_issues = parse_fast_plan(doc.get("content") or "")
            if plan is None or plan.metadata.get("Cycle-Mode") != "FAST":
                continue
            if parse_issues:
                issues.extend(f"Fast composite: {issue}" for issue in parse_issues)
                continue
            header = (f"Cycle-Stem: `{plan.metadata.get('Cycle-Stem', '')}`\n"
                      f"Risk Level: {plan.metadata.get('Risk Level', '')}\n")
            for phase in ("01", "02", "03", "04"):
                expanded[phase].append({
                    "path": doc.get("path"),
                    "content": header + plan.sections.get(phase, ""),
                    "virtual_fast": True,
                })
    except Exception as exc:
        issues.append(f"Fast composite parser failure: {type(exc).__name__}: {exc}")
    return expanded, issues


CONVERTED_ENTRY_MODE = "FAST-CONVERTED"


def _converted_fast_run(fast_records, cycle_stem):
    """이 stem 의 살아있는 전환 run id 와, 정할 수 없을 때의 사유. `(run_id, issue)`.

    전환 run 은 문서에 `Fast-Audit-Run` 을 남기지 않으므로(설계상 문서를 건드리지 않는다) 결속
    수단이 stem 하나뿐이다. 그래서 두 경우를 갈라야 한다:

    - **중단된 전환**은 후보에서 뺀다. abort 는 전환을 취소하는 정규 수단이고, 취소된 뒤 그 사이클은
      Standard 로 완주한다. 남겨두면 정상 취소가 영구 차단이 되고, 유일한 해소책이 다시 전환하는
      것(= 후보 둘)이 된다.
    - **후보가 둘 이상**이면 어느 쪽 증거인지 정할 수 없다. 이때 조용히 결속을 포기하면 검증이
      통째로 꺼지므로, 사유를 돌려 호출부가 fail-closed 하게 한다. run 단위로 도는 감사 무결성
      검사는 서로 다른 run 이 같은 stem 을 쓰는 상태를 보지 못한다.

    entry_mode 는 레코드 필드가 아니라 event 이름에서 파생하므로 위조할 자리가 없다.
    """
    aborted = {record.get("run_id") for record in fast_records
               if record.get("event") == "fast_abort"}
    candidates = {record.get("run_id") for record in fast_records
                  if record.get("event") == "fast_convert"
                  and record.get("cycle_stem") == cycle_stem
                  and isinstance(record.get("run_id"), str)} - aborted
    if not candidates:
        return None, None
    if len(candidates) > 1:
        return None, (f"cycle stem {cycle_stem!r} has {len(candidates)} live converted Fast runs; "
                      "the authority cannot tell which one the evidence belongs to")
    return candidates.pop(), None


def _fast_evidence_reasons(request, selected, cycle_stem):
    """Verify committed Fast and Loop audit evidence against the selected plan/review."""
    plan_doc = selected.get("00") if isinstance(selected, dict) else None
    review_doc = selected.get("05") if isinstance(selected, dict) else None
    if not plan_doc:
        return ["Fast authority requires selected Phase 00"]
    from sage.fast_cycle_contract import evidence_marker_issues, parse_fast_plan
    plan, plan_issues = parse_fast_plan(plan_doc.get("content") or "")
    composite = plan is not None and plan.metadata.get("Cycle-Mode") == "FAST"
    _trusted_gate_modules()  # inserts the trusted runtime directory
    import loop_audit
    try:
        fast_raw = request.get("fast_cycle_audit")
        loop_raw = request.get("loop_audit")
        raw_present = isinstance(fast_raw, str) and isinstance(loop_raw, str)
        fast_records, fast_file_issues = (
            loop_audit._parse_bytes(fast_raw.encode("utf-8")) if raw_present else ([], []))
        loop_records, loop_file_issues = (
            loop_audit._parse_bytes(loop_raw.encode("utf-8")) if raw_present else ([], []))
    except Exception as exc:
        return [f"audit parse failed closed: {type(exc).__name__}: {exc}"]

    # 전환 run 은 Phase 00 이 Standard 문서라 `Cycle-Mode: FAST` 가 없다. 여기서 composite 여부만
    # 보고 빠져나가면 전환 run 은 Fast 증거가 **하나도** 검증되지 않은 채 표준 경로로 통과한다 —
    # 실제로 수행된 리뷰는 축약된 Fast 인데, 그 깊이를 확인하는 층이 사라진다.
    converted_run, converted_issue = (
        (None, None) if composite else _converted_fast_run(fast_records, cycle_stem))
    if not composite and converted_run is None:
        # 전환 run 의 Fast 성은 문서가 아니라 감사에만 있다. 감사를 커밋하지 않으면(`.gitignore`
        # 한 줄이면 된다) 여기서 평범한 Standard 로 통과한다. 그래서 커밋 트리에 남는 다른 신호를
        # 본다 — `fast-cycle review` 가 Phase 05 에 강제한 `Fast-Run:` 표기다. 그 표기가 있는데
        # 감사가 뒷받침하지 못하면 증거 부재이지 Standard 사이클이 아니다.
        core = _trusted_gate_modules()[0]
        declared = (core._marker_values(review_doc.get("content") or "", "Fast-Run")
                    if isinstance(review_doc, dict) else [])
        if converted_issue:
            return [f"Fast authority: {converted_issue}"]
        if declared:
            return ["Phase 05 declares a Fast run but no committed Fast audit corroborates it: "
                    f"{declared}"]
        return []
    reasons = [f"Fast composite: {issue}" for issue in plan_issues] if composite else []
    if not review_doc:
        reasons.append("Fast authority requires selected Phase 05")
        return reasons
    if not raw_present:
        return reasons + ["committed Fast and Loop audit text is required"]
    reasons.extend(f"Fast audit: {issue}" for issue in fast_file_issues)
    reasons.extend(f"Loop audit: {issue}" for issue in loop_file_issues)

    fast_run = plan.metadata.get("Fast-Audit-Run") if composite else converted_run
    fast = [record for record in fast_records if record.get("run_id") == fast_run]
    fast_events = [record.get("event") for record in fast]
    opener_event = "fast_open" if composite else "fast_convert"
    if (fast_events.count(opener_event) != 1 or fast_events.count("fast_close") != 1
            or fast_events.count("fast_abort") != 0 or fast_events.count("fast_review") < 1
            or fast_events[-1:] != ["fast_close"]):
        reasons.append(f"Fast run {fast_run!r} is not clean terminal APPROVED evidence")
        return reasons
    if loop_audit._chain_states(fast_records).get(fast_run) is not True:
        reasons.append(f"Fast run {fast_run!r} strict hash-chain is invalid or legacy")
    if loop_audit._seq_ok([record.get("seq") for record in fast]) is not True:
        reasons.append(f"Fast run {fast_run!r} seq is not strict and continuous")
    opened = next(record for record in fast if record.get("event") == opener_event)
    reviewed = [record for record in fast if record.get("event") == "fast_review"][-1]
    closed = fast[-1]
    plan_hash = hashlib.sha256((plan_doc.get("content") or "").encode("utf-8")).hexdigest()
    # composite 은 문서가 stem 을 따로 선언하므로 대조 대상이 둘이다. 전환 run 은 문서에 선언이
    # 없고 opener 자체를 stem 으로 뽑았으므로, 여기서 다시 비교할 독립 축이 없다.
    if opened.get("cycle_stem") != cycle_stem or (
            composite and plan.metadata.get("Cycle-Stem") != cycle_stem):
        reasons.append("Fast run/plan cycle stem does not match authority stem")
    # 전환 run 의 위험도 정본은 Standard Phase 00 의 선언이다 — 공용 파서 하나만 읽는다.
    declared_risk = (plan.metadata.get("Risk Level") if composite
                     else _declared_risk({"00": plan_doc}, _trusted_gate_modules()[2]))
    if opened.get("actual_risk_open") != declared_risk:
        reasons.append("Fast open actual risk does not match Phase 00")
    if (reviewed.get("result") != "APPROVED" or closed.get("result") != "APPROVED"
            or reviewed.get("plan_hash_before_review") != plan_hash
            or closed.get("plan_hash_final") != plan_hash):
        reasons.append("Fast review/close result or plan hash binding is invalid")
    loop_run = reviewed.get("loop_run_id")
    if closed.get("loop_run_id") != loop_run:
        reasons.append("Fast close references a different Loop run")
    review_text = review_doc.get("content") or ""
    reasons.extend(
        f"Phase 05 Fast evidence marker invalid: {issue}"
        for issue in evidence_marker_issues(
            review_text, fast_run_id=fast_run, loop_run_id=loop_run))

    loop = [record for record in loop_records if record.get("run_id") == loop_run]
    loop_events = [record.get("event") for record in loop]
    if loop_events.count("loop_open") != 1 or loop_events.count("loop_close") != 1 or loop_events[-1:] != ["loop_close"]:
        reasons.append(f"Loop run {loop_run!r} is not clean and closed")
        return reasons
    if loop_audit._chain_states(loop_records).get(loop_run) is not True:
        reasons.append(f"Loop run {loop_run!r} strict hash-chain is invalid or legacy")
    if loop_audit._seq_ok([record.get("seq") for record in loop]) is not True:
        reasons.append(f"Loop run {loop_run!r} seq is not strict and continuous")
    loop_open = next(record for record in loop if record.get("event") == "loop_open")
    loop_close = loop[-1]
    rounds = [record for record in loop if record.get("event") == "round"]
    lenses = opened.get("lenses") or []
    if (loop_open.get("cycle_stem") != cycle_stem or loop_open.get("lenses") != lenses
            or loop_close.get("result") != "APPROVED"):
        reasons.append("Loop run stem/lenses/result does not match Fast open")
    if len(rounds) < int(opened.get("minimum_rounds") or 0) or reviewed.get("rounds") != len(rounds):
        reasons.append("Loop round count does not satisfy Fast minimum/review receipt")
    if any(record.get("lens_receipts") != lenses for record in rounds):
        reasons.append("one or more Loop rounds lack exact selected lens receipts")
    receipts_payload = json.dumps(
        [{"iteration": record.get("iteration"), "lenses": record.get("lens_receipts")} for record in rounds],
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    receipts_hash = hashlib.sha256(receipts_payload.encode("utf-8")).hexdigest()
    if reviewed.get("lens_receipts_hash") != receipts_hash:
        reasons.append("Fast review lens receipt hash does not match Loop rounds")
    requested = loop_open.get("reviewer_requested")
    actual = loop_close.get("reviewer_actual")
    if requested is not None and actual != requested:
        reasons.append("Loop reviewer is degraded or unproven")
    return reasons


def _done_criteria_evidence(request, selected, cycle_stem, profile):
    """Return blocking reasons and advisory diagnostics for the selected Phase 00."""
    pdca = profile.get("pdca") if isinstance(profile, dict) else None
    base_plan = pdca.get("base_plan") if isinstance(pdca, dict) else None
    mode = base_plan.get("done_criteria_gate", "off") if isinstance(base_plan, dict) else "off"
    if mode == "off":
        return [], []
    if mode not in ("advisory", "enforce"):
        return [f"invalid pdca.base_plan.done_criteria_gate={mode!r}"], []

    diagnostics = []
    plan_doc = selected.get("00") if isinstance(selected, dict) else None
    if not plan_doc:
        diagnostics.append("Done Criteria authority requires selected Phase 00")
    else:
        from sage.done_criteria_contract import (
            document_revision,
            parse_done_criteria,
            phase00_text_hash,
        )
        content = plan_doc.get("content") or ""
        parse_mode = "fast" if re.search(r"(?m)^Cycle-Mode:\s*FAST\s*$", content) else "standard"
        result = parse_done_criteria(content, mode=parse_mode)
        diagnostics.extend(f"Phase 00 Done Criteria: {issue}" for issue in result.issues)
        diagnostics.extend(
            f"Phase 00 Done Criteria unresolved at line {item.line}: {item.text}"
            for item in result.unresolved
        )

        if result.status == "valid" and parse_mode == "standard":
            if result.latest_revision is not None:
                for phase in result.latest_revision.affected_phases:
                    phase_doc = selected.get(phase)
                    if not phase_doc:
                        diagnostics.append(f"affected Phase {phase} is missing for revision {result.revision}")
                        continue
                    revision, revision_issues = document_revision(phase_doc.get("content"))
                    if revision_issues or revision != result.revision:
                        diagnostics.append(
                            f"affected Phase {phase} revision={revision!r}, expected={result.revision}")

            review_doc = selected.get("05")
            review_text = (review_doc or {}).get("content") or ""
            core, _cycle_binding, _risk = _trusted_gate_modules()
            final_status, status_error = core._final_status(review_text)
            marker = str(pdca.get("approve_marker") or "APPROVED").upper()
            if status_error or final_status != marker:
                diagnostics.append(
                    f"Phase 05 is not exactly {marker}: {status_error or final_status}")
            hash_values = []
            run_ids = []
            for raw in core._non_fenced_lines(review_text):
                line = core._structured_declaration_line(raw)
                hash_match = re.fullmatch(
                    r"Phase00-Hash:\s*(sha256:[0-9a-f]{64})", line)
                run_match = re.fullmatch(r"Loop-Run:\s*(\S+)", line, re.IGNORECASE)
                if hash_match:
                    hash_values.append(hash_match.group(1))
                if run_match:
                    run_ids.append(run_match.group(1))
            current_hash = phase00_text_hash(content)
            if len(hash_values) != 1 or hash_values[0] != current_hash:
                diagnostics.append(
                    f"Phase 05 Phase00-Hash does not bind current Phase 00: "
                    f"current={current_hash}, declared={hash_values}")
            if len(run_ids) != 1:
                diagnostics.append(
                    f"Phase 05 Loop-Run must appear exactly once for Done Criteria authority; "
                    f"found={len(run_ids)}")
            else:
                _trusted_gate_modules()
                import loop_audit
                try:
                    raw = request.get("loop_audit")
                    if not isinstance(raw, str):
                        raise ValueError("committed Loop audit text is required")
                    records, file_issues = loop_audit._parse_bytes(raw.encode("utf-8"))
                except Exception as exc:
                    diagnostics.append(
                        f"Loop audit parse failed closed: {type(exc).__name__}: {exc}")
                else:
                    diagnostics.extend(f"Loop audit: {issue}" for issue in file_issues)
                    run_id = run_ids[0]
                    run = [record for record in records if record.get("run_id") == run_id]
                    events = [record.get("event") for record in run]
                    close = run[-1] if run else {}
                    if (events.count("loop_open") != 1 or events.count("loop_close") != 1
                            or events[-1:] != ["loop_close"]):
                        diagnostics.append(f"Loop run {run_id!r} is not uniquely open/closed")
                    elif (loop_audit._chain_states(records).get(run_id) is not True
                          or loop_audit._seq_ok([record.get("seq") for record in run]) is not True):
                        diagnostics.append(f"Loop run {run_id!r} lacks strict chain/sequence integrity")
                    else:
                        opened = next(record for record in run if record.get("event") == "loop_open")
                        if (opened.get("cycle_stem") != cycle_stem
                                or close.get("result") != "APPROVED"
                                or close.get("phase00_hash") != current_hash):
                            diagnostics.append(
                                f"Loop run {run_id!r} does not bind cycle/result/current Phase 00 hash")

    return (diagnostics, []) if mode == "enforce" else ([], diagnostics)


def _declared_risk(selected: dict[str, dict[str, Any]], risk_declaration):
    """선택된 phase 문서들의 선언 최대 tier. 하나라도 깨졌으면 unknown.

    선언은 헤더 metadata 영역에만 있다 — 본문 산문의 `Risk Level` 언급까지 세면 실제 L1 사이클이
    L3 로 읽혀 CI 가 과차단된다. 여러 문서의 최대를 취하는 보수성과, 문법을 벗어난 줄에서 unknown
    으로 떨어지는 fail-closed 는 그대로 둔다 — 여기서 낮게 읽는 것이 위험한 방향이다.
    """
    found = []
    for doc in selected.values():
        declarations, error = risk_declaration.scan(doc.get("content") or "")
        if error is not None:
            return "unknown"
        for _line, tier in declarations:
            # 이 층이 아는 사이클 tier 는 L1~L3 다. `L0` 는 조용히 버리지 않고 unknown 으로
            # 떨어뜨린다 — 버리면 옆의 낮은 선언이 채택돼 실제보다 헐거운 판정이 된다.
            if tier not in _CYCLE_TIERS:
                return "unknown"
            found.append(tier)
    return max(found, key=_RANK.get) if found else None


def _review_assurance(selected: dict[str, dict[str, Any]], core) -> tuple[str, list[str]]:
    """Phase 05 가 선언한 리뷰 보증 수준과, 그 선언 자체의 정합성 문제.

    조기 완료 승인은 일반 승인과 같은 `APPROVED` 토큰을 쓴다. 서버 권위가 둘을 구분하지 못하면
    보증이 낮은 승인이 표준 승인과 같은 무게로 통과한다. 네 표기는 함께 있거나 함께 없어야 하고,
    일부만 있으면 어느 쪽으로도 해석할 수 없으므로 fail-closed 한다.
    """
    document = selected.get("05")
    content = document.get("content") or "" if isinstance(document, dict) else ""
    if not content.strip():
        # 05 를 읽지 못한 상태(선택 실패·phase 결핍)는 "표준 보증" 이 아니다. 미확인을 STANDARD 로
        # 적으면 조기 종료 승인이 서버 권위에서 일반 승인과 같은 무게로 남는다. 05 를 요구하지 않는
        # 위험도가 있으므로 이유는 만들지 않는다 — 값만 정직해지고 차단 폭은 그대로다.
        return "UNKNOWN", []
    found = {label: core._marker_values(content, label)
             for label in core._REDUCED_ASSURANCE_MARKERS}
    # `Review-Rounds`·`Residual-Findings` 는 일반 리뷰 문서에도 자연스럽게 적히는 중립 표기다.
    # 존재를 트리거로 쓰면 그 한 줄을 적은 평범한 05 가 게이트는 통과하고 권위에서만 막힌다 —
    # 같은 문서에 두 층이 다른 답을 내는 상태다. 게이트와 같은 기준으로 **자칭**만 본다.
    claimed = any(value.strip().upper() == token
                  for label, token in (("Review-Assurance", core.REVIEW_ASSURANCE_REDUCED),
                                       ("Review-Close-Reason", core.EARLY_CLOSE_REASON))
                  for value in found[label])
    if not claimed:
        return "STANDARD", []
    duplicated = [label for label, values in found.items() if len(values) > 1]
    if duplicated:
        return "UNKNOWN", [f"Phase 05 declares {duplicated} more than once"]
    missing = [label for label, values in found.items() if not values]
    if missing:
        return "UNKNOWN", [f"Phase 05 reduced-assurance markers are incomplete: missing {missing}"]
    if found["Review-Assurance"][0].upper() != core.REVIEW_ASSURANCE_REDUCED:
        return "UNKNOWN", [f"Phase 05 Review-Assurance must be {core.REVIEW_ASSURANCE_REDUCED}"]
    if found["Review-Close-Reason"][0].upper() != core.EARLY_CLOSE_REASON:
        return "UNKNOWN", [f"Phase 05 Review-Close-Reason must be {core.EARLY_CLOSE_REASON}"]
    return core.REVIEW_ASSURANCE_REDUCED, []


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
    advisories = []
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
    core, cycle_binding, risk_declaration = _trusted_gate_modules()
    # 05 를 읽지 못한 경로(선택 실패·phase 결핍)에서도 결과 모양이 같아야 한다. 미확인은 STANDARD
    # 가 아니라 UNKNOWN 이다 — 확인 못 한 것을 표준 승인으로 적으면 그게 곧 조용한 통과다.
    review_assurance = "UNKNOWN"
    cycle_stem = cycle_binding.normalize_stem(request.get("cycle_stem"))
    if cycle_stem is None:
        reasons.append("explicit safe cycle_stem is required")
    else:
        phase_docs, fast_phase_issues = _expand_fast_phase_docs(request.get("phase_docs") or {})
        reasons.extend(fast_phase_issues)
        selected, phase_errors = _selected_phases(phase_docs, cycle_stem, cycle_binding)
        try:
            declared = _declared_risk(selected, risk_declaration)
            if declared == "unknown":
                risk = "L3"
            elif declared and _RANK[declared] > _RANK[risk]:
                risk = declared
        except AuthorityError as exc:
            reasons.append(str(exc))
        if risk in ("L2", "L3"):
            reasons.extend(phase_errors)
        if not phase_errors:
            reasons.extend(_fast_evidence_reasons(request, selected, cycle_stem))
            done_reasons, done_advisories = _done_criteria_evidence(
                request, selected, cycle_stem, request.get("head_profile"))
            reasons.extend(done_reasons)
            advisories.extend(done_advisories)
            if risk == "L3":
                status, error = core._final_status(selected["05"].get("content") or "")
                head_profile = request.get("head_profile")
                pdca = head_profile.get("pdca") if isinstance(head_profile, dict) else None
                marker = str(pdca.get("approve_marker") or "APPROVED").upper() \
                    if isinstance(pdca, dict) else "APPROVED"
                if error or status != marker:
                    reasons.append(f"Phase 05 is not exactly {marker}: {error or status}")
                reasons.extend(_acceptance_evidence(selected, core))
        review_assurance, assurance_reasons = _review_assurance(selected, core)
        reasons.extend(assurance_reasons)
    return {
        "status": "BLOCK" if reasons else "PASS",
        "exit_code": 2 if reasons else 0,
        "risk": risk,
        "review_assurance": review_assurance,
        "base_risk": base_result["risk"],
        "head_risk": head_result["risk"],
        "diff_sha256": digest,
        "cycle_stem": cycle_stem,
        "selected_phases": {phase: doc.get("path") for phase, doc in selected.items()},
        "reasons": reasons,
        "advisories": advisories,
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
