#!/usr/bin/env python3
"""retro_gate 단위 — Stop 훅 정책, `sage retro --check` 실행 여부 사후 확인(9-C v1).

검증:
  1. off/no-06/run_id 특정불가 → INFO(N/A), block 없음
  2. checked=True → OK
  3. unchecked + advisory → WARN(block 아님)
  4. unchecked + enforce + stop_hook_active=False(첫 시도) → BLOCK
  5. unchecked + enforce + stop_hook_active=True(재시도) → WARN 로 낮춤(플랫폼 제약: 세션당 1회만 block)
  6. 무효 mode 문자열 → off 취급(fail-closed 로 조용히 통과시키지 않되, 최소 크래시 없음)
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
POLICIES = os.path.join(os.path.dirname(HERE), "policies")
sys.path.insert(0, POLICIES)
import retro_gate as rg  # noqa: E402


class TestRetroGate(unittest.TestCase):
    def test_off_is_info(self):
        r = rg.check("off", True, "rl-a", False, False)
        self.assertEqual(r["severity"], "INFO")
        self.assertIn("off", r["text"])

    def test_invalid_mode_treated_as_off(self):
        r = rg.check("bogus", True, "rl-a", False, False)
        self.assertEqual(r["severity"], "INFO")

    def test_no_06_this_session_is_info(self):
        r = rg.check("enforce", False, "rl-a", False, False)
        self.assertEqual(r["severity"], "INFO")
        self.assertIn("06", r["text"])

    def test_unresolvable_run_id_is_info_not_block(self):
        # 멀티사이클/마커없음 등으로 run_id 특정 불가 → 오탐보다 침묵(skip)이 낫다.
        r = rg.check("enforce", True, None, False, False)
        self.assertEqual(r["severity"], "INFO")

    def test_checked_is_ok_regardless_of_mode(self):
        for mode in ("advisory", "enforce"):
            r = rg.check(mode, True, "rl-a", True, False)
            self.assertEqual(r["severity"], "OK", mode)
            self.assertIn("rl-a", r["text"])

    def test_advisory_unchecked_is_warn_never_block(self):
        r = rg.check("advisory", True, "rl-a", False, False)
        self.assertEqual(r["severity"], "WARN")
        r2 = rg.check("advisory", True, "rl-a", False, True)   # stop_hook_active 무관
        self.assertEqual(r2["severity"], "WARN")

    def test_enforce_unchecked_first_attempt_blocks(self):
        r = rg.check("enforce", True, "rl-a", False, False)
        self.assertEqual(r["severity"], "BLOCK")
        self.assertIn("rl-a", r["text"])
        self.assertIn("retro --check", r["text"])

    def test_enforce_unchecked_retry_never_blocks_again(self):
        # 플랫폼 제약(stop_hook_active): 세션당 block 은 정확히 1회. 무시하면 반드시 통과.
        r = rg.check("enforce", True, "rl-a", False, True)
        self.assertEqual(r["severity"], "WARN")

    def test_block_text_includes_actionable_command(self):
        r = rg.check("enforce", True, "rl-xyz", False, False)
        self.assertIn("--run-id rl-xyz", r["text"])

    def test_name_field_is_stable(self):
        for args in (("off", True, "rl-a", False, False), ("enforce", True, "rl-a", True, False)):
            self.assertEqual(rg.check(*args)["name"], "retro_gate")

    def test_notes_disabled_is_inactive_even_under_enforce(self):
        # codex 6R P1: retro_note off → 노트 미생성 → --check 불가 → enforce 라도 skip(INFO), block 아님.
        r = rg.check("enforce", True, "rl-a", False, False, notes_enabled=False)
        self.assertEqual(r["severity"], "INFO")
        self.assertIn("retro_note off", r["text"])

    def test_notes_enabled_default_true_preserves_block(self):
        # notes_enabled 미전달(기본 True) 시 종전 동작 유지.
        r = rg.check("enforce", True, "rl-a", False, False)
        self.assertEqual(r["severity"], "BLOCK")


if __name__ == "__main__":
    unittest.main(verbosity=2)
