#!/usr/bin/env python3
"""project hook runtime API 사전 호환성 — 순수 결정표.

이 판정이 존재하는 이유는 하나다. 소비 프로젝트의 새 hook core 가 아직 없는 `sage.*` 모듈을
import 하면, 옛 `sage-hook` 은 그걸 `ModuleNotFoundError` 로 만난다. traceback 은 host 에 따라
그냥 "hook 이 죽었다" 로 해석되고, 정책을 실행해야 할 게이트가 조용히 빠진다.

그래서 판정은 **파일이 아니라 manifest dict** 를 받는다. 결정표 전수를 파일시스템 없이 돌려야
사각지대가 남지 않는다.
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)

from sage.runtime_api import HOOK_RUNTIME_API, compatibility  # noqa: E402


def _manifest(**kw):
    base = {"sage_version": "1.0.0", "host_runtime": "codex", "assets": {}}
    base.update(kw)
    return base


class TestCurrentApi(unittest.TestCase):
    def test_first_api_is_one(self):
        self.assertEqual(HOOK_RUNTIME_API, 1)

    def test_api_is_a_plain_int_not_a_bool(self):
        # bool 은 int 의 서브클래스다. 상수가 True 로 흘러들면 비교가 조용히 성립한다.
        self.assertIs(type(HOOK_RUNTIME_API), int)


class TestCompatibleAndTooOld(unittest.TestCase):
    def test_equal_api_is_ok(self):
        status, _ = compatibility(_manifest(runtime_api={"required": HOOK_RUNTIME_API}))
        self.assertEqual(status, "ok")

    def test_older_requirement_is_ok(self):
        status, _ = compatibility(_manifest(runtime_api={"required": 1},
                                            generator_version="1.0.0"))
        self.assertEqual(status, "ok")

    def test_newer_requirement_is_too_old(self):
        status, evidence = compatibility(_manifest(runtime_api={"required": HOOK_RUNTIME_API + 1}))
        self.assertEqual(status, "too_old")
        self.assertEqual(evidence["required_api"], HOOK_RUNTIME_API + 1)
        self.assertEqual(evidence["current_api"], HOOK_RUNTIME_API)

    def test_the_comparison_is_required_versus_current(self):
        # 비교 자체가 사라지면(항상 ok) 이 테스트가 잡는다.
        for ahead in (1, 2, 99):
            with self.subTest(ahead=ahead):
                status, _ = compatibility(_manifest(runtime_api={"required": HOOK_RUNTIME_API + ahead}))
                self.assertEqual(status, "too_old")


class TestDamagedMarker(unittest.TestCase):
    def test_manifest_is_not_a_mapping(self):
        for value in (None, [], "", 3, True):
            with self.subTest(value=value):
                self.assertEqual(compatibility(value)[0], "damaged")

    def test_runtime_api_is_not_a_mapping(self):
        for value in (1, "1", [], None):
            with self.subTest(value=value):
                self.assertEqual(compatibility(_manifest(runtime_api=value))[0], "damaged")

    def test_required_is_missing(self):
        self.assertEqual(compatibility(_manifest(runtime_api={}))[0], "damaged")

    def test_required_is_not_a_positive_int(self):
        for value in (0, -1, 1.0, "1", None, [], {}):
            with self.subTest(value=value):
                self.assertEqual(compatibility(_manifest(runtime_api={"required": value}))[0],
                                 "damaged")

    def test_required_true_is_not_api_one(self):
        # True == 1 이므로 bool 을 걸러내지 않으면 `{"required": True}` 가 ok 로 통과한다.
        self.assertEqual(compatibility(_manifest(runtime_api={"required": True}))[0], "damaged")


class TestLegacy(unittest.TestCase):
    """marker 부재는 그 자체로 legacy 가 아니다.

    부재를 먼저 legacy 로 처리하면, marker 와 version 을 함께 지운 downgrade 가 통과한다.
    legacy 는 **적극적으로 증명**돼야 한다 — 유효한 SemVer 이고 major 가 0 일 때만.
    """

    def test_generator_major_zero_without_marker_is_legacy(self):
        for version in ("0.9.84", "0.1.0", "0.0.1"):
            with self.subTest(version=version):
                self.assertEqual(compatibility(_manifest(generator_version=version))[0], "legacy")

    def test_generator_major_one_without_marker_is_damaged(self):
        # 1.0 manifest 인데 marker 가 없다 → 손상이다. legacy 로 낮추지 않는다.
        for version in ("1.0.0", "1.1.0", "2.0.0"):
            with self.subTest(version=version):
                self.assertEqual(compatibility(_manifest(generator_version=version))[0], "damaged")

    def test_missing_generator_version_without_marker_is_damaged(self):
        self.assertEqual(compatibility(_manifest())[0], "damaged")

    def test_damaged_generator_version_without_marker_is_damaged(self):
        for version in ("", "abc", "0", "0.9", None, 0, [], "v0.9.84"):
            with self.subTest(version=version):
                self.assertEqual(compatibility(_manifest(generator_version=version))[0], "damaged")

    def test_a_marker_wins_over_a_legacy_looking_version(self):
        # marker 가 있으면 version 은 legacy 판정에 관여하지 않는다.
        status, _ = compatibility(_manifest(runtime_api={"required": HOOK_RUNTIME_API + 1},
                                            generator_version="0.9.84"))
        self.assertEqual(status, "too_old")


class TestEvidence(unittest.TestCase):
    def test_evidence_is_json_scalars_only(self):
        for manifest in (_manifest(runtime_api={"required": 9}),
                         _manifest(generator_version="0.9.84"),
                         _manifest()):
            with self.subTest(manifest=manifest):
                _, evidence = compatibility(manifest)
                self.assertIsInstance(evidence, dict)
                for key, value in evidence.items():
                    self.assertIsInstance(key, str)
                    self.assertIsInstance(value, (int, str, type(None)))

    def test_evidence_carries_no_paths(self):
        _, evidence = compatibility(_manifest(runtime_api={"required": 9}))
        for value in evidence.values():
            if isinstance(value, str):
                self.assertNotIn("/", value)


class TestRunAllRegistration(unittest.TestCase):
    def test_this_suite_is_wired(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run-all.sh"),
                  encoding="utf-8") as fh:
            self.assertIn("test_runtime_api.py", fh.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
