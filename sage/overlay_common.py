"""CORE 렌더 오버레이 물리 합성(materialization) 프리미티브 — 마커·바이트·블록 연산.

오버레이(sage/asset_overrides/{agents,skills}/<id>.md)는 CORE agent/skill 렌더를
프로젝트 로컬로 덧대는 hand-authored 파일이다(install 미ship, `--force` 생존). 기존엔
CORE 렌더가 "오버레이를 먼저 읽어라"는 프로즈에만 의존해 실제 반영을 아무도 강제하지
않았다(GitHub 이슈 #5). 이 모듈은 오버레이를 렌더의 관리 블록(managed block)으로 물리
삽입해 반영을 결정론적으로 만든다 — `sage/mcp_common.py` 의 codex managed-block 선례와
같은 패턴(마커 구간 교체·중복/짝불일치 error·idempotent).

경계: 이 모듈은 "물리 반영"만 다룬다. 어떤 자산이 오버레이를 받을 자격이 있는지(게이트
완화 위험)는 `sage.overlay_classify` 가, base 무결성 앵커는 manifest core_renders 가 담당한다.
"""
import os
import re
import stat
import uuid
from pathlib import Path

# 버전 붙은 HTML 주석 마커. 전 대상이 markdown 이라 주석 하나로 통일한다. START 는 편집
# 리다이렉트 힌트를 담고, 버전(v1)은 미래 포맷 변경 시 옛 마커를 식별·재합성하는 근거.
MARKER_START = "<!-- >>> SAGE OVERLAY v1 START (edit sage/asset_overrides/, not here) -->"
MARKER_END = "<!-- <<< SAGE OVERLAY v1 END -->"

# 마커 토큰(구간 없이 토큰 문자열만) — 오버레이 본문에 이게 있으면 합성 시 마커 짝이
# 깨지므로 저작 단계에서 reject 한다.
_MARKER_TOKENS = (">>> SAGE OVERLAY", "<<< SAGE OVERLAY")

# 마커 구간(START..END, 뒤 개행 1개 흡수) 매칭. mcp_common.replace_codex_block 과 동일 방식.
_BLOCK_RE = re.compile(re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END) + r"\n?", re.DOTALL)

# 프로젝트 라우팅 블록(FB25) 마커 — 오버레이와 별개 관리 구간. 오버레이 블록이 프로젝트 로컬
# 오버레이 파일에서 오는 반면, 라우팅 블록은 sage/project-profile.yaml 에서 결정론 생성된다.
# framework overlay 는 blocked(FB-12) 이므로 framework 렌더의 이 슬롯만 라우팅 블록이 채우고,
# 오버레이 블록과 절대 공존하지 않는다. base 해시 앵커는 두 관리 구간을 모두 제거한 base 로 잡아야
# 프로젝트별 라우팅 값이 앵커를 오염시키지 않는다(base_of 가 두 구간을 함께 strip).
ROUTING_MARKER_START = "<!-- >>> SAGE PROJECT ROUTING v1 START (sage/project-profile.yaml 에서 생성, 여기서 수정 금지) -->"
ROUTING_MARKER_END = "<!-- <<< SAGE PROJECT ROUTING v1 END -->"
_ROUTING_TOKENS = (">>> SAGE PROJECT ROUTING", "<<< SAGE PROJECT ROUTING")
_ROUTING_BLOCK_RE = re.compile(
    re.escape(ROUTING_MARKER_START) + r".*?" + re.escape(ROUTING_MARKER_END) + r"\n?", re.DOTALL)


def _normalize_trailing(text):
    """말미 개행을 정확히 1개로 정규화(빈 문자열은 그대로). base·블록·본문 결합의 결정론 확보."""
    if not text:
        return text
    return text.rstrip("\n") + "\n"


def read_text_lf(path):
    """오버레이/렌더를 LF 고정으로 읽는다(플랫폼 개행 변환 회피, Windows 결정론).

    반환 (text, error). 읽기 실패는 조용히 넘기지 않고 error 로 표면화한다(silent skip 금지).
    """
    try:
        # newline="" → 개행 변환 없이 원문 유지. 이후 CRLF 를 LF 로 명시 정규화.
        with open(path, "r", encoding="utf-8", newline="") as f:
            raw = f.read()
    except (OSError, UnicodeError) as e:
        return None, f"오버레이/렌더 읽기 실패: {path} ({e})"
    return raw.replace("\r\n", "\n").replace("\r", "\n"), None


def write_text_lf(path, text, mode=None):
    """LF 고정으로 원자적 기록(같은 디렉터리 temp 에 완결 후 os.replace).

    L1(SessionStart)이 세션마다 렌더를 쓰고 claude/codex SessionStart 가 공유 AGENT_GUIDE 를 동시
    기록할 수 있어, 직접 open('w') 는 kill/경합 시 잘린 파일을 남기고 다음 read_text_lf 가 base 를
    오판한다. temp+os.replace 로 부분파일을 없앤다. os.replace 는 대상이 symlink 여도 링크 자체를
    교체하므로(링크 대상 밖 기록 안 함) symlink 경유 우회도 자연히 막는다."""
    previous_mode = None
    try:
        previous_stat = os.lstat(path)
        if stat.S_ISREG(previous_stat.st_mode):
            previous_mode = stat.S_IMODE(previous_stat.st_mode)
    except FileNotFoundError:
        pass
    d = os.path.dirname(path) or "."
    while True:
        tmp = os.path.join(d, f".sage-overlay-tmp-{uuid.uuid4().hex}")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            break
        except FileExistsError:
            continue
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        target_mode = mode if mode is not None else previous_mode
        if target_mode is not None:
            os.chmod(tmp, target_mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def validate_overlay(text):
    """오버레이 본문 검사 → error 메시지 | None. 본문에 마커 토큰이 있으면 reject.

    저작·compose·lint 어디서든 선검사한다 — 마커 토큰이 본문에 섞이면 합성 후 마커 짝이
    깨져 base_of/insert_block 이 malformed 로 오판한다.
    """
    for tok in _MARKER_TOKENS + _ROUTING_TOKENS:
        if tok in text:
            return f"오버레이 본문에 예약 마커 토큰('{tok}')이 있어 합성할 수 없습니다"
    return None


def routing_block_token_error(text):
    """라우팅 블록 본문에 예약 마커 토큰이 있는지 검사 → error | None.

    profile 유래 문자열(도메인 id·경로·label)이 마커 토큰을 포함하면 합성 후 마커 짝이 깨져
    base_of/insert_routing_block 이 malformed 로 오판한다. 렌더 직전 fail-closed 로 막는다.
    """
    for tok in _MARKER_TOKENS + _ROUTING_TOKENS:
        if tok in text:
            return f"라우팅 블록 본문에 예약 마커 토큰('{tok}')이 있어 생성할 수 없습니다"
    return None


def wrap_routing_block(body):
    """라우팅 블록 본문 → 마커로 감싼 관리 블록 문자열. 본문이 비면 '' 반환.

    base 는 건드리지 않고 블록만 만든다(오버레이 compose_block 과 동형). idempotent.
    """
    body = body.strip()
    if not body:
        return ""
    return f"{ROUTING_MARKER_START}\n{body}\n{ROUTING_MARKER_END}\n"


def compose_block(overlay_text, kind, id):
    """오버레이 텍스트 → 관리 블록 문자열(마커+헤더+본문). 오버레이가 비면 '' 반환.

    블록만 만든다(base 는 건드리지 않는다). additive-only 헤더로 "CORE 에 더한다, 완화
    불가"를 명시한다(오버레이가 안전 경계를 덮지 못하게). idempotent: 같은 입력→같은 출력.
    """
    body = overlay_text.strip()
    if not body:
        return ""
    header = (
        f"## Project-Local Additions (sage/asset_overrides/{kind}/{id}.md)\n"
        "아래는 이 프로젝트 로컬 추가 지침이며 CORE 기본 지침에 **더한다**.\n"
        "AGENT_GUIDE·phase·review·verification·안전 경계를 **완화할 수 없다**."
    )
    return f"{MARKER_START}\n{header}\n{body}\n{MARKER_END}\n"


def _counts_ok(text, start, end, block_re, label):
    """마커 구간 정합 검사 → error | None. 중복(>1)·짝불일치·순서역전을 malformed 로 잡는다.

    count 만 보면 END 가 START 앞에 온 역순(각 1개)이 통과하지만, block_re(START..END DOTALL)는
    추출에 실패해 base_of 가 그 마커를 base 에 남긴다 → 앵커 오염 + drift 미감지. count 가 1-and-1
    이면 실제 정규식 추출이 되는지까지 확인해 이 괴리를 없앤다(codex R1-1).
    """
    starts = text.count(start)
    ends = text.count(end)
    if starts > 1 or ends > 1:
        return f"{label} 마커 중복(관리 블록이 2개 이상)"
    if (starts == 1) != (ends == 1):
        return f"{label} 마커 짝 불일치(malformed)"
    if starts == 1 and not block_re.search(text):
        return f"{label} 마커 순서/중첩 오류(START..END 추출 불가)"
    return None


def _marker_counts_ok(text):
    """오버레이 마커 짝 검사 → error | None."""
    return _counts_ok(text, MARKER_START, MARKER_END, _BLOCK_RE, "오버레이")


def _routing_marker_counts_ok(text):
    """라우팅 마커 짝 검사 → error | None."""
    return _counts_ok(text, ROUTING_MARKER_START, ROUTING_MARKER_END, _ROUTING_BLOCK_RE, "라우팅")


def base_of(installed_text):
    """설치본에서 관리 구간(오버레이 + 라우팅)을 모두 제거한 base 를 반환 → (base, error).

    마커 0쌍이면 원문 그대로(정상). >1 또는 짝불일치면 error(해시 대조 불가). base 해시
    앵커 대조·expected_render 의 base' 계산에 쓴다. **두 관리 구간을 함께 제거**해야 프로젝트별
    라우팅 값이 base 앵커를 오염시키지 않는다(FB25) — 라우팅 블록이 없던 기존 설치본은 라우팅
    정규식이 무매칭이라 거동 불변.
    """
    err = _marker_counts_ok(installed_text) or _routing_marker_counts_ok(installed_text)
    if err:
        return installed_text, err
    # 말미 개행 1개로 정규화 = canonical base. base_of 는 install/validate 양쪽에서 앵커
    # 해시원으로 쓰이므로, 블록 삽입 시 생긴 구분 개행을 흡수해 round-trip 을 안정화한다.
    stripped = _ROUTING_BLOCK_RE.sub("", _BLOCK_RE.sub("", installed_text))
    # 오버레이·라우팅 마커가 교차 중첩(예: OVERLAY_START·ROUTING_START·OVERLAY_END·ROUTING_END)하면
    # 각 count/regex 는 통과하나 한 구간을 먼저 지운 뒤 다른 구간의 짝이 깨져 잔여 마커가 base 에 남는다
    # → 앵커 오염(codex R2-1). 두 구간을 지운 뒤에도 마커 문자열이 남으면 malformed 로 거부한다. base 는
    # SAGE 예약 마커를 담지 않으며(오버레이/라우팅 본문도 마커 토큰을 reject) 정상 입력엔 무영향.
    if any(mark in stripped for mark in (MARKER_START, MARKER_END,
                                         ROUTING_MARKER_START, ROUTING_MARKER_END)):
        return installed_text, "오버레이·라우팅 마커 교차 중첩(관리 구간 겹침)"
    return _normalize_trailing(stripped), None


def insert_block(installed_text, block):
    """설치본의 마커 구간을 block 으로 교체 → (new_text, error). base 영역 불변.

    - block 이 비면(''): 기존 마커 구간을 제거(스트립)한다 — (c)/미분류 또는 오버레이 삭제 시
      조작 블록이 남지 않도록 수렴시킨다.
    - 마커가 없고 block 이 있으면: base 말미에 append.
    - 마커 중복/짝불일치 → error(아무것도 안 바꿈).
    """
    err = _marker_counts_ok(installed_text)
    if err:
        return installed_text, err
    has_block = installed_text.count(MARKER_START) == 1
    if not block:
        if not has_block:
            return installed_text, None
        # 마커 구간 제거 후 말미 개행 정규화(스트립 자국 없이 깔끔한 base 로 수렴).
        return _normalize_trailing(_BLOCK_RE.sub("", installed_text)), None
    if has_block:
        return _BLOCK_RE.sub(block, installed_text, count=1), None
    base = _normalize_trailing(installed_text)
    joiner = "\n" if base else ""
    return base + joiner + block, None


def extract_block(text):
    """설치본에서 관리 블록 문자열을 추출(없으면 None). 마커 구간 대조·존재 판정용."""
    m = _BLOCK_RE.search(text)
    return m.group(0) if m else None


def insert_routing_block(installed_text, block):
    """설치본의 라우팅 마커 구간을 block 으로 교체 → (new_text, error). base·오버레이 구간 불변.

    insert_block 과 동형이나 라우팅 마커만 다룬다. block 이 비면 기존 라우팅 구간을 제거(스트립),
    없으면 base 말미에 append. 마커 중복/짝불일치 → error(아무것도 안 바꿈).
    """
    err = _routing_marker_counts_ok(installed_text)
    if err:
        return installed_text, err
    has_block = installed_text.count(ROUTING_MARKER_START) == 1
    if not block:
        if not has_block:
            return installed_text, None
        return _normalize_trailing(_ROUTING_BLOCK_RE.sub("", installed_text)), None
    if has_block:
        return _ROUTING_BLOCK_RE.sub(block, installed_text, count=1), None
    base = _normalize_trailing(installed_text)
    joiner = "\n" if base else ""
    return base + joiner + block, None


def extract_routing_block(text):
    """설치본에서 라우팅 관리 블록 문자열을 추출(없으면 None)."""
    m = _ROUTING_BLOCK_RE.search(text)
    return m.group(0) if m else None
