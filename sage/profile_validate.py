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

_RANK = {"INFO": 0, "WARN": 1, "FAIL": 2}

# 폐쇄 섹션(스키마 additionalProperties:false)의 허용 키 — jsonschema 가 없어도 오타 키를
# 항상 적발하기 위한 폴백(N-R1/P0-2). 권위 출처는 schema/profile.schema.json 이며, 스키마를
# 읽을 수 있으면 거기서 로드해 드리프트를 막는다. 폴백은 스키마 파일이 아예 없을 때만 쓰인다.
_CLOSED_SECTION_FALLBACK = {
    "risk": {"desktop_block_glob", "desktop_block_hint", "generic_tokens", "l0_pass_globs",
             "l1_path_globs", "l2_content_keywords", "l2_path_globs", "l3_content_keywords",
             "l3_filename_globs", "l3_review_strategy", "plan_glob", "review_patterns"},
    "pdca": {"approve_marker", "approve_phase", "enabled", "phases",
             "pre_implementation_required", "report_phase", "review_loop"},
    "output_contract": {"markers"},
    "mcp": {"enabled"},
    "extraction": {"config"},
}

# review_loop(Loop A) 엔진 어휘 — 스택 중립(severity·risk level 처럼 엔진 레벨 vocabulary, 도메인값 아님).
# 닫힌 집합이라 오타(예: secuirty)를 fail-closed 로 적발 — jsonschema 선택의존과 무관하게 항상 동작.
_KNOWN_LENSES = {"correctness", "security", "concurrency", "convention", "lifecycle",
                 "performance", "error_handling", "data_integrity", "api_contract"}
_KNOWN_SEVERITY = {"P0", "P1", "P2", "P3"}
_LOOP_TIERS = {"L2", "L3"}   # L0/L1 은 루프 없음(risk → mandatory phase 표)
_REVIEW_LOOP_KEYS = {"enabled", "lenses", "refuters", "refute_threshold", "max_iterations",
                     "dry_rounds", "budget_tokens", "cross_model", "severity_block",
                     "architecture_escalation", "termination_enforce", "report_gate_enforce"}
_TERMINATION_MODES = {"advisory", "enforce"}   # 종료 검산 모드(기본 advisory)
_REPORT_GATE_MODES = {"off", "advisory", "enforce"}   # 06←05 audit 게이트 모드(기본 advisory)
_ACCEPTANCE_KEYS = {"enabled", "require_for_risk", "statuses", "unresolved_statuses", "report_gate_enforce"}
_ACCEPTANCE_TIERS = {"L1", "L2", "L3"}
_CANONICAL_ACCEPTANCE_STATUSES = {"PASS", "FAIL", "NOT TESTED", "N/A"}


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
        return [("FAIL", "pdca.review_loop 는 매핑(object)이어야 함")]

    issues = []
    # 0. 미지 키(오타) — jsonschema 없어도 항상 적발(닫힌 섹션 철학).
    #    key=str: malformed YAML 의 혼합타입 키({1, "foo"})를 sorted 가 비교하다 TypeError 나는 것 방지(codex).
    unknown = sorted(set(rl.keys()) - _REVIEW_LOOP_KEYS, key=str)
    if unknown:
        issues.append(("FAIL", f"pdca.review_loop 에 미지 키(오타 추정) {unknown} → 루프 설정 침묵 무시 위험. "
                               f"허용 키: {sorted(_REVIEW_LOOP_KEYS)}"))

    # enabled 타입 검사 (codex P0): bool 아닌 truthy(enabled:1, "true")는 `is True` 가 False →
    # 루프가 침묵 비활성. jsonschema 없으면 type:boolean 도 못 잡으므로 순수파이썬으로 fail-closed.
    enabled_raw = rl.get("enabled")
    if enabled_raw is not None and not isinstance(enabled_raw, bool):
        issues.append(("FAIL", f"pdca.review_loop.enabled={enabled_raw!r} 는 bool(true/false)이어야 함 — "
                               f"enabled:1/\"true\" 류는 루프가 침묵 비활성됨"))
    enabled = enabled_raw is True

    # 1. lenses — enabled 인데 비면 FIND 가 아무 렌즈도 안 돌아 루프가 침묵(최악 실패 모드).
    #    (codex 재리뷰 P1) 리스트 아닌 타입(lenses:true)은 순수파이썬에서 iterate 시 TypeError 크래시 →
    #    제어된 FAIL 로 전환(jsonschema 없어도 크래시 대신 fail-closed).
    lenses, lens_issue = _as_list(rl, "lenses")
    issues += lens_issue
    if enabled and not lenses and not lens_issue:
        issues.append(("FAIL", "pdca.review_loop.enabled=true 인데 lenses 가 비어 있음 → FIND 렌즈 0개 = 루프 침묵 비활성"))
    bad_lens = sorted({x for x in lenses if x not in _KNOWN_LENSES}, key=str)
    if bad_lens:
        issues.append(("FAIL", f"pdca.review_loop.lenses 에 미지 렌즈(오타 추정) {bad_lens}. "
                               f"엔진 어휘: {sorted(_KNOWN_LENSES)}"))

    # 2. sentinel-or-bool 필드 (codex P1): cross_model/architecture_escalation 은 정해진 sentinel
    #    문자열 또는 bool 만. 오타(from_option.cross_model, from_risk.ll3)는 sentinel 불일치로 host 가
    #    동작을 침묵 누락 → "유효 YAML, 비활성 동작" 갭. 알 수 없는 문자열은 FAIL.
    issues += _sentinel_or_bool_issue(rl, "cross_model", "from_options.cross_model")
    issues += _sentinel_or_bool_issue(rl, "architecture_escalation", "from_risk.l3")

    # 3. max_iterations / budget_tokens — tier 키는 {L2,L3} 만, 값은 양수 정수(bool 불가: True==1 회피).
    #    (codex P1) enabled 면 루프 tier(L2/L3) 가 *모두 존재*해야 함 — L3 누락/오타(L33)는 해당 위험도
    #    변경이 상한 없이 무한 루프. WARN 이 아니라 fail-closed.
    for key, floor, label in (("max_iterations", 1, "반복 상한"), ("budget_tokens", 1, "토큰 예산")):
        tiers = rl.get(key)
        if tiers is None:
            if enabled:
                issues.append(("FAIL", f"pdca.review_loop.{key} 누락 → 켜진 루프에 {label} 없음(무한 루프 위험). "
                                       f"{sorted(_LOOP_TIERS)} 필요"))
            continue
        if not isinstance(tiers, dict):
            issues.append(("FAIL", f"pdca.review_loop.{key} 는 tier 매핑(예: {{L2: .., L3: ..}})이어야 함"))
            continue
        unknown_tier = sorted(set(tiers.keys()) - _LOOP_TIERS, key=str)
        if unknown_tier:
            issues.append(("WARN", f"pdca.review_loop.{key} 에 루프 비대상 tier {unknown_tier} (루프는 L2/L3 만). 오타 확인"))
        for tier, val in tiers.items():
            if tier not in _LOOP_TIERS:
                continue
            if isinstance(val, bool) or not isinstance(val, int) or val < floor:
                issues.append(("FAIL", f"pdca.review_loop.{key}[{tier}]={val!r} → {label} 무효(정수 ≥{floor})"))
        if enabled:
            missing = sorted(_LOOP_TIERS - set(tiers.keys()))
            if missing:
                issues.append(("FAIL", f"pdca.review_loop.{key} 에 루프 tier {missing} 누락 → 해당 위험도 변경이 "
                                       f"{label} 없이 무한 루프 위험(fail-closed)"))

    # 4. severity_block — 차단 심각도 어휘 검사(오타 시 차단이 침묵). 리스트 가드(크래시 방지).
    sev_list, sev_issue = _as_list(rl, "severity_block")
    issues += sev_issue
    bad_sev = sorted({s for s in sev_list if s not in _KNOWN_SEVERITY}, key=str)
    if bad_sev:
        issues.append(("FAIL", f"pdca.review_loop.severity_block 에 미지 심각도(오타 추정) {bad_sev}. "
                               f"허용: {sorted(_KNOWN_SEVERITY)}"))

    # 4b. termination_enforce — 종료 검산 모드. advisory|enforce 만(오타 시 침묵 무효 방지). 비문자열 FAIL.
    te = rl.get("termination_enforce")
    if te is not None:
        if not isinstance(te, str) or te not in _TERMINATION_MODES:
            issues.append(("FAIL", f"pdca.review_loop.termination_enforce={te!r} → {sorted(_TERMINATION_MODES)} 중 하나만"))

    # 4c. report_gate_enforce — 06←05 audit 게이트 모드. off|advisory|enforce 만(오타 침묵 무효 방지). 비문자열 FAIL.
    rge = rl.get("report_gate_enforce")
    if rge is not None:
        if not isinstance(rge, str) or rge not in _REPORT_GATE_MODES:
            issues.append(("FAIL", f"pdca.review_loop.report_gate_enforce={rge!r} → {sorted(_REPORT_GATE_MODES)} 중 하나만"))
        elif rge == "enforce":
            issues.append(("WARN", "pdca.review_loop.report_gate_enforce=enforce — 모든 Phase 05 가 리뷰 루프를 "
                                   "돌(Loop-Run 기록) 때만 안전. L1-only cycle 이 섞이면 06 오차단 위험(advisory 로 측정 후 전환 권장)"))

    # 5. refute_threshold — 비문자열(true/1)은 FAIL(schema type:string 과 일치), 미지원 문자열은 WARN(전방호환).
    thr = rl.get("refute_threshold")
    if thr is not None:
        if not isinstance(thr, str):
            issues.append(("FAIL", f"pdca.review_loop.refute_threshold={thr!r} 는 문자열이어야 함(v1=majority)"))
        elif thr != "majority":
            issues.append(("WARN", f"pdca.review_loop.refute_threshold='{thr}' 미지원(v1=majority). majority 로 동작"))

    # 6. 스칼라 노브 (codex P1): refuters/dry_rounds 타입·범위. bool/문자열/<1 → enabled 면 FAIL,
    #    꺼져 있어도 명백한 무효값은 WARN(켤 때 침묵 방지). isinstance(int) 만 보던 누락 보강.
    #    refuters 는 enabled 면 필수(반박자 수 미정 = REFUTE 단계 정의 불가). dry_rounds 는 선택(기본 1).
    issues += _positive_int_issue(rl, "refuters", enabled, "REFUTE false-positive 필터", required=True)
    issues += _positive_int_issue(rl, "dry_rounds", enabled, "연속 dry 라운드 수렴 카운트")

    if not enabled:
        return issues   # 아래는 켜진 루프에서만 의미있는 degrade 경고

    # 7. cross_model 배선했으나 options.cross_model off → 루프가 opposite-runtime peer 없이 단일모델로 돈다.
    #    options 비-dict 는 _semantic_issues 가 FAIL → 여기선 크래시만 방지(coerce).
    options = profile.get("options")
    options = options if isinstance(options, dict) else {}
    if rl.get("cross_model") == "from_options.cross_model" and not options.get("cross_model"):
        issues.append(("WARN", "pdca.review_loop.cross_model=from_options.cross_model 이나 options.cross_model 가 off "
                               "→ REFUTE 가 단일모델(모델편향 못 없앰). cross_model 켜면 상대 런타임이 반박자"))

    # 8. architecture_escalation 배선했으나 risk.l3_* 전부 비었음 → arch 차단이 무력.
    risk = profile.get("risk")
    risk = risk if isinstance(risk, dict) else {}
    if rl.get("architecture_escalation") == "from_risk.l3" \
            and not any(risk.get(k) for k in ("l3_filename_globs", "l3_content_keywords")):
        issues.append(("WARN", "pdca.review_loop.architecture_escalation=from_risk.l3 이나 risk.l3_* 가 모두 비어 "
                               "→ 아키텍처 에스컬레이션(BLOCKED_ARCH) 무력. risk.l3_filename_globs/l3_content_keywords 채울 것"))
    return issues


def _as_list(rl, key):
    """리스트 필드 안전 추출 → (list, issues). 리스트 아닌 타입(true/문자열)은 순수파이썬에서
    iterate 시 TypeError 크래시 위험 → 제어된 FAIL 로 전환(codex 재리뷰 P1, jsonschema 없어도 견고)."""
    v = rl.get(key)
    if v is None:
        return [], []
    if not isinstance(v, list):
        return [], [("FAIL", f"pdca.review_loop.{key} 는 리스트여야 함(받음: {type(v).__name__})")]
    return v, []


def _sentinel_or_bool_issue(rl, key, sentinel):
    """sentinel 문자열 또는 bool 만 허용. 그 외 문자열(오타)은 FAIL — host 가 sentinel 못 알아보고
    동작을 침묵 누락하는 갭 차단(codex P1)."""
    v = rl.get(key)
    if v is None or isinstance(v, bool) or v == sentinel:
        return []
    return [("FAIL", f"pdca.review_loop.{key}={v!r} → '{sentinel}' 또는 bool 만 허용(오타 시 동작 침묵 누락)")]


def _positive_int_issue(rl, key, enabled, role, required=False):
    """양수 정수 노브 검사. malformed(bool/문자열/<1)는 enabled 무관 항상 FAIL — schema(type:integer,
    minimum:1)와 일치시켜 jsonschema 유무 분기를 없앤다. isinstance(bool) 선검사로 True==1 통과 차단
    (codex P1). required 면 enabled 인데 누락 시 FAIL(꺼져 있으면 누락 허용 — 기본값 적용)."""
    v = rl.get(key)
    if v is None:
        if required and enabled:
            return [("FAIL", f"pdca.review_loop.{key} 누락 → 켜진 루프에 {role} 미정. 정수 ≥1 필요")]
        return []
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        return [("FAIL", f"pdca.review_loop.{key}={v!r} → 정수 ≥1 필요({role}). 문자열/0/bool 불가")]
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
        return [("WARN", "jsonschema 미설치 — profile 구조검증 skip (pip install 'sage-harness[schema]')")]
    except Exception as e:
        # 손상된 jsonschema 설치(ImportError 외 예외)도 구조검증만 불가 → 의미검증 폴백(WARN). codex.
        return [("WARN", f"jsonschema 로드 실패({type(e).__name__}) — 구조검증 skip, 의미검증으로 폴백")]
    sp = _schema_path(root)
    if not sp:
        return [("WARN", "profile.schema.json 없음 — 구조검증 skip")]
    try:
        schema = json.loads(Path(sp).read_text(encoding="utf-8"))
        jsonschema.validate(profile, schema)
        return []
    except jsonschema.ValidationError as e:
        loc = "/".join(str(x) for x in e.absolute_path) or "(root)"
        return [("FAIL", f"profile 스키마 위반 @ {loc}: {e.message}")]
    except Exception as e:
        # SAGE-infra 실패(손상된 schema 파일·SchemaError·기타 jsonschema 예외)는 사용자 입력 문제가 아니다.
        # 구조검증만 불가 → 의미검증(fail-closed 코어)으로 폴백(WARN). 입력-malformed FAIL 과 구분(codex).
        return [("WARN", f"profile 구조검증 불가({type(e).__name__}) — schema 손상/오류 추정. 의미검증으로 폴백")]


def _semantic_issues(profile, root):
    issues = []

    # 섹션 타입 가드(codex 재리뷰) — risk/pdca/options/knowledge_capture 가 truthy 비-dict 면 이후
    #   .get() 크래시(retro 등 런타임 읽기 포함). jsonschema 없어도 제어된 FAIL 을 단일 출처로 발행.
    for section in ("risk", "pdca", "options", "knowledge_capture", "verification"):
        v = profile.get(section)
        if v is not None and not isinstance(v, dict):
            issues.append(("FAIL", f"{section} 섹션은 매핑(object)이어야 함(받음: {type(v).__name__})"))
    risk = profile.get("risk") if isinstance(profile.get("risk"), dict) else {}

    # 0. 폐쇄 섹션 미지 키(오타) 적발 — jsonschema 선택의존과 무관하게 항상 동작(N-R1/P0-2).
    #    예: l3_filename_globs→l3_filename_glob 오타가 빈 리스트로 통과해 L3 게이트가 침묵
    #    비활성되는 거버넌스 최악 실패 모드를 기본 설치(jsonschema 없음)에서도 차단.
    for section, allowed in _closed_section_keys(root).items():
        sec = profile.get(section)
        if isinstance(sec, dict):
            unknown = sorted(set(sec.keys()) - allowed, key=str)
            if unknown:
                issues.append(("FAIL", f"{section} 에 미지 키(오타 추정) {unknown} → 게이트 침묵 비활성 위험. "
                                       f"허용 키만 사용(스키마 properties)."))

    # 1. L3 review 전략 모듈 존재 — 없으면 전략 미선택과 동일(L3 BLOCK). 오타/미배치 적발.
    strat = risk.get("l3_review_strategy") or ""
    if strat:
        mp = os.path.join(root, "scripts", "sage_harness", "hooks", "strategies",
                          "pre_implementation_gate", f"{strat}.py")
        if not os.path.exists(mp):
            issues.append(("FAIL", f"risk.l3_review_strategy '{strat}' 모듈 없음 → L3 게이트 영구 BLOCK. "
                                   f"경로: {os.path.relpath(mp, root)}"))

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
            issues.append(("FAIL", f"pdca.pre_implementation_required[{lvl}] 미정의 phase 참조 {unknown} "
                                   f"(정의된 phase: {sorted(phase_ids, key=str)})"))

    # 3. 위험 분류 글롭이 전부 비면 게이트가 사실상 무동작(의도일 수 있어 INFO).
    if not any(risk.get(k) for k in ("l1_path_globs", "l2_path_globs", "l3_filename_globs")):
        issues.append(("INFO", "risk 의 l1/l2/l3 글롭이 모두 비어 있음 — 위험 게이트 사실상 무동작(의도면 무시)"))
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
        return [("FAIL", "verification.acceptance 는 매핑(object)이어야 함")]

    issues = []
    unknown = sorted(set(ac.keys()) - _ACCEPTANCE_KEYS, key=str)
    if unknown:
        issues.append(("FAIL", f"verification.acceptance 에 미지 키(오타 추정) {unknown} → acceptance gate 침묵 무시 위험. "
                               f"허용 키: {sorted(_ACCEPTANCE_KEYS)}"))

    enabled_raw = ac.get("enabled")
    if enabled_raw is not None and not isinstance(enabled_raw, bool):
        issues.append(("FAIL", f"verification.acceptance.enabled={enabled_raw!r} 는 bool(true/false)이어야 함"))
    enabled = enabled_raw is True

    tiers = ac.get("require_for_risk")
    if tiers is not None:
        if not isinstance(tiers, list):
            issues.append(("FAIL", "verification.acceptance.require_for_risk 는 리스트여야 함"))
        else:
            bad = sorted({x for x in tiers if x not in _ACCEPTANCE_TIERS}, key=str)
            if bad:
                issues.append(("FAIL", f"verification.acceptance.require_for_risk 에 미지 risk {bad}. "
                                       f"허용: {sorted(_ACCEPTANCE_TIERS)}"))
            if enabled and not tiers:
                issues.append(("WARN", "verification.acceptance.enabled=true 이나 require_for_risk 가 비어 있음 "
                                       "→ 어떤 위험도에서도 acceptance evidence 기대가 불명확"))

    statuses = ac.get("statuses")
    if statuses is None:
        statuses = []
    elif not isinstance(statuses, list) or not all(isinstance(x, str) and x.strip() for x in statuses):
        issues.append(("FAIL", "verification.acceptance.statuses 는 비어있지 않은 문자열 리스트여야 함"))
        statuses = []
    normalized_statuses = {s.upper() for s in statuses}
    if enabled and not statuses:
        issues.append(("FAIL", "verification.acceptance.enabled=true 인데 statuses 가 비어 있음"))
    missing_canonical = sorted(_CANONICAL_ACCEPTANCE_STATUSES - normalized_statuses)
    if enabled and missing_canonical:
        issues.append(("FAIL", f"verification.acceptance.statuses 에 표준 상태 {missing_canonical} 누락. "
                               "PASS/FAIL/NOT TESTED/N/A 를 명시해야 04/05 해석이 갈리지 않음"))

    unresolved = ac.get("unresolved_statuses")
    if unresolved is None:
        unresolved = []
    elif not isinstance(unresolved, list) or not all(isinstance(x, str) and x.strip() for x in unresolved):
        issues.append(("FAIL", "verification.acceptance.unresolved_statuses 는 비어있지 않은 문자열 리스트여야 함"))
        unresolved = []
    normalized_unresolved = {s.upper() for s in unresolved}
    unknown_unresolved = sorted(normalized_unresolved - normalized_statuses)
    if unknown_unresolved and normalized_statuses:
        issues.append(("FAIL", f"verification.acceptance.unresolved_statuses {unknown_unresolved} 가 statuses 에 없음"))
    if enabled and not {"FAIL", "NOT TESTED"}.issubset(normalized_unresolved):
        issues.append(("FAIL", "verification.acceptance.unresolved_statuses 는 FAIL 과 NOT TESTED 를 포함해야 함 "
                               "— 미구현/미검증 요구사항이 APPROVED 로 통과하는 것 방지"))

    mode = ac.get("report_gate_enforce")
    if mode is not None and (not isinstance(mode, str) or mode not in _REPORT_GATE_MODES):
        issues.append(("FAIL", f"verification.acceptance.report_gate_enforce={mode!r} → {sorted(_REPORT_GATE_MODES)} 중 하나만"))
    elif enabled and (mode or "off") == "off":
        issues.append(("WARN", "verification.acceptance.enabled=true 이나 report_gate_enforce=off "
                               "→ 06 report gate 에서 acceptance evidence 를 확인하지 않음"))
    elif mode == "enforce":
        issues.append(("WARN", "verification.acceptance.report_gate_enforce=enforce — 기존 프로젝트는 04 acceptance table "
                               "없으면 06 오차단 가능. advisory 로 측정 후 전환 권장"))

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
        issues.append(("WARN", f"knowledge_capture.vault_path={vp!r} 는 문자열이어야 함(경로). 비-str 은 vault 출력 시 무시/오류"))
    vault = (vp or "").strip() if isinstance(vp, str) else ""
    for key in ("scan_before_dev", "update_after_dev", "loop_audit_dashboard", "retro_note"):
        v = kc.get(key)
        if v is None:
            continue
        if not isinstance(v, bool):
            issues.append(("WARN", f"knowledge_capture.{key}={v!r} 는 bool 이어야 함(true/false). 비-bool 은 침묵 off 됨"))
        elif v is True and not vault:
            issues.append(("WARN", f"knowledge_capture.{key}=true 이나 vault_path 비어 있음 → vault 출력 OFF. "
                                   f"vault_path 설정해야 동작"))
    return issues


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
        return [("FAIL", f"profile 은 매핑(object)이어야 함 — 최상위가 key:value 구조여야 함(받음: {type(profile).__name__})")]
    issues = _schema_issues(profile, root)
    try:
        issues = issues + _semantic_issues(profile, root) + _review_loop_issues(profile) \
            + _acceptance_issues(profile) + _knowledge_capture_issues(profile)
    except Exception as e:
        issues.append(("FAIL", f"profile 의미검증 중 예외 — malformed profile 추정({type(e).__name__}). "
                               f"구조(중첩 값 타입) 점검 필요"))
    return issues


def severity_of(issues):
    """집계 severity. 비면 PASS."""
    return max((s for s, _ in issues), key=lambda s: _RANK[s], default="PASS")
