"""io_codex — pre-implementation-gate 의 Codex 전용 IO (입력추출/declared/렌더). R1 분리.

런타임이 진짜 다른 부분만: apply_patch 다중파일 파싱, .codex/logs declared 읽기,
block→stderr / 그 외→hookSpecificOutput JSON 렌더. 본문 로직은 hook_runtime 공유.
msg 테이블은 원본 codex 어댑터에서 verbatim 이식(출력 문자열 무변경).
"""
import json
import os
import re
import sys

RUNTIME = "codex"
HOST_DIR = ".codex"
ROOT_ENV = "CODEX_PROJECT_ROOT"


def should_skip(raw):
    return (raw.get("tool_name") or "") != "apply_patch"


def extract_changes(raw, rel):
    # apply_patch 본문 → 파일별 {path, op, content(+라인 누적)}
    command = (raw.get("tool_input") or {}).get("command") or ""
    changes, cur = [], None
    for line in command.splitlines():
        m = re.match(r"^\*\*\* (Add|Update|Delete) File: (.+)$", line)
        if m:
            cur = {"path": rel(m.group(2).strip()), "op": m.group(1).lower(), "content": ""}
            changes.append(cur)
            continue
        if cur is not None and line.startswith("+"):
            cur["content"] += line[1:] + "\n"
    return changes


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
    table = {
        "block_desktop": f"[GATE BLOCK] 동기화 산출물/금지 경로 직접수정 금지. 파일: {fs} | {(profile.get('risk') or {}).get('desktop_block_hint','원본 경로 수정 후 동기화')}",
        "block_l3_no_plan": f"[GATE BLOCK - L3] L3 작업 + plan 문서 없음. 파일: {fs} | 근거: {rs}",
        "block_l3_strategy_unresolved": f"[GATE BLOCK - L3] L3 review 전략 미선택(unresolved) → 리뷰 확인 불가. 파일: {fs} (override required)",
        "warn_l3_no_review": f"[GATE WARN - L3] 2라운드 리뷰 문서 미확인. 파일: {fs} | 근거: {rs}",
        "warn_l2_no_plan": f"[GATE WARN - L2] 소스/설정 변경인데 plan 문서 없음. 파일: {fs} | 근거: {rs}",
        "block_phase_incomplete": f"[GATE BLOCK - {d.get('risk')}] 의무 PDCA phase 미작성: [{', '.join(d.get('missing_phases') or [])}]. 파일: {fs} | 근거: {rs} (docs/agent/pdca-templates.md)",
        "warn_phase_incomplete": f"[GATE WARN - L1] 권장 PDCA phase 미작성: [{', '.join(d.get('missing_phases') or [])}]. 파일: {fs}",
        "block_report_without_approval": f"[GATE BLOCK - PDCA] {rs}. 파일: {fs}",
        "ok_l3": f"[GATE OK - L3] review 확인됨 | {fs}",
        "ok_l2": f"[GATE OK - L2] plan 확인 | {fs}",
    }
    m = table.get(k, "")
    if d["status"] == "block":
        if m:
            print(m, file=sys.stderr)
    elif m:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": m}},
                         ensure_ascii=False))
    return d["exit_code"]
