"""Deterministic Fast Cycle state machine."""

from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
from pathlib import Path

from sage import _resources, overlay_common
from sage.fast_cycle_contract import (
    bind_run_id,
    done_criteria_issues,
    evidence_marker_issues,
    open_issues,
    parse_fast_plan,
    reason_issue,
)
from sage.profile_layers import load_profile_layers
from sage.profile_validate import validate_profile
from sage.i18n import tr


def _positive(value):
    import argparse
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("positive integer required")
    if parsed < 1:
        raise argparse.ArgumentTypeError("positive integer required")
    return parsed


def register(sub, context):
    parser = sub.add_parser("fast-cycle", help=tr(context, "cli.fast_cycle.fast_cycle"))
    actions = parser.add_subparsers(dest="action", metavar="<action>")
    actions.required = True

    opened = actions.add_parser("open", help=tr(context, "cli.fast_cycle.open"))
    opened.add_argument("--stem", required=True)
    opened.add_argument("--level", required=True, choices=["L2", "L3"])
    opened.add_argument("--lens-count", required=True, type=_positive)
    opened.add_argument("--reason", required=True)
    opened.add_argument("--root", default=None)
    opened.set_defaults(func=_run_open)

    reviewed = actions.add_parser("review", help=tr(context, "cli.fast_cycle.review"))
    reviewed.add_argument("--run-id", required=True)
    reviewed.add_argument("--loop-run-id", required=True)
    reviewed.add_argument("--root", default=None)
    reviewed.set_defaults(func=_run_review)

    closed = actions.add_parser("close", help=tr(context, "cli.fast_cycle.close"))
    closed.add_argument("--run-id", required=True)
    closed.add_argument("--root", default=None)
    closed.set_defaults(func=_run_close)

    aborted = actions.add_parser("abort", help=tr(context, "cli.fast_cycle.abort"))
    aborted.add_argument("--run-id", required=True)
    aborted.add_argument("--reason", required=True)
    aborted.add_argument("--root", default=None)
    aborted.set_defaults(func=_run_abort)

    shown = actions.add_parser("show", help=tr(context, "cli.fast_cycle.show"))
    shown.add_argument("--run-id", default=None)
    shown.add_argument("--vault", nargs="?", const="", default=None)
    shown.add_argument("--root", default=None)
    shown.set_defaults(func=_run_show)


def _runtime(name):
    runtime = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks", "runtime")
    if runtime not in sys.path:
        sys.path.insert(0, runtime)
    return __import__(name)


def _root(args):
    if args.root:
        return os.path.abspath(args.root)
    cycle_state = _runtime("cycle_state")
    return cycle_state.find_project_root(os.getcwd()) or os.path.abspath(os.getcwd())


def _profile(root):
    path = os.path.join(root, "sage", "project-profile.yaml")
    if not os.path.isfile(path):
        raise ValueError(f"shared profile not found: {path}")
    layers = load_profile_layers(path)
    failures = [message for severity, message in layers.issues if severity == "FAIL"]
    failures.extend(message for severity, message in validate_profile(layers.effective, _resources.sage_root())
                    if severity == "FAIL")
    if failures:
        raise ValueError("profile invalid: " + "; ".join(failures[:3]))
    return layers.effective


def _phase_glob(profile, phase_id):
    pdca = profile.get("pdca") if isinstance(profile, dict) else None
    phases = pdca.get("phases") if isinstance(pdca, dict) else None
    matches = [item.get("glob") for item in (phases or [])
               if isinstance(item, dict) and item.get("id") == phase_id and isinstance(item.get("glob"), str)]
    if len(matches) != 1:
        raise ValueError(f"profile needs exactly one phase {phase_id} glob")
    return matches[0]


def _stem_doc(root, profile, phase_id, stem):
    pattern = _phase_glob(profile, phase_id)
    paths = [path for path in glob.glob(os.path.join(root, pattern), recursive=True)
             if os.path.isfile(path) and os.path.basename(path) == f"{stem}.md"]
    if len(paths) != 1:
        raise ValueError(f"phase {phase_id} document for {stem!r} must exist exactly once; found={len(paths)}")
    real_root = os.path.realpath(root)
    path = os.path.realpath(paths[0])
    if os.path.commonpath([real_root, path]) != real_root:
        raise ValueError(f"phase {phase_id} document escapes project root")
    return path


def _fast_policy(profile):
    pdca = profile.get("pdca") if isinstance(profile, dict) else None
    fast = pdca.get("fast_cycle") if isinstance(pdca, dict) else None
    if not isinstance(fast, dict) or fast.get("enabled") is not True:
        raise ValueError("pdca.fast_cycle.enabled=true is required")
    return fast


def _done_criteria_mode(profile):
    pdca = profile.get("pdca") if isinstance(profile, dict) else None
    base_plan = pdca.get("base_plan") if isinstance(pdca, dict) else None
    mode = base_plan.get("done_criteria_gate", "off") if isinstance(base_plan, dict) else "off"
    if mode not in ("off", "advisory", "enforce"):
        raise ValueError(f"invalid pdca.base_plan.done_criteria_gate={mode!r}")
    return mode


def _apply_done_criteria_policy(profile, plan, *, stage, include_unresolved):
    mode = _done_criteria_mode(profile)
    if mode == "off":
        return
    issues = done_criteria_issues(plan, include_unresolved=include_unresolved)
    if not issues:
        return
    detail = "; ".join(issues[:3])
    if mode == "enforce":
        raise ValueError(f"Fast Plan Done Criteria rejected at {stage}: {detail}")
    print(f"⚠️ [sage fast-cycle] Done Criteria advisory at {stage}: {detail}", file=sys.stderr)


def _profile_hash(profile):
    payload = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _warn(actual_risk, level, rounds, lenses, reason, run_id):
    print(f"⚠️ [SAGE FAST {actual_risk}]", file=sys.stderr)
    if actual_risk == "L3" and level == "L2":
        print("이 작업은 L3 위험도로 분류됐지만 L2 Fast 리뷰 절차를 사용합니다.", file=sys.stderr)
    else:
        print(f"표준 {actual_risk} PDCA 대신 Fast Cycle을 사용합니다.", file=sys.stderr)
    print(f"리뷰가 {rounds}라운드·{len(lenses)}개 렌즈로 축약되어 표준 절차보다 검증 보증이 낮습니다.", file=sys.stderr)
    print(f"선택 렌즈: {', '.join(lenses)}", file=sys.stderr)
    print(f"사유: {reason}", file=sys.stderr)
    print(f"감사 기록: .sage/fast_cycle.jsonl ({run_id})", file=sys.stderr)


def _open_snapshot_issues(state, *, stem, actual_risk, level, rounds, lenses,
                          reason, profile_hash):
    expected = {
        "cycle_stem": stem,
        "actual_risk": actual_risk,
        "fast_review_level": level,
        "minimum_rounds": rounds,
        "lenses": lenses,
        "reason": reason,
        "profile_hash": profile_hash,
    }
    issues = [f"{key}: audit={state.get(key)!r}, requested={value!r}"
              for key, value in expected.items() if state.get(key) != value]
    if state.get("terminal") or state.get("clean") is not True:
        issues.append("audit run is terminal or structurally unclean")
    if state.get("chain_ok") is not True or state.get("seq_ok") is not True:
        issues.append("audit run lacks strict chain/sequence integrity")
    return issues


def _run_open(args):
    root = _root(args)
    try:
        issue = reason_issue(args.reason)
        if issue:
            raise ValueError(issue)
        profile = _profile(root)
        policy = _fast_policy(profile)
        minimum_lenses = policy["minimum_lenses"][args.level]
        if args.lens_count < minimum_lenses:
            raise ValueError(f"lens-count must be at least {minimum_lenses} for {args.level}")
        candidates = policy["lenses"][args.level]
        if args.lens_count > len(candidates):
            raise ValueError(f"lens-count exceeds configured candidates ({len(candidates)})")
        lenses = candidates[:args.lens_count]
        rounds = policy["minimum_rounds"][args.level]
        cycle_state = _runtime("cycle_state")
        stem, _origin, state_error = cycle_state.resolve_stem(root)
        if state_error or stem != args.stem:
            raise ValueError(f"active cycle stem must be {args.stem!r}; active={stem!r}, error={state_error}")
        path = _stem_doc(root, profile, "00", args.stem)
        audit = _runtime("fast_cycle_audit")
        profile_hash = _profile_hash(profile)
        with audit.open_operation_lock(root):
            content = Path(path).read_text(encoding="utf-8")
            plan, issues = parse_fast_plan(content)
            if plan is None:
                raise ValueError("; ".join(issues))
            issues.extend(open_issues(plan, stem=args.stem, level=args.level,
                                      lens_count=args.lens_count, reason=args.reason,
                                      minimum_rounds=rounds, lenses=lenses))
            if issues:
                raise ValueError("; ".join(issues[:5]))
            _apply_done_criteria_policy(
                profile, plan, stage="open", include_unresolved=False)
            actual_risk = plan.metadata["Risk Level"]
            summary = audit.audit_summary(root)
            if summary.get("file_ok") is not True:
                raise ValueError("Fast audit file integrity failed")
            run_id = plan.metadata["Fast-Audit-Run"]
            if run_id == "pending":
                active = [rid for rid in (summary.get("active") or [])
                          if (summary.get("runs") or {}).get(rid, {}).get("cycle_stem") == args.stem]
                if len(active) > 1:
                    raise ValueError(f"multiple active Fast runs for stem {args.stem!r}: {active}")
                run_id = active[0] if active else audit.new_run_id()
                bound = bind_run_id(content, run_id)
                bound_hash = hashlib.sha256(bound.encode("utf-8")).hexdigest()
                existing = (summary.get("runs") or {}).get(run_id)
                if existing:
                    snapshot_issues = _open_snapshot_issues(
                        existing, stem=args.stem, actual_risk=actual_risk, level=args.level,
                        rounds=rounds, lenses=lenses, reason=args.reason,
                        profile_hash=profile_hash)
                    if existing.get("plan_hash_open") != bound_hash:
                        snapshot_issues.append("pending plan does not match the audited open hash")
                    if snapshot_issues:
                        raise ValueError("Fast-Audit-Run does not match its audit snapshot: "
                                         + "; ".join(snapshot_issues))
                    overlay_common.write_text_lf(path, bound)
                    content = bound
                else:
                    audit.open_fast(
                        root, cycle_stem=args.stem, actual_risk=actual_risk,
                        fast_review_level=args.level, reason=args.reason,
                        minimum_rounds=rounds, lenses=lenses, profile_hash=profile_hash,
                        plan_hash_open=bound_hash, run_id=run_id)
                    try:
                        overlay_common.write_text_lf(path, bound)
                        content = bound
                    except Exception as write_error:
                        try:
                            audit.abort_fast(
                                root, run_id, reason="Fast Plan run-id binding failed",
                                stage="open", actual_risk=actual_risk)
                        except Exception as abort_error:
                            raise RuntimeError(
                                f"Fast Plan binding failed ({write_error}); audit rollback failed: "
                                f"{abort_error}") from write_error
                        raise
            else:
                existing = (summary.get("runs") or {}).get(run_id)
                if not existing:
                    raise ValueError(f"Fast-Audit-Run {run_id} has no audit record")
                snapshot_issues = _open_snapshot_issues(
                    existing, stem=args.stem, actual_risk=actual_risk, level=args.level,
                    rounds=rounds, lenses=lenses, reason=args.reason,
                    profile_hash=profile_hash)
                if snapshot_issues:
                    raise ValueError("Fast-Audit-Run does not match its audit snapshot: "
                                     + "; ".join(snapshot_issues))
        print(run_id)
        _warn(actual_risk, args.level, rounds, lenses, args.reason, run_id)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"⛔ [sage fast-cycle] open rejected: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"⛔ [sage fast-cycle] open audit failure: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _run_review(args):
    root = _root(args)
    try:
        profile = _profile(root)
        audit = _runtime("fast_cycle_audit")
        audit_issues = audit.integrity_issues(root)
        state = audit.audit_summary(root)["runs"].get(args.run_id)
        if audit_issues or not state or state.get("terminal"):
            raise ValueError("active clean Fast run required: " + "; ".join(audit_issues[:3]))
        stem = state.get("cycle_stem")
        plan_path = _stem_doc(root, profile, "00", stem)
        content = Path(plan_path).read_text(encoding="utf-8")
        plan, issues = parse_fast_plan(content)
        if plan is None or issues:
            raise ValueError("invalid Fast Plan: " + "; ".join(issues[:3]))
        _apply_done_criteria_policy(
            profile, plan, stage="review", include_unresolved=True)
        if plan.metadata.get("Fast-Audit-Run") != args.run_id:
            raise ValueError("Fast Plan run id does not match")
        if "PENDING — implementation not started" in plan.sections.get("04", ""):
            raise ValueError("Phase 04 is still PENDING")

        review_path = _stem_doc(root, profile, "05", stem)
        review_text = Path(review_path).read_text(encoding="utf-8")
        marker_issues = evidence_marker_issues(
            review_text, fast_run_id=args.run_id, loop_run_id=args.loop_run_id)
        if marker_issues:
            raise ValueError("Phase 05 evidence markers invalid: " + "; ".join(marker_issues))

        loop = _runtime("loop_audit")
        loop_issues = loop.integrity_issues(root)
        loop_state = loop.audit_summary(root)["runs"].get(args.loop_run_id)
        if loop_issues or not loop_state:
            raise ValueError("Loop Audit invalid or run missing: " + "; ".join(loop_issues[:3]))
        if not (loop_state.get("clean") and loop_state.get("closed")
                and loop_state.get("result") == "APPROVED"
                and loop_state.get("seq_ok") is True
                and loop_state.get("chain_ok") is True
                and not loop_state.get("degraded")):
            raise ValueError("Loop run must be clean, strict-chain, non-degraded, closed APPROVED")
        loop_records = [record for record in loop.read_records(root)
                        if record.get("run_id") == args.loop_run_id]
        loop_open = next((record for record in loop_records if record.get("event") == "loop_open"), None)
        if not loop_open or loop_open.get("cycle_stem") != stem:
            raise ValueError("Loop run cycle stem does not match Fast run")
        expected_lenses = state.get("lenses") or []
        if loop_open.get("lenses") != expected_lenses:
            raise ValueError("Loop open lenses do not match Fast run")
        rounds = [record for record in loop_records if record.get("event") == "round"]
        if len(rounds) < int(state.get("minimum_rounds") or 0):
            raise ValueError("Loop run has fewer rounds than Fast minimum")
        for record in rounds:
            if record.get("lens_receipts") != expected_lenses:
                raise ValueError(f"Loop round {record.get('iteration')} lens receipts do not match")
        receipts_payload = json.dumps(
            [{"iteration": record.get("iteration"), "lenses": record.get("lens_receipts")} for record in rounds],
            ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        receipts_hash = hashlib.sha256(receipts_payload.encode("utf-8")).hexdigest()
        plan_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        audit.record_review(root, args.run_id, loop_run_id=args.loop_run_id,
                            actual_risk=plan.metadata.get("Risk Level"), rounds=len(rounds),
                            lens_receipts_hash=receipts_hash,
                            plan_hash_before_review=plan_hash, result="APPROVED")
        print(f"[sage fast-cycle] review bound {args.run_id} -> {args.loop_run_id}")
        _warn(plan.metadata.get("Risk Level"), state.get("fast_review_level"),
              state.get("minimum_rounds"), expected_lenses, state.get("reason"), args.run_id)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"⛔ [sage fast-cycle] review rejected: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"⛔ [sage fast-cycle] review audit failure: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _run_close(args):
    root = _root(args)
    try:
        profile = _profile(root)
        audit = _runtime("fast_cycle_audit")
        issues = audit.integrity_issues(root)
        state = audit.audit_summary(root)["runs"].get(args.run_id)
        if issues or not state or state.get("terminal") or state.get("review_result") != "APPROVED":
            raise ValueError("active run with clean APPROVED Fast review required")
        stem = state.get("cycle_stem")
        plan_path = _stem_doc(root, profile, "00", stem)
        content = Path(plan_path).read_text(encoding="utf-8")
        current_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if current_hash != state.get("plan_hash_before_review"):
            raise ValueError("Fast Plan changed after the latest review; run review again")
        loop_run_id = state.get("loop_run_id")
        review_text = Path(_stem_doc(root, profile, "05", stem)).read_text(encoding="utf-8")
        report_path = _stem_doc(root, profile, "06", stem)
        report_text = Path(report_path).read_text(encoding="utf-8")
        review_marker_issues = evidence_marker_issues(
            review_text, fast_run_id=args.run_id, loop_run_id=loop_run_id)
        if review_marker_issues:
            raise ValueError("Phase 05 no longer matches latest Fast/Loop review: "
                             + "; ".join(review_marker_issues))
        report_marker_issues = evidence_marker_issues(
            report_text, fast_run_id=args.run_id, loop_run_id=loop_run_id)
        if report_marker_issues:
            raise ValueError("Phase 06 does not bind latest Fast/Loop review and APPROVED status: "
                             + "; ".join(report_marker_issues))
        plan, parse_issues = parse_fast_plan(content)
        if plan is None or parse_issues:
            raise ValueError("Fast Plan is invalid at close")
        _apply_done_criteria_policy(
            profile, plan, stage="close", include_unresolved=True)
        audit.close_fast(root, args.run_id, loop_run_id=loop_run_id,
                         actual_risk=plan.metadata.get("Risk Level"),
                         plan_hash_final=current_hash,
                         report_path=os.path.relpath(report_path, root).replace(os.sep, "/"))
        print(f"[sage fast-cycle] closed {args.run_id}")
        _auto_dashboard(root)
        _warn(plan.metadata.get("Risk Level"), state.get("fast_review_level"),
              state.get("minimum_rounds"), state.get("lenses") or [],
              state.get("reason"), args.run_id)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"⛔ [sage fast-cycle] close rejected: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"⛔ [sage fast-cycle] close audit failure: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _run_abort(args):
    root = _root(args)
    issue = reason_issue(args.reason)
    if issue:
        print(f"⛔ [sage fast-cycle] abort rejected: {issue}", file=sys.stderr)
        return 2
    audit = _runtime("fast_cycle_audit")
    try:
        with audit.open_operation_lock(root):
            state = audit.audit_summary(root)["runs"].get(args.run_id)
            if not state or state.get("terminal"):
                print(f"⛔ [sage fast-cycle] active run not found: {args.run_id}", file=sys.stderr)
                return 2
            audit.abort_fast(root, args.run_id, reason=args.reason, stage="manual",
                             actual_risk=state.get("actual_risk"))
    except Exception as exc:
        print(f"⛔ [sage fast-cycle] abort audit failure: {exc}", file=sys.stderr)
        return 2
    print(f"[sage fast-cycle] aborted {args.run_id}")
    _auto_dashboard(root)
    return 0


def _run_show(args):
    root = _root(args)
    audit = _runtime("fast_cycle_audit")
    summary = audit.audit_summary(root)
    if not summary["file_ok"]:
        for issue in summary["file_issues"]:
            print(f"FAIL: {issue}")
        return 2
    run_ids = [args.run_id] if args.run_id else sorted(summary["runs"])
    for run_id in run_ids:
        state = summary["runs"].get(run_id)
        if state is None:
            print(f"unknown run: {run_id}", file=sys.stderr)
            return 2
        print(f"{run_id} stem={state.get('cycle_stem')} risk={state.get('actual_risk')} "
              f"fast={state.get('fast_review_level')} result={state.get('result') or 'ACTIVE'}")
    if args.vault is not None:
        try:
            _write_dashboard(root, args.vault or None)
        except Exception as exc:
            print(f"⚠️ [sage fast-cycle] vault dashboard failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
    return 0


def _table(value):
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _dashboard_body(root):
    audit = _runtime("fast_cycle_audit")
    records = audit.read_records(root)
    summary = audit.audit_summary(root)
    rows = []
    for run_id, state in sorted(summary["runs"].items()):
        run_records = [record for record in records if record.get("run_id") == run_id]
        opened = next((record for record in run_records if record.get("event") == "fast_open"), {})
        reviews = [record for record in run_records if record.get("event") == "fast_review"]
        terminal = next((record for record in reversed(run_records)
                         if record.get("event") in ("fast_close", "fast_abort")), {})
        actual_rounds = reviews[-1].get("rounds") if reviews else "-"
        result = terminal.get("result") or ("ABORTED" if terminal.get("event") == "fast_abort" else "ACTIVE")
        rows.append("| " + " | ".join(_table(value) for value in (
            run_id, state.get("cycle_stem"), state.get("actual_risk"),
            state.get("fast_review_level"), state.get("minimum_rounds"), actual_rounds,
            ", ".join(state.get("lenses") or []), state.get("reason"),
            state.get("loop_run_id") or "-", result,
            opened.get("ts") or "-", terminal.get("ts") or "-")) + " |")
    body = [
        "# SAGE Fast Cycle 감사 대시보드", "",
        "> 정본 데이터: `.sage/fast_cycle.jsonl`. 이 노트는 파생 대시보드이며 정본이 아닙니다.", "",
        "| run | stem | actual risk | Fast level | min rounds | actual rounds | lenses | reason | Loop run | result | opened | terminal |",
        "|---|---|---|---|---:|---:|---|---|---|---|---|---|",
        *(rows or ["| (기록 없음) | | | | | | | | | | | |"]),
    ]
    issues = audit.integrity_issues(root)
    if issues:
        body.extend(["", "## 무결성 경고", *[f"- {_table(issue)}" for issue in issues]])
    return "\n".join(body) + "\n"


def _write_dashboard(root, override=None):
    import datetime
    from sage.commands import _vault
    from sage.commands._common import _project_name
    from sage.commands.knowledge import _note_filename
    profile = _profile(root)
    vault, folder = _vault.vault_target(profile, override, root)
    if not vault:
        raise ValueError("effective vault path is not configured")
    project = _project_name(profile) or "SAGE"
    filename = _note_filename(profile, "TECH", f"{project} fast cycle audit")
    frontmatter = {"tags": ["sage", "fast-cycle", "audit"],
                   "updated": datetime.date.today().isoformat(),
                   "generated_by": "sage fast-cycle"}
    path = _vault.write_note(vault, folder, filename, frontmatter, _dashboard_body(root))
    print(f"[sage fast-cycle] Obsidian dashboard: {path}", file=sys.stderr)


def _auto_dashboard(root):
    try:
        profile = _profile(root)
        capture = profile.get("knowledge_capture") if isinstance(profile, dict) else None
        if not isinstance(capture, dict) or capture.get("fast_cycle_dashboard") is not True:
            return
        _write_dashboard(root)
    except Exception as exc:
        print(f"⚠️ [sage fast-cycle] automatic vault dashboard failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)
