"""reverse_extract_skill — skill 자산 역추출 (typed claim, 결정론, 도메인값 0).

Codex 2R 합의: skill 은 agent 와 타입이 다르다(행위 절차). 공유 코어(reverse_extract_common) 위임.
타입: when_to_use / procedure_step(순서보존) / uses / output_contract / input_scope / advisory_scope / state_mutation.
section 헤더는 config alias(한국어 ChatForYou 헤더 엔진 고정 금지 — 독립). ChatForYou 패턴은 extract_config_chatforyou.

claim gate(conformance, v1): uses/input_scope/output_contract = presence FAIL 후보. procedure_step/when_to_use/
advisory_scope = WARN/skip(서술형). state_mutation = advisory(WARN). procedure order = WARN only.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reverse_extract_common as common  # noqa: E402

CONTRACT_VERSION = "1"

# 엔진 도메인값 0. section 헤더 alias 는 범용 기본(영문) + config 로 프로젝트 헤더(한국어 등) 주입.
DEFAULT_SKILL_CONFIG = {
    "intent_headers": ["purpose", "intent", "목적", "개요"],
    "procedure_headers": ["procedure", "steps", "how to use", "실행 방법", "실행방법", "절차", "단계"],
    "output_headers": ["output", "report format", "output format", "리포트 형식", "출력 형식", "결과"],
    "scope_headers": ["boundaries", "caveats", "scope", "주의사항", "범위", "행동 규칙"],
    "input_scope_patterns": [],          # 프로젝트 입력 범위 표현(예: git diff 변경파일) — config 주입
    "guide_boundary_tokens": ["commit", "push"],
    "runtime_policy_tokens": {"codex": ["gstack"]},
    "trigger_quote_re": r'"([^"]{2,40})"',  # description/triggers 의 따옴표 발동표현
}

_HEADER_RE = re.compile(r"^#{1,4}\s+(.+?)\s*$")
_NUM_STEP_RE = re.compile(r"^\s*(\d+)[.)]\s+(.+?)\s*$")
# "Step 1: 제목" / "1단계: 제목" 형태 절차 헤더 텍스트(헤더 # 는 _HEADER_RE 가 이미 제거). P1: ship false-negative
_STEP_HEADER_RE = re.compile(r"^(?:step|스텝)?\s*(\d+)\s*(?:단계)?\s*[:：]\s*(.+?)\s*$", re.IGNORECASE)
# 파일 경로 목록 항목(절차 아님 — design-review 노이즈 배제, P2). numbered/bullet 모두, 경로/백틱 시작.
_PATH_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+`?[\w./\[\]N월_-]+\.(?:md|java|js|ts|py|sh|json|yml|yaml)`?")
# input_scope: regex 패턴 → 사람이 읽는 라벨 (raw regex 노출 방지)
_INPUT_SCOPE_LABELS = {r"git diff": "git diff 변경파일", r"변경된?\s*파일": "변경 파일",
                       r"changed files": "changed files"}


def _eff(config):
    e = dict(DEFAULT_SKILL_CONFIG)
    if config:
        # skill config 는 별도 키 또는 공유 키 모두 허용
        for k in DEFAULT_SKILL_CONFIG:
            if k in config:
                e[k] = config[k]
        for k in ("guide_boundary_tokens", "runtime_policy_tokens"):
            if k in config:
                e[k] = config[k]
    return e


def _section_kind(header_low, eff):
    for kind, key in (("intent", "intent_headers"), ("procedure", "procedure_headers"),
                      ("output", "output_headers"), ("scope", "scope_headers")):
        if any(h in header_low for h in eff[key]):
            return kind
    return None


def _step_label(text):
    """절차 step 텍스트 → 안정 식별 라벨(앞 토큰 기반, 결정론). 서술 전체 대신 핵심구만."""
    # "**변경 파일 감지**: ..." → "변경 파일 감지" (마크다운 ** ` 제거, — 뒤 설명 제거)
    head = re.split(r"[:：]", text, 1)[0].strip()
    head = re.split(r"\s+[—–-]\s+", head, 1)[0].strip()   # "path — 설명" → "path" 제거 방향이나 라벨은 앞부분
    head = head.replace("**", "")
    head = re.sub(r"`[^`]*`", "", head).strip()
    return head[:40]


def _extract_typed(text, config=None):
    eff = _eff(config)
    claims = {t: set() for t in
              ("when_to_use", "procedure_step", "uses", "output_contract",
               "input_scope", "advisory_scope", "state_mutation")}
    ordered_steps = []  # (order, label) — 순서 보존용

    # uses (범용 ref) + convention doc
    common.extract_tool_refs(text, claims["uses"])
    for m in common.CONVENTION_DOC_RE.findall(text):
        claims["uses"].add(m)

    # when_to_use: frontmatter description/triggers 의 따옴표 발동표현
    fm = re.search(r"^---\n(.*?)\n---", text, re.DOTALL)
    if fm:
        for q in re.findall(eff["trigger_quote_re"], fm.group(1)):
            claims["when_to_use"].add(q.strip())

    # input_scope: config 패턴 → 사람이 읽는 라벨(raw regex 노출 방지)
    for pat in eff["input_scope_patterns"]:
        if re.search(pat, text, re.IGNORECASE):
            claims["input_scope"].add(_INPUT_SCOPE_LABELS.get(pat, pat))

    # 섹션 순회
    cur_section = None
    step_no = 0
    for raw in text.splitlines():
        line = raw.rstrip()
        hm = _HEADER_RE.match(line.strip())
        if hm:
            header = hm.group(1)
            # "## Step N: 제목" 헤더 = 절차 단계 (섹션 전환과 별개로 직접 step 추가)
            shm = _STEP_HEADER_RE.match(header)
            if shm:
                step_no += 10
                lbl = _step_label(shm.group(2))
                if lbl:
                    claims["procedure_step"].add(lbl)
                    ordered_steps.append((step_no, lbl))
                cur_section = "procedure"
                continue
            cur_section = _section_kind(header.lower(), eff)
            # output 섹션 헤더 자체를 output_contract presence 신호로 (리포트 형식 섹션 존재)
            if cur_section == "output":
                claims["output_contract"].add("output:report_format")
            continue
        if cur_section == "procedure":
            sm = _NUM_STEP_RE.match(line)
            if sm and not _PATH_ITEM_RE.match(line):   # 파일목록 항목 노이즈 배제(P2)
                step_no += 10
                lbl = _step_label(sm.group(2))
                if lbl:
                    claims["procedure_step"].add(lbl)
                    ordered_steps.append((step_no, lbl))
        if cur_section == "output":
            # 리포트 형식 섹션의 헤더성 라벨(### / 표 헤더)을 output_contract 로
            sub = re.match(r"^#{2,5}\s+(.+)", line)
            if sub:
                claims["output_contract"].add(f"output:{_step_label(sub.group(1))}")
        if cur_section == "scope":
            s = line.strip().lstrip("-").strip()
            if s and re.search(r"(금지|하지\s*않는다|말라|않는다)", s) and not common.PERSONA_RE.search(s):
                claims["advisory_scope"].add(s[:60])
        # state_mutation: 체크박스/파일 갱신 등 side effect (advisory)
        if re.search(r"(\[x\]|\[ \]|체크박스|업데이트|갱신|update.*checkbox)", line, re.IGNORECASE):
            claims["state_mutation"].add("mutates:checklist/state")

    claims["_ordered_steps"] = ordered_steps  # 직렬화 시 order 부여
    return claims


def extract_claims(claude_text, codex_text, guide_text="", config=None):
    eff = _eff(config)
    cc = _extract_typed(claude_text, config)
    cx = _extract_typed(codex_text, config)
    order_map = {lbl: o for o, lbl in (cc.get("_ordered_steps", []) or cx.get("_ordered_steps", []))}
    cc.pop("_ordered_steps", None); cx.pop("_ordered_steps", None)
    codex_tokens = eff["runtime_policy_tokens"].get("codex", [])
    for tok in codex_tokens:
        if tok in codex_text.lower():
            cx["uses"].add(f"runtime_policy.codex:{tok}")
    merged = common.merge_typed(
        cc, cx,
        forbidden_types={"advisory_scope"},   # skill 의 금지/범위 → forbidden 슬롯
        allowlist_extra=codex_tokens,
        guide_text=guide_text, guide_boundary_tokens=eff["guide_boundary_tokens"],
        codex_tokens=codex_tokens,
        inherited_forbidden="AGENT_GUIDE.non_negotiable_boundaries",
        # 서술형(conformance skip 타입)은 unresolved 표면화 제외 — 절차 어휘차이 노이즈 폭증 방지
        descriptive_types={"procedure_step", "when_to_use", "state_mutation"},
    )
    # procedure_step 에 order 부여(순서 보존, gate 는 WARN — conformance 가 skip)
    for c in merged["required_claims"]:
        if c["type"] == "procedure_step" and c["value"] in order_map:
            c["order"] = order_map[c["value"]]
    return merged


def _frontmatter_description(text):
    m = re.search(r'description:\s*>?\s*\n?\s*(.+)', text)
    return (m.group(1).strip() if m else "").split(".")[0][:120]


def spec_draft(skill_id, claude_text, codex_text, claims):
    desc = _frontmatter_description(claude_text) or _frontmatter_description(codex_text)
    intent = common.PERSONA_RE.sub("", desc).strip()
    triggers = sorted({c["value"] for c in claims["required_claims"] if c["type"] == "when_to_use"})[:6]
    uses = sorted({c["value"] for c in claims["required_claims"] if c["type"] == "uses"})[:8]
    steps = [c for c in claims["required_claims"] if c["type"] == "procedure_step"]
    steps = [c["value"] for c in sorted(steps, key=lambda c: c.get("order", 999))]
    lines = [
        "---", f"id: {skill_id}", "kind: skill",
        "# AUTO-DRAFT (reverse_extract) — 사람이 intent/when_to_use/procedure 검토·수정", "---",
        "## intent", intent or "(draft: 설명 추출 실패)", "",
        "## when_to_use", "- " + ("\n- ".join(triggers) if triggers else "(미검출)"), "",
        "## procedure",
    ]
    for i, s in enumerate(steps, 1):
        lines.append(f"{i}. {s}")
    if not steps:
        lines.append("(미검출)")
    lines += ["", "## advisory_scope", "- uses: " + (", ".join(uses) if uses else "(미검출)"),
              "", "## runtime_bindings", "- claude .claude/skills/{id}.md / codex .codex/skills/{id}/SKILL.md"]
    return "\n".join(lines) + "\n"


# 직렬화는 공유 코어 (kind:skill 기록)
def claims_to_yaml(claims):
    return common.claims_to_yaml(claims, kind="skill")
