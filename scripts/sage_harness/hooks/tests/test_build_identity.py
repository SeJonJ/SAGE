#!/usr/bin/env python3
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.build_identity import (_inventory, describe_content_drift,  # noqa: E402
                                 source_core_content_hash, source_core_content_snapshot,
                                 source_identity)


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


class TestContentDriftDiagnosis(unittest.TestCase):
    """EH-13: drift 가 "소스가 바뀌었다"에서 끝나지 않고 논리경로를 지목해야 한다."""

    def test_snapshot_aggregate_matches_published_hash(self):
        # 이 값은 설치된 프로젝트 manifest 에 박히므로 알고리즘이 흔들리면 전 소비자가
        # drift 로 오판된다. snapshot 도입이 그 계약을 바꾸지 않았음을 못박는다.
        aggregate, per_file = source_core_content_snapshot()
        self.assertEqual(aggregate, source_core_content_hash())
        self.assertEqual(set(per_file), {name for name, _path in _inventory()})
        for digest in per_file.values():
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_identical_snapshots_describe_nothing(self):
        _aggregate, per_file = source_core_content_snapshot()
        self.assertEqual(describe_content_drift(per_file, per_file), "")
        self.assertEqual(describe_content_drift({}, {}), "")

    def test_changed_added_removed_paths_are_named(self):
        before = {"engine/a.py": "0" * 64, "engine/gone.py": "1" * 64}
        after = {"engine/a.py": "2" * 64, "engine/new.py": "3" * 64}
        detail = describe_content_drift(before, after)
        self.assertIn("engine/a.py", detail)
        self.assertIn("engine/new.py", detail)
        self.assertIn("engine/gone.py", detail)
        self.assertIn("변경 1건", detail)
        self.assertIn("추가 1건", detail)
        self.assertIn("삭제 1건", detail)

    def test_long_lists_are_truncated_with_a_count(self):
        before = {f"engine/f{i}.py": "0" * 64 for i in range(9)}
        after = {f"engine/f{i}.py": "1" * 64 for i in range(9)}
        detail = describe_content_drift(before, after)
        self.assertIn("변경 9건", detail)
        self.assertIn("외 4건", detail)   # 5개만 나열하고 나머지는 건수로

    def test_missing_maps_are_tolerated(self):
        # 진단 경로가 원래 오류를 가리는 2차 예외를 내면 안 된다.
        self.assertEqual(describe_content_drift(None, None), "")
        self.assertIn("추가 1건", describe_content_drift(None, {"engine/a.py": "0" * 64}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
