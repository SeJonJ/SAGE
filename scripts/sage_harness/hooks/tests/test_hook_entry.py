#!/usr/bin/env python3
"""sage-hook 콘솔 엔트리포인트(W2b) — root/core-dir 해석 + dispatch 재사용 검증.

등록 command 가 bash 대신 `sage-hook --runtime X --hook Y` 로 바뀌었으므로, 이 엔트리가
셸 어댑터와 동일하게 프로젝트 루트/코어를 해석하고 run_hook.dispatch 를 재사용하는지 확인한다.
"""
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage import hook_entry  # noqa: E402

CORE = os.path.join(REPO, "scripts", "sage_harness", "hooks")


class TestRootResolution(unittest.TestCase):
    def test_explicit_wins(self):
        self.assertEqual(hook_entry._resolve_root("claude", "/tmp/x"), os.path.abspath("/tmp/x"))

    def test_claude_env(self):
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        with tempfile.TemporaryDirectory() as d:
            os.environ["CLAUDE_PROJECT_DIR"] = d
            try:
                self.assertEqual(hook_entry._resolve_root("claude", None), os.path.abspath(d))
            finally:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)

    def test_codex_env_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["CODEX_PROJECT_ROOT"] = d
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
            try:
                self.assertEqual(hook_entry._resolve_root("codex", None), os.path.abspath(d))
            finally:
                os.environ.pop("CODEX_PROJECT_ROOT", None)


class TestCoreDirResolution(unittest.TestCase):
    def test_explicit_wins(self):
        self.assertEqual(hook_entry._resolve_core_dir("/root", CORE), CORE)

    def test_project_local_preferred(self):
        with tempfile.TemporaryDirectory() as root:
            local = os.path.join(root, "scripts", "sage_harness", "hooks", "runtime")
            os.makedirs(local)
            got = hook_entry._resolve_core_dir(root, None)
            self.assertEqual(got, os.path.join(root, "scripts", "sage_harness", "hooks"))

    def test_bundle_fallback_when_no_local(self):
        with tempfile.TemporaryDirectory() as root:   # no scripts/ tree
            got = hook_entry._resolve_core_dir(root, None)
            self.assertTrue(got.endswith(os.path.join("scripts", "sage_harness", "hooks")))
            self.assertTrue(os.path.isdir(os.path.join(got, "runtime")))


class TestDispatchIntegration(unittest.TestCase):
    def _run(self, hook, stdin=""):
        return subprocess.run([sys.executable, "-m", "sage.hook_entry",
                               "--runtime", "claude", "--hook", hook,
                               "--root", tempfile.gettempdir(), "--core-dir", CORE],
                              input=stdin, capture_output=True, text=True, cwd=REPO)

    def test_unknown_hook_safe_pass(self):
        r = self._run("does-not-exist")
        self.assertEqual(r.returncode, 0)

    def test_known_hook_dispatches(self):
        # post-tool-logger 는 로깅 hook — 어떤 입력이든 통과(0). dispatch 배선 확인용.
        r = self._run("post-tool-logger", stdin="{}")
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
