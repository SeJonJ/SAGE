"""승인된 계획만 실행하는 층.

## 왜 자기 프리미티브를 갖지 않는가

이 층은 lock 도 backup 도 지문도 **직접 만들지 않는다.** 전부 `install_transaction` 의 것을
쓴다. 처음에는 uninstall 전용으로 따로 만들었는데, 그것이 바로 이 사이클이 roster 에서 고쳤던
실수와 같은 모양이었다 — 같은 일을 하는 것이 두 벌이면 언젠가 갈라지고, 갈라진 뒤에는 아무도
모른다.

lock 에서는 갈라짐이 즉시 위험이다. `install` 이 `DestinationLock` 을 잡고 uninstall 이 자기
lock 파일을 잡으면, 둘은 서로를 **전혀 막지 못한 채** 각자 "잠갔다" 고 믿는다. 같은 destination
을 한쪽이 배치하는 동안 다른 쪽이 지운다. 그래서 공식 writer 는 모두 같은 권위를 통과한다.

## 왜 계획을 다시 읽지 않는가

이 층은 무엇을 지울지 **정하지 않는다.** 계획의 기준(`plan.baseline`) 에 없는 경로는 어떤
이유로도 열지 않는다. 실행 중에 대상을 추가할 수 있으면 "계획을 보여 주고 동의를 받는다" 는
계약이 무의미해진다 — 사용자가 동의한 것과 실제로 지운 것이 달라진다.

## 왜 옮기고 나서 지우는가

삭제는 되돌릴 수 없다. 그래서 실제로 하는 일은 **같은 부모 안의 사설 backup 으로 이동**이고,
마지막 검증까지 통과한 뒤에야 backup 을 버린다. 중간 어디서 실패해도 되돌릴 것이 디스크에
남아 있다.

`STRIP` 도 같은 방식이다. 원본을 먼저 옆으로 **치우고** 빈 자리에 새로 만든다. 경로에 대고
덮어쓰면 검사와 쓰기 사이에 leaf 가 symlink 로 바뀌었을 때 남의 파일을 고치게 되는데, 원본이
이미 치워진 자리에 `O_EXCL | O_NOFOLLOW` 로 만들면 그 창 자체가 없다 — 무엇이든 이미 있으면
만들기가 실패하기 때문이다.

## 왜 한 단위로 되돌리는가

`--all` 은 project 와 global 을 하나의 명령으로 다룬다. 한쪽만 커밋하면 사용자는 "절반 지워진"
상태를 손으로 수습해야 하고, 그 상태가 어떤 모양인지 문서에 적을 수도 없다. 그래서 journal 이
하나이고, 어느 scope 에서 실패하든 **양쪽을 함께** 되돌린다. 그 journal 은 첫 mutation 전에
양쪽 scope 를 모두 알고 있어야 한다 — 나중에 알게 되면 그때는 이미 한쪽을 건드린 뒤다.

## commit 과 cleanup 은 다른 일이다

`commit` 은 **되돌리지 않기로 정하는 순간**이다. 여기까지 오면 요청한 변경은 전부 적용되었고
검증도 끝났다. `cleanup` 은 그 뒤에 보관소를 치우는 뒷정리다.

둘을 한 단계로 묶으면 뒷정리 실패가 "명령 실패" 로 보고되는데, 그때 실제 디스크는 **요청대로
지워진 상태**다. 사용자는 실패했다고 듣고 다시 실행하고, 두 번째 실행은 이미 없는 것을 찾는다.
그래서 cleanup 실패는 결과를 바꾸지 않고 **남은 경로를 보고**한다.

## lock 은 왜 실행 층에만 있는가

lock 을 잡는 것은 **쓰기**다. `--check` 가 잠그면 읽기 전용 계약이 깨진다. 그래서 계획 층은
어떤 root 를 잠가야 하는지만 말하고(`plan.lock_roots()`), 실제로 잠그는 일은 여기서 한다.
"""
import hashlib
import os
import stat

from sage import install_transaction as _tx
from sage import uninstall_plan as _plan
from sage import uninstall_shared as _shared

# 기준을 뜨는 일은 **읽기**라 계획 층이 한다. 여기서는 이름만 다시 내보내 기존 호출자가 같은
# 함수를 보게 한다 — 구현이 두 벌이 되면 두 기준이 생긴다.
fingerprint = _plan.fingerprint


class RollbackFailed(Exception):
    """되돌리기까지 실패했다. 보존한 경로를 사용자에게 넘겨야 하는 유일한 경우."""

    def __init__(self, message, preserved_paths, reasons=()):
        super().__init__(message)
        self.preserved_paths = tuple(preserved_paths)
        # 왜 되돌리지 못했는지도 함께 든다. 경로만 주고 이유를 감추면, 사용자는 무엇을 어떻게
        # 수습해야 하는지 모른 채 디렉터리 하나를 받는다.
        self.reasons = tuple(reasons)


class ExecutionResult:
    """실행이 끝나고 남은 사실. 무엇을 처리했고 무엇을 못 치웠는가.

    `leftover_backups` 가 비어 있지 않아도 명령은 성공이다. 요청한 변경은 전부 적용되었고,
    남은 것은 우리가 만든 임시 보관소뿐이다 — 그 사실을 숨기지 않고 경로로 넘긴다.
    """

    __slots__ = ("processed", "leftover_backups")

    def __init__(self, processed, leftover_backups=()):
        self.processed = tuple(processed)
        self.leftover_backups = tuple(leftover_backups)

    def __iter__(self):
        """예전 호출자가 처리된 action 묶음으로 읽던 자리를 그대로 둔다."""
        return iter(self.processed)

    def __len__(self):
        return len(self.processed)


# --- 열린 부모에 결속하기 -----------------------------------------------------

def _pinning_support():
    """부모 fd 결속에 **실제로 쓰는 것**만 하나씩 묻는다.

    ## 왜 `os.lstat` 으로 묻지 않는가

    처음에는 `os.lstat in os.supports_dir_fd` 를 조건에 넣었다. 이것이 Python 버전을 탄다 —
    3.10·3.11 에서는 거짓이고 3.14 에서는 참이다. `os.lstat` 은 `os.stat(follow_symlinks=False)`
    의 얇은 껍데기라 capability 집합이 `os.stat` 쪽에만 이름을 싣기 때문이다.

    그 하나 때문에 지원 플랫폼에서 결속이 통째로 꺼졌고, 핵심 검사는 **통과가 아니라 skip**
    되었다. 개발 머신(3.14)에서만 참이었으므로 로컬은 초록이고 CI 세 버전은 전부 꺼진
    상태였다 — 조건 하나가 틀렸는데 그 사실을 아무도 볼 수 없는 모양이었다.

    그래서 이름이 아니라 **쓰는 기능**을 묻는다. `os.stat` 은 `dir_fd` 와 `follow_symlinks`
    양쪽에 있어야 하고(둘 다 있어야 `lstat` 의미가 나온다), 나머지는 각자 필요한 자리에서
    묻는다. 조건이 실제 호출과 하나씩 대응하면 이런 어긋남이 생기지 않는다.
    """
    if not (hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW")):
        return False
    if os.stat not in os.supports_dir_fd or os.stat not in os.supports_follow_symlinks:
        return False
    # POSIX 에서 `os.rename` 은 `os.replace` 와 같은 `renameat` 이고 둘 다 덮어쓴다. capability
    # 집합이 이름으로 `os.rename` 을 싣기 때문에 그쪽으로 묻는다.
    for function in (os.open, os.rename, os.unlink, os.rmdir, os.readlink):
        if function not in os.supports_dir_fd:
            return False
    return os.scandir in os.supports_fd and os.listdir in os.supports_fd


_PINNING = _pinning_support()


def _lstat_at(dir_fd, name):
    """부모 fd 기준 `lstat`. **링크를 따라가지 않는다.**

    `os.lstat(name, dir_fd=...)` 대신 이 형태를 쓰는 이유는 위 `_pinning_support` 에 적었다 —
    capability 를 묻는 이름과 실제로 부르는 이름이 다르면 조건이 조용히 어긋난다.
    """
    return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)


def _open_dir_chain(root, path):
    """`root` 아래 성분을 하나씩 `O_NOFOLLOW` 로 열어 `path` 의 부모 fd 를 얻는다.

    두 가지를 동시에 한다. 여는 동안 성분 중 하나라도 symlink 면 실패하므로 **그 순간 경계가
    깨끗했다**는 것이 증명되고, 얻은 fd 는 그 디렉터리의 **inode 를 붙든다** — 이후 누가 상위
    이름을 symlink 로 바꿔도 이 fd 를 통한 작업은 원래 디렉터리로 간다.

    경로를 다시 검사하는 방식으로는 이것을 얻을 수 없다. 검사와 작업 사이가 언제나 열려 있고,
    그 창이 바로 외부 파일이 만들어지는 자리다.
    """
    parent = os.path.dirname(os.path.abspath(path))
    rel = os.path.relpath(parent, root)
    handle = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    if rel == os.curdir:
        return handle
    try:
        for part in rel.split(os.sep):
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=handle)
            os.close(handle)
            handle = nxt
    except BaseException:
        os.close(handle)
        raise
    return handle


def _rmtree_at(dir_fd, name):
    """부모 fd 기준 재귀 삭제. 어느 단계에서도 이름을 따라가지 않는다."""
    try:
        info = _lstat_at(dir_fd, name)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(info.st_mode):
        os.unlink(name, dir_fd=dir_fd)
        return
    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        names = [entry.name for entry in os.scandir(child)]
        for entry in names:
            _rmtree_at(child, entry)
    finally:
        os.close(child)
    os.rmdir(name, dir_fd=dir_fd)


def _fingerprint_at(dir_fd, name):
    """`install_transaction.path_fingerprint` 와 **같은 값**을 부모 fd 기준으로 만든다.

    값이 같아야 하는 이유는 기록된 지문과 대조하기 때문이다. 그래서 계산 방식을 새로 정하지
    않고 그대로 옮긴다 — 여기서 달라지면 되돌리기가 언제나 "바뀌었다" 고 판단한다.
    """
    before = _lstat_at(dir_fd, name)
    mode = before.st_mode
    common = (_tx._kind(mode), stat.S_IMODE(mode), before.st_dev, before.st_ino)
    if stat.S_ISLNK(mode):
        return common + (os.readlink(name, dir_fd=dir_fd),)
    if not stat.S_ISREG(mode):
        return common
    digest = hashlib.sha256()
    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        while True:
            chunk = os.read(handle, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        opened = os.fstat(handle)
    finally:
        os.close(handle)
    after = _lstat_at(dir_fd, name)
    if ((before.st_dev, before.st_ino, before.st_mode, before.st_size,
         before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_mode, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
        raise _tx.InstallDriftError(
            _tx.Diagnostic("install.file_changed_during_fingerprint", path=name))
    return common + (before.st_size, digest.hexdigest())


def _tree_fingerprint_at(dir_fd, name):
    """부모 fd 기준 tree 지문. 디렉터리 symlink 를 따라가지 않는다."""
    root_fp = _fingerprint_at(dir_fd, name)
    if root_fp[0] != "dir":
        return ((".", root_fp),)
    entries = [(".", root_fp)]

    def walk(handle, relbase):
        names = sorted(entry.name for entry in os.scandir(handle))
        for child in names:
            rel = os.path.join(relbase, child) if relbase else child
            fp = _fingerprint_at(handle, child)
            entries.append((rel, fp))
            if fp[0] == "dir":
                nested = os.open(child, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                 dir_fd=handle)
                try:
                    walk(nested, rel)
                finally:
                    os.close(nested)

    top = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        walk(top, "")
    finally:
        os.close(top)
    return tuple(entries)


class _PinnedTransaction(_tx.InstallTransaction):
    """모든 변경을 **첫 mutation 전에 열어 둔 부모 fd** 기준으로 수행하는 journal.

    backup 은 원본과 같은 부모에 만들어지므로 rename·생성·삭제가 전부 한 디렉터리 안에서
    일어난다. 그래서 부모 하나만 붙들면 이 명령의 모든 변경이 결속된다.

    되돌리기도 같은 fd 를 쓴다. 되돌릴 때만 경로로 돌아가면, 실패한 순간이 곧 공격이 성립하는
    순간이 된다 — 되돌리기는 이미 무언가 잘못된 뒤에 도는 코드다.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parents = {}

    def pin(self, root, path):
        parent = os.path.dirname(os.path.abspath(path))
        if parent in self.parents:
            return
        self.parents[parent] = _open_dir_chain(root, path)

    def close(self):
        for handle in self.parents.values():
            try:
                os.close(handle)
            except OSError:
                pass
        self.parents.clear()

    def _fd_for(self, path):
        return self.parents.get(os.path.dirname(os.path.abspath(path)))

    def _replace(self, source, target):
        handle = self._fd_for(source)
        if handle is None or self._fd_for(target) != handle:
            # 경로 기준으로 되돌아가지 않는다. 그 길을 남겨 두면 조건 하나가 어긋나는 날
            # 조용히 그쪽으로 떨어지고, 그것이 정확히 이번에 겪은 일이다.
            raise _tx.InstallDriftError(f"unpinned parent for rename: {source}")
        os.rename(os.path.basename(source), os.path.basename(target),
                  src_dir_fd=handle, dst_dir_fd=handle)

    def _remove(self, path):
        handle = self._fd_for(path)
        if handle is None:
            raise _tx.InstallDriftError(f"unpinned parent for remove: {path}")
        _rmtree_at(handle, os.path.basename(path))
        return None

    def _probe(self, path):
        handle = self._fd_for(path)
        if handle is None:
            return super()._probe(path)
        try:
            _lstat_at(handle, os.path.basename(path))
        except (FileNotFoundError, NotADirectoryError):
            return False
        return True

    def _measure(self, path, form):
        handle = self._fd_for(path)
        if handle is None:
            return super()._measure(path, form)
        if not self._probe(path):
            return ("absent",) if form == "path" else ((".", ("absent",)),)
        name = os.path.basename(path)
        return (_tree_fingerprint_at(handle, name) if form == "tree"
                else _fingerprint_at(handle, name))

    def read_bytes(self, path):
        """대상을 부모 fd 기준으로 읽는다. leaf 도 이름도 따라가지 않는다."""
        handle = self._fd_for(path)
        if handle is None:
            return _read_bytes_nofollow(path)
        return _read_bytes_nofollow(os.path.basename(path), dir_fd=handle)

    def write_new(self, path, body, mode):
        """치워진 자리에 부모 fd 기준으로 새로 만든다.

        `O_EXCL` 은 마지막 성분이 이미 있으면 실패한다. `dir_fd` 는 **상위**가 바뀌어도 원래
        디렉터리 안에 만들게 한다. 둘이 함께 있어야 프로젝트 밖에 파일이 생기지 않는다.
        """
        handle = self._fd_for(path)
        if handle is None:
            return _write_new_file(path, body, mode)
        return _write_new_file(os.path.basename(path), body, mode, dir_fd=handle)

    def listdir(self, path):
        handle = self._fd_for(path)
        name = os.path.basename(path) if handle is not None else path
        if handle is None:
            return os.listdir(path)
        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=handle)
        try:
            return os.listdir(child)
        finally:
            os.close(child)


def _acquire_all(roots):
    """정렬된 순서로 전부 잡거나, 하나도 잡지 않는다.

    `install`·`generate` 와 **같은** `DestinationLock` 을 쓴다. 다른 lock 을 쓰면 두 명령이
    서로를 막지 못한 채 각자 잠갔다고 믿는다.

    중간에 실패하면 그때까지 잡은 것을 **역순으로** 놓는다. 절반 잡은 채 올라가면 그 lock 은
    아무도 놓지 않는다. 순서를 값으로 고정하는 것은 교착을 없애기 위해서다 — 두 실행이 서로
    다른 순서로 집으면 상대의 첫 lock 을 물고 영원히 기다린다.
    """
    held = []
    for root in sorted(roots):
        lock = _tx.DestinationLock(root)
        try:
            lock.acquire()
        except (_tx.InstallBusyError, _tx.InstallDriftError, OSError):
            for earlier in reversed(held):
                earlier.release()
            raise ValueError("uninstall.lock_busy")
        held.append(lock)
    return held


def _read_bytes_nofollow(path, dir_fd=None):
    """leaf 를 따라가지 않고 **bytes 로** 읽는다. 링크였다면 여는 순간 실패한다.

    여기서 decode 하지 않는 것이 요점이다. 실행 층이 자기 자리에서 `utf-8` 로 풀면 비 UTF-8
    파일 하나가 판정을 거치지 않은 예외로 올라오고, 그 예외는 이름이 없어 계약된 진단이 되지
    못한다. 판정은 `uninstall_shared` 하나가 한다 — 이 층은 바이트만 건넨다.
    """
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    handle = os.open(path, flags, dir_fd=dir_fd)
    try:
        if not stat.S_ISREG(os.fstat(handle).st_mode):
            raise OSError(f"not a regular file: {path}")
        chunks = []
        while True:
            chunk = os.read(handle, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(handle)
    return b"".join(chunks)


def _write_new_file(path, body, mode, dir_fd=None):
    """**비어 있는 자리에** 새로 만든다. 이미 무엇이 있으면 실패한다.

    `O_EXCL` 이 핵심이다. 원본은 이미 backup 으로 치워졌으므로 이 자리는 비어 있어야 하고,
    비어 있지 않다면 누군가 그 사이에 무엇을 놓은 것이다 — symlink 일 수 있으므로 따라가지
    않고 멈춘다. 경로에 대고 덮어쓰는 방식에는 이 보장이 없다.
    """
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    payload = body.encode("utf-8")
    handle = os.open(path, flags, mode, dir_fd=dir_fd)
    complete = False
    try:
        # `os.write` 는 **요청한 만큼 쓴다고 보장하지 않는다.** 한 번 부르고 반환값을 버리면
        # 잘려 쓰인 파일이 정상으로 통과한다 — 그 파일이 사용자의 `.gitignore` 나 host 설정
        # 이라면 우리가 남긴 것은 남의 데이터를 자른 결과다. 다 쓸 때까지 반복하고, 마지막에
        # 실제 크기까지 확인한다.
        written = 0
        while written < len(payload):
            count = os.write(handle, payload[written:])
            if count <= 0:
                raise OSError(f"short write: {written}/{len(payload)} bytes to {path}")
            written += count
        if written != len(payload):
            raise OSError(f"short write: {written}/{len(payload)} bytes to {path}")
        os.fsync(handle)
        if os.fstat(handle).st_size != len(payload):
            raise OSError(f"size mismatch after write: {path}")
        if hasattr(os, "fchmod"):
            os.fchmod(handle, mode)
        complete = True
    finally:
        os.close(handle)
        if not complete:
            # **반쯤 쓰인 파일을 남기면 되돌리기가 거부된다.** journal 의 rollback 은 대상
            # 자리에 자기가 모르는 파일이 있으면 "동시 변경" 으로 보고 backup 복원을 멈춘다 —
            # 안전한 기본값이지만, 여기서는 그 낯선 파일이 바로 우리가 방금 만든 잘린 파일이다.
            # 그대로 두면 사용자의 `.gitignore` 는 잘린 채 끝나고 원본은 숨은 backup 에 갇힌다.
            # `O_EXCL` 로 만들었으니 이 자리는 우리 것이고, 만든 쪽이 치우는 것이 맞다.
            try:
                os.unlink(path, dir_fd=dir_fd)
            except OSError:
                pass
    if not hasattr(os, "fchmod"):
        os.chmod(path, mode, dir_fd=dir_fd) if dir_fd is not None else os.chmod(path, mode)


def _strip_outcome(path, raw, sage_commands, host=None):
    """공유 파일 bytes 하나의 판정. **계획 층과 글자 그대로 같은 함수를 부른다.**

    실행 층이 자기 파서를 들면 계획이 "뺄 수 있다" 고 판정한 문서를 실행이 다르게 읽는 날이
    오고, 그날 화면은 "제거했다" 고 말하는데 파일은 그대로다.
    """
    if path.endswith(".gitignore"):
        return _shared.classify_gitignore_bytes(raw)
    return _shared.classify_host_bytes(raw, sage_commands, host)


def _strip_file(path, sage_commands):
    """검증용 — 지금 파일에 아직 뺄 것이 남았는가."""
    return _strip_outcome(path, _read_bytes_nofollow(path), sage_commands, _host_of(path))


def _host_of(path):
    return "codex" if path.endswith("hooks.json") else "claude"


def execute(plan, environ=None, trace=None):
    """계획을 실행하고 `ExecutionResult` 를 돌려준다.

    실패하면 되돌린 뒤 예외를 올린다. 되돌리기까지 실패하면 `RollbackFailed` 로 보존 경로를
    함께 넘긴다 — 그때 사용자에게 줄 수 있는 유일하게 정직한 것은 "여기 있다" 는 사실이다.

    ## 단계 순서가 계약이다

    ```
    lock → fingerprint → prepare → recheck → backup → verify → commit → cleanup → unlock
    ```

    `lock` 이 맨 앞인 이유는 그 뒤 모든 검사가 **잠긴 상태에서** 이뤄져야 의미가 있기 때문이다.
    잠그기 전에 확인하면 확인과 쓰기 사이가 그대로 경쟁 구간으로 남는다. `prepare` 는 첫
    mutation 전에 **양쪽 scope** 의 journal 과 경계를 세우는 자리다. `recheck` 는 계획을 잠그기
    전에 세웠기 때문에 있다 — 후보를 열기 직전에 경계를 다시 본다.

    `trace` 는 검사가 단계 **순서**를 읽기 위한 자리다. 순서가 계약인데 그 순서를 밖에서
    확인할 수 없으면, 구현이 순서를 바꿔도 아무도 모른다.
    """
    def step(name):
        if trace is not None:
            trace.append(name)

    # 부모 fd 결속이 없는 플랫폼에서는 **아무것도 바꾸지 않는다.** 이 명령은 상위 디렉터리
    # 교체만으로 프로젝트 밖 파일을 만들 수 있고, 그 위험은 "알려진 한계" 로 넘길 성질이
    # 아니다 — 되돌릴 수 없는 쪽으로 틀리는 명령이기 때문이다. 계획(`--check`)은 읽기라
    # 그대로 동작하므로 사용자는 무엇이 지워질지 볼 수 있다.
    if not _PINNING:
        raise ValueError("uninstall.unsafe_platform")

    # 같은 경로를 두 번 주장하는 계획은 실행하지 않는다. 계획 층이 이미 막지만, 그 검사가
    # 언젠가 다른 분기를 놓치면 여기서 잡혀야 한다 — **lock 도 잡기 전, mutation 전**이다.
    # 중복은 "지운다" 와 "보존한다" 가 같은 파일에 대해 동시에 참이라는 뜻이고, 그 상태에서
    # 실행하면 보존한다고 보고한 파일을 지운다.
    if _plan.conflicting_actions(plan.actions):
        raise ValueError("uninstall.action_conflict")

    step("lock")
    locks = _acquire_all(plan.lock_roots())
    try:
        return _execute_locked(plan, step)
    finally:
        step("unlock")
        for lock in reversed(locks):
            lock.release()


def _execute_locked(plan, step):
    # 승인된 대상은 **계획이 만들어질 때 뜬 기준**이다. 실행 직전에 다시 뜨면 그 사이에 바뀐
    # 것을 기준으로 삼게 되어, 확인 화면이 열려 있는 동안 사용자가 고친 파일이 그대로 지워진다.
    step("fingerprint")
    expected = plan.baseline
    approved = set(expected)
    findings = _tx.verify_captured(expected)
    if findings:
        raise ValueError("uninstall.fingerprint_changed")

    # journal 하나가 양쪽 scope 를 다룬다. write root 를 **첫 mutation 전에** 모두 넘기는 것이
    # 요점이다 — 나중에 알려 주면 그때는 이미 한쪽을 건드린 뒤라, 되돌릴 범위가 반쪽이다.
    step("prepare")
    roots = plan.lock_roots()
    pending = [action for action in plan.actions
               if action.kind in (_plan.DELETE, _plan.STRIP)]
    # journal 의 단계별 재검증에서 **빈 부모 정리 대상은 뺀다.** 그 디렉터리들은 우리가
    # 자식을 지우면서 스스로 바뀌므로, 넣어 두면 매 단계 "계획 이후 바뀌었다" 고 스스로를
    # 고발한다. 이들의 기준은 위 `fingerprint` 단계에서 이미 한 번 대조했고, 실제로 비었는지는
    # 지우기 직전에 다시 본다 — 그 둘이 이 대상에 필요한 전부다.
    prune_paths = {a.path for a in pending if a.group == "prune"}
    journal = _PinnedTransaction(
        expected={path: mark for path, mark in expected.items() if path not in prune_paths},
        write_roots=roots)
    try:
        for action in pending:
            if action.path not in approved:
                # 계획 밖 경로. 여기 오면 실행 층이 스스로 대상을 늘린 것이다.
                raise ValueError("uninstall.target_outside_plan")
            journal._guard_path(action.path)
            collision = journal._backup_path(action.path)
            if os.path.lexists(collision):
                raise ValueError("uninstall.backup_collision")
            # 부모를 **여기서** 붙든다. 첫 mutation 전에 전부 열어 두므로, 그 뒤 상위 이름이
            # 어떻게 바뀌든 우리의 모든 작업은 지금 확인한 그 디렉터리로 간다.
            journal.pin(plan.root_for(action), action.path)
    except OSError as exc:
        journal.close()
        raise ValueError("uninstall.boundary_changed") from exc
    except BaseException:
        # `Exception` 만 잡으면 Ctrl-C 가 여기를 그냥 지나간다. 사용자가 취소한 것뿐인데
        # 열어 둔 fd 가 남는다.
        journal.close()
        raise

    processed = []
    committed = False
    try:
      try:
        for action in pending:
            # 계획은 잠그기 **전에** 세웠다. 그 사이에 경계가 바뀌었으면 지금 여는 경로는
            # 우리가 판정한 그 경로가 아니다. 열기 직전에 다시 본다.
            step("recheck")
            blocked = _plan.candidate_block(plan.root_for(action), action.path,
                                            following=(action.kind == _plan.STRIP))
            if blocked:
                raise ValueError("uninstall.boundary_changed")

            step("backup")
            if action.kind == _plan.DELETE:
                if action.group == "prune":
                    # 계획은 예상이었다. 실행 시점에 무엇이 남아 있으면 정리하지 않는다 —
                    # 그 사이에 사용자가 파일을 놓았을 수 있고, 그건 우리 것이 아니다.
                    if not _effectively_empty(journal, action.path):
                        journal._expected.pop(action.path, None)
                        continue
                if not journal.stage_remove_tree(action.path):
                    journal._expected.pop(action.path, None)
                    continue
            else:
                host = _host_of(action.path)
                outcome = _strip_outcome(action.path, journal.read_bytes(action.path),
                                         _plan.canonical_commands(host), host)
                if not outcome.strippable:
                    # 계획은 뺄 수 있다고 판정했는데 지금은 아니다. 조용히 넘기면 화면은
                    # "제거했다" 고 말하고 파일은 그대로다 — 하지 않은 일을 했다고 보고하는 것이
                    # 이 명령이 절대 하면 안 되는 일이다. 계획과 디스크가 어긋났으니 멈추고,
                    # 여기까지 한 것을 **전부 되돌린다.**
                    raise ValueError("uninstall.strip_not_applicable")
                body = outcome.body
                mode = stat.S_IMODE(os.lstat(action.path).st_mode)
                # 원본을 먼저 치우고 빈 자리에 만든다. 경로에 덮어쓰지 않으므로 leaf 가
                # 그 사이 symlink 로 바뀌어도 따라갈 대상이 없다.
                journal.stage_write(action.path)
                journal.write_new(action.path, body, mode)
                journal.record_output(action.path)
            processed.append(action)

        step("verify")
        for action in processed:
            if action.kind == _plan.DELETE and os.path.lexists(action.path):
                raise ValueError("uninstall.delete_not_effective")
            if action.kind == _plan.STRIP:
                # STRIP 은 파일이 남는 것이 정상이라 존재만으로는 아무것도 확인되지 않는다.
                # 우리가 뺀 것이 정말 빠졌는지 다시 읽는다 — 쓰고 나서 확인하지 않으면
                # "썼다" 와 "의도대로 됐다" 가 같은 말이 된다.
                host = _host_of(action.path)
                leftover = _strip_outcome(action.path, journal.read_bytes(action.path),
                                          _plan.canonical_commands(host), host)
                if leftover.strippable or leftover.damage:
                    raise ValueError("uninstall.strip_not_effective")
        journal.verify_outputs()

        # 여기가 되돌리지 않기로 정하는 지점이다. 이 뒤에 무엇이 실패해도 사용자가 요청한
        # 변경은 이미 전부 적용되었고 검증도 끝났다.
        step("commit")
        committed = True
      except BaseException:
        # **`BaseException` 이어야 한다.** `Exception` 만 잡으면 Ctrl-C(`KeyboardInterrupt`)가
        # rollback 을 통째로 건너뛴다. 그때 디스크에는 원본이 사라진 자리와 숨은 backup 만
        # 남는다 — 취소는 정상적인 사용자 행동이고, 정상적인 행동이 원자성을 깨면 그 계약은
        # 없는 것이다.
        if committed:
            raise
        step("rollback")
        errors = journal.rollback()
        if errors:
            raise RollbackFailed("uninstall.rollback_failed",
                                 [journal._backup_path(a.path) for a in pending],
                                 errors) from None
        raise
    except BaseException:
        journal.close()
        raise

    step("cleanup")
    try:
        return ExecutionResult(processed, _cleanup(journal))
    finally:
        journal.close()


def _effectively_empty(journal, path):
    """지금 비어 있는가. **우리가 방금 옆으로 치운 것은 없는 것으로 센다.**

    backup 은 원본과 **같은 부모**에 만들어진다(그래야 이동이 원자적이다). 그래서 자식을 치운
    직후의 부모에는 그 backup 이 남아 있고, 그것을 남의 파일로 세면 부모는 영원히 "비지 않은"
    상태가 된다 — 우리가 만든 흔적 때문에 우리가 정리를 못 한다.

    남이 놓은 것은 그대로 센다. 구별의 근거는 이 실행의 token 이고, 다른 실행의 backup 은
    다른 token 을 갖는다.
    """
    if not os.path.isdir(path) or os.path.islink(path):
        return False
    ours = f".sage-install-backup-{journal._token}-"
    return not [name for name in journal.listdir(path) if not name.startswith(ours)]


def _cleanup(journal):
    """보관소를 치우고, **못 치운 실제 경로**를 돌려준다.

    commit 뒤의 실패는 명령 실패가 아니다 — 요청한 변경은 이미 적용됐다. 그렇다고 예외를
    삼키고 빈 목록을 내면 안 된다. 그러면 디스크에는 backup 이 남았는데 화면에는 아무것도
    남지 않았다고 나오고, 사용자는 치울 것이 있다는 사실조차 모른다. **숨기는 것과 실패로
    올리는 것은 둘 다 틀렸고**, 옳은 것은 결과를 유지한 채 경로를 그대로 말하는 것뿐이다.
    """
    try:
        errors = list(journal.commit())
    except BaseException:
        # commit 자체가 터졌으면 journal 이 아는 backup 을 우리가 직접 센다.
        journal._committed = True
        errors = []
    leftover = []
    for path, backup in journal._entries:
        if backup is None:
            continue
        if os.path.lexists(backup) and backup not in leftover:
            leftover.append(backup)
    for note in errors:
        # commit 이 문자열로 보고한 것 중 위에서 못 본 것도 함께 낸다.
        name = note.split(":", 1)[0]
        if name and name not in leftover and os.path.lexists(name):
            leftover.append(name)
    return tuple(leftover)
