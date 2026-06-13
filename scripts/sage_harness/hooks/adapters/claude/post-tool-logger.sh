#!/bin/bash
# post-tool-logger — Claude adapter (rendered)
# SSOT: scripts/sage_harness/hooks/post_tool_logger_core.py
# adapter 책임: 입력추출(Claude tool_input.file_path 단일) / 경로·env 바인딩 / branch·now_utc 관측 /
#              profile 로드 / 파일IO(JSONL append). 분류 알고리즘은 core. (generated artifact — 직접수정 금지)
# profile 외부주입 필수: $SAGE_PROFILE 없으면 noop(graceful).

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
LOG_DIR="$PROJECT_ROOT/.claude/logs"
CORE_DIR="${SAGE_HOOK_CORE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
mkdir -p "$LOG_DIR"

INPUT=$(cat)

SAGE_HOOK_INPUT="$INPUT" python3 - "$PROJECT_ROOT" "$LOG_DIR" "$CORE_DIR" <<'PYEOF'
import sys, os, json, subprocess, time
root, log_dir, core_dir = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, core_dir)
import post_tool_logger_core as core

try:
    raw = json.loads(os.environ.get("SAGE_HOOK_INPUT", "{}"))
except Exception:
    sys.exit(0)

prof_path = os.environ.get("SAGE_PROFILE", "")
if not prof_path or not os.path.exists(prof_path):
    sys.exit(0)  # profile 외부주입 필수 — 없으면 noop
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

def branch():
    if os.environ.get("SAGE_GATE_BRANCH"):
        return os.environ["SAGE_GATE_BRANCH"]
    try:
        return subprocess.check_output(
            ["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        return "unknown"

fp = (raw.get("tool_input") or {}).get("file_path") or ""
changes = [{"path": rel(fp), "op": "write"}] if fp else []

event = {
    "hook_id": "post-tool-logger",
    "hook_event_name": "PostToolUse",
    "runtime": "claude",
    "session_id": raw.get("session_id", "") or "",
    "tool": raw.get("tool_name", "") or "",
    "branch": branch(),
    "now_utc": os.environ.get("SAGE_NOW_UTC") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "changes": changes,
}
decision = core.decide(event, profile)
if decision["action"] == "log":
    out = os.path.join(log_dir, decision["log_file"])
    with open(out, "a", encoding="utf-8") as fh:
        for e in decision["log_entries"]:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
sys.exit(decision["exit_code"])
PYEOF
exit 0
