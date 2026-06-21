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
             "pre_implementation_required", "report_phase"},
    "output_contract": {"markers"},
    "mcp": {"enabled"},
    "extraction": {"config"},
}


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


def _semantic_issues(profile, root):
    issues = []
    risk = profile.get("risk") or {}

    # 0. 폐쇄 섹션 미지 키(오타) 적발 — jsonschema 선택의존과 무관하게 항상 동작(N-R1/P0-2).
    #    예: l3_filename_globs→l3_filename_glob 오타가 빈 리스트로 통과해 L3 게이트가 침묵
    #    비활성되는 거버넌스 최악 실패 모드를 기본 설치(jsonschema 없음)에서도 차단.
    for section, allowed in _closed_section_keys(root).items():
        sec = profile.get(section)
        if isinstance(sec, dict):
            unknown = sorted(set(sec.keys()) - allowed)
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
    pdca = profile.get("pdca") or {}
    phase_ids = {p.get("id") for p in (pdca.get("phases") or []) if p.get("id")}
    for lvl, req in (pdca.get("pre_implementation_required") or {}).items():
        unknown = [r for r in (req or []) if r not in phase_ids]
        if unknown:
            issues.append(("FAIL", f"pdca.pre_implementation_required[{lvl}] 미정의 phase 참조 {unknown} "
                                   f"(정의된 phase: {sorted(phase_ids)})"))

    # 3. 위험 분류 글롭이 전부 비면 게이트가 사실상 무동작(의도일 수 있어 INFO).
    if not any(risk.get(k) for k in ("l1_path_globs", "l2_path_globs", "l3_filename_globs")):
        issues.append(("INFO", "risk 의 l1/l2/l3 글롭이 모두 비어 있음 — 위험 게이트 사실상 무동작(의도면 무시)"))
    return issues


def validate_profile(profile, root):
    """구조 + 의미 검증 결과 [(severity, message)]."""
    return _schema_issues(profile, root) + _semantic_issues(profile, root)


def severity_of(issues):
    """집계 severity. 비면 PASS."""
    return max((s for s, _ in issues), key=lambda s: _RANK[s], default="PASS")
