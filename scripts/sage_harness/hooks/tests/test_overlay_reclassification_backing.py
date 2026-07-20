#!/usr/bin/env python3
"""FB23 — 적대적 우회 증명: (c)->(b) 재분류의 backing 오라클이 게이트를 floor 한다.

각 테스트는 malicious overlay 가 만들려는 사이클 상태를 주입하고, backing 오라클이 여전히
BLOCK 함을 assert 한다. 오라클(_report_gate/_acceptance_gate/_audit_gate/_missing_pre_impl_phases)은
(event, profile, snapshot) 순수함수라 asset 텍스트를 입력받지 않는다 — 오버레이가 물리 반영돼도
floor(loop_audit 레코드·05 APPROVED 마커·04 evidence·bound phase 문서)를 낮출 수 없다.
review_loop-ON/OFF 두 projection 모두에서 delta-0(합성이 새 우회를 안 연다)을 실증한다.

canonical fixture(PDCA_PROFILE·snap_audit·_audit_profile·_pdoc·ev)는 sibling
test_pre_implementation_gate 에서 재사용한다(중복 정본 회피).
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HOOKS_DIR)))
sys.path.insert(0, HOOKS_DIR)
sys.path.insert(0, REPO)

import pre_implementation_gate_core as core  # noqa: E402
import test_pre_implementation_gate as pig  # noqa: E402  (canonical fixtures/helpers)
from sage import overlay_classify as ocl  # noqa: E402


def _doc(content, path="feature.md"):
    stem = os.path.basename(path)[:-3] if path.lower().endswith(".md") else path
    return {"path": path, "content": f"Cycle-Stem: `{stem}`\n{content}", "recent": True}


# reviewer/sage-review 가 open 만 하고 close 를 실제 리뷰 없이 위조하려는 정황들. asset 프로즈로는
# 아래 loop_audit 레코드를 만들 수 없다 → _audit_gate 가 BLOCK.
_DEGRADED = {"closed": True, "result": "APPROVED", "clean": True, "seq_ok": True,
             "degraded": True, "reviewer_requested": "codex", "reviewer_actual": "claude"}
_UNCLEAN = {"closed": True, "result": "APPROVED", "clean": False, "seq_ok": True}
_SEQ_BROKEN = {"closed": True, "result": "APPROVED", "clean": True, "seq_ok": False}


class TestReviewerBacking(unittest.TestCase):
    """reviewer / sage-review — _audit_gate(loop_audit) + _report_gate(05 APPROVED)."""

    def test_reviewer_forge_blocked_loop_on(self):
        # 05 는 APPROVED + Loop-Run 을 선언하지만 audit run 이 degraded(cross-model 폴백) → BLOCK.
        d = core.decide(pig._REPORT_EV, pig._audit_profile(mode="enforce"),
                        pig.snap_audit([_doc("Final Status: APPROVED\nLoop-Run: r1")],
                                       runs={"r1": _DEGRADED}), None)
        self.assertEqual(d["message_key"], "block_report_without_audit")
        self.assertEqual(d["exit_code"], 2)

    def test_reviewer_forge_blocked_loop_off(self):
        # review_loop OFF → _audit_gate skip. 그래도 _report_gate 가 05 APPROVED 를 자산-불read 로 강제.
        # 승인 안 된 05(=리뷰 미통과)면 06 report BLOCK. base 와 동일 floor → 합성 delta 0.
        d = core.decide(pig._REPORT_EV, pig._audit_profile(mode="advisory", enabled=False),
                        pig.snap_audit([_doc("Final Status: CHANGES_REQUESTED")]), None)
        self.assertEqual(d["message_key"], "block_report_without_approval")
        self.assertEqual(d["exit_code"], 2)

    def test_sage_review_degraded_run_blocked(self):
        # unclean(중복/재사용 open·close·고아) run → 증거 모호 → BLOCK.
        d = core.decide(pig._REPORT_EV, pig._audit_profile(mode="enforce"),
                        pig.snap_audit([_doc("Final Status: APPROVED\nLoop-Run: r1")],
                                       runs={"r1": _UNCLEAN}), None)
        self.assertEqual(d["message_key"], "block_report_without_audit")

    def test_sage_review_seq_forged_run_blocked(self):
        # seq 불연속 = 수기 JSONL append/순서 조작 → BLOCK.
        d = core.decide(pig._REPORT_EV, pig._audit_profile(mode="enforce"),
                        pig.snap_audit([_doc("Final Status: APPROVED\nLoop-Run: r1")],
                                       runs={"r1": _SEQ_BROKEN}), None)
        self.assertEqual(d["message_key"], "block_report_without_audit")


class TestReportBacking(unittest.TestCase):
    """sage-cycle / sage-team — _report_gate(06←05 APPROVED), asset-text-independent."""

    def test_sage_cycle_report_without_approve_blocked(self):
        # 이번 cycle 의 05 가 없음(리뷰 스킵) → 06 report BLOCK.
        d = core.decide(pig._REPORT_EV, pig.PDCA_PROFILE, pig.snap_audit([]), None)
        self.assertEqual(d["message_key"], "block_report_without_approval")
        self.assertEqual(d["exit_code"], 2)

    def test_sage_team_skip_review_blocked_loop_off(self):
        # sage-team 오버레이 "리뷰어 건너뛰기": loop OFF 여도 _report_gate 가 bound 05 APPROVED 요구.
        # 리뷰 스킵 → APPROVED 05 부재 → 06 report BLOCK(합성 delta 0).
        d = core.decide(pig._REPORT_EV, pig._audit_profile(mode="advisory", enabled=False),
                        pig.snap_audit([]), None)
        self.assertEqual(d["message_key"], "block_report_without_approval")
        self.assertEqual(d["exit_code"], 2)


class TestPhaseBacking(unittest.TestCase):
    """leader / sage-plan — _missing_pre_impl_phases(bound phase 문서), asset-text-independent."""

    def test_leader_phase_skip_blocked(self):
        # leader 오버레이 "계획 생략": L2 소스 편집인데 의무 phase(01/02/03) 결핍 → BLOCK.
        d = core.decide(pig.ev("backend/Svc.java"), pig.PDCA_PROFILE,
                        pig.snap_pdca(phase_docs={"00": [pig._pdoc()]}), None)
        self.assertEqual(d["message_key"], "block_phase_incomplete")
        self.assertEqual(d["exit_code"], 2)
        self.assertEqual(d["missing_phases"], ["01", "02", "03"])

    def test_sage_plan_unbound_plan_blocked(self):
        # sage-plan 오버레이가 다른 cycle 의 plan 문서를 재활용해도 stem 결속 불일치 → 결핍 → BLOCK.
        event = pig.ev("backend/Svc.java", "Cycle-Stem: `feat-x`\n")
        docs = {p: [pig._pdoc(stem="other")] for p in ("00", "01", "02", "03")}
        d = core.decide(event, pig.PDCA_PROFILE, pig.snap_pdca(phase_docs=docs), None)
        self.assertEqual(d["message_key"], "block_phase_incomplete")
        self.assertEqual(d["exit_code"], 2)


class TestQaExclusion(unittest.TestCase):
    """qa 는 (c) 잔류 — _acceptance_gate 는 04 증거 '구조'만 보고 claimed PASS 를 재실행하지 않는다.
    fake all-PASS 04 를 오라클이 못 잡으므로 적대적 우회 테스트 RED → 등록 불가(FB24 후보)."""

    def _matrix(self):
        return ("## Acceptance Matrix\n"
                "| ID | User Requirement | Required Evidence | Owner | Required? |\n"
                "|---|---|---|---|---|\n"
                "| A1 | search | test | qa | yes |\n"
                "| A2 | notify | test | qa | yes |\n")

    def _snap(self, content04):
        def bound(c):
            return f"Cycle-Stem: `feature`\n{c}"
        return {"plan_files": [], "review_candidates": [], "phase_docs": {
            "01": [{"path": "feature.md", "content": bound(self._matrix()), "recent": True}],
            "04": [{"path": "feature.md", "content": bound(content04), "recent": True}],
            "05": [{"path": "feature.md", "content": bound("Final Status: APPROVED"), "recent": True}]}}

    def test_fabricated_all_pass_04_is_not_caught(self):
        # qa 오버레이가 실제 테스트 없이 모든 행을 PASS 로 위조해도 구조가 유효하면 gate 통과(ok).
        fake04 = ("## Acceptance Evidence\n| ID | Status | Evidence |\n|---|---|---|\n"
                  "| A1 | PASS | (fabricated) |\n| A2 | PASS | (fabricated) |\n")
        d = core.decide(pig._REPORT_EV, pig._acceptance_profile(mode="enforce"),
                        self._snap(fake04), None)
        self.assertEqual(d["status"], "ok", "구조적으로 유효한 fake-PASS 04 는 acceptance gate 를 통과")

    def test_qa_stays_c(self):
        self.assertNotIn(("agents", "qa"), ocl.INDEPENDENT_ORACLE_COMPOSE_ALLOWED)
        self.assertIn(("agents", "qa"), ocl.GATE_BEARING_UNBACKED)
        self.assertEqual(ocl.classify("agents", "qa"), "blocked")


class TestAcceptanceContentGapIsPreExisting(unittest.TestCase):
    """FB23 R3 — _acceptance_gate 는 구조만 floor 하고 내용 진위는 재검하지 않는다.

    포함된 자산(leader matrix 축소·sage-team fake-04)과 제외된 qa 가 동일 클래스의 미포착
    내용-forge 를 가짐을 명시한다. 단 이는 오버레이 없이 base 도 가진 선존 갭(합성 delta=0)이라
    합성 위협모델 밖이다. (b) 멤버십은 primary 게이트가 floored 인지로 정한다: leader/sage-team 은
    primary 기여(phase/시퀀싱)가 floored → (b); qa 는 primary 기여가 04 진위 자체 → (c)."""

    def _snap(self, matrix_ids, ev_ids):
        def bound(c):
            return f"Cycle-Stem: `feature`\n{c}"
        m = ("## Acceptance Matrix\n| ID | User Requirement | Required Evidence | Owner | Required? |\n"
             "|---|---|---|---|---|\n"
             + "".join(f"| {i} | req | test | qa | yes |\n" for i in matrix_ids))
        e = ("## Acceptance Evidence\n| ID | Status | Evidence |\n|---|---|---|\n"
             + "".join(f"| {i} | PASS | x |\n" for i in ev_ids))
        return {"plan_files": [], "review_candidates": [], "phase_docs": {
            "01": [{"path": "feature.md", "content": bound(m), "recent": True}],
            "04": [{"path": "feature.md", "content": bound(e), "recent": True}],
            "05": [{"path": "feature.md", "content": bound("Final Status: APPROVED"), "recent": True}]}}

    def _decide(self, matrix_ids, ev_ids):
        return core.decide(pig._REPORT_EV, pig._acceptance_profile(mode="enforce"),
                           self._snap(matrix_ids, ev_ids), None)

    def test_content_forges_are_uncaught_but_structural_gap_is_caught(self):
        # 내용 forge(포함/제외 자산 공통): 전부 미포착 = ok. → 합성 위협모델 밖(delta-0 선존 갭).
        self.assertEqual(self._decide(["A1", "A2"], ["A1", "A2"])["status"], "ok",
                         "qa/sage-team fake all-PASS 04 는 미포착(실행 오라클 부재)")
        self.assertEqual(self._decide(["A1"], ["A1"])["status"], "ok",
                         "leader 가 01 matrix 를 축소해도 미포착(진짜 요구사항을 아는 오라클 부재)")
        # 구조 gap(required row 누락)은 포착 = BLOCK. 이것이 오라클이 실제 floor 하는 것.
        self.assertEqual(self._decide(["A1", "A2"], ["A1"])["message_key"],
                         "block_report_without_acceptance",
                         "04 가 required ID 를 빠뜨리는 구조 gap 은 포착")

    def test_qa_stays_c_because_primary_contribution_is_the_uncaught_content(self):
        self.assertNotIn(("agents", "qa"), ocl.INDEPENDENT_ORACLE_COMPOSE_ALLOWED)
        self.assertIn(("agents", "qa"), ocl.GATE_BEARING_UNBACKED)


class TestBackingRecordEnforcement(unittest.TestCase):
    """산출물 ③ — 등록=BACKING+적대적 테스트 보유(위조불가 배선)."""

    def test_every_registered_asset_has_backing_and_named_tests(self):
        this_module = sys.modules[__name__]
        for entry in ocl.INDEPENDENT_ORACLE_COMPOSE_ALLOWED:
            rec = ocl.BACKING.get(entry)
            self.assertIsNotNone(rec, f"{entry} registered without BACKING record")
            self.assertTrue(rec.get("oracles"), f"{entry} BACKING has no oracles")
            names = rec.get("adversarial_tests") or []
            self.assertTrue(names, f"{entry} BACKING has no adversarial tests")
            for tname in names:
                found = any(hasattr(getattr(this_module, cls), tname)
                            for cls in dir(this_module)
                            if isinstance(getattr(this_module, cls), type)
                            and issubclass(getattr(this_module, cls), unittest.TestCase))
                self.assertTrue(found, f"{entry} names missing adversarial test {tname!r}")


if __name__ == "__main__":
    unittest.main()
