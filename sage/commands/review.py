"""sage review — auto_approve_safe_default 분류 UX (step8).

최종검증 §3 합의: 사람 diff 승인을 기본→예외로 강등. validate 결과 위에서 자산을
auto(자동승인 후보) / review(사람 검토 예외)로 분류·리포트. v1 은 분류만(승인 상태변경 X — generate 폐루프 후속).

auto 조건(Codex 2R): validate_sev==PASS AND unresolved 없음 AND not safety_degraded AND risk 없음 AND render_current.
render_current: hook=validate PASS(hash 재계산 일치) / agent(interpretive)=render_hash{claude,codex} stamp 존재 + validate PASS.
exit: 기본 0(정보성) / --gate review>0 시 1 / tool err 2.
"""

import json
import os
import sys
from pathlib import Path

from sage.commands import validate as V


def register(sub):
    p = sub.add_parser("review", help="자동승인(auto)/사람검토(review) 분류 — auto_approve_safe_default")
    p.add_argument("--kind", choices=["hook", "agent", "skill", "mcp", "all"], default="all")
    p.add_argument("--batch", action="store_true", help="auto 버킷을 1줄 요약")
    p.add_argument("--gate", action="store_true", help="review 버킷 있으면 exit 1 (CI 게이트)")
    p.add_argument("--root", default=None)
    p.set_defaults(func=run)


def _render_current(entry):
    form = entry.get("form", "core_adapter")
    rh = entry.get("render_hash") or {}
    if form == "interpretive":
        # agent: 양 target stamp 존재(validate PASS 가 spec/claims 최신 보증)
        return "claude" in rh and "codex" in rh
    if form == "native":
        return "native" in rh
    if form == "declarative":
        # mcp: spec.runtime_targets 가 선언한 target 만 stamp 요구(단일-target 을 미완으로 오분류 방지).
        targets = entry.get("runtime_targets") or list(rh.keys())
        return bool(targets) and all(t in rh for t in targets)
    return "claude" in rh or "codex" in rh


def auto_approve_decision(asset_id, validate_sev, entry):
    """auto|review 결정 + 사유. validate_sev 가 PASS 가 아니면 그 자체가 review 사유."""
    reasons = []
    if validate_sev != "PASS":
        reasons.append(f"validate={validate_sev}")
    if entry.get("unresolved"):
        reasons.append(f"unresolved {len(entry['unresolved'])}건")
    if entry.get("safety_degraded"):
        reasons.append("safety_degraded")
    if entry.get("risk"):
        reasons.append(f"risk {len(entry['risk'])}건")
    if not _render_current(entry):
        reasons.append("render 미최신(stamp 누락)")
    return {"decision": "auto" if not reasons else "review", "reasons": reasons}


def run(args):
    root = V._find_root(args.root)
    if not root:
        print("[sage review] TOOL ERROR: manifest 없음", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).read_text())
    except Exception as e:
        print(f"[sage review] TOOL ERROR: manifest 파싱 실패: {e}", file=sys.stderr)
        return 2

    assets = manifest.get("assets", {})
    prefixes = []
    if args.kind in ("hook", "all"):
        prefixes.append("hooks/")
    if args.kind in ("agent", "all"):
        prefixes.append("agents/")
    if args.kind in ("skill", "all"):
        prefixes.append("skills/")   # skill(interpretive) 도 승인 UX 대상 (누락 수정)
    if args.kind in ("mcp", "all"):
        prefixes.append("mcps/")     # mcp(declarative) 도 승인 UX 대상
    ids = sorted(k for k in assets if any(k.startswith(p) for p in prefixes))

    # MCP managed-block/.mcp.json 무결성은 자산 횡단(run-level) 검사라 per-asset _validate_mcp 가 못 본다.
    # review 가 이를 안 거치면 블록 안 주입 서버가 auto-approve 된다(codex R6) → 여기서 1회 검사해 반영.
    mcp_tamper = False
    if args.kind in ("mcp", "all"):
        _mcp_ids = [k.split("/", 1)[1] for k in assets if k.startswith("mcps/")]
        _codex_ids = [k.split("/", 1)[1] for k in assets if k.startswith("mcps/")
                      and "codex" in (assets[k].get("runtime_targets") or [])]
        _osev, _ = V._mcp_ownership_check(root, _mcp_ids, _codex_ids)
        mcp_tamper = (_osev == "FAIL")

    auto, review = [], []
    for aid in ids:
        entry = assets[aid]
        if aid.startswith("hooks/"):
            sev, _ = V._validate_hook(root, aid, entry, run_regression=False)
        elif aid.startswith("mcps/"):
            sev, _ = V._validate_mcp(root, aid, entry)
            # 블록 무결성 위반(미선언 서버 주입 등) → 해당 codex-target 자산 자동승인 차단(end-to-end 폐쇄)
            if mcp_tamper and "codex" in (entry.get("runtime_targets") or []) and sev == "PASS":
                sev = "FAIL"
        else:
            sev, _ = V._validate_interpretive(root, aid, entry, run_regression=False)
        d = auto_approve_decision(aid, sev, entry)
        (auto if d["decision"] == "auto" else review).append((aid, d["reasons"]))

    print(f"== sage review ({args.kind}) — auto_approve_safe_default ==")
    if args.batch:
        print(f"✅ auto-approved (batch): {len(auto)}건 — {', '.join(a for a, _ in auto) or '없음'}")
    else:
        print(f"✅ auto-approved: {len(auto)}건 (사람 확인 불필요)")
        for aid, _ in auto:
            print(f"   - {aid}")
    print(f"⚠️  review 필요: {len(review)}건 (사람 검토 예외)")
    for aid, reasons in review:
        print(f"   - {aid}: {', '.join(reasons)}")

    if args.gate and review:
        print("---- GATE: review 버킷 존재 → exit 1 ----")
        return 1
    return 0
