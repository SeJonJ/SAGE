#!/usr/bin/env python3
"""진단 code 의 severity·복구 계약.

`Diagnostic` 은 439 곳에서 쓰이고 시그니처가 계약이다. 그래서 severity 와 recovery 를 그 클래스에
필드로 밀어 넣지 않는다. 둘 다 **진단 인스턴스의 속성이 아니라 code 의 속성**이다 — 같은 code 가
어떤 호출부에서는 WARN 이고 다른 곳에서는 BLOCK 이면 그 code 는 안정 식별자이길 그만둔다.

그리고 recovery 를 생성 인자로 두면 439 곳이 각자 복구 명령을 적을 수 있다. "같은 recovery id 는
같은 명령" 을 검사로 뒤늦게 잡는 것보다, 애초에 갈릴 수 없는 자리에 두는 편이 낫다.
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)

from sage.diagnostics import Diagnostic, render  # noqa: E402
from sage.diagnostic_contract import (  # noqa: E402
    BLOCK, INFO, WARN, Finding, RecoveryStep, contract_issues, order, recovery_for, severity_of,
)


class TestExistingDiagnosticIsUntouched(unittest.TestCase):
    """가산 확장의 전제 — 기존 시그니처와 렌더가 그대로다."""

    def test_signature_still_takes_code_evidence_and_arguments(self):
        d = Diagnostic("some.code", evidence="raw text", name="x")
        self.assertEqual(d.code, "some.code")
        self.assertEqual(d.evidence, "raw text")
        self.assertEqual(d.arguments, {"name": "x"})

    def test_diagnostic_has_no_severity_or_recovery_field(self):
        d = Diagnostic("some.code")
        for field in ("severity", "recovery", "message_key", "subject"):
            with self.subTest(field=field):
                self.assertFalse(hasattr(d, field))

    def test_render_still_builds_the_key_from_prefix_and_code(self):
        seen = {}

        def translate(key, **kw):
            seen["key"] = key
            return "문장"

        self.assertEqual(render(Diagnostic("gate.phase_incomplete"), translate, "hook"), "문장")
        self.assertEqual(seen["key"], "hook.gate.phase_incomplete")


class TestSeverity(unittest.TestCase):
    def test_unregistered_code_defaults_to_info(self):
        # 439 개 기존 진단은 등재되지 않았고, 등재되지 않았다는 이유로 화면이 바뀌면 안 된다.
        self.assertEqual(severity_of("never.registered.anywhere"), INFO)

    def test_registered_block_code(self):
        self.assertEqual(severity_of("runtime.api_too_old"), BLOCK)

    def test_severity_is_a_property_of_the_code_not_the_instance(self):
        a = Diagnostic("runtime.api_too_old", evidence="one")
        b = Diagnostic("runtime.api_too_old", evidence="two")
        self.assertEqual(severity_of(a.code), severity_of(b.code))


class TestRecoveryOwnership(unittest.TestCase):
    def test_every_block_code_has_recovery(self):
        from sage.diagnostic_contract import SEVERITY
        for code, severity in SEVERITY.items():
            if severity == BLOCK:
                with self.subTest(code=code):
                    self.assertTrue(recovery_for(code), f"{code} 에 recovery 가 없다")

    def test_every_block_recovery_has_an_executable_command(self):
        from sage.diagnostic_contract import SEVERITY
        for code, severity in SEVERITY.items():
            if severity == BLOCK:
                with self.subTest(code=code):
                    self.assertTrue(any(step.command for step in recovery_for(code)),
                                    f"{code} 의 복구가 전부 수동 지시다")

    def test_unregistered_code_has_empty_recovery(self):
        self.assertEqual(recovery_for("never.registered.anywhere"), ())

    def test_recovery_is_immutable(self):
        self.assertIsInstance(recovery_for("runtime.api_too_old"), tuple)

    def test_mutating_steps_form_a_single_contiguous_phase(self):
        """복구는 `확인 → 수정 → 재검증` 이다.

        읽기 전용이 mutation 뒤에 오는 것은 정상이다 — 그게 재검증이다. 막아야 하는 것은
        고치고·보고·또 고치는 순서다. 그러면 중간에 멈춘 사용자가 어디까지 했는지 잃는다.
        """
        from sage.diagnostic_contract import SEVERITY
        for code, severity in SEVERITY.items():
            if severity != BLOCK:
                continue
            flags = [step.mutating for step in recovery_for(code)]
            blocks = sum(1 for i, f in enumerate(flags) if f and not (i and flags[i - 1]))
            with self.subTest(code=code):
                self.assertLessEqual(blocks, 1, f"{code}: mutation 이 {blocks} 덩어리로 흩어졌다")

    def test_scattered_mutation_phases_are_reported(self):
        fix_a = RecoveryStep("fix-a", "sage install --host x --force --dest .", "d", mutating=True)
        look = RecoveryStep("look", "sage status", "d", mutating=False)
        fix_b = RecoveryStep("fix-b", "sage generate --kind hook --write", "d", mutating=True)
        issues = contract_issues(severity={"x": BLOCK}, recovery={"x": (fix_a, look, fix_b)})
        self.assertTrue(any("덩어리" in i for i in issues))


class TestContractSelfCheck(unittest.TestCase):
    """계약이 자기 자신에 대해 강제하는 것. oracle 이 여기를 부른다."""

    def test_the_shipped_contract_is_clean(self):
        self.assertEqual(contract_issues(), [])

    def test_a_block_without_recovery_is_reported(self):
        issues = contract_issues(severity={"x.block": BLOCK}, recovery={})
        self.assertTrue(any("x.block" in i for i in issues))

    def test_a_block_with_only_manual_steps_is_reported(self):
        step = RecoveryStep("manual-only", None, "d", mutating=False)
        issues = contract_issues(severity={"x.block": BLOCK}, recovery={"x.block": (step,)})
        self.assertTrue(any("x.block" in i for i in issues))

    def test_the_same_recovery_id_may_not_carry_two_commands(self):
        a = RecoveryStep("same-id", "sage status", "d", mutating=False)
        b = RecoveryStep("same-id", "sage doctor", "d", mutating=False)
        issues = contract_issues(severity={"p": BLOCK, "q": BLOCK},
                                 recovery={"p": (a,), "q": (b,)})
        self.assertTrue(any("same-id" in i for i in issues))

    def test_the_same_recovery_id_with_the_same_command_is_fine(self):
        a = RecoveryStep("same-id", "sage status", "d", mutating=False)
        b = RecoveryStep("same-id", "sage status", "d", mutating=False)
        issues = contract_issues(severity={"p": BLOCK, "q": BLOCK},
                                 recovery={"p": (a,), "q": (b,)})
        self.assertEqual(issues, [])

    def test_forbidden_commands_are_reported(self):
        for command in ("rm -rf .sage",
                        "rm .sage/loop_audit.jsonl",
                        "git reset --hard origin/main",
                        "git clean -fd",
                        "sage override grant --all",
                        "truncate -s 0 .sage/override.jsonl"):
            with self.subTest(command=command):
                step = RecoveryStep("bad", command, "d", mutating=True)
                issues = contract_issues(severity={"x": BLOCK}, recovery={"x": (step,)})
                self.assertTrue(any("bad" in i for i in issues), f"{command} 가 통과했다")

    def test_recovery_for_an_unregistered_severity_is_reported(self):
        step = RecoveryStep("s", "sage status", "d", mutating=False)
        issues = contract_issues(severity={}, recovery={"orphan": (step,)})
        self.assertTrue(any("orphan" in i for i in issues))


class TestOrdering(unittest.TestCase):
    def test_block_then_warn_then_info(self):
        findings = [Finding("z.info"), Finding("a.warn"), Finding("m.block")]
        severity = {"m.block": BLOCK, "a.warn": WARN, "z.info": INFO}
        got = [f.code for f in order(findings, severity_of=severity.get)]
        self.assertEqual(got, ["m.block", "a.warn", "z.info"])

    def test_codes_sort_within_one_severity(self):
        findings = [Finding("b"), Finding("c"), Finding("a")]
        got = [f.code for f in order(findings)]
        self.assertEqual(got, ["a", "b", "c"])

    def test_ordering_is_deterministic_across_input_permutations(self):
        import itertools
        severity = {"m.block": BLOCK, "a.warn": WARN, "z.info": INFO}
        expected = None
        for perm in itertools.permutations(["m.block", "a.warn", "z.info"]):
            got = [f.code for f in order([Finding(c) for c in perm], severity_of=severity.get)]
            expected = expected or got
            self.assertEqual(got, expected)


class TestFindingJson(unittest.TestCase):
    def test_json_keys_are_fixed(self):
        payload = Finding("runtime.api_too_old", evidence={"required_api": 2}).to_json()
        self.assertEqual(set(payload), {"code", "severity", "evidence", "recovery"})

    def test_json_carries_no_translated_sentence(self):
        payload = Finding("runtime.api_too_old", evidence={"required_api": 2},
                          arguments={"host": "codex"}).to_json()
        # arguments 는 catalog template 에 넘길 렌더용 값이다 → 번역 문장의 조각이므로 JSON 밖.
        self.assertNotIn("arguments", payload)
        self.assertNotIn("message", payload)

    def test_recovery_in_json_is_id_command_and_mutating(self):
        payload = Finding("runtime.api_too_old").to_json()
        for step in payload["recovery"]:
            self.assertEqual(set(step), {"id", "command", "mutating"})

    def test_evidence_defaults_to_an_empty_mapping(self):
        self.assertEqual(Finding("x").to_json()["evidence"], {})

    def test_finding_renders_through_the_existing_diagnostic_path(self):
        seen = {}

        def translate(key, **kw):
            seen.update(key=key, kw=kw)
            return "문장"

        f = Finding("runtime.api_too_old", arguments={"required": 2})
        self.assertEqual(render(f.diagnostic(), translate, "cli"), "문장")
        self.assertEqual(seen["key"], "cli.runtime.api_too_old")
        self.assertEqual(seen["kw"], {"required": 2})


class TestCompletenessOracle(unittest.TestCase):
    """검사에 이빨이 있는가. 무치인 검사는 없는 검사보다 나쁘다 — 초록으로 보이기 때문이다."""

    def _hook_recovery(self):
        import sys as _sys
        runtime = os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime")
        if runtime not in _sys.path:
            _sys.path.insert(0, runtime)
        import recovery
        return recovery

    def test_the_shipped_repository_is_clean(self):
        from sage.i18n.validation import recovery_issues
        self.assertEqual(recovery_issues(REPO), [])

    def test_every_block_message_key_has_a_code(self):
        from sage.i18n.validation import NOT_MESSAGE_KEYS, load_hook_catalogs
        hook = self._hook_recovery()
        keys = {k for k in load_hook_catalogs(REPO).get("ko", {})
                if k.startswith("block_")} - set(NOT_MESSAGE_KEYS)
        self.assertEqual(sorted(keys - set(hook.CODE_OF)), [])

    def test_the_four_non_keys_are_not_codes(self):
        from sage.i18n.validation import NOT_MESSAGE_KEYS
        hook = self._hook_recovery()
        for name in NOT_MESSAGE_KEYS:
            with self.subTest(name=name):
                self.assertNotIn(name, hook.CODE_OF)

    def test_every_hook_block_code_has_an_executable_command(self):
        hook = self._hook_recovery()
        for code in set(hook.CODE_OF.values()) | set(hook.GUARD_CODES):
            with self.subTest(code=code):
                steps = hook.steps_for(code)
                self.assertTrue(steps, f"{code} 에 복구 순서가 없다")
                self.assertTrue(any(command for _i, command, _k, _m in steps),
                                f"{code} 의 복구가 전부 수동 지시다")

    def test_shared_recovery_ids_carry_the_same_command_on_both_sides(self):
        from sage.diagnostic_contract import RECOVERY as CLI
        hook = self._hook_recovery()
        cli = {}
        for steps in CLI.values():
            for step in steps:
                cli.setdefault(step.id, step.command)
        shared = 0
        for steps in hook.RECOVERY.values():
            for step_id, command, _k, _m in steps:
                if step_id in cli:
                    shared += 1
                    self.assertEqual(cli[step_id], command, f"{step_id} 가 갈렸다")
        # 공유가 0 이면 위 비교는 아무것도 검사하지 않는다.
        self.assertGreater(shared, 0, "양쪽이 공유하는 recovery id 가 하나도 없다")

    def test_the_hook_recovery_module_does_not_import_the_engine(self):
        path = os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime", "recovery.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("import sage", source)
        self.assertNotIn("from sage", source)


class TestRunAllRegistration(unittest.TestCase):
    def test_this_suite_is_wired(self):
        from pathlib import Path
        here = Path(os.path.dirname(os.path.abspath(__file__)))
        self.assertIn("test_recovery_contract.py",
                      (here / "run-all.sh").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
