#!/usr/bin/env python3
"""Regression tests for the generated-artifact write guard."""
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
HOOKS_DIR = REPO / "scripts" / "sage_harness" / "hooks"
RUNTIME_DIR = HOOKS_DIR / "runtime"
sys.path.insert(0, str(RUNTIME_DIR))
sys.path.insert(0, str(HOOKS_DIR))

import hook_runtime as hr  # noqa: E402
import run_hook  # noqa: E402


def _cases():
    path = Path(__file__).with_name("cases.tsv")
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        target, expected, description = line.split("\t", 2)
        yield target, int(expected), description


class TestGuardCoreContract(unittest.TestCase):
    def test_path_cases_preserve_shell_contract(self):
        import generated_artifact_write_guard_core as core

        for target, expected, description in _cases():
            with self.subTest(description=description, target=target):
                result = core.decide_paths([target])
                self.assertEqual(result["exit_code"], expected)

    def test_claude_and_codex_inputs_block_all_guarded_targets(self):
        import generated_artifact_write_guard_core as core

        claude = {"tool_input": {"file_path": ".claude/agents/z.md"}}
        codex = {"tool_name": "apply_patch", "tool_input": {"command": (
            "*** Begin Patch\n"
            "*** Add File: src/ok.py\n+x\n"
            "*** Move to: .codex/hooks/guard.sh\n"
            "*** End Patch"
        )}}
        self.assertEqual(core.decide_json(json.dumps(claude))["exit_code"], 2)
        self.assertEqual(core.decide_json(json.dumps(codex))["exit_code"], 2)

    def test_malformed_or_targetless_input_passes(self):
        import generated_artifact_write_guard_core as core

        self.assertEqual(core.decide_json("{")["exit_code"], 0)
        self.assertEqual(core.decide_json('{"tool_input":{}}')["exit_code"], 0)

    def test_windows_backslash_paths_are_guarded(self):
        import generated_artifact_write_guard_core as core

        self.assertEqual(core.decide_paths(
            [r"D:\work\project\.claude\agents\leader.md"])["exit_code"], 2)
        self.assertEqual(core.decide_paths(
            [r"D:\work\project\src\main.py"])["exit_code"], 0)

    def test_messages_keep_eligibility_specific_guidance(self):
        import generated_artifact_write_guard_core as core

        eligible = core.decide_paths([".CLAUDE/agents/IMPLEMENTER-A.md"])["message"]
        blocked = core.decide_paths([".claude/skills/sage-profile-modify/SKILL.md"])["message"]
        framework = core.decide_paths(["AGENT_GUIDE.md"])["message"]
        custom = core.decide_paths([".claude/agents/my-custom.md"])["message"]
        self.assertIn("sage/asset_overrides/agents/implementer-a.md", eligible)
        self.assertIn("현재 overlay 비지원", blocked)
        self.assertNotIn("sage-profile-modify.md", blocked)
        self.assertIn("project-profile.yaml", framework)
        self.assertIn("sage generate", custom)

    def test_nested_or_incomplete_paths_do_not_gain_core_overlay_eligibility(self):
        import generated_artifact_write_guard_core as core

        nested_agent = core.decide_paths(
            [".claude/agents/archive/leader.md"])["message"]
        incomplete_skill = core.decide_paths(
            [".claude/skills/sage-review"])["message"]
        self.assertNotIn("sage/asset_overrides/agents/leader.md", nested_agent)
        self.assertNotIn("sage/asset_overrides/skills/sage-review.md", incomplete_skill)


class TestDispatchFailClosed(unittest.TestCase):
    def test_write_guard_dispatches_without_subprocess(self):
        raw = json.dumps({"tool_input": {"file_path": ".codex/agents/a.md"}})
        with mock.patch("subprocess.run", side_effect=AssertionError("subprocess must not run")):
            self.assertEqual(run_hook.dispatch("codex", "generated-artifact-write-guard",
                                               str(REPO), str(HOOKS_DIR), raw), 2)

    def test_core_exception_is_diagnostic_exit_two(self):
        stderr = StringIO()
        with mock.patch("importlib.import_module", side_effect=RuntimeError("boom")):
            with redirect_stderr(stderr):
                rc = hr.run_generated_artifact_write_guard("{}", str(HOOKS_DIR))
        self.assertEqual(rc, 2)
        # 산문이 아니라 code 를 본다 — 문장은 언어를 타지만 code 는 타지 않는다.
        self.assertIn("runtime.core_failure", stderr.getvalue())
        self.assertIn("Next: ", stderr.getvalue())
        self.assertIn("RuntimeError", stderr.getvalue())

    def test_legacy_direct_path_inputs_remain_supported_by_both_adapters(self):
        guarded = ".codex/agents/direct-call.md"
        for runtime in ("claude", "codex"):
            adapter = HOOKS_DIR / "adapters" / runtime / "generated-artifact-write-guard.sh"
            env = os.environ.copy()
            env.update({
                "SAGE_PYTHON": sys.executable,
                "SAGE_HOOK_CORE_DIR": str(HOOKS_DIR),
                "CLAUDE_PROJECT_DIR": str(REPO),
                "CODEX_PROJECT_ROOT": str(REPO),
            })
            with self.subTest(runtime=runtime, source="--path"):
                result = subprocess.run(
                    ["bash", str(adapter), "--path", guarded],
                    input="", capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 2, result.stderr)
            with self.subTest(runtime=runtime, source="SAGE_GUARD_PATH"):
                env["SAGE_GUARD_PATH"] = guarded
                result = subprocess.run(
                    ["bash", str(adapter)],
                    input="", capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 2, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
