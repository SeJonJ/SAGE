"""conformance — agent/skill 렌더 산출물의 claim 부합 결정론 검사 (LLM judge 금지).

Codex 2R 합의(step7): render 는 interpretive(런타임 AI), SAGE 결정론 책임은 conformance lint.
auto_approve_safe_default 의 안전망. status 우선순위 FAIL > WARN > PASS.

판정(gating matrix):
- FAIL: missing_required(verbatim 안정 식별자) / forbidden_policy_contradictions / allowlist_violations
- WARN: forbidden_policy_missing / 서술형 claim 미검출(role_boundary·test_scope·workflow_step) / unresolved·low-confidence claim
- presence 는 정규화 substring(머신체크). 서술형은 normalize 가 비-verbatim 이라 v1 WARN(오탐 회피).
"""

import re

CONTRACT_VERSION = "1"

# presence 누락 시 FAIL 가능(verbatim 안정 식별자만)
_FAIL_PRESENCE_TYPES = {"owned_paths", "convention_doc", "tool_or_skill_ref"}
# 서술형/비-verbatim 정규화 타입 — v1 presence-gate 제외(skip). normalize 가 비-verbatim 이라
# presence 매칭 신뢰 불가 → FAIL/WARN 둘 다 안 함(오탐 + auto-approve 무력화 회피).
# v1.1 에서 claims 에 must_terms 추가 시 gating 검토.
_SKIP_PRESENCE_TYPES = {"role_boundary", "test_scope", "workflow_step"}
# gating 대상 confidence (unresolved 는 제외)
_GATING_CONF = {"high", "source_supported", "runtime_allowed"}

# forbidden 금지-반대 허용문구 denylist (FAIL). 보수적 — 명백한 위반만.
_CONTRADICTION_PATTERNS = [
    (r"git\s*commit|커밋\s*(을)?\s*(한다|수행|실행)", "commit/push"),
    (r"git\s*push|push\s*(를)?\s*(한다|수행|실행)", "commit/push"),
    (r"통합\s*테스트\s*(를)?\s*(작성|수행|담당)", "integration tests"),
    (r"경계값\s*테스트\s*(를)?\s*(작성|수행|담당)", "boundary tests"),
    (r"chatforyou-desktop/src\s*(를)?\s*(직접\s*)?(수정|편집)", "desktop/src edit"),
]


def _presence_token(value: str) -> str:
    """claim value → rendered 에서 찾을 검색 토큰."""
    for pfx in ("skill:", "agent:", "mcp:", "skill_or_agent:"):
        if value.startswith(pfx):
            return value[len(pfx):]
    # namespaced ref (backend-development:backend-architect) 는 그대로
    return value


def conformance_lint(rendered_text: str, claims: dict) -> dict:
    text = rendered_text or ""
    low = text.lower()

    missing_required = []
    warnings = []

    for c in claims.get("required_claims", []):
        if "type" not in c:
            continue
        conf = c.get("confidence", "unresolved")
        ctype = c["type"]
        if ctype in _SKIP_PRESENCE_TYPES:
            continue  # 서술형 — v1 presence-gate 제외
        token = _presence_token(c["value"]).lower()
        # boundary-aware 매칭 (audit 2회차 P1-6: substring 오탐 차단 — backend-test-layer-extra 등)
        if token and re.search(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])", low):
            continue
        if conf not in _GATING_CONF:
            warnings.append({"reason": "unresolved/low-confidence 미검출", "claim": c["value"]})
        elif ctype in _FAIL_PRESENCE_TYPES:
            missing_required.append({"type": ctype, "value": c["value"]})
        else:
            warnings.append({"reason": "미분류 claim 미검출", "claim": c["value"]})

    # forbidden: contradictions(FAIL) + missing-policy(WARN)
    contradictions = []
    missing_policy = []
    for c in claims.get("forbidden_claims", []):
        if "inherited_forbidden_claims" in c:
            continue
        val = c.get("value", "")
        subject = val.split(":", 1)[1] if ":" in val else val
        # contradiction
        for pat, label in _CONTRADICTION_PATTERNS:
            if label in subject and re.search(pat, text, re.IGNORECASE):
                contradictions.append({"value": val, "matched": label})
        # missing-policy: 금지 주제어가 rendered 에 아예 없음
        key = re.split(r"[\s/]+", subject)[0].lower()
        if key and key not in low:
            missing_policy.append({"value": val})

    status = "PASS"
    if missing_required or contradictions:
        status = "FAIL"
    elif warnings or missing_policy:
        status = "WARN"

    return {
        "status": status,
        "missing_required": missing_required,
        "forbidden_policy_contradictions": contradictions,
        "forbidden_policy_missing": missing_policy,
        "allowlist_violations": [],   # 단일 텍스트 v1 — 교차런타임 검사는 후속
        "warnings": warnings,
    }
