#!/usr/bin/env python3
"""압축 직후 SessionStart(source `compact`) 재진입 문맥.

에이전트는 압축을 직접 못 한다. 사용자 `/compact` 나 자동 압축 뒤에 SessionStart 가 발화하고, 그때
넣는 짧은 글이 「문서에서 다시 읽고 이어 가라」를 지시한다. 이 파일은 그 글이 ① 압축일 때만 나오고
② 두 호스트 wire 가 같으며 ③ 사이클이 모호하면 고르지 않고 ④ 실패를 삼키지 않고 ⑤ 2048 바이트를
넘지 않으며 ⑥ 엔진 없이 돈다는 것을 본다. 기존 SessionStart 동작(06 baseline)은 바뀌지 않아야 한다.
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
RUNTIME = os.path.join(HOOKS_DIR, "runtime")
sys.path.insert(0, HOOKS_DIR)
sys.path.insert(0, RUNTIME)

import compact_reentry  # noqa: E402
import loop_audit as la  # noqa: E402

STEM = "demo-cycle"


def _declare(root, stem):
    Path(root, ".sage").mkdir(exist_ok=True)
    Path(root, ".sage", "cycle.json").write_text(json.dumps(
        {"version": 2, "cycle_stem": stem, "document_language": "ko",
         "declared_at": "2026-10-02T00:00:00Z"}), encoding="utf-8")


def _snapshot(root, stem, name):
    directory = Path(root, ".sage", "context", "snapshots", stem)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("{}", encoding="utf-8")
    return path


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def build(self, environ=None, language="ko", profile=None):
        return compact_reentry.build(self.root, profile, environ=environ or {}, language=language)

    def test_full_context_points_to_snapshot_restore_and_loop(self):
        _declare(self.root, STEM)
        _snapshot(self.root, STEM, "03-ctx-aaaa.json")
        _snapshot(self.root, STEM, "04-ctx-bbbb.json")
        rid = la.open_loop(self.root, "L2", cfg={}, cycle_stem=STEM)
        for i in (1, 2, 3):
            la.record_round(self.root, rid, i, 1, 1, 0)
        text = self.build()
        self.assertIn(STEM, text)
        self.assertIn(".sage/context/snapshots/demo-cycle/04-ctx-bbbb.json", text)
        self.assertIn("sage context restore --snapshot", text)
        self.assertIn("04 → 다음 05", text)
        self.assertIn(rid, text)
        self.assertIn("3/3", text)
        self.assertIn("ASK CYCLE_CAP", text)
        self.assertIn("ledger show --cycle-stem demo-cycle", text)
        self.assertIn("/sage-team", text)
        self.assertLessEqual(len(text.encode("utf-8")), compact_reentry.MAX_BYTES)

    def test_a_converged_run_at_the_cap_is_not_shown_as_waiting(self):
        _declare(self.root, STEM)
        rid = la.open_loop(self.root, "L2", cfg={}, cycle_stem=STEM)
        la.record_round(self.root, rid, 1, 1, 1, 0)
        la.record_round(self.root, rid, 2, 1, 1, 0)
        la.record_round(self.root, rid, 3, 1, 0, 0)
        self.assertNotIn("ASK CYCLE_CAP", self.build())

    def test_a_stop_verdict_is_not_shown_as_ask(self):
        _declare(self.root, STEM)
        cfg = {"budget_tokens": {"L2": 50}}
        rid = la.open_loop(self.root, "L2", cfg=cfg, cycle_stem=STEM)
        la.record_round(self.root, rid, 1, 1, 1, 0)
        la.record_round(self.root, rid, 2, 1, 1, 0)
        la.record_round(self.root, rid, 3, 1, 1, 0, tokens=100)
        text = self.build(profile={"pdca": {"review_loop": cfg}})
        self.assertNotIn("ASK CYCLE_CAP", text)
        self.assertIn("STOP BUDGET_TOK", text)

    def test_a_damaged_declaration_is_reported_not_hidden_as_absent(self):
        Path(self.root, ".sage").mkdir()
        Path(self.root, ".sage", "cycle.json").write_text("{broken", encoding="utf-8")
        text = self.build()
        self.assertIn("확인 실패", text)
        self.assertIn("cycle_state.json_invalid", text)

    def test_ambiguous_cycle_is_not_chosen(self):
        _declare(self.root, STEM)
        _snapshot(self.root, STEM, "04-ctx-bbbb.json")
        text = self.build(environ={"SAGE_CYCLE_STEM": "other"})
        self.assertIn("env=other", text)
        self.assertIn(f"file={STEM}", text)
        self.assertNotIn("sage context restore", text)

    def test_an_open_run_of_another_cycle_makes_it_ambiguous(self):
        _declare(self.root, STEM)
        la.open_loop(self.root, "L2", cfg={}, cycle_stem="elsewhere")
        text = self.build()
        self.assertIn("run=elsewhere", text)
        self.assertNotIn("sage context restore", text)

    def test_no_cycle_and_no_snapshot_still_says_the_documents_are_canonical(self):
        text = self.build()
        self.assertIn("정본은 phase 문서", text)
        self.assertIn("선언된 사이클이 없습니다", text)
        _declare(self.root, STEM)
        text = self.build()
        self.assertIn("snapshot 없음", text)

    def test_a_damaged_audit_is_reported(self):
        _declare(self.root, STEM)
        Path(self.root, ".sage", "loop_audit.jsonl").write_text("{not json\n", encoding="utf-8")
        text = self.build()
        self.assertIn("확인 실패", text)

    def test_symlinked_snapshot_is_ignored(self):
        _declare(self.root, STEM)
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside, "x.json")
            target.write_text("{}", encoding="utf-8")
            directory = Path(self.root, ".sage", "context", "snapshots", STEM)
            directory.mkdir(parents=True)
            os.symlink(target, directory / "05-ctx-cccc.json")
            self.assertIn("snapshot 없음", self.build())

    def test_profile_phase_order_drives_the_next_phase(self):
        _declare(self.root, STEM)
        _snapshot(self.root, STEM, "B-ctx-aaaa.json")
        profile = {"pdca": {"phases": [{"id": "A"}, {"id": "B"}, {"id": "C"}]}}
        self.assertIn("B → 다음 C", self.build(profile=profile))

    def test_english(self):
        _declare(self.root, STEM)
        text = self.build(language="en")
        self.assertIn("The context was compacted", text)
        self.assertNotRegex(text, "[가-힣]")

    def test_size_is_capped(self):
        long_stem = "s" * 150
        _declare(self.root, long_stem)
        for i in range(20):
            la.open_loop(self.root, "L2", cfg={}, cycle_stem=long_stem)
        text = self.build()
        self.assertLessEqual(len(text.encode("utf-8")), compact_reentry.MAX_BYTES + 16)


class TestSessionStartHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        _declare(self.root, STEM)
        _snapshot(self.root, STEM, "04-ctx-bbbb.json")

    def hook(self, runtime, source):
        env = {k: v for k, v in os.environ.items()
               if k not in ("SAGE_CYCLE_STEM", "PYTHONPATH", "SAGE_PROFILE")}
        return subprocess.run(
            [sys.executable, os.path.join(RUNTIME, "run_hook.py"), "--runtime", runtime,
             "--hook", "session-start-snapshot", "--root", self.root, "--core-dir", HOOKS_DIR],
            input=json.dumps({"session_id": "s1", "source": source}), text=True,
            capture_output=True, env=env, cwd=self.root)

    def test_both_hosts_emit_one_session_start_json_line_on_compact(self):
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime):
                result = self.hook(runtime, "compact")
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = [line for line in result.stdout.splitlines() if line.strip()]
                self.assertEqual(len(lines), 1)
                payload = json.loads(lines[0])["hookSpecificOutput"]
                self.assertEqual(payload["hookEventName"], "SessionStart")
                self.assertIn("sage context restore", payload["additionalContext"])

    def test_other_sources_emit_nothing_on_stdout(self):
        for source in ("startup", "resume", "clear"):
            with self.subTest(source=source):
                result = self.hook("claude", source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "")


class TestEngineIndependence(unittest.TestCase):
    def test_imports_and_builds_without_the_sage_package(self):
        with tempfile.TemporaryDirectory() as root:
            code = (
                "import sys; sys.path[:0] = [%r, %r]\n"
                "import compact_reentry\n"
                "text = compact_reentry.build(%r, None, environ={}, language='ko')\n"
                "assert 'sage' not in sys.modules, sorted(m for m in sys.modules if m.startswith('sage'))\n"
                "print('ok')\n" % (RUNTIME, HOOKS_DIR, root))
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                    cwd=root, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "ok")


if __name__ == "__main__":
    unittest.main(verbosity=1)
