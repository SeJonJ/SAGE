#!/usr/bin/env python3
"""EH-18 conformance: sage-init/sage-profile-modify/bootstrap-authoring.md must keep naming
the schema keys they are responsible for raising or documenting.

These are not behavior tests (SKILL.md is a prompt, not code) — they are drift guards. If a
future edit strips one of these mentions, the interview silently regresses to the same gap
EH-18 fixed, and nothing else would catch it.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SAGE_INIT = ROOT / "templates/core/framework/.claude/skills/sage-init/SKILL.md"
PROFILE_MODIFY = ROOT / "templates/core/framework/.claude/skills/sage-profile-modify/SKILL.md"
BOOTSTRAP_AUTHORING = ROOT / "templates/core/framework/docs/agent/bootstrap-authoring.md"


class TestSkillInterviewCoverage(unittest.TestCase):
    def test_sage_init_raises_active_host(self):
        text = SAGE_INIT.read_text(encoding="utf-8")
        self.assertIn("runtime.active_host", text)

    def test_sage_init_raises_feedback(self):
        text = SAGE_INIT.read_text(encoding="utf-8")
        self.assertIn("feedback.*", text)
        self.assertIn("block_release", text)
        self.assertIn("`record`", text)

    def test_sage_init_raises_acceptance(self):
        text = SAGE_INIT.read_text(encoding="utf-8")
        self.assertIn("verification.acceptance", text)

    def test_sage_init_raises_checklist_scan_targets(self):
        text = SAGE_INIT.read_text(encoding="utf-8")
        self.assertIn("checklist_scan_targets", text)

    def test_sage_init_raises_l2_content_keywords(self):
        text = SAGE_INIT.read_text(encoding="utf-8")
        self.assertIn("l2_content_keywords", text)

    def test_profile_modify_lists_conventions(self):
        text = PROFILE_MODIFY.read_text(encoding="utf-8")
        self.assertIn("`conventions`", text)

    def test_bootstrap_authoring_documents_inert_runtime_fields(self):
        text = BOOTSTRAP_AUTHORING.read_text(encoding="utf-8")
        self.assertIn("runtime.asset_ssot", text)
        self.assertIn("runtime.external_reviewer", text)

    def test_bootstrap_authoring_documents_compaction_as_advanced(self):
        text = BOOTSTRAP_AUTHORING.read_text(encoding="utf-8")
        self.assertIn("context_management.compaction", text)


if __name__ == "__main__":
    unittest.main()
