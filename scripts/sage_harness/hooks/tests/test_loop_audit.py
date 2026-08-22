#!/usr/bin/env python3
"""loop_audit 단위 — Loop A(Phase 05 적대적 review-rework) 라운드별 append-only 감사.

검증:
  1. open_loop → run_id 발급 + loop_open 레코드(risk/cfg)
  2. record_round → round 레코드(found/survived/accepted/arch/tokens)
  3. close_loop → loop_close 레코드(result/reason/iterations)
  4. strict run별 hash-chain: self-hash, immediate predecessor, legacy 전환
  5. 동시성: OS 소유 lock 안에서 seq/hash stamp, short append rollback
  6. 견고성: 손상 줄 file_ok=False + 후속 쓰기 거부, 부재 파일 → []
  7. 경로: .sage/loop_audit.jsonl (커밋 대상)
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from copy import deepcopy
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = os.path.join(os.path.dirname(HERE), "runtime")
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, RUNTIME)
sys.path.insert(0, REPO)
import loop_audit as la  # noqa: E402


def _has(issues, code, **arguments):
    """무결성 위반을 문구가 아니라 code·인자로 확인한다 — 문안은 부른 쪽 catalog 소유다."""
    for issue in issues:
        if issue.get("code") != code:
            continue
        if all(issue.get("arguments", {}).get(name) == value
               for name, value in arguments.items()):
            return True
    return False


def _round_record(run_id, iteration, *, now):
    """`record_round` 가 만드는 것과 같은 모양의 round 레코드(검증기만 우회)."""
    return {"event": "round", "run_id": run_id, "ts": "t", "epoch": int(now),
            "iteration": iteration, "found": 1, "survived": 0, "accepted": 0,
            "arch": 0, "tokens": 10}


def _append_out_of_band(root, record):
    """라이브러리 계약을 우회해 들어온 기록을 흉내 낸다.

    `close_loop` 과 `record_round` 는 lock 안에서 "terminal 한 번"·"open 된 run 에만" 을 강제하므로
    중복 close 도, 종료 후 라운드도 만들지 않는다. 그래도 사후 탐지층은 있어야 한다 — 수기 편집이나
    옛 클라이언트가 남긴 기록은 여전히 파일에 있을 수 있고, 그걸 잡는 게 `clean`/`integrity_issues`
    의 일이다. 쓰기를 막았다고 탐지를 지우면 이미 손상된 파일이 조용히 통과한다.
    """
    return la._append(la.audit_path(root), record)


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
        self.assertEqual(s, {
            "runs": {}, "has_any_records": False, "file_ok": True,
            "file_issues": [],
        })

    def test_audit_summary_open_then_closed(self):
        r1 = la.open_loop(self.tmp, "L3", run_id="run-a", now=0)
        la.open_loop(self.tmp, "L2", run_id="run-b", now=1)   # open, not closed
        la.close_loop(self.tmp, r1, result="APPROVED", reason="CONVERGED", iterations=1, now=2)
        s = la.audit_summary(self.tmp)
        self.assertTrue(s["has_any_records"])
        self.assertEqual(s["runs"]["run-a"], {"closed": True, "result": "APPROVED", "clean": True,
                                              "seq_ok": True, "chain_ok": True, "reviewer_requested": None,
                                              "reviewer_actual": None, "degraded": False,
                                              "close_reason": "CONVERGED", "review_assurance": None,
                                              "completed_rounds": None,
                                              "configured_max_iterations": None,
                                              "survived_by_severity": None})
        self.assertEqual(s["runs"]["run-b"], {"closed": False, "result": None, "clean": True,
                                              "seq_ok": True, "chain_ok": True, "reviewer_requested": None,
                                              "reviewer_actual": None, "degraded": False,
                                              "close_reason": None, "review_assurance": None,
                                              "completed_rounds": None,
                                              "configured_max_iterations": None,
                                              "survived_by_severity": None})

    def test_audit_summary_blocked_result(self):
        r = la.open_loop(self.tmp, "L3", run_id="run-x", now=0)
        la.close_loop(self.tmp, r, result="BLOCKED", reason="BUDGET_ITER", iterations=3, now=1)
        self.assertEqual(la.audit_summary(self.tmp)["runs"]["run-x"],
                         {"closed": True, "result": "BLOCKED", "clean": True, "seq_ok": True, "chain_ok": True,
                          "reviewer_requested": None, "reviewer_actual": None, "degraded": False,
                          "close_reason": "BUDGET_ITER", "review_assurance": None,
                          "completed_rounds": None, "configured_max_iterations": None,
                          "survived_by_severity": None})

    def test_audit_summary_reused_run_id_not_clean(self):
        # 재사용 run_id(중복 open+close) → clean=False (게이트가 stale 증거로 통과되는 것 차단).
        la.open_loop(self.tmp, "L3", run_id="dup", now=0)
        la.close_loop(self.tmp, "dup", result="BLOCKED", reason="BUDGET_ITER", iterations=1, now=1)
        la.open_loop(self.tmp, "L3", run_id="dup", now=2)
        _append_out_of_band(self.tmp, {"event": "loop_close", "run_id": "dup", "ts": "t", "epoch": 3,
                                       "result": "APPROVED", "reason": "CONVERGED", "iterations": 1})
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

    def test_corrupt_line_is_file_invalid_and_refuses_later_append(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        with open(la.audit_path(self.tmp), "a", encoding="utf-8") as f:
            f.write("{ this is not valid json\n")
            f.write("\n")   # 빈 줄
        summary = la.audit_summary(self.tmp)
        self.assertFalse(summary["file_ok"])
        self.assertIn("malformed JSON", summary["file_issues"][0])
        with self.assertRaises(la.AuditWriteError):
            la.record_round(self.tmp, rid, 1, 1, 1, 1, 0, 10, now=1)
        recs = la.read_records(self.tmp)   # 조회는 견고하게 유효 dict만 반환하되 권한 판정은 file_ok로 닫는다.
        self.assertEqual([r["event"] for r in recs], ["loop_open"])

    def test_missing_file_empty(self):
        self.assertEqual(la.read_records(self.tmp), [])
        self.assertEqual(la.rounds_of(self.tmp, "rl-x"), [])
        self.assertIsNone(la.close_of(self.tmp, "rl-x"))

    def test_unicode_safe(self):
        la.open_loop(self.tmp, "L3", cfg={"note": "보안 렌즈 검토"}, now=0)
        self.assertEqual(la.read_records(self.tmp)[0]["cfg"]["note"], "보안 렌즈 검토")

    # --- codex S2 후속: valid-but-non-dict 줄이 소비자 .get() 크래시 안 내게 skip ---
    def test_valid_nondict_json_is_file_invalid_without_consumer_crash(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        with open(la.audit_path(self.tmp), "a", encoding="utf-8") as f:
            f.write("42\n[]\n\"junk\"\nnull\n")   # 전부 valid JSON 이지만 비-dict
        self.assertFalse(la.audit_summary(self.tmp)["file_ok"])
        with self.assertRaises(la.AuditWriteError):
            la.record_round(self.tmp, rid, 1, 1, 1, 1, 0, 10, now=1)
        recs = la.read_records(self.tmp)   # dict만 남겨 조회 consumer는 크래시하지 않는다.
        self.assertEqual([r["event"] for r in recs], ["loop_open"])
        # 소비자 헬퍼가 비-dict 줄에도 크래시하지 않음
        self.assertEqual(len(la.rounds_of(self.tmp, rid)), 0)
        self.assertEqual(la.runs(self.tmp), [rid])
        self.assertIsNone(la.close_of(self.tmp, rid))

    # --- codex S2 후속: run_id 무결성 체크가능 불변식 ---
    def test_integrity_clean(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.record_round(self.tmp, rid, 1, 1, 0, 0, 0, 10, now=1)
        la.close_loop(self.tmp, rid, "APPROVED", "CONVERGED", 1, now=2)
        self.assertEqual(la.integrity_issues(self.tmp), [])

    def test_integrity_orphan_round(self):
        _append_out_of_band(self.tmp, _round_record("rl-ghost", 1, now=1))   # open 없이 round
        issues = la.integrity_issues(self.tmp)
        self.assertTrue(_has(issues, "loop_audit.orphan_event", event="round",
                            run_id="'rl-ghost'"), issues)

    def test_integrity_duplicate_open(self):
        la.open_loop(self.tmp, "L3", run_id="rl-dup", now=0)
        la.open_loop(self.tmp, "L2", run_id="rl-dup", now=1)   # 같은 id 재사용
        issues = la.integrity_issues(self.tmp)
        self.assertTrue(_has(issues, "loop_audit.duplicate_open", run_id="'rl-dup'", count=2),
                        issues)

    def test_integrity_duplicate_close(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.close_loop(self.tmp, rid, "APPROVED", "CONVERGED", 1, now=1)
        _append_out_of_band(self.tmp, {"event": "loop_close", "run_id": rid, "ts": "t", "epoch": 2,
                                       "result": "BLOCKED", "reason": "BUDGET_ITER",
                                       "iterations": 2})   # 우회 경로로 들어온 중복 close
        issues = la.integrity_issues(self.tmp)
        self.assertTrue(_has(issues, "loop_audit.duplicate_close", run_id=repr(rid), count=2),
                        issues)

    def test_close_loop_refuses_a_second_terminal_inside_the_lock(self):
        """탐지층이 있다고 해서 라이브러리가 중복을 써도 되는 것은 아니다."""
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.close_loop(self.tmp, rid, "APPROVED", "CONVERGED", 1, now=1)
        with self.assertRaises(la.AuditWriteError):
            la.close_loop(self.tmp, rid, "BLOCKED", "BUDGET_ITER", 2, now=2)
        closes = [r for r in la.read_records(self.tmp)
                  if r.get("event") == "loop_close" and r.get("run_id") == rid]
        self.assertEqual(len(closes), 1)

    def test_record_round_refuses_a_closed_or_unopened_run_inside_the_lock(self):
        """탐지층이 있다고 해서 라이브러리가 손상을 써도 되는 것은 아니다.

        해시 체인이라 붙은 줄은 지울 수 없다. 종료 뒤 라운드 한 줄이면 그 감사는 영구히
        `integrity_issues` 가 붉고, 복구 수단이 없다 — 우회가 아니라 복구 불가능한 손상이다.
        """
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.close_loop(self.tmp, rid, "APPROVED", "CONVERGED", 1, now=1)
        with self.assertRaises(la.AuditWriteError):
            la.record_round(self.tmp, rid, 2, 1, 0, 0, 0, 10, now=2)
        with self.assertRaises(la.AuditWriteError):
            la.record_round(self.tmp, "rl-never-opened", 1, 1, 0, 0, 0, 10, now=3)
        self.assertEqual(la.integrity_issues(self.tmp), [])
        self.assertEqual([r.get("event") for r in la.read_records(self.tmp)],
                         ["loop_open", "loop_close"])

    def _authorization(self, **over):
        auth = {"authorization_reason": "배포 창구가 오늘 닫힌다", "confirmed_by": "sejon",
                "completed_rounds": 1, "configured_max_iterations": 3,
                "survived_by_severity": {"P0": 0, "P1": 0, "P2": 2, "P3": 0},
                "actual_risk": "L3", "mode": "STANDARD", "lens_receipts": ["correctness"]}
        auth.update(over)
        return auth

    def test_an_early_close_refuses_a_round_that_landed_after_its_authorization(self):
        """`record_round` 의 in-lock 검증은 close→round 한 방향만 막았다. 반대 순서가 더 나쁘다.

        close 가 1라운드 기준으로 판정을 끝낸 사이 2라운드가 먼저 append 되면, 최신 P0 finding 을
        무시한 승인이 남는다. 그 감사는 무결성·체인·seq 가 전부 정상이라 게이트도 권위도 잡지
        못한다 — 손상이 보이는 반대 방향과 달리, 이쪽은 조용히 유효한 stale 승인이 된다.
        """
        rid = la.open_loop(self.tmp, "L3", now=0, cycle_stem="demo", lenses=["correctness"])
        la.record_round(self.tmp, rid, 1, 3, 2, 1, 0, 10, now=1, lens_receipts=["correctness"],
                        survived_by_severity={"P0": 0, "P1": 0, "P2": 2, "P3": 0})
        la.record_round(self.tmp, rid, 2, 5, 1, 0, 0, 20, now=2, lens_receipts=["correctness"],
                        survived_by_severity={"P0": 1, "P1": 0, "P2": 0, "P3": 0})

        with self.assertRaises(la.AuditWriteError):
            la.close_loop(self.tmp, rid, "APPROVED", la.EARLY_CLOSE_REASON, 1, now=3,
                          authorization=self._authorization())

        self.assertIsNone(la.close_of(self.tmp, rid))
        self.assertFalse(la.audit_summary(self.tmp)["runs"][rid]["closed"])
        self.assertEqual(la.integrity_issues(self.tmp), [])

    def test_an_early_close_refuses_an_authorization_that_no_longer_matches_the_last_round(self):
        """라운드 수가 같아도 마지막 라운드가 바뀌었으면 그 승인은 다른 사실을 인수한 것이다."""
        cases = (
            ("영수증", {"survived_by_severity": {"P0": 0, "P1": 0, "P2": 1, "P3": 0}}),
            ("lens 영수증", {"lens_receipts": ["correctness", "security"]}),
            ("라운드 수", {"completed_rounds": 2}),
        )
        for label, over in cases:
            with self.subTest(label), tempfile.TemporaryDirectory() as root:
                rid = la.open_loop(root, "L3", now=0, cycle_stem="demo", lenses=["correctness"])
                la.record_round(root, rid, 1, 3, 2, 1, 0, 10, now=1,
                                lens_receipts=["correctness"],
                                survived_by_severity={"P0": 0, "P1": 0, "P2": 2, "P3": 0})
                with self.assertRaises(la.AuditWriteError):
                    la.close_loop(root, rid, "APPROVED", la.EARLY_CLOSE_REASON, 1, now=2,
                                  authorization=self._authorization(**over))
                self.assertIsNone(la.close_of(root, rid))

    def test_a_matching_early_close_still_lands(self):
        """검증은 판정을 한 순간 뒤에 다시 보는 것이지 새 규칙이 아니다."""
        rid = la.open_loop(self.tmp, "L3", now=0, cycle_stem="demo", lenses=["correctness"])
        la.record_round(self.tmp, rid, 1, 3, 2, 1, 0, 10, now=1, lens_receipts=["correctness"],
                        survived_by_severity={"P0": 0, "P1": 0, "P2": 2, "P3": 0})
        la.close_loop(self.tmp, rid, "APPROVED", la.EARLY_CLOSE_REASON, 1, now=2,
                      authorization=self._authorization())
        self.assertEqual(la.close_of(self.tmp, rid)["reason"], la.EARLY_CLOSE_REASON)
        self.assertEqual(la.integrity_issues(self.tmp), [])

    def test_a_normal_close_is_not_given_the_early_close_round_binding(self):
        """일반 close 는 `iterations` 가 라운드 수와 다른 정상 호출이 이미 있다.

        조기 종료에서 옮긴 것은 CLI 가 **이미 강제하던** 판정뿐이다. 같은 검사를 일반 close 로
        넓히면 지금 통과하던 기록이 소급 거부된다 — 수렴 판정을 advisory 로 두는 것도 계약이다.
        """
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.record_round(self.tmp, rid, 1, 3, 3, 0, 0, 10, now=1)
        la.close_loop(self.tmp, rid, "APPROVED", "CONVERGED", 5, now=2)
        self.assertEqual(la.close_of(self.tmp, rid)["iterations"], 5)

    def test_integrity_activity_after_close(self):
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.close_loop(self.tmp, rid, "APPROVED", "CONVERGED", 1, now=1)
        _append_out_of_band(self.tmp, _round_record(rid, 2, now=2))   # 종료 후 round
        issues = la.integrity_issues(self.tmp)
        self.assertTrue(_has(issues, "loop_audit.event_after_close", event="round"), issues)

    def test_integrity_diagnostics_carry_no_finished_sentence(self):
        """이 모듈은 어느 catalog 도 알 수 없다 — 완성 문장을 만들면 그 언어를 호출부가 못 고른다.

        원문 증거(파서 메시지)는 번역 대상이 아니라 `evidence` 로 그대로 실린다.
        """
        korean = re.compile(r"[가-힣]")
        path = la.audit_path(self.tmp)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("{ corrupt\n")
        issues = la.integrity_issues(self.tmp)

        self.assertTrue(issues)
        for issue in issues:
            self.assertEqual({"code", "arguments", "evidence"}, set(issue))
            self.assertFalse(korean.search(json.dumps(issue, ensure_ascii=False)), issue)
        self.assertTrue(_has(issues, "loop_audit.malformed_line"), issues)
        self.assertIn("malformed JSON",
                      next(i for i in issues if i["code"] == "loop_audit.malformed_line")["evidence"])

    def test_integrity_diagnostics_render_in_both_languages(self):
        """같은 진단이 두 언어로 렌더되고, run_id·증거는 언어와 무관하게 같아야 한다."""
        from sage.i18n import LanguageContext, render_issue
        _append_out_of_band(self.tmp, _round_record("rl-ghost", 1, now=1))
        issue = la.integrity_issues(self.tmp)[0]

        korean = render_issue(LanguageContext(language="ko"), issue)
        english = render_issue(LanguageContext(language="en"), issue)

        self.assertIn("rl-ghost", korean)
        self.assertIn("rl-ghost", english)
        self.assertIn("loop_open 없음", korean)
        self.assertIn("there is no loop_open", english)
        self.assertNotRegex(english, r"[가-힣]")

    # --- 7차 배치3: seq 무결성 (수기 위조·순서조작 탐지) ---
    def test_seq_stamped_monotonic(self):
        # 라이브러리가 open=0, round=1.., close=last 로 seq 자동 stamp.
        rid = la.open_loop(self.tmp, "L3", now=0)
        la.record_round(self.tmp, rid, 1, 2, 1, 1, 0, 10, now=1)
        la.record_round(self.tmp, rid, 2, 0, 0, 0, 0, 20, now=2)
        la.close_loop(self.tmp, rid, "APPROVED", "CONVERGED", 2, now=3)
        seqs = [r["seq"] for r in la.read_records(self.tmp)]
        self.assertEqual(seqs, [0, 1, 2, 3])
        run = la.audit_summary(self.tmp)["runs"][rid]
        self.assertTrue(run["seq_ok"])
        self.assertEqual(la.integrity_issues(self.tmp), [])

    def test_seq_handwritten_round_detected(self):
        # CLI/라이브러리 우회한 수기 round(seq 없음) → seq_ok False + integrity 위반.
        la.open_loop(self.tmp, "L3", run_id="rl-forge", now=0)
        with open(la.audit_path(self.tmp), "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "round", "run_id": "rl-forge", "iteration": 1,
                                "found": 9, "survived": 9, "accepted": 9}) + "\n")   # seq 누락
        with self.assertRaises(la.AuditWriteError):
            la.close_loop(self.tmp, "rl-forge", "APPROVED", "CONVERGED", 1, now=2)
        run = la.audit_summary(self.tmp)["runs"]["rl-forge"]
        self.assertFalse(run["seq_ok"])
        self.assertFalse(run["chain_ok"])
        self.assertTrue(_has(la.integrity_issues(self.tmp), "loop_audit.sequence_broken",
                             run_id="'rl-forge'"), la.integrity_issues(self.tmp))

    def test_seq_legacy_no_seq_skips(self):
        # 구버전 기록(seq 전무) → seq_ok None(검사 skip, 하위호환).
        path = la.audit_path(self.tmp)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "loop_open", "run_id": "rl-old", "risk": "L3"}) + "\n")
            f.write(json.dumps({"event": "loop_close", "run_id": "rl-old", "result": "APPROVED",
                                "reason": "CONVERGED", "iterations": 1}) + "\n")
        run = la.audit_summary(self.tmp)["runs"]["rl-old"]
        self.assertIsNone(run["seq_ok"])
        self.assertIsNone(run["chain_ok"])
        self.assertEqual(la.integrity_issues(self.tmp), [])

    # --- 7차 배치3: reviewer degraded (cross-model 폴백 침묵 차단) ---
    def test_reviewer_degraded_on_mismatch(self):
        la.open_loop(self.tmp, "L3", run_id="rl-x", now=0, reviewer_requested="cross_model")
        la.close_loop(self.tmp, "rl-x", "APPROVED", "CONVERGED", 1, now=1,
                      reviewer_actual="same_runtime")
        run = la.audit_summary(self.tmp)["runs"]["rl-x"]
        self.assertEqual(run["reviewer_requested"], "cross_model")
        self.assertEqual(run["reviewer_actual"], "same_runtime")
        self.assertTrue(run["degraded"])

    def test_reviewer_not_degraded_when_match(self):
        la.open_loop(self.tmp, "L3", run_id="rl-y", now=0, reviewer_requested="cross_model")
        la.close_loop(self.tmp, "rl-y", "APPROVED", "CONVERGED", 1, now=1,
                      reviewer_actual="cross_model")
        self.assertFalse(la.audit_summary(self.tmp)["runs"]["rl-y"]["degraded"])

    def test_reviewer_absent_not_degraded(self):
        # reviewer 미기록(legacy/미사용) → degraded False(오탐 방지).
        la.open_loop(self.tmp, "L3", run_id="rl-z", now=0)
        la.close_loop(self.tmp, "rl-z", "APPROVED", "CONVERGED", 1, now=1)
        self.assertFalse(la.audit_summary(self.tmp)["runs"]["rl-z"]["degraded"])


class TestStrictHashChain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _cycle(self, run_id="rl-chain"):
        la.open_loop(self.tmp, "L3", run_id=run_id, now=0)
        la.record_round(self.tmp, run_id, 1, 2, 1, 1, 0, 10, now=1)
        la.close_loop(self.tmp, run_id, "APPROVED", "CONVERGED", 1, now=2)
        return la.read_records(self.tmp)

    def test_record_hash_is_canonical_and_covers_prev_hash(self):
        left = {"event": "round", "run_id": "r", "prev_hash": "a", "note": "보안"}
        right = {"note": "보안", "prev_hash": "a", "run_id": "r", "event": "round"}
        self.assertEqual(la._record_hash(left), la._record_hash(right))
        changed = dict(left, prev_hash="b")
        self.assertNotEqual(la._record_hash(left), la._record_hash(changed))

    def test_new_run_forms_one_strict_chain_and_self_verifies_tip(self):
        records = self._cycle()
        self.assertEqual([r["chain_version"] for r in records], [1, 1, 1])
        self.assertEqual(records[0]["prev_hash"], la.GENESIS)
        self.assertEqual(records[1]["prev_hash"], records[0]["record_hash"])
        self.assertEqual(records[2]["prev_hash"], records[1]["record_hash"])
        self.assertTrue(la._chain_states(records)["rl-chain"])
        self.assertTrue(la.audit_summary(self.tmp)["runs"]["rl-chain"]["chain_ok"])

    def test_modifying_open_middle_or_final_close_is_detected(self):
        records = self._cycle()
        for index, field, value in ((0, "risk", "L2"), (1, "found", 99),
                                    (2, "result", "BLOCKED")):
            changed = deepcopy(records)
            changed[index][field] = value
            self.assertFalse(la._chain_states(changed)["rl-chain"], (index, field))

    def test_insert_delete_and_reorder_are_detected(self):
        records = self._cycle()
        inserted = deepcopy(records)
        inserted.insert(1, dict(inserted[0]))
        self.assertFalse(la._chain_states(inserted)["rl-chain"])
        self.assertFalse(la._chain_states([records[0], records[2]])["rl-chain"])
        self.assertFalse(la._chain_states([records[1], records[0], records[2]])["rl-chain"])

    def test_stale_same_predecessor_sibling_is_rejected(self):
        records = self._cycle()
        sibling = deepcopy(records[1])
        sibling["iteration"] = 2
        sibling["record_hash"] = la._record_hash(sibling)
        self.assertFalse(la._chain_states([records[0], records[1], sibling])["rl-chain"])

    def test_interleaved_runs_have_independent_strict_chains(self):
        la.open_loop(self.tmp, "L3", run_id="run-a", now=0)
        la.open_loop(self.tmp, "L2", run_id="run-b", now=1)
        la.record_round(self.tmp, "run-a", 1, 1, 0, 0, 0, 1, now=2)
        la.record_round(self.tmp, "run-b", 1, 1, 0, 0, 0, 1, now=3)
        states = la._chain_states(la.read_records(self.tmp))
        self.assertEqual(states, {"run-a": True, "run-b": True})

    def test_legacy_only_is_none_and_first_v1_links_to_legacy_tip(self):
        path = la.audit_path(self.tmp)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        legacy = {"event": "loop_open", "run_id": "rl-old", "risk": "L3", "seq": 0}
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(legacy) + "\n")
        self.assertIsNone(la._chain_states([legacy])["rl-old"])
        la.record_round(self.tmp, "rl-old", 1, 1, 0, 0, 0, 1, now=1)
        records = la.read_records(self.tmp)
        self.assertEqual(records[1]["prev_hash"], la._record_hash(legacy))
        self.assertTrue(la._chain_states(records)["rl-old"])

    def test_unstamped_or_partial_record_after_chain_start_is_invalid(self):
        records = self._cycle()
        unstamped = {"event": "round", "run_id": "rl-chain", "seq": 3}
        partial = dict(unstamped, chain_version=1, prev_hash=records[-1]["record_hash"])
        self.assertFalse(la._chain_states(records + [unstamped])["rl-chain"])
        self.assertFalse(la._chain_states(records + [partial])["rl-chain"])

    def test_removing_every_chain_field_is_an_explicit_legacy_downgrade_boundary(self):
        records = self._cycle()
        stripped = deepcopy(records)
        for record in stripped:
            for field in ("chain_version", "prev_hash", "record_hash"):
                record.pop(field)

        # With no external provenance anchor, this is byte-for-byte
        # indistinguishable from a legitimate legacy run.
        self.assertIsNone(la._chain_states(stripped)["rl-chain"])


class TestLockedWriter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_short_append_rolls_back_to_original_bytes(self):
        rid = la.open_loop(self.tmp, "L3", run_id="rl-short", now=0)
        path = la.audit_path(self.tmp)
        with open(path, "rb") as f:
            before = f.read()

        def partial_write(fd, payload):
            return os.write(fd, payload[:len(payload) // 2])

        with mock.patch.object(la, "_write_once", side_effect=partial_write):
            with self.assertRaises(la.AuditWriteError):
                la.record_round(self.tmp, rid, 1, 1, 0, 0, 0, 1, now=1)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_complete_final_record_without_newline_can_be_extended(self):
        rid = la.open_loop(self.tmp, "L3", run_id="rl-no-newline", now=0)
        path = la.audit_path(self.tmp)
        with open(path, "rb") as f:
            before = f.read()
        self.assertTrue(before.endswith(b"\n"))
        with open(path, "wb") as f:
            f.write(before[:-1])

        la.record_round(self.tmp, rid, 1, 1, 0, 0, 0, 1, now=1)

        summary = la.audit_summary(self.tmp)
        self.assertTrue(summary["file_ok"])
        self.assertTrue(summary["runs"][rid]["chain_ok"])
        self.assertEqual([record["seq"] for record in la.read_records(self.tmp)],
                         [0, 1])

    @unittest.skipIf(os.name == "nt", "POSIX subprocess command is covered separately on Windows")
    def test_os_lock_serializes_concurrent_writers_and_stamps_inside_lock(self):
        la.open_loop(self.tmp, "L3", run_id="rl-lock", now=0)
        code = (
            "import loop_audit as la,sys;"
            "i=int(sys.argv[2]);"
            "la.record_round(sys.argv[1],'rl-lock',i,1,0,0,0,i,now=i)"
        )
        env = dict(os.environ, PYTHONPATH=RUNTIME)
        with la._audit_lock(la.audit_path(self.tmp)):
            children = [
                subprocess.Popen([sys.executable, "-c", code, self.tmp, str(iteration)],
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True)
                for iteration in (1, 2)
            ]
            time.sleep(0.2)
            for child in children:
                self.assertIsNone(child.poll(), "writer bypassed the OS-owned lock")
        for child in children:
            stdout, stderr = child.communicate(timeout=5)
            self.assertEqual(child.returncode, 0, (stdout, stderr))
        self.assertTrue(la.audit_summary(self.tmp)["runs"]["rl-lock"]["chain_ok"])
        self.assertEqual([r["seq"] for r in la.read_records(self.tmp)], [0, 1, 2])

    def test_windows_backend_uses_msvcrt_lock_and_unlock(self):
        fake = mock.Mock()
        fake.LK_LOCK = 1
        fake.LK_UNLCK = 2
        with mock.patch.object(la.os, "name", "nt"), mock.patch.dict(sys.modules, {"msvcrt": fake}):
            with la._audit_lock(os.path.join(self.tmp, "audit.jsonl")):
                pass
        self.assertEqual([call.args[1] for call in fake.locking.call_args_list],
                         [fake.LK_LOCK, fake.LK_UNLCK])


if __name__ == "__main__":
    unittest.main(verbosity=2)
