#!/usr/bin/env python3
"""Project SAGE version contract tests."""
import os
import sys
import unittest


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)

from sage.version_contract import (  # noqa: E402
    version_axes,
    version_contract_issues,
    version_is_exact,
)


class VersionContractTests(unittest.TestCase):
    def test_exact_match_has_no_issues(self):
        profile = {"sage": {"required_version": "0.9.60"}}
        manifest = {"sage_version": "0.9.60", "generator_version": "0.9.60"}

        axes = version_axes(profile, manifest, "0.9.60")

        self.assertEqual("0.9.60", axes.required)
        self.assertEqual("0.9.60", axes.installed)
        self.assertEqual("0.9.60", axes.generated)
        self.assertEqual("0.9.60", axes.runtime)
        self.assertEqual([], version_contract_issues(profile, manifest, "0.9.60"))

    def test_each_mismatch_is_a_nonblocking_warning_with_remediation(self):
        profile = {
            "sage": {"required_version": "1.2.3"},
            "runtime": {"active_host": "codex"},
        }
        manifest = {
            "sage_version": "1.2.0",
            "generator_version": "1.2.1",
            "host_runtime": "codex",
            "core_skill_receipts": {
                "codex": {"scope": "project-local", "sage_version": "1.2.0"},
            },
        }

        issues = version_contract_issues(profile, manifest, "1.2.2")

        self.assertEqual(["installed", "generated", "runtime"], [issue.axis for issue in issues])
        self.assertTrue(all(issue.severity == "WARN" for issue in issues))
        self.assertIn("sage install --host codex --skill-scope project-local --force",
                      issues[0].remediation)
        self.assertIn("sage generate --kind hook --write", issues[1].remediation)
        self.assertIn("sage-harness==1.2.3", issues[2].remediation)

    def test_missing_manifest_axes_are_unknown_not_false_matches(self):
        profile = {"sage": {"required_version": "0.9.60"}}

        axes = version_axes(profile, None, "0.9.60")
        issues = version_contract_issues(profile, None, "0.9.60")

        self.assertEqual("unknown", axes.installed)
        self.assertEqual("unknown", axes.generated)
        self.assertEqual(["installed", "generated"], [issue.axis for issue in issues])
        self.assertTrue(all(issue.severity == "WARN" for issue in issues))

    def test_legacy_profile_without_required_version_reports_unknown_only(self):
        axes = version_axes({}, {"sage_version": "0.9.60"}, "0.9.60")
        issues = version_contract_issues({}, {"sage_version": "0.9.60"}, "0.9.60")

        self.assertEqual("unknown", axes.required)
        self.assertEqual(1, len(issues))
        self.assertEqual("INFO", issues[0].severity)
        self.assertEqual("required", issues[0].axis)

    def test_invalid_required_version_is_fail_without_comparison_noise(self):
        issues = version_contract_issues(
            {"sage": {"required_version": ">=0.9"}},
            {"sage_version": "0.9.60", "generator_version": "0.9.60"},
            "0.9.60",
        )

        self.assertEqual(1, len(issues))
        self.assertEqual("FAIL", issues[0].severity)
        self.assertEqual("required", issues[0].axis)

    def test_non_string_required_version_is_malformed_not_legacy(self):
        issues = version_contract_issues(
            {"sage": {"required_version": 1.2}},
            {"sage_version": "0.9.60", "generator_version": "0.9.60"},
            "0.9.60",
        )

        self.assertEqual(1, len(issues))
        self.assertEqual("FAIL", issues[0].severity)
        self.assertEqual("required", issues[0].axis)
        self.assertIn("1.2", issues[0].message)

    def test_malformed_receipt_and_runtime_axes_are_explicit_nonblocking_warnings(self):
        cases = (
            ("installed", {"sage_version": "latest", "generator_version": "1.2.3"}, "1.2.3"),
            ("installed", {"sage_version": 1.2, "generator_version": "1.2.3"}, "1.2.3"),
            ("generated", {"sage_version": "1.2.3", "generator_version": "latest"}, "1.2.3"),
            ("runtime", {"sage_version": "1.2.3", "generator_version": "1.2.3"}, "latest"),
        )
        profile = {"sage": {"required_version": "1.2.3"}}

        for expected_axis, manifest, runtime in cases:
            with self.subTest(axis=expected_axis, manifest=manifest, runtime=runtime):
                issues = version_contract_issues(profile, manifest, runtime)

                self.assertEqual(1, len(issues))
                self.assertEqual("WARN", issues[0].severity)
                self.assertEqual(expected_axis, issues[0].axis)
                self.assertIn("형식 오류", issues[0].message)

    def test_exact_version_format_accepts_suffixes_and_rejects_ranges(self):
        self.assertTrue(version_is_exact("1.2.3"))
        self.assertTrue(version_is_exact("1.2.3-rc.1+build.5"))
        for invalid in ("1.2", "01.2.3", ">=1.2.3", "1.2.x", "latest", ""):
            with self.subTest(version=invalid):
                self.assertFalse(version_is_exact(invalid))


if __name__ == "__main__":
    unittest.main(verbosity=2)
