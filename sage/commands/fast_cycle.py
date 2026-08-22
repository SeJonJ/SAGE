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
    PHASES,
    bind_run_id,
    done_criteria_issues,
    evidence_marker_issues,
    open_issues,
    parse_fast_plan,
    reason_issue,
)
from sage.profile_layers import load_profile_layers
from sage.profile_validate import validate_profile
from sage.i18n import english_text, language_of, render_issue, tr


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

    converted = actions.add_parser("convert", help=tr(context, "cli.fast_cycle.convert"))
    converted.add_argument("--stem", required=True)
    converted.add_argument("--current-phase", required=True, choices=list(CONVERTIBLE_PHASES))
    converted.add_argument("--level", required=True, choices=["L2", "L3"])
    converted.add_argument("--lens-count", required=True, type=_positive)
    converted.add_argument("--reason", required=True)
    converted.add_argument("--confirmed-by", required=True)
    converted.add_argument("--confirm", required=True,
                           help=tr(context, "cli.fast_cycle.confirm"))
    converted.add_argument("--root", default=None)
    converted.set_defaults(func=_run_convert)

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
    hooks = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks")
    for candidate in (os.path.join(hooks, "runtime"), hooks):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
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
    failures = [english_text(message) for severity, message in layers.issues if severity == "FAIL"]
    # 검증 기준은 프로젝트 root 다 — `governance_docs` 는 프로젝트 상대 경로라 번들 root 로 재면
    # 실재하는 문서가 부재로 판정돼, 정상 profile 이 Fast Cycle 진입을 막는다. root 를 새로 추론하지
    # 않고 `_root(args)` 가 이미 확정해 넘겨준 값을 그대로 쓴다.
    failures.extend(english_text(message)
                    for severity, message in validate_profile(layers.effective, root)
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


def _warn(actual_risk, level, rounds, lenses, reason, run_id, language=None):
    print(f"⚠️ [SAGE FAST {actual_risk}]", file=sys.stderr)
    if actual_risk == "L3" and level == "L2":
        print(tr(language, 'cli.fast_cycle.msg01'), file=sys.stderr)
    else:
        print(tr(language, 'cli.fast_cycle.msg02', actual_risk=actual_risk), file=sys.stderr)
    print(tr(language, 'cli.fast_cycle.msg03', rounds=rounds, count=len(lenses)), file=sys.stderr)
    print(tr(language, 'cli.fast_cycle.msg04', items=', '.join(lenses)), file=sys.stderr)
    print(tr(language, 'cli.fast_cycle.msg05', reason=reason), file=sys.stderr)
    print(tr(language, 'cli.fast_cycle.msg06', run_id=run_id), file=sys.stderr)


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


# 전환 스냅샷의 phase 집합은 공용 계약 하나에서 온다. 여기서 따로 적으면 권위 층이 기대하는
# 집합과 조용히 갈라지고, 그 어긋남은 "스냅샷이 덜 들어 있다" 로만 나타나 눈에 띄지 않는다.
CONVERTIBLE_PHASES = PHASES
CONVERT_CONFIRMATION = "FAST-CONVERTED"


def _transition_enabled(fast):
    """Standard→Fast 전환 opt-in. 키 부재는 비활성이다 — 설정하지 않은 프로젝트는 열리지 않는다."""
    block = fast.get("standard_transition")
    return isinstance(block, dict) and block.get("enabled") is True


def _source_phase_snapshot(root, profile, stem, current_phase):
    """전환 시점 00~current-phase 의 경로·raw-byte 해시·크기.

    동결 기준이 아니라 provenance 다 — 전환 뒤 문서가 정상 개발로 바뀌는 것은 허용하고, 어디까지
    어떤 문서로 Standard 를 진행했는지만 남긴다. 경로 이탈과 symlink 는 여기서 거부한다: 감사가
    가리키는 대상이 실제 그 파일이라는 보장이 없으면 provenance 가 아니다.
    """
    real_root = os.path.realpath(root)
    snapshot = {}
    for phase in CONVERTIBLE_PHASES[:CONVERTIBLE_PHASES.index(current_phase) + 1]:
        pattern = _phase_glob(profile, phase)
        candidates = [path for path in glob.glob(os.path.join(root, pattern), recursive=True)
                      if os.path.basename(path) == f"{stem}.md"]
        if any(os.path.islink(path) for path in candidates):
            raise ValueError(f"phase {phase} document for {stem!r} is a symlink")
        path = _stem_doc(root, profile, phase, stem)
        payload = Path(path).read_bytes()
        snapshot[phase] = {
            "path": os.path.relpath(path, real_root).replace(os.sep, "/"),
            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }
    return snapshot


def _completed_cycle_issue(root, profile, stem):
    """최종 승인된 05 나 06 이 있는 완결 사이클은 전환하지 않는다."""
    pdca = (profile.get("pdca") or {}) if isinstance(profile, dict) else {}
    approve_phase = str(pdca.get("approve_phase") or "05")
    marker = str(pdca.get("approve_marker") or "APPROVED")
    report_phase = str(pdca.get("report_phase") or "06")
    try:
        approved = Path(_stem_doc(root, profile, approve_phase, stem)).read_text(encoding="utf-8")
    except (ValueError, OSError, UnicodeError):
        approved = ""
    if marker.lower() in approved.lower():
        return f"cycle {stem!r} already has an approved phase {approve_phase}"
    try:
        _stem_doc(root, profile, report_phase, stem)
    except (ValueError, OSError):
        return None
    return f"cycle {stem!r} already has a phase {report_phase} report"


def _convert_risk(content):
    """Phase 00 의 실제 위험도. 공용 파서가 유일한 해석 정본이다."""
    declaration = _runtime("risk_declaration").parse(content)
    if declaration.status != "valid" or declaration.tier not in ("L1", "L2", "L3"):
        detail = declaration.status
        if declaration.line is not None:
            detail = f"{detail} (line {declaration.line}: {declaration.excerpt})"
        raise ValueError(f"Phase 00 Risk Level declaration is not usable: {detail}")
    return declaration.tier


def _run_convert(args):
    root = _root(args)
    try:
        # 확인 토큰은 preflight 의 첫 관문이다. 정확히 일치하지 않으면 어떤 상태도 읽지 않는다.
        if args.confirm != CONVERT_CONFIRMATION:
            raise ValueError(f"--confirm must be exactly {CONVERT_CONFIRMATION}")
        issue = reason_issue(args.reason)
        if issue:
            raise ValueError(issue)
        if not (args.confirmed_by or "").strip():
            raise ValueError("--confirmed-by must be a non-empty line")
        profile = _profile(root)
        policy = _fast_policy(profile)
        if not _transition_enabled(policy):
            raise ValueError("pdca.fast_cycle.standard_transition.enabled=true is required")
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
            error_text = english_text(state_error) if state_error else None
            raise ValueError(f"active cycle stem must be {args.stem!r}; active={stem!r}, error={error_text}")

        completed = _completed_cycle_issue(root, profile, args.stem)
        if completed:
            raise ValueError(completed)

        snapshot = _source_phase_snapshot(root, profile, args.stem, args.current_phase)
        phase00 = Path(root, snapshot["00"]["path"]).read_text(encoding="utf-8")
        # 이미 composite Fast Plan 인 사이클은 전환 대상이 아니다 — 전환하면 entry_mode 가
        # FAST-CONVERTED 가 되어 review 가 composite 검사를 통째로 건너뛴다(Phase 04 PENDING,
        # run-id 결속, 문서 선언과 인자 대조). fresh Fast 는 `open` 이 유일한 입구다.
        existing, _issues = parse_fast_plan(phase00)
        if existing is not None and existing.metadata.get("Cycle-Mode") == "FAST":
            raise ValueError("Phase 00 is already a composite Fast Plan; use `fast-cycle open`")
        actual_risk = _convert_risk(phase00)
        if actual_risk not in ("L2", "L3"):
            raise ValueError(f"only L2/L3 cycles convert to Fast; actual={actual_risk}")
        _apply_standard_done_criteria_policy(profile, phase00)

        audit = _runtime("fast_cycle_audit")
        with audit.open_operation_lock(root):
            summary = audit.audit_summary(root)
            # `file_ok` 는 줄이 JSON 으로 읽히는지만 본다 — 레코드 값을 고쳐도 참이다. 전환은
            # 기존 감사 위에 opener 를 얹는 조작이라, 밑에 깔린 기록이 손상됐으면 얹으면 안 된다.
            integrity = audit.integrity_issues(root)
            if integrity:
                raise ValueError("Fast audit integrity failed: "
                                 + "; ".join(str(issue) for issue in integrity[:3]))
            active = [rid for rid in (summary.get("active") or [])
                      if (summary.get("runs") or {}).get(rid, {}).get("cycle_stem") == args.stem]
            if active:
                raise ValueError(f"stem {args.stem!r} already has an active Fast run: {active}")
            run_id = audit.convert_fast(
                root, cycle_stem=args.stem, current_phase=args.current_phase,
                actual_risk=actual_risk, fast_review_level=args.level, reason=args.reason,
                confirmed_by=args.confirmed_by, minimum_rounds=rounds, lenses=lenses,
                source_phases=snapshot)
    except (ValueError, OSError, UnicodeError, KeyError) as exc:
        print(f"⛔ [sage fast-cycle] convert failed: {exc}", file=sys.stderr)
        return 2
    print(f"[sage fast-cycle] converted stem={args.stem} run_id={run_id} "
          f"actual_risk={actual_risk} fast_level={args.level} phase={args.current_phase}",
          file=sys.stderr)
    print(f"Fast-Run: {run_id}")
    return 0


def _apply_standard_done_criteria_policy(profile, content, include_unresolved=False):
    """표준 Phase 00 의 Done Criteria 정책. 단계에 따라 보는 범위가 다르다.

    **전환 시점**(`include_unresolved=False`)은 형식과 revision 만 본다 — 전환은 남은 절차의 계약을
    바꾸는 것이지 완료를 선언하는 게 아니다. 형식이 깨졌으면 이후 review/close 가 기댈 기준이 없다.

    **review·close**(`include_unresolved=True`)는 미완료 항목도 본다. fresh 경로가 같은 자리에서
    `include_unresolved=True` 로 막으므로, 여기서 빼면 전환 run 만 미완료 완료기준으로 닫힌다.
    """
    mode = _done_criteria_mode(profile)
    if mode == "off":
        return
    from sage.done_criteria_contract import parse_done_criteria

    result = parse_done_criteria(content, mode="standard")
    issues = list(result.issues or []) if result.status == "invalid" else []
    if include_unresolved and result.unresolved:
        issues.append(f"unresolved Done Criteria: {len(result.unresolved)} item(s)")
    if not issues:
        return
    detail = "; ".join(issues[:3])
    if mode == "enforce":
        raise ValueError(f"Phase 00 Done Criteria is invalid: {detail}")
    print(f"[sage fast-cycle] Done Criteria advisory: {detail}", file=sys.stderr)


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
            error_text = english_text(state_error) if state_error else None
            raise ValueError(f"active cycle stem must be {args.stem!r}; active={stem!r}, error={error_text}")
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
            # `file_ok` 는 줄이 JSON 으로 읽히는지만 본다. 결속된 run 의 chain 상태는 아래 재개
            # 대조가 보지만, 새 run 은 대조할 상대가 없어 손상된 감사 위에 그대로 얹혔다.
            # review·close 는 이미 여기서 거부한다 — open 만 통과하면 원인이 두 단계 뒤에 드러난다.
            integrity = audit.integrity_issues(root)
            if integrity:
                raise ValueError("Fast audit integrity failed: "
                                 + "; ".join(str(issue) for issue in integrity[:3]))
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
        _warn(actual_risk, args.level, rounds, lenses, args.reason, run_id,
              language_of(args))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        # 원인만 적으면 사용자는 무엇을 고쳐 어떻게 다시 실행하는지 스스로 재구성해야 한다.
        # 재실행 명령과 "Fast 를 안 써도 된다" 는 출구를 같이 준다 — open 은 실패 시 아무것도
        # 기록하지 않으므로 되돌릴 상태가 없다는 사실이 그 출구의 근거다.
        language = language_of(args)
        print(f"⛔ [sage fast-cycle] open rejected: {exc}", file=sys.stderr)
        print("   " + tr(language, "cli.fast_cycle.open_retry", stem=args.stem,
                         level=args.level, lens_count=args.lens_count), file=sys.stderr)
        print("   " + tr(language, "cli.fast_cycle.open_standard_fallback"), file=sys.stderr)
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
            # 이 표면은 표시 언어와 무관하게 영어다 — 틀이 영어면 하부 진단도 영어로 맞춘다.
            raise ValueError("active clean Fast run required: "
                             + "; ".join(english_text(item) for item in audit_issues[:3]))
        stem = state.get("cycle_stem")
        plan_path = _stem_doc(root, profile, "00", stem)
        content = Path(plan_path).read_text(encoding="utf-8")
        # 전환 run 에는 composite 문서가 없다. 여기서 파싱을 요구하면 전환한 사이클은 abort 말고
        # 나갈 길이 없어진다 — 위험도·완료기준·Phase 04 는 Standard 문서에서 그대로 읽는다.
        converted = state.get("entry_mode") == audit.ENTRY_MODES.get("fast_convert")
        review_snapshot = None
        if converted:
            actual_risk = _convert_risk(content)
            if actual_risk != state.get("actual_risk"):
                raise ValueError("Phase 00 risk no longer matches the converted run")
            _apply_standard_done_criteria_policy(profile, content, include_unresolved=True)
            # current_phase는 전환 당시 provenance의 끝점이다. 리뷰 시점에는 그 뒤에 작성한
            # 필수 01~04도 승인 범위에 들어가므로 최종 pre-report 문서 전체를 다시 증언한다.
            review_snapshot = _source_phase_snapshot(root, profile, stem, "04")
        else:
            plan, issues = parse_fast_plan(content)
            if plan is None or issues:
                raise ValueError("invalid Fast Plan: " + "; ".join(issues[:3]))
            _apply_done_criteria_policy(
                profile, plan, stage="review", include_unresolved=True)
            if plan.metadata.get("Fast-Audit-Run") != args.run_id:
                raise ValueError("Fast Plan run id does not match")
            if "PENDING — implementation not started" in plan.sections.get("04", ""):
                raise ValueError("Phase 04 is still PENDING")
            actual_risk = plan.metadata.get("Risk Level")

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
            # 이 표면은 표시 언어와 무관하게 영어다 — 틀이 영어면 하부 진단도 영어로 맞춘다.
            raise ValueError("Loop Audit invalid or run missing: "
                             + "; ".join(english_text(item) for item in loop_issues[:3]))
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
                            actual_risk=actual_risk, rounds=len(rounds),
                            lens_receipts_hash=receipts_hash,
                            plan_hash_before_review=plan_hash, result="APPROVED",
                            source_phases_review=review_snapshot)
        print(f"[sage fast-cycle] review bound {args.run_id} -> {args.loop_run_id}")
        _warn(actual_risk, state.get("fast_review_level"),
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
        if state.get("entry_mode") == audit.ENTRY_MODES.get("fast_convert"):
            actual_risk = _convert_risk(content)
            _apply_standard_done_criteria_policy(profile, content, include_unresolved=True)
            # 전환 run 의 계획·설계·구현 기록은 Phase 00 밖에 있다. Phase 00 해시만 대조하면
            # 리뷰 뒤 01~04 가 바뀌어도 통과한다 — fresh 는 composite 하나라 그 자리가 없었다.
            reviewed_snapshot = state.get("source_phases_review")
            if not isinstance(reviewed_snapshot, dict) or not reviewed_snapshot:
                raise ValueError("converted review source phase snapshot is missing; run review again")
            current = _source_phase_snapshot(root, profile, stem, "04")
            if current != reviewed_snapshot:
                raise ValueError("phase documents changed after the latest review; "
                                 "run review again")
        else:
            plan, parse_issues = parse_fast_plan(content)
            if plan is None or parse_issues:
                raise ValueError("Fast Plan is invalid at close")
            _apply_done_criteria_policy(
                profile, plan, stage="close", include_unresolved=True)
            actual_risk = plan.metadata.get("Risk Level")
        audit.close_fast(root, args.run_id, loop_run_id=loop_run_id,
                         actual_risk=actual_risk,
                         plan_hash_final=current_hash,
                         report_path=os.path.relpath(report_path, root).replace(os.sep, "/"))
        print(f"[sage fast-cycle] closed {args.run_id}")
        _auto_dashboard(root, language_of(args))
        _warn(actual_risk, state.get("fast_review_level"),
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
    _auto_dashboard(root, language_of(args))
    return 0


def _run_show(args):
    root = _root(args)
    audit = _runtime("fast_cycle_audit")
    summary = audit.audit_summary(root)
    if not summary["file_ok"]:
        for issue in summary["file_issues"]:
            print(f"FAIL: {issue}")
        return 2
    # 표시는 막지 않되 숨기지도 않는다 — `entry=` 를 판별자로 읽는 쪽이 손상 여부를 같이 봐야 한다.
    for issue in audit.integrity_issues(root):
        print(f"⚠️ {english_text(issue)}", file=sys.stderr)
    run_ids = [args.run_id] if args.run_id else sorted(summary["runs"])
    for run_id in run_ids:
        state = summary["runs"].get(run_id)
        if state is None:
            print(f"unknown run: {run_id}", file=sys.stderr)
            return 2
        # entry 는 "문서에 Fast-Audit-Run 이 없는 것이 정상인가" 의 유일한 판별자다 — 없으면
        # 전환 run 과 스탬프에 실패한 fresh open 이 같아 보인다. opener 가 없는 run 은 FAST 로
        # 단정하지 않는다: 스킬이 이 값을 판별자로 쓰므로 확신에 찬 오답이 가장 나쁘다.
        print(f"{run_id} entry={state.get('entry_mode') or 'UNKNOWN'} "
              f"stem={state.get('cycle_stem')} risk={state.get('actual_risk')} "
              f"fast={state.get('fast_review_level')} result={state.get('result') or 'ACTIVE'}")
    if args.vault is not None:
        try:
            _write_dashboard(root, args.vault or None, language_of(args))
        except Exception as exc:
            print(f"⚠️ [sage fast-cycle] vault dashboard failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
    return 0


def _table(value):
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _dashboard_body(root, language=None):
    audit = _runtime("fast_cycle_audit")
    records = audit.read_records(root)
    summary = audit.audit_summary(root)
    rows = []
    for run_id, state in sorted(summary["runs"].items()):
        run_records = [record for record in records if record.get("run_id") == run_id]
        # opener 는 둘이다(fast_open / fast_convert). 리터럴로 한쪽만 보면 전환 run 의 열이 빈다.
        opened = next((record for record in run_records
                       if record.get("event") in audit.OPENER_EVENTS), {})
        reviews = [record for record in run_records if record.get("event") == "fast_review"]
        terminal = next((record for record in reversed(run_records)
                         if record.get("event") in ("fast_close", "fast_abort")), {})
        actual_rounds = reviews[-1].get("rounds") if reviews else "-"
        result = terminal.get("result") or ("ABORTED" if terminal.get("event") == "fast_abort" else "ACTIVE")
        rows.append("| " + " | ".join(_table(value) for value in (
            # `show` 와 같은 판정이어야 한다 — opener 가 사라진 run 을 여기서 FAST 로 적으면
            # 두 산출물이 같은 run 을 반대로 말하고, 노트만 읽는 사람은 그걸 알 수 없다.
            run_id, state.get("entry_mode") or "UNKNOWN",
            state.get("cycle_stem"), state.get("actual_risk"),
            state.get("fast_review_level"), state.get("minimum_rounds"), actual_rounds,
            ", ".join(state.get("lenses") or []), state.get("reason"),
            state.get("loop_run_id") or "-", result,
            opened.get("ts") or "-", terminal.get("ts") or "-")) + " |")
    body = [
        tr(language, "cli.fast_cycle.dashboard_title"), "",
        tr(language, "cli.fast_cycle.dashboard_note"), "",
        # `entry` 는 번역하지 않는다 — 감사 레코드의 값 그대로여야 두 언어 노트를 대조할 수 있다.
        "| run | entry | stem | actual risk | Fast level | min rounds | actual rounds | lenses | reason | Loop run | result | opened | terminal |",
        "|---|---|---|---|---|---:|---:|---|---|---|---|---|---|",
        *(rows or [tr(language, "cli.fast_cycle.dashboard_empty_row")]),
    ]
    issues = audit.integrity_issues(root)
    if issues:
        body.extend(["", tr(language, "cli.fast_cycle.dashboard_integrity_heading"),
                    *[f"- {_table(render_issue(language, issue))}" for issue in issues]])
    return "\n".join(body) + "\n"


def _write_dashboard(root, override=None, language=None):
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
    path = _vault.write_note(vault, folder, filename, frontmatter, _dashboard_body(root, language))
    print(f"[sage fast-cycle] Obsidian dashboard: {path}", file=sys.stderr)


def _auto_dashboard(root, language=None):
    try:
        profile = _profile(root)
        capture = profile.get("knowledge_capture") if isinstance(profile, dict) else None
        if not isinstance(capture, dict) or capture.get("fast_cycle_dashboard") is not True:
            return
        _write_dashboard(root, language=language)
    except Exception as exc:
        print(f"⚠️ [sage fast-cycle] automatic vault dashboard failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)
