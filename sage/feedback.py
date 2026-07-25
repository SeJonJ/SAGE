"""sage-feedback 개발자 피드백 마커 스캔 (§10-a-C).

개발자가 완료된 사이클 코드에 남긴 `sage-feedback ::` 마커를 찾는다. 주석 기호가 아니라
**토큰 문자열**을 찾으므로 언어에 무관하다(`//` Java/JS · `#` Python/YAML · `--` SQL 등).

스캔 범위는 **git 추적 파일**로 한정한다. vault·빌드 산출물·`.sage/` 로그가 자동으로 빠져,
기록 노트에 적힌 토큰이 다음 스캔에서 새 마커로 잡히는 자기증식을 구조적으로 막는다.
문자열 리터럴은 걸러내지 않는다 — 거르려면 주석 판별이 필요하고 그러면 언어 무관성이
깨진다. `::` 구분자가 필수라 단어만 든 문자열은 애초에 걸리지 않는다.
"""
import os
import re
import subprocess

# (!?)  = 심각도. `!` 접두 = 차단성, 없으면 advisory.
# 두 토큰을 따로 검색하면 `sage-feedback` 이 `!sage-feedback` 의 부분문자열이라
# 차단성 마커가 advisory 검색에도 걸린다. optional 그룹으로 한 번에 뽑는다.
MARKER_RE = re.compile(r"(!?)sage-feedback\s*::[ \t]*(.*)")

# 바이너리·초대형 파일 방어. 소스 주석에 마커를 다는 용도라 이 상한이면 충분하다.
_MAX_BYTES = 2 * 1024 * 1024

# 블록 주석 종료자. 주석 문법을 해석하진 않지만(언어 무관성 유지), 마커 본문 끝에 딸려온
# 종료자는 기록·표시에 노이즈라 잘라낸다. 판정에는 영향이 없다.
_TRAILING_COMMENT_ENDS = ("-->", "*/", "--}}", "#}", "*)", '"""', "'''")


class Marker:
    """마커 1건. 정체성은 `path:line` 이다(대응하는 acceptance_id 가 없다)."""

    __slots__ = ("path", "line", "blocking", "text")

    def __init__(self, path, line, blocking, text):
        self.path = path
        self.line = line
        self.blocking = blocking
        self.text = text

    def as_dict(self):
        return {"path": self.path, "line": self.line,
                "blocking": self.blocking, "text": self.text}

    def __repr__(self):
        bang = "!" if self.blocking else ""
        return f"<Marker {self.path}:{self.line} {bang}sage-feedback :: {self.text[:40]!r}>"


def tracked_files(root):
    """git 추적 파일 목록. git 저장소가 아니거나 git 이 없으면 빈 리스트(스캔 대상 없음)."""
    try:
        proc = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                              capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    out = proc.stdout.decode("utf-8", "surrogateescape")
    return [p for p in out.split("\0") if p]


def _excluded_prefixes(profile):
    """스캔에서 제외할 경로 접두. plan_docs 는 마커 예시·설계 서술을 담아 오탐원이다."""
    prefixes = []
    paths = (profile or {}).get("paths") or {}
    if isinstance(paths, dict):
        value = paths.get("plan_docs")
        if isinstance(value, str) and value.strip():
            prefixes.append(value.strip().strip("/").replace(os.sep, "/") + "/")
    return prefixes


def _is_excluded(rel_path, prefixes):
    return any(rel_path.startswith(prefix) for prefix in prefixes)


def _clean_text(value):
    value = value.strip()
    for end in _TRAILING_COMMENT_ENDS:
        if value.endswith(end):
            value = value[: -len(end)].rstrip()
            break
    return value


def scan_text(text, path="<text>"):
    """문자열 1건에서 마커를 뽑는다(파일 IO 없이 단위 테스트 가능하도록 분리)."""
    found = []
    for number, raw in enumerate(text.splitlines(), start=1):
        match = MARKER_RE.search(raw)
        if match:
            found.append(Marker(path, number, match.group(1) == "!", _clean_text(match.group(2))))
    return found


def scan(root, profile=None):
    """저장소에서 마커를 스캔한다. 반환은 path, line 순 정렬."""
    prefixes = _excluded_prefixes(profile)
    markers = []
    for rel in tracked_files(root):
        if _is_excluded(rel, prefixes):
            continue
        absolute = os.path.join(root, rel)
        try:
            if os.path.getsize(absolute) > _MAX_BYTES:
                continue
            with open(absolute, "rb") as handle:
                raw = handle.read()
            # NUL 바이트 = 바이너리(git 과 동일 판정). NUL 은 유효한 UTF-8 코드포인트라
            # decode 만으로는 걸러지지 않는다 — 텍스트로 열면 바이너리에서 오탐이 난다.
            if b"\0" in raw:
                continue
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue          # 읽기 불가·비 UTF-8 파일은 조용히 건너뛴다
        markers.extend(scan_text(text, rel))
    markers.sort(key=lambda m: (m.path, m.line))
    return markers


def blocking(markers):
    return [m for m in markers if m.blocking]


def enabled(profile):
    """profile.feedback.enabled. 섹션이 없으면 비활성(하위호환 — 기존 프로필 무손상)."""
    section = (profile or {}).get("feedback")
    if not isinstance(section, dict):
        return False
    return bool(section.get("enabled"))
