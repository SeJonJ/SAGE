#!/usr/bin/env python3
"""reviewer_resolution 검증 (7차 배치2 — gstack 의존 폐기, peer CLI 직접 탐지).

결정표:
  cross off → same-runtime(degraded=false, 의도적)
  cross on + claude-host + codex CLI 가용 → opposite(codex) via `codex exec`
  cross on + claude-host + codex CLI 불가 → blocked(codex_cli_unavailable)
  cross on + codex-host + claude CLI 가용 → opposite(claude) via `claude -p`
  cross on + codex-host + claude CLI 불가 → blocked(claude_cli_unavailable)
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import doctor as D  # noqa: E402


def prof(host, cross):
    return {"runtime": {"host": host}, "options": {"cross_model": cross}}


class TestReviewerResolution(unittest.TestCase):
    def test_cross_off_intentional(self):
        r = D.reviewer_resolution(prof("claude", False), {"codex": True, "claude": True})
        self.assertEqual(r["reviewer_mode"], "clean_context_same_runtime")
        self.assertFalse(r["fallback_used"])
        self.assertFalse(r["reviewer_degraded"])  # 의도적 — degraded 아님

    def test_claude_host_codex_avail_opposite(self):
        r = D.reviewer_resolution(prof("claude", True), {"codex": True})
        self.assertEqual(r["reviewer_mode"], "opposite_runtime")
        self.assertEqual(r["reviewer_runtime"], "codex")
        self.assertFalse(r["reviewer_degraded"])

    def test_claude_host_no_codex_blocks(self):
        r = D.reviewer_resolution(prof("claude", True), {"codex": False})
        self.assertEqual(r["reviewer_mode"], "blocked")
        self.assertFalse(r["fallback_used"])
        self.assertTrue(r["reviewer_degraded"])
        self.assertEqual(r["reviewer_runtime"], "codex")
        self.assertEqual(r["reviewer_degrade_reason"], "codex_cli_unavailable")

    def test_codex_host_claude_avail_opposite(self):
        r = D.reviewer_resolution(prof("codex", True), {"claude": True})
        self.assertEqual(r["reviewer_mode"], "opposite_runtime")
        self.assertEqual(r["reviewer_runtime"], "claude")
        self.assertFalse(r["reviewer_degraded"])

    def test_codex_host_no_claude_cli_blocks(self):
        r = D.reviewer_resolution(prof("codex", True), {"claude": False})
        self.assertEqual(r["reviewer_mode"], "blocked")
        self.assertFalse(r["fallback_used"])
        self.assertTrue(r["reviewer_degraded"])
        self.assertEqual(r["reviewer_runtime"], "claude")
        self.assertEqual(r["reviewer_degrade_reason"], "claude_cli_unavailable")

    def test_peer_runtime_independent_of_caps_keys(self):
        # claude-host 는 codex caps 만 보고, claude caps 유무는 무관(대칭 확인).
        r = D.reviewer_resolution(prof("claude", True), {"codex": True, "claude": False})
        self.assertEqual(r["reviewer_runtime"], "codex")
        self.assertFalse(r["reviewer_degraded"])


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
