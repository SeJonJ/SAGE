#!/usr/bin/env python3
"""retro_audit 단위 — Loop C(`sage retro --check`) 성공 증거의 append-only 감사.

검증:
  1. record_check → retro_check_ok 레코드(run_id/note_path/digest/ts)
  2. digest_of = 전체 SHA-256(잘라쓰지 않음), 내용이 다르면 다른 digest
  3. audit_summary: run_id 별 **최신** 기록만 남음(재검사 시 갱신)
  4. 견고성: 손상 줄 skip, 비-dict 줄 skip, 부재 파일 → []
  5. 경로: .sage/retro_audit.jsonl (커밋 대상, loop_audit.jsonl 과 동일 자리)
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = os.path.join(os.path.dirname(HERE), "runtime")
sys.path.insert(0, RUNTIME)
import retro_audit as ra  # noqa: E402


class TestRetroAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_audit_path_is_dot_sage(self):
        self.assertEqual(ra.audit_path(self.tmp), os.path.join(self.tmp, ".sage", "retro_audit.jsonl"))

    def test_digest_of_full_sha256_not_truncated(self):
        d = ra.digest_of("hello")
        self.assertEqual(64, len(d))   # SHA-256 hex = 64자
        self.assertEqual(d, ra.digest_of("hello"))
        self.assertNotEqual(d, ra.digest_of("hello world"))

    def test_digest_of_empty_and_none_do_not_crash(self):
        self.assertEqual(ra.digest_of(""), ra.digest_of(None))

    def test_record_check_appends_and_returns_record(self):
        rec = ra.record_check(self.tmp, "rl-aaa", "wiki/note.md", "본문내용")
        self.assertEqual(rec["event"], "retro_check_ok")
        self.assertEqual(rec["run_id"], "rl-aaa")
        self.assertEqual(rec["note_path"], "wiki/note.md")
        self.assertEqual(rec["digest"], ra.digest_of("본문내용"))
        self.assertTrue(rec["ts"])
        self.assertTrue(os.path.isfile(ra.audit_path(self.tmp)))

    def test_read_records_missing_file_returns_empty(self):
        self.assertEqual([], ra.read_records(self.tmp))

    def test_read_records_directory_at_path_returns_empty_not_crash(self):
        # codex 구현리뷰 P2: audit 경로가 디렉토리면(수기 오염 등) 읽기 측은 크래시 없이 [] (Stop 훅 fail-open).
        os.makedirs(ra.audit_path(self.tmp), exist_ok=True)
        self.assertEqual([], ra.read_records(self.tmp))
        self.assertEqual({}, ra.audit_summary(self.tmp))

    def test_read_records_skips_malformed_and_non_dict_lines(self):
        path = ra.audit_path(self.tmp)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"event":"retro_check_ok","run_id":"rl-a"}\n')
            f.write("not json at all\n")
            f.write("42\n")          # valid JSON, 비-dict
            f.write('["a","b"]\n')   # valid JSON, 비-dict
            f.write("\n")            # 빈 줄
            f.write('{"event":"retro_check_ok","run_id":"rl-b"}\n')
        recs = ra.read_records(self.tmp)
        self.assertEqual(2, len(recs))
        self.assertEqual({"rl-a", "rl-b"}, {r["run_id"] for r in recs})

    def test_audit_summary_empty_when_no_records(self):
        self.assertEqual({}, ra.audit_summary(self.tmp))

    def test_audit_summary_keeps_latest_per_run_id(self):
        ra.record_check(self.tmp, "rl-aaa", "note-v1.md", "첫 내용")
        ra.record_check(self.tmp, "rl-aaa", "note-v1.md", "재검사 후 내용")   # 같은 run 재검사
        ra.record_check(self.tmp, "rl-bbb", "note-v2.md", "다른 run")
        summary = ra.audit_summary(self.tmp)
        self.assertEqual({"rl-aaa", "rl-bbb"}, set(summary.keys()))
        self.assertEqual(summary["rl-aaa"]["digest"], ra.digest_of("재검사 후 내용"))
        self.assertTrue(summary["rl-aaa"]["checked"])

    def test_audit_summary_ignores_records_without_run_id(self):
        path = ra.audit_path(self.tmp)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"event":"retro_check_ok"}\n')   # run_id 없음
        self.assertEqual({}, ra.audit_summary(self.tmp))

    def test_audit_summary_ignores_unknown_event_types(self):
        path = ra.audit_path(self.tmp)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"event":"something_else","run_id":"rl-aaa"}\n')
        self.assertEqual({}, ra.audit_summary(self.tmp))

    def test_record_missing_appends_and_sets_state(self):
        rec = ra.record_missing(self.tmp, "rl-aaa")
        self.assertEqual(rec["event"], "retro_check_missing")
        self.assertEqual(ra.latest_state(self.tmp, "rl-aaa"), "missing")
        self.assertFalse(ra.audit_summary(self.tmp)["rl-aaa"]["checked"])

    def test_record_missing_is_state_change_only(self):
        # 매 Stop 마다 파일이 불어나지 않도록: 이미 missing 이면 재기록 안 함(None 반환).
        self.assertIsNotNone(ra.record_missing(self.tmp, "rl-aaa"))
        self.assertIsNone(ra.record_missing(self.tmp, "rl-aaa"))
        self.assertEqual(1, len(ra.read_records(self.tmp)))

    def test_missing_then_check_flips_to_ok(self):
        # 미완료로 종료 후 사람이 check → 최신 상태가 ok 로 뒤집힘.
        ra.record_missing(self.tmp, "rl-aaa")
        ra.record_check(self.tmp, "rl-aaa", "note.md", "채운 내용")
        self.assertEqual(ra.latest_state(self.tmp, "rl-aaa"), "ok")
        self.assertTrue(ra.audit_summary(self.tmp)["rl-aaa"]["checked"])
        # 그 뒤 다시 미완료 종료가 감지되면 상태변화라 다시 기록됨.
        self.assertIsNotNone(ra.record_missing(self.tmp, "rl-aaa"))
        self.assertEqual(ra.latest_state(self.tmp, "rl-aaa"), "missing")

    def test_latest_state_none_when_no_record(self):
        self.assertIsNone(ra.latest_state(self.tmp, "rl-nope"))

    def test_read_status_absent_vs_unreadable(self):
        # codex 구현리뷰 4R P1: 진짜 없음(absent)과 신뢰불가(unreadable)를 구분해야 doctor 가 오보 안 함.
        self.assertEqual(ra.read_records_status(self.tmp)[0], "absent")
        os.makedirs(ra.audit_path(self.tmp), exist_ok=True)   # 파일 자리에 디렉토리
        self.assertEqual(ra.read_records_status(self.tmp)[0], "unreadable")

    def test_read_status_broken_symlink_is_unreadable(self):
        # 깨진 심링크: exists()는 False라 absent 로 오판하기 쉬움 → lexists 로 unreadable 판정해야 한다.
        path = ra.audit_path(self.tmp)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.symlink(os.path.join(self.tmp, "nonexistent-target"), path)
        self.assertEqual(ra.read_records_status(self.tmp)[0], "unreadable")

    def test_audit_summary_status_directory_is_unreadable(self):
        os.makedirs(ra.audit_path(self.tmp), exist_ok=True)
        status, summary = ra.audit_summary_status(self.tmp)
        self.assertEqual(status, "unreadable")
        self.assertEqual({}, summary)


if __name__ == "__main__":
    unittest.main(verbosity=2)
