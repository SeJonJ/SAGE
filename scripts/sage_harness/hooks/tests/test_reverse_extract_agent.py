#!/usr/bin/env python3
"""reverse_extract_agent 검증 (step6 — agent typed claim 자동도출, 결정론).

검증(Codex DoD):
  - 7 claim 타입 각 1+ 추출
  - persona("30년 경력/시니어") drop (claims 에 안 들어감)
  - gstack(codex-only) = runtime_allowed
  - 양쪽 공통 = high (교집합)
  - 한쪽만 + 무근거 = unresolved
  - spec draft 에 intent/advisory_scope 골격 생성
self-contained: 합성 입력(외부 ChatForYou 비의존).
"""
import os
import sys
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/sage_harness/hooks
SAGE_SCRIPTS = os.path.dirname(HOOKS)                                 # scripts/sage_harness
sys.path.insert(0, SAGE_SCRIPTS)
import reverse_extract_agent as rx  # noqa: E402

GUIDE = "Do not run git commit or git push. Do not edit chatforyou-desktop/src directly."

CLAUDE = """---
name: "chatforyou-backend-expert"
description: "백엔드 전문가. Service 레이어 단위 테스트 작성. 통합 테스트는 QA 영역이다."
---
# 백엔드 전문가 (30년 경력)
당신은 30년 경력 시니어 엔지니어다.
**역할 경계**: 통합/HTTP/경계값/시나리오 테스트 금지 → QA 전문가 영역
소유: springboot-backend/src/main/java/webChat
`backend-convention-checker` agent (`.claude/agents/backend-convention-checker.md`)
`backend-test-layer` skill (`.claude/skills/backend-test-layer.md`)
docs/springboot_backend.md 준수
Service 단위 테스트 (@ExtendWith(MockitoExtension))
commit / push 금지
1. 구현 가이드 작성
nodejs-frontend 수정 금지
ONLY_IN_CLAUDE: springboot-backend/src/main/java/onlyclaude
"""

CODEX = """---
name: "chatforyou-backend-expert"
description: "백엔드 전문가. Service 레이어 단위 테스트 작성. 통합 테스트는 QA 영역이다."
---
역할 경계: 통합/HTTP/경계값/시나리오 테스트 금지 → QA 전문가 영역
소유: springboot-backend/src/main/java/webChat
`backend-convention-checker` agent (`.codex/agents/backend-convention-checker.md`)
`backend-test-layer` skill (`.codex/skills/backend-test-layer/SKILL.md`)
docs/springboot_backend.md 준수
Service 단위 테스트
commit / push 금지
1. 구현 가이드 작성
nodejs-frontend 수정 금지
gstack 사용 규칙: 보안 작업은 gstack skill 우선.
"""


class TestExtract(unittest.TestCase):
    def setUp(self):
        self.claims = rx.extract_claims(CLAUDE, CODEX, GUIDE)
        self.req = self.claims["required_claims"]
        self.types = {c["type"] for c in self.req if "type" in c}

    def test_seven_types_present(self):
        for t in ("owned_paths", "role_boundary", "test_scope", "tool_or_skill_ref",
                  "convention_doc", "workflow_step"):
            self.assertIn(t, self.types, t)
        # safety_forbid 는 forbidden_claims 에
        self.assertTrue(any(c.get("type") == "safety_forbid" for c in self.claims["forbidden_claims"]))

    def test_persona_dropped(self):
        for c in self.req:
            self.assertNotIn("경력", c.get("value", ""))
            self.assertNotIn("시니어", c.get("value", ""))

    def test_gstack_runtime_allowed(self):
        vals = [c["value"] for c in self.claims["runtime_delta_allowlist"]]
        self.assertTrue(any("gstack" in v for v in vals), "gstack=runtime_allowed")

    def test_intersection_high(self):
        # 양쪽 공통 owned_path 는 high
        wc = [c for c in self.req if c["value"] == "springboot-backend/src/main/java/webChat"]
        self.assertTrue(wc and wc[0]["confidence"] == "high")

    def test_one_sided_unresolved(self):
        # claude 에만 있는 경로 → unresolved
        oc = [c for c in self.req if c["value"].endswith("onlyclaude")]
        self.assertTrue(oc and oc[0]["confidence"] == "unresolved")
        self.assertIn("springboot-backend/src/main/java/onlyclaude", self.claims["unresolved"])

    def test_inherited_forbidden_ref(self):
        self.assertTrue(any("inherited_forbidden_claims" in c for c in self.claims["forbidden_claims"]))

    def test_safety_forbid_values(self):
        fvals = [c.get("value", "") for c in self.claims["forbidden_claims"]]
        self.assertTrue(any("commit/push" in v for v in fvals))
        self.assertTrue(any("integration" in v for v in fvals))


class TestSpecDraft(unittest.TestCase):
    def test_draft_skeleton(self):
        claims = rx.extract_claims(CLAUDE, CODEX, GUIDE)
        draft = rx.spec_draft("chatforyou-backend-expert", CLAUDE, CODEX, claims)
        self.assertIn("## intent", draft)
        self.assertIn("## advisory_scope", draft)
        self.assertIn("AUTO-DRAFT", draft)
        self.assertNotIn("30년 경력", draft)  # persona 제거


if __name__ == "__main__":
    unittest.main(verbosity=2)
