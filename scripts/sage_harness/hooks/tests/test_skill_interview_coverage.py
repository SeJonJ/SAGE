#!/usr/bin/env python3
"""EH-18 conformance: sage-init/sage-profile-modify/bootstrap-authoring.md must keep naming
the schema keys they are responsible for raising or documenting.

These are not behavior tests (SKILL.md is a prompt, not code) — they are drift guards. If a
future edit strips one of these mentions, the interview silently regresses to the same gap
EH-18 fixed, and nothing else would catch it.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SAGE_INIT = ROOT / "templates/core/framework/.claude/skills/sage-init/SKILL.md"
PROFILE_MODIFY = ROOT / "templates/core/framework/.claude/skills/sage-profile-modify/SKILL.md"
BOOTSTRAP_AUTHORING = ROOT / "templates/core/framework/docs/agent/bootstrap-authoring.md"
SKILLS = ROOT / "templates/core/framework/.claude/skills"


class TestSkillInterviewCoverage(unittest.TestCase):
    def test_sage_init_raises_active_host(self):
        text = SAGE_INIT.read_text(encoding="utf-8")
        self.assertIn("runtime.active_host", text)

    def test_sage_init_raises_feedback(self):
        text = SAGE_INIT.read_text(encoding="utf-8")
        self.assertIn("feedback.*", text)
        self.assertIn("block_release", text)
        self.assertIn("`record`", text)

    def test_sage_init_raises_acceptance(self):
        text = SAGE_INIT.read_text(encoding="utf-8")
        self.assertIn("verification.acceptance", text)

    def test_sage_init_raises_checklist_scan_targets(self):
        text = SAGE_INIT.read_text(encoding="utf-8")
        self.assertIn("checklist_scan_targets", text)

    def test_sage_init_raises_l2_content_keywords(self):
        text = SAGE_INIT.read_text(encoding="utf-8")
        self.assertIn("l2_content_keywords", text)

    def test_cycle_binding_visibility_has_a_documented_owner(self):
        # EH-15/16 은 인터뷰 대상이 아니다(기본값이 옳고 all 은 비용을 아는 사람이 켠다).
        # 그렇다면 사후 편집 경로와 "왜 안 묻는가"가 반드시 문서에 있어야 EH-18 이 고친
        # "스키마에는 있는데 대화 경로가 없는 키" 로 되돌아가지 않는다.
        self.assertIn("pdca.cycle_binding_visibility",
                      PROFILE_MODIFY.read_text(encoding="utf-8"))
        self.assertIn("pdca.cycle_binding_visibility",
                      BOOTSTRAP_AUTHORING.read_text(encoding="utf-8"))

    def test_profile_modify_lists_conventions(self):
        text = PROFILE_MODIFY.read_text(encoding="utf-8")
        self.assertIn("`conventions`", text)

    def test_the_two_new_opt_ins_are_raised_and_default_off(self):
        """스키마에만 있고 대화 경로가 없는 키를 다시 만들지 않는다.

        두 옵트인은 게이트를 **느슨하게** 하는 쪽이라, 인터뷰가 조용히 빠지면 사용자가
        모르는 채로 켜지거나(더 나쁘게는) 기본값이 무엇인지 아무도 모르게 된다.
        """
        bootstrap = BOOTSTRAP_AUTHORING.read_text(encoding="utf-8")
        init = SAGE_INIT.read_text(encoding="utf-8")
        modify = PROFILE_MODIFY.read_text(encoding="utf-8")
        for key in ("pdca.review_loop.early_completion", "pdca.fast_cycle.standard_transition"):
            with self.subTest(key=key):
                self.assertIn(key, bootstrap)
                self.assertIn(key, init)
        self.assertIn("standard_transition", modify)
        self.assertIn("early_completion", modify)
        # 기본값이 off 라는 것이 문항 자체에 적혀 있어야 한다.
        self.assertIn("default off — `pdca.review_loop.early_completion`", bootstrap)
        self.assertIn("default off —\n`pdca.fast_cycle.standard_transition`", bootstrap)

    def test_the_interview_forbids_inferring_the_confirmation(self):
        """확인 토큰·사유·승인자를 스킬이 스스로 채우면 두 기능의 담보가 통째로 사라진다.

        profile 에서 기능을 켠 것은 개별 실행의 승인이 아니다 — 그 구분이 문서에 남아 있어야 한다.
        """
        bootstrap = BOOTSTRAP_AUTHORING.read_text(encoding="utf-8")
        self.assertIn("Never infer the authorization.", bootstrap)
        self.assertIn("Never infer the conversion.", bootstrap)
        modify = PROFILE_MODIFY.read_text(encoding="utf-8")
        self.assertIn("the feature is not the authorization", modify)
        self.assertIn("the feature is not the confirmation", modify)

    def test_the_fast_and_review_skills_carry_the_new_commands(self):
        """배포되는 것은 spec 이 아니라 렌더다 — 렌더에 없으면 host 실행에 없는 것이다."""
        plan_fast = (SKILLS / "sage-plan-fast" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("sage fast-cycle convert", plan_fast)
        self.assertIn("--confirm FAST-CONVERTED", plan_fast)
        self.assertIn("standard_transition", plan_fast)
        review = (SKILLS / "sage-review" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("--survived-by-severity", review)
        self.assertIn("USER_AUTHORIZED_EARLY", review)
        self.assertIn("REDUCED_BY_USER_AUTHORIZATION", review)
        cycle_fast = (SKILLS / "sage-cycle-fast" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("standard_transition", cycle_fast)

    def test_the_skill_that_runs_a_converted_fast_run_knows_the_mode(self):
        """전환 run 을 실제로 실행하는 것은 team-fast 다. 모드를 모르면 계약을 지키려는 host 조차
        composite 도 `Fast-Audit-Run` 도 없는 문서에 그것들을 만들어 넣는다."""
        team_fast = (SKILLS / "sage-team-fast" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("FAST-CONVERTED", team_fast)
        self.assertIn("entry=", team_fast)
        self.assertIn("Review-Assurance", team_fast)

    def test_a_disabled_opt_in_has_a_stated_next_move(self):
        """금지문만 있고 대안 행동이 없으면, 막힌 host 에게 남는 가장 자연스러운 수는
        profile 을 켜서 여는 것이다 — 그건 이 실행에 대한 승인이 아니다."""
        for name in ("sage-review", "sage-plan-fast", "sage-cycle"):
            # 줄바꿈을 넘지 않는 조각으로 본다 — 문장이 감기면 전체 문구 매칭은 조용히 깨진다.
            text = " ".join((SKILLS / name / "SKILL.md").read_text(encoding="utf-8").split())
            with self.subTest(skill=name):
                self.assertIn("propose editing the profile", text)

    def test_the_approver_is_not_taken_from_metadata(self):
        """확인 토큰은 프롬프트에 리터럴로 있어 host 가 언제든 낼 수 있다. 실질 담보는
        사유와 승인자뿐인데, 승인자의 정의가 없으면 git/profile 에서 끌어와도 금지문에 안 걸린다."""
        for name in ("sage-review", "sage-plan-fast"):
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=name):
                self.assertIn("git config", text)

    def test_the_reduced_assurance_markers_are_never_translated(self):
        """`Document-Language: ko` 사이클에서 라벨을 번역하면 게이트가 표기를 0개로 읽는다."""
        for relative in ("templates/core/framework/docs/agent/language-policy.md",
                         "templates/core/framework/docs/agent/pdca-templates.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(document=relative):
                for label in ("Review-Assurance", "Review-Close-Reason",
                              "Review-Rounds", "Residual-Findings"):
                    self.assertIn(label, text)
                self.assertIn("REDUCED_BY_USER_AUTHORIZATION", text)

    def test_the_consequence_table_carries_both_new_toggles(self):
        """하드 룰과 Step 2 가 가리키는 것은 표다 — 산문에만 있으면 체크리스트에서 빠진다."""
        text = PROFILE_MODIFY.read_text(encoding="utf-8")
        table = text[text.index("| change | consequence to surface |"):]
        self.assertIn("early_completion.enabled", table)
        self.assertIn("standard_transition.enabled", table)

    def test_bootstrap_authoring_documents_inert_runtime_fields(self):
        text = BOOTSTRAP_AUTHORING.read_text(encoding="utf-8")
        self.assertIn("runtime.asset_ssot", text)
        self.assertIn("runtime.external_reviewer", text)

    def test_bootstrap_authoring_documents_compaction_as_advanced(self):
        text = BOOTSTRAP_AUTHORING.read_text(encoding="utf-8")
        self.assertIn("context_management.compaction", text)


if __name__ == "__main__":
    unittest.main()
