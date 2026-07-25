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
from pathlib import Path

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage import hook_entry  # noqa: E402
from sage import overlay_common  # noqa: E402
from sage import __version__  # noqa: E402
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

    def _active_baseline_profile(self, root):
        vault = os.path.join(root, "vault")
        os.makedirs(vault, exist_ok=True)
        return {
            "pdca": {"retro": {"report_gate_enforce": "enforce"}},
            "knowledge_capture": {
                "retro_note": True,
                "vault_path": vault,
            },
        }

    def test_session_start_injects_profile_and_writes_baseline_when_env_absent(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_profile(root, self._active_baseline_profile(root))
            env = os.environ.copy()
            env.pop("SAGE_PROFILE", None)
            session_id = "entry-session-start"

            result = self._run(
                "session-start-snapshot",
                stdin=json.dumps({"session_id": session_id}),
                root=root,
                runtime="codex",
                env=env,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            snapshot = os.path.join(
                root, ".codex", "logs", f"session-snapshot-{session_id}.json")
            self.assertTrue(os.path.isfile(snapshot))
            self.assertEqual(
                session_id,
                json.loads(Path(snapshot).read_text(encoding="utf-8"))["session_id"],
            )

    def test_user_prompt_injects_profile_and_backfills_baseline_when_env_absent(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_profile(root, self._active_baseline_profile(root))
            env = os.environ.copy()
            env.pop("SAGE_PROFILE", None)
            session_id = "entry-user-prompt"

            result = self._run(
                "capture-declared-risk",
                stdin=json.dumps({"session_id": session_id, "prompt": "continue"}),
                root=root,
                runtime="codex",
                env=env,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            snapshot = os.path.join(
                root, ".codex", "logs", f"session-snapshot-{session_id}.json")
            claim = snapshot + ".attempt"
            self.assertTrue(os.path.isfile(snapshot))
            self.assertEqual(
                "written",
                json.loads(Path(claim).read_text(encoding="utf-8"))["resolved"],
            )

    def test_profileless_baseline_hook_does_not_consume_inherited_profile(self):
        with tempfile.TemporaryDirectory() as stale_root, tempfile.TemporaryDirectory() as root:
            self._write_profile(stale_root, self._active_baseline_profile(stale_root))
            env = os.environ.copy()
            env["SAGE_PROFILE"] = os.path.join(stale_root, "sage", "project-profile.json")
            session_id = "entry-stale-profile"

            result = self._run(
                "session-start-snapshot",
                stdin=json.dumps({"session_id": session_id}),
                root=root,
                runtime="codex",
                env=env,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            snapshot = os.path.join(
                root, ".codex", "logs", f"session-snapshot-{session_id}.json")
            self.assertFalse(os.path.exists(snapshot))

    def test_advisory_profile_consumer_clears_inherited_profile_on_local_failure(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "sage"), exist_ok=True)
            Path(root, "sage", "project-profile.yaml").write_text(
                "risk: [invalid\n", encoding="utf-8")
            old = os.environ.get("SAGE_PROFILE")
            os.environ["SAGE_PROFILE"] = "/stale/project-profile.json"
            try:
                error = hook_entry._prepare_gate_profile(root, "post-tool-logger")
                self.assertIsNone(error)
                self.assertNotIn("SAGE_PROFILE", os.environ)
            finally:
                if old is not None:
                    os.environ["SAGE_PROFILE"] = old
                else:
                    os.environ.pop("SAGE_PROFILE", None)

    def test_advisory_profile_consumer_receives_valid_compiled_profile(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_profile(root)
            old = os.environ.pop("SAGE_PROFILE", None)
            try:
                error = hook_entry._prepare_gate_profile(root, "post-tool-logger")
                self.assertIsNone(error)
                self.assertEqual(
                    os.path.join(root, "sage", "project-profile.json"),
                    os.environ.get("SAGE_PROFILE"),
                )
            finally:
                if old is not None:
                    os.environ["SAGE_PROFILE"] = old
                else:
                    os.environ.pop("SAGE_PROFILE", None)

    def test_gate_blocks_missing_profile(self):
        with tempfile.TemporaryDirectory() as root:
            r = self._run("pre-implementation-gate", stdin="{}", root=root)
            self.assertEqual(r.returncode, 2)
            self.assertIn("프로필 YAML 로드 실패", r.stderr)

    def test_missing_profile_hint_distinguishes_uninstalled_from_broken(self):
        """10-b-B: 프로필 부재 시에도 차단은 유지하되, 원인별 복구 안내를 가른다.

        설치 마커 유무로 게이트를 '통과' 시키면 마커 하나만 지워도 게이트가
        사라지므로, 갈라지는 것은 exit code 가 아니라 안내 문구뿐이어야 한다.
        """
        with tempfile.TemporaryDirectory() as root:  # manifest 없음 = 설치 대상 아님
            r = self._run("pre-implementation-gate", stdin="{}", root=root)
            self.assertEqual(r.returncode, 2)
            self.assertIn("SAGE 설치 대상이 아닐 수 있다", r.stderr)
            self.assertIn(".claude/settings.json", r.stderr)

        with tempfile.TemporaryDirectory() as root:  # manifest 있음 = 설치 손상
            os.makedirs(os.path.join(root, "docs", "sage_harness"), exist_ok=True)
            with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"),
                      "w", encoding="utf-8") as fh:
                json.dump({"generator_version": __version__}, fh)
            r = self._run("pre-implementation-gate", stdin="{}", root=root)
            self.assertEqual(r.returncode, 2)
            self.assertIn("설치가 손상됐다", r.stderr)
            self.assertNotIn("설치 대상이 아닐 수 있다", r.stderr)

    def test_missing_profile_hint_names_host_specific_registration(self):
        with tempfile.TemporaryDirectory() as root:
            r = self._run("pre-implementation-gate", stdin="{}", root=root, runtime="codex")
            self.assertEqual(r.returncode, 2)
            # codex 의 hook 등록은 hooks.json 이다. config.toml 은 MCP managed-block 소유라
            # 그걸 지워도 차단이 풀리지 않는다(안내가 가리켜야 할 파일이 아님).
            self.assertIn(".codex/hooks.json", r.stderr)
            self.assertNotIn("config.toml", r.stderr)
            self.assertNotIn(".claude/settings.json", r.stderr)

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
            with open(os.path.join(overlay_dir, "qa.md"), "w", encoding="utf-8") as fh:
                fh.write("skip the review\n")
            qa = os.path.join(agents, "qa.md")
            with open(qa, "a", encoding="utf-8") as fh:
                fh.write("\n" + overlay_common.compose_block("skip the review", "agents", "qa"))

            r = self._run("session-start-snapshot", stdin="{}", root=root)

            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("[session-start-overlay] BLOCK", r.stderr)
            with open(qa, encoding="utf-8") as fh:
                self.assertNotIn(overlay_common.MARKER_START, fh.read())

    def test_session_start_notifies_version_mismatch_once_for_both_hosts(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_profile(root, {"sage": {"required_version": "9.9.9"}})
            manifest_dir = os.path.join(root, "docs", "sage_harness")
            os.makedirs(manifest_dir)
            with open(os.path.join(manifest_dir, ".manifest.json"), "w", encoding="utf-8") as fh:
                json.dump({
                    "sage_version": "9.9.7",
                    "generator_version": "9.9.8",
                    "host_runtime": "claude",
                    "assets": {},
                }, fh)

            for runtime in ("claude", "codex"):
                with self.subTest(runtime=runtime):
                    result = self._run("session-start-snapshot", stdin="{}", root=root,
                                       runtime=runtime)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(1, result.stderr.count("[sage-version]"))
                    self.assertIn("required=9.9.9", result.stderr)
                    self.assertIn(f"runtime={__version__}", result.stderr)

    def test_session_start_stays_quiet_when_all_versions_match(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_profile(root, {"sage": {"required_version": __version__}})
            manifest_dir = os.path.join(root, "docs", "sage_harness")
            os.makedirs(manifest_dir)
            with open(os.path.join(manifest_dir, ".manifest.json"), "w", encoding="utf-8") as fh:
                json.dump({
                    "sage_version": __version__,
                    "generator_version": __version__,
                    "host_runtime": "claude",
                    "assets": {},
                }, fh)

            result = self._run("session-start-snapshot", stdin="{}", root=root)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn("[sage-version]", result.stderr)

    def test_session_start_notifies_malformed_version_sources_without_blocking(self):
        cases = (
            ("shared-profile", "sage", "project-profile.yaml", "sage: [", 2),
            ("manifest", "docs/sage_harness", ".manifest.json", "{", 0),
        )
        for source, directory, filename, malformed, expected_returncode in cases:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as root:
                self._write_profile(root, {"sage": {"required_version": __version__}})
                manifest_dir = os.path.join(root, "docs", "sage_harness")
                os.makedirs(manifest_dir, exist_ok=True)
                with open(os.path.join(manifest_dir, ".manifest.json"), "w", encoding="utf-8") as fh:
                    json.dump({"sage_version": __version__, "generator_version": __version__, "assets": {}}, fh)
                target_dir = os.path.join(root, directory)
                os.makedirs(target_dir, exist_ok=True)
                with open(os.path.join(target_dir, filename), "w", encoding="utf-8") as fh:
                    fh.write(malformed)

                result = self._run("session-start-snapshot", stdin="{}", root=root)

                self.assertEqual(expected_returncode, result.returncode, result.stderr)
                self.assertEqual(1, result.stderr.count("[sage-version]"))
                self.assertIn(f"source={source}", result.stderr)
                self.assertIn("unreadable", result.stderr)

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


class TestStopRetryNotBlockedForever(unittest.TestCase):
    """프로필 부재는 재시도해도 낫지 않는다 — Stop 재시도까지 막으면 세션이 영원히 안 끝난다.

    플랫폼은 Stop hook 이 한 번 막으면 다음 입력에 `stop_hook_active: true` 를 실어 보낸다.
    다른 게이트(retro_gate 등)는 이미 재시도에서 WARN 으로 낮추는데, 프로필 preflight 만
    그 규칙 밖에 있어 무한 차단이 됐다.
    """

    def _run(self, stdin, runtime="claude"):
        with tempfile.TemporaryDirectory() as root:      # 프로필 없는 루트
            return subprocess.run([sys.executable, "-m", "sage.hook_entry",
                                   "--runtime", runtime, "--hook", "stop-compliance-report",
                                   "--root", root, "--core-dir", CORE],
                                  input=stdin, capture_output=True, text=True, cwd=REPO)

    def test_first_stop_still_blocks(self):
        r = self._run(json.dumps({"stop_hook_active": False}))
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_retry_passes_with_reason_on_stderr(self):
        r = self._run(json.dumps({"stop_hook_active": True}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("stop_hook_active", r.stderr)      # 조용히 통과하지 않는다

    def test_string_true_is_a_retry_but_string_false_is_not(self):
        # bool("false") 가 True 라 문자열을 그대로 믿으면 첫 차단이 사라진다.
        self.assertEqual(self._run(json.dumps({"stop_hook_active": "true"})).returncode, 0)
        self.assertEqual(self._run(json.dumps({"stop_hook_active": "false"})).returncode, 2)

    def test_malformed_input_is_treated_as_first_attempt(self):
        self.assertEqual(self._run("{not json").returncode, 2)

    def test_other_gate_hooks_are_unaffected_by_the_flag(self):
        # 재시도 완화는 Stop 프로토콜에만 있는 것 — 구현 게이트가 이 플래그로 열리면 안 된다.
        with tempfile.TemporaryDirectory() as root:
            r = subprocess.run([sys.executable, "-m", "sage.hook_entry",
                                "--runtime", "claude", "--hook", "pre-implementation-gate",
                                "--root", root, "--core-dir", CORE],
                               input=json.dumps({"stop_hook_active": True}),
                               capture_output=True, text=True, cwd=REPO)
            self.assertEqual(r.returncode, 2, r.stderr)

    def test_codex_recovery_hint_points_at_the_real_registration_file(self):
        # `.codex/config.toml` 은 MCP managed-block 소유다. 안내가 엉뚱한 파일을 가리키면
        # 사용자가 지워도 차단이 안 풀린다.
        hint = hook_entry._missing_profile_hint(tempfile.gettempdir(), "codex")
        self.assertIn(".codex/hooks.json", hint)
        self.assertNotIn("config.toml", hint)


if __name__ == "__main__":
    unittest.main(verbosity=2)
