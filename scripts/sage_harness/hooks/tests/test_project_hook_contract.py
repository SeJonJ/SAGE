#!/usr/bin/env python3
"""project hook spec 계약 — 판정이 **어떤 code 를 내는지** 고정한다.

이관 전에는 이 모듈의 판정을 확인하는 테스트가 없었다. 호출부가 exit 2 만 보고 있어서,
어떤 위반이든 같은 종료 코드로 수렴하면 판정이 바뀌어도 아무도 모른다. 문구는 catalog
소유라 문장으로 고정하지 않고 code 와 named argument 로 고정한다.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from sage.project_hook_contract import _binding_issue, inspect_project_hook  # noqa: E402

_OK_CLAUDE = {"event": "PreToolUse", "matcher": "Write|Edit", "timeout": 10}
_OK_CODEX = {"event": "PreToolUse", "matcher": "apply_patch", "timeout": 10}


def _code(diagnostic):
    return getattr(diagnostic, "code", None)


class TestBindingIssueCodes(unittest.TestCase):
    def test_valid_bindings_produce_no_diagnostic(self):
        self.assertIsNone(_binding_issue("claude", _OK_CLAUDE))
        self.assertIsNone(_binding_issue("codex", _OK_CODEX))

    def test_each_violation_has_its_own_code(self):
        cases = [
            ("claude", "not a mapping", "binding.not_mapping"),
            ("claude", dict(_OK_CLAUDE, extra=1), "binding.unknown_fields"),
            ("claude", dict(_OK_CLAUDE, event="PostToolUse"), "binding.event_invalid"),
            ("claude", dict(_OK_CLAUDE, timeout=0), "binding.timeout_invalid"),
            ("claude", dict(_OK_CLAUDE, timeout=601), "binding.timeout_invalid"),
            # bool 은 int 의 subclass 라 `isinstance` 로 검사하면 통과한다 — 그 구멍을 고정한다.
            ("claude", dict(_OK_CLAUDE, timeout=True), "binding.timeout_invalid"),
            ("claude", dict(_OK_CLAUDE, matcher=""), "binding.matcher_not_string"),
            ("claude", dict(_OK_CLAUDE, matcher=3), "binding.matcher_not_string"),
            ("claude", dict(_OK_CLAUDE, matcher=" Write"), "binding.matcher_whitespace"),
            ("claude", dict(_OK_CLAUDE, matcher="Write| Edit"), "binding.matcher_token_blank"),
            ("claude", dict(_OK_CLAUDE, matcher="Write||Edit"), "binding.matcher_token_blank"),
            ("claude", dict(_OK_CLAUDE, matcher="Write|Write"), "binding.matcher_token_duplicated"),
            ("claude", dict(_OK_CLAUDE, matcher="Write|Bash"), "binding.matcher_not_subset"),
            ("codex", dict(_OK_CODEX, matcher="Write"), "binding.matcher_not_apply_patch"),
        ]
        for host, value, expected in cases:
            with self.subTest(host=host, expected=expected):
                self.assertEqual(_code(_binding_issue(host, value)), expected)

    def test_the_diagnostic_names_the_binding_it_judged(self):
        issue = _binding_issue("codex", "nope")
        self.assertEqual(issue.arguments["where"], "runtime_bindings.codex")


class TestInspectProjectHookCodes(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.root = self._tmp
        os.makedirs(os.path.join(self.root, "docs", "sage_harness", "hooks"))
        os.makedirs(os.path.join(self.root, "scripts", "sage_harness", "hooks"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write(self, hook_id, spec, core='CONTRACT_VERSION = "1"\n'):
        if spec is not None:
            Path(self.root, "docs", "sage_harness", "hooks",
                 f"{hook_id}.md").write_text(spec, encoding="utf-8")
        if core is not None:
            Path(self.root, "scripts", "sage_harness", "hooks",
                 f"{hook_id.replace('-', '_')}_core.py").write_text(core, encoding="utf-8")

    def _codes(self, hook_id):
        _metadata, issues = inspect_project_hook(self.root, hook_id)
        return [_code(item) for item in issues]

    def test_malformed_id_is_rejected_before_any_file_is_read(self):
        self.assertEqual(self._codes("Not_Kebab"), ["hook_spec.id_invalid"])

    def test_missing_spec_and_missing_core_are_distinct(self):
        self.assertEqual(self._codes("absent"), ["hook_spec.spec_missing"])
        self._write("half", "---\nid: half\n---\n", core=None)
        self.assertEqual(self._codes("half"), ["hook_spec.core_missing"])

    def test_frontmatter_shape_violations_carry_their_own_codes(self):
        for spec, expected in (
                ("no frontmatter at all\n", "hook_spec.frontmatter_missing"),
                ("---\n- a\n- b\n---\n", "hook_spec.frontmatter_not_mapping"),
                ("---\n1: x\n---\n", "hook_spec.frontmatter_key_not_string")):
            with self.subTest(expected=expected):
                self._write("shape", spec)
                self.assertEqual(self._codes("shape"), [expected])

    def test_parse_failure_keeps_the_external_text_as_evidence(self):
        self._write("broken", "---\nid: [unclosed\n---\n")
        _metadata, issues = inspect_project_hook(self.root, "broken")
        self.assertEqual(_code(issues[0]), "hook_spec.parse_failed")
        self.assertTrue(issues[0].evidence, "파서 원문이 사라졌다 — 사용자가 검색할 수 없다")

    def test_field_level_violations_are_reported_together(self):
        self._write("many", "---\nid: other\nkind: skill\nextra: 1\n"
                            "runtime_bindings:\n  claude: {}\n---\n")
        self.assertEqual(
            self._codes("many"),
            ["hook_spec.unknown_fields", "hook_spec.id_mismatch", "hook_spec.kind_invalid",
             "hook_spec.bindings_hosts", "binding.event_invalid", "binding.not_mapping"])

    def test_missing_contract_version_in_core_is_its_own_code(self):
        self._write("plain",
                    "---\nid: plain\nkind: hook\nruntime_bindings:\n"
                    "  claude: {event: PreToolUse, matcher: Write}\n"
                    "  codex: {event: PreToolUse, matcher: apply_patch}\n---\n",
                    core="# no constant here\n")
        self.assertEqual(self._codes("plain"), ["hook_spec.core_missing_contract_version"])

    def test_a_wholly_valid_spec_produces_no_issues(self):
        self._write("good",
                    "---\nid: good\nkind: hook\nruntime_bindings:\n"
                    "  claude: {event: PreToolUse, matcher: Write}\n"
                    "  codex: {event: PreToolUse, matcher: apply_patch}\n---\n")
        metadata, issues = inspect_project_hook(self.root, "good")
        self.assertEqual(issues, [])
        self.assertEqual(metadata["id"], "good")


class TestRunAllRegistration(unittest.TestCase):
    def test_this_suite_is_wired(self):
        here = Path(__file__).resolve().parent
        self.assertIn("test_project_hook_contract.py",
                      (here / "run-all.sh").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
