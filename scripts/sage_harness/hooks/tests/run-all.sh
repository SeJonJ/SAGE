#!/usr/bin/env bash
# SAGE hook 전체 회귀 테스트 — write guard(bash) + reverse_extract hook(python).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rc=0

echo "### 1. generated-artifact write guard"
bash "$HERE/run-tests.sh" || rc=1

echo ""
echo "### 2. capture-declared-risk reverse_extract 폐루프"
python3 "$HERE/test_capture_declared_risk.py" || rc=1

echo ""
echo "### 3. post-tool-logger reverse_extract 폐루프 (structural + profile_bound)"
python3 "$HERE/test_post_tool_logger.py" || rc=1

echo ""
echo "### 4. pre-phase4-checklist-gate reverse_extract 폐루프 (IO-bound gate, 2단계 pure core)"
python3 "$HERE/test_pre_phase4_checklist_gate.py" || rc=1

echo ""
if [[ "$rc" == "0" ]]; then echo "✅ ALL HOOK TESTS PASS"; else echo "❌ FAILURES"; fi
exit "$rc"
