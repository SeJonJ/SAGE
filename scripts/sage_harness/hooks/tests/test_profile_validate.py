#!/usr/bin/env python3
"""profile_validate 단위 (외부검토 R2/P0-2 — 게이트 침묵 비활성 차단).

핵심 teeth: `l3_filename_globs`→`l3_filename_glob` 오타가 schema(additionalProperties:false)로 FAIL.
+ 의미검증(전략 모듈 부재·미정의 phase 참조 FAIL / 위험 글롭 전무 INFO).
schema 검증은 jsonschema 선택의존 — 미설치면 schema 의존 테스트 skip(의미검증은 항상 동작).
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.profile_validate import severity_of, validate_profile  # noqa: E402

try:
    import jsonschema  # noqa: F401
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


def sevs(profile):
    return validate_profile(profile, REPO)   # REPO 에 schema/ 와 strategies/ 존재


@unittest.skipUnless(_HAS_JSONSCHEMA, "jsonschema 미설치 — schema 검증 skip")
class TestProfileSchema(unittest.TestCase):
    def test_clean_profile_no_fail(self):
        prof = {"risk": {"l3_filename_globs": ["*secret*"], "l3_review_strategy": "claude_grep_first"},
                "pdca": {"phases": [{"id": "00", "glob": "x"}], "pre_implementation_required": {"L3": ["00"]}}}
        self.assertNotIn("FAIL", [s for s, _ in sevs(prof)])

    def test_singular_typo_in_risk_is_fail(self):
        # P0-2 핵심 시나리오: 단수 오타 → core 가 조용히 빈 리스트 → L3 침묵 비활성. schema 가 적발.
        issues = sevs({"risk": {"l3_filename_glob": ["*secret*"]}})
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("l3_filename_glob" in m for _, m in issues))

    def test_top_level_typo_is_fail(self):
        self.assertEqual(severity_of(sevs({"file_type_maps": []})), "FAIL")   # file_type_map 오타


class TestProfileSemantic(unittest.TestCase):
    def test_missing_strategy_module_fail(self):
        prof = {"risk": {"l3_review_strategy": "no_such_strategy_xyz", "l3_filename_globs": ["*x*"]}}
        issues = sevs(prof)
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("no_such_strategy_xyz" in m for _, m in issues))

    def test_existing_strategy_module_ok(self):
        prof = {"risk": {"l3_review_strategy": "claude_grep_first", "l3_filename_globs": ["*x*"]}}
        self.assertNotIn("FAIL", [s for s, _ in sevs(prof)])

    def test_undefined_phase_ref_fail(self):
        prof = {"pdca": {"phases": [{"id": "00", "glob": "x"}],
                         "pre_implementation_required": {"L2": ["00", "99"]}},
                "risk": {"l2_path_globs": ["*x*"]}}
        issues = sevs(prof)
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("99" in m for _, m in issues))

    def test_all_empty_globs_is_info(self):
        # 위험 글롭 전무 → INFO(의도일 수 있음). FAIL/WARN 아님.
        self.assertEqual(severity_of(sevs({"risk": {}})), "INFO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
