#!/usr/bin/env python3
"""manifest_util 검증 (하 등급 — manifest 공용 헬퍼).

self-contained: 임시 SAGE 루트 구성 후 upsert_agent/refresh_hashes 동작 확인.
"""
import json
import os
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

SAGE_SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, SAGE_SCRIPTS)
import manifest_util as mu  # noqa: E402


def make_root(d):
    os.makedirs(os.path.join(d, "docs", "sage_harness", "agents"), exist_ok=True)
    with open(os.path.join(d, mu.MANIFEST_REL), "w", encoding="utf-8") as f:
        json.dump({"sage_version": "0.1.0", "host_runtime": "claude", "assets": {}}, f)
    # agent spec + claims
    ad = os.path.join(d, "docs", "sage_harness", "agents")
    Path(os.path.join(ad, "demo.md")).write_text("# demo spec")
    Path(os.path.join(ad, "demo.claims.yml")).write_text("required_claims: []\n")


class TestManifestUtil(unittest.TestCase):
    def test_find_root_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d)
            sub = os.path.join(d, "docs", "sage_harness", "agents")
            root = mu.find_root(sub)
            self.assertIsNotNone(root)
            self.assertTrue(os.path.exists(os.path.join(root, mu.MANIFEST_REL)))
            self.assertIn("assets", mu.load(d))

    def test_upsert_agent(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d)
            # render 산출물(있으면 해시)
            r = os.path.join(d, "render_claude.md"); Path(r).write_text("rendered")
            entry = mu.upsert_agent(d, "demo", claude_render=r, codex_render="",
                                    test="scripts/sage_harness/hooks/tests/test_x.py", unresolved=["u1"])
            self.assertEqual(entry["form"], "interpretive")
            self.assertTrue(entry["spec_hash"].startswith("sha256:"))
            self.assertTrue(entry["claims_hash"].startswith("sha256:"))
            self.assertIn("claude", entry["render_hash"])
            self.assertEqual(entry["unresolved"], ["u1"])
            # 저장 확인
            m = mu.load(d)
            self.assertIn("agents/demo", m["assets"])

    def test_upsert_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d)
            e1 = mu.upsert_agent(d, "demo", claude_render="", codex_render="", test="t.py", unresolved=[])
            e2 = mu.upsert_agent(d, "demo", claude_render="", codex_render="", test="t.py", unresolved=[])
            self.assertEqual(e1, e2)

    def test_agent_and_skill_upsert_preserve_manifest_when_atomic_replace_fails(self):
        for kind in ("agent", "skill"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                make_root(d)
                if kind == "skill":
                    skill_dir = Path(d, "docs", "sage_harness", "skills")
                    skill_dir.mkdir(parents=True)
                    Path(skill_dir, "demo.md").write_text("# demo spec")
                    Path(skill_dir, "demo.claims.yml").write_text("required_claims: []\n")
                manifest_path = Path(d, mu.MANIFEST_REL)
                before = manifest_path.read_bytes()
                upsert = mu.upsert_agent if kind == "agent" else mu.upsert_skill

                with mock.patch.object(mu, "atomic_write_json", side_effect=OSError("injected")):
                    with self.assertRaises(OSError):
                        upsert(d, "demo", claude_render="", codex_render="", test="t.py", unresolved=[])

                self.assertEqual(before, manifest_path.read_bytes())

    def test_refresh_hashes_nested(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d)
            mu.upsert_agent(d, "demo", claude_render="", codex_render="", test="t.py", unresolved=[])
            spec = os.path.join(d, "docs", "sage_harness", "agents", "demo.md")
            entry = mu.refresh_hashes(d, "agents/demo", {"spec_hash": spec, "render_hash.claude": spec})
            self.assertEqual(entry["spec_hash"], mu.sha256_of(spec))
            self.assertEqual(entry["render_hash"]["claude"], mu.sha256_of(spec))


if __name__ == "__main__":
    unittest.main(verbosity=2)
