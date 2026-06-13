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
# persona/권위 — drop (verifiability 필터)
_PERSONA_RE = re.compile(r"(\d+\s*년\s*경력|시니어|전문가입니다|베테랑)")

_COMPONENT_PATH_RE = re.compile(r"(?:springboot-backend|nodejs-frontend|chatforyou-desktop)/[\w./-]+")
_CONVENTION_DOC_RE = re.compile(r"docs/[\w_]+\.md")
_NAMESPACED_REF_RE = re.compile(r"`([a-z][\w-]+:[\w-]+)`")          # backend-development:backend-architect
_SKILL_PATH_RE = re.compile(r"\.(?:claude|codex)/skills/([\w-]+)(?:/SKILL)?\.md")
_AGENT_PATH_RE = re.compile(r"\.(?:claude|codex)/agents/([\w-]+)\.md")
_BARE_REF_RE = re.compile(r"`([a-z][\w-]+-(?:checker|layer|expert|architect|auditor|debugger))`")


def _norm_path(p: str) -> str:
    return p.rstrip("/").split("←")[0].strip()


def _extract_typed(text: str) -> dict:
    """한 텍스트에서 타입별 claim value 집합 추출 (verifiability: object 있는 것만)."""
    claims = {t: set() for t in
              ("owned_paths", "role_boundary", "test_scope", "tool_or_skill_ref",
               "convention_doc", "safety_forbid", "workflow_step")}

    # owned_paths
    for m in _COMPONENT_PATH_RE.findall(text):
        v = _norm_path(m)
        # 디렉토리 루트만(파일 잡음 줄임): 4 depth 이하 + 트리 마커 제거
        if v and not v.endswith(".md"):
            claims["owned_paths"].add(v)

    # convention_doc
    for m in _CONVENTION_DOC_RE.findall(text):
        claims["convention_doc"].add(m)

    # tool_or_skill_ref (canonicalize)
    for m in _NAMESPACED_REF_RE.findall(text):
        claims["tool_or_skill_ref"].add(m.lower())
    for m in _BARE_REF_RE.findall(text):
        claims["tool_or_skill_ref"].add(f"skill_or_agent:{m.lower()}")
    for m in _SKILL_PATH_RE.findall(text):
        claims["tool_or_skill_ref"].add(f"skill:{m.lower()}")
    for m in _AGENT_PATH_RE.findall(text):
        claims["tool_or_skill_ref"].add(f"agent:{m.lower()}")
    if "codegraph" in text.lower():
        claims["tool_or_skill_ref"].add("mcp:codegraph")

    # safety_forbid / role_boundary / test_scope / workflow_step (라인 신호)
    for raw in text.splitlines():
        line = raw.strip()
        low = line.lower()
        if not line:
            continue
        # safety_forbid: 금지/미담당/하지 않는다 + object
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
        # workflow_step (numbered or 구현가이드)
        if re.match(r"^\d+[.)]\s", line) or "구현 가이드" in line:
            if "구현 가이드" in line:
                claims["workflow_step"].add("workflow:write impl guide")

    return claims


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
