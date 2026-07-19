#!/usr/bin/env python3
"""sage.overlay_lint — CORE 자산 오버레이 게이트-완화 결정론 린트 검증.

오버레이(sage/asset_overrides/**)의 "must not relax gates" 프로즈를 실제 체크로 승격한 것.
default validate는 WARN, materialization preflight와 strict validate는 hard-fail한다.
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

    def test_flags_optional_or_unapproved_review(self):
        self.assertTrue(overlay_lint.scan_text("Phase 05 review is optional for hotfixes."))
        self.assertTrue(overlay_lint.scan_text("Approval is not required before Phase 06."))
        self.assertTrue(overlay_lint.scan_text("Deploy without approval."))
        self.assertTrue(overlay_lint.scan_text("긴급 배포에서는 리뷰가 필수 아님."))
        self.assertTrue(overlay_lint.scan_text("Skip approval for hotfixes."))
        self.assertTrue(overlay_lint.scan_text("Bypass approval for emergencies."))
        self.assertTrue(overlay_lint.scan_text("승인을 생략한다."))
        self.assertTrue(overlay_lint.scan_text("Phase 05 review may be omitted for hotfixes."))
        self.assertTrue(overlay_lint.scan_text("Phase 05 review need not be performed."))

    def test_flags_natural_passive_and_no_approval_variants(self):
        samples = [
            "All reviews may be skipped for hotfixes.",
            "Proceed with no approval for emergency changes.",
            "Turn off the review gate for hotfixes.",
            "Verification is unnecessary for documentation-only edits.",
            "Phase 05 approval is not needed for hotfixes.",
            "긴급 배포에서는 승인을 받지 않아도 된다.",
            "리뷰를 수행할 필요가 없다.",
        ]
        for text in samples:
            with self.subTest(text=text):
                self.assertTrue(overlay_lint.scan_text(text), text)

    def test_scan_overlays_includes_mixed_case_markdown_extension(self):
        with tempfile.TemporaryDirectory() as root:
            agents = os.path.join(root, "sage", "asset_overrides", "agents")
            os.makedirs(agents)
            Path(os.path.join(agents, "implementer-a.MD")).write_text(
                "Phase 05 review is optional.\n", encoding="utf-8")
            results = overlay_lint.scan_overlays(root)
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0][0].endswith("implementer-a.MD"))

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

    def _framework(self, root, body):
        d = os.path.join(root, "sage", "asset_overrides", "framework")
        os.makedirs(d, exist_ok=True)
        Path(os.path.join(d, "AGENT_GUIDE.md")).write_text(body, encoding="utf-8")

    def _profile(self):
        return {"risk": {"domains": [{
            "id": "webrtc", "risk_level": "L3",
            "path_globs": ["**/kurento/**"],
            "content_keywords": ["RTCPeerConnection"],
            "protocol_pointer": "sage/critical-domains/webrtc.md",
        }]}}

    def test_domain_contract_accepts_reference_only(self):
        with tempfile.TemporaryDirectory() as root:
            self._framework(root, "---\ndomain_refs: [webrtc]\n---\n# Project rules\nFollow the domain protocol.\n")
            self.assertEqual(overlay_lint.scan_domain_contract(root, self._profile()), [])

    def test_domain_contract_rejects_unknown_reference(self):
        with tempfile.TemporaryDirectory() as root:
            self._framework(root, "---\ndomain_refs: [payments]\n---\n# Rules\n")
            findings = overlay_lint.scan_domain_contract(root, self._profile())
            self.assertTrue(any("미등록" in msg for _, _, msg in findings))

    def test_domain_contract_rejects_trigger_duplication(self):
        with tempfile.TemporaryDirectory() as root:
            self._framework(root, "---\ndomain_refs: [webrtc]\n---\nWatch **/kurento/** and `RTCPeerConnection`.\n")
            findings = overlay_lint.scan_domain_contract(root, self._profile())
            self.assertGreaterEqual(len([x for x in findings if "재복제" in x[2]]), 2)

    def test_domain_contract_rejects_extra_frontmatter_key(self):
        with tempfile.TemporaryDirectory() as root:
            self._framework(root, "---\ndomain_refs: [webrtc]\nrisk_level: L0\n---\n# Rules\n")
            findings = overlay_lint.scan_domain_contract(root, self._profile())
            self.assertTrue(any("미허용 키" in msg for _, _, msg in findings))


if __name__ == "__main__":
    unittest.main()
