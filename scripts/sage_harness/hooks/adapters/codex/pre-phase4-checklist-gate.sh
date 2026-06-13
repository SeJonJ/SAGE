#!/bin/bash
# pre-phase4-checklist-gate — Codex adapter (rendered)
# SSOT: scripts/sage_harness/hooks/pre_phase4_checklist_gate_core.py
# adapter 책임: 입력추출(apply_patch Add/Update targets) / fs_adapter(snapshot) / 경로·env 바인딩 /
#              출력렌더(block=stderr+exit2 / warn·ok=hookSpecificOutput JSON+exit0). gate 판정은 core. (직접수정 금지)
# profile 외부주입 필수($SAGE_PROFILE) — 없으면 통과(exit 0).

PROJECT_ROOT="${CODEX_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CORE_DIR="${SAGE_HOOK_CORE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

INPUT=$(cat)

SAGE_HOOK_INPUT="$INPUT" python3 - "$PROJECT_ROOT" "$CORE_DIR" <<'PYEOF'
import sys, os, re, glob, json
root, core_dir = sys.argv[1], sys.argv[2]
sys.path.insert(0, core_dir)
import pre_phase4_checklist_gate_core as core

try:
    raw = json.loads(os.environ.get("SAGE_HOOK_INPUT", "{}"))
except Exception:
    sys.exit(0)

if (raw.get("tool_name") or "") != "apply_patch":
    sys.exit(0)

prof_path = os.environ.get("SAGE_PROFILE", "")
if not prof_path or not os.path.exists(prof_path):
    sys.exit(0)
with open(prof_path, encoding="utf-8") as f:
    profile = json.load(f)

def rel(p):
    if not p:
        return ""
    if not os.path.isabs(p):
        return p
    try:
        return os.path.relpath(p, root)
    except Exception:
        return p

command = (raw.get("tool_input") or {}).get("command") or ""
changes = []
for line in command.splitlines():
    m = re.match(r"^\*\*\* (Add|Update) File: (.+)$", line)
    if m:
        changes.append({"path": rel(m.group(2).strip()), "op": m.group(1).lower()})

event = {"hook_id": "pre-phase4-checklist-gate", "hook_event_name": "PreToolUse",
         "runtime": "codex", "session_id": raw.get("session_id", "") or "", "changes": changes}

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
snapshot = {"glob_results": glob_results, "files": files}

decision = core.decide(event, profile, snapshot)


def build_msg(dec):
    s = dec["status"]
    if s == "block":
        lines = [f"[GATE BLOCK - Phase 3->4] 체크리스트 미완료 {dec['total_unchecked']}건 (기능: {dec['base']})"]
        for ev in dec["evidence"]:
            lines.append(f"  - {ev['label']}: {ev['file']} ({len(ev['unchecked'])}건 미완료)")
        return "\n".join(lines)
    if s == "warn":
        return f"[GATE WARN - Phase 3->4] '{dec['base']}' 의 03-implementation 문서를 찾지 못했습니다."
    if s == "ok":
        return f"[GATE OK - Phase 3->4] '{dec['base']}' 체크리스트 완료 확인"
    return ""

msg = build_msg(decision)
if decision["status"] == "block":
    if msg:
        print(msg, file=sys.stderr)
elif msg:
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}
    }, ensure_ascii=False))
sys.exit(decision["exit_code"])
PYEOF
exit $?
