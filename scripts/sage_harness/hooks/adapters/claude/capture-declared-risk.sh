#!/bin/bash
# capture-declared-risk — Claude thin adapter (R1: 본문은 runtime/run_hook.py 단일소스)
# SSOT: scripts/sage_harness/hooks/capture_declared_risk_core.py (decide)
#       scripts/sage_harness/hooks/runtime/{hook_runtime,io_claude}.py (IO 오케스트레이션)
# log_dir 는 run_hook 이 root/.claude/logs 로 해석. (generated artifact — 직접수정 금지)
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
CORE_DIR="${SAGE_HOOK_CORE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
exec python3 "$CORE_DIR/runtime/run_hook.py" \
  --runtime claude --hook capture-declared-risk --root "$PROJECT_ROOT" --core-dir "$CORE_DIR"
