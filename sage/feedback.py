"""sage-feedback 개발자 피드백 마커 스캔 (§10-a-C) — CLI 측 파일 IO 계층.

마커 정규식·해소 판정 같은 **원시 로직은 이 모듈이 소유하지 않는다**. hook 코어가
`sage` 패키지에 의존할 수 없어(프로젝트가 자기 hook 코어를 소유하는 모델) 원시 로직은
`scripts/sage_harness/hooks/runtime/feedback_markers.py` 에 있고, 여기서는 그것을 로드해
쓴다 — acceptance_waiver 와 같은 구조. 복제하면 게이트와 CLI 가 서로 다른 마커를 보게 된다.

이 모듈이 담당하는 것은 **스캔 범위**와 **처리 이력 기록**이다. 스캔은 git 추적 파일로 한정하고
plan_docs 를 제외한다.
vault·빌드 산출물·.sage 로그가 자동으로 빠져, 기록 노트에 적힌 토큰이 다음 스캔에서
새 마커로 잡히는 자기증식을 구조적으로 막는다.
"""
import json
import os
import subprocess
import sys
import time

from sage import _resources

from sage.diagnostics import Diagnostic


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

# 기록은 감사 목적이라 `.sage/override.jsonl` 과 같이 **커밋된다**. 그래서 추적 파일이 되고,
# 레코드에 담긴 마커 원문이 다음 스캔에서 새 마커로 잡혀 자기증식한다 — `.sage/` 를 항상
# 제외해 구조적으로 막는다. 감사 로그는 마커를 다는 자리가 아니므로 잃는 것이 없다.
_ALWAYS_EXCLUDED = (".sage/",)

RECORD_REL = os.path.join(".sage", "feedback.jsonl")

# 3분기 판정(스킬 워크플로와 1:1). undetermined 는 마커를 남기므로 미해소다.
VERDICT_FIXED = "fixed"                  # 실제 불일치 → 계획에 맞게 수정, 마커 제거
VERDICT_INTENTIONAL = "intentional"      # 불일치 아님(의도적·정당) → 코드 불변, 마커 제거
VERDICT_UNDETERMINED = "undetermined"    # 판단 불가 → 코드·마커 불변, 사용자에게 되질문
VERDICTS = (VERDICT_FIXED, VERDICT_INTENTIONAL, VERDICT_UNDETERMINED)
_RESOLVING = (VERDICT_FIXED, VERDICT_INTENTIONAL)


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



class ScanError(RuntimeError):
    """스캔 실패. **완성 문장이 아니라 언어 중립 진단을 실어 나른다.**

    이 모듈은 설치된 hook 이 닿는 경로에 있어 `sage.i18n` 을 import 할 수 없다. 그래서 무엇이
    잘못됐는지(`diagnostic`)만 들고 올라가고, 어느 언어의 어떤 문장으로 보일지는 호출부가 정한다.

    `str(exc)` 는 code 와 evidence 를 그대로 낸다 — 사람이 읽는 문장은 아니지만, 이행 중 이
    예외를 문자열로 찍던 경로에서도 정보가 사라지지 않는다.
    """

    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        detail = getattr(diagnostic, "evidence", "")
        code = getattr(diagnostic, "code", str(diagnostic))
        super().__init__(f"{code}: {detail}" if detail else code)


# git 이 "저장소가 아니다" 라고 답하는 경우만 정상적인 빈 결과다. 그 외 실패는 스캔 불능이다.
_NOT_A_REPO = ("not a git repository", "not a working tree")


def tracked_files(root):
    """git 추적 파일 목록. git 저장소가 아니면 빈 리스트, 그 외 실패는 ScanError."""
    try:
        proc = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                              capture_output=True, timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise ScanError(Diagnostic("feedback.git_timeout", root=root)) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise ScanError(Diagnostic("feedback.git_failed", root=root,
                                   evidence=f"{type(exc).__name__}: {exc}")) from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        if any(token in stderr.lower() for token in _NOT_A_REPO):
            return []                     # git 저장소가 아님 = 스캔 대상 없음(정상)
        # stderr 는 git 이 돌려준 원문이다 — 번역하면 사용자가 검색할 수 있는 문자열이 사라진다.
        raise ScanError(Diagnostic("feedback.git_exit", code=proc.returncode,
                                   evidence=stderr))
    out = proc.stdout.decode("utf-8", "surrogateescape")
    return [p for p in out.split("\0") if p]


def _excluded_prefixes(profile):
    """스캔에서 제외할 경로 접두. plan_docs 는 마커 예시·설계 서술을 담아 오탐원이다."""
    prefixes = list(_ALWAYS_EXCLUDED)
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
    """저장소에서 마커를 스캔한다. 반환은 path, line 순 정렬. 목록 확정 실패는 ScanError."""
    prefixes = _excluded_prefixes(profile)
    markers = []
    for rel in tracked_files(root):
        if _is_excluded(rel, prefixes):
            continue
        absolute = os.path.join(root, rel)
        if not os.path.exists(absolute):
            continue                      # 인덱스에는 있고 워크트리엔 없음(삭제 스테이징 전) = 정상
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
        except UnicodeDecodeError:
            continue          # 비 UTF-8 = 마커 규약 밖(토큰은 ASCII)
        except OSError as exc:
            # 존재하는데 못 읽는 파일은 "마커 없음" 이 아니라 **모름** 이다. 조용히 넘기면
            # 권한 하나로 게이트가 통과하므로 스캔 실패로 올린다.
            raise ScanError(Diagnostic("feedback.unreadable_file", path=rel,
                                       evidence=f"{type(exc).__name__}: {exc}")) from exc
        markers.extend(scan_text(text, rel))
    markers.sort(key=lambda m: (m.path, m.line))
    return markers


def blocking(markers):
    return [m for m in markers if m.blocking]


def _section(profile):
    section = (profile or {}).get("feedback")
    return section if isinstance(section, dict) else {}


def enabled(profile):
    """profile.feedback.enabled. 섹션이 없으면 비활성(하위호환 — 기존 프로필 무손상)."""
    return bool(_section(profile).get("enabled"))


def record_enabled(profile):
    """profile.feedback.record. enabled 가 꺼져 있으면 기록도 없다(기능 자체가 off)."""
    return enabled(profile) and _section(profile).get("record") is True


def block_release(profile):
    """profile.feedback.block_release — 미해결 차단성 마커로 릴리즈를 막을지."""
    return enabled(profile) and _section(profile).get("block_release") is True


def record_target(profile):
    """profile.feedback.record_target. 무효값은 auto 로 degrade(검증기가 별도 WARN)."""
    value = _section(profile).get("record_target")
    return value if value in ("auto", "sage", "vault") else "auto"


def record_path(root):
    return os.path.join(root, RECORD_REL)


def build_record(path, line, verdict, note, blocking=False,
                 marker_text=None, cycle_stem=None, user=None, now=None):
    """기록 레코드 1건. `resolved` 는 verdict 에서 파생된다 — 호출자가 따로 주장하지 못하게
    한다(판단 불가인데 해소됨으로 기록되면 감사가 거짓이 된다)."""
    epoch = time.time() if now is None else now
    return {"event": "feedback", "ts": _iso(epoch), "epoch": int(epoch),
            "path": path, "line": int(line), "blocking": bool(blocking),
            "verdict": verdict, "resolved": verdict in _RESOLVING,
            "note": note, "marker_text": marker_text or "",
            "cycle_stem": cycle_stem or "",
            "user": user or os.environ.get("USER") or "unknown"}


def append_record(root, record):
    """감사 로그에 append-only 로 1건 추가 → 기록된 절대경로.

    마커는 해소되면 코드에서 사라지는 짧은 수명이라 파일 단위 기록은 죽은 파일만 쌓인다.
    append-only 는 해소 레코드를 덧붙이면 되므로 수명 문제가 없다(override.jsonl 과 같은 관례).
    """
    path = record_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def read_records(root):
    """기록 전 레코드(파싱 실패 줄은 skip). 부재 → []."""
    path = record_path(root)
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))
