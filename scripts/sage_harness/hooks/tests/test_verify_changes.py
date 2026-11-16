#!/usr/bin/env python3
"""Exercise the bundled verification runner in disposable project directories."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[4]
SCRIPT = REPO / "templates/core/framework/scripts/verify-changes.sh"


class VerifyChangesTests(unittest.TestCase):
    def run_checks(self, commands=None, level="L2", alternate=False):
        with tempfile.TemporaryDirectory(prefix="sage-verify-") as tmp:
            root = Path(tmp)
            env = dict(os.environ)
            env.pop("SAGE_PROFILE", None)
            if commands is not None:
                profile = root / ("other profile.yaml" if alternate else "sage/project-profile.yaml")
                profile.parent.mkdir(parents=True, exist_ok=True)
                profile.write_text("verification:\n  commands:\n" + "".join(
                    f'    {key}: "{command}"\n' for key, command in commands.items()
                ), encoding="utf-8")
                if alternate:
                    env["SAGE_PROFILE"] = str(profile)
            result = subprocess.run(["bash", str(SCRIPT), level], cwd=root, env=env,
                                    stdin=subprocess.DEVNULL, text=True, capture_output=True)
            marker = root / "execution.log"
            return result, marker.read_text() if marker.exists() else ""

    def test_absent_profile_reports_no_evidence_without_changing_exit_code(self):
        result, marker = self.run_checks()
        self.assertEqual(result.returncode, 0)
        self.assertIn("NO_EVIDENCE", result.stdout)
        self.assertIn("skipped=unknown", result.stdout)
        self.assertNotIn("verify-changes: PASS", result.stdout)
        self.assertEqual(marker, "")

    def test_empty_commands_do_not_report_pass(self):
        for commands in ({}, {"build": "", "test": "", "lint": ""}):
            with self.subTest(commands=commands):
                result, marker = self.run_checks(commands)
                self.assertEqual(result.returncode, 0)
                self.assertIn("NO_EVIDENCE (executed=0; skipped=3)", result.stdout)
                self.assertIn("skipped checks: build test lint", result.stdout)
                self.assertNotIn("verify-changes: PASS", result.stdout)
                self.assertEqual(marker, "")

    def test_partial_success_names_only_executed_scope(self):
        result, marker = self.run_checks({"build": "printf B >> execution.log"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(marker, "B")
        self.assertIn("PASS (executed=1; skipped=2)", result.stdout)
        self.assertIn("executed checks: build", result.stdout)
        self.assertIn("skipped checks: test lint", result.stdout)

    def test_all_commands_execute_in_original_order(self):
        result, marker = self.run_checks({
            "lint": "printf L >> execution.log", "test": "printf T >> execution.log",
            "build": "printf B >> execution.log"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(marker, "BTL")
        self.assertIn("PASS (executed=3; skipped=0)", result.stdout)
        self.assertIn("skipped checks: (none)", result.stdout)

    def test_failure_remains_failure_and_later_commands_still_run(self):
        result, marker = self.run_checks({
            "build": "printf B >> execution.log; exit 7",
            "test": "printf T >> execution.log"})
        self.assertEqual(result.returncode, 1)
        self.assertEqual(marker, "BT")
        self.assertIn("FAIL: build", result.stderr)
        self.assertIn("FAIL (executed=2; skipped=1)", result.stderr)
        self.assertNotIn("verify-changes: PASS", result.stdout)

    def test_syntax_only_level_does_not_run_build(self):
        result, marker = self.run_checks({
            "syntax": "printf S >> execution.log", "build": "printf B >> execution.log"}, "L1")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(marker, "S")
        self.assertIn("PASS (executed=1; skipped=0)", result.stdout)
        self.assertIn("executed checks: syntax", result.stdout)

    def test_undeclared_syntax_is_no_evidence(self):
        result, marker = self.run_checks({"build": "printf B >> execution.log"}, "L1")
        self.assertEqual(result.returncode, 0)
        self.assertIn("NO_EVIDENCE (executed=0; skipped=1)", result.stdout)
        self.assertEqual(marker, "")

    def test_l3_preserves_same_command_selection(self):
        result, marker = self.run_checks({"lint": "printf L >> execution.log"}, "L3")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(marker, "L")
        self.assertIn("PASS (executed=1; skipped=2)", result.stdout)

    def test_profile_override_with_spaces_is_honored(self):
        result, marker = self.run_checks({"test": "printf T >> execution.log"}, alternate=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(marker, "T")
        self.assertIn("executed checks: test", result.stdout)

    def test_invalid_level_keeps_existing_error_status(self):
        result, marker = self.run_checks({}, "invalid")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown level", result.stderr)
        self.assertEqual(marker, "")


if __name__ == "__main__":
    unittest.main()
