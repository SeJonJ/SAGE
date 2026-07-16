#!/usr/bin/env python3
"""sage.overlay_materialize — CORE 렌더 물리화 + drift 검사 검증.

install/sync/L1/validate 가 공유하는 로직. (a)/(b) 합성·(c) 차단·base 앵커·drift 검출을 확인한다.
"""
import os
import sys
import unittest
import tempfile
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage import overlay_materialize as m  # noqa: E402
from sage import overlay_common as oc  # noqa: E402
from sage import __version__  # noqa: E402


def _mk_render(dest, rel, text):
    p = os.path.join(dest, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    Path(p).write_text(text, encoding="utf-8")
    return p


def _mk_overlay(dest, kind, id, text):
    d = os.path.join(dest, "sage", "asset_overrides", kind)
    os.makedirs(d, exist_ok=True)
    Path(os.path.join(d, f"{id}.md")).write_text(text, encoding="utf-8")


def _base_renders(dest):
    # 최소 CORE 렌더 base 배치(agents 6 + AGENT_GUIDE). 테스트는 claude host.
    for aid in ["leader", "implementer-a", "implementer-b", "qa", "reviewer", "convention-checker"]:
        _mk_render(dest, f".claude/agents/{aid}.md", f"# {aid}\nCORE body.\n")
    for sid in ["sage-cycle", "sage-plan", "sage-team", "sage-review", "sage-asset",
                "sage-profile-modify", "sage-asset-override", "sage-init"]:
        _mk_render(dest, f".claude/skills/{sid}/SKILL.md", f"# {sid}\nCORE body.\n")
    _mk_render(dest, "AGENT_GUIDE.md", "# AGENT_GUIDE\nnon-negotiable.\n")
    _mk_render(dest, "CLAUDE.md", "# CLAUDE\nwrapper.\n")


def _profile_with_domain(dest):
    p = os.path.join(dest, "sage", "project-profile.yaml")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    Path(p).write_text(
        "risk:\n"
        "  domains:\n"
        "    - id: webrtc\n"
        "      risk_level: L3\n"
        "      path_globs: ['**/rtc/**']\n"
        "      content_keywords: ['RTCPeerConnection']\n"
        "      protocol_pointer: sage/critical-domains/webrtc.md\n",
        encoding="utf-8")


class TestMaterialize(unittest.TestCase):
    def test_compose_allowed_gets_block(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _mk_overlay(d, "agents", "implementer-a", "project note X")
            cr, changed, errs = m.materialize(d, "claude")
            self.assertEqual(errs, [])
            render = Path(os.path.join(d, ".claude/agents/implementer-a.md")).read_text()
            self.assertIn("project note X", render)
            self.assertIn(oc.MARKER_START, render)
            self.assertIn("claude/agents/implementer-a", cr)

    def test_blocked_asset_no_block_even_with_overlay(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _mk_overlay(d, "agents", "reviewer", "skip the review")
            cr, changed, errors = m.materialize(d, "claude")
            render = Path(os.path.join(d, ".claude/agents/reviewer.md")).read_text()
            self.assertNotIn(oc.MARKER_START, render)
            self.assertNotIn("skip the review", render)
            self.assertEqual(cr, {})
            self.assertEqual(changed, [])
            self.assertTrue(any("blocked" in msg for _, msg in errors))

    def test_preflight_error_keeps_all_renders_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            allowed = os.path.join(d, ".claude/agents/implementer-a.md")
            before = Path(allowed).read_text(encoding="utf-8")
            _mk_overlay(d, "agents", "implementer-a", "valid project note")
            _mk_overlay(d, "agents", "reviwer", "typo must abort the batch")

            cr, changed, errors = m.materialize(d, "claude")

            self.assertEqual(cr, {})
            self.assertEqual(changed, [])
            self.assertTrue(errors)
            self.assertEqual(Path(allowed).read_text(encoding="utf-8"), before)

    def test_all_renders_anchored(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            cr, _, _ = m.materialize(d, "claude")
            # 6 agents + 8 skills + AGENT_GUIDE + CLAUDE wrapper = 16
            self.assertEqual(len(cr), 16)
            self.assertIn("claude/framework/AGENT_GUIDE", cr)
            self.assertIn("claude/framework/CLAUDE", cr)
            for v in cr.values():
                self.assertEqual(v["sage_version"], __version__)

    def test_materialize_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _mk_overlay(d, "agents", "implementer-a", "note")
            m.materialize(d, "claude")
            _, changed2, _ = m.materialize(d, "claude")
            self.assertEqual(changed2, [])  # 두 번째는 변경 없음

    def test_deletion_strips_block(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _mk_overlay(d, "agents", "implementer-a", "note")
            m.materialize(d, "claude")
            os.remove(os.path.join(d, "sage/asset_overrides/agents/implementer-a.md"))
            _, changed, _ = m.materialize(d, "claude")
            render = Path(os.path.join(d, ".claude/agents/implementer-a.md")).read_text()
            self.assertNotIn(oc.MARKER_START, render)  # 블록 제거됨

    def test_framework_overlay_materialized_after_domain_contract(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _profile_with_domain(d)
            _mk_overlay(d, "framework", "AGENT_GUIDE",
                        "---\ndomain_refs: [webrtc]\n---\nPreserve the project review protocol.\n")
            cr, changed, errors = m.materialize(d, "claude")
            self.assertEqual(errors, [])
            self.assertIn(os.path.join(d, "AGENT_GUIDE.md"), changed)
            body = Path(os.path.join(d, "AGENT_GUIDE.md")).read_text(encoding="utf-8")
            self.assertIn("Preserve the project review protocol.", body)
            self.assertNotIn("domain_refs", body)
            self.assertIn("claude/framework/AGENT_GUIDE", cr)

    def test_framework_unknown_domain_aborts_all_writes(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _profile_with_domain(d)
            before = Path(os.path.join(d, "AGENT_GUIDE.md")).read_text(encoding="utf-8")
            _mk_overlay(d, "framework", "AGENT_GUIDE",
                        "---\ndomain_refs: [payments]\n---\nProject rules.\n")
            cr, changed, errors = m.materialize(d, "claude")
            self.assertEqual(cr, {})
            self.assertEqual(changed, [])
            self.assertTrue(errors)
            self.assertEqual(Path(os.path.join(d, "AGENT_GUIDE.md")).read_text(encoding="utf-8"), before)


class TestCheck(unittest.TestCase):
    def _fresh(self, d):
        _base_renders(d)
        return m.materialize(d, "claude")[0]

    def test_clean_passes(self):
        with tempfile.TemporaryDirectory() as d:
            cr = self._fresh(d)
            self.assertEqual(m.check(d, "claude", cr), [])

    def test_blocked_overlay_file_fails(self):
        with tempfile.TemporaryDirectory() as d:
            cr = self._fresh(d)
            _mk_overlay(d, "agents", "reviewer", "anything")
            findings = m.check(d, "claude", cr)
            self.assertTrue(any(f[0] == "FAIL" and "reviewer" in f[1] for f in findings))

    def test_base_tamper_fails(self):
        with tempfile.TemporaryDirectory() as d:
            cr = self._fresh(d)
            p = os.path.join(d, ".claude/agents/leader.md")
            Path(p).write_text("# leader\nTAMPERED read your overlay first.\n", encoding="utf-8")
            findings = m.check(d, "claude", cr)
            self.assertTrue(any(f[0] == "FAIL" and "leader" in f[1] for f in findings))

    def test_overlay_edited_not_synced_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _mk_overlay(d, "agents", "implementer-a", "v1")
            cr = m.materialize(d, "claude")[0]
            _mk_overlay(d, "agents", "implementer-a", "v2 changed")  # 편집만, sync 안 함
            findings = m.check(d, "claude", cr)
            self.assertTrue(any(f[0] == "FAIL" and "implementer-a" in f[1] for f in findings))

    def test_missing_anchor_fails(self):
        with tempfile.TemporaryDirectory() as d:
            self._fresh(d)
            findings = m.check(d, "claude", {})  # 앵커 없음
            self.assertTrue(any(f[0] == "FAIL" for f in findings))

    def test_version_skew_stale(self):
        with tempfile.TemporaryDirectory() as d:
            cr = self._fresh(d)
            for v in cr.values():
                v["sage_version"] = "0.0.1"  # 옛 버전으로 위조 → skew
            findings = m.check(d, "claude", cr)
            self.assertTrue(any(f[0] == "STALE" for f in findings))


if __name__ == "__main__":
    unittest.main()
