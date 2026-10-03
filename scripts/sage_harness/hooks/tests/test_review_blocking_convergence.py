#!/usr/bin/env python3
"""Phase 05 리뷰 규칙 2단계 — 차단 기준 수렴(`converge_on: blocking`)·크리티컬 P2 결정·변경 전 결함.

지금 수렴 조건은 「마지막 라운드 생존 0」이라, P3 하나만 남아도 리뷰가 끝나지 않았다. 이 파일은
`blocking` 을 켠 run 이 차단 지적(P0·P1·판단 안 된 크리티컬 P2)이 0 일 때 잔여를 안고 승인하는지,
그 승인이 일반 승인과 구분되는지(보증 저하), 크리티컬 P2 를 사람이 정하기 전에는 다음 라운드도
종료도 없는지, 그 결정이 지적 내용에 묶이는지를 본다. 켜지 않은 run 의 판정은 1단계와 같아야 한다.
"""
import itertools
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
sys.path.insert(0, HOOKS_DIR)
sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))

import loop_audit as la  # noqa: E402
import review_rounds as rr  # noqa: E402
from sage.profile_validate import validate_profile  # noqa: E402

STEM = "demo-cycle"


def _profile(mode="blocking"):
    review = {
        "enabled": True,
        "lenses": ["correctness", "security"],
        "refuters": 1,
        "max_iterations": {"L2": 10, "L3": 10},
        "budget_tokens": {"L2": 10_000_000, "L3": 10_000_000},
        "severity_block": ["P0", "P1"],
        "early_completion": {"enabled": True, "minimum_completed_rounds": 1},
    }
    if mode is not None:
        review["converge_on"] = mode
    return {"pdca": {"phases": [{"id": "00", "glob": "plan_docs/00-base_plan/**/*.md"}],
                     "review_loop": review}}


def _finding(fid, severity="P2", status="survived", disposition="residual", **extra):
    item = {"id": fid, "source": {"kind": "lens", "name": "security"}, "file": "app.py",
            "line": 10, "severity": severity, "claim": f"claim of {fid}", "status": status,
            "disposition": disposition}
    item.update(extra)
    return item


def _critical(fid, category="deploy_breakage", **extra):
    return _finding(fid, critical=True, critical_category=category, **extra)


class _Case(unittest.TestCase):
    RISK = "L3"
    MODE = "blocking"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        Path(self.root, "sage").mkdir()
        self.profile = _profile(self.MODE)
        self._write_profile()
        self.rid = None

    def _write_profile(self):
        import yaml  # noqa: PLC0415
        Path(self.root, "sage", "project-profile.yaml").write_text(
            yaml.safe_dump(self.profile, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def _run(self, *args):
        environ = dict(os.environ, PYTHONPATH=REPO)
        environ.pop("SAGE_CYCLE_STEM", None)
        return subprocess.run([sys.executable, "-m", "sage", "review-loop", *args,
                               "--root", self.root],
                              text=True, capture_output=True, env=environ, cwd=self.root)

    def _open(self):
        result = self._run("open", "--risk", self.RISK, "--cycle-stem", STEM)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.rid = result.stdout.strip().splitlines()[0]
        return self.rid

    def _round(self, iteration, findings, unexplored=(), closure=()):
        doc = {"schema": rr.SCHEMA, "run_id": self.rid, "iteration": iteration,
               "findings": list(findings), "unexplored": list(unexplored),
               "closure": list(closure)}
        path = Path(self.root, f"side-{iteration}.json")
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return self._run("round", "--run-id", self.rid, "--iteration", str(iteration),
                         "--findings-file", str(path))

    def _ok_round(self, iteration, findings, **extra):
        result = self._round(iteration, findings, **extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def _next(self):
        result = self._run("next", "--run-id", self.rid)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip().splitlines()[-1], result.stderr

    def _shown_claim(self, finding):
        """`next` 가 보여 주는 주장 해시 — 마지막 라운드 영수증의 그 지적."""
        rounds = [r for r in self._records() if r.get("event") == "round"]
        for item in (rounds[-1].get("receipt") or {}).get("critical_findings") or []:
            if item["id"] == finding:
                return item["claim_sha256"][:12]
        return "0" * 12

    def _decide(self, finding, choice, reason="사용자 판단", by="sejon"):
        return self._run("decide", "--run-id", self.rid, "--finding", finding,
                         "--claim", self._shown_claim(finding), f"--{choice}",
                         "--reason", reason, "--decided-by", by)

    def _close(self, reason, result="APPROVED", iterations=None):
        rounds = [r for r in self._records() if r.get("event") == "round"]
        return self._run("close", "--run-id", self.rid, "--result", result, "--reason", reason,
                         "--iterations", str(len(rounds) if iterations is None else iterations))

    def _records(self):
        path = Path(self.root, ".sage", "loop_audit.jsonl")
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class TestResidualConvergence(_Case):
    def test_nonblocking_residuals_converge_and_close_with_reduced_assurance(self):
        self._open()
        self._ok_round(1, [_finding("F1", "P2"), _finding("F2", "P3"),
                           _finding("F3", "P1", status="refuted", disposition=None)])
        line, err = self._next()
        self.assertEqual(line, "NEXT: STOP result=APPROVED reason=CONVERGED_RESIDUAL")
        self.assertIn("blocking 0", err.replace("차단 0", "blocking 0"))
        closed = self._close("CONVERGED_RESIDUAL")
        self.assertEqual(closed.returncode, 0, closed.stderr)
        self.assertIn("REDUCED_BY_POLICY", closed.stderr)
        close = self._records()[-1]
        self.assertEqual(close["review_assurance"], "REDUCED_BY_POLICY")
        self.assertEqual(close["residual"],
                         {"blocking_open": 0, "accepted_residual": 0, "nonblocking": 2})
        self.assertEqual(close["accepted_decisions"], [])
        summary = la.audit_summary(self.root)["runs"][self.rid]
        self.assertEqual(summary["close_reason"], "CONVERGED_RESIDUAL")
        self.assertEqual(summary["review_assurance"], "REDUCED_BY_POLICY")

    def test_a_standard_close_cannot_carry_residuals_on_a_blocking_run(self):
        """잔여 승인이 거부됐다고 사유를 `CONVERGED` 로 바꾸면 잔여를 안은 승인이 일반 승인으로 남는다.
        종료 검산이 advisory(기본)여도 막는다 — CLI 와 잠금 안 둘 다."""
        self._open()
        self._ok_round(1, [_finding("F1", "P3")])
        for reason in ("CONVERGED", "DRY"):
            with self.subTest(reason=reason):
                result = self._close(reason)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("CONVERGED_RESIDUAL", result.stderr)
                with self.assertRaises(la.AuditWriteError):
                    la.close_loop(self.root, self.rid, "APPROVED", reason, 1)
        self.assertEqual([r for r in self._records() if r.get("event") == "loop_close"], [])

    def test_p0_and_p1_block_whatever_severity_block_says(self):
        """잔여 승인에서 P0·P1 은 설정과 무관하게 차단이다 — 빈 목록이든 P0 를 뺀 목록이든."""
        for block in ([], ["P1"], ["P3"]):
            with self.subTest(block=block):
                self.profile["pdca"]["review_loop"]["severity_block"] = block
                self._write_profile()
                self._open()
                self._ok_round(1, [_finding("F1", "P0", disposition="fix")])
                self.assertEqual(self._next()[0], "NEXT: CONTINUE")

    def test_no_critical_question_when_p2_already_blocks(self):
        """P2 가 차단 심각도면 크리티컬 P2 는 어차피 고쳐야 수렴한다 — 수용할 수 없는 질문을 하지 않는다."""
        self.profile["pdca"]["review_loop"]["severity_block"] = ["P0", "P1", "P2"]
        self._write_profile()
        self._open()
        self._ok_round(1, [_critical("F1")])
        self.assertEqual(self._next()[0], "NEXT: CONTINUE")
        self._ok_round(2, [_finding("F1", status="refuted", disposition=None)])

    def test_a_blocking_severity_keeps_the_loop_going(self):
        self._open()
        self._ok_round(1, [_finding("F1", "P1", disposition="fix"), _finding("F2", "P3")])
        self.assertEqual(self._next()[0], "NEXT: CONTINUE")
        self.assertEqual(self._close("CONVERGED_RESIDUAL").returncode, 2)

    def test_zero_survivors_is_a_normal_convergence(self):
        self._open()
        self._ok_round(1, [_finding("F1", status="refuted", disposition=None)])
        self.assertEqual(self._next()[0], "NEXT: STOP result=APPROVED reason=CONVERGED")

    def test_unexplored_lens_or_pending_refutation_is_not_convergence(self):
        self._open()
        self._ok_round(1, [_finding("F1", "P3")],
                       unexplored=[{"lens": "security", "reason": "timeout"}])
        self.assertEqual(self._next()[0], "NEXT: CONTINUE")
        self._ok_round(2, [_finding("F1", "P3", refute_pending=True)])
        self.assertEqual(self._next()[0], "NEXT: CONTINUE")

    def test_a_round_without_a_receipt_is_not_convergence(self):
        self._open()
        result = self._run("round", "--run-id", self.rid, "--iteration", "1", "--found", "1",
                           "--survived", "1", "--accepted", "0",
                           "--survived-by-severity", "P0=0,P1=0,P2=0,P3=1")
        self.assertEqual(result.returncode, 0, result.stderr)
        line, err = self._next()
        self.assertEqual(line, "NEXT: CONTINUE")
        self.assertIn("--findings-file", err)

    def test_the_iteration_cap_with_only_residuals_is_a_residual_approval(self):
        self.profile["pdca"]["review_loop"]["max_iterations"] = {"L2": 1, "L3": 1}
        self._write_profile()
        self._open()
        self._ok_round(1, [_finding("F1", "P3")])
        self.assertEqual(self._next()[0],
                         "NEXT: STOP result=APPROVED reason=CONVERGED_RESIDUAL")

    def test_residual_close_rechecks_the_verdict_inside_the_lock(self):
        self._open()
        self._ok_round(1, [_finding("F1", "P3")])
        records = la.read_records(self.root)
        verdict = la.loop_verdict(records, self.rid, {}, "L3")
        residual = {"completed_rounds": 1, "configured_max_iterations": 10,
                    "survived_by_severity": {"P0": 0, "P1": 0, "P2": 0, "P3": 1},
                    "actual_risk": "L3", "mode": "STANDARD",
                    "residual": {"blocking_open": 0, "accepted_residual": 0, "nonblocking": 1},
                    "accepted_decisions": [],
                    "sidecar_sha256": records[-1]["sidecar"]["sha256"]}
        self.assertEqual(verdict["reason"], "CONVERGED_RESIDUAL")
        # close 가 판정을 끝낸 사이 차단 지적이 있는 라운드가 붙었다.
        self._ok_round(2, [_finding("F9", "P1", disposition="fix")])
        with self.assertRaises(la.AuditWriteError):
            la.close_loop(self.root, self.rid, "APPROVED", "CONVERGED_RESIDUAL", 1,
                          residual=residual)

    def test_a_residual_record_is_only_for_its_reason(self):
        self._open()
        self._ok_round(1, [_finding("F1", status="refuted", disposition=None)])
        with self.assertRaises(la.AuditWriteError):
            la.close_loop(self.root, self.rid, "APPROVED", "CONVERGED", 1,
                          residual={"completed_rounds": 1})
        with self.assertRaises(la.AuditWriteError):
            la.close_loop(self.root, self.rid, "APPROVED", "CONVERGED_RESIDUAL", 1)


class TestResidualEligibility(_Case):
    """잔여 승인은 조기 종료와 같은 승인 자격 검사를 거친다 — 한쪽만 느슨하면 그쪽이 우회로다."""

    def _phase00(self, resolved):
        self.profile["pdca"]["base_plan"] = {"done_criteria_gate": "advisory"}
        self._write_profile()
        path = Path(self.root, "plan_docs", "00-base_plan", f"{STEM}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        mark = "x" if resolved else " "
        path.write_text(f"# demo\n\nCycle-Stem: `{STEM}`\nRisk Level: L3\n"
                        "Done-Criteria-Revision: 1\n\n## 5. Done Criteria\n\n"
                        f"- [{mark}] behaviour verified\n", encoding="utf-8")

    def _acceptance(self, status):
        self.profile["pdca"]["phases"] += [{"id": "01", "glob": "plan_docs/01-plan/**/*.md"},
                                           {"id": "04", "glob": "plan_docs/04-analyze/**/*.md"}]
        self.profile["verification"] = {"acceptance": {
            "enabled": True, "require_for_risk": ["L2", "L3"],
            "report_gate_by_risk": {"L2": "advisory", "L3": "enforce"}}}
        self._write_profile()
        for directory, body in (("01-plan", "## Acceptance Matrix\n"
                                 "| ID | User Requirement | Required Evidence | Owner | Required? |\n"
                                 "|---|---|---|---|---|\n| A1 | 검색 | test | qa | yes |"),
                                ("04-analyze", "## Acceptance Evidence\n| ID | Status | Evidence |\n"
                                 f"|---|---|---|\n| A1 | {status} | 로그 |")):
            target = Path(self.root, "plan_docs", directory)
            target.mkdir(parents=True, exist_ok=True)
            Path(target, f"{STEM}.md").write_text(f"Cycle-Stem: `{STEM}`\n\n{body}\n",
                                                 encoding="utf-8")

    def _residual_run(self):
        self._open()
        self._ok_round(1, [_finding("F1", "P3")])
        return self._close("CONVERGED_RESIDUAL")

    def test_unresolved_done_criteria_block_the_residual_approval(self):
        self._phase00(resolved=False)
        result = self._residual_run()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Done Criteria", result.stderr)
        self.assertEqual([r for r in self._records() if r.get("event") == "loop_close"], [])

    def test_resolved_done_criteria_are_recorded_on_the_close(self):
        self._phase00(resolved=True)
        result = self._residual_run()
        self.assertEqual(result.returncode, 0, result.stderr)
        close = self._records()[-1]
        self.assertTrue(close.get("phase00_hash"))
        self.assertEqual(close.get("done_criteria_revision"), 1)

    def test_a_failed_requirement_blocks_the_residual_approval(self):
        self._acceptance("FAIL")
        result = self._residual_run()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("unresolved acceptance", result.stderr)

    def test_a_passing_requirement_does_not_block(self):
        self._acceptance("PASS")
        self.assertEqual(self._residual_run().returncode, 0)


class TestCriticalP2(_Case):
    def test_a_critical_p2_asks_and_blocks_rounds_and_closes(self):
        self._open()
        self._ok_round(1, [_critical("F1"), _finding("F2", "P3")])
        line, err = self._next()
        self.assertEqual(line, "NEXT: ASK kind=CRITICAL_P2 findings=F1")
        self.assertIn("decide --run-id", err)
        self.assertIn("claim of F1", err)
        refused = self._round(2, [_finding("F2", "P3")])
        self.assertEqual(refused.returncode, 2)
        self.assertIn("decide", refused.stderr)
        for reason, result in (("CONVERGED_RESIDUAL", "APPROVED"), ("BUDGET_ITER", "BLOCKED"),
                               ("CYCLE_CAP", "BLOCKED")):
            with self.subTest(reason=reason):
                self.assertEqual(self._close(reason, result=result).returncode, 2)
        self.assertEqual([r for r in self._records() if r.get("event") == "round"].__len__(), 1)

    def test_the_lock_refuses_a_round_while_a_critical_waits(self):
        self._open()
        self._ok_round(1, [_critical("F1")])
        with self.assertRaises(la.AuditWriteError):
            la.record_round(self.root, self.rid, 2, 0, 0, 0)

    def test_accepting_the_critical_converges_with_reduced_assurance(self):
        self._open()
        self._ok_round(1, [_critical("F1"), _finding("F2", "P3")])
        decided = self._decide("F1", "accept", reason="운영 영향 없음")
        self.assertEqual(decided.returncode, 0, decided.stderr)
        decision = self._records()[-1]
        self.assertEqual((decision["kind"], decision["choice"], decision["finding_id"],
                          decision["iteration"]), ("critical_p2", "accept", "F1", 1))
        self.assertEqual(decision["claim_sha256"], rr.claim_sha256("claim of F1"))
        self.assertEqual(self._next()[0], "NEXT: STOP result=APPROVED reason=CONVERGED_RESIDUAL")
        closed = self._close("CONVERGED_RESIDUAL")
        self.assertEqual(closed.returncode, 0, closed.stderr)
        close = self._records()[-1]
        self.assertEqual(close["residual"]["accepted_residual"], 1)
        self.assertEqual(close["accepted_decisions"][0]["finding_id"], "F1")
        ledger = self._run("ledger", "show", "--cycle-stem", STEM)
        self.assertIn("운영 영향 없음", ledger.stdout)

    def test_fixing_continues_and_the_same_critical_is_asked_again_next_round(self):
        self._open()
        self._ok_round(1, [_critical("F1")])
        self.assertEqual(self._decide("F1", "fix").returncode, 0)
        self.assertEqual(self._next()[0], "NEXT: CONTINUE")
        # 고쳤다고 했지만 같은 주장이 다시 살아남았다 — 옛 결정은 새 라운드에 적용되지 않는다.
        self._ok_round(2, [_critical("F1")])
        self.assertEqual(self._next()[0], "NEXT: ASK kind=CRITICAL_P2 findings=F1")

    def test_a_decision_does_not_apply_to_a_changed_claim(self):
        self._open()
        self._ok_round(1, [_critical("F1")])
        records = la.read_records(self.root)
        forged = dict(records[-1])
        # 같은 라운드·같은 id 라도 주장이 다르면 결정은 적용되지 않는다(판정 함수 단위로 확인).
        receipt = dict(forged["receipt"])
        receipt["critical_findings"] = [{"id": "F1", "claim_sha256": "0" * 64,
                                         "category": "deploy_breakage"}]
        forged["receipt"] = receipt
        decision = {"event": "decision", "run_id": self.rid, "kind": "critical_p2",
                    "choice": "accept", "iteration": 1, "finding_id": "F1",
                    "round_hash": forged["record_hash"],
                    "claim_sha256": rr.claim_sha256("claim of F1")}
        self.assertEqual(la.critical_state(records + [decision], self.rid)["accept"], ["F1"])
        state = la.critical_state(records[:-1] + [forged, decision], self.rid)
        self.assertEqual(state["pending"], ["F1"])

    def test_a_decision_does_not_carry_over_to_a_round_with_the_same_number(self):
        self._open()
        self._ok_round(1, [_critical("F1")])
        self.assertEqual(self._decide("F1", "fix").returncode, 0)
        # iteration 번호는 다시 쓰일 수 있다. 같은 번호·같은 주장이어도 다른 라운드면 다시 묻는다.
        self._ok_round(1, [_critical("F1")])
        self.assertEqual(self._next()[0], "NEXT: ASK kind=CRITICAL_P2 findings=F1")

    def test_an_answer_is_not_attached_to_a_finding_that_changed_meanwhile(self):
        """선검사와 쓰기 사이에 다른 세션이 결정·새 라운드를 붙이면, 같은 id 의 새 주장에 옛 답을 붙이지
        않는다 — 사용자가 답한 것은 그때 보여 준 주장이다."""
        self._open()
        self._ok_round(1, [_critical("F1")])
        shown = [r for r in self._records() if r.get("event") == "round"][-1]
        self.assertEqual(self._decide("F1", "fix").returncode, 0)   # 다른 세션
        changed = _critical("F1")
        changed["claim"] = "a different claim"
        self._ok_round(2, [changed])
        with self.assertRaises(la.AuditWriteError):
            la.record_decision(self.root, self.rid, la.DECISION_CRITICAL_P2, "accept", "r", "u",
                               finding_id="F1", expected_round_hash=shown["record_hash"],
                               expected_claim_sha256=rr.claim_sha256("claim of F1"))
        with self.assertRaises(la.AuditWriteError):
            la.record_decision(self.root, self.rid, la.DECISION_CRITICAL_P2, "accept", "r", "u",
                               finding_id="F1")
        self.assertEqual(self._next()[0], "NEXT: ASK kind=CRITICAL_P2 findings=F1")

    def test_decide_with_the_shown_claim(self):
        """`next` 가 보여 준 주장 해시를 넘기면, 그 사이 같은 id 에 다른 주장이 와도 옛 답이 붙지 않는다."""
        self._open()
        self._ok_round(1, [_critical("F1")])
        _line, err = self._next()
        shown = rr.claim_sha256("claim of F1")[:12]
        self.assertIn(f"[claim {shown}]", err)
        for claim in ("0" * 12, shown[:4]):
            with self.subTest(claim=claim):
                result = self._run("decide", "--run-id", self.rid, "--finding", "F1",
                                   "--claim", claim, "--accept", "--reason", "r",
                                   "--decided-by", "u")
                self.assertEqual(result.returncode, 2)
        result = self._run("decide", "--run-id", self.rid, "--finding", "F1", "--claim", shown,
                           "--accept", "--reason", "r", "--decided-by", "u")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_decide_refusals(self):
        self._open()
        self._ok_round(1, [_critical("F1"), _finding("F2", "P3")])
        cases = {
            "not pending": ("decide", "--run-id", self.rid, "--finding", "F2", "--fix",
                            "--claim", "0" * 12, "--reason", "r", "--decided-by", "u"),
            "no claim": ("decide", "--run-id", self.rid, "--finding", "F1", "--fix",
                         "--reason", "r", "--decided-by", "u"),
            "claim on the cycle form": ("decide", "--run-id", self.rid, "--cycle", "continue",
                                        "--extend", "1", "--claim", "0" * 12,
                                        "--reason", "r", "--decided-by", "u"),
            "mixed forms": ("decide", "--run-id", self.rid, "--finding", "F1", "--fix",
                            "--cycle", "continue", "--extend", "1",
                            "--reason", "r", "--decided-by", "u"),
            "no choice": ("decide", "--run-id", self.rid, "--finding", "F1",
                          "--reason", "r", "--decided-by", "u"),
            "empty reason": ("decide", "--run-id", self.rid, "--finding", "F1", "--fix",
                             "--reason", " ", "--decided-by", "u"),
            "cycle first": ("decide", "--run-id", self.rid, "--cycle", "continue",
                            "--extend", "1", "--reason", "r", "--decided-by", "u"),
        }
        for label, args in cases.items():
            with self.subTest(label):
                self.assertEqual(self._run(*args).returncode, 2)
        self.assertEqual([r for r in self._records() if r.get("event") == "decision"], [])
        self.assertEqual(self._decide("F1", "fix").returncode, 0)
        self.assertEqual(self._decide("F1", "accept").returncode, 2)   # 이미 결정됨

    def test_early_completion_is_refused_while_a_critical_waits(self):
        self._open()
        self._ok_round(1, [_critical("F1")])
        result = self._run("close", "--run-id", self.rid, "--result", "APPROVED",
                           "--reason", "USER_AUTHORIZED_EARLY", "--iterations", "1",
                           "--authorization-reason", "마감", "--confirmed-by", "sejon",
                           "--confirm", "USER_AUTHORIZED_EARLY")
        self.assertEqual(result.returncode, 2)

    def test_early_completion_counts_a_fix_decision_as_blocking(self):
        self.profile["pdca"]["review_loop"]["max_iterations"] = {"L2": 1, "L3": 1}
        self._write_profile()
        self._open()
        self._ok_round(1, [_critical("F1")])
        self.assertEqual(self._decide("F1", "fix").returncode, 0)
        self.assertEqual(self._next()[0], "NEXT: STOP result=BLOCKED reason=BUDGET_ITER")
        result = self._run("close", "--run-id", self.rid, "--result", "APPROVED",
                           "--reason", "USER_AUTHORIZED_EARLY", "--iterations", "1",
                           "--authorization-reason", "마감", "--confirmed-by", "sejon",
                           "--confirm", "USER_AUTHORIZED_EARLY")
        self.assertEqual(result.returncode, 2)
        self.assertIn("blocking_open=1", result.stderr)

    def test_architecture_and_budget_stops_may_still_close(self):
        self._open()
        self._ok_round(1, [_critical("F1"),
                           _finding("F2", "P1", triage="architecture_change", disposition="pending")])
        self.assertEqual(self._next()[0], "NEXT: STOP result=BLOCKED reason=BLOCKED_ARCH")
        self.assertEqual(self._close("BLOCKED_ARCH", result="BLOCKED").returncode, 0)


class TestSidecarPolicy(_Case):
    def _refused(self, findings):
        result = self._round(1, findings)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual([r for r in self._records() if r.get("event") == "round"], [])
        return result.stderr

    def test_critical_marks_only_a_p2_in_a_listed_category(self):
        self._open()
        self.assertIn("P2 only", self._refused([_critical("F1", severity="P1")]))
        self.assertIn("not one of", self._refused([_critical("F1", category="made_up")]))
        self.assertIn("critical is false", self._refused(
            [_finding("F1", critical_category="deploy_breakage")]))

    def test_profile_categories_replace_the_defaults(self):
        self.profile["pdca"]["review_loop"]["critical_p2"] = ["custom_one"]
        self._write_profile()
        self._open()
        self._refused([_critical("F1")])
        self._ok_round(1, [_critical("F1", category="custom_one")])

    def test_a_critical_grade_preexisting_defect_is_dropped_only_when_unchanged(self):
        self._open()
        drop = [{"refuter": "r1", "verdict": "refuted", "reason": "base 에도 있음",
                 "drop_reason": "out_of_scope_preexisting"}]
        for exposure in ("touched", "reach_changed", None):
            with self.subTest(exposure=exposure):
                self._refused([_finding("F1", "P0", status="refuted", disposition=None,
                                        preexisting=True, exposure=exposure, refute=drop)])
        self.assertIn("preexisting: true", self._refused(
            [_finding("F1", "P3", status="refuted", disposition=None, refute=drop)]))
        self._ok_round(1, [_finding("F1", "P0", status="refuted", disposition=None,
                                    preexisting=True, exposure="unchanged", refute=drop)])
        ledger = self._run("ledger", "show", "--cycle-stem", STEM).stdout
        self.assertIn("F1", ledger)
        self.assertIn("unchanged", ledger)

    def test_the_critical_grade_does_not_follow_severity_block(self):
        """크리티컬급은 P0·P1·크리티컬 P2 로 고정이다. 수렴용 `severity_block` 을 바꿔도 P0 보호가 빠지거나
        P3 까지 막히지 않는다."""
        drop = [{"refuter": "r1", "verdict": "refuted", "reason": "base",
                 "drop_reason": "out_of_scope_preexisting"}]
        self.profile["pdca"]["review_loop"]["severity_block"] = ["P1"]
        self._write_profile()
        self._open()
        self._refused([_finding("F1", "P0", status="refuted", disposition=None,
                                preexisting=True, exposure="reach_changed", refute=drop)])
        self.profile["pdca"]["review_loop"]["severity_block"] = ["P0", "P1", "P3"]
        self._write_profile()
        self._open()
        self._ok_round(1, [_finding("F1", "P3", status="refuted", disposition=None,
                                    preexisting=True, exposure="touched", refute=drop)])

    def test_all_mode_keeps_recording_as_before(self):
        self.profile = _profile(None)
        self._write_profile()
        self._open()
        self._ok_round(1, [_critical("F1", severity="P1"), _finding("F2", "P3")])
        self.assertEqual(self._next()[0], "NEXT: CONTINUE")
        self.assertEqual(self._close("CONVERGED_RESIDUAL").returncode, 2)

    def test_closure_checks_are_recorded_and_listed(self):
        self._open()
        self._ok_round(1, [_finding("F1", "P3")],
                       closure=[{"ref": "rl-x:1:F3", "closed": False, "note": "재발"}])
        receipt = self._records()[-1]["receipt"]
        self.assertEqual(receipt["unclosed"], 1)
        self.assertIn("rl-x:1:F3", self._run("ledger", "show", "--cycle-stem", STEM).stdout)


class TestFastMinimum(unittest.TestCase):
    def _records(self, rounds, fast_minimum=2, cap=None, mode=None):
        cfg = {}
        if cap is not None:
            cfg["max_cycle_rounds"] = {"L3": cap}
        if mode:
            cfg["converge_on"] = mode
        opened = {"event": "loop_open", "run_id": "rl-1", "risk": "L3", "cfg": cfg,
                  "cycle_stem": STEM}
        if fast_minimum is not None:
            opened["fast_minimum_rounds"] = fast_minimum
        return [opened] + [{"event": "round", "run_id": "rl-1", "iteration": i, "found": 0,
                            "survived": 0, "accepted": 0, "arch": 0, "tokens": 0}
                           for i in range(1, rounds + 1)]

    def test_convergence_below_the_fast_minimum_continues(self):
        verdict = la.loop_verdict(self._records(1), "rl-1", {}, "L3")
        self.assertEqual((verdict["action"], verdict["basis"]), ("CONTINUE", "fast_minimum"))
        verdict = la.loop_verdict(self._records(2), "rl-1", {}, "L3")
        self.assertEqual((verdict["action"], verdict["reason"]), ("STOP", "CONVERGED"))

    def test_runs_without_the_snapshot_are_unchanged(self):
        verdict = la.loop_verdict(self._records(1, fast_minimum=None), "rl-1", {}, "L3")
        self.assertEqual((verdict["action"], verdict["reason"]), ("STOP", "CONVERGED"))

    def test_the_cycle_cap_below_the_fast_minimum_asks_instead_of_deadlocking(self):
        verdict = la.loop_verdict(self._records(1, cap=1), "rl-1", {}, "L3")
        self.assertEqual((verdict["action"], verdict["reason"]), ("ASK", "CYCLE_CAP"))

    def test_open_records_the_fast_minimum_of_the_one_live_fast_run(self):
        import fast_cycle_audit as fca  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as root:
            Path(root, "sage").mkdir()
            import yaml  # noqa: PLC0415
            Path(root, "sage", "project-profile.yaml").write_text(
                yaml.safe_dump(_profile(None)), encoding="utf-8")
            fca.open_fast(root, cycle_stem=STEM, actual_risk="L3", fast_review_level="L3",
                          reason="긴급", minimum_rounds=3, lenses=["correctness", "security"],
                          profile_hash="sha256:" + "0" * 64, plan_hash_open="0" * 64)
            environ = dict(os.environ, PYTHONPATH=REPO)
            environ.pop("SAGE_CYCLE_STEM", None)
            result = subprocess.run([sys.executable, "-m", "sage", "review-loop", "open",
                                     "--risk", "L3", "--cycle-stem", STEM, "--root", root],
                                    text=True, capture_output=True, env=environ, cwd=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            opened = la.read_records(root)[0]
            self.assertEqual(opened["fast_minimum_rounds"], 3)


# 1단계 `loop_verdict` 사본 — `converge_on` 이 없는 run 의 판정은 이것과 같아야 한다.
def _stage1_verdict(records, run_id, cfg, risk):
    rounds = [r for r in records if r.get("event") == "round" and r.get("run_id") == run_id]
    budget = la._tier_int(cfg, "budget_tokens", risk)
    max_iter = la._tier_int(cfg, "max_iterations", risk)
    cycle = la.run_cycle_state(records, run_id)
    tokens = la.budget_tokens_of(rounds)
    if not rounds:
        if cycle is not None and cycle["reached"]:
            return ("ASK", None, "CYCLE_CAP", "cycle_cap")
        return ("CONTINUE", None, None, "no_rounds")
    converged = int(rounds[-1].get("survived", 0) or 0) == 0
    if any(int(r.get("arch", 0) or 0) > 0 for r in rounds):
        return ("STOP", "BLOCKED", "BLOCKED_ARCH", "arch_escalated")
    if budget is not None and tokens >= budget:
        return ("STOP", "BLOCKED", "BUDGET_TOK", "over_budget")
    if max_iter is not None and len(rounds) >= max_iter:
        if converged:
            return ("STOP", "APPROVED", "CONVERGED", "max_iter_converged")
        return ("STOP", "BLOCKED", "BUDGET_ITER", "max_iter_unresolved")
    if cycle is not None and cycle["reached"] and not converged:
        return ("ASK", None, "CYCLE_CAP", "cycle_cap")
    if converged:
        return ("STOP", "APPROVED", "CONVERGED", "converged")
    return ("CONTINUE", None, None, "continue")


class TestAllModeUnchanged(unittest.TestCase):
    def test_every_combination_matches_stage_one(self):
        count = 0
        for (n_rounds, survived, arch, tokens, max_iter, cap, receipt,
             critical) in itertools.product((0, 1, 2, 3), (0, 1, 2), (0, 1), (10, 1000),
                                            (None, 1, 2, 3), (1, 2, 5),
                                            (False, True), (False, True)):
            cfg = {"budget_tokens": {"L3": 500}, "max_cycle_rounds": {"L3": cap}}
            if max_iter is not None:
                cfg["max_iterations"] = {"L3": max_iter}
            records = [{"event": "loop_open", "run_id": "rl-1", "risk": "L3", "cfg": cfg,
                        "cycle_stem": STEM}]
            for i in range(1, n_rounds + 1):
                record = {"event": "round", "run_id": "rl-1", "iteration": i, "found": 3,
                          "survived": survived, "accepted": 0, "arch": arch,
                          "tokens": tokens}
                if receipt:
                    record["survived_by_severity"] = {"P0": 0, "P1": 0, "P2": survived, "P3": 0}
                    record["receipt"] = {"critical": int(critical), "refute_pending": 0,
                                         "unexplored": 0, "critical_findings": (
                                             [{"id": "F1", "claim_sha256": "a" * 64}]
                                             if critical else [])}
                records.append(record)
            new = la.loop_verdict(records, "rl-1", cfg, "L3")
            got = (new["action"], new["result"], new["reason"], new["basis"])
            self.assertEqual(got, _stage1_verdict(records, "rl-1", cfg, "L3"),
                             (n_rounds, survived, arch, tokens, max_iter, cap, receipt, critical))
            count += 1
        self.assertEqual(count, 4 * 3 * 2 * 2 * 4 * 3 * 2 * 2)


class TestAssuranceLayers(unittest.TestCase):
    def setUp(self):
        import pre_implementation_gate_core as core  # noqa: PLC0415
        self.core = core

    def _doc(self, assurance="REDUCED_BY_POLICY", reason="CONVERGED_RESIDUAL"):
        return ("Final Status: APPROVED\nLoop-Run: rl-1\n"
                f"Review-Assurance: {assurance}\nReview-Close-Reason: {reason}\n"
                "Review-Rounds: 2 (configured max: 3)\n"
                "Residual-Findings: P0=0, P1=0, P2=1, P3=1\n")

    def _run(self, reason="CONVERGED_RESIDUAL"):
        return {"close_reason": reason, "completed_rounds": 2, "configured_max_iterations": 3,
                "survived_by_severity": {"P0": 0, "P1": 0, "P2": 1, "P3": 1}}

    def test_the_gate_matches_the_policy_token(self):
        self.assertEqual(self.core._reduced_assurance_issues(self._doc(), self._run()), [])
        wrong = self._doc(assurance="REDUCED_BY_USER_AUTHORIZATION")
        self.assertNotEqual(self.core._reduced_assurance_issues(wrong, self._run()), [])
        missing = "Final Status: APPROVED\nLoop-Run: rl-1\n"
        self.assertNotEqual(self.core._reduced_assurance_issues(missing, self._run()), [])

    def test_a_standard_close_may_not_claim_the_policy_token(self):
        for doc in (self._doc(), "Review-Assurance: REDUCED_BY_POLICY\n",
                    "Review-Close-Reason: CONVERGED_RESIDUAL\n"):
            with self.subTest(doc=doc):
                self.assertNotEqual(
                    self.core._reduced_assurance_issues(doc, self._run("CONVERGED")), [])

    def test_the_early_close_contract_is_unchanged(self):
        doc = self._doc("REDUCED_BY_USER_AUTHORIZATION", "USER_AUTHORIZED_EARLY")
        self.assertEqual(self.core._reduced_assurance_issues(doc, self._run("USER_AUTHORIZED_EARLY")),
                         [])
        self.assertNotEqual(self.core._reduced_assurance_issues(
            self._doc(), self._run("USER_AUTHORIZED_EARLY")), [])


class TestProfileKeys(unittest.TestCase):
    def _issues(self, **review):
        profile = {"pdca": {"review_loop": dict(review)}}
        return [(severity, str(issue)) for severity, issue in validate_profile(profile, REPO)
                if any(key in str(issue) or key in str(getattr(issue, "arguments", ""))
                       or key in str(getattr(issue, "code", ""))
                       for key in ("converge_on", "critical_p2"))]

    def test_valid_values_pass(self):
        self.assertEqual(self._issues(converge_on="blocking"), [])
        self.assertEqual(self._issues(converge_on="all", critical_p2=["deploy_breakage"]), [])

    def test_invalid_values_fail(self):
        for review in ({"converge_on": "block"}, {"converge_on": True}, {"critical_p2": []},
                       {"critical_p2": ["Deploy"]}, {"critical_p2": ["a", "a"]},
                       {"critical_p2": "deploy_breakage"}):
            with self.subTest(review=review):
                self.assertTrue(any(sev == "FAIL" for sev, _ in self._issues(**review)))


class TestCompactReentry(unittest.TestCase):
    def test_the_reentry_context_names_the_critical_question(self):
        import compact_reentry  # noqa: PLC0415
        records = [{"event": "loop_open", "run_id": "rl-1", "risk": "L3",
                    "cfg": {"converge_on": "blocking"}, "cycle_stem": STEM},
                   {"event": "round", "run_id": "rl-1", "iteration": 1, "found": 1,
                    "survived": 1, "accepted": 0, "arch": 0, "tokens": 0,
                    "survived_by_severity": {"P0": 0, "P1": 0, "P2": 1, "P3": 0},
                    "receipt": {"critical": 1, "refute_pending": 0, "unexplored": 0,
                                "critical_findings": [{"id": "F7", "claim_sha256": "b" * 64}]}}]
        lines = compact_reentry._loop_lines("en", records, STEM, {})
        self.assertIn("CRITICAL_P2", lines[0])
        self.assertIn("F7", lines[0])


if __name__ == "__main__":
    unittest.main()
