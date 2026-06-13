#!/usr/bin/env python3
"""auto_approve_decision 검증 (step8 — 승인 UX).

auto iff validate PASS + unresolved 없음 + not safety_degraded + risk 없음 + render_current.
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))  # sage_project
sys.path.insert(0, REPO)
from sage.commands.review import auto_approve_decision, _render_current  # noqa: E402


def hook_entry(**over):
    e = {"form": "core_adapter", "render_hash": {"claude": "x", "codex": "y"},
         "unresolved": [], "risk": []}
    e.update(over)
    return e


def agent_entry(**over):
    e = {"form": "interpretive", "render_hash": {"claude": "x", "codex": "y"},
         "unresolved": [], "risk": []}
    e.update(over)
    return e


class TestDecision(unittest.TestCase):
    def test_auto(self):
        self.assertEqual(auto_approve_decision("hooks/x", "PASS", hook_entry())["decision"], "auto")

    def test_review_validate_warn(self):
        d = auto_approve_decision("hooks/x", "WARN", hook_entry())
        self.assertEqual(d["decision"], "review")
        self.assertIn("validate=WARN", d["reasons"])

    def test_review_stale(self):
        self.assertEqual(auto_approve_decision("hooks/x", "STALE", hook_entry())["decision"], "review")

    def test_review_fail(self):
        self.assertEqual(auto_approve_decision("hooks/x", "FAIL", hook_entry())["decision"], "review")

    def test_review_unresolved(self):
        d = auto_approve_decision("hooks/x", "PASS", hook_entry(unresolved=["drift"]))
        self.assertEqual(d["decision"], "review")
        self.assertTrue(any("unresolved" in r for r in d["reasons"]))

    def test_review_safety_degraded(self):
        d = auto_approve_decision("hooks/x", "PASS", hook_entry(safety_degraded=True))
        self.assertEqual(d["decision"], "review")
        self.assertIn("safety_degraded", d["reasons"])

    def test_review_risk(self):
        self.assertEqual(auto_approve_decision("hooks/x", "PASS", hook_entry(risk=["r"]))["decision"], "review")

    def test_review_render_not_current(self):
        # agent: render_hash 한쪽만 → render 미최신 → review
        d = auto_approve_decision("agents/x", "PASS", agent_entry(render_hash={"claude": "x"}))
        self.assertEqual(d["decision"], "review")
        self.assertTrue(any("render" in r for r in d["reasons"]))

    def test_agent_auto(self):
        self.assertEqual(auto_approve_decision("agents/x", "PASS", agent_entry())["decision"], "auto")


class TestRenderCurrent(unittest.TestCase):
    def test_native(self):
        self.assertTrue(_render_current({"form": "native", "render_hash": {"native": "x"}}))
        self.assertFalse(_render_current({"form": "native", "render_hash": {}}))

    def test_interpretive_needs_both(self):
        self.assertTrue(_render_current({"form": "interpretive", "render_hash": {"claude": "x", "codex": "y"}}))
        self.assertFalse(_render_current({"form": "interpretive", "render_hash": {"claude": "x"}}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
