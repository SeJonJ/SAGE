#!/usr/bin/env python3
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.build_identity import _inventory, source_core_content_hash, source_identity  # noqa: E402


class TestBuildIdentity(unittest.TestCase):
    def test_source_hash_is_stable_sha256(self):
        first = source_core_content_hash()
        self.assertRegex(first, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(first, source_core_content_hash())

    def test_install_identity_uses_same_source_and_installed_stamp(self):
        identity = source_identity()
        self.assertEqual(identity["source_core_content_hash"],
                         identity["installed_core_content_hash"])
        self.assertIsInstance(identity["dirty_flag"], bool)
        self.assertTrue(identity["sage_source_commit"])

    def test_inventory_covers_governance_engine_code(self):
        logical = {name for name, _path in _inventory()}
        self.assertIn("engine/hook_entry.py", logical)
        self.assertIn("engine/commands/validate.py", logical)
        self.assertIn("engine/profile_validate.py", logical)
        self.assertIn("engine/overlay_materialize.py", logical)
        self.assertIn("templates/agent.spec.md", logical)
        self.assertIn("templates/hook.spec.md", logical)
        self.assertIn("templates/skill.spec.md", logical)
        self.assertIn("templates/claims.yml", logical)
        self.assertIn("templates/project-profile.yaml", logical)


if __name__ == "__main__":
    unittest.main(verbosity=2)
