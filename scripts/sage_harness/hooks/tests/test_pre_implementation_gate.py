#!/usr/bin/env python3
"""pre-implementation-gate 폐루프 검증 (부분추출: 공유 risk-gate core + unresolved 전략슬롯).

검증(Codex Q2 — core 중심):
  1. classify_risk: L0/L1/L2/L3 분류, 내용 escalation, desktop block, declared 상향, case-insensitive
  2. decide: desktop block / L3+no-plan block / L3+전략미선택 BLOCK(safety_degraded) / L3+found ok / L3+notfound warn /
             L2 no-plan warn / L2 plan ok / L1 ok
  3. 전략 후보 보존: claude_grep_first / codex_feature_signal find_l3_review 동작(병합 안 함)
  4. adapter: claude file_path & codex apply_patch → L3 미선택 BLOCK 동일
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
ADAPTERS = os.path.join(HOOKS_DIR, "adapters")
PROFILE_PATH = os.path.join(HERE, "fixtures", "pre_impl_gate", "example.profile.json")

sys.path.insert(0, HOOKS_DIR)
sys.path.insert(0, os.path.join(HOOKS_DIR, "strategies", "pre_implementation_gate"))
import pre_implementation_gate_core as core  # noqa: E402
import claude_grep_first  # noqa: E402
import codex_feature_signal  # noqa: E402

with open(PROFILE_PATH, encoding="utf-8") as _f:
    PROFILE = json.load(_f)


def ev(path, content="", branch="main", declared=None):
    return {"hook_id": "pre-implementation-gate", "runtime": "test", "branch": branch,
            "declared_max": declared, "changes": [{"path": path, "op": "write", "content": content}]}


class TestClassify(unittest.TestCase):
    def test_levels(self):
        cases = [
            ("docs/x.md", "", "L0"),
            ("frontend/static/js/app.js", "", "L1"),
            ("backend/src/main/java/Foo.java", "", "L2"),
            ("backend/payment/Svc.java", "", "L3"),       # filename 패턴(고위험=payment)
        ]
        for path, content, exp in cases:
            self.assertEqual(core.classify_risk(ev(path, content), PROFILE)["risk"], exp, path)

    def test_content_escalation(self):
        l3 = core.classify_risk(ev("frontend/static/js/x.js", "encrypt()"), PROFILE)
        l2 = core.classify_risk(ev("frontend/static/js/x.js", "Repository"), PROFILE)
        self.assertEqual(l3["risk"], "L3")
        self.assertEqual(l3["trigger_sources"], ["path_l1", "content_l3"])
        self.assertEqual(l2["risk"], "L2")
        self.assertEqual(l2["trigger_sources"], ["path_l1", "content_l2"])

    def test_l0_content_l3_flagged(self):
        # P2-9: L0 즉시통과 문서(.md)에 L3 키워드 포함 → 위험은 L0 유지(비차단)하되 l0_l3_file 플래그.
        c = core.classify_risk(ev("docs/x.md", "encrypt()"), PROFILE)
        self.assertEqual(c["risk"], "L0")
        self.assertEqual(c["l0_l3_file"], "docs/x.md")
        # L3 키워드 없는 L0 문서 → 플래그 없음
        self.assertEqual(core.classify_risk(ev("docs/x.md", "just docs"), PROFILE)["l0_l3_file"], "")

    def test_l0_exclusion_promotes_only_bound_domain_assets(self):
        profile = {"risk": {
            "l0_pass_globs": ["**/*.png"],
            "l0_exclude_globs": ["assets/game/**"],
            "l1_path_globs": [],
            "l2_path_globs": [],
            "l3_filename_globs": ["assets/game/**"],
            "l2_content_keywords": [],
            "l3_content_keywords": [],
        }}
        generic = core.classify_risk(ev("assets/common/logo.png"), profile)
        domain = core.classify_risk(ev("assets/game/board.png"), profile)
        self.assertEqual(generic["risk"], "L0")
        self.assertEqual(domain["risk"], "L3")
        self.assertEqual(domain["trigger_sources"], ["filename_l3", "l0_excluded"])

        orphan = {"risk": {"l0_pass_globs": ["**/*.png"],
                            "l0_exclude_globs": ["assets/game/**"]}}
        fail_closed = core.classify_risk(ev("assets/game/board.png"), orphan)
        self.assertEqual(fail_closed["risk"], "L3")
        self.assertEqual(fail_closed["trigger_sources"], ["l0_excluded", "invalid_profile"])

    def test_l0_first_is_preserved_without_exclusion(self):
        profile = {"risk": {
            "l0_pass_globs": ["**/*.png"],
            "l3_filename_globs": ["assets/game/**"],
        }}
        self.assertEqual(core.classify_risk(ev("assets/game/board.png"), profile)["risk"], "L0")

    def test_case_insensitive(self):
        # 소문자 키워드도 잡혀야(canonical=case-insensitive, 더 안전)
        self.assertEqual(core.classify_risk(ev("backend/src/main/java/F.java", "privatekey"), PROFILE)["risk"], "L3")
        self.assertEqual(core.classify_risk(ev("x/KEYSTORE_handler.txt", ""), PROFILE)["risk"], "L3")  # filename 대문자

    def test_desktop_block(self):
        self.assertEqual(core.classify_risk(ev("generated/x.js"), PROFILE)["risk"], "DESKTOP_BLOCK")

    def test_declared_escalation(self):
        c = core.classify_risk(ev("frontend/static/js/x.js", "", declared="L3"), PROFILE)
        self.assertEqual(c["risk"], "L3")
        self.assertEqual(c["trigger_sources"], ["path_l1", "declared_l3"])

    def test_reason_neutral_no_stack_leak(self):
        # 제약 #2: core 분류 사유는 스택/도메인 중립이어야 한다(엔진 도메인값 0).
        # Tier 2(weatherapp) 회귀 가드: L1/L2 사유에 '백엔드/프론트/java' 등 스택어가 박히면 실패.
        leak = ("백엔드", "프론트", "backend", "frontend", "springboot",
                "nodejs", "java", "js/ui", "kurento", "webrtc", "kotlin")
        l2 = core.classify_risk(ev("backend/src/main/java/Foo.java"), PROFILE)
        l1 = core.classify_risk(ev("frontend/static/js/app.js"), PROFILE)
        self.assertEqual(l2["risk"], "L2")
        self.assertEqual(l1["risk"], "L1")
        for label in (l2["reason"], l1["reason"]):
            for w in leak:
                self.assertNotIn(w, label.lower(), f"스택 누출: {label!r}")
        # 중립 라벨은 발동 규칙(L1/L2)만 기술
        self.assertEqual(l2["reason"], "L2 소스/설정")
        self.assertEqual(l1["reason"], "L1 저위험")


def snap(plan=None, review=None):
    return {"plan_files": plan or [], "review_candidates": review or []}


class TestDecide(unittest.TestCase):
    def test_desktop(self):
        d = core.decide(ev("generated/x.js"), PROFILE, snap(), None)
        self.assertEqual((d["status"], d["exit_code"]), ("block", 2))

    def test_l3_no_plan_block(self):
        d = core.decide(ev("a/payment.java"), PROFILE, snap(plan=[]), None)
        self.assertEqual(d["message_key"], "block_l3_no_plan")
        self.assertEqual(d["exit_code"], 2)

    def test_content_l3_block_is_opt_in_and_l0_carveout_remains(self):
        enforcing = json.loads(json.dumps(PROFILE))
        enforcing["risk"]["content_l3_enforce"] = "block"
        content_event = ev("frontend/static/js/x.js", "encrypt()")
        blocked = core.decide(content_event, enforcing, snap(plan=[]), {"found": False})
        compatible = core.decide(content_event, PROFILE, snap(plan=[]), {"found": False})
        l0 = core.decide(ev("docs/x.md", "encrypt()"), enforcing, snap(plan=[]), None)
        self.assertEqual(blocked["message_key"], "block_l3_no_plan")
        self.assertEqual(compatible["message_key"], "warn_l3_no_review")
        self.assertEqual(l0["message_key"], "warn_l0_l3_content")

    def test_l3_strategy_unselected_block(self):
        # plan 있음 → no-plan block 회피, 전략 미선택 → safety BLOCK
        plan = [{"path": "plan_docs/00-base_plan/x.md", "content": "#127 feature"}]
        d = core.decide(ev("a/payment.java", branch="bug/127"), PROFILE, snap(plan=plan), None)
        self.assertEqual(d["message_key"], "block_l3_strategy_unresolved")
        self.assertTrue(d["safety_degraded"])
        self.assertEqual(d["exit_code"], 2)

    def test_sd8_strategy_not_found_blocks_instead_of_warn(self):
        plan = [{"path": "plan_docs/00-base_plan/x.md", "content": "#127 feature"}]
        d = core.decide(ev("a/payment.java", branch="bug/127"), PROFILE, snap(plan=plan),
                        {"found": False, "enforce": True, "reason": "missing domain review"})
        self.assertEqual(d["message_key"], "block_l3_review_evidence")
        self.assertEqual(d["exit_code"], 2)

    def test_l3_strategy_found_ok(self):
        plan = [{"path": "plan_docs/00-base_plan/x.md", "content": "#127"}]
        d = core.decide(ev("a/payment.java", branch="bug/127"), PROFILE, snap(plan=plan), {"found": True, "path": "r.md"})
        self.assertEqual((d["status"], d["exit_code"]), ("ok", 0))

    def test_l3_strategy_notfound_warn(self):
        plan = [{"path": "plan_docs/00-base_plan/x.md", "content": "#127"}]
        d = core.decide(ev("a/payment.java", branch="bug/127"), PROFILE, snap(plan=plan), {"found": False})
        self.assertEqual((d["status"], d["exit_code"]), ("warn", 0))

    def test_l2_plan_gate(self):
        f = "backend/src/main/java/Foo.java"
        self.assertEqual(core.decide(ev(f), PROFILE, snap(plan=[]), None)["message_key"], "warn_l2_no_plan")
        plan = [{"path": "p.md", "content": "#127"}]
        self.assertEqual(core.decide(ev(f, branch="bug/127"), PROFILE, snap(plan=plan), None)["status"], "ok")

    def test_plan_fallback_7day(self):
        # audit P1: ticket 미매칭 시 7일 이내(recent) plan 만 fallback 인정
        f = "backend/src/main/java/Foo.java"
        recent_plan = [{"path": "r.md", "content": "무관", "recent": True}]
        old_plan = [{"path": "o.md", "content": "무관", "recent": False}]
        # branch 에 ticket 없음 → fallback. recent=True → plan 인정(ok)
        self.assertEqual(core.decide(ev(f, branch="main"), PROFILE, snap(plan=recent_plan), None)["status"], "ok")
        # recent=False(오래된 plan) → plan 미인정 → warn_l2_no_plan
        self.assertEqual(core.decide(ev(f, branch="main"), PROFILE, snap(plan=old_plan), None)["message_key"], "warn_l2_no_plan")

    def test_l1_ok(self):
        self.assertEqual(core.decide(ev("frontend/static/js/x.js"), PROFILE, snap(), None)["status"], "ok")

    def test_l0_l3_content_warns(self):
        # P2-9: L0 문서에 L3 키워드 → 비차단 WARN(exit0). 차단 아님(문서 대상, 저위험).
        d = core.decide(ev("docs/x.md", "encrypt()"), PROFILE, snap(), None)
        self.assertEqual(d["status"], "warn")
        self.assertEqual(d["message_key"], "warn_l0_l3_content")
        self.assertEqual(d["exit_code"], 0)
        # 깨끗한 L0 문서는 ok(message_key 없음) — WARN 오발 없음
        self.assertEqual(core.decide(ev("docs/x.md", "plain"), PROFILE, snap(), None)["message_key"], None)


PDCA_PROFILE = {
    "risk": {
        "l0_pass_globs": ["*.md", "plan_docs/*"],
        "l1_path_globs": ["*frontend*"],
        "l2_path_globs": ["*backend*"],
        "l3_filename_globs": ["*payment*"],
    },
    "pdca": {
        "enabled": True,
        "phases": [
            {"id": "00", "glob": "plan_docs/00-base_plan/**/*.md"},
            {"id": "01", "glob": "plan_docs/01-plan/**/*.md"},
            {"id": "02", "glob": "plan_docs/02-design/**/*.md"},
            {"id": "03", "glob": "plan_docs/03-implementation/**/*.md"},
            {"id": "04", "glob": "plan_docs/04-analyze/**/*.md"},
            {"id": "05", "glob": "plan_docs/05-expert-review/**/*.md"},
            {"id": "06", "glob": "plan_docs/06-report/**/*.md"},
        ],
        "pre_implementation_required": {"L1": ["00"], "L2": ["00", "01", "02", "03"], "L3": ["00", "01", "02", "03"]},
        "report_phase": "06", "approve_phase": "05", "approve_marker": "APPROVED",
    },
}


def _pdoc(content="x", recent=True, stem="main"):
    return {"path": f"{stem}.md", "content": f"Cycle-Stem: `{stem}`\n{content}", "recent": recent}


def snap_pdca(phase_docs=None, plan=None, review=None):
    return {"plan_files": plan or [], "review_candidates": review or [], "phase_docs": phase_docs or {}}


class TestPdcaEnforcement(unittest.TestCase):
    def test_new_phase_doc_without_cycle_stem_blocks(self):
        event = ev("plan_docs/06-report/feature.md", "Status: COMPLETE\n")
        d = core.decide(event, PDCA_PROFILE, snap_pdca(), None)
        self.assertEqual(d["message_key"], "block_cycle_binding")
        self.assertEqual(d["exit_code"], 2)
        self.assertIn("Cycle-Stem declaration missing", d["reason"])

    def test_multiple_changed_cycle_stems_block(self):
        event = {"branch": "main", "changes": [
            {"path": "plan_docs/01-plan/a.md", "op": "write", "content": "Cycle-Stem: `a`\n"},
            {"path": "plan_docs/04-analyze/b.md", "op": "write", "content": "Cycle-Stem: `b`\n"},
        ]}
        d = core.decide(event, PDCA_PROFILE, snap_pdca(), None)
        self.assertEqual(d["message_key"], "block_cycle_binding")
        self.assertIn("candidate count", d["reason"])

    def test_l2_missing_phases_blocks(self):
        # 의무 phase(00/01/02/03) 중 01·02·03 결핍 → L2 BLOCK
        d = core.decide(ev("backend/Svc.java"), PDCA_PROFILE,
                        snap_pdca(phase_docs={"00": [_pdoc()]}), None)
        self.assertEqual(d["message_key"], "block_phase_incomplete")
        self.assertEqual(d["exit_code"], 2)
        self.assertEqual(d["missing_phases"], ["01", "02", "03"])

    def test_l2_missing_only_03_blocks(self):
        # 00/01/02 있어도 03(구현 문서=파일소유/체크리스트) 없으면 소스 편집 BLOCK — 스캐폴딩 우회 차단
        docs = {"00": [_pdoc()], "01": [_pdoc()], "02": [_pdoc()]}
        d = core.decide(ev("backend/build.gradle.kts"), PDCA_PROFILE,
                        snap_pdca(phase_docs=docs, plan=[_pdoc()]), None)
        self.assertEqual(d["message_key"], "block_phase_incomplete")
        self.assertEqual(d["exit_code"], 2)
        self.assertEqual(d["missing_phases"], ["03"])

    def test_l2_all_phases_present_falls_through(self):
        # 00/01/02/03 충족 → phase 통과 → 기존 L2 로직(plan 있음 → ok_l2)
        docs = {"00": [_pdoc()], "01": [_pdoc()], "02": [_pdoc()], "03": [_pdoc()]}
        d = core.decide(ev("backend/Svc.java"), PDCA_PROFILE,
                        snap_pdca(phase_docs=docs, plan=[_pdoc()]), None)
        self.assertEqual(d["message_key"], "ok_l2")

    def test_l3_phases_present_then_review_logic_preserved(self):
        # phase 충족이 L3 review 게이트를 단축하지 않는다 → 전략 미선택이면 여전히 BLOCK
        docs = {"00": [_pdoc(stem="127")], "01": [_pdoc(stem="127")],
                "02": [_pdoc(stem="127")], "03": [_pdoc(stem="127")]}
        d = core.decide(ev("a/payment.java", branch="bug/127"), PDCA_PROFILE,
                        snap_pdca(phase_docs=docs, plan=[_pdoc(stem="127")]), None)
        self.assertEqual(d["message_key"], "block_l3_strategy_unresolved")

    def test_l3_missing_only_03_blocks(self):
        # L3 도 03 선행 강제 — 00/01/02 있어도 03 없으면 BLOCK
        docs = {"00": [_pdoc()], "01": [_pdoc()], "02": [_pdoc()]}
        d = core.decide(ev("a/payment.java"), PDCA_PROFILE,
                        snap_pdca(phase_docs=docs, plan=[_pdoc()]), {"found": True})
        self.assertEqual(d["message_key"], "block_phase_incomplete")
        self.assertEqual(d["missing_phases"], ["03"])

    def test_l3_missing_phases_blocks_before_review(self):
        # phase 결핍이 우선 → review 전략 결과와 무관하게 phase BLOCK
        d = core.decide(ev("a/payment.java"), PDCA_PROFILE,
                        snap_pdca(phase_docs={"00": [_pdoc()]}), {"found": True})
        self.assertEqual(d["message_key"], "block_phase_incomplete")
        self.assertEqual(d["missing_phases"], ["01", "02", "03"])

    def test_l1_missing_phases_warns(self):
        d = core.decide(ev("frontend/app.js"), PDCA_PROFILE, snap_pdca(phase_docs={}), None)
        self.assertEqual(d["message_key"], "warn_phase_incomplete")
        self.assertEqual(d["exit_code"], 0)
        self.assertEqual(d["missing_phases"], ["00"])

    def test_report_blocked_without_approval(self):
        # 06-report 작성 + 05 에 APPROVED 없음 → BLOCK
        d = core.decide(ev("plan_docs/06-report/feature.md", "Cycle-Stem: `feature`\n"), PDCA_PROFILE,
                        snap_pdca(phase_docs={"05": [_pdoc(content="Final Status: FAIL", stem="feature")]}), None)
        self.assertEqual(d["message_key"], "block_report_without_approval")
        self.assertEqual(d["exit_code"], 2)

    def test_noncanonical_report_paths_cannot_skip_report_gate(self):
        snapshot = snap_pdca(phase_docs={
            "05": [_pdoc(content="Final Status: FAIL", stem="feature")],
        })
        for path in (
            "plan_docs/./06-report/feature.md",
            "plan_docs//06-report/feature.md",
            "plan_docs/05-expert-review/../06-report/feature.md",
        ):
            with self.subTest(path=path):
                d = core.decide(ev(path, "Cycle-Stem: `feature`\n"), PDCA_PROFILE, snapshot, None)
                self.assertEqual(d["message_key"], "block_report_without_approval")
                self.assertEqual(d["exit_code"], 2)

    def test_report_allowed_with_approval(self):
        # 05 에 APPROVED → 06 작성 허용(L0 문서 → ok)
        d = core.decide(ev("plan_docs/06-report/feature.md", "Cycle-Stem: `feature`\n"), PDCA_PROFILE,
                        snap_pdca(phase_docs={"05": [_pdoc(content="Final Status: APPROVED", stem="feature")]}), None)
        self.assertEqual(d["status"], "ok")
        self.assertNotEqual(d["message_key"], "block_report_without_approval")

    def test_report_rejects_unfilled_status_placeholder(self):
        placeholder = "**Final Status:** APPROVED / FAIL / BLOCKED"
        d = core.decide(ev("plan_docs/06-report/feature.md", "Cycle-Stem: `feature`\n"), PDCA_PROFILE,
                        snap_pdca(phase_docs={"05": [_pdoc(content=placeholder, stem="feature")]}), None)
        self.assertEqual(d["message_key"], "block_report_without_approval")
        self.assertIn("Final Status", d["reason"])

    def test_report_rejects_duplicate_final_status(self):
        content = "Final Status: APPROVED\nFinal Status: APPROVED"
        d = core.decide(ev("plan_docs/06-report/feature.md", "Cycle-Stem: `feature`\n"), PDCA_PROFILE,
                        snap_pdca(phase_docs={"05": [_pdoc(content=content, stem="feature")]}), None)
        self.assertEqual(d["message_key"], "block_report_without_approval")
        self.assertIn("found 2", d["reason"])

    def test_report_cannot_share_change_with_evidence_phases(self):
        event = {"branch": "feat/feature", "changes": [
            {"path": "plan_docs/04-analyze/feature.md", "op": "update",
             "content": "Cycle-Stem: `feature`\n| A1 | FAIL |\n"},
            {"path": "plan_docs/05-expert-review/feature.md", "op": "update",
             "content": "Cycle-Stem: `feature`\nFinal Status: FAIL\n"},
            {"path": "plan_docs/06-report/feature.md", "op": "add",
             "content": "Cycle-Stem: `feature`\n"},
        ]}
        d = core.decide(event, PDCA_PROFILE, snap_pdca(), None)
        self.assertEqual(d["message_key"], "block_report_mixed_evidence")
        self.assertEqual(d["exit_code"], 2)

    def test_report_cannot_share_change_with_any_snapshot_dependency_phase(self):
        for phase, directory in (("00", "00-base_plan"), ("02", "02-design"),
                                 ("03", "03-implementation")):
            with self.subTest(phase=phase):
                event = {"branch": "feat/feature", "changes": [
                    {"path": f"plan_docs/{directory}/feature.md", "op": "update",
                     "content": "Cycle-Stem: `feature`\nRisk Level: L3\n"},
                    {"path": "plan_docs/06-report/feature.md", "op": "add",
                     "content": "Cycle-Stem: `feature`\n"},
                ]}
                d = core.decide(event, PDCA_PROFILE, snap_pdca(), None)
                self.assertEqual(d["message_key"], "block_report_mixed_evidence")
                self.assertIn(phase, d["reason"])

    def test_non_markdown_phase_attachment_is_not_cycle_governed(self):
        d = core.decide(ev("plan_docs/01-plan/notes.txt", "plain attachment", branch="feat/current"),
                        PDCA_PROFILE, snap_pdca(), None)
        self.assertEqual(d["status"], "ok")
        self.assertNotEqual(d["message_key"], "block_cycle_binding")

    def test_report_ignores_approved_other_cycle(self):
        docs = [
            _pdoc(content="Final Status: FAIL", stem="feature"),
            _pdoc(content="Final Status: APPROVED", stem="other"),
        ]
        event = ev("plan_docs/06-report/feature.md", "Cycle-Stem: `feature`\n")
        d = core.decide(event, PDCA_PROFILE, snap_pdca(phase_docs={"05": docs}), None)
        self.assertEqual(d["message_key"], "block_report_without_approval")
        self.assertIn("feature.md", d["reason"])

    def test_ticketless_branch_exact_stem_selects_required_phases(self):
        stem = "weather-search"
        docs = {phase: [_pdoc(stem=stem)] for phase in ("00", "01", "02", "03")}
        d = core.decide(ev("backend/Svc.java", branch=f"feat/{stem}"), PDCA_PROFILE,
                        snap_pdca(phase_docs=docs, plan=[_pdoc(stem=stem)]), None)
        self.assertEqual(d["message_key"], "ok_l2")

    def test_recent_unrelated_phase_docs_do_not_satisfy_source_cycle(self):
        docs = {phase: [_pdoc(stem="other", recent=True)] for phase in ("00", "01", "02", "03")}
        d = core.decide(ev("backend/Svc.java", branch="feat/current"), PDCA_PROFILE,
                        snap_pdca(phase_docs=docs, plan=[_pdoc(stem="other")]), None)
        self.assertEqual(d["message_key"], "block_phase_incomplete")
        self.assertEqual(d["missing_phases"], ["00", "01", "02", "03"])

    def test_inactive_pdca_is_backward_compatible(self):
        # pdca 미설정(기존 PROFILE) → phase 강제 None → 기존 동작(L2 no-plan → warn)
        self.assertIsNone(core._missing_pre_impl_phases(ev("backend/src/main/java/F.java"), PROFILE, snap_pdca(), "L2"))
        d = core.decide(ev("backend/src/main/java/Foo.java"), PROFILE, snap(plan=[]), None)
        self.assertEqual(d["message_key"], "warn_l2_no_plan")


def _audit_profile(mode="advisory", enabled=True):
    import copy
    p = copy.deepcopy(PDCA_PROFILE)
    p["pdca"]["review_loop"] = {"enabled": enabled, "report_gate_enforce": mode}
    return p


def _acceptance_profile(mode="advisory", enabled=True):
    import copy
    p = copy.deepcopy(PDCA_PROFILE)
    p["verification"] = {
        "acceptance": {
            "enabled": enabled,
            "statuses": ["PASS", "FAIL", "NOT TESTED", "N/A"],
            "unresolved_statuses": ["FAIL", "NOT TESTED"],
            "report_gate_enforce": mode,
        }
    }
    return p


def _risk_acceptance_profile(waiver_enabled=True):
    p = _acceptance_profile(enabled=True)
    ac = p["verification"]["acceptance"]
    ac.pop("report_gate_enforce", None)
    ac["report_gate_by_risk"] = {"L2": "advisory", "L3": "enforce"}
    ac["waiver"] = {"enabled": waiver_enabled}
    return p


def snap_audit(docs05, runs=None, has_any=None):
    """06 작성 시나리오: 05 phase_docs + 주입된 loop_audit."""
    return {"plan_files": [], "review_candidates": [], "phase_docs": {"05": docs05},
            "loop_audit": {"runs": runs or {}, "has_any_records": runs is not None if has_any is None else has_any}}


_REPORT_EV = ev("plan_docs/06-report/feature.md", "Cycle-Stem: `feature`\n")


class TestReportAuditGate(unittest.TestCase):
    """9.5 — 06←05 가 cycle 05 가 가리키는 loop run 의 closed+APPROVED 를 검사(run_id 바인딩)."""

    def _doc(self, content, recent=True, path="feature.md"):
        stem = os.path.basename(path)[:-3] if path.lower().endswith(".md") else path
        return {"path": path, "content": f"Cycle-Stem: `{stem}`\n{content}", "recent": recent}

    def test_off_is_marker_only(self):
        # report_gate_enforce off → audit 미검사. APPROVED 있으면 통과(ok), Loop-Run 없어도 무관.
        d = core.decide(_REPORT_EV, _audit_profile(mode="off"),
                        snap_audit([self._doc("Final Status: APPROVED")]), None)
        self.assertEqual(d["status"], "ok")

    def test_loop_disabled_skips(self):
        # review_loop.enabled=false → flag advisory 여도 audit skip(마커만).
        d = core.decide(_REPORT_EV, _audit_profile(mode="advisory", enabled=False),
                        snap_audit([self._doc("Final Status: APPROVED")]), None)
        self.assertEqual(d["status"], "ok")

    def test_advisory_warns_without_loop_run(self):
        # APPROVED 있으나 Loop-Run 미기재 → advisory WARN(exit0, 진행).
        d = core.decide(_REPORT_EV, _audit_profile(mode="advisory"),
                        snap_audit([self._doc("Final Status: APPROVED")], runs={}), None)
        self.assertEqual(d["message_key"], "warn_report_without_audit")
        self.assertEqual(d["exit_code"], 0)

    def test_enforce_blocks_without_loop_run(self):
        d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                        snap_audit([self._doc("Final Status: APPROVED")], runs={}), None)
        self.assertEqual(d["message_key"], "block_report_without_audit")
        self.assertEqual(d["exit_code"], 2)

    def test_enforce_blocks_run_absent_from_audit(self):
        d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                        snap_audit([self._doc("Final Status: APPROVED\nLoop-Run: run-x1")], runs={}), None)
        self.assertEqual(d["message_key"], "block_report_without_audit")

    def test_enforce_blocks_run_open(self):
        d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                        snap_audit([self._doc("Final Status: APPROVED\nLoop-Run: run-x1")],
                                   runs={"run-x1": {"closed": False, "result": None}}), None)
        self.assertEqual(d["message_key"], "block_report_without_audit")

    def test_enforce_blocks_run_closed_nonapproved(self):
        d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                        snap_audit([self._doc("Final Status: APPROVED\nLoop-Run: run-x1")],
                                   runs={"run-x1": {"closed": True, "result": "BLOCKED"}}), None)
        self.assertEqual(d["message_key"], "block_report_without_audit")

    def test_pass_closed_approved_run(self):
        # APPROVED 마커 + Loop-Run + run closed APPROVED → 통과(L0 ok).
        d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                        snap_audit([self._doc("Final Status: APPROVED\nLoop-Run: run-x1")],
                                   runs={"run-x1": {"closed": True, "result": "APPROVED"}}), None)
        self.assertEqual(d["status"], "ok")
        self.assertNotIn(d["message_key"], ("block_report_without_audit", "warn_report_without_audit"))

    # --- 7차 배치3-5: report_gate_enforce 키 부재 → 기본 advisory ---
    def test_default_advisory_when_key_absent(self):
        import copy
        p = copy.deepcopy(PDCA_PROFILE)
        p["pdca"]["review_loop"] = {"enabled": True}   # report_gate_enforce 미설정
        d = core.decide(_REPORT_EV, p,
                        snap_audit([self._doc("Final Status: APPROVED")], runs={}), None)
        self.assertEqual(d["message_key"], "warn_report_without_audit")   # off 가 아니라 advisory WARN
        self.assertEqual(d["exit_code"], 0)

    # --- 7차 배치3-3: seq 불연속(수기/순서조작) → advisory WARN / enforce BLOCK ---
    def test_seq_ok_false_blocks_enforce(self):
        d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                        snap_audit([self._doc("Final Status: APPROVED\nLoop-Run: run-x1")],
                                   runs={"run-x1": {"closed": True, "result": "APPROVED", "seq_ok": False}}), None)
        self.assertEqual(d["message_key"], "block_report_without_audit")
        self.assertEqual(d["exit_code"], 2)

    def test_seq_ok_false_warns_advisory(self):
        d = core.decide(_REPORT_EV, _audit_profile(mode="advisory"),
                        snap_audit([self._doc("Final Status: APPROVED\nLoop-Run: run-x1")],
                                   runs={"run-x1": {"closed": True, "result": "APPROVED", "seq_ok": False}}), None)
        self.assertEqual(d["message_key"], "warn_report_without_audit")
        self.assertEqual(d["exit_code"], 0)

    def test_seq_ok_none_legacy_passes(self):
        # seq_ok None(레거시) → seq 검사 skip, 나머지 정상이면 통과.
        d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                        snap_audit([self._doc("Final Status: APPROVED\nLoop-Run: run-x1")],
                                   runs={"run-x1": {"closed": True, "result": "APPROVED", "seq_ok": None}}), None)
        self.assertEqual(d["status"], "ok")

    # --- 7차 배치3-4: reviewer degraded(cross-model 폴백) → advisory WARN / enforce BLOCK ---
    def test_degraded_blocks_enforce(self):
        d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                        snap_audit([self._doc("Final Status: APPROVED\nLoop-Run: run-x1")],
                                   runs={"run-x1": {"closed": True, "result": "APPROVED",
                                                    "degraded": True, "reviewer_requested": "cross_model",
                                                    "reviewer_actual": "same_runtime"}}), None)
        self.assertEqual(d["message_key"], "block_report_without_audit")
        self.assertEqual(d["exit_code"], 2)

    def test_degraded_warns_advisory(self):
        d = core.decide(_REPORT_EV, _audit_profile(mode="advisory"),
                        snap_audit([self._doc("Final Status: APPROVED\nLoop-Run: run-x1")],
                                   runs={"run-x1": {"closed": True, "result": "APPROVED",
                                                    "degraded": True, "reviewer_requested": "cross_model",
                                                    "reviewer_actual": "same_runtime"}}), None)
        self.assertEqual(d["message_key"], "warn_report_without_audit")
        self.assertEqual(d["exit_code"], 0)

    def test_marker_on_other_doc_not_selected_fails(self):
        # codex 회귀: ticket 으로 선택된 05 문서엔 APPROVED 없고, 다른 05 에만 APPROVED+Loop-Run.
        # 마커 게이트(any)는 통과하지만 audit 은 selected 문서에 APPROVED 가 없어 fail 해야 한다.
        selected = self._doc("리뷰 진행 ...", path="feature.md")
        other = self._doc("Final Status: APPROVED\nLoop-Run: run-x1", path="b.md")
        runs = {"run-x1": {"closed": True, "result": "APPROVED"}}
        d = core.decide(_REPORT_EV,
                        _audit_profile(mode="enforce"),
                        snap_audit([selected, other], runs=runs), None)
        self.assertEqual(d["message_key"], "block_report_without_approval")

    def test_missing_approval_marker_still_blocks_first(self):
        # 마커 전무 → 기존 block_report_without_approval 가 audit 전에 BLOCK(flag 무관).
        d = core.decide(_REPORT_EV, _audit_profile(mode="advisory"),
                        snap_audit([self._doc("Final Status: FAIL")], runs={}), None)
        self.assertEqual(d["message_key"], "block_report_without_approval")

    def test_fenced_final_status_does_not_approve(self):
        content = "```text\nFinal Status: APPROVED\n```"
        d = core.decide(_REPORT_EV, _audit_profile(mode="off"),
                        snap_audit([self._doc(content)], runs={}), None)
        self.assertEqual(d["message_key"], "block_report_without_approval")

    def test_indented_final_status_does_not_approve(self):
        for label, declaration in (
            ("spaces", "    Final Status: APPROVED"),
            ("tab", "\tFinal Status: APPROVED"),
        ):
            with self.subTest(label=label):
                d = core.decide(_REPORT_EV, _audit_profile(mode="off"),
                                snap_audit([self._doc(declaration)], runs={}), None)
                self.assertEqual(d["message_key"], "block_report_without_approval")

    def test_emphasized_final_status_approves_consistently(self):
        for declaration in (
            "*Final Status:* APPROVED", "*Final Status*: APPROVED", "*Final Status: APPROVED*",
            "**Final Status:** APPROVED", "**Final Status**: APPROVED", "**Final Status: APPROVED**",
            "***Final Status:*** APPROVED", "***Final Status***: APPROVED", "***Final Status: APPROVED***",
            "_Final Status:_ APPROVED", "_Final Status_: APPROVED", "_Final Status: APPROVED_",
            "__Final Status:__ APPROVED", "__Final Status__: APPROVED", "__Final Status: APPROVED__",
            "___Final Status:___ APPROVED", "___Final Status___: APPROVED", "___Final Status: APPROVED___",
        ):
            with self.subTest(declaration=declaration):
                d = core.decide(_REPORT_EV, _audit_profile(mode="off"),
                                snap_audit([self._doc(declaration)], runs={}), None)
                self.assertEqual(d["status"], "ok")

    def test_fenced_or_duplicate_loop_run_does_not_satisfy_audit(self):
        fenced = self._doc("Final Status: APPROVED\n```text\nLoop-Run: run-x1\n```")
        duplicate = self._doc("Final Status: APPROVED\nLoop-Run: run-x1\nLoop-Run: run-x1")
        runs = {"run-x1": {"closed": True, "result": "APPROVED"}}
        for label, phase05 in (("fenced", fenced), ("duplicate", duplicate)):
            with self.subTest(label=label):
                d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                                snap_audit([phase05], runs=runs), None)
                self.assertEqual(d["message_key"], "block_report_without_audit")

    def test_indented_loop_run_does_not_satisfy_audit(self):
        runs = {"run-x1": {"closed": True, "result": "APPROVED"}}
        for label, declaration in (
            ("spaces", "    Loop-Run: run-x1"),
            ("tab", "\tLoop-Run: run-x1"),
        ):
            with self.subTest(label=label):
                phase05 = self._doc(f"Final Status: APPROVED\n{declaration}")
                d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                                snap_audit([phase05], runs=runs), None)
                self.assertEqual(d["message_key"], "block_report_without_audit")

    def test_bold_loop_run_label_satisfies_audit(self):
        runs = {"run-x1": {"closed": True, "result": "APPROVED"}}
        for declaration in (
            "*Loop-Run:* run-x1", "*Loop-Run*: run-x1", "*Loop-Run: run-x1*",
            "**Loop-Run:** run-x1", "**Loop-Run**: run-x1", "**Loop-Run: run-x1**",
            "***Loop-Run:*** run-x1", "***Loop-Run***: run-x1", "***Loop-Run: run-x1***",
            "_Loop-Run:_ run-x1", "_Loop-Run_: run-x1", "_Loop-Run: run-x1_",
            "__Loop-Run:__ run-x1", "__Loop-Run__: run-x1", "__Loop-Run: run-x1__",
            "___Loop-Run:___ run-x1", "___Loop-Run___: run-x1", "___Loop-Run: run-x1___",
        ):
            with self.subTest(declaration=declaration):
                phase05 = self._doc(f"Final Status: APPROVED\n{declaration}")
                d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                                snap_audit([phase05], runs=runs), None)
                self.assertEqual(d["status"], "ok")

    def test_loop_run_normalization_preserves_run_id(self):
        runs = {"rev:123": {"closed": True, "result": "APPROVED"},
                "run/1": {"closed": True, "result": "APPROVED"},
                "run__1": {"closed": True, "result": "APPROVED"},
                "run**1": {"closed": True, "result": "APPROVED"}}
        for run_id in runs:
            with self.subTest(run_id=run_id):
                phase05 = self._doc(f"Final Status: APPROVED\nLoop-Run: {run_id}")
                d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                                snap_audit([phase05], runs=runs), None)
                self.assertEqual(d["status"], "ok")

    def test_enforce_blocks_when_no_cycle_05_doc_selected(self):
        # 05 문서가 없어 _doc_match 가 빈값 → sel None → enforce BLOCK(마커 게이트는 빈 05 라 통과 못하므로
        # 마커가 있는 05 를 두되 recent=False·ticket 불일치로 selection 을 비운다).
        d = core.decide(_REPORT_EV,
                        _audit_profile(mode="enforce"),
                        snap_audit([self._doc("Final Status: APPROVED", recent=False, path="other.md")], runs={}), None)
        self.assertEqual(d["message_key"], "block_report_without_approval")

    def test_run_id_with_nonword_chars_matches(self):
        # codex R1-P1: rev:123 / run/1 같은 비-word run_id 도 게이트가 인식(verbatim).
        d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                        snap_audit([self._doc("Final Status: APPROVED\nLoop-Run: rev:123")],
                                   runs={"rev:123": {"closed": True, "result": "APPROVED"}}), None)
        self.assertEqual(d["status"], "ok")

    def test_enforce_blocks_ambiguous_reused_run(self):
        # codex R2-P1: 재사용/중복으로 clean=False 인 run 은 closed+APPROVED 여도 증거 모호 → BLOCK.
        d = core.decide(_REPORT_EV, _audit_profile(mode="enforce"),
                        snap_audit([self._doc("Final Status: APPROVED\nLoop-Run: run-dup")],
                                   runs={"run-dup": {"closed": True, "result": "APPROVED", "clean": False}}), None)
        self.assertEqual(d["message_key"], "block_report_without_audit")

    def test_advisory_no_audit_records_diagnostic(self):
        # has_any_records=False 일 때 사유에 "audit 기록 자체가 없음" 신호가 들어간다(진단 구분).
        d = core.decide(_REPORT_EV, _audit_profile(mode="advisory"),
                        snap_audit([self._doc("Final Status: APPROVED")], runs={}, has_any=False), None)
        self.assertEqual(d["message_key"], "warn_report_without_audit")
        self.assertIn("audit 기록 자체가 없음", d["reason"])


class TestReportAcceptanceGate(unittest.TestCase):
    def test_pending_gate_selection_preserves_all_advisory_reasons(self):
        decisions = [
            {"status": "warn", "message_key": "warn_report_with_l3_waiver",
             "reason": "acceptance residual"},
            {"status": "warn", "message_key": "warn_report_without_audit",
             "reason": "loop audit missing"},
        ]

        selected = core._select_pending_gate_decision(decisions)

        self.assertEqual(selected["message_key"], "warn_report_with_l3_waiver")
        self.assertIn("acceptance residual", selected["reason"])
        self.assertIn("loop audit missing", selected["reason"])

    """06←04 acceptance evidence gate — 명시 요구사항별 미구현/미검증 상태를 report 전에 드러낸다."""

    def _matrix(self, rows=None):
        rows = rows or [("| A1 | Korean city search | test | qa | yes |"),
                        ("| A2 | notification | test | qa | yes |")]
        return "\n".join([
            "## Acceptance Matrix",
            "| ID | User Requirement | Required Evidence | Owner | Required? |",
            "|---|---|---|---|---|",
            *rows,
        ])

    def _snap(self, content04, content05="Final Status: APPROVED", recent04=True, content01=None):
        def bound(content):
            return f"Cycle-Stem: `feature`\n{content}"
        return {
            "plan_files": [],
            "review_candidates": [],
            "phase_docs": {
                "01": [{"path": "feature.md", "content": bound(content01 or self._matrix()), "recent": True}],
                "04": [{"path": "feature.md", "content": bound(content04), "recent": recent04}],
                "05": [{"path": "feature.md", "content": bound(content05), "recent": True}],
            },
        }

    def test_disabled_is_marker_only(self):
        d = core.decide(_REPORT_EV, _acceptance_profile(enabled=False),
                        self._snap("no acceptance table"), None)
        self.assertEqual(d["status"], "ok")

    def test_advisory_warns_when_acceptance_table_missing(self):
        report_ev = ev("plan_docs/06-report/feature.md", "Cycle-Stem: `feature`\n", declared="L2")
        d = core.decide(report_ev, _acceptance_profile(mode="advisory"),
                        self._snap("## Coverage\nno table"), None)
        self.assertEqual(d["message_key"], "warn_report_without_acceptance")
        self.assertEqual(d["exit_code"], 0)

    def test_enforce_blocks_when_acceptance_table_missing(self):
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                        self._snap("## Coverage\nno table"), None)
        self.assertEqual(d["message_key"], "block_report_without_acceptance")
        self.assertEqual(d["exit_code"], 2)

    def test_fenced_acceptance_tables_do_not_count_as_evidence(self):
        fenced04 = """## Acceptance Evidence
```markdown
| ID | Status | Evidence |
|---|---|---|
| A1 | PASS | fake |
| A2 | PASS | fake |
```
"""
        fenced01 = """## Acceptance Matrix
```markdown
| ID | Required? |
|---|---|
| A1 | yes |
```
"""
        blocked04 = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                                self._snap(fenced04), None)
        blocked01 = core.decide(
            _REPORT_EV, _acceptance_profile(mode="enforce"),
            self._snap("## Acceptance Evidence\n| ID | Status |\n|---|---|\n| A1 | PASS |",
                       content01=fenced01), None)
        self.assertEqual(blocked04["message_key"], "block_report_without_acceptance")
        self.assertEqual(blocked01["message_key"], "block_report_without_acceptance")

    def test_indented_acceptance_tables_do_not_count_as_evidence(self):
        indented04 = """## Acceptance Evidence
    | ID | Status | Evidence |
    |---|---|---|
    | A1 | PASS | fake |
    | A2 | PASS | fake |
"""
        indented01 = """## Acceptance Matrix
    | ID | Required? |
    |---|---|
    | A1 | yes |
"""
        blocked04 = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                                self._snap(indented04), None)
        blocked01 = core.decide(
            _REPORT_EV, _acceptance_profile(mode="enforce"),
            self._snap("## Acceptance Evidence\n| ID | Status |\n|---|---|\n| A1 | PASS |",
                       content01=indented01), None)
        self.assertEqual(blocked04["message_key"], "block_report_without_acceptance")
        self.assertEqual(blocked01["message_key"], "block_report_without_acceptance")

    def test_enforce_blocks_unresolved_acceptance(self):
        content04 = """## Acceptance Evidence
| ID | Requirement | Status | Evidence |
|---|---|---|---|
| A1 | Korean city search | NOT TESTED | no e2e |
| A2 | notification | FAIL | manual smoke failed |
"""
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                        self._snap(content04), None)
        self.assertEqual(d["message_key"], "block_report_without_acceptance")
        self.assertIn("NOT TESTED", d["reason"])
        self.assertIn("FAIL", d["reason"])

    def test_passes_when_all_required_acceptance_resolved(self):
        content04 = """## Acceptance Evidence
| ID | Requirement | Status | Evidence |
|---|---|---|---|
| A1 | Korean city search must not fail | PASS | test + manual smoke |
| A2 | notification | PASS | worker test |
"""
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                        self._snap(content04), None)
        self.assertEqual(d["status"], "ok")
        self.assertNotIn(d["message_key"], ("block_report_without_acceptance", "warn_report_without_acceptance"))

    def test_optional_unresolved_acceptance_does_not_block(self):
        matrix = self._matrix(rows=[
            "| A1 | required | test | qa | yes |",
            "| A2 | optional | test | qa | no |",
        ])
        content04 = """## Acceptance Evidence
| ID | Status |
|---|---|
| A1 | PASS |
| A2 | NOT TESTED |
"""
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                        self._snap(content04, content01=matrix), None)
        self.assertEqual(d["status"], "ok")

    def test_all_optional_acceptance_matrix_is_valid(self):
        matrix = self._matrix(rows=["| A1 | optional | test | qa | no |"])
        content04 = """## Acceptance Evidence
| ID | Status |
|---|---|
| A1 | NOT TESTED |
"""
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                        self._snap(content04, content01=matrix), None)
        self.assertEqual(d["status"], "ok")

    def test_required_na_requires_explicit_reason(self):
        missing = """## Acceptance Evidence
| ID | Status | Evidence |
|---|---|---|
| A1 | N/A | |
| A2 | PASS | test |
"""
        explained = missing.replace("| A1 | N/A | |", "| A1 | N/A | user-approved deferred scope |")
        blocked = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                              self._snap(missing), None)
        passed = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                             self._snap(explained), None)
        self.assertEqual(blocked["message_key"], "block_report_without_acceptance")
        self.assertIn("N/A 사유 누락", blocked["reason"])
        self.assertEqual(passed["status"], "ok")

        placeholder = missing.replace("| A1 | N/A | |", "| A1 | N/A | N/A |")
        placeholder_result = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                                         self._snap(placeholder), None)
        self.assertEqual(placeholder_result["message_key"], "block_report_without_acceptance")

    def test_cycle_risk_uses_maximum_bound_declaration(self):
        snap = self._snap("## Acceptance Evidence\n| ID | Status |\n|---|---|\n| A1 | FAIL |\n| A2 | PASS |")
        snap["phase_docs"]["00"] = [{
            "path": "feature.md", "content": "Cycle-Stem: `feature`\nRisk Level: L1\n",
        }]
        snap["phase_docs"]["03"] = [{
            "path": "feature.md", "content": "Cycle-Stem: `feature`\nRisk Level: L3\n",
        }]
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"), snap, None)
        self.assertEqual(d["message_key"], "block_report_without_acceptance")
        self.assertIn("A1", d["reason"])

    def test_cycle_risk_recognizes_bold_label(self):
        for declaration in (
            "*Risk Level:* L3", "*Risk Level*: L3", "*Risk Level: L3*",
            "**Risk Level:** L3", "**Risk Level**: L3", "**Risk Level: L3**",
            "***Risk Level:*** L3", "***Risk Level***: L3", "***Risk Level: L3***",
            "_Risk Level:_ L3", "_Risk Level_: L3", "_Risk Level: L3_",
            "__Risk Level:__ L3", "__Risk Level__: L3", "__Risk Level: L3__",
            "___Risk Level:___ L3", "___Risk Level___: L3", "___Risk Level: L3___",
        ):
            with self.subTest(declaration=declaration):
                snap = self._snap("## Acceptance Evidence\n| ID | Status |\n|---|---|\n| A1 | PASS |\n| A2 | PASS |")
                snap["phase_docs"]["00"] = [{
                    "path": "feature.md",
                    "content": f"Cycle-Stem: `feature`\nRisk Level: L1\n{declaration}\n",
                }]
                self.assertEqual(core._cycle_risk(_REPORT_EV, _acceptance_profile(), snap,
                                                  _acceptance_profile()["pdca"]), "L3")

    def test_unparseable_risk_like_label_fails_closed(self):
        snap = self._snap("## Acceptance Evidence\n| ID | Status |\n|---|---|\n| A1 | PASS |\n| A2 | PASS |")
        snap["phase_docs"]["00"] = [{
            "path": "feature.md",
            "content": "Cycle-Stem: `feature`\nRisk Level: L1\nRisk Level [custom]: L3\n",
        }]
        self.assertEqual(core._cycle_risk(_REPORT_EV, _acceptance_profile(), snap,
                                          _acceptance_profile()["pdca"]), "unknown")

    def test_acceptance_enforce_precedes_audit_advisory(self):
        # acceptance enforce 가 audit advisory warning 에 가려지면 핵심 요구사항 실패가 report 로 통과한다.
        p = _acceptance_profile(mode="enforce")
        p["pdca"]["review_loop"] = {"enabled": True, "report_gate_enforce": "advisory"}
        snap = self._snap("## Acceptance Evidence\n| ID | Status |\n|---|---|\n| A1 | FAIL |\n| A2 | PASS |")
        snap["loop_audit"] = {"runs": {}, "has_any_records": False}
        d = core.decide(_REPORT_EV, p, snap, None)
        self.assertEqual(d["message_key"], "block_report_without_acceptance")

    def test_audit_enforce_precedes_acceptance_advisory(self):
        p = _acceptance_profile(mode="advisory")
        p["pdca"]["review_loop"] = {"enabled": True, "report_gate_enforce": "enforce"}
        snap = self._snap("## Coverage\nno acceptance table")
        snap["loop_audit"] = {"runs": {}, "has_any_records": False}
        report_ev = ev("plan_docs/06-report/feature.md", "Cycle-Stem: `feature`\n", declared="L2")
        d = core.decide(report_ev, p, snap, None)
        self.assertEqual(d["message_key"], "block_report_without_audit")
        self.assertEqual(d["exit_code"], 2)

    def test_ignores_unrelated_tables_and_free_text_fail(self):
        # status 컬럼이 아니라 요구사항/증거 문장의 "fail" 을 잡으면 false positive.
        content04 = """## Coverage Verification
| Check | Status |
|---|---|
| build | FAIL |

## Acceptance Evidence
| ID | Requirement | Status | Evidence |
|---|---|---|---|
| A1 | Korean city search must not fail | PASS | manual smoke says no fail wording matters |
| A2 | notification | PASS | worker test |
"""
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                        self._snap(content04), None)
        self.assertEqual(d["status"], "ok")

    def test_enforce_blocks_missing_matrix_id_in_04(self):
        content04 = """## Acceptance Evidence
| ID | Requirement | Status | Evidence |
|---|---|---|---|
| A1 | Korean city search | PASS | manual smoke |
"""
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                        self._snap(content04), None)
        self.assertEqual(d["message_key"], "block_report_without_acceptance")
        self.assertIn("A2", d["reason"])

    def test_enforce_blocks_unknown_evidence_id(self):
        content04 = """## Acceptance Evidence
| ID | Status |
|---|---|
| A1 | PASS |
| A2 | PASS |
| STALE | PASS |
"""
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"), self._snap(content04), None)
        self.assertEqual(d["message_key"], "block_report_without_acceptance")
        self.assertIn("미정의 ID", d["reason"])
        self.assertIn("STALE", d["reason"])

    def test_enforce_blocks_duplicate_evidence_id(self):
        content04 = """## Acceptance Evidence
| ID | Status |
|---|---|
| A1 | PASS |
| A1 | PASS |
| A2 | PASS |
"""
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"), self._snap(content04), None)
        self.assertEqual(d["message_key"], "block_report_without_acceptance")
        self.assertIn("duplicate ID", d["reason"])

    def test_enforce_blocks_duplicate_matrix_id(self):
        matrix = self._matrix(rows=[
            "| A1 | first | test | qa | yes |",
            "| A1 | duplicate | test | qa | yes |",
        ])
        content04 = """## Acceptance Evidence
| ID | Status |
|---|---|
| A1 | PASS |
"""
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                        self._snap(content04, content01=matrix), None)
        self.assertEqual(d["message_key"], "block_report_without_acceptance")
        self.assertIn("duplicate acceptance ID", d["reason"])

    def test_enforce_blocks_malformed_acceptance_id(self):
        matrix = self._matrix(rows=["| A 1 | malformed | test | qa | yes |"])
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"),
                        self._snap("## Acceptance Evidence\n| ID | Status |\n|---|---|\n| A1 | PASS |",
                                   content01=matrix), None)
        self.assertEqual(d["message_key"], "block_report_without_acceptance")
        self.assertIn("invalid acceptance ID", d["reason"])

    def test_acceptance_selects_same_stem_not_recent_other_cycle(self):
        snap = self._snap("## Acceptance Evidence\n| ID | Status |\n|---|---|\n| A1 | FAIL |\n| A2 | PASS |")
        snap["phase_docs"]["04"].append({
            "path": "other.md", "recent": True,
            "content": "Cycle-Stem: `other`\n## Acceptance Evidence\n| ID | Status |\n|---|---|\n| A1 | PASS |\n| A2 | PASS |",
        })
        d = core.decide(_REPORT_EV, _acceptance_profile(mode="enforce"), snap, None)
        self.assertEqual(d["message_key"], "block_report_without_acceptance")
        self.assertIn("A1", d["reason"])

    def test_require_for_risk_skips_known_l1_cycle(self):
        content04 = """## Acceptance Evidence
| ID | Status |
|---|---|
| A1 | FAIL |
"""
        d = core.decide(ev("plan_docs/06-report/feature.md", declared="L1"),
                        _acceptance_profile(mode="enforce"), self._snap(content04), None)
        self.assertNotIn(d["message_key"], ("block_report_without_acceptance", "warn_report_without_acceptance"))

    def test_risk_defaults_are_l2_advisory_and_l3_unknown_enforce(self):
        content04 = """## Acceptance Evidence
| ID | Status | Evidence |
|---|---|---|
| A1 | NOT TESTED | production only |
| A2 | PASS | test |
"""
        profile = _risk_acceptance_profile(waiver_enabled=False)
        l2 = core.decide(ev("plan_docs/06-report/feature.md", "Cycle-Stem: `feature`\n", declared="L2"), profile,
                         self._snap(content04), None)
        unknown = core.decide(_REPORT_EV, profile, self._snap(content04), None)
        self.assertEqual(l2["message_key"], "warn_report_without_acceptance")
        self.assertEqual(unknown["message_key"], "block_report_without_acceptance")

        defaults = _risk_acceptance_profile(waiver_enabled=False)
        defaults["verification"]["acceptance"].pop("report_gate_by_risk")
        default_l2 = core.decide(ev("plan_docs/06-report/feature.md", "Cycle-Stem: `feature`\n", declared="L2"), defaults,
                                 self._snap(content04), None)
        default_unknown = core.decide(_REPORT_EV, defaults, self._snap(content04), None)
        self.assertEqual(default_l2["message_key"], "warn_report_without_acceptance")
        self.assertEqual(default_unknown["message_key"], "block_report_without_acceptance")

    def test_exact_l3_not_tested_waiver_warns_and_preserves_residual(self):
        content04 = """## Acceptance Evidence
| ID | Status | Evidence |
|---|---|---|
| A1 | NOT TESTED | production only |
| A2 | PASS | test |
"""
        snap = self._snap(content04)
        snap["phase_docs"]["00"] = [{"path": "feature.md", "content": "Cycle-Stem: `feature`\nRisk Level: L3\n"}]
        grant = {"waiver_id": "aw-1", "cycle_stem": "feature", "acceptance_id": "A1",
                 "reason": "production only", "scope": "single smoke",
                 "remaining_evidence": "live callback", "confirmed_by": "sejon"}
        snap["acceptance_waivers"] = {"valid": True, "issues": [], "active": [grant]}
        decision = core.decide(_REPORT_EV, _risk_acceptance_profile(), snap, None)
        self.assertEqual(decision["message_key"], "warn_report_with_l3_waiver")
        self.assertEqual(decision["status"], "warn")
        self.assertIn("NOT TESTED", decision["reason"])
        self.assertEqual(decision["waiver_uses"], [dict(grant, report_path="feature.md")])

    def test_waiver_is_exact_and_never_applies_to_fail(self):
        grant = {"waiver_id": "aw-1", "cycle_stem": "feature", "acceptance_id": "A1",
                 "reason": "production only", "scope": "single smoke",
                 "remaining_evidence": "live callback", "confirmed_by": "sejon"}
        for status, acceptance_id in (("NOT TESTED", "A2"), ("FAIL", "A1")):
            with self.subTest(status=status, acceptance_id=acceptance_id):
                content04 = f"""## Acceptance Evidence
| ID | Status | Evidence |
|---|---|---|
| A1 | {status} | production only |
| A2 | PASS | test |
"""
                snap = self._snap(content04)
                snap["acceptance_waivers"] = {
                    "valid": True, "issues": [], "active": [dict(grant, acceptance_id=acceptance_id)]}
                decision = core.decide(_REPORT_EV, _risk_acceptance_profile(), snap, None)
                self.assertEqual(decision["message_key"], "block_report_without_acceptance")

    def test_invalid_waiver_audit_cannot_downgrade_l3(self):
        content04 = """## Acceptance Evidence
| ID | Status | Evidence |
|---|---|---|
| A1 | NOT TESTED | production only |
| A2 | PASS | test |
"""
        snap = self._snap(content04)
        snap["phase_docs"]["00"] = [{"path": "feature.md", "content": "Cycle-Stem: `feature`\nRisk Level: L3\n"}]
        snap["acceptance_waivers"] = {"valid": False, "issues": ["malformed line"], "active": []}
        decision = core.decide(_REPORT_EV, _risk_acceptance_profile(), snap, None)
        self.assertEqual(decision["message_key"], "block_report_without_acceptance")
        self.assertIn("waiver audit invalid", decision["reason"])

    def test_invalid_profile_cannot_downgrade_l3_at_runtime(self):
        content04 = """## Acceptance Evidence
| ID | Status |
|---|---|
| A1 | NOT TESTED |
| A2 | PASS |
"""
        profile = _risk_acceptance_profile(waiver_enabled=False)
        profile["verification"]["acceptance"]["report_gate_by_risk"]["L3"] = "advisory"
        decision = core.decide(_REPORT_EV, profile, self._snap(content04), None)
        self.assertEqual(decision["message_key"], "block_report_without_acceptance")

    def test_require_for_risk_cannot_disable_l3_at_runtime(self):
        content04 = """## Acceptance Evidence
| ID | Status |
|---|---|
| A1 | NOT TESTED |
| A2 | PASS |
"""
        profile = _risk_acceptance_profile(waiver_enabled=False)
        profile["verification"]["acceptance"]["require_for_risk"] = ["L2"]
        snap = self._snap(content04)
        snap["phase_docs"]["00"] = [{
            "path": "feature.md", "content": "Cycle-Stem: `feature`\nRisk Level: L3\n",
        }]
        decision = core.decide(_REPORT_EV, profile, snap, None)
        self.assertEqual(decision["message_key"], "block_report_without_acceptance")

    def test_malformed_acceptance_profile_values_fail_closed_without_crash(self):
        content04 = """## Acceptance Evidence
| ID | Status |
|---|---|
| A1 | NOT TESTED |
| A2 | PASS |
"""
        snap = self._snap(content04)
        snap["phase_docs"]["00"] = [{
            "path": "feature.md", "content": "Cycle-Stem: `feature`\nRisk Level: L3\n",
        }]
        for field, value in (("require_for_risk", [{"L3": True}]),
                             ("statuses", 5),
                             ("unresolved_statuses", 7),
                             ("unresolved_statuses", ["FAIL"])):
            with self.subTest(field=field, value=value):
                profile = _risk_acceptance_profile(waiver_enabled=False)
                profile["verification"]["acceptance"][field] = value
                decision = core.decide(_REPORT_EV, profile, snap, None)
                self.assertEqual(decision["message_key"], "block_report_without_acceptance")

    def test_custom_profile_status_is_unresolved_at_runtime(self):
        content04 = """## Acceptance Evidence
| ID | Status |
|---|---|
| A1 | SKIPPED |
| A2 | PASS |
"""
        profile = _risk_acceptance_profile(waiver_enabled=False)
        profile["verification"]["acceptance"]["statuses"].append("SKIPPED")
        snap = self._snap(content04)
        snap["phase_docs"]["00"] = [{
            "path": "feature.md", "content": "Cycle-Stem: `feature`\nRisk Level: L3\n",
        }]
        decision = core.decide(_REPORT_EV, profile, snap, None)
        self.assertEqual(decision["message_key"], "block_report_without_acceptance")
        self.assertIn("SKIPPED", decision["reason"])

    def test_legacy_off_or_advisory_cannot_downgrade_l3(self):
        content04 = """## Acceptance Evidence
| ID | Status |
|---|---|
| A1 | NOT TESTED |
| A2 | PASS |
"""
        for mode in ("off", "advisory"):
            with self.subTest(mode=mode):
                decision = core.decide(_REPORT_EV, _acceptance_profile(mode=mode),
                                       self._snap(content04), None)
                self.assertEqual(decision["message_key"], "block_report_without_acceptance")

    def test_legacy_enforce_still_blocks_declared_l2(self):
        content04 = """## Acceptance Evidence
| ID | Status |
|---|---|
| A1 | NOT TESTED |
| A2 | PASS |
"""
        report_ev = ev("plan_docs/06-report/feature.md", "Cycle-Stem: `feature`\n", declared="L2")
        decision = core.decide(report_ev, _acceptance_profile(mode="enforce"),
                               self._snap(content04), None)
        self.assertEqual(decision["message_key"], "block_report_without_acceptance")


class TestStrategies(unittest.TestCase):
    def test_grep_first(self):
        r = claude_grep_first.find_l3_review({}, snap(review=[{"path": "a.md", "content": "Round 1 review 완료"}]))
        self.assertTrue(r["found"])
        self.assertFalse(claude_grep_first.find_l3_review({}, snap(review=[{"path": "b.md", "content": "무관"}]))["found"])

    def test_grep_first_inline_flag_patterns(self):
        # F8a: profile review_patterns 에 인라인 (?i) 가 있어도 크래시 없이 매칭(개별 컴파일).
        # 이전엔 join 후 단일 컴파일 → 중간 글로벌 플래그로 re.error → 전략 크래시 → L3 영구 BLOCK.
        r = claude_grep_first.find_l3_review(
            {"review_patterns": ["(?i)location", "(?i)api[_]?key"]},
            snap(review=[{"path": "a.md", "content": "현재 LOCATION 처리 점검"}]))
        self.assertTrue(r["found"])

    def test_grep_first_malformed_pattern_skipped(self):
        # F8a: 무효한 개별 패턴은 skip — default 마커로 여전히 매칭(한 패턴 오류가 게이트 전체를 죽이지 않음).
        r = claude_grep_first.find_l3_review(
            {"review_patterns": ["[unclosed"]},
            snap(review=[{"path": "a.md", "content": "Round 1 review 완료"}]))
        self.assertTrue(r["found"])

    def test_feature_signal(self):
        r = codex_feature_signal.find_l3_review(
            {"files": ["recording"]}, snap(review=[{"path": "recording_review.md", "content": "recording 기능 review"}]))
        self.assertTrue(r["found"])


def run_adapter(runtime, raw, root):
    env_root = "CLAUDE_PROJECT_DIR" if runtime == "claude" else "CODEX_PROJECT_ROOT"
    env = dict(os.environ, **{env_root: root, "SAGE_HOOK_CORE_DIR": HOOKS_DIR,
                              "SAGE_PROFILE": PROFILE_PATH, "SAGE_GATE_BRANCH": "main"})
    adapter = os.path.join(ADAPTERS, runtime, "pre-implementation-gate.sh")
    return subprocess.run(["bash", adapter], input=json.dumps(raw), capture_output=True, text=True, env=env)


class TestAdapters(unittest.TestCase):
    def test_l3_block_both(self):
        for runtime, raw in [
            ("claude", {"tool_name": "Write", "tool_input": {"file_path": "a/payment.java"}, "session_id": "t"}),
            ("codex", {"tool_name": "apply_patch", "tool_input": {"command": "*** Add File: a/payment.java\n+x\n"}, "session_id": "t"}),
        ]:
            with tempfile.TemporaryDirectory() as root:
                p = run_adapter(runtime, raw, root)
                self.assertEqual(p.returncode, 2, f"{runtime} L3 no-plan block")

    def test_l1_pass_both(self):
        for runtime, raw in [
            ("claude", {"tool_name": "Write", "tool_input": {"file_path": "frontend/static/js/x.js"}, "session_id": "t"}),
            ("codex", {"tool_name": "apply_patch", "tool_input": {"command": "*** Add File: frontend/static/js/x.js\n+x\n"}, "session_id": "t"}),
        ]:
            with tempfile.TemporaryDirectory() as root:
                p = run_adapter(runtime, raw, root)
                self.assertEqual(p.returncode, 0, f"{runtime} L1 pass")


if __name__ == "__main__":
    unittest.main(verbosity=2)
