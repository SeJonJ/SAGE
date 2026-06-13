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
echo "### 5. pre-implementation-gate reverse_extract 폐루프 (부분추출 + unresolved 전략슬롯)"
python3 "$HERE/test_pre_implementation_gate.py" || rc=1

echo ""
echo "### 6. stop-compliance-report reverse_extract 폐루프 (부분추출 + policy_delta 보존)"
python3 "$HERE/test_stop_compliance_report.py" || rc=1

echo ""
echo "### 7. reverse_extract_agent (agent typed claim 자동도출)"
python3 "$HERE/test_reverse_extract_agent.py" || rc=1

echo ""
echo "### 8. conformance_lint (agent/skill 렌더 부합 결정론 검사)"
python3 "$HERE/test_conformance.py" || rc=1

echo ""
echo "### 9. auto_approve_decision (승인 UX — auto_approve_safe_default)"
python3 "$HERE/test_review.py" || rc=1

echo ""
echo "### 10. sage change 라우터 (자연어 의도 → generate/absorb)"
python3 "$HERE/test_change_router.py" || rc=1

echo ""
if [[ "$rc" == "0" ]]; then echo "✅ ALL HOOK TESTS PASS"; else echo "❌ FAILURES"; fi
exit "$rc"
