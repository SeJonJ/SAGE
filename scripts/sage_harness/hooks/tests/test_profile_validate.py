#!/usr/bin/env python3
"""profile_validate 단위 (외부검토 R2/P0-2 — 게이트 침묵 비활성 차단).

핵심 teeth: `l3_filename_globs`→`l3_filename_glob` 오타가 schema(additionalProperties:false)로 FAIL.
+ 의미검증(전략 모듈 부재·미정의 phase 참조 FAIL / 위험 글롭 전무 INFO).
schema 검증은 jsonschema 선택의존 — 미설치면 schema 의존 테스트 skip(의미검증은 항상 동작).
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.profile_validate import severity_of, validate_profile  # noqa: E402

try:
    import jsonschema  # noqa: F401
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


def sevs(profile):
    return validate_profile(profile, REPO)   # REPO 에 schema/ 와 strategies/ 존재


@unittest.skipUnless(_HAS_JSONSCHEMA, "jsonschema 미설치 — schema 검증 skip")
class TestProfileSchema(unittest.TestCase):
    def test_clean_profile_no_fail(self):
        prof = {"risk": {"l3_filename_globs": ["*secret*"], "l3_review_strategy": "claude_grep_first"},
                "pdca": {"phases": [{"id": "00", "glob": "x"}], "pre_implementation_required": {"L3": ["00"]}}}
        self.assertNotIn("FAIL", [s for s, _ in sevs(prof)])

    def test_singular_typo_in_risk_is_fail(self):
        # P0-2 핵심 시나리오: 단수 오타 → core 가 조용히 빈 리스트 → L3 침묵 비활성. schema 가 적발.
        issues = sevs({"risk": {"l3_filename_glob": ["*secret*"]}})
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("l3_filename_glob" in m for _, m in issues))

    def test_top_level_typo_is_fail(self):
        self.assertEqual(severity_of(sevs({"file_type_maps": []})), "FAIL")   # file_type_map 오타

    def test_risk_trigger_array_items_must_be_nonempty_strings(self):
        for bad in (["ok", 1], [""], ["   "]):
            with self.subTest(bad=bad):
                self.assertEqual(severity_of(sevs({"risk": {"l3_filename_globs": bad}})), "FAIL")

    def test_domain_trigger_array_items_must_be_nonempty_strings(self):
        base = {"id": "auth", "risk_level": "L3", "protocol_pointer": "sage/auth.md"}
        for field, bad in (("path_globs", [""]), ("content_keywords", ["   "]),
                           ("path_globs", ["ok", 1])):
            with self.subTest(field=field, bad=bad):
                domain = dict(base)
                domain[field] = bad
                self.assertEqual(severity_of(sevs({"risk": {"domains": [domain]}})), "FAIL")

    def test_domain_trigger_fields_remain_optional_in_schema(self):
        domain = {"id": "auth", "risk_level": "L3", "protocol_pointer": "sage/auth.md"}
        self.assertNotIn("FAIL", [severity for severity, _ in sevs({"risk": {"domains": [domain]}})])


class TestProfileSemantic(unittest.TestCase):
    def test_non_mapping_risk_type_has_one_semantic_owner(self):
        messages = [message for severity, message in sevs({"risk": "bad"})
                    if severity == "FAIL" and "risk 섹션은 매핑" in message]
        self.assertEqual(len(messages), 1)

    def test_scalar_risk_trigger_fails_without_relying_on_jsonschema(self):
        for field in ("l0_pass_globs", "l0_exclude_globs", "l1_path_globs", "l2_path_globs",
                      "l3_filename_globs", "l2_content_keywords", "l3_content_keywords"):
            with self.subTest(field=field):
                issues = sevs({"risk": {field: "auth"}})
                self.assertEqual(severity_of(issues), "FAIL")
                self.assertTrue(any(f"risk.{field}" in m for _, m in issues))

    def test_l0_exclusion_requires_exact_higher_risk_path_binding(self):
        orphan = {"risk": {"l0_pass_globs": ["**/*.png"],
                           "l0_exclude_globs": ["assets/game/**"],
                           "l3_filename_globs": ["assets/rtc/**"]}}
        issues = sevs(orphan)
        self.assertTrue(any(s == "FAIL" and "l0_exclude_globs" in m and "상위" in m
                            for s, m in issues))

        bound = {"risk": {"l0_pass_globs": ["**/*.png"],
                          "l0_exclude_globs": ["assets/game/**"],
                          "l3_filename_globs": ["assets/game/**"]}}
        self.assertNotIn("FAIL", [s for s, _ in sevs(bound)])

    def test_bad_risk_trigger_item_fails_semantically(self):
        for bad in (["auth/**", 1], ["   "]):
            with self.subTest(bad=bad):
                issues = sevs({"risk": {"l3_filename_globs": bad}})
                self.assertEqual(severity_of(issues), "FAIL")
                self.assertTrue(any("risk.l3_filename_globs" in m for _, m in issues))

    def test_bad_domain_trigger_item_fails_semantically(self):
        domain = {"id": "auth", "risk_level": "L3", "path_globs": ["   "],
                  "protocol_pointer": "sage/auth.md"}
        issues = sevs({"risk": {"domains": [domain]}})
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("risk.domains[0].path_globs" in m for _, m in issues))

    def test_standard_cross_runtime_project_root_env_is_valid(self):
        issues = sevs({"hooks": {"project_root_env": "SAGE_PROJECT_ROOT"}})
        self.assertNotIn("FAIL", [s for s, _ in issues])

    def test_custom_project_root_env_fails_instead_of_being_ignored(self):
        issues = sevs({"hooks": {"project_root_env": "MY_PROJECT_ROOT"}})
        self.assertTrue(any(s == "FAIL" and "project_root_env" in m for s, m in issues))

    def test_risk_domains_valid(self):
        profile = {"risk": {"domains": [{
            "id": "webrtc", "risk_level": "L3", "path_globs": ["**/rtc/**"],
            "content_keywords": ["RTCPeerConnection"],
            "protocol_pointer": "sage/critical-domains/webrtc.md",
        }]}}
        self.assertNotIn("FAIL", [s for s, _ in sevs(profile)])

    def test_risk_domains_duplicate_id_fails(self):
        domain = {"id": "webrtc", "risk_level": "L3", "path_globs": ["**/rtc/**"],
                  "content_keywords": ["RTC"], "protocol_pointer": "sage/critical-domains/webrtc.md"}
        issues = sevs({"risk": {"domains": [domain, dict(domain)]}})
        self.assertTrue(any(s == "FAIL" and "중복" in m for s, m in issues))

    def test_risk_domains_unsafe_pointer_fails(self):
        profile = {"risk": {"domains": [{
            "id": "webrtc", "risk_level": "L3", "path_globs": [], "content_keywords": [],
            "protocol_pointer": "../outside.md",
        }]}}
        self.assertTrue(any(s == "FAIL" and "protocol_pointer" in m for s, m in sevs(profile)))

    def test_missing_strategy_module_fail(self):
        prof = {"risk": {"l3_review_strategy": "no_such_strategy_xyz", "l3_filename_globs": ["*x*"]}}
        issues = sevs(prof)
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("no_such_strategy_xyz" in m for _, m in issues))

    def test_existing_strategy_module_ok(self):
        prof = {"risk": {"l3_review_strategy": "claude_grep_first", "l3_filename_globs": ["*x*"]}}
        self.assertNotIn("FAIL", [s for s, _ in sevs(prof)])

    def test_undefined_phase_ref_fail(self):
        prof = {"pdca": {"phases": [{"id": "00", "glob": "x"}],
                         "pre_implementation_required": {"L2": ["00", "99"]}},
                "risk": {"l2_path_globs": ["*x*"]}}
        issues = sevs(prof)
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("99" in m for _, m in issues))

    def test_all_empty_globs_is_info(self):
        # 위험 글롭 전무 → INFO(의도일 수 있음). FAIL/WARN 아님.
        self.assertEqual(severity_of(sevs({"risk": {}})), "INFO")

    # --- N-R1/P0-2: 오타 방어를 선택의존성(jsonschema)에서 떼어내기 — 의미검증은 항상 동작 ---
    def test_singular_typo_caught_without_jsonschema(self):
        # 핵심: l3_filename_globs→l3_filename_glob 오타가 jsonschema 미설치 환경에서도
        # 의미검증(known-keys)으로 FAIL. 메시지에 "미지 키" 가 있어야 의미검증 경로가 탔음을 보장.
        issues = sevs({"risk": {"l3_filename_glob": ["*secret*"]}})
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("미지 키" in m and "l3_filename_glob" in m for _, m in issues))

    def test_pdca_typo_caught_without_jsonschema(self):
        # pdca 폐쇄 섹션 오타(enabld)도 의미검증으로 항상 FAIL.
        issues = sevs({"pdca": {"enabld": True}})
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("미지 키" in m and "enabld" in m for _, m in issues))

    def test_known_keys_no_false_positive(self):
        # 허용 키만 있으면 known-keys 검사가 오탐(미지 키 FAIL)을 내지 않는다.
        prof = {"risk": {"l3_review_strategy": "claude_grep_first", "l3_filename_globs": ["*x*"],
                         "l2_path_globs": ["*.py"], "plan_glob": "plan_docs/**/*.md"}}
        self.assertFalse(any("미지 키" in m for _, m in sevs(prof)))


def _valid_rl(**over):
    """유효한 review_loop 기본값 + 오버라이드 (Loop A 검증 테스트 헬퍼)."""
    rl = {"enabled": True, "lenses": ["correctness", "security"], "refuters": 2,
          "refute_threshold": "majority", "max_iterations": {"L2": 1, "L3": 3},
          "dry_rounds": 1, "budget_tokens": {"L2": 150000, "L3": 600000},
          "cross_model": "from_options.cross_model", "severity_block": ["P0", "P1"],
          "architecture_escalation": "from_risk.l3"}
    rl.update(over)
    return rl


class TestReviewLoop(unittest.TestCase):
    """Loop A review_loop 의미검증 — '유효 YAML 이지만 루프 침묵/오동작' fail-closed."""

    def _prof(self, rl, **extra):
        # 켜진 루프의 degrade WARN(cross_model/arch)을 끄려면 options.cross_model + risk.l3 제공.
        prof = {"options": {"cross_model": True}, "risk": {"l3_filename_globs": ["*secret*"]},
                "pdca": {"review_loop": rl}}
        prof.update(extra)
        return prof

    def test_clean_review_loop_no_issue(self):
        self.assertNotIn("FAIL", [s for s, _ in sevs(self._prof(_valid_rl()))])
        self.assertNotIn("WARN", [s for s, _ in sevs(self._prof(_valid_rl()))])

    def test_absent_review_loop_no_issue(self):
        # review_loop 미선언 = Loop A 미사용(정상) — review_loop 발 이슈 없음.
        self.assertFalse(any("review_loop" in m for _, m in sevs({"risk": {"l2_path_globs": ["*.py"]}})))

    def test_enabled_empty_lenses_fail(self):
        issues = sevs(self._prof(_valid_rl(lenses=[])))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("lenses" in m and "침묵" in m for _, m in issues))

    def test_disabled_empty_lenses_ok(self):
        # 꺼진 루프의 빈 lenses 는 정상(침묵-비활성 규칙은 enabled 에서만).
        self.assertNotIn("FAIL", [s for s, _ in sevs(self._prof(_valid_rl(enabled=False, lenses=[])))])

    def test_unknown_lens_fail(self):
        issues = sevs(self._prof(_valid_rl(lenses=["correctness", "secuirty"])))  # 오타
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("secuirty" in m for _, m in issues))

    def test_unknown_review_loop_key_fail(self):
        rl = _valid_rl()
        rl["refuter"] = 2   # refuters 오타
        issues = sevs(self._prof(rl))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("미지 키" in m and "refuter" in m for _, m in issues))

    def test_refuters_below_one_fail(self):
        issues = sevs(self._prof(_valid_rl(refuters=0)))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("refuters" in m for _, m in issues))

    def test_max_iterations_l3_zero_fail(self):
        issues = sevs(self._prof(_valid_rl(max_iterations={"L2": 1, "L3": 0})))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("max_iterations" in m and "L3" in m for _, m in issues))

    def test_budget_tokens_nonpositive_fail(self):
        issues = sevs(self._prof(_valid_rl(budget_tokens={"L2": 0, "L3": 600000})))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("budget_tokens" in m and "L2" in m for _, m in issues))

    def test_unknown_tier_warn(self):
        # 루프 비대상 tier(L1) → WARN(오타 추정). L2/L3 둘 다 존재하므로 FAIL 아님.
        issues = sevs(self._prof(_valid_rl(max_iterations={"L1": 1, "L2": 1, "L3": 3})))
        self.assertNotIn("FAIL", [s for s, _ in issues])
        self.assertTrue(any("L1" in m for _, m in issues))

    def test_unknown_severity_block_fail(self):
        issues = sevs(self._prof(_valid_rl(severity_block=["P0", "P9"])))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("P9" in m for _, m in issues))

    def test_cross_model_wired_but_option_off_warn(self):
        # cross_model 배선했으나 options.cross_model off → 단일모델 degrade WARN.
        prof = {"options": {"cross_model": False}, "risk": {"l3_filename_globs": ["*x*"]},
                "pdca": {"review_loop": _valid_rl()}}
        issues = sevs(prof)
        self.assertNotIn("FAIL", [s for s, _ in issues])
        self.assertTrue(any("cross_model" in m and "단일모델" in m for _, m in issues))

    def test_arch_escalation_wired_but_no_l3_warn(self):
        # arch escalation 배선했으나 risk.l3_* 전무 → 무력 WARN.
        prof = {"options": {"cross_model": True}, "risk": {"l2_path_globs": ["*.py"]},
                "pdca": {"review_loop": _valid_rl()}}
        issues = sevs(prof)
        self.assertNotIn("FAIL", [s for s, _ in issues])
        self.assertTrue(any("architecture_escalation" in m for _, m in issues))

    def test_refute_threshold_unsupported_warn(self):
        issues = sevs(self._prof(_valid_rl(refute_threshold="unanimous")))
        self.assertNotIn("FAIL", [s for s, _ in issues])
        self.assertTrue(any("refute_threshold" in m for _, m in issues))

    def test_termination_enforce_valid_ok(self):
        for mode in ("advisory", "enforce"):
            self.assertNotIn("FAIL", [s for s, _ in sevs(self._prof(_valid_rl(termination_enforce=mode)))], mode)

    def test_termination_enforce_invalid_fail(self):
        issues = sevs(self._prof(_valid_rl(termination_enforce="strict")))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("termination_enforce" in m for _, m in issues))

    def test_report_gate_enforce_valid_ok(self):
        for mode in ("off", "advisory", "enforce"):
            sev = [s for s, _ in sevs(self._prof(_valid_rl(report_gate_enforce=mode)))]
            self.assertNotIn("FAIL", sev, mode)

    def test_report_gate_enforce_invalid_fail(self):
        issues = sevs(self._prof(_valid_rl(report_gate_enforce="block")))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("report_gate_enforce" in m for _, m in issues))

    def test_report_gate_enforce_enforce_warns(self):
        # enforce 는 유효하지만 "모든 05 가 루프 돌 때만 안전" WARN 을 동반(L1-only 오차단 주의 환기).
        issues = sevs(self._prof(_valid_rl(report_gate_enforce="enforce")))
        self.assertNotEqual(severity_of(issues), "FAIL")
        self.assertTrue(any(s == "WARN" and "report_gate_enforce" in m for s, m in issues))

    # --- codex 리뷰 #1 후속: jsonschema 없어도 닫혀야 할 fail-open 갭 (순수파이썬 강제) ---
    def test_enabled_non_bool_fail(self):
        # P0: enabled:1 은 `is True`=False → 침묵 비활성. bool 아니면 FAIL.
        issues = sevs(self._prof(_valid_rl(enabled=1)))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("enabled" in m and "bool" in m for _, m in issues))

    def test_cross_model_typo_fail(self):
        # P1: sentinel 오타 → host 가 못 알아보고 opposite-runtime peer 침묵 누락.
        issues = sevs(self._prof(_valid_rl(cross_model="from_option.cross_model")))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("cross_model" in m for _, m in issues))

    def test_cross_model_bool_ok(self):
        # 리터럴 bool 은 유효(옵션 무관 강제 on/off).
        prof = {"options": {"cross_model": True}, "risk": {"l3_filename_globs": ["*x*"]},
                "pdca": {"review_loop": _valid_rl(cross_model=True)}}
        self.assertNotIn("FAIL", [s for s, _ in sevs(prof)])

    def test_arch_escalation_typo_fail(self):
        issues = sevs(self._prof(_valid_rl(architecture_escalation="from_risk.ll3")))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("architecture_escalation" in m for _, m in issues))

    def test_enabled_missing_l3_iteration_cap_fail(self):
        # P1: 켜진 루프에 L3 반복 상한 누락 → 무한 루프. WARN 아닌 FAIL.
        issues = sevs(self._prof(_valid_rl(max_iterations={"L2": 1})))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("max_iterations" in m and "L3" in m for _, m in issues))

    def test_enabled_typo_tier_l33_missing_l3_fail(self):
        # P1: L33 오타 → L3 누락. WARN(unknown tier) + FAIL(L3 누락) 둘 다.
        issues = sevs(self._prof(_valid_rl(budget_tokens={"L2": 150000, "L33": 600000})))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("budget_tokens" in m and "L3" in m and "누락" in m for _, m in issues))

    def test_enabled_missing_budget_entirely_fail(self):
        rl = _valid_rl()
        del rl["budget_tokens"]
        issues = sevs(self._prof(rl))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("budget_tokens" in m and "무한" in m for _, m in issues))

    def test_refuters_string_fail(self):
        # P1: refuters:"2" 는 isinstance(int) 아님 → 이전엔 통과. 이제 FAIL.
        issues = sevs(self._prof(_valid_rl(refuters="2")))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("refuters" in m for _, m in issues))

    def test_refuters_missing_when_enabled_fail(self):
        rl = _valid_rl()
        del rl["refuters"]
        issues = sevs(self._prof(rl))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("refuters" in m and "누락" in m for _, m in issues))

    def test_dry_rounds_zero_fail_when_enabled(self):
        issues = sevs(self._prof(_valid_rl(dry_rounds=0)))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("dry_rounds" in m for _, m in issues))

    def test_iteration_value_bool_fail(self):
        # True==1 이지만 bool 은 정수 노브로 부적격(오타/실수 방어).
        issues = sevs(self._prof(_valid_rl(max_iterations={"L2": True, "L3": 3})))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("max_iterations" in m and "L2" in m for _, m in issues))

    def test_disabled_bad_scalar_still_fail(self):
        # malformed 스칼라(refuters:"2")는 enabled 무관 항상 FAIL — schema 와 일치(jsonschema 유무 분기 제거).
        issues = sevs(self._prof(_valid_rl(enabled=False, refuters="2")))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("refuters" in m for _, m in issues))

    # --- codex 재리뷰 후속: 컨테이너 타입 크래시 방지 + refute_threshold 타입 엄격화 ---
    def test_lenses_non_list_fail_not_crash(self):
        # lenses:true 가 iterate 시 TypeError 크래시하지 않고 제어된 FAIL.
        issues = sevs(self._prof(_valid_rl(lenses=True)))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("lenses" in m and "리스트" in m for _, m in issues))

    def test_severity_block_non_list_fail_not_crash(self):
        issues = sevs(self._prof(_valid_rl(severity_block=True)))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("severity_block" in m and "리스트" in m for _, m in issues))

    def test_refute_threshold_non_string_fail(self):
        # 비문자열(true)은 WARN 아닌 FAIL(schema type:string 과 일치).
        issues = sevs(self._prof(_valid_rl(refute_threshold=True)))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("refute_threshold" in m for _, m in issues))

    # --- codex 재리뷰 후속: 부모 섹션 비-dict 크래시 방지(제어된 FAIL) ---
    def test_profile_not_mapping_fail_not_crash(self):
        for bad in ("just a string", [1, 2, 3], 42):
            issues = validate_profile(bad, REPO)
            self.assertEqual(severity_of(issues), "FAIL")
            self.assertTrue(any("매핑" in m for _, m in issues))

    def test_pdca_non_dict_fail_not_crash(self):
        issues = validate_profile({"pdca": "oops", "risk": {"l2_path_globs": ["*.py"]}}, REPO)
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("pdca" in m and "매핑" in m for _, m in issues))

    def test_options_non_dict_fail_not_crash(self):
        issues = validate_profile({"options": "oops"}, REPO)
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("options" in m and "매핑" in m for _, m in issues))

    def test_risk_non_dict_fail_not_crash(self):
        issues = validate_profile({"risk": ["not", "a", "map"]}, REPO)
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("risk" in m and "매핑" in m for _, m in issues))

    def test_pathological_inputs_never_crash(self):
        # 거버넌스 게이트는 어떤 malformed 입력에도 크래시(미제어) 대신 제어된 결과를 내야 한다(codex).
        # 혼합타입 키/아이템(sorted TypeError), 비-iterable phases/pre_impl 등 병적 케이스 fuzz.
        pathological = [
            {"pdca": {"review_loop": {1: "x", "enabled": True, "also": "y"}}},   # 혼합타입 미지 키
            {"pdca": {"review_loop": {"enabled": True, "lenses": [1, "foo", None]}}},  # 혼합타입 lens
            {"pdca": {"review_loop": {"enabled": True, "severity_block": [1, "P9"]}}},  # 혼합타입 sev
            {"pdca": {"review_loop": {"enabled": True, "max_iterations": {1: 2, "L33": 3}}}},  # 혼합 tier 키
            {"pdca": {"phases": True}},                          # phases 비-list
            {"pdca": {"phases": [1, "notdict", {"id": "00"}]}},   # phases 혼합
            {"pdca": {"pre_implementation_required": "oops"}},   # 비-dict
            {"pdca": {"pre_implementation_required": {"L2": 5}}},  # 비-list req
            {"pdca": {"pre_implementation_required": {"L2": [1, "00"]}}, "risk": {"l2_path_globs": ["*x*"]}},
            {"risk": {"l3_review_strategy": 123}},               # 비-string strategy
            # 중첩 unhashable 값(set comprehension/membership 크래시 유발) — backstop 이 FAIL 로 봉쇄.
            {"pdca": {"review_loop": {"lenses": [{}]}}},
            {"pdca": {"review_loop": {"severity_block": [{}]}}},
            {"pdca": {"phases": [{"id": [1]}]}},
            {"pdca": {"phases": [{"id": "p1"}], "pre_implementation_required": {"L3": [{}]}}},
        ]
        for prof in pathological:
            try:
                issues = validate_profile(prof, REPO)
                self.assertIsInstance(issues, list)   # 항상 리스트 반환(크래시 없음)
            except Exception as e:
                self.fail(f"validate_profile crashed on {prof!r}: {type(e).__name__}: {e}")

    def test_backstop_does_not_mask_valid_profiles(self):
        # 예외 backstop 이 정상 입력의 로직버그를 가리지 않는지 — 대표 valid 프로파일(템플릿 + enabled 루프)이
        # "의미검증 중 예외" FAIL 을 내지 않아야 한다(codex 재리뷰 #2 완화).
        import yaml
        tmpl = yaml.safe_load(open(os.path.join(REPO, "templates", "project-profile.yaml"), encoding="utf-8"))
        valid_full = {"options": {"cross_model": True}, "risk": {"l3_filename_globs": ["*secret*"]},
                      "pdca": {"phases": [{"id": "00", "glob": "x"}],
                               "pre_implementation_required": {"L3": ["00"]},
                               "review_loop": _valid_rl()}}
        for prof in (tmpl, valid_full):
            issues = validate_profile(prof, REPO)
            self.assertFalse(any("예외" in m for _, m in issues),
                             f"backstop fired on valid profile: {[m for _, m in issues]}")


def _valid_acceptance(**over):
    ac = {"enabled": True, "require_for_risk": ["L2", "L3"],
          "statuses": ["PASS", "FAIL", "NOT TESTED", "N/A"],
          "unresolved_statuses": ["FAIL", "NOT TESTED"],
          "report_gate_enforce": "advisory"}
    ac.update(over)
    return ac


def _risk_acceptance(**over):
    ac = _valid_acceptance()
    ac.pop("report_gate_enforce")
    ac.update({"report_gate_by_risk": {"L2": "advisory", "L3": "enforce"},
               "waiver": {"enabled": True}})
    ac.update(over)
    return ac


class TestAcceptanceValidation(unittest.TestCase):
    """verification.acceptance 의미검증 — 요구사항별 수용증거 gate 의 침묵 비활성 방지."""

    def _prof(self, ac):
        return {"verification": {"acceptance": ac}, "risk": {"l2_path_globs": ["*.py"]}}

    def test_clean_acceptance_no_fail(self):
        self.assertNotIn("FAIL", [s for s, _ in sevs(self._prof(_valid_acceptance()))])

    def test_unknown_acceptance_key_fail(self):
        issues = sevs(self._prof(_valid_acceptance(unresolved_status=["FAIL"])))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("미지 키" in m and "unresolved_status" in m for _, m in issues))

    def test_enabled_non_bool_fail(self):
        issues = sevs(self._prof(_valid_acceptance(enabled="true")))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("acceptance.enabled" in m for _, m in issues))

    def test_missing_not_tested_unresolved_fail(self):
        issues = sevs(self._prof(_valid_acceptance(unresolved_statuses=["FAIL"])))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("NOT TESTED" in m for _, m in issues))

    def test_missing_canonical_status_fail(self):
        issues = sevs(self._prof(_valid_acceptance(statuses=["PASS", "FAIL"])))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("NOT TESTED" in m and "N/A" in m for _, m in issues))

    def test_custom_status_cannot_mint_resolved_state(self):
        issues = sevs(self._prof(_valid_acceptance(
            statuses=["PASS", "FAIL", "NOT TESTED", "N/A", "SKIPPED"])))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("비표준 상태" in message and "SKIPPED" in message
                            for _, message in issues))

    def test_invalid_report_gate_mode_fail(self):
        issues = sevs(self._prof(_valid_acceptance(report_gate_enforce="block")))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("report_gate_enforce" in m for _, m in issues))

    def test_enforce_warns_for_migration_risk(self):
        issues = sevs(self._prof(_valid_acceptance(report_gate_enforce="enforce")))
        self.assertNotIn("FAIL", [s for s, _ in issues])
        self.assertTrue(any(s == "WARN" and "acceptance.report_gate_enforce" in m for s, m in issues))

    def test_risk_policy_and_waiver_are_valid(self):
        issues = sevs(self._prof(_risk_acceptance()))
        self.assertNotIn("FAIL", [severity for severity, _ in issues])

    def test_legacy_and_risk_policy_together_fail(self):
        issues = sevs(self._prof(_risk_acceptance(report_gate_enforce="advisory")))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("동시에" in message for _, message in issues))

    def test_l3_profile_downgrade_and_incomplete_map_fail(self):
        for policy in ({"L2": "advisory", "L3": "advisory"}, {"L2": "advisory"}):
            with self.subTest(policy=policy):
                issues = sevs(self._prof(_risk_acceptance(report_gate_by_risk=policy)))
                self.assertEqual(severity_of(issues), "FAIL")

    def test_enabled_acceptance_requires_l3_tier(self):
        for tiers in ([], ["L1"], ["L2"], ["L1", "L2"]):
            with self.subTest(tiers=tiers):
                issues = sevs(self._prof(_risk_acceptance(require_for_risk=tiers)))
                self.assertEqual(severity_of(issues), "FAIL")
                self.assertTrue(any("require_for_risk" in message and "L3" in message
                                    for _, message in issues))

    def test_waiver_schema_is_closed_and_bool_typed(self):
        for waiver in ({"enabled": "true"}, {"enabled": True, "implicit": True}):
            with self.subTest(waiver=waiver):
                issues = sevs(self._prof(_risk_acceptance(waiver=waiver)))
                self.assertEqual(severity_of(issues), "FAIL")


class TestKnowledgeCaptureVault(unittest.TestCase):
    """7.5단계 A — vault-output 플래그(loop_audit_dashboard/retro_note) 의존 검증."""

    def test_flag_on_without_vault_path_warn(self):
        for key in ("loop_audit_dashboard", "retro_note"):
            issues = sevs({"knowledge_capture": {"vault_path": "", key: True}})
            self.assertNotIn("FAIL", [s for s, _ in issues])
            self.assertTrue(any(key in m and "vault_path" in m for _, m in issues), key)

    def test_flag_on_with_vault_path_ok(self):
        prof = {"knowledge_capture": {"vault_path": "/v", "loop_audit_dashboard": True, "retro_note": True}}
        self.assertFalse(any("loop_audit_dashboard" in m or "retro_note" in m for _, m in sevs(prof)))

    def test_flag_off_no_issue(self):
        prof = {"knowledge_capture": {"vault_path": "", "loop_audit_dashboard": False, "retro_note": False}}
        self.assertFalse(any("loop_audit_dashboard" in m or "retro_note" in m for _, m in sevs(prof)))

    def test_flag_non_bool_warn(self):
        # 비-bool 은 `is True` 로 침묵 off → 타입 WARN.
        issues = sevs({"knowledge_capture": {"vault_path": "/v", "retro_note": "yes"}})
        self.assertNotIn("FAIL", [s for s, _ in issues])
        self.assertTrue(any("retro_note" in m and "bool" in m for _, m in issues))

    def test_kc_non_dict_fail_not_crash(self):
        # 비-dict knowledge_capture → 섹션 가드가 FAIL(런타임 .get 크래시 방지, codex A).
        issues = validate_profile({"knowledge_capture": "oops"}, REPO)
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("knowledge_capture" in m and "매핑" in m for _, m in issues))

    def test_vault_path_non_string_warn(self):
        # vault_path 비-str(123) → WARN(런타임 .strip() 크래시 예방, codex A).
        issues = sevs({"knowledge_capture": {"vault_path": 123, "retro_note": True}})
        self.assertNotIn("FAIL", [s for s, _ in issues])
        self.assertTrue(any("vault_path" in m and "문자열" in m for _, m in issues))


class TestCrossModelEffort(unittest.TestCase):
    def _prof(self, **cm):
        return {"runtime": {"host": "claude"}, "options": {"cross_model": True}, "cross_model": cm}

    def test_unset_is_clean(self):
        self.assertEqual([], [i for i in sevs(self._prof(peer="opposite_runtime")) if i[0] == "FAIL"])

    def test_valid_effort_for_resolved_peer(self):
        self.assertNotIn("FAIL", [s for s, _ in sevs(self._prof(effort="xhigh"))])

    def test_effort_from_wrong_peer_vocabulary_is_fail(self):
        # host=claude → peer=codex. `max` 는 claude 어휘라 codex 가 조용히 무시 → 정적으로 차단.
        issues = sevs(self._prof(effort="max"))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("max" in m for _, m in issues))
        # host 를 뒤집으면 같은 값이 유효해진다(peer=claude).
        prof = self._prof(effort="max"); prof["runtime"]["host"] = "codex"
        self.assertNotIn("FAIL", [s for s, _ in sevs(prof)])

    def test_effort_without_cross_model_on_is_warn(self):
        prof = self._prof(effort="high"); prof["options"]["cross_model"] = False
        issues = sevs(prof)
        self.assertNotIn("FAIL", [s for s, _ in issues])
        self.assertTrue(any("무동작" in m for _, m in issues))

    def test_non_string_effort_is_fail_not_crash(self):
        self.assertEqual(severity_of(sevs(self._prof(effort=3))), "FAIL")

    def test_unknown_cross_model_key_is_fail(self):
        # `effrot: max` 가 조용히 무시되면 기본 high 로 돌면서 설정대로 돈 것처럼 보인다.
        issues = sevs(self._prof(effrot="max"))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("effrot" in m for _, m in issues))

    def test_known_cross_model_keys_pass(self):
        prof = self._prof(peer="opposite_runtime", on_unavailable="block", effort="high")
        self.assertNotIn("FAIL", [s for s, _ in sevs(prof)])

    def test_unimplemented_peer_or_on_unavailable_value_is_fail(self):
        self.assertEqual(severity_of(sevs(self._prof(on_unavailable="clean_context_same_runtime"))), "FAIL")
        self.assertEqual(severity_of(sevs(self._prof(peer="claude"))), "FAIL")

    def test_retired_invocation_key_is_fail(self):
        # 옛 gstack wrapper 시절 키. 남아 있으면 조용히 무시되므로 FAIL 로 이주를 강제한다.
        self.assertEqual(severity_of(sevs(self._prof(invocation="codex exec"))), "FAIL")

    def test_non_mapping_cross_model_is_fail_without_jsonschema(self):
        # jsonschema 는 선택 의존성 — 구조검증이 skip 되는 환경에서 의미검증이 유일한 관문이다.
        from sage.profile_validate import _cross_model_issues
        issues = _cross_model_issues({"cross_model": ["effort", "max"]})
        self.assertEqual([s for s, _ in issues], ["FAIL"])
        self.assertEqual([], _cross_model_issues({}))   # 미설정은 정상


class TestTeamAgentModelEffort(unittest.TestCase):
    def _prof(self, host="claude", **runtime):
        role = {"enabled": True}
        if runtime:
            role["runtime"] = runtime
        return {"runtime": {"host": host}, "team": {"core": {"leader": role}}}

    def test_unset_is_clean(self):
        self.assertNotIn("FAIL", [s for s, _ in sevs(self._prof())])

    def test_valid_alias_and_effort(self):
        self.assertNotIn("FAIL", [s for s, _ in sevs(self._prof(model="opus", effort="xhigh"))])

    def test_full_model_id_allowed(self):
        self.assertNotIn("FAIL", [s for s, _ in sevs(self._prof(model="claude-opus-4-8"))])

    def test_integer_effort_allowed(self):
        self.assertNotIn("FAIL", [s for s, _ in sevs(self._prof(effort=8))])

    def test_bool_effort_rejected(self):
        # bool 은 int 의 서브클래스 — `effort: true` 가 effort=1 로 통과하면 안 됨.
        self.assertEqual(severity_of(sevs(self._prof(effort=True))), "FAIL")

    def test_model_typo_is_fail(self):
        issues = sevs(self._prof(model="opuss"))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("opuss" in m and "leader" in m for _, m in issues))

    def test_model_id_with_newline_is_fail(self):
        # frontmatter 로 그대로 주입되므로 개행이 섞인 id 는 키 주입 통로가 된다.
        self.assertEqual(severity_of(sevs(self._prof(model="claude-x\nname: replaced"))), "FAIL")

    def test_effort_typo_is_fail(self):
        self.assertEqual(severity_of(sevs(self._prof(effort="ultra"))), "FAIL")

    def test_unknown_runtime_key_is_fail(self):
        self.assertEqual(severity_of(sevs(self._prof(modle="opus"))), "FAIL")

    def test_runtime_non_dict_is_fail_not_crash(self):
        prof = {"runtime": {"host": "claude"}, "team": {"core": {"leader": {"runtime": "opus"}}}}
        self.assertEqual(severity_of(sevs(prof)), "FAIL")

    def test_codex_host_warns_inert(self):
        issues = sevs(self._prof(host="codex", model="opus"))
        self.assertNotIn("FAIL", [s for s, _ in issues])
        self.assertTrue(any("무동작" in m for _, m in issues))

    def test_role_typo_is_fail_not_silently_ignored(self):
        # `reviewerr` 를 무시하면 설정이 죽은 필드가 된다 — 렌더에도 doctor 에도 안 잡힘.
        prof = {"runtime": {"host": "claude"}, "team": {"core": {"reviewerr": {"runtime": {"model": "opus"}}}}}
        issues = sevs(prof)
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("reviewerr" in m for _, m in issues))

    def test_legacy_role_level_model_warns_inert(self):
        # 옛 프로필의 죽은 필드. 조용히 승격되지 않고, 조용히 무시되지도 않는다.
        prof = {"runtime": {"host": "claude"}, "team": {"core": {"reviewer": {"model": "sonnet"}}}}
        issues = sevs(prof)
        self.assertNotIn("FAIL", [s for s, _ in issues])
        self.assertTrue(any("무동작" in m and "runtime" in m for _, m in issues))


class TestRetroGateEnforce(unittest.TestCase):
    """pdca.retro.report_gate_enforce (9-C v1) 검증."""

    def _prof(self, mode=None, retro_note=None, glob06="plan_docs/06-report/**/*.md",
              file_type_map=None):
        pdca = {}
        if mode is not None:
            pdca["retro"] = {"report_gate_enforce": mode}
        if glob06 is not None:
            pdca["phases"] = [{"id": "06", "glob": glob06}]
        prof = {"pdca": pdca}
        if retro_note is not None:
            prof["knowledge_capture"] = {"retro_note": retro_note, "vault_path": "/tmp/v"}
        # 기본은 06 을 커버하는 file_type_map(로그 커버리지 경고를 유발하지 않도록)
        prof["file_type_map"] = file_type_map if file_type_map is not None \
            else [{"glob": "plan_docs/**", "type": "plan-doc"}]
        return prof

    def test_unset_is_clean(self):
        self.assertNotIn("FAIL", [s for s, _ in sevs(self._prof())])

    def test_off_is_clean(self):
        self.assertNotIn("FAIL", [s for s, _ in sevs(self._prof(mode="off"))])

    def test_valid_modes_pass_with_retro_note_on(self):
        for mode in ("advisory", "enforce"):
            issues = sevs(self._prof(mode=mode, retro_note=True))
            self.assertNotIn("FAIL", [s for s, _ in issues], mode)

    def test_typo_mode_is_fail(self):
        issues = sevs(self._prof(mode="enforcee"))
        self.assertEqual(severity_of(issues), "FAIL")
        self.assertTrue(any("enforcee" in m for _, m in issues))

    def test_non_string_mode_is_fail(self):
        self.assertEqual(severity_of(sevs(self._prof(mode=True))), "FAIL")

    def test_non_dict_retro_section_is_fail_not_crash(self):
        issues = sevs({"pdca": {"retro": "oops"}})
        self.assertEqual(severity_of(issues), "FAIL")

    def test_enabled_without_retro_note_warns_inert(self):
        issues = sevs(self._prof(mode="enforce", retro_note=False))
        self.assertNotIn("FAIL", [s for s, _ in issues])
        self.assertTrue(any("retro_note" in m and "off" in m for _, m in issues))

    def test_enabled_with_retro_note_no_warn(self):
        issues = sevs(self._prof(mode="advisory", retro_note=True))
        self.assertEqual([], [m for s, m in issues if s == "WARN" and "retro_note" in m])

    def test_enforce_warns_when_06_not_logged(self):
        # codex 구현리뷰 P1: 06 이 file_type_map 에 안 걸리면 post_tool_logger 가 안 남겨 게이트 무동작.
        issues = sevs(self._prof(mode="enforce", retro_note=True, file_type_map=[{"glob": "src/**", "type": "code"}]))
        self.assertNotIn("FAIL", [s for s, _ in issues])
        self.assertTrue(any("file_type_map" in m and "06" in m for _, m in issues))

    def test_enforce_no_logger_warn_when_06_covered(self):
        # plan_docs/** 가 06 을 덮으면 경고 없음.
        issues = sevs(self._prof(mode="enforce", retro_note=True,
                                 file_type_map=[{"glob": "plan_docs/**", "type": "plan-doc"}]))
        self.assertEqual([], [m for s, m in issues if "file_type_map" in m])

    def test_empty_file_type_map_warns(self):
        issues = sevs(self._prof(mode="enforce", retro_note=True, file_type_map=[]))
        self.assertTrue(any("file_type_map" in m for _, m in issues))

    def test_retro_key_accepted_in_schemaless_fallback(self):
        # jsonschema 없어도 pdca.retro 가 오타로 FAIL 되면 안 된다(_CLOSED_SECTION_FALLBACK 포함 확인).
        import sage.profile_validate as pv
        self.assertIn("retro", pv._CLOSED_SECTION_FALLBACK["pdca"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
