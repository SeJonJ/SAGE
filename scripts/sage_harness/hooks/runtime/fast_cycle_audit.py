"""Strict audit trail for the SAGE Fast Cycle protocol."""

import os
import time
import uuid

import loop_audit as _chain

AUDIT_REL = os.path.join(".sage", "fast_cycle.jsonl")
EVENTS = ("fast_open", "fast_review", "fast_close", "fast_abort")
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
    opens = [record for record in records if record.get("event") == "fast_open"]
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


def record_review(root, run_id, *, loop_run_id, actual_risk, rounds,
                  lens_receipts_hash, plan_hash_before_review, result, now=None):
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
            "terminal": False, "result": None, "loop_run_id": None,
        })
        seqs.setdefault(rid, []).append(record.get("seq"))
        event = record.get("event")
        if event == "fast_open":
            state["opens"] += 1
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


def integrity_issues(root):
    summary = audit_summary(root)
    issues = [f"fast cycle audit damaged: {item}" for item in summary["file_issues"]]
    for rid, state in summary["runs"].items():
        if not state["clean"]:
            issues.append(f"run {rid}: duplicate or orphan state transition")
        if state["seq_ok"] is False:
            issues.append(f"run {rid}: seq is not continuous")
        if state["chain_ok"] is False:
            issues.append(f"run {rid}: strict hash-chain is invalid")
    return issues
