#!/usr/bin/env python3
"""sage.overlay_lint — CORE 자산 오버레이 게이트-완화 결정론 린트 검증.

오버레이(sage/asset_overrides/**)의 "must not relax gates" 프로즈를 실제 체크로 승격한 것.
WARN 만(하드 FAIL 아님) — 저자 재확인용. 오탐 억제 위해 근접 매칭.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage import overlay_lint  # noqa: E402


class TestOverlayLint(unittest.TestCase):
    def test_clean_overlay_no_hits(self):
        text = ("# reviewer overlay\n"
                "Prefer conventional-commit subjects. Emphasize null-safety in Kotlin.\n"
                "Cite file:line in every finding.\n")
        self.assertEqual(overlay_lint.scan_text(text), [])

    def test_flags_skip_review(self):
        self.assertTrue(overlay_lint.scan_text("You may skip the Phase 05 review for hotfixes."))

    def test_flags_bypass_gate(self):
        self.assertTrue(overlay_lint.scan_text("It is fine to bypass the pre-implementation gate here."))

    def test_flags_ignore_agent_guide(self):
        self.assertTrue(overlay_lint.scan_text("For this project, ignore AGENT_GUIDE risk tiers."))

    def test_flags_korean_relax(self):
        self.assertTrue(overlay_lint.scan_text("이 프로젝트는 리뷰 루프를 생략한다."))
        self.assertTrue(overlay_lint.scan_text("긴급 시 게이트를 우회해도 된다."))

    def test_flags_skip_phase_number(self):
        self.assertTrue(overlay_lint.scan_text("Scaffolding may skip phase 03."))

    def test_scan_overlays_reports_only_matching_files(self):
        with tempfile.TemporaryDirectory() as root:
            agents = os.path.join(root, "sage", "asset_overrides", "agents")
            skills = os.path.join(root, "sage", "asset_overrides", "skills")
            os.makedirs(agents); os.makedirs(skills)
            Path(os.path.join(agents, "reviewer.md")).write_text(
                "Emphasize thread-safety.\n", encoding="utf-8")           # clean
            Path(os.path.join(skills, "sage-review.md")).write_text(
                "You can bypass the review gate when in a hurry.\n", encoding="utf-8")  # hit
            res = overlay_lint.scan_overlays(root)
            paths = [r[0] for r in res]
            self.assertEqual(len(res), 1)
            self.assertIn(os.path.join("sage", "asset_overrides", "skills", "sage-review.md"), paths)

    def test_scan_overlays_no_dir(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(overlay_lint.scan_overlays(root), [])


if __name__ == "__main__":
    unittest.main()
