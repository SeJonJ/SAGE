"""FB25 프로젝트 라우팅 블록 렌더 + 입력 안전성 — profile → 결정론 라우팅 블록.

프로젝트는 자기 소유 거버넌스 문서와 도메인 프로토콜을 갖지만, 에이전트가 세션 시작에 읽는
auto-loaded surface(AGENT_GUIDE)에서 그 존재를 알 방법이 없었다. 이 모듈은 profile 의
risk.domains + governance_docs 로부터 그 경로 포인터를 결정론 블록으로 렌더해 전달 갭을 닫는다.

경계: **라우팅(경로 포인터 + 짧은 라벨)만** 담는다. 규칙 본문은 각 경로 문서에 남기고,
분류 trigger(path_globs/content_keywords)는 절대 렌더하지 않는다 — 그것들은 risk hook 이 소유한
authoritative 데이터라 재복제하면 두 번째 진실 소스가 생기고(SD-4) 게이트 우회 표면이 된다.

**입력 안전성(codex R1 하드닝)**: 라우팅 블록은 auto-loaded governance surface 라, profile 유래
문자열이 그 안에 임의 마크다운/지시(가짜 heading·"Phase 05 optional" 류)를 심는 주입 벡터가 된다.
게이트 자체는 훅이 강제하므로 텍스트로 우회할 수 없지만, LLM 이 신뢰해 읽는 표면을 오염시키는 것을
막는다. `routing_input_issues` 가 문법(안전 경로/짧은 라벨)·단일라인(유니코드 구분자 포함)·
gate-relaxation 스캔·예약 마커 토큰·경로 봉쇄를 검사하며, **render 경계(expected_routing_block)와
authoring(profile_validate)이 같은 함수를 공유**해 검증이 optional advisory 가 아닌 강제 경계가 된다.
"""
import os
import re

_VALID_RISK = ("L1", "L2", "L3")
_MAX_LABEL_LEN = 80
# 렌더될 경로: 안전 상대경로 문자만. 백틱/공백/마크다운/백슬래시/제어 배제(코드스팬 breakout 차단).
# 세그먼트별로 검사한다 — 각 세그먼트는 leading dot(.github/.well-known 등 숨김 경로)을 허용하되
# 그 뒤 영숫자를 강제하므로 `.`/`..` 단독 세그먼트(경로 탈출)와 절대경로(선행 `/`)는 표현 불가.
_PATH_RE = re.compile(r"^\.?[A-Za-z0-9][A-Za-z0-9._-]*(?:/\.?[A-Za-z0-9][A-Za-z0-9._-]*)*$")
# 라벨 금지 문자: 마크다운 활성(코드스팬/강조/취소선/링크/heading/표) — 라이브 마크다운 주입 차단.
_LABEL_BAD_CHARS = frozenset("`*_[]<>#|\\~")


def _has_control(value):
    return any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in value)


def _is_single_line(value):
    """유니코드 라인/문단 구분자(U+0085/2028/2029, VT/FF 등 포함)까지 단일 라인인가.

    ord<0x20 검사는 U+0085/2028/2029 를 놓친다(codex R1-4). str.splitlines 는 이들 전부에서 쪼개므로
    "쪼갠 결과가 1줄이고 그 줄이 원문과 동일"이면 어떤 라인 구분자도 없음이 보장된다.
    """
    lines = value.splitlines()
    return len(lines) <= 1 and (not lines or lines[0] == value)


def _path_issue(value):
    """렌더될 경로 필드의 안전성 → 사유 | None. 문자열 안전만(봉쇄는 별도)."""
    if not isinstance(value, str) or value.strip() == "":
        return "비어있지 않은 문자열이어야 함"
    if not _is_single_line(value) or _has_control(value):
        return "개행/제어문자 불가(단일 라인)"
    if not _PATH_RE.fullmatch(value):
        return "안전 상대경로 세그먼트만 허용(세그먼트당 leading dot 후 영숫자; 절대경로·백틱·공백·마크다운·백슬래시 불가)"
    if ".." in value.split("/"):
        return "상위 경로(..) 세그먼트 불가"
    return None


def _code_value_issue(value):
    """백틱 코드스팬 안에 렌더되는 값(도메인 id 등)의 안전성 → 사유 | None.

    코드스팬 내부에서는 `*`/`_`/`[` 등이 리터럴이라 무해하고, 유일한 breakout 벡터는 백틱이다.
    (id 는 schema `^[a-z][a-z0-9_-]*$` 라 `_` 를 담을 수 있어 라벨 문법으로 검사하면 오탈락한다.)
    마커 토큰 주입은 raw parser 가 code span 을 모르므로 여기서 막지 못한다 → 호출측이 _scan 도 돌린다.
    """
    if not isinstance(value, str) or value.strip() == "":
        return "비어있지 않은 문자열이어야 함"
    if not _is_single_line(value) or _has_control(value):
        return "개행/제어문자 불가(단일 라인)"
    if "`" in value:
        return "백틱 불가(코드스팬 breakout 차단)"
    return None


def _label_issue(value):
    """렌더될 라벨 필드의 안전성 → 사유 | None."""
    if not isinstance(value, str) or value.strip() == "":
        return "비어있지 않은 문자열이어야 함"
    if not _is_single_line(value) or _has_control(value):
        return "개행/제어문자 불가(단일 라인)"
    if len(value) > _MAX_LABEL_LEN:
        return f"라벨은 {_MAX_LABEL_LEN}자 이하여야 함(짧은 라우팅 라벨)"
    if any(ch in _LABEL_BAD_CHARS for ch in value):
        return "마크다운 활성 문자(` * _ [ ] < > # | \\ ~) 불가 — 지시/마크다운 주입 차단"
    if "://" in value:
        return "URL 스킴(://) 불가 — GFM autolink 주입 차단"
    return None


def _containment_issue(root, rel, require_exists):
    """rel 이 project root 안(탈출·심링크 성분 없음)의 안전 경로인지 → 사유 | None.

    lexical 검사만으론 심링크 탈출(os.path.isfile 는 심링크 추종)과 Windows `..\\` 를 놓친다
    (codex R1-5/R3-3). project-owned 입력 검사(realpath 봉쇄·경로 성분 심링크 거부)를 재사용한다.
    require_exists 면 실재 일반 파일까지 요구(doc), 아니면 존재는 요구하지 않는다(pointer 는 저작
    선행 가능).
    """
    from sage.overlay_materialize import _project_path_issue
    target = os.path.join(root, rel)
    issue = _project_path_issue(root, target, leaf_kind="file" if require_exists else None)
    if issue:
        return issue
    if require_exists and not os.path.isfile(target):
        return f"경로가 존재하지 않음(프로젝트 상대 파일): {rel}"
    return None


def pointer_issue(value, root=None):
    """도메인 protocol_pointer 의 안전성 → 사유 | None. render 경계·authoring 검증 공용(파리티).

    FB25 는 과거 렌더되지 않던 pointer 를 auto-loaded 문서의 실제 읽기 지시로 승격한다. 공백을
    허용하던 완화(구 R2-3)는 앞뒤 공백으로 절대/역참조 검사를 우회하고 URI·`~`·Windows 절대경로가
    렌더되는 탈출을 열었다(codex R3-3). 그래서 doc 과 동일한 엄격 문법 + root 봉쇄를 적용한다
    (존재는 미요구). 이 함수를 profile_validate 와 render 가 공유해 authoring↔render 판정을 일치시킨다.
    """
    issue = _path_issue(value)
    if issue:
        return issue
    if root is not None:
        return _containment_issue(root, value, require_exists=False)
    return None


def routing_input_issues(domains, governance_docs, root=None):
    """렌더될 라우팅 입력의 안전성 검사 → [(위치, 사유)]. render 경계·validate 공용(단일 소스).

    문법(안전 경로/짧은 라벨)·단일라인·gate-relaxation 스캔·예약 마커 토큰을 강제하고, root 가
    주어지면 governance_docs.doc 의 realpath 봉쇄+심링크 거부+실재까지 확인한다. domain 은 렌더되는
    protocol_pointer 의 문자열 안전만 검사(실재/봉쇄는 pre-existing 도메인 계약 소관이라 미확장).
    """
    from sage.overlay_common import routing_block_token_error
    from sage.overlay_lint import scan_text

    issues = []

    def _scan_prose(where, value):
        # gate-relaxation 프로즈 스캔은 자유 텍스트(라벨)에만 적용한다. 경로(doc/pointer)에 적용하면
        # 정상 파일명("review-optional.md")이 optional-gate 정규식에 오탐된다(codex R4-2). 경로는 엄격
        # 문법이 이미 마커/마크다운 문자를 차단하므로 프로즈 스캔이 불필요하다.
        if not isinstance(value, str):
            return
        for pattern_id, description in scan_text(value):
            issues.append((where, f"gate-relaxation({pattern_id}): {description}"))

    def _scan_marker(where, value):
        # id 는 _code_value_issue 가 lenient(<>공백 허용) 라 마커 토큰이 들어올 수 있어 검사한다.
        # (doc/pointer 는 엄격 문법이 마커를 이미 차단하므로 생략 — whole-body backstop 도 이중 차단.)
        if not isinstance(value, str):
            return
        token_error = routing_block_token_error(value)
        if token_error:
            issues.append((where, token_error))

    # malformed shape 를 render 경계에서 fail-closed 로 잡는다 — 조용히 무시하면 install --force 가
    # 오염/빈 블록을 쓰거나 기존 블록을 소리없이 지운다(codex R2-2). None(키 부재/명시 null)은 정상.
    if governance_docs is not None and not isinstance(governance_docs, list):
        issues.append(("governance_docs", "리스트여야 함"))
    if isinstance(governance_docs, list):
        for idx, entry in enumerate(governance_docs):
            if not isinstance(entry, dict):
                issues.append((f"governance_docs[{idx}]", "매핑(object)이어야 함"))
                continue
            # 미지 키를 render 경계에서 거부 — schema additionalProperties:false 는 --schema 검증에서만
            # 도므로 JSON-only/무-스키마 경로가 우회한다(codex R3-1 논리). 여분 키가 렌더되진 않지만
            # 오타(예: labell)를 조용히 흘리면 의도한 라벨이 누락된 채 통과한다.
            # 비문자열 키(예: YAML 숫자 키 42)도 미지 키로 fail-closed 처리한다. sorted/join 이
            # 비문자열에서 TypeError 를 내지 않도록 repr 로 정렬하고 str 로 표시한다.
            unknown = sorted(set(entry) - {"doc", "label"}, key=repr)
            if unknown:
                issues.append((f"governance_docs[{idx}]",
                               f"미지 키: {', '.join(map(str, unknown))} (doc/label 만 허용)"))
            doc, label = entry.get("doc"), entry.get("label")
            path_issue = _path_issue(doc)
            if path_issue:
                issues.append((f"governance_docs[{idx}].doc", path_issue))
            elif root is not None:
                containment = _containment_issue(root, doc, require_exists=True)
                if containment:
                    issues.append((f"governance_docs[{idx}].doc", containment))
            label_issue = _label_issue(label)
            if label_issue:
                issues.append((f"governance_docs[{idx}].label", label_issue))
            _scan_prose(f"governance_docs[{idx}].label", label)

    # domains 도 fail-closed. YAML 은 materialize_profile 이 타입을 검증하지만 JSON-only profile 은
    # 그 검증을 우회하므로(codex R3-1) render 경계가 타입·entry·risk_level 을 직접 막아야 한다.
    if domains is not None and not isinstance(domains, list):
        issues.append(("risk.domains", "리스트여야 함"))
    if isinstance(domains, list):
        for idx, domain in enumerate(domains):
            if not isinstance(domain, dict):
                issues.append((f"risk.domains[{idx}]", "매핑(object)이어야 함"))
                continue
            did = domain.get("id")
            id_issue = _code_value_issue(did)
            if id_issue:
                issues.append((f"risk.domains[{idx}].id", id_issue))
            # id 는 raw 텍스트로 렌더되고 _code_value_issue 가 lenient 라 마커 토큰 주입 대상 — code span
            # 은 raw parser 를 막지 못한다(codex R2-4). 프로즈 스캔은 하지 않는다(정상 id 오탐 방지).
            _scan_marker(f"risk.domains[{idx}].id", did)
            if domain.get("risk_level") not in _VALID_RISK:
                issues.append((f"risk.domains[{idx}].risk_level", "L1/L2/L3 중 하나여야 함"))
            pointer = domain.get("protocol_pointer")
            pe = pointer_issue(pointer, root)
            if pe:
                issues.append((f"risk.domains[{idx}].protocol_pointer", pe))
    return issues


def _domain_lines(domains):
    """risk.domains → 라우팅 라인 리스트. 안전하지 않은 항목은 건너뛴다(렌더러 최종 방어선).

    id·risk_level·protocol_pointer 만 렌더하고 path_globs/content_keywords 는 절대 포함하지 않는다.
    """
    lines = []
    if not isinstance(domains, list):
        return lines
    for domain in domains:
        if not isinstance(domain, dict):
            continue
        did = domain.get("id")
        pointer = domain.get("protocol_pointer")
        level = domain.get("risk_level")
        if _code_value_issue(did) or _path_issue(pointer) or level not in _VALID_RISK:
            continue
        lines.append(f"- `{did}` ({level}) — `{pointer}`")
    return lines


def _governance_lines(governance_docs):
    """governance_docs → 라우팅 라인 리스트. 안전하지 않은 항목은 건너뛴다."""
    lines = []
    if not isinstance(governance_docs, list):
        return lines
    for entry in governance_docs:
        if not isinstance(entry, dict):
            continue
        doc = entry.get("doc")
        label = entry.get("label")
        if _path_issue(doc) or _label_issue(label):
            continue
        lines.append(f"- `{doc}` — {label}")
    return lines


def render_routing_body(domains, governance_docs):
    """domains + governance_docs → 라우팅 블록 본문(마커 없음). 둘 다 비면 '' 반환.

    같은 입력은 항상 같은 본문을 낸다(결정론). 렌더 순서는 profile 리스트 순서를 보존한다. 안전하지
    않은 항목은 건너뛴다 — 그러나 render 경계(expected_routing_block)가 그 항목을 error 로 먼저
    차단하므로 정상 경로에서 silent drop 은 발생하지 않는다.
    """
    gov_lines = _governance_lines(governance_docs)
    domain_lines = _domain_lines(domains)
    if not gov_lines and not domain_lines:
        return ""

    sections = [
        "## 프로젝트 라우팅 (sage/project-profile.yaml 에서 생성)",
        "세션 시작 시 아래 경로의 프로젝트 고유 문서를 확인하라. 이 블록은 결정론 생성되며 "
        "손편집은 `sage install --force` 시 사라진다 — 규칙 본문은 각 경로 문서에 있다.",
    ]
    if gov_lines:
        sections.append("### 거버넌스 문서\n" + "\n".join(gov_lines))
    if domain_lines:
        sections.append("### 중요 도메인 (프로토콜 포인터)\n" + "\n".join(domain_lines))
    return "\n\n".join(sections)
