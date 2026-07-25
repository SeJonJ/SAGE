#!/usr/bin/env python3
"""sage._resources 검증 (중 등급 — 번들 리소스 경로 해석, 패키징/재배치 대비).

repo fallback 으로 실제 리소스가 존재하는지 + $SAGE_RESOURCE_ROOT override 동작.
"""
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage import _resources  # noqa: E402


class TestResources(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("SAGE_RESOURCE_ROOT", None)

    def tearDown(self):
        os.environ.pop("SAGE_RESOURCE_ROOT", None)
        if self._saved is not None:
            os.environ["SAGE_RESOURCE_ROOT"] = self._saved

    def test_repo_fallback_resolves_real_resources(self):
        # repo fallback: install 이 복사하는 실제 번들 리소스가 존재해야 함
        self.assertTrue(os.path.isfile(os.path.join(_resources.templates_dir(), "project-profile.yaml")))
        self.assertTrue(os.path.isfile(os.path.join(_resources.core_dir(), "framework", "AGENT_GUIDE.md")))
        self.assertTrue(os.path.isfile(os.path.join(_resources.schema_dir(), "manifest.schema.json")))
        self.assertTrue(os.path.isfile(os.path.join(_resources.hooks_src_dir(), "pre_implementation_gate_core.py")))
        self.assertTrue(os.path.isfile(os.path.join(_resources.hook_specs_dir(), "pre-implementation-gate.md")))

    def test_env_override(self):
        # $SAGE_RESOURCE_ROOT 가 디렉토리면 그 경로를 사용(재배치/설치 시나리오)
        with tempfile.TemporaryDirectory() as d:
            os.environ["SAGE_RESOURCE_ROOT"] = d
            self.assertEqual(_resources.sage_root(), os.path.abspath(d))
            self.assertEqual(_resources.templates_dir(), os.path.join(d, "templates"))

    def test_env_override_ignored_if_not_dir(self):
        os.environ["SAGE_RESOURCE_ROOT"] = "/nonexistent/path/xyz"
        # 없는 경로면 무시하고 repo fallback
        self.assertTrue(os.path.isfile(os.path.join(_resources.templates_dir(), "project-profile.yaml")))


class TestEngineSourceTree(unittest.TestCase):
    """엔진 저장소 판별 — host 산출물이 엔진 저장소에 생기면 SAGE 자신의 게이트가 SAGE 개발을 막는다."""

    def test_this_repo_is_recognized(self):
        self.assertTrue(_resources.is_engine_source_tree(REPO))

    def test_installed_project_is_not(self):
        # 설치 대상에는 templates/core/framework 도 sage/cli.py 도 없다(프로필만 sage/ 아래).
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sage"))
            open(os.path.join(d, "sage", "project-profile.yaml"), "w").close()
            os.makedirs(os.path.join(d, "scripts", "sage_harness", "hooks"))
            self.assertFalse(_resources.is_engine_source_tree(d))

    def test_partial_markers_are_not_enough(self):
        # 한쪽 표식만으로 판정하면 우연히 같은 이름을 쓰는 프로젝트를 오차단한다.
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "templates", "core", "framework"))
            self.assertFalse(_resources.is_engine_source_tree(d))
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sage"))
            open(os.path.join(d, "sage", "cli.py"), "w").close()
            self.assertFalse(_resources.is_engine_source_tree(d))

    def test_empty_path_is_not(self):
        self.assertFalse(_resources.is_engine_source_tree(None))
        self.assertFalse(_resources.is_engine_source_tree(""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
