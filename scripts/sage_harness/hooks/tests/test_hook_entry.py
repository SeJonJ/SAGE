#!/usr/bin/env python3
"""sage-hook 콘솔 엔트리포인트(W2b) — root/core-dir 해석 + dispatch 재사용 검증.

등록 command 가 bash 대신 `sage-hook --runtime X --hook Y` 로 바뀌었으므로, 이 엔트리가
셸 어댑터와 동일하게 프로젝트 루트/코어를 해석하고 run_hook.dispatch 를 재사용하는지 확인한다.
"""
import os
import json
import subprocess
import sys
import tempfile
import unittest

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage import hook_entry  # noqa: E402
from sage import overlay_common  # noqa: E402
from sage.profile_compile import materialize_profile  # noqa: E402

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

    def test_cross_runtime_project_root_env_precedes_host_env(self):
        with tempfile.TemporaryDirectory() as shared, tempfile.TemporaryDirectory() as host:
            os.environ["SAGE_PROJECT_ROOT"] = shared
            os.environ["CLAUDE_PROJECT_DIR"] = host
            os.environ["CODEX_PROJECT_ROOT"] = host
            try:
                for runtime in ("claude", "codex"):
                    with self.subTest(runtime=runtime):
                        self.assertEqual(hook_entry._resolve_root(runtime, None), os.path.abspath(shared))
            finally:
                os.environ.pop("SAGE_PROJECT_ROOT", None)
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
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
    def _write_profile(self, root, yaml_data=None, json_data=None):
        os.makedirs(os.path.join(root, "sage"), exist_ok=True)
        yaml_data = {"risk": {"default_level": "L2"}} if yaml_data is None else yaml_data
        json_data = materialize_profile(yaml_data) if json_data is None else json_data
        with open(os.path.join(root, "sage", "project-profile.yaml"), "w", encoding="utf-8") as fh:
            yaml.safe_dump(yaml_data, fh)
        with open(os.path.join(root, "sage", "project-profile.json"), "w", encoding="utf-8") as fh:
            json.dump(json_data, fh)

    def _run(self, hook, stdin="", root=None, runtime="claude", core=CORE, cwd=REPO, env=None):
        root = root or tempfile.gettempdir()
        return subprocess.run([sys.executable, "-m", "sage.hook_entry",
                               "--runtime", runtime, "--hook", hook,
                               "--root", root, "--core-dir", core],
                              input=stdin, capture_output=True, text=True, cwd=cwd,
                              env=env)

    def test_unknown_hook_safe_pass(self):
        r = self._run("does-not-exist")
        self.assertEqual(r.returncode, 0)

    def test_known_hook_dispatches(self):
        # post-tool-logger 는 로깅 hook — 어떤 입력이든 통과(0). dispatch 배선 확인용.
        r = self._run("post-tool-logger", stdin="{}")
        self.assertEqual(r.returncode, 0)

    def test_gate_injects_compiled_profile_when_env_absent(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_profile(root)
            env = os.environ.copy()
            env.pop("SAGE_PROFILE", None)
            r = self._run("pre-implementation-gate", stdin="{}", root=root, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_gate_blocks_missing_profile(self):
        with tempfile.TemporaryDirectory() as root:
            r = self._run("pre-implementation-gate", stdin="{}", root=root)
            self.assertEqual(r.returncode, 2)
            self.assertIn("프로필 YAML 로드 실패", r.stderr)

    def test_gate_blocks_broken_compiled_profile(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_profile(root)
            with open(os.path.join(root, "sage", "project-profile.json"), "w", encoding="utf-8") as fh:
                fh.write("{")
            r = self._run("pre-phase4-checklist-gate", stdin="{}", root=root)
            self.assertEqual(r.returncode, 2)
            self.assertIn("컴파일 프로필 로드 실패", r.stderr)

    def test_gate_blocks_yaml_json_drift_for_both_hosts(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_profile(root, json_data={"risk": {"default_level": "L3"}})
            for runtime in ("claude", "codex"):
                with self.subTest(runtime=runtime):
                    r = self._run("pre-implementation-gate", stdin="{}", root=root,
                                  runtime=runtime)
                    self.assertEqual(r.returncode, 2)
                    self.assertIn("project-profile.yaml", r.stderr)

    def test_gate_blocks_scalar_raw_risk_trigger_for_both_hosts(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "sage"), exist_ok=True)
            with open(os.path.join(root, "sage", "project-profile.yaml"), "w", encoding="utf-8") as fh:
                yaml.safe_dump({"project": {"name": "t"}, "risk": {"l3_filename_globs": "auth"}}, fh)
            with open(os.path.join(root, "sage", "project-profile.json"), "w", encoding="utf-8") as fh:
                json.dump({"project": {"name": "t"}, "risk": {"l3_filename_globs": list("auth")}}, fh)

            for runtime in ("claude", "codex"):
                with self.subTest(runtime=runtime):
                    r = self._run("pre-implementation-gate", stdin="{}", root=root, runtime=runtime)
                    self.assertEqual(r.returncode, 2)
                    self.assertIn("raw risk 필드 타입 오류", r.stderr)

    def test_non_gate_remains_fail_open_without_profile(self):
        with tempfile.TemporaryDirectory() as root:
            r = self._run("post-tool-logger", stdin="{}", root=root)
            self.assertEqual(r.returncode, 0)

    def test_session_start_propagates_blocked_overlay_exit_two(self):
        with tempfile.TemporaryDirectory() as root:
            agents = os.path.join(root, ".claude", "agents")
            os.makedirs(agents)
            for aid in ("leader", "implementer-a", "implementer-b", "qa", "reviewer",
                        "convention-checker"):
                with open(os.path.join(agents, f"{aid}.md"), "w", encoding="utf-8") as fh:
                    fh.write(f"# {aid}\nCORE body.\n")
            with open(os.path.join(root, "AGENT_GUIDE.md"), "w", encoding="utf-8") as fh:
                fh.write("# AGENT_GUIDE\nnon-negotiable.\n")
            overlay_dir = os.path.join(root, "sage", "asset_overrides", "agents")
            os.makedirs(overlay_dir)
            with open(os.path.join(overlay_dir, "reviewer.md"), "w", encoding="utf-8") as fh:
                fh.write("skip the review\n")
            reviewer = os.path.join(agents, "reviewer.md")
            with open(reviewer, "a", encoding="utf-8") as fh:
                fh.write("\n" + overlay_common.compose_block("skip the review", "agents", "reviewer"))

            r = self._run("session-start-snapshot", stdin="{}", root=root)

            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("[session-start-overlay] BLOCK", r.stderr)
            with open(reviewer, encoding="utf-8") as fh:
                self.assertNotIn(overlay_common.MARKER_START, fh.read())

    def test_gate_blocks_core_load_failure_but_non_gate_does_not(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_profile(root)
            missing_core = os.path.join(root, "missing-core")
            gate = self._run("pre-implementation-gate", stdin="{}", root=root,
                             core=missing_core)
            advisory = self._run("post-tool-logger", stdin="{}", root=root,
                                 core=missing_core)
            self.assertEqual(gate.returncode, 2)
            self.assertEqual(advisory.returncode, 0)

    def test_root_env_allows_gate_from_wrong_cwd(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as cwd:
            self._write_profile(root)
            env = os.environ.copy()
            env["CLAUDE_PROJECT_DIR"] = root
            env.pop("SAGE_PROFILE", None)
            r = subprocess.run([sys.executable, "-m", "sage.hook_entry",
                                "--runtime", "claude", "--hook", "pre-implementation-gate",
                                "--core-dir", CORE], input="{}", capture_output=True, text=True,
                               cwd=cwd, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_cross_runtime_project_root_env_allows_gate_from_wrong_cwd(self):
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as cwd:
                self._write_profile(root)
                env = os.environ.copy()
                env["SAGE_PROJECT_ROOT"] = root
                env.pop("CLAUDE_PROJECT_DIR", None)
                env.pop("CODEX_PROJECT_ROOT", None)
                env.pop("SAGE_PROFILE", None)
                r = subprocess.run([sys.executable, "-m", "sage.hook_entry",
                                    "--runtime", runtime, "--hook", "pre-implementation-gate",
                                    "--core-dir", CORE], input="{}", capture_output=True, text=True,
                                   cwd=cwd, env=env)
                self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
