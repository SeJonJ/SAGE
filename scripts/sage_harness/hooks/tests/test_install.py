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
        with tempfile.TemporaryDirectory() as d:
            rc = install.run(Args("claude", d))
            self.assertEqual(rc, 0)
            for rel in ("sage/project-profile.yaml", "docs/sage_harness/.manifest.json",
                        "docs/sage_harness/hooks/.gitkeep", "docs/sage_harness/agents/.gitkeep",
                        "schema/manifest.schema.json", "sage/templates/agent.spec.md"):
                self.assertTrue(os.path.exists(os.path.join(d, rel)), rel)

    def test_host_prefix_substitution(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("codex", d, prefix="myapp"))
            prof = open(os.path.join(d, "sage", "project-profile.yaml"), encoding="utf-8").read()
            self.assertIn("host: codex", prof)
            self.assertIn('prefix: "myapp"', prof)
            manifest = open(os.path.join(d, "docs", "sage_harness", ".manifest.json"), encoding="utf-8").read()
            self.assertIn('"host_runtime": "codex"', manifest)
            self.assertIn('"assets": {}', manifest)

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
