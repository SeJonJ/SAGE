#!/usr/bin/env python3
"""reviewer_resolution 검증 (step10 — cross-model reviewer 대칭 능력게이팅, P2-8).

결정표:
  cross off → same-runtime(degraded=false, 의도적)
  cross on + claude-host + gstack → opposite(codex)
  cross on + claude-host + !gstack → fallback(degraded, gstack_unavailable)
  cross on + codex-host + claude CLI → opposite(claude)
  cross on + codex-host + !claude CLI → fallback(degraded, claude_cli_unavailable)  [P2-8 스텁 제거]
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

    def test_codex_host_configured_with_claude_opposite(self):
        # P2-8: 경로 설정 + claude CLI 가용 → opposite(claude). (이전엔 능력검증 없이 맹신 — 스텁)
        r = D.reviewer_resolution(prof("codex", True, codex_host="$claude consult"), {"claude": True})
        self.assertEqual(r["reviewer_mode"], "opposite_runtime")
        self.assertEqual(r["reviewer_runtime"], "claude")
        self.assertFalse(r["reviewer_degraded"])

    def test_codex_host_configured_no_claude_cli_fallback(self):
        # P2-8 대칭 게이팅: 경로 설정됐으나 claude CLI 미가용 → degraded fallback(claude_cli_unavailable).
        r = D.reviewer_resolution(prof("codex", True, codex_host="$claude consult"), {"claude": False})
        self.assertEqual(r["reviewer_mode"], "clean_context_same_runtime")
        self.assertTrue(r["reviewer_degraded"])
        self.assertEqual(r["reviewer_degrade_reason"], "claude_cli_unavailable")


class TestDoctorOutput(unittest.TestCase):
    def test_doctor_runs_exit0(self):
        class Args:
            profile = None
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = D.run(Args())
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("실행 환경", out)   # P3-11: OS/python/bash 진단 섹션
        self.assertIn("bash", out)
        self.assertIn("옵션 의존성", out)
        self.assertIn("Phase 05 reviewer", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
