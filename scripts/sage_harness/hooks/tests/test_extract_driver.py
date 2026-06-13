#!/usr/bin/env python3
"""extract_agent 드라이버 검증 (자가점검 R5 — 재현 가능 진입점).

self-contained: 합성 입력 + config 로 결정론·구조 검증 (ChatForYou 파일 비의존 = 독립).
"""
import os
import sys
import tempfile
import unittest

SAGE_SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/sage_harness
sys.path.insert(0, SAGE_SCRIPTS)
import extract_agent as drv  # noqa: E402

CLAUDE = '---\nname: "x"\ndescription: "데모 전문가. 통합 테스트는 QA 영역이다."\n---\n소유: myapp/src/core\ndocs/myapp_conv.md 준수\ncommit / push 금지\n'
CODEX = CLAUDE
GUIDE = "Do not run git commit or git push."

# 가상 프로젝트 config (ChatForYou 아님 — 독립 입증)
DEMO_CONFIG = {
    "component_path_globs": [r"myapp/[\w./-]+"],
    "guide_boundary_tokens": ["commit", "push"],
    "signal_rules": [],
}


class TestDriver(unittest.TestCase):
    def _write_inputs(self, d):
        cp = os.path.join(d, "c.md"); xp = os.path.join(d, "x.md"); gp = os.path.join(d, "g.md")
        open(cp, "w", encoding="utf-8").write(CLAUDE)
        open(xp, "w", encoding="utf-8").write(CODEX)
        open(gp, "w", encoding="utf-8").write(GUIDE)
        return cp, xp, gp

    def test_extract_demo_config(self):
        with tempfile.TemporaryDirectory() as d:
            cp, xp, gp = self._write_inputs(d)
            spec, claims_yaml, claims = drv.extract("demo", cp, xp, gp, DEMO_CONFIG)
            owned = [c["value"] for c in claims["required_claims"] if c["type"] == "owned_paths"]
            self.assertIn("myapp/src/core", owned)  # 가상 프로젝트 경로 추출(독립)
            self.assertIn("## intent", spec)
            self.assertIn("required_claims:", claims_yaml)

    def test_default_config_domain_free(self):
        # config 없으면 owned_paths 미추출 (엔진 도메인값 0)
        with tempfile.TemporaryDirectory() as d:
            cp, xp, gp = self._write_inputs(d)
            _, _, claims = drv.extract("demo", cp, xp, gp, None)
            owned = [c for c in claims["required_claims"] if c["type"] == "owned_paths"]
            self.assertEqual(owned, [])

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            cp, xp, gp = self._write_inputs(d)
            a = drv.extract("demo", cp, xp, gp, DEMO_CONFIG)[1]
            b = drv.extract("demo", cp, xp, gp, DEMO_CONFIG)[1]
            self.assertEqual(a, b)

    def test_write_mode(self):
        with tempfile.TemporaryDirectory() as d:
            cp, xp, gp = self._write_inputs(d)
            out = os.path.join(d, "out")
            rc = drv.main(["--id", "demo", "--claude", cp, "--codex", xp, "--guide", gp, "--out-dir", out, "--write"])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(out, "demo.md")))
            self.assertTrue(os.path.exists(os.path.join(out, "demo.claims.yml")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
