#!/usr/bin/env python3
"""Regression tests for manual double-host profile and review routing."""
import unittest

from sage.commands.doctor import reviewer_resolution
from sage.commands.install import team_runtime_issues
from sage.commands.review import intended_peer
from sage.profile_validate import validate_profile
from sage.runtime_hosts import (active_host, configured_hosts, opposite_host, profile_issues,
                                receipt_hosts, receipt_issues)


class RuntimeHostTests(unittest.TestCase):
    def test_legacy_host_remains_compatible(self):
        profile = {"runtime": {"host": "codex"}}
        self.assertEqual("codex", active_host(profile))
        self.assertEqual(["codex"], configured_hosts(profile))
        self.assertEqual([], profile_issues(profile))

    def test_new_double_host_has_one_active_and_opposite_reviewer(self):
        profile = {
            "runtime": {"installed_hosts": ["claude", "codex"], "active_host": "codex"},
            "options": {"cross_model": True},
        }
        self.assertEqual("codex", active_host(profile))
        self.assertEqual(["claude", "codex"], configured_hosts(profile))
        self.assertEqual("claude", opposite_host(profile))
        self.assertEqual("claude", intended_peer(profile))
        result = reviewer_resolution(profile, {"claude": True, "codex": True})
        self.assertEqual("opposite_runtime", result["reviewer_mode"])
        self.assertEqual("claude", result["reviewer_runtime"])
        self.assertEqual([], profile_issues(profile))

    def test_active_claude_routes_to_codex(self):
        profile = {
            "runtime": {"installed_hosts": ["claude", "codex"], "active_host": "claude"},
            "options": {"cross_model": True},
        }
        result = reviewer_resolution(profile, {"claude": True, "codex": True})
        self.assertEqual("codex", result["reviewer_runtime"])

    def test_active_codex_drives_host_specific_agent_diagnostic(self):
        profile = {
            "runtime": {"installed_hosts": ["claude", "codex"], "active_host": "codex"},
            "options": {"cross_model": True},
            "team": {"core": {"reviewer": {"runtime": {"effort": "high"}}}},
        }
        issues = team_runtime_issues(profile)
        self.assertTrue(any(severity == "WARN" and "codex host" in message
                            for severity, message in issues))

    def test_legacy_alias_conflict_is_fail_closed(self):
        profile = {"runtime": {"host": "claude", "active_host": "codex",
                               "installed_hosts": ["claude", "codex"]}}
        failures = [message for severity, message in profile_issues(profile) if severity == "FAIL"]
        self.assertTrue(any("정본이 모호" in message for message in failures))
        validated = validate_profile(profile, ".")
        self.assertTrue(any(severity == "FAIL" and "정본이 모호" in message
                            for severity, message in validated))

    def test_malformed_or_missing_active_membership_fails(self):
        cases = [
            {"installed_hosts": "both", "active_host": "claude"},
            {"installed_hosts": ["claude", "claude"], "active_host": "claude"},
            {"installed_hosts": ["claude"], "active_host": "codex"},
            {"installed_hosts": ["other"], "active_host": "claude"},
        ]
        for runtime in cases:
            with self.subTest(runtime=runtime):
                self.assertTrue(any(severity == "FAIL"
                                    for severity, _ in profile_issues({"runtime": runtime})))

    def test_double_host_cross_model_false_is_strong_warning_not_auto_enable(self):
        profile = {"runtime": {"installed_hosts": ["claude", "codex"], "active_host": "codex"},
                   "options": {"cross_model": False}}
        issues = profile_issues(profile)
        self.assertTrue(any(severity == "WARN" and "강하게 권장" in message
                            for severity, message in issues))
        result = reviewer_resolution(profile, {"claude": True, "codex": True})
        self.assertEqual("clean_context_same_runtime", result["reviewer_mode"])

    def test_receipt_tracks_actual_install_separately_from_profile_intent(self):
        profile = {"runtime": {"installed_hosts": ["claude", "codex"], "active_host": "codex"},
                   "options": {"cross_model": True}}
        one_host = {"host_runtime": "claude", "installed_hosts": ["claude"]}
        self.assertEqual(["claude"], receipt_hosts(one_host))
        issues = receipt_issues(profile, one_host)
        self.assertEqual(2, len(issues))
        both = {"host_runtime": "claude", "installed_hosts": ["claude", "codex"]}
        self.assertEqual([], receipt_issues(profile, both))

    def test_unknown_runtime_key_fails_without_jsonschema(self):
        issues = profile_issues({"runtime": {"active_hsot": "codex"}})
        self.assertTrue(any(severity == "FAIL" and "알 수 없는 키" in message
                            for severity, message in issues))


if __name__ == "__main__":
    unittest.main()
