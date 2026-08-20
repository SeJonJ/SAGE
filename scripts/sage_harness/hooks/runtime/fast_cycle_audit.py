"""Strict audit trail for the SAGE Fast Cycle protocol."""

import os
import time
import uuid

import loop_audit as _chain

AUDIT_REL = os.path.join(".sage", "fast_cycle.jsonl")
EVENTS = ("fast_open", "fast_convert", "fast_review", "fast_close", "fast_abort")
# run 을 여는 이벤트는 둘이다 — 새 Fast Plan(`fast_open`)과 Standard 에서 전환한 run(`fast_convert`).
# 이후 review/close/abort 는 두 경로가 공유하므로 "opener 정확히 1개" 라는 공통 상태로 정규화한다.
OPENER_EVENTS = ("fast_open", "fast_convert")
ENTRY_MODES = {"fast_open": "FAST", "fast_convert": "FAST-CONVERTED"}
TERMINAL_EVENTS = ("fast_close", "fast_abort")
AuditWriteError = _chain.AuditWriteError


def audit_path(root):
    return os.path.join(root, AUDIT_REL)


def open_operation_lock(root):
    """Serialize the cross-file plan binding and fast_open transition."""
    return _chain._audit_lock(audit_path(root) + ".open")


def new_run_id():
    return "fc-" + uuid.uuid4().hex[:12]


def _records(root):
    return _chain._read_status(audit_path(root))


def read_records(root):
    return _records(root)[0]


def _for_run(root, run_id):
    return [record for record in read_records(root) if record.get("run_id") == run_id]


def _state_from_records(all_records, run_id):
    records = [record for record in all_records if record.get("run_id") == run_id]
    opens = [record for record in records if record.get("event") in OPENER_EVENTS]
    reviews = [record for record in records if record.get("event") == "fast_review"]
    terminals = [record for record in records if record.get("event") in TERMINAL_EVENTS]
    return records, opens, reviews, terminals


def _state(root, run_id):
    return _state_from_records(read_records(root), run_id)


def _append(root, record, validator=None):
    try:
        return _chain._append(audit_path(root), record, validator=validator)
    except _chain.AuditWriteError as exc:
        raise AuditWriteError(str(exc).replace("loop audit", "fast cycle audit")) from exc


def _base(event, run_id, cycle_stem, now=None):
    epoch = time.time() if now is None else now
    return {
        "event": event,
        "run_id": run_id,
        "cycle_stem": cycle_stem,
        "ts": _chain._iso(epoch),
        "epoch": int(epoch),
        "actor": os.environ.get("SAGE_ACTOR") or os.environ.get("USER") or "unknown",
    }


def open_fast(root, *, cycle_stem, actual_risk, fast_review_level, reason,
              minimum_rounds, lenses, profile_hash, plan_hash_open,
              run_id=None, now=None):
    rid = run_id or new_run_id()
    records, opens, _reviews, terminals = _state(root, rid)
    if records or opens or terminals:
        raise AuditWriteError(f"run {rid!r} already exists")
    for other_id, state in audit_summary(root)["runs"].items():
        if state.get("cycle_stem") == cycle_stem and not state.get("terminal"):
            raise AuditWriteError(f"cycle stem {cycle_stem!r} already has active run {other_id}")
    record = _base("fast_open", rid, cycle_stem, now)
    record.update({
        "entry_mode": ENTRY_MODES["fast_open"],
        "actual_risk_open": actual_risk,
        "fast_review_level": fast_review_level,
        "reason": reason,
        "minimum_rounds": minimum_rounds,
        "lens_count": len(lenses),
        "lenses": list(lenses),
        "profile_hash": profile_hash,
        "plan_hash_open": plan_hash_open,
    })

    def validate(prior, _record):
        records, opens, _reviews, terminals = _state_from_records(prior, rid)
        if records or opens or terminals:
            raise AuditWriteError(f"run {rid!r} already exists")
        run_ids = {item.get("run_id") for item in prior
                   if isinstance(item.get("run_id"), str) and item.get("run_id")}
        for other_id in run_ids:
            _items, other_opens, _other_reviews, other_terminals = _state_from_records(prior, other_id)
            if (len(other_opens) == 1 and not other_terminals
                    and other_opens[0].get("cycle_stem") == cycle_stem):
                raise AuditWriteError(f"cycle stem {cycle_stem!r} already has active run {other_id}")

    _append(root, record, validator=validate)
    return rid


def convert_fast(root, *, cycle_stem, current_phase, actual_risk, fast_review_level,
                 reason, confirmed_by, minimum_rounds, lenses, source_phases,
                 run_id=None, now=None):
    """진행 중 Standard Cycle 을 Fast 계약으로 바꾸는 opener.

    문서를 하나도 쓰지 않는다 — 그래서 prepare/commit 중간 상태도, 교차 파일 롤백도 없다. 이 append
    가 실패하면 전환 전 상태가 그대로 남는다. `source_phases` 는 전환 시점에 존재하던 00~04 각각의
    저장소 상대 경로·raw-byte SHA-256·크기이고, 동결 기준이 아니라 "어디까지 어떤 문서로 Standard 를
    진행했는가" 를 남기는 provenance 다.

    `actual_risk` 와 `fast_review_level` 은 다른 값이다. 전자는 실제 위험도라 감사에 고정되고,
    후자는 Fast 리뷰 정책 선택일 뿐 실제 risk 를 바꾸지 않는다.
    """
    rid = run_id or new_run_id()
    records, opens, _reviews, terminals = _state(root, rid)
    if records or opens or terminals:
        raise AuditWriteError(f"run {rid!r} already exists")
    for other_id, state in audit_summary(root)["runs"].items():
        if state.get("cycle_stem") == cycle_stem and not state.get("terminal"):
            raise AuditWriteError(f"cycle stem {cycle_stem!r} already has active run {other_id}")
    record = _base("fast_convert", rid, cycle_stem, now)
    record.update({
        "entry_mode": ENTRY_MODES["fast_convert"],
        "current_phase": current_phase,
        "actual_risk_open": actual_risk,
        "fast_review_level": fast_review_level,
        "reason": reason,
        "confirmed_by": confirmed_by,
        "attestation": "self_asserted_local",
        "minimum_rounds": minimum_rounds,
        "lens_count": len(lenses),
        "lenses": list(lenses),
        "source_phases_open": source_phases,
    })

    def validate(prior, _record):
        records, opens, _reviews, terminals = _state_from_records(prior, rid)
        if records or opens or terminals:
            raise AuditWriteError(f"run {rid!r} already exists")
        run_ids = {item.get("run_id") for item in prior
                   if isinstance(item.get("run_id"), str) and item.get("run_id")}
        for other_id in run_ids:
            _items, other_opens, _other_reviews, other_terminals = _state_from_records(prior, other_id)
            if (len(other_opens) == 1 and not other_terminals
                    and other_opens[0].get("cycle_stem") == cycle_stem):
                raise AuditWriteError(f"cycle stem {cycle_stem!r} already has active run {other_id}")

    _append(root, record, validator=validate)
    return rid


def _snapshot_delta(before, after):
    """전환 시점 스냅샷 대비 리뷰 시점의 추가·변경·삭제. 판정이 아니라 구조화된 기록이다.

    변경 판단은 phase 별 `sha256` 과 `path` 둘 다로 한다 — 내용이 같고 파일만 옮긴 경우도 리뷰가
    본 것과 다른 문서다. `added`/`removed` 는 리뷰 스냅샷 범위가 전환 시점과 같아 보통 비어 있지만,
    범위가 달라지는 호출자를 위해 계산은 남긴다.
    """
    before = before if isinstance(before, dict) else {}
    after = after if isinstance(after, dict) else {}
    changed = [phase for phase in sorted(set(before) & set(after))
               if ((before[phase] or {}).get("sha256") != (after[phase] or {}).get("sha256")
                   or (before[phase] or {}).get("path") != (after[phase] or {}).get("path"))]
    return {"added": sorted(set(after) - set(before)),
            "removed": sorted(set(before) - set(after)),
            "changed": changed}


def record_review(root, run_id, *, loop_run_id, actual_risk, rounds,
                  lens_receipts_hash, plan_hash_before_review, result, now=None,
                  source_phases_review=None):
    _records_for_run, opens, reviews, terminals = _state(root, run_id)
    if len(opens) != 1 or terminals:
        raise AuditWriteError(f"run {run_id!r} cannot accept fast_review")
    record = _base("fast_review", run_id, opens[0].get("cycle_stem"), now)
    record.update({
        "loop_run_id": loop_run_id,
        "actual_risk_review": actual_risk,
        "rounds": rounds,
        "lens_receipts_hash": lens_receipts_hash,
        "plan_hash_before_review": plan_hash_before_review,
        "result": result,
    })
    # 전환 run 은 composite 문서가 없어 plan hash 로 "리뷰가 무엇을 봤는가" 를 고정할 수 없다.
    # 그 자리를 스냅샷이 대신한다. fresh run 에는 plan hash 가 정본이므로 지어내지 않는다.
    if source_phases_review is not None:
        record["source_phases_review"] = source_phases_review
        record["source_phases_delta"] = _snapshot_delta(
            opens[0].get("source_phases_open"), source_phases_review)

    def validate(prior, _record):
        _records_for_run, current_opens, _current_reviews, current_terminals = _state_from_records(prior, run_id)
        if len(current_opens) != 1 or current_terminals:
            raise AuditWriteError(f"run {run_id!r} cannot accept fast_review")

    return _append(root, record, validator=validate)


def close_fast(root, run_id, *, loop_run_id, actual_risk, plan_hash_final,
               report_path, now=None):
    _records_for_run, opens, reviews, terminals = _state(root, run_id)
    if len(opens) != 1 or not reviews or terminals:
        raise AuditWriteError(f"run {run_id!r} cannot accept fast_close")
    if reviews[-1].get("result") != "APPROVED" or reviews[-1].get("loop_run_id") != loop_run_id:
        raise AuditWriteError(f"run {run_id!r} has no matching APPROVED review")
    record = _base("fast_close", run_id, opens[0].get("cycle_stem"), now)
    record.update({
        "loop_run_id": loop_run_id,
        "actual_risk_final": actual_risk,
        "result": "APPROVED",
        "plan_hash_final": plan_hash_final,
        "report_path": report_path,
    })

    def validate(prior, _record):
        _records_for_run, current_opens, current_reviews, current_terminals = _state_from_records(prior, run_id)
        if len(current_opens) != 1 or not current_reviews or current_terminals:
            raise AuditWriteError(f"run {run_id!r} cannot accept fast_close")
        if (current_reviews[-1].get("result") != "APPROVED"
                or current_reviews[-1].get("loop_run_id") != loop_run_id):
            raise AuditWriteError(f"run {run_id!r} has no matching APPROVED review")

    return _append(root, record, validator=validate)


def abort_fast(root, run_id, *, reason, stage, actual_risk, now=None):
    _records_for_run, opens, _reviews, terminals = _state(root, run_id)
    if len(opens) != 1 or terminals:
        raise AuditWriteError(f"run {run_id!r} cannot accept fast_abort")
    record = _base("fast_abort", run_id, opens[0].get("cycle_stem"), now)
    record.update({"reason": reason, "stage": stage, "actual_risk_at_abort": actual_risk})

    def validate(prior, _record):
        _records_for_run, current_opens, _current_reviews, current_terminals = _state_from_records(prior, run_id)
        if len(current_opens) != 1 or current_terminals:
            raise AuditWriteError(f"run {run_id!r} cannot accept fast_abort")

    return _append(root, record, validator=validate)


def audit_summary(root):
    records, file_issues = _records(root)
    chain_states = _chain._chain_states(records)
    runs = {}
    seqs = {}
    for record in records:
        rid = record.get("run_id")
        if not isinstance(rid, str) or not rid:
            continue
        state = runs.setdefault(rid, {
            "cycle_stem": None, "opens": 0, "reviews": 0, "terminals": 0,
            "terminal": False, "result": None, "loop_run_id": None, "entry_mode": None,
        })
        seqs.setdefault(rid, []).append(record.get("seq"))
        event = record.get("event")
        if event in OPENER_EVENTS:
            state["opens"] += 1
            state["entry_mode"] = ENTRY_MODES[event]
            state["current_phase"] = record.get("current_phase")
            state["confirmed_by"] = record.get("confirmed_by")
            state["source_phases_open"] = record.get("source_phases_open")
            state["cycle_stem"] = record.get("cycle_stem")
            state["actual_risk"] = record.get("actual_risk_open")
            state["fast_review_level"] = record.get("fast_review_level")
            state["minimum_rounds"] = record.get("minimum_rounds")
            state["lenses"] = record.get("lenses")
            state["reason"] = record.get("reason")
            state["profile_hash"] = record.get("profile_hash")
            state["plan_hash_open"] = record.get("plan_hash_open")
        elif event == "fast_review":
            state["reviews"] += 1
            state["loop_run_id"] = record.get("loop_run_id")
            state["review_result"] = record.get("result")
            state["plan_hash_before_review"] = record.get("plan_hash_before_review")
            # 전환 run 의 "리뷰가 무엇을 봤는가" 는 plan hash 가 아니라 이 스냅샷이다. 상태로
            # 올리지 않으면 close 가 대조할 기준을 갖지 못한다.
            state["source_phases_review"] = record.get("source_phases_review")
        elif event in TERMINAL_EVENTS:
            state["terminals"] += 1
            state["terminal"] = True
            state["result"] = record.get("result") or "ABORTED"
    for rid, state in runs.items():
        state["clean"] = state["opens"] == 1 and state["terminals"] <= 1
        state["seq_ok"] = _chain._seq_ok(seqs.get(rid, []))
        state["chain_ok"] = chain_states.get(rid)
        del state["opens"]
        del state["reviews"]
        del state["terminals"]
    active = sorted(rid for rid, state in runs.items() if not state["terminal"])
    return {
        "runs": runs,
        "active": active,
        "has_any_records": bool(records),
        "file_ok": not file_issues,
        "file_issues": file_issues,
    }


def _diagnostic(code, **arguments):
    """언어 중립 진단(code+arguments). 이 모듈은 sage.diagnostics 를 import 할 수 없어
    (엔진 없이 소비 프로젝트에서 단독 실행되어야 하므로) 같은 모양의 plain dict 로 올린다 —
    CLI 호출부(cycle.py/fast_cycle.py)가 각자 필요한 언어로 렌더한다."""
    return {"code": code, "arguments": arguments, "evidence": ""}


def integrity_issues(root):
    summary = audit_summary(root)
    issues = [_diagnostic("fast_cycle_audit.damaged", detail=item) for item in summary["file_issues"]]
    for rid, state in summary["runs"].items():
        if not state["clean"]:
            issues.append(_diagnostic("fast_cycle_audit.duplicate_or_orphan", run_id=rid))
        if state["seq_ok"] is False:
            issues.append(_diagnostic("fast_cycle_audit.seq_broken", run_id=rid))
        if state["chain_ok"] is False:
            issues.append(_diagnostic("fast_cycle_audit.chain_invalid", run_id=rid))
    return issues
