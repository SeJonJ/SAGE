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

import re

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
    "signal_rules": [],                # 라인 단위 프로젝트 컨벤션 휴리스틱(아래 _apply_signal_rules)
}

# persona/권위 문구 — drop (verifiability 필터). 역할명(예: "백엔드 전문가")은 보존하고
# 권위 수식("N년 경력/시니어/베테랑/전문가입니다")만 제거한다. (범용)
_PERSONA_RE = re.compile(r"(\d+\s*년\s*경력|시니어|전문가입니다|베테랑)")

# 범용 추출 패턴(프로젝트 무관)
_CONVENTION_DOC_RE = re.compile(r"docs/[\w_]+\.md")
_NAMESPACED_REF_RE = re.compile(r"`([a-z][\w-]+:[\w-]+)`")          # backend-development:backend-architect
_SKILL_PATH_RE = re.compile(r"\.(?:claude|codex)/skills/([\w-]+)(?:/SKILL)?\.md")
_AGENT_PATH_RE = re.compile(r"\.(?:claude|codex)/agents/([\w-]+)\.md")
_BARE_REF_RE = re.compile(r"`([a-z][\w-]+-(?:checker|layer|expert|architect|auditor|debugger))`")
# tool_ref 문맥 마커 — namespaced ref(`a:b`)는 이 문맥 동반 라인에서만 (audit 2회차 P0-2)
_TOOL_CTX_RE = re.compile(r"(\||사용|도구|활용|참조|호출|점검|추적|skill|agent|mcp|검증)", re.IGNORECASE)


def _norm_path(p: str) -> str:
    return p.rstrip("/").split("←")[0].strip()


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

    # tool_or_skill_ref — 경로기반(skill:/agent:)이 canonical (범용)
    skill_ids, agent_ids = set(), set()
    for m in _SKILL_PATH_RE.findall(text):
        claims["tool_or_skill_ref"].add(f"skill:{m.lower()}"); skill_ids.add(m.lower())
    for m in _AGENT_PATH_RE.findall(text):
        claims["tool_or_skill_ref"].add(f"agent:{m.lower()}"); agent_ids.add(m.lower())
    if "codegraph" in text.lower():
        claims["tool_or_skill_ref"].add("mcp:codegraph")

    for raw in text.splitlines():
        line = raw.strip()
        low = line.lower()
        if not line:
            continue
        # namespaced ref: 문맥 마커 동반 라인에서만 (범용, false positive 차단)
        if _TOOL_CTX_RE.search(line):
            for m in _NAMESPACED_REF_RE.findall(line):
                claims["tool_or_skill_ref"].add(m.lower())
            for m in _BARE_REF_RE.findall(line):
                base = m.lower()
                if base not in skill_ids and base not in agent_ids:  # dedupe (audit P0-1)
                    claims["tool_or_skill_ref"].add(f"skill_or_agent:{base}")
        # commit/push 금지 (범용 AI 안전 — 항상 적용)
        if re.search(r"(금지|하지\s*않는다)", line) and re.search(r"commit|push", low) and not _PERSONA_RE.search(line):
            claims["safety_forbid"].add("forbid:commit/push")
        # 프로젝트 컨벤션 휴리스틱(config.signal_rules)
        _apply_signal_rules(line, low, claims, rules)

    return claims


def _guide_subject_tokens(value: str):
    """source_supported 판정용 subject 토큰 (예: forbid:commit/push → [commit, push])."""
    subject = value.split(":", 1)[1] if ":" in value else value
    return [t for t in re.split(r"[\s/]+", subject.lower()) if t]


def _confidence(value, in_claude, in_codex, guide_text, eff) -> str:
    if in_claude and in_codex:
        return "high"
    only_codex = in_codex and not in_claude
    low = value.lower()
    guide_low = (guide_text or "").lower()
    # source_supported: 값의 핵심 토큰이 경계와 매칭 + 그 토큰이 전부 guide 에 존재 (audit P1-4: 엄격화)
    boundary_hit = [tok for tok in eff["guide_boundary_tokens"] if tok in low]
    if boundary_hit:
        subj = _guide_subject_tokens(value)
        if subj and all(t in guide_low for t in subj):
            return "source_supported"
    codex_tokens = eff["runtime_policy_tokens"].get("codex", [])
    if only_codex and any(tok in low for tok in codex_tokens):
        return "runtime_allowed"
    return "unresolved"


def extract_claims(claude_text: str, codex_text: str, guide_text: str = "", config=None) -> dict:
    """양쪽 typed claim 교집합/차집합 → confidence 부여한 claims dict. config 로 프로젝트 패턴 주입(독립)."""
    eff = _effective_config(config)
    c_claude = _extract_typed(claude_text, config)
    c_codex = _extract_typed(codex_text, config)
    # 한쪽 런타임 고유 정책 토큰(codex gstack 등) 보강
    for tok in eff["runtime_policy_tokens"].get("codex", []):
        if tok in codex_text.lower():
            c_codex["tool_or_skill_ref"].add(f"runtime_policy.codex:{tok}")

    required, forbidden, allowlist, unresolved = [], [], [], []
    for ctype in c_claude:
        for value in sorted(c_claude[ctype] | c_codex[ctype]):
            conf = _confidence(value, value in c_claude[ctype], value in c_codex[ctype], guide_text, eff)
            entry = {"type": ctype, "value": value, "confidence": conf}
            if ctype == "safety_forbid":
                forbidden.append(entry)
            elif conf == "runtime_allowed":
                allowlist.append(entry)
            elif conf == "unresolved":
                unresolved.append(entry)
                required.append(entry)  # 보존(검증은 unresolved 표시)
            else:
                required.append(entry)
    return {
        "required_claims": required,
        "forbidden_claims": forbidden + [{"inherited_forbidden_claims": "AGENT_GUIDE.non_negotiable_boundaries"}],
        "runtime_delta_allowlist": allowlist,
        "unresolved": [e["value"] for e in unresolved],
    }


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
