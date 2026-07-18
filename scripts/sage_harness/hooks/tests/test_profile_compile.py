#!/usr/bin/env python3
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.profile_compile import ProfileCompileError, materialize_profile  # noqa: E402


class TestProfileCompile(unittest.TestCase):
    def test_domains_materialize_and_highest_risk_wins(self):
        source = {"risk": {
            "l0_pass_globs": ["docs/**"],
            "l1_path_globs": ["shared/**", "ui/**"],
            "l2_path_globs": ["shared/**"],
            "l3_filename_globs": [],
            "l2_content_keywords": ["credential"],
            "l3_content_keywords": [],
            "domains": [
                {"id": "auth", "risk_level": "L3", "path_globs": ["shared/**"],
                 "content_keywords": ["credential"]},
            ],
        }}
        compiled = materialize_profile(source)
        risk = compiled["risk"]
        self.assertEqual(risk["l3_filename_globs"], ["shared/**"])
        self.assertEqual(risk["l2_path_globs"], [])
        self.assertEqual(risk["l1_path_globs"], ["ui/**"])
        self.assertEqual(risk["l3_content_keywords"], ["credential"])
        self.assertEqual(risk["l2_content_keywords"], [])
        self.assertEqual(risk["l0_pass_globs"], ["docs/**"])
        self.assertEqual(risk["l0_exclude_globs"], ["shared/**"])
        self.assertEqual(source["risk"]["l1_path_globs"], ["shared/**", "ui/**"])

    def test_domain_paths_materialize_as_l0_exclusions_without_mutating_source(self):
        source = {"risk": {
            "l0_pass_globs": ["**/*.png"],
            "domains": [
                {"id": "game", "risk_level": "L3", "path_globs": ["assets/game/**"],
                 "protocol_pointer": "sage/game.md"},
                {"id": "media", "risk_level": "L2", "path_globs": ["assets/media/**"],
                 "protocol_pointer": "sage/media.md"},
            ],
        }}
        compiled = materialize_profile(source)
        self.assertEqual(compiled["risk"]["l0_exclude_globs"], ["assets/game/**", "assets/media/**"])
        self.assertNotIn("l0_exclude_globs", source["risk"])

    def test_top_level_trigger_fields_reject_scalar_and_null_before_coercion(self):
        fields = (
            "l0_pass_globs", "l0_exclude_globs", "l1_path_globs", "l2_path_globs", "l3_filename_globs",
            "l2_content_keywords", "l3_content_keywords",
        )
        for field in fields:
            for bad in ("auth", None, 3, True):
                with self.subTest(field=field, bad=bad), self.assertRaises(ProfileCompileError) as ctx:
                    materialize_profile({"risk": {field: bad}})
                self.assertIn(f"risk.{field}", str(ctx.exception))

    def test_trigger_lists_reject_non_string_and_blank_items(self):
        for bad in (["ok", 3], ["ok", True], ["ok", ""], ["ok", "   "]):
            with self.subTest(bad=bad), self.assertRaises(ProfileCompileError) as ctx:
                materialize_profile({"risk": {"l3_filename_globs": bad}})
            self.assertIn("risk.l3_filename_globs", str(ctx.exception))

    def test_domain_trigger_fields_use_same_raw_contract(self):
        base = {"id": "auth", "risk_level": "L3", "path_globs": ["auth/**"],
                "content_keywords": ["token"], "protocol_pointer": "sage/auth.md"}
        for field, bad in (("path_globs", "auth/**"), ("content_keywords", "token"),
                           ("path_globs", ["ok", 1]), ("content_keywords", None)):
            domain = dict(base)
            domain[field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ProfileCompileError) as ctx:
                materialize_profile({"risk": {"domains": [domain]}})
                self.assertIn(f"risk.domains[0].{field}", str(ctx.exception))

    def test_domain_risk_level_rejects_unknown_or_missing_values(self):
        for bad in ("L0", "l3", "", None, 3):
            with self.subTest(bad=bad):
                domain = {"id": "auth", "path_globs": ["auth/**"]}
                if bad is not None:
                    domain["risk_level"] = bad
                with self.assertRaises(ProfileCompileError) as ctx:
                    materialize_profile({"risk": {"domains": [domain]}})
                self.assertIn("risk.domains[0].risk_level", str(ctx.exception))

    def test_missing_domain_trigger_fields_remain_optional(self):
        domain = {"id": "auth", "risk_level": "L3", "content_keywords": ["token"],
                  "protocol_pointer": "sage/auth.md"}
        compiled = materialize_profile({"risk": {"domains": [domain]}})
        self.assertEqual(compiled["risk"]["l3_filename_globs"], [])
        self.assertEqual(compiled["risk"]["l3_content_keywords"], ["token"])

    def test_invalid_profile_is_not_mutated(self):
        source = {"risk": {"l3_filename_globs": "auth"}}
        with self.assertRaises(ProfileCompileError):
            materialize_profile(source)
        self.assertEqual(source, {"risk": {"l3_filename_globs": "auth"}})


if __name__ == "__main__":
    unittest.main(verbosity=2)
