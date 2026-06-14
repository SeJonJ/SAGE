#!/usr/bin/env python3
"""validate 안전성 검증 (audit 4회차 P1-1: 오염 manifest test 경로 임의 실행 차단)."""
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands.validate import _safe_test_path, _schema_check, _validate_interpretive  # noqa: E402

ROOT = REPO  # sage_project (실제 구조 사용)

try:
    import jsonschema  # noqa: F401
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


class TestSafeTestPath(unittest.TestCase):
    def test_reject_absolute(self):
        self.assertIsNone(_safe_test_path(ROOT, "/tmp/payload.sh"))

    def test_reject_parent_traversal(self):
        self.assertIsNone(_safe_test_path(ROOT, "../../payload.py"))

    def test_reject_outside_scripts(self):
        # root 내부지만 scripts/sage_harness 밖 → 거부
        self.assertIsNone(_safe_test_path(ROOT, "sage/cli.py"))

    def test_reject_bad_extension(self):
        self.assertIsNone(_safe_test_path(ROOT, "scripts/sage_harness/hooks/tests/cases.tsv"))

    def test_accept_valid(self):
        p = _safe_test_path(ROOT, "scripts/sage_harness/hooks/tests/test_conformance.py")
        self.assertIsNotNone(p)
        self.assertTrue(p.endswith("test_conformance.py"))

    def test_reject_missing(self):
        self.assertIsNone(_safe_test_path(ROOT, "scripts/sage_harness/hooks/tests/nope.py"))


class TestSchemaCheck(unittest.TestCase):
    """sage validate --schema (manifest JSON Schema 구조검증)."""
    def test_no_jsonschema_warns(self):
        # jsonschema 미설치 환경: WARN(skip) — 결정론적 검증 불가하므로 설치 시에만 PASS/FAIL 단정
        if _HAS_JSONSCHEMA:
            self.skipTest("jsonschema 설치됨")
        with tempfile.TemporaryDirectory() as d:
            sev, _ = _schema_check(d, {"sage_version": "0.1.0", "host_runtime": "claude", "assets": {}})
            self.assertEqual(sev, "WARN")

    @unittest.skipUnless(_HAS_JSONSCHEMA, "jsonschema 필요")
    def test_valid_manifest_pass(self):
        # root/schema 없으면 _resources(SAGE 번들) schema 사용
        with tempfile.TemporaryDirectory() as d:
            m = {"sage_version": "0.1.0", "host_runtime": "claude",
                 "assets": {"hooks/x": {"conformance": "PASS", "form": "native"}}}
            self.assertEqual(_schema_check(d, m)[0], "PASS")

    @unittest.skipUnless(_HAS_JSONSCHEMA, "jsonschema 필요")
    def test_invalid_manifest_fail(self):
        with tempfile.TemporaryDirectory() as d:
            m = {"sage_version": "0.1.0", "host_runtime": "claude",
                 "assets": {"hooks/x": {"conformance": "BOGUS", "form": "native"}}}  # enum 위반
            self.assertEqual(_schema_check(d, m)[0], "FAIL")


class TestDescriptiveUnresolved(unittest.TestCase):
    """descriptive unresolved(비게이팅) 가 INFO 로 가시화되되 severity 는 안 올리는지."""
    def test_info_surfaced_not_gating(self):
        with tempfile.TemporaryDirectory() as d:
            sk = os.path.join(d, "docs", "sage_harness", "skills")
            os.makedirs(sk)
            open(os.path.join(sk, "x.md"), "w").write("# x\n")
            open(os.path.join(sk, "x.claims.yml"), "w").write(
                'required_claims:\n'
                '  - { type: procedure_step, value: "a", confidence: unresolved }\n'
                '  - { type: procedure_step, value: "b", confidence: unresolved }\n'
                'forbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n')
            entry = {"form": "interpretive", "unresolved": []}
            sev, msgs = _validate_interpretive(d, "skills/x", entry, run_regression=False)
            self.assertTrue(any("descriptive unresolved 2건" in m for m in msgs))
            self.assertEqual(sev, "PASS")   # INFO 는 게이팅 아님


if __name__ == "__main__":
    unittest.main(verbosity=2)
