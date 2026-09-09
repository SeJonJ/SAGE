"""Failure-atomic filesystem primitives for ``sage install``.

The journal preserves existing filesystem objects by moving them to a private
same-parent backup before the first mutation. This keeps modes, symlinks,
hard-link identity, and directory trees intact for rollback.
"""

import hashlib
import os
import shutil
import stat
import tempfile
import unicodedata
import uuid

from sage.diagnostics import Diagnostic


class _DiagnosticError(RuntimeError):
    """진단을 실어 나르는 예외의 공통 형태.

    이 모듈은 install·generate·upgrade 가 모두 쓰는 하부 계층이라 어느 도메인의 catalog 도 알
    수 없다. 그래서 완성 문장 대신 code 를 들고 올라가고, 문장은 잡은 쪽이 만든다.

    `str(exc)` 는 code 와 evidence 를 낸다 — 사람이 읽는 문장은 아니지만, 이 예외를 그대로
    찍던 경로에서도 정보가 사라지지 않는다.
    """

    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        detail = getattr(diagnostic, "evidence", "")
        code = getattr(diagnostic, "code", str(diagnostic))
        super().__init__(f"{code}: {detail}" if detail else code)


class InstallBusyError(_DiagnosticError):
    pass


class InstallDriftError(_DiagnosticError):
    pass


def _kind(mode):
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "dir"
    if stat.S_ISLNK(mode):
        return "symlink"
    return f"special:{stat.S_IFMT(mode):o}"


def path_fingerprint(path):
    """Return a deterministic lstat/content fingerprint without following symlinks."""
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        return ("absent",)
    mode = before.st_mode
    common = (_kind(mode), stat.S_IMODE(mode), before.st_dev, before.st_ino)
    if stat.S_ISLNK(mode):
        return common + (os.readlink(path),)
    if not stat.S_ISREG(mode):
        return common
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        opened = os.fstat(stream.fileno())
    after = os.lstat(path)
    if ((before.st_dev, before.st_ino, before.st_mode, before.st_size,
         before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_mode, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
        raise InstallDriftError(Diagnostic("install.file_changed_during_fingerprint", path=path))
    return common + (before.st_size, digest.hexdigest())


def file_semantic_fingerprint(path):
    """Fingerprint regular-file bytes and mode without depending on inode identity."""
    current = os.lstat(path)
    if not stat.S_ISREG(current.st_mode):
        return (_kind(current.st_mode), stat.S_IMODE(current.st_mode))
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return ("file", stat.S_IMODE(current.st_mode), current.st_size, digest.hexdigest())


def tree_fingerprint(path):
    """Fingerprint a tree inventory without traversing directory symlinks."""
    root = os.path.abspath(path)
    root_fp = path_fingerprint(root)
    if root_fp[0] != "dir":
        return ((".", root_fp),)
    entries = [(".", root_fp)]

    def walk(directory, relbase):
        with os.scandir(directory) as iterator:
            children = sorted(iterator, key=lambda item: item.name)
        for child in children:
            rel = os.path.join(relbase, child.name) if relbase else child.name
            fp = path_fingerprint(child.path)
            entries.append((rel, fp))
            if fp[0] == "dir":
                walk(child.path, rel)

    walk(root, "")
    return tuple(entries)


def capture_paths(paths, recursive=()):
    recursive = {os.path.abspath(path) for path in recursive}
    return {
        os.path.abspath(path): ("tree", tree_fingerprint(path))
        if os.path.abspath(path) in recursive else ("path", path_fingerprint(path))
        for path in paths
    }


def verify_captured(captured):
    findings = []
    for path, (form, expected) in sorted(captured.items()):
        try:
            actual = tree_fingerprint(path) if form == "tree" else path_fingerprint(path)
        except (OSError, InstallDriftError) as exc:
            findings.append(Diagnostic("install.path_unreadable", path=path,
                                       evidence=str(exc)))
            continue
        if actual != expected:
            findings.append(Diagnostic("install.input_changed_since_preflight", path=path))
    return findings


class DestinationLock:
    """Non-blocking process lock scoped by the absolute install destination."""

    def __init__(self, destination):
        absolute = os.path.abspath(destination)
        canonical = unicodedata.normalize("NFC", os.path.realpath(absolute)).casefold()
        self.destination = absolute
        self._canonical = canonical
        identities = {f"path:{canonical}"}
        try:
            current = os.stat(absolute)
            identities.add(f"inode:{current.st_dev}:{current.st_ino}")
        except OSError:
            pass
        uid = os.geteuid() if hasattr(os, "geteuid") else None
        lock_name = "sage-install-locks" if uid is None else f"sage-install-locks-{uid}"
        lock_root = os.path.join(tempfile.gettempdir(), lock_name)
        self.lock_root = lock_root
        self.paths = tuple(sorted(
            os.path.join(lock_root, hashlib.sha256(identity.encode("utf-8")).hexdigest() + ".lock")
            for identity in identities))
        self.path = next(path for path in self.paths
                         if hashlib.sha256(f"path:{canonical}".encode("utf-8")).hexdigest() in path)
        self._locks = []

    def _prepare_lock_root(self):
        try:
            os.mkdir(self.lock_root, 0o700)
        except FileExistsError:
            pass
        current = os.lstat(self.lock_root)
        if not stat.S_ISDIR(current.st_mode) or stat.S_ISLNK(current.st_mode):
            raise InstallBusyError(Diagnostic("install.lock_root_unsafe", path=self.lock_root))
        if hasattr(os, "geteuid") and current.st_uid != os.geteuid():
            raise InstallBusyError(Diagnostic("install.lock_root_foreign_owner", path=self.lock_root))
        if os.name != "nt" and stat.S_IMODE(current.st_mode) & 0o077:
            raise InstallBusyError(Diagnostic("install.lock_root_permissive", path=self.lock_root))

    def verify_identity(self):
        current = unicodedata.normalize(
            "NFC", os.path.realpath(self.destination)).casefold()
        if current != self._canonical:
            raise InstallDriftError(
                f"install destination identity changed while acquiring lock: {self.destination}")

    def _acquire_one(self, path):
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                backend = "msvcrt"
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                backend = "fcntl"
            os.ftruncate(fd, 0)
            os.write(fd, f"pid={os.getpid()}\n".encode("ascii"))
        except (ImportError, OSError) as exc:
            os.close(fd)
            raise InstallBusyError(Diagnostic("install.destination_busy")) from exc
        self._locks.append((fd, backend))

    def acquire(self):
        self._prepare_lock_root()
        try:
            for path in self.paths:
                self._acquire_one(path)
            self.verify_identity()
        except BaseException:
            self.release()
            raise

    def release(self):
        while self._locks:
            fd, backend = self._locks.pop()
            try:
                if backend == "msvcrt":
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


class InstallTransaction:
    """Rollback journal for project and optional global install mutations."""

    def __init__(self, expected=None, write_roots=()):
        self._expected = dict(expected or {})
        self._initial_expected = dict(self._expected)
        self._write_roots = tuple(sorted(
            {os.path.abspath(os.fspath(root)) for root in write_roots},
            key=len, reverse=True))
        self._entries = []
        self._staged = {}
        self._created_dirs = []
        self._outputs = {}
        self._declared_outputs = {}
        self._originals = {}
        self._token = uuid.uuid4().hex
        self._committed = False

    @property
    def committed(self):
        return self._committed

    def _guard_path(self, path):
        """Reject writes that escape a declared root or traverse a symlink ancestor.

        **두 검사는 성격이 다르다.** 소속 판정은 문자열만 보고, 조상 판정은 파일시스템을
        읽는다. 부모를 이미 붙든 소비자에게는 두 번째가 계약 위반이다 — 붙든 대상을 절대
        경로로 다시 물으면, 상위가 바뀐 순간 그 답이 다른 디렉터리에 대해 나온다. 그래서
        나눠 두고, 조상 판정만 갈아 끼울 수 있게 한다.
        """
        root = self._guard_root_membership(path)
        if root is not None:
            self._guard_ancestors(root, path)

    def _guard_root_membership(self, path):
        """선언한 root 안인가. **문자열만 본다** — 파일시스템을 읽지 않는다."""
        if not self._write_roots:
            return None
        target = os.path.abspath(path)
        for candidate in self._write_roots:
            try:
                if os.path.commonpath((candidate, target)) == candidate:
                    return candidate
            except ValueError:
                continue
        raise InstallDriftError(f"install write path is outside declared roots: {target}")

    def _guard_ancestors(self, root, path):
        """조상이 symlink 가 아니고 디렉터리인가. **파일시스템을 읽는다.**

        경로 기준이라, 부모를 붙든 소비자는 이 판정을 결속된 seam 으로 갈아 끼운다.
        """
        target = os.path.abspath(path)
        cursor = root
        parent = os.path.dirname(target)
        rel_parent = os.path.relpath(parent, root)
        parts = () if rel_parent == "." else rel_parent.split(os.sep)
        for part in parts:
            cursor = os.path.join(cursor, part)
            try:
                mode = os.lstat(cursor).st_mode
            except FileNotFoundError:
                break
            if stat.S_ISLNK(mode):
                raise InstallDriftError(f"install write ancestor is a symlink: {cursor}")
            if not stat.S_ISDIR(mode):
                raise InstallDriftError(f"install write ancestor is not a directory: {cursor}")

    def _actual(self, path, expected):
        form, _value = expected
        return self._measure(path, form)

    def verify_unconsumed(self):
        findings = []
        for path, expected in sorted(self._expected.items()):
            try:
                actual = self._actual(path, expected)
            except (OSError, InstallDriftError) as exc:
                findings.append(Diagnostic("install.path_unreadable", path=path,
                                           evidence=str(exc)))
                continue
            if actual != expected[1]:
                findings.append(Diagnostic("install.output_changed_since_preflight", path=path))
        if findings:
            raise InstallDriftError(Diagnostic(
                "install.inputs_changed_during_preflight",
                evidence="; ".join(str(item) for item in findings)))

    def _ensure_parents(self, path):
        missing = []
        cursor = os.path.dirname(path) or "."
        while cursor and not os.path.lexists(cursor):
            missing.append(cursor)
            parent = os.path.dirname(cursor)
            if parent == cursor:
                break
            cursor = parent
        for directory in reversed(missing):
            self._created_dirs.append(directory)
            try:
                os.mkdir(directory)
            except FileExistsError:
                self._created_dirs.remove(directory)
                raise

    def _backup_path(self, path):
        parent = os.path.dirname(path) or "."
        name = os.path.basename(path)
        return os.path.join(parent, f".sage-install-backup-{self._token}-{name}")

    def stage_write(self, path):
        path = os.path.abspath(path)
        if path in self._staged:
            output = self._outputs.get(path)
            if output is None:
                raise InstallDriftError(f"staged path has no recorded installer output: {path}")
            form, expected = output
            if self._measure(path, form) != expected:
                raise InstallDriftError(f"staged installer output changed before rewrite: {path}")
            return
        self.verify_unconsumed()
        self._guard_path(path)
        self._ensure_parents(path)
        # 존재 여부와 종류를 **지문 하나에서** 읽는다. `os.path.lexists` 와 `os.lstat` 은
        # 절대 경로를 다시 조회하므로, 부모를 붙든 소비자에서도 그 두 줄만 결속 밖으로
        # 빠져나간다 — 상위가 바뀐 뒤에는 다른 디렉터리에 대해 "있다/없다" 를 답한다.
        original = ("path", self._measure(path, "path"))
        existed = original[1][0] != "absent"
        if existed and original[1][0] == "dir":
            raise IsADirectoryError(path)
        backup = self._backup_path(path) if existed else None
        if backup is not None and self._probe(backup):
            raise FileExistsError(f"transaction backup collision: {backup}")
        entry = (path, backup)
        self._entries.append(entry)
        self._staged[path] = entry
        self._originals[path] = original
        self._expected.pop(path, None)
        if backup is not None:
            self._replace(path, backup)
            if self._measure(backup, "path") != original[1]:
                raise InstallDriftError(f"install input changed during backup rename: {path}")

    def stage_remove_tree(self, path):
        path = os.path.abspath(path)
        # `_probe` 로 묻는다. 절대 경로로 물으면 붙든 대상이 멀쩡히 있는데도 상위가 바뀐
        # 것만으로 "없다" 가 나오고, 그러면 지워야 할 것을 지우지 않은 채 성공으로 끝난다.
        if path in self._staged or not self._probe(path):
            return False
        self.verify_unconsumed()
        self._guard_path(path)
        backup = self._backup_path(path)
        if self._probe(backup):
            raise FileExistsError(f"transaction backup collision: {backup}")
        original = ("tree", self._measure(path, "tree"))
        entry = (path, backup)
        self._entries.append(entry)
        self._staged[path] = entry
        self._originals[path] = original
        self._expected.pop(path, None)
        self._replace(path, backup)
        if self._measure(backup, "tree") != original[1]:
            raise InstallDriftError(f"install input tree changed during backup rename: {path}")
        self._outputs[path] = ("path", ("absent",))
        return True

    def declare_file_output(self, path, content, mode):
        path = os.path.abspath(path)
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        self._declared_outputs[path] = (
            "file", mode, len(data), hashlib.sha256(data).hexdigest())

    @staticmethod
    def _matches_declared_file(path, declared):
        actual = file_semantic_fingerprint(path)
        if declared[1] is None:
            return actual[0] == "file" and actual[2:] == declared[2:]
        return actual == declared

    def record_output(self, path, recursive=False):
        path = os.path.abspath(path)
        form = "tree" if recursive else "path"
        self._outputs[path] = (form, self._measure(path, form))

    def verify_outputs(self):
        findings = []
        for path, (form, expected) in sorted(self._outputs.items()):
            try:
                actual = self._measure(path, form)
            except (OSError, InstallDriftError) as exc:
                findings.append(Diagnostic("install.path_unreadable", path=path,
                                           evidence=str(exc)))
                continue
            if actual != expected:
                findings.append(Diagnostic("install.input_changed_since_preflight", path=path))
        if findings:
            raise InstallDriftError(Diagnostic(
                "install.outputs_changed_before_commit",
                evidence="; ".join(str(item) for item in findings)))

    def _probe(self, path):
        """`path` 자리에 무언가 있는가. 소비자가 해석 방식을 바꿀 수 있게 seam 으로 둔다."""
        return os.path.lexists(path)

    def _measure(self, path, form):
        """`path` 의 지문. `form` 은 `"tree"` 또는 `"path"`."""
        return tree_fingerprint(path) if form == "tree" else path_fingerprint(path)

    def _replace(self, source, target):
        """이름 하나를 다른 이름으로 옮긴다.

        여기 seam 이 있는 이유는, 소비자에 따라 **경로가 아니라 열린 부모 handle 기준**으로
        옮겨야 하기 때문이다. 경로로 옮기면 상위 디렉터리가 그 사이 symlink 로 바뀌었을 때
        전혀 다른 자리로 옮기게 되고, `O_NOFOLLOW` 는 마지막 성분만 보므로 그것을 막지 못한다.
        기본 구현은 경로 기준이고 install 의 동작은 그대로다.
        """
        os.replace(source, target)

    def _remove(self, path):
        if not os.path.lexists(path):
            return
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.unlink(path)

    def _rollback_entry(self, path, backup):
        output = self._outputs.get(path)
        declared = self._declared_outputs.get(path)
        original = self._originals.get(path)
        backup_required = backup is not None
        if backup_required and not self._probe(backup):
            if original is not None and self._probe(path):
                form, expected = original
                actual = self._measure(path, form)
                if actual == expected:
                    return
            raise InstallDriftError(
                f"transaction backup missing; current path preserved for recovery: {backup}")

        if self._probe(path):
            if output is None:
                if declared is None or not self._matches_declared_file(path, declared):
                    raise InstallDriftError(
                        f"unrecorded/concurrent path preserved; backup not restored: {path}")
            else:
                form, expected = output
                actual = self._measure(path, form)
                if actual != expected and (declared is None
                                           or not self._matches_declared_file(path, declared)):
                    raise InstallDriftError(
                        f"concurrent path mutation preserved; backup not restored: {path}")
            self._remove(path)

        if backup_required:
            self._replace(backup, path)

    def rollback(self):
        errors = []
        for path, backup in reversed(self._entries):
            try:
                self._rollback_entry(path, backup)
            except (OSError, InstallDriftError) as exc:
                errors.append(f"{path}: {exc}")
        for directory in list(reversed(self._created_dirs)):
            try:
                os.rmdir(directory)
            except FileNotFoundError:
                pass
            except OSError:
                # Existing/untracked children make the directory non-empty; preserve it.
                pass
        return errors

    def restore_path(self, path):
        """Undo one staged path for a deliberately non-fatal optional write."""
        path = os.path.abspath(path)
        entry = self._staged.pop(path, None)
        if entry is None:
            return
        _path, backup = entry
        self._rollback_entry(path, backup)
        self._entries.remove(entry)
        self._outputs.pop(path, None)
        self._declared_outputs.pop(path, None)
        self._originals.pop(path, None)
        if path in self._initial_expected:
            self._expected[path] = self._initial_expected[path]
        for directory in list(reversed(self._created_dirs)):
            try:
                os.rmdir(directory)
                self._created_dirs.remove(directory)
            except (FileNotFoundError, OSError):
                pass

    def commit(self):
        # All install outputs are final at this point. Backup removal is post-commit GC;
        # an interrupt may leave residue, but must never trigger a partial rollback.
        self._committed = True
        errors = []
        for _path, backup in self._entries:
            if backup is None:
                continue
            try:
                self._remove(backup)
            except OSError as exc:
                errors.append(f"{backup}: {exc}")
        return errors
