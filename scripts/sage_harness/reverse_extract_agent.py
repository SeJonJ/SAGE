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

# AGENT_GUIDE non-negotiable 경계 토큰 (source_supported 판정용)
_GUIDE_BOUNDARY_TOKENS = ["commit", "push", "chatforyou-desktop/src"]
# codex 런타임 고유 정책 토큰 (runtime_allowed 판정용)
_CODEX_RUNTIME_TOKENS = ["gstack"]
# persona/권위 문구 — drop (verifiability 필터). 역할명(예: "백엔드 전문가")은 보존하고
# 권위 수식("N년 경력/시니어/베테랑/전문가입니다")만 제거한다.
_PERSONA_RE = re.compile(r"(\d+\s*년\s*경력|시니어|전문가입니다|베테랑)")

# ⚠️ v1 pilot 한계(audit 2회차 P1-7): 경로/역할 regex 가 ChatForYou 컴포넌트(springboot-backend 등)에
#    묶여 있다. lead/qa/frontend 일반화는 후속에서 component/role 규칙을 profile 로 외부화해야 한다.
#    v1 은 backend-expert 파일럿으로 알고리즘(typed 교집합/verifiability/confidence)을 증명하는 범위.

_COMPONENT_PATH_RE = re.compile(r"(?:springboot-backend|nodejs-frontend|chatforyou-desktop)/[\w./-]+")
_CONVENTION_DOC_RE = re.compile(r"docs/[\w_]+\.md")
_NAMESPACED_REF_RE = re.compile(r"`([a-z][\w-]+:[\w-]+)`")          # backend-development:backend-architect
_SKILL_PATH_RE = re.compile(r"\.(?:claude|codex)/skills/([\w-]+)(?:/SKILL)?\.md")
_AGENT_PATH_RE = re.compile(r"\.(?:claude|codex)/agents/([\w-]+)\.md")
_BARE_REF_RE = re.compile(r"`([a-z][\w-]+-(?:checker|layer|expert|architect|auditor|debugger))`")


def _norm_path(p: str) -> str:
    return p.rstrip("/").split("←")[0].strip()


# tool_ref 문맥 마커 — namespaced ref(`a:b`)를 tool claim 으로 올리려면 이 문맥이 동반돼야 함
# (audit 2회차 P0-2: 임의의 a:b 가 본문 예시/잡음으로 잡히는 false positive 차단)
_TOOL_CTX_RE = re.compile(r"(\||사용|도구|활용|참조|호출|점검|추적|skill|agent|mcp|검증)", re.IGNORECASE)
_PLANNING_PATH_RE = re.compile(r"plan_docs", re.IGNORECASE)


def _extract_typed(text: str) -> dict:
    """한 텍스트에서 타입별 claim value 집합 추출 (verifiability: object 있는 것만)."""
    claims = {t: set() for t in
              ("owned_paths", "role_boundary", "test_scope", "tool_or_skill_ref",
               "convention_doc", "safety_forbid", "workflow_step")}

    # owned_paths — plan_docs(워크플로우 산출물)·.md 는 소유경로 아님 (audit P1-3)
    for m in _COMPONENT_PATH_RE.findall(text):
        v = _norm_path(m)
        if v and not v.endswith(".md") and not _PLANNING_PATH_RE.search(v):
            claims["owned_paths"].add(v)

    # convention_doc
    for m in _CONVENTION_DOC_RE.findall(text):
        claims["convention_doc"].add(m)

    # tool_or_skill_ref — 경로기반(skill:/agent:)이 canonical. namespaced 는 문맥 동반 시만(라인 단위).
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
        # namespaced ref: 문맥 마커 동반 라인에서만 (false positive 차단)
        if _TOOL_CTX_RE.search(line):
            for m in _NAMESPACED_REF_RE.findall(line):
                claims["tool_or_skill_ref"].add(m.lower())
            for m in _BARE_REF_RE.findall(line):
                base = m.lower()
                # dedupe: 이미 skill:/agent: 로 잡힌 대상은 skill_or_agent 로 중복 추가 안 함 (audit P0-1)
                if base not in skill_ids and base not in agent_ids:
                    claims["tool_or_skill_ref"].add(f"skill_or_agent:{base}")
        # safety_forbid
        if re.search(r"(금지|미담당|하지\s*않는다|영역이다|영역\b)", line) and not _PERSONA_RE.search(line):
            if re.search(r"(통합|http|경계값|시나리오)\s*테스트", line):
                claims["safety_forbid"].add("forbid:integration/http/boundary/scenario tests")
            if re.search(r"commit|push", low):
                claims["safety_forbid"].add("forbid:commit/push")
            if "nodejs-frontend" in low or "미배분" in line:
                claims["safety_forbid"].add("forbid:unassigned files")
        # test_scope
        if re.search(r"(service|서비스).*(단위\s*테스트|unit test)", low) or "MockitoExtension" in line:
            claims["test_scope"].add("test_scope:service unit only")
        # role_boundary (QA 인계)
        if "qa" in low and re.search(r"(영역|인계|전문가)", line):
            claims["role_boundary"].add("boundary:integration/scenario → qa")
        # workflow_step
        if "구현 가이드" in line:
            claims["workflow_step"].add("workflow:write impl guide")

    return claims


def _guide_subject_tokens(value: str):
    """source_supported 판정용 subject 토큰 (예: forbid:commit/push → [commit, push])."""
    subject = value.split(":", 1)[1] if ":" in value else value
    return [t for t in re.split(r"[\s/]+", subject.lower()) if t]


def _confidence(value: str, in_claude: bool, in_codex: bool, guide_text: str) -> str:
    if in_claude and in_codex:
        return "high"
    only_codex = in_codex and not in_claude
    low = value.lower()
    guide_low = (guide_text or "").lower()
    # source_supported: 값의 핵심 토큰이 AGENT_GUIDE 경계와 매칭 + 그 토큰이 전부 guide 에 존재 (audit P1-4: 엄격화)
    boundary_hit = [tok for tok in _GUIDE_BOUNDARY_TOKENS if tok in low]
    if boundary_hit:
        subj = _guide_subject_tokens(value)
        if subj and all(t in guide_low for t in subj):
            return "source_supported"
    if only_codex and any(tok in low for tok in _CODEX_RUNTIME_TOKENS):
        return "runtime_allowed"
    return "unresolved"


def _confidence(value: str, in_claude: bool, in_codex: bool, guide_text: str) -> str:
    if in_claude and in_codex:
        return "high"
    only_codex = in_codex and not in_claude
    low = value.lower()
    if any(tok in low for tok in _GUIDE_BOUNDARY_TOKENS) and any(tok in (guide_text or "").lower() for tok in _GUIDE_BOUNDARY_TOKENS if tok in low):
        return "source_supported"
    if only_codex and any(tok in low for tok in _CODEX_RUNTIME_TOKENS):
        return "runtime_allowed"
    return "unresolved"


def extract_claims(claude_text: str, codex_text: str, guide_text: str = "") -> dict:
    """양쪽 typed claim 교집합/차집합 → confidence 부여한 claims dict."""
    # codex 런타임 토큰(gstack) 보강: codex 본문에 gstack 규칙이 있으면 tool_or_skill_ref 로
    c_claude = _extract_typed(claude_text)
    c_codex = _extract_typed(codex_text)
    if "gstack" in codex_text.lower():
        c_codex["tool_or_skill_ref"].add("runtime_policy.codex:gstack")

    required, forbidden, allowlist, unresolved = [], [], [], []
    for ctype in c_claude:
        for value in sorted(c_claude[ctype] | c_codex[ctype]):
            conf = _confidence(value, value in c_claude[ctype], value in c_codex[ctype], guide_text)
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
