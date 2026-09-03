"""POSIX 결속 구현 — 열린 부모 `dir_fd` 에 모든 변경을 묶는다.

이 파일의 내용은 `uninstall_executor` 에 있던 것을 **동작을 바꾸지 않고** 옮긴 것이다. 이사와
개선을 같은 변경에서 하면 POSIX 회귀가 났을 때 원인이 이사인지 개선인지 구분할 수 없다.

## 왜 경로를 다시 검사하지 않는가

검사와 작업 사이는 언제나 열려 있고, 그 창이 바로 외부 파일이 만들어지는 자리다. 부모를 fd 로
붙들면 이후 누가 상위 이름을 symlink 로 바꿔도 이 fd 를 통한 작업은 원래 디렉터리로 간다.
"""
import hashlib
import os
import stat

from sage import install_transaction as _tx
from sage import uninstall_fs as _fs


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


def probe_capability(roots=()):
    """POSIX 에서는 결속 기능이 곧 capability 다. 볼륨·파일시스템을 따로 묻지 않는다.

    묻지 않는 이유는 `dir_fd` 결속이 파일시스템 종류와 무관하게 커널이 보장하는 것이기
    때문이다. Windows 쪽이 볼륨을 묻는 것은 그 보장이 볼륨 구현에 달려 있어서다.
    """
    ok = _pinning_support()
    return _fs.MutationCapability(
        _fs.BACKEND_POSIX if ok else _fs.BACKEND_NONE,
        primitives={name: ok for name in _fs.PRIMITIVES},
        failure_code=None if ok else "uninstall.unsafe_platform")


def _lstat_at(dir_fd, name):
    """부모 fd 기준 `lstat`. **링크를 따라가지 않는다.**

    `os.lstat(name, dir_fd=...)` 대신 이 형태를 쓰는 이유는 위 `_pinning_support` 에 적었다 —
    capability 를 묻는 이름과 실제로 부르는 이름이 다르면 조건이 조용히 어긋난다.
    """
    return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)


def _descend(root_handle, root, path):
    """**이미 열린 root fd** 에서 성분을 하나씩 `O_NOFOLLOW` 로 열어 부모 fd 를 얻는다.

    두 가지를 동시에 한다. 여는 동안 성분 중 하나라도 symlink 면 실패하므로 **그 순간 경계가
    깨끗했다**는 것이 증명되고, 얻은 fd 는 그 디렉터리의 **inode 를 붙든다** — 이후 누가 상위
    이름을 symlink 로 바꿔도 이 fd 를 통한 작업은 원래 디렉터리로 간다.

    root 를 여기서 다시 열지 않는 것이 요점이다. 다시 열면 "확인한 root" 와 "쓰는 root" 가
    달라질 수 있고, 그 둘 사이가 그대로 경쟁 구간이다.

    실패하면 **이번 하강에서 연 중간 fd 를 역순으로 모두 닫는다.** 남기면 그 디렉터리를
    붙든 채 실패가 올라가고, 우리가 만든 장애가 된다. root fd 는 우리 것이 아니라 닫지 않는다.
    """
    parent = os.path.dirname(os.path.abspath(path))
    rel = os.path.relpath(parent, root)
    if rel == os.curdir:
        return root_handle, ()
    handle = root_handle
    opened = []
    try:
        for part in rel.split(os.sep):
            handle = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=handle)
            opened.append(handle)
    except BaseException:
        for extra in reversed(opened):
            try:
                os.close(extra)
            except OSError:
                pass
        raise
    return handle, tuple(opened)


def _fd_identity(handle):
    """열린 fd 가 가리키는 디렉터리의 기준. `uninstall_plan.root_fingerprint` 와 같은 형이다."""
    info = os.fstat(handle)
    return (_tx._kind(info.st_mode), stat.S_IMODE(info.st_mode), info.st_dev, info.st_ino)


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


def read_bytes_nofollow(path, dir_fd=None):
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


def write_new_file(path, body, mode, dir_fd=None):
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


class PosixBackend(_fs.MutationBackend):
    """모든 변경을 **첫 mutation 전에 열어 둔 부모 fd** 기준으로 수행한다.

    backup 은 원본과 같은 부모에 만들어지므로 rename·생성·삭제가 전부 한 디렉터리 안에서
    일어난다. 그래서 부모 하나만 붙들면 이 명령의 모든 변경이 결속된다.

    되돌리기도 같은 fd 를 쓴다. 되돌릴 때만 경로로 돌아가면, 실패한 순간이 곧 공격이 성립하는
    순간이 된다 — 되돌리기는 이미 무언가 잘못된 뒤에 도는 코드다.
    """

    name = _fs.BACKEND_POSIX

    def __init__(self, capability=None):
        self.capability = capability
        self.roots = {}
        self.parents = {}
        self._owned = []

    def open_roots(self, marks):
        for root, mark in sorted(marks.items()):
            base = os.path.abspath(root)
            if base in self.roots:
                continue
            handle = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
            try:
                if _fd_identity(handle) != mark:
                    # 계획을 세운 그 디렉터리가 아니다. 상대 경로는 새 root 안에서도
                    # 성립하므로, 여기서 멈추지 않으면 남의 디렉터리에서 지운다.
                    raise ValueError("uninstall.boundary_changed")
            except BaseException:
                os.close(handle)
                raise
            self.roots[base] = handle

    def _root_handle(self, root):
        base = os.path.abspath(root)
        handle = self.roots.get(base)
        if handle is None:
            # root 를 여기서 열면 확인한 root 와 쓰는 root 가 달라진다. 열지 않고 거부한다.
            raise _tx.InstallDriftError(f"root was never opened and verified: {base}")
        return handle

    def pin(self, root, path):
        parent = os.path.dirname(os.path.abspath(path))
        if parent in self.parents:
            return
        handle, owned = _descend(self._root_handle(root), os.path.abspath(root), path)
        self.parents[parent] = handle
        # 마지막 것만 부모로 쓴다. 중간 fd 를 열어 둔 채로 두면 그 디렉터리를 붙들고,
        # 그것은 다른 프로세스에게 우리가 만든 장애다.
        for extra in owned[:-1]:
            os.close(extra)
        if owned:
            self._owned.append(owned[-1])

    def pinned(self, path):
        return os.path.dirname(os.path.abspath(path)) in self.parents

    def close(self):
        """몇 번 불려도 안전해야 한다. 어떤 실패 경로에서도 반드시 불린다."""
        for handle in self._owned:
            try:
                os.close(handle)
            except OSError:
                pass
        self._owned.clear()
        self.parents.clear()
        for handle in self.roots.values():
            try:
                os.close(handle)
            except OSError:
                pass
        self.roots.clear()

    def _fd_for(self, path):
        return self.parents.get(os.path.dirname(os.path.abspath(path)))

    def replace(self, source, target):
        handle = self._fd_for(source)
        if handle is None or self._fd_for(target) != handle:
            # 경로 기준으로 되돌아가지 않는다. 그 길을 남겨 두면 조건 하나가 어긋나는 날
            # 조용히 그쪽으로 떨어지고, 그것이 정확히 이번에 겪은 일이다.
            raise _tx.InstallDriftError(f"unpinned parent for rename: {source}")
        os.rename(os.path.basename(source), os.path.basename(target),
                  src_dir_fd=handle, dst_dir_fd=handle)

    def remove_tree(self, path):
        handle = self._fd_for(path)
        if handle is None:
            raise _tx.InstallDriftError(f"unpinned parent for remove: {path}")
        _rmtree_at(handle, os.path.basename(path))
        return None

    def probe(self, path):
        handle = self._fd_for(path)
        try:
            _lstat_at(handle, os.path.basename(path))
        except (FileNotFoundError, NotADirectoryError):
            return False
        return True

    def measure(self, path, form):
        handle = self._fd_for(path)
        if not self.probe(path):
            return ("absent",) if form == "path" else ((".", ("absent",)),)
        name = os.path.basename(path)
        return (_tree_fingerprint_at(handle, name) if form == "tree"
                else _fingerprint_at(handle, name))

    def read_bytes(self, path):
        """대상을 부모 fd 기준으로 읽는다. leaf 도 이름도 따라가지 않는다."""
        handle = self._fd_for(path)
        return read_bytes_nofollow(os.path.basename(path), dir_fd=handle)

    def write_new(self, path, body, mode):
        """치워진 자리에 부모 fd 기준으로 새로 만든다.

        `O_EXCL` 은 마지막 성분이 이미 있으면 실패한다. `dir_fd` 는 **상위**가 바뀌어도 원래
        디렉터리 안에 만들게 한다. 둘이 함께 있어야 프로젝트 밖에 파일이 생기지 않는다.
        """
        handle = self._fd_for(path)
        return write_new_file(os.path.basename(path), body, mode, dir_fd=handle)

    def listdir(self, path):
        handle = self._fd_for(path)
        child = os.open(os.path.basename(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=handle)
        try:
            return os.listdir(child)
        finally:
            os.close(child)
