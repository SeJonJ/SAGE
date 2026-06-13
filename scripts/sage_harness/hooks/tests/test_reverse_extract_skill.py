#!/usr/bin/env python3
"""reverse_extract_skill 검증 (상 등급 — skill typed claim 자동도출, Codex 2R 합의).

self-contained: 합성 skill 입력 + config. ChatForYou 비의존(독립).
"""
import os
import sys
import unittest

SAGE_SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, SAGE_SCRIPTS)
import reverse_extract_skill as rs  # noqa: E402

GUIDE = "Do not run git commit or git push."
CFG = {
    "intent_headers": ["목적", "purpose"],
    "procedure_headers": ["실행 방법", "procedure"],
    "output_headers": ["리포트 형식", "output"],
    "scope_headers": ["주의사항", "boundaries"],
    "input_scope_patterns": [r"git diff"],
    "guide_boundary_tokens": ["commit", "push"],
    "runtime_policy_tokens": {"codex": ["gstack"]},
}

CLAUDE = """---
name: demo-skill
description: >
  데모 스킬. "데모 수행", "demo check" 표현에 사용.
---
# 데모
## 목적
변경 파일 검증.
## 실행 방법
`backend-convention-checker` agent 로 아래 수행:
1. **변경 파일 감지**: git diff 로 추출
2. **검증 수행**: docs/demo_conv.md 기준
3. **결과 리포트**: 위반 출력
## 주의사항
- 변경 파일 없으면 종료
- commit / push 금지
"""
CODEX = CLAUDE.replace(".claude", ".codex") + "\ngstack 사용 규칙: 보안은 gstack 우선.\n"


class TestSkillExtract(unittest.TestCase):
    def setUp(self):
        self.c = rs.extract_claims(CLAUDE, CODEX, GUIDE, CFG)
        self.req = self.c["required_claims"]
        self.types = {x["type"] for x in self.req if "type" in x}

    def test_when_to_use(self):
        whens = {x["value"] for x in self.req if x["type"] == "when_to_use"}
        self.assertIn("데모 수행", whens)

    def test_procedure_ordered(self):
        steps = [(x.get("order"), x["value"]) for x in self.req if x["type"] == "procedure_step"]
        self.assertTrue(steps)
        # 순서 보존: order 가 증가
        ordered = [v for o, v in sorted(steps, key=lambda z: (z[0] or 999))]
        self.assertEqual(ordered[0], "변경 파일 감지")
        self.assertNotIn("**", ordered[0])  # 마크다운 제거

    def test_uses_and_input_scope(self):
        uses = {x["value"] for x in self.req if x["type"] == "uses"}
        self.assertTrue(any("backend-convention-checker" in u for u in uses))
        self.assertIn("docs/demo_conv.md", uses)
        inp = {x["value"] for x in self.req if x["type"] == "input_scope"}
        self.assertTrue(any("git diff" in i for i in inp))
        self.assertNotIn(r"git diff", inp)  # raw regex 노출 아님(라벨화)

    def test_gstack_runtime_allowed(self):
        vals = [x["value"] for x in self.c["runtime_delta_allowlist"]]
        self.assertTrue(any("gstack" in v for v in vals))

    def test_independence_no_config(self):
        # config 없으면 input_scope/owned 류 ChatForYou 가정 미추출 (엔진 도메인값 0)
        c = rs.extract_claims(CLAUDE, CODEX, GUIDE)  # DEFAULT
        inp = [x for x in c["required_claims"] if x["type"] == "input_scope"]
        self.assertEqual(inp, [], "DEFAULT 는 input_scope_patterns 비어 미추출")

    def test_claims_yaml_kind_skill(self):
        y = rs.claims_to_yaml(self.c)
        self.assertIn("kind: skill", y)
        self.assertIn("required_claims:", y)

    def test_deterministic(self):
        a = rs.claims_to_yaml(rs.extract_claims(CLAUDE, CODEX, GUIDE, CFG))
        b = rs.claims_to_yaml(rs.extract_claims(CLAUDE, CODEX, GUIDE, CFG))
        self.assertEqual(a, b)

    def test_cross_model_invocation_allowlist(self):
        # 사람 결정: cross-model 호출 토큰(한쪽-only)은 unresolved 아니라 allowlist (§3.2.1)
        cfg = dict(CFG); cfg["cross_model_invocation"] = {"claude": ["gstack:codex"], "codex": ["$claude consult"]}
        cl = CLAUDE + "\n외부 검증: `gstack:codex` 로 cross-model review.\n"
        cx = CODEX + "\n외부 검증: $claude consult 로 cross-model review.\n"
        c = rs.extract_claims(cl, cx, GUIDE, cfg)
        self.assertNotIn("gstack:codex", [x["value"] for x in c["required_claims"]])  # required 아님
        self.assertIn("runtime_policy.cross_model_review", [x["value"] for x in c["runtime_delta_allowlist"]])
        self.assertNotIn("gstack:codex", c["unresolved"])  # unresolved 아님


if __name__ == "__main__":
    unittest.main(verbosity=2)
