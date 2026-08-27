#!/usr/bin/env python3
"""`sage audit show` — 조회는 조회여야 하고, 보증을 올려 말하지 않아야 한다.

이 스위트가 지키는 것은 여섯이다.

1. **아무것도 쓰지 않는다.** lock 파일도 만들지 않는다. 실행 전후 `.sage/` 의 파일 목록과
   모든 감사 파일의 bytes 를 대조한다. 조회가 트리에 흔적을 남기면 그건 조회가 아니다.
2. **보증을 올려 말하지 않는다.** 검증이 없는 출처는 어떤 경로로도 `valid` 로 표시되지 않는다.
3. **부재를 안전 방향으로 읽지 않는다.** 부재·손상·읽는 중 변경은 서로 다른 결과다.
4. **절대경로가 어디에도 없다.** 경로 필드와 자유 문자열 양쪽에 주입해서 전수로 확인한다.
5. **로컬 데이터의 관문은 하나다.** `--include-local` 없이 로컬 출처를 지목하면 빈 결과가
   아니라 usage 오류다.
6. **JSON 은 언어를 타지 않는다.** ko 와 en 이 byte 동일해야 한다.
"""
import argparse
import ast
import errno
import hashlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
HOOKS = os.path.join(REPO, "scripts", "sage_harness", "hooks")
for _p in (os.path.join(HOOKS, "runtime"), HOOKS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sage import audit_sources, audit_view  # noqa: E402
from sage.commands import audit as A  # noqa: E402
from sage.diagnostic_contract import BLOCK, RECOVERY, SEVERITY, severity_of  # noqa: E402

import acceptance_waiver  # noqa: E402
import fast_cycle_audit  # noqa: E402
import loop_audit  # noqa: E402
import retro_audit  # noqa: E402

REL = {source.id: source.rel for source in audit_view.SOURCES}


def _tree(module):
    with open(module.__file__, encoding="utf-8") as handle:
        return ast.parse(handle.read())


def _imports(module):
    """모듈이 실제로 import 하는 top-level 이름. 주석·docstring 은 세지 않는다."""
    names = set()
    for node in ast.walk(_tree(module)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
            names.update(alias.name for alias in node.names)
    return names


def _called_names(module):
    """호출되는 이름. `f(...)` 의 `f`, `a.b(...)` 의 `b` 둘 다."""
    names = set()
    for node in ast.walk(_tree(module)):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


class Args:
    """argparse 결과 대역. 기본값은 CLI 등록과 같아야 한다."""

    def __init__(self, root, **kw):
        self.root = root
        self.source = None
        self.include_local = False
        self.cycle_stem = None
        self.run_id = None
        self.limit = A.DEFAULT_LIMIT
        self.json = False
        self.lang = None
        for key, value in kw.items():
            setattr(self, key, value)


def write(root, rel, *records):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write((record if isinstance(record, str)
                          else json.dumps(record, ensure_ascii=False)) + "\n")
    return path


def run(root, **kw):
    """(rc, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = A.run_show(Args(root, **kw))
    return rc, out.getvalue(), err.getvalue()


def payload(root, **kw):
    rc, out, _err = run(root, json=True, **kw)
    return rc, json.loads(out)


def digests(root):
    """`.sage/` 아래 모든 파일의 (상대경로 -> sha256). 목록 자체가 증거다."""
    base = os.path.join(root, ".sage")
    found = {}
    for current, _dirs, files in os.walk(base):
        for name in files:
            path = os.path.join(current, name)
            with open(path, "rb") as handle:
                found[os.path.relpath(path, base)] = hashlib.sha256(handle.read()).hexdigest()
    return found


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sage-audit-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, ".sage"), exist_ok=True)

    def seed_review(self, stem="demo-stem"):
        run_id = loop_audit.open_loop(self.root, "L3", cycle_stem=stem)
        loop_audit.record_round(self.root, run_id, 1, 3, 1, 1)
        loop_audit.close_loop(self.root, run_id, "APPROVED", "CONVERGED", 1)
        return run_id

    def seed_fast(self, stem="demo-stem"):
        return fast_cycle_audit.open_fast(
            self.root, cycle_stem=stem, actual_risk="L3", fast_review_level="L2",
            reason="demo", minimum_rounds=1, lenses=["a"],
            profile_hash="sha256:" + "0" * 64, plan_hash_open="sha256:" + "1" * 64)

    def seed_acceptance(self, stem="demo-stem"):
        return acceptance_waiver.grant(
            self.root, stem, "AC1", "reason", "scope", "evidence", "user", ttl_seconds=3600)

    def seed_override(self):
        return write(self.root, REL["override"],
                     {"event": "grant", "grant_id": "g1", "ts": "2026-01-01T00:00:00+00:00",
                      "epoch": 1767225600, "gate": "all", "reason": "demo",
                      "ttl_seconds": 60, "user": "tester"})


class ReadOnly(Base):
    """조회가 트리에 흔적을 남기지 않는다."""

    def test_no_bytes_change_and_no_new_files(self):
        self.seed_review()
        self.seed_fast()
        self.seed_acceptance()
        self.seed_override()
        before = digests(self.root)
        rc, _out, _err = run(self.root, include_local=True)
        after = digests(self.root)
        self.assertIn(rc, (0, 1))
        self.assertEqual(before, after, "조회가 .sage 를 바꿨다")

    def test_creates_no_lock_file(self):
        """lock 은 bounded 여도 파일을 만든다. 만드는 순간 읽기 전용 계약이 깨진다."""
        self.seed_review()
        before = set(digests(self.root))
        run(self.root)
        created = set(digests(self.root)) - before
        self.assertEqual(created, set(), f"조회가 새 파일을 만들었다: {created}")

    def test_absent_project_creates_nothing(self):
        empty = tempfile.mkdtemp(prefix="sage-audit-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        rc, data = payload(empty)
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(os.path.join(empty, ".sage")),
                         "조회가 .sage 디렉터리를 만들었다")
        self.assertTrue(all(entry["present"] is False for entry in data["sources"]))

    def test_does_not_wait_for_a_held_writer_lock(self):
        """writer 가 lock 을 쥐고 있어도 조회는 그것을 기다리지 않는다."""
        self.seed_review()
        path = loop_audit.audit_path(self.root)
        holding = threading.Event()
        release = threading.Event()

        def hold():
            with loop_audit._audit_lock(path):
                holding.set()
                release.wait(10)

        worker = threading.Thread(target=hold, daemon=True)
        worker.start()
        self.assertTrue(holding.wait(5), "테스트가 lock 을 잡지 못했다")
        try:
            started = time.monotonic()
            rc, _out, _err = run(self.root)
            elapsed = time.monotonic() - started
        finally:
            release.set()
            worker.join(10)
        self.assertIn(rc, (0, 1))
        self.assertLess(elapsed, 2.0, f"조회가 lock 을 기다렸다 ({elapsed:.2f}s)")


class Integrity(Base):
    """method 와 status 두 축이 실제 보증만 말한다."""

    def test_valid_review_is_valid(self):
        self.seed_review()
        _rc, data = payload(self.root)
        entry = next(item for item in data["sources"] if item["id"] == "review")
        self.assertEqual(entry["integrity"],
                         {"method": "strict_chain", "status": "valid"})

    def test_forged_review_chain_is_invalid_and_exits_one(self):
        self.seed_review()
        path = loop_audit.audit_path(self.root)
        with open(path, encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle if line.strip()]
        lines[-1]["result"] = "BLOCKED"          # 체인 해시와 어긋난다
        write(self.root, REL["review"], *lines)
        rc, data = payload(self.root)
        entry = next(item for item in data["sources"] if item["id"] == "review")
        self.assertEqual(entry["integrity"]["status"], "invalid")
        self.assertEqual(rc, 1)

    def test_legacy_review_is_not_a_failure(self):
        """보증 필드가 없는 과거 run 은 손상이 아니다."""
        write(self.root, REL["review"],
              {"event": "loop_open", "run_id": "rl-old", "ts": "2020-01-01T00:00:00+00:00",
               "epoch": 1577836800, "risk": "L3"},
              {"event": "loop_close", "run_id": "rl-old", "ts": "2020-01-01T00:10:00+00:00",
               "epoch": 1577837400, "result": "APPROVED", "reason": "CONVERGED",
               "iterations": 1})
        rc, data = payload(self.root)
        entry = next(item for item in data["sources"] if item["id"] == "review")
        self.assertEqual(entry["integrity"]["status"], "legacy")
        self.assertEqual(rc, 0, "legacy 를 실패로 올리면 과거 run 을 가진 저장소가 전부 붉어진다")
        codes = {item["code"] for item in data["diagnostics"]}
        self.assertIn("audit.source.legacy", codes, "보증 없음이 화면에 나가지 않았다")

    def test_unverified_sources_are_never_valid(self):
        self.seed_override()
        write(self.root, REL["feedback"],
              {"event": "feedback", "ts": "2026-01-01T00:00:00+00:00", "epoch": 1767225600,
               "path": "src/a.py", "line": 3, "blocking": False, "verdict": "fixed",
               "resolved": True, "note": "n", "marker_text": "m", "cycle_stem": "demo-stem",
               "user": "tester"})
        _rc, data = payload(self.root, include_local=True)
        for name in ("override", "feedback"):
            entry = next(item for item in data["sources"] if item["id"] == name)
            self.assertEqual(entry["integrity"]["method"], "none")
            self.assertNotEqual(entry["integrity"]["status"], "valid",
                                f"{name} 이 검증도 없이 valid 로 표시됐다")

    def test_override_caveat_is_always_present(self):
        """추적 사본이라는 사실은 조건부로 숨기지 않는다."""
        self.seed_override()
        _rc, data = payload(self.root)
        entry = next(item for item in data["sources"] if item["id"] == "override")
        self.assertEqual(entry["caveat"], "audit.caveat.override_tracking_copy")
        _rc, out, _err = run(self.root)
        self.assertIn("집행 정본", out)

    def test_broken_fast_sequence_is_invalid(self):
        """fast 는 자기 opener 계약과 seq 를 스스로 판정한다. 조회가 그 판정을 그대로 전달한다."""
        self.seed_fast()
        path = os.path.join(self.root, *REL["fast"].split("/"))
        with open(path, encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle if line.strip()]
        lines[0].pop("minimum_rounds")          # opener 담보 하나를 뜯어낸다
        write(self.root, REL["fast"], *lines)
        rc, data = payload(self.root)
        entry = next(item for item in data["sources"] if item["id"] == "fast")
        self.assertEqual(entry["integrity"]["status"], "invalid")
        self.assertEqual(rc, 1)

    def test_a_damaged_fast_source_does_not_hide_a_healthy_review(self):
        """source 별 판정은 서로 옮겨붙지 않는다. 한 벌의 generic parser 였다면 함께 물든다."""
        self.seed_review()
        write(self.root, REL["fast"], "{broken")
        _rc, data = payload(self.root)
        review = next(item for item in data["sources"] if item["id"] == "review")
        self.assertEqual(review["integrity"]["status"], "valid")

    def test_acceptance_conflict_is_invalid(self):
        record = {"event": "grant", "waiver_id": "aw-" + "a" * 16, "epoch": 1767225600,
                  "created_at": "2026-01-01T00:00:00+00:00", "expires_epoch": 4102444800,
                  "expires_at": "2100-01-01T00:00:00+00:00", "ttl_seconds": 3600,
                  "attestation": "self_asserted_local", "cycle_stem": "demo-stem",
                  "acceptance_id": "AC1", "reason": "r", "scope": "s",
                  "remaining_evidence": "e", "confirmed_by": "u"}
        second = dict(record, waiver_id="aw-" + "b" * 16)
        write(self.root, REL["acceptance"], record, second)
        rc, data = payload(self.root)
        entry = next(item for item in data["sources"] if item["id"] == "acceptance")
        self.assertEqual(entry["integrity"]["status"], "invalid")
        self.assertEqual(rc, 1)


class Absence(Base):
    """부재·빈 파일·손상은 서로 다른 사실이다."""

    def test_absent_is_not_an_error(self):
        rc, data = payload(self.root)
        self.assertEqual(rc, 0)
        for entry in data["sources"]:
            self.assertFalse(entry["present"])
            self.assertEqual(entry["record_count"], 0)
            self.assertIsNone(entry["tracking"], "없는 파일의 추적 상태를 단정했다")

    def test_empty_file_is_not_damage(self):
        write(self.root, REL["review"])
        rc, data = payload(self.root)
        entry = next(item for item in data["sources"] if item["id"] == "review")
        self.assertTrue(entry["present"])
        self.assertEqual(entry["record_count"], 0)
        self.assertEqual(rc, 0)

    def test_malformed_line_is_reported_not_skipped(self):
        write(self.root, REL["override"], "{not json", '{"event": "grant"}')
        rc, data = payload(self.root)
        codes = {item["code"] for item in data["diagnostics"]}
        self.assertIn("audit.source.malformed", codes)
        self.assertEqual(rc, 1)

    def test_non_object_line_is_reported(self):
        write(self.root, REL["override"], "42", '"junk"', "[]")
        rc, data = payload(self.root)
        reasons = [item["evidence"].get("reason", "") for item in data["diagnostics"]
                   if item["code"] == "audit.source.malformed"]
        self.assertEqual(len(reasons), 3)
        self.assertTrue(all("object" in reason for reason in reasons))
        self.assertEqual(rc, 1)

    def test_symlink_source_is_refused(self):
        target = write(self.root, "elsewhere.jsonl", {"event": "grant"})
        link = os.path.join(self.root, *REL["override"].split("/"))
        os.makedirs(os.path.dirname(link), exist_ok=True)
        os.symlink(target, link)
        rc, data = payload(self.root)
        entry = next(item for item in data["sources"] if item["id"] == "override")
        self.assertEqual(entry["integrity"]["status"], "unreadable")
        self.assertEqual(rc, 1)

    def test_non_regular_source_is_refused(self):
        path = os.path.join(self.root, *REL["override"].split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.mkfifo(path)
        rc, data = payload(self.root)
        entry = next(item for item in data["sources"] if item["id"] == "override")
        self.assertEqual(entry["integrity"]["status"], "unreadable")
        self.assertEqual(rc, 1)

    def test_invalid_utf8_is_not_guess_repaired(self):
        path = os.path.join(self.root, *REL["override"].split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b'{"event": "grant", "reason": "\xff\xfe"}\n')
        rc, data = payload(self.root)
        entry = next(item for item in data["sources"] if item["id"] == "override")
        self.assertEqual(entry["integrity"]["status"], "unreadable")
        reason = next(item["evidence"]["reason"] for item in data["diagnostics"]
                      if item["code"] == "audit.source.unreadable")
        self.assertTrue(reason.startswith("not_utf8"), reason)
        self.assertEqual(rc, 1)

    def test_oversize_source_is_bounded_failure(self):
        path = os.path.join(self.root, *REL["override"].split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"x" * (audit_sources.MAX_BYTES + 1))
        rc, data = payload(self.root)
        entry = next(item for item in data["sources"] if item["id"] == "override")
        self.assertEqual(entry["integrity"]["status"], "unreadable")
        self.assertEqual(rc, 1)

    def test_line_count_cap_is_a_bounded_failure_not_a_silent_truncation(self):
        """상한을 넘겨도 앞부분만 읽어 판정하지 않는다 — 잘린 꼬리에 종료 이벤트가 있을 수 있다."""
        line = json.dumps({"event": "grant", "grant_id": "g", "epoch": 1767225600}) + "\n"
        path = os.path.join(self.root, *REL["override"].split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(line * (audit_sources.MAX_LINES + 1))
        rc, data = payload(self.root)
        entry = next(item for item in data["sources"] if item["id"] == "override")
        self.assertEqual(entry["integrity"]["status"], "unreadable")
        self.assertEqual(entry["record_count"], 0, "상한 초과인데 일부를 읽어 판정했다")
        reason = next(item["evidence"]["reason"] for item in data["diagnostics"]
                      if item["code"] == "audit.source.unreadable")
        self.assertTrue(reason.startswith("too_many_lines"), reason)
        self.assertEqual(rc, 1)

    def test_partial_last_line_is_not_skipped_as_in_flight_append(self):
        path = os.path.join(self.root, *REL["override"].split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"event": "grant", "grant_id": "g1"}\n')
            handle.write('{"event": "gra')          # 진행 중 append 처럼 보이는 손상
        rc, data = payload(self.root)
        codes = {item["code"] for item in data["diagnostics"]}
        self.assertIn("audit.source.malformed", codes,
                      "불완전한 마지막 줄을 진행 중 append 로 추측해 넘겼다")
        self.assertEqual(rc, 1)

    def test_one_broken_source_keeps_the_others(self):
        self.seed_review()
        write(self.root, REL["override"], "{broken")
        rc, data = payload(self.root)
        self.assertEqual(rc, 1)
        self.assertTrue(any(item["source"] == "review" for item in data["events"]),
                        "한 출처가 깨졌다고 나머지를 숨겼다")


class Concurrency(Base):
    def test_change_during_read_is_a_stable_failure(self):
        """읽는 중 파일이 바뀌면 재시도 한 번 뒤 실패한다. 부분 결과를 정상으로 내지 않는다."""
        self.seed_override()
        path = os.path.join(self.root, *REL["override"].split("/"))
        original = audit_sources._read_once
        calls = []

        def unstable(target):
            calls.append(target)
            if target == path:
                return audit_sources.READ_CONCURRENT, b"", "changed_while_reading"
            return original(target)

        audit_sources._read_once = unstable
        try:
            rc, data = payload(self.root)
        finally:
            audit_sources._read_once = original
        self.assertEqual(calls.count(path), 2, "재시도가 정확히 한 번이 아니다")
        codes = {item["code"] for item in data["diagnostics"]}
        self.assertIn("audit.source.concurrent_change", codes)
        self.assertEqual(rc, 1)
        entry = next(item for item in data["sources"] if item["id"] == "override")
        self.assertEqual(entry["record_count"], 0, "부분 결과가 정상으로 표시됐다")


class Redaction(Base):
    """절대경로는 어떤 출력에도 없다. 경로 필드와 자유 문자열 두 겹으로 막는다."""

    LEAK = "/Users/someone/Obsidian/vault/note.md"

    def test_path_field_escape_is_hidden(self):
        write(self.root, REL["feedback"],
              {"event": "feedback", "ts": "2026-01-01T00:00:00+00:00", "epoch": 1767225600,
               "path": self.LEAK, "line": 3, "blocking": True, "verdict": "open"})
        rc, out, _err = run(self.root, include_local=True)
        _rc, data = payload(self.root, include_local=True)
        raw = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("/Users/someone", raw)
        self.assertNotIn("/Users/someone", out)
        self.assertIn(audit_view.REDACTED, raw)
        codes = {item["code"] for item in data["diagnostics"]}
        self.assertIn("audit.source.redacted", codes, "치환을 조용히 삼켰다")
        self.assertIn(rc, (0, 1))

    def test_retro_note_path_is_never_emitted(self):
        """정상 상대경로여도 내보내지 않는다.

        redaction 은 **이탈**을 가린다. `note_path` 는 이탈하지 않아도 vault 안 개인 노트를
        어디에 두는지를 드러내므로, 가리기가 아니라 존재 여부로 투영한다.
        """
        retro_audit.record_check(self.root, "rl-1", "docs/notes/retro.md", "body")
        _rc, out, _err = run(self.root, include_local=True)
        _rc2, data = payload(self.root, include_local=True)
        raw = json.dumps(data, ensure_ascii=False)
        for blob in (raw, out):
            self.assertNotIn("note_path", blob, "원본 경로 필드가 나갔다")
            self.assertNotIn("docs/notes/retro.md", blob)
        self.assertEqual(data["events"][0]["data"],
                         {"state": "ok", "vault_note_present": True, "digest_present": True})

    def test_retro_projection_still_distinguishes_the_states(self):
        """투영이 사실을 지우지는 않는다. 있음과 없음이 같은 값이 되면 화면이 쓸모없어진다."""
        retro_audit.record_missing(self.root, "rl-2")
        _rc, data = payload(self.root, include_local=True)
        item = data["events"][0]["data"]
        self.assertEqual(item["state"], "missing")
        self.assertFalse(item["vault_note_present"])

    def test_free_text_escape_is_sanitized(self):
        """`reason` 은 사용자가 직접 쓰는 자리다. 필드 이름으로는 막을 수 없다."""
        retro_audit.record_skip(self.root, "rl-1", reason=f"vault {self.LEAK} 없음")
        _rc, data = payload(self.root, include_local=True)
        raw = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("/Users/someone", raw)
        self.assertIn(audit_view.REDACTED, raw)

    def test_no_absolute_path_anywhere(self):
        """전수 확인. 어떤 출처의 어떤 필드에도 절대경로가 남지 않는다."""
        self.seed_review()
        write(self.root, REL["override"],
              {"event": "bypass", "ts": "2026-01-01T00:00:00+00:00", "epoch": 1767225600,
               "gate": "all", "message_key": "block_x", "files": [self.LEAK, "src/a.py"],
               "grant_id": "g1", "reason": f"보세요 {self.LEAK}", "user": "tester"})
        retro_audit.record_check(self.root, "rl-1", self.LEAK, "body")
        _rc, out, _err = run(self.root, include_local=True)
        _rc2, data = payload(self.root, include_local=True)
        for blob in (out, json.dumps(data, ensure_ascii=False)):
            self.assertNotIn("/Users/", blob)
            self.assertNotIn(os.path.expanduser("~"), blob)

    def test_relative_paths_survive(self):
        """가리는 것은 이탈뿐이다. 정상 상대경로까지 지우면 화면이 쓸모없어진다."""
        write(self.root, REL["override"],
              {"event": "bypass", "ts": "2026-01-01T00:00:00+00:00", "epoch": 1767225600,
               "gate": "all", "message_key": "block_x", "files": ["src/a.py"],
               "grant_id": "g1", "reason": "ok", "user": "tester"})
        _rc, data = payload(self.root)
        self.assertIn("src/a.py", json.dumps(data))

    def test_sanitizer_keeps_ordinary_slashes(self):
        for text in ("L2/L3", "and/or", "https://example.com/a/b"):
            cleaned, hits = audit_view.sanitize_text(text)
            self.assertEqual((cleaned, hits), (text, 0), text)


def _strings(value):
    """중첩 구조 안의 모든 문자열. dict 의 key 도 낸다 — key 로 새는 경로가 실재한다."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


class MetaRedaction(Base):
    """`data` 밖의 자리로도 경로가 새지 않는다.

    `run_id`·`cycle_stem`·`ts`·`event` 는 allowlist 를 지나지 않는다 — allowlist 는 `data` 의
    key 만 고르기 때문이다. 그래서 이 넷은 "거르는 대상을 고른" 구현에서 조용히 통과한다.
    감사 파일을 쓸 수 있는 쪽이면 무엇이든 넣을 수 있는 자리이므로 통과하면 안 된다.

    OS 예외도 같은 종류의 구멍이다. `str(OSError)` 에는 열려던 파일명이 붙고, 이 명령에서
    그 파일명은 저장소 절대경로다.
    """

    LEAK = "/Users/someone/Obsidian/vault/note.md"

    def meta_record(self, **kw):
        record = {"event": "grant", "grant_id": "g1", "ts": self.LEAK, "epoch": 1767225600,
                  "gate": "all", "reason": "ok", "ttl_seconds": 60, "user": "tester",
                  "run_id": self.LEAK, "cycle_stem": self.LEAK}
        record.update(kw)
        return write(self.root, REL["override"], record)

    def assert_clean(self, *blobs):
        """주입한 경로와 **저장소 자신의 절대경로** 둘 다 본다.

        주입 문자열만 보면 OS 예외가 흘리는 경로를 놓친다 — 그건 우리가 주입한 값이 아니라
        임시 root 자신이고, 임시 root 는 HOME 아래에 있지도 않다.
        """
        for blob in blobs:
            self.assertNotIn("/Users/", blob)
            self.assertNotIn(os.path.expanduser("~"), blob)
            self.assertNotIn(self.root, blob, "저장소 절대경로가 출력에 남았다")
            self.assertNotIn(os.path.realpath(self.root), blob)

    def test_run_id_and_cycle_stem_and_ts_are_sanitized(self):
        self.meta_record()
        _rc, out, _err = run(self.root)
        _rc2, data = payload(self.root)
        self.assert_clean(out, json.dumps(data, ensure_ascii=False))
        item = data["events"][0]
        for field in ("run_id", "cycle_stem", "occurred_at"):
            self.assertEqual(item[field], audit_view.REDACTED, field)
        codes = {entry["code"] for entry in data["diagnostics"]}
        self.assertIn("audit.source.redacted", codes, "치환을 조용히 삼켰다")

    def test_unknown_event_name_is_sanitized(self):
        """모르는 event 이름은 진단 인자로 나간다. envelope 만 걸러서는 막지 못한다."""
        self.meta_record(event=self.LEAK, ts="2026-01-01T00:00:00+00:00")
        _rc, out, _err = run(self.root)
        _rc2, data = payload(self.root)
        self.assert_clean(out, json.dumps(data, ensure_ascii=False))
        unknown = [entry for entry in data["diagnostics"]
                   if entry["code"] == "audit.source.unknown_event"]
        self.assertTrue(unknown, "모르는 event 를 조용히 삼켰다")

    def test_every_string_in_the_payload_is_sanitized(self):
        """전수 오라클. envelope 에 key 를 하나 더해도 이 검사는 그 key 를 함께 본다."""
        self.meta_record(actor=self.LEAK)
        _rc, data = payload(self.root)
        leaked = [text for text in _strings(data)
                  if "/Users/" in text or text.startswith("/")]
        self.assertEqual(leaked, [], f"경로가 남았다: {leaked}")

    def test_adapter_judgement_text_is_sanitized(self):
        """판정문은 우리가 쓴 문자열이 아니다.

        무결성 판정은 각 감사 모듈이 소유하고, 그 모듈이 만든 문장에는 레코드 원문이 그대로
        박힌다. 이 층은 그 문장의 내용을 통제하지 못하므로 나가는 문에서 거른다.
        """
        write(self.root, REL["retro"],
              {"event": self.LEAK, "ts": "2026-01-01T00:00:00+00:00", "run_id": "r1"})
        _rc, out, _err = run(self.root, include_local=True)
        _rc2, data = payload(self.root, include_local=True)
        self.assert_clean(out, json.dumps(data, ensure_ascii=False))
        codes = {entry["code"] for entry in data["diagnostics"]}
        self.assertIn("audit.source.invalid", codes, "모르는 retro 이벤트를 조용히 삼켰다")

    def test_os_detail_never_carries_the_filename(self):
        exc = PermissionError(errno.EACCES, "Permission denied",
                              "/Users/someone/vault/proj/.sage/loop_audit.jsonl")
        detail = audit_sources._os_detail(exc)
        self.assertNotIn("/Users", detail, "OS 예외 문자열에 파일명이 붙어 나갔다")
        self.assertIn("EACCES", detail, "원인을 구분할 수 없게 지웠다")

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0,
                     "root 는 권한 오류를 만들 수 없다")
    def test_unreadable_reason_carries_no_path(self):
        """읽을 수 없는 감사의 진단이 경로를 싣지 않는다. 손상 상태는 그대로 표면화한다."""
        path = self.seed_override()
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, stat.S_IRUSR | stat.S_IWUSR)
        rc, out, _err = run(self.root)
        _rc2, data = payload(self.root)
        self.assert_clean(out, json.dumps(data, ensure_ascii=False))
        unreadable = [entry for entry in data["diagnostics"]
                      if entry["code"] == "audit.source.unreadable"]
        self.assertTrue(unreadable, "읽기 실패를 조용히 삼켰다")
        self.assertEqual(rc, 1, "읽기 실패가 통과로 떨어졌다")
        entry = [item for item in data["sources"] if item["id"] == "override"][0]
        self.assertEqual(entry["integrity"]["status"], audit_view.STATUS_UNREADABLE)


class SchemaV1(Base):
    """JSON v1 최상위 계약. 확정된 key 집합과 파생 값의 정의를 고정한다."""

    TOP_LEVEL = {"schema_version", "ok", "status", "exit_code", "ordering", "selection",
                 "sources", "events", "returned", "omitted", "truncated", "diagnostics"}

    def test_top_level_keys_are_exactly_the_contract(self):
        """더 나오는 것도 계약 위반이다 — 소비자는 없던 key 가 생기는 것도 변경으로 읽는다."""
        self.seed_override()
        _rc, data = payload(self.root)
        self.assertEqual(set(data), self.TOP_LEVEL)
        self.assertEqual(data["schema_version"], 1)

    def test_derived_values_match_their_definitions(self):
        """`ok`·`returned`·`truncated` 는 다른 값의 함수다. 따로 계산하면 갈릴 수 있다."""
        write(self.root, REL["override"], *[
            {"event": "grant", "grant_id": f"g{n}", "ts": "2026-01-01T00:00:00+00:00",
             "epoch": 1767225600 + n, "gate": "all", "reason": "r",
             "ttl_seconds": 60, "user": "tester"} for n in range(5)])
        for limit, expect_truncated in ((3, True), (100, False)):
            rc, data = payload(self.root, limit=limit)
            self.assertIs(data["ok"], data["exit_code"] == 0, limit)
            self.assertEqual(data["ok"], rc == 0, limit)
            self.assertEqual(data["returned"], len(data["events"]), limit)
            self.assertIs(data["truncated"], data["omitted"] > 0, limit)
            self.assertIs(data["truncated"], expect_truncated, limit)

    def test_ok_is_false_when_a_source_is_broken(self):
        write(self.root, REL["override"], "{not json")
        _rc, data = payload(self.root)
        self.assertIs(data["ok"], False)
        self.assertEqual(data["exit_code"], 1)

    def test_selection_reports_what_was_actually_applied(self):
        self.seed_override()
        _rc, data = payload(self.root, include_local=True, cycle_stem="stem-1",
                            run_id="run-1", limit=7)
        self.assertEqual(data["selection"], {
            "sources": list(audit_view.SOURCE_IDS),
            "include_local": True, "cycle_stem": "stem-1",
            "run_id": "run-1", "limit": 7})

    def test_diagnostics_are_the_single_home_and_bind_by_evidence(self):
        """`sources[]` 에 사본을 두면 둘이 갈렸을 때 어느 쪽이 옳은지 판정할 근거가 없다."""
        write(self.root, REL["override"], "{not json")
        _rc, data = payload(self.root)
        for entry in data["sources"]:
            self.assertNotIn("issues", entry, entry["id"])
        bound = [item for item in data["diagnostics"]
                 if item["code"] == "audit.source.malformed"]
        self.assertTrue(bound, "손상을 조용히 삼켰다")
        self.assertEqual(bound[0]["evidence"]["source"], "override")

    def test_every_source_scoped_diagnostic_names_its_source(self):
        """전역 진단 둘 말고는 전부 결속된다. 결속이 없으면 어느 출처 문제인지 알 수 없다."""
        global_codes = {"audit.source.truncated", "audit.selection.redacted"}
        write(self.root, REL["override"], "{not json")
        retro_audit.record_check(self.root, "rl-1", "docs/n.md", "b")
        _rc, data = payload(self.root, include_local=True, limit=1)
        for item in data["diagnostics"]:
            if item["code"] in global_codes:
                continue
            self.assertIn("source", item["evidence"], item["code"])

    def test_selection_free_text_is_sanitized(self):
        """필터 값은 감사에서 온 것이 아니라 사용자가 친 것이다. 되비추면 그대로 나간다."""
        leak = "/Users/someone/Obsidian/vault/note.md"
        self.seed_override()
        _rc, out, _err = run(self.root, cycle_stem=leak, run_id=leak)
        _rc2, data = payload(self.root, cycle_stem=leak, run_id=leak)
        raw = json.dumps(data, ensure_ascii=False)
        for blob in (raw, out):
            self.assertNotIn("/Users/", blob)
            self.assertNotIn(self.root, blob)
        self.assertEqual(data["selection"]["cycle_stem"], audit_view.REDACTED)
        self.assertEqual(data["selection"]["run_id"], audit_view.REDACTED)
        codes = {item["code"] for item in data["diagnostics"]}
        self.assertIn("audit.selection.redacted", codes, "치환을 조용히 삼켰다")

    def test_the_filter_and_the_screen_agree_on_the_same_value(self):
        """양쪽이 같은 sanitizer 를 지나야 필터가 자기 화면에 보이는 줄을 찾는다.

        한쪽만 정화하면 같은 값을 가리키는 두 문자열이 서로 다른 것이 되고, 필터는 조용히
        0건을 낸다 — 사용자는 그것을 "그런 기록이 없다" 로 읽는다.
        """
        stem = "/Users/someone/vault"
        write(self.root, REL["override"],
              {"event": "grant", "grant_id": "g1", "ts": "2026-01-01T00:00:00+00:00",
               "epoch": 1767225600, "gate": "all", "reason": "r", "ttl_seconds": 60,
               "user": "t", "cycle_stem": stem})
        _rc, data = payload(self.root, cycle_stem=stem)
        self.assertEqual(data["returned"], 1, "원본으로 대조하지 않았다")

    def test_absence_is_the_canonical_quiet_state(self):
        """부재는 `present=false` + `record_count=0` + 진단 없음 + exit 0 이다."""
        empty = tempfile.mkdtemp(prefix="sage-audit-canon-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        rc, data = payload(empty)
        self.assertEqual(rc, 0)
        self.assertIs(data["ok"], True)
        self.assertEqual(data["status"], "OK")
        for entry in data["sources"]:
            self.assertIs(entry["present"], False, entry["id"])
            self.assertEqual(entry["record_count"], 0, entry["id"])
            self.assertIsNone(entry["tracking"], entry["id"])
        self.assertEqual(data["diagnostics"], [], "부재가 진단을 만들었다")


class KnownFilterCollision(Base):
    """RA-7 — 수용 대기 중인 잔여 위험을 **보이게** 고정한다.

    필터와 화면이 같은 sanitizer 를 지나므로, 서로 다른 절대경로 식별자 둘이 같은 토큰으로
    겹치면 한쪽으로 필터해도 둘 다 나온다. `--cycle-stem` 과 `--run-id` 가 같은 관문을 쓰므로
    위험도 둘 다에 있다 — 한쪽만 못박으면 나머지 한쪽은 고칠 때 조용히 지나간다. 이것은
    FR-D04 의 exact 일치를 깨는 결함이고
    고쳐야 할 것이지만, 고치려면 대조용 **원문** 값을 따로 들고 다녀야 한다 — 정의상 출력에
    실리면 안 되는 값이라 이번 사이클에서 새 채널을 열지 않기로 했다.

    그래서 지우거나 통과시키지 않고 현재 동작을 그대로 못박는다. 고치는 사람은 이 검사가
    깨지는 것을 보고 RA-7 을 함께 닫게 된다. 아무 검사도 없으면 수용한 위험과 잊은 위험이
    구분되지 않는다.
    """

    def test_two_absolute_stems_collide_after_redaction(self):
        write(self.root, REL["override"], *[
            {"event": "grant", "grant_id": f"g{n}", "ts": "2026-01-01T00:00:00+00:00",
             "epoch": 1767225600 + n, "gate": "all", "reason": "r", "ttl_seconds": 60,
             "user": "t", "cycle_stem": value}
            for n, value in enumerate(("/Users/alice/private-a", "/Users/bob/private-b"))])
        _rc, data = payload(self.root, cycle_stem="/Users/alice/private-a")
        self.assertEqual(data["returned"], 2,
                         "RA-7 이 고쳐졌다면 이 검사와 Phase 02 의 RA-7 항목을 함께 닫아야 한다")
        self.assertEqual({item["cycle_stem"] for item in data["events"]},
                         {audit_view.REDACTED})

    def test_two_absolute_run_ids_collide_after_redaction(self):
        """`--run-id` 도 같은 관문을 지난다. 위험은 `cycle_stem` 한 필드의 것이 아니다."""
        write(self.root, REL["override"], *[
            {"event": "grant", "grant_id": f"g{n}", "ts": "2026-01-01T00:00:00+00:00",
             "epoch": 1767225600 + n, "gate": "all", "reason": "r", "ttl_seconds": 60,
             "user": "t", "run_id": value}
            for n, value in enumerate(("/Users/alice/run-a", "/Users/bob/run-b"))])
        _rc, data = payload(self.root, run_id="/Users/alice/run-a")
        self.assertEqual(data["returned"], 2,
                         "RA-7 이 고쳐졌다면 이 검사와 Phase 02 의 RA-7 항목을 함께 닫아야 한다")
        self.assertEqual({item["run_id"] for item in data["events"]},
                         {audit_view.REDACTED})

    def test_ordinary_stems_do_not_collide(self):
        """정상 slug 는 sanitizer 를 그대로 지난다 — RA-7 의 재현 조건이 좁은 이유다."""
        write(self.root, REL["override"], *[
            {"event": "grant", "grant_id": f"g{n}", "ts": "2026-01-01T00:00:00+00:00",
             "epoch": 1767225600 + n, "gate": "all", "reason": "r", "ttl_seconds": 60,
             "user": "t", "cycle_stem": value}
            for n, value in enumerate(("payment-refactor", "audit-visibility"))])
        _rc, data = payload(self.root, cycle_stem="payment-refactor")
        self.assertEqual(data["returned"], 1)
        self.assertEqual(data["events"][0]["cycle_stem"], "payment-refactor")


class ToolFailure(Base):
    """`load_source` 자체가 터진 경로. 이 경로만 상태 dict 를 따로 짓고 있었다."""

    SOURCE_KEYS = {"id", "path", "present", "record_count", "integrity",
                   "caveat", "policy", "tracking"}

    def source_keys(self, **kw):
        _rc, data = payload(self.root, **kw)
        return [set(entry) for entry in data["sources"]]

    def test_the_source_schema_is_the_same_in_every_state(self):
        """정상·부재·손상·도구 실패가 같은 key 집합을 낸다.

        소비자에게 key 집합은 계약이다. 예외 경로에서만 달라지는 계약은 하필 예외가 났을 때
        깨지고, 그때는 이미 다른 것이 무너진 뒤라 원인을 가리기 어렵다.
        """
        seen = []
        seen += self.source_keys()                       # 부재
        self.seed_review()
        self.seed_override()
        seen += self.source_keys()                       # 정상
        write(self.root, REL["override"], "{not json")
        seen += self.source_keys()                       # 손상
        with self.outer_failure():
            seen += self.source_keys()                   # 도구 실패
        for keys in seen:
            self.assertEqual(keys, self.SOURCE_KEYS)

    def outer_failure(self):
        """`load_source` 안의 그물을 지나가는 예외. 내부 adapter 실패와 다른 경로다."""
        import contextlib

        @contextlib.contextmanager
        def patched():
            original = audit_sources.load_source

            def boom(*_a, **_kw):
                raise RuntimeError("load_source itself failed")

            audit_sources.load_source = boom
            try:
                yield
            finally:
                audit_sources.load_source = original
        return patched()

    def test_outer_failure_is_a_tool_error_that_keeps_the_policy(self):
        self.seed_override()
        with self.outer_failure():
            rc, data = payload(self.root, include_local=True)
        self.assertEqual(rc, 2, "도구 실패가 정책 차단(1)이나 통과(0)로 떨어졌다")
        self.assertEqual(data["status"], "ERROR")
        self.assertIs(data["ok"], False)
        policies = {entry["id"]: entry["policy"] for entry in data["sources"]}
        self.assertEqual(policies, {"override": "shared", "acceptance": "shared",
                                    "review": "shared", "fast": "shared",
                                    "retro": "local", "feedback": "local"})
        codes = {item["code"] for item in data["diagnostics"]}
        self.assertIn("audit.source.unavailable", codes)

    def test_a_tool_failure_is_not_read_as_absence(self):
        """`present` 는 `None` 이다. `False` 로 접으면 도구 실패가 "기록 없음" 이 된다."""
        with self.outer_failure():
            _rc, data = payload(self.root)
        for entry in data["sources"]:
            self.assertIsNone(entry["present"], entry["id"])

    def test_text_and_json_agree_that_the_state_is_undetermined(self):
        """화면도 세 상태를 낸다. `no` 로 접으면 두 형식이 같은 실행을 다르게 말한다."""
        with self.outer_failure():
            rc, out, _err = run(self.root)
        self.assertEqual(rc, 2)
        self.assertIn("present=unknown", out)
        self.assertNotIn("present=no", out)
        with self.outer_failure():
            _rc, data = payload(self.root)
        self.assertTrue(all(entry["present"] is None for entry in data["sources"]))

    def test_both_states_come_from_one_constructor(self):
        """모양을 두 자리에서 짓지 않는다 — 이 결함이 정확히 그렇게 생겼다."""
        source = audit_view.source_of("retro")
        self.assertEqual(set(audit_sources.state_of(source)), self.SOURCE_KEYS)
        self.assertEqual(audit_sources.state_of(source)["policy"], "local")


class SourceState(Base):
    """source 상태가 정책과 실제를 따로 낸다."""

    def test_state_carries_both_policy_and_tracking(self):
        """하나로 접으면 '공유 대상인데 커밋 안 됨' 과 '원래 개인 것' 이 같은 값이 된다."""
        self.seed_override()
        _rc, data = payload(self.root, include_local=True)
        policies = {entry["id"]: entry["policy"] for entry in data["sources"]}
        self.assertEqual(policies, {"override": "shared", "acceptance": "shared",
                                    "review": "shared", "fast": "shared",
                                    "retro": "local", "feedback": "local"})
        for entry in data["sources"]:
            self.assertIn("tracking", entry, entry["id"])

    def test_policy_comes_from_the_registry_not_a_branch(self):
        for source in audit_view.SOURCES:
            self.assertEqual(source.visibility,
                             "local" if source.local else "shared", source.id)


class Allowlist(Base):
    def test_keys_outside_the_allowlist_never_appear(self):
        """review 의 `cfg` 는 profile 스냅샷 전체다. 통과 목록에 없으면 나가지 않는다."""
        run_id = loop_audit.open_loop(self.root, "L3", cfg={"secret": "s3cret"},
                                      cycle_stem="demo-stem")
        loop_audit.close_loop(self.root, run_id, "APPROVED", "CONVERGED", 1)
        _rc, data = payload(self.root)
        raw = json.dumps(data)
        self.assertNotIn("s3cret", raw)
        self.assertNotIn("cfg", raw)
        for item in data["events"]:
            allowed = audit_view.allowed_keys(item["source"], item["event"]) or ()
            self.assertTrue(set(item["data"]) <= set(allowed), item)

    def test_unknown_event_is_kept_with_an_empty_payload(self):
        write(self.root, REL["override"],
              {"event": "brand_new", "ts": "2026-01-01T00:00:00+00:00", "epoch": 1767225600,
               "secret_field": "leak"})
        rc, data = payload(self.root)
        self.assertEqual(len(data["events"]), 1, "모르는 이벤트를 버렸다")
        self.assertEqual(data["events"][0]["data"], {}, "raw passthrough 가 열려 있다")
        self.assertNotIn("leak", json.dumps(data))
        codes = {item["code"] for item in data["diagnostics"]}
        self.assertIn("audit.source.unknown_event", codes)
        self.assertEqual(rc, 0, "모르는 이벤트는 손상이 아니다")


class Selection(Base):
    def test_local_sources_are_excluded_by_default(self):
        retro_audit.record_check(self.root, "rl-1", "docs/n.md", "body")
        _rc, data = payload(self.root)
        self.assertEqual([item for item in data["events"] if item["source"] == "retro"], [])
        self.assertNotIn("retro", {entry["id"] for entry in data["sources"]})

    def test_include_local_opens_the_single_gate(self):
        retro_audit.record_check(self.root, "rl-1", "docs/n.md", "body")
        _rc, data = payload(self.root, include_local=True)
        self.assertTrue(any(item["source"] == "retro" for item in data["events"]))

    def test_naming_a_local_source_without_the_gate_is_a_usage_error(self):
        retro_audit.record_check(self.root, "rl-1", "docs/n.md", "body")
        rc, out, err = run(self.root, source=["retro"])
        self.assertEqual(rc, 2, "빈 결과는 '기록이 없다' 로 읽힌다")
        self.assertEqual(out, "")
        self.assertIn("--include-local", err)

    def test_unknown_source_is_a_usage_error(self):
        rc, _out, err = run(self.root, source=["nope"])
        self.assertEqual(rc, 2)
        self.assertIn("nope", err)

    def test_filters_are_exact(self):
        self.seed_review("stem-a")
        other = loop_audit.open_loop(self.root, "L3", cycle_stem="stem-b")
        _rc, data = payload(self.root, cycle_stem="stem-b")
        self.assertTrue(data["events"])
        self.assertTrue(all(item["cycle_stem"] == "stem-b" for item in data["events"]))
        _rc, data = payload(self.root, run_id=other)
        self.assertTrue(all(item["run_id"] == other for item in data["events"]))

    def test_filters_do_not_skip_integrity(self):
        """필터가 무결성 판정을 건너뛰면 '보이는 것만 검사' 가 된다."""
        self.seed_review("stem-a")
        write(self.root, REL["override"], "{broken")
        rc, data = payload(self.root, cycle_stem="stem-a")
        self.assertEqual(rc, 1)
        codes = {item["code"] for item in data["diagnostics"]}
        self.assertIn("audit.source.malformed", codes)


class Output(Base):
    def test_ordering_is_deterministic(self):
        self.seed_review()
        self.seed_fast()
        self.seed_acceptance()
        first = payload(self.root)[1]["events"]
        second = payload(self.root)[1]["events"]
        self.assertEqual(first, second)
        epochs = [item["epoch"] for item in first if item["epoch"] is not None]
        self.assertEqual(epochs, sorted(epochs, reverse=True))

    def test_repeated_runs_are_byte_identical(self):
        self.seed_review()
        self.seed_override()
        first = run(self.root, json=True)[1]
        second = run(self.root, json=True)[1]
        self.assertEqual(first, second)

    def test_truncation_is_counted_not_silent(self):
        for index in range(6):
            write(self.root, REL["override"], *[
                {"event": "grant", "grant_id": f"g{n}", "ts": "2026-01-01T00:00:00+00:00",
                 "epoch": 1767225600 + n, "gate": "all", "reason": "r",
                 "ttl_seconds": 60, "user": "tester"} for n in range(6)])
        rc, data = payload(self.root, limit=2)
        self.assertEqual(len(data["events"]), 2)
        self.assertEqual(data["omitted"], 4)
        self.assertIs(data["truncated"], True)
        self.assertEqual(data["returned"], 2)
        codes = {item["code"] for item in data["diagnostics"]}
        self.assertIn("audit.source.truncated", codes)
        self.assertEqual(rc, 0, "잘린 것은 손상이 아니다")

    def test_default_limit_matches_the_declared_contract(self):
        """상수와 실제 parser 기본값을 함께 본다.

        상수만 보면 등록부가 다른 값을 넣어도 통과하고, parser 만 보면 다른 호출부가 상수를
        읽어 갈라진 것을 놓친다.
        """
        self.assertEqual(audit_view.LIMIT_DEFAULT, 100)
        self.assertEqual(A.DEFAULT_LIMIT, audit_view.LIMIT_DEFAULT)
        parser = argparse.ArgumentParser()
        A.register(parser.add_subparsers(), "ko")
        self.assertEqual(parser.parse_args(["audit", "show"]).limit, 100)

    def test_out_of_range_limits_are_usage_errors(self):
        """`0` 은 무제한이 아니다. 범위 밖은 조용히 끌어당기지 않고 거절한다.

        끌어당기면 사용자가 요청한 값과 받은 값이 달라지고 화면 어디에도 그 사실이 남지
        않는다. 조회를 시작하기 전에 끝나므로 파일도 읽지 않는다.
        """
        self.seed_override()
        for value in (0, -1, -100, audit_view.LIMIT_MAX + 1, 999999):
            rc, out, err = run(self.root, limit=value)
            self.assertEqual(rc, 2, f"--limit {value} 가 통과했다")
            self.assertEqual(out, "", f"--limit {value} 가 결과를 냈다")
            self.assertIn(str(value), err, f"--limit {value} 가 무엇이 문제인지 말하지 않았다")

    def test_range_boundaries_are_accepted(self):
        self.seed_override()
        for value in (audit_view.LIMIT_MIN, audit_view.LIMIT_MAX):
            rc, data = payload(self.root, limit=value)
            self.assertEqual(rc, 0, f"--limit {value} 가 거절됐다")
            self.assertEqual(data["omitted"], 0)
            self.assertIs(data["truncated"], False)

    def test_a_rejected_limit_does_not_read_the_audit(self):
        """옵션 검증은 읽기 전에 끝난다 — 읽고 나서 거절하면 그 읽기가 헛수고다."""
        path = self.seed_override()
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, stat.S_IRUSR | stat.S_IWUSR)
        rc, _out, _err = run(self.root, limit=0)
        self.assertEqual(rc, 2, "읽기 실패(1)가 옵션 오류(2)를 덮었다")

    def test_json_is_locale_independent(self):
        self.seed_review()
        self.seed_override()
        korean = run(self.root, json=True, lang="ko")[1]
        english = run(self.root, json=True, lang="en")[1]
        self.assertEqual(korean.encode("utf-8"), english.encode("utf-8"))

    def test_text_states_that_ordering_is_display_only(self):
        self.seed_review()
        _rc, out, _err = run(self.root)
        self.assertIn("표시 순서", out)
        _rc, data = payload(self.root)
        self.assertEqual(data["ordering"], "display_order_only")

    def test_every_event_has_a_sentence_in_both_catalogs(self):
        """catalog key 를 만들어 두고 렌더하지 않으면 화면은 code 만 보이거나 문장을 잃는다."""
        from sage.i18n import CATALOGS
        expected = {f"cli.audit.event.{source}.{event}"
                    for source, event in audit_view._ALLOWLIST}
        expected.add("cli.audit.event.unknown")
        for language in ("ko", "en"):
            missing = sorted(expected - set(CATALOGS[language]))
            self.assertEqual(missing, [], f"{language} catalog 에 없는 event 문장 {missing}")

    def test_the_text_render_actually_uses_the_event_sentence(self):
        """죽은 catalog 방지 — 화면에 문장이 실제로 나오는지 본다."""
        from sage.i18n import CATALOGS
        self.seed_override()
        _rc, out, _err = run(self.root)
        self.assertIn(CATALOGS["ko"]["cli.audit.event.override.grant"], out)

    def test_missing_action_is_a_usage_error(self):
        rc = A._no_action(Args(self.root))
        self.assertEqual(rc, 2)


class Contract(Base):
    """조회는 새 권위를 만들지 않고, 진단 계약을 자기 식으로 다시 쓰지 않는다."""

    def test_every_block_code_has_a_recovery(self):
        for code, level in SEVERITY.items():
            if code.startswith("audit.") and level == BLOCK:
                self.assertTrue(RECOVERY.get(code), f"{code} 가 BLOCK 인데 다음 행동이 없다")

    def test_adapter_failure_is_a_tool_error_not_a_policy_block(self):
        self.seed_override()
        original = audit_sources._INTEGRITY["override"]

        def explode(_numbered):
            raise RuntimeError("boom")

        audit_sources._INTEGRITY["override"] = explode
        try:
            rc, data = payload(self.root)
        finally:
            audit_sources._INTEGRITY["override"] = original
        self.assertEqual(rc, 2, "도구 실패가 정책 차단과 같은 exit 로 나갔다")
        self.assertEqual(data["status"], "ERROR")
        codes = {item["code"] for item in data["diagnostics"]}
        self.assertIn("audit.source.unavailable", codes)

    def test_pure_layer_never_touches_the_filesystem(self):
        """문자열이 아니라 AST 로 본다 — 주석과 docstring 은 코드가 아니다."""
        self.assertEqual(_imports(audit_view) & {"os", "io", "pathlib", "shutil", "subprocess",
                                                 "fcntl", "msvcrt"}, set())
        self.assertNotIn("open", _called_names(audit_view))

    def test_view_layers_do_not_import_platform_locks(self):
        for module in (audit_view, audit_sources, A):
            self.assertEqual(_imports(module) & {"fcntl", "msvcrt"}, set(),
                             f"{module.__name__} 이 플랫폼 lock 을 import 한다")

    def test_no_layer_calls_the_writer_lock(self):
        """`_audit_lock` 은 `.sage/` 와 `.lock` 파일을 만든다. 부르는 순간 조회가 아니다."""
        for module in (audit_view, audit_sources, A):
            self.assertNotIn("_audit_lock", _called_names(module),
                             f"{module.__name__} 이 writer lock 을 부른다")

    def test_result_is_not_wired_into_any_gate(self):
        """조회 결과가 게이트 입력이 되면 읽기 전용 계층이 새 권위가 된다."""
        import pre_implementation_gate_core as gate
        with open(gate.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for banned in ("audit_view", "audit_sources", "commands.audit", "audit show"):
            self.assertNotIn(banned, source)


class PureBoundary(Base):
    """경계 정리가 writer·gate 의 판정을 바꾸지 않는다."""

    def test_loop_summary_is_unchanged_by_the_split(self):
        self.seed_review()
        records, issues = loop_audit._read_status(loop_audit.audit_path(self.root))
        self.assertEqual(json.dumps(loop_audit.audit_summary(self.root), sort_keys=True),
                         json.dumps(loop_audit.summarize_records(records, issues),
                                    sort_keys=True))

    def test_loop_integrity_is_unchanged_by_the_split(self):
        self.seed_review()
        records, issues = loop_audit._read_status(loop_audit.audit_path(self.root))
        self.assertEqual(loop_audit.integrity_issues(self.root),
                         loop_audit.integrity_from_records(records, issues))

    def test_acceptance_summary_is_unchanged_by_the_split(self):
        self.seed_acceptance()
        parsed, issues = acceptance_waiver._read_lines(self.root)
        now = 1767225600
        self.assertEqual(
            json.dumps(acceptance_waiver.audit_summary(self.root, now=now), sort_keys=True),
            json.dumps(acceptance_waiver.summarize_records(parsed, issues, now=now),
                       sort_keys=True))

    def test_pure_summary_does_not_accumulate_issues_across_calls(self):
        self.seed_acceptance()
        parsed, issues = acceptance_waiver._read_lines(self.root)
        first = acceptance_waiver.summarize_records(parsed, issues)
        second = acceptance_waiver.summarize_records(parsed, issues)
        self.assertEqual(first["issues"], second["issues"])
        self.assertEqual(issues, [], "호출부의 리스트를 건드렸다")

    def test_loop_snapshot_reports_status_without_folding(self):
        self.assertEqual(loop_audit.snapshot(self.root)["status"], "absent")
        self.seed_review()
        self.assertEqual(loop_audit.snapshot(self.root)["status"], "valid")
        write(self.root, REL["review"], "{broken")
        self.assertEqual(loop_audit.snapshot(self.root)["status"], "damaged")


class Tracking(Base):
    def test_missing_git_does_not_stop_the_query(self):
        self.seed_override()
        rc, data = payload(self.root)          # 임시 디렉터리는 Git 저장소가 아니다
        entry = next(item for item in data["sources"] if item["id"] == "override")
        self.assertEqual(entry["tracking"], "unavailable")
        self.assertEqual(rc, 0, "Git probe 실패가 조회를 막았다")
        codes = {item["code"] for item in data["diagnostics"]}
        self.assertIn("audit.source.tracking_unavailable", codes)

    def test_tracking_state_is_never_changed(self):
        self.seed_override()
        before = digests(self.root)
        run(self.root)
        self.assertEqual(before, digests(self.root))
        self.assertFalse(os.path.exists(os.path.join(self.root, ".gitignore")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
