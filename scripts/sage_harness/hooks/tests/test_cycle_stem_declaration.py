#!/usr/bin/env python3
"""EH-7 — 장수 브랜치 cycle stem 해석: 안내 정확성 + 선언 통로 감사.

배경(ChatForYou 실측): 사이클마다 브랜치를 따지 않는 장수 브랜치에서는 비-phase 편집의 stem 이
브랜치 leaf 에서 추론되어 실제 사이클과 영영 어긋난다. 00~03 문서가 전부 있는데도 "의무 PDCA
phase 미작성" BLOCK 이 걸리고, 안내는 "문서를 작성하세요" 라 방향이 틀렸다. 탈출구인
SAGE_CYCLE_STEM 은 문서에도 출력에도 없었고, 그 선언이 게이트를 통과시킨 사실도 남지 않았다.

여기서 못박는 것:
  1. 추론(branch-leaf) BLOCK 은 추론 사실과 선언 경로를 안내한다 — 경로 유래 stem 에는 오안내 없음
  2. 선언하면 같은 스냅샷이 통과한다(게이트를 끄는 게 아니라 올바른 사이클을 주는 것)
  3. 선언된 stem 은 판정에 스탬프되고, OK 줄에도 노출된다(낡은 선언이 보이게)
  4. 선언 사용은 .sage/override.jsonl 에 세션·stem 단위 1회 기록되며, 기록 실패 시 통과 금지
"""
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
import io as _io
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
RUNTIME = os.path.join(HOOKS_DIR, "runtime")
sys.path.insert(0, RUNTIME)
sys.path.insert(0, HOOKS_DIR)
import pre_implementation_gate_core as core   # noqa: E402
import messages                               # noqa: E402


# 권한 캐시가 저장소 밖 상태 디렉터리로 옮겨졌다(10-e). 격리하지 않으면 테스트가 개발자의 실제
# ~/.local/state/sage 를 오염시킨다. 파일 전체에 강제한다.
_STATE_TMP = None


def setUpModule():
    global _STATE_TMP
    _STATE_TMP = tempfile.TemporaryDirectory()
    os.environ["SAGE_STATE_HOME"] = _STATE_TMP.name


def tearDownModule():
    os.environ.pop("SAGE_STATE_HOME", None)
    _STATE_TMP.cleanup()

import override_audit as ov                   # noqa: E402
import hook_runtime as hr                     # noqa: E402

GATE = "pre-implementation-gate"
LONG_BRANCH = "chatforyou_v2_sage"
REAL_STEM = "sage_project_profile_refresh"

PDCA_PROFILE = {
    "risk": {"l0_pass_globs": ["*plan_docs/*", "*.md"], "l2_path_globs": ["*backend/*.java"]},
    "pdca": {
        "enabled": True,
        "phases": [{"id": pid, "glob": f"plan_docs/{pid}-x/**/*.md"} for pid in
                   ("00", "01", "02", "03")],
        "pre_implementation_required": {"L2": ["00", "01", "02", "03"]},
    },
}


def _pdoc(stem, risk=""):
    risk_line = f"Risk Level: {risk}\n" if risk else ""
    return {"path": f"{stem}.md",
            "content": f"Cycle-Stem: `{stem}`\n{risk_line}", "recent": True}


def _complete_snapshot(stem):
    """실제 사이클 stem 으로 00~03 이 모두 갖춰진 스냅샷 — 결핍이 아닌 상태."""
    return {"plan_files": [_pdoc(stem)], "review_candidates": [],
            "phase_docs": {
                "00": [_pdoc(stem, risk="L2")],
                "01": [_pdoc(stem)],
                "02": [_pdoc(stem)],
                "03": [_pdoc(stem)],
            }}


def _event(cycle_stem="", branch=LONG_BRANCH, path="backend/App.java", origin="env"):
    # origin 은 어댑터가 싣는다 — 선언 통로가 둘(env / .sage/cycle.json)이라 표시·감사가
    # 어느 쪽을 읽었는지 갈라 말하려면 stem 만으로는 부족하다.
    return {"hook_id": GATE, "runtime": "test", "branch": branch, "session_id": "sess-1",
            "cycle_stem": cycle_stem, "cycle_stem_origin": origin if cycle_stem else "",
            "declared_max": None,
            "changes": [{"path": path, "op": "write", "content": "x"}]}


class TestLongLivedBranchMisbinding(unittest.TestCase):
    """장수 브랜치에서 문서가 다 있는데도 막히는 상태를 재현하고, 안내가 맞는지 본다."""

    def test_complete_cycle_still_blocks_when_stem_is_inferred_from_branch(self):
        d = core.decide(_event(), PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        self.assertEqual(d["message_key"], "block_cycle_risk_declaration")
        # 판정은 그대로지만 출처는 이제 밖으로 나온다 — 이게 오안내를 고칠 재료다.
        self.assertEqual(d["cycle_source"], ["branch-leaf"])
        self.assertEqual(d["cycle_stem"], LONG_BRANCH)
        self.assertFalse(d["cycle_stem_declared"])

    def test_declaring_the_real_stem_passes_the_same_snapshot(self):
        d = core.decide(_event(cycle_stem=REAL_STEM), PDCA_PROFILE,
                        _complete_snapshot(REAL_STEM), None)
        self.assertEqual(d["message_key"], "ok_l2")
        self.assertEqual(d["exit_code"], 0)
        self.assertEqual(d["cycle_stem"], REAL_STEM)
        self.assertTrue(d["cycle_stem_declared"])
        self.assertEqual(d["cycle_source"], ["event"])

    def test_phase_write_binds_from_path_not_branch(self):
        # phase 문서 편집은 경로에서 stem 을 얻는다(위조 불가) — 브랜치는 신호가 아니다.
        event = {"hook_id": GATE, "branch": LONG_BRANCH, "session_id": "s",
                 "changes": [{"path": f"plan_docs/01-x/{REAL_STEM}.md", "op": "write",
                              "content": f"Cycle-Stem: `{REAL_STEM}`\n"}]}
        d = core.decide(event, PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        self.assertEqual(d["cycle_stem"], REAL_STEM)
        self.assertEqual(d["cycle_source"], [f"plan_docs/01-x/{REAL_STEM}.md"])

    def test_pdca_disabled_is_not_stamped(self):
        d = core.decide(_event(), {"risk": {"l2_paths": ["**/*.java"]}}, {}, None)
        self.assertNotIn("cycle_stem", d)
        self.assertNotIn("cycle_stem_declared", d)


class TestHintPointsAtTheRealEscape(unittest.TestCase):
    """차단 안내가 원인에 맞는 탈출구를 가리키는지. 오안내는 없는 문서를 다시 쓰게 만든다."""

    def _render(self, decision):
        return messages.gate_text(decision, {}, "claude")

    def test_inferred_stem_block_names_declaration_and_the_inferred_leaf(self):
        d = core.decide(_event(), PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        text = self._render(d)
        self.assertIn("SAGE_CYCLE_STEM", text)
        self.assertIn(LONG_BRANCH, text)          # 무엇으로 추론했는지 보여야 함
        self.assertIn("추론", text)

    def test_path_bound_stem_block_does_not_suggest_declaration(self):
        # 경로에서 stem 을 얻은 결핍은 진짜 문서 부재다 — 여기서 선언을 권하면 우회를 가르치는 셈이다.
        docs = {"00": [_pdoc(REAL_STEM, risk="L2")]}
        event = {"hook_id": GATE, "branch": LONG_BRANCH, "session_id": "s",
                 "changes": [{"path": f"plan_docs/00-x/{REAL_STEM}.md", "op": "write",
                              "content": f"Cycle-Stem: `{REAL_STEM}`\n"},
                             {"path": "backend/App.java", "op": "write", "content": "x"}]}
        d = core.decide(event, PDCA_PROFILE,
                        {"plan_files": [], "review_candidates": [], "phase_docs": docs}, None)
        self.assertEqual(d["message_key"], "block_phase_incomplete")
        text = self._render(d)
        self.assertNotIn("SAGE_CYCLE_STEM", text)
        self.assertIn("pdca-templates.md", text)

    def test_binding_failure_on_non_phase_edit_offers_declaration(self):
        # 브랜치 leaf 조차 못 쓰는 상태(브랜치 없음) → "파일명을 맞추라" 만으로는 나갈 길이 없다.
        event = dict(_event(), branch="")
        d = core.decide(event, PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        self.assertEqual(d["message_key"], "block_cycle_binding")
        self.assertIn("SAGE_CYCLE_STEM", self._render(d))

    def test_declared_stem_is_visible_on_pass(self):
        d = core.decide(_event(cycle_stem=REAL_STEM), PDCA_PROFILE,
                        _complete_snapshot(REAL_STEM), None)
        text = self._render(d)
        self.assertIn(REAL_STEM, text)
        self.assertIn("SAGE_CYCLE_STEM 선언", text)

    def test_file_declaration_is_labelled_as_the_file_not_the_env(self):
        # 통로가 둘이므로 "선언" 으로 뭉치면 안 된다 — 읽은 자리를 그대로 적는다.
        d = core.decide(_event(cycle_stem=REAL_STEM, origin="cli"), PDCA_PROFILE,
                        _complete_snapshot(REAL_STEM), None)
        text = self._render(d)
        self.assertIn(".sage/cycle.json 선언", text)
        self.assertNotIn("SAGE_CYCLE_STEM 선언", text)

    def test_both_runtimes_carry_the_same_guidance(self):
        d = core.decide(_event(), PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        for runtime in ("claude", "codex"):
            self.assertIn("SAGE_CYCLE_STEM", messages.gate_text(d, {}, runtime), runtime)


CLOSED_STEM = "sage_finished_cycle"

CLOSED_PROFILE = {
    "risk": {"l0_pass_globs": ["*plan_docs/*", "*.md"], "l2_path_globs": ["*backend/*.java"]},
    "pdca": {
        "enabled": True,
        "phases": [{"id": pid, "glob": f"plan_docs/{pid}-x/**/*.md"} for pid in
                   ("00", "01", "02", "03", "04", "05", "06")],
        "pre_implementation_required": {"L2": ["00", "01", "02", "03"]},
        "report_phase": "06",
        "approve_phase": "05",
        "approve_marker": "APPROVED",
    },
}


def _closed_snapshot(stem, final_status="APPROVED", with_report=True):
    approve = {"path": f"{stem}.md",
               "content": f"Cycle-Stem: `{stem}`\nFinal Status: {final_status}\n", "recent": True}
    docs = {pid: [_pdoc(stem)] for pid in ("01", "02", "03", "04")}
    docs["00"] = [_pdoc(stem, risk="L2")]
    docs["05"] = [approve]
    if with_report:
        docs["06"] = [_pdoc(stem)]
    return {"plan_files": [_pdoc(stem)], "review_candidates": [], "phase_docs": docs}


class TestClosedCycleIsNotSilentlyReused(unittest.TestCase):
    """끝난 사이클은 00~06 이 다 있어 모든 게이트를 통과한다 — 새 작업이 계획 없이 진행된다."""

    def _source_event(self, **kw):
        return _event(branch=CLOSED_STEM, **kw)

    def test_inferred_stem_on_a_closed_cycle_blocks_new_source_edits(self):
        d = core.decide(self._source_event(), CLOSED_PROFILE, _closed_snapshot(CLOSED_STEM), None)
        self.assertEqual(d["message_key"], "block_cycle_closed")
        self.assertEqual(d["exit_code"], 2)
        self.assertEqual(d["cycle_source"], ["branch-leaf"])

    def test_block_names_both_escapes(self):
        d = core.decide(self._source_event(), CLOSED_PROFILE, _closed_snapshot(CLOSED_STEM), None)
        for runtime in ("claude", "codex"):
            text = messages.gate_text(d, {}, runtime)
            self.assertIn("Phase 00", text, runtime)
            self.assertIn("SAGE_CYCLE_STEM", text, runtime)

    def test_declared_stem_is_blocked_too(self):
        # 예전에는 선언을 면제했다. env 선언은 셸과 함께 죽어 무해했기 때문이다.
        # 파일 선언은 세션을 넘겨 살아남으므로 3주 전 선언이 이 차단을 통째로 꺼버린다.
        for origin in ("env", "cli"):
            d = core.decide(self._source_event(cycle_stem=CLOSED_STEM, origin=origin),
                            CLOSED_PROFILE, _closed_snapshot(CLOSED_STEM), None)
            self.assertEqual(d["message_key"], "block_cycle_closed", origin)
            self.assertEqual(d["exit_code"], 2, origin)

    def test_block_reason_names_the_binding_origin(self):
        # 사유가 `브랜치에서 추론한` 으로 고정돼 있으면 낡은 선언 때문에 막힌 사용자를 브랜치로
        # 보내서 해제 안내를 정면으로 무효화한다.
        declared = core.decide(self._source_event(cycle_stem=CLOSED_STEM), CLOSED_PROFILE,
                               _closed_snapshot(CLOSED_STEM), None)
        inferred = core.decide(self._source_event(), CLOSED_PROFILE,
                               _closed_snapshot(CLOSED_STEM), None)
        self.assertIn("선언된", declared["reason"])
        self.assertNotIn("브랜치에서 추론한", declared["reason"])
        self.assertIn("브랜치에서 추론한", inferred["reason"])

    def test_block_points_at_the_release_channel(self):
        # 낡은 선언이 원인일 때 해제 통로를 말하지 않으면 사용자는 나갈 길이 없다.
        d = core.decide(self._source_event(cycle_stem=CLOSED_STEM), CLOSED_PROFILE,
                        _closed_snapshot(CLOSED_STEM), None)
        for runtime in ("claude", "codex"):
            text = messages.gate_text(d, {}, runtime)
            self.assertIn("sage cycle clear", text, runtime)

    def test_phase_edits_on_a_closed_cycle_stay_open(self):
        # 끝난 사이클의 05·06 을 고치는 것은 정상 작업이다.
        for phase in ("05", "06"):
            event = {"hook_id": GATE, "branch": CLOSED_STEM, "session_id": "s",
                     "changes": [{"path": f"plan_docs/{phase}-x/{CLOSED_STEM}.md", "op": "write",
                                  "content": f"Cycle-Stem: `{CLOSED_STEM}`\n"}]}
            d = core.decide(event, CLOSED_PROFILE, _closed_snapshot(CLOSED_STEM), None)
            self.assertNotEqual(d["message_key"], "block_cycle_closed", phase)

    def test_a_single_doc_line_mixed_into_source_edits_does_not_exempt(self):
        """면제를 `any()` 로 쓰면 소스 열 개에 문서 한 줄만 섞어 차단 전체를 끌 수 있다.

        실측으로 확인된 우회다 — 이 갈래가 열리면 D4 자체가 무의미해진다.
        """
        event = {"hook_id": GATE, "branch": CLOSED_STEM, "session_id": "s",
                 "changes": [{"path": "backend/App.java", "op": "write", "content": "x"},
                             {"path": f"plan_docs/05-x/{CLOSED_STEM}.md", "op": "update",
                              "content": f"Cycle-Stem: `{CLOSED_STEM}`\n"}]}
        d = core.decide(event, CLOSED_PROFILE, _closed_snapshot(CLOSED_STEM), None)
        self.assertEqual(d["message_key"], "block_cycle_closed")

    def test_zero_changes_is_not_an_exemption(self):
        # 어댑터가 경로를 못 뽑은 상태가 차단을 사면하면 안 된다.
        event = dict(self._source_event(), changes=[], declared_max="L3")
        d = core.decide(event, CLOSED_PROFILE, _closed_snapshot(CLOSED_STEM), None)
        self.assertEqual(d["message_key"], "block_cycle_closed")

    def test_l0_change_on_a_closed_cycle_stays_open(self):
        d = core.decide(self._source_event(path="notes/x.md"), CLOSED_PROFILE,
                        _closed_snapshot(CLOSED_STEM), None)
        self.assertNotEqual(d["message_key"], "block_cycle_closed")

    def test_session_declaration_raises_l0_paths_into_the_block(self):
        # "L0 경로는 대상이 아니다" 는 사실이 아니다 — declared_max 가 L0 를 상향시키므로 L3 를
        # 선언한 세션에서는 문서 편집도 걸린다. 마찰이지만 effective-max 의 기존 의미와 일관되고,
        # 탈출구(선언·신규 사이클)가 같다. 실제 동작을 못박아 문서가 다시 어긋나지 않게 한다.
        event = dict(self._source_event(path="notes/x.md"), declared_max="L3")
        d = core.decide(event, CLOSED_PROFILE, _closed_snapshot(CLOSED_STEM), None)
        self.assertEqual(d["message_key"], "block_cycle_closed")

    def test_another_cycles_report_does_not_close_mine(self):
        # report 문서를 stem 결속 없이 세면 저장소에 06 이 한 건이라도 있는 순간 모든 stem 이
        # 완결로 판정된다(대량 과차단).
        snapshot = _closed_snapshot(CLOSED_STEM)
        snapshot["phase_docs"] = {**snapshot["phase_docs"], "06": [_pdoc("some_other_stem")]}
        d = core.decide(self._source_event(), CLOSED_PROFILE, snapshot, None)
        self.assertNotEqual(d["message_key"], "block_cycle_closed")

    def test_custom_approve_marker_is_honoured(self):
        cfg = {**CLOSED_PROFILE, "pdca": {**CLOSED_PROFILE["pdca"], "approve_marker": "SHIPPED"}}
        closed = _closed_snapshot(CLOSED_STEM, final_status="SHIPPED")
        still_open = _closed_snapshot(CLOSED_STEM, final_status="APPROVED")
        self.assertEqual(core.decide(self._source_event(), cfg, closed, None)["message_key"],
                         "block_cycle_closed")
        self.assertNotEqual(core.decide(self._source_event(), cfg, still_open, None)["message_key"],
                            "block_cycle_closed")

    def _with_approve_docs(self, docs):
        snapshot = _closed_snapshot(CLOSED_STEM)
        snapshot["phase_docs"] = {**snapshot["phase_docs"], "05": docs}
        return snapshot

    def test_unfinished_cycles_are_not_treated_as_closed(self):
        # 완결 판정이 한 갈래라도 헐거우면 정상 진행 중인 사이클을 막는다 — 갈래별로 고정한다.
        # 판정 불가(문서 선택 실패·상태 오류)도 완결이 아니다: 여기서 fail-closed 하면 아직 끝나지
        # 않은 사이클의 소스 편집이 통째로 막힌다.
        approve = f"Cycle-Stem: `{CLOSED_STEM}`\nFinal Status: APPROVED\n"
        for label, snapshot in (
                ("06 없음", _closed_snapshot(CLOSED_STEM, with_report=False)),
                ("승인 아님", _closed_snapshot(CLOSED_STEM, final_status="BLOCKED")),
                ("Final Status 중복", self._with_approve_docs(
                    [{"path": f"{CLOSED_STEM}.md", "content": approve + "Final Status: APPROVED\n",
                      "recent": True}])),
                ("승인 문서 없음", self._with_approve_docs([])),
                ("승인 문서 모호", self._with_approve_docs(
                    [{"path": f"{CLOSED_STEM}.md", "content": approve, "recent": True},
                     {"path": f"a/{CLOSED_STEM}.md", "content": approve, "recent": True}]))):
            d = core.decide(self._source_event(), CLOSED_PROFILE, snapshot, None)
            self.assertNotEqual(d["message_key"], "block_cycle_closed", label)

    def test_profile_without_report_or_approve_phase_makes_no_judgment(self):
        for key in ("report_phase", "approve_phase"):
            cfg = {**CLOSED_PROFILE, "pdca": {**CLOSED_PROFILE["pdca"], key: ""}}
            d = core.decide(self._source_event(), cfg, _closed_snapshot(CLOSED_STEM), None)
            self.assertNotEqual(d["message_key"], "block_cycle_closed", key)


class TestBindingIsAlwaysVisibleOnPass(unittest.TestCase):
    """통과 줄에 stem 이 안 보이면 잘못된 결속이 화면에 드러나지 않는다."""

    def _ok_line(self, decision):
        return messages.gate_text(decision, {}, "claude")

    def test_inferred_binding_is_shown_with_its_origin(self):
        # 선언했을 때만 보여주면 정작 위험한 쪽(추론)이 안 보인다.
        snapshot = _complete_snapshot(LONG_BRANCH)
        d = core.decide(_event(), PDCA_PROFILE, snapshot, None)
        self.assertEqual(d["exit_code"], 0)
        self.assertIn(f"cycle: {LONG_BRANCH} (브랜치 leaf 추론)", self._ok_line(d))

    def test_path_bound_origin_is_labelled(self):
        # phase 문서만 고치면 L0 라 OK 줄 자체가 없다 — 소스를 함께 건드려 통과 줄을 만든다.
        event = {"hook_id": GATE, "branch": LONG_BRANCH, "session_id": "s",
                 "changes": [{"path": f"plan_docs/03-x/{REAL_STEM}.md", "op": "write",
                              "content": f"Cycle-Stem: `{REAL_STEM}`\n"},
                             {"path": "backend/App.java", "op": "write", "content": "x"}]}
        d = core.decide(event, PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        self.assertEqual(d["exit_code"], 0)
        self.assertIn(f"cycle: {REAL_STEM} (phase 문서)", self._ok_line(d))

    def test_pdca_disabled_shows_nothing(self):
        # OK 경로까지 도달해야 접미가 실제로 호출된다 — plan 이 없으면 WARN 으로 빠져 공허해진다.
        profile = {"risk": {"l2_path_globs": ["*backend/*.java"], "plan_glob": "plan_docs/**/*.md"}}
        snapshot = {"plan_files": [{"path": "plan_docs/p.md", "content": "x", "recent": True}],
                    "review_candidates": [], "phase_docs": {}}
        d = core.decide(_event(), profile, snapshot, None)
        self.assertEqual(d["message_key"], "ok_l2")
        self.assertNotIn("cycle:", self._ok_line(d))

    def test_warn_pass_also_shows_the_binding(self):
        # plan 없이 통과하는 상태가 결속이 가장 의심스러운 자리다 — 여기서 안 보이면 목적을 못 이룬다.
        d = core.decide(_event(), PDCA_PROFILE,
                        {"plan_files": [], "review_candidates": [],
                         "phase_docs": _complete_snapshot(LONG_BRANCH)["phase_docs"]}, None)
        self.assertEqual(d["message_key"], "warn_l2_no_plan")
        self.assertIn(f"cycle: {LONG_BRANCH} (브랜치 leaf 추론)", self._ok_line(d))


class TestDeclarationIsAudited(unittest.TestCase):
    """선언 통로 자체는 막지 않는다. 다만 무흔적 통과는 남기지 않는다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def _records(self):
        return [r for r in ov.read_records(self.root) if r.get("event") == "cycle_stem_declared"]

    def test_declaration_is_recorded_once_per_session_and_stem(self):
        first = ov.record_cycle_stem_declaration(self.root, GATE, REAL_STEM, "sess-1", status="ok")
        again = ov.record_cycle_stem_declaration(self.root, GATE, REAL_STEM, "sess-1", status="ok")
        self.assertIsNotNone(first)
        self.assertIsNone(again)           # 게이트는 편집마다 발동한다 — 같은 사실로 부풀지 않아야
        self.assertEqual(len(self._records()), 1)
        self.assertEqual(first["cycle_stem"], REAL_STEM)

    def test_different_session_or_stem_is_a_separate_fact(self):
        ov.record_cycle_stem_declaration(self.root, GATE, REAL_STEM, "sess-1")
        ov.record_cycle_stem_declaration(self.root, GATE, REAL_STEM, "sess-2")
        ov.record_cycle_stem_declaration(self.root, GATE, "other_cycle", "sess-1")
        self.assertEqual(len(self._records()), 3)

    def test_audit_lives_in_the_committed_log_not_the_local_grant_cache(self):
        # 선언은 권한 부여가 아니라 사후 추적이다 — 권한 캐시를 오염시키면 안 된다.
        ov.record_cycle_stem_declaration(self.root, GATE, REAL_STEM, "sess-1")
        self.assertTrue(os.path.exists(ov.audit_path(self.root)))
        self.assertFalse(os.path.exists(ov.grants_path(self.root)))
        self.assertEqual(ov.active_grants(self.root), [])

    def test_reused_completed_cycle_leaves_a_trace(self):
        # 이게 이 변경의 이유다: 완결된 과거 사이클을 지목한 통과가 기록에 남는다.
        decision = core.decide(_event(cycle_stem=REAL_STEM), PDCA_PROFILE,
                               _complete_snapshot(REAL_STEM), None)
        out = hr._record_declared_cycle_stem(GATE, self.root, decision, "sess-1")
        self.assertEqual(out["message_key"], "ok_l2")
        rec = self._records()
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["cycle_stem"], REAL_STEM)
        self.assertEqual(rec[0]["status"], "ok")
        self.assertEqual(rec[0]["session_id"], "sess-1")

    def test_inferred_stem_is_not_recorded(self):
        decision = core.decide(_event(), PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        hr._record_declared_cycle_stem(GATE, self.root, decision, "sess-1")
        self.assertEqual(self._records(), [])

    def test_unrecordable_declaration_does_not_pass(self):
        # waiver 소비 기록 실패와 같은 성질의 무감사 통과다 → fail-closed.
        decision = {"status": "ok", "exit_code": 0, "message_key": "ok_l2",
                    "cycle_stem": REAL_STEM, "cycle_stem_declared": True, "file_short": "App.java"}
        with mock.patch.object(ov, "record_cycle_stem_declaration",
                               side_effect=OSError("read-only fs")):
            with redirect_stderr(_io.StringIO()) as err:
                out = hr._record_declared_cycle_stem(GATE, self.root, decision, "sess-1")
        self.assertEqual(out["status"], "block")
        self.assertEqual(out["exit_code"], 2)
        self.assertEqual(out["message_key"], "block_cycle_stem_audit_failure")
        self.assertIn("fail-closed", err.getvalue())
        self.assertIn(".sage/override.jsonl", messages.gate_text(out, {}, "claude"))

    def test_audit_failure_leaves_an_existing_block_alone(self):
        decision = {"status": "block", "exit_code": 2, "message_key": "block_phase_incomplete",
                    "cycle_stem": REAL_STEM, "cycle_stem_declared": True}
        with mock.patch.object(ov, "record_cycle_stem_declaration",
                               side_effect=OSError("read-only fs")):
            with redirect_stderr(_io.StringIO()):
                out = hr._record_declared_cycle_stem(GATE, self.root, decision, "s")
        self.assertEqual(out["message_key"], "block_phase_incomplete")

    def test_missing_session_id_does_not_dedupe_forever(self):
        """session_id 없는 입력을 빈 키로 dedupe 하면 첫 레코드가 이후 전부를 삼킨다 → 무기록 통과."""
        day = 1_700_000_000                      # 고정 시각(같은 UTC 날짜)
        self.assertIsNotNone(ov.record_cycle_stem_declaration(
            self.root, GATE, REAL_STEM, "", now=day))
        self.assertIsNone(ov.record_cycle_stem_declaration(   # 같은 날 = 같은 사실
            self.root, GATE, REAL_STEM, "", now=day + 60))
        self.assertIsNotNone(ov.record_cycle_stem_declaration(  # 다음 날은 별개 사실
            self.root, GATE, REAL_STEM, "", now=day + 86_400))
        self.assertEqual(len(self._records()), 2)

    def test_audit_failure_block_survives_an_active_override_grant(self):
        """감사 실패 BLOCK 을 일반 override grant 가 통과시키면 fail-closed 가 무의미해진다.

        override 는 그 자체가 감사에 남는 우회다 — 감사를 못 쓰는 상태에서 감사로 우회한다는 건
        성립하지 않는다. `_record_declared_cycle_stem` 직후 `_maybe_override` 가 오는 실제 순서로 본다.
        """
        ov.grant(self.root, "긴급 우회", 10000, gate="all")
        decision = {"status": "ok", "exit_code": 0, "message_key": "ok_l2",
                    "cycle_stem": REAL_STEM, "cycle_stem_declared": True, "file_short": "App.java"}
        with mock.patch.object(ov, "record_cycle_stem_declaration",
                               side_effect=OSError("read-only fs")):
            with redirect_stderr(_io.StringIO()):
                decision = hr._record_declared_cycle_stem(GATE, self.root, decision, "sess-1")
                bypassed = hr._maybe_override(GATE, self.root, decision, [{"path": "App.java"}])
        self.assertEqual(decision["message_key"], "block_cycle_stem_audit_failure")
        self.assertFalse(bypassed)
        self.assertEqual([r for r in ov.read_records(self.root) if r.get("event") == "bypass"], [])

    def test_records_are_valid_jsonl(self):
        ov.record_cycle_stem_declaration(self.root, GATE, REAL_STEM, "sess-1")
        with open(ov.audit_path(self.root), encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(lines[0]["event"], "cycle_stem_declared")
        self.assertIn("ts", lines[0])
        self.assertIn("user", lines[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
