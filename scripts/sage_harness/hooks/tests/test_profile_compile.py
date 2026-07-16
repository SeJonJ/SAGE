#!/usr/bin/env python3
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.profile_compile import materialize_profile  # noqa: E402


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
        self.assertEqual(source["risk"]["l1_path_globs"], ["shared/**", "ui/**"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
