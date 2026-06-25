"""hook_runtime — 어댑터에 복제돼 있던 IO 오케스트레이션의 공유 단일소스 (외부검토 R1 / P0-1).

claude/codex 어댑터가 바이트 단위로 복제하던 profile 로드·rel·snapshot 빌드·L3 전략 로드·
core.decide 호출을 여기로 1회만 들어올린다(verbatim lift — 동작 무변경). 런타임이 진짜 다른
입력추출/declared 읽기/출력렌더만 io_claude/io_codex 로 분리.

보존 원칙(원본 어댑터와 동일):
- 입력 JSON 파싱 실패 = transient 글리치 → fail-open(exit0) 하되 stderr surface(silent 금지).
- profile 파싱 실패 = 게이트 무력화 → fail-open 하되 LOUD surface(조용한 gate-disable = Pattern A 방지).
- root 밖/절대경로 glob 거부(독립성). L3 전략 크래시는 surface + fail-closed(None → core BLOCK 유지, F8b).
"""
import calendar
import glob
import importlib
import json
import os
import re
import subprocess
import sys
import time


def resolve_branch(root, default=""):
    """현재 브랜치. SAGE_GATE_BRANCH 우선, 없으면 root 기준 git. git 실패 → default.

    default 는 hook 별 원본 fallback 보존용(pre-impl="" / post-tool-logger="unknown").
    git 성공 시 stdout 그대로(분리HEAD 등 빈 문자열 가능 — 원본 충실).
    """
    b = os.environ.get("SAGE_GATE_BRANCH")
    if b:
        return b
    try:
        return subprocess.run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return default


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


def parse_input_fail_open(hook_id, raw_text, surface=True):
    """stdin raw → dict. 실패 → None(호출자가 exit0).

    surface=True(게이트 hook): malformed 입력을 stderr surface(silent 금지 — Pattern A 방지).
    surface=False(비게이트 hook, 예: capture-declared-risk): 원본 어댑터가 silent exit0 이었으므로 보존.
    """
    try:
        return json.loads(raw_text or "{}")
    except Exception as e:
        if surface:
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

    # 9.5 report←approve audit 증거: loop_audit 요약을 core 에 주입(2층 — adapter 가 .sage 읽기, core 순수).
    # fail-open: audit 없음/손상이어도 빈 요약(게이트가 advisory/enforce 로 처리, snapshot 빌드는 안 깸).
    try:
        import loop_audit
        la = loop_audit.audit_summary(root)
    except Exception:
        la = {"runs": {}, "has_any_records": False}
    return {"plan_files": plan_files, "review_candidates": review_candidates,
            "phase_docs": phase_docs, "loop_audit": la}


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


def _maybe_override(hook_id, root, decision, changes):
    """게이트 BLOCK 을 활성 override(미만료)로 합법 우회 → 통과(True) 전 bypass 를 감사로그에 기록 (P1-5).

    순수 코어(IO 0)는 정책만 판정하고, 우회는 런타임/운영 관심사이므로 여기서 처리(코어 불변).
    안전: 정확히 이 게이트(또는 'all') 대상 미만료 grant 가 있을 때만 우회하며, 무엇을(message_key)
    어느 파일에 적용했는지 .sage/override.jsonl 에 남긴다. override_audit 미가용/비-block → False(원래 흐름).
    """
    if (decision or {}).get("status") != "block":
        return False
    try:
        import override_audit as ov
    except Exception:
        return False
    grants = ov.active_grants(root, gate=hook_id)
    if not grants:
        return False
    files = [c.get("path") for c in (changes or []) if c.get("path")]
    g = grants[0]
    ov.record_bypass(root, hook_id, files, decision.get("message_key"), g)
    print(f"⚠️  [{hook_id}] GATE BLOCK override 적용 — 사유: {g.get('reason')} "
          f"(만료 {g.get('expires_at')}, .sage/override.jsonl 감사). "
          f"우회: {decision.get('message_key')} | 파일: {', '.join(files) or '(미상)'}",
          file=sys.stderr)
    return True


def run_pre_implementation_gate(io, root, core_dir, raw_text):
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
             "session_id": raw.get("session_id", "") or "", "branch": resolve_branch(root, ""),
             "declared_max": declared, "changes": changes}
    snapshot = build_snapshot(profile, root, rel)
    strategy_result = run_strategy(hid, profile, core_dir, changes, event, snapshot)

    sys.path.insert(0, core_dir)
    import pre_implementation_gate_core as core
    decision = core.decide(event, profile, snapshot, strategy_result)
    if _maybe_override(hid, root, decision, changes):   # P1-5: 활성 override 면 BLOCK 우회(감사 기록)
        return 0
    return io.render_gate(decision, profile)     # ← 런타임별 채널/포맷/exit


def run_capture_declared_risk(io, root, core_dir, raw_text):
    """capture-declared-risk 오케스트레이터(UserPromptSubmit). 게이트 아님 → parse 실패 silent(원본 보존).

    cleanup(만료 state 삭제)·state write 는 런타임 무관 공유. 포착 메시지 렌더만 io 위임.
    """
    hid = "capture-declared-risk"
    raw = parse_input_fail_open(hid, raw_text, surface=False)
    if raw is None:
        return 0
    log_dir = os.path.join(root, io.HOST_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)

    sys.path.insert(0, core_dir)
    import capture_declared_risk_core as core
    event = {"hook_id": hid, "hook_event_name": "UserPromptSubmit", "runtime": io.RUNTIME,
             "session_id": raw.get("session_id", "") or "", "prompt": raw.get("prompt", "") or "",
             "now_utc": os.environ.get("SAGE_NOW_UTC") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    decision = core.decide(event)

    c = decision["cleanup"]
    now = time.time()
    for f in glob.glob(os.path.join(log_dir, c["pattern"])):
        try:
            if now - os.path.getmtime(f) > c["older_than_seconds"]:
                os.remove(f)
        except Exception:
            pass

    if decision["action"] == "capture":
        path = os.path.join(log_dir, decision["state_file"])
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(decision["state"], fh, ensure_ascii=False)
            io.render_declared_capture(decision["level"])
        except Exception:
            pass
    return decision["exit_code"]


def run_post_tool_logger(io, root, core_dir, raw_text):
    """post-tool-logger 오케스트레이터(PostToolUse). 변경 분류 JSONL append. 게이트 아님(parse silent)."""
    hid = "post-tool-logger"
    raw = parse_input_fail_open(hid, raw_text, surface=False)
    if raw is None:
        return 0
    if io.should_skip(raw):
        return 0
    profile = load_profile_fail_open(hid)
    if profile is None:                          # profile 외부주입 필수 — 없으면 noop
        return 0
    log_dir = os.path.join(root, io.HOST_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)

    rel = make_rel(root)
    event = {"hook_id": hid, "hook_event_name": "PostToolUse", "runtime": io.RUNTIME,
             "session_id": raw.get("session_id", "") or "", "tool": io.logger_tool_name(raw),
             "branch": resolve_branch(root, "unknown"),
             "now_utc": os.environ.get("SAGE_NOW_UTC") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "changes": io.extract_logged_changes(raw, rel)}

    sys.path.insert(0, core_dir)
    import post_tool_logger_core as core
    decision = core.decide(event, profile)
    if decision["action"] == "log":
        out = os.path.join(log_dir, decision["log_file"])
        with open(out, "a", encoding="utf-8") as fh:
            for e in decision["log_entries"]:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return decision["exit_code"]


def build_checklist_snapshot(core, event, profile, root):
    """pre-phase4 fs_adapter: core.plan_reads 가 요구한 glob 을 읽어 snapshot 구성(런타임 무관)."""
    reads = core.plan_reads(event, profile)
    glob_results, files = {}, {}
    for g in reads["globs"]:
        matches = sorted(os.path.relpath(p, root) for p in glob.glob(os.path.join(root, g)))
        glob_results[g] = matches
        for rp in matches:
            try:
                with open(os.path.join(root, rp), encoding="utf-8") as fh:
                    files[rp] = fh.read()
            except Exception:
                files[rp] = None
    return {"glob_results": glob_results, "files": files}


def run_pre_phase4_checklist_gate(io, root, core_dir, raw_text):
    """pre-phase4-checklist-gate 오케스트레이터(PreToolUse). 03→04 전환 시 체크리스트 완료 강제."""
    hid = "pre-phase4-checklist-gate"
    raw = parse_input_fail_open(hid, raw_text, surface=False)
    if raw is None:
        return 0
    if io.should_skip(raw):
        return 0
    profile = load_profile_fail_open(hid)
    if profile is None:
        return 0

    rel = make_rel(root)
    event = {"hook_id": hid, "hook_event_name": "PreToolUse", "runtime": io.RUNTIME,
             "session_id": raw.get("session_id", "") or "", "changes": io.extract_phase4_changes(raw, rel)}
    sys.path.insert(0, core_dir)
    import pre_phase4_checklist_gate_core as core
    snapshot = build_checklist_snapshot(core, event, profile, root)
    decision = core.decide(event, profile, snapshot)
    if _maybe_override(hid, root, decision, event["changes"]):   # P1-5: 활성 override 면 BLOCK 우회(감사 기록)
        return 0
    return io.render_phase4(decision)


def code_types_of(profile):
    """코드 타입 집합 — plan_gate_code_types 우선, 없으면 file_type_map 의 type 전체(도메인 하드코딩 금지)."""
    comp = profile.get("compliance", {}) or {}
    ct = set(comp.get("plan_gate_code_types") or [])
    if not ct:
        ct = {m.get("type") for m in (profile.get("file_type_map") or []) if m.get("type")}
    return ct


def _epoch_of_iso(s):
    try:
        return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None


def knowledge_capture_result(profile, entries):
    """knowledge_capture 정책 결과(양 런타임 공유 — F7). policies 는 호출 전 sys.path 에 있어야 함."""
    import knowledge_capture
    ct = code_types_of(profile)
    has_code = any(e.get("type") in ct for e in entries)
    vault = (profile.get("knowledge_capture", {}) or {}).get("vault_path", "") or ""
    wiki_log = os.path.join(vault, "wiki", "log.md") if vault else ""
    wiki_mtime = os.path.getmtime(wiki_log) if (wiki_log and os.path.exists(wiki_log)) else None
    code_ts = [t for t in (_epoch_of_iso(e.get("ts", "")) for e in entries if e.get("type") in ct) if t]
    earliest = min(code_ts) if code_ts else None
    return knowledge_capture.check(vault, has_code, wiki_mtime, earliest)


def run_stop_compliance_report(io, root, core_dir, raw_text):
    """stop-compliance-report 오케스트레이터(Stop). session JSONL → report.md.

    knowledge_capture 는 양 런타임 공유(F7). output_contract 는 codex 전용 → io.attach_policy_results 가
    런타임별로 policy_results 순서까지 결정(codex: [output_contract, knowledge_capture] / claude: [knowledge_capture]).
    """
    hid = "stop-compliance-report"
    today = os.environ.get("SAGE_TODAY") or time.strftime("%Y-%m-%d", time.localtime())
    log_dir = os.path.join(root, io.HOST_DIR, "logs")
    log_file = os.path.join(log_dir, f"session-{today}.jsonl")
    if not os.path.exists(log_file):
        return 0   # 로그 없으면 리포트 생략
    profile = load_profile_fail_open(hid)
    if profile is None:
        return 0

    entries = []
    with open(log_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass

    snapshot = {"entries": entries, "today": today, "branch": resolve_branch(root, ""), "runtime": io.RUNTIME}
    event = {"hook_id": hid, "hook_event_name": "Stop", "runtime": io.RUNTIME}
    sys.path.insert(0, core_dir)
    sys.path.insert(0, os.path.join(core_dir, "policies"))
    import stop_compliance_report_core as core
    model = core.decide(event, profile, snapshot)

    kc_result = knowledge_capture_result(profile, entries)   # 공유(F7)
    io.attach_policy_results(model, profile, entries, raw_text, kc_result)  # 런타임별 정책+순서

    md = core.render_markdown(model)
    report = os.path.join(log_dir, f"compliance-{today}.md")
    with open(report, "a", encoding="utf-8") as f:
        f.write(md)
    io.render_report_saved(today)
    return model["exit_code"]
