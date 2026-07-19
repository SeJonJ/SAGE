#!/usr/bin/env python3
"""writeback_depth_gate 단위 — Stop 훅 정책, L2/L3 write-back 심층 노트가 depth self-review 를
거쳤는지 06 자기선언(`Depth-Self-Review: performed`)으로 사후 확인.

검증:
  1. off/invalid mode → INFO(N/A)
  2. write-back off(vault_enabled=False) → INFO(강제 대상 노트 없음)
  3. applies=False(L1·06 없음) → INFO
  4. declared=True → OK
  5. 미선언 + advisory → WARN(block 아님)
  6. 미선언 + enforce + 첫 Stop → BLOCK
  7. 미선언 + enforce + 재시도(stop_hook_active) → WARN 로 낮춤(세션당 1회 block 제약)
  8. off 우선순위: applies·미선언이어도 off 면 INFO
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
POLICIES = os.path.join(os.path.dirname(HERE), "policies")
sys.path.insert(0, POLICIES)
import writeback_depth_gate as wg  # noqa: E402


class TestWritebackDepthGate(unittest.TestCase):
    def test_off_is_info(self):
        r = wg.check("off", True, False, False)
        self.assertEqual(r["severity"], "INFO")
        self.assertIn("off", r["text"])

    def test_invalid_mode_treated_as_off(self):
        r = wg.check("bogus", True, False, False)
        self.assertEqual(r["severity"], "INFO")

    def test_vault_disabled_is_info(self):
        # write-back 이 꺼져 심층 노트가 안 써지면 강제할 대상이 없다 → skip(INFO).
        r = wg.check("enforce", True, False, False, vault_enabled=False)
        self.assertEqual(r["severity"], "INFO")
        self.assertIn("write-back off", r["text"])

    def test_no_l2l3_06_is_info(self):
        r = wg.check("enforce", False, False, False)
        self.assertEqual(r["severity"], "INFO")

    def test_declared_is_ok(self):
        r = wg.check("enforce", True, True, False)
        self.assertEqual(r["severity"], "OK")
        self.assertIn("performed", r["text"])

    def test_undeclared_advisory_warns(self):
        r = wg.check("advisory", True, False, False)
        self.assertEqual(r["severity"], "WARN")
        self.assertIn("Depth-Self-Review", r["text"])

    def test_undeclared_enforce_first_stop_blocks(self):
        r = wg.check("enforce", True, False, False)
        self.assertEqual(r["severity"], "BLOCK")

    def test_undeclared_enforce_retry_downgrades_to_warn(self):
        # 플랫폼 제약: enforce BLOCK 도 재시도(stop_hook_active=True)에선 WARN 로 낮춰 무한 block 방지.
        r = wg.check("enforce", True, False, True)
        self.assertEqual(r["severity"], "WARN")

    def test_off_precedence_over_undeclared(self):
        r = wg.check("off", True, False, False)
        self.assertEqual(r["severity"], "INFO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
