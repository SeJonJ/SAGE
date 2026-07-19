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
    for tok in _MARKER_TOKENS:
        if tok in text:
            return f"오버레이 본문에 예약 마커 토큰('{tok}')이 있어 합성할 수 없습니다"
    return None


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


def _marker_counts_ok(text):
    """마커 짝 검사 → error | None. 중복(>1)·짝불일치는 malformed."""
    starts = text.count(MARKER_START)
    ends = text.count(MARKER_END)
    if starts > 1 or ends > 1:
        return "오버레이 마커 중복(관리 블록이 2개 이상)"
    if (starts == 1) != (ends == 1):
        return "오버레이 마커 짝 불일치(malformed)"
    return None


def base_of(installed_text):
    """설치본에서 마커 구간을 제거한 base 를 반환 → (base, error).

    마커 0쌍이면 원문 그대로(정상). >1 또는 짝불일치면 error(해시 대조 불가). base 해시
    앵커 대조·expected_render 의 base' 계산에 쓴다.
    """
    err = _marker_counts_ok(installed_text)
    if err:
        return installed_text, err
    # 말미 개행 1개로 정규화 = canonical base. base_of 는 install/validate 양쪽에서 앵커
    # 해시원으로 쓰이므로, 블록 삽입 시 생긴 구분 개행을 흡수해 round-trip 을 안정화한다.
    return _normalize_trailing(_BLOCK_RE.sub("", installed_text)), None


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
