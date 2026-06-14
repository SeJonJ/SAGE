#!/usr/bin/env python3
"""sage doctor 검증 (중 등급 — profile 로드 실패 원인 구분, Codex P1).

parse_error(설정 무시됨) = FAIL(exit 1) / missing_file·missing_pyyaml = WARN/INFO(exit 0).
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import doctor  # noqa: E402

try:
    import yaml  # noqa: F401
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


class Args:
    def __init__(self, profile=None):
        self.profile = profile


def run_doctor(profile_path):
    out = io.StringIO()
    with redirect_stdout(out):
        rc = doctor.run(Args(profile=profile_path))
    return rc, out.getvalue()


class TestDoctor(unittest.TestCase):
    def test_load_profile_missing_file(self):
        self.assertEqual(doctor._load_profile("/no/such/profile.yaml")[1], "missing_file")

    def test_missing_file_exit0(self):
        rc, out = run_doctor("/no/such/profile.yaml")
        self.assertEqual(rc, 0)
        self.assertIn("profile 없음", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요(parse 단계 도달)")
    def test_parse_error_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.yaml")
            Path(p).write_text("risk:\n  globs: [unclosed\n")   # 잘못된 flow sequence
            rc, out = run_doctor(p)
            self.assertEqual(rc, 1)            # 설정이 깨졌으면 FAIL
            self.assertIn("파싱 오류", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_ok_profile_exit0(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.yaml")
            Path(p).write_text("runtime: { host: codex }\noptions: { cross_model: false }\n")
            rc, out = run_doctor(p)
            self.assertEqual(rc, 0)
            self.assertEqual(doctor._load_profile(p)[1], "ok")


if __name__ == "__main__":
    unittest.main(verbosity=2)
