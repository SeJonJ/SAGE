"""통합 감사 조회의 I/O 층 — 안전한 snapshot 과 source adapter.

## 왜 lock 을 잡지 않는가

`loop_audit._audit_lock` 은 `.sage/` 디렉터리와 `.lock` 파일을 **만든다**. 읽기만 하겠다고
약속한 명령이 그 함수를 부르면 그 순간 약속이 깨진다 — 얻는 lock 이 bounded 인지와는 무관한
문제다. 그래서 이 모듈은 lock 을 만들지도, 획득하지도, 기다리지도 않는다.

대가는 진행 중인 append 중간을 볼 수 있다는 것이다. 그 상태를 감추지 않는다. `lstat` 으로
identity 를 잡고, 읽은 뒤 `fstat` 으로 다시 대조해서, 바뀌었으면 한 번만 재시도하고 그래도
바뀌면 실패한다. 부분 결과를 정상으로 표시하는 분기는 없다.

## 왜 세 상태를 하나로 접지 않는가

`absent`(파일이 없다)·`unreadable`(읽을 수 없다)·`concurrent`(읽는 중 바뀌었다)는 서로 다른
사실이다. `absent` 를 손상으로 올리면 감사를 한 번도 쓰지 않은 정상 프로젝트가 붉어지고,
손상을 `absent` 로 접으면 깨진 감사가 "기록 없음" 으로 사라진다. 후자가 더 조용한 방향이라
더 위험하다.

## 왜 진단 인자를 한 문으로 모으는가

이 층이 만드는 문자열의 출처가 우리 코드만이 아니다. OS 예외 메시지에는 열려던 파일의
**절대경로**가 들어 있고, 감사 모듈의 판정문에는 레코드에서 온 값이 들어 있다. 둘 다 그대로
`reason` 이 되어 화면과 JSON 으로 나간다. 그래서 진단은 `load_source` 안의 문 하나를 지나고,
그 문에서 인자 전체를 한 번 더 거른다 — 부르는 자리마다 기억해서 거르는 방식은 새 진단이
생길 때 잊힌다.

## 왜 판정을 여기서 하지 않는가

무결성 판정은 각 감사 모듈이 이미 소유하고 있다. 여기서 다시 구현하면 같은 감사 형식의
해석기가 둘이 되고, 갈렸을 때 어느 쪽이 옳은지 판정할 근거가 없어진다. 이 모듈은 bytes 를
안전하게 가져와 그 모듈들의 **순수 함수** 에 넘기기만 한다.
"""
from __future__ import annotations

import errno
import json
import os
import stat
import subprocess

from sage import audit_view as view

# source 당 상한. 넘치면 잘라 읽어 절반만 판정하지 않고 `unreadable` 로 올린다 — 잘린 꼬리에
# terminal 이벤트가 있으면 끝난 run 을 진행 중으로 보게 된다.
MAX_BYTES = 16 * 1024 * 1024
MAX_LINES = 100_000

# Git probe 상한. 부가 정보 하나 때문에 조회가 멈추지 않는다.
GIT_TIMEOUT_SECONDS = 5

READ_ABSENT = "absent"
READ_OK = "ok"
READ_UNREADABLE = "unreadable"
READ_CONCURRENT = "concurrent"


def _os_detail(exc):
    """OS 예외를 경로 없는 토큰으로. (`PermissionError:EACCES` 꼴)

    `str(exc)` 를 쓰지 않는다. `OSError` 의 문자열에는 열려던 파일명이 붙고, 이 층에서 그
    파일명은 곧 저장소 절대경로다 — vault 아래에 있는 프로젝트면 vault 경로가 그대로 나간다.
    errno 이름은 원인을 구분하기에 충분하면서 경로를 담지 않는다.
    """
    name = errno.errorcode.get(exc.errno) if exc.errno is not None else None
    return f"{type(exc).__name__}:{name or 'UNKNOWN'}"


def _identity(info):
    return (info.st_dev, info.st_ino)


def _volatile(info):
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_once(path):
    """(status, bytes, detail). lock 을 잡지 않고 한 번 읽는다."""
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        return READ_ABSENT, b"", None
    except OSError as exc:
        return READ_UNREADABLE, b"", _os_detail(exc)

    if stat.S_ISLNK(before.st_mode):
        # symlink 는 따라가지 않는다. 따라가면 조회 대상이 저장소 밖 임의 파일이 될 수 있고,
        # 그 내용이 감사인 것처럼 화면에 실린다.
        return READ_UNREADABLE, b"", "symlink"
    if not stat.S_ISREG(before.st_mode):
        return READ_UNREADABLE, b"", "not_regular"
    if before.st_size > MAX_BYTES:
        return READ_UNREADABLE, b"", f"oversize:{before.st_size}"

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        return READ_UNREADABLE, b"", _os_detail(exc)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
            # lstat 과 open 사이에 다른 파일로 바뀌었다. 여기서 그냥 읽으면 우리가 검사한
            # 파일이 아닌 것을 검사한 결과로 보고하게 된다.
            return READ_CONCURRENT, b"", "identity_changed"
        chunks, total = [], 0
        while total <= MAX_BYTES:
            chunk = os.read(fd, min(65536, MAX_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > MAX_BYTES:
            return READ_UNREADABLE, b"", f"oversize:{total}"
        after = os.fstat(fd)
    except OSError as exc:
        return READ_UNREADABLE, b"", _os_detail(exc)
    finally:
        os.close(fd)

    if _volatile(after) != _volatile(opened):
        return READ_CONCURRENT, b"", "changed_while_reading"
    return READ_OK, b"".join(chunks), None


def secure_snapshot(path):
    """(status, bytes, detail). 불안정하면 **한 번만** 재시도한다.

    무한 재시도를 두지 않는 이유는, 계속 쓰이고 있는 감사에서 조회가 끝나지 않기 때문이다.
    한 번으로 안정되지 않으면 그 사실을 그대로 보고하는 것이 맞다.
    """
    status, data, detail = _read_once(path)
    if status != READ_CONCURRENT:
        return status, data, detail
    return _read_once(path)


def _decode_lines(data):
    """(lines, issue). 추측 복구를 하지 않는다."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, f"not_utf8:{exc.reason}"
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        return None, f"too_many_lines:{len(lines)}"
    return lines, None


def parse_lines(lines):
    """(번호 붙은 dict 레코드, issue 문자열). 비-dict 는 조용히 버리지 않는다.

    `_parse_bytes` 와 판정이 같아야 하지만 여기서 그 함수를 부르지 않는다 — 그쪽은 줄 번호를
    버리고, 조회는 몇 번째 줄이 깨졌는지를 사용자에게 말해야 한다.
    """
    numbered, issues = [], []
    for line_no, line in enumerate(lines, 1):
        raw = line.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except Exception:
            issues.append(f"line {line_no}: malformed JSON")
            continue
        if not isinstance(record, dict):
            issues.append(f"line {line_no}: record must be an object")
            continue
        numbered.append((line_no, record))
    return numbered, issues


def _hook_path():
    """hook 런타임 모듈을 import 할 수 있게 한다. 매 호출마다 확인한다.

    다른 모듈이 남긴 `sys.path` 부작용에 기대면 호출 순서를 바꾸거나 그쪽이 실패했을 때
    조용히 import 가 깨진다.
    """
    import sys

    from sage import _resources
    hooks = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks")
    for candidate in (os.path.join(hooks, "runtime"), hooks):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


# --- source 별 무결성 판정 ---------------------------------------------------
#
# 각 함수는 (status, issues) 를 돌려준다. 판정 자체는 감사 모듈의 순수 함수가 하고, 여기서는
# 그 결과를 조회 어휘로 옮기기만 한다.


def _review_integrity(numbered):
    _hook_path()
    import loop_audit

    records = [record for _line, record in numbered]
    summary = loop_audit.summarize_records(records, [])
    diagnostics = loop_audit.integrity_from_records(records, [])
    issues = [f"{item['code']}: {item.get('evidence') or item.get('arguments')}"
              for item in diagnostics]
    chain = [state.get("chain_ok") for state in summary["runs"].values()]
    if any(state is False for state in chain):
        return view.STATUS_INVALID, issues
    if issues:
        return view.STATUS_INVALID, issues
    if records and all(state is None for state in chain):
        # 보증 필드가 없는 과거 run 이다. 실패가 아니라 "이 run 에는 보증이 없다" 이고,
        # 실패로 올리면 과거 run 을 가진 모든 저장소가 붉어진다.
        return view.STATUS_LEGACY, issues
    return view.STATUS_VALID, issues


def _fast_integrity(numbered):
    _hook_path()
    import fast_cycle_audit

    records = [record for _line, record in numbered]
    summary = fast_cycle_audit.summarize_records(records, [])
    issues = []
    for run_id in sorted(summary["runs"]):
        for line in fast_cycle_audit.opener_issues(summary["runs"][run_id]):
            issues.append(f"{run_id}: {line}")
    if issues:
        return view.STATUS_INVALID, issues
    chain = [state.get("chain_ok") for state in summary["runs"].values()]
    if records and all(state is None for state in chain):
        return view.STATUS_LEGACY, issues
    return view.STATUS_VALID, issues


def _acceptance_integrity(numbered):
    _hook_path()
    import acceptance_waiver

    summary = acceptance_waiver.summarize_records(numbered, [])
    if summary["issues"]:
        return view.STATUS_INVALID, list(summary["issues"])
    return view.STATUS_VALID, []


def _retro_integrity(numbered):
    _hook_path()
    import retro_audit

    known = set(retro_audit._EVENTS)
    issues = [f"line {line_no}: unknown event {record.get('event')!r}"
              for line_no, record in numbered if record.get("event") not in known]
    return (view.STATUS_INVALID if issues else view.STATUS_VALID), issues


def _unverified_integrity(_numbered):
    """override·feedback. 검증이 없으므로 판정할 것도 없다.

    `valid` 로 표시하지 않는 것이 요점이다. 파싱이 됐다는 사실은 무결성이 아니다.
    """
    return view.STATUS_NOT_APPLICABLE, []


_INTEGRITY = {
    "review": _review_integrity,
    "fast": _fast_integrity,
    "acceptance": _acceptance_integrity,
    "retro": _retro_integrity,
    "override": _unverified_integrity,
    "feedback": _unverified_integrity,
}


def state_of(source):
    """source 상태 dict 의 정본 모양. **읽기 전 기본값**이다.

    `load_source` 와 그 바깥의 실패 대체가 같은 이 함수를 쓴다. 두 자리에서 각각 dict 를 짓던
    동안 한쪽에만 key 를 더한 것이 조용히 통과했다 — 소비자에게 key 집합은 계약이고, 예외
    경로에서만 달라지는 계약은 하필 예외가 났을 때 깨진다.

    `tracking` 은 실제 Git 상태고 `policy` 는 이 source 가 공유물인지 개인물인지다. 하나로
    접으면 "공유 대상인데 커밋 안 됨" 과 "원래 개인 것" 이 같은 값이 된다.
    """
    return {
        "id": source.id,
        "path": source.rel,
        "present": False,
        "record_count": 0,
        "integrity": {"method": source.method, "status": view.STATUS_NOT_APPLICABLE},
        "caveat": source.caveat,
        "policy": source.visibility,
        "tracking": None,
    }


def load_source(root, source):
    """source 하나를 읽어 조회 결과로. 예외를 밖으로 올리지 않는다.

    한 source 가 무너져도 나머지는 보여준다. "하나 실패하면 전부 안 보여준다" 는 조회 도구가
    할 수 있는 가장 나쁜 실패 양식이다.
    """
    result = dict(state_of(source), issues=[], events=[])

    def report(code, **arguments):
        """이 source 의 모든 진단이 지나는 문 하나.

        인자를 여기서 한 번 더 거른다. `reason` 에 실리는 문자열은 우리가 쓴 것만이 아니라
        OS 예외와 감사 모듈 판정문에서도 오고, 그 둘은 절대경로와 레코드 원문을 품는다.
        """
        clean, _hits = view.sanitize_value(dict(arguments, source=source.id))
        result["issues"].append((code, clean))

    path = os.path.join(root, *source.rel.split("/"))
    status, data, detail = secure_snapshot(path)

    if status == READ_ABSENT:
        return result
    result["present"] = True

    if status == READ_UNREADABLE:
        result["integrity"]["status"] = view.STATUS_UNREADABLE
        report("audit.source.unreadable", reason=detail or "unknown")
        return result
    if status == READ_CONCURRENT:
        result["integrity"]["status"] = view.STATUS_UNREADABLE
        report("audit.source.concurrent_change", reason=detail or "unknown")
        return result

    lines, decode_issue = _decode_lines(data)
    if lines is None:
        result["integrity"]["status"] = view.STATUS_UNREADABLE
        report("audit.source.unreadable", reason=decode_issue)
        return result

    numbered, parse_issues = parse_lines(lines)
    result["record_count"] = len(numbered)
    for line in parse_issues:
        report("audit.source.malformed", reason=line)

    try:
        integrity_status, integrity_issues = _INTEGRITY[source.id](numbered)
    except Exception as exc:
        # adapter 자체가 터진 것은 프로젝트 상태가 아니라 도구 실패다. 같은 축으로 내면
        # 사용자는 고칠 것이 없는 것을 고치러 간다.
        result["integrity"]["status"] = view.STATUS_UNREADABLE
        report("audit.source.unavailable", error=type(exc).__name__)
        return result

    result["integrity"]["status"] = integrity_status
    for line in integrity_issues:
        report("audit.source.invalid", reason=line)
    if integrity_status == view.STATUS_LEGACY:
        # 보증이 없다는 사실은 화면에 나가야 한다. status 에만 적고 진단을 올리지 않으면
        # 사용자는 `legacy` 라는 토큰을 보고도 그것이 무슨 뜻인지 알 수 없다.
        report("audit.source.legacy")

    for line_no, record in numbered:
        item, issues = view.envelope(source.id, line_no, record)
        result["events"].append(item)
        for code, arguments in issues:
            report(code, **arguments)
    return result


# --- Git probe ---------------------------------------------------------------


def tracking_of(root, rels):
    """{rel: tracked|ignored|untracked|unavailable}. 읽기만 한다.

    자동 `git add`·`git rm --cached`·`.gitignore` 수정을 하지 않는다. Git 이 없거나 probe 가
    실패하면 `unavailable` 로 낮추고 조회는 계속한다 — 부가 정보 하나 때문에 감사를 못 보는
    것은 교환이 맞지 않는다.
    """
    result = {rel: "unavailable" for rel in rels}
    if not rels:
        return result
    try:
        tracked = subprocess.run(
            ["git", "-C", root, "ls-files", "-z", "--"] + list(rels),
            capture_output=True, timeout=GIT_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError):
        return result
    if tracked.returncode != 0:
        return result
    listed = {name for name in tracked.stdout.decode("utf-8", "replace").split("\0") if name}
    for rel in rels:
        result[rel] = "tracked" if rel in listed else "untracked"

    remaining = [rel for rel in rels if result[rel] == "untracked"]
    if not remaining:
        return result
    try:
        ignored = subprocess.run(
            ["git", "-C", root, "check-ignore", "-z", "--"] + remaining,
            capture_output=True, timeout=GIT_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError):
        return result
    # check-ignore 는 무시 대상이 하나도 없으면 1 로 끝난다. 실패가 아니다.
    if ignored.returncode not in (0, 1):
        return result
    for name in ignored.stdout.decode("utf-8", "replace").split("\0"):
        if name in result:
            result[name] = "ignored"
    return result
