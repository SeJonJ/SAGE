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
        r = self._blocked(_manifest(required=HOOK_RUNTIME_API + 1))
        nexts = [ln for ln in r.stderr.splitlines() if ln.startswith("Next: ")]
        self.assertTrue(nexts, r.stderr)
        self.assertTrue(any("sage " in ln or "pipx " in ln for ln in nexts))

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

    def test_an_unreadable_manifest_is_left_to_the_existing_bootstrap_path(self):
        # 이 검사의 소관이 아니다. 함께 처리하면 같은 상태에 두 개의 다른 메시지가 생긴다.
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "proj")
            os.makedirs(os.path.join(root, "docs", "sage_harness"))
            with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                      encoding="utf-8") as fh:
                fh.write("{")
            r = _run("post-tool-logger", root, _poisoned_core(tmp))
        self.assertNotIn("[sage-runtime-api]", r.stderr)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
