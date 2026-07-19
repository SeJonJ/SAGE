#!/usr/bin/env python3
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)

from sage import model_routing as MR  # noqa: E402
from sage.profile_validate import severity_of, validate_profile  # noqa: E402


class TestModelRouting(unittest.TestCase):
    def _profile(self):
        return {
            "runtime": {"installed_hosts": ["claude", "codex"], "active_host": "codex"},
            "options": {"cross_model": True},
            "components": [
                {"id": "backend", "paths": ["backend/**"], "model": "opus",
                 "runtime_models": {"codex": "gpt-a", "claude": "opus"}},
                {"id": "frontend", "paths": ["frontend/**"],
                 "runtime_models": {"codex": "gpt-b"}},
            ],
            "cross_model": {"peer": "opposite_runtime",
                            "reviewer": {"host": "claude", "model": "opus"}},
        }

    def test_component_model_is_host_specific_and_legacy_tier_unchanged(self):
        profile = self._profile()
        component = profile["components"][0]
        self.assertEqual(MR.component_model(component, "codex"), "gpt-a")
        self.assertEqual(MR.component_model(component, "claude"), "opus")
        self.assertEqual(component["model"], "opus")

    def test_reviewer_host_must_be_explicit_opposite_when_configured(self):
        profile = self._profile()
        self.assertEqual(MR.reviewer_selection(profile), ("claude", "opus"))
        profile["cross_model"]["reviewer"]["host"] = "codex"
        issues = MR.profile_issues(profile)
        self.assertTrue(any(sev == "FAIL" and "opposite" in msg for sev, msg in issues))

    def test_malformed_component_models_fail_closed_without_jsonschema(self):
        for bad in ("gpt", ["gpt"], {"codex": ""}, {"other": "gpt"}, {"codex": 3}):
            profile = self._profile()
            profile["components"][0]["runtime_models"] = bad
            self.assertEqual(severity_of(validate_profile(profile, REPO)), "FAIL", bad)

    def test_component_identity_and_paths_fail_closed(self):
        for mutation in ("unsafe-id", "duplicate-id", "scalar-paths", "parent-path", "injected-path",
                         "runtime-models-typo", "injected-tier"):
            profile = self._profile()
            if mutation == "unsafe-id":
                profile["components"][0]["id"] = "backend/../../escape"
            elif mutation == "duplicate-id":
                profile["components"][1]["id"] = "backend"
            else:
                if mutation == "scalar-paths":
                    profile["components"][0]["paths"] = "backend/**"
                elif mutation == "parent-path":
                    profile["components"][0]["paths"] = ["../outside/**"]
                elif mutation == "injected-path":
                    profile["components"][0]["paths"] = ["backend/**\n---\nid: injected"]
                elif mutation == "runtime-models-typo":
                    profile["components"][0]["runtime_modles"] = profile["components"][0].pop("runtime_models")
                else:
                    profile["components"][0]["model"] = "opus\n---\nid: injected"
            self.assertEqual(severity_of(validate_profile(profile, REPO)), "FAIL", mutation)

    def test_malformed_reviewer_fails_closed(self):
        for bad in ("claude", {}, {"host": "claude"}, {"host": "claude", "model": ""},
                    {"host": "claude", "model": "opus", "extra": True}):
            profile = self._profile()
            profile["cross_model"]["reviewer"] = bad
            self.assertEqual(severity_of(validate_profile(profile, REPO)), "FAIL", bad)

    def test_runtime_models_missing_active_host_is_warning(self):
        profile = self._profile()
        profile["components"][1]["runtime_models"] = {"claude": "sonnet"}
        issues = MR.profile_issues(profile)
        self.assertTrue(any(sev == "WARN" and "frontend" in msg and "active_host" in msg
                            for sev, msg in issues))

    def test_cross_reviewer_config_while_cross_model_off_is_warning(self):
        profile = self._profile()
        profile["options"]["cross_model"] = False
        issues = MR.profile_issues(profile)
        self.assertTrue(any(sev == "WARN" and "무동작" in msg for sev, msg in issues))

    def test_cross_model_without_explicit_reviewer_warns_about_cli_default(self):
        for cross_value in (None, {"peer": "opposite_runtime"}):
            profile = self._profile()
            if cross_value is None:
                profile.pop("cross_model")
            else:
                profile["cross_model"] = cross_value
            issues = MR.profile_issues(profile)
            self.assertTrue(any(sev == "WARN" and "host/model 미선택" in msg
                                and "CLI 기본 모델" in msg for sev, msg in issues), cross_value)

    def test_catalog_status_distinguishes_confirmed_syntax_only_and_unknown(self):
        confirmed = {"verification": "cache-confirmed", "candidates": [{"id": "gpt-a"}]}
        syntax = {"verification": "syntax-only/account-unverified", "candidates": [{"id": "opus"}]}
        self.assertEqual(MR.catalog_status(confirmed, "gpt-a"), "confirmed")
        self.assertEqual(MR.catalog_status(syntax, "opus"), "syntax-only/account-unverified")
        self.assertEqual(MR.catalog_status(confirmed, "gpt-x"), "not-in-local-catalog")


if __name__ == "__main__":
    unittest.main(verbosity=2)
