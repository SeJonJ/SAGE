"""profile_validate — project-profile 구조(스키마) + 의미 검증 (외부검토 R2/P0-2).

배경: 가장 자주 손대는 project-profile.yaml 에 검증이 없어, `l3_filename_globs`→`l3_filename_glob`
같은 오타가 유효한 YAML 로 통과한 뒤 core 의 `.get("l3_filename_globs", [])` 가 조용히 빈 리스트를
받아 **L3 게이트가 침묵 비활성**된다(거버넌스 최악 실패 모드). 이를 설치/생성 시점에 차단한다.

- 구조검증: schema/profile.schema.json (risk/pdca additionalProperties:false 가 오타 키 적발).
  jsonschema 는 선택의존(미설치 시 WARN skip — 핵심 CLI 경량 유지).
- 의미검증(스키마로 못 잡는 것): 전략 모듈 존재? pre_implementation_required 가 정의된 phase 만 참조?
  위험 글롭 전부 비었나(무동작 INFO)?

반환: [(severity, message)] — severity ∈ {FAIL, WARN, INFO}. FAIL 이 있으면 호출측이 fail-closed.
"""
import json
import os
from pathlib import Path

from sage.diagnostics import Diagnostic
from sage.profile_compile import materialization_issues

_RANK = {"INFO": 0, "WARN": 1, "FAIL": 2}

# 폐쇄 섹션(스키마 additionalProperties:false)의 허용 키 — jsonschema 가 없어도 오타 키를
# 항상 적발하기 위한 폴백(N-R1/P0-2). 권위 출처는 schema/profile.schema.json 이며, 스키마를
# 읽을 수 있으면 거기서 로드해 드리프트를 막는다. 폴백은 스키마 파일이 아예 없을 때만 쓰인다.
_CLOSED_SECTION_FALLBACK = {
    "sage": {"required_version"},
    "risk": {"desktop_block_glob", "desktop_block_hint", "generic_tokens", "l0_pass_globs", "l0_exclude_globs",
             "l1_path_globs", "l2_content_keywords", "l2_path_globs", "l3_content_keywords",
             "l3_filename_globs", "l3_review_strategy", "l3_review_glob", "content_l3_enforce",
             "domains", "plan_glob", "review_patterns"},
    "pdca": {"approve_marker", "approve_phase", "base_plan", "cycle_binding_visibility", "enabled",
             "phases", "pre_implementation_required", "report_phase", "review_loop", "fast_cycle",
             "retro", "writeback"},
    "output_contract": {"markers"},
    "mcp": {"enabled"},
    "extraction": {"config"},
    "runtime": {"host", "installed_hosts", "active_host", "external_reviewer", "asset_ssot"},
}

# review_loop(Loop A) 엔진 어휘 — 스택 중립(severity·risk level 처럼 엔진 레벨 vocabulary, 도메인값 아님).
# 닫힌 집합이라 오타(예: secuirty)를 fail-closed 로 적발 — jsonschema 선택의존과 무관하게 항상 동작.
_KNOWN_LENSES = {"correctness", "security", "concurrency", "convention", "lifecycle",
                 "performance", "error_handling", "data_integrity", "api_contract"}
_KNOWN_SEVERITY = {"P0", "P1", "P2", "P3"}
_LOOP_TIERS = {"L2", "L3"}   # L0/L1 은 루프 없음(risk → mandatory phase 표)
_REVIEW_LOOP_KEYS = {"enabled", "lenses", "refuters", "refute_threshold", "max_iterations",
                     "dry_rounds", "budget_tokens", "cross_model", "severity_block",
                     "architecture_escalation", "termination_enforce", "report_gate_enforce",
                     "early_completion"}
_TERMINATION_MODES = {"advisory", "enforce"}   # 종료 검산 모드(기본 advisory)
_REPORT_GATE_MODES = {"off", "advisory", "enforce"}   # 06←05 audit 게이트 모드(기본 advisory)
_BASE_PLAN_KEYS = {"done_criteria_gate"}
_DONE_CRITERIA_GATE_MODES = {"off", "advisory", "enforce"}
# EH-15/16 통과 줄 결속 노출. 닫힌 어휘 — 오타가 조용히 기본값으로 떨어지면 켠 줄 알고 안 켜진다.
_CYCLE_BINDING_VISIBILITY = {"gated", "all"}
_FAST_CYCLE_KEYS = {"enabled", "reason_required", "minimum_rounds", "minimum_lenses", "lenses",
                    "standard_transition"}
# Standard→Fast 명시 전환 opt-in. 키 부재는 비활성이다 — 여기서 부재를 활성으로 읽으면 설정하지
# 않은 프로젝트에서 전환이 열린다.
_STANDARD_TRANSITION_KEYS = {"enabled"}
# 사용자 승인 리뷰 조기 완료 opt-in. 하한은 엔진이 1로 고정하고 profile 은 상향만 가능하다.
_EARLY_COMPLETION_KEYS = {"enabled", "minimum_completed_rounds"}
EARLY_COMPLETION_ROUND_FLOOR = 1
_ACCEPTANCE_KEYS = {"enabled", "require_for_risk", "statuses", "unresolved_statuses",
                    "report_gate_enforce", "report_gate_by_risk", "waiver"}
_ACCEPTANCE_TIERS = {"L1", "L2", "L3"}
_CANONICAL_ACCEPTANCE_STATUSES = {"PASS", "FAIL", "NOT TESTED", "N/A"}
# §10-a-C sage-feedback: 닫힌 키 어휘. 미지 키는 오타로 게이트가 조용히 꺼지는 걸 막으려 FAIL.
_FEEDBACK_KEYS = {"enabled", "block_release", "record", "record_target"}
_FEEDBACK_RECORD_TARGETS = {"auto", "sage", "vault"}


def _done_criteria_gate_issues(profile):
    """Validate the closed Phase 00 Done Criteria policy without jsonschema."""
    pdca = profile.get("pdca")
    if pdca is not None and not isinstance(pdca, dict):
        return []
    base_plan = (pdca or {}).get("base_plan")
    if base_plan is None:
        return []
    if not isinstance(base_plan, dict):
        return [("FAIL", Diagnostic("validate.base_plan_not_mapping"))]
    issues = []
    unknown = sorted(set(base_plan) - _BASE_PLAN_KEYS, key=str)
    if unknown:
        issues.append(("FAIL", Diagnostic("validate.base_plan_unknown_keys", keys=unknown,
                                          allowed=sorted(_BASE_PLAN_KEYS))))
    mode = base_plan.get("done_criteria_gate")
    if mode is not None and (not isinstance(mode, str) or mode not in _DONE_CRITERIA_GATE_MODES):
        issues.append(("FAIL", Diagnostic("validate.done_criteria_gate_invalid", value=repr(mode),
                                          allowed=sorted(_DONE_CRITERIA_GATE_MODES))))
    return issues


def _cycle_binding_visibility_issues(profile):
    """EH-15/16: 통과 줄 결속 노출 어휘를 닫아둔다(오타 → 조용한 기본값 복귀 방지)."""
    pdca = profile.get("pdca")
    if not isinstance(pdca, dict):
        return []
    mode = pdca.get("cycle_binding_visibility")
    if mode is None:
        return []
    if not isinstance(mode, str) or mode not in _CYCLE_BINDING_VISIBILITY:
        return [("FAIL", Diagnostic("validate.cycle_binding_visibility_invalid", value=repr(mode),
                                    allowed=sorted(_CYCLE_BINDING_VISIBILITY)))]
    return []


def _fast_cycle_issues(profile):
    """Validate the closed Fast Cycle policy without relying on jsonschema."""
    pdca = profile.get("pdca")
    if pdca is not None and not isinstance(pdca, dict):
        return []
    fast = (pdca or {}).get("fast_cycle")
    if fast is None:
        return []
    if not isinstance(fast, dict):
        return [("FAIL", Diagnostic("validate.fast_cycle_not_mapping"))]

    issues = []
    unknown = sorted((key for key in fast if key not in _FAST_CYCLE_KEYS), key=str)
    if unknown:
        issues.append(("FAIL", Diagnostic("validate.fast_cycle_unknown_keys", keys=unknown,
                                          allowed=sorted(_FAST_CYCLE_KEYS))))
    for key in ("enabled", "reason_required"):
        value = fast.get(key)
        if not isinstance(value, bool):
            issues.append(("FAIL", Diagnostic("validate.fast_cycle_field_not_bool", field=key)))
    if fast.get("reason_required") is not True:
        issues.append(("FAIL", Diagnostic("validate.fast_cycle_reason_required_locked")))

    tier_values = {}
    for key, floor in (("minimum_rounds", 1), ("minimum_lenses", 2)):
        value = fast.get(key)
        if not isinstance(value, dict):
            issues.append(("FAIL", Diagnostic("validate.fast_cycle_tier_not_mapping", field=key)))
            continue
        keys = set(value)
        if keys != _LOOP_TIERS:
            issues.append(("FAIL", Diagnostic("validate.fast_cycle_tier_keys_invalid", field=key)))
        for tier in _LOOP_TIERS:
            item = value.get(tier)
            if type(item) is not int or item < floor:
                issues.append(("FAIL", Diagnostic("validate.fast_cycle_tier_value_invalid", field=key,
                                                  tier=tier, floor=floor)))
            else:
                tier_values[(key, tier)] = item

    issues.extend(_opt_in_block_issues(fast.get("standard_transition"), _STANDARD_TRANSITION_KEYS,
                                       _STANDARD_TRANSITION_CODES,
                                       "fast_cycle.standard_transition"))

    lenses = fast.get("lenses")
    if not isinstance(lenses, dict):
        issues.append(("FAIL", Diagnostic("validate.fast_cycle_lenses_not_mapping")))
        return issues
    if set(lenses) != _LOOP_TIERS:
        issues.append(("FAIL", Diagnostic("validate.fast_cycle_lenses_keys_invalid")))
    for tier in _LOOP_TIERS:
        values = lenses.get(tier)
        if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
            issues.append(("FAIL", Diagnostic("validate.fast_cycle_lenses_not_string_list", tier=tier)))
            continue
        if len(values) != len(set(values)):
            issues.append(("FAIL", Diagnostic("validate.fast_cycle_lenses_duplicated", tier=tier)))
        bad = sorted(set(values) - _KNOWN_LENSES)
        if bad:
            issues.append(("FAIL", Diagnostic("validate.fast_cycle_lenses_unknown", tier=tier, lenses=bad)))
        minimum = tier_values.get(("minimum_lenses", tier))
        if minimum is not None and len(values) < minimum:
            issues.append(("FAIL", Diagnostic("validate.fast_cycle_lenses_below_minimum", tier=tier)))
    return issues


def _opt_in_block_issues(block, allowed, codes, field):
    """`{enabled: bool}` 형태 opt-in 블록의 공통 검증. 부재는 비활성이므로 검증 대상이 아니다.

    진단 code 는 호출부가 리터럴로 넘긴다 — f-string 으로 조립하면 catalog 완전성 oracle 이 그 code
    를 정적으로 찾지 못해, 번역이 빠진 채로 배포돼도 테스트가 통과한다.
    """
    if block is None:
        return []
    if not isinstance(block, dict):
        return [("FAIL", Diagnostic(codes["not_mapping"], field=field))]
    issues = []
    unknown = sorted((key for key in block if key not in allowed), key=str)
    if unknown:
        issues.append(("FAIL", Diagnostic(codes["unknown_keys"], field=field,
                                          keys=unknown, allowed=sorted(allowed))))
    if not isinstance(block.get("enabled"), bool):
        issues.append(("FAIL", Diagnostic(codes["enabled_not_bool"], field=field)))
    return issues


_STANDARD_TRANSITION_CODES = {
    "not_mapping": "validate.standard_transition_not_mapping",
    "unknown_keys": "validate.standard_transition_unknown_keys",
    "enabled_not_bool": "validate.standard_transition_enabled_not_bool",
}
_EARLY_COMPLETION_CODES = {
    "not_mapping": "validate.early_completion_not_mapping",
    "unknown_keys": "validate.early_completion_unknown_keys",
    "enabled_not_bool": "validate.early_completion_enabled_not_bool",
}


def _early_completion_issues(review_loop):
    """리뷰 조기 완료 opt-in. `minimum_completed_rounds` 는 엔진 하한 1 아래로 못 내려간다.

    하한을 profile 이 0 으로 내릴 수 있으면 "리뷰 0라운드 승인" 이 설정 한 줄로 열린다. 그건
    이 기능이 절대 허용하지 않는 상태이므로 상향만 받는다.
    """
    block = review_loop.get("early_completion")
    issues = _opt_in_block_issues(block, _EARLY_COMPLETION_KEYS, _EARLY_COMPLETION_CODES,
                                  "review_loop.early_completion")
    if not isinstance(block, dict):
        return issues
    if "minimum_completed_rounds" in block:
        value = block.get("minimum_completed_rounds")
        if type(value) is not int or value < EARLY_COMPLETION_ROUND_FLOOR:
            issues.append(("FAIL", Diagnostic("validate.early_completion_round_floor",
                                              floor=EARLY_COMPLETION_ROUND_FLOOR)))
    return issues


def _review_loop_issues(profile):
    """review_loop(Loop A) 의미검증 — "유효 YAML 이지만 루프 침묵/오동작" 을 fail-closed 차단.

    구조 규칙은 enabled 와 무관하게 항상 검사(오타·잘못된 어휘는 끄든 켜든 오류). 침묵-비활성 규칙
    (빈 lenses, refuters<1)은 enabled=true 일 때만 — 꺼진 루프의 빈 설정은 정상이기 때문.
    jsonschema 미설치에서도 동작하도록 키/어휘 검사는 순수 파이썬(N-R1/P0-2 패턴)."""
    # (codex 재리뷰) 부모 섹션 비-dict(truthy)면 .get() 크래시 → 제어 종료. pdca 비-dict 의 FAIL 은
    #   _semantic_issues 섹션 타입 가드가 단일 출처로 발행(여기선 중복 회피 위해 조용히 종료).
    pdca = profile.get("pdca")
    if pdca is not None and not isinstance(pdca, dict):
        return []
    rl = (pdca or {}).get("review_loop")
    if rl is None:
        return []   # review_loop 미선언 = Loop A 미사용(정상)
    if not isinstance(rl, dict):
        return [("FAIL", Diagnostic("validate.review_loop_not_mapping"))]

    issues = []
    # 0. 미지 키(오타) — jsonschema 없어도 항상 적발(닫힌 섹션 철학).
    #    key=str: malformed YAML 의 혼합타입 키({1, "foo"})를 sorted 가 비교하다 TypeError 나는 것 방지(codex).
    unknown = sorted(set(rl.keys()) - _REVIEW_LOOP_KEYS, key=str)
    if unknown:
        issues.append(("FAIL", Diagnostic("validate.review_loop_unknown_keys", keys=unknown,
                                          allowed=sorted(_REVIEW_LOOP_KEYS))))
    issues.extend(_early_completion_issues(rl))

    # enabled 타입 검사 (codex P0): bool 아닌 truthy(enabled:1, "true")는 `is True` 가 False →
    # 루프가 침묵 비활성. jsonschema 없으면 type:boolean 도 못 잡으므로 순수파이썬으로 fail-closed.
    enabled_raw = rl.get("enabled")
    if enabled_raw is not None and not isinstance(enabled_raw, bool):
        issues.append(("FAIL", Diagnostic("validate.review_loop_enabled_not_bool",
                                          value=repr(enabled_raw))))
    enabled = enabled_raw is True

    # 1. lenses — enabled 인데 비면 FIND 가 아무 렌즈도 안 돌아 루프가 침묵(최악 실패 모드).
    #    (codex 재리뷰 P1) 리스트 아닌 타입(lenses:true)은 순수파이썬에서 iterate 시 TypeError 크래시 →
    #    제어된 FAIL 로 전환(jsonschema 없어도 크래시 대신 fail-closed).
    lenses, lens_issue = _as_list(rl, "lenses")
    issues += lens_issue
    if enabled and not lenses and not lens_issue:
        issues.append(("FAIL", Diagnostic("validate.review_loop_lenses_empty")))
    bad_lens = sorted({x for x in lenses if x not in _KNOWN_LENSES}, key=str)
    if bad_lens:
        issues.append(("FAIL", Diagnostic("validate.review_loop_lenses_unknown", lenses=bad_lens,
                                          allowed=sorted(_KNOWN_LENSES))))

    # 2. sentinel-or-bool 필드 (codex P1): cross_model/architecture_escalation 은 정해진 sentinel
    #    문자열 또는 bool 만. 오타(from_option.cross_model, from_risk.ll3)는 sentinel 불일치로 host 가
    #    동작을 침묵 누락 → "유효 YAML, 비활성 동작" 갭. 알 수 없는 문자열은 FAIL.
    issues += _sentinel_or_bool_issue(rl, "cross_model", "from_options.cross_model")
    issues += _sentinel_or_bool_issue(rl, "architecture_escalation", "from_risk.l3")

    # 3. max_iterations / budget_tokens — tier 키는 {L2,L3} 만, 값은 양수 정수(bool 불가: True==1 회피).
    #    (codex P1) enabled 면 루프 tier(L2/L3) 가 *모두 존재*해야 함 — L3 누락/오타(L33)는 해당 위험도
    #    변경이 상한 없이 무한 루프. WARN 이 아니라 fail-closed.
    for key, floor in (("max_iterations", 1), ("budget_tokens", 1)):
        tiers = rl.get(key)
        if tiers is None:
            if enabled:
                issues.append(("FAIL", Diagnostic("validate.review_loop_tier_key_missing", field=key,
                                                  allowed=sorted(_LOOP_TIERS))))
            continue
        if not isinstance(tiers, dict):
            issues.append(("FAIL", Diagnostic("validate.review_loop_tier_not_mapping", field=key)))
            continue
        unknown_tier = sorted(set(tiers.keys()) - _LOOP_TIERS, key=str)
        if unknown_tier:
            issues.append(("WARN", Diagnostic("validate.review_loop_tier_out_of_scope", field=key,
                                              tiers=unknown_tier)))
        for tier, val in tiers.items():
            if tier not in _LOOP_TIERS:
                continue
            if isinstance(val, bool) or not isinstance(val, int) or val < floor:
                issues.append(("FAIL", Diagnostic("validate.review_loop_tier_value_invalid", field=key,
                                                  tier=tier, value=repr(val), floor=floor)))
        if enabled:
            missing = sorted(_LOOP_TIERS - set(tiers.keys()))
            if missing:
                issues.append(("FAIL", Diagnostic("validate.review_loop_tier_incomplete", field=key,
                                                  missing=missing)))

    # 4. severity_block — 차단 심각도 어휘 검사(오타 시 차단이 침묵). 리스트 가드(크래시 방지).
    sev_list, sev_issue = _as_list(rl, "severity_block")
    issues += sev_issue
    bad_sev = sorted({s for s in sev_list if s not in _KNOWN_SEVERITY}, key=str)
    if bad_sev:
        issues.append(("FAIL", Diagnostic("validate.review_loop_severity_unknown", severities=bad_sev,
                                          allowed=sorted(_KNOWN_SEVERITY))))

    # 4b. termination_enforce — 종료 검산 모드. advisory|enforce 만(오타 시 침묵 무효 방지). 비문자열 FAIL.
    te = rl.get("termination_enforce")
    if te is not None:
        if not isinstance(te, str) or te not in _TERMINATION_MODES:
            issues.append(("FAIL", Diagnostic("validate.review_loop_termination_mode_invalid", value=repr(te),
                                              allowed=sorted(_TERMINATION_MODES))))

    # 4c. report_gate_enforce — 06←05 audit 게이트 모드. off|advisory|enforce 만(오타 침묵 무효 방지). 비문자열 FAIL.
    rge = rl.get("report_gate_enforce")
    if rge is not None:
        if not isinstance(rge, str) or rge not in _REPORT_GATE_MODES:
            issues.append(("FAIL", Diagnostic("validate.review_loop_report_gate_mode_invalid", value=repr(rge),
                                              allowed=sorted(_REPORT_GATE_MODES))))
        elif rge == "enforce":
            issues.append(("WARN", Diagnostic("validate.review_loop_report_gate_enforce_warn")))

    # 5. refute_threshold — 비문자열(true/1)은 FAIL(schema type:string 과 일치), 미지원 문자열은 WARN(전방호환).
    thr = rl.get("refute_threshold")
    if thr is not None:
        if not isinstance(thr, str):
            issues.append(("FAIL", Diagnostic("validate.review_loop_refute_threshold_not_string",
                                              value=repr(thr))))
        elif thr != "majority":
            issues.append(("WARN", Diagnostic("validate.review_loop_refute_threshold_unsupported",
                                              value=thr)))

    # 6. 스칼라 노브 (codex P1): refuters/dry_rounds 타입·범위. bool/문자열/<1 → enabled 면 FAIL,
    #    꺼져 있어도 명백한 무효값은 WARN(켤 때 침묵 방지). isinstance(int) 만 보던 누락 보강.
    #    refuters 는 enabled 면 필수(반박자 수 미정 = REFUTE 단계 정의 불가). dry_rounds 는 선택(기본 1).
    issues += _positive_int_issue(rl, "refuters", enabled, required=True)
    issues += _positive_int_issue(rl, "dry_rounds", enabled)

    if not enabled:
        return issues   # 아래는 켜진 루프에서만 의미있는 degrade 경고

    # 7. cross_model 배선했으나 options.cross_model off → 루프가 opposite-runtime peer 없이 단일모델로 돈다.
    #    options 비-dict 는 _semantic_issues 가 FAIL → 여기선 크래시만 방지(coerce).
    options = profile.get("options")
    options = options if isinstance(options, dict) else {}
    if rl.get("cross_model") == "from_options.cross_model" and not options.get("cross_model"):
        issues.append(("WARN", Diagnostic("validate.review_loop_cross_model_ineffective")))

    # 8. architecture_escalation 배선했으나 risk.l3_* 전부 비었음 → arch 차단이 무력.
    risk = profile.get("risk")
    risk = risk if isinstance(risk, dict) else {}
    if rl.get("architecture_escalation") == "from_risk.l3" \
            and not any(risk.get(k) for k in ("l3_filename_globs", "l3_content_keywords")):
        issues.append(("WARN", Diagnostic("validate.review_loop_arch_escalation_ineffective")))
    return issues


def _sample_path_from_glob(g):
    """phase glob → 대표 직속-자식 경로. 로그 커버리지 사전점검용(post_tool_logger 가 이 06 파일을
    분류·기록할지). `**` 세그먼트는 0개 디렉토리 케이스(직속 자식)로 떨어뜨리고, `*` 는 probe 로,
    `*.ext` 는 probe.ext 로 치환한다. 예: plan_docs/06-report/**/*.md → plan_docs/06-report/probe.md."""
    if not isinstance(g, str) or not g:
        return ""
    segs = []
    for s in g.split("/"):
        if s == "**":
            continue
        if "*" in s:
            s = s.replace("*", "probe")
        segs.append(s)
    return "/".join(segs)


def _classifies(path, file_type_map):
    """post_tool_logger_core._classify 와 동일(ordered first-match fnmatch). 로그 커버리지 heuristic
    이라 하드 게이트 아님 — post_tool_logger 와 어휘가 어긋나도 WARN 오탐/미탐일 뿐."""
    import fnmatch
    if not isinstance(file_type_map, list):
        return False
    for entry in file_type_map:
        if not isinstance(entry, dict):
            continue
        gl = entry.get("glob", "")
        if gl and fnmatch.fnmatch(path, gl):
            return True
    return False


def _retro_gate_issues(profile):
    """pdca.retro.report_gate_enforce 검증(9-C v1) — off|advisory|enforce 만(오타 침묵 무효 방지).
    9.5 의 pdca.review_loop.report_gate_enforce 와 동일 어휘·검증 형태(단일 소스는 아니고 나란히 존재 —
    06←05 게이트와 Stop 게이트는 강제 지점이 달라 서로 다른 값을 가질 수 있어야 한다)."""
    pdca = profile.get("pdca")
    if not isinstance(pdca, dict):
        return []   # 비-dict pdca 는 _semantic_issues 가 이미 FAIL(중복 회피)
    retro = pdca.get("retro")
    if retro is None:
        return []
    if not isinstance(retro, dict):
        return [("FAIL", Diagnostic("validate.retro_not_mapping", actual=type(retro).__name__))]
    mode = retro.get("report_gate_enforce")
    if mode is None:
        return []
    if not isinstance(mode, str) or mode not in _REPORT_GATE_MODES:
        return [("FAIL", Diagnostic("validate.retro_gate_mode_invalid", value=repr(mode),
                                    allowed=sorted(_REPORT_GATE_MODES)))]
    if mode == "off":
        return []
    issues = []
    kc = profile.get("knowledge_capture")
    kc = kc if isinstance(kc, dict) else {}
    if not kc.get("retro_note"):
        issues.append(("WARN", Diagnostic("validate.retro_note_off", mode=mode)))
    # 게이트의 06 감지는 post_tool_logger 가 남긴 세션 로그에 의존한다 — 06 파일이 file_type_map 으로
    # 분류되지 않고 skip_untyped=true 면 로그에 안 남아 게이트가 조용히 무동작(codex 구현리뷰 P1).
    phases = pdca.get("phases")
    glob06 = ""
    if isinstance(phases, list):
        for ph in phases:
            if isinstance(ph, dict) and ph.get("id") == "06":
                glob06 = ph.get("glob") or ""
                break
    sample = _sample_path_from_glob(glob06)
    ftm = profile.get("file_type_map")
    skip_untyped = profile.get("skip_untyped", True)
    if sample and skip_untyped and not _classifies(sample, ftm):
        issues.append(("WARN", Diagnostic("validate.retro_06_not_classified", mode=mode, sample=sample)))
    return issues


def _writeback_gate_issues(profile):
    """pdca.writeback.depth_review_gate 검증 — off|advisory|enforce 만(오타 침묵 무효 방지). retro 게이트와
    동일 어휘·형태. 활성이면 write-back(update_after_dev)이 켜져 있어야 강제할 심층 노트가 생긴다."""
    pdca = profile.get("pdca")
    if not isinstance(pdca, dict):
        return []   # 비-dict pdca 는 _semantic_issues 가 이미 FAIL(중복 회피)
    wb = pdca.get("writeback")
    if wb is None:
        return []
    if not isinstance(wb, dict):
        return [("FAIL", Diagnostic("validate.writeback_not_mapping", actual=type(wb).__name__))]
    # 닫힌 키 집합 — jsonschema 미설치 시 schema additionalProperties:false 가 안 돌아, 오타
    # (예: depth_review_gates)가 조용히 게이트를 off 로 두는 걸 fail-closed 로 적발한다.
    unknown = sorted(set(wb.keys()) - {"depth_review_gate"}, key=str)
    if unknown:
        return [("FAIL", Diagnostic("validate.writeback_unknown_keys", keys=unknown))]
    mode = wb.get("depth_review_gate")
    if mode is None:
        return []
    if not isinstance(mode, str) or mode not in _REPORT_GATE_MODES:
        return [("FAIL", Diagnostic("validate.writeback_gate_mode_invalid", value=repr(mode),
                                    allowed=sorted(_REPORT_GATE_MODES)))]
    if mode == "off":
        return []
    issues = []
    kc = profile.get("knowledge_capture")
    kc = kc if isinstance(kc, dict) else {}
    if kc.get("update_after_dev") is not True:
        issues.append(("WARN", Diagnostic("validate.writeback_update_after_dev_off", mode=mode)))
    # 게이트의 06 감지는 로그기반 ∪ SessionStart 스냅샷이다. 로그기반이 주경로인데 06 문서가
    # file_type_map 으로 분류되지 않고 skip_untyped=true 면 post_tool_logger 가 안 남겨 감지가 약해진다
    # (retro 게이트와 동일 근거). WARN 으로 표면화한다.
    phases = pdca.get("phases")
    glob06 = ""
    if isinstance(phases, list):
        for ph in phases:
            if isinstance(ph, dict) and ph.get("id") == "06":
                glob06 = ph.get("glob") or ""
                break
    # 게이트의 06 감지(로그기반·스냅샷)는 pdca.phases 의 id=="06" glob 을 하드 참조한다. 그 phase 가
    # 없으면(또는 glob 빈값) enforce 여도 게이트가 조용히 무동작한다 — 침묵 비활성 대신 표면화한다.
    if not glob06:
        issues.append(("WARN", Diagnostic("validate.writeback_06_phase_missing", mode=mode)))
    sample = _sample_path_from_glob(glob06)
    ftm = profile.get("file_type_map")
    skip_untyped = profile.get("skip_untyped", True)
    if sample and skip_untyped and not _classifies(sample, ftm):
        issues.append(("WARN", Diagnostic("validate.writeback_06_not_classified", mode=mode, sample=sample)))
    return issues


def _as_list(rl, key):
    """리스트 필드 안전 추출 → (list, issues). 리스트 아닌 타입(true/문자열)은 순수파이썬에서
    iterate 시 TypeError 크래시 위험 → 제어된 FAIL 로 전환(codex 재리뷰 P1, jsonschema 없어도 견고)."""
    v = rl.get(key)
    if v is None:
        return [], []
    if not isinstance(v, list):
        return [], [("FAIL", Diagnostic("validate.list_field_invalid", field=key,
                                        actual=type(v).__name__))]
    return v, []


def _sentinel_or_bool_issue(rl, key, sentinel):
    """sentinel 문자열 또는 bool 만 허용. 그 외 문자열(오타)은 FAIL — host 가 sentinel 못 알아보고
    동작을 침묵 누락하는 갭 차단(codex P1)."""
    v = rl.get(key)
    if v is None or isinstance(v, bool) or v == sentinel:
        return []
    return [("FAIL", Diagnostic("validate.sentinel_or_bool_invalid", field=key, value=repr(v),
                                sentinel=sentinel))]


def _positive_int_issue(rl, key, enabled, required=False):
    """양수 정수 노브 검사. malformed(bool/문자열/<1)는 enabled 무관 항상 FAIL — schema(type:integer,
    minimum:1)와 일치시켜 jsonschema 유무 분기를 없앤다. isinstance(bool) 선검사로 True==1 통과 차단
    (codex P1). required 면 enabled 인데 누락 시 FAIL(꺼져 있으면 누락 허용 — 기본값 적용)."""
    v = rl.get(key)
    if v is None:
        if required and enabled:
            return [("FAIL", Diagnostic("validate.positive_int_required", field=key))]
        return []
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        return [("FAIL", Diagnostic("validate.positive_int_invalid", field=key, value=repr(v)))]
    return []


def _schema_path(root):
    sp = os.path.join(root, "schema", "profile.schema.json")
    if os.path.exists(sp):
        return sp
    try:
        from sage import _resources
        cand = os.path.join(_resources.schema_dir(), "profile.schema.json")
        return cand if os.path.exists(cand) else ""
    except Exception:
        return ""


def _closed_section_keys(root):
    """스키마의 additionalProperties:false 섹션별 허용 키 집합. 스키마 로드 실패 시 폴백."""
    sp = _schema_path(root)
    if sp:
        try:
            schema = json.loads(Path(sp).read_text(encoding="utf-8"))
            out = {}
            for sec, node in (schema.get("properties") or {}).items():
                if node.get("additionalProperties") is False and node.get("properties"):
                    out[sec] = set(node["properties"].keys())
            if out:
                return out
        except Exception:
            pass
    return {k: set(v) for k, v in _CLOSED_SECTION_FALLBACK.items()}


def _schema_issues(profile, root):
    try:
        import jsonschema
    except ImportError:
        return [("WARN", Diagnostic("validate.jsonschema_missing"))]
    except Exception as e:
        # 손상된 jsonschema 설치(ImportError 외 예외)도 구조검증만 불가 → 의미검증 폴백(WARN). codex.
        return [("WARN", Diagnostic("validate.jsonschema_load_failed", kind=type(e).__name__))]
    sp = _schema_path(root)
    if not sp:
        return [("WARN", Diagnostic("validate.schema_file_missing"))]
    try:
        schema = json.loads(Path(sp).read_text(encoding="utf-8"))
        jsonschema.validate(profile, schema)
        return []
    except jsonschema.ValidationError as e:
        loc = "/".join(str(x) for x in e.absolute_path) or "(root)"
        return [("FAIL", Diagnostic("validate.schema_violation", location=loc, evidence=e.message))]
    except Exception as e:
        # SAGE-infra 실패(손상된 schema 파일·SchemaError·기타 jsonschema 예외)는 사용자 입력 문제가 아니다.
        # 구조검증만 불가 → 의미검증(fail-closed 코어)으로 폴백(WARN). 입력-malformed FAIL 과 구분(codex).
        return [("WARN", Diagnostic("validate.schema_check_unavailable", kind=type(e).__name__))]


def _semantic_issues(profile, root):
    issues = [("FAIL", message) for message in materialization_issues(profile)]

    from sage.checklist_contract import checklist_target_issues
    issues.extend(("FAIL", message) for message in checklist_target_issues(profile, root))

    # 섹션 타입 가드(codex 재리뷰) — risk/pdca/options/knowledge_capture 가 truthy 비-dict 면 이후
    #   .get() 크래시(retro 등 런타임 읽기 포함). jsonschema 없어도 제어된 FAIL 을 단일 출처로 발행.
    # risk 루트 타입은 materialization_issues가 소유한다. 여기서 다시 발행하면 동일 FAIL이 중복된다.
    for section in ("sage", "pdca", "options", "knowledge_capture", "verification", "hooks", "context_management"):
        v = profile.get(section)
        if v is not None and not isinstance(v, dict):
            issues.append(("FAIL", Diagnostic("validate.section_not_mapping", section=section,
                                              actual=type(v).__name__)))
    sage_section = profile.get("sage") if isinstance(profile.get("sage"), dict) else {}
    if "required_version" in sage_section:
        from sage.version_contract import version_is_exact
        required_version = sage_section["required_version"]
        if not version_is_exact(required_version):
            issues.append(("FAIL", Diagnostic("validate.required_version_not_exact")))
    risk = profile.get("risk") if isinstance(profile.get("risk"), dict) else {}
    hooks = profile.get("hooks") if isinstance(profile.get("hooks"), dict) else {}
    root_env = hooks.get("project_root_env")
    if root_env not in (None, "", "SAGE_PROJECT_ROOT"):
        issues.append(("FAIL", Diagnostic("validate.project_root_env_unsupported", value=repr(root_env))))

    domains = risk.get("domains")
    if domains is not None and not isinstance(domains, list):
        domains = []
    seen_domains = set()
    for idx, domain in enumerate(domains or []):
        label = f"risk.domains[{idx}]"
        if not isinstance(domain, dict):
            continue
        did = domain.get("id")
        if not isinstance(did, str) or not did:
            issues.append(("FAIL", Diagnostic("validate.domain_id_invalid", label=label)))
        elif did in seen_domains:
            issues.append(("FAIL", Diagnostic("validate.domain_id_duplicated", value=did)))
        else:
            seen_domains.add(did)
        if domain.get("risk_level") not in ("L1", "L2", "L3"):
            issues.append(("FAIL", Diagnostic("validate.domain_risk_level_invalid", label=label)))
        # authoring↔render 파리티: pointer 는 render 와 동일한 helper 로 검사한다(codex R2-6/R3-4).
        # 이렇게 해야 validate OK·install FAIL(또는 그 역)로 갈리지 않는다. root 봉쇄까지 공유.
        from sage.routing_block import pointer_issue
        pe = pointer_issue(domain.get("protocol_pointer"), root)
        if pe:
            issues.append(("FAIL", Diagnostic("validate.domain_pointer_invalid", label=label, reason=pe)))

    exclusions = risk.get("l0_exclude_globs")
    if isinstance(exclusions, list):
        higher = set()
        for key in ("l1_path_globs", "l2_path_globs", "l3_filename_globs"):
            values = risk.get(key)
            if isinstance(values, list):
                higher.update(value for value in values if isinstance(value, str))
        for domain in domains or []:
            if not isinstance(domain, dict) or domain.get("risk_level") not in ("L1", "L2", "L3"):
                continue
            values = domain.get("path_globs")
            if isinstance(values, list):
                higher.update(value for value in values if isinstance(value, str))
        orphaned = [value for value in exclusions if isinstance(value, str) and value not in higher]
        if orphaned:
            issues.append(("FAIL", Diagnostic("validate.l0_exclude_orphaned", globs=orphaned)))

    # 0. 폐쇄 섹션 미지 키(오타) 적발 — jsonschema 선택의존과 무관하게 항상 동작(N-R1/P0-2).
    #    예: l3_filename_globs→l3_filename_glob 오타가 빈 리스트로 통과해 L3 게이트가 침묵
    #    비활성되는 거버넌스 최악 실패 모드를 기본 설치(jsonschema 없음)에서도 차단.
    for section, allowed in _closed_section_keys(root).items():
        sec = profile.get(section)
        if isinstance(sec, dict):
            unknown = sorted(set(sec.keys()) - allowed, key=str)
            if unknown:
                issues.append(("FAIL", Diagnostic("validate.closed_section_unknown_keys", section=section,
                                                  keys=unknown)))

    # 1. L3 review 전략 모듈 존재 — 없으면 전략 미선택과 동일(L3 BLOCK). 오타/미배치 적발.
    strat = risk.get("l3_review_strategy") or ""
    if strat:
        mp = os.path.join(root, "scripts", "sage_harness", "hooks", "strategies",
                          "pre_implementation_gate", f"{strat}.py")
        if not os.path.exists(mp):
            issues.append(("FAIL", Diagnostic("validate.l3_strategy_missing", strategy=strat,
                                              path=os.path.relpath(mp, root))))

    # 2. pre_implementation_required 가 pdca.phases 에 정의된 id 만 참조하는지.
    #    phases/pre_implementation_required/req 가 기대 타입(list/dict/list) 아니면 .items()/iterate 크래시 →
    #    isinstance 가드로 무시(섹션 타입 FAIL 은 위 가드/스키마가 발행). codex: 비-iterable malformed 방어.
    pdca = profile.get("pdca") if isinstance(profile.get("pdca"), dict) else {}
    phases = pdca.get("phases")
    phase_ids = {p.get("id") for p in phases if isinstance(p, dict) and p.get("id")} if isinstance(phases, list) else set()
    pir = pdca.get("pre_implementation_required")
    for lvl, req in (pir.items() if isinstance(pir, dict) else []):
        unknown = [r for r in req if r not in phase_ids] if isinstance(req, list) else []
        if unknown:
            issues.append(("FAIL", Diagnostic("validate.pre_implementation_unknown_phase", level=lvl,
                                              phases=unknown, defined=sorted(phase_ids, key=str))))

    # 3. 위험 분류 글롭이 전부 비면 게이트가 사실상 무동작(의도일 수 있어 INFO).
    if not any(risk.get(k) for k in ("l1_path_globs", "l2_path_globs", "l3_filename_globs")):
        issues.append(("INFO", Diagnostic("validate.risk_globs_all_empty")))
    return issues


def _acceptance_issues(profile):
    """verification.acceptance 의미검증.

    acceptance 는 '빌드/테스트 통과 != 사용자 요구사항 충족' 갭을 닫는 게이트다. 오타/타입 오류가
    있으면 04/05/06 수용증거 확인이 침묵 비활성될 수 있으므로 review_loop 처럼 fail-closed 로 본다.
    """
    verification = profile.get("verification")
    if verification is not None and not isinstance(verification, dict):
        return []   # _semantic_issues 의 섹션 타입 가드가 단일 FAIL 출처
    ac = (verification or {}).get("acceptance")
    if ac is None:
        return []
    if not isinstance(ac, dict):
        return [("FAIL", Diagnostic("validate.acceptance_not_mapping"))]

    issues = []
    unknown = sorted(set(ac.keys()) - _ACCEPTANCE_KEYS, key=str)
    if unknown:
        issues.append(("FAIL", Diagnostic("validate.acceptance_unknown_keys", keys=unknown,
                                          allowed=sorted(_ACCEPTANCE_KEYS))))

    enabled_raw = ac.get("enabled")
    if enabled_raw is not None and not isinstance(enabled_raw, bool):
        issues.append(("FAIL", Diagnostic("validate.acceptance_enabled_not_bool", value=repr(enabled_raw))))
    enabled = enabled_raw is True

    tiers = ac.get("require_for_risk")
    if tiers is not None:
        if not isinstance(tiers, list):
            issues.append(("FAIL", Diagnostic("validate.acceptance_require_for_risk_not_list")))
        else:
            bad = sorted({x for x in tiers if x not in _ACCEPTANCE_TIERS}, key=str)
            if bad:
                issues.append(("FAIL", Diagnostic("validate.acceptance_require_for_risk_unknown", risks=bad,
                                                  allowed=sorted(_ACCEPTANCE_TIERS))))
            if enabled and "L3" not in tiers:
                issues.append(("FAIL", Diagnostic("validate.acceptance_require_for_risk_missing_l3")))

    statuses = ac.get("statuses")
    if statuses is None:
        statuses = []
    elif not isinstance(statuses, list) or not all(isinstance(x, str) and x.strip() for x in statuses):
        issues.append(("FAIL", Diagnostic("validate.acceptance_statuses_not_string_list")))
        statuses = []
    normalized_statuses = {s.upper() for s in statuses}
    if enabled and not statuses:
        issues.append(("FAIL", Diagnostic("validate.acceptance_statuses_empty")))
    missing_canonical = sorted(_CANONICAL_ACCEPTANCE_STATUSES - normalized_statuses)
    extra_statuses = sorted(normalized_statuses - _CANONICAL_ACCEPTANCE_STATUSES)
    if enabled and missing_canonical:
        issues.append(("FAIL", Diagnostic("validate.acceptance_statuses_missing_canonical",
                                          statuses=missing_canonical)))
    if extra_statuses:
        issues.append(("FAIL", Diagnostic("validate.acceptance_statuses_nonstandard",
                                          statuses=extra_statuses)))

    unresolved = ac.get("unresolved_statuses")
    if unresolved is None:
        unresolved = []
    elif not isinstance(unresolved, list) or not all(isinstance(x, str) and x.strip() for x in unresolved):
        issues.append(("FAIL", Diagnostic("validate.acceptance_unresolved_not_string_list")))
        unresolved = []
    normalized_unresolved = {s.upper() for s in unresolved}
    unknown_unresolved = sorted(normalized_unresolved - normalized_statuses)
    if unknown_unresolved and normalized_statuses:
        issues.append(("FAIL", Diagnostic("validate.acceptance_unresolved_unknown",
                                          statuses=unknown_unresolved)))
    if enabled and not {"FAIL", "NOT TESTED"}.issubset(normalized_unresolved):
        issues.append(("FAIL", Diagnostic("validate.acceptance_unresolved_missing_required")))

    mode = ac.get("report_gate_enforce")
    by_risk = ac.get("report_gate_by_risk")
    if mode is not None and by_risk is not None:
        issues.append(("FAIL", Diagnostic("validate.acceptance_gate_mode_conflict")))
    if mode is not None and (not isinstance(mode, str) or mode not in _REPORT_GATE_MODES):
        issues.append(("FAIL", Diagnostic("validate.acceptance_gate_mode_invalid", value=repr(mode),
                                          allowed=sorted(_REPORT_GATE_MODES))))
    elif mode is not None:
        issues.append(("WARN", Diagnostic("validate.acceptance_gate_mode_legacy_warn")))

    if by_risk is not None:
        if not isinstance(by_risk, dict):
            issues.append(("FAIL", Diagnostic("validate.acceptance_gate_by_risk_not_mapping")))
        else:
            unknown_risks = sorted(set(by_risk) - _ACCEPTANCE_TIERS, key=str)
            if unknown_risks:
                issues.append(("FAIL", Diagnostic("validate.acceptance_gate_by_risk_unknown_risk",
                                                  risks=unknown_risks)))
            for risk, expected in (("L1", "advisory"), ("L2", "advisory"), ("L3", "enforce")):
                value = by_risk.get(risk)
                if value is not None and value not in ("advisory", "enforce"):
                    issues.append(("FAIL", Diagnostic("validate.acceptance_gate_by_risk_value_invalid",
                                                      risk=risk, value=repr(value))))
                elif value is not None and value != expected:
                    issues.append(("FAIL", Diagnostic("validate.acceptance_gate_by_risk_value_locked",
                                                      risk=risk, expected=expected)))
            if enabled and (by_risk.get("L2"), by_risk.get("L3")) != ("advisory", "enforce"):
                issues.append(("FAIL", Diagnostic("validate.acceptance_gate_by_risk_incomplete")))

    waiver = ac.get("waiver")
    if waiver is not None:
        if not isinstance(waiver, dict):
            issues.append(("FAIL", Diagnostic("validate.acceptance_waiver_not_mapping")))
        else:
            unknown_waiver = sorted(set(waiver) - {"enabled"}, key=str)
            if unknown_waiver:
                issues.append(("FAIL", Diagnostic("validate.acceptance_waiver_unknown_keys",
                                                  keys=unknown_waiver)))
            waiver_enabled = waiver.get("enabled")
            if waiver_enabled is not None and not isinstance(waiver_enabled, bool):
                issues.append(("FAIL", Diagnostic("validate.acceptance_waiver_enabled_not_bool")))

    return issues


def _knowledge_capture_issues(profile):
    """knowledge_capture vault-output 플래그(loop_audit_dashboard/retro_note) 의존 검증.
    vault 출력은 부가 기능(거버넌스 게이트 아님)이라 WARN 수준: 켰는데 vault_path 비면 무동작(OFF) 알림,
    비-bool 이면 `is True` 로 침묵 off 되니 타입 WARN. knowledge_capture 는 open object 라 키 오타는
    스키마/여기서 강제 안 함(freeform 키 보존) — 이 둘만 점검."""
    kc = profile.get("knowledge_capture")
    if not isinstance(kc, dict):
        return []   # 비-dict 는 _semantic_issues 섹션 가드가 FAIL 로 발행(중복 회피)
    issues = []
    vp = kc.get("vault_path")
    # vault_path 는 문자열이어야 함 — 비-str(예: 123)이면 vault_target 의 .strip() 이 런타임 크래시(codex A).
    if vp is not None and not isinstance(vp, str):
        issues.append(("WARN", Diagnostic("validate.knowledge_capture_vault_path_not_string",
                                          value=repr(vp))))
    vault = (vp or "").strip() if isinstance(vp, str) else ""
    for key in ("scan_before_dev", "update_after_dev", "loop_audit_dashboard", "fast_cycle_dashboard", "retro_note"):
        v = kc.get(key)
        if v is None:
            continue
        if not isinstance(v, bool):
            issues.append(("WARN", Diagnostic("validate.knowledge_capture_flag_not_bool", field=key,
                                              value=repr(v))))
        elif v is True and not vault:
            issues.append(("WARN", Diagnostic("validate.knowledge_capture_flag_vault_off", field=key)))
    return issues


def _feedback_issues(profile):
    """feedback(§10-a-C sage-feedback 마커) 섹션 검증 — 키 어휘 닫힘 + 타입 + 의존.

    `enabled`/`block_release` 는 게이트 강제력에 직접 관여하므로 비-bool 은 `is True` 로
    침묵 off 되는 걸 막아 FAIL 로 올린다(knowledge_capture 의 부가 출력 플래그가 WARN 인 것과 대비).
    `record`/`record_target` 은 기록 부가 기능이라 WARN.
    """
    section = profile.get("feedback")
    if section is None:
        return []                      # 섹션 미설정 = 기능 off (하위호환)
    if not isinstance(section, dict):
        return [("FAIL", Diagnostic("validate.feedback_not_mapping", value=repr(section)))]

    issues = []
    unknown = sorted((str(k) for k in section if k not in _FEEDBACK_KEYS))
    if unknown:
        issues.append(("FAIL", Diagnostic("validate.feedback_unknown_keys", keys=", ".join(unknown),
                                          allowed=", ".join(sorted(_FEEDBACK_KEYS)))))

    for key in ("enabled", "block_release"):
        value = section.get(key)
        if value is not None and not isinstance(value, bool):
            issues.append(("FAIL", Diagnostic("validate.feedback_flag_not_bool", field=key,
                                              value=repr(value))))

    record = section.get("record")
    if record is not None and not isinstance(record, bool):
        issues.append(("WARN", Diagnostic("validate.feedback_record_not_bool", value=repr(record))))

    target = section.get("record_target")
    if target is not None and target not in _FEEDBACK_RECORD_TARGETS:
        issues.append(("WARN", Diagnostic("validate.feedback_record_target_invalid", value=repr(target),
                                          allowed="|".join(sorted(_FEEDBACK_RECORD_TARGETS)))))

    # block_release 는 enabled 없이는 무동작 — 침묵 무시 대신 명시적으로 알린다.
    if section.get("block_release") is True and section.get("enabled") is not True:
        issues.append(("WARN", Diagnostic("validate.feedback_block_release_ineffective")))
    return issues


def _governance_docs_issues(profile, root):
    """governance_docs(FB25 라우팅 블록 소스) 의미검증 — fail-closed.

    라우팅 블록은 auto-loaded AGENT_GUIDE 에 주입되므로, 여기 담긴 문자열은 gate-relaxation
    프로즈나 마커 토큰을 심는 경로가 될 수 있다. jsonschema 미설치에서도 동작하도록 순수 파이썬으로
    키 어휘·타입·안전 경로를 강제하고, doc 은 프로젝트 상대 실재 파일이어야 하며(부재 시 라우팅이
    허깨비 경로를 가리킴), label/doc 에 오버레이 gate-relaxation 스캔과 예약 마커 토큰 검사를
    적용한다(overlay 저작과 동일 방어). 규칙 본문이 아니라 경로 포인터만 담기게 한다.
    """
    if "governance_docs" not in profile:
        return []
    docs = profile.get("governance_docs")
    if docs is None:
        # 명시적 null 은 malformed non-list — silent-strip 방지(codex R3-2). 키 부재만 정상.
        return [("FAIL", Diagnostic("validate.governance_docs_null"))]
    if not isinstance(docs, list):
        return [("FAIL", Diagnostic("validate.governance_docs_not_list"))]

    # entry 타입·미지 키·필드 안전성(문법·단일라인·gate-relaxation·마커 토큰·경로 봉쇄+실재)은 모두
    # render 경계와 동일 함수를 단일 소스로 공유한다 — 검증과 render 가 어긋나면 한쪽만 통과하는 갭이
    # 생기고, 여기에 별도 미지-키 검사를 두면 같은 오타를 두 번 보고한다.
    from sage.routing_block import routing_input_issues
    issues = []
    for where, reason in routing_input_issues(None, docs, root):
        issues.append(("FAIL", Diagnostic("validate.governance_docs_entry", where=where, reason=reason)))
    return issues


def _cross_model_issues(profile):
    """cross_model 검증. 판정은 review 의 `cross_model_issues` 가 소유한다 — validate 와 cross-check 가
    서로 다른 규칙을 쓰면, cross-check 가 오타 키/미구현 값을 조용히 무시한 채 기본값으로 돈다(codex 7R).
    여기서는 그 위에 "설정했지만 cross_model:false 라 무동작" WARN 만 얹는다."""
    from sage.commands.review import cross_model_issues, resolve_effort

    issues = list(cross_model_issues(profile))
    if any(sev == "FAIL" for sev, _ in issues):
        return issues
    _, configured = resolve_effort(profile)
    opts = profile.get("options")
    on = bool(opts.get("cross_model", False)) if isinstance(opts, dict) else False
    if configured is not None and not on:
        issues.append(("WARN", Diagnostic("validate.cross_model_effort_ineffective", effort=configured)))
    return issues


def _team_agent_issues(profile):
    """team.core.<role>.runtime.{model,effort} 검증. 판정은 install 의 `team_runtime_issues` 가 소유한다 —
    install(주입 직전 관문)과 validate 가 서로 다른 규칙을 쓰면, validate 를 건너뛴 `install --force` 가
    오타 설정을 조용히 무시한 채 성공한다(codex 4R)."""
    from sage.commands.install import team_runtime_issues

    return team_runtime_issues(profile)


def _runtime_host_issues(profile):
    from sage.runtime_hosts import profile_issues
    return profile_issues(profile)


def _component_model_issues(profile):
    from sage.model_routing import component_issues
    return component_issues(profile)


def validate_profile(profile, root):
    """구조 + 의미 검증 결과 [(severity, message)]. 어떤 입력에도 예외를 던지지 않는다(totality 계약).

    거버넌스 게이트는 fail-closed — malformed profile 에 미제어 예외(traceback)가 아니라 제어된 FAIL 을
    내야 한다. 구체 검사(섹션 타입·키 어휘·스칼라 범위)가 현실적 오류를 친절한 메시지로 잡고, 그 아래
    예외 backstop 이 병적 잔여(중첩된 unhashable 값 등)를 FAIL 로 봉쇄(codex 재리뷰). 정상 입력의 로직
    버그가 이 backstop 에 가려지지 않도록 테스트가 정상 케이스의 구체 severity 를 검증한다.

    totality 범위 = 신뢰 불가한 `profile`(파싱된 YAML) 입력. `root` 는 SAGE 내부 호출자(generate/validate)가
    항상 경로 문자열로 주입하는 신뢰 파라미터다 — 비-경로 root 는 호출자 버그이므로 의도적으로 감싸지 않는다
    (감싸면 실제 버그를 'malformed profile' 로 오귀속해 masking). 즉 보장은 'profile 입력으로는 절대 크래시
    안 함'이다(codex 재리뷰 결정)."""
    # profile 최상위가 매핑이 아니면(빈/스칼라/리스트 YAML) 모든 서브검증이 .get() 크래시 → 단일 FAIL 로 차단.
    if not isinstance(profile, dict):
        return [("FAIL", Diagnostic("validate.top_level_not_mapping", actual=type(profile).__name__))]
    issues = _schema_issues(profile, root)
    try:
        from sage.context_packet import profile_issues as context_profile_issues

        issues = issues + _semantic_issues(profile, root) + _review_loop_issues(profile) \
            + _done_criteria_gate_issues(profile) \
            + _cycle_binding_visibility_issues(profile) \
            + _fast_cycle_issues(profile) \
            + _acceptance_issues(profile) + _knowledge_capture_issues(profile) \
            + _cross_model_issues(profile) + _team_agent_issues(profile) + _retro_gate_issues(profile) \
            + _writeback_gate_issues(profile) + _governance_docs_issues(profile, root) \
            + _feedback_issues(profile)
        issues = issues + _runtime_host_issues(profile) + _component_model_issues(profile) \
            + context_profile_issues(profile)
    except Exception as e:
        issues.append(("FAIL", Diagnostic("validate.exception_fallback", kind=type(e).__name__)))
    return issues


def severity_of(issues):
    """집계 severity. 비면 PASS."""
    return max((s for s, _ in issues), key=lambda s: _RANK[s], default="PASS")
