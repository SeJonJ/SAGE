#!/usr/bin/env python3
"""reviewer_resolution 검증 (step10 — codex-host opposite reviewer fallback).

4행 결정표(Codex 2R):
  cross off → same-runtime(degraded=false, 의도적)
  cross on + claude-host + gstack → opposite(codex)
  cross on + claude-host + !gstack → fallback(degraded, gstack_unavailable)
  cross on + codex-host(미설정) → fallback(degraded, codex_host_claude_invocation_unresolved)
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import doctor as D  # noqa: E402


def prof(host, cross, claude_host="/codex consult", codex_host=""):
    return {
        "runtime": {"host": host},
        "options": {"cross_model": cross},
        "cross_model": {"invocation": {"claude_host": claude_host, "codex_host": codex_host}},
    }


class TestReviewerResolution(unittest.TestCase):
    def test_cross_off_intentional(self):
        r = D.reviewer_resolution(prof("claude", False), {"gstack": True})
        self.assertEqual(r["reviewer_mode"], "clean_context_same_runtime")
        self.assertFalse(r["fallback_used"])
        self.assertFalse(r["reviewer_degraded"])  # 의도적 — degraded 아님

    def test_claude_host_gstack_opposite(self):
        r = D.reviewer_resolution(prof("claude", True), {"gstack": True})
        self.assertEqual(r["reviewer_mode"], "opposite_runtime")
        self.assertEqual(r["reviewer_runtime"], "codex")
        self.assertFalse(r["reviewer_degraded"])

    def test_claude_host_no_gstack_fallback(self):
        r = D.reviewer_resolution(prof("claude", True), {"gstack": False})
        self.assertEqual(r["reviewer_mode"], "clean_context_same_runtime")
        self.assertTrue(r["fallback_used"])
        self.assertTrue(r["reviewer_degraded"])
        self.assertEqual(r["reviewer_degrade_reason"], "gstack_unavailable")

    def test_codex_host_unresolved_fallback(self):
        r = D.reviewer_resolution(prof("codex", True, codex_host=""), {"gstack": False})
        self.assertEqual(r["reviewer_mode"], "clean_context_same_runtime")
        self.assertTrue(r["reviewer_degraded"])
        self.assertEqual(r["reviewer_degrade_reason"], "codex_host_claude_invocation_unresolved")

    def test_codex_host_configured_opposite(self):
        r = D.reviewer_resolution(prof("codex", True, codex_host="$claude consult"), {"gstack": False})
        self.assertEqual(r["reviewer_mode"], "opposite_runtime")
        self.assertEqual(r["reviewer_runtime"], "claude")


class TestDoctorOutput(unittest.TestCase):
    def test_doctor_runs_exit0(self):
        class Args:
            profile = None
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = D.run(Args())
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("옵션 의존성", out)
        self.assertIn("Phase 05 reviewer", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
