#!/usr/bin/env python3
"""loop_audit 단위 — Loop A(Phase 05 적대적 review-rework) 라운드별 append-only 감사.

검증:
  1. open_loop → run_id 발급 + loop_open 레코드(risk/cfg)
  2. record_round → round 레코드(found/survived/accepted/arch/tokens)
  3. close_loop → loop_close 레코드(result/reason/iterations)
  4. append-only: 다회 open/round/close 가 누적, run_id 별 격리
  5. 견고성: 손상 줄 skip, 부재 파일 → []
  6. 경로: .sage/loop_audit.jsonl (커밋 대상)
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = os.path.join(os.path.dirname(HERE), "runtime")
sys.path.insert(0, RUNTIME)
import loop_audit as la  # noqa: E402


class TestLoopAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_path_is_committed_sage_jsonl(self):
        self.assertTrue(la.audit_path(self.tmp).endswith(os.path.join(".sage", "loop_audit.jsonl")))

    def test_open_returns_run_id_and_records(self):
        rid = la.open_loop(self.tmp, "L3", cfg={"refuters": 2, "lenses": ["security"]}, now=1000)
        self.assertTrue(rid.startswith("rl-"))
        recs = la.read_records(self.tmp)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["event"], "loop_open")
        self.assertEqual(recs[0]["run_id"], rid)
        self.assertEqual(recs[0]["risk"], "L3")
        self.assertEqual(recs[0]["cfg"]["refuters"], 2)
        self.assertEqual(recs[0]["ts"], "1970-01-01T00:16:40Z")   # _iso(1000)

    def test_explicit_run_id_honored(self):
        rid = la.open_loop(self.tmp, "L2", run_id="rl-fixed123", now=0)
        self.assertEqual(rid, "rl-fixed123")

    def test_round_record_fields(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.record_round(self.tmp, rid, iteration=1, found=7, survived=3, accepted=3, arch=0, tokens=48213, now=1)
        rounds = la.rounds_of(self.tmp, rid)
        self.assertEqual(len(rounds), 1)
        r = rounds[0]
        self.assertEqual((r["iteration"], r["found"], r["survived"], r["accepted"], r["arch"], r["tokens"]),
                         (1, 7, 3, 3, 0, 48213))

    def test_close_record(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.close_loop(self.tmp, rid, result="APPROVED", reason="CONVERGED", iterations=2, now=5)
        c = la.close_of(self.tmp, rid)
        self.assertIsNotNone(c)
        self.assertEqual((c["result"], c["reason"], c["iterations"]), ("APPROVED", "CONVERGED", 2))

    def test_audit_summary_empty(self):
        s = la.audit_summary(self.tmp)
        self.assertEqual(s, {"runs": {}, "has_any_records": False})

    def test_audit_summary_open_then_closed(self):
        r1 = la.open_loop(self.tmp, "L3", run_id="run-a", now=0)
        la.open_loop(self.tmp, "L2", run_id="run-b", now=1)   # open, not closed
        la.close_loop(self.tmp, r1, result="APPROVED", reason="CONVERGED", iterations=1, now=2)
        s = la.audit_summary(self.tmp)
        self.assertTrue(s["has_any_records"])
        self.assertEqual(s["runs"]["run-a"], {"closed": True, "result": "APPROVED", "clean": True})
        self.assertEqual(s["runs"]["run-b"], {"closed": False, "result": None, "clean": True})

    def test_audit_summary_blocked_result(self):
        r = la.open_loop(self.tmp, "L3", run_id="run-x", now=0)
        la.close_loop(self.tmp, r, result="BLOCKED", reason="BUDGET_ITER", iterations=3, now=1)
        self.assertEqual(la.audit_summary(self.tmp)["runs"]["run-x"],
                         {"closed": True, "result": "BLOCKED", "clean": True})

    def test_audit_summary_reused_run_id_not_clean(self):
        # 재사용 run_id(중복 open+close) → clean=False (게이트가 stale 증거로 통과되는 것 차단).
        la.open_loop(self.tmp, "L3", run_id="dup", now=0)
        la.close_loop(self.tmp, "dup", result="BLOCKED", reason="BUDGET_ITER", iterations=1, now=1)
        la.open_loop(self.tmp, "L3", run_id="dup", now=2)
        la.close_loop(self.tmp, "dup", result="APPROVED", reason="CONVERGED", iterations=1, now=3)
        run = la.audit_summary(self.tmp)["runs"]["dup"]
        self.assertFalse(run["clean"])
        self.assertEqual(run["result"], "APPROVED")   # 마지막 결과는 남되 clean=False 로 신뢰 불가 표시

    def test_audit_summary_orphan_close_not_clean(self):
        # loop_open 없는 close → opens==0 → clean=False.
        la.close_loop(self.tmp, "orphan", result="APPROVED", reason="CONVERGED", iterations=1, now=0)
        self.assertFalse(la.audit_summary(self.tmp)["runs"]["orphan"]["clean"])

    def test_full_cycle_append_only(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.record_round(self.tmp, rid, 1, 5, 2, 2, 0, 1000, now=1)
        la.record_round(self.tmp, rid, 2, 1, 0, 0, 0, 2000, now=2)
        la.close_loop(self.tmp, rid, "APPROVED", "DRY", 2, now=3)
        recs = la.read_records(self.tmp)
        self.assertEqual([r["event"] for r in recs], ["loop_open", "round", "round", "loop_close"])

    def test_multiple_runs_isolated(self):
        r1 = la.open_loop(self.tmp, "L3", now=0)
        r2 = la.open_loop(self.tmp, "L2", now=10)
        la.record_round(self.tmp, r1, 1, 4, 1, 1, 0, 100, now=1)
        la.record_round(self.tmp, r2, 1, 2, 0, 0, 0, 50, now=11)
        self.assertEqual(len(la.rounds_of(self.tmp, r1)), 1)
        self.assertEqual(len(la.rounds_of(self.tmp, r2)), 1)
        self.assertEqual(la.rounds_of(self.tmp, r1)[0]["found"], 4)
        self.assertEqual(sorted(la.runs(self.tmp)), sorted([r1, r2]))

    def test_blocked_arch_close(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.close_loop(self.tmp, rid, "BLOCKED", "BLOCKED_ARCH", 1, now=2)
        self.assertEqual(la.close_of(self.tmp, rid)["reason"], "BLOCKED_ARCH")

    def test_corrupt_line_skipped(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        with open(la.audit_path(self.tmp), "a", encoding="utf-8") as f:
            f.write("{ this is not valid json\n")
            f.write("\n")   # 빈 줄
        la.record_round(self.tmp, rid, 1, 1, 1, 1, 0, 10, now=1)
        recs = la.read_records(self.tmp)   # 손상 줄·빈 줄 skip, 유효 2건만
        self.assertEqual([r["event"] for r in recs], ["loop_open", "round"])

    def test_missing_file_empty(self):
        self.assertEqual(la.read_records(self.tmp), [])
        self.assertEqual(la.rounds_of(self.tmp, "rl-x"), [])
        self.assertIsNone(la.close_of(self.tmp, "rl-x"))

    def test_unicode_safe(self):
        rid = la.open_loop(self.tmp, "L3", cfg={"note": "보안 렌즈 검토"}, now=0)
        self.assertEqual(la.read_records(self.tmp)[0]["cfg"]["note"], "보안 렌즈 검토")

    # --- codex S2 후속: valid-but-non-dict 줄이 소비자 .get() 크래시 안 내게 skip ---
    def test_valid_nondict_json_skipped_no_crash(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        with open(la.audit_path(self.tmp), "a", encoding="utf-8") as f:
            f.write("42\n[]\n\"junk\"\nnull\n")   # 전부 valid JSON 이지만 비-dict
        la.record_round(self.tmp, rid, 1, 1, 1, 1, 0, 10, now=1)
        recs = la.read_records(self.tmp)   # dict 만 남음
        self.assertEqual([r["event"] for r in recs], ["loop_open", "round"])
        # 소비자 헬퍼가 비-dict 줄에도 크래시하지 않음
        self.assertEqual(len(la.rounds_of(self.tmp, rid)), 1)
        self.assertEqual(la.runs(self.tmp), [rid])
        self.assertIsNone(la.close_of(self.tmp, rid))

    # --- codex S2 후속: run_id 무결성 체크가능 불변식 ---
    def test_integrity_clean(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.record_round(self.tmp, rid, 1, 1, 0, 0, 0, 10, now=1)
        la.close_loop(self.tmp, rid, "APPROVED", "CONVERGED", 1, now=2)
        self.assertEqual(la.integrity_issues(self.tmp), [])

    def test_integrity_orphan_round(self):
        la.record_round(self.tmp, "rl-ghost", 1, 1, 0, 0, 0, 10, now=1)   # open 없이 round
        issues = la.integrity_issues(self.tmp)
        self.assertTrue(any("orphan" in i and "rl-ghost" in i for i in issues))

    def test_integrity_duplicate_open(self):
        la.open_loop(self.tmp, "L3", run_id="rl-dup", now=0)
        la.open_loop(self.tmp, "L2", run_id="rl-dup", now=1)   # 같은 id 재사용
        issues = la.integrity_issues(self.tmp)
        self.assertTrue(any("중복" in i and "rl-dup" in i for i in issues))

    def test_integrity_duplicate_close(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.close_loop(self.tmp, rid, "APPROVED", "CONVERGED", 1, now=1)
        la.close_loop(self.tmp, rid, "BLOCKED", "BUDGET_ITER", 2, now=2)   # 중복 close
        issues = la.integrity_issues(self.tmp)
        self.assertTrue(any("loop_close" in i and "중복" in i for i in issues))

    def test_integrity_activity_after_close(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.close_loop(self.tmp, rid, "APPROVED", "CONVERGED", 1, now=1)
        la.record_round(self.tmp, rid, 2, 1, 0, 0, 0, 10, now=2)   # 종료 후 round
        issues = la.integrity_issues(self.tmp)
        self.assertTrue(any("after loop_close" in i for i in issues))


if __name__ == "__main__":
    unittest.main(verbosity=2)
