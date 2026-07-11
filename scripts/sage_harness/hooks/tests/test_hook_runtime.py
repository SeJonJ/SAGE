#!/usr/bin/env python3
"""hook_runtime / io_* 단위 테스트 (외부검토 R1 의 진짜 이득).

이전엔 어댑터 heredoc 안에 임베드돼 import·단위테스트 불가였던 IO 로직이, runtime 모듈 추출로
직접 검증 가능해졌다. 입력추출(런타임별)·snapshot·전략 F8b·렌더 채널을 픽스처로 못박는다.
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
HOOKS_DIR = os.path.join(REPO, "scripts", "sage_harness", "hooks")
RUNTIME_DIR = os.path.join(HOOKS_DIR, "runtime")
sys.path.insert(0, RUNTIME_DIR)
sys.path.insert(0, os.path.join(HOOKS_DIR, "policies"))   # output_contract_check / knowledge_capture
import hook_runtime as hr   # noqa: E402
import io_claude            # noqa: E402
import io_codex             # noqa: E402

_ID = lambda p: p   # noqa: E731  (rel passthrough)


class TestExtractChangesClaude(unittest.TestCase):
    def test_write_content(self):
        ch = io_claude.extract_changes({"tool_input": {"file_path": "a/b.src", "content": "x"}}, _ID)
        self.assertEqual(ch, [{"path": "a/b.src", "op": "write", "content": "x"}])

    def test_edit_new_string_and_multiedit_accumulate(self):
        raw = {"tool_input": {"file_path": "f.src", "new_string": "base",
                              "edits": [{"new_string": "e1"}, {"new_string": "e2"}]}}
        ch = io_claude.extract_changes(raw, _ID)
        self.assertEqual(ch[0]["path"], "f.src")
        for tok in ("base", "e1", "e2"):
            self.assertIn(tok, ch[0]["content"])

    def test_no_file_path_yields_empty(self):
        self.assertEqual(io_claude.extract_changes({"tool_input": {}}, _ID), [])

    def test_claude_never_skips(self):
        self.assertFalse(io_claude.should_skip({"tool_name": "anything"}))


class TestExtractChangesCodex(unittest.TestCase):
    def test_apply_patch_multifile(self):
        cmd = ("*** Begin Patch\n*** Add File: a.src\n+hello\n"
               "*** Update File: b.src\n+world\n*** End Patch")
        ch = io_codex.extract_changes({"tool_name": "apply_patch", "tool_input": {"command": cmd}}, _ID)
        self.assertEqual(len(ch), 2)
        self.assertEqual((ch[0]["path"], ch[0]["op"]), ("a.src", "add"))
        self.assertIn("hello", ch[0]["content"])
        self.assertEqual((ch[1]["path"], ch[1]["op"]), ("b.src", "update"))
        self.assertIn("world", ch[1]["content"])

    def test_should_skip_non_apply_patch(self):
        self.assertTrue(io_codex.should_skip({"tool_name": "shell"}))
        self.assertFalse(io_codex.should_skip({"tool_name": "apply_patch"}))


class TestBuildSnapshot(unittest.TestCase):
    def test_phase_docs_recent_flag(self):
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, "plan_docs", "00-base_plan")
            os.makedirs(d)
            with open(os.path.join(d, "f.md"), "w", encoding="utf-8") as f:
                f.write("# x")
            profile = {"risk": {"plan_glob": "plan_docs/**/*.md"},
                       "pdca": {"enabled": True,
                                "phases": [{"id": "00", "glob": "plan_docs/00-base_plan/**/*.md"}]}}
            snap = hr.build_snapshot(profile, root, hr.make_rel(root))
            self.assertIn("00", snap["phase_docs"])
            self.assertEqual(len(snap["phase_docs"]["00"]), 1)
            self.assertTrue(snap["phase_docs"]["00"][0]["recent"])
            self.assertGreaterEqual(len(snap["plan_files"]), 1)

    def test_unsafe_glob_rejected_empty(self):
        with tempfile.TemporaryDirectory() as root:
            snap = hr.build_snapshot({"risk": {"plan_glob": "/abs/evil/**"}}, root, hr.make_rel(root))
            self.assertEqual(snap["plan_files"], [])

    def test_loop_audit_injected(self):
        # 9.5: build_snapshot 이 .sage/loop_audit.jsonl 요약을 snapshot 에 주입한다.
        import loop_audit as la
        with tempfile.TemporaryDirectory() as root:
            rid = la.open_loop(root, "L3", run_id="run-z", now=0)
            la.close_loop(root, rid, result="APPROVED", reason="CONVERGED", iterations=1, now=2)
            snap = hr.build_snapshot({"risk": {}, "pdca": {}}, root, hr.make_rel(root))
            self.assertIn("loop_audit", snap)
            self.assertTrue(snap["loop_audit"]["has_any_records"])
            self.assertEqual(snap["loop_audit"]["runs"]["run-z"],
                             {"closed": True, "result": "APPROVED", "clean": True, "seq_ok": True,
                              "reviewer_requested": None, "reviewer_actual": None, "degraded": False})

    def test_loop_audit_fail_open_no_sage_dir(self):
        # .sage 부재 → fail-open 빈 요약(snapshot 빌드는 안 깨짐).
        with tempfile.TemporaryDirectory() as root:
            snap = hr.build_snapshot({"risk": {}, "pdca": {}}, root, hr.make_rel(root))
            self.assertEqual(snap["loop_audit"], {"runs": {}, "has_any_records": False})


class TestReduce06Bindings(unittest.TestCase):
    """9-C-2 W1: 06 자기선언 Loop-Run 을 06 별로 결속 → worst-case 축약(집계 마스킹/오판 제거)."""

    def test_single_checked_resolves_ok(self):
        self.assertEqual(hr._reduce_06_bindings({"06-a.md": {"rl-a"}}, {"rl-a": {"checked": True}}),
                         ("rl-a", "resolved", True, []))

    def test_single_unchecked(self):
        self.assertEqual(hr._reduce_06_bindings({"06-a.md": {"rl-a"}}, {}), ("rl-a", "resolved", False, ["rl-a"]))

    def test_no_marker_is_no_candidate(self):
        rid, binding, _, missing = hr._reduce_06_bindings({"06-a.md": set()}, {})
        self.assertEqual((rid, binding, missing), (None, "no_candidate", []))

    def test_two_markers_in_one_06_is_ambiguous(self):
        rid, binding, _, missing = hr._reduce_06_bindings({"06-a.md": {"rl-a", "rl-b"}}, {})
        self.assertEqual((rid, binding, missing), (None, "ambiguous", []))

    def test_multi_06_all_checked_passes(self):
        # codex W1 P1: 정상 다중 사이클을 모호로 오판하지 않는다(각 06 유일 결속·확인).
        summary = {"rl-a": {"checked": True}, "rl-b": {"checked": True}}
        rid, binding, checked, missing = hr._reduce_06_bindings({"06-a.md": {"rl-a"}, "06-b.md": {"rl-b"}}, summary)
        self.assertEqual((binding, checked, missing), ("resolved", True, []))
        self.assertIn(rid, ("rl-a", "rl-b"))

    def test_multi_06_one_unbound_not_masked(self):
        # codex W1 P1: 확인된 06 이 결속 불가 06 을 가리지 않는다 — 미선언 06 이 있으면 no_candidate.
        rid, binding, _, missing = hr._reduce_06_bindings(
            {"06-a.md": {"rl-a"}, "06-b.md": set()}, {"rl-a": {"checked": True}})
        self.assertEqual((rid, binding, missing), (None, "no_candidate", []))

    def test_multi_06_all_unchecked_returns_all_missing(self):
        # codex W1 R2 P1: 다중 미확인 run 을 첫 하나로 자르지 않는다 — missing 에 전부 담아 감사 기록 보장.
        rid, binding, checked, missing = hr._reduce_06_bindings(
            {"06-a.md": {"rl-a"}, "06-b.md": {"rl-b"}}, {})
        self.assertEqual((rid, binding, checked, missing), ("rl-a", "resolved", False, ["rl-a", "rl-b"]))

    def test_multi_06_one_unchecked_reports_that_run(self):
        # 전부 유일 결속이나 하나가 미확인 → 대표는 그 미확인 run, missing 도 그 run 만.
        summary = {"rl-a": {"checked": True}, "rl-b": {"checked": False}}
        self.assertEqual(hr._reduce_06_bindings({"06-a.md": {"rl-a"}, "06-b.md": {"rl-b"}}, summary),
                         ("rl-b", "resolved", False, ["rl-b"]))

    def test_no_candidate_still_records_resolved_unchecked(self):
        # codex W1 R2 재검 P1: 결속 불가(미선언 06)여도 유효 선언·미확인 run 은 missing 에 남아야 한다
        # (게이트는 no_candidate 로 BLOCK 하되 doctor 가시성용 감사 대상은 유지).
        self.assertEqual(hr._reduce_06_bindings({"06-a.md": {"rl-a"}, "06-b.md": set()}, {}),
                         (None, "no_candidate", False, ["rl-a"]))

    def test_ambiguous_still_records_resolved_unchecked(self):
        # 상충 06 이 있어도 다른 유효 선언·미확인 run 은 missing 에 남는다.
        self.assertEqual(hr._reduce_06_bindings({"06-a.md": {"rl-a"}, "06-b.md": {"rl-x", "rl-y"}}, {}),
                         (None, "ambiguous", False, ["rl-a"]))


class TestHeaderLoopRunIds(unittest.TestCase):
    """9-C-2 W1: 06 헤더(첫 H2 전)만 Loop-Run 파싱 — 본문 코드블록/헤딩 변형 무시, BOM 제거."""

    def test_marker_before_first_h2(self):
        c = "# [Report] X\n\nLoop-Run: rl-a\nSource-05: p\n\n## 1. Summary\n"
        self.assertEqual(hr._header_loop_run_ids(c), {"rl-a"})

    def test_body_code_block_ignored(self):
        c = "# X\nLoop-Run: rl-a\n\n## 예시\n```\nLoop-Run: rl-example\n```\n"
        self.assertEqual(hr._header_loop_run_ids(c), {"rl-a"})

    def test_indented_and_tab_h2_terminate_header(self):
        # codex W1 R2 재검 P2: `  ## `·`##\t` 도 헤더 종료로 봐 본문 예시 Loop-Run 이 새지 않는다.
        for h2 in ("  ## Summary", "##\tSummary"):
            c = f"# X\nLoop-Run: rl-a\n{h2}\nLoop-Run: rl-body\n"
            self.assertEqual(hr._header_loop_run_ids(c), {"rl-a"}, h2)

    def test_bom_prefixed_marker_detected(self):
        # codex W1 R2 재검 P2: 선두 BOM 뒤 바로 오는 Loop-Run 도 놓치지 않는다.
        self.assertEqual(hr._header_loop_run_ids("\ufeffLoop-Run: rl-a\n## S\n"), {"rl-a"})

    def test_h1_is_not_a_terminator(self):
        # H1 제목은 종료가 아니다 — 그 아래 Loop-Run 을 여전히 읽는다.
        self.assertEqual(hr._header_loop_run_ids("# [Report]\nLoop-Run: rl-a\n## S\n"), {"rl-a"})


class TestRunStrategyF8b(unittest.TestCase):
    def test_crash_surfaces_and_fails_closed(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            r = hr.run_strategy("pre-implementation-gate",
                                {"risk": {"l3_review_strategy": "nonexistent_strategy_xyz"}},
                                "/tmp/sage-no-core", [], {"branch": ""}, {})
        self.assertIsNone(r)                          # fail-closed (None → core L3 BLOCK 유지)
        self.assertIn("fail-closed BLOCK", buf.getvalue())  # 크래시 surface(F8b)

    def test_no_strategy_returns_none(self):
        self.assertIsNone(hr.run_strategy("h", {"risk": {}}, "/tmp", [], {}, {}))

    def test_parse_input_fail_open_surface(self):
        # 게이트 hook(surface=True): malformed 입력을 stderr 로 surface + None(호출자 exit0). (5-1)
        err = io.StringIO()
        with redirect_stderr(err):
            r = hr.parse_input_fail_open("pre-phase4-checklist-gate", "{not valid json", surface=True)
        self.assertIsNone(r)
        self.assertIn("파싱 실패", err.getvalue())

    def test_parse_input_fail_open_silent_for_nongate(self):
        # 비게이트(surface=False): 원본 silent 보존.
        err = io.StringIO()
        with redirect_stderr(err):
            r = hr.parse_input_fail_open("post-tool-logger", "{bad", surface=False)
        self.assertIsNone(r)
        self.assertEqual(err.getvalue(), "")


class TestRenderChannels(unittest.TestCase):
    def test_codex_block_to_stderr_exit2(self):
        d = {"message_key": "block_l3_no_plan", "status": "block", "exit_code": 2,
             "file_short": "f", "reason": "r"}
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = io_codex.render_gate(d, {})
        self.assertEqual(rc, 2)
        self.assertIn("GATE BLOCK", err.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_codex_warn_to_hookspecific_json(self):
        d = {"message_key": "warn_l2_no_plan", "status": "warn", "exit_code": 0,
             "file_short": "f", "reason": "r"}
        out = io.StringIO()
        with redirect_stdout(out):
            rc = io_codex.render_gate(d, {})
        self.assertEqual(rc, 0)
        self.assertIn("hookSpecificOutput", out.getvalue())

    def test_claude_block_to_stdout_with_phase_text(self):
        d = {"message_key": "block_phase_incomplete", "status": "block", "exit_code": 2,
             "risk": "L2", "file_short": "f", "reason": "r", "missing_phases": ["00", "01"]}
        out = io.StringIO()
        with redirect_stdout(out):
            rc = io_claude.render_gate(d, {})
        self.assertEqual(rc, 2)
        self.assertIn("PDCA phase 미작성", out.getvalue())   # 게이트 출력 문자열 계약 보존


class TestLoggerExtraction(unittest.TestCase):
    def test_claude_single_file_write(self):
        ch = io_claude.extract_logged_changes({"tool_input": {"file_path": "a.src"}}, _ID)
        self.assertEqual(ch, [{"path": "a.src", "op": "write"}])

    def test_codex_add_update_delete_move(self):
        cmd = ("*** Add File: a.src\n+x\n*** Update File: b.src\n+y\n"
               "*** Delete File: c.src\n*** Move to: d.src")
        ch = io_codex.extract_logged_changes({"tool_input": {"command": cmd}}, _ID)
        ops = {(c["path"], c["op"]) for c in ch}
        self.assertEqual(ops, {("a.src", "add"), ("b.src", "update"), ("c.src", "delete"), ("d.src", "move")})


class TestPhase4Extraction(unittest.TestCase):
    def test_codex_only_add_update_not_delete(self):
        cmd = "*** Add File: a.src\n*** Update File: b.src\n*** Delete File: c.src"
        ch = io_codex.extract_phase4_changes({"tool_input": {"command": cmd}}, _ID)
        paths = {c["path"] for c in ch}
        self.assertEqual(paths, {"a.src", "b.src"})    # Delete 는 phase4 추출 대상 아님(원본 충실)


class TestStopPolicyOrder(unittest.TestCase):
    """stop-compliance-report: claude=[knowledge_capture] / codex=[output_contract, knowledge_capture] 순서 보존."""

    def _model(self):
        return {"sections": {"policy_results": []}}

    def test_claude_only_knowledge_capture(self):
        m = self._model()
        io_claude.attach_policy_results(m, {}, [], "{}", {"check": "kc"})
        res = m["sections"]["policy_results"]
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0], {"check": "kc"})

    def test_codex_output_contract_then_knowledge_capture(self):
        m = self._model()
        profile = {"compliance": {"plan_gate_code_types": ["src"]}}
        io_codex.attach_policy_results(m, profile, [], "{}", {"check": "kc"})
        res = m["sections"]["policy_results"]
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].get("name"), "output_contract")    # codex 는 output_contract 먼저
        self.assertEqual(res[1], {"check": "kc"})                  # 그 다음 공유 knowledge_capture(sentinel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
