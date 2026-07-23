#!/usr/bin/env python3
"""hook_runtime / io_* 단위 테스트 (외부검토 R1 의 진짜 이득).

이전엔 어댑터 heredoc 안에 임베드돼 import·단위테스트 불가였던 IO 로직이, runtime 모듈 추출로
직접 검증 가능해졌다. 입력추출(런타임별)·snapshot·전략 F8b·렌더 채널을 픽스처로 못박는다.
"""
import io
import errno
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
HOOKS_DIR = os.path.join(REPO, "scripts", "sage_harness", "hooks")
RUNTIME_DIR = os.path.join(HOOKS_DIR, "runtime")
sys.path.insert(0, RUNTIME_DIR)
sys.path.insert(0, os.path.join(HOOKS_DIR, "policies"))   # output_contract_check / knowledge_capture
sys.path.insert(0, HOOKS_DIR)
import hook_runtime as hr   # noqa: E402
import io_claude            # noqa: E402
import io_codex             # noqa: E402
import pre_implementation_gate_core as pre_gate  # noqa: E402

_ID = lambda p: p   # noqa: E731  (rel passthrough)


class TestExtractChangesClaude(unittest.TestCase):
    def test_write_content(self):
        ch = io_claude.extract_changes({"tool_name": "Write",
                                        "tool_input": {"file_path": "a/b.src", "content": "x"}}, _ID)
        self.assertEqual(ch, [{"path": "a/b.src", "op": "write", "content": "x",
                               "full_content": True}])

    def test_edit_new_string_and_multiedit_accumulate(self):
        raw = {"tool_name": "MultiEdit", "tool_input": {
            "file_path": "f.src", "new_string": "base", "old_string": "old-base",
            "edits": [{"new_string": "e1", "old_string": "old-e1"},
                      {"new_string": "e2", "old_string": "old-e2"}]}}
        ch = io_claude.extract_changes(raw, _ID)
        self.assertEqual(ch[0]["path"], "f.src")
        self.assertEqual(ch[0]["op"], "update")
        for tok in ("base", "e1", "e2"):
            self.assertIn(tok, ch[0]["content"])
        for tok in ("old-base", "old-e1", "old-e2"):
            self.assertIn(tok, ch[0]["removed_content"])

    def test_no_file_path_yields_empty(self):
        self.assertEqual(io_claude.extract_changes({"tool_input": {}}, _ID), [])

    def test_claude_never_skips(self):
        self.assertFalse(io_claude.should_skip({"tool_name": "anything"}))


class TestExtractChangesCodex(unittest.TestCase):
    @staticmethod
    def _empty_snapshot():
        return {"plan_files": [], "review_candidates": [], "phase_docs": {}}

    def test_apply_patch_multifile(self):
        cmd = ("*** Begin Patch\n*** Add File: a.src\n+hello\n"
               "*** Update File: b.src\n+world\n*** End Patch")
        ch = io_codex.extract_changes({"tool_name": "apply_patch", "tool_input": {"command": cmd}}, _ID)
        self.assertEqual(len(ch), 2)
        self.assertEqual((ch[0]["path"], ch[0]["op"]), ("a.src", "add"))
        self.assertIn("hello", ch[0]["content"])
        self.assertEqual((ch[1]["path"], ch[1]["op"]), ("b.src", "update"))
        self.assertIn("world", ch[1]["content"])

    def test_apply_patch_preserves_removed_lines(self):
        cmd = ("*** Begin Patch\n*** Update File: phase.md\n@@\n"
               "-Cycle-Stem: `feature`\n+Status: COMPLETE\n*** End Patch")
        ch = io_codex.extract_changes(
            {"tool_name": "apply_patch", "tool_input": {"command": cmd}}, _ID)
        self.assertEqual(ch[0]["removed_content"], "Cycle-Stem: `feature`\n")

    def test_should_skip_non_apply_patch(self):
        self.assertTrue(io_codex.should_skip({"tool_name": "shell"}))
        self.assertFalse(io_codex.should_skip({"tool_name": "apply_patch"}))

    def test_rename_keeps_source_destination_and_added_content(self):
        cmd = ("*** Begin Patch\n*** Update File: src/old.py\n"
               "*** Move to: src/new.py\n@@\n-old\n+privateKey = value\n*** End Patch")
        ch = io_codex.extract_changes({"tool_name": "apply_patch", "tool_input": {"command": cmd}}, _ID)

        self.assertEqual([(c["path"], c["op"]) for c in ch],
                         [("src/old.py", "update"), ("src/new.py", "move")])
        self.assertTrue(all("privateKey = value" in c["content"] for c in ch))

    def test_rename_destination_l3_glob_controls_compound_risk(self):
        cmd = ("*** Begin Patch\n*** Update File: src/harmless.py\n"
               "*** Move to: security/critical.py\n@@\n+x = privateKey\n*** End Patch")
        changes = io_codex.extract_changes(
            {"tool_name": "apply_patch", "tool_input": {"command": cmd}}, _ID)
        profile = {"risk": {
            "l0_pass_globs": [],
            "l1_path_globs": [],
            "l2_path_globs": ["src/**"],
            "l3_filename_globs": ["security/**"],
            "l2_content_keywords": [],
            "l3_content_keywords": ["privateKey"],
        }}

        classified = pre_gate.classify_risk({"changes": changes}, profile)

        self.assertEqual(classified["risk"], "L3")
        self.assertTrue(classified["is_l3_filename"])
        self.assertEqual(classified["file_short"], "security/critical.py")
        self.assertEqual(set(classified["trigger_sources"]), {"path_l2", "content_l3", "filename_l3"})

        decision = pre_gate.decide({"changes": changes}, profile, self._empty_snapshot(), None)
        self.assertEqual((decision["status"], decision["exit_code"], decision["message_key"]),
                         ("block", 2, "block_l3_no_plan"))

    def test_rename_added_content_is_available_for_content_l3(self):
        cmd = ("*** Begin Patch\n*** Update File: src/old.py\n"
               "*** Move to: src/new.py\n@@\n+x = privateKey\n*** End Patch")
        changes = io_codex.extract_changes(
            {"tool_name": "apply_patch", "tool_input": {"command": cmd}}, _ID)
        profile = {"risk": {
            "l0_pass_globs": [],
            "l1_path_globs": [],
            "l2_path_globs": ["src/**"],
            "l3_filename_globs": [],
            "l2_content_keywords": [],
            "l3_content_keywords": ["privateKey"],
        }}

        classified = pre_gate.classify_risk({"changes": changes}, profile)

        self.assertEqual(classified["risk"], "L3")
        self.assertIn("content_l3", classified["trigger_sources"])

        profile["risk"]["content_l3_enforce"] = "block"
        decision = pre_gate.decide({"changes": changes}, profile, self._empty_snapshot(), None)
        self.assertEqual((decision["status"], decision["exit_code"], decision["message_key"]),
                         ("block", 2, "block_l3_no_plan"))

    def test_orphan_move_marker_still_preserves_destination(self):
        cmd = "*** Begin Patch\n*** Move to: security/orphan.py\n+x = 1\n*** End Patch"
        ch = io_codex.extract_changes({"tool_name": "apply_patch", "tool_input": {"command": cmd}}, _ID)

        self.assertEqual(ch, [{"path": "security/orphan.py", "op": "move", "content": "x = 1\n"}])

    def test_move_after_hunk_backfills_destination_for_content_l3(self):
        cmd = ("*** Begin Patch\n*** Update File: tmp/scratch.txt\n"
               "@@\n+privateKey = value\n*** Move to: src/new.py\n*** End Patch")
        changes = io_codex.extract_changes(
            {"tool_name": "apply_patch", "tool_input": {"command": cmd}}, _ID)
        profile = {"risk": {
            "l0_pass_globs": [],
            "l1_path_globs": [],
            "l2_path_globs": ["src/**"],
            "l3_filename_globs": [],
            "l2_content_keywords": [],
            "l3_content_keywords": ["privateKey"],
        }}

        classified = pre_gate.classify_risk({"changes": changes}, profile)

        self.assertEqual(changes[1]["content"], "privateKey = value\n")
        self.assertEqual(classified["risk"], "L3")
        self.assertIn("content_l3", classified["trigger_sources"])

    def test_l0_source_does_not_mask_l3_destination(self):
        cmd = ("*** Begin Patch\n*** Update File: docs/harmless.md\n"
               "*** Move to: security/critical.py\n@@\n+x = 1\n*** End Patch")
        changes = io_codex.extract_changes(
            {"tool_name": "apply_patch", "tool_input": {"command": cmd}}, _ID)
        profile = {"risk": {
            "l0_pass_globs": ["docs/**"],
            "l1_path_globs": [],
            "l2_path_globs": [],
            "l3_filename_globs": ["security/**"],
            "l2_content_keywords": [],
            "l3_content_keywords": [],
        }}

        classified = pre_gate.classify_risk({"changes": changes}, profile)

        self.assertEqual(classified["risk"], "L3")
        self.assertTrue(classified["is_l3_filename"])
        self.assertEqual(classified["file_short"], "security/critical.py")

    def test_new_file_marker_resets_rename_content_targets(self):
        cmd = ("*** Begin Patch\n*** Update File: src/a.py\n*** Move to: src/b.py\n"
               "@@\n+first\n*** Update File: src/c.py\n@@\n+second\n"
               "*** Move to: src/d.py\n*** End Patch")
        changes = io_codex.extract_changes(
            {"tool_name": "apply_patch", "tool_input": {"command": cmd}}, _ID)
        by_path = {change["path"]: change["content"] for change in changes}

        self.assertEqual(by_path, {
            "src/a.py": "first\n",
            "src/b.py": "first\n",
            "src/c.py": "second\n",
            "src/d.py": "second\n",
        })

    def test_duplicate_move_markers_backfill_and_fan_out_deterministically(self):
        cmd = ("*** Begin Patch\n*** Update File: src/old.py\n@@\n+before\n"
               "*** Move to: src/new-a.py\n+middle\n*** Move to: src/new-b.py\n+after\n"
               "*** End Patch")
        changes = io_codex.extract_changes(
            {"tool_name": "apply_patch", "tool_input": {"command": cmd}}, _ID)
        by_path = {change["path"]: change["content"] for change in changes}

        self.assertEqual(by_path, {
            "src/old.py": "before\nmiddle\nafter\n",
            "src/new-a.py": "before\nmiddle\nafter\n",
            "src/new-b.py": "before\nmiddle\nafter\n",
        })

    def test_same_file_preserves_filename_and_content_l3_provenance(self):
        profile = {"risk": {
            "l0_pass_globs": [],
            "l1_path_globs": [],
            "l2_path_globs": [],
            "l3_filename_globs": ["security/**"],
            "l2_content_keywords": [],
            "l3_content_keywords": ["privateKey"],
        }}

        classified = pre_gate.classify_risk({"changes": [{
            "path": "security/critical.py",
            "op": "move",
            "content": "privateKey = value\n",
        }]}, profile)

        self.assertEqual(classified["trigger_sources"], ["filename_l3", "content_l3"])
        self.assertEqual(classified["file_short"], "security/critical.py")
        self.assertIn("내용 L3 키워드", classified["reason"])

    def test_equal_rank_trigger_union_does_not_misattribute_reason(self):
        profile = {"risk": {
            "l0_pass_globs": [],
            "l1_path_globs": [],
            "l2_path_globs": ["src/**"],
            "l3_filename_globs": ["security/**"],
            "l2_content_keywords": [],
            "l3_content_keywords": ["privateKey"],
        }}
        changes = [
            {"path": "src/contains-key.py", "op": "update", "content": "privateKey = value\n"},
            {"path": "security/plain.py", "op": "move", "content": "x = 1\n"},
        ]

        classified = pre_gate.classify_risk({"changes": changes}, profile)

        self.assertEqual(set(classified["trigger_sources"]), {"path_l2", "content_l3", "filename_l3"})
        self.assertEqual(classified["file_short"], "security/plain.py")
        self.assertEqual(classified["reason"], "L3 filename 패턴")


class TestMakeRel(unittest.TestCase):
    def test_normalizes_equivalent_paths_inside_root(self):
        with tempfile.TemporaryDirectory() as root:
            rel = hr.make_rel(root)
            basename = os.path.basename(root)
            for path in (
                "plan_docs/./06-report/feature.md",
                "plan_docs//06-report/feature.md",
                "plan_docs/05-expert-review/../06-report/feature.md",
                f"../{basename}/plan_docs/06-report/feature.md",
                os.path.join(root, "plan_docs", "06-report", "feature.md"),
            ):
                with self.subTest(path=path):
                    self.assertEqual(rel(path), "plan_docs/06-report/feature.md")

    def test_rejects_paths_outside_project_namespace(self):
        with tempfile.TemporaryDirectory() as root:
            rel = hr.make_rel(root)
            self.assertEqual(rel("../../outside.md"), "<outside-project>")
            self.assertEqual(rel(os.path.join(os.path.dirname(root), "outside.md")),
                             "<outside-project>")


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

    def test_dedicated_l3_review_glob_is_separate_from_plan_candidates(self):
        with tempfile.TemporaryDirectory() as root:
            review_dir = os.path.join(root, "reviews")
            os.makedirs(review_dir)
            with open(os.path.join(review_dir, "r.md"), "w", encoding="utf-8") as fh:
                fh.write("---\ncycle_id: 7\nround: [1, 2]\ndomain_ref: auth\n---\n")
            snap = hr.build_snapshot({"risk": {"l3_review_glob": "reviews/*.md"}},
                                     root, hr.make_rel(root))
            self.assertEqual([d["path"] for d in snap["l3_review_docs"]], ["reviews/r.md"])
            self.assertEqual(snap["review_candidates"], [])

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

    def test_acceptance_waiver_audit_injected_only_when_enabled(self):
        import acceptance_waiver as aw
        with tempfile.TemporaryDirectory() as root:
            grant = aw.grant(root, "feature", "A1", "prod only", "one smoke",
                             "live callback", "sejon", ttl_seconds=3600)
            enabled = {"verification": {"acceptance": {"waiver": {"enabled": True}}}}
            snap = hr.build_snapshot(enabled, root, hr.make_rel(root))
            self.assertTrue(snap["acceptance_waivers"]["valid"])
            self.assertEqual(snap["acceptance_waivers"]["active"][0]["waiver_id"], grant["waiver_id"])
            disabled = hr.build_snapshot({}, root, hr.make_rel(root))
            self.assertEqual(disabled["acceptance_waivers"]["active"], [])


class TestAcceptanceWaiverUseAdapter(unittest.TestCase):
    def test_records_use_before_returning_warning(self):
        import acceptance_waiver as aw
        with tempfile.TemporaryDirectory() as root:
            grant = aw.grant(root, "feature", "A1", "prod only", "one smoke",
                             "live callback", "sejon", ttl_seconds=3600)
            decision = {"status": "warn", "exit_code": 0, "message_key": "warn_report_with_l3_waiver",
                        "file_short": "feature.md",
                        "waiver_uses": [dict(grant, report_path="plan_docs/06-report/feature.md")]}
            result = hr._record_acceptance_waiver_uses("pre-implementation-gate", root, decision)
            self.assertIs(result, decision)
            self.assertEqual([r["event"] for r in aw.read_records(root)], ["grant", "use"])

    def test_audit_append_failure_turns_warning_into_block(self):
        from unittest import mock
        decision = {"status": "warn", "exit_code": 0, "message_key": "warn_report_with_l3_waiver",
                    "file_short": "feature.md", "waiver_uses": [{"report_path": "feature.md"}]}
        with mock.patch("acceptance_waiver.record_use", side_effect=OSError("disk full")):
            result = hr._record_acceptance_waiver_uses("pre-implementation-gate", "/tmp", decision)
        self.assertEqual(result["message_key"], "block_report_waiver_audit_failure")
        self.assertEqual(result["exit_code"], 2)

    def test_unexpected_core_exception_turns_into_exit2_block(self):
        class ExplodingCore:
            @staticmethod
            def decide(*_args):
                raise TypeError("bad profile shape")

        event = {"changes": [{"path": "plan_docs/06-report/feature.md"}]}
        err = io.StringIO()
        with redirect_stderr(err):
            result = hr._decide_pre_implementation_fail_closed(
                "pre-implementation-gate", ExplodingCore, event, {}, {}, None)
        self.assertEqual(result["message_key"], "block_gate_runtime_error")
        self.assertEqual(result["exit_code"], 2)
        self.assertTrue(result["safety_degraded"])
        self.assertIn("TypeError", err.getvalue())


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


class TestHeaderFields06(unittest.TestCase):
    """writeback_depth_gate 어댑터: 06 헤더(첫 H2 전)에서 Risk Level·Depth-Self-Review 파싱."""

    def test_tier_and_declared_performed(self):
        c = "# [Report] X\n\nLoop-Run: rl-a\nRisk Level: L2\nDepth-Self-Review: performed\n\n## 1. 결과\n"
        self.assertEqual(hr._header_fields_06(c), ("L2", True))

    def test_skipped_is_not_declared(self):
        c = "# X\nRisk Level: L1\nDepth-Self-Review: skipped\n## S\n"
        self.assertEqual(hr._header_fields_06(c), ("L1", False))

    def test_missing_fields(self):
        self.assertEqual(hr._header_fields_06("# X\n\n## 본문\n"), (None, False))

    def test_body_line_after_h2_ignored(self):
        # 본문 코드블록/섹션의 동명 라인은 헤더 종료 뒤라 무시된다(_header_loop_run_ids 와 동일 규약).
        c = "# X\nRisk Level: L3\n\n## 변경\n```\nDepth-Self-Review: performed\n```\n"
        self.assertEqual(hr._header_fields_06(c), ("L3", False))

    def test_case_insensitive_performed(self):
        c = "# X\nRisk Level: l2\nDepth-Self-Review: PERFORMED\n## S\n"
        self.assertEqual(hr._header_fields_06(c), ("L2", True))

    def test_fenced_marker_before_h2_not_declared(self):
        # 헤더 구간의 펜스 예시 안 `Depth-Self-Review: performed` 는 실제 선언이 아니다(오인 방지).
        c = "# X\nRisk Level: L2\n```\nDepth-Self-Review: performed\n```\n## S\n"
        self.assertEqual(hr._header_fields_06(c), ("L2", False))

    def test_performed_then_skipped_is_not_declared(self):
        # performed/skipped 상충 → 미선언(fail-closed). skipped 우회도 마찬가지.
        c = "# X\nRisk Level: L2\nDepth-Self-Review: performed\nDepth-Self-Review: skipped\n## S\n"
        self.assertEqual(hr._header_fields_06(c), ("L2", False))

    def test_mixed_fence_does_not_close_early(self):
        # ``` 안의 ~~~ 는 펜스를 닫지 못한다 — 혼합 펜스로 예시 선언을 실제 선언으로 우회 불가.
        c = "# X\nRisk Level: L2\n```\n~~~\nDepth-Self-Review: performed\n```\n## S\n"
        self.assertEqual(hr._header_fields_06(c), ("L2", False))

    def test_config_non_dict_writeback_is_off(self):
        # 손상 profile(writeback 비-dict)에 crash 대신 off 로 안전 degrade.
        self.assertEqual(hr._writeback_gate_config({"pdca": {"writeback": "oops"}}, ".")[0], "off")

    def test_config_non_dict_pdca_is_off(self):
        # pdca 자체가 비-dict 여도 crash 없이 off.
        self.assertEqual(hr._writeback_gate_config({"pdca": "x"}, ".")[0], "off")


class TestAuthoritativeCycleTier(unittest.TestCase):
    """writeback 게이트: tier 는 06 자기선언이 아니라 결속된 00 정본에서 온다(위조 L1 우회 봉쇄)."""

    def _mk(self, root, rel, body):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)

    def _prof(self):
        return {"pdca": {"phases": [{"id": "00", "glob": "plan_docs/00/*.md"},
                                     {"id": "06", "glob": "plan_docs/06/*.md"}]}}

    def test_doc_risk_tier_ignores_fenced_and_takes_max(self):
        self.assertEqual(hr._doc_risk_tier("Risk Level: L2\n```\nRisk Level: L3\n```\nRisk Level: L1\n"), "L2")
        self.assertIsNone(hr._doc_risk_tier("no risk here\n"))

    def test_doc_risk_tier_l0_no_crash(self):
        # L0 도 _RISK_LEVEL_RE 매치 — rank 에 없으면 KeyError 로 게이트가 조용히 죽는다(codex R4 P1).
        self.assertEqual(hr._doc_risk_tier("Risk Level: L0\nRisk Level: L2\n"), "L2")
        self.assertEqual(hr._doc_risk_tier("Risk Level: L0\n"), "L0")

    def test_doc_risk_tier_zero_width_prefixed_line_not_missed(self):
        # 제로폭/BOM 이 라인 앞에 껴도 Risk Level 선언을 놓치지 않는다(\s 가 Cf 를 안 잡아 under-read, codex R7 P1).
        self.assertEqual(hr._doc_risk_tier("Risk Level: L1\n﻿Risk Level: L3\n"), "L3")
        self.assertEqual(hr._doc_risk_tier("Risk Level: L1\n​Risk Level: L3\n"), "L3")

    def test_doc_risk_tier_header_only_ignores_body_prose(self):
        # 본문 산문/루브릭의 'Risk Level: L3' 를 tier 로 오독하지 않는다 — L1 사이클 false-BLOCK 방지(self-review P2).
        self.assertEqual(
            hr._doc_risk_tier("# B\nRisk Level: L1\n\n## Escalation\nrejected — Risk Level: L3\n"), "L1")

    def test_malformed_phases_item_no_crash(self):
        # bare 문자열 phase 항목(들여쓰기 실수) → ph.get() 크래시로 게이트 무력화 금지(self-review P1).
        prof = {"pdca": {"phases": ["00", {"id": "06", "glob": "plan_docs/06/*.md"}]}}
        self.assertEqual(hr._pdca_phase_glob(prof, "06"), "plan_docs/06/*.md")
        self.assertEqual(hr._pdca_phase_glob(prof, "00"), "")   # bare string skipped, no crash

    def test_overlapping_00_06_glob_06_not_its_own_authoritative_00(self):
        # 00/06 glob 겹침 misconfig 에서 06 이 자기 자신의 authoritative 00 이 돼 자기선언 Risk Level 이
        # 정본으로 부활하는 우회를 막는다 — 06 은 00 조회에서 제외(self-review P2).
        prof = {"pdca": {"phases": [{"id": "00", "glob": "plan_docs/*.md"},
                                     {"id": "06", "glob": "plan_docs/*.md"}]}}
        with tempfile.TemporaryDirectory() as root:
            self._mk(root, "plan_docs/cycle.md", "# R\nRisk Level: L1\n")   # the forging 06
            depth = hr._session_06_depth(root, prof, {"plan_docs/cycle.md"})
            self.assertIsNone(depth["plan_docs/cycle.md"][0])
            self.assertEqual(hr._reduce_06_depth(depth), (True, False))   # None → L2 → 우회 안 됨

    def test_l0_00_not_applies(self):
        with tempfile.TemporaryDirectory() as root:
            self._mk(root, "plan_docs/00/cycle.md", "# B\nCycle-Stem: `cycle`\nRisk Level: L0\n")
            self._mk(root, "plan_docs/06/cycle.md", "# R\nCycle-Stem: `cycle`\n")
            depth = hr._session_06_depth(root, self._prof(), {"plan_docs/06/cycle.md"})
            self.assertEqual(hr._reduce_06_depth(depth), (False, False))   # L0 → not applies, no crash

    def test_forged_cycle_stem_ignored_binds_by_path(self):
        # 결속은 06 의 경로 basename 으로만 한다 — 자기선언 Cycle-Stem 은 무시(위조 불가한 경로가 정본).
        # L3 사이클의 06(파일명 high.md)이 무관 L1 사이클(low)의 Cycle-Stem 을 선언해 우회하려 해도
        # path_stem='high' → 00/high(L3) 로 결속돼 BLOCK 축(applies)이 유지된다(codex R5 P1).
        with tempfile.TemporaryDirectory() as root:
            self._mk(root, "plan_docs/00/high.md", "# B\nCycle-Stem: `high`\nRisk Level: L3\n")
            self._mk(root, "plan_docs/00/low.md", "# B\nCycle-Stem: `low`\nRisk Level: L1\n")
            self._mk(root, "plan_docs/06/high.md", "# R\nCycle-Stem: `low`\nRisk Level: L1\n")  # 위조
            depth = hr._session_06_depth(root, self._prof(), {"plan_docs/06/high.md"})
            self.assertEqual(depth["plan_docs/06/high.md"][0], "L3")       # 경로 basename 이 정본
            self.assertEqual(hr._reduce_06_depth(depth), (True, False))    # 우회 안 됨

    def test_authoritative_tier_from_bound_00(self):
        with tempfile.TemporaryDirectory() as root:
            self._mk(root, "plan_docs/00/cycle.md", "# B\nCycle-Stem: `cycle`\nRisk Level: L3\n")
            self.assertEqual(hr._authoritative_cycle_tier(root, self._prof(), "cycle"), "L3")

    def test_forged_06_l1_resolves_to_authoritative_l3(self):
        with tempfile.TemporaryDirectory() as root:
            self._mk(root, "plan_docs/00/cycle.md", "# B\nCycle-Stem: `cycle`\nRisk Level: L3\n")
            self._mk(root, "plan_docs/06/cycle.md", "# R\nCycle-Stem: `cycle`\nRisk Level: L1\n")
            depth = hr._session_06_depth(root, self._prof(), {"plan_docs/06/cycle.md"})
            self.assertEqual(depth["plan_docs/06/cycle.md"][0], "L3")   # 06 위조 L1 무시
            self.assertEqual(hr._reduce_06_depth(depth), (True, False))  # applies

    def test_unreadable_or_tierless_same_stem_00_fails_closed(self):
        # 동일 stem 00 이 여럿일 때 하나라도 Risk Level 부재/모호(또는 읽기 실패)면 낮은 동거 tier 로
        # 확정하지 않고 None(→L2 applies)으로 fail-closed 한다 — malformed L3 + 동거 L1 우회 봉쇄(codex R6 P1).
        prof = {"pdca": {"phases": [{"id": "00", "glob": "plan_docs/00/**/*.md"},
                                     {"id": "06", "glob": "plan_docs/06/*.md"}]}}
        with tempfile.TemporaryDirectory() as root:
            self._mk(root, "plan_docs/00/a/cycle.md", "# 실제 L3 인데 Risk Level 라인 손상/부재\n")
            self._mk(root, "plan_docs/00/b/cycle.md", "# B\nRisk Level: L1\n")
            self._mk(root, "plan_docs/06/cycle.md", "# R\n")
            depth = hr._session_06_depth(root, prof, {"plan_docs/06/cycle.md"})
            self.assertIsNone(depth["plan_docs/06/cycle.md"][0])
            self.assertEqual(hr._reduce_06_depth(depth), (True, False))   # L1 로 우회 안 됨

    def test_no_bound_00_is_none_then_l2(self):
        with tempfile.TemporaryDirectory() as root:
            self._mk(root, "plan_docs/06/cycle.md", "# R\nCycle-Stem: `cycle`\n")
            depth = hr._session_06_depth(root, self._prof(), {"plan_docs/06/cycle.md"})
            self.assertIsNone(depth["plan_docs/06/cycle.md"][0])
            self.assertEqual(hr._reduce_06_depth(depth), (True, False))  # None → L2 → applies

    def test_genuine_l1_00_exempts(self):
        with tempfile.TemporaryDirectory() as root:
            self._mk(root, "plan_docs/00/cycle.md", "# B\nCycle-Stem: `cycle`\nRisk Level: L1\n")
            self._mk(root, "plan_docs/06/cycle.md", "# R\nCycle-Stem: `cycle`\n")
            depth = hr._session_06_depth(root, self._prof(), {"plan_docs/06/cycle.md"})
            self.assertEqual(hr._reduce_06_depth(depth), (False, False))  # L1 → not applies


class TestReduce06Depth(unittest.TestCase):
    """writeback_depth_gate 어댑터: 세션 06 별 (tier, declared) → (applies, declared) 축약."""

    def test_l2_declared(self):
        self.assertEqual(hr._reduce_06_depth({"06-a.md": ("L2", True)}), (True, True))

    def test_l2_undeclared(self):
        self.assertEqual(hr._reduce_06_depth({"06-a.md": ("L2", False)}), (True, False))

    def test_l1_excluded(self):
        # L1 은 얕은 노트가 정상 → 게이트 대상 아님(applies=False).
        self.assertEqual(hr._reduce_06_depth({"06-a.md": ("L1", False)}), (False, False))

    def test_unset_tier_treated_as_l2(self):
        # Risk Level 미기재 → 보수적으로 심층 대상(applies), 미선언이면 declared=False.
        self.assertEqual(hr._reduce_06_depth({"06-a.md": (None, False)}), (True, False))

    def test_multi_06_one_undeclared_not_declared(self):
        # 다중 L2/L3 06 중 하나라도 미선언이면 전체 미완료.
        self.assertEqual(
            hr._reduce_06_depth({"06-a.md": ("L2", True), "06-b.md": ("L3", False)}), (True, False))

    def test_multi_06_all_declared(self):
        self.assertEqual(
            hr._reduce_06_depth({"06-a.md": ("L2", True), "06-b.md": ("L3", True)}), (True, True))

    def test_l1_plus_l2_only_l2_counts(self):
        # L1 은 제외하고 L2 만 대상 — L2 가 선언되면 declared=True.
        self.assertEqual(
            hr._reduce_06_depth({"06-a.md": ("L1", False), "06-b.md": ("L2", True)}), (True, True))


class TestWritebackDepthGateResult(unittest.TestCase):
    """writeback_depth_gate_result 어댑터: degraded baseline fail-closed + 문구 보존."""

    def _prof(self):
        return {"pdca": {"writeback": {"depth_review_gate": "enforce"},
                         "phases": [{"id": "06", "glob": "p/06-*.md"}]},
                "knowledge_capture": {"update_after_dev": True, "vault_path": os.getcwd()}}

    def test_degraded_baseline_keeps_text_even_when_severity_equal(self):
        # logged L2 undeclared(이미 BLOCK) + corrupt baseline → severity 는 BLOCK 유지되지만
        # 'writer-독립 감지 불가' 문구가 리포트에서 사라지지 않아야 한다(감사 신호 보존).
        from unittest.mock import patch
        with patch.object(hr, "_session_06_depth", return_value={"06.md": ("L2", False)}):
            r = hr.writeback_depth_gate_result(self._prof(), ".", {"stop_hook_active": False},
                                               [{"file": "p/06-x.md"}], set(), "corrupt")
        self.assertEqual(r["severity"], "BLOCK")
        self.assertIn("writer-독립", r["text"])

    def test_degraded_baseline_no_06_still_fails_closed(self):
        # 06 전무여도 baseline 손상 + enforce → 놓친 Bash 06 가능성 → fail-closed BLOCK.
        from unittest.mock import patch
        with patch.object(hr, "_session_06_depth", return_value={}):
            r = hr.writeback_depth_gate_result(self._prof(), ".", {"stop_hook_active": False},
                                               [], set(), "absent")
        self.assertEqual(r["severity"], "BLOCK")


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

    def test_cycle_domain_strategy_receives_cycle_and_all_matched_domains(self):
        profile = {"risk": {
            "l3_review_strategy": "cycle_domain_review",
            "domains": [
                {"id": "auth", "path_globs": ["src/auth/**"], "content_keywords": []},
                {"id": "secret", "path_globs": [], "content_keywords": ["private_key"]},
            ],
        }}
        docs = [
            {"path": "r1.md", "content": "---\ncycle_stem: 141\nround: [1, 2]\ndomain_ref: auth\n---\n"},
            {"path": "r2.md", "content": "---\ncycle_stem: 141\nround: [1, 2]\ndomain_ref: secret\n---\n"},
        ]
        result = hr.run_strategy("pre-implementation-gate", profile, HOOKS_DIR,
                                 [{"path": "src/auth/x.py", "content": "private_key"}],
                                 {"branch": "issue/141"}, {"l3_review_docs": docs})
        self.assertTrue(result["found"])
        self.assertEqual(result["domains"], ["auth", "secret"])

    def test_cycle_domain_strategy_does_not_split_branch_numbers(self):
        profile = {"risk": {
            "l3_review_strategy": "cycle_domain_review",
            "domains": [{"id": "auth", "path_globs": ["src/auth/**"], "content_keywords": []}],
        }}
        stale = {"l3_review_docs": [{
            "path": "stale.md",
            "content": "---\ncycle_stem: 3\nround: [1, 2]\ndomain_ref: auth\n---\n",
        }]}
        result = hr.run_strategy("pre-implementation-gate", profile, HOOKS_DIR,
                                 [{"path": "src/auth/x.py", "content": ""}],
                                 {"branch": "feat/141-sd3"}, stale)
        self.assertFalse(result["found"])
        self.assertEqual(result["missing_domains"], ["auth"])

    def test_cycle_domain_strategy_exact_ticketless_stem_passes(self):
        profile = {"risk": {
            "l3_review_strategy": "cycle_domain_review",
            "domains": [{"id": "auth", "path_globs": ["src/auth/**"], "content_keywords": []}],
        }}
        docs = {"l3_review_docs": [{
            "path": "review.md",
            "content": "---\ncycle_stem: auth-hardening\nround: [1, 2]\ndomain_ref: auth\n---\n",
        }]}
        result = hr.run_strategy("pre-implementation-gate", profile, HOOKS_DIR,
                                 [{"path": "src/auth/x.py", "content": ""}],
                                 {"branch": "feat/auth-hardening"}, docs)
        self.assertTrue(result["found"])

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


class TestSessionLogEntries(unittest.TestCase):
    def test_non_object_json_line_skips_only_that_line(self):
        # 유효 JSON 이지만 object 가 아닌 라인(숫자·배열·문자열: 손상/동시쓰기/손편집)이 있어도
        # .get 이 터져 파일 뒤 라인이 통째로 유실되면 안 된다 — 그 라인만 건너뛰고 이후는 수집.
        import json
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "session-2026-07-19.jsonl")
            with open(fp, "w", encoding="utf-8") as f:
                for x in (json.dumps({"session": "S", "phase": "foo"}), "123", "[]", '"x"',
                          json.dumps({"session": "S", "phase": "bar"})):
                    f.write(x + "\n")
            got = [e.get("phase") for e in hr._session_log_entries(d, "S")]
        self.assertEqual(got, ["foo", "bar"])


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


sys.path.insert(0, HOOKS_DIR)   # cores 는 HOOKS_DIR 직속
import session_start_snapshot_core as sss_core   # noqa: E402


class TestSessionStartSnapshotCore(unittest.TestCase):
    """W2: SessionStart 06 baseline 스냅샷 결정(순수 core)."""

    def test_writes_when_no_existing_snapshot(self):
        d = sss_core.decide({"session_id": "s1", "now_utc": "2026-07-12T00:00:00Z"},
                            {"exists": False, "sha256": {"plan_docs/06-a.md": "h1"}})
        self.assertEqual(d["action"], "write")
        self.assertEqual(d["record"], {"session_id": "s1", "taken": "2026-07-12T00:00:00Z",
                                       "sha256": {"plan_docs/06-a.md": "h1"}})

    def test_noop_when_snapshot_exists(self):
        # write-once: 이미 baseline 있으면 안 덮는다(resume 시 초기 변경 유실 방지).
        d = sss_core.decide({"session_id": "s1", "now_utc": "t"}, {"exists": True, "sha256": {"x": "y"}})
        self.assertEqual(d, {"action": "noop", "record": None})

    def test_empty_sha_map_still_writes_baseline(self):
        # 06 이 아직 하나도 없어도 빈 baseline 을 남겨야 이후 신규 06 을 diff 로 잡는다.
        d = sss_core.decide({"session_id": "s1", "now_utc": "t"}, {"exists": False, "sha256": {}})
        self.assertEqual(d["action"], "write")
        self.assertEqual(d["record"]["sha256"], {})


class TestSnapshotChanged06(unittest.TestCase):
    """W2: baseline 대비 신규/변경된 06 정규 키 집합 + status(writer-독립 감지, degraded 표면화용)."""

    def _profile(self, root):
        # 게이트 활성이어야 SessionStart 가 스냅샷을 쓴다(비활성 프로젝트 IO 절약). usable vault(isdir) 필요.
        vault = os.path.join(root, "vault")
        os.makedirs(vault, exist_ok=True)
        return {"pdca": {"enabled": True, "phases": [{"id": "06", "glob": "plan_docs/06-*.md"}],
                         "retro": {"report_gate_enforce": "enforce"}},
                "knowledge_capture": {"retro_note": True, "vault_path": vault}}

    def _write06(self, root, name, text):
        os.makedirs(os.path.join(root, "plan_docs"), exist_ok=True)
        with open(os.path.join(root, "plan_docs", name), "w", encoding="utf-8") as f:
            f.write(text)

    def _snapshot(self, root, log_dir, session_id="s1"):
        import json
        prof_path = os.path.join(root, "profile.json")
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump(self._profile(root), f)
        old = os.environ.get("SAGE_PROFILE")
        os.environ["SAGE_PROFILE"] = prof_path
        try:
            hr.run_session_start_snapshot(io_claude, root, HOOKS_DIR, json.dumps({"session_id": session_id}))
        finally:
            os.environ.pop("SAGE_PROFILE", None) if old is None else os.environ.__setitem__("SAGE_PROFILE", old)

    def test_absent_snapshot_returns_absent_status(self):
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".claude", "logs")
            os.makedirs(log_dir, exist_ok=True)
            self._write06(root, "06-a.md", "x")
            self.assertEqual(hr._snapshot_changed_06(root, self._profile(root), log_dir, "s1"), ("absent", set()))

    def test_no_session_id_returns_no_session_status(self):
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".claude", "logs")
            os.makedirs(log_dir, exist_ok=True)
            self.assertEqual(hr._snapshot_changed_06(root, self._profile(root), log_dir, ""), ("no_session", set()))

    def test_new_and_changed_06_detected_unchanged_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".claude", "logs")
            os.makedirs(log_dir, exist_ok=True)
            self._write06(root, "06-old.md", "orig")     # baseline 에 포함될 파일
            self._snapshot(root, log_dir)                # SessionStart baseline(현재 상태)
            self._write06(root, "06-old.md", "MUTATED")  # 내용 변경
            self._write06(root, "06-new.md", "brand new") # 신규
            status, changed = hr._snapshot_changed_06(root, self._profile(root), log_dir, "s1")
            self.assertEqual(status, "ok")
            self.assertEqual(changed, {"plan_docs/06-old.md", "plan_docs/06-new.md"})

    def test_user_prompt_submit_backfills_missing_session_start_snapshot(self):
        # Codex SessionStart 가 누락/지연돼도 첫 UserPromptSubmit 은 agent 작업 전에 도착한다.
        # capture-declared-risk 경로가 같은 write-once baseline 을 확보해야 Stop 이 false-block 하지 않는다.
        import json
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".codex", "logs")
            os.makedirs(log_dir, exist_ok=True)
            prof_path = os.path.join(root, "profile.json")
            profile = self._profile(root)
            with open(prof_path, "w", encoding="utf-8") as f:
                json.dump(profile, f)
            old = os.environ.get("SAGE_PROFILE")
            os.environ["SAGE_PROFILE"] = prof_path
            try:
                hr.run_capture_declared_risk(
                    io_codex,
                    root,
                    HOOKS_DIR,
                    json.dumps({"session_id": "s1", "prompt": "코드 리뷰 해줘"}),
                )
                self.assertEqual(
                    hr._snapshot_changed_06(root, profile, log_dir, "s1"), ("ok", set()))
                self._write06(root, "06-new.md", "brand new")
                hr.run_capture_declared_risk(
                    io_codex,
                    root,
                    HOOKS_DIR,
                    json.dumps({"session_id": "s1", "prompt": "계속 진행해줘"}),
                )
            finally:
                os.environ.pop("SAGE_PROFILE", None) if old is None else os.environ.__setitem__(
                    "SAGE_PROFILE", old)

            self.assertEqual(
                hr._snapshot_changed_06(root, profile, log_dir, "s1"),
                ("ok", {"plan_docs/06-new.md"}),
            )
            self.assertTrue(os.path.exists(hr._snapshot_claim_path(log_dir, "s1")))

    def test_first_inactive_prompt_prevents_late_baseline_after_gate_activation(self):
        # 첫 prompt 때 게이트가 비활성이면 snapshot은 만들지 않되 기회는 소비한다. 이후 설정이 활성화돼도
        # 이미 06 변경이 일어난 뒤 늦은 baseline을 만들면 false-pass이므로 absent를 유지해야 한다.
        import json
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".codex", "logs")
            os.makedirs(log_dir, exist_ok=True)
            prof_path = os.path.join(root, "profile.json")
            inactive = self._profile(root)
            inactive["pdca"]["retro"]["report_gate_enforce"] = "off"
            with open(prof_path, "w", encoding="utf-8") as f:
                json.dump(inactive, f)
            old = os.environ.get("SAGE_PROFILE")
            os.environ["SAGE_PROFILE"] = prof_path
            try:
                hr.run_capture_declared_risk(
                    io_codex,
                    root,
                    HOOKS_DIR,
                    json.dumps({"session_id": "s1", "prompt": "첫 요청"}),
                )
                self.assertEqual(
                    hr._snapshot_changed_06(root, inactive, log_dir, "s1"), ("absent", set()))
                self._write06(root, "06-late.md", "already changed")
                active = self._profile(root)
                with open(prof_path, "w", encoding="utf-8") as f:
                    json.dump(active, f)
                hr.run_capture_declared_risk(
                    io_codex,
                    root,
                    HOOKS_DIR,
                    json.dumps({"session_id": "s1", "prompt": "다음 요청"}),
                )
            finally:
                os.environ.pop("SAGE_PROFILE", None) if old is None else os.environ.__setitem__(
                    "SAGE_PROFILE", old)

            self.assertTrue(os.path.exists(hr._snapshot_claim_path(log_dir, "s1")))
            self.assertEqual(
                hr._snapshot_changed_06(root, active, log_dir, "s1"), ("absent", set()))

    def test_snapshot_opportunity_claim_has_exactly_one_concurrent_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".codex", "logs")
            with ThreadPoolExecutor(max_workers=8) as pool:
                won = list(pool.map(
                    lambda _i: hr._claim_snapshot_opportunity(log_dir, "s1"),
                    range(24),
                ))

            self.assertEqual(sum(won), 1)
            self.assertTrue(os.path.exists(hr._snapshot_claim_path(log_dir, "s1")))

    def test_corrupt_snapshot_returns_corrupt_status(self):
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".claude", "logs")
            os.makedirs(log_dir, exist_ok=True)
            with open(hr._snapshot_path(log_dir, "s1"), "w", encoding="utf-8") as f:
                f.write('{"sha256": {tr')   # 잘린 JSON
            self.assertEqual(hr._snapshot_changed_06(root, self._profile(root), log_dir, "s1"), ("corrupt", set()))

    def test_valid_json_nondict_sha256_is_corrupt_not_crash(self):
        # codex R2 P1: 유효 JSON 이지만 sha256 이 dict 가 아니면(문자열 등) base.get() 이 던지기 전에
        # corrupt 로 분류해야 한다 — 이 함수는 게이트 try 밖에서 불려 예외가 Stop 세션을 죽인다.
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".claude", "logs")
            os.makedirs(log_dir, exist_ok=True)
            with open(hr._snapshot_path(log_dir, "s1"), "w", encoding="utf-8") as f:
                f.write('{"sha256": "not-a-map"}')
            self.assertEqual(hr._snapshot_changed_06(root, self._profile(root), log_dir, "s1"), ("corrupt", set()))

    def test_snapshot_symlink_is_corrupt_and_never_trusted(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".claude", "logs")
            os.makedirs(log_dir, exist_ok=True)
            target = os.path.join(root, "attacker.json")
            with open(target, "w", encoding="utf-8") as f:
                json.dump({"sha256": {}}, f)
            os.symlink(target, hr._snapshot_path(log_dir, "s1"))

            self.assertEqual(
                hr._snapshot_changed_06(root, self._profile(root), log_dir, "s1"),
                ("corrupt", set()),
            )

    def test_snapshot_publish_is_create_once(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "session-snapshot-s1.json")
            original = {"session_id": "existing", "sha256": {"06.md": "old"}}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(original, f)

            self.assertFalse(hr._publish_snapshot_create_once(
                path, {"session_id": "replacement", "sha256": {}}))
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f), original)

    def test_snapshot_publish_falls_back_when_hardlinks_are_unsupported(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "session-snapshot-s1.json")
            record = {"session_id": "s1", "sha256": {"06.md": "hash"}}
            unsupported = OSError(errno.EOPNOTSUPP, "hard links unsupported")

            with mock.patch.object(hr.os, "link", side_effect=unsupported):
                self.assertTrue(hr._publish_snapshot_create_once(path, record))

            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f), record)

    def test_claim_creation_error_blocks_user_prompt_fallback(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.object(hr, "_claim_snapshot_opportunity", return_value=None):
                rc = hr.run_capture_declared_risk(
                    io_codex,
                    root,
                    HOOKS_DIR,
                    json.dumps({"session_id": "s1", "prompt": "첫 요청"}),
                )

            self.assertEqual(rc, 2)

    def test_claim_open_error_is_not_treated_as_existing_claim(self):
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".codex", "logs")
            with mock.patch.object(
                    hr.os, "open", side_effect=PermissionError(errno.EACCES, "denied")):
                self.assertIsNone(hr._claim_snapshot_opportunity(log_dir, "s1"))

    def test_user_prompt_does_not_replace_dangling_snapshot_symlink(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".codex", "logs")
            os.makedirs(log_dir, exist_ok=True)
            path = hr._snapshot_path(log_dir, "s1")
            missing_target = os.path.join(root, "missing-attacker.json")
            os.symlink(missing_target, path)

            prof_path = os.path.join(root, "profile.json")
            profile = self._profile(root)
            with open(prof_path, "w", encoding="utf-8") as f:
                json.dump(profile, f)
            old = os.environ.get("SAGE_PROFILE")
            os.environ["SAGE_PROFILE"] = prof_path
            try:
                hr.run_capture_declared_risk(
                    io_codex,
                    root,
                    HOOKS_DIR,
                    json.dumps({"session_id": "s1", "prompt": "첫 요청"}),
                )
            finally:
                os.environ.pop("SAGE_PROFILE", None) if old is None else os.environ.__setitem__(
                    "SAGE_PROFILE", old)

            self.assertTrue(os.path.islink(path))
            self.assertFalse(os.path.exists(missing_target))
            self.assertEqual(
                hr._snapshot_changed_06(root, profile, log_dir, "s1"),
                ("corrupt", set()),
            )

    def test_ttl_cleanup_preserves_current_session(self):
        # codex R2 P1: TTL 초과여도 이번 세션 baseline 은 지우지 않는다(장수 세션이 자기 baseline 을 잃지 않게).
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".claude", "logs")
            os.makedirs(log_dir, exist_ok=True)
            cur = hr._snapshot_path(log_dir, "s1")
            claim = hr._snapshot_claim_path(log_dir, "s1")
            old = hr._snapshot_path(log_dir, "s-old")
            for p in (cur, claim, old):
                with open(p, "w", encoding="utf-8") as f:
                    f.write("{}")
            stale = time.time() - (hr._SNAPSHOT_TTL_SECONDS + 3600)
            for p in (cur, claim, old):
                os.utime(p, (stale, stale))
            hr._cleanup_old_snapshots(log_dir, keep_paths=(cur, claim))
            self.assertTrue(os.path.exists(cur), "이번 세션 baseline 은 보존")
            self.assertTrue(os.path.exists(claim), "이번 세션 first-opportunity claim 은 보존")
            self.assertFalse(os.path.exists(old), "다른 세션 오래된 baseline 은 삭제")

    def test_ttl_cleanup_preserves_claimed_resumable_session(self):
        # 다른 세션이 14일 지난 claim+baseline을 지우면 resume 시 늦은 baseline을 만들 수 있다.
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".claude", "logs")
            os.makedirs(log_dir, exist_ok=True)
            old = hr._snapshot_path(log_dir, "s-old")
            old_claim = hr._snapshot_claim_path(log_dir, "s-old")
            for p in (old, old_claim):
                with open(p, "w", encoding="utf-8") as f:
                    f.write("{}")
                stale = time.time() - (hr._SNAPSHOT_TTL_SECONDS + 3600)
                os.utime(p, (stale, stale))

            hr._cleanup_old_snapshots(log_dir)

            self.assertTrue(os.path.exists(old))
            self.assertTrue(os.path.exists(old_claim))

    def test_unresolved_claim_blocks_instead_of_silently_proceeding(self):
        # codex 리뷰: winner 가 claim 만 하고(O_EXCL 성공) resolved 마킹 전에 죽으면(중단/크래시),
        # loser 가 "누가 이미 claim 했으니 안전"으로 착각해 조용히 진행하면 안 된다 — 그 사이 agent 가
        # 06 을 바꿔도 winner 가 뒤늦게 게시하는 baseline 이 이미 바뀐 상태를 흡수할 수 있다.
        import json
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".codex", "logs")
            os.makedirs(log_dir, exist_ok=True)
            claim = hr._snapshot_claim_path(log_dir, "s1")
            with open(claim, "w", encoding="utf-8") as f:
                json.dump({"session_id": "s1", "claimed_at": "t"}, f)   # resolved 없음 = 미해결

            rc = hr._ensure_session_06_snapshot(
                io_codex, root, HOOKS_DIR, json.dumps({"session_id": "s1", "prompt": "p"}))

            self.assertEqual(rc, 2)
            self.assertFalse(os.path.exists(hr._snapshot_path(log_dir, "s1")))

    def test_resolved_noop_claim_lets_loser_proceed(self):
        # 첫 시도가 게이트 비활성으로 noop 확정되면, 대기 중이던 loser 는 매 prompt 마다 막히지 않고
        # 정상 진행해야 한다(steady-state 게이트-비활성 세션이 영구 차단되면 안 됨).
        import json
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".codex", "logs")
            os.makedirs(log_dir, exist_ok=True)
            claim = hr._snapshot_claim_path(log_dir, "s1")
            with open(claim, "w", encoding="utf-8") as f:
                json.dump({"session_id": "s1", "resolved": "noop"}, f)

            rc = hr._ensure_session_06_snapshot(
                io_codex, root, HOOKS_DIR, json.dumps({"session_id": "s1", "prompt": "p"}))

            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(hr._snapshot_path(log_dir, "s1")))

    def test_malformed_truthy_resolved_claim_still_blocks(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".codex", "logs")
            os.makedirs(log_dir, exist_ok=True)
            claim = hr._snapshot_claim_path(log_dir, "s1")
            for malformed in ("pending", True, 1):
                with open(claim, "w", encoding="utf-8") as f:
                    json.dump({"session_id": "s1", "resolved": malformed}, f)
                rc = hr._ensure_session_06_snapshot(
                    io_codex, root, HOOKS_DIR, json.dumps({"session_id": "s1", "prompt": "p"}))
                self.assertEqual(rc, 2, malformed)

    def test_resolved_claim_from_different_session_id_still_blocks(self):
        # 파일명 정규화 충돌(다른 session_id 가 같은 claim 경로로 접힘)로 남의 resolved 마커를 내
        # 세션의 완료 신호로 오인하면 안 된다.
        import json
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".codex", "logs")
            os.makedirs(log_dir, exist_ok=True)
            claim = hr._snapshot_claim_path(log_dir, "s1")
            with open(claim, "w", encoding="utf-8") as f:
                json.dump({"session_id": "some-other-session", "resolved": "noop"}, f)

            rc = hr._ensure_session_06_snapshot(
                io_codex, root, HOOKS_DIR, json.dumps({"session_id": "s1", "prompt": "p"}))

            self.assertEqual(rc, 2)

    def test_snapshot_session_id_mismatch_is_treated_as_corrupt(self):
        # 파일명 정규화(sanitize+truncate)로 다른 session_id 가 같은 경로에 접히거나 잔여파일이
        # 재사용되는 상황에서, 내용의 session_id 가 다르면 남의 baseline 을 "ok"로 신뢰하면 안 된다.
        import json
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".claude", "logs")
            os.makedirs(log_dir, exist_ok=True)
            with open(hr._snapshot_path(log_dir, "s1"), "w", encoding="utf-8") as f:
                json.dump({"session_id": "s2", "taken": "t", "sha256": {}}, f)

            self.assertEqual(
                hr._snapshot_changed_06(root, self._profile(root), log_dir, "s1"),
                ("corrupt", set()))

    def test_existing_baseline_from_different_session_blocks_before_agent_work(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".codex", "logs")
            os.makedirs(log_dir, exist_ok=True)
            path = hr._snapshot_path(log_dir, "s1")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"session_id": "other", "taken": "t", "sha256": {}}, f)

            rc = hr._ensure_session_06_snapshot(
                io_codex, root, HOOKS_DIR, json.dumps({"session_id": "s1", "prompt": "p"}))

            self.assertEqual(rc, 2)
            self.assertFalse(os.path.exists(hr._snapshot_claim_path(log_dir, "s1")))

    def test_publish_race_with_mismatched_baseline_keeps_claim_unresolved_and_blocks(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            log_dir = os.path.join(root, ".codex", "logs")
            os.makedirs(log_dir, exist_ok=True)
            prof_path = os.path.join(root, "profile.json")
            with open(prof_path, "w", encoding="utf-8") as f:
                json.dump(self._profile(root), f)
            path = hr._snapshot_path(log_dir, "s1")

            def lose_publish_race(_path, _record):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"session_id": "other", "taken": "t", "sha256": {}}, f)
                return False

            old = os.environ.get("SAGE_PROFILE")
            os.environ["SAGE_PROFILE"] = prof_path
            try:
                with mock.patch.object(hr, "_publish_snapshot_create_once",
                                       side_effect=lose_publish_race):
                    rc = hr._ensure_session_06_snapshot(
                        io_codex, root, HOOKS_DIR,
                        json.dumps({"session_id": "s1", "prompt": "p"}))
            finally:
                os.environ.pop("SAGE_PROFILE", None) if old is None else os.environ.__setitem__(
                    "SAGE_PROFILE", old)

            claim = hr._snapshot_claim_path(log_dir, "s1")
            self.assertEqual(rc, 2)
            self.assertFalse(hr._snapshot_opportunity_resolved(claim, "s1"))

    def test_off_mode_stop_does_not_hash_06(self):
        # codex R2 P2: mode=off 면 Stop 이 06 을 해싱하지 않는다(_snapshot_changed_06 미호출).
        import json
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".claude", "logs"), exist_ok=True)
            log_dir = os.path.join(root, ".claude", "logs")
            with open(os.path.join(log_dir, "session-2026-06-13.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"ts": "t", "tool": "Write", "file": "a.src", "type": "src",
                                    "branch": "m", "session": "s1"}) + "\n")
            prof = {"pdca": {"phases": [{"id": "06", "glob": "plan_docs/06-*.md"}],
                             "retro": {"report_gate_enforce": "off"}}}   # 게이트 off
            prof_path = os.path.join(root, "profile.json")
            with open(prof_path, "w", encoding="utf-8") as f:
                json.dump(prof, f)
            orig = hr._hash_06_glob
            hr._hash_06_glob = lambda *a, **k: (_ for _ in ()).throw(AssertionError("off 인데 06 해싱함"))
            env_keys = {"SAGE_PROFILE": prof_path, "SAGE_TODAY": "2026-06-13", "SAGE_GATE_BRANCH": "m"}
            saved = {k: os.environ.get(k) for k in env_keys}
            os.environ.update(env_keys)
            try:
                rc = hr.run_stop_compliance_report(io_claude, root, HOOKS_DIR,
                                                   json.dumps({"session_id": "s1"}))
                self.assertEqual(rc, 0)   # 해싱 안 하고 정상 종료
            finally:
                hr._hash_06_glob = orig
                for k, v in saved.items():
                    os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


class TestSessionStartOverlayL1(unittest.TestCase):
    """SessionStart L1 — 오버레이 블록 재수렴(편의 레이어). 앵커 미기록·수렴·fail-open·(c) 차단."""

    def _base_renders(self, dest):
        for aid in ["leader", "implementer-a", "implementer-b", "qa", "reviewer", "convention-checker"]:
            p = os.path.join(dest, ".claude", "agents", f"{aid}.md")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"# {aid}\nCORE body.\n")
        p = os.path.join(dest, "AGENT_GUIDE.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# AGENT_GUIDE\nnon-negotiable.\n")

    def _overlay(self, dest, kind, id, text):
        d = os.path.join(dest, "sage", "asset_overrides", kind)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{id}.md"), "w", encoding="utf-8") as f:
            f.write(text)

    def _codex_skill_and_manifest(self, dest, scope):
        import json
        skill = os.path.join(dest, ".codex", "skills", "sage-team", "SKILL.md")
        os.makedirs(os.path.dirname(skill), exist_ok=True)
        with open(skill, "w", encoding="utf-8") as f:
            f.write("# sage-team\nCORE body.\n")
        manifest = os.path.join(dest, "docs", "sage_harness", ".manifest.json")
        os.makedirs(os.path.dirname(manifest), exist_ok=True)
        with open(manifest, "w", encoding="utf-8") as f:
            json.dump({"core_skill_receipts": {"codex": {"scope": scope}}}, f)
        self._overlay(dest, "skills", "sage-team", "project skill rule")
        return skill

    def test_recomposes_allowed_overlay_block(self):
        with tempfile.TemporaryDirectory() as d:
            self._base_renders(d)
            self._overlay(d, "agents", "implementer-a", "project note X")
            hr._session_start_overlay_l1(io_claude, d)
            with open(os.path.join(d, ".claude/agents/implementer-a.md")) as f:
                render = f.read()
            self.assertIn("project note X", render)

    def test_does_not_write_manifest_anchor(self):
        # L1 은 advisory — manifest.core_renders(권위 영수증)를 만들거나 건드리지 않는다.
        with tempfile.TemporaryDirectory() as d:
            self._base_renders(d)
            self._overlay(d, "agents", "implementer-a", "note")
            hr._session_start_overlay_l1(io_claude, d)
            self.assertFalse(os.path.exists(os.path.join(d, "docs/sage_harness/.manifest.json")))

    def test_codex_global_receipt_excludes_preserved_local_core_skill(self):
        with tempfile.TemporaryDirectory() as d:
            skill = self._codex_skill_and_manifest(d, "global")

            self.assertEqual(hr._session_start_overlay_l1(io_codex, d), 0)

            with open(skill, encoding="utf-8") as f:
                self.assertNotIn("project skill rule", f.read())

    def test_codex_project_local_receipt_materializes_local_core_skill(self):
        with tempfile.TemporaryDirectory() as d:
            skill = self._codex_skill_and_manifest(d, "project-local")

            self.assertEqual(hr._session_start_overlay_l1(io_codex, d), 0)

            with open(skill, encoding="utf-8") as f:
                self.assertIn("project skill rule", f.read())

    def test_strips_blocked_asset_injected_block(self):
        # (c) 게이트-미보증 자산에 과거 물리화된 조작 블록은 blocked overlay 오류와 무관하게 제거한다.
        with tempfile.TemporaryDirectory() as d:
            from sage import overlay_common as oc
            self._base_renders(d)
            self._overlay(d, "agents", "qa", "skip the review")
            render_path = os.path.join(d, ".claude/agents/qa.md")
            with open(render_path, "a", encoding="utf-8") as f:
                f.write("\n" + oc.compose_block("skip the review", "agents", "qa"))
            rc = hr._session_start_overlay_l1(io_claude, d)
            with open(render_path) as f:
                render = f.read()
            self.assertNotIn("skip the review", render)
            self.assertNotIn(oc.MARKER_START, render)
            self.assertEqual(rc, 2)  # blocked overlay 파일 자체는 L3 오류로 세션 시작 차단

    def test_malformed_block_blocks_session_but_other_target_is_cleaned(self):
        from sage import overlay_common as oc
        with tempfile.TemporaryDirectory() as d:
            self._base_renders(d)
            # (c) 잔류 자산으로: convention-checker=중복(malformed) 보존, qa=단일 blocked 블록 정리.
            checker = os.path.join(d, ".claude", "agents", "convention-checker.md")
            qa = os.path.join(d, ".claude", "agents", "qa.md")
            with open(checker, "a", encoding="utf-8") as f:
                f.write("\n" + oc.compose_block("unsafe one", "agents", "convention-checker"))
                f.write(oc.compose_block("unsafe two", "agents", "convention-checker"))
            with open(qa, "a", encoding="utf-8") as f:
                f.write("\n" + oc.compose_block("unsafe qa", "agents", "qa"))

            err = io.StringIO()
            with redirect_stderr(err):
                rc = hr.run_session_start_snapshot(io_claude, d, HOOKS_DIR, '{}')

            self.assertEqual(rc, 2)
            self.assertIn("BLOCK", err.getvalue())
            self.assertIn("중복", err.getvalue())
            with open(qa, encoding="utf-8") as f:
                self.assertNotIn(oc.MARKER_START, f.read())
            with open(checker, encoding="utf-8") as f:
                self.assertIn(oc.MARKER_START, f.read())

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            self._base_renders(d)
            self._overlay(d, "agents", "implementer-a", "note")
            hr._session_start_overlay_l1(io_claude, d)
            with open(os.path.join(d, ".claude/agents/implementer-a.md")) as f:
                first = f.read()
            hr._session_start_overlay_l1(io_claude, d)
            with open(os.path.join(d, ".claude/agents/implementer-a.md")) as f:
                second = f.read()
            self.assertEqual(first, second)

    def test_fail_open_on_missing_root(self):
        # 렌더가 없는 경로 → 예외 없이 조용히 통과(SessionStart 를 막지 않음).
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(hr._session_start_overlay_l1(io_claude, os.path.join(d, "nonexistent")), 0)

    def test_fail_open_when_sage_unimportable(self):
        # sage 패키지 import 실패를 시뮬레이션 → skip, 예외 없음.
        import builtins
        real_import = builtins.__import__

        def _blocked_import(name, *a, **k):
            if name == "sage.overlay_materialize" or name == "sage":
                raise ImportError("simulated")
            return real_import(name, *a, **k)

        builtins.__import__ = _blocked_import
        try:
            hr._session_start_overlay_l1(io_claude, "/tmp")
        finally:
            builtins.__import__ = real_import


if __name__ == "__main__":
    unittest.main(verbosity=2)
