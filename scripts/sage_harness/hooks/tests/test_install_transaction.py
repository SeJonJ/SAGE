#!/usr/bin/env python3
import os
import stat
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from sage import install_transaction as tx


class TestInstallTransaction(unittest.TestCase):
    def test_rollback_restores_regular_mode_and_hardlink_identity(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            external = Path(outside, "shared.md")
            external.write_text("original\n", encoding="utf-8")
            target = Path(root, "nested", "target.md")
            target.parent.mkdir()
            os.link(external, target)
            os.chmod(target, 0o640)
            original_inode = os.stat(target).st_ino
            journal = tx.InstallTransaction()

            journal.stage_write(target)
            target.write_text("replacement\n", encoding="utf-8")
            journal.record_output(target)
            self.assertEqual(journal.rollback(), [])

            self.assertEqual(target.read_text(encoding="utf-8"), "original\n")
            self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o640)
            self.assertEqual(os.stat(target).st_ino, original_inode)
            self.assertEqual(os.stat(target).st_ino, os.stat(external).st_ino)

    def test_new_nested_file_rollback_removes_created_directories(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "a", "b", "new.md")
            journal = tx.InstallTransaction()
            journal.stage_write(target)
            target.write_text("new\n", encoding="utf-8")
            journal.record_output(target)

            self.assertEqual(journal.rollback(), [])
            self.assertFalse(Path(root, "a").exists())

    def test_removed_tree_is_restored_on_rollback_and_deleted_on_commit(self):
        for commit in (False, True):
            with self.subTest(commit=commit), tempfile.TemporaryDirectory() as root:
                legacy = Path(root, "legacy")
                legacy.mkdir()
                Path(legacy, "SKILL.md").write_text("legacy\n", encoding="utf-8")
                journal = tx.InstallTransaction()
                self.assertTrue(journal.stage_remove_tree(legacy))
                self.assertFalse(legacy.exists())
                errors = journal.commit() if commit else journal.rollback()
                self.assertEqual(errors, [])
                self.assertEqual(legacy.exists(), not commit)
                self.assertFalse(any(".sage-install-backup-" in p.name
                                     for p in Path(root).rglob("*")))

    def test_expected_drift_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "input.md")
            target.write_text("before\n", encoding="utf-8")
            expected = tx.capture_paths([target])
            target.write_text("after\n", encoding="utf-8")
            journal = tx.InstallTransaction(expected)

            with self.assertRaises(tx.InstallDriftError):
                journal.verify_unconsumed()

    def test_optional_restore_reinstates_expected_state_tracking(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "optional.md")
            journal = tx.InstallTransaction(tx.capture_paths([target]))
            journal.stage_write(target)
            target.write_text("attempt\n", encoding="utf-8")
            journal.record_output(target)
            journal.restore_path(target)
            journal.verify_unconsumed()

            target.write_text("concurrent\n", encoding="utf-8")
            with self.assertRaises(tx.InstallDriftError):
                journal.verify_unconsumed()

    def test_output_drift_after_stage_is_detected_before_commit(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "output.md")
            journal = tx.InstallTransaction()
            journal.stage_write(target)
            target.write_text("installed\n", encoding="utf-8")
            journal.record_output(target)
            journal.verify_outputs()

            target.write_text("concurrent\n", encoding="utf-8")
            with self.assertRaises(tx.InstallDriftError):
                journal.verify_outputs()
            errors = journal.rollback()
            self.assertEqual(len(errors), 1)
            self.assertIn("concurrent path mutation preserved", errors[0])
            self.assertEqual(target.read_text(encoding="utf-8"), "concurrent\n")

    def test_rollback_preserves_current_path_when_original_backup_is_missing(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "output.md")
            target.write_text("original\n", encoding="utf-8")
            journal = tx.InstallTransaction()
            journal.stage_write(target)
            target.write_text("installed\n", encoding="utf-8")
            journal.record_output(target)
            backup = next(Path(root).glob(".sage-install-backup-*"))
            backup.unlink()

            errors = journal.rollback()

            self.assertEqual(len(errors), 1)
            self.assertIn("transaction backup missing", errors[0])
            self.assertEqual(target.read_text(encoding="utf-8"), "installed\n")

    def test_destination_lock_rejects_competing_holder(self):
        with tempfile.TemporaryDirectory() as root:
            first = tx.DestinationLock(root)
            second = tx.DestinationLock(root)
            first.acquire()
            try:
                with self.assertRaises(tx.InstallBusyError):
                    second.acquire()
            finally:
                first.release()
            second.acquire()
            second.release()

    def test_destination_lock_uses_realpath_for_symlink_alias(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent, "project")
            alias = Path(parent, "alias")
            root.mkdir()
            alias.symlink_to(root, target_is_directory=True)
            first = tx.DestinationLock(root)
            second = tx.DestinationLock(alias)
            first.acquire()
            try:
                with self.assertRaises(tx.InstallBusyError):
                    second.acquire()
            finally:
                first.release()

    def test_destination_lock_uses_inode_for_case_alias(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent, "case-project")
            root.mkdir()
            alias = Path(parent, "CASE-PROJECT")
            if not alias.exists() or not os.path.samefile(root, alias):
                self.skipTest("filesystem is case-sensitive")

            self.assertEqual(tx.DestinationLock(root).path, tx.DestinationLock(alias).path)

    def test_destination_lock_path_key_survives_destination_creation(self):
        with tempfile.TemporaryDirectory() as parent:
            destination = Path(parent, "new-project")
            first = tx.DestinationLock(destination)
            first.acquire()
            try:
                destination.mkdir()
                second = tx.DestinationLock(destination)
                self.assertEqual(first.path, second.path)
                with self.assertRaises(tx.InstallBusyError):
                    second.acquire()
            finally:
                first.release()

    def test_destination_lock_conservatively_casefolds_missing_destination(self):
        with tempfile.TemporaryDirectory() as parent:
            lower = Path(parent, "missing-project")
            upper = Path(parent, "MISSING-PROJECT")
            self.assertEqual(tx.DestinationLock(lower).path, tx.DestinationLock(upper).path)

    def test_write_ahead_entry_recovers_interrupt_after_backup_rename(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "target.md")
            target.write_text("original\n", encoding="utf-8")
            journal = tx.InstallTransaction()
            original_replace = os.replace

            def replace_then_interrupt(src, dst):
                original_replace(src, dst)
                raise KeyboardInterrupt("after backup rename")

            with mock.patch("sage.install_transaction.os.replace",
                            side_effect=replace_then_interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    journal.stage_write(target)

            self.assertEqual(journal.rollback(), [])
            self.assertEqual(target.read_text(encoding="utf-8"), "original\n")

    def test_backup_rename_detects_and_preserves_concurrent_file_replacement(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "target.md")
            target.write_text("original\n", encoding="utf-8")
            journal = tx.InstallTransaction()
            original_replace = os.replace

            def replace_after_concurrent_swap(src, dst):
                if os.path.abspath(src) == os.path.abspath(target):
                    concurrent = Path(root, "concurrent.md")
                    concurrent.write_text("concurrent\n", encoding="utf-8")
                    original_replace(concurrent, target)
                return original_replace(src, dst)

            with mock.patch("sage.install_transaction.os.replace",
                            side_effect=replace_after_concurrent_swap):
                with self.assertRaises(tx.InstallDriftError):
                    journal.stage_write(target)

            self.assertEqual(journal.rollback(), [])
            self.assertEqual(target.read_text(encoding="utf-8"), "concurrent\n")

    def test_backup_rename_detects_and_preserves_concurrent_tree_replacement(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "legacy")
            target.mkdir()
            Path(target, "SKILL.md").write_text("original\n", encoding="utf-8")
            journal = tx.InstallTransaction()
            original_replace = os.replace

            def replace_after_concurrent_swap(src, dst):
                if os.path.abspath(src) == os.path.abspath(target):
                    concurrent = Path(root, "concurrent-tree")
                    concurrent.mkdir()
                    Path(concurrent, "SKILL.md").write_text("concurrent\n", encoding="utf-8")
                    original_replace(target, Path(root, "displaced-original"))
                    original_replace(concurrent, target)
                return original_replace(src, dst)

            with mock.patch("sage.install_transaction.os.replace",
                            side_effect=replace_after_concurrent_swap):
                with self.assertRaises(tx.InstallDriftError):
                    journal.stage_remove_tree(target)

            self.assertEqual(journal.rollback(), [])
            self.assertEqual(Path(target, "SKILL.md").read_text(encoding="utf-8"),
                             "concurrent\n")

    def test_repeated_stage_rejects_changed_installer_output(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "render.md")
            target.write_text("original\n", encoding="utf-8")
            journal = tx.InstallTransaction()
            journal.stage_write(target)
            target.write_text("installed-base\n", encoding="utf-8")
            journal.record_output(target)
            target.write_text("concurrent\n", encoding="utf-8")

            with self.assertRaises(tx.InstallDriftError):
                journal.stage_write(target)

            errors = journal.rollback()
            self.assertEqual(len(errors), 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "concurrent\n")

    def test_destination_identity_change_during_lock_acquire_is_rejected(self):
        with tempfile.TemporaryDirectory() as parent, tempfile.TemporaryDirectory() as outside:
            link = Path(parent, "link")
            destination = link / "project"
            lock = tx.DestinationLock(destination)
            link.symlink_to(outside, target_is_directory=True)

            with self.assertRaises(tx.InstallDriftError):
                lock.acquire()

            self.assertEqual(lock._locks, [])

    def test_lock_root_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_root, tempfile.TemporaryDirectory() as outside:
            with mock.patch("sage.install_transaction.tempfile.gettempdir",
                            return_value=temp_root):
                lock = tx.DestinationLock(Path(temp_root, "project"))
            Path(lock.lock_root).symlink_to(outside, target_is_directory=True)

            with self.assertRaises(tx.InstallBusyError):
                lock.acquire()

    def test_commit_interrupt_is_commit_forward_not_partial_rollback(self):
        with tempfile.TemporaryDirectory() as root:
            targets = [Path(root, "one.md"), Path(root, "two.md")]
            journal = tx.InstallTransaction()
            for target in targets:
                target.write_text("original\n", encoding="utf-8")
                journal.stage_write(target)
                target.write_text("installed\n", encoding="utf-8")
                journal.record_output(target)
            original_remove = journal._remove
            calls = {"count": 0}

            def interrupt_second_cleanup(path):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise KeyboardInterrupt("during backup gc")
                return original_remove(path)

            with mock.patch.object(journal, "_remove", side_effect=interrupt_second_cleanup):
                with self.assertRaises(KeyboardInterrupt):
                    journal.commit()

            self.assertTrue(journal.committed)
            self.assertEqual([path.read_text(encoding="utf-8") for path in targets],
                             ["installed\n", "installed\n"])

    def test_write_guard_rejects_symlink_ancestor(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            Path(root, "docs").symlink_to(outside, target_is_directory=True)
            journal = tx.InstallTransaction(write_roots=[root])

            with self.assertRaises(tx.InstallDriftError):
                journal.stage_write(Path(root, "docs", "agent", "review.md"))

            self.assertEqual(os.listdir(outside), [])


class TestLockRootPermissions(unittest.TestCase):
    """#28 — 관리자로 처음 만든 잠금 폴더 때문에 같은 사용자의 일반 권한 명령이 전부 막히던 결함.

    Python 3.12.4 부터 Windows 의 `mkdir(..., 0o700)` 은 「만든 주체만」 ACL 을 건다. 그래서
    Windows 에서는 mode 를 주지 않고, 이미 그렇게 만들어진 폴더를 피하도록 이름을 바꾼다. 잠금
    자리를 못 여는 것은 「다른 명령이 실행 중」이 아니므로 다른 진단으로 올린다.
    """

    def _lock(self, temp_root):
        with mock.patch("sage.install_transaction.tempfile.gettempdir", return_value=temp_root):
            return tx.DestinationLock(Path(temp_root, "project"))

    def _mkdir_calls(self, os_name):
        calls = []
        real_mkdir = os.mkdir

        def spy(path, *args, **kwargs):
            calls.append(args + tuple(kwargs.values()))
            return real_mkdir(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temp_root:
            lock = self._lock(temp_root)
            with mock.patch("sage.install_transaction.os.mkdir", side_effect=spy), \
                    mock.patch("sage.install_transaction.os.name", os_name):
                lock._prepare_lock_root()
        return calls

    def test_windows_creates_the_lock_root_without_a_mode(self):
        self.assertEqual(self._mkdir_calls("nt"), [()],
                         "Windows 에서 mode 를 주면 관리자 생성 폴더를 일반 권한이 못 연다")

    @unittest.skipIf(os.name == "nt", "POSIX 권한 검사 전제")
    def test_posix_keeps_the_private_mode(self):
        self.assertEqual(self._mkdir_calls("posix"), [(0o700,)])

    def test_windows_uses_a_new_lock_folder_name(self):
        """1.3.3 까지의 폴더가 관리자 소유로 남아 있어도 손으로 지우지 않고 풀려야 한다."""
        saved = getattr(os, "geteuid", None)
        if saved is not None:
            del os.geteuid
        try:
            with tempfile.TemporaryDirectory() as temp_root, \
                    mock.patch("sage.install_transaction.os.name", "nt"):
                lock = self._lock(temp_root)
        finally:
            if saved is not None:
                os.geteuid = saved
        self.assertEqual(os.path.basename(lock.lock_root), "sage-install-locks-v2")

    def _assert_unavailable(self, raised, lock):
        diagnostic = raised.exception.diagnostic
        self.assertEqual(diagnostic.code, "install.lock_unavailable")
        self.assertEqual(diagnostic.arguments["path"], lock.lock_root)
        self.assertIn("PermissionError", diagnostic.arguments["error"])
        self.assertEqual(lock._locks, [])

    def test_a_lock_root_that_cannot_be_created_is_a_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp_root:
            lock = self._lock(temp_root)
            with mock.patch("sage.install_transaction.os.mkdir",
                            side_effect=PermissionError(13, "Access is denied")):
                with self.assertRaises(tx.InstallBusyError) as raised:
                    lock.acquire()
            self._assert_unavailable(raised, lock)

    def test_a_lock_file_that_cannot_be_opened_is_not_reported_as_busy(self):
        with tempfile.TemporaryDirectory() as temp_root:
            lock = self._lock(temp_root)
            with mock.patch("sage.install_transaction.os.open",
                            side_effect=PermissionError(13, "Access is denied")):
                with self.assertRaises(tx.InstallBusyError) as raised:
                    lock.acquire()
            self._assert_unavailable(raised, lock)

    def test_a_held_lock_is_still_reported_as_busy(self):
        """과차단 방향의 반대 — 진짜 실행 중은 그대로 실행 중이다."""
        with tempfile.TemporaryDirectory() as temp_root:
            first, second = self._lock(temp_root), self._lock(temp_root)
            first.acquire()
            # 임시 폴더를 지우기 전에 놓는다. Windows 는 열린 잠금 파일을 지우지 못한다.
            try:
                with self.assertRaises(tx.InstallBusyError) as raised:
                    second.acquire()
            finally:
                first.release()
            self.assertEqual(raised.exception.diagnostic.code, "install.destination_busy")


if __name__ == "__main__":
    unittest.main(verbosity=2)
