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
    elif k == "warn_l0_l3_content":
        m = f"⚠️  [GATE WARN — L0] 문서/plan 에 L3 내용 키워드 감지 — 민감정보 노출 점검. 파일: {fs}"
    elif k == "block_phase_incomplete":
        miss = ", ".join(d.get("missing_phases") or [])
        m = (f"⛔ [GATE BLOCK — {d.get('risk')}] 의무 PDCA phase 미작성: [{miss}]. 파일: {fs} | 근거: {rs}\n"
             f"  해당 phase 문서를 먼저 작성하세요 (docs/agent/pdca-templates.md)")
    elif k == "warn_phase_incomplete":
        miss = ", ".join(d.get("missing_phases") or [])
        m = f"⚠️  [GATE WARN — L1] 권장 PDCA phase 미작성: [{miss}]. 파일: {fs}"
    elif k == "block_report_without_approval":
        m = f"⛔ [GATE BLOCK — PDCA] {rs}. 파일: {fs}\n  approve phase 문서에 APPROVED 기록 후 report 작성"
    elif k == "block_report_without_audit":
        m = (f"⛔ [GATE BLOCK — PDCA] {rs}. 파일: {fs}\n"
             f"  Phase 05 를 /sage-review 로 돌려 loop 을 닫고(APPROVED) 05 문서에 'Loop-Run: <run_id>' 를 기록하세요")
    elif k == "warn_report_without_audit":
        m = (f"⚠️  [GATE WARN — PDCA] {rs}. 파일: {fs}\n"
             f"  (advisory) Phase 05 리뷰 루프 audit 증거 권장 — /sage-review 로 loop 실행 + 05 에 'Loop-Run: <run_id>' 기록")
    elif k == "ok_l3":
        m = f"✅ [GATE OK — L3] review 확인됨 | {fs}"
    elif k == "ok_l2":
        m = f"✅ [GATE OK — L2] plan 확인 | {fs}"
    else:
        m = ""
    if m:
        print(m)
    return d["exit_code"]


def render_declared_capture(level):
    # Claude 출력 프로토콜: plain text (stdout = additionalContext)
    print(f"ℹ️  [Risk 선언 포착] 이번 세션 작업 레벨: {level} — 소스 수정 시 해당 레벨 게이트가 적용됩니다.")


# --- post-tool-logger IO (Claude: tool_input.file_path 단일) ---
def logger_tool_name(raw):
    return raw.get("tool_name", "") or ""


def extract_logged_changes(raw, rel):
    fp = (raw.get("tool_input") or {}).get("file_path") or ""
    return [{"path": rel(fp), "op": "write"}] if fp else []


# --- pre-phase4-checklist-gate IO (Claude) ---
def extract_phase4_changes(raw, rel):
    fp = (raw.get("tool_input") or {}).get("file_path") or ""
    return [{"path": rel(fp), "op": "write"}] if fp else []


def render_phase4(decision):
    dec = decision
    s = dec["status"]
    if s == "block":
        lines = [f"⛔ [GATE BLOCK — Phase 3→4] 체크리스트 미완료 {dec['total_unchecked']}건",
                 f"  기능: {dec['base']}",
                 "  04-analyze 작성 전 아래 항목을 완료(또는 N/A 사유와 함께 [x])하세요:"]
        for ev in dec["evidence"]:
            lines.append(f"  ▸ {ev['label']}: {ev['file']} ({len(ev['unchecked'])}건 미완료)")
            for it in ev["unchecked"][:6]:
                t = it["text"]
                lines.append(f"      L{it['line']}: {t if len(t) <= 90 else t[:87] + '...'}")
            extra = len(ev["unchecked"]) - 6
            if extra > 0:
                lines.append(f"      ... 외 {extra}건")
        msg = "\n".join(lines)
    elif s == "warn":
        msg = f"⚠️  [GATE WARN — Phase 3→4] '{dec['base']}' 의 03-implementation 문서를 찾지 못했습니다."
    elif s == "ok":
        msg = f"✅ [GATE OK — Phase 3→4] '{dec['base']}' 체크리스트 완료 확인"
    else:
        msg = ""
    if msg:
        print(msg)
    return dec["exit_code"]


# --- stop-compliance-report IO (Claude) ---
def attach_policy_results(model, profile, entries, raw_text, kc_result):
    # F7: claude 도 knowledge_capture 주입. output_contract 는 미적용(Codex-only 설계 + 마커 비독립).
    model["sections"]["policy_results"].append(kc_result)


def render_report_saved(today):
    print(f"📋 Compliance report saved: .claude/logs/compliance-{today}.md")
