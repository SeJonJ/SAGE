"""Keep Codex global install mutations reversible across an upgrade's steps.

Project assets retain their command-local transactions and upgrade snapshot.
Only the global installer uses this scoped journal; project overlays never do.
"""

from contextvars import ContextVar
import os
import stat

from sage.install_transaction import (
    DestinationLock, InstallDriftError, InstallTransaction, path_fingerprint,
)


_ACTIVE = ContextVar("sage_global_upgrade", default=None)


def active_global_upgrade():
    return _ACTIVE.get()


def _within(root, path):
    try:
        return os.path.commonpath((root, path)) == root
    except ValueError:  # separate drives on Windows
        return False


class GlobalRollbackError(RuntimeError):
    def __init__(self, problems):
        self.problems = problems
        super().__init__("; ".join(problems))


class _GlobalTransaction(InstallTransaction):
    """Refuse recovery through replaced parents, retaining backups for recovery."""

    def __init__(self, lock, **kwargs):
        super().__init__(**kwargs)
        self._lock = lock
        self._parents = {}

    def _guard_path(self, path):
        self._lock.verify_identity()
        super()._guard_path(path)
        root = self._guard_root_membership(path)
        cursor = os.path.dirname(os.path.abspath(path))
        while root and os.path.commonpath((root, cursor)) == root:
            current = path_fingerprint(cursor)
            if current[0] != "absent":
                if cursor == root and current[0] == "symlink":
                    # CODEX_HOME itself may be an existing user-selected link. Bind
                    # both the link and its directory target; descendants stay no-link.
                    target = os.stat(cursor)
                    if not stat.S_ISDIR(target.st_mode):
                        raise InstallDriftError(f"global home target is not a directory: {cursor}")
                    current += ("target", stat.S_IMODE(target.st_mode), target.st_dev, target.st_ino)
                elif current[0] != "dir":
                    raise InstallDriftError(f"global skill parent is not a directory: {cursor}")
                previous = self._parents.setdefault(cursor, current)
                if current != previous:
                    raise InstallDriftError(f"global skill parent changed: {cursor}")
            elif cursor in self._parents:
                raise InstallDriftError(f"global skill parent disappeared: {cursor}")
            if cursor == root:
                break
            cursor = os.path.dirname(cursor)

    def record_output(self, path, recursive=False):
        self._guard_path(path)  # also bind directories created by stage_write
        super().record_output(path, recursive=recursive)

    def _rollback_entry(self, path, backup):
        try:
            self._guard_path(path)
            self._verify_backup(path, backup)
            if backup is not None and path in self._outputs and not self._probe(path):
                form, expected = self._outputs[path]
                if self._measure(path, form) != expected:
                    raise InstallDriftError(f"concurrent deletion preserved: {path}")
            super()._rollback_entry(path, backup)
        except (OSError, InstallDriftError) as exc:
            raise InstallDriftError(f"{exc}; recovery backup: {backup}") from exc

    def _remove(self, path):
        try:
            self._guard_path(path)
        except InstallDriftError as exc:
            if self.committed:
                # Backup GC is after commit. Preserve residue and report the warning;
                # it must never turn into a project-only rollback.
                raise OSError(str(exc)) from exc
            raise
        super()._remove(path)

    def _verify_backup(self, path, backup):
        if backup is not None and self._probe(backup):
            form, original = self._originals[path]
            if self._measure(backup, form) != original:
                raise InstallDriftError(f"recovery backup changed: {backup}")

    def verify_outputs(self):
        for path in self._outputs:
            self._guard_path(path)
        for path, backup in self._entries:
            self._verify_backup(path, backup)
            if backup is not None and not self._probe(backup):
                raise InstallDriftError(f"recovery backup missing: {backup}")
        super().verify_outputs()

    def rollback(self):
        # A replaced parent can also redirect rmdir of newly-created directories.
        # Leave those directories untouched, just as we leave untrusted files.
        created, safe, problems = self._created_dirs, [], []
        for directory in created:
            try:
                self._guard_path(os.path.join(directory, ".sage-parent-check"))
                safe.append(directory)
            except (OSError, InstallDriftError) as exc:
                problems.append(f"{directory}: {exc}")
        self._created_dirs = safe
        try:
            return super().rollback() + problems
        finally:
            self._created_dirs = created


class GlobalSkillUpgrade:
    """Own the global lock and journal until the upgrade's activation boundary."""

    def __init__(self, skills_root, project_root):
        self.skills_root = os.path.abspath(skills_root)
        self.home = os.path.dirname(self.skills_root)
        self.project_root = os.path.abspath(project_root)
        self.lock = DestinationLock(self.skills_root)
        self.transaction = None
        self._token = None

    def __enter__(self):
        if active_global_upgrade() is not None:
            raise InstallDriftError("nested global upgrade scope")
        real_home = os.path.realpath(self.home)
        real_project = os.path.realpath(self.project_root)
        if _within(real_home, real_project) or _within(real_project, real_home):
            raise InstallDriftError("project and Codex global home overlap")
        self.lock.acquire()
        self._token = _ACTIVE.set(self)
        return self

    def verify_lock(self, skills_root, project_root):
        if (os.path.abspath(skills_root) != self.skills_root
                or os.path.abspath(project_root) != self.project_root
                or not self.lock._locks):
            raise InstallDriftError("global upgrade lock does not cover install destination")
        self.lock.verify_identity()

    def prepare(self, preconditions):
        """Transfer global preconditions, leaving project inputs with install."""
        if self.transaction is not None:
            raise InstallDriftError("global upgrade installer already ran")
        global_inputs = {path: value for path, value in preconditions.items()
                         if _within(self.home, path)}
        self.transaction = _GlobalTransaction(
            self.lock, expected=global_inputs, write_roots=(self.home,))
        self.transaction.verify_unconsumed()
        return {path: value for path, value in preconditions.items() if path not in global_inputs}

    def commit(self):
        if self.transaction is None:
            return []
        self.transaction.verify_unconsumed()
        self.transaction.verify_outputs()
        return self.transaction.commit()

    def __exit__(self, exc_type, exc, traceback):
        try:
            if self.transaction is not None and not self.transaction.committed:
                problems = self.transaction.rollback()
                if problems:
                    raise GlobalRollbackError(problems) from exc
        finally:
            _ACTIVE.reset(self._token)
            self.lock.release()
