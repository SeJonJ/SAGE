"""sage-feedback 개발자 피드백 마커 스캔 (§10-a-C) — CLI 측 파일 IO 계층.

마커 정규식·해소 판정 같은 **원시 로직은 이 모듈이 소유하지 않는다**. hook 코어가
`sage` 패키지에 의존할 수 없어(프로젝트가 자기 hook 코어를 소유하는 모델) 원시 로직은
`scripts/sage_harness/hooks/runtime/feedback_markers.py` 에 있고, 여기서는 그것을 로드해
쓴다 — acceptance_waiver 와 같은 구조. 복제하면 게이트와 CLI 가 서로 다른 마커를 보게 된다.

이 모듈이 담당하는 것은 **스캔 범위**다: git 추적 파일로 한정하고 plan_docs 를 제외한다.
vault·빌드 산출물·.sage 로그가 자동으로 빠져, 기록 노트에 적힌 토큰이 다음 스캔에서
새 마커로 잡히는 자기증식을 구조적으로 막는다.
"""
import os
import subprocess
import sys

from sage import _resources


def _markers_module():
    runtime = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks", "runtime")
    if runtime not in sys.path:
        sys.path.insert(0, runtime)
    import feedback_markers
    return feedback_markers


_fm = _markers_module()
MARKER_RE = _fm.MARKER_RE

# 바이너리·초대형 파일 방어. 소스 주석에 마커를 다는 용도라 이 상한이면 충분하다.
_MAX_BYTES = 2 * 1024 * 1024


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


def scan_text(text, path="<text>"):
    """문자열 1건에서 마커를 뽑는다(runtime 단일 출처 위임)."""
    return [Marker(d["path"], d["line"], d["blocking"], d["text"])
            for d in _fm.scan_text(text, path)]


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
