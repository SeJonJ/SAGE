"""io_claude — pre-implementation-gate 의 Claude 전용 IO (입력추출/declared/렌더). R1 분리.

런타임이 진짜 다른 부분만: Write/Edit/MultiEdit 입력추출, .claude/logs declared 읽기,
stdout 평문(emoji) 렌더. 본문 로직(snapshot/전략/decide)은 hook_runtime 공유.
msg 테이블은 원본 claude 어댑터에서 verbatim 이식(출력 문자열 무변경).
"""
import json
import os
import re

RUNTIME = "claude"
HOST_DIR = ".claude"
ROOT_ENV = "CLAUDE_PROJECT_DIR"


def should_skip(raw):
    return False   # claude: 모든 Write/Edit/MultiEdit 대상


def extract_changes(raw, rel):
    ti = raw.get("tool_input") or {}
    fp = ti.get("file_path") or ""
    blob = (ti.get("content") or "") or (ti.get("new_string") or "")
    for e in (ti.get("edits") or []):
        blob += "\n" + (e.get("new_string") or "")
    return [{"path": rel(fp), "op": "write", "content": blob}] if fp else []


def read_declared_level(raw, root):
    sid = re.sub(r"[^A-Za-z0-9_-]", "_", raw.get("session_id", "") or "nosession")[:64]
    dp = os.path.join(root, HOST_DIR, "logs", f"declared-risk-{sid}.json")
    try:
        with open(dp, encoding="utf-8") as f:
            return json.load(f).get("level")
    except Exception:
        return None


def render_gate(decision, profile):
    d = decision
    k = d.get("message_key")
    fs = d.get("file_short", "")
    rs = d.get("reason", "")
    if k == "block_desktop":
        hint = (profile.get("risk") or {}).get("desktop_block_hint", "원본 경로 수정 후 동기화")
        m = f"⛔ [GATE BLOCK] 동기화 산출물/금지 경로 직접수정 금지. 파일: {fs}\n  → {hint}"
    elif k == "block_l3_no_plan":
        m = f"⛔ [GATE BLOCK — L3] L3 작업 + plan 문서 없음. 파일: {fs} | 근거: {rs}\n  plan 문서 생성 + L3 리뷰 프로토콜(2라운드) 수행"
    elif k == "block_l3_strategy_unresolved":
        m = f"⛔ [GATE BLOCK — L3] L3 review 매칭 전략 미선택(unresolved) → 리뷰 확인 불가. 파일: {fs} | 근거: {rs}\n  (override required: SAGE manifest 에서 find_l3_review 전략 canonical 선택 필요)"
    elif k == "warn_l3_no_review":
        m = f"⚠️  [GATE WARN — L3] 2라운드 리뷰 문서 미확인. 파일: {fs} | 근거: {rs}"
    elif k == "warn_l2_no_plan":
        m = f"⚠️  [GATE WARN — L2] 소스/설정 변경인데 plan 문서 없음. 파일: {fs} | 근거: {rs}"
    elif k == "block_phase_incomplete":
        miss = ", ".join(d.get("missing_phases") or [])
        m = (f"⛔ [GATE BLOCK — {d.get('risk')}] 의무 PDCA phase 미작성: [{miss}]. 파일: {fs} | 근거: {rs}\n"
             f"  해당 phase 문서를 먼저 작성하세요 (docs/agent/pdca-templates.md)")
    elif k == "warn_phase_incomplete":
        miss = ", ".join(d.get("missing_phases") or [])
        m = f"⚠️  [GATE WARN — L1] 권장 PDCA phase 미작성: [{miss}]. 파일: {fs}"
    elif k == "block_report_without_approval":
        m = f"⛔ [GATE BLOCK — PDCA] {rs}. 파일: {fs}\n  approve phase 문서에 APPROVED 기록 후 report 작성"
    elif k == "ok_l3":
        m = f"✅ [GATE OK — L3] review 확인됨 | {fs}"
    elif k == "ok_l2":
        m = f"✅ [GATE OK — L2] plan 확인 | {fs}"
    else:
        m = ""
    if m:
        print(m)
    return d["exit_code"]
