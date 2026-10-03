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
import math

from sage import _resources
from sage.diagnostics import Diagnostic
from sage.profile_layers import load_profile_layers
from sage.i18n import language_of, render_issue, tr

# result↔reason 의미 짝(설계 §3) — APPROVED 는 수렴/dry 로만, BLOCKED 는 예산초과/아키텍처로만.
_RESIDUAL_REASON = "CONVERGED_RESIDUAL"
_APPROVED_REASONS = {"CONVERGED", "DRY", "USER_AUTHORIZED_EARLY", _RESIDUAL_REASON}
_EARLY_REASON = "USER_AUTHORIZED_EARLY"
_CRITICAL_REASON = "CRITICAL_P2"
# 크리티컬 P2 결정 대기 중에도 닫을 수 있는 사유. 판정 순위가 크리티컬 질문보다 앞선다.
_CLOSE_DURING_CRITICAL = {"BLOCKED_ARCH", "BUDGET_TOK"}
_EARLY_AUTHORIZATION_ARGS = ("authorization_reason", "confirmed_by", "confirm")
# 상한 미설정을 화면과 감사가 같은 단어로 말한다. 예전에는 화면이 `unset`, 감사가 `-1` 이라
# 같은 사실이 두 곳에서 다른 모양이었고, 대시보드는 그 `-1` 을 `2/-1 rounds` 로 냈다.
# `loop_audit` 이 정본이지만 그 모듈 import 는 런타임 경로 주입 뒤에만 가능해 여기 상수로 둔다.
_UNBOUNDED_LABEL = "unbounded"
_CYCLE_CAP_REASON = "CYCLE_CAP"
_BLOCKED_REASONS = {"BUDGET_ITER", "BUDGET_TOK", "BLOCKED_ARCH", _CYCLE_CAP_REASON}
# 조기 종료(잔여 승인)를 받을 수 있는 `next` 판정. 반복 상한·사이클 상한은 "남은 것을 보고
# 사람이 정하라" 는 지점이라 허용하고, 예산 초과·아키텍처 에스컬레이션은 사용자 승인으로 덮을 수
# 없는 BLOCKED 라 허용하지 않는다. 수렴은 정상 close 가 있으므로 허용하지 않는다.
_EARLY_ALLOWED_VERDICTS = {("CONTINUE", None), ("STOP", "BUDGET_ITER"), ("ASK", _CYCLE_CAP_REASON)}
_GIT_TIMEOUT_S = 30


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


def _load_runtime(name):
    rt = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks", "runtime")
    if rt not in sys.path:
        sys.path.insert(0, rt)
    import importlib
    return importlib.import_module(name)


def _nonneg_of(context):
    """argparse type 콜러블을 만든다 — 음수/비정수 거부(라운드 카운트는 ≥0 정수).

    argparse 는 type 콜러블에 args 를 넘기지 않으므로 `language_of(args)` 를 쓸 수 없다.
    parser 를 세울 때 이미 결정된 표시 언어를 닫아두면, 파싱 실패 문장도 나머지 화면과 같은
    언어로 나온다.
    """
    import argparse

    def _nonneg(v):
        try:
            n = int(v)
        except (ValueError, TypeError):
            raise argparse.ArgumentTypeError(
                tr(context, "cli.review_loop.not_an_integer", value=repr(v)))
        if n < 0:
            raise argparse.ArgumentTypeError(
                tr(context, "cli.review_loop.negative_not_allowed", n=n))
        return n
    return _nonneg


def register(sub, context):
    _nonneg = _nonneg_of(context)
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
    # 사이드카가 있으면 개수는 사이드카에서 산출하고, 손으로 준 값은 일치 검사에만 쓴다.
    # 그래서 argparse 가 아니라 `_run_round` 가 "사이드카가 없을 때만 필수" 를 강제한다.
    pr.add_argument("--found", default=None, type=_nonneg, help=tr(context, "cli.review_loop.found"))
    pr.add_argument("--survived", default=None, type=_nonneg, help=tr(context, "cli.review_loop.survived"))
    pr.add_argument("--accepted", default=None, type=_nonneg, help=tr(context, "cli.review_loop.accepted"))
    pr.add_argument("--arch", default=None, type=_nonneg, help=tr(context, "cli.review_loop.arch"))
    pr.add_argument("--findings-file", default=None,
                    help=tr(context, "cli.review_loop.findings_file"))
    pr.add_argument("--tokens", default=0, type=_nonneg, help=tr(context, "cli.review_loop.tokens"))
    pr.add_argument("--peer-tokens", default=None,
                    help=tr(context, "cli.review_loop.peer_tokens"))
    pr.add_argument("--lens-receipts", default=None,
                    help=tr(context, "cli.review_loop.lens_receipts"))
    pr.add_argument("--survived-by-severity", default=None,
                    help=tr(context, "cli.review_loop.survived_by_severity"))
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
    pc.add_argument("--authorization-reason", default=None,
                    help=tr(context, "cli.review_loop.authorization_reason"))
    pc.add_argument("--confirmed-by", default=None,
                    help=tr(context, "cli.review_loop.confirmed_by"))
    pc.add_argument("--confirm", default=None,
                    help=tr(context, "cli.review_loop.confirm"))
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

    pd = sp.add_parser("decide", help=tr(context, "cli.review_loop.decide"))
    pd.add_argument("--run-id", required=True)
    # 두 형태 중 하나다: 사이클 상한의 `--cycle continue --extend N`, 크리티컬 P2 의
    # `--finding <id> --claim <hash> --fix|--accept`. 섞였는지는 `_run_decide` 가 본다.
    pd.add_argument("--cycle", default=None, choices=["continue"],
                    help=tr(context, "cli.review_loop.decide_cycle"))
    pd.add_argument("--extend", default=None, type=_nonneg,
                    help=tr(context, "cli.review_loop.decide_extend"))
    pd.add_argument("--finding", default=None, help=tr(context, "cli.review_loop.decide_finding"))
    pd.add_argument("--claim", default=None, help=tr(context, "cli.review_loop.decide_claim"))
    choice = pd.add_mutually_exclusive_group()
    choice.add_argument("--fix", action="store_const", const="fix", dest="critical_choice",
                        help=tr(context, "cli.review_loop.decide_fix"))
    choice.add_argument("--accept", action="store_const", const="accept", dest="critical_choice",
                        help=tr(context, "cli.review_loop.decide_accept"))
    pd.add_argument("--reason", required=True, help=tr(context, "cli.review_loop.decide_reason"))
    pd.add_argument("--decided-by", required=True,
                    help=tr(context, "cli.review_loop.decide_decided_by"))
    pd.add_argument("--root", default=None)
    pd.set_defaults(func=_run_decide)

    pl = sp.add_parser("ledger", help=tr(context, "cli.review_loop.ledger"))
    lsp = pl.add_subparsers(dest="ledger_action", metavar="<action>")
    lsp.required = True
    la_add = lsp.add_parser("add", help=tr(context, "cli.review_loop.ledger_add"))
    la_add.add_argument("--cycle-stem", default=None, help=tr(context, "cli.review_loop.ledger_stem"))
    la_add.add_argument("--kind", required=True, choices=["out_of_scope", "preexisting", "withdraw"])
    la_add.add_argument("--source", default=None, help=tr(context, "cli.review_loop.ledger_source"))
    la_add.add_argument("--reason", required=True)
    la_add.add_argument("--severity", default=None, choices=["P0", "P1", "P2", "P3"])
    la_add.add_argument("--location", default=None)
    la_add.add_argument("--ref", default=None, help=tr(context, "cli.review_loop.ledger_ref"))
    la_add.add_argument("--root", default=None)
    la_add.set_defaults(func=_run_ledger_add)
    for name in ("show", "render"):
        lp = lsp.add_parser(name, help=tr(context, f"cli.review_loop.ledger_{name}"))
        lp.add_argument("--cycle-stem", default=None,
                        help=tr(context, "cli.review_loop.ledger_stem"))
        lp.add_argument("--root", default=None)
        lp.set_defaults(func=_run_ledger_show if name == "show" else _run_ledger_render)


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
        print(tr(language, "cli.review_loop.msg01", message=render_issue(language, message),
                 layers_shared_path=layers.shared_path, layers_local_path=layers.local_path),
              file=sys.stderr)
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


def _open_cycle_stem(root, explicit, language):
    """open 이 run 에 묶을 사이클 stem. 못 정하면 None(거부 문구는 여기서 낸다).

    사이클 라운드 상한은 같은 stem 의 run 을 합쳐 센다. stem 없이 열린 run 은 그 집계에서 빠지므로,
    결속을 선택으로 두면 상한을 우회하는 run 이 생긴다. 해석은 게이트와 같은 `resolve_stem`(env > 파일)
    이다 — 다른 해석기를 쓰면 게이트가 보는 사이클과 루프가 세는 사이클이 갈린다.
    """
    binding = _load_cycle_binding()
    cycle_state = _load_runtime("cycle_state")
    try:
        resolved, origin, error = cycle_state.resolve_stem(root)
    except Exception as exc:  # noqa: BLE001 - 선언을 못 읽으면 "없다" 가 아니라 실패다
        resolved, origin, error = "", "", f"{type(exc).__name__}: {exc}"
    if error:
        print(tr(language, "cli.review_loop.cycle_declaration_issue",
                 error=render_issue(language, error)), file=sys.stderr)
    stem = explicit if explicit is not None else resolved
    normalized = binding.normalize_stem(stem) if stem else None
    if not normalized:
        print(tr(language, "cli.review_loop.cycle_stem_required"), file=sys.stderr)
        return None
    if explicit is not None and resolved and binding.normalize_stem(resolved) != normalized:
        print(tr(language, "cli.review_loop.cycle_stem_differs", explicit=normalized,
                 resolved=resolved, origin=origin), file=sys.stderr)
    return normalized


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
    stem = _open_cycle_stem(root, args.cycle_stem, language_of(args))
    if stem is None:
        return 2
    fast_minimum = _fast_minimum_rounds(root, stem)
    rid = _write_audit(
        la,
        lambda: la.open_loop(root, args.risk, cfg=_cfg_snapshot(root, profile),
                             run_id=args.run_id,
                             reviewer_requested=args.reviewer_requested,
                             cycle_stem=stem, lenses=lenses,
                             fast_minimum_rounds=fast_minimum),
        language=language_of(args),
    )
    if rid is None:
        return 2
    print(rid)   # stdout = run_id 만(스킬이 캡처해 후속 round/close 에 전달)
    print(f"[sage review-loop] open run_id={rid} risk={args.risk} → {la.audit_path(root)}", file=sys.stderr)
    return 0


def _fast_cycle_audit():
    rt = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks", "runtime")
    if rt not in sys.path:
        sys.path.insert(0, rt)
    import fast_cycle_audit as fca
    return fca


def _fast_minimum_rounds(root, stem):
    """같은 사이클의 살아 있는 Fast run 이 정확히 하나면 그 최소 라운드. 아니면 None.

    Loop 가 이 값보다 먼저 수렴해 승인으로 닫히면 `sage fast-cycle review` 가 거부하는데, 닫힌
    run 에는 라운드를 더 붙일 수 없다. open 시점에 적어 두면 `next` 가 그 전까지 계속을 권한다.
    Fast 를 쓰지 않는 프로젝트가 대부분이라 읽기 실패는 「없음」으로 둔다.
    """
    try:
        runs = _fast_cycle_audit().audit_summary(root).get("runs") or {}
    except Exception:  # noqa: BLE001 - Fast 미사용·감사 없음은 정상
        return None
    live = [state for state in runs.values()
            if state.get("cycle_stem") == stem and not state.get("terminal")
            and state.get("clean") is not False]
    if len(live) != 1:
        return None
    value = live[0].get("minimum_rounds")
    return value if type(value) is int and value > 0 else None


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
    records = la.read_records(root)
    state = la.run_cycle_state(records, args.run_id)
    if state is not None and state["reached"]:
        print(tr(language_of(args), "cli.review_loop.round_cycle_cap", stem=state["stem"],
                 rounds=state["rounds"], cap=state["cap"], run_id=args.run_id), file=sys.stderr)
        return 2
    pending = la.pending_critical(records, args.run_id)
    if pending:
        print(tr(language_of(args), "cli.review_loop.round_critical_pending", run_id=args.run_id,
                 findings=", ".join(pending)), file=sys.stderr)
        return 2
    policy = la.run_policy(records, args.run_id)
    sidecar_doc = None
    if args.findings_file is not None:
        rounds_mod = _load_runtime("review_rounds")
        try:
            with open(args.findings_file, "rb") as handle:
                data = handle.read(rounds_mod.MAX_SIDECAR_BYTES + 1)
            sidecar_doc = rounds_mod.parse(data, run_id=args.run_id, iteration=args.iteration)
        except OSError as exc:
            print(f"[sage review-loop] --findings-file unreadable: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            return 2
        except rounds_mod.SidecarError as exc:
            print(f"[sage review-loop] --findings-file invalid: {exc}", file=sys.stderr)
            return 2
        if policy["converge_on"] == "blocking":
            problems = rounds_mod.policy_issues(sidecar_doc, policy)
            if problems:
                more = "" if len(problems) <= 5 else f"; ... and {len(problems) - 5} more"
                print(tr(language_of(args), "cli.review_loop.round_policy_invalid",
                         issues="; ".join(problems[:5]) + more), file=sys.stderr)
                return 2
        derived = rounds_mod.derive(sidecar_doc)
        mismatched = [f"--{name.replace('_', '-')}={getattr(args, name)} != {derived[name]}"
                      for name in ("found", "survived", "accepted", "arch")
                      if getattr(args, name) is not None and getattr(args, name) != derived[name]]
        if args.survived_by_severity is not None:
            try:
                manual = _severity_receipt(args.survived_by_severity)
            except ValueError as exc:
                print(f"[sage review-loop] --survived-by-severity invalid: {exc}", file=sys.stderr)
                return 2
            if manual != derived["survived_by_severity"]:
                mismatched.append(f"--survived-by-severity {manual} != "
                                  f"{derived['survived_by_severity']}")
        if mismatched:
            print("[sage review-loop] counts disagree with --findings-file: "
                  + "; ".join(mismatched), file=sys.stderr)
            return 2
        for name in ("found", "survived", "accepted", "arch"):
            setattr(args, name, derived[name])
        args.survived_by_severity = ",".join(
            f"{key}={value}" for key, value in derived["survived_by_severity"].items())
    else:
        missing = [f"--{name}" for name in ("found", "survived", "accepted")
                   if getattr(args, name) is None]
        if missing:
            print(tr(language_of(args), "cli.review_loop.round_counts_required",
                     missing=", ".join(missing)), file=sys.stderr)
            return 2
        if args.arch is None:
            args.arch = 0
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
    try:
        receipt = _severity_receipt(args.survived_by_severity)
    except ValueError as exc:
        print(f"[sage review-loop] --survived-by-severity invalid: {exc}", file=sys.stderr)
        return 2
    if receipt is not None:
        issues = la.severity_receipt_issues(receipt, args.survived)
        if issues:
            print("[sage review-loop] --survived-by-severity invalid: " + "; ".join(issues),
                  file=sys.stderr)
            return 2
    try:
        peer_usage = parse_peer_tokens(getattr(args, "peer_tokens", None))
    except ValueError as exc:
        print(f"[sage review-loop] --peer-tokens invalid: {exc}", file=sys.stderr)
        return 2
    sidecar_ref, round_receipt, tree = "absent", None, None
    if sidecar_doc is not None:
        side_peer = sidecar_doc["usage"]["peer"]
        if side_peer is not None and peer_usage is not None and side_peer != peer_usage:
            print("[sage review-loop] --findings-file usage.peer disagrees with --peer-tokens "
                  "(--peer-tokens is the measured value; copy it into the sidecar verbatim)",
                  file=sys.stderr)
            return 2
        rounds_mod = _load_runtime("review_rounds")
        try:
            sidecar_ref = rounds_mod.store(root, sidecar_doc)
        except (OSError, rounds_mod.SidecarError) as exc:
            print(f"[sage review-loop] sidecar could not be stored: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            return 2
        round_receipt = rounds_mod.derive(sidecar_doc)["receipt"]
    # 작업 트리 식별자는 사이드카와 무관하게 라운드마다 남긴다. 한 라운드라도 빠지면 다음 delta 가
    # 「직전 라운드 대비」가 아니게 된다.
    tree = _round_tree(la, _load_runtime("review_rounds"), root, args.run_id, args.iteration)
    written = _write_audit(
        la,
        lambda: la.record_round(root, args.run_id, args.iteration, args.found,
                                args.survived, args.accepted, arch=args.arch,
                                tokens=args.tokens, lens_receipts=lens_receipts,
                                survived_by_severity=receipt, peer_usage=peer_usage,
                                sidecar=sidecar_ref, receipt=round_receipt, tree=tree),
        language=language_of(args),
    )
    if written is None:
        return 2
    print(f"[sage review-loop] round {args.iteration} run_id={args.run_id} "
          f"found={args.found} survived={args.survived} accepted={args.accepted} arch={args.arch}", file=sys.stderr)
    return 0


def _git(root, *argv, env=None, binary=False):
    import subprocess
    result = subprocess.run(["git", *argv], cwd=root, capture_output=True, env=env,
                            timeout=_GIT_TIMEOUT_S)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else f"git {argv[0]} exited {result.returncode}")
    return result.stdout if binary else result.stdout.decode("utf-8", "replace").strip()


def _previous_tree(la, records, run_id):
    """직전 라운드의 tree → (식별자 또는 None, 없을 때의 사유 또는 None).

    직전 라운드는 같은 run 의 마지막 라운드, run 의 첫 라운드면 같은 사이클의 마지막 라운드다. 그
    라운드에 식별자가 없으면(업그레이드 전 기록·git 실패) 더 앞 라운드로 건너뛰지 않는다 — 건너뛰면
    patch 가 두 라운드 이상의 변경을 「직전 대비」로 담는다.
    """
    def _last(run_ids):
        found = None
        for record in records:
            if record.get("event") == "round" and record.get("run_id") in run_ids:
                found = record
        return found
    previous = _last({run_id})
    if previous is None:
        state = la.run_cycle_state(records, run_id)
        previous = _last(set(state["runs"]) - {run_id}) if state else None
    if previous is None:
        return None, "first_round"
    tree = previous.get("tree")
    if isinstance(tree, dict) and isinstance(tree.get("id"), str):
        return tree["id"], None
    return None, "previous_round_without_tree"


def _round_tree(la, rounds_mod, root, run_id, iteration):
    """라운드 시점 작업 트리 식별자와 직전 라운드 대비 delta.

    임시 index 로 `git add -A` → `git write-tree` 를 한다. 실제 index 는 건드리지 않는다. 임시
    index 를 실제 index 의 사본에서 시작하는 이유는 바뀌지 않은 파일의 재해시를 피하려는 것이다.
    계측이라 실패가 라운드를 막지 않는다 — 사유만 남긴다.
    """
    import shutil
    records = la.read_records(root)
    prev, prev_note = _previous_tree(la, records, run_id)
    tree = {"id": None, "prev": prev, "patch": None, "note": None}
    workdir = None
    try:
        import tempfile
        top = _git(root, "rev-parse", "--show-toplevel")
        index = _git(root, "rev-parse", "--git-path", "index")
        index = index if os.path.isabs(index) else os.path.join(root, index)
        workdir = tempfile.mkdtemp(prefix="sage-round-index-")
        temp_index = os.path.join(workdir, "index")
        if os.path.isfile(index):
            shutil.copyfile(index, temp_index)
        env = dict(os.environ, GIT_INDEX_FILE=temp_index)
        # `.sage/` 는 SAGE 가 라운드마다 쓰는 곳이다(감사·사이드카). 프로젝트가 git 무시로 두지
        # 않았어도 빼야 delta 가 리뷰 대상 변경만 담는다.
        sage_rel = os.path.relpath(os.path.join(os.path.realpath(root), ".sage"),
                                   os.path.realpath(top)).replace(os.sep, "/")
        _git(top, "add", "-A", "--", ".", f":(exclude){sage_rel}", env=env)
        tree["id"] = _git(top, "write-tree", env=env)
        if prev is None:
            tree["note"] = prev_note
        elif prev != tree["id"]:
            patch = _git(top, "diff", "--binary", prev, tree["id"], binary=True)
            if patch:
                tree["patch"] = rounds_mod.store_patch(root, run_id, iteration, patch)
    except Exception as exc:  # noqa: BLE001 - git 없음·저장소 아님·시간 초과 모두 계측 실패일 뿐
        tree["note"] = f"git_unavailable: {type(exc).__name__}: {str(exc)[:200]}"
    finally:
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)
    return tree


_PEER_TOKEN_KEYS = {"new_input": int, "cached_input": int, "output": int, "turns": int,
                    "tool_calls": int, "wall_s": int, "cost_usd": float}
# 끊긴 실행을 메시지별 usage 로 추정한 값이면 `measured=partial` 이 붙는다.
_PEER_TOKEN_MEASURED = frozenset({"partial"})


def parse_peer_tokens(text):
    """`sage cross-check` 의 `REVIEWER_TOKENS:` 값 → dict, "unknown", 또는 None(인자 없음).

    값을 그대로 옮겨 적게 한다 — 호스트가 추정치를 넣던 자리를 실측으로 바꾸는 것이 목적이다.
    """
    if text is None:
        return None
    text = text.strip()
    if text.startswith("REVIEWER_TOKENS:"):
        text = text[len("REVIEWER_TOKENS:"):].strip()
    if text == "unknown":
        return "unknown"
    out = {}
    for part in text.split():
        key, sep, value = part.partition("=")
        if key == "measured" and sep:
            if value not in _PEER_TOKEN_MEASURED:
                raise ValueError(f"measured must be one of {sorted(_PEER_TOKEN_MEASURED)}")
            out[key] = value
            continue
        if not sep or key not in _PEER_TOKEN_KEYS:
            raise ValueError(f"unexpected field {part!r}")
        try:
            number = _PEER_TOKEN_KEYS[key](value)
        except ValueError:
            raise ValueError(f"{key} is not a number: {value!r}") from None
        if not math.isfinite(number):
            raise ValueError(f"{key} is not a finite number: {value!r}")
        if number < 0:
            raise ValueError(f"{key} is negative")
        out[key] = number
    if not {"new_input", "output"} <= set(out):
        raise ValueError("new_input and output are required (or pass 'unknown')")
    return out


def budget_tokens_of(rounds):
    """예산 판정 총량. 정의는 hook runtime `loop_audit` 에 있다 — 훅과 CLI 가 같은 값을 써야 한다."""
    return _load_loop_audit().budget_tokens_of(rounds)


def unmeasured_peer_rounds(rounds):
    """peer 사용량을 모르는 라운드 수. 정의는 `loop_audit` 에 있다."""
    return _load_loop_audit().unmeasured_peer_rounds(rounds)


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
    """기록된 라운드 + cfg(review_loop)로 close 의 result/reason 일관성 검산 → [(kind, Diagnostic)].
    kind: 'mismatch'(사실과 모순 — enforce 가 거부) | 'skip'(cfg/데이터 부족으로 검증 불가 — 항상 WARN, 차단 안 함).
    7.8단계 A. 결정론(LLM 0, audit 사실 vs cfg 산술 비교만, codex 리뷰 A 반영).

    검산 결과는 언어 중립 진단이다 — 여기서 문장을 만들면 같은 모순이 표시 언어마다 다른
    문자열로 남아, enforce 거부 사유를 나중에 대조할 수 없다. 문장은 `_run_close` 가 만든다."""
    out = []
    rounds = la.rounds_of(root, run_id)
    if not rounds:
        # 라운드 0 — 수렴/승인을 뒷받침할 증거 없음(codex P1). BLOCKED 는 즉시차단 가능하므로 미해당.
        if result == "APPROVED" or reason in ("CONVERGED", "DRY"):
            out.append(("mismatch", Diagnostic("review_loop.term_no_rounds_claims_convergence")))
        elif reason == _CYCLE_CAP_REASON:
            # 앞 run 들이 사이클 상한을 다 쓴 뒤 열린 run 은 라운드 0 에서 멈출 수 있다. 사이클
            # 상한 사실은 이 run 의 라운드가 아니라 사이클 집계에서 확인한다.
            state = la.run_cycle_state(la.read_records(root), run_id)
            if state is None or not state["reached"]:
                out.append(("mismatch", Diagnostic(
                    "review_loop.term_cycle_cap_not_reached",
                    rounds=(state or {}).get("rounds", 0), cap=(state or {}).get("cap", 0))))
        else:
            out.append(("skip", Diagnostic("review_loop.term_no_rounds_nothing_to_check")))
        return out
    last_survived = int(rounds[-1].get("survived", 0) or 0)
    total_tokens = budget_tokens_of(rounds)
    any_arch = any(int(r.get("arch", 0) or 0) > 0 for r in rounds)

    def _tier_int(section):
        m = cfg.get(section) if isinstance(cfg.get(section), dict) else {}
        v = m.get(risk)
        return v if isinstance(v, int) and not isinstance(v, bool) else None
    budget = _tier_int("budget_tokens")
    max_iter = _tier_int("max_iterations")
    dry = cfg.get("dry_rounds") if isinstance(cfg.get("dry_rounds"), int) and not isinstance(cfg.get("dry_rounds"), bool) else None

    # 조기 완료는 정의상 "미해결 비차단 finding 이 남은 채 APPROVED" 다 — 그게 이 기능의 내용이다.
    # 잔여는 감사 레코드의 severity 영수증에 숫자로 남고 05/06 이 보증 저하를 표기한다. 여기서
    # 수렴 검산을 적용하면 모든 조기 종료가 "사실과 모순" 으로 잡혀, enforce 프로젝트에서는 기능이
    # 통째로 죽고 advisory 에서는 매번 거짓 경고가 찍힌다.
    if reason == la.EARLY_CLOSE_REASON:
        return out
    # 잔여 승인도 생존을 안고 닫는 것이 그 기능이다. 대신 그 run 이 `blocking` 으로 열렸고 판정이
    # 정말 그 사유인지를 본다 — 아니면 일반 승인이 잔여를 숨긴 것이다.
    if reason == _RESIDUAL_REASON:
        records = la.read_records(root)
        if la.run_policy(records, run_id)["converge_on"] != "blocking":
            out.append(("mismatch", Diagnostic("review_loop.term_residual_not_blocking")))
        else:
            verdict = la.loop_verdict(records, run_id, cfg, risk)
            if (verdict["action"], verdict["reason"]) != ("STOP", _RESIDUAL_REASON):
                out.append(("mismatch", Diagnostic("review_loop.term_residual_verdict",
                                                   action=verdict["action"],
                                                   reason=verdict["reason"])))
        return out
    # APPROVED/CONVERGED 는 미해결(survived>0)과 공존 불가 (cfg 불요)
    if result == "APPROVED" and last_survived > 0:
        out.append(("mismatch", Diagnostic("review_loop.term_approved_with_survivors",
                                           survived=last_survived)))
    if reason == "CONVERGED" and last_survived > 0:
        out.append(("mismatch", Diagnostic("review_loop.term_converged_with_survivors",
                                           survived=last_survived)))
    # 예산(cfg 필요): APPROVED 면 미초과, BUDGET_TOK 면 초과여야. budget 미설정 → skip+WARN
    if reason == "BUDGET_TOK" or (result == "APPROVED"):
        if budget is None:
            out.append(("skip", Diagnostic("review_loop.term_budget_unset", risk=risk)))
        else:
            unmeasured = unmeasured_peer_rounds(rounds)
            if unmeasured:
                # 예산 안이라는 판정이 실제보다 낮은 총량에서 나왔을 수 있다 — 모순은 아니라 skip 으로 알린다.
                out.append(("skip", Diagnostic("review_loop.term_peer_usage_unknown", rounds=unmeasured)))
            if result == "APPROVED" and total_tokens >= budget:
                out.append(("mismatch", Diagnostic("review_loop.term_approved_over_budget",
                                                   tokens=total_tokens, budget=budget)))
            if reason == "BUDGET_TOK" and total_tokens < budget:
                out.append(("mismatch", Diagnostic("review_loop.term_budget_tok_under_budget",
                                                   tokens=total_tokens, budget=budget)))
    # 반복 상한(cfg 필요): BUDGET_ITER 면 상한 도달 AND 미수렴(survived>0). max 미설정 → skip
    if reason == "BUDGET_ITER":
        if max_iter is None:
            out.append(("skip", Diagnostic("review_loop.term_max_iterations_unset", risk=risk)))
        else:
            if int(iterations) < max_iter:
                out.append(("mismatch", Diagnostic("review_loop.term_budget_iter_below_max",
                                                   iterations=iterations, risk=risk,
                                                   max_iterations=max_iter)))
            if last_survived == 0:
                out.append(("mismatch", Diagnostic("review_loop.term_budget_iter_converged")))
    # 사이클 상한(open cfg 스냅샷): CYCLE_CAP 이면 사이클 라운드가 상한에 닿아 있어야 한다.
    if reason == _CYCLE_CAP_REASON:
        state = la.run_cycle_state(la.read_records(root), run_id)
        if state is None:
            out.append(("mismatch", Diagnostic("review_loop.term_cycle_cap_unbound")))
        elif not state["reached"]:
            out.append(("mismatch", Diagnostic("review_loop.term_cycle_cap_not_reached",
                                               rounds=state["rounds"], cap=state["cap"])))
    # 아키텍처 에스컬레이션(cfg 불요)
    if reason == "BLOCKED_ARCH" and not any_arch:
        out.append(("mismatch", Diagnostic("review_loop.term_blocked_arch_without_arch")))
    # dry 수렴(cfg 필요): 마지막 dry 라운드가 각각 found==0. dry 미설정 → skip
    if reason == "DRY":
        if dry is None:
            out.append(("skip", Diagnostic("review_loop.term_dry_rounds_unset")))
        elif len(rounds) < dry or any(int(r.get("found", 0) or 0) > 0 for r in rounds[-dry:]):
            out.append(("mismatch", Diagnostic("review_loop.term_dry_not_dry", dry=dry)))
    return out


def _severity_receipt(raw):
    """`P0=0,P1=0,P2=2,P3=0` 를 매핑으로. 미지정은 None(레거시 호환)이다."""
    if raw is None:
        return None
    receipt = {}
    for chunk in str(raw).split(","):
        item = chunk.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"expected SEVERITY=COUNT, got {item!r}")
        key, _, value = item.partition("=")
        key = key.strip().upper()
        if key in receipt:
            raise ValueError(f"duplicate severity {key}")
        try:
            receipt[key] = int(value.strip())
        except ValueError:
            raise ValueError(f"{key} count must be an integer") from None
    return receipt


def _early_completion_policy(cfg):
    """리뷰 조기 완료 opt-in. 키 부재는 비활성이고 하한은 엔진이 1로 고정한다.

    반환은 (정책, 이유) 다. 둘을 합쳐 `None` 하나로 돌려주면 "옵트인이 꺼져 있다" 와 "하한이
    잘못 적혀 있다" 가 같은 진단을 받는다 — `enabled: true` 를 분명히 적은 사용자가 "enabled=true
    가 필요하다" 는 말을 듣고 무엇을 고칠지 알 수 없게 된다. 하한 진단의 정본은 `validate` 지만
    이 명령은 그 경로를 지나지 않으므로 여기서 직접 말한다.
    """
    block = cfg.get("early_completion")
    if not isinstance(block, dict) or block.get("enabled") is not True:
        return None, "pdca.review_loop.early_completion.enabled=true is required"
    floor = block.get("minimum_completed_rounds", 1)
    if type(floor) is not int or floor < 1:
        return None, ("pdca.review_loop.early_completion.minimum_completed_rounds must be an "
                      f"integer of at least 1 (found {floor!r}); `sage validate` reports the same")
    return {"minimum_completed_rounds": floor}, None


def _phase00_identity(la, root, profile, run_id):
    """조기 종료 레코드에 실을 (Phase 00 hash, Done Criteria revision).

    `done_criteria_gate` 가 `off` 여도 계산한다 — 이 두 값은 게이트 설정이 아니라 사후 stale 판정의
    축이다. 조기 승인 뒤 Phase 00 이나 revision 이 바뀌면 그 승인은 낡은 것인데, 레코드에 기준이
    없으면 바뀐 사실을 확인할 방법이 사라진다.
    """
    opened = _open_record(la, root, run_id) or {}
    stem = opened.get("cycle_stem")
    if not isinstance(stem, str) or not stem:
        return None, None
    try:
        binding = _load_cycle_binding()
        selected, error = binding.select_document(_phase_docs(root, profile, "00"), stem)
        if error or not selected:
            return None, None
        from sage.done_criteria_contract import document_revision, phase00_text_hash
        content = selected.get("content") or ""
        revision, revision_issues = document_revision(content)
        return phase00_text_hash(content), (None if revision_issues else revision)
    except (OSError, UnicodeError, ValueError):
        return None, None


def _load_gate_core():
    hooks = _resources.hooks_src_dir()
    if hooks not in sys.path:
        sys.path.insert(0, hooks)
    import pre_implementation_gate_core
    return pre_implementation_gate_core


def _acceptance_blockers(la, root, args, profile, risk):
    """미해결 acceptance 가 조기 완료를 막는가.

    조기 완료는 **잔여 리뷰 findings** 를 사용자 권한으로 인수하는 절차다. 요구사항이 FAIL 이거나
    승인 없이 `NOT TESTED` 인 것은 리뷰가 남긴 잔여가 아니라 검증되지 않은 기능이고, 그 둘은 인수
    대상이 다르다. 06 report 게이트가 어차피 막지만 그때는 05 가 이미 조기 승인으로 닫힌 뒤라,
    감사에는 "축약된 리뷰로 승인" 만 남고 무엇이 미검증이었는지는 남지 않는다.

    판정은 06 과 **같은 정책·같은 파서**를 쓴다. 여기서 규칙을 새로 적으면 06 이 막는 상태를 조기
    완료가 통과시키거나 그 반대가 되고, 어느 쪽이든 두 층이 같은 문서에 다른 답을 내는 상태다.
    L3 exact waiver 로 잔여가 된 `NOT TESTED` 는 여기서도 막지 않는다 — 그건 이미 명시 승인된
    잔여 위험이고, 조기 완료가 인수하는 것과 같은 종류다.
    """
    try:
        core = _load_gate_core()
    except Exception as exc:  # noqa: BLE001 - 게이트 코어를 못 읽으면 판정 자체가 불가능하다
        return [f"acceptance check failed: {type(exc).__name__}: {exc}"]
    # `open` 은 `--risk` 를 L2/L3 로 강제하므로 정상 run 에는 항상 값이 있다. 없는 것은 손질된
    # 기록이고, 그때 검사를 끄면 위험도를 지우는 것이 곧 우회가 된다 — 게이트와 같은 `unknown`
    # 으로 넘겨 가장 엄격한 정책을 받는다.
    policy = core.acceptance_policy(profile, risk if risk in ("L1", "L2", "L3") else "unknown")
    if policy is None:
        return []   # 이 위험도에서 acceptance 를 강제하지 않는 프로젝트 — 없던 검사를 켜지 않는다
    opened = _open_record(la, root, args.run_id) or {}
    stem = opened.get("cycle_stem")
    if not isinstance(stem, str) or not stem:
        return ["review-loop open record has no --cycle-stem"]
    binding = _load_cycle_binding()
    selected = {}
    for phase in ("01", "04"):
        document, error = binding.select_document(_phase_docs(root, profile, phase), stem)
        if error:
            return [f"Phase {phase} exact cycle selection failed: {error}"]
        selected[phase] = document
    structural, unresolved_rows = core.acceptance_findings(
        selected["01"].get("content") or "", selected["04"].get("content") or "", policy,
        plan_path=selected["01"].get("path"), report_path=selected["04"].get("path"))
    if structural:
        return [f"acceptance evidence unreadable: {structural[0]}"]
    if not unresolved_rows:
        return []
    try:
        rt = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks", "runtime")
        if rt not in sys.path:
            sys.path.insert(0, rt)
        import acceptance_waiver
        waivers = acceptance_waiver.audit_summary(root)
    except Exception as exc:  # noqa: BLE001
        # 승인 대장을 읽지 못하면 "승인이 없다" 가 아니라 "모른다" 다. 없는 것으로 치면 승인된
        # 잔여가 막히고, 유효한 것으로 치면 대장을 지우는 것이 곧 승인이 된다.
        waivers = {"valid": False, "active": [],
                   "issues": [f"{type(exc).__name__}: {exc}"]}
    remaining, _uses = core.acceptance_waiver_split(
        unresolved_rows, policy, risk if risk in ("L1", "L2", "L3") else "unknown", stem, waivers,
        report_path=selected["04"].get("path"))
    if not remaining:
        return []
    lines = [row["detail"] for row in remaining]
    more = "" if len(lines) <= 3 else f"; ... and {len(lines) - 3} more"
    return ["unresolved acceptance must be resolved or waived before an early close: "
            + "; ".join(lines[:3]) + more]


def _early_close_blockers(la, root, args, profile, cfg, risk, language):
    """조기 종료를 막아야 하는 상태 전부. 하나라도 걸리면 append 0건이다."""
    blockers = []
    policy, policy_issue = _early_completion_policy(cfg)
    if policy is None:
        return [policy_issue]
    for name in _EARLY_AUTHORIZATION_ARGS:
        if not (getattr(args, name, None) or "").strip():
            blockers.append(f"--{name.replace('_', '-')} must be a non-empty line")
    if args.confirm is not None and args.confirm != _EARLY_REASON:
        blockers.append(f"--confirm must be exactly {_EARLY_REASON}")
    if args.result != "APPROVED":
        blockers.append(f"{_EARLY_REASON} closes are APPROVED only")

    rounds = la.rounds_of(root, args.run_id)
    if len(rounds) < policy["minimum_completed_rounds"]:
        blockers.append(f"at least {policy['minimum_completed_rounds']} completed round(s) required; "
                        f"recorded={len(rounds)}")
    if args.iterations != len(rounds):
        blockers.append(f"--iterations must equal the recorded rounds ({len(rounds)})")
    if la.integrity_issues(root):
        blockers.append("loop audit integrity failed")

    receipt = (rounds[-1].get("survived_by_severity") if rounds else None)
    if not isinstance(receipt, dict):
        blockers.append("the last round has no survived_by_severity receipt; "
                        "legacy runs cannot close early. Record one more round with "
                        "--survived-by-severity, or close normally once the loop converges")
    else:
        issues = la.severity_receipt_issues(receipt, rounds[-1].get("survived", 0))
        if issues:
            blockers.append("last round severity receipt invalid: " + "; ".join(issues))
        elif la.run_policy(la.read_records(root), args.run_id)["converge_on"] == "blocking":
            # 차단 기준 수렴 run 은 통일 수렴식으로 본다 — 결정 없는 크리티컬·「수정」으로 정한
            # 크리티컬도 차단이고, 「수용」으로 정한 크리티컬은 차단이 아니다.
            verdict = la.loop_verdict(la.read_records(root), args.run_id, cfg, risk)
            state = verdict.get("convergence") or {}
            if not state.get("receipt"):
                blockers.append("converge_on: blocking needs a sidecar receipt on the last round "
                                "to show the blocking findings are zero")
            elif state.get("blocking_open"):
                blockers.append(f"blocking findings remain unresolved: "
                                f"blocking_open={state['blocking_open']}")
        else:
            blocking = [s for s in (cfg.get("severity_block") or ["P0", "P1"])
                        if isinstance(s, str)]
            unresolved = {s: receipt.get(s, 0) for s in blocking if int(receipt.get(s, 0)) > 0}
            if unresolved:
                blockers.append(f"blocking severities remain unresolved: {unresolved}")

    # 설계상 "사용자 확인으로도 통과할 수 없는 상태" 에 Done Criteria 미해결이 들어 있다. 일반
    # close 는 advisory 에서 경고만 내고 통과시키지만, 조기 종료에서는 그 경고가 곧 인수 대상이
    # 되므로 mode 와 무관하게 막는다. gate 가 `off` 인 프로젝트에 없던 검사를 새로 켜지는 않는다.
    try:
        _hash, done_issue, done_mode = _approved_phase00_hash(la, root, profile, args.run_id)
    except (OSError, UnicodeError, ValueError) as exc:
        done_issue, done_mode = f"Done Criteria check failed: {type(exc).__name__}: {exc}", "enforce"
    if done_issue and done_mode in ("advisory", "enforce"):
        blockers.append(f"Phase 00 Done Criteria must be resolved: {done_issue}")


    blockers.extend(_acceptance_blockers(la, root, args, profile, risk))

    action, result, reason, _why, _skips = _next_recommendation(la, root, args.run_id, cfg, risk)
    if (action, reason) not in _EARLY_ALLOWED_VERDICTS:
        if action == "STOP" and result == "APPROVED":
            # 정상 승인이 가능한 상태에서 조기 종료를 쓰면 정상 승인이 보증 저하로 잘못 기록된다.
            blockers.append(f"normal close is available ({result}/{reason}); use it instead")
        elif action == "ASK" and reason == _CRITICAL_REASON:
            blockers.append("critical P2 findings await the developer's decision; record each "
                            "with `sage review-loop decide --finding <id> --claim <hash> --fix|--accept` first")
        else:
            # 예산 초과·아키텍처 에스컬레이션은 사용자 확인으로 덮을 수 없는 BLOCKED 다.
            blockers.append(f"{action} {result}/{reason} cannot be closed by user authorization")
    elif action == "ASK" and not rounds:
        blockers.append("this run has no completed round; authorize the residual on the run that "
                        "reached the cap, or decide to continue")
    return blockers


def _stopped_at(action, reason):
    """조기 종료 시점의 `next` 판정을 감사에 남길 한 단어."""
    return "CONTINUE" if action == "CONTINUE" else f"{action}:{reason}"


def _fast_run_id(la, root, loop_run_id):
    """이 Loop run 이 속한 Fast run(있으면). Standard 면 None 이다.

    **결속 축은 cycle stem 이다.** 예전에는 Fast run 이 적어 둔 `loop_run_id` 를 역방향으로 찾았는데,
    그 값을 심는 것은 `sage fast-cycle review` 이고 그건 Loop 가 닫힌 **뒤**에 실행된다. 그래서 close
    시점에는 어떤 Fast run 도 이 Loop 를 가리키지 않아 `mode` 가 구조적으로 FAST 가 될 수 없었다 —
    조기 종료 감사가 예외 없이 STANDARD 로 기록됐다. stem 은 open 시점에 이미 양쪽에 있다.

    살아있는 후보가 둘 이상이면 어느 쪽인지 정할 수 없으므로 None 이다. 여기서 아무거나 고르면
    기록이 틀린 run 을 가리키고, 그건 결속이 없는 것보다 나쁘다.
    """
    try:
        fca = _fast_cycle_audit()
    except Exception:  # noqa: BLE001 - Fast 미사용 프로젝트에서 결속 정보가 없는 것은 정상
        return None
    open_record = _open_record(la, root, loop_run_id)
    stem = (open_record or {}).get("cycle_stem")
    try:
        summary = fca.audit_summary(root)
    except Exception:  # noqa: BLE001
        return None
    runs = summary.get("runs") or {}
    for rid, state in runs.items():
        if state.get("loop_run_id") == loop_run_id:
            return rid
    if not stem:
        return None
    live = [rid for rid, state in runs.items()
            if state.get("cycle_stem") == stem and not state.get("terminal")
            and state.get("clean") is not False]
    return live[0] if len(live) == 1 else None


def _cycle_mode(la, root, loop_run_id):
    return "FAST" if _fast_run_id(la, root, loop_run_id) else "STANDARD"


def _residual_lines(la, root, last_round):
    """마지막 라운드 사이드카의 잔여 지적 한 줄씩. 사이드카가 없거나 해시가 다르면 그 사실 한 줄."""
    ref = (last_round or {}).get("sidecar")
    if not isinstance(ref, dict):
        return ["(no sidecar for the last round — counts only)"]
    rounds_mod = _load_runtime("review_rounds")
    doc, problem = rounds_mod.load(root, ref)
    if problem:
        return [f"(sidecar unusable: {problem} — counts only)"]
    lines = []
    for item in doc["findings"]:
        if item["status"] != "survived" or item["disposition"] == "fix":
            continue
        where = item["file"] or "-"
        if item["line"]:
            where = f"{where}:{item['line']}"
        claim = " ".join(item["claim"].split())
        claim = claim if len(claim) <= 120 else claim[:117] + "..."
        lines.append(f"{item['id']} {item['severity']} {where} — {claim}")
    return lines or ["(no residual finding in the last round sidecar)"]


def _residual_close(la, root, args, profile, cfg, risk):
    """`CONVERGED_RESIDUAL` close 의 차단 사유와 기록할 잔여 묶음.

    승인 자격 검사(감사 무결성·Done Criteria·acceptance)는 조기 종료와 같은 기준이다. 잔여를 안고
    닫는 두 경로 중 하나만 느슨하면 그쪽이 우회로가 된다.
    """
    blockers = []
    records = la.read_records(root)
    if la.run_policy(records, args.run_id)["converge_on"] != "blocking":
        blockers.append("this run was not opened with converge_on: blocking")
    rounds = la.rounds_of(root, args.run_id)
    if args.iterations != len(rounds):
        blockers.append(f"--iterations must equal the recorded rounds ({len(rounds)})")
    if la.integrity_issues(root):
        blockers.append("loop audit integrity failed")
    verdict = la.loop_verdict(records, args.run_id, cfg, risk)
    if (verdict["action"], verdict["reason"]) != ("STOP", _RESIDUAL_REASON):
        blockers.append(f"next is {verdict['action']} {verdict['reason']}, not STOP "
                        f"{_RESIDUAL_REASON}")
    try:
        _hash, done_issue, done_mode = _approved_phase00_hash(la, root, profile, args.run_id)
    except (OSError, UnicodeError, ValueError) as exc:
        done_issue, done_mode = f"Done Criteria check failed: {type(exc).__name__}: {exc}", "enforce"
    if done_issue and done_mode in ("advisory", "enforce"):
        blockers.append(f"Phase 00 Done Criteria must be resolved: {done_issue}")
    blockers.extend(_acceptance_blockers(la, root, args, profile, risk))
    if blockers:
        return blockers, None
    last = rounds[-1]
    state = verdict["convergence"]
    max_iterations = ((cfg.get("max_iterations") or {}).get(risk)
                      if isinstance(cfg.get("max_iterations"), dict) else None)
    sidecar = last.get("sidecar") if isinstance(last.get("sidecar"), dict) else {}
    return [], {
        "completed_rounds": len(rounds),
        "configured_max_iterations": (max_iterations if max_iterations is not None
                                      else la.UNBOUNDED_ITERATIONS),
        "survived_by_severity": last.get("survived_by_severity"),
        "actual_risk": risk or "unknown",
        "mode": _cycle_mode(la, root, args.run_id),
        "residual": {"blocking_open": state["blocking_open"],
                     "accepted_residual": state["accepted_residual"],
                     "nonblocking": state["nonblocking"]},
        "accepted_decisions": la.accepted_decision_refs(verdict["critical"]),
        "sidecar_sha256": sidecar.get("sha256"),
        "lens_receipts": last.get("lens_receipts") or [],
        "fast_run_id": _fast_run_id(la, root, args.run_id),
    }


def _print_residual_disclosure(residual, residual_lines=()):
    """잔여 승인이 무엇을 남기는지 화면에 먼저 드러낸다."""
    receipt = residual["survived_by_severity"]
    counts = ", ".join(f"{key}={int(receipt.get(key, 0))}" for key in ("P0", "P1", "P2", "P3"))
    state = residual["residual"]
    print("", file=sys.stderr)
    print("⚠️  [SAGE REVIEW RESIDUAL APPROVAL — converge_on: blocking]", file=sys.stderr)
    print(f"    completed reviews: {residual['completed_rounds']}", file=sys.stderr)
    print(f"    residual findings: {counts} (blocking_open={state['blocking_open']}, "
          f"accepted critical={state['accepted_residual']}, nonblocking={state['nonblocking']})",
          file=sys.stderr)
    for line in residual_lines:
        print(f"      - {line}", file=sys.stderr)
    print("    Phase 05 and 06 record REDUCED_BY_POLICY with the four markers — assurance is "
          "lower than a standard close.", file=sys.stderr)
    print("", file=sys.stderr)


def _print_early_disclosure(authorization, max_iterations, residual_lines=()):
    """무엇을 인수하는지 화면에 먼저 드러낸다 — 조기 종료는 잔여 위험의 명시적 인수다."""
    receipt = authorization["survived_by_severity"]
    residual = ", ".join(f"{key}={int(receipt.get(key, 0))}" for key in ("P0", "P1", "P2", "P3"))
    ceiling = max_iterations if max_iterations is not None else _UNBOUNDED_LABEL
    print("", file=sys.stderr)
    print("⚠️  [SAGE REVIEW EARLY COMPLETION]", file=sys.stderr)
    print(f"    configured iteration ceiling: {ceiling}", file=sys.stderr)
    print(f"    completed reviews: {authorization['completed_rounds']}", file=sys.stderr)
    print(f"    residual findings: {residual}", file=sys.stderr)
    for line in residual_lines:
        print(f"      - {line}", file=sys.stderr)
    print(f"    next normal verdict: {authorization.get('stopped_at') or 'CONTINUE'}",
          file=sys.stderr)
    print("    Phase 06 records REDUCED_BY_USER_AUTHORIZATION — verification assurance is lower "
          "than a standard close.", file=sys.stderr)
    print("", file=sys.stderr)


def _run_close(args):
    # 조기 종료 인자는 조기 종료에만 붙는다. 일반 close 에 붙이면 감사 레코드가 두 계약을 섞는다.
    supplied = [name for name in _EARLY_AUTHORIZATION_ARGS if getattr(args, name, None) is not None]
    if args.reason != _EARLY_REASON and supplied:
        print(f"[sage review-loop] authorization arguments are only valid with "
              f"--reason {_EARLY_REASON}: {supplied}", file=sys.stderr)
        return 2
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
    # 크리티컬 P2 결정 전에는 아키텍처·예산 STOP 말고는 닫지 않는다(잠금 안에서도 다시 본다).
    records = la.read_records(root)
    pending = la.pending_critical(records, args.run_id)
    if pending and args.reason not in _CLOSE_DURING_CRITICAL:
        print(tr(language_of(args), "cli.review_loop.close_critical_pending", run_id=args.run_id,
                 findings=", ".join(pending)), file=sys.stderr)
        return 2
    # `blocking` run 에서 생존이 남은 승인은 잔여 승인(보증 저하)뿐이다. 종료 검산 mode 와 무관하게
    # 막는다(잠금 안에서도 다시 본다).
    run_rounds = [r for r in records if r.get("event") == "round" and r.get("run_id") == args.run_id]
    if (args.result == "APPROVED" and args.reason in ("CONVERGED", "DRY")
            and la.run_policy(records, args.run_id)["converge_on"] == "blocking"
            and run_rounds and int(run_rounds[-1].get("survived", 0) or 0) > 0):
        print(tr(language_of(args), "cli.review_loop.close_blocking_survivors",
                 run_id=args.run_id, reason=args.reason), file=sys.stderr)
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
        print(tr(language_of(args), "cli.review_loop.msg15",
                 m=render_issue(language_of(args), m)), file=sys.stderr)
    if mismatches:
        for m in mismatches:
            print(tr(language_of(args), "cli.review_loop.msg16",
                     m=render_issue(language_of(args), m)), file=sys.stderr)
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

    authorization = None
    if args.reason == _EARLY_REASON:
        blockers = _early_close_blockers(la, root, args, profile, cfg, risk, language_of(args))
        if blockers:
            for item in blockers:
                print(f"[sage review-loop] early completion refused: {item}", file=sys.stderr)
            return 2
        rounds = la.rounds_of(root, args.run_id)
        last = rounds[-1]
        max_iterations = ((cfg.get("max_iterations") or {}).get(risk)
                          if isinstance(cfg.get("max_iterations"), dict) else None)
        phase00_identity, done_revision = _phase00_identity(la, root, profile, args.run_id)
        verdict_action, _result, verdict_reason, _why, _skips = _next_recommendation(
            la, root, args.run_id, cfg, risk)
        if phase00_hash is None:
            phase00_hash = phase00_identity
        authorization = {
            "authorization_reason": args.authorization_reason,
            "done_criteria_revision": done_revision,
            "confirmed_by": args.confirmed_by,
            "completed_rounds": len(rounds),
            "configured_max_iterations": (max_iterations if max_iterations is not None
                                          else la.UNBOUNDED_ITERATIONS),
            "survived_by_severity": last.get("survived_by_severity"),
            "actual_risk": risk or "unknown",
            "mode": _cycle_mode(la, root, args.run_id),
            "lens_receipts": last.get("lens_receipts") or [],
            "fast_run_id": _fast_run_id(la, root, args.run_id),
            "stopped_at": _stopped_at(verdict_action, verdict_reason),
        }
        _print_early_disclosure(authorization, max_iterations,
                                _residual_lines(la, root, last))

    residual = None
    if args.reason == _RESIDUAL_REASON:
        blockers, residual = _residual_close(la, root, args, profile, cfg, risk)
        if blockers:
            for item in blockers:
                print(f"[sage review-loop] residual approval refused: {item}", file=sys.stderr)
            return 2
        phase00_identity, residual["done_criteria_revision"] = _phase00_identity(
            la, root, profile, args.run_id)
        if phase00_hash is None:
            phase00_hash = phase00_identity
        _print_residual_disclosure(residual, _residual_lines(la, root,
                                                             la.rounds_of(root, args.run_id)[-1]))

    written = _write_audit(
        la,
        lambda: la.close_loop(root, args.run_id, args.result, args.reason,
                              args.iterations,
                              reviewer_actual=args.reviewer_actual,
                              phase00_hash=phase00_hash,
                              authorization=authorization,
                              residual=residual, cfg=cfg, risk=risk),
        language=language_of(args),
    )
    if written is None:
        return 2
    print(f"[sage review-loop] close run_id={args.run_id} {args.result}/{args.reason} iterations={args.iterations}", file=sys.stderr)
    if phase00_hash is not None:
        print(f"Phase00-Hash: {phase00_hash}", file=sys.stderr)
    _auto_write_vault_dashboard(la, root, language_of(args))
    return 0


def _print_cycle_summary(la, root, run_ids, language):
    """보여 준 run 들이 속한 사이클마다 라운드 집계 한 줄, 그리고 사이클에 묶이지 않은 run 수."""
    records = la.read_records(root)
    seen = set()
    unbound = 0
    for rid in run_ids:
        state = la.run_cycle_state(records, rid)
        if state is None:
            unbound += 1
            continue
        if state["stem"] in seen:
            continue
        seen.add(state["stem"])
        print(tr(language, "cli.review_loop.cycle_line", stem=state["stem"], rounds=state["rounds"],
                 cap=state["cap"], base=state["base_cap"], extended=state["extended"], tokens=state["tokens"],
                 runs=len(state["runs"]), unbound=len(state["unbound_runs"])))
    if unbound and seen:
        print(tr(language, "cli.review_loop.cycle_unbound_count", count=unbound))


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
        # result/reason 은 감사 어휘라 번역하지 않는다 — 셈 단위와 미종료 표기만 표시 언어를 따른다.
        status = (tr(language_of(args), "cli.review_loop.status_closed", result=close["result"],
                     reason=close["reason"], iterations=close["iterations"])
                  if close else tr(language_of(args), "cli.review_loop.status_open"))
        print(tr(language_of(args), "cli.review_loop.msg22", rid=rid, status=status, count=len(rounds)))
        if close and close.get("phase00_hash"):
            print(f"      Phase00-Hash: {close['phase00_hash']}")
        for r in rounds:
            extra = ""
            # 새 필드는 있을 때만 붙인다 — 옛 기록의 화면은 그대로다.
            if isinstance(r.get("sidecar"), dict):
                extra += f" sidecar={r['sidecar'].get('path')}"
            elif r.get("sidecar") == "absent":
                extra += " sidecar=absent"
            if isinstance(r.get("receipt"), dict):
                extra += " receipt=" + ",".join(f"{k}={v}" for k, v in sorted(r["receipt"].items())
                                                if k != "critical_findings")
                listed = r["receipt"].get("critical_findings")
                if isinstance(listed, list) and listed:
                    extra += " critical=" + ",".join(str((item or {}).get("id")) for item in listed)
            print(f"      [{r.get('iteration')}] found={r.get('found')} survived={r.get('survived')} "
                  f"accepted={r.get('accepted')} arch={r.get('arch')} tokens={r.get('tokens')}{extra}")
        for d in la.decisions_of(root, rid):
            if d.get("kind") == la.DECISION_CRITICAL_P2:
                print(f"      decision {d.get('kind')}/{d.get('choice')} {d.get('finding_id')} "
                      f"(round {d.get('iteration')}) by {d.get('decided_by')}")
                continue
            print(f"      decision {d.get('kind')}/{d.get('choice')} +{d.get('extend')} "
                  f"({d.get('cap_before')}→{d.get('cap_after')}) by {d.get('decided_by')}")
    _print_cycle_summary(la, root, target_runs, language_of(args))
    if integ:
        print(tr(language_of(args), "cli.review_loop.msg23"))
        for i in integ:
            print(f"   - {render_issue(language_of(args), i)}")

    if args.vault is not None:
        _write_vault_dashboard(la, root, args.vault or None, language_of(args))
    return 1 if integ else 0


def _next_recommendation(la, root, run_id, cfg, risk):
    """기록된 라운드 + cfg(review_loop)로 '계속 vs 종료'를 결정론 권고한다(LLM 0, 감사 기록 0).
    판정은 `loop_audit.loop_verdict` 하나다 — `decide` 의 잠금 안 검사와 압축 재진입 문맥도 같은
    함수를 쓴다. 반환: (action, result, reason, why, skips).
    action == 'STOP' 이면 result/reason 은 close 에 그대로 넘길 값. action == 'ASK' 면 사람이 정할
    차례이고 reason 자리에 질문 종류(`CYCLE_CAP`)가 온다. 권고는 사실 기반이라, 자료가
    부족한 축(cfg tier 미설정)은 STOP 을 권하지 않고 skip 사유만 남긴다(false STOP 방지).

    `why`·`skips` 는 언어 중립 진단이다 — 권고 근거는 판정이고 문장은 `_run_next` 가 만든다."""
    verdict = la.loop_verdict(la.read_records(root), run_id, cfg, risk)
    skips = []
    if verdict["budget"] is None:
        skips.append(Diagnostic("review_loop.next_budget_unset", risk=risk))
    if verdict["max_iterations"] is None:
        skips.append(Diagnostic("review_loop.next_max_iterations_unset", risk=risk))
    if verdict["iterations"] and verdict["unmeasured"]:
        skips.append(Diagnostic("review_loop.next_peer_usage_unknown", rounds=verdict["unmeasured"]))
    basis = verdict["basis"]
    cycle = verdict["cycle"] or {}
    if basis == "cycle_cap":
        why = Diagnostic("review_loop.next_cycle_cap", stem=cycle.get("stem"),
                         rounds=cycle.get("rounds"), cap=cycle.get("cap"))
    elif basis == "no_rounds":
        why = Diagnostic("review_loop.next_no_rounds")
    elif basis == "arch_escalated":
        why = Diagnostic("review_loop.next_arch_escalated")
    elif basis == "over_budget":
        why = Diagnostic("review_loop.next_over_budget", tokens=verdict["tokens"], risk=risk,
                         budget=verdict["budget"])
    elif basis == "critical_pending":
        pending = (verdict["critical"] or {}).get("pending") or []
        why = Diagnostic("review_loop.next_critical_pending", count=len(pending),
                         findings=", ".join(pending))
    elif basis == "max_iter_converged" and verdict["reason"] == _RESIDUAL_REASON:
        state = verdict["convergence"] or {}
        why = Diagnostic("review_loop.next_max_iter_residual", iterations=verdict["iterations"],
                         risk=risk, max_iterations=verdict["max_iterations"],
                         accepted=state.get("accepted_residual"),
                         nonblocking=state.get("nonblocking"))
    elif basis == "max_iter_converged":
        why = Diagnostic("review_loop.next_max_iter_converged", iterations=verdict["iterations"],
                         risk=risk, max_iterations=verdict["max_iterations"])
    elif basis == "max_iter_unresolved":
        why = Diagnostic("review_loop.next_max_iter_unresolved", iterations=verdict["iterations"],
                         risk=risk, max_iterations=verdict["max_iterations"],
                         survived=verdict["survived"])
    elif basis == "converged":
        why = Diagnostic("review_loop.next_converged")
    elif basis == "converged_residual":
        state = verdict["convergence"] or {}
        why = Diagnostic("review_loop.next_converged_residual",
                         accepted=state.get("accepted_residual"),
                         nonblocking=state.get("nonblocking"))
    elif basis == "fast_minimum":
        why = Diagnostic("review_loop.next_fast_minimum",
                         minimum=verdict["policy"]["fast_minimum_rounds"],
                         iterations=verdict["iterations"])
    elif basis == "receipt_missing":
        why = Diagnostic("review_loop.next_receipt_missing", survived=verdict["survived"])
    else:
        why = Diagnostic("review_loop.next_continue", survived=verdict["survived"])
    return verdict["action"], verdict["result"], verdict["reason"], why, skips


def _print_cycle_line(la, root, run_id, language):
    """run 이 속한 사이클의 라운드 집계 한 줄(stderr). 사이클에 묶이지 않은 run 이면 그렇다고 말한다."""
    records = la.read_records(root)
    state = la.run_cycle_state(records, run_id)
    if state is None:
        print(tr(language, "cli.review_loop.cycle_unbound_run", run_id=run_id), file=sys.stderr)
        return
    print(tr(language, "cli.review_loop.cycle_line", stem=state["stem"], rounds=state["rounds"],
             cap=state["cap"], base=state["base_cap"], extended=state["extended"], tokens=state["tokens"],
             runs=len(state["runs"]), unbound=len(state["unbound_runs"])), file=sys.stderr)


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
        print(tr(language_of(args), "cli.review_loop.msg26",
                 s=render_issue(language_of(args), s)), file=sys.stderr)
    print(tr(language_of(args), "cli.review_loop.msg27",
             why=render_issue(language_of(args), why)), file=sys.stderr)
    _print_cycle_line(la, root, args.run_id, language_of(args))
    _print_blocking_line(la, root, args.run_id, cfg, risk, language_of(args))
    if action == "CONTINUE":
        print("NEXT: CONTINUE")
    elif action == "ASK" and reason == _CRITICAL_REASON:
        critical = la.critical_state(la.read_records(root), args.run_id)
        print(f"NEXT: ASK kind={reason} findings={','.join(critical['pending'])}")
        print(tr(language_of(args), "cli.review_loop.ask_critical_p2", run_id=args.run_id,
                 iteration=critical["iteration"]), file=sys.stderr)
        for line in _critical_lines(la, root, args.run_id, critical):
            print(f"      - {line}", file=sys.stderr)
    elif action == "ASK":
        cycle = la.run_cycle_state(la.read_records(root), args.run_id) or {}
        print(f"NEXT: ASK kind={reason} cycle_rounds={cycle.get('rounds')} cap={cycle.get('cap')}")
        print(tr(language_of(args), "cli.review_loop.ask_cycle_cap", run_id=args.run_id,
                 stem=cycle.get("stem"), count=len(la.rounds_of(root, args.run_id))),
              file=sys.stderr)
    else:
        print(f"NEXT: STOP result={result} reason={reason}")
        print(tr(language_of(args), "cli.review_loop.msg28", args_run_id=args.run_id, result=result, reason=reason, count=len(la.rounds_of(root, args.run_id))), file=sys.stderr)
    print(tr(language_of(args), "cli.review_loop.msg29"), file=sys.stderr)
    return 0


_MAX_EXTEND = 10


def _print_blocking_line(la, root, run_id, cfg, risk, language):
    """`converge_on: blocking` run 이면 통일 수렴식의 칸들을 한 줄로(stderr)."""
    records = la.read_records(root)
    if la.run_policy(records, run_id)["converge_on"] != "blocking":
        return
    state = la.loop_verdict(records, run_id, cfg, risk).get("convergence")
    if not state:
        return
    print(tr(language, "cli.review_loop.blocking_line", blocking_open=state["blocking_open"],
             accepted=state["accepted_residual"], nonblocking=state["nonblocking"],
             refute_pending=state["refute_pending"], unexplored=state["unexplored"]),
          file=sys.stderr)


def _critical_lines(la, root, run_id, critical):
    """결정을 기다리는 크리티컬 지적 한 줄씩. 사이드카를 해시로 읽을 수 없으면 id·분류만."""
    rounds = la.rounds_of(root, run_id)
    ref = rounds[-1].get("sidecar") if rounds else None
    doc = None
    if isinstance(ref, dict):
        doc, _problem = _load_runtime("review_rounds").load(root, ref)
    by_id = {item["id"]: item for item in (doc or {}).get("findings") or []}
    lines = []
    for entry in critical["listed"]:
        if entry["id"] not in critical["pending"]:
            continue
        item = by_id.get(entry["id"])
        claim_tag = f"[claim {entry['claim_sha256'][:12]}]"
        if item is None:
            lines.append(f"{entry['id']} {claim_tag} P2 {entry.get('category') or '-'} "
                         "(sidecar unavailable)")
            continue
        where = item["file"] or "-"
        if item["line"]:
            where = f"{where}:{item['line']}"
        claim = " ".join(item["claim"].split())
        claim = claim if len(claim) <= 120 else claim[:117] + "..."
        lines.append(f"{entry['id']} {claim_tag} P2 {entry.get('category') or '-'} {where} — {claim}")
    return lines


def _run_decide(args):
    """사람의 결정을 감사에 남긴다. 사유·결정자는 그 턴의 사용자 말이다.

    사이클 상한의 「계속」과 크리티컬 P2 하나의 「수정·수용」 두 형태다.
    """
    la = _load_loop_audit()
    root = _root(args)
    language = language_of(args)
    if not _is_open(la, root, args.run_id):
        print(tr(language, "cli.review_loop.msg24", args_run_id=args.run_id), file=sys.stderr)
        return 2
    if _is_closed(la, root, args.run_id):
        print(tr(language, "cli.review_loop.msg05", args_run_id=args.run_id), file=sys.stderr)
        return 2
    cycle_form = args.cycle is not None or args.extend is not None
    critical_form = (args.finding is not None or args.critical_choice is not None
                     or args.claim is not None)
    problems = []
    if cycle_form == critical_form:
        problems.append("give exactly one form: --cycle continue --extend <N>, or "
                        "--finding <id> --claim <hash> --fix|--accept")
    elif cycle_form:
        if args.cycle is None or args.extend is None:
            problems.append("--cycle continue needs --extend <N>")
        elif not 1 <= args.extend <= _MAX_EXTEND:
            problems.append(f"--extend must be between 1 and {_MAX_EXTEND}")
    elif args.finding is None or args.critical_choice is None or args.claim is None:
        # `--claim` 은 사용자가 본 주장이다. 없으면 결정이 「그 사이 바뀐 주장」에 붙을 수 있다.
        problems.append("--finding <id> needs --claim <hash shown by next> and --fix or --accept")
    for name in ("reason", "decided_by"):
        if not (getattr(args, name) or "").strip():
            problems.append(f"--{name.replace('_', '-')} must be a non-empty line")
    if problems:
        for item in problems:
            print(f"[sage review-loop] decide refused: {item}", file=sys.stderr)
        return 2
    if critical_form:
        return _decide_critical(la, root, args, language)
    state = la.run_cycle_state(la.read_records(root), args.run_id)
    cfg = risk = None
    if state is None:
        problems.append("this run is not bound to a cycle")
    elif not state["reached"]:
        problems.append(f"cycle {state['stem']} has not reached its round cap "
                        f"({state['rounds']}/{state['cap']}); nothing to decide")
    else:
        # `next` 와 같은 판정이어야 한다. 상한에 닿았어도 STOP 이거나 크리티컬 P2 를 먼저 정해야
        # 하면 연장할 자리가 아니다.
        profile = _validated_profile(root, language)
        if profile is None:
            return 2
        cfg = _cfg_snapshot(root, profile)
        risk = _run_risk(la, root, args.run_id)
        action, _result, reason, _why, _skips = _next_recommendation(la, root, args.run_id,
                                                                    cfg, risk)
        if (action, reason) != ("ASK", _CYCLE_CAP_REASON):
            problems.append(f"next is {action} {reason}, not ASK {_CYCLE_CAP_REASON}; "
                            "nothing to decide")
    if problems:
        for item in problems:
            print(f"[sage review-loop] decide refused: {item}", file=sys.stderr)
        return 2
    written = _write_audit(
        la,
        lambda: la.record_decision(root, args.run_id, la.DECISION_CYCLE_CAP, args.cycle,
                                   args.reason, args.decided_by, extend=args.extend,
                                   cfg=cfg, risk=risk),
        language=language,
    )
    if written is None:
        return 2
    print(tr(language, "cli.review_loop.decide_recorded", stem=written["cycle_stem"],
             before=written["cap_before"], after=written["cap_after"],
             rounds=written["cycle_rounds"]), file=sys.stderr)
    return 0


def _decide_critical(la, root, args, language):
    """크리티컬 P2 하나의 결정. 결정은 마지막 라운드의 그 지적 내용(주장 해시)에 묶인다."""
    profile = _validated_profile(root, language)
    if profile is None:
        return 2
    cfg = _cfg_snapshot(root, profile)
    risk = _run_risk(la, root, args.run_id)
    records = la.read_records(root)
    problems = []
    if la.run_policy(records, args.run_id)["converge_on"] != "blocking":
        problems.append("this run was not opened with converge_on: blocking; critical P2 "
                        "decisions do not apply")
    else:
        # 판정·크리티컬 목록·라운드 해시를 한 번 읽은 같은 레코드에서 만든다. 따로 읽으면 두 시점이 섞인다.
        verdict = la.loop_verdict(records, args.run_id, cfg, risk)
        critical = la.critical_state(records, args.run_id)
        pending = critical["pending"]
        if (verdict["action"], verdict["reason"]) != ("ASK", _CRITICAL_REASON):
            problems.append(f"next is {verdict['action']} {verdict['reason']}, not ASK "
                            f"{_CRITICAL_REASON}; nothing to decide")
        elif args.finding not in pending:
            problems.append(f"{args.finding} is not a critical P2 awaiting a decision "
                            f"(pending: {', '.join(pending) or '-'})")
        else:
            # 사용자가 본 `next` 출력의 주장 해시. 그 뒤 같은 id 에 다른 주장이 왔으면 이 답은 그 주장에
            # 대한 답이 아니다.
            shown = next(item for item in critical["listed"] if item["id"] == args.finding)
            prefix = args.claim.strip().lower()
            if len(prefix) < 8 or not shown["claim_sha256"].startswith(prefix):
                problems.append(f"{args.finding} now has claim {shown['claim_sha256'][:12]}, not "
                                f"the {args.claim!r} that was shown; show the current finding "
                                "and ask again")
    if problems:
        for item in problems:
            print(f"[sage review-loop] decide refused: {item}", file=sys.stderr)
        return 2
    # 잠금 안에서 같은 라운드·같은 주장인지 다시 본다. 그 사이 라운드가 바뀌었으면 이 답은 지금 지적에
    # 대한 답이 아니다.
    shown = next(item for item in critical["listed"] if item["id"] == args.finding)
    last_hash = [r for r in records if r.get("event") == "round"
                 and r.get("run_id") == args.run_id][-1].get("record_hash")
    written = _write_audit(
        la,
        lambda: la.record_decision(root, args.run_id, la.DECISION_CRITICAL_P2,
                                   args.critical_choice, args.reason, args.decided_by,
                                   finding_id=args.finding, cfg=cfg, risk=risk,
                                   expected_round_hash=last_hash,
                                   expected_claim_sha256=shown["claim_sha256"]),
        language=language,
    )
    if written is None:
        return 2
    print(tr(language, "cli.review_loop.decide_critical_recorded", finding=args.finding,
             choice=args.critical_choice, iteration=written["iteration"]), file=sys.stderr)
    return 0


def _ledger_stem(args, language):
    binding = _load_cycle_binding()
    stem = args.cycle_stem
    if stem is None:
        try:
            stem = _load_runtime("cycle_state").resolve_stem(_root(args))[0]
        except Exception:  # noqa: BLE001
            stem = ""
    normalized = binding.normalize_stem(stem) if stem else None
    if not normalized:
        print(tr(language, "cli.review_loop.cycle_stem_required"), file=sys.stderr)
    return normalized


def _run_ledger_add(args):
    la = _load_loop_audit()
    rounds_mod = _load_runtime("review_rounds")
    language = language_of(args)
    stem = _ledger_stem(args, language)
    if stem is None:
        return 2
    try:
        entry = rounds_mod.add_entry(_root(args), stem, args.kind, source=args.source,
                                     reason=args.reason, severity=args.severity,
                                     location=args.location, ref=args.ref,
                                     lock=la._audit_lock)
    except (OSError, rounds_mod.SidecarError, la.AuditWriteError) as exc:
        print(f"[sage review-loop] ledger add refused: {exc}", file=sys.stderr)
        return 2
    print(entry["id"])
    return 0


def _ledger(args, language):
    la = _load_loop_audit()
    rounds_mod = _load_runtime("review_rounds")
    stem = _ledger_stem(args, language)
    if stem is None:
        return None
    root = _root(args)
    return rounds_mod.build_ledger(root, la.read_records(root), stem)


def _finding_label(item):
    where = item.get("file") or "-"
    if item.get("line"):
        where = f"{where}:{item['line']}"
    claim = " ".join(str(item.get("claim") or "").split())
    claim = claim if len(claim) <= 160 else claim[:157] + "..."
    return f"{item.get('severity')} {where} — {claim}"


def _ledger_lines(ledger, language):
    out = []
    if ledger["manual"]:
        out.append(f"### {tr(language, 'cli.review_loop.ledger_h_manual')}")
        for item in ledger["manual"]:
            severity = f" {item.get('severity')}" if item.get("severity") else ""
            location = f" {item.get('location')}" if item.get("location") else ""
            out.append(f"- {item.get('id')} [{item.get('kind')}]{severity}{location} — "
                       f"{item.get('reason')} (source: {item.get('source')})")
    if ledger["residual"]:
        out.append(f"### {tr(language, 'cli.review_loop.ledger_h_residual')}")
        for item in ledger["residual"]:
            out.append(f"- {item['run_id']}:{item['iteration']}:{item['id']} {_finding_label(item)}")
    if ledger.get("accepted_critical"):
        out.append(f"### {tr(language, 'cli.review_loop.ledger_h_accepted_critical')}")
        for item in ledger["accepted_critical"]:
            out.append(f"- {item['run_id']}:{item.get('iteration')}:{item.get('finding_id')} P2 "
                       f"{item.get('category') or '-'} — {item['reason']} / {item['decided_by']}")
    if ledger.get("preexisting"):
        out.append(f"### {tr(language, 'cli.review_loop.ledger_h_preexisting')}")
        for item in ledger["preexisting"]:
            out.append(f"- {item['run_id']}:{item['iteration']}:{item['id']} "
                       f"{_finding_label(item)} [exposure: {item.get('exposure') or '-'}]")
    reduced = (_EARLY_REASON, _RESIDUAL_REASON)
    decided = [d for d in ledger["decisions"]] + [
        c for c in ledger["closes"] if c.get("reason") in reduced]
    if decided:
        out.append(f"### {tr(language, 'cli.review_loop.ledger_h_decisions')}")
        for item in ledger["decisions"]:
            if item.get("kind") == "critical_p2":
                out.append(f"- {item['run_id']} critical {item.get('finding_id')} "
                           f"{item.get('choice')} (round {item.get('iteration')}) — "
                           f"{item['reason']} / {item['decided_by']}")
                continue
            out.append(f"- {item['run_id']} cycle continue +{item['extend']} "
                       f"({item['cap_before']}→{item['cap_after']}) — {item['reason']} "
                       f"/ {item['decided_by']}")
        for item in ledger["closes"]:
            if item.get("reason") == _EARLY_REASON:
                out.append(f"- {item['run_id']} USER_AUTHORIZED_EARLY at "
                           f"{item.get('stopped_at') or 'CONTINUE'} — "
                           f"{item.get('authorization_reason')} / {item.get('confirmed_by')}")
            elif item.get("reason") == _RESIDUAL_REASON:
                state = item.get("residual") or {}
                out.append(f"- {item['run_id']} CONVERGED_RESIDUAL (REDUCED_BY_POLICY) — "
                           f"accepted critical {state.get('accepted_residual')}, "
                           f"nonblocking {state.get('nonblocking')}")
    if ledger.get("unclosed"):
        out.append(f"### {tr(language, 'cli.review_loop.ledger_h_unclosed')}")
        for item in ledger["unclosed"]:
            note = f" — {item['note']}" if item.get("note") else ""
            out.append(f"- {item['run_id']}:{item['iteration']} {item.get('ref')}{note}")
    if ledger["refuted"]:
        out.append(f"### {tr(language, 'cli.review_loop.ledger_h_refuted')}")
        for item in ledger["refuted"]:
            reasons = "; ".join(
                f"{r.get('drop_reason') or '-'}: {r.get('reason') or '-'}" for r in item["reasons"])
            out.append(f"- {item['run_id']}:{item['iteration']}:{item['id']} "
                       f"{_finding_label(item)} [{reasons or '-'}]")
    return out


def _ledger_warnings(ledger, language):
    out = []
    for item in ledger["sidecar_issues"]:
        out.append(tr(language, "cli.review_loop.ledger_sidecar_issue", run_id=item["run_id"],
                      iteration=item["iteration"], problem=item["problem"]))
    for item in ledger["entry_issues"]:
        out.append(tr(language, "cli.review_loop.ledger_entry_issue", problem=item))
    return out


def _run_ledger_show(args):
    language = language_of(args)
    ledger = _ledger(args, language)
    if ledger is None:
        return 2
    print(tr(language, "cli.review_loop.ledger_show_title", stem=ledger["stem"],
             runs=len(ledger["runs"])))
    lines = _ledger_lines(ledger, language)
    print("\n".join(lines) if lines else tr(language, "cli.review_loop.ledger_empty"))
    if ledger["conflicts"]:
        print(f"### {tr(language, 'cli.review_loop.ledger_h_conflicts')}")
        for item in ledger["conflicts"]:
            print(f"- {item['run_id']}:{item['iteration']}:{item['id']} → {item['ledger_ref']} "
                  f"{_finding_label(item)}")
    warnings = _ledger_warnings(ledger, language)
    for line in warnings:
        print(line, file=sys.stderr)
    return 1 if warnings else 0


def _run_ledger_render(args):
    """패킷의 「결정·잔여」 절. 손으로 옮기지 않게 장부에서 그대로 찍는다."""
    language = language_of(args)
    ledger = _ledger(args, language)
    if ledger is None:
        return 2
    print(f"## {tr(language, 'cli.review_loop.ledger_render_heading')}")
    print("")
    print(tr(language, "cli.review_loop.ledger_render_note"))
    print("")
    lines = _ledger_lines(ledger, language)
    print("\n".join(lines) if lines else tr(language, "cli.review_loop.ledger_empty"))
    # 빠진 사이드카를 조용히 건너뛰면 패킷이 완전한 장부처럼 보인다. 경고를 패킷 본문에도 싣는다.
    warnings = _ledger_warnings(ledger, language)
    if warnings:
        print("")
        for line in warnings:
            print(f"> {line}")
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


def _dashboard_md(la, root, retro_links=None, language=None):
    """loop_audit → Obsidian 대시보드 마크다운(plain 테이블 — DataView 플러그인 무관 항상 가독).
    run 별 1행: run_id·risk·rounds·found/accepted 합계·종료. 무결성 경고 섹션.

    사용자가 vault 에서 읽는 산출물이라 본문 문장은 표시 언어를 따른다. 반대로 표 구조 marker,
    감사 레코드의 필드명 열, `run_id`, `result/reason` 어휘는 언어와 무관하게 고정한다 — 같은
    사실이 언어마다 다른 문자열로 남으면 두 언어로 쓴 노트를 나중에 대조할 수 없다."""
    retro_links = retro_links or {}
    rows = []
    for rid in la.runs(root):
        rounds = la.rounds_of(root, rid)
        close = la.close_of(root, rid)
        risk = next((r.get("risk") for r in la.read_records(root)
                     if r.get("event") == "loop_open" and r.get("run_id") == rid), "")
        f_tot = sum(int(r.get("found", 0) or 0) for r in rounds)
        a_tot = sum(int(r.get("accepted", 0) or 0) for r in rounds)
        status = (f"{close['result']}/{close['reason']}" if close
                  else tr(language, "cli.review_loop.dashboard_status_open"))
        iters = close["iterations"] if close else len(rounds)
        retro = ", ".join(retro_links.get(rid, [])) or "-"
        rows.append(f"| {rid} | {risk} | {len(rounds)} | {f_tot} | {a_tot} | {status} | {iters} | {retro} |")
    from sage.commands._common import _project_name
    from sage.commands.knowledge import _safe_title
    # 파일명(_note_filename)과 동일하게 개행/구분자를 정규화 — 정규화 안 하면 project.name 에
    # 섞인 개행(`\n## x`)이 H1 본문에 살아 대시보드가 주입 헤딩으로 깨진다.
    name = _project_name(_load_profile(root))
    title_suffix = f" — {_safe_title(name)}" if name else ""
    # 열 개수는 코드가 고정한다 — 헤더 행 전체를 catalog 에 두면 번역하면서 열이 늘거나 줄어
    # 구분자 행과 어긋난다. 사람이 읽는 열 이름만 번역하고 감사 필드명 열은 그대로 둔다.
    header = ("| run_id | risk | rounds"
              f" | {tr(language, 'cli.review_loop.dashboard_col_found')}"
              f" | {tr(language, 'cli.review_loop.dashboard_col_accepted')}"
              f" | {tr(language, 'cli.review_loop.dashboard_col_result')}"
              " | iters | retro |")
    body = [f"# {tr(language, 'cli.review_loop.dashboard_title')}{title_suffix}", "",
            f"> {tr(language, 'cli.review_loop.dashboard_note_accepted')}",
            f"> {tr(language, 'cli.review_loop.dashboard_note_source')}", "",
            header,
            "|---|---|---:|---:|---:|---|---:|---|"]
    body += rows or [f"| {tr(language, 'cli.review_loop.dashboard_no_records')} | | | | | | | |"]
    integ = la.integrity_issues(root)
    # 종료 열은 `APPROVED/USER_AUTHORIZED_EARLY`·`APPROVED/CONVERGED_RESIDUAL` 로 이미 둘을 가른다.
    # 여기서 더하는 것은 **무엇이 남은 채로 닫혔는가** — 그게 없으면 노트만 보고는 잔여 위험을 모른다.
    early = _early_close_rows(la, root)
    if early:
        body += ["", f"## {tr(language, 'cli.review_loop.dashboard_reduced_heading')}", "",
                 f"> {tr(language, 'cli.review_loop.dashboard_reduced_note')}", ""]
        body += early
    if integ:
        body += ["", f"## ⚠️ {tr(language, 'cli.review_loop.dashboard_integrity_heading')}", ""]
        body += [f"- {render_issue(language, i)}" for i in integ]
    return "\n".join(body) + "\n"


def _early_close_rows(la, root):
    """잔여를 안고 닫은 run(조기 종료·잔여 승인)의 잔여 영수증 줄. 없으면 빈 목록.

    영수증 어휘(`P0`~`P3`)와 승인자·사유는 감사 레코드 그대로 쓴다 — 표시 언어로 바꾸면 같은
    사실이 언어마다 다른 문자열로 남아 두 언어 노트를 대조할 수 없다.
    """
    rows = []
    for rid in la.runs(root):
        close = la.close_of(root, rid) or {}
        if close.get("reason") not in la.REDUCED_ASSURANCE_BY_REASON:
            continue
        receipt = close.get("survived_by_severity")
        residual = (", ".join(f"{key}={receipt.get(key, 0)}" for key in la.SEVERITIES)
                    if isinstance(receipt, dict) else "-")
        rounds = close.get("completed_rounds")
        # 옛 레코드는 상한 미설정을 `-1` 로 적었다. 그대로 렌더하면 `2/-1 rounds` 가 된다.
        configured = close.get("configured_max_iterations")
        if configured in (-1, None):
            configured = _UNBOUNDED_LABEL
        if close.get("reason") == la.CONVERGED_RESIDUAL_REASON:
            state = close.get("residual") or {}
            rows.append(f"- `{rid}` — {la.CONVERGED_RESIDUAL_REASON} · {rounds}/{configured} rounds"
                        f" · {residual} · accepted critical {state.get('accepted_residual', '-')}")
            continue
        rows.append(f"- `{rid}` — {rounds}/{configured} rounds · {residual}"
                    f" · {close.get('confirmed_by') or '-'}"
                    f" · {close.get('authorization_reason') or '-'}")
    return rows


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
    # frontmatter 는 노트의 출처 기록이다 — 표시 언어를 따라 흔들리면 같은 산출물이 언어마다 다른
    # provenance 를 갖고, 나중에 vault 를 훑어 생성기별로 모을 수 없다. 언어 중립으로 고정한다.
    fm = {"tags": ["sage", "loop-audit"], "updated": datetime.date.today().isoformat(),
          "generated_by": "sage review-loop (close auto / show --vault)"}
    path = _vault.write_note(vault, folder, _dashboard_filename(profile), fm,
                             _dashboard_md(la, root, _retro_links_by_run(vault, folder),
                                           language=language))
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
