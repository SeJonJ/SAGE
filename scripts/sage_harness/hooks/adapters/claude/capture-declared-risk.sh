#!/bin/bash
# capture-declared-risk — Claude adapter (rendered)
# SSOT: scripts/sage_harness/hooks/capture_declared_risk_core.py
# adapter 책임: 입력추출(Claude stdin JSON) / 경로·env 바인딩 / 파일IO / 출력렌더(plain text + exit).
# 알고리즘(레벨탐지/cleanup선언/state)은 core 가 소유. (generated artifact — 직접수정 금지)

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
LOG_DIR="$PROJECT_ROOT/.claude/logs"
CORE_DIR="${SAGE_HOOK_CORE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
mkdir -p "$LOG_DIR"

INPUT=$(cat)

SAGE_HOOK_INPUT="$INPUT" python3 - "$LOG_DIR" "$CORE_DIR" <<'PYEOF'
import sys, os, json, glob, time
log_dir, core_dir = sys.argv[1], sys.argv[2]
sys.path.insert(0, core_dir)
import capture_declared_risk_core as core

try:
    raw = json.loads(os.environ.get("SAGE_HOOK_INPUT", "{}"))
except Exception:
    sys.exit(0)

event = {
    "hook_id": "capture-declared-risk",
    "hook_event_name": "UserPromptSubmit",
    "runtime": "claude",
    "session_id": raw.get("session_id", "") or "",
    "prompt": raw.get("prompt", "") or "",
    "now_utc": os.environ.get("SAGE_NOW_UTC") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
decision = core.decide(event)

# cleanup (adapter IO — core 가 선언한 정책대로)
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
        # Claude 출력 프로토콜: plain text (stdout = additionalContext)
        print(f"ℹ️  [Risk 선언 포착] 이번 세션 작업 레벨: {decision['level']} — 소스 수정 시 해당 레벨 게이트가 적용됩니다.")
    except Exception:
        pass

sys.exit(decision["exit_code"])
PYEOF
exit 0
