#!/bin/bash
# pre-implementation-gate — Claude adapter (rendered, 부분추출)
# SSOT: scripts/sage_harness/hooks/pre_implementation_gate_core.py
# adapter: 입력추출(file_path+content) / declared_max 읽기 / plan_files snapshot / 출력렌더 / 경로바인딩.
# L3 review 매칭 전략은 UNRESOLVED(미선택) → core 가 L3 를 BLOCK+override (안전 바닥). (직접수정 금지)
# profile 외부주입 필수($SAGE_PROFILE) — 없으면 통과.

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
CORE_DIR="${SAGE_HOOK_CORE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BRANCH=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)
INPUT=$(cat)

SAGE_HOOK_INPUT="$INPUT" SAGE_BRANCH="${SAGE_GATE_BRANCH:-$BRANCH}" python3 - "$PROJECT_ROOT" "$CORE_DIR" <<'PYEOF'
import sys, os, json, glob, re
root, core_dir = sys.argv[1], sys.argv[2]
sys.path.insert(0, core_dir)
import pre_implementation_gate_core as core

try:
    raw = json.loads(os.environ.get("SAGE_HOOK_INPUT", "{}"))
except Exception as e:
    # malformed 입력 = 신뢰 런타임의 transient 글리치 → fail-open(availability) 하되 silent 금지(surface).
    print(f"[pre-implementation-gate] hook 입력 JSON 파싱 실패 → 이번 호출 게이트 skip: {type(e).__name__}", file=sys.stderr)
    sys.exit(0)

prof_path = os.environ.get("SAGE_PROFILE", "")
if not prof_path or not os.path.exists(prof_path):
    sys.exit(0)
try:
    with open(prof_path, encoding="utf-8") as f:
        profile = json.load(f)
except Exception as e:
    # profile 파싱 실패 = 위험 게이트 무력화. fail-closed 면 profile 수정 Edit 도 차단되는 deadlock →
    # fail-open(exit0) 하되 LOUD surface 로 무력화 상태 가시화(조용한 gate-disable = Pattern A 방지).
    print(f"⛔ [pre-implementation-gate] profile 파싱 실패 → 위험 게이트 무력화(SAGE_PROFILE 수정 필요): "
          f"{type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(0)

def rel(p):
    if not p: return ""
    if not os.path.isabs(p): return p
    try: return os.path.relpath(p, root)
    except Exception: return p

ti = raw.get("tool_input") or {}
fp = ti.get("file_path") or ""
blob = (ti.get("content") or "") or (ti.get("new_string") or "")
for e in (ti.get("edits") or []):
    blob += "\n" + (e.get("new_string") or "")
changes = [{"path": rel(fp), "op": "write", "content": blob}] if fp else []

# declared_max: capture-declared-risk 가 쓴 세션 파일 (있으면)
declared = None
sid = re.sub(r"[^A-Za-z0-9_-]", "_", raw.get("session_id", "") or "nosession")[:64]
dp = os.path.join(root, ".claude", "logs", f"declared-risk-{sid}.json")
try:
    with open(dp, encoding="utf-8") as f:
        declared = json.load(f).get("level")
except Exception:
    pass

event = {"hook_id": "pre-implementation-gate", "hook_event_name": "PreToolUse", "runtime": "claude",
         "session_id": raw.get("session_id", "") or "", "branch": os.environ.get("SAGE_BRANCH", ""),
         "declared_max": declared, "changes": changes}

# snapshot: plan_files. plan_glob 은 profile 주입(독립 — 경로 하드코딩/디렉토리 가정 제거).
pg = (profile.get("risk") or {}).get("plan_glob", "")   # 미설정/무효 → plan scan 없음(graceful)
if pg and (os.path.isabs(pg) or ".." in pg.split("/")):  # root 밖 glob 거부 → 경로 fallback 대신 빈 scan
    pg = ""
import time as _t
paths = sorted(glob.glob(os.path.join(root, pg), recursive=True), key=lambda p: -os.path.getmtime(p)) if pg else []
_now = _t.time()
plan_files = []
for p in paths:
    try:
        with open(p, encoding="utf-8", errors="ignore") as f: c = f.read()
    except Exception: c = ""
    recent = (_now - os.path.getmtime(p)) <= 7 * 86400   # 원본 -mtime -7 충실성
    plan_files.append({"path": rel(p), "content": c, "recent": recent})
# review_candidates: review 매칭 전략 입력(최근 30일 plan/review 문서)
review_candidates = [pf for pf, p in zip(plan_files, paths) if (_now - os.path.getmtime(p)) <= 30 * 86400]

# PDCA phase 문서 스캔(phase 강제용). profile.pdca.phases=[{id,glob}] — glob 은 root 상대(독립).
phase_docs = {}
_pdca = profile.get("pdca") or {}
if _pdca.get("enabled"):
    for ph in (_pdca.get("phases") or []):
        pid, pglob = ph.get("id"), ph.get("glob") or ""
        if not pid or not pglob or os.path.isabs(pglob) or ".." in pglob.split("/"):
            continue   # root 밖/무효 glob 거부
        docs = []
        for p in glob.glob(os.path.join(root, pglob), recursive=True):
            try:
                with open(p, encoding="utf-8", errors="ignore") as f: cc = f.read()
            except Exception: cc = ""
            docs.append({"path": rel(p), "content": cc, "recent": (_now - os.path.getmtime(p)) <= 7 * 86400})
        phase_docs[pid] = docs
snapshot = {"plan_files": plan_files, "review_candidates": review_candidates, "phase_docs": phase_docs}

# L3 review 매칭 전략: profile.risk.l3_review_strategy(독립 — 엔진 하드코딩 아님). 미설정 시 None(안전 BLOCK).
strategy_result = None
strat = (profile.get("risk") or {}).get("l3_review_strategy", "")
if strat:
    import importlib
    # 전략은 SAGE 코어 자산 → CORE_DIR(스크립트 위치) 기준, 타겟 프로젝트 root 아님
    sys.path.insert(0, os.path.join(core_dir, "strategies", "pre_implementation_gate"))
    try:
        smod = importlib.import_module(strat)
        rk = profile.get("risk") or {}
        ftoks = set()
        for c in changes:                       # whole-path 아닌 토큰으로(전략이 토큰 겹침 비교)
            cp = c["path"]
            ftoks |= {t.lower() for t in re.split(r"[^A-Za-z0-9가-힣]+", cp + " " + os.path.basename(cp)) if len(t) >= 3}
        signals = {"tickets": set(re.findall(r"[0-9]+", event.get("branch", "") or "")),
                   "plan": set(), "files": ftoks,
                   "generic_tokens": rk.get("generic_tokens") or [],   # 전략 확장(profile 주입)
                   "review_patterns": rk.get("review_patterns") or []}
        strategy_result = smod.find_l3_review(signals, snapshot)
    except Exception as e:
        # F8b: 전략 크래시를 조용히 None 처리하면 block_l3_strategy_unresolved(="전략 미선택")로
        # 둔갑해 진짜 원인(import 실패/패턴 오류 등)이 숨는다 → 에러를 surface 하고 fail-closed BLOCK 유지.
        print(f"[pre-implementation-gate] L3 전략 '{strat}' 실행 오류 → fail-closed BLOCK: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        strategy_result = None
decision = core.decide(event, profile, snapshot, strategy_result)

def msg(d):
    k = d.get("message_key")
    fs = d.get("file_short", ""); rs = d.get("reason", "")
    if k == "block_desktop":
        hint = (profile.get("risk") or {}).get("desktop_block_hint", "원본 경로 수정 후 동기화")
        return f"⛔ [GATE BLOCK] 동기화 산출물/금지 경로 직접수정 금지. 파일: {fs}\n  → {hint}"
    if k == "block_l3_no_plan":
        return f"⛔ [GATE BLOCK — L3] L3 작업 + plan 문서 없음. 파일: {fs} | 근거: {rs}\n  plan 문서 생성 + L3 리뷰 프로토콜(2라운드) 수행"
    if k == "block_l3_strategy_unresolved":
        return f"⛔ [GATE BLOCK — L3] L3 review 매칭 전략 미선택(unresolved) → 리뷰 확인 불가. 파일: {fs} | 근거: {rs}\n  (override required: SAGE manifest 에서 find_l3_review 전략 canonical 선택 필요)"
    if k == "warn_l3_no_review":
        return f"⚠️  [GATE WARN — L3] 2라운드 리뷰 문서 미확인. 파일: {fs} | 근거: {rs}"
    if k == "warn_l2_no_plan":
        return f"⚠️  [GATE WARN — L2] 소스/설정 변경인데 plan 문서 없음. 파일: {fs} | 근거: {rs}"
    if k == "block_phase_incomplete":
        miss = ", ".join(d.get("missing_phases") or [])
        return (f"⛔ [GATE BLOCK — {d.get('risk')}] 의무 PDCA phase 미작성: [{miss}]. 파일: {fs} | 근거: {rs}\n"
                f"  해당 phase 문서를 먼저 작성하세요 (docs/agent/pdca-templates.md)")
    if k == "warn_phase_incomplete":
        miss = ", ".join(d.get("missing_phases") or [])
        return f"⚠️  [GATE WARN — L1] 권장 PDCA phase 미작성: [{miss}]. 파일: {fs}"
    if k == "block_report_without_approval":
        return f"⛔ [GATE BLOCK — PDCA] {rs}. 파일: {fs}\n  approve phase 문서에 APPROVED 기록 후 report 작성"
    if k == "ok_l3": return f"✅ [GATE OK — L3] review 확인됨 | {fs}"
    if k == "ok_l2": return f"✅ [GATE OK — L2] plan 확인 | {fs}"
    return ""

m = msg(decision)
if m: print(m)
sys.exit(decision["exit_code"])
PYEOF
exit $?
