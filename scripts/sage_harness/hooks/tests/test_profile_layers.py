import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import yaml

from sage.profile_layers import (
    cross_model_enabled,
    cross_model_policy,
    effective_profile,
    load_profile_layers,
    local_profile_git_issues,
    profile_layer_issues,
)
from sage.profile_validate import validate_profile


REPO = Path(__file__).resolve().parents[4]


class ProfileLayerContractTests(unittest.TestCase):
    def setUp(self):
        self.shared = {
            "project": {"name": "demo"},
            "options": {"cross_model": False, "obsidian": "optional"},
            "components": [{"id": "backend", "paths": ["src/**"]}],
            "risk": {"l2_path_globs": ["src/**"]},
            "runtime": {"host": "codex"},
            "cross_model": {"policy": "recommended"},
            "knowledge_capture": {"provider": "obsidian", "vault_path": ""},
        }

    def test_recommended_defaults_on_and_local_can_opt_out(self):
        self.assertEqual("recommended", cross_model_policy(self.shared))
        self.assertTrue(cross_model_enabled(self.shared, None))

        local = {"cross_model": {"enabled": False}}
        self.assertFalse(cross_model_enabled(self.shared, local))
        effective = effective_profile(self.shared, local)
        self.assertFalse(effective["options"]["cross_model"])
        self.assertEqual("recommended", effective["cross_model"]["policy"])

    def test_required_local_false_is_fail_and_cannot_weaken_effective(self):
        self.shared["cross_model"]["policy"] = "required"
        local = {"cross_model": {"enabled": False}}

        issues = profile_layer_issues(self.shared, local)
        self.assertIn(
            ("FAIL", "cross_model.policy=required는 local cross_model.enabled=false로 완화할 수 없음"),
            issues,
        )
        self.assertTrue(cross_model_enabled(self.shared, local))
        self.assertTrue(effective_profile(self.shared, local)["options"]["cross_model"])

    def test_off_policy_ignores_local_enable_and_legacy_bool_stays_compatible(self):
        self.shared["cross_model"]["policy"] = "off"
        self.assertFalse(cross_model_enabled(self.shared, {"cross_model": {"enabled": True}}))

        legacy = {"options": {"cross_model": True}}
        self.assertIsNone(cross_model_policy(legacy))
        self.assertTrue(cross_model_enabled(legacy, None))
        self.assertFalse(cross_model_enabled(legacy, {"cross_model": {"enabled": False}}))

    def test_only_capability_allowlist_is_accepted(self):
        local = {
            "runtime": {"installed_hosts": ["claude", "codex"]},
            "capabilities": {"claude": True, "codex": True},
            "cross_model": {"enabled": False},
            "knowledge_capture": {
                "enabled": True,
                "vault_path": "/tmp/private-vault",
            },
            "models": {
                "available": {
                    "claude": ["claude-opus-4"],
                    "codex": ["gpt-5.6-sol"],
                }
            },
        }
        self.assertEqual([], profile_layer_issues(self.shared, local))

        effective = effective_profile(self.shared, local)
        self.assertEqual(["claude", "codex"], effective["runtime"]["installed_hosts"])
        self.assertEqual({"claude": True, "codex": True}, effective["capabilities"])
        self.assertEqual("/tmp/private-vault", effective["knowledge_capture"]["vault_path"])
        self.assertTrue(effective["knowledge_capture"]["enabled"])
        self.assertNotIn("models", effective)
        self.assertEqual("", self.shared["knowledge_capture"]["vault_path"])

    def test_policy_owned_and_unknown_local_keys_fail_closed(self):
        cases = [
            ({"risk": {"l3_filename_globs": ["**"]}}, "local의 알 수 없는 최상위 키: ['risk']"),
            ({"runtime": {"active_host": "claude"}}, "local runtime의 알 수 없는 키: ['active_host']"),
            ({"cross_model": {"policy": "off"}}, "local cross_model의 알 수 없는 키: ['policy']"),
            ({"knowledge_capture": {"provider": "none"}}, "local knowledge_capture의 알 수 없는 키: ['provider']"),
            ({"capabilities": {"gstack": True}}, "local capabilities의 알 수 없는 키: ['gstack']"),
        ]
        for local, expected in cases:
            with self.subTest(local=local):
                self.assertIn(("FAIL", expected), profile_layer_issues(self.shared, local))

    def test_malformed_local_types_fail_without_coercion(self):
        cases = [
            ({"runtime": {"installed_hosts": "codex"}}, "local runtime.installed_hosts는 non-empty unique host 배열이어야 함"),
            ({"cross_model": {"enabled": "false"}}, "local cross_model.enabled는 boolean이어야 함"),
            ({"knowledge_capture": {"enabled": 1}}, "local knowledge_capture.enabled는 boolean이어야 함"),
            ({"knowledge_capture": {"vault_path": ""}}, "local knowledge_capture.vault_path는 유효한 non-empty 문자열이어야 함"),
            ({"models": {"available": {"codex": "gpt"}}}, "local models.available.codex는 non-empty model id 배열이어야 함"),
        ]
        for local, expected in cases:
            with self.subTest(local=local):
                self.assertIn(("FAIL", expected), profile_layer_issues(self.shared, local))


class ProfileLayerLoadingTests(unittest.TestCase):
    def test_loads_shared_and_optional_local_with_distinct_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            sage_dir = Path(tmp, "sage")
            sage_dir.mkdir()
            shared_path = sage_dir / "project-profile.yaml"
            local_path = sage_dir / "project-profile.local.yaml"
            shared_path.write_text(
                yaml.safe_dump({
                    "project": {"name": "demo"},
                    "options": {"cross_model": False},
                    "cross_model": {"policy": "recommended"},
                }),
                encoding="utf-8",
            )
            local_path.write_text(
                yaml.safe_dump({"cross_model": {"enabled": False}}),
                encoding="utf-8",
            )

            layers = load_profile_layers(str(shared_path))

            self.assertEqual(os.path.realpath(shared_path), layers.shared_path)
            self.assertEqual(os.path.realpath(local_path), layers.local_path)
            self.assertFalse(layers.effective["options"]["cross_model"])
            self.assertEqual([], layers.issues)

    def test_missing_local_is_valid_but_malformed_local_is_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            sage_dir = Path(tmp, "sage")
            sage_dir.mkdir()
            shared_path = sage_dir / "project-profile.yaml"
            shared_path.write_text("project:\n  name: demo\n", encoding="utf-8")

            layers = load_profile_layers(str(shared_path))
            self.assertIsNone(layers.local)
            self.assertEqual([], layers.issues)

            local_path = sage_dir / "project-profile.local.yaml"
            local_path.write_text("cross_model: [", encoding="utf-8")
            broken = load_profile_layers(str(shared_path))
            self.assertTrue(any(severity == "FAIL" and "local profile YAML 파싱 오류" in message
                                for severity, message in broken.issues))

    def test_local_values_never_appear_in_shared_materialization(self):
        shared = {"project": {"name": "demo"}, "options": {"cross_model": True}}
        local = {
            "knowledge_capture": {"enabled": True, "vault_path": "/Users/me/private"},
            "cross_model": {"enabled": False},
        }
        effective = effective_profile(shared, local)
        self.assertNotIn("knowledge_capture", shared)
        self.assertNotEqual(shared, effective)
        self.assertNotIn("/Users/me/private", yaml.safe_dump(shared))

    def test_local_profile_git_diagnostics_cover_non_git_unignored_and_tracked(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp, "sage", "project-profile.local.yaml")
            local.parent.mkdir()
            local.write_text("cross_model: { enabled: false }\n", encoding="utf-8")

            self.assertEqual(
                [("INFO", "local profile Git 점검 N/A (Git 저장소 아님)")],
                local_profile_git_issues(tmp, str(local)),
            )

            subprocess.run(["git", "init", "-q", tmp], check=True)
            issues = local_profile_git_issues(tmp, str(local))
            self.assertTrue(any(severity == "WARN" and "ignore되지 않음" in message
                                for severity, message in issues), issues)

            subprocess.run(["git", "-C", tmp, "add", "-f", "sage/project-profile.local.yaml"],
                           check=True)
            tracked = local_profile_git_issues(tmp, str(local))
            self.assertTrue(any(severity == "WARN" and "Git에 추적됨" in message
                                for severity, message in tracked), tracked)

    def test_local_profile_git_diagnostics_normalize_status_probe_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp, "sage", "project-profile.local.yaml")
            local.parent.mkdir()
            local.write_text("cross_model: { enabled: false }\n", encoding="utf-8")
            root_probe = subprocess.CompletedProcess(
                args=["git"], returncode=0, stdout=f"{tmp}\n", stderr=""
            )
            with mock.patch(
                "sage.profile_layers.subprocess.run",
                side_effect=[root_probe, subprocess.TimeoutExpired(["git", "ls-files"], 5)],
            ):
                issues = local_profile_git_issues(tmp, str(local))

            self.assertTrue(any(severity == "WARN" and "Git 추적 상태 점검 실패" in message
                                for severity, message in issues), issues)


class ProfileLayerSchemaTests(unittest.TestCase):
    def test_shared_policy_is_accepted_by_semantic_validator(self):
        for policy in ("required", "recommended", "off"):
            with self.subTest(policy=policy):
                issues = validate_profile({"cross_model": {"policy": policy}}, str(REPO))
                self.assertFalse(any(severity == "FAIL" for severity, _ in issues), issues)

        issues = validate_profile({"cross_model": {"policy": "optional"}}, str(REPO))
        self.assertTrue(any(severity == "FAIL" and "cross_model.policy" in message
                            for severity, message in issues), issues)

    def test_local_schema_is_closed_and_matches_manual_contract(self):
        schema_path = REPO / "schema" / "profile.local.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            {"runtime", "capabilities", "cross_model", "knowledge_capture", "models"},
            set(schema["properties"]),
        )
        for section in schema["properties"].values():
            self.assertFalse(section["additionalProperties"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
