#!/usr/bin/env python3
"""사용자 승인 기반 리뷰 라운드 조기 완료.

이 기능은 반복 횟수 면제가 아니라 **잔여 비차단 위험의 명시적 인수**다. 정상 수렴이 가능한 상태
에서는 쓰지 않으며, 차단 심각도 finding·architecture escalation·검증 실패·감사 손상은 사용자
확인으로도 통과하지 못한다. 그래서 이 파일의 대부분은 "닫히면 안 되는 상태" 목록이다.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HOOKS_DIR)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))

from sage.profile_validate import validate_profile  # noqa: E402

import loop_audit as la  # noqa: E402


class TestEarlyCompletionOptIn(unittest.TestCase):
    def _fails(self, early):
        """early_completion 이 만든 FAIL 만 본다 — 최소 profile 의 다른 결핍과 섞지 않는다."""
        profile = {"pdca": {"review_loop": {"enabled": True, "early_completion": early}}}
        return [str(message) for severity, message in validate_profile(profile, REPO)
                if severity == "FAIL" and "early_completion" in str(message)]

    def test_absent_block_stays_valid(self):
        profile = {"pdca": {"review_loop": {"enabled": True}}}
        fails = [m for s, m in validate_profile(profile, REPO) if s == "FAIL"]
        self.assertEqual([str(m) for m in fails if "early_completion" in str(m)], [])

    def test_enabled_flag_and_raised_floor_validate(self):
        self.assertEqual(self._fails({"enabled": False}), [])
        self.assertEqual(self._fails({"enabled": True, "minimum_completed_rounds": 2}), [])

    def test_floor_cannot_be_lowered_below_one(self):
        """0 을 허용하면 '리뷰 0라운드 승인' 이 설정 한 줄로 열린다."""
        for value in (0, -1, True, 1.0):
            self.assertNotEqual(self._fails({"enabled": True, "minimum_completed_rounds": value}),
                                [], repr(value))

    def test_unknown_key_and_non_bool_enabled_are_rejected(self):
        self.assertNotEqual(self._fails({"enabled": True, "typo": 1}), [])
        self.assertNotEqual(self._fails({"enabled": "true"}), [])


class TestSeverityReceipt(unittest.TestCase):
    """합계 강제가 없으면 P0=0 만 적어 차단 finding 을 숨길 수 있다."""

    def test_exact_total_is_required(self):
        self.assertEqual(la.severity_receipt_issues({"P0": 0, "P1": 0, "P2": 2, "P3": 0}, 2), [])
        self.assertNotEqual(la.severity_receipt_issues({"P0": 0, "P1": 0, "P2": 1, "P3": 0}, 2), [])

    def test_missing_unknown_negative_and_bool_are_rejected(self):
        cases = (
            {"P0": 0, "P1": 0, "P2": 2},
            {"P0": 0, "P1": 0, "P2": 2, "P3": 0, "P9": 0},
            {"P0": -1, "P1": 0, "P2": 3, "P3": 0},
            {"P0": True, "P1": 0, "P2": 1, "P3": 0},
            {"P0": "0", "P1": 0, "P2": 2, "P3": 0},
            ["P0=0"],
        )
        for receipt in cases:
            self.assertNotEqual(la.severity_receipt_issues(receipt, 2), [], repr(receipt))


class TestEarlyCloseCLI(unittest.TestCase):
    RISK = "L3"

    def setUp(self):
        import yaml  # noqa: PLC0415

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        Path(self.root, "sage").mkdir()
        self.profile = {"pdca": {
            "phases": [{"id": "00", "glob": "plan_docs/00-base_plan/**/*.md"}],
            "review_loop": {
                "enabled": True,
                "lenses": {"L2": ["correctness", "error_handling"],
                           "L3": ["correctness", "security", "data_integrity"]},
                "refuters": {"L2": 1, "L3": 1},
                "max_iterations": {"L2": 2, "L3": 3},
                "budget_tokens": {"L2": 100000, "L3": 200000},
                "severity_block": ["P0", "P1"],
                "early_completion": {"enabled": True, "minimum_completed_rounds": 1},
            },
        }}
        self._write_profile()
        self.run_id = None

    def _write_profile(self):
        import yaml  # noqa: PLC0415
        Path(self.root, "sage", "project-profile.yaml").write_text(
            yaml.safe_dump(self.profile, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def _run(self, *args):
        env = dict(os.environ, PYTHONPATH=REPO)
        return subprocess.run([sys.executable, "-m", "sage", "review-loop", *args,
                               "--root", self.root],
                              text=True, capture_output=True, env=env, cwd=self.root)

    def _open(self):
        result = self._run("open", "--risk", self.RISK)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.run_id = result.stdout.strip().split()[-1]
        return self.run_id

    def _round(self, iteration=1, found=3, survived=2, accepted=1, arch=0,
               severity="P0=0,P1=0,P2=2,P3=0"):
        args = ["round", "--run-id", self.run_id, "--iteration", str(iteration),
                "--found", str(found), "--survived", str(survived),
                "--accepted", str(accepted), "--arch", str(arch)]
        if severity is not None:
            args += ["--survived-by-severity", severity]
        return self._run(*args)

    def _close(self, **over):
        argv = {"--run-id": self.run_id, "--result": "APPROVED",
                "--reason": "USER_AUTHORIZED_EARLY", "--iterations": "1",
                "--authorization-reason": "배포 창구가 오늘 닫힌다",
                "--confirmed-by": "sejon", "--confirm": "USER_AUTHORIZED_EARLY"}
        argv.update(over)
        flat = [item for pair in argv.items() for item in pair if item is not None]
        return self._run("close", *flat)

    def _records(self):
        path = Path(self.root, ".sage", "loop_audit.jsonl")
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def _closes(self):
        return [r for r in self._records() if r.get("event") == "loop_close"]

    def test_a_continuing_loop_with_no_blocking_severity_can_close_early(self):
        self._open()
        self.assertEqual(self._round().returncode, 0)
        result = self._close()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SAGE REVIEW EARLY COMPLETION", result.stderr)
        close = self._closes()[-1]
        self.assertEqual(close["result"], "APPROVED")
        self.assertEqual(close["reason"], "USER_AUTHORIZED_EARLY")
        self.assertEqual(close["review_assurance"], "REDUCED_BY_USER_AUTHORIZATION")
        self.assertEqual(close["attestation"], "self_asserted_local")
        self.assertEqual(close["completed_rounds"], 1)
        self.assertEqual(close["configured_max_iterations"], 3)
        self.assertEqual(close["survived_by_severity"], {"P0": 0, "P1": 0, "P2": 2, "P3": 0})
        self.assertEqual(close["confirmed_by"], "sejon")
        self.assertEqual(close["actual_risk"], "L3")
        self.assertEqual(close["mode"], "STANDARD")

    def test_an_unset_ceiling_is_recorded_as_unbounded_not_as_minus_one(self):
        """상한이 설정되지 않은 프로젝트에서 감사에 `-1` 이 남으면, 그 값은 "상한 없음" 이
        아니라 "라운드 -1 회" 로 읽힌다 — 대시보드가 `1/-1 rounds` 를 냈다. 레코드 필드는
        None 을 받을 수 없으므로(조기 종료 계약이 누락을 거부한다) 값 자체가 뜻을 말해야 한다.
        """
        self.profile["pdca"]["review_loop"].pop("max_iterations")
        self._write_profile()
        self._open()
        self.assertEqual(self._round().returncode, 0)
        result = self._close()
        self.assertEqual(result.returncode, 0, result.stderr)
        close = self._closes()[-1]
        self.assertEqual(close["configured_max_iterations"], la.UNBOUNDED_ITERATIONS)
        self.assertIn(f"ceiling: {la.UNBOUNDED_ITERATIONS}", result.stderr)

    def test_every_refusal_writes_no_close(self):
        self._open()
        self.assertEqual(self._round().returncode, 0)
        cases = {
            "wrong confirm token": {"--confirm": "yes"},
            # 두 기능의 확인 토큰은 서로의 승인이 아니다. 하나로 다른 하나를 열면 사용자가
            # 승인한 것과 실제로 일어난 일이 갈린다.
            "the other feature's token": {"--confirm": "FAST-CONVERTED"},
            "no confirm token": {"--confirm": None},
            "no authorization reason": {"--authorization-reason": None},
            "blank authorization reason": {"--authorization-reason": "  "},
            "no approver": {"--confirmed-by": None},
            "blocked result": {"--result": "BLOCKED", "--reason": "BLOCKED_ARCH"},
            "iterations mismatch": {"--iterations": "2"},
        }
        for label, over in cases.items():
            with self.subTest(label=label):
                self.assertEqual(self._close(**over).returncode, 2, label)
                self.assertEqual(self._closes(), [], label)

    def test_a_bad_floor_is_not_reported_as_a_missing_opt_in(self):
        """`enabled: true` 를 분명히 적은 사용자가 "enabled=true 가 필요하다" 를 듣는다면,
        무엇을 고칠지 알 방법이 없다 — 하한 진단의 정본(`validate`)은 이 명령을 지나지 않는다.
        """
        self._open()
        self.assertEqual(self._round().returncode, 0)
        for bad in (0, "2", True):
            with self.subTest(floor=bad):
                self.profile["pdca"]["review_loop"]["early_completion"] = {
                    "enabled": True, "minimum_completed_rounds": bad}
                self._write_profile()
                result = self._close()
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("minimum_completed_rounds", result.stderr)
                self.assertNotIn("enabled=true is required", result.stderr)
                self.assertEqual(self._closes(), [])

    def test_a_missing_opt_in_still_says_so(self):
        self._open()
        self.assertEqual(self._round().returncode, 0)
        self.profile["pdca"]["review_loop"].pop("early_completion")
        self._write_profile()
        result = self._close()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("enabled=true is required", result.stderr)

    def test_a_damaged_audit_cannot_be_closed_early(self):
        """조기 종료는 감사 위에 승인 레코드를 얹는 조작이다.

        밑에 깔린 기록이 손상됐으면 얹으면 안 된다 — 손상된 감사에 남은 승인은 사후에 무엇이
        참인지 판별할 수 없다.
        """
        self._open()
        self.assertEqual(self._round().returncode, 0)
        path = Path(self.root, ".sage", "loop_audit.jsonl")
        lines = path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[-1])
        record["survived"] = record.get("survived", 0) + 7
        lines[-1] = json.dumps(record, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = self._close()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("integrity", result.stderr)
        self.assertEqual(self._closes(), [])

    def test_blocking_severity_cannot_be_waved_through(self):
        self._open()
        self.assertEqual(self._round(survived=2, severity="P0=0,P1=1,P2=1,P3=0").returncode, 0)
        result = self._close()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("blocking severities remain unresolved", result.stderr)
        self.assertEqual(self._closes(), [])

    def test_zero_rounds_never_closes_early(self):
        self._open()
        self.assertEqual(self._close(**{"--iterations": "0"}).returncode, 2)
        self.assertEqual(self._closes(), [])

    def test_architecture_escalation_is_not_an_early_completion(self):
        self._open()
        self.assertEqual(self._round(arch=1).returncode, 0)
        result = self._close()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self._closes(), [])

    def test_a_converged_loop_is_told_to_use_the_normal_close(self):
        self._open()
        self.assertEqual(self._round(found=2, survived=0, accepted=0,
                                     severity="P0=0,P1=0,P2=0,P3=0").returncode, 0)
        result = self._close()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("normal close is available", result.stderr)
        self.assertEqual(self._closes(), [])

    def test_a_legacy_round_without_a_receipt_cannot_close_early(self):
        self._open()
        self.assertEqual(self._round(severity=None).returncode, 0)
        result = self._close()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("survived_by_severity", result.stderr)
        self.assertEqual(self._closes(), [])
        # 같은 레거시 run 이라도 정상 수렴 경로는 계속 쓸 수 있다.
        self.assertEqual(self._round(iteration=2, found=1, survived=0, accepted=0,
                                     severity=None).returncode, 0)
        normal = self._run("close", "--run-id", self.run_id, "--result", "APPROVED",
                           "--reason", "CONVERGED", "--iterations", "2")
        self.assertEqual(normal.returncode, 0, normal.stderr)

    def test_the_opt_in_must_be_on(self):
        self.profile["pdca"]["review_loop"].pop("early_completion")
        self._write_profile()
        self._open()
        self.assertEqual(self._round().returncode, 0)
        self.assertEqual(self._close().returncode, 2)
        self.assertEqual(self._closes(), [])

    def test_a_raised_floor_is_honoured(self):
        self.profile["pdca"]["review_loop"]["early_completion"] = {
            "enabled": True, "minimum_completed_rounds": 2}
        self._write_profile()
        self._open()
        self.assertEqual(self._round().returncode, 0)
        self.assertEqual(self._close().returncode, 2)
        self.assertEqual(self._round(iteration=2).returncode, 0)
        self.assertEqual(self._close(**{"--iterations": "2"}).returncode, 0)

    def test_enforce_termination_mode_does_not_kill_the_feature(self):
        """조기 완료는 정의상 survived>0 인 APPROVED 다 — 수렴 검산이 그걸 모순으로 잡으면 안 된다.

        profile 주석이 `termination_enforce: enforce` 전환을 권장한다. 그 권장을 따른 프로젝트에서
        기능이 통째로 죽으면, 죽은 줄 모르고 쓰다가 배포 창구 앞에서 발견하게 된다.
        """
        self.profile["pdca"]["review_loop"]["termination_enforce"] = "enforce"
        self._write_profile()
        self._open()
        self.assertEqual(self._round().returncode, 0)
        result = self._close()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("종료 검산 불일치", result.stderr)
        self.assertEqual(self._closes()[-1]["reason"], "USER_AUTHORIZED_EARLY")

    def test_enforce_mode_still_rejects_a_genuinely_inconsistent_normal_close(self):
        """조기 종료 면제가 일반 close 의 검산까지 끄지 않는다."""
        self.profile["pdca"]["review_loop"]["termination_enforce"] = "enforce"
        self._write_profile()
        self._open()
        self.assertEqual(self._round(survived=2).returncode, 0)
        result = self._run("close", "--run-id", self.run_id, "--result", "APPROVED",
                           "--reason", "CONVERGED", "--iterations", "1")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self._closes(), [])

    def test_authorization_arguments_are_refused_on_a_normal_close(self):
        self._open()
        self.assertEqual(self._round(found=1, survived=0, accepted=0,
                                     severity="P0=0,P1=0,P2=0,P3=0").returncode, 0)
        result = self._run("close", "--run-id", self.run_id, "--result", "APPROVED",
                           "--reason", "CONVERGED", "--iterations", "1",
                           "--confirmed-by", "sejon")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self._closes(), [])

    def _with_phase00(self, done_mode="advisory", resolved=True):
        """Done Criteria 를 가진 Standard Phase 00 과 stem 결속을 붙인 fixture."""
        self.profile["pdca"]["base_plan"] = {"done_criteria_gate": done_mode}
        self._write_profile()
        mark = "x" if resolved else " "
        path = Path(self.root, "plan_docs", "00-base_plan", "demo.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# [기본 계획] demo\n\nCycle-Stem: `demo`\nRisk Level: L3\n"
            "Done-Criteria-Revision: 1\n\n"
            "## 5. Done Criteria\n\n"
            f"- [{mark}] demo behaviour is verified\n",
            encoding="utf-8")
        result = self._run("open", "--risk", self.RISK, "--cycle-stem", "demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.run_id = result.stdout.strip().split()[-1]

    def test_unresolved_done_criteria_blocks_early_completion_even_in_advisory(self):
        """일반 close 는 advisory 에서 경고만 낸다. 조기 종료에서는 그 경고가 곧 인수 대상이다."""
        self._with_phase00(done_mode="advisory", resolved=False)
        self.assertEqual(self._round().returncode, 0)
        result = self._close()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Done Criteria", result.stderr)
        self.assertEqual(self._closes(), [])

    def test_resolved_done_criteria_records_the_phase00_identity(self):
        """§7.7 의 stale 판정 축 두 개가 레코드에 남아야 한다."""
        self._with_phase00(done_mode="advisory", resolved=True)
        self.assertEqual(self._round().returncode, 0)
        result = self._close()
        self.assertEqual(result.returncode, 0, result.stderr)
        close = self._closes()[-1]
        self.assertTrue(close.get("phase00_hash"), close)
        self.assertEqual(close.get("done_criteria_revision"), 1, close)

    def test_a_project_with_the_gate_off_is_not_given_a_new_gate(self):
        """`done_criteria_gate: off` 프로젝트에 없던 검사를 조기 종료가 새로 켜지는 않는다."""
        self._with_phase00(done_mode="off", resolved=False)
        self.assertEqual(self._round().returncode, 0)
        result = self._close()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self._closes()[-1].get("phase00_hash"))

    def test_the_terminal_transition_happens_once(self):
        self._open()
        self.assertEqual(self._round().returncode, 0)
        self.assertEqual(self._close().returncode, 0)
        self.assertEqual(self._close().returncode, 2)
        self.assertEqual(self._round(iteration=2).returncode, 2)
        self.assertEqual(len(self._closes()), 1)

    def test_a_mismatched_receipt_is_refused_at_the_round(self):
        self._open()
        result = self._round(survived=2, severity="P0=0,P1=0,P2=1,P3=0")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual([r for r in self._records() if r.get("event") == "round"], [])


class TestReducedAssuranceBinding(unittest.TestCase):
    """05 문서의 보증 저하 표기와 terminal 감사 레코드는 함께 있거나 함께 없어야 한다."""

    def setUp(self):
        sys.path.insert(0, HOOKS_DIR)
        import pre_implementation_gate_core as core  # noqa: PLC0415

        self.core = core

    def _doc(self, **over):
        fields = {"Review-Assurance": "REDUCED_BY_USER_AUTHORIZATION",
                  "Review-Close-Reason": "USER_AUTHORIZED_EARLY",
                  "Review-Rounds": "2 (configured max: 3)",
                  "Residual-Findings": "P0=0, P1=0, P2=2, P3=0"}
        fields.update({k: v for k, v in over.items() if v is not None})
        for key, value in over.items():
            if value is None:
                fields.pop(key, None)
        body = "Final Status: APPROVED\nLoop-Run: rl-1\n"
        body += "".join(f"{key}: {value}\n" for key, value in fields.items())
        return body

    def _early_run(self, **over):
        run = {"close_reason": "USER_AUTHORIZED_EARLY", "completed_rounds": 2,
               "configured_max_iterations": 3,
               "survived_by_severity": {"P0": 0, "P1": 0, "P2": 2, "P3": 0}}
        run.update(over)
        return run

    def test_matching_document_and_audit_pass(self):
        self.assertEqual(self.core._reduced_assurance_issues(self._doc(), self._early_run()), [])

    def test_a_normal_close_may_not_carry_reduced_assurance_markers(self):
        issues = self.core._reduced_assurance_issues(self._doc(), {"close_reason": "CONVERGED"})
        self.assertNotEqual(issues, [])

    def test_an_early_close_without_markers_is_blocked(self):
        issues = self.core._reduced_assurance_issues("Final Status: APPROVED\n", self._early_run())
        self.assertNotEqual(issues, [])

    def test_partial_markers_are_blocked(self):
        for missing in ("Review-Assurance", "Review-Close-Reason", "Review-Rounds",
                        "Residual-Findings"):
            issues = self.core._reduced_assurance_issues(self._doc(**{missing: None}),
                                                         self._early_run())
            self.assertNotEqual(issues, [], missing)

    def test_duplicated_markers_are_blocked(self):
        doc = self._doc() + "Review-Assurance: REDUCED_BY_USER_AUTHORIZATION\n"
        self.assertNotEqual(self.core._reduced_assurance_issues(doc, self._early_run()), [])

    def test_round_count_and_residual_findings_must_match_the_audit(self):
        wrong_rounds = self._doc(**{"Review-Rounds": "3 (configured max: 3)"})
        self.assertNotEqual(self.core._reduced_assurance_issues(wrong_rounds, self._early_run()), [])
        wrong_residual = self._doc(**{"Residual-Findings": "P0=0, P1=0, P2=1, P3=0"})
        self.assertNotEqual(self.core._reduced_assurance_issues(wrong_residual, self._early_run()), [])

    def test_an_early_close_must_use_the_exact_marker_values(self):
        """표기가 4개 다 있어도 값이 다르면 조기 종료를 자칭한 것이 아니다.

        개수만 세면 `Review-Assurance: STANDARD` 로 닫힌 05 가 통과한다 — 감사에는 조기 종료가,
        문서에는 일반 승인이 남아 사후 판별이 불가능해진다.
        """
        for label, wrong in (("Review-Assurance", "STANDARD"),
                             ("Review-Close-Reason", "CONVERGED")):
            with self.subTest(label=label):
                doc = self._doc(**{label: wrong})
                self.assertNotEqual(
                    self.core._reduced_assurance_issues(doc, self._early_run()), [], label)

    def test_the_declared_ceiling_must_match_the_audit(self):
        """라운드 수만 대조하면 "몇 번 중 몇 번" 의 분모가 검증에서 빠진다.

        `2 (configured max: 3)` 를 `2 (configured max: 999)` 로 부풀리면 아직 한참 남은 리뷰를
        접은 것처럼, `2 (configured max: 2)` 로 낮추면 상한까지 다 돈 정상 승인처럼 읽힌다.
        네 표기를 강제하는 이유가 그 판별인데 분모만 자유롭게 적을 수 있었다.
        """
        for wrong in ("2 (configured max: 999)", "2 (configured max: 2)",
                      "2 (configured max: unbounded)", "2",
                      "2 (configured max: 3) (configured max: 999)"):
            with self.subTest(wrong=wrong):
                issues = self.core._reduced_assurance_issues(
                    self._doc(**{"Review-Rounds": wrong}), self._early_run())
                self.assertNotEqual(issues, [], wrong)

    def test_an_unset_ceiling_is_declared_with_the_same_word_the_audit_uses(self):
        """상한 없는 프로젝트의 분모는 숫자가 아니다. 화면·감사·문서가 같은 낱말을 써야
        `unbounded` 를 임의의 숫자로 바꿔 적는 자리가 생기지 않는다."""
        run = self._early_run(configured_max_iterations="unbounded")
        self.assertEqual(
            self.core._reduced_assurance_issues(
                self._doc(**{"Review-Rounds": "2 (configured max: unbounded)"}), run), [])
        self.assertNotEqual(
            self.core._reduced_assurance_issues(
                self._doc(**{"Review-Rounds": "2 (configured max: 3)"}), run), [])

    def test_a_record_without_a_ceiling_is_not_turned_into_a_ceiling_complaint(self):
        """감사에 상한이 없으면 대조 기준이 없다. 그때 상한 표기를 요구하면 손상된 레코드 하나가
        진단을 엉뚱한 이야기로 바꾼다 — 감사 손상은 무결성 검사가 말할 일이다."""
        run = self._early_run(configured_max_iterations=None)
        self.assertEqual(
            self.core._reduced_assurance_issues(self._doc(**{"Review-Rounds": "2"}), run), [])

    def test_a_normal_close_may_carry_neutral_review_lines(self):
        """`Review-Rounds` 는 일반 리뷰 문서에도 자연스럽게 적힌다. 차단 근거는 표기의 존재가
        아니라 문서가 보증 저하를 **자칭**하는 것이다."""
        for line in ("Review-Rounds: 3", "Residual-Findings: P0=0, P1=0, P2=0, P3=0",
                     "Review-Close-Reason: CONVERGED", "Review-Assurance: STANDARD"):
            with self.subTest(line=line):
                doc = f"Final Status: APPROVED\n{line}\n"
                self.assertEqual(
                    self.core._reduced_assurance_issues(doc, {"close_reason": "CONVERGED"}), [])

    def test_a_normal_close_may_not_claim_early_close_by_either_label(self):
        for line in ("Review-Assurance: REDUCED_BY_USER_AUTHORIZATION",
                     "Review-Close-Reason: USER_AUTHORIZED_EARLY"):
            with self.subTest(line=line):
                doc = f"Final Status: APPROVED\n{line}\n"
                self.assertNotEqual(
                    self.core._reduced_assurance_issues(doc, {"close_reason": "CONVERGED"}), [])

    def test_bold_labels_read_the_same_as_the_plain_ones(self):
        """같은 문서의 `**Final Status:**` 는 읽히는데 `**Review-Assurance:**` 만 안 읽히면,
        올바르게 적은 05 가 'found 0' 으로 막히고 작성자는 원인을 짐작할 수 없다."""
        bold = "".join(f"**{line.split(':', 1)[0]}:** {line.split(':', 1)[1].strip()}\n"
                       for line in self._doc().strip().splitlines())
        self.assertEqual(self.core._reduced_assurance_issues(bold, self._early_run()), [])

    def test_markers_inside_a_fence_do_not_count(self):
        doc = "Final Status: APPROVED\n```text\nReview-Assurance: REDUCED_BY_USER_AUTHORIZATION\n```\n"
        self.assertNotEqual(self.core._reduced_assurance_issues(doc, self._early_run()), [])
        self.assertEqual(self.core._reduced_assurance_issues(doc, {"close_reason": "CONVERGED"}), [])


class TestDashboardFailureDoesNotUndoTheAudit(unittest.TestCase):
    """vault 는 파생 산출물이다 — 쓰기 실패가 이미 성공한 감사를 되돌리면 안 된다.

    조기 종료는 특히 그렇다. 감사에 terminal 이 남았는데 대시보드 실패로 close 가 취소된 것처럼
    보이면, run 은 닫혔는데 사용자는 안 닫힌 줄 알고 다시 닫으려 한다.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, ".sage"), exist_ok=True)

    def test_the_dashboard_stays_off_until_the_project_opts_in(self):
        """opt-in 이 없으면 vault 에 아무것도 쓰지 않는다.

        가드가 사라지면 dashboard 를 요청한 적 없는 프로젝트의 vault 에 파일이 생긴다 — 실패가
        아니라 조용한 부수효과라 아무도 알아채지 못한다.
        """
        from unittest import mock  # noqa: PLC0415

        from sage.commands import review_loop as rl  # noqa: PLC0415

        for profile in ({}, {"knowledge_capture": {}},
                        {"knowledge_capture": {"loop_audit_dashboard": False}},
                        {"knowledge_capture": {"loop_audit_dashboard": "true"}}):
            with self.subTest(profile=profile), \
                 mock.patch.object(rl, "_load_profile", return_value=profile), \
                 mock.patch.object(rl, "_write_vault_dashboard") as writer:
                rl._auto_write_vault_dashboard(la, self.tmp)
                self.assertEqual(writer.call_count, 0, profile)

    def test_a_failing_dashboard_write_leaves_the_close_recorded(self):
        from unittest import mock  # noqa: PLC0415

        from sage.commands import review_loop as rl  # noqa: PLC0415

        rid = la.open_loop(self.tmp, "L3", now=0, cycle_stem="demo")
        la.record_round(self.tmp, rid, 1, 5, 2, 3, now=1,
                        survived_by_severity={"P0": 0, "P1": 0, "P2": 2, "P3": 0})
        la.close_loop(self.tmp, rid, "APPROVED", la.EARLY_CLOSE_REASON, 1, now=5,
                      authorization={"authorization_reason": "창구 마감", "confirmed_by": "sejon",
                                     "completed_rounds": 1, "configured_max_iterations": 3,
                                     "survived_by_severity": {"P0": 0, "P1": 0, "P2": 2, "P3": 0},
                                     "actual_risk": "L3", "mode": "STANDARD"})
        with mock.patch.object(rl, "_load_profile",
                               return_value={"knowledge_capture": {"loop_audit_dashboard": True}}), \
             mock.patch.object(rl, "_write_vault_dashboard", side_effect=OSError("vault offline")):
            rl._auto_write_vault_dashboard(la, self.tmp)

        closed = la.close_of(self.tmp, rid)
        self.assertIsNotNone(closed)
        self.assertEqual(closed["reason"], la.EARLY_CLOSE_REASON)
        self.assertTrue(la.audit_summary(self.tmp)["runs"][rid]["closed"])


class TestEarlyCloseAuditContract(unittest.TestCase):
    """조기 종료 terminal 레코드의 계약은 CLI 가 아니라 감사 층이 지킨다.

    라이브러리를 직접 부르는 경로(다른 도구·구버전 클라이언트)에서 손상된 승인 영수증은
    `AuditWriteError` 로 거절돼야 한다. 여기서 `AttributeError` 가 나면 진단이 아니라 크래시다.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _auth(self, **over):
        auth = {"authorization_reason": "USER_AUTHORIZED_EARLY", "confirmed_by": "sejon",
                "completed_rounds": 2, "configured_max_iterations": 3,
                "survived_by_severity": {"P0": 0, "P1": 0, "P2": 2, "P3": 0},
                "actual_risk": "L3", "mode": "FAST"}
        auth.update(over)
        return auth

    def _close(self, auth):
        """이 계약이 사는 상태를 그대로 세운다 — 라운드 없이 `iterations=2` 로 닫는 것은 애초에
        CLI 가 막는 상태이고, 이제 라이브러리도 막는다. 영수증 계약만 보려고 불가능한 상태를
        지름길로 쓰면, 그 지름길이 막히는 날 계약이 깨진 것처럼 보인다."""
        rid = la.open_loop(self.tmp, "L3", now=0)
        receipt = auth.get("survived_by_severity")
        if not isinstance(receipt, dict):
            receipt = {"P0": 0, "P1": 0, "P2": 2, "P3": 0}
        for iteration in (1, 2):
            la.record_round(self.tmp, rid, iteration, 2, 2, 0, 0, 10, now=iteration,
                            survived_by_severity=dict(receipt))
        return la.close_loop(self.tmp, rid, result="APPROVED", reason=la.EARLY_CLOSE_REASON,
                             iterations=2, now=5, authorization=auth)

    def test_a_valid_authorization_closes(self):
        self._close(self._auth())
        self.assertEqual(la.close_of(self.tmp, la.audit_summary(self.tmp)["runs"] and
                                     next(iter(la.audit_summary(self.tmp)["runs"])))["reason"],
                         la.EARLY_CLOSE_REASON)

    def test_a_corrupt_receipt_is_refused_not_crashed(self):
        for broken in (["P2=1"], "P2=1", 3, {"P0": "0", "P1": 0, "P2": 2, "P3": 0}):
            with self.subTest(receipt=broken):
                with self.assertRaises(la.AuditWriteError):
                    self._close(self._auth(survived_by_severity=broken))


class TestEarlyCloseAppendFailure(unittest.TestCase):
    """조기 close 의 append 가 실패하면 run 은 열린 상태로 남고 06 은 막혀야 한다.

    절반만 쓰고 끝나면 승인은 없는데 run 은 닫힌 것처럼 보일 수 있다 — 그 상태에서 06 이 통과
    하면 승인 없는 완료가 리포트로 나간다.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run_id = la.open_loop(self.tmp, "L3", now=0, cycle_stem="demo")
        la.record_round(self.tmp, self.run_id, 1, 5, 2, 3, now=1,
                        survived_by_severity={"P0": 0, "P1": 0, "P2": 2, "P3": 0})

    def _authorization(self):
        return {"authorization_reason": "창구 마감", "confirmed_by": "sejon",
                "completed_rounds": 1, "configured_max_iterations": 3,
                "survived_by_severity": {"P0": 0, "P1": 0, "P2": 2, "P3": 0},
                "actual_risk": "L3", "mode": "STANDARD"}

    def test_a_half_written_close_leaves_the_run_open_and_blocks_the_report(self):
        from unittest import mock  # noqa: PLC0415

        path = Path(la.audit_path(self.tmp))
        before = path.read_bytes()

        def partial_write(fd, payload):
            return os.write(fd, payload[:len(payload) // 2])

        with mock.patch.object(la, "_write_once", side_effect=partial_write), \
             self.assertRaises(la.AuditWriteError):
            la.close_loop(self.tmp, self.run_id, "APPROVED", la.EARLY_CLOSE_REASON, 1, now=5,
                          authorization=self._authorization())

        self.assertEqual(path.read_bytes(), before)
        self.assertIsNone(la.close_of(self.tmp, self.run_id))
        state = la.audit_summary(self.tmp)["runs"][self.run_id]
        self.assertIs(state["closed"], False)
        self.assertIs(state["clean"], True)
        self.assertIs(state["chain_ok"], True)


class TestEarlyCloseOnTheDashboard(unittest.TestCase):
    """vault 대시보드를 읽는 사람이 조기 승인과 수렴 승인을 구분할 수 있는가.

    종료 열은 이미 `APPROVED/USER_AUTHORIZED_EARLY` 로 둘을 가른다. 빠진 것은 **무엇이 남은
    채로 닫혔는가** 다 — 그게 없으면 조기 승인의 실제 잔여 위험을 노트만 보고는 알 수 없다.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, ".sage"), exist_ok=True)

    def _dashboard(self, early):
        from sage.commands import review_loop as rl  # noqa: PLC0415

        rid = la.open_loop(self.tmp, "L3", now=0, cycle_stem="demo")
        receipt = {"P0": 0, "P1": 0, "P2": 2, "P3": 0}
        la.record_round(self.tmp, rid, 1, 5, 2 if early else 0, 3, now=1,
                        survived_by_severity=receipt if early else None)
        if early:
            la.close_loop(self.tmp, rid, "APPROVED", la.EARLY_CLOSE_REASON, 1, now=5,
                          authorization={"authorization_reason": "창구 마감",
                                         "confirmed_by": "sejon", "completed_rounds": 1,
                                         "configured_max_iterations": 3,
                                         "survived_by_severity": receipt,
                                         "actual_risk": "L3", "mode": "STANDARD"})
        else:
            la.close_loop(self.tmp, rid, "APPROVED", "CONVERGED", 1, now=5)
        return rid, rl._dashboard_md(la, self.tmp)

    def test_an_early_close_shows_its_residual_receipt(self):
        rid, md = self._dashboard(early=True)
        self.assertIn("APPROVED/USER_AUTHORIZED_EARLY", md)
        self.assertIn("P2=2", md)
        self.assertIn("sejon", md)
        self.assertIn(rid, md)

    def test_a_converged_close_adds_no_reduced_assurance_section(self):
        _rid, md = self._dashboard(early=False)
        self.assertNotIn("USER_AUTHORIZED_EARLY", md)
        self.assertNotIn("P2=", md)

    def test_an_unset_ceiling_never_renders_as_a_negative_round_count(self):
        """상한 미설정을 `-1` 로 적으면 노트가 `1/-1 rounds` 를 낸다 — 읽는 사람에게 그건
        "상한 없음" 이 아니라 "라운드 -1 회" 다. 옛 레코드의 `-1` 도 같은 단어로 렌더한다.
        """
        from sage.commands import review_loop as rl  # noqa: PLC0415

        receipt = {"P0": 0, "P1": 0, "P2": 2, "P3": 0}
        rid = la.open_loop(self.tmp, "L3", now=0, cycle_stem="demo")
        la.record_round(self.tmp, rid, 1, 5, 2, 3, now=1, survived_by_severity=receipt)
        la.close_loop(self.tmp, rid, "APPROVED", la.EARLY_CLOSE_REASON, 1, now=5,
                      authorization={"authorization_reason": "창구 마감",
                                     "confirmed_by": "sejon", "completed_rounds": 1,
                                     "configured_max_iterations": -1,
                                     "survived_by_severity": receipt,
                                     "actual_risk": "L3", "mode": "STANDARD"})
        md = rl._dashboard_md(la, self.tmp)
        self.assertNotIn("/-1 rounds", md)
        self.assertIn(f"1/{la.UNBOUNDED_ITERATIONS} rounds", md)

    def test_a_fast_cycle_is_not_recorded_as_a_standard_close(self):
        """`mode` 는 예전에 구조적으로 FAST 가 될 수 없었다.

        Fast run 이 `loop_run_id` 를 적는 것은 `sage fast-cycle review` 이고 그건 Loop 가 닫힌
        **뒤**에 실행된다. close 시점에 역방향으로 찾으면 어떤 Fast run 도 이 Loop 를 가리키지
        않으므로, 조기 종료 감사가 예외 없이 STANDARD 로 남았다. 결속 축은 open 시점에 이미
        양쪽에 있는 stem 이다.
        """
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))), "scripts", "sage_harness", "hooks", "runtime"))
        import fast_cycle_audit as fca  # noqa: PLC0415

        from sage.commands import review_loop as rl  # noqa: PLC0415

        rid = la.open_loop(self.tmp, "L3", now=0, cycle_stem="demo-fast")
        self.assertEqual(rl._cycle_mode(la, self.tmp, rid), "STANDARD")

        fast_id = fca.open_fast(self.tmp, cycle_stem="demo-fast", actual_risk="L3",
                                fast_review_level="L2", reason="긴급", minimum_rounds=1,
                                lenses=["correctness"], profile_hash="b" * 64,
                                plan_hash_open="a" * 64)
        self.assertEqual(rl._cycle_mode(la, self.tmp, rid), "FAST")
        self.assertEqual(rl._fast_run_id(la, self.tmp, rid), fast_id)

    def test_an_ambiguous_or_finished_fast_run_is_not_guessed_at(self):
        """살아있는 후보가 정해지지 않으면 아무거나 고르지 않는다 — 틀린 run 을 가리키는
        기록은 결속이 없는 것보다 나쁘다."""
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))), "scripts", "sage_harness", "hooks", "runtime"))
        import fast_cycle_audit as fca  # noqa: PLC0415

        from sage.commands import review_loop as rl  # noqa: PLC0415

        rid = la.open_loop(self.tmp, "L3", now=0, cycle_stem="demo-fast")
        other = fca.open_fast(self.tmp, cycle_stem="다른-사이클", actual_risk="L3",
                              fast_review_level="L2", reason="긴급", minimum_rounds=1,
                              lenses=["correctness"], profile_hash="b" * 64,
                                plan_hash_open="a" * 64)
        self.assertEqual(rl._fast_run_id(la, self.tmp, rid), None, other)

        first = fca.open_fast(self.tmp, cycle_stem="demo-fast", actual_risk="L3",
                              fast_review_level="L2", reason="긴급", minimum_rounds=1,
                              lenses=["correctness"], profile_hash="b" * 64,
                              plan_hash_open="a" * 64)
        self.assertEqual(rl._fast_run_id(la, self.tmp, rid), first)
        # 라이브러리는 stem 당 활성 run 을 하나로 강제한다. 후보가 둘인 상태는 수기 편집이나 옛
        # 클라이언트가 남긴 감사에서만 나오므로, 그 모양을 직접 만들어 가드를 고정한다.
        opener = next(record for record in fca._records(self.tmp)[0]
                      if record.get("cycle_stem") == "demo-fast")
        fca._append(self.tmp, dict(opener, run_id="fc-hand-edited"))
        self.assertEqual(rl._fast_run_id(la, self.tmp, rid), None)

    def test_the_screen_and_the_audit_use_the_same_word_for_no_ceiling(self):
        """화면은 `unset`, 감사는 `-1` 이던 시절에는 같은 사실이 두 곳에서 다른 모양이었다."""
        from sage.commands import review_loop as rl  # noqa: PLC0415

        self.assertEqual(rl._UNBOUNDED_LABEL, la.UNBOUNDED_ITERATIONS)
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            rl._print_early_disclosure(
                {"survived_by_severity": {"P0": 0, "P1": 0, "P2": 1, "P3": 0},
                 "completed_rounds": 2}, None)
        self.assertIn(f"ceiling: {la.UNBOUNDED_ITERATIONS}", stream.getvalue())


class TestEarlyCloseAcceptance(TestEarlyCloseCLI):
    """미검증 요구사항은 조기 완료가 인수하는 잔여 위험이 아니다.

    조기 완료는 리뷰가 남긴 finding 을 사용자 권한으로 인수하는 절차다. 요구사항이 FAIL 이거나
    승인 없이 `NOT TESTED` 인 것은 리뷰의 잔여가 아니라 검증되지 않은 기능이고, 그건 06 리포트
    게이트가 어차피 막는다 — 다만 그때는 05 가 이미 조기 승인으로 닫힌 뒤라 감사에는 "축약된
    리뷰로 승인" 만 남고 무엇이 미검증이었는지는 남지 않는다.
    """

    STEM = "demo"

    def setUp(self):
        super().setUp()
        self.profile["pdca"]["phases"] += [
            {"id": "01", "glob": "plan_docs/01-plan/**/*.md"},
            {"id": "04", "glob": "plan_docs/04-analyze/**/*.md"},
        ]
        self.profile["verification"] = {"acceptance": {
            "enabled": True, "require_for_risk": ["L2", "L3"],
            "report_gate_by_risk": {"L2": "advisory", "L3": "enforce"},
            "waiver": {"enabled": True},
        }}
        self._write_profile()
        self._write_phase("01", "\n".join([
            "## Acceptance Matrix",
            "| ID | User Requirement | Required Evidence | Owner | Required? |",
            "|---|---|---|---|---|",
            "| A1 | 도시 검색 | test | qa | yes |",
        ]))
        # 물려받은 조기 완료 테스트들은 acceptance 를 다루지 않는다. 기본을 통과 상태로 두면
        # 그 테스트들이 acceptance 가 켜진 프로젝트에서도 그대로 성립하는지까지 같이 확인된다.
        self._write_phase("04", self._evidence("PASS"))

    def _write_phase(self, phase, body):
        directory = {"01": "01-plan", "04": "04-analyze"}[phase]
        target = Path(self.root, "plan_docs", directory)
        target.mkdir(parents=True, exist_ok=True)
        Path(target, f"{self.STEM}.md").write_text(
            f"Cycle-Stem: `{self.STEM}`\n\n{body}\n", encoding="utf-8")

    def _evidence(self, status, reason="테스트 로그"):
        return "\n".join([
            "## Acceptance Evidence",
            "| ID | Status | Evidence |",
            "|---|---|---|",
            f"| A1 | {status} | {reason} |",
        ])

    def _open(self):
        result = self._run("open", "--risk", self.RISK, "--cycle-stem", self.STEM)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.run_id = result.stdout.strip().split()[-1]
        return self.run_id

    def _early(self, status, reason="테스트 로그"):
        self._write_phase("04", self._evidence(status, reason))
        self._open()
        self.assertEqual(self._round().returncode, 0)
        return self._close()

    def test_a_failed_requirement_cannot_be_closed_early(self):
        result = self._early("FAIL")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("unresolved acceptance", result.stderr)
        self.assertEqual(self._closes(), [])

    def test_an_unwaived_not_tested_requirement_cannot_be_closed_early(self):
        result = self._early("NOT TESTED")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("unresolved acceptance", result.stderr)
        self.assertEqual(self._closes(), [])

    def test_a_passing_requirement_does_not_block(self):
        self.assertEqual(self._early("PASS").returncode, 0)
        self.assertEqual(len(self._closes()), 1)

    def test_an_exactly_waived_not_tested_requirement_is_an_accepted_residual(self):
        """L3 명시 waiver 로 잔여가 된 `NOT TESTED` 는 이미 승인된 잔여 위험이다 —
        조기 완료가 인수하는 것과 같은 종류라 여기서 두 번 막지 않는다."""
        sys.path.insert(0, os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime"))
        import acceptance_waiver  # noqa: PLC0415

        Path(self.root, ".sage").mkdir(exist_ok=True)
        acceptance_waiver.grant(self.root, self.STEM, "A1", reason="계측 장비 대기",
                                scope="A1 만", remaining_evidence="다음 사이클 실측",
                                confirmed_by="sejon")
        self.assertEqual(self._early("NOT TESTED").returncode, 0)
        self.assertEqual(len(self._closes()), 1)

    def test_a_project_without_acceptance_is_not_given_a_new_gate(self):
        """`verification.acceptance` 를 쓰지 않는 프로젝트에 없던 검사를 새로 켜지 않는다."""
        self.profile["verification"]["acceptance"]["enabled"] = False
        self._write_profile()
        self.assertEqual(self._early("FAIL").returncode, 0)
        self.assertEqual(len(self._closes()), 1)



if __name__ == "__main__":
    unittest.main(verbosity=2)
