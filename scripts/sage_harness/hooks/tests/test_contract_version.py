#!/usr/bin/env python3
"""contract_version_of 단위 (외부검토 R3/P1-3).

generate 가 manifest.adapter_contract_version 을 core.CONTRACT_VERSION 으로 스탬프하고
validate 가 대조 → core.decide() 인터페이스 계약 드리프트를 hash 와 별개로 잡는 두 번째 방어선.
이 헬퍼는 import 부작용 없이(정규식) 값을 읽어야 한다.
"""
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands._common import contract_version_of  # noqa: E402


def _core(d, body):
    p = os.path.join(d, "x_core.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    return p


class TestContractVersionOf(unittest.TestCase):
    def test_reads_double_quoted(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(contract_version_of(_core(d, 'CONTRACT_VERSION = "3"\n')), "3")

    def test_reads_single_quoted(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(contract_version_of(_core(d, "CONTRACT_VERSION = '7'\n")), "7")

    def test_missing_file_none(self):
        self.assertIsNone(contract_version_of("/tmp/sage-nonexistent-core-xyz.py"))

    def test_no_marker_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(contract_version_of(_core(d, "x = 1\n")))

    def test_no_import_side_effects(self):
        # 모듈 본문이 실행되면 RuntimeError. 정규식 읽기이므로 실행되지 않고 값만 반환해야 한다.
        with tempfile.TemporaryDirectory() as d:
            body = 'raise RuntimeError("must not execute")\nCONTRACT_VERSION = "1"\n'
            self.assertEqual(contract_version_of(_core(d, body)), "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
