#!/usr/bin/env python3
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)

from sage import model_routing as MR  # noqa: E402
from sage.profile_validate import severity_of, validate_profile  # noqa: E402


def _has(issues, severity, code, **arguments):
    """판정을 문구가 아니라 code·인자로 확인한다 — 문안은 catalog 소유다."""
    for sev, message in issues:
        if sev != severity or getattr(message, "code", None) != code:
            continue
        if all(message.arguments.get(name) == value for name, value in arguments.items()):
            return True
    return False


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

    def test_reviewer_host_cannot_be_the_declared_active_host(self):
        profile = self._profile()
        self.assertEqual(MR.reviewer_selection(profile), ("claude", "opus"))
        profile["cross_model"]["reviewer"]["host"] = "codex"   # = active_host
        issues = MR.profile_issues(profile)
        self.assertTrue(_has(issues, "FAIL", "routing.reviewer_host_is_active"))

    def test_reviewer_host_must_be_installed(self):
        # 설치되지 않은 runtime 을 리뷰어로 지정하면 실행 시점에 CLI 가 없어 BLOCKED 로 끝난다.
        # 이전에는 opposite 이기만 하면 통과해서 이 오설정이 정적 검사를 그냥 지나갔다.
        profile = self._profile()
        profile["runtime"] = {"installed_hosts": ["codex"], "active_host": "codex"}
        profile["cross_model"]["reviewer"]["host"] = "claude"
        issues = MR.profile_issues(profile)
        self.assertTrue(_has(issues, "FAIL", "routing.reviewer_host_not_installed"))

    def test_auto_active_host_leaves_reviewer_host_to_runtime(self):
        # auto 면 peer 가 실행 시점에만 정해지므로 정적으로 옳고 그름을 말할 수 없다 → 판정하지 않는다.
        profile = self._profile()
        profile["runtime"]["active_host"] = "auto"
        for host in ("claude", "codex"):
            profile["cross_model"]["reviewer"]["host"] = host
            issues = [msg for sev, msg in MR.profile_issues(profile) if sev == "FAIL"]
            self.assertEqual([], issues, host)

    def test_reviewer_requires_both_host_and_model(self):
        """host 는 중복이 아니다 — model id 가 런타임 종속이라 어느 peer 용인지 알아야 한다.

        (`gpt-5.6-terra` 는 codex, `opus` 는 claude. 실제 peer 가 달라지면 그 모델은 쓸 수 없다.)
        """
        profile = self._profile()
        profile["runtime"]["active_host"] = "auto"
        for partial in ({"model": "opus"}, {"host": "claude"}):
            profile["cross_model"]["reviewer"] = partial
            self.assertTrue(_has(MR.profile_issues(profile), "FAIL",
                                 "routing.reviewer_incomplete"), partial)

    def test_detected_host_is_never_its_own_reviewer(self):
        """감지가 성공하면 pin 과 무관하게 현재 host 를 제외한다 — 이게 10-b 의 본체다."""
        profile = self._profile()          # active_host: codex (pin)
        # pin 은 codex 인데 실제로는 claude 에서 돌고 있다 → 리뷰어는 claude 가 아니어야 한다.
        self.assertEqual(MR.reviewer_selection(profile, "claude")[0], "codex")
        # 반대 방향도 대칭.
        self.assertEqual(MR.reviewer_selection(profile, "codex")[0], "claude")

    def test_explicit_reviewer_host_is_dropped_when_it_is_the_running_host(self):
        profile = self._profile()
        profile["cross_model"]["reviewer"]["host"] = "claude"
        self.assertEqual(MR.reviewer_selection(profile, "codex")[0], "claude")   # 충돌 없음
        self.assertEqual(MR.reviewer_selection(profile, "claude")[0], "codex")   # 자기리뷰 → 무시

    def test_undetected_host_falls_back_to_profile(self):
        profile = self._profile()
        self.assertEqual(MR.reviewer_selection(profile, None)[0], "claude")      # opposite(codex)

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
        self.assertTrue(_has(issues, "WARN", "routing.runtime_models_no_active_choice",
                             label="frontend"))

    def test_cross_reviewer_config_while_cross_model_off_is_warning(self):
        profile = self._profile()
        profile["options"]["cross_model"] = False
        issues = MR.profile_issues(profile)
        self.assertTrue(_has(issues, "WARN", "routing.reviewer_set_but_disabled"))

    def test_cross_model_without_explicit_reviewer_warns_about_cli_default(self):
        for cross_value in (None, {"peer": "opposite_runtime"}):
            profile = self._profile()
            if cross_value is None:
                profile.pop("cross_model")
            else:
                profile["cross_model"] = cross_value
            issues = MR.profile_issues(profile)
            self.assertTrue(_has(issues, "WARN", "routing.reviewer_unselected"), cross_value)

    def test_catalog_status_distinguishes_confirmed_syntax_only_and_unknown(self):
        confirmed = {"verification": "cache-confirmed", "candidates": [{"id": "gpt-a"}]}
        syntax = {"verification": "syntax-only/account-unverified", "candidates": [{"id": "opus"}]}
        self.assertEqual(MR.catalog_status(confirmed, "gpt-a"), "confirmed")
        self.assertEqual(MR.catalog_status(syntax, "opus"), "syntax-only/account-unverified")
        self.assertEqual(MR.catalog_status(confirmed, "gpt-x"), "not-in-local-catalog")


if __name__ == "__main__":
    unittest.main(verbosity=2)
