#!/usr/bin/env python3
"""`sage-hook` 이 project core 를 import 하기 전에 호환성을 닫는가 — 실제 entrypoint subprocess.

이 테스트가 지키는 것은 판정이 아니라 **순서**다. 판정은 `test_runtime_api.py` 가 결정표로
덮는다. 여기서 확인하는 것은 그 판정이 `_load_run_hook()` 앞에 선다는 것 하나다.

순서가 뒤집히면 새 project core 가 아직 없는 `sage.*` 를 import 하면서 `ModuleNotFoundError`
가 먼저 나온다. 그 traceback 은 host 에 따라 그냥 "hook 이 죽었다" 로 처리되고, 정책을
실행해야 할 게이트가 조용히 빠진다. 그래서 core 를 **import 하는 순간 터지는 core-dir** 을
쥐여 주고, 그래도 진단이 나오는지를 본다 — 진단이 나오면 core 는 로드되지 않은 것이다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.profile_compile import materialize_profile  # noqa: E402
from sage.runtime_api import HOOK_RUNTIME_API  # noqa: E402

CORE = os.path.join(REPO, "scripts", "sage_harness", "hooks")

GATE_HOOKS = ("pre-implementation-gate", "pre-phase4-checklist-gate")
BASELINE_HOOKS = ("post-tool-logger", "capture-declared-risk")


def _source_env():
    env = dict(os.environ)
    current = [e for e in env.get("PYTHONPATH", "").split(os.pathsep) if e and e != REPO]
    env["PYTHONPATH"] = os.pathsep.join([REPO, *current])
    return env


def _project(root, manifest, profile=None):
    os.makedirs(os.path.join(root, "docs", "sage_harness"), exist_ok=True)
    with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh)
    os.makedirs(os.path.join(root, "sage"), exist_ok=True)
    profile = {"risk": {"default_level": "L2"}} if profile is None else profile
    with open(os.path.join(root, "sage", "project-profile.yaml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump(profile, fh)
    with open(os.path.join(root, "sage", "project-profile.json"), "w", encoding="utf-8") as fh:
        json.dump(materialize_profile(profile), fh)
    return root


def _manifest(required=None, generator_version="1.0.0", **extra):
    manifest = {"sage_version": "1.0.0", "host_runtime": "codex", "assets": {},
                "generator_version": generator_version}
    if required is not None:
        manifest["runtime_api"] = {"required": required}
    manifest.update(extra)
    return manifest


def _poisoned_core(tmp):
    """core 를 import 하는 순간 터지는 core-dir. catalog 는 살려 둔다.

    catalog 까지 죽이면 fallback 문장만 나와서 "무엇 때문에 막혔는가" 를 확인할 수 없다.
    죽여야 하는 것은 dispatch 진입점 하나다.
    """
    dest = os.path.join(tmp, "core")
    shutil.copytree(CORE, dest,
                    ignore=shutil.ignore_patterns("__pycache__", "tests", "*.pyc"))
    with open(os.path.join(dest, "runtime", "run_hook.py"), "w", encoding="utf-8") as fh:
        fh.write('raise RuntimeError("core was imported — the preflight ran too late")\n')
    return dest


def _run(hook, root, core, runtime="codex", stdin=""):
    return subprocess.run([sys.executable, "-m", "sage.hook_entry",
                           "--runtime", runtime, "--hook", hook,
                           "--root", root, "--core-dir", core],
                          input=stdin, capture_output=True, text=True, cwd=REPO,
                          env=_source_env())


class TestBlockedBeforeCoreImport(unittest.TestCase):
    """정책을 실행하는 hook 은 fail-closed 다."""

    def _blocked(self, manifest, hook="pre-implementation-gate", runtime="codex"):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(os.path.join(tmp, "proj"), manifest)
            return _run(hook, root, _poisoned_core(tmp), runtime=runtime)

    def test_newer_required_api_blocks_with_rc_2(self):
        r = self._blocked(_manifest(required=HOOK_RUNTIME_API + 1))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("runtime.api_too_old", r.stderr)

    def test_missing_marker_in_a_1_0_manifest_blocks(self):
        r = self._blocked(_manifest(required=None, generator_version="1.0.0"))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("runtime.api_marker_missing", r.stderr)

    def test_damaged_marker_blocks(self):
        for bad in ({"required": 0}, {"required": "1"}, {"required": True}, {}, "1"):
            with self.subTest(bad=bad):
                r = self._blocked(_manifest(required=None, runtime_api=bad))
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("runtime.api_marker", r.stderr)

    def test_the_core_is_never_imported(self):
        # poisoned core 는 import 되면 RuntimeError 를 던진다. 그 흔적이 없어야 한다.
        r = self._blocked(_manifest(required=HOOK_RUNTIME_API + 1))
        self.assertNotIn("core was imported", r.stderr + r.stdout)
        self.assertNotIn("entry.core_load_failed", r.stderr)

    def test_no_traceback_reaches_the_user(self):
        r = self._blocked(_manifest(required=HOOK_RUNTIME_API + 1))
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("ModuleNotFoundError", r.stderr)

    def test_the_block_carries_an_executable_next(self):
        """`Next:` 조각을 host wire 모양과 무관하게 센다.

        Codex 는 한 줄만 받으므로 복구 줄이 `|` 로 이어진다. 줄 단위로만 세면 그 host 에서
        안내가 사라진 것처럼 보이지만, 실제로는 구분자만 다르다.
        """
        r = self._blocked(_manifest(required=HOOK_RUNTIME_API + 1))
        parts = [chunk.strip() for line in r.stderr.splitlines()
                 for chunk in line.split(" | ")]
        nexts = [chunk for chunk in parts if chunk.startswith("Next: ")]
        self.assertTrue(nexts, r.stderr)
        self.assertTrue(any("sage " in chunk or "pipx " in chunk for chunk in nexts))

    def test_the_codex_block_stays_on_one_line(self):
        r = self._blocked(_manifest(required=HOOK_RUNTIME_API + 1))
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)

    def test_every_gate_hook_is_fail_closed(self):
        for hook in GATE_HOOKS:
            with self.subTest(hook=hook):
                r = self._blocked(_manifest(required=HOOK_RUNTIME_API + 1), hook=hook)
                self.assertEqual(r.returncode, 2, r.stderr)

    def test_the_write_guard_is_fail_closed(self):
        r = self._blocked(_manifest(required=HOOK_RUNTIME_API + 1),
                          hook="generated-artifact-write-guard")
        self.assertEqual(r.returncode, 2, r.stderr)


class TestHostWireContract(unittest.TestCase):
    """진단 UX 를 이유로 host 계약을 통일하지 않는다."""

    def test_codex_stop_uses_a_single_json_object_with_rc_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(os.path.join(tmp, "proj"),
                            _manifest(required=HOOK_RUNTIME_API + 1))
            r = _run("stop-compliance-report", root, _poisoned_core(tmp), runtime="codex")
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout.strip())          # 단일 객체여야 파싱된다
        self.assertEqual(payload["decision"], "block")
        self.assertIn("runtime.api_too_old", payload["reason"])
        self.assertIn("Next: ", payload["reason"])

    def test_claude_stop_uses_stderr_and_a_blocking_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(os.path.join(tmp, "proj"),
                            _manifest(required=HOOK_RUNTIME_API + 1))
            r = _run("stop-compliance-report", root, _poisoned_core(tmp), runtime="claude")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("runtime.api_too_old", r.stderr)
        self.assertEqual(r.stdout.strip(), "")


class TestNonEnforcingHooks(unittest.TestCase):
    """logger·baseline 하나가 host 작업 전체를 막지는 않는다. 그러나 조용하지도 않다."""

    def test_baseline_hooks_warn_loudly_with_rc_zero(self):
        for hook in BASELINE_HOOKS:
            with self.subTest(hook=hook):
                with tempfile.TemporaryDirectory() as tmp:
                    root = _project(os.path.join(tmp, "proj"),
                                    _manifest(required=HOOK_RUNTIME_API + 1))
                    r = _run(hook, root, _poisoned_core(tmp))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("[sage-runtime-api] WARN", r.stderr)
                self.assertIn("runtime.api_too_old", r.stderr)

    def test_a_baseline_warning_still_carries_a_next(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(os.path.join(tmp, "proj"),
                            _manifest(required=HOOK_RUNTIME_API + 1))
            r = _run("post-tool-logger", root, _poisoned_core(tmp))
        self.assertIn("Next: ", r.stderr)

    def test_the_baseline_hook_still_does_not_import_the_core(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(os.path.join(tmp, "proj"),
                            _manifest(required=HOOK_RUNTIME_API + 1))
            r = _run("post-tool-logger", root, _poisoned_core(tmp))
        self.assertNotIn("core was imported", r.stderr + r.stdout)


class TestCompatibleAndLegacyPassThrough(unittest.TestCase):
    """호환이거나 1.0 이전 설치면 preflight 는 아무것도 하지 않는다."""

    def _reaches_core(self, manifest, hook="post-tool-logger"):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(os.path.join(tmp, "proj"), manifest)
            r = _run(hook, root, _poisoned_core(tmp))
        # preflight 가 통과시켰다면 core 로드까지 갔다는 흔적이 남는다.
        return ("core was imported" in (r.stderr + r.stdout)
                or "core_load_failed" in r.stderr), r

    def test_matching_api_passes_through(self):
        reached, r = self._reaches_core(_manifest(required=HOOK_RUNTIME_API))
        self.assertTrue(reached, r.stderr)
        self.assertNotIn("[sage-runtime-api]", r.stderr)

    def test_pre_1_0_install_without_marker_passes_through(self):
        reached, r = self._reaches_core(_manifest(required=None, generator_version="0.9.84"))
        self.assertTrue(reached, r.stderr)
        self.assertNotIn("[sage-runtime-api]", r.stderr)

    def test_an_unreadable_manifest_is_reported_not_ignored(self):
        """이전에는 "부트스트랩이 소유한다" 며 넘겼다. 그 경로는 manifest 를 읽지 않는다.

        읽을 수 없으면 호환성을 판정할 근거가 없다. 근거 없음을 통과로 접으면 "판정 전에는
        import 하지 않는다" 는 계약이 사라진다. 다만 logger 는 아무 정책도 집행하지 않으므로
        막지는 않는다 — 알리고 통과한다.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "proj")
            os.makedirs(os.path.join(root, "docs", "sage_harness"))
            with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                      encoding="utf-8") as fh:
                fh.write("{")
            r = _run("post-tool-logger", root, _poisoned_core(tmp))
        self.assertIn("runtime.manifest_unreadable", r.stderr)

    def test_an_unreadable_manifest_blocks_a_gate_before_the_core(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "proj")
            os.makedirs(os.path.join(root, "docs", "sage_harness"))
            with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                      encoding="utf-8") as fh:
                fh.write("{")
            r = _run("pre-implementation-gate", root, _poisoned_core(tmp))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("runtime.manifest_unreadable", r.stderr)
        self.assertNotIn("core was imported", r.stderr + r.stdout)


class TestProjectHookIsFailClosed(unittest.TestCase):
    """project 가 소유한 hook 은 정책을 실행하므로 gate 와 같이 닫힌다."""

    def test_project_owned_hook_blocks_with_rc_2(self):
        manifest = _manifest(required=HOOK_RUNTIME_API + 1)
        manifest["assets"] = {"hooks/custom-policy": {"conformance": "PASS",
                                                      "form": "core_adapter",
                                                      "origin": "project"}}
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(os.path.join(tmp, "proj"), manifest)
            r = _run("custom-policy", root, _poisoned_core(tmp))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("runtime.api_too_old", r.stderr)


class TestRunAllRegistration(unittest.TestCase):
    def test_this_suite_is_wired(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run-all.sh"),
                  encoding="utf-8") as fh:
            self.assertIn("test_runtime_api_preflight.py", fh.read())


BUILT_IN_HOOKS = ("capture-declared-risk", "generated-artifact-write-guard",
                  "post-tool-logger", "pre-implementation-gate",
                  "pre-phase4-checklist-gate", "session-start-snapshot",
                  "stop-compliance-report")


class TestBothHostsAcrossEveryBuiltInHook(unittest.TestCase):
    """7종 × 2 host 를 실제 adapter subprocess 로 전부 돌린다.

    이전 증거는 대부분 Codex 진입점 하나였다. host 분기는 실제로 존재하므로(Codex 는 단일 줄,
    Stop 은 stdout JSON), 한쪽만 도는 증거로 "양 host 통과"를 주장할 수 없다.
    """

    def _matrix(self, manifest):
        seen = {}
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(os.path.join(tmp, "proj"), manifest)
            core = _poisoned_core(tmp)
            for hook in BUILT_IN_HOOKS:
                for runtime in ("claude", "codex"):
                    seen[(hook, runtime)] = _run(hook, root, core, runtime=runtime)
        return seen

    def test_the_matrix_is_seven_hooks_by_two_hosts(self):
        self.assertEqual(len(BUILT_IN_HOOKS), 7)
        self.assertEqual(len(self._matrix(_manifest(required=HOOK_RUNTIME_API))), 14)

    def test_no_host_ever_imports_the_poisoned_core_when_incompatible(self):
        for (hook, runtime), r in self._matrix(_manifest(required=HOOK_RUNTIME_API + 1)).items():
            with self.subTest(hook=hook, runtime=runtime):
                self.assertNotIn("core was imported", r.stderr + r.stdout)

    def test_every_hook_names_the_code_on_both_hosts(self):
        for (hook, runtime), r in self._matrix(_manifest(required=HOOK_RUNTIME_API + 1)).items():
            with self.subTest(hook=hook, runtime=runtime):
                self.assertIn("runtime.api_too_old", r.stderr + r.stdout)

    def test_every_hook_names_a_next_action_on_both_hosts(self):
        for (hook, runtime), r in self._matrix(_manifest(required=HOOK_RUNTIME_API + 1)).items():
            with self.subTest(hook=hook, runtime=runtime):
                self.assertIn("Next: ", r.stderr + r.stdout)

    def test_codex_output_stays_on_one_line(self):
        for (hook, runtime), r in self._matrix(_manifest(required=HOOK_RUNTIME_API + 1)).items():
            if runtime != "codex" or hook == "stop-compliance-report":
                continue
            with self.subTest(hook=hook):
                self.assertLessEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)

    def test_codex_stop_answers_on_stdout_as_json_with_rc_zero(self):
        r = self._matrix(_manifest(required=HOOK_RUNTIME_API + 1))[
            ("stop-compliance-report", "codex")]
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("Next: ", payload["reason"])

    def test_enforcing_hooks_block_and_the_rest_pass_on_both_hosts(self):
        expected = {"pre-implementation-gate": 2, "pre-phase4-checklist-gate": 2,
                    "generated-artifact-write-guard": 2,
                    "capture-declared-risk": 0, "post-tool-logger": 0,
                    "session-start-snapshot": 0, "stop-compliance-report": 2}
        for (hook, runtime), r in self._matrix(_manifest(required=HOOK_RUNTIME_API + 1)).items():
            want = 0 if (runtime == "codex" and hook == "stop-compliance-report") \
                else expected[hook]
            with self.subTest(hook=hook, runtime=runtime):
                self.assertEqual(r.returncode, want, r.stderr + r.stdout)

    def test_a_compatible_manifest_lets_every_hook_reach_its_core(self):
        """호환일 때는 preflight 가 아무 말도 하지 않아야 한다 — 과차단이 없다는 증거다."""
        for (hook, runtime), r in self._matrix(_manifest(required=HOOK_RUNTIME_API)).items():
            with self.subTest(hook=hook, runtime=runtime):
                self.assertNotIn("[sage-runtime-api]", r.stderr)
                self.assertNotIn("runtime.api_too_old", r.stderr + r.stdout)

class TestDesignScenarioMatrix(unittest.TestCase):
    """동결 설계 §12.3 의 7 시나리오 × 2 host = 14 case.

    `TestBothHostsAcrossEveryBuiltInHook` 과 다른 것을 본다. 그쪽은 hook **ID** 7종을 한 가지
    상태로 돌린다. 여기는 **상태** 7가지를 양 host 로 돌린다 — 요구가 시나리오 행렬이므로
    hook 이름 개수로 대체할 수 없다.
    """

    HOSTS = ("claude", "codex")

    def _one(self, hook, manifest, runtime, stdin=""):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(os.path.join(tmp, "proj"), manifest)
            return _run(hook, root, _poisoned_core(tmp), runtime=runtime, stdin=stdin)

    # 1. compatible → preflight 가 아무 말도 하지 않고 기존 판정으로 넘어간다
    def test_scenario_1_compatible_preserves_the_existing_decision(self):
        for runtime in self.HOSTS:
            with self.subTest(runtime=runtime):
                r = self._one("pre-implementation-gate", _manifest(required=HOOK_RUNTIME_API),
                              runtime)
                self.assertNotIn("runtime.api_", r.stderr + r.stdout)
                # poisoned core 까지 실제로 도달했다 = preflight 가 막지 않았다.
                self.assertIn("core was imported", r.stderr + r.stdout)

    # 2. required API 가 더 큼
    def test_scenario_2_newer_required_api_blocks_before_the_core(self):
        for runtime in self.HOSTS:
            with self.subTest(runtime=runtime):
                r = self._one("pre-implementation-gate",
                              _manifest(required=HOOK_RUNTIME_API + 1), runtime)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertNotIn("core was imported", r.stderr + r.stdout)
                self.assertNotIn("Traceback", r.stderr)
                self.assertIn("Next: ", r.stderr + r.stdout)

    # 3. 1.0 인데 marker 없음
    def test_scenario_3_missing_marker_on_a_1_0_install_blocks(self):
        for runtime in self.HOSTS:
            with self.subTest(runtime=runtime):
                r = self._one("pre-implementation-gate",
                              _manifest(required=None, generator_version="1.0.0"), runtime)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("runtime.api_marker_missing", r.stderr + r.stdout)

    # 4. legacy(marker 없는 0.x) → 기존 동작 그대로, WARN 은 SessionStart 에서만
    def test_scenario_4_legacy_keeps_its_behavior_and_warns_only_at_session_start(self):
        legacy = _manifest(required=None, generator_version="0.9.84")
        for runtime in self.HOSTS:
            with self.subTest(runtime=runtime, half="session start warns"):
                r = self._one("session-start-snapshot", legacy, runtime)
                self.assertIn("[sage-runtime-api] WARN", r.stderr)
                self.assertIn("runtime.api_marker_absent_legacy", r.stderr)
                # 경고는 표시이지 차단이 아니다 — 기존 경로가 그대로 돌아야 한다.
                self.assertIn("core was imported", r.stderr + r.stdout)
            with self.subTest(runtime=runtime, half="other hooks stay quiet"):
                r = self._one("pre-implementation-gate", legacy, runtime)
                self.assertNotIn("[sage-runtime-api]", r.stderr)
                self.assertIn("core was imported", r.stderr + r.stdout)

    # 5. logger/baseline 비호환 → rc 0 + 시끄러운 WARN
    def test_scenario_5_baseline_warns_loudly_with_rc_zero(self):
        for runtime in self.HOSTS:
            for hook in ("post-tool-logger", "capture-declared-risk"):
                with self.subTest(runtime=runtime, hook=hook):
                    r = self._one(hook, _manifest(required=HOOK_RUNTIME_API + 1), runtime)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertIn("[sage-runtime-api]", r.stderr)
                    self.assertIn("Next: ", r.stderr)

    # 6. project 소유 hook 비호환 → rc 2
    def test_scenario_6_project_hook_blocks(self):
        manifest = _manifest(required=HOOK_RUNTIME_API + 1)
        manifest["assets"] = {"hooks/custom-policy": {"conformance": "PASS",
                                                      "form": "core_adapter",
                                                      "origin": "project"}}
        for runtime in self.HOSTS:
            with self.subTest(runtime=runtime):
                r = self._one("custom-policy", manifest, runtime)
                self.assertEqual(r.returncode, 2, r.stderr)

    # 7. Codex Stop → rc 0 + 단일 decision:block JSON / Claude Stop → stderr + 차단 exit
    def test_scenario_7_stop_follows_each_host_wire_contract(self):
        manifest = _manifest(required=HOOK_RUNTIME_API + 1)
        codex = self._one("stop-compliance-report", manifest, "codex", stdin="{}")
        self.assertEqual(codex.returncode, 0, codex.stderr)
        payload = json.loads(codex.stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("runtime.api_too_old", payload["reason"])
        self.assertIn("Next: ", payload["reason"])

        claude = self._one("stop-compliance-report", manifest, "claude", stdin="{}")
        self.assertEqual(claude.returncode, 2, claude.stdout)
        self.assertEqual(claude.stdout.strip(), "")
        self.assertIn("Next: ", claude.stderr)

    def test_the_matrix_covers_seven_scenarios_on_two_hosts(self):
        """행렬의 크기 자체를 고정한다 — 시나리오가 빠지면 여기서 걸린다."""
        scenarios = [name for name in dir(self)
                     if name.startswith("test_scenario_")]
        self.assertEqual(len(scenarios), 7, sorted(scenarios))
        self.assertEqual(len(self.HOSTS), 2)

if __name__ == "__main__":
    unittest.main(verbosity=2)
