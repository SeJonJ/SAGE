"""Phase 문서 본문(prose)의 선언 언어 위반 — 구조적 smoke, 자연어 품질 검토가 아니다.

`document_language.py` 가 `Document-Language:` 한 줄의 marker 일치를 본다면, 여기는 그 아래
본문이 실제로 그 언어인지를 본다. 완벽한 판정은 하지 않는다 — fenced code·inline code·Markdown
링크 목적지·인용된 외부 evidence(blockquote)·기계 marker 줄을 뺀 나머지에서 명백한 구조 이상만
잡는다. 전체 자연어 품질과 주 언어 준수는 design 문서 §7.8 이 명시한 대로 사람이 검토한다.

이 모듈은 catalog 를 import 하지 않는다 — `document_language.py` 와 같은 이유로, 표시 언어와
문서 언어는 수명이 다르다.
"""
import re

LANGUAGES = ("ko", "en")

_FENCE = re.compile(r"^\s*(```|~~~)")
_BLOCKQUOTE = re.compile(r"^\s*>")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_MD_LINK_DEST = re.compile(r"\]\([^)]*\)")
_MARKER_LINE = re.compile(
    r"^(Cycle-Stem|Document-Language|Risk\s+Level|Done-Criteria-Revision|Final\s+Status|"
    r"Loop-Run|Phase00-Hash|Phase|Status)\s*:", re.IGNORECASE)
_HANGUL = re.compile(r"[가-힣]")
_NON_SPACE = re.compile(r"\s")

# ko 문서의 "번역 대상 prose 가 사실상 전부 영어" smoke 판정 최소 표본(공백 제외 문자 수).
# 표본이 이보다 작으면 짧은 skeleton/제목뿐인 문서를 오탐으로 막을 위험이 더 크다.
MIN_PROSE_SAMPLE = 40


def prose_lines(text):
    """[(1-based line_no, cleaned_line)] — fence·blockquote·기계 marker 줄은 제외.

    inline code 와 Markdown 링크 목적지는 그 줄 안에서만 지운다(줄 자체는 prose 후보로 남을 수
    있다) — 명령어 하나만 backtick 에 감싼 문장도 나머지 한국어/영어 서술까지 함께 지우면
    안 되기 때문이다.
    """
    out = []
    in_fence = False
    for line_no, line in enumerate((text or "").splitlines(), start=1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _BLOCKQUOTE.match(line):
            continue
        if _MARKER_LINE.match(line.strip()):
            continue
        cleaned = _MD_LINK_DEST.sub(" ", _INLINE_CODE.sub(" ", line))
        out.append((line_no, cleaned))
    return out


def violations(text, language):
    """(text, language) -> [(line_no, snippet)]. 빈 리스트면 통과.

    en: 남은 prose 줄 중 한글이 하나라도 있으면 그 줄들을 그대로 돌려준다(라인별 지목 가능).
    ko: 표본이 `MIN_PROSE_SAMPLE` 이상인데 한글이 전혀 없으면 문서 전체를 구조 이상으로
        `[(0, "")]` 하나로 표시한다(특정 줄이 아니라 문서 전체 성격의 문제라서).
    그 외 language 값(미판정 등)은 무엇에 맞춰 볼지 정의되지 않으므로 항상 통과시킨다.
    """
    lines = prose_lines(text)
    if language == "en":
        return [(no, snippet) for no, snippet in lines if _HANGUL.search(snippet)]
    if language == "ko":
        sample = sum(len(_NON_SPACE.sub("", snippet)) for _, snippet in lines)
        has_korean = any(_HANGUL.search(snippet) for _, snippet in lines)
        if sample >= MIN_PROSE_SAMPLE and not has_korean:
            return [(0, "")]
        return []
    return []
