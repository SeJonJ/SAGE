"""io_codex — pre-implementation-gate 의 Codex 전용 IO (입력추출/declared/렌더). R1 분리.

런타임이 진짜 다른 부분만: apply_patch 다중파일 파싱, .codex/logs declared 읽기,
block→stderr / 그 외→hookSpecificOutput JSON 렌더(채널). 본문 로직은 hook_runtime 공유,
사용자 문구는 messages 모듈 공유(5-3 — io_claude 와의 테이블 중복 제거).
"""
import json
import os
import re
import sys

import messages

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
    # 문구는 messages 공유(SSOT), 채널은 Codex=block→stderr / 그 외→hookSpecific JSON.
    m = messages.gate_text(decision, profile, RUNTIME)
    if decision["status"] == "block":
        if m:
            print(m, file=sys.stderr)
    elif m:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": m}},
                         ensure_ascii=False))
    return decision["exit_code"]


def render_declared_capture(level):
    # Codex 출력 프로토콜: hookSpecificOutput JSON
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": messages.declared_capture_text(level, RUNTIME)
        }
    }, ensure_ascii=False))


# --- post-tool-logger IO (Codex: apply_patch 본문 다중파일 + Move) ---
def logger_tool_name(raw):
    return "apply_patch"


def extract_logged_changes(raw, rel):
    command = (raw.get("tool_input") or {}).get("command") or ""
    changes = []
    for line in command.splitlines():
        op = path = None
        m = re.match(r"^\*\*\* (Add|Update|Delete) File: (.+)$", line)
        if m:
            op = m.group(1).lower()
            path = m.group(2).strip()
        else:
            m2 = re.match(r"^\*\*\* Move to: (.+)$", line)
            if m2:
                op = "move"
                path = m2.group(1).strip()
        if path:
            changes.append({"path": rel(path), "op": op})
    return changes


# --- pre-phase4-checklist-gate IO (Codex: apply_patch Add|Update 만) ---
def extract_phase4_changes(raw, rel):
    command = (raw.get("tool_input") or {}).get("command") or ""
    changes = []
    for line in command.splitlines():
        m = re.match(r"^\*\*\* (Add|Update) File: (.+)$", line)
        if m:
            changes.append({"path": rel(m.group(2).strip()), "op": m.group(1).lower()})
    return changes


def render_phase4(decision):
    dec = decision
    s = dec["status"]
    if s == "block":
        lines = [messages.phase4_block_header(dec['total_unchecked'], dec['base'], RUNTIME)]
        for ev in dec["evidence"]:
            lines.append(f"  - {ev['label']}: {ev['file']} ({len(ev['unchecked'])}건 미완료)")
        msg = "\n".join(lines)
    elif s == "warn":
        msg = messages.phase4_warn(dec['base'], RUNTIME)
    elif s == "ok":
        msg = messages.phase4_ok(dec['base'], RUNTIME)
    else:
        msg = ""
    if dec["status"] == "block":
        if msg:
            print(msg, file=sys.stderr)
    elif msg:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}},
                         ensure_ascii=False))
    return dec["exit_code"]


# --- stop-compliance-report IO (Codex) ---
def _last_assistant_text(path):
    if not path or not os.path.exists(path):
        return ""
    last = ""
    seen = 0
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                seen += 1
                if seen > 200000:   # audit P1: 거대 transcript DoS 방지 (라인 캡)
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                role = d.get("role") or (d.get("message") or {}).get("role")
                if role == "assistant":
                    c = d.get("content") or (d.get("message") or {}).get("content") or ""
                    last = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
    except Exception:
        return ""
    return last


def attach_policy_results(model, profile, entries, raw_text, kc_result):
    # Codex 전용 output_contract 먼저, 그 다음 공유 knowledge_capture (원본 순서 보존).
    import hook_runtime as hr
    import output_contract_check
    try:
        raw = json.loads(raw_text or "{}")
    except Exception:
        raw = {}
    transcript = raw.get("transcript_path", "") or ""
    has_code = any(e.get("type") in hr.code_types_of(profile) for e in entries)
    markers = (profile.get("output_contract") or {}).get("markers")   # EH-2: 프로젝트 고유 마커 주입(없으면 중립 기본)
    oc = output_contract_check.check(_last_assistant_text(transcript), has_code, markers)
    model["sections"]["policy_results"].append(oc)
    model["sections"]["policy_results"].append(kc_result)


def render_report_saved(today):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "Stop",
          "additionalContext": messages.report_saved_text(HOST_DIR, today, RUNTIME)}},
                     ensure_ascii=False))
