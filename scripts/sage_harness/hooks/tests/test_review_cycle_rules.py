#!/usr/bin/env python3
"""Phase 05 리뷰 규칙 1단계 — 라운드 사이드카·사이클 상한(ASK)·decide·CYCLE_CAP·상한 잔여 승인·장부.

run 을 새로 열 때마다 반복 카운터가 0 으로 돌아가 사이클 전체가 몇 라운드를 돌았는지 엔진이 몰랐다.
이 파일은 그 집계가 run 을 넘어 이어지는지, 상한에서 사람에게 묻는지(그 전에는 라운드를 열 수
없는지), 그리고 그 질문이 우회되지 않는지를 본다. 사이드카는 개수를 손으로 쓰지 않게 하는 장치라,
산출값과 손으로 준 값이 다르면 아무것도 쓰지 않는지를 본다.
"""
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


def _base_profile():
    return {"pdca": {
        "phases": [{"id": "00", "glob": "plan_docs/00-base_plan/**/*.md"}],
        "review_loop": {
            "enabled": True,
            "lenses": ["correctness", "security"],
            "refuters": 1,
            "max_iterations": {"L2": 10, "L3": 10},
            "budget_tokens": {"L2": 10_000_000, "L3": 10_000_000},
            "severity_block": ["P0", "P1"],
            "early_completion": {"enabled": True, "minimum_completed_rounds": 1},
        },
    }}


class _CliCase(unittest.TestCase):
    RISK = "L2"   # 기본 사이클 상한 3 — 테스트가 짧다

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        Path(self.root, "sage").mkdir()
        self.profile = _base_profile()
        self._write_profile()

    def _write_profile(self):
        import yaml  # noqa: PLC0415
        Path(self.root, "sage", "project-profile.yaml").write_text(
            yaml.safe_dump(self.profile, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def _run(self, *args, env=None):
        environ = dict(os.environ, PYTHONPATH=REPO)
        environ.pop("SAGE_CYCLE_STEM", None)
        environ.update(env or {})
        return subprocess.run([sys.executable, "-m", "sage", "review-loop", *args,
                               "--root", self.root],
                              text=True, capture_output=True, env=environ, cwd=self.root)

    def _open(self, stem=STEM, risk=None):
        args = ["open", "--risk", risk or self.RISK]
        if stem is not None:
            args += ["--cycle-stem", stem]
        result = self._run(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip().splitlines()[0]

    def _round(self, rid, iteration, survived=1, severity=None, **extra):
        severity = severity or f"P0=0,P1=0,P2={survived},P3=0"
        args = ["round", "--run-id", rid, "--iteration", str(iteration),
                "--found", str(max(survived, 1)), "--survived", str(survived),
                "--accepted", "0", "--survived-by-severity", severity]
        for key, value in extra.items():
            args += [f"--{key.replace('_', '-')}", str(value)]
        return self._run(*args)

    def _next(self, rid):
        result = self._run("next", "--run-id", rid)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip().splitlines()[-1]

    def _records(self):
        path = Path(self.root, ".sage", "loop_audit.jsonl")
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class TestCycleBinding(_CliCase):
    def test_open_without_any_cycle_is_refused_and_writes_nothing(self):
        result = self._run("open", "--risk", "L2")
        self.assertEqual(result.returncode, 2)
        self.assertIn("sage cycle set", result.stderr)
        self.assertEqual(self._records(), [])

    def test_open_uses_the_file_declaration(self):
        Path(self.root, ".sage").mkdir(exist_ok=True)
        Path(self.root, ".sage", "cycle.json").write_text(json.dumps(
            {"version": 2, "cycle_stem": STEM, "document_language": "ko",
             "declared_at": "2026-10-02T00:00:00Z"}), encoding="utf-8")
        result = self._run("open", "--risk", "L2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._records()[0]["cycle_stem"], STEM)

    def test_env_wins_over_the_file_like_the_gate(self):
        Path(self.root, ".sage").mkdir(exist_ok=True)
        Path(self.root, ".sage", "cycle.json").write_text(json.dumps(
            {"version": 2, "cycle_stem": "from-file", "document_language": "ko",
             "declared_at": "2026-10-02T00:00:00Z"}), encoding="utf-8")
        result = self._run("open", "--risk", "L2", env={"SAGE_CYCLE_STEM": "from-env"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._records()[0]["cycle_stem"], "from-env")

    def test_explicit_stem_that_differs_from_the_declaration_warns(self):
        result = self._run("open", "--risk", "L2", "--cycle-stem", "explicit",
                           env={"SAGE_CYCLE_STEM": "declared"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("declared", result.stderr)
        self.assertEqual(self._records()[0]["cycle_stem"], "explicit")

    def test_an_invalid_stem_is_refused(self):
        result = self._run("open", "--risk", "L2", "--cycle-stem", "a/b")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self._records(), [])


class TestCycleCap(_CliCase):
    def test_rounds_add_up_across_runs_and_the_cap_asks(self):
        first = self._open()
        for i in (1, 2):
            self.assertEqual(self._round(first, i).returncode, 0)
        self.assertEqual(self._run("close", "--run-id", first, "--result", "BLOCKED",
                                   "--reason", "BUDGET_TOK", "--iterations", "2").returncode, 0)
        second = self._open()
        self.assertEqual(self._next(second), "NEXT: CONTINUE")
        self.assertEqual(self._round(second, 1).returncode, 0)
        self.assertEqual(self._next(second), "NEXT: ASK kind=CYCLE_CAP cycle_rounds=3 cap=3")

    def test_a_new_run_after_the_cap_asks_before_its_first_round(self):
        first = self._open()
        for i in (1, 2, 3):
            self.assertEqual(self._round(first, i).returncode, 0)
        self._run("close", "--run-id", first, "--result", "BLOCKED", "--reason", "CYCLE_CAP",
                  "--iterations", "3")
        second = self._open()
        self.assertTrue(self._next(second).startswith("NEXT: ASK kind=CYCLE_CAP"))
        refused = self._round(second, 1)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("decide", refused.stderr)

    def test_converging_on_the_cap_round_is_a_normal_approval(self):
        rid = self._open()
        self._round(rid, 1)
        self._round(rid, 2)
        self._round(rid, 3, survived=0, severity="P0=0,P1=0,P2=0,P3=0")
        self.assertEqual(self._next(rid), "NEXT: STOP result=APPROVED reason=CONVERGED")

    def test_the_run_iteration_cap_comes_before_the_cycle_cap(self):
        self.profile["pdca"]["review_loop"]["max_iterations"] = {"L2": 3, "L3": 3}
        self._write_profile()
        rid = self._open()
        for i in (1, 2, 3):
            self._round(rid, i)
        self.assertEqual(self._next(rid), "NEXT: STOP result=BLOCKED reason=BUDGET_ITER")

    def test_the_profile_cap_overrides_the_default(self):
        self.profile["pdca"]["review_loop"]["max_cycle_rounds"] = {"L2": 1, "L3": 5}
        self._write_profile()
        rid = self._open()
        self._round(rid, 1)
        self.assertEqual(self._next(rid), "NEXT: ASK kind=CYCLE_CAP cycle_rounds=1 cap=1")

    def test_one_cycle_has_one_cap_whichever_run_is_asked(self):
        older = la.open_loop(self.root, "L2", cfg={"max_cycle_rounds": {"L2": 10}},
                             cycle_stem=STEM)
        la.record_round(self.root, older, 1, 1, 1, 0)
        newer = la.open_loop(self.root, "L2", cfg={"max_cycle_rounds": {"L2": 1}},
                             cycle_stem=STEM)
        records = la.read_records(self.root)
        caps = [la.run_cycle_state(records, rid)["cap"] for rid in (older, newer)]
        self.assertEqual(caps, [1, 1])
        with self.assertRaises(la.AuditWriteError):
            la.record_round(self.root, older, 2, 1, 1, 0)

    def test_next_shows_the_cycle_usage(self):
        first = self._open()
        self._round(first, 1, tokens=120)
        self._run("close", "--run-id", first, "--result", "BLOCKED", "--reason", "BUDGET_ITER",
                  "--iterations", "1")
        second = self._open()
        self._round(second, 1, tokens=30)
        shown = self._run("next", "--run-id", second)
        self.assertIn("누적 사용량 150", shown.stderr)

    def test_other_cycles_are_not_counted(self):
        other = self._open(stem="other-cycle")
        for i in (1, 2, 3):
            self._round(other, i)
        rid = self._open()
        self.assertEqual(self._next(rid), "NEXT: CONTINUE")
        self.assertEqual(self._round(rid, 1).returncode, 0)

    def test_the_lock_refuses_a_round_even_when_the_cli_check_is_skipped(self):
        rid = self._open()
        for i in (1, 2, 3):
            self._round(rid, i)
        with self.assertRaises(la.AuditWriteError) as caught:
            la.record_round(self.root, rid, 4, 1, 1, 0)
        self.assertIn("round cap", str(caught.exception))

    def test_a_legacy_unbound_run_is_not_capped_retroactively(self):
        rid = la.open_loop(self.root, "L2", cfg=self.profile["pdca"]["review_loop"])
        for i in (1, 2, 3, 4):
            la.record_round(self.root, rid, i, 1, 1, 0)
        self.assertEqual(self._next(rid), "NEXT: CONTINUE")
        shown = self._run("next", "--run-id", rid)
        self.assertIn(rid, shown.stderr)


class TestDecide(_CliCase):
    def _capped(self):
        rid = self._open()
        for i in (1, 2, 3):
            self._round(rid, i)
        return rid

    def _decide(self, rid, extend="2", reason="한 번 더 본다", by="sejon"):
        return self._run("decide", "--run-id", rid, "--cycle", "continue", "--extend", extend,
                         "--reason", reason, "--decided-by", by)

    def test_continue_extends_the_cap_and_is_recorded(self):
        rid = self._capped()
        result = self._decide(rid)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._next(rid), "NEXT: CONTINUE")
        decision = [r for r in self._records() if r.get("event") == "decision"][-1]
        self.assertEqual((decision["kind"], decision["choice"], decision["extend"]),
                         ("cycle_cap", "continue", 2))
        self.assertEqual((decision["cap_before"], decision["cap_after"]), (3, 5))
        self.assertEqual(decision["cycle_stem"], STEM)
        self.assertEqual(decision["decided_by"], "sejon")
        self.assertEqual(self._round(rid, 4).returncode, 0)
        self.assertEqual(la.integrity_issues(self.root), [])

    def test_deciding_before_the_cap_is_refused(self):
        rid = self._open()
        self._round(rid, 1)
        result = self._decide(rid)
        self.assertEqual(result.returncode, 2)
        self.assertEqual([r for r in self._records() if r.get("event") == "decision"], [])

    def test_bad_extend_and_empty_lines_are_refused(self):
        rid = self._capped()
        for args in (("0",), ("11",)):
            self.assertEqual(self._decide(rid, extend=args[0]).returncode, 2)
        self.assertEqual(self._decide(rid, reason="  ").returncode, 2)
        self.assertEqual(self._decide(rid, by="").returncode, 2)
        self.assertEqual([r for r in self._records() if r.get("event") == "decision"], [])

    def test_a_stop_verdict_at_the_cap_cannot_be_extended(self):
        self.profile["pdca"]["review_loop"]["budget_tokens"] = {"L2": 50, "L3": 50}
        self._write_profile()
        rid = self._open()
        for i in (1, 2, 3):
            self._round(rid, i, tokens=100 if i == 3 else 0)
        self.assertEqual(self._next(rid), "NEXT: STOP result=BLOCKED reason=BUDGET_TOK")
        result = self._decide(rid)
        self.assertEqual(result.returncode, 2)
        self.assertIn("BUDGET_TOK", result.stderr)
        # CLI 검사를 건너뛰어도 잠금 안에서 같은 판정으로 거부한다.
        with self.assertRaises(la.AuditWriteError):
            la.record_decision(self.root, rid, la.DECISION_CYCLE_CAP, "continue", "r", "u",
                               extend=1, cfg=self.profile["pdca"]["review_loop"], risk="L2")
        self.assertEqual([r for r in self._records() if r.get("event") == "decision"], [])

    def test_a_closed_run_cannot_take_a_decision(self):
        rid = self._capped()
        self._run("close", "--run-id", rid, "--result", "BLOCKED", "--reason", "CYCLE_CAP",
                  "--iterations", "3")
        self.assertEqual(self._decide(rid).returncode, 2)

    def test_integrity_flags_decisions_without_an_open_or_after_close(self):
        records = [
            {"event": "decision", "run_id": "rl-ghost", "seq": 0},
            {"event": "loop_open", "run_id": "rl-a", "seq": 0},
            {"event": "loop_close", "run_id": "rl-a", "seq": 1},
            {"event": "decision", "run_id": "rl-a", "seq": 2},
        ]
        codes = [issue["code"] for issue in la.integrity_from_records(records, [])]
        self.assertIn("loop_audit.orphan_event", codes)
        self.assertIn("loop_audit.event_after_close", codes)


class TestCycleCapClose(_CliCase):
    def test_cycle_cap_close_below_the_cap_is_a_mismatch_under_enforce(self):
        self.profile["pdca"]["review_loop"]["termination_enforce"] = "enforce"
        self._write_profile()
        rid = self._open()
        self._round(rid, 1)
        result = self._run("close", "--run-id", rid, "--result", "BLOCKED", "--reason",
                           "CYCLE_CAP", "--iterations", "1")
        self.assertEqual(result.returncode, 2)

    def test_cycle_cap_close_at_the_cap_passes_under_enforce(self):
        self.profile["pdca"]["review_loop"]["termination_enforce"] = "enforce"
        self._write_profile()
        rid = self._open()
        for i in (1, 2, 3):
            self._round(rid, i)
        result = self._run("close", "--run-id", rid, "--result", "BLOCKED", "--reason",
                           "CYCLE_CAP", "--iterations", "3")
        self.assertEqual(result.returncode, 0, result.stderr)


class TestResidualApprovalAtTheCaps(_CliCase):
    def _early(self, rid, iterations):
        return self._run("close", "--run-id", rid, "--result", "APPROVED", "--reason",
                         "USER_AUTHORIZED_EARLY", "--iterations", str(iterations),
                         "--authorization-reason", "P2 하나는 다음 사이클", "--confirmed-by",
                         "sejon", "--confirm", "USER_AUTHORIZED_EARLY")

    def test_budget_iter_stop_can_close_with_only_nonblocking_residuals(self):
        self.profile["pdca"]["review_loop"]["max_iterations"] = {"L2": 2, "L3": 2}
        self._write_profile()
        rid = self._open()
        self._round(rid, 1)
        self._round(rid, 2)
        self.assertEqual(self._next(rid), "NEXT: STOP result=BLOCKED reason=BUDGET_ITER")
        result = self._early(rid, 2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("next normal verdict: STOP:BUDGET_ITER", result.stderr)
        close = [r for r in self._records() if r.get("event") == "loop_close"][-1]
        self.assertEqual(close["stopped_at"], "STOP:BUDGET_ITER")

    def test_budget_iter_stop_with_a_blocking_survivor_is_still_refused(self):
        self.profile["pdca"]["review_loop"]["max_iterations"] = {"L2": 1, "L3": 1}
        self._write_profile()
        rid = self._open()
        self._round(rid, 1, severity="P0=0,P1=1,P2=0,P3=0")
        result = self._early(rid, 1)
        self.assertEqual(result.returncode, 2)
        self.assertIn("blocking severities", result.stderr)

    def test_cycle_cap_ask_can_close_with_residual_approval(self):
        rid = self._open()
        for i in (1, 2, 3):
            self._round(rid, i)
        result = self._early(rid, 3)
        self.assertEqual(result.returncode, 0, result.stderr)
        close = [r for r in self._records() if r.get("event") == "loop_close"][-1]
        self.assertEqual(close["stopped_at"], "ASK:CYCLE_CAP")

    def test_budget_tok_stop_cannot_be_closed_by_authorization(self):
        self.profile["pdca"]["review_loop"]["budget_tokens"] = {"L2": 10, "L3": 10}
        self._write_profile()
        rid = self._open()
        self._round(rid, 1, tokens=100)
        result = self._early(rid, 1)
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be closed by user authorization", result.stderr)
        self.assertEqual([r for r in self._records() if r.get("event") == "loop_close"], [])

    def test_a_run_with_no_round_at_the_cycle_cap_cannot_close_early(self):
        first = self._open()
        for i in (1, 2, 3):
            self._round(first, i)
        self._run("close", "--run-id", first, "--result", "BLOCKED", "--reason", "CYCLE_CAP",
                  "--iterations", "3")
        second = self._open()
        result = self._early(second, 0)
        self.assertEqual(result.returncode, 2)

    def test_the_disclosure_lists_sidecar_residuals(self):
        rid = self._open()
        sidecar = {"schema": rr.SCHEMA, "run_id": rid, "iteration": 1, "findings": [
            {"id": "F1", "source": {"kind": "lens", "name": "security"}, "file": "a.py",
             "line": 3, "severity": "P2", "claim": "남는 지적", "status": "survived",
             "disposition": "residual"}]}
        path = Path(self.root, "side.json")
        path.write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(self._run("round", "--run-id", rid, "--iteration", "1",
                                   "--findings-file", str(path)).returncode, 0)
        result = self._early(rid, 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("F1 P2 a.py:3", result.stderr)


class TestSidecarRound(_CliCase):
    def _sidecar(self, rid, iteration=1, findings=None, **extra):
        doc = {"schema": rr.SCHEMA, "run_id": rid, "iteration": iteration,
               "findings": findings if findings is not None else [
                   {"id": "F1", "source": {"kind": "lens", "name": "security"},
                    "severity": "P1", "claim": "고칠 것", "status": "survived",
                    "disposition": "fix", "file": "a.txt", "line": 1},
                   {"id": "F2", "source": {"kind": "peer", "name": "codex"},
                    "severity": "P3", "claim": "탈락", "status": "refuted",
                    "refute": [{"refuter": "r1", "verdict": "refuted", "reason": "HEAD 동일",
                                "drop_reason": "out_of_scope_preexisting"}]}]}
        doc.update(extra)
        path = Path(self.root, f"side-{iteration}.json")
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def _record(self, rid, iteration=1, *extra, **kw):
        return self._run("round", "--run-id", rid, "--iteration", str(iteration),
                         "--findings-file", self._sidecar(rid, iteration, **kw), *extra)

    def test_counts_and_receipt_come_from_the_sidecar(self):
        rid = self._open()
        result = self._record(rid)
        self.assertEqual(result.returncode, 0, result.stderr)
        rnd = [r for r in self._records() if r.get("event") == "round"][-1]
        self.assertEqual((rnd["found"], rnd["survived"], rnd["accepted"], rnd["arch"]),
                         (2, 1, 1, 0))
        self.assertEqual(rnd["survived_by_severity"], {"P0": 0, "P1": 1, "P2": 0, "P3": 0})
        self.assertEqual(rnd["receipt"]["refuted_out_of_scope"], 1)
        stored = Path(self.root, rnd["sidecar"]["path"])
        self.assertTrue(stored.is_file())
        self.assertEqual(rr.sha256_hex(stored.read_bytes()), rnd["sidecar"]["sha256"])

    def test_hand_counts_that_disagree_are_refused_and_nothing_is_written(self):
        rid = self._open()
        result = self._record(rid, 1, "--survived", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("disagree", result.stderr)
        self.assertEqual([r for r in self._records() if r.get("event") == "round"], [])
        self.assertFalse(Path(self.root, ".sage", "review-rounds").exists())

    def test_matching_hand_counts_are_accepted(self):
        rid = self._open()
        result = self._record(rid, 1, "--found", "2", "--survived", "1",
                              "--survived-by-severity", "P0=0,P1=1,P2=0,P3=0")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_invalid_sidecar_is_refused(self):
        rid = self._open()
        bad = [{"id": "F1", "source": {"kind": "lens", "name": "x"}, "severity": "P9",
                "claim": "c", "status": "survived"}]
        result = self._record(rid, findings=bad)
        self.assertEqual(result.returncode, 2)
        self.assertIn("severity", result.stderr)
        self.assertEqual([r for r in self._records() if r.get("event") == "round"], [])

    def test_a_sidecar_for_another_run_or_iteration_is_refused(self):
        rid = self._open()
        path = self._sidecar("rl-000000000000")
        result = self._run("round", "--run-id", rid, "--iteration", "1", "--findings-file", path)
        self.assertEqual(result.returncode, 2)
        path = self._sidecar(rid, iteration=5)
        result = self._run("round", "--run-id", rid, "--iteration", "1", "--findings-file", path)
        self.assertEqual(result.returncode, 2)

    def test_peer_usage_must_match_the_measured_tokens(self):
        rid = self._open()
        result = self._record(rid, 1, "--peer-tokens", "new_input=10 output=5",
                              usage={"peer": {"new_input": 99, "output": 5}})
        self.assertEqual(result.returncode, 2)
        self.assertIn("--peer-tokens", result.stderr)

    def test_a_round_without_sidecar_is_marked_absent(self):
        rid = self._open()
        self.assertEqual(self._round(rid, 1).returncode, 0)
        rnd = [r for r in self._records() if r.get("event") == "round"][-1]
        self.assertEqual(rnd["sidecar"], "absent")
        # 작업 트리 식별자는 사이드카와 무관하게 남는다(여기는 git 밖이라 사유만).
        self.assertIn("tree", rnd)

    def test_without_sidecar_the_counts_are_required(self):
        rid = self._open()
        result = self._run("round", "--run-id", rid, "--iteration", "1", "--found", "1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--survived", result.stderr)

    def test_tree_and_delta_in_a_git_repository(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        Path(self.root, "a.txt").write_text("one\n", encoding="utf-8")
        rid = self._open()
        self.assertEqual(self._record(rid, 1).returncode, 0)
        Path(self.root, "a.txt").write_text("two\n", encoding="utf-8")
        self.assertEqual(self._record(rid, 2).returncode, 0)
        rounds = [r for r in self._records() if r.get("event") == "round"]
        first, second = rounds[0]["tree"], rounds[1]["tree"]
        self.assertEqual(first["note"], "first_round")
        self.assertEqual(second["prev"], first["id"])
        patch = Path(self.root, second["patch"]).read_text(encoding="utf-8")
        self.assertIn("+two", patch)
        self.assertNotIn(".sage/", patch)
        status = subprocess.run(["git", "status", "--porcelain"], cwd=self.root,
                                capture_output=True, text=True).stdout
        self.assertNotIn("A ", status)   # 실제 index 는 건드리지 않는다

    def test_outside_git_the_round_is_still_recorded(self):
        rid = self._open()
        env_git = dict(GIT_CEILING_DIRECTORIES=os.path.dirname(self.root))
        result = self._run("round", "--run-id", rid, "--iteration", "1",
                           "--findings-file", self._sidecar(rid), env=env_git)
        self.assertEqual(result.returncode, 0, result.stderr)
        tree = [r for r in self._records() if r.get("event") == "round"][-1]["tree"]
        self.assertIsNone(tree["id"])
        self.assertTrue(tree["note"].startswith("git_unavailable"))


    def test_every_round_keeps_the_tree_so_the_delta_is_from_the_previous_round(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        Path(self.root, "a.txt").write_text("one\n", encoding="utf-8")
        rid = self._open()
        self.assertEqual(self._record(rid, 1).returncode, 0)
        Path(self.root, "a.txt").write_text("two\n", encoding="utf-8")
        self.assertEqual(self._round(rid, 2).returncode, 0)        # 사이드카 없음
        Path(self.root, "a.txt").write_text("three\n", encoding="utf-8")
        self.assertEqual(self._record(rid, 3).returncode, 0)
        trees = [r["tree"] for r in self._records() if r.get("event") == "round"]
        self.assertEqual(trees[1]["prev"], trees[0]["id"])
        self.assertEqual(trees[2]["prev"], trees[1]["id"])
        patch = Path(self.root, trees[2]["patch"]).read_text(encoding="utf-8")
        self.assertIn("-two", patch)
        self.assertNotIn("-one", patch)

    def test_a_previous_round_without_a_tree_is_not_skipped_over(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        rid = self._open()
        self.assertEqual(self._record(rid, 1).returncode, 0)
        la.record_round(self.root, rid, 2, 1, 1, 0)                 # 업그레이드 전 모양: tree 없음
        self.assertEqual(self._record(rid, 3).returncode, 0)
        tree = [r for r in self._records() if r.get("event") == "round"][-1]["tree"]
        self.assertIsNone(tree["prev"])
        self.assertEqual(tree["note"], "previous_round_without_tree")
        self.assertIsNone(tree["patch"])

    def test_peer_usage_values_are_checked_even_without_peer_tokens(self):
        rid = self._open()
        for peer in ({"new_input": -2, "output": 1}, {"new_input": 1, "output": "bad"},
                     {"new_input": 1, "output": 1, "measured": "fake"}, {"output": 1},
                     {"new_input": 1, "output": 1, "cached_input": None},
                     {"new_input": 1, "output": 1, "cost_usd": None},
                     {"new_input": 1, "output": 1, "cost_usd": float("inf")}):
            with self.subTest(peer=peer):
                result = self._record(rid, 1, usage={"peer": peer})
                self.assertEqual(result.returncode, 2)
                self.assertIn("usage.peer", result.stderr)
        self.assertEqual([r for r in self._records() if r.get("event") == "round"], [])


class TestLedger(_CliCase):
    def test_add_show_render_and_withdraw(self):
        rid = self._open()
        sidecar = {"schema": rr.SCHEMA, "run_id": rid, "iteration": 1, "findings": [
            {"id": "F1", "source": {"kind": "lens", "name": "x"}, "severity": "P3",
             "claim": "남김", "status": "survived", "disposition": "residual"},
            {"id": "F2", "source": {"kind": "lens", "name": "x"}, "severity": "P2",
             "claim": "다시 올림", "status": "survived", "disposition": "fix",
             "ledger_ref": "L-1"}]}
        path = Path(self.root, "side.json")
        path.write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
        self._run("round", "--run-id", rid, "--iteration", "1", "--findings-file", str(path))
        added = self._run("ledger", "add", "--cycle-stem", STEM, "--kind", "out_of_scope",
                          "--source", "04 F-4", "--reason", "선재 결함", "--severity", "P0",
                          "--location", "server.js:44")
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertEqual(added.stdout.strip(), "L-1")
        shown = self._run("ledger", "show", "--cycle-stem", STEM)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        for needle in ("L-1", "선재 결함", "F1", "남김", "L-1"):
            self.assertIn(needle, shown.stdout)
        rendered = self._run("ledger", "render", "--cycle-stem", STEM)
        self.assertIn("ledger render", rendered.stdout)
        self.assertIn("server.js:44", rendered.stdout)
        withdraw = self._run("ledger", "add", "--cycle-stem", STEM, "--kind", "withdraw",
                             "--ref", "L-1", "--reason", "범위에 넣기로")
        self.assertEqual(withdraw.returncode, 0, withdraw.stderr)
        self.assertNotIn("선재 결함", self._run("ledger", "render", "--cycle-stem",
                                                 STEM).stdout)

    def test_a_tampered_sidecar_is_reported_not_silently_skipped(self):
        rid = self._open()
        sidecar = {"schema": rr.SCHEMA, "run_id": rid, "iteration": 1, "findings": []}
        path = Path(self.root, "side.json")
        path.write_text(json.dumps(sidecar), encoding="utf-8")
        self._run("round", "--run-id", rid, "--iteration", "1", "--findings-file", str(path))
        stored = [r for r in self._records() if r.get("event") == "round"][-1]["sidecar"]["path"]
        Path(self.root, stored).write_text("{}", encoding="utf-8")
        shown = self._run("ledger", "show", "--cycle-stem", STEM)
        self.assertEqual(shown.returncode, 1)
        self.assertIn("sha256", shown.stderr)
        rendered = self._run("ledger", "render", "--cycle-stem", STEM)
        self.assertIn("sha256", rendered.stdout)

    def test_withdrawing_an_unknown_entry_is_refused(self):
        result = self._run("ledger", "add", "--cycle-stem", STEM, "--kind", "withdraw",
                           "--ref", "L-9", "--reason", "x")
        self.assertEqual(result.returncode, 2)

    def test_a_symlinked_parent_does_not_lead_the_ledger_outside_the_project(self):
        with tempfile.TemporaryDirectory() as outside:
            Path(outside, STEM).mkdir()
            Path(outside, STEM, "entries.jsonl").write_text(json.dumps(
                {"id": "L-1", "kind": "preexisting", "reason": "바깥", "source": "x"}) + "\n",
                encoding="utf-8")
            Path(self.root, ".sage", "review-rounds").mkdir(parents=True)
            os.symlink(outside, Path(self.root, ".sage", "review-rounds", "cycles"))
            entries, issues = rr.read_entries(self.root, STEM)
            self.assertEqual(entries, [])
            self.assertTrue(any("symlink" in item for item in issues), issues)
            result = self._run("ledger", "show", "--cycle-stem", STEM)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("바깥", result.stdout)

    def test_a_damaged_ledger_is_reported_and_blocks_appends(self):
        self.assertEqual(self._run("ledger", "add", "--cycle-stem", STEM, "--kind",
                                   "preexisting", "--source", "04 §2", "--reason", "옛 결함"
                                   ).returncode, 0)
        path = Path(self.root, ".sage", "review-rounds", "cycles", STEM, "entries.jsonl")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"id": "L-1", "kind": "out_of_scope", "reason": "중복",
                                     "source": "x"}) + "\n")
            handle.write("{}\n")
            handle.write(json.dumps({"id": "L-3", "kind": "withdraw", "reason": "r",
                                     "ref": "L-9"}) + "\n")
            for bad_ref in ([], {"x": 1}, 7):
                handle.write(json.dumps({"id": "L-4", "kind": "withdraw", "reason": "r",
                                         "ref": bad_ref}) + "\n")
        entries, issues = rr.read_entries(self.root, STEM)
        self.assertEqual([item["id"] for item in entries], ["L-1"])
        self.assertTrue(any("duplicated" in item for item in issues), issues)
        self.assertTrue(any("kind must be" in item for item in issues), issues)
        self.assertTrue(any("unknown entry" in item for item in issues), issues)
        self.assertEqual(self._run("ledger", "show", "--cycle-stem", STEM).returncode, 1)
        rendered = self._run("ledger", "render", "--cycle-stem", STEM).stdout
        self.assertIn("duplicated", rendered)
        result = self._run("ledger", "add", "--cycle-stem", STEM, "--kind", "preexisting",
                           "--source", "x", "--reason", "y")
        self.assertEqual(result.returncode, 2)


class TestSidecarValidation(unittest.TestCase):
    def _doc(self, **finding):
        item = {"id": "F1", "source": {"kind": "lens", "name": "x"}, "severity": "P2",
                "claim": "c", "status": "survived"}
        item.update(finding)
        return {"schema": rr.SCHEMA, "run_id": "rl-0123456789ab", "iteration": 1,
                "findings": [item]}

    def test_defaults_are_filled_without_changing_meaning(self):
        doc = rr.validate(self._doc())
        item = doc["findings"][0]
        self.assertEqual((item["critical"], item["preexisting"], item["refute"], item["closes"]),
                         (False, None, [], []))

    def test_rejections(self):
        cases = [
            {"severity": "P5"}, {"status": "maybe"}, {"claim": ""}, {"claim": "x" * 9000},
            {"line": 0}, {"closes": ["bad"]}, {"ledger_ref": "X-1"}, {"unknown": 1},
            {"refute": [{"refuter": "r", "verdict": "no"}]}, {"id": "a b"},
        ]
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(rr.SidecarError):
                    rr.validate(self._doc(**case))

    def test_duplicate_ids_are_rejected(self):
        doc = self._doc()
        doc["findings"].append(dict(doc["findings"][0]))
        with self.assertRaises(rr.SidecarError):
            rr.validate(doc)

    def test_size_limit(self):
        with self.assertRaises(rr.SidecarError):
            rr.parse(b" " * (rr.MAX_SIDECAR_BYTES + 1))

    def test_an_input_that_grows_past_the_limit_when_normalized_is_refused(self):
        findings = [{"id": f"F{i}", "source": {"kind": "lens", "name": "x"}, "severity": "P3",
                     "claim": "c" * 1800, "status": "survived"} for i in range(500)]
        data = json.dumps({"schema": rr.SCHEMA, "run_id": "rl-0123456789ab", "iteration": 1,
                           "findings": findings}, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(data), rr.MAX_SIDECAR_BYTES)
        with self.assertRaises(rr.SidecarError) as caught:
            rr.parse(data)
        self.assertIn("normalized", str(caught.exception))

    def test_store_refuses_a_symlinked_directory(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            os.makedirs(os.path.join(root, ".sage"))
            os.symlink(outside, os.path.join(root, ".sage", "review-rounds"))
            with self.assertRaises(rr.SidecarError):
                rr.store(root, rr.validate(self._doc()))
            self.assertEqual(os.listdir(outside), [])


class TestProfileKey(unittest.TestCase):
    def _issues(self, value):
        profile = {"pdca": {"review_loop": {"max_cycle_rounds": value}}}
        return [(severity, str(issue)) for severity, issue in validate_profile(profile, REPO)
                if "max_cycle_rounds" in str(issue)
                or "max_cycle_rounds" in str(getattr(issue, "arguments", ""))]

    def test_valid_value_has_no_issue(self):
        self.assertEqual(self._issues({"L2": 3, "L3": 5}), [])

    def test_invalid_values_fail(self):
        for value in ({"L3": 0}, {"L3": True}, {"L2": "3"}, [3, 5]):
            with self.subTest(value=value):
                self.assertTrue(any(sev == "FAIL" for sev, _ in self._issues(value)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
