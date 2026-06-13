#!/bin/bash
# post-tool-logger — Codex adapter (rendered)
# SSOT: scripts/sage_harness/hooks/post_tool_logger_core.py
# adapter 책임: 입력추출(Codex apply_patch 본문 다중파일 파싱) / 경로·env 바인딩 / branch·now_utc /
#              profile 로드 / 파일IO. 분류 알고리즘은 core. (generated artifact — 직접수정 금지)
# profile 외부주입 필수: $SAGE_PROFILE 없으면 noop(graceful).

PROJECT_ROOT="${CODEX_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
LOG_DIR="$PROJECT_ROOT/.codex/logs"
CORE_DIR="${SAGE_HOOK_CORE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
mkdir -p "$LOG_DIR"

INPUT=$(cat)

SAGE_HOOK_INPUT="$INPUT" python3 - "$PROJECT_ROOT" "$LOG_DIR" "$CORE_DIR" <<'PYEOF'
import sys, os, re, json, subprocess, time
root, log_dir, core_dir = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, core_dir)
import post_tool_logger_core as core

try:
    raw = json.loads(os.environ.get("SAGE_HOOK_INPUT", "{}"))
except Exception:
    sys.exit(0)

if (raw.get("tool_name") or "") != "apply_patch":
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

event = {
    "hook_id": "post-tool-logger",
    "hook_event_name": "PostToolUse",
    "runtime": "codex",
    "session_id": raw.get("session_id", "") or "",
    "tool": "apply_patch",
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
