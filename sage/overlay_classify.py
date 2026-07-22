"""오버레이 합성 자격 분류(gate-classification) — 단일 resolver.

이슈 #5 봉쇄의 핵심: CORE 자산 오버레이가 물리 반영되면 "read overlay before CORE" 프로즈
보다 강하게 게이트-완화를 심을 수 있다(승인 조작 등). 그런데 게이트 완화 여부를 내용
린트로 막는 건 휴리스틱이라 우회 가능(theater). 그래서 **자격 단계**에서 막는다:

  (a) 게이트 비보유 or (b) 게이트가 자산 텍스트를 읽지 않는 독립 결정론 오라클(hook/CI)로
      강제됨 → 물리 합성 허용(compose).
  (c) 게이트 보유하나 아직 오라클 미보증 → 오버레이 경로 전면 차단(blocked): 합성도
      프로즈-read 도 없음. 오버레이 파일이 있으면 validate FAIL.

기본값은 fail-closed: **입증된 (a)/(b)만 compose**, 미분류/미지 자산은 전부 blocked.
(c)→(b) 재분류는 자산-불read 결정론 오라클(pre_implementation_gate_core)이 게이트를 floor 하고
적대적 우회 테스트가 GREEN 일 때만 이뤄진다(FB23). 미보증분은 GATE_BEARING_UNBACKED 로 남는다.

**(b) 멤버십 기준 = "primary 게이트가 floored"** (FB23 R3 정밀화): 자산의 *주된* 워크플로 기여가
자산-불read 오라클로 강제되면 (b). 여기서 오라클이 검증하는 것은 **구조**다 — 06←05 APPROVED 마커
존재, loop_audit 레코드 무결성, 04 evidence row/status 존재, bound phase 문서 존재. **내용의
진위**(04 PASS 가 실제 통과인지, 01 acceptance matrix 가 완전한지)는 어떤 오라클도 재검하지 않는다.
그래서 내용을 위조하는 forge(leader 가 01 matrix 를 축소, sage-team 이 qa 우회해 fake-PASS 04 대필,
qa 가 fake-PASS 기입)는 전부 미포착이다. 그러나 이것은 **오버레이 없이 base 자산도 동일하게 가진
선존 품질/LLM-신뢰 갭**이라 합성 delta=0 — 합성이 새로 여는 우회가 아니므로 합성 위협모델 밖이다.
leader/sage-cycle/sage-team 은 primary 기여(plan/phase 존재·사이클 시퀀싱)가 floored 라 (b);
**qa 는 primary 기여 자체가 그 미검증 내용(04 진위)**이라 (c) 로 남긴다(실행 재검 오라클=FB24/SD-9 대기).

install·sync·session-start(L1)·validate 는 오버레이를 다룰 때 반드시 이 모듈의 classify /
expected_block 을 경유한다 — 분류를 우회하는 합성 경로가 없어야 한다.
"""
import os

from sage import overlay_common as _oc

# CORE 자산 정본 roster. install._CORE_AGENTS / _CORE_SKILLS / _CORE_BOOTSTRAP_SKILLS 와
# 일치해야 한다(test_overlay_classify 가 대조). 여기 두는 이유: install 이 이 모듈을 import
# 하므로 역참조(circular) 회피.
CORE_IDS = {
    "agents": frozenset({
        "leader", "implementer-a", "implementer-b", "qa", "reviewer", "convention-checker",
    }),
    "skills": frozenset({
        "sage-cycle", "sage-plan", "sage-team", "sage-review", "sage-asset",
        "sage-profile-modify", "sage-asset-override", "sage-init", "sage-init-local",
    }),
    "framework": frozenset({"AGENT_GUIDE", "CLAUDE", "CODEX", "AGENTS"}),
}

# 물리 합성 허용 자산 (a)/(b). 입증된 비게이트 워커만 연다:
# implementer-a/-b 는 순수 실행 워커라 어떤 워크플로 게이트도 소유하지 않는다 → 오버레이가
# 텍스트로 게이트를 완화해도 완화할 게이트 자체가 없다.
NON_GATE_COMPOSE_ALLOWED = frozenset({
    ("agents", "implementer-a"),
    ("agents", "implementer-b"),
})

# 자산 텍스트 밖의 executable oracle이 게이트를 독립 보장할 때만 여기에 등록한다. 등록 자격은
# 선언이 아니라 적대적 우회 테스트(GREEN)로 판정한다 — 오라클이 malicious overlay 를 BLOCK 해야 한다.
# 오라클은 (event, profile, snapshot) 순수함수라 asset 텍스트를 입력받지 않으므로, 오버레이가
# 물리 반영돼도 floor(loop_audit·05 APPROVED·04 evidence·bound phase docs)를 낮출 수 없다.
INDEPENDENT_ORACLE_COMPOSE_ALLOWED = frozenset({
    ("agents", "leader"), ("agents", "reviewer"),
    ("skills", "sage-cycle"), ("skills", "sage-plan"),
    ("skills", "sage-review"), ("skills", "sage-team"),
})

# 등록 항목별 backing 근거(오라클)와 적대적 테스트(test_overlay_reclassification_backing.py).
# 메타테스트가 "등록=BACKING+테스트 보유" 를 강제한다. 여기 오라클은 **구조**를 floor 한다(내용 진위
# 아님 — docstring 참조). 아래 자산의 primary 기여는 구조로 강제되고, 잔여 내용-forge 는 delta-0 선존 갭.
# 제외: qa(primary 기여=04 진위, 이를 재검하는 실행 오라클 부재→FB24/SD-9 후보),
# sage-profile-modify(오라클 입력 profile 을 편집→FB24/SD-9), framework ×4(FB25).
BACKING = {
    ("agents", "leader"): {
        "oracles": ["_missing_pre_impl_phases", "_acceptance_gate", "_report_gate"],
        "adversarial_tests": ["test_leader_phase_skip_blocked"]},
    ("agents", "reviewer"): {
        "oracles": ["_audit_gate", "_report_gate"],
        "adversarial_tests": ["test_reviewer_forge_blocked_loop_on",
                              "test_reviewer_forge_blocked_loop_off"]},
    ("skills", "sage-cycle"): {
        "oracles": ["_report_gate", "_acceptance_gate", "_missing_pre_impl_phases"],
        "adversarial_tests": ["test_sage_cycle_report_without_approve_blocked"]},
    ("skills", "sage-plan"): {
        "oracles": ["_missing_pre_impl_phases"],
        "adversarial_tests": ["test_sage_plan_unbound_plan_blocked"]},
    ("skills", "sage-review"): {
        "oracles": ["_audit_gate", "_report_gate"],
        "adversarial_tests": ["test_sage_review_degraded_run_blocked",
                              "test_sage_review_seq_forged_run_blocked"]},
    ("skills", "sage-team"): {
        "oracles": ["_report_gate", "_acceptance_gate", "_missing_pre_impl_phases"],
        "adversarial_tests": ["test_sage_team_skip_review_blocked_loop_off"]},
}

COMPOSE_ALLOWED = NON_GATE_COMPOSE_ALLOWED | INDEPENDENT_ORACLE_COMPOSE_ALLOWED

# 명시적 (c) — 게이트 보유하나 오라클 미보증(문서화용; 실제 차단은 COMPOSE_ALLOWED 미포함으로 성립).
GATE_BEARING_UNBACKED = frozenset({
    ("agents", "qa"),
    ("skills", "sage-profile-modify"),
    ("framework", "AGENT_GUIDE"), ("framework", "CLAUDE"),
    ("framework", "CODEX"), ("framework", "AGENTS"),
})


def is_core(kind, id):
    """(kind,id) 가 유효한 CORE 자산인가. 오타/미지 id 하드-리포트 판정에 쓴다."""
    return id in CORE_IDS.get(kind, ())


def classify(kind, id):
    """오버레이 합성 자격 → 'compose' | 'blocked'. 미분류/미지는 전부 blocked(fail-closed)."""
    return "compose" if (kind, id) in COMPOSE_ALLOWED else "blocked"


def overlay_path(root, kind, id):
    """오버레이 파일 경로(존재 여부 무관)."""
    return os.path.join(root, "sage", "asset_overrides", kind, f"{id}.md")


def overlay_files(root):
    """sage/asset_overrides/{agents,skills,framework}/*.md 전부 열거 → [(kind, id, path)].

    render_targets(유효 CORE id 만) 와 달리 실제 존재하는 오버레이 파일을 그대로 연다 — 오타/미지
    id(예: reviwer.md) 도 잡아 하드-리포트할 수 있도록. install·sync·validate 가 공유.
    """
    found = []
    base = os.path.join(root, "sage", "asset_overrides")
    for kind in ("agents", "skills", "framework"):
        d = os.path.join(base, kind)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            # case-insensitive filesystem에서는 `x.MD`가 canonical `x.md` lookup과 같은 파일을
            # 가리킨다. inventory가 이를 놓치면 preflight/strict scanner만 우회하고 합성은 된다.
            if fn.lower().endswith(".md"):
                found.append((kind, fn[:-3], os.path.join(d, fn)))
    return found


def overlay_filename_error(kind, id, path):
    """overlay 파일명이 canonical `<id>.md`인지 검사한다."""
    actual = os.path.basename(path)
    expected = f"{id}.md"
    if actual != expected:
        return f"비정규 overlay 파일명: '{actual}' (expected '{expected}')"
    return None


def overlay_text(root, kind, id):
    """오버레이 파일을 LF 로 읽어 (text, error) 반환. 파일 없으면 (None, None)."""
    p = overlay_path(root, kind, id)
    if not os.path.isfile(p):
        return None, None
    return _oc.read_text_lf(p)


def expected_block(kind, id, root):
    """이 자산에 반영돼야 할 관리 블록 문자열 → str.

    - blocked((c)/미분류): 항상 '' — 합성하지 않는다(오버레이를 읽지도 넣지도 않음).
    - compose((a)/(b)): 오버레이가 있으면 compose_block, 없으면 ''.
    반환 (block, error). error 는 오버레이 읽기 실패/토큰 주입 시.
    """
    if classify(kind, id) == "blocked":
        return "", None
    text, err = overlay_text(root, kind, id)
    if err:
        return "", err
    if text is None:
        return "", None
    if kind == "framework":
        from sage.overlay_lint import _split_frontmatter
        _meta, text, ferr = _split_frontmatter(text)
        if ferr:
            return "", ferr
    verr = _oc.validate_overlay(text)
    if verr:
        return "", verr
    return _oc.compose_block(text, kind, id), None


# 라우팅 블록(FB25)을 실을 유일한 렌더 대상. AGENT_GUIDE 는 양 host 가 세션 시작 read order 로
# 읽는 공유 정본이라 여기 한 곳에만 주입하면 codex(AGENTS.md 먼저 읽음)도 라우터를 통해 도달한다.
# framework overlay 는 blocked(FB-12) 로 남으며 — 이 블록은 오버레이 파일이 아니라 profile 에서
# 생성되므로 overlay 개방과 무관하다.
_ROUTING_TARGET = ("framework", "AGENT_GUIDE")


def expected_routing_block(kind, id, root, profile=None):
    """이 렌더 대상에 반영돼야 할 라우팅 블록 문자열 → (block, error).

    AGENT_GUIDE 이외 대상은 항상 '' (라우팅 블록 미대상). profile 의 risk.domains + governance_docs
    로부터 결정론 생성하며, profile 이 None 이면 root 에서 로드한다(materialize/check 공용). 규칙 본문·
    분류 trigger 는 렌더하지 않는다(routing_block 모듈 경계).
    """
    if (kind, id) != _ROUTING_TARGET:
        return "", None
    if profile is None:
        from sage.overlay_materialize import load_profile
        profile, perr = load_profile(root)
        if perr:
            return "", perr
    profile = profile if isinstance(profile, dict) else {}
    risk = profile.get("risk")
    # 명시적 null(키는 있고 값이 None)은 malformed 이며 silent-strip 경로다(codex R3-2/R4-1). risk 비-dict
    # 도 fail-closed(codex R3-1) — JSON-only profile 은 materialize_profile 타입검증을 우회하기 때문.
    if "risk" in profile and risk is None:
        return "", "라우팅 입력 오류(risk): null 불가(미설정은 키 생략 또는 {})"
    if risk is not None and not isinstance(risk, dict):
        return "", "라우팅 입력 오류(risk): 매핑(object)이어야 함"
    if "governance_docs" in profile and profile.get("governance_docs") is None:
        return "", "라우팅 입력 오류(governance_docs): null 불가(미설정은 키 생략 또는 [])"
    if isinstance(risk, dict) and "domains" in risk and risk.get("domains") is None:
        return "", "라우팅 입력 오류(risk.domains): null 불가(미설정은 키 생략 또는 [])"
    domains = risk.get("domains") if isinstance(risk, dict) else None
    governance_docs = profile.get("governance_docs")

    from sage.routing_block import render_routing_body, routing_input_issues
    # render 경계에서 입력 안전성을 강제한다 — profile_validate 는 install --force / `validate --check`
    # 경로에서 항상 돌지 않으므로(codex R1-2), 여기서 fail-closed 로 막아야 injection/봉쇄가 실질 경계가
    # 된다. 하나라도 걸리면 이 렌더 대상(AGENT_GUIDE) 물화가 실패해 오염 블록이 기록되지 않는다.
    input_issues = routing_input_issues(domains, governance_docs, root)
    if input_issues:
        where, reason = input_issues[0]
        return "", f"라우팅 입력 오류({where}): {reason}"
    body = render_routing_body(domains, governance_docs)
    if not body:
        return "", None
    # 조립된 본문 전체 마커 토큰 backstop — 어느 필드가 마커를 심어도 raw parser 가 관리 구간으로
    # 오집계하는 것을 막는다(codex R2-4 whole-body 방어). per-field _scan 과 이중 차단.
    token_error = _oc.routing_block_token_error(body)
    if token_error:
        return "", token_error
    return _oc.wrap_routing_block(body), None
