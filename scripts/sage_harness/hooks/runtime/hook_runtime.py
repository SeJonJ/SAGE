"""hook_runtime — 어댑터에 복제돼 있던 IO 오케스트레이션의 공유 단일소스 (외부검토 R1 / P0-1).

claude/codex 어댑터가 바이트 단위로 복제하던 profile 로드·rel·snapshot 빌드·L3 전략 로드·
core.decide 호출을 여기로 1회만 들어올린다(verbatim lift — 동작 무변경). 런타임이 진짜 다른
입력추출/declared 읽기/출력렌더만 io_claude/io_codex 로 분리.

보존 원칙(원본 어댑터와 동일):
- 입력 JSON 파싱 실패 = transient 글리치 → fail-open(exit0) 하되 stderr surface(silent 금지).
- profile 파싱 실패 = 게이트 무력화 → fail-open 하되 LOUD surface(조용한 gate-disable = Pattern A 방지).
- root 밖/절대경로 glob 거부(독립성). L3 전략 크래시는 surface + fail-closed(None → core BLOCK 유지, F8b).
"""
import glob
import importlib
import json
import os
import re
import sys
import time


def load_profile_fail_open(hook_id):
    """SAGE_PROFILE 로드. 미설정/부재 → None(게이트 통과). 파싱실패 → None + LOUD surface."""
    prof_path = os.environ.get("SAGE_PROFILE", "")
    if not prof_path or not os.path.exists(prof_path):
        return None
    try:
        with open(prof_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⛔ [{hook_id}] profile 파싱 실패 → 위험 게이트 무력화(SAGE_PROFILE 수정 필요): "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return None


def parse_input_fail_open(hook_id, raw_text):
    """stdin raw → dict. 실패 → None(호출자가 exit0) + stderr surface."""
    try:
        return json.loads(raw_text or "{}")
    except Exception as e:
        print(f"[{hook_id}] hook 입력 JSON 파싱 실패 → 이번 호출 게이트 skip: {type(e).__name__}",
              file=sys.stderr)
        return None


def make_rel(root):
    """절대경로 → root 상대(독립). 비절대/빈값/실패는 그대로."""
    def rel(p):
        if not p:
            return ""
        if not os.path.isabs(p):
            return p
        try:
            return os.path.relpath(p, root)
        except Exception:
            return p
    return rel


def build_snapshot(profile, root, rel):
    """plan_files / review_candidates / phase_docs 스냅샷. glob 은 profile 주입(경로 하드코딩 없음)."""
    pg = (profile.get("risk") or {}).get("plan_glob", "")   # 미설정/무효 → plan scan 없음(graceful)
    if pg and (os.path.isabs(pg) or ".." in pg.split("/")):  # root 밖 glob 거부 → 빈 scan
        pg = ""
    paths = sorted(glob.glob(os.path.join(root, pg), recursive=True),
                   key=lambda p: -os.path.getmtime(p)) if pg else []
    now = time.time()
    plan_files = []
    for p in paths:
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                c = f.read()
        except Exception:
            c = ""
        plan_files.append({"path": rel(p), "content": c, "recent": (now - os.path.getmtime(p)) <= 7 * 86400})
    review_candidates = [pf for pf, p in zip(plan_files, paths) if (now - os.path.getmtime(p)) <= 30 * 86400]

    phase_docs = {}
    pdca = profile.get("pdca") or {}
    if pdca.get("enabled"):
        for ph in (pdca.get("phases") or []):
            pid, pglob = ph.get("id"), ph.get("glob") or ""
            if not pid or not pglob or os.path.isabs(pglob) or ".." in pglob.split("/"):
                continue   # root 밖/무효 glob 거부
            docs = []
            for p in glob.glob(os.path.join(root, pglob), recursive=True):
                try:
                    with open(p, encoding="utf-8", errors="ignore") as f:
                        cc = f.read()
                except Exception:
                    cc = ""
                docs.append({"path": rel(p), "content": cc, "recent": (now - os.path.getmtime(p)) <= 7 * 86400})
            phase_docs[pid] = docs
    return {"plan_files": plan_files, "review_candidates": review_candidates, "phase_docs": phase_docs}


def run_strategy(hook_id, profile, core_dir, changes, event, snapshot):
    """L3 review 매칭 전략(profile.risk.l3_review_strategy) 로드·실행. 미설정 → None(안전 BLOCK).

    크래시를 조용히 None 처리하면 '전략 미선택'으로 둔갑해 진짜 원인이 숨음 → surface + fail-closed(F8b).
    """
    strat = (profile.get("risk") or {}).get("l3_review_strategy", "")
    if not strat:
        return None
    # 전략은 SAGE 코어 자산 → CORE_DIR 기준(타겟 프로젝트 root 아님)
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
        return smod.find_l3_review(signals, snapshot)
    except Exception as e:
        print(f"[{hook_id}] L3 전략 '{strat}' 실행 오류 → fail-closed BLOCK: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return None


def run_pre_implementation_gate(io, root, core_dir, branch, raw_text):
    """pre-implementation-gate 오케스트레이터. io = io_claude | io_codex (런타임별 IO만 위임)."""
    hid = "pre-implementation-gate"
    raw = parse_input_fail_open(hid, raw_text)
    if raw is None:
        return 0
    if io.should_skip(raw):                      # codex: tool_name!=apply_patch 면 skip / claude: 항상 처리
        return 0
    profile = load_profile_fail_open(hid)
    if profile is None:
        return 0

    rel = make_rel(root)
    changes = io.extract_changes(raw, rel)       # ← 런타임별 (file_path vs apply_patch)
    declared = io.read_declared_level(raw, root)  # ← 런타임별 ($host/logs)
    event = {"hook_id": hid, "hook_event_name": "PreToolUse", "runtime": io.RUNTIME,
             "session_id": raw.get("session_id", "") or "", "branch": branch,
             "declared_max": declared, "changes": changes}
    snapshot = build_snapshot(profile, root, rel)
    strategy_result = run_strategy(hid, profile, core_dir, changes, event, snapshot)

    sys.path.insert(0, core_dir)
    import pre_implementation_gate_core as core
    decision = core.decide(event, profile, snapshot, strategy_result)
    return io.render_gate(decision, profile)     # ← 런타임별 채널/포맷/exit
