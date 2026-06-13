"""reverse_extract_agent — agent 자산 역추출 (typed claim 자동도출, 결정론, LLM 없음).

Codex 2R 합의(최종검증 §6 알고리즘 구현):
- 입력: claude .md(frontmatter+body), codex .md(+.toml), AGENT_GUIDE 본문
- 산출: spec.md 초안(intent + advisory_scope, 사람이 승인·수정) + {id}.claims.yml(자동, 사람 수기금지)
- typed claim 7타입: owned_paths / role_boundary / test_scope / tool_or_skill_ref / convention_doc / safety_forbid / workflow_step
- verifiability 필터: object 있는 typed token 만 claim, persona("30년 경력/전문가")는 drop
- canonicalization: skill `.claude/skills/X.md`·`.codex/skills/X/SKILL.md`·`X` → `skill:X` / agent → `agent:Y`
- confidence: 양쪽=high / 한쪽+AGENT_GUIDE 경계토큰=source_supported / 한쪽+codex 런타임토큰(gstack)=runtime_allowed / 그외=unresolved
- conformance PASS/FAIL gate 는 결정론만(LLM judge 금지).
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reverse_extract_common as common  # noqa: E402

CONTRACT_VERSION = "1"

# ───────────────────────────────────────────────────────────────────────────
# 엔진은 도메인값 0 (제약 #2: ChatForYou 독립). 프로젝트 고유 패턴은 ExtractConfig 로 주입한다.
# DEFAULT 는 범용(commit/push 안전 + gstack 은 SAGE cross-model 도구). 컴포넌트 경로/컨벤션 휴리스틱은
# 프로젝트 config 가 제공(없으면 해당 claim 미추출 — 다른 스택에서도 graceful). ChatForYou 패턴은
# extract_config_chatforyou.py 에 분리(인스턴스), 엔진에는 없음.
# ───────────────────────────────────────────────────────────────────────────
DEFAULT_EXTRACT_CONFIG = {
    "component_path_globs": [],        # owned_paths 인식용 regex(프로젝트 컴포넌트 경로). 비면 owned 미추출
    "not_owned_substrings": [],        # 소유 아님(동기화 산출물/금지 경로)
    "planning_path_substrings": ["plan_docs"],  # 워크플로우 산출물(소유 아님) — 범용
    "guide_boundary_tokens": ["commit", "push"],            # source_supported 판정 경계(범용 AI 안전)
    "runtime_policy_tokens": {"codex": ["gstack"]},         # 한쪽 런타임 고유 정책(SAGE cross-model)
    "cross_model_invocation": {},      # {claude:[토큰], codex:[토큰]} — cross-model 호출 의미동등(allowlist, §3.2.1)
    "signal_rules": [],                # 라인 단위 프로젝트 컨벤션 휴리스틱(아래 _apply_signal_rules)
}

# 공유 코어(reverse_extract_common) 위임 — persona/ref/confidence/merge/serialize 는 common (Codex 2R A1).
_PERSONA_RE = common.PERSONA_RE
_CONVENTION_DOC_RE = common.CONVENTION_DOC_RE
_norm_path = common.norm_path


def _effective_config(config):
    eff = dict(DEFAULT_EXTRACT_CONFIG)
    if config:
        eff.update(config)
    return eff


def _apply_signal_rules(line, low, claims, rules):
    """라인 단위 프로젝트 컨벤션 휴리스틱(config.signal_rules). 각 rule:
    { type, value, match_any:[regex], require_any:[regex](선택), exclude_persona:bool(선택) }."""
    for r in rules:
        if r.get("exclude_persona") and _PERSONA_RE.search(line):
            continue
        req = r.get("require_any")
        if req and not any(re.search(p, line) for p in req):
            continue
        if any(re.search(p, line, re.IGNORECASE) for p in r["match_any"]):
            claims[r["type"]].add(r["value"])


def _extract_typed(text: str, config=None) -> dict:
    """한 텍스트에서 타입별 claim value 집합 추출 (verifiability: object 있는 것만). config 주입형."""
    eff = _effective_config(config)
    comp_res = [re.compile(g) for g in eff["component_path_globs"]]
    not_owned = eff["not_owned_substrings"]
    planning = eff["planning_path_substrings"]
    rules = eff["signal_rules"]

    claims = {t: set() for t in
              ("owned_paths", "role_boundary", "test_scope", "tool_or_skill_ref",
               "convention_doc", "safety_forbid", "workflow_step")}

    # owned_paths — 프로젝트 컴포넌트 경로 regex(config) 매칭. plan_docs·.md·not_owned 는 소유 아님
    for cre in comp_res:
        for m in cre.findall(text):
            v = _norm_path(m if isinstance(m, str) else m[0])
            if not v or v.endswith(".md"):
                continue
            if any(s in v for s in planning) or any(s.lower() in v.lower() for s in not_owned):
                continue
            claims["owned_paths"].add(v)

    # convention_doc (범용)
    for m in _CONVENTION_DOC_RE.findall(text):
        claims["convention_doc"].add(m)

    # tool_or_skill_ref — 공유 코어 위임. cross_model 호출 토큰은 제외(별도 allowlist 처리, §3.2.1)
    cmi = eff.get("cross_model_invocation", {}) or {}
    exclude = {t for toks in cmi.values() for t in toks}
    common.extract_tool_refs(text, claims["tool_or_skill_ref"], exclude_refs=exclude)

    for raw in text.splitlines():
        line = raw.strip()
        low = line.lower()
        if not line:
            continue
        # commit/push 금지 (범용 AI 안전 — 항상 적용)
        if re.search(r"(금지|하지\s*않는다)", line) and re.search(r"commit|push", low) and not _PERSONA_RE.search(line):
            claims["safety_forbid"].add("forbid:commit/push")
        # 프로젝트 컨벤션 휴리스틱(config.signal_rules)
        _apply_signal_rules(line, low, claims, rules)

    return claims


def extract_claims(claude_text: str, codex_text: str, guide_text: str = "", config=None) -> dict:
    """양쪽 typed claim 교집합/차집합 → confidence 부여한 claims dict. config 로 프로젝트 패턴 주입(독립).

    merge/confidence 는 공유 코어(common.merge_typed) 위임 — agent/skill 동일 로직.
    """
    eff = _effective_config(config)
    c_claude = _extract_typed(claude_text, config)
    c_codex = _extract_typed(codex_text, config)
    codex_tokens = eff["runtime_policy_tokens"].get("codex", [])
    for tok in codex_tokens:
        if tok in codex_text.lower():
            c_codex["tool_or_skill_ref"].add(f"runtime_policy.codex:{tok}")
    # cross-model 호출(§3.2.1): 어느 한쪽에 호출 토큰이 있으면 runtime delta allowlist (unresolved 아님)
    common.apply_cross_model_invocation(eff.get("cross_model_invocation", {}), claude_text, codex_text, c_claude, c_codex)
    return common.merge_typed(
        c_claude, c_codex,
        forbidden_types={"safety_forbid"}, allowlist_extra=codex_tokens,
        guide_text=guide_text, guide_boundary_tokens=eff["guide_boundary_tokens"],
        codex_tokens=codex_tokens,
        inherited_forbidden="AGENT_GUIDE.non_negotiable_boundaries",
        # 서술형(conformance skip 타입)은 unresolved 표면화 제외 — 일관성(skill 과 동일 규칙)
        descriptive_types={"role_boundary", "test_scope", "workflow_step"},
    )


def _frontmatter_description(text: str) -> str:
    m = re.search(r'description:\s*"(.*?)"', text, re.DOTALL)
    return (m.group(1) if m else "").split("\\n")[0]


def spec_draft(agent_id: str, claude_text: str, codex_text: str, claims: dict) -> str:
    """intent + advisory_scope 초안 (사람이 승인·수정). claims 는 별도 .claims.yml."""
    desc = _frontmatter_description(claude_text) or _frontmatter_description(codex_text)
    # intent: persona 제거한 description 첫 문장
    intent = _PERSONA_RE.sub("", desc).strip().split(".")[0]
    owns = sorted({c["value"] for c in claims["required_claims"] if c["type"] == "owned_paths"})[:6]
    skills = sorted({c["value"] for c in claims["required_claims"] if c["type"] == "tool_or_skill_ref"})[:6]
    docs = sorted({c["value"] for c in claims["required_claims"] if c["type"] == "convention_doc"})
    lines = [
        "---", f"id: {agent_id}", "kind: agent", "# AUTO-DRAFT (reverse_extract) — 사람이 intent/advisory_scope 검토·수정", "---",
        "## intent", intent or "(draft: 설명 추출 실패 — 수기 작성 필요)", "",
        "## advisory_scope",
        "- owns: " + (", ".join(owns) if owns else "(미검출)"),
        "- uses: " + (", ".join(skills) if skills else "(미검출)"),
        "- convention_doc: " + (", ".join(docs) if docs else "(미검출)"),
        "- role_boundary: " + "; ".join(sorted({c["value"] for c in claims["required_claims"] if c["type"] == "role_boundary"}) or ["(미검출)"]),
        "",
        "## runtime_bindings",
        "- claude/codex interpretive render (claims 는 {id}.claims.yml)",
    ]
    return "\n".join(lines) + "\n"


def claims_to_yaml(claims: dict) -> str:
    """claims dict → {id}.claims.yml 문자열 (결정론 직렬화 — 재현 가능 생성용 커밋 코드).

    이전엔 생성 인라인 스크립트에 흩어져 있던 직렬화를 엔진 공개 함수로 승격(자가점검 R3).
    extract_claims 가 이미 정렬된 순서를 보장하므로 입력 동일 → 출력 byte-identical.
    """
    L = ["# generated by reverse_extract_agent — do not hand-edit (override만 허용)",
         "# confidence: high | source_supported | runtime_allowed | unresolved",
         "required_claims:"]
    for x in claims["required_claims"]:
        L.append(f'  - {{ type: {x["type"]}, value: "{x["value"]}", confidence: {x["confidence"]} }}')
    L.append("forbidden_claims:")
    for x in claims["forbidden_claims"]:
        if "inherited_forbidden_claims" in x:
            L.append(f'  - {{ inherited_forbidden_claims: "{x["inherited_forbidden_claims"]}" }}')
        else:
            L.append(f'  - {{ type: {x["type"]}, value: "{x["value"]}", confidence: {x["confidence"]} }}')
    L.append("runtime_delta_allowlist:")
    for x in claims["runtime_delta_allowlist"]:
        L.append(f'  - {{ type: {x["type"]}, value: "{x["value"]}", confidence: {x["confidence"]} }}')
    L.append(f"unresolved: {_json_compact(claims['unresolved'])}")
    return "\n".join(L) + "\n"


def _json_compact(lst):
    import json
    return json.dumps(lst, ensure_ascii=False)
