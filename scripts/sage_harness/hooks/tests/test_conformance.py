#!/usr/bin/env python3
"""conformance_lint 검증 (step7 — agent/skill 렌더 부합 결정론 검사).

Codex DoD 4케이스: (a)PASS (b)owned_path 누락→FAIL (c)금지-반대 문구→FAIL (d)forbidden subject 부재→WARN.
+ unresolved=WARN / 서술형 skip / forbidden contradiction.
self-contained: 합성 입력 + 예시 인스턴스 contradiction 패턴(특정 소비 프로젝트 비의존 = 독립).
"""
import os
import sys
import unittest

SAGE_SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/sage_harness
sys.path.insert(0, SAGE_SCRIPTS)
import conformance as cf  # noqa: E402
from extract_config_example import EXAMPLE_CONTRADICTION_PATTERNS as CPAT  # noqa: E402

CLAIMS = {
    "required_claims": [
        {"type": "owned_paths", "value": "backend/src/main/java/core", "confidence": "high"},
        {"type": "convention_doc", "value": "docs/backend.md", "confidence": "high"},
        {"type": "tool_or_skill_ref", "value": "skill:backend-test-layer", "confidence": "high"},
        {"type": "role_boundary", "value": "boundary:integration/scenario → qa", "confidence": "high"},  # 서술형 skip
    ],
    "forbidden_claims": [
        {"type": "safety_forbid", "value": "forbid:commit/push", "confidence": "high"},
        {"type": "safety_forbid", "value": "forbid:integration tests", "confidence": "high"},
        {"inherited_forbidden_claims": "AGENT_GUIDE.non_negotiable_boundaries"},
    ],
    "runtime_delta_allowlist": [],
    "unresolved": [],
}

# (a) PASS: 구조 식별자 전부 + forbidden subject 언급 + 반대문구 없음
RENDERED_PASS = """owns backend/src/main/java/core.
docs/backend.md 준수. backend-test-layer 스킬 참고.
commit/push 금지. 통합(integration) 테스트는 QA 영역."""

# (b) FAIL: owned_path 누락
RENDERED_MISS_PATH = """docs/backend.md 준수. backend-test-layer 참고.
commit/push 금지. integration 테스트는 QA."""

# (c) FAIL: 금지-반대 허용문구
RENDERED_CONTRADICT = """owns backend/src/main/java/core.
docs/backend.md. backend-test-layer.
이 에이전트는 통합 테스트를 작성한다. commit/push. integration."""

# (d) WARN: forbidden subject(integration) 부재 → forbidden_policy_missing
RENDERED_WARN = """owns backend/src/main/java/core.
docs/backend.md. backend-test-layer. commit/push 금지."""


class TestConformance(unittest.TestCase):
    def test_a_pass(self):
        r = cf.conformance_lint(RENDERED_PASS, CLAIMS, CPAT)
        self.assertEqual(r["status"], "PASS", r)
        self.assertEqual(r["missing_required"], [])

    def test_b_missing_path_fail(self):
        r = cf.conformance_lint(RENDERED_MISS_PATH, CLAIMS, CPAT)
        self.assertEqual(r["status"], "FAIL")
        self.assertTrue(any(m["type"] == "owned_paths" for m in r["missing_required"]))

    def test_c_contradiction_fail(self):
        r = cf.conformance_lint(RENDERED_CONTRADICT, CLAIMS, CPAT)
        self.assertEqual(r["status"], "FAIL")
        self.assertTrue(r["forbidden_policy_contradictions"])

    def test_d_forbidden_missing_warn(self):
        r = cf.conformance_lint(RENDERED_WARN, CLAIMS, CPAT)
        self.assertEqual(r["status"], "WARN")
        self.assertTrue(any("integration" in f["value"] for f in r["forbidden_policy_missing"]))

    def test_descriptive_skipped(self):
        # role_boundary(서술형)은 토큰 미검출이어도 FAIL/WARN 유발 안 함
        r = cf.conformance_lint(RENDERED_PASS, CLAIMS, CPAT)
        self.assertEqual(r["status"], "PASS")

    def test_priority_fail_over_warn(self):
        r = cf.conformance_lint(RENDERED_MISS_PATH, CLAIMS, CPAT)
        self.assertEqual(r["status"], "FAIL")  # FAIL > WARN

    def test_boundary_aware_presence(self):
        # audit P1-6: substring 오탐 차단 — 'backend-test-layer-extra' 는 'backend-test-layer' presence 아님
        rendered = ("owns backend/src/main/java/core. docs/backend.md. "
                    "backend-test-layer-extra 라는 다른 토큰만 있음. commit/push 금지. integration.")
        r = cf.conformance_lint(rendered, CLAIMS, CPAT)
        self.assertEqual(r["status"], "FAIL")  # skill:backend-test-layer 미검출 → FAIL
        self.assertTrue(any("backend-test-layer" in m["value"] for m in r["missing_required"]))

    def test_synthetic_output_contract_matches_report_heading(self):
        claims = {"required_claims": [{"type": "output_contract",
                                        "value": "output:report_format", "confidence": "high"}],
                  "forbidden_claims": [], "runtime_delta_allowlist": [], "unresolved": []}
        for heading in ("## 리포트 형식", "## 10. 리포트 형식 (체커 모드)", "### 응답 형식 (필수)"):
            result = cf.conformance_lint(heading + "\n", claims)
            self.assertEqual(result["status"], "PASS", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
