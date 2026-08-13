"""sage review-loop — Loop A(Phase 05 적대적 review-rework) 라운드 감사 기록 CLI.

sage-review 스킬이 호스트에서 루프를 돌릴 때, 각 경계(open/round/close)를 이 CLI 로 기록한다 →
SAGE 가 감사 스키마·쓰기를 소유(결정론). 판단(찾기/반박/수정)은 스킬이, 횟수·집계·기록은 SAGE 가.
override.py 가 override_audit 를 래핑하듯, 이 CLI 는 loop_audit 라이브러리를 래핑하고 어휘(result/reason)를
argparse 로 강제한다(라이브러리는 permissive recorder).

감사 로그: <root>/.sage/loop_audit.jsonl (커밋 대상). 종료 backstop(06←05 APPROVED)은 기존 hook 이 담당 —
이 CLI 는 advisory 기록만(루프 자체를 강제하지 않음, 설계 §8 advisory-first).
"""
import os
import sys
import re
import glob

from sage import _resources
from sage.profile_layers import load_profile_layers
from sage.i18n import language_of, tr

# result↔reason 의미 짝(설계 §3) — APPROVED 는 수렴/dry 로만, BLOCKED 는 예산초과/아키텍처로만.
_APPROVED_REASONS = {"CONVERGED", "DRY"}
_BLOCKED_REASONS = {"BUDGET_ITER", "BUDGET_TOK", "BLOCKED_ARCH"}


def _load_loop_audit():
    rt = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks", "runtime")
    if rt not in sys.path:
        sys.path.insert(0, rt)
    import loop_audit as la
    return la


def _load_cycle_binding():
    hooks = _resources.hooks_src_dir()
    if hooks not in sys.path:
        sys.path.insert(0, hooks)
    import cycle_binding
    return cycle_binding


def _nonneg(v):
    """argparse type — 음수/비정수 거부(라운드 카운트는 ≥0 정수)."""
    import argparse
    try:
        n = int(v)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(f"정수가 아님: {v!r}")
    if n < 0:
        raise argparse.ArgumentTypeError(f"음수 불가: {n}")
    return n


def register(sub, context):
    p = sub.add_parser("review-loop", help=tr(context, "cli.review_loop.review_loop"))
    sp = p.add_subparsers(dest="action", metavar="<action>")
    sp.required = True

    po = sp.add_parser("open", help=tr(context, "cli.review_loop.open"))
    po.add_argument("--risk", required=True, choices=["L2", "L3"], help=tr(context, "cli.review_loop.risk"))
    po.add_argument("--run-id", default=None, help=tr(context, "cli.review_loop.run_id"))
    po.add_argument("--reviewer-requested", default=None,
                    help=tr(context, "cli.review_loop.reviewer_requested"))
    po.add_argument("--cycle-stem", default=None, help=tr(context, "cli.review_loop.cycle_stem"))
    po.add_argument("--lenses", default=None, help=tr(context, "cli.review_loop.lenses"))
    po.add_argument("--root", default=None)
    po.set_defaults(func=_run_open)

    pr = sp.add_parser("round", help=tr(context, "cli.review_loop.round"))
    pr.add_argument("--run-id", required=True)
    pr.add_argument("--iteration", required=True, type=_nonneg)
    pr.add_argument("--found", required=True, type=_nonneg, help=tr(context, "cli.review_loop.found"))
    pr.add_argument("--survived", required=True, type=_nonneg, help=tr(context, "cli.review_loop.survived"))
    pr.add_argument("--accepted", required=True, type=_nonneg, help=tr(context, "cli.review_loop.accepted"))
    pr.add_argument("--arch", default=0, type=_nonneg, help=tr(context, "cli.review_loop.arch"))
    pr.add_argument("--tokens", default=0, type=_nonneg, help=tr(context, "cli.review_loop.tokens"))
    pr.add_argument("--lens-receipts", default=None,
                    help=tr(context, "cli.review_loop.lens_receipts"))
    pr.add_argument("--root", default=None)
    pr.set_defaults(func=_run_round)

    pc = sp.add_parser("close", help=tr(context, "cli.review_loop.close"))
    pc.add_argument("--run-id", required=True)
    pc.add_argument("--result", required=True, choices=["APPROVED", "BLOCKED"])
    pc.add_argument("--reason", required=True,
                    choices=sorted(_APPROVED_REASONS | _BLOCKED_REASONS))
    pc.add_argument("--iterations", required=True, type=_nonneg)
    pc.add_argument("--reviewer-actual", default=None,
                    help=tr(context, "cli.review_loop.reviewer_actual"))
    pc.add_argument("--root", default=None)
    pc.set_defaults(func=_run_close)

    ps = sp.add_parser("show", help=tr(context, "cli.review_loop.show"))
    ps.add_argument("--run-id", default=None, help=tr(context, "cli.review_loop.run_id_2"))
    ps.add_argument("--vault", nargs="?", const="", default=None,
                    help=tr(context, "cli.review_loop.vault"))
    ps.add_argument("--root", default=None)
    ps.set_defaults(func=_run_show)

    pn = sp.add_parser("next", help=tr(context, "cli.review_loop.next"))
    pn.add_argument("--run-id", required=True)
    pn.add_argument("--root", default=None)
    pn.set_defaults(func=_run_next)


def _find_project_root(start):
    """프로젝트 루트 탐색(codex S3 P1) — cwd 의존 제거. 서브디렉토리에서 실행해도 open/round/close 가
    같은 <root>/.sage/loop_audit.jsonl 과 같은 profile 을 본다. 마커 = sage/project-profile.yaml(설치 항상 배치).
    못 찾으면 cwd 로 폴백(genuine no-profile). 무관한 조상 .sage 로 잘못 해석하지 않도록 profile 단일 마커만
    상향 탐색한다(codex S3: stray-.sage 오해석 위험 제거 — Loop A 는 profile 이 있어야 동작하므로 충분)."""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(cur, "sage", "project-profile.yaml")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())   # 폴백: cwd(no-profile = Loop A 비대상 컨텍스트)
        cur = parent


def _root(args):
    # --root 명시 시 그대로(테스트/명시 제어), 아니면 cwd 상향 탐색(서브디렉토리 robust).
    return os.path.abspath(args.root) if args.root else _find_project_root(os.getcwd())


def _load_profile(root):
    """공유·로컬 profile의 유효 설정. 로컬 실패 시 공유 정책을 보존한다."""
    ppath = os.path.join(root, "sage", "project-profile.yaml")
    if not os.path.exists(ppath):
        return {}
    layers = load_profile_layers(ppath)
    return layers.shared if layers.has_fail else layers.effective


def _validated_profile(root, language=None):
    """게이트 판단용 profile. 설치되지 않은 저장소는 legacy {}, 손상된 계층은 FAIL."""
    ppath = os.path.join(root, "sage", "project-profile.yaml")
    if not os.path.exists(ppath):
        return {}
    layers = load_profile_layers(ppath)
    failures = [message for severity, message in layers.issues if severity == "FAIL"]
    if not failures:
        return layers.effective
    for message in failures:
        print(tr(language, "cli.review_loop.msg01", message=message, layers_shared_path=layers.shared_path, layers_local_path=layers.local_path), file=sys.stderr)
    return None


def _cfg_snapshot(root, profile=None):
    """profile.pdca.review_loop 스냅샷(있으면) — open 레코드에 적용 설정 기록용. 없으면 {}."""
    profile = _load_profile(root) if profile is None else profile
    rl = ((profile.get("pdca") or {}).get("review_loop")) or {}
    return rl if isinstance(rl, dict) else {}


def _is_open(la, root, run_id):
    """run_id 에 loop_open 이 있는지(CLI 강제용 — orphan round/close 차단, codex S3 P2)."""
    return run_id in set(la.runs(root))


def _is_closed(la, root, run_id):
    """run_id 가 이미 loop_close 됐는지(round/close-after-close 차단, codex S3 강화)."""
    return la.close_of(root, run_id) is not None


def _write_audit(la, operation, language=None):
    """Convert fail-closed audit writer failures into the CLI's blocking contract."""
    try:
        return operation()
    except (la.AuditWriteError, OSError) as exc:
        print(tr(language, "cli.review_loop.msg02", exc=exc), file=sys.stderr)
        return None


def _comma_list(value):
    if value is None:
        return None
    items = [item.strip() for item in value.split(",")]
    if not items or any(not item for item in items) or len(items) != len(set(items)):
        raise ValueError("comma list must contain unique non-empty values")
    return items


def _run_open(args):
    la = _load_loop_audit()
    root = _root(args)
    profile = _validated_profile(root, language_of(args))
    if profile is None:
        return 2
    # 명시 run_id 중복 open 거부(integrity 불변식을 write 시점에 강제 — strict CLI 레이어).
    if args.run_id and _is_open(la, root, args.run_id):
        print(tr(language_of(args), "cli.review_loop.msg03", args_run_id=args.run_id), file=sys.stderr)
        return 2
    try:
        lenses = _comma_list(args.lenses)
    except ValueError as exc:
        print(f"[sage review-loop] --lenses invalid: {exc}", file=sys.stderr)
        return 2
    rid = _write_audit(
        la,
        lambda: la.open_loop(root, args.risk, cfg=_cfg_snapshot(root, profile),
                             run_id=args.run_id,
                             reviewer_requested=args.reviewer_requested,
                             cycle_stem=args.cycle_stem, lenses=lenses),
        language=language_of(args),
    )
    if rid is None:
        return 2
    print(rid)   # stdout = run_id 만(스킬이 캡처해 후속 round/close 에 전달)
    print(f"[sage review-loop] open run_id={rid} risk={args.risk} → {la.audit_path(root)}", file=sys.stderr)
    return 0


def _run_round(args):
    la = _load_loop_audit()
    root = _root(args)
    # orphan 차단: loop_open 없는 run_id 의 round 거부(codex S3 P2 — CLI 가 integrity 를 write 시 강제).
    if not _is_open(la, root, args.run_id):
        print(tr(language_of(args), "cli.review_loop.msg04", args_run_id=args.run_id), file=sys.stderr)
        return 2
    if _is_closed(la, root, args.run_id):
        print(tr(language_of(args), "cli.review_loop.msg05", args_run_id=args.run_id), file=sys.stderr)
        return 2
    # 불가능 튜플 거부(순수 산술, 읽기 불요): survived ≤ found, accepted ≤ survived, arch ≤ survived.
    #   (REFUTE 는 발견 부분집합, REWORK 채택은 생존 부분집합, arch 에스컬레이션은 생존 중 분류.)
    if args.survived > args.found:
        print(tr(language_of(args), "cli.review_loop.msg06", args_survived=args.survived, args_found=args.found), file=sys.stderr)
        return 2
    if args.accepted > args.survived:
        print(tr(language_of(args), "cli.review_loop.msg07", args_accepted=args.accepted, args_survived=args.survived), file=sys.stderr)
        return 2
    if args.arch > args.survived:
        print(tr(language_of(args), "cli.review_loop.msg08", args_arch=args.arch, args_survived=args.survived), file=sys.stderr)
        return 2
    try:
        lens_receipts = _comma_list(args.lens_receipts)
    except ValueError as exc:
        print(f"[sage review-loop] --lens-receipts invalid: {exc}", file=sys.stderr)
        return 2
    written = _write_audit(
        la,
        lambda: la.record_round(root, args.run_id, args.iteration, args.found,
                                args.survived, args.accepted, arch=args.arch,
                                tokens=args.tokens, lens_receipts=lens_receipts),
        language=language_of(args),
    )
    if written is None:
        return 2
    print(f"[sage review-loop] round {args.iteration} run_id={args.run_id} "
          f"found={args.found} survived={args.survived} accepted={args.accepted} arch={args.arch}", file=sys.stderr)
    return 0


def _run_risk(la, root, run_id):
    """run_id 의 loop_open 에 기록된 risk (없으면 None)."""
    for r in la.read_records(root):
        if r.get("event") == "loop_open" and r.get("run_id") == run_id:
            return r.get("risk")
    return None


def _open_record(la, root, run_id):
    return next((record for record in la.read_records(root)
                 if record.get("event") == "loop_open" and record.get("run_id") == run_id), None)


def _phase_docs(root, profile, phase):
    pdca = profile.get("pdca") if isinstance(profile.get("pdca"), dict) else {}
    entry = next((item for item in (pdca.get("phases") or [])
                  if isinstance(item, dict) and str(item.get("id") or "") == phase), None)
    pattern = (entry or {}).get("glob") or ""
    if not pattern or os.path.isabs(pattern) or ".." in pattern.replace("\\", "/").split("/"):
        raise ValueError(f"safe Phase {phase} glob is required in pdca.phases")
    docs = []
    root_real = os.path.realpath(root)
    for path in glob.glob(os.path.join(root, pattern), recursive=True):
        path_real = os.path.realpath(path)
        try:
            contained = os.path.commonpath((root_real, path_real)) == root_real
        except ValueError:
            contained = False
        if not contained:
            raise ValueError(f"Phase {phase} document escapes project root: {path}")
        if not os.path.isfile(path) or os.path.islink(path):
            continue
        with open(path_real, encoding="utf-8") as fh:
            content = fh.read()
        docs.append({"path": os.path.relpath(path, root).replace(os.sep, "/"), "content": content})
    return docs


def _approved_phase00_hash(la, root, profile, run_id):
    """Return the current Phase 00 hash or a mode-scoped approval issue."""
    pdca = profile.get("pdca") if isinstance(profile.get("pdca"), dict) else {}
    base_plan = pdca.get("base_plan") if isinstance(pdca.get("base_plan"), dict) else {}
    mode = base_plan.get("done_criteria_gate", "off")
    if mode == "off":
        return None, None, mode
    if mode not in ("advisory", "enforce"):
        return None, f"invalid pdca.base_plan.done_criteria_gate={mode!r}", "enforce"
    opened = _open_record(la, root, run_id) or {}
    stem = opened.get("cycle_stem")
    if not isinstance(stem, str) or not stem:
        return None, "review-loop open record has no --cycle-stem", mode

    binding = _load_cycle_binding()
    selected, error = binding.select_document(_phase_docs(root, profile, "00"), stem)
    if error:
        return None, f"Phase 00 exact cycle selection failed: {error}", mode
    from sage.done_criteria_contract import document_revision, parse_done_criteria, phase00_text_hash
    content = selected.get("content") or ""
    parse_mode = "fast" if re.search(r"(?m)^Cycle-Mode:\s*FAST\s*$", content) else "standard"
    result = parse_done_criteria(content, mode=parse_mode)
    if result.status != "valid":
        return None, "Phase 00 Done Criteria invalid: " + "; ".join(result.issues[:3]), mode
    if result.unresolved:
        pending = "; ".join(f"line {item.line}: {item.text}" for item in result.unresolved[:3])
        return None, f"Phase 00 Done Criteria unresolved={len(result.unresolved)}: {pending}", mode

    if parse_mode == "standard" and result.latest_revision is not None:
        stale = []
        for phase in result.latest_revision.affected_phases:
            phase_doc, phase_error = binding.select_document(_phase_docs(root, profile, phase), stem)
            if phase_error:
                stale.append(f"{phase}: {phase_error}")
                continue
            revision, revision_issues = document_revision(phase_doc.get("content"))
            if revision_issues or revision != result.revision:
                stale.append(f"{phase}: revision={revision!r}, expected={result.revision}")
        if stale:
            return None, "affected Phase rerun is stale: " + "; ".join(stale[:3]), mode
    return phase00_text_hash(content), None, mode


def _termination_discrepancies(la, root, run_id, result, reason, iterations, cfg, risk):
    """기록된 라운드 + cfg(review_loop)로 close 의 result/reason 일관성 검산 → [(kind, msg)].
    kind: 'mismatch'(사실과 모순 — enforce 가 거부) | 'skip'(cfg/데이터 부족으로 검증 불가 — 항상 WARN, 차단 안 함).
    7.8단계 A. 결정론(LLM 0, audit 사실 vs cfg 산술 비교만, codex 리뷰 A 반영)."""
    out = []
    rounds = la.rounds_of(root, run_id)
    if not rounds:
        # 라운드 0 — 수렴/승인을 뒷받침할 증거 없음(codex P1). BLOCKED 는 즉시차단 가능하므로 미해당.
        if result == "APPROVED" or reason in ("CONVERGED", "DRY"):
            out.append(("mismatch", "라운드 기록 0 — 루프가 돈 증거 없는데 수렴/승인 주장"))
        else:
            out.append(("skip", "라운드 기록 0 — 검산할 사실 없음"))
        return out
    last_survived = int(rounds[-1].get("survived", 0) or 0)
    total_tokens = max((int(r.get("tokens", 0) or 0) for r in rounds), default=0)  # tokens=누적 → max=총량
    any_arch = any(int(r.get("arch", 0) or 0) > 0 for r in rounds)

    def _tier_int(section):
        m = cfg.get(section) if isinstance(cfg.get(section), dict) else {}
        v = m.get(risk)
        return v if isinstance(v, int) and not isinstance(v, bool) else None
    budget = _tier_int("budget_tokens")
    max_iter = _tier_int("max_iterations")
    dry = cfg.get("dry_rounds") if isinstance(cfg.get("dry_rounds"), int) and not isinstance(cfg.get("dry_rounds"), bool) else None

    # APPROVED/CONVERGED 는 미해결(survived>0)과 공존 불가 (cfg 불요)
    if result == "APPROVED" and last_survived > 0:
        out.append(("mismatch", f"APPROVED 인데 마지막 라운드 survived={last_survived}(미해결 남음) — 수렴 아님"))
    if reason == "CONVERGED" and last_survived > 0:
        out.append(("mismatch", f"CONVERGED 인데 마지막 라운드 survived={last_survived}(0 이어야)"))
    # 예산(cfg 필요): APPROVED 면 미초과, BUDGET_TOK 면 초과여야. budget 미설정 → skip+WARN
    if reason == "BUDGET_TOK" or (result == "APPROVED"):
        if budget is None:
            out.append(("skip", f"budget_tokens[{risk}] 미설정 — 예산 검산 skip"))
        else:
            if result == "APPROVED" and total_tokens >= budget:
                out.append(("mismatch", f"APPROVED 인데 누적 tokens={total_tokens} ≥ budget={budget} — BUDGET_TOK/BLOCKED 여야"))
            if reason == "BUDGET_TOK" and total_tokens < budget:
                out.append(("mismatch", f"BUDGET_TOK 인데 누적 tokens={total_tokens} < budget={budget}(초과 아님)"))
    # 반복 상한(cfg 필요): BUDGET_ITER 면 상한 도달 AND 미수렴(survived>0). max 미설정 → skip
    if reason == "BUDGET_ITER":
        if max_iter is None:
            out.append(("skip", f"max_iterations[{risk}] 미설정 — 반복상한 검산 skip"))
        else:
            if int(iterations) < max_iter:
                out.append(("mismatch", f"BUDGET_ITER 인데 iterations={iterations} < max[{risk}]={max_iter}(상한 미도달)"))
            if last_survived == 0:
                out.append(("mismatch", "BUDGET_ITER 인데 마지막 survived=0(수렴함 — CONVERGED 여야)"))
    # 아키텍처 에스컬레이션(cfg 불요)
    if reason == "BLOCKED_ARCH" and not any_arch:
        out.append(("mismatch", "BLOCKED_ARCH 인데 arch>0 인 라운드 없음"))
    # dry 수렴(cfg 필요): 마지막 dry 라운드가 각각 found==0. dry 미설정 → skip
    if reason == "DRY":
        if dry is None:
            out.append(("skip", "dry_rounds 미설정 — dry 검산 skip"))
        elif len(rounds) < dry or any(int(r.get("found", 0) or 0) > 0 for r in rounds[-dry:]):
            out.append(("mismatch", f"DRY 인데 마지막 {dry} 라운드에 found>0(신규 있음) 또는 라운드 부족"))
    return out


def _run_close(args):
    # result↔reason 의미 짝 강제(감사 트레일 일관성). 라이브러리는 permissive 이므로 여기서 게이트.
    if args.result == "APPROVED" and args.reason not in _APPROVED_REASONS:
        print(tr(language_of(args), "cli.review_loop.msg09", arg=sorted(_APPROVED_REASONS), args_reason=args.reason), file=sys.stderr)
        return 2
    if args.result == "BLOCKED" and args.reason not in _BLOCKED_REASONS:
        print(tr(language_of(args), "cli.review_loop.msg10", arg=sorted(_BLOCKED_REASONS), args_reason=args.reason), file=sys.stderr)
        return 2
    la = _load_loop_audit()
    root = _root(args)
    if not _is_open(la, root, args.run_id):
        print(tr(language_of(args), "cli.review_loop.msg11", args_run_id=args.run_id), file=sys.stderr)
        return 2
    if _is_closed(la, root, args.run_id):
        print(tr(language_of(args), "cli.review_loop.msg12", args_run_id=args.run_id), file=sys.stderr)
        return 2

    profile = _validated_profile(root, language_of(args))
    if profile is None:
        return 2

    # 7.8단계 A — 종료 결정론 검산: 기록된 라운드 + cfg 로 close 가 사실과 일관한지 검산(codex 리뷰 A 반영).
    cfg = ((profile.get("pdca") or {}).get("review_loop")) or {}
    cfg = cfg if isinstance(cfg, dict) else {}
    raw_mode = cfg.get("termination_enforce", "advisory")
    mode = raw_mode if raw_mode in ("advisory", "enforce") else "advisory"
    if raw_mode != mode:   # 미지 mode 는 침묵 말고 알림(런타임 fail-open 방지)
        print(tr(language_of(args), "cli.review_loop.msg13", raw_mode=raw_mode), file=sys.stderr)
    # audit 무결성 경고(손상/orphan) 있으면 라운드 사실을 못 믿으므로 enforce 라도 advisory 로 degrade(§2).
    integ = la.integrity_issues(root)
    if integ and mode == "enforce":
        print(tr(language_of(args), "cli.review_loop.msg14", count=len(integ)), file=sys.stderr)
        mode = "advisory"
    risk = _run_risk(la, root, args.run_id)
    checks = _termination_discrepancies(la, root, args.run_id, args.result, args.reason, args.iterations, cfg, risk)
    mismatches = [m for k, m in checks if k == "mismatch"]
    for _, m in [(k, m) for k, m in checks if k == "skip"]:
        print(tr(language_of(args), "cli.review_loop.msg15", m=m), file=sys.stderr)
    if mismatches:
        for m in mismatches:
            print(tr(language_of(args), "cli.review_loop.msg16", m=m), file=sys.stderr)
        if mode == "enforce":
            print(tr(language_of(args), "cli.review_loop.msg17"), file=sys.stderr)
            return 2
        print(tr(language_of(args), "cli.review_loop.msg18"),
              file=sys.stderr)

    phase00_hash = None
    if args.result == "APPROVED":
        try:
            phase00_hash, done_issue, done_mode = _approved_phase00_hash(
                la, root, profile, args.run_id)
        except (OSError, UnicodeError, ValueError) as exc:
            done_issue = f"Done Criteria approval check failed: {type(exc).__name__}: {exc}"
            done_mode = "enforce"
        if done_issue:
            print(tr(language_of(args), "cli.review_loop.msg19", done_issue=done_issue), file=sys.stderr)
            if done_mode == "enforce":
                return 2
            print(tr(language_of(args), "cli.review_loop.msg20"), file=sys.stderr)

    written = _write_audit(
        la,
        lambda: la.close_loop(root, args.run_id, args.result, args.reason,
                              args.iterations,
                              reviewer_actual=args.reviewer_actual,
                              phase00_hash=phase00_hash),
        language=language_of(args),
    )
    if written is None:
        return 2
    print(f"[sage review-loop] close run_id={args.run_id} {args.result}/{args.reason} iterations={args.iterations}", file=sys.stderr)
    if phase00_hash is not None:
        print(f"Phase00-Hash: {phase00_hash}", file=sys.stderr)
    _auto_write_vault_dashboard(la, root, language_of(args))
    return 0


def _run_show(args):
    la = _load_loop_audit()
    root = _root(args)
    print(f"== sage review-loop --show ({la.audit_path(root)}) ==")
    integ = la.integrity_issues(root)
    target_runs = [args.run_id] if args.run_id else la.runs(root)
    if not target_runs:
        print(tr(language_of(args), "cli.review_loop.msg21"))
    for rid in target_runs:
        rounds = la.rounds_of(root, rid)
        close = la.close_of(root, rid)
        status = f"{close['result']}/{close['reason']} ({close['iterations']}회)" if close else "진행중(미종료)"
        print(tr(language_of(args), "cli.review_loop.msg22", rid=rid, status=status, count=len(rounds)))
        if close and close.get("phase00_hash"):
            print(f"      Phase00-Hash: {close['phase00_hash']}")
        for r in rounds:
            print(f"      [{r.get('iteration')}] found={r.get('found')} survived={r.get('survived')} "
                  f"accepted={r.get('accepted')} arch={r.get('arch')} tokens={r.get('tokens')}")
    if integ:
        print(tr(language_of(args), "cli.review_loop.msg23"))
        for i in integ:
            print(f"   - {i}")

    if args.vault is not None:
        _write_vault_dashboard(la, root, args.vault or None, language_of(args))
    return 1 if integ else 0


def _next_recommendation(la, root, run_id, cfg, risk):
    """기록된 라운드 + cfg(review_loop)로 '계속 vs 종료'를 결정론 권고한다(LLM 0, 감사 기록 0).
    _termination_discrepancies 와 같은 신호(survived/tokens/arch + cfg tier)를 쓰되, 사후 검산이
    아니라 전향 권고를 낸다. 반환: (action, result, reason, why, skips).
    action == 'STOP' 이면 result/reason 은 close 에 그대로 넘길 값. 권고는 사실 기반이라, 자료가
    부족한 축(cfg tier 미설정)은 STOP 을 권하지 않고 skip 사유만 남긴다(false STOP 방지)."""
    rounds = la.rounds_of(root, run_id)

    def _tier_int(section):
        m = cfg.get(section) if isinstance(cfg.get(section), dict) else {}
        v = m.get(risk)
        return v if isinstance(v, int) and not isinstance(v, bool) else None
    budget = _tier_int("budget_tokens")
    max_iter = _tier_int("max_iterations")

    skips = []
    if budget is None:
        skips.append(f"budget_tokens[{risk}] 미설정 — 예산 초과 종료 권고 불가")
    if max_iter is None:
        skips.append(f"max_iterations[{risk}] 미설정 — 반복상한 종료 권고 불가")

    if not rounds:
        return ("CONTINUE", None, None, "라운드 기록 0 — 첫 라운드부터 진행", skips)

    iterations = len(rounds)
    last_survived = int(rounds[-1].get("survived", 0) or 0)
    total_tokens = max((int(r.get("tokens", 0) or 0) for r in rounds), default=0)  # tokens=누적 → max=총량
    any_arch = any(int(r.get("arch", 0) or 0) > 0 for r in rounds)
    converged = last_survived == 0

    # 우선순위: 아키텍처 > 예산 > 반복상한 > 수렴 > 계속.
    if any_arch:
        return ("STOP", "BLOCKED", "BLOCKED_ARCH",
                "아키텍처 에스컬레이션 기록됨(arch>0) — 루프 밖 상위 결정 필요", skips)
    if budget is not None and total_tokens >= budget:
        return ("STOP", "BLOCKED", "BUDGET_TOK",
                f"누적 tokens={total_tokens} ≥ budget[{risk}]={budget}", skips)
    if max_iter is not None and iterations >= max_iter:
        if converged:
            return ("STOP", "APPROVED", "CONVERGED",
                    f"반복 상한 도달(iter={iterations}=max[{risk}]={max_iter}) + 마지막 survived=0(수렴)", skips)
        return ("STOP", "BLOCKED", "BUDGET_ITER",
                f"반복 상한 도달(iter={iterations}=max[{risk}]={max_iter}) + survived={last_survived}(미수렴)", skips)
    if converged:
        return ("STOP", "APPROVED", "CONVERGED", "마지막 라운드 survived=0 — 미해결 없음(수렴)", skips)
    return ("CONTINUE", None, None,
            f"마지막 survived={last_survived}(미해결 남음), 예산·반복상한 여유 — 라운드 계속", skips)


def _run_next(args):
    la = _load_loop_audit()
    root = _root(args)
    if not _is_open(la, root, args.run_id):
        print(tr(language_of(args), "cli.review_loop.msg24", args_run_id=args.run_id), file=sys.stderr)
        return 2
    if _is_closed(la, root, args.run_id):
        close = la.close_of(root, args.run_id)
        print(tr(language_of(args), "cli.review_loop.msg25", args_run_id=args.run_id, arg=close['result'], arg2=close['reason']), file=sys.stderr)
        print("NEXT: DONE")
        return 0
    profile = _validated_profile(root, language_of(args))
    if profile is None:
        return 2
    cfg = _cfg_snapshot(root, profile)
    risk = _run_risk(la, root, args.run_id)
    action, result, reason, why, skips = _next_recommendation(la, root, args.run_id, cfg, risk)
    for s in skips:
        print(tr(language_of(args), "cli.review_loop.msg26", s=s), file=sys.stderr)
    print(tr(language_of(args), "cli.review_loop.msg27", why=why), file=sys.stderr)
    if action == "CONTINUE":
        print("NEXT: CONTINUE")
    else:
        print(f"NEXT: STOP result={result} reason={reason}")
        print(tr(language_of(args), "cli.review_loop.msg28", args_run_id=args.run_id, result=result, reason=reason, count=len(la.rounds_of(root, args.run_id))), file=sys.stderr)
    print(tr(language_of(args), "cli.review_loop.msg29"), file=sys.stderr)
    return 0


def _wiki_stem(filename):
    """Obsidian wikilink target = filename without .md."""
    return os.path.splitext(os.path.basename(filename))[0]


def _frontmatter_run_id(path):
    """Best-effort frontmatter run_id reader for retro notes. No YAML dependency here."""
    try:
        with open(path, encoding="utf-8") as f:
            txt = f.read(4096)
    except Exception:
        return None
    if not txt.startswith("---"):
        return None
    end = txt.find("\n---", 3)
    if end == -1:
        return None
    fm = txt[3:end]
    m = re.search(r"(?m)^run_id:\s*['\"]?([^'\"\n]+)['\"]?\s*$", fm)
    return m.group(1).strip() if m else None


def _retro_links_by_run(vault, folder):
    """Return {run_id: ['[[retro note]]', ...]} for existing retro human-gate notes."""
    if not vault or not folder:
        return {}
    base = os.path.join(vault, folder)
    try:
        names = os.listdir(base)
    except OSError:
        return {}
    out = {}
    for name in names:
        lower = name.lower()
        if (not name.endswith(".md") or
                not (re.search(r"(^|[\s_.-])retro([\s_.-]|$)", lower) or lower.startswith("sage-retro-"))):
            continue
        rid = _frontmatter_run_id(os.path.join(base, name))
        if not rid:
            continue
        out.setdefault(rid, []).append(f"[[{_wiki_stem(name)}]]")
    for links in out.values():
        links.sort()
    return out


def _dashboard_md(la, root, retro_links=None):
    """loop_audit → Obsidian 대시보드 마크다운(plain 테이블 — DataView 플러그인 무관 항상 가독).
    run 별 1행: run_id·risk·rounds·found/accepted 합계·종료. 무결성 경고 섹션."""
    retro_links = retro_links or {}
    rows = []
    for rid in la.runs(root):
        rounds = la.rounds_of(root, rid)
        close = la.close_of(root, rid)
        risk = next((r.get("risk") for r in la.read_records(root)
                     if r.get("event") == "loop_open" and r.get("run_id") == rid), "")
        f_tot = sum(int(r.get("found", 0) or 0) for r in rounds)
        a_tot = sum(int(r.get("accepted", 0) or 0) for r in rounds)
        status = f"{close['result']}/{close['reason']}" if close else "진행중"
        iters = close["iterations"] if close else len(rounds)
        retro = ", ".join(retro_links.get(rid, [])) or "-"
        rows.append(f"| {rid} | {risk} | {len(rounds)} | {f_tot} | {a_tot} | {status} | {iters} | {retro} |")
    from sage.commands._common import _project_name
    from sage.commands.knowledge import _safe_title
    # 파일명(_note_filename)과 동일하게 개행/구분자를 정규화 — 정규화 안 하면 project.name 에
    # 섞인 개행(`\n## x`)이 H1 본문에 살아 대시보드가 주입 헤딩으로 깨진다.
    name = _project_name(_load_profile(root))
    title_suffix = f" — {_safe_title(name)}" if name else ""
    body = [f"# SAGE Loop A 감사 대시보드{title_suffix}", "",
            "> Phase 05 적대적 review-rework 루프 이력. `accepted` 합계 = 리뷰가 채운 host 의 체계적 누락.",
            "> 정본 데이터: `.sage/loop_audit.jsonl`. 이 노트는 `sage review-loop show --vault` 또는 `loop_audit_dashboard: true` 상태의 close 로 갱신.", "",
            "| run_id | risk | rounds | found(합) | accepted(합) | 종료 | iters | retro |",
            "|---|---|---:|---:|---:|---|---:|---|"]
    body += rows or ["| (기록 없음) | | | | | | | |"]
    integ = la.integrity_issues(root)
    if integ:
        body += ["", "## ⚠️ 무결성 경고", ""] + [f"- {i}" for i in integ]
    return "\n".join(body) + "\n"


def _dashboard_filename(profile):
    """loop audit 대시보드 파일명 — vault note_convention + project.name 파생.

    프로젝트당 1페이지(예: `TECH - weatherapp loop audit.md`)로, close 마다 같은 파일을
    덮어쓰기 갱신한다(run 별 페이지 난립 방지). 여러 프로젝트가 한 vault 를 공유해도 파일명이
    프로젝트별로 갈려 서로 덮어쓰지 않는다. write-back 노트와 동일한 `_note_filename` 을 재사용해
    vault 명명 관례(prefix·filename_pattern)를 그대로 따른다. project.name 이 비면 'SAGE' 폴백."""
    from sage.commands.knowledge import _note_filename
    from sage.commands._common import _project_name
    name = _project_name(profile) or "SAGE"
    return _note_filename(profile, "TECH", f"{name} loop audit")


def _write_vault_dashboard(la, root, override, language=None):
    from sage.commands import _vault
    profile = _load_profile(root)
    vault, folder = _vault.vault_target(profile, override, root)
    if not vault:
        print(tr(language, "cli.review_loop.msg30"), file=sys.stderr)
        return
    import datetime
    fm = {"tags": ["sage", "loop-audit"], "updated": datetime.date.today().isoformat(),
          "generated_by": "sage review-loop (close 자동 / show --vault)"}
    path = _vault.write_note(vault, folder, _dashboard_filename(profile), fm,
                             _dashboard_md(la, root, _retro_links_by_run(vault, folder)))
    print(tr(language, "cli.review_loop.msg31", path=path), file=sys.stderr)


def _auto_write_vault_dashboard(la, root, language=None):
    """profile opt-in 이면 close 직후 vault 대시보드를 갱신한다.

    `loop_audit_dashboard` 는 사람이 별도 `show --vault` 를 실행해야 하는 힌트가 아니라
    loop close 의 side artifact opt-in 이다. 실패해도 audit close 자체는 이미 성공했으므로
    non-fatal WARN 으로 표면화한다.
    """
    profile = _load_profile(root)
    kc = profile.get("knowledge_capture") if isinstance(profile, dict) else {}
    kc = kc if isinstance(kc, dict) else {}
    if kc.get("loop_audit_dashboard") is not True:
        return
    try:
        _write_vault_dashboard(la, root, None, language)
    except Exception as e:
        print(tr(language, "cli.review_loop.msg32", arg=type(e).__name__, e=e), file=sys.stderr)
