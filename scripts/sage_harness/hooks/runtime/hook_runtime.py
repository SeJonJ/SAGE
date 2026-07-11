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
import posixpath
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
    # 게이트 hook 이므로 malformed 입력을 surface(5-1): pre-implementation-gate 와 일관.
    # silent fail-open 은 게이트가 조용히 열린 걸 숨긴다(비게이트 logger 와 달리). fail-closed 전환은
    # transient 입력 전면차단 위험이라 별도 설계결정(보류) — 여기선 비silent 화까지만.
    raw = parse_input_fail_open(hid, raw_text, surface=True)
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


_LOOP_RUN_RE = re.compile(r"(?im)^\s*Loop-Run:\s*(\S+)\s*$")   # pre_implementation_gate_core.py 와 동일 어휘


def _pdca_phase_glob(profile, phase_id):
    for ph in ((profile.get("pdca") or {}).get("phases") or []):
        if ph.get("id") == phase_id:
            return ph.get("glob") or ""
    return ""


def _safe_glob(root, pglob):
    """root 밖/절대경로/`..` 탈출 glob 은 거부(build_snapshot 과 동일 방어 — 독립성) 후 실제 매치 경로.
    `glob.glob(recursive=True)` 를 쓴다 — `fnmatch` 는 `foo/**/*.md` 가 `foo/x.md`(0 단계 디렉토리)에
    안 걸린다(codex 구현리뷰 P0: 표준 06 glob `plan_docs/06-report/**/*.md` 가 06 문서를 직속 자식으로
    두면 fnmatch 로는 영원히 매치 안 돼 게이트가 항상 조용히 skip). glob.glob 은 `**` 를 문서화된 대로
    "0개 이상의 디렉토리"로 올바르게 해석한다."""
    if not pglob or os.path.isabs(pglob) or ".." in pglob.split("/"):
        return []
    return glob.glob(os.path.join(root, pglob), recursive=True)


def _canon_relkey(s):
    """root-상대 경로를 대조용 정규 키로. 세션 로그의 `entries[].file`(logger 가 그대로 저장)과
    glob 결과가 표기만 달라 조용히 공집합이 되는 것을 막는다(codex 구현리뷰 2R P1): `\\`→`/`,
    선행 `./` 제거, 중복 슬래시 정리(posixpath.normpath). 양쪽에 동일 적용해야 의미가 있다.
    심링크로 06 을 두고 target 경로로 편집하는 경우는 표기정규화로도 안 잡혀 공집합→skip(fail-open,
    잘못된 block 은 아님) — v1 은 심링크 06 을 지원 대상으로 명시하지 않는다."""
    s = (s or "").replace("\\", "/")
    return posixpath.normpath(s) if s else ""


def _glob_relmap(root, pglob):
    """{정규 키: abspath} — glob 매치 파일을 세션 로그 키(정규화)로 인덱싱."""
    return {_canon_relkey(os.path.relpath(p, root)): p for p in _safe_glob(root, pglob)}


def _glob_relpaths(root, pglob):
    """세션 로그의 상대경로(`entries[].file`)와 직접 대조하기 위한 root-상대 정규 키 집합."""
    return set(_glob_relmap(root, pglob).keys())


_H2_PLUS_RE = re.compile(r"#{2,}(?:\s|$)")   # H2 이상 ATX 헤딩 = 본문 섹션 시작(H1 제목은 종료로 보지 않음)


def _header_loop_run_ids(content):
    """06 문서 **최상단 메타데이터 블록**의 Loop-Run run_id 집합. 첫 H2 이상 헤딩 전까지만 본다.

    문서 전체를 finditer 하면(codex W1 R2 P2) 본문 섹션의 예시 코드블록에 든 `Loop-Run: rl-example` 까지
    매치돼 실제 run 과 상충으로 잡혀 false ambiguous BLOCK 이 난다. Loop-Run/Source-05 는 템플릿상 H1 제목
    바로 아래(첫 H2 전)에 오는 고정 헤더이므로 그 구간만 파싱한다. 헤딩 판정은 선행 공백/탭을 제거하고
    H2 이상(`##`+)만 종료로 본다(codex W1 R2 재검 P2: `  ## `·`##\t` 변형이 새어 본문 예시를 재파싱). 선두
    BOM 은 제거해 BOM+Loop-Run 시작 문서에서 마커를 놓치지 않는다. H1(`# `)은 제목이라 종료로 보지 않는다."""
    ids = set()
    for line in content.lstrip("\ufeff").splitlines():
        if _H2_PLUS_RE.match(line.lstrip()):
            break
        m = _LOOP_RUN_RE.match(line)
        if m:
            ids.add(m.group(1))
    return ids


def _session_06_run_ids(root, profile, session_files):
    """이번 세션에 쓰인 06 문서별로 자기선언한 Loop-Run run_id 집합. {정규 키: {run_ids}}.

    06 이 자기 사이클을 명시 선언(Loop-Run:)하게 하고 게이트는 06 만 읽는다. 05 를 stem 으로 추측해
    디스크에서 찾지 않는다(codex W1 P1 2건): 전역 stem 스캔은 (1) 다중 06 을 하나의 run_id 집합으로 합쳐
    결속 불가 06 을 이미 확인된 06 에 가리고, (2) 과거/타 디렉토리의 동명 05 를 이번 06 에 오결속한다.
    run_id 는 sage-review 가 05 에 기록하고 06 작성 시 06 으로 복사된다(쓰기 시점에 06←05 review_loop
    게이트가 그 run 결속을 이미 검증). 06 이 이번 세션 로그 ∩ glob 실존파일일 때만 인정한다. 한 06 에
    마커가 여럿이어도 finditer 로 전부 보아 상충을 포착한다 — 0개/2개↑ 판정은 호출부(_reduce_06_bindings)."""
    out = {}
    for key, path in _glob_relmap(root, _pdca_phase_glob(profile, "06")).items():
        if key not in session_files:
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            content = ""
        out[key] = _header_loop_run_ids(content)
    return out


def _reduce_06_bindings(per06_ids, audit_summary):
    """이번 세션 06 들의 자기선언 결속을 retro_gate.check 용 판정 (run_id, binding, checked, missing)으로 축약.

    **06 마다** 결속을 본다(codex W1 P1: 집계 run_id 는 결속 불가 06 을 확인된 다른 06 에 가리고, 정상
    다중 사이클을 모호로 오판한다). 한 06 이라도 마커가 정확히 1개가 아니면 결속 불가다 — 2개↑=상충
    (ambiguous), 0개=미선언(no_candidate). 전부 유일 결속이면 각 run 을 감사에서 확인한다: 대표 run_id 와
    checked 는 게이트 표시용(정렬 첫 미확인, 없으면 첫 run).

    missing 은 **유일 결속(마커 1개) 06 의 미확인 run 전체**다 — **다른 06 의 결속 불가와 무관하게** 모은다
    (codex W1 R2 재검 P1: 결속 불가 06 을 먼저 만나 즉시 missing=[] 를 반환하면, 같은 세션에서 유효 선언·미확인
    된 run 의 doctor 가시성이 사라져 R2 #2 가 다시 깨진다). 게이트 판정만 worst-case binding failure 로 축약한다.
    어댑터가 missing 전부를 record_missing 해야 다중 미확인이 첫 run 하나로 잘리지 않는다(codex W1 R2 P1)."""
    items = sorted(per06_ids.items())
    resolved = [next(iter(ids)) for _, ids in items if len(ids) == 1]
    missing = sorted({r for r in resolved if not bool((audit_summary.get(r) or {}).get("checked"))})
    if any(len(ids) > 1 for _, ids in items):
        return None, "ambiguous", False, missing
    if any(len(ids) == 0 for _, ids in items):
        return None, "no_candidate", False, missing
    if missing:
        return missing[0], "resolved", False, missing
    return resolved[0], "resolved", True, missing


def _stop_hook_active(raw):
    """Stop 입력의 `stop_hook_active` 를 안전하게 판정. 플랫폼은 JSON boolean 을 보내지만, 어댑터
    직렬화/스키마 변형에 대비해 bool True 와 문자열 "true"(대소문자 무관)만 active 로 본다(codex
    구현리뷰 P1: `bool("false")` 는 True 라 문자열 "false" 를 재시도로 오인해 첫 block 이 사라진다).

    방향성: 재시도(무한루프 방지)는 플랫폼이 `true` 를 보낼 때만 성립하므로 `true`/`"true"` 를 놓치지
    않으면 루프-안전이 유지되고, 그 외(`false`/`"false"`/누락/malformed)를 not-active 로 봐 첫 시도의
    teeth 를 보존한다."""
    v = raw.get("stop_hook_active")
    if v is True:
        return True
    return isinstance(v, str) and v.strip().lower() == "true"


def _session_log_entries(log_dir, session_id):
    """이번 세션(session_id)의 로그 엔트리를 로그 디렉토리의 **모든** session-*.jsonl 에서 모은다.

    로거는 UTC 날짜(now_utc[:10] = gmtime)로 session-YYYY-MM-DD.jsonl 을 쓰는데 Stop 은 로컬 날짜
    (localtime)로 파일 하나만 열어(codex 7R P0), KST 등 양수 오프셋의 자정 경계·UTC 자정을 넘는 세션에서
    파일명이 어긋나 게이트가 조용히 무동작한다. 세션 감지를 날짜 파일 하나가 아니라 session_id 로 전
    파일에서 걸러야 타임존/날짜와 무관하게 이번 세션을 놓치지 않는다(리포트 본문 집계 범위는 그대로 둔다)."""
    if not session_id:
        return []
    out = []
    for fp in glob.glob(os.path.join(log_dir, "session-*.jsonl")):
        try:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    if e.get("session") == session_id:
                        out.append(e)
        except Exception:
            continue
    return out


def retro_gate_result(profile, root, raw, session_entries):
    """retro_gate 정책 결과(양 런타임 공유, knowledge_capture 와 동형 — 9-C v1).

    raw = Stop 이벤트 원본(파싱됨, session_id/stop_hook_active 추출용). session_entries = 이번 세션의
    로그 엔트리(모든 session-*.jsonl 에서 session_id 로 모은 것 — _session_log_entries). 06/05 작성
    감지에만 쓴다(리포트 본문 집계 범위는 건드리지 않는다 — 기존 동작 보존)."""
    import retro_audit
    import retro_gate

    pdca_retro = (profile.get("pdca") or {}).get("retro")
    mode = (pdca_retro or {}).get("report_gate_enforce") or "off"
    kc = profile.get("knowledge_capture")
    kc = kc if isinstance(kc, dict) else {}
    # 게이트 활성 조건을 retro CLI 와 일치시킨다(codex 7R P1): CLI 는 `retro_note is True` 이고 vault 경로가
    # 실제로 잡혀야 노트를 쓴다(_vault.vault_target). 노트가 안 써지면 --check 대상이 없어 게이트가 통과
    # 불가능한 걸 강제하게 된다. bool(retro_note) 만 보면 "false"(문자열)·vault 미설정을 활성으로 오판한다.
    # vault 는 실제 디렉토리여야 한다(codex W1 R2 P1): 비어있지 않은 문자열이어도 일반 파일/`/dev/null`/권한
    # 불가 경로면 노트 디렉토리를 만들 수 없어 --check 대상이 없다 — isdir 로 usable vault 만 활성화한다.
    # 상대경로 vault 는 **project root 기준**으로 판정한다(codex W1 R2 재검 P1): 어댑터가 --root 만 넘기고
    # cd 하지 않아, raw 상대경로에 isdir 를 걸면 hook CWD 기준이 돼 정상 vault 도 조용히 무동작(INFO)한다.
    vp = kc.get("vault_path")
    vault = vp.strip() if isinstance(vp, str) else ""
    vault_abs = vault if os.path.isabs(vault) else os.path.join(root, vault)
    notes_enabled = (kc.get("retro_note") is True) and bool(vault) and os.path.isdir(vault_abs)

    # 06 감지는 이번 세션 로그 파일집합(정규 키) ∩ glob.glob(recursive) 실존파일로 한다.
    # fnmatch 로 `entries[].file` 을 직접 매칭하면 `**` 제로디렉토리 케이스를 놓친다(구현리뷰 1R P0).
    session_files = {_canon_relkey(e.get("file", "")) for e in session_entries}
    per06 = _session_06_run_ids(root, profile, session_files) if session_files else {}
    has_06 = bool(per06)

    run_id, binding, checked, missing = None, "resolved", False, []
    if has_06:
        run_id, binding, checked, missing = _reduce_06_bindings(per06, retro_audit.audit_summary(root))

    result = retro_gate.check(mode, has_06, run_id, checked, _stop_hook_active(raw), notes_enabled, binding)

    # 미완료 종료(게이트 활성 + 미확인 = WARN/BLOCK)를 .sage/retro_audit.jsonl 에 영구 기록한다 —
    # host 로그의 컴플라이언스 리포트와 별개로, doctor/다음 사이클이 볼 수 있는 커밋 대상 증거(유저 스코프).
    # **미확인 run 전부** 기록한다(codex W1 R2 P1): 다중 06 이 각기 미확인이면 대표 하나만 기록하던 옛
    # 코드는 나머지를 재시도 dedup 뒤 doctor 가시성에서 잃었다. 상태변화 시에만 append(record_missing 이
    # dedup). 기록 실패는 세션을 막지 않되(fail-open) **조용히 삼키지 않는다** — 리포트에 명시(구현리뷰 3R P1).
    if missing and result["severity"] in ("WARN", "BLOCK"):
        try:
            for rid in missing:
                retro_audit.record_missing(root, rid, note_path=None)
        except Exception as e:
            result = dict(result)
            result["text"] += f" (⚠️ retro_audit 기록 실패: {type(e).__name__} — 미완료 영구기록·doctor 가시성 유실)"

    return result


def run_stop_compliance_report(io, root, core_dir, raw_text):
    """stop-compliance-report 오케스트레이터(Stop). session JSONL → report.md.

    knowledge_capture 는 양 런타임 공유(F7). output_contract 는 codex 전용 → io.attach_policy_results 가
    런타임별로 policy_results 순서까지 결정(codex: [output_contract, knowledge_capture] / claude: [knowledge_capture]).
    retro_gate(9-C v1)는 그 뒤에 공유로 붙는다(호스트 무관 문구라 순서 분기 불필요).

    retro_gate 가 BLOCK 을 내면 이 함수가 exit 2 를 반환한다 — 기존 PreToolUse 게이트(io.render_gate)와
    동일한 "exit code 2 = block" 관례를 그대로 쓴다(이 저장소에 Stop 전용 JSON decision 프로토콜 선례가
    없어, 검증된 기존 관례를 재사용). `stop_hook_active` 가 true 인 재시도에서는 retro_gate 가 스스로
    severity 를 WARN 으로 낮추므로, 여기서 별도 처리 없이 model["exit_code"]==0 이 자연히 나온다
    (플랫폼 제약: 세션당 block 은 최대 1회 — retro_gate.py 문서 참조).
    """
    hid = "stop-compliance-report"
    today = os.environ.get("SAGE_TODAY") or time.strftime("%Y-%m-%d", time.localtime())
    log_dir = os.path.join(root, io.HOST_DIR, "logs")
    log_file = os.path.join(log_dir, f"session-{today}.jsonl")
    profile = load_profile_fail_open(hid)
    if profile is None:
        return 0

    # 리포트 본문은 오늘자(로컬 날짜) 파일을 그대로 쓴다(기존 집계 범위 보존). 게이트 세션 감지는 이와
    # 별개로 모든 session-*.jsonl 에서 이번 session_id 로 모은다 — 로거는 UTC 날짜로, Stop 은 로컬 날짜로
    # 파일명을 잡아 자정 경계에서 오늘자 파일이 아예 없을 수 있고(codex 7R P0), 그때 여기서 早期 return
    # 하면 게이트가 통째로 무동작한다. 그래서 오늘자 파일 부재만으로는 바로 종료하지 않는다.
    raw = parse_input_fail_open(hid, raw_text, surface=False) or {}   # session_id/stop_hook_active 추출용
    session_entries = _session_log_entries(log_dir, raw.get("session_id") or "")

    entries = []
    if os.path.exists(log_file):
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    elif not session_entries:
        return 0   # 오늘자 로그도, 이번 세션 로그도 없음 → 리포트/게이트 생략(기존 동작)

    snapshot = {"entries": entries, "today": today, "branch": resolve_branch(root, ""), "runtime": io.RUNTIME}
    event = {"hook_id": hid, "hook_event_name": "Stop", "runtime": io.RUNTIME}
    sys.path.insert(0, core_dir)
    sys.path.insert(0, os.path.join(core_dir, "policies"))
    import stop_compliance_report_core as core
    model = core.decide(event, profile, snapshot)

    kc_result = knowledge_capture_result(profile, entries)   # 공유(F7)
    io.attach_policy_results(model, profile, entries, raw_text, kc_result)  # 런타임별 정책+순서

    try:
        rg_result = retro_gate_result(profile, root, raw, session_entries)
    except Exception as e:
        # Stop 훅은 내부 오류로 세션을 막으면 안 된다(fail-open) — 게이트 판정 불가 시 skip 으로 낮춘다.
        rg_result = {"name": "retro_gate", "severity": "INFO",
                     "text": f"N/A — 게이트 판정 중 오류로 skip ({type(e).__name__})"}
    model["sections"]["policy_results"].append(rg_result)

    md = core.render_markdown(model)
    report = os.path.join(log_dir, f"compliance-{today}.md")
    with open(report, "a", encoding="utf-8") as f:
        f.write(md)
    io.render_report_saved(today)

    exit_code = model["exit_code"]
    if rg_result["severity"] == "BLOCK":
        # v1 스코프(유저 결정): claude host 만 실제 exit 2. codex 의 Stop lifecycle exit-2 차단은
        # 이 저장소에서 실 세션으로 검증된 적이 없다 — 검증 전 codex 에서 exit 2 를 내면 이 리포에서
        # 근거 없는 새 메커니즘에 기대는 셈이라, codex 는 리포트에만 BLOCK 을 남기고 세션은 통과시킨다.
        if io.RUNTIME == "claude":
            print(f"[stop-compliance-report] ❌ {rg_result['text']}")
            exit_code = 2
        else:
            print(f"[stop-compliance-report] ⚠️  (codex — 미검증 미차단) {rg_result['text']}")
    return exit_code
