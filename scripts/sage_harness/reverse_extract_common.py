"""reverse_extract_common — agent/skill reverse_extract 공유 코어 (도메인값 0, 결정론).

agent(reverse_extract_agent)·skill(reverse_extract_skill) 둘 다 import. 상호 import 없음(Codex 2R A1).
범용 추출 패턴·persona 필터·confidence·교집합 머지·claims 직렬화를 단일화.
소비 프로젝트 고유값은 caller 의 config 로만 주입(엔진 도메인값 0).
"""
import json
import os
import re

CONTRACT_VERSION = "1"

# 범용 추출 패턴(프로젝트 무관)
CONVENTION_DOC_RE = re.compile(r"docs/[\w_]+\.md")
NAMESPACED_REF_RE = re.compile(r"`([a-z][\w-]+:[\w-]+)`")          # backend-development:backend-architect
SKILL_PATH_RE = re.compile(r"\.(?:claude|codex)/skills/([\w-]+)(?:/SKILL)?\.md")
AGENT_PATH_RE = re.compile(r"\.(?:claude|codex)/agents/([\w-]+)\.md")
BARE_REF_RE = re.compile(r"`([a-z][\w-]+-(?:checker|layer|expert|architect|auditor|debugger))`")
# tool_ref 문맥 마커 — namespaced ref(`a:b`)는 이 문맥 동반 라인에서만 (false positive 차단)
TOOL_CTX_RE = re.compile(r"(\||사용|도구|활용|참조|호출|점검|추적|skill|agent|mcp|검증)", re.IGNORECASE)
# persona/권위 문구 — drop (verifiability 필터). 역할명은 보존, 권위 수식만 제거.
PERSONA_RE = re.compile(r"(\d+\s*년\s*경력|시니어|전문가입니다|베테랑)")


def norm_path(p: str) -> str:
    return p.rstrip("/").split("←")[0].strip()


def extract_tool_refs(text: str, into: set, exclude_refs=frozenset()):
    """경로기반(skill:/agent:) canonical + 문맥 동반 namespaced/bare ref. (범용)

    exclude_refs: tool_or_skill_ref 로 넣지 않을 ref(소문자) — 예: cross_model 호출 토큰(별도 allowlist 처리).
    """
    excl = {e.lower() for e in exclude_refs}
    skill_ids, agent_ids = set(), set()
    for m in SKILL_PATH_RE.findall(text):
        into.add(f"skill:{m.lower()}"); skill_ids.add(m.lower())
    for m in AGENT_PATH_RE.findall(text):
        into.add(f"agent:{m.lower()}"); agent_ids.add(m.lower())
    if "codegraph" in text.lower():
        into.add("mcp:codegraph")
    for raw in text.splitlines():
        line = raw.strip()
        if line and TOOL_CTX_RE.search(line):
            for m in NAMESPACED_REF_RE.findall(line):
                v = m.lower()
                if v not in excl:
                    into.add(v)
            for m in BARE_REF_RE.findall(line):
                base = m.lower()
                if base not in skill_ids and base not in agent_ids and base not in excl:  # dedupe
                    into.add(f"skill_or_agent:{base}")


def apply_cross_model_invocation(cmi: dict, claude_text: str, codex_text: str, c_claude: dict, c_codex: dict):
    """cross-model 호출 토큰(§3.2.1)을 tool_or_skill_ref 가 아닌 runtime delta 로 처리.

    cmi = {claude:[토큰...], codex:[토큰...]}. 각 런타임 텍스트에 자기쪽 호출 토큰이 있으면
    그 산출물의 tool_or_skill_ref 에 'runtime_policy.cross_model_review' 추가 → merge 가 runtime_allowed 로 분류
    (한쪽-only 여도 unresolved 아님). 둘 다 있으면 high(의미동등 인정).
    """
    if not cmi:
        return
    tag = "runtime_policy.cross_model_review"
    cl_low, cx_low = claude_text.lower(), codex_text.lower()
    if any(t.lower() in cl_low for t in cmi.get("claude", [])):
        c_claude["tool_or_skill_ref"].add(tag)
    if any(t.lower() in cx_low for t in cmi.get("codex", [])):
        c_codex["tool_or_skill_ref"].add(tag)


def guide_subject_tokens(value: str):
    subject = value.split(":", 1)[1] if ":" in value else value
    return [t for t in re.split(r"[\s/]+", subject.lower()) if t]


def confidence(value, in_claude, in_codex, guide_text, guide_boundary_tokens, codex_tokens):
    """양쪽=high / runtime_policy.*=runtime_allowed(한쪽 무관) / 한쪽+guide경계=source_supported / codex-only+runtime토큰=runtime_allowed / else unresolved."""
    # runtime_policy.* 태그(cross_model_review / codex:gstack 등)는 런타임 delta — 한쪽-only 여도 allowlist
    if value.startswith("runtime_policy."):
        return "runtime_allowed"
    if in_claude and in_codex:
        return "high"
    only_codex = in_codex and not in_claude
    low = value.lower()
    guide_low = (guide_text or "").lower()
    if any(tok in low for tok in guide_boundary_tokens):
        subj = guide_subject_tokens(value)
        if subj and all(t in guide_low for t in subj):
            return "source_supported"
    if only_codex and any(tok in low for tok in codex_tokens):
        return "runtime_allowed"
    return "unresolved"


def merge_typed(c_claude: dict, c_codex: dict, *, forbidden_types, allowlist_extra,
                guide_text, guide_boundary_tokens, codex_tokens, inherited_forbidden,
                descriptive_types=frozenset()):
    """양 런타임 typed claim dict → required/forbidden/allowlist/unresolved (confidence 부여).

    forbidden_types: forbidden 으로 분류할 claim type 집합(예: {"safety_forbid"}).
    allowlist_extra: codex 본문에서 보강할 runtime_policy 토큰 list(이미 c_codex 에 추가됐다고 가정).
    descriptive_types: 서술형 타입(예: procedure_step) — conformance 가 어차피 skip 하므로 한쪽-only 여도
      unresolved 표면화에서 제외(사람 결정 불필요). required 에는 보존(정보성). 노이즈 폭증 방지.
    """
    required, forbidden, allowlist, unresolved = [], [], [], []
    for ctype in c_claude:
        for value in sorted(c_claude[ctype] | c_codex[ctype]):
            conf = confidence(value, value in c_claude[ctype], value in c_codex[ctype],
                              guide_text, guide_boundary_tokens, codex_tokens)
            entry = {"type": ctype, "value": value, "confidence": conf}
            if ctype in forbidden_types:
                forbidden.append(entry)
            elif conf == "runtime_allowed":
                allowlist.append(entry)
            elif conf == "unresolved":
                # 서술형은 unresolved 목록에서 제외(사람 결정 대상 아님), required 엔 보존
                if ctype not in descriptive_types:
                    unresolved.append(entry)
                required.append(entry)
            else:
                required.append(entry)
    fb = forbidden + [{"inherited_forbidden_claims": inherited_forbidden}] if inherited_forbidden else forbidden
    return {
        "required_claims": required,
        "forbidden_claims": fb,
        "runtime_delta_allowlist": allowlist,
        "unresolved": [e["value"] for e in unresolved],
    }


def claims_to_yaml(claims: dict, kind: str = None) -> str:
    """claims dict → {id}.claims.yml (결정론). kind 명시 시 헤더에 기록(agent/skill 구분)."""
    L = ["# generated by reverse_extract — do not hand-edit (override만 허용)",
         "# confidence: high | source_supported | runtime_allowed | unresolved"]
    if kind:
        L.append(f"kind: {kind}")
    # value 는 json.dumps 로 직렬화 — 따옴표/역슬래시/개행이 들어가도 깨지지 않는 따옴표 스칼라가 되고,
    # 같은 형식이 아래 폴백 리더(_parse_flow_entry)와 pyyaml 양쪽에서 그대로 역파싱된다.
    L.append("required_claims:")
    for x in claims["required_claims"]:
        order = f", order: {x['order']}" if "order" in x else ""
        L.append(f'  - {{ type: {x["type"]}, value: {json.dumps(x["value"], ensure_ascii=False)}, confidence: {x["confidence"]}{order} }}')
    L.append("forbidden_claims:")
    for x in claims["forbidden_claims"]:
        if "inherited_forbidden_claims" in x:
            L.append(f'  - {{ inherited_forbidden_claims: {json.dumps(x["inherited_forbidden_claims"], ensure_ascii=False)} }}')
        else:
            L.append(f'  - {{ type: {x["type"]}, value: {json.dumps(x["value"], ensure_ascii=False)}, confidence: {x["confidence"]} }}')
    L.append("runtime_delta_allowlist:")
    for x in claims["runtime_delta_allowlist"]:
        L.append(f'  - {{ type: {x["type"]}, value: {json.dumps(x["value"], ensure_ascii=False)}, confidence: {x["confidence"]} }}')
    L.append(f"unresolved: {json.dumps(claims['unresolved'], ensure_ascii=False)}")
    return "\n".join(L) + "\n"


# 값은 json.dumps 로 쓰인 따옴표 스칼라(이스케이프된 따옴표 \" 포함) 또는 따옴표 없는 토큰.
_FLOW_KV_RE = re.compile(r'(\w+):\s*("(?:[^"\\]|\\.)*"|[^,}]+)')
_CLAIMS_SECTIONS = {"required_claims:": "required_claims",
                    "forbidden_claims:": "forbidden_claims",
                    "runtime_delta_allowlist:": "runtime_delta_allowlist"}


def _parse_flow_entry(body):
    """'type: x, value: "y", confidence: z' → dict. claims_to_yaml flow-entry 의 역."""
    d = {}
    for kv in _FLOW_KV_RE.finditer(body):
        k, raw = kv.group(1), kv.group(2).strip()
        if raw[:1] == '"':
            try:
                v = json.loads(raw)          # 이스케이프(\" \\ \n) 복원
            except ValueError:
                v = raw.strip('"')
        else:
            v = raw
        if k == "order":
            try:
                v = int(v)
            except (ValueError, TypeError):
                pass
        d[k] = v
    return d


def load_claims_yaml(path):
    """{id}.claims.yml → dict (claims_to_yaml 의 역 — round-trip 짝, 단일 canonical 리더).

    pyyaml 있으면 safe_load(완전), 없거나 실패하면 결정론 폴백(claims.yml 은 기계생성 고정 flow-style
    이라 의존성 없이 파싱 가능 — absorb·validate 가 같은 파서를 쓰게 통일). 부재/빈 → 빈 골격.
    반환: {required_claims, forbidden_claims, runtime_delta_allowlist, unresolved}(+ 있으면 kind)."""
    skel = {"required_claims": [], "forbidden_claims": [], "runtime_delta_allowlist": [], "unresolved": []}
    if not path or not os.path.exists(path):
        return dict(skel)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        import yaml
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            for k in skel:
                v = data.get(k)           # pyyaml 은 빈 섹션(`forbidden_claims:`)을 None 으로 파싱 → list 정규화
                data[k] = v if isinstance(v, list) else []
            return data
    except ImportError:
        pass
    except Exception:
        pass   # 파싱 실패 → 결정론 폴백 시도(기계생성 포맷)

    out = dict(skel)
    section = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("kind:"):
            out["kind"] = s.split(":", 1)[1].strip(); section = None; continue
        if s.startswith("unresolved:"):
            m = re.search(r"unresolved:\s*(\[.*\])", s)
            try:
                out["unresolved"] = json.loads(m.group(1)) if m else []
            except Exception:
                out["unresolved"] = []
            section = None; continue
        if s in _CLAIMS_SECTIONS:
            section = _CLAIMS_SECTIONS[s]; continue
        if section and s.startswith("- {") and s.endswith("}"):
            out[section].append(_parse_flow_entry(s[s.index("{") + 1:s.rindex("}")]))
    return out
