#!/usr/bin/env python3
"""sage install 검증 (중 등급 — 부트스트랩).

self-contained: 임시 dest 에 install 후 산출물/치환/멱등 확인.
"""
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import install  # noqa: E402


class Args:
    def __init__(self, host, dest, prefix="sage", force=False):
        self.host = host; self.dest = dest; self.prefix = prefix; self.force = force


class TestInstall(unittest.TestCase):
    def test_creates_layout(self):
        """CORE 하네스 전부 배치 — framework + hook spec/정본 + roster agent + manifest 등록."""
        with tempfile.TemporaryDirectory() as d:
            rc = install.run(Args("claude", d))
            self.assertEqual(rc, 0)
            for rel in (
                # profile + 템플릿 + schema
                "sage/project-profile.yaml", "schema/manifest.schema.json", "sage/templates/agent.spec.md",
                # framework(중립)
                "AGENT_GUIDE.md", "CLAUDE.md", "verification-protocol.md", "scripts/verify-changes.sh",
                "docs/agent/risk-classification.md", "docs/agent/review-protocol.md", "docs/agent/output-contract.md",
                # CORE hook spec + 정본(core/adapter/strategy)
                "docs/sage_harness/.manifest.json",
                "docs/sage_harness/hooks/pre-implementation-gate.md",
                "scripts/sage_harness/hooks/pre_implementation_gate_core.py",
                "scripts/sage_harness/hooks/adapters/claude/pre-implementation-gate.sh",
                "scripts/sage_harness/hooks/adapters/codex/pre-implementation-gate.sh",
                "scripts/sage_harness/hooks/generated-artifact-write-guard.sh",
                "scripts/sage_harness/hooks/strategies/pre_implementation_gate/codex_feature_signal.py",
                # CORE roster agent(중립)
                "docs/sage_harness/agents/leader.md", "docs/sage_harness/agents/backend.md",
                "docs/sage_harness/agents/reviewer.md", "docs/sage_harness/agents/convention-checker.md",
            ):
                self.assertTrue(os.path.exists(os.path.join(d, rel)), rel)
            # tests/ 는 배치하지 않음(런타임 불필요)
            self.assertFalse(os.path.exists(os.path.join(d, "scripts/sage_harness/hooks/tests")))

    def test_host_prefix_substitution(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("codex", d, prefix="myapp"))
            prof = open(os.path.join(d, "sage", "project-profile.yaml"), encoding="utf-8").read()
            self.assertIn("host: codex", prof)
            self.assertIn('prefix: "myapp"', prof)
            # codex host → CODEX.md wrapper (CLAUDE.md 아님)
            self.assertTrue(os.path.exists(os.path.join(d, "CODEX.md")))
            self.assertFalse(os.path.exists(os.path.join(d, "CLAUDE.md")))
            import json
            m = json.load(open(os.path.join(d, "docs", "sage_harness", ".manifest.json"), encoding="utf-8"))
            self.assertEqual(m["host_runtime"], "codex")
            # manifest 는 CORE hook 6종 등록(빈 assets 아님) → generate 가 동작 가능
            self.assertEqual(len([k for k in m["assets"] if k.startswith("hooks/")]), 6)
            self.assertEqual(m["assets"]["hooks/pre-implementation-gate"]["form"], "core_adapter")
            self.assertEqual(m["assets"]["hooks/generated-artifact-write-guard"]["form"], "native")

    def test_independence_no_domain_tokens(self):
        """제약 #2: 설치된 CORE 트리에 ChatForYou 도메인 토큰 0 (정본/spec/agent 중립)."""
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            # 설치 트리 전체에서 도메인 토큰 검색(테스트/캐시 제외 — 애초에 배치 안 함)
            hits = subprocess.run(
                ["grep", "-rniE", r"chatforyou|springboot|webchat|nodejs|kurento|dev-team|webrtc|electron", d],
                capture_output=True, text=True).stdout.strip()
            self.assertEqual(hits, "", f"도메인 토큰 누출:\n{hits}")

    def test_unstamped_validate_stale(self):
        """Codex P2-6: install 직후(generate 전) hook 은 미스탬프 → validate STALE(exit 3), healthy 로 안 보임."""
        from sage.commands import validate

        class VArgs:
            kind = "hook"; check = True; id = None

            def __init__(self, root):
                self.root = root
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            rc = validate.run(VArgs(d))
            self.assertEqual(rc, 3)  # STALE — generate --write 로 스탬프 필요

    def test_idempotent_skip(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            # 재실행: profile 내용 안 바뀜(skip)
            before = open(os.path.join(d, "sage", "project-profile.yaml"), encoding="utf-8").read()
            install.run(Args("codex", d))  # host 바꿔도 skip 이라 안 덮어씀
            after = open(os.path.join(d, "sage", "project-profile.yaml"), encoding="utf-8").read()
            self.assertEqual(before, after)

    def test_force_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            install.run(Args("codex", d, force=True))
            prof = open(os.path.join(d, "sage", "project-profile.yaml"), encoding="utf-8").read()
            self.assertIn("host: codex", prof)  # force 로 덮어써짐


if __name__ == "__main__":
    unittest.main(verbosity=2)
