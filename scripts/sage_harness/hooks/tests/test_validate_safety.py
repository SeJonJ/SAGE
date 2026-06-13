#!/usr/bin/env python3
"""validate 안전성 검증 (audit 4회차 P1-1: 오염 manifest test 경로 임의 실행 차단)."""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands.validate import _safe_test_path  # noqa: E402

ROOT = REPO  # sage_project (실제 구조 사용)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
