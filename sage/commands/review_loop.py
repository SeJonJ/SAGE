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

from sage import _resources

# result↔reason 의미 짝(설계 §3) — APPROVED 는 수렴/dry 로만, BLOCKED 는 예산초과/아키텍처로만.
_APPROVED_REASONS = {"CONVERGED", "DRY"}
_BLOCKED_REASONS = {"BUDGET_ITER", "BUDGET_TOK", "BLOCKED_ARCH"}


def _load_loop_audit():
    rt = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks", "runtime")
    if rt not in sys.path:
        sys.path.insert(0, rt)
    import loop_audit as la
    return la


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


def register(sub):
    p = sub.add_parser("review-loop", help="Loop A(Phase 05 적대적 리뷰) 라운드 감사를 기록·조회합니다")
    sp = p.add_subparsers(dest="action", metavar="<action>")
    sp.required = True

    po = sp.add_parser("open", help="루프 시작 기록 → run_id 출력")
    po.add_argument("--risk", required=True, choices=["L2", "L3"], help="위험 tier(루프는 L2/L3 만)")
    po.add_argument("--run-id", default=None, help="명시 run_id(기본: 자동 발급)")
    po.add_argument("--root", default=None)
    po.set_defaults(func=_run_open)

    pr = sp.add_parser("round", help="라운드 1건 기록(찾기/반박/채택 집계)")
    pr.add_argument("--run-id", required=True)
    pr.add_argument("--iteration", required=True, type=_nonneg)
    pr.add_argument("--found", required=True, type=_nonneg, help="FIND 발견 수")
    pr.add_argument("--survived", required=True, type=_nonneg, help="REFUTE 생존 수")
    pr.add_argument("--accepted", required=True, type=_nonneg, help="REWORK 채택 수")
    pr.add_argument("--arch", default=0, type=_nonneg, help="아키텍처 에스컬레이션 수")
    pr.add_argument("--tokens", default=0, type=_nonneg, help="누적 토큰")
    pr.add_argument("--root", default=None)
    pr.set_defaults(func=_run_round)

    pc = sp.add_parser("close", help="루프 종료 기록(result/reason/iterations)")
    pc.add_argument("--run-id", required=True)
    pc.add_argument("--result", required=True, choices=["APPROVED", "BLOCKED"])
    pc.add_argument("--reason", required=True,
                    choices=sorted(_APPROVED_REASONS | _BLOCKED_REASONS))
    pc.add_argument("--iterations", required=True, type=_nonneg)
    pc.add_argument("--root", default=None)
    pc.set_defaults(func=_run_close)

    ps = sp.add_parser("show", help="루프 감사 요약(+무결성 점검). --vault 면 Obsidian 대시보드 노트도 작성")
    ps.add_argument("--run-id", default=None, help="특정 run_id(미지정: 전체 요약)")
    ps.add_argument("--vault", nargs="?", const="", default=None,
                    help="Obsidian vault 대시보드 작성. 경로 생략 시 profile.knowledge_capture.vault_path 사용")
    ps.add_argument("--root", default=None)
    ps.set_defaults(func=_run_show)


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
    """<root>/sage/project-profile.yaml → dict. 없음/실패 → {}."""
    ppath = os.path.join(root, "sage", "project-profile.yaml")
    if not os.path.exists(ppath):
        return {}
    try:
        import yaml
        prof = yaml.safe_load(open(ppath, encoding="utf-8")) or {}
        return prof if isinstance(prof, dict) else {}
    except Exception:
        return {}


def _cfg_snapshot(root):
    """profile.pdca.review_loop 스냅샷(있으면) — open 레코드에 적용 설정 기록용. 없으면 {}."""
    rl = ((_load_profile(root).get("pdca") or {}).get("review_loop")) or {}
    return rl if isinstance(rl, dict) else {}


def _is_open(la, root, run_id):
    """run_id 에 loop_open 이 있는지(CLI 강제용 — orphan round/close 차단, codex S3 P2)."""
    return run_id in set(la.runs(root))


def _is_closed(la, root, run_id):
    """run_id 가 이미 loop_close 됐는지(round/close-after-close 차단, codex S3 강화)."""
    return la.close_of(root, run_id) is not None


def _run_open(args):
    la = _load_loop_audit()
    root = _root(args)
    # 명시 run_id 중복 open 거부(integrity 불변식을 write 시점에 강제 — strict CLI 레이어).
    if args.run_id and _is_open(la, root, args.run_id):
        print(f"[sage review-loop] run_id '{args.run_id}' 이미 open 됨 — 중복 open 거부(integrity)", file=sys.stderr)
        return 2
    rid = la.open_loop(root, args.risk, cfg=_cfg_snapshot(root), run_id=args.run_id)
    print(rid)   # stdout = run_id 만(스킬이 캡처해 후속 round/close 에 전달)
    print(f"[sage review-loop] open run_id={rid} risk={args.risk} → {la.audit_path(root)}", file=sys.stderr)
    return 0


def _run_round(args):
    la = _load_loop_audit()
    root = _root(args)
    # orphan 차단: loop_open 없는 run_id 의 round 거부(codex S3 P2 — CLI 가 integrity 를 write 시 강제).
    if not _is_open(la, root, args.run_id):
        print(f"[sage review-loop] run_id '{args.run_id}' 의 loop_open 없음 — orphan round 거부. 먼저 open", file=sys.stderr)
        return 2
    if _is_closed(la, root, args.run_id):
        print(f"[sage review-loop] run_id '{args.run_id}' 이미 종료됨 — 종료 후 round 거부", file=sys.stderr)
        return 2
    # 불가능 튜플 거부(순수 산술, 읽기 불요): survived ≤ found, accepted ≤ survived, arch ≤ survived.
    #   (REFUTE 는 발견 부분집합, REWORK 채택은 생존 부분집합, arch 에스컬레이션은 생존 중 분류.)
    if args.survived > args.found:
        print(f"[sage review-loop] survived({args.survived}) > found({args.found}) 불가(생존은 발견의 부분집합)", file=sys.stderr)
        return 2
    if args.accepted > args.survived:
        print(f"[sage review-loop] accepted({args.accepted}) > survived({args.survived}) 불가(채택은 생존의 부분집합)", file=sys.stderr)
        return 2
    if args.arch > args.survived:
        print(f"[sage review-loop] arch({args.arch}) > survived({args.survived}) 불가(아키텍처는 생존 중 분류)", file=sys.stderr)
        return 2
    la.record_round(root, args.run_id, args.iteration, args.found, args.survived,
                    args.accepted, arch=args.arch, tokens=args.tokens)
    print(f"[sage review-loop] round {args.iteration} run_id={args.run_id} "
          f"found={args.found} survived={args.survived} accepted={args.accepted} arch={args.arch}", file=sys.stderr)
    return 0


def _run_close(args):
    # result↔reason 의미 짝 강제(감사 트레일 일관성). 라이브러리는 permissive 이므로 여기서 게이트.
    if args.result == "APPROVED" and args.reason not in _APPROVED_REASONS:
        print(f"[sage review-loop] APPROVED 는 reason ∈ {sorted(_APPROVED_REASONS)} 만 — 받음 '{args.reason}'", file=sys.stderr)
        return 2
    if args.result == "BLOCKED" and args.reason not in _BLOCKED_REASONS:
        print(f"[sage review-loop] BLOCKED 는 reason ∈ {sorted(_BLOCKED_REASONS)} 만 — 받음 '{args.reason}'", file=sys.stderr)
        return 2
    la = _load_loop_audit()
    root = _root(args)
    if not _is_open(la, root, args.run_id):
        print(f"[sage review-loop] run_id '{args.run_id}' 의 loop_open 없음 — orphan close 거부. 먼저 open", file=sys.stderr)
        return 2
    if _is_closed(la, root, args.run_id):
        print(f"[sage review-loop] run_id '{args.run_id}' 이미 종료됨 — 중복 close 거부", file=sys.stderr)
        return 2
    la.close_loop(root, args.run_id, args.result, args.reason, args.iterations)
    print(f"[sage review-loop] close run_id={args.run_id} {args.result}/{args.reason} iterations={args.iterations}", file=sys.stderr)
    return 0


def _run_show(args):
    la = _load_loop_audit()
    root = _root(args)
    print(f"== sage review-loop --show ({la.audit_path(root)}) ==")
    integ = la.integrity_issues(root)
    target_runs = [args.run_id] if args.run_id else la.runs(root)
    if not target_runs:
        print("기록 없음.")
    for rid in target_runs:
        rounds = la.rounds_of(root, rid)
        close = la.close_of(root, rid)
        status = f"{close['result']}/{close['reason']} ({close['iterations']}회)" if close else "진행중(미종료)"
        print(f"  · {rid}: {status}, 라운드 {len(rounds)}건")
        for r in rounds:
            print(f"      [{r.get('iteration')}] found={r.get('found')} survived={r.get('survived')} "
                  f"accepted={r.get('accepted')} arch={r.get('arch')} tokens={r.get('tokens')}")
    if integ:
        print("⚠️  무결성 경고:")
        for i in integ:
            print(f"   - {i}")

    if args.vault is not None:
        _write_vault_dashboard(la, root, args.vault or None)
    return 1 if integ else 0


def _dashboard_md(la, root):
    """loop_audit → Obsidian 대시보드 마크다운(plain 테이블 — DataView 플러그인 무관 항상 가독).
    run 별 1행: run_id·risk·rounds·found/accepted 합계·종료. 무결성 경고 섹션."""
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
        rows.append(f"| {rid} | {risk} | {len(rounds)} | {f_tot} | {a_tot} | {status} | {iters} |")
    body = ["# SAGE Loop A 감사 대시보드", "",
            "> Phase 05 적대적 review-rework 루프 이력. `accepted` 합계 = 리뷰가 채운 host 의 체계적 누락.",
            "> 정본 데이터: `.sage/loop_audit.jsonl`. 이 노트는 `sage review-loop show --vault` 로 갱신.", "",
            "| run_id | risk | rounds | found(합) | accepted(합) | 종료 | iters |",
            "|---|---|---:|---:|---:|---|---:|"]
    body += rows or ["| (기록 없음) | | | | | | |"]
    integ = la.integrity_issues(root)
    if integ:
        body += ["", "## ⚠️ 무결성 경고", ""] + [f"- {i}" for i in integ]
    return "\n".join(body) + "\n"


def _write_vault_dashboard(la, root, override):
    from sage.commands import _vault
    vault, folder = _vault.vault_target(_load_profile(root), override)
    if not vault:
        print("  ℹ️  vault 비활성(knowledge_capture.vault_path 미설정, --vault 경로도 없음) → 대시보드 생략", file=sys.stderr)
        return
    import datetime
    fm = {"tags": ["sage", "loop-audit"], "updated": datetime.date.today().isoformat(),
          "generated_by": "sage review-loop show --vault"}
    path = _vault.write_note(vault, folder, "SAGE-loop-audit.md", fm, _dashboard_md(la, root))
    print(f"  ✅ Obsidian 대시보드 작성: {path}", file=sys.stderr)
