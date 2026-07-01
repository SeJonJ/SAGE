#!/usr/bin/env python3
"""messages SSOT 단위 테스트 (5-3).

io_claude/io_codex 공유 문구 모듈이 message_key/phase4/declared/report 를 런타임별로
정확히 렌더하는지 핀(pin)한다. 게이트 문구는 사용자 대상 출력 계약이므로, 통일된 포맷을
여기서 고정해 이후 드리프트를 회귀로 잡는다(codex 5-3 R1 P2: 비-게이트 출력 핀 부재 해소).
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "runtime"))
import messages as M  # noqa: E402


class TestGateText(unittest.TestCase):
    def _d(self, key, **kw):
        base = {"message_key": key, "file_short": "f.py", "reason": "R",
                "risk": "L2", "missing_phases": ["00", "01"]}
        base.update(kw)
        return base

    def test_unknown_key_empty(self):
        self.assertEqual(M.gate_text(self._d("nope"), {}, "claude"), "")
        self.assertEqual(M.gate_text(self._d("nope"), {}, "codex"), "")

    def test_all_legacy_keys_render_nonempty(self):
        # 옛 io_claude/io_codex 테이블의 모든 message_key 가 여전히 렌더된다(silent drop 방지).
        keys = ["block_desktop", "block_l3_no_plan", "block_l3_strategy_unresolved",
                "warn_l3_no_review", "warn_l2_no_plan", "warn_l0_l3_content",
                "block_phase_incomplete", "warn_phase_incomplete",
                "block_report_without_approval", "block_report_without_audit",
                "warn_report_without_audit", "block_report_without_acceptance",
                "warn_report_without_acceptance", "ok_l3", "ok_l2"]
        for k in keys:
            for rt in ("claude", "codex"):
                self.assertTrue(M.gate_text(self._d(k), {}, rt), f"{k}/{rt} empty")

    def test_claude_block_emoji_emdash_newline_hint(self):
        m = M.gate_text(self._d("block_l3_no_plan"), {}, "claude")
        self.assertTrue(m.startswith("⛔ [GATE BLOCK — L3]"))
        self.assertIn("파일: f.py", m)
        self.assertIn("| 근거: R", m)
        self.assertIn("\n  → ", m)   # claude 힌트는 개행+화살표

    def test_codex_block_hyphen_pipe_hint(self):
        m = M.gate_text(self._d("block_l3_no_plan"), {}, "codex")
        self.assertTrue(m.startswith("[GATE BLOCK - L3]"))   # ASCII 하이픈, emoji 없음
        self.assertNotIn("\n", m)                             # codex 는 한 줄(파이프 구분)
        self.assertIn(" | ", m)

    def test_ok_layout_uses_pipe_fs(self):
        # OK 는 "파일:" 대신 " | {fs}" 레이아웃.
        self.assertEqual(M.gate_text(self._d("ok_l2"), {}, "claude"), "✅ [GATE OK — L2] plan 확인 | f.py")
        self.assertEqual(M.gate_text(self._d("ok_l2"), {}, "codex"), "[GATE OK - L2] plan 확인 | f.py")

    def test_desktop_hint_from_profile(self):
        prof = {"risk": {"desktop_block_hint": "커스텀힌트"}}
        self.assertIn("커스텀힌트", M.gate_text(self._d("block_desktop"), prof, "claude"))
        self.assertIn("커스텀힌트", M.gate_text(self._d("block_desktop"), prof, "codex"))

    def test_phase_incomplete_interpolates_missing_and_risk(self):
        m = M.gate_text(self._d("block_phase_incomplete"), {}, "claude")
        self.assertIn("[GATE BLOCK — L2]", m)      # scope = risk (동적)
        self.assertIn("[00, 01]", m)               # missing_phases 조인

    def test_review_cmd_prefix_per_runtime(self):
        self.assertIn("/sage-review", M.gate_text(self._d("block_report_without_audit"), {}, "claude"))
        self.assertIn("$sage-review", M.gate_text(self._d("block_report_without_audit"), {}, "codex"))
        self.assertNotIn("$sage-review", M.gate_text(self._d("block_report_without_audit"), {}, "claude"))


class TestOtherMessages(unittest.TestCase):
    def test_declared_capture(self):
        self.assertEqual(M.declared_capture_text("L3", "claude"),
                         "ℹ️  [Risk 선언 포착] 이번 세션 작업 레벨: L3 — 소스 수정 시 해당 레벨 게이트가 적용됩니다.")
        self.assertEqual(M.declared_capture_text("L3", "codex"),
                         "[Risk 선언 포착] 이번 세션 작업 레벨: L3 — 소스 수정 시 해당 레벨 게이트가 적용됩니다.")

    def test_report_saved_host_dir(self):
        self.assertEqual(M.report_saved_text(".claude", "2026-07-01", "claude"),
                         "📋 Compliance report saved: .claude/logs/compliance-2026-07-01.md")
        self.assertEqual(M.report_saved_text(".codex", "2026-07-01", "codex"),
                         "Compliance report saved: .codex/logs/compliance-2026-07-01.md")

    def test_phase4_arrow_and_dash_per_runtime(self):
        self.assertEqual(M.phase4_block_header(3, "feat", "claude"),
                         "⛔ [GATE BLOCK — Phase 3→4] 체크리스트 미완료 3건 (기능: feat)")
        self.assertEqual(M.phase4_block_header(3, "feat", "codex"),
                         "[GATE BLOCK - Phase 3->4] 체크리스트 미완료 3건 (기능: feat)")
        self.assertTrue(M.phase4_warn("feat", "claude").startswith("⚠️"))
        self.assertIn("3->4", M.phase4_warn("feat", "codex"))
        self.assertIn("완료 확인", M.phase4_ok("feat", "claude"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
