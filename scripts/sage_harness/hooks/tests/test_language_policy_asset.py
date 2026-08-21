#!/usr/bin/env python3
"""managed language policy 문서의 4경로 계약 — 정본·설치본·영수증·논리경로.

이 문서는 저장소 설명서가 아니라 소비 프로젝트로 배포되는 managed CORE 자산이다. 그래서 파일만
있으면 되는 게 아니라 install 이 설치본을 만들고, manifest 가 영수증을 남기고, build identity 가
논리경로로 잡아야 EH-13 drift 진단이 이 문서의 변경·삭제·설치누락을 볼 수 있다. 네 축 중 하나만
빠져도 나머지가 조용히 통과하므로 함께 고정한다.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from sage.build_identity import source_core_content_snapshot  # noqa: E402
from sage.commands.install import _valid_core_receipt  # noqa: E402
from sage import overlay_materialize as _mat  # noqa: E402

SOURCE = REPO / "templates/core/framework/docs/agent/language-policy.md"
INSTALLED_REL = Path("docs/agent/language-policy.md")
LOGICAL = "core/framework/docs/agent/language-policy.md"
ANCHOR = "shared/framework-doc/docs/agent/language-policy"


def _install(dest, force=False):
    cmd = [sys.executable, "-m", "sage", "install", "--host", "claude", "--dest", dest]
    if force:
        cmd.append("--force")
    env = dict(os.environ, PYTHONPATH=str(REPO))
    return subprocess.run(cmd, capture_output=True, text=True, input="", env=env, cwd=str(REPO))


class TestLanguagePolicyAsset(unittest.TestCase):
    def test_engine_canonical_source_exists(self):
        self.assertTrue(SOURCE.is_file(), f"엔진 정본이 없음: {SOURCE}")
        self.assertTrue(SOURCE.read_text(encoding="utf-8").strip())

    def test_logical_path_joins_build_identity(self):
        """EH-13 aggregate 에 참여하지 않으면 정본 변경이 drift 로 보이지 않는다."""
        _, paths = source_core_content_snapshot()
        self.assertIn(LOGICAL, paths)

    def test_install_deploys_render_and_receipt(self):
        with tempfile.TemporaryDirectory() as dest:
            self.assertEqual(_install(dest).returncode, 0)
            self.assertEqual(_install(dest, force=True).returncode, 0)

            installed = Path(dest) / INSTALLED_REL
            self.assertTrue(installed.is_file(), "소비자 설치본이 없음")
            self.assertEqual(installed.read_text(encoding="utf-8"),
                             SOURCE.read_text(encoding="utf-8"))

            manifest = json.loads(
                (Path(dest) / "docs/sage_harness/.manifest.json").read_text(encoding="utf-8"))
            receipt = manifest.get("core_renders", {}).get(ANCHOR)
            self.assertIsNotNone(receipt, f"영수증 키가 없음: {ANCHOR}")
            self.assertEqual(receipt["semantic_source"], LOGICAL)
            self.assertTrue(_valid_core_receipt(receipt))

    def test_receipt_requires_the_full_semantic_source_pair(self):
        """한쪽만 있으면 정본을 지목만 하고 대조할 값이 없거나 그 반대다 — 둘 다 아니면 거부."""
        base = {"base_sha256": "a" * 64, "sage_version": "0.0.0"}
        self.assertTrue(_valid_core_receipt(base))
        self.assertTrue(_valid_core_receipt(
            dict(base, semantic_source=LOGICAL, semantic_source_sha256="b" * 64)))
        self.assertFalse(_valid_core_receipt(dict(base, semantic_source=LOGICAL)))
        self.assertFalse(_valid_core_receipt(dict(base, semantic_source_sha256="b" * 64)))
        self.assertFalse(_valid_core_receipt(dict(base, unexpected="x")))

    def test_missing_installed_render_yields_no_receipt(self):
        """구버전 소비자에는 설치본이 없다. 그 상태를 오류로 만들면 upgrade 가 실행조차 못 한다."""
        with tempfile.TemporaryDirectory() as dest:
            receipt, error = _mat._language_policy_receipt(dest)
            self.assertIsNone(receipt)
            self.assertIsNone(error)


if __name__ == "__main__":
    unittest.main()
