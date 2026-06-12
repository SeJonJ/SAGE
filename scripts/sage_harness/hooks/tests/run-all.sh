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
if [[ "$rc" == "0" ]]; then echo "✅ ALL HOOK TESTS PASS"; else echo "❌ FAILURES"; fi
exit "$rc"
