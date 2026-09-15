#!/usr/bin/env python3
"""Acceptance waiver audit/CLI regressions for SAGE-FB-02."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from argparse import Namespace
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
RUNTIME = os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime")
sys.path.insert(0, REPO)
sys.path.insert(0, RUNTIME)
import acceptance_waiver as aw  # noqa: E402

POSIX_ONLY = "descriptor-bound POSIX path; Windows is covered by TestAcceptanceWaiverWindowsIo"


class TestAcceptanceWaiverAudit(unittest.TestCase):
    def _grant(self, root, **over):
        args = dict(cycle_stem="feature", acceptance_id="A1", reason="production-only check",
                    scope="single production smoke", remaining_evidence="verify live callback",
                    confirmed_by="sejon", ttl_seconds=3600, now=100)
        args.update(over)
        return aw.grant(root, **args)

    def test_grant_is_exact_active_and_auditable(self):
        with tempfile.TemporaryDirectory() as root:
            rec = self._grant(root)
            summary = aw.audit_summary(root, now=101)
            self.assertTrue(summary["valid"])
            self.assertEqual([g["waiver_id"] for g in summary["active"]], [rec["waiver_id"]])
            self.assertEqual(summary["active"][0]["attestation"], "self_asserted_local")

    def test_required_fields_and_wildcards_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            for field in ("cycle_stem", "acceptance_id", "reason", "scope",
                          "remaining_evidence", "confirmed_by"):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self._grant(root, **{field: ""})
            for field in ("cycle_stem", "acceptance_id"):
                with self.subTest(wildcard=field), self.assertRaises(ValueError):
                    self._grant(root, **{field: "*"})

    def test_ttl_cap_expiry_and_revoke_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                self._grant(root, ttl_seconds=aw.MAX_TTL_SECONDS + 1)
            expired = self._grant(root, ttl_seconds=1)
            self.assertEqual(aw.audit_summary(root, now=102)["active"], [])
            live = self._grant(root, acceptance_id="A2", now=200)
            self.assertIsNotNone(aw.revoke(root, live["waiver_id"], "cancelled", "sejon", now=201))
            self.assertEqual(aw.audit_summary(root, now=202)["active"], [])
            self.assertIsNone(aw.revoke(root, expired["waiver_id"], "late", "sejon", now=202))

    def test_malformed_duplicate_and_conflicting_records_invalidate_summary(self):
        with tempfile.TemporaryDirectory() as root:
            rec = self._grant(root)
            path = aw.audit_path(root)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("not-json\n")
                fh.write(json.dumps(rec) + "\n")
            summary = aw.audit_summary(root, now=101)
            self.assertFalse(summary["valid"])
            self.assertTrue(any("malformed" in issue for issue in summary["issues"]))
            self.assertTrue(any("duplicate waiver_id" in issue for issue in summary["issues"]))

        with tempfile.TemporaryDirectory() as root:
            first = self._grant(root)
            conflict = dict(first, waiver_id="aw-conflicting", epoch=101,
                            created_at="1970-01-01T00:01:41Z", expires_epoch=3701,
                            expires_at="1970-01-01T01:01:41Z")
            with open(aw.audit_path(root), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(conflict) + "\n")
            summary = aw.audit_summary(root, now=102)
            self.assertFalse(summary["valid"])
            self.assertTrue(any("conflicting active grants" in issue for issue in summary["issues"]))

    def test_use_is_append_only_and_exact(self):
        with tempfile.TemporaryDirectory() as root:
            rec = self._grant(root)
            use = aw.record_use(root, rec, "plan_docs/06-report/feature.md", now=110)
            self.assertEqual(use["event"], "use")
            self.assertEqual(use["cycle_stem"], "feature")
            self.assertEqual(use["acceptance_id"], "A1")
            self.assertEqual([r["event"] for r in aw.read_records(root)], ["grant", "use"])

    @unittest.skipIf(os.name == "nt", POSIX_ONLY)
    def test_symlinked_audit_parent_or_file_is_invalid(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            os.symlink(outside, os.path.join(root, ".sage"))
            summary = aw.audit_summary(root)
            self.assertFalse(summary["valid"])
            with self.assertRaises((ValueError, OSError)):
                self._grant(root)
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            os.makedirs(os.path.join(root, ".sage"))
            target = os.path.join(outside, "audit.jsonl")
            open(target, "w", encoding="utf-8").close()
            os.symlink(target, aw.audit_path(root))
            self.assertFalse(aw.audit_summary(root)["valid"])

    @unittest.skipIf(os.name == "nt", POSIX_ONLY)
    def test_audit_parent_swap_race_cannot_escape_project_root(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            sage_dir = os.path.join(root, ".sage")
            original_dir = os.path.join(root, ".sage-original")
            os.mkdir(sage_dir)
            real_open = os.open
            swapped = False

            def swapping_open(path, flags, *args, **kwargs):
                nonlocal swapped
                if not swapped and path == ".sage" and kwargs.get("dir_fd") is not None:
                    os.rename(sage_dir, original_dir)
                    os.symlink(outside, sage_dir)
                    swapped = True
                return real_open(path, flags, *args, **kwargs)

            try:
                with mock.patch.object(aw.os, "open", side_effect=swapping_open):
                    with self.assertRaises((ValueError, OSError)):
                        self._grant(root)
                self.assertFalse(os.path.exists(os.path.join(outside, "acceptance-waivers.jsonl")))
            finally:
                if os.path.islink(sage_dir):
                    os.unlink(sage_dir)
                if os.path.isdir(original_dir):
                    os.rename(original_dir, sage_dir)

    def test_use_after_revoke_or_outside_lifetime_invalidates_audit(self):
        with tempfile.TemporaryDirectory() as root:
            grant = self._grant(root)
            aw.revoke(root, grant["waiver_id"], "cancel", "sejon", now=101)
            forged = {"event": "use", "waiver_id": grant["waiver_id"], "cycle_stem": "feature",
                      "acceptance_id": "A1", "report_path": "report.md", "epoch": 102,
                      "ts": "1970-01-01T00:01:42Z"}
            with open(aw.audit_path(root), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(forged) + "\n")
            self.assertFalse(aw.audit_summary(root, now=102)["valid"])

    def test_parse_ttl_rejects_infinity_without_crash(self):
        self.assertIsNone(aw.parse_ttl("inf"))
        self.assertIsNone(aw.parse_ttl("infh"))

    def test_concurrent_same_scope_grants_compensate_instead_of_bricking_audit(self):
        with tempfile.TemporaryDirectory() as root:
            original_append = aw._append
            before_append = threading.Barrier(2)
            after_append = threading.Barrier(2)

            def synchronized_append(project_root, record):
                if record.get("event") == "grant":
                    before_append.wait(timeout=5)
                original_append(project_root, record)
                if record.get("event") == "grant":
                    after_append.wait(timeout=5)

            outcomes = []

            def issue(user):
                try:
                    outcomes.append(("ok", self._grant(root, confirmed_by=user, now=100)))
                except ValueError as exc:
                    outcomes.append(("rejected", str(exc)))
                except Exception as exc:
                    outcomes.append(("unexpected", f"{type(exc).__name__}: {exc}"))

            with mock.patch.object(aw, "_append", side_effect=synchronized_append):
                threads = [threading.Thread(target=issue, args=(user,)) for user in ("u1", "u2")]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=10)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertFalse([item for item in outcomes if item[0] == "unexpected"], outcomes)
            self.assertEqual(len(outcomes), 2, outcomes)
            summary = aw.audit_summary(root, now=101)
            self.assertTrue(summary["valid"], summary["issues"])
            self.assertLessEqual(len(summary["active"]), 1)

    def test_explicit_revoke_recovers_preexisting_conflict_only_audit(self):
        with tempfile.TemporaryDirectory() as root:
            first = self._grant(root)
            conflict = dict(first, waiver_id="aw-conflicting", epoch=101,
                            created_at="1970-01-01T00:01:41Z", expires_epoch=3701,
                            expires_at="1970-01-01T01:01:41Z")
            with open(aw.audit_path(root), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(conflict) + "\n")
            self.assertFalse(aw.audit_summary(root, now=102)["valid"])
            self.assertIsNotNone(aw.revoke(root, conflict["waiver_id"], "resolve conflict", "sejon", now=102))
            self.assertTrue(aw.audit_summary(root, now=103)["valid"])


class TestAcceptanceWaiverCli(unittest.TestCase):
    def _project(self, root):
        os.makedirs(os.path.join(root, "sage"))
        os.makedirs(os.path.join(root, "plan_docs", "01-plan"))
        with open(os.path.join(root, "sage", "project-profile.yaml"), "w", encoding="utf-8") as fh:
            fh.write("""verification:\n  acceptance:\n    enabled: true\n    report_gate_by_risk: { L2: advisory, L3: enforce }\n    waiver: { enabled: true }\npdca:\n  enabled: true\n  phases:\n    - { id: '01', glob: 'plan_docs/01-plan/**/*.md' }\n""")
        with open(os.path.join(root, "plan_docs", "01-plan", "feature.md"), "w", encoding="utf-8") as fh:
            fh.write("""Cycle-Stem: `feature`\n## Acceptance Matrix\n| ID | Requirement | Required? |\n|---|---|---|\n| A1 | production check | yes |\n| A2 | optional | no |\n""")

    def _sage(self, root, *args):
        return subprocess.run([sys.executable, "-m", "sage", "acceptance-waiver", *args, "--root", root],
                              cwd=REPO, capture_output=True, text=True)

    def test_grant_requires_exact_required_matrix_id_then_list_and_revoke(self):
        with tempfile.TemporaryDirectory() as root:
            self._project(root)
            base = ("grant", "--cycle-stem", "feature", "--acceptance-id", "A1",
                    "--reason", "prod only", "--scope", "one smoke",
                    "--remaining-evidence", "live callback", "--confirm-user", "sejon")
            granted = self._sage(root, *base)
            self.assertEqual(granted.returncode, 0, granted.stderr)
            waiver_id = granted.stdout.strip().splitlines()[0]
            self.assertTrue(waiver_id.startswith("aw-"))
            listed = self._sage(root, "list")
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertIn(waiver_id, listed.stdout)
            revoked = self._sage(root, "revoke", "--waiver-id", waiver_id,
                                 "--reason", "done", "--confirm-user", "sejon")
            self.assertEqual(revoked.returncode, 0, revoked.stderr)

    def test_grant_rejects_optional_or_unknown_id(self):
        with tempfile.TemporaryDirectory() as root:
            self._project(root)
            for acceptance_id in ("A2", "UNKNOWN"):
                result = self._sage(root, "grant", "--cycle-stem", "feature",
                                    "--acceptance-id", acceptance_id, "--reason", "prod only",
                                    "--scope", "one smoke", "--remaining-evidence", "live callback",
                                    "--confirm-user", "sejon")
                self.assertEqual(result.returncode, 2)
                self.assertIn("required acceptance ID", result.stderr)

    def test_grant_and_revoke_normalize_filesystem_errors(self):
        from sage.commands import acceptance_waiver as cli

        runtime = mock.Mock()
        runtime.MAX_TTL_SECONDS = 86400
        runtime.parse_ttl.return_value = 3600
        runtime.grant.side_effect = PermissionError("audit is read-only")
        runtime.revoke.side_effect = OSError("audit fsync failed")
        grant_args = Namespace(root="/tmp/project", ttl="1h", cycle_stem="feature",
                               acceptance_id="A1", reason="prod only", scope="one smoke",
                               remaining_evidence="live callback", confirm_user="sejon")
        revoke_args = Namespace(root="/tmp/project", waiver_id="aw-1",
                                reason="done", confirm_user="sejon")
        with mock.patch.object(cli, "_load_runtime_modules", return_value=(runtime, None, None)), \
             mock.patch.object(cli, "_load_profile", return_value={}), \
             mock.patch.object(cli, "_assert_required_acceptance"), \
             mock.patch("sys.stderr"):
            self.assertEqual(cli._run_grant(grant_args), 2)
            self.assertEqual(cli._run_revoke(revoke_args), 2)

    def test_runtime_import_failure_is_a_diagnostic_not_a_traceback(self):
        """런타임을 못 불러오는 상태를 플랫폼과 무관하게 주입해 세 명령이 진단 한 줄로 끝나는지 본다."""
        import contextlib
        import io
        from sage import cli as sage_cli
        from sage.commands import acceptance_waiver as cli

        missing = ModuleNotFoundError("No module named 'acceptance_waiver'", name="acceptance_waiver")
        commands = (
            ("grant", "--cycle-stem", "feature", "--acceptance-id", "A1", "--reason", "prod only",
             "--scope", "one smoke", "--remaining-evidence", "live callback", "--confirm-user", "sejon"),
            ("list",),
            ("revoke", "--waiver-id", "aw-1", "--reason", "done", "--confirm-user", "sejon"),
        )
        for command in commands:
            with self.subTest(command=command[0]):
                stderr = io.StringIO()
                with mock.patch.object(cli, "_load_runtime_modules", side_effect=missing), \
                     contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
                    rc = sage_cli.main(["--lang", "en", "acceptance-waiver", *command, "--root", "/nonexistent"])
                self.assertEqual(rc, 2, stderr.getvalue())
                self.assertNotIn("Traceback", stderr.getvalue())
                self.assertIn("[sage acceptance-waiver] Could not load the acceptance waiver runtime",
                              stderr.getvalue())
                self.assertIn("ModuleNotFoundError: No module named 'acceptance_waiver'", stderr.getvalue())


class _FakeMsvcrt:
    """POSIX 에서 Windows 분기를 돌리기 위한 msvcrt 대역. 실제 Windows 에서는 쓰지 않는다.

    LK_LOCK 은 실제처럼 짧게 재시도한 뒤 OSError 로 포기한다 — 잠금이 새면 테스트가 멈추지 않고 실패한다.
    """
    LK_UNLCK, LK_LOCK = 0, 1

    def __init__(self):
        self.calls = []

    def locking(self, fd, mode, nbytes):
        import fcntl
        self.calls.append(mode)
        if mode == self.LK_UNLCK:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return
        for _ in range(20):
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                time.sleep(0.01)
        raise OSError("Resource deadlock avoided")


def _reparse_stat(real, st_mode=None):
    """lstat 결과에 reparse point 속성을 얹은 대역. symlink 생성 권한과 무관하게 거부 분기를 친다."""
    import types
    fields = {name: getattr(real, name) for name in dir(real) if name.startswith("st_")}
    if st_mode is not None:
        fields["st_mode"] = st_mode
    fields["st_file_attributes"] = (getattr(real, "st_file_attributes", 0)
                                    | stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return types.SimpleNamespace(**fields)


class TestAcceptanceWaiverWindowsIo(TestAcceptanceWaiverAudit):
    """Windows 분기로 감사 의미 테스트 전체를 다시 돌린다. POSIX 에서는 msvcrt 대역으로 돈다."""

    def setUp(self):
        self.fake = None
        patches = [mock.patch.object(aw, "_NT_IO", True)]
        if os.name != "nt":
            self.fake = _FakeMsvcrt()
            patches.append(mock.patch.dict(sys.modules, {"msvcrt": self.fake}))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _assert_every_lock_released(self):
        """fd 를 닫으면 잠금도 풀리므로 대역의 호출 짝으로 명시 해제를 본다. 실제 Windows 에서는 native 테스트가 맡는다."""
        if self.fake is not None:
            self.assertEqual(self.fake.calls.count(_FakeMsvcrt.LK_LOCK),
                             self.fake.calls.count(_FakeMsvcrt.LK_UNLCK), "LK_UNLCK 없이 fd 만 닫았다")

    def _lock_path(self, root):
        return aw.audit_path(root) + aw.LOCK_SUFFIX

    def _append_probe(self, root):
        """grant 앞의 조회 검사를 거치지 않고 쓰기 경로만 친다 — 쓰기·잠금 실패가 OSError 로 오는지 본다."""
        aw._append(root, {"event": "probe"})

    def test_symlinked_audit_parent_or_file_is_invalid(self):
        for leaf in ("dir", "audit", "lock"):
            with self.subTest(leaf=leaf), tempfile.TemporaryDirectory() as root, \
                    tempfile.TemporaryDirectory() as outside:
                sage_dir = os.path.join(root, ".sage")
                if leaf == "dir":
                    target, link = outside, sage_dir
                else:
                    os.mkdir(sage_dir)
                    target = os.path.join(outside, "planted")
                    open(target, "wb").close()
                    link = aw.audit_path(root) if leaf == "audit" else self._lock_path(root)
                try:
                    os.symlink(target, link, target_is_directory=(leaf == "dir"))
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"symlink creation is not permitted here: {exc}")
                self.assertFalse(aw.audit_summary(root)["valid"])
                with self.assertRaises((ValueError, OSError)):
                    self._grant(root)
                with self.assertRaises(OSError):
                    self._append_probe(root)
                self.assertEqual(sorted(os.listdir(outside)), [] if leaf == "dir" else ["planted"])
                if leaf != "dir":
                    self.assertEqual(os.path.getsize(target), 0)

    def test_audit_parent_swap_race_cannot_escape_project_root(self):
        self.skipTest("검사와 open 사이의 .sage 교체 경쟁은 Windows 분기에서 수용한 잔여 위험이다")

    def test_reparse_point_is_rejected_without_link_privilege(self):
        for leaf in ("dir", "audit", "lock"):
            with self.subTest(leaf=leaf), tempfile.TemporaryDirectory() as root:
                self._grant(root)
                # 분기는 realpath(root) 아래 경로로 lstat 한다. patch 안에서 realpath 를 부르면 재귀한다.
                target = os.path.normcase({"dir": os.path.join(os.path.realpath(root), ".sage"),
                                           "audit": os.path.realpath(aw.audit_path(root)),
                                           "lock": os.path.realpath(self._lock_path(root))}[leaf])
                real_lstat = os.lstat

                def reparse_lstat(path, *args, **kwargs):
                    result = real_lstat(path, *args, **kwargs)
                    return _reparse_stat(result) if os.path.normcase(str(path)) == target else result

                size = os.path.getsize(aw.audit_path(root))
                with mock.patch.object(aw.os, "lstat", side_effect=reparse_lstat) as patched:
                    summary = aw.audit_summary(root)
                    with self.assertRaises(OSError):
                        self._append_probe(root)
                self.assertTrue(any(os.path.normcase(str(call.args[0])) == target
                                    for call in patched.call_args_list), "대역이 검사 경로에 닿지 않았다")
                self.assertFalse(summary["valid"])
                self.assertEqual(os.path.getsize(aw.audit_path(root)), size)

    def test_records_are_stored_with_lf_line_endings(self):
        with tempfile.TemporaryDirectory() as root:
            rec = self._grant(root)
            aw.revoke(root, rec["waiver_id"], "done", "sejon", now=101)
            with open(aw.audit_path(root), "rb") as fh:
                data = fh.read()
            self.assertEqual(data.count(b"\n"), 2)
            self.assertNotIn(b"\r", data)
            self.assertTrue(os.path.isfile(self._lock_path(root)))
            self._assert_every_lock_released()

    def test_missing_sage_is_empty_but_missing_root_is_invalid(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(aw._read_lines(root), ([], []))
            self.assertTrue(aw.audit_summary(root)["valid"])
            self.assertFalse(os.path.exists(os.path.join(root, ".sage")), "읽기가 .sage 를 만들었다")
            missing = os.path.join(root, "no-such-project")
            self.assertFalse(aw.audit_summary(missing)["valid"])
            with self.assertRaises(OSError):
                self._append_probe(missing)
            self.assertFalse(os.path.exists(missing))
            not_dir = os.path.join(root, "file-root")
            open(not_dir, "wb").close()
            self.assertFalse(aw.audit_summary(not_dir)["valid"])
            os.mkdir(os.path.join(root, "proj"))
            open(os.path.join(root, "proj", ".sage"), "wb").close()
            self.assertFalse(aw.audit_summary(os.path.join(root, "proj"))["valid"])
            with self.assertRaises(OSError):
                self._append_probe(os.path.join(root, "proj"))

    def test_descriptors_and_lock_are_released_after_failures(self):
        real_open, real_close = os.open, os.close
        opened, closed = [], []

        def counting_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd

        def counting_close(fd):
            closed.append(fd)
            return real_close(fd)

        def failing_write(fd, data):
            raise OSError("No space left on device")

        # (이름, 주입, 조회 성공 여부, 쓰기 성공 여부)
        cases = (
            ("write", lambda: mock.patch.object(aw.os, "write", side_effect=failing_write), True, False),
            ("read", lambda: mock.patch.object(aw, "_read_opened", side_effect=OSError("read")), False, None),
            ("open-check", lambda: mock.patch.object(aw, "_nt_verify_opened", side_effect=OSError("check")),
             False, False),
        )
        for name, failure, read_ok, write_ok in cases:
            with self.subTest(failure=name), tempfile.TemporaryDirectory() as root:
                self._grant(root)
                size = os.path.getsize(aw.audit_path(root))
                opened.clear()
                closed.clear()
                with mock.patch.object(aw.os, "open", side_effect=counting_open), \
                     mock.patch.object(aw.os, "close", side_effect=counting_close), failure():
                    self.assertEqual(aw.audit_summary(root, now=101)["valid"], read_ok)
                    if write_ok is False:
                        with self.assertRaises(OSError):
                            self._append_probe(root)
                self.assertTrue(opened)
                self.assertEqual(sorted(opened), sorted(closed), "실패 경로에서 fd 가 닫히지 않았다")
                self.assertEqual(os.path.getsize(aw.audit_path(root)), size)
                self._assert_every_lock_released()
                # 잠금이 새면 LK_LOCK 이 포기해 여기서 invalid 가 된다.
                self.assertTrue(aw.audit_summary(root, now=103)["valid"])

    def test_lock_acquisition_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            self._grant(root)
            size = os.path.getsize(aw.audit_path(root))
            broken = mock.Mock(LK_LOCK=1, LK_UNLCK=0)
            broken.locking.side_effect = OSError("Resource deadlock avoided")
            with mock.patch.dict(sys.modules, {"msvcrt": broken}):
                summary = aw.audit_summary(root, now=101)
                with self.assertRaises(OSError):
                    self._append_probe(root)
            self.assertFalse(summary["valid"])
            self.assertTrue(any("audit read failed" in issue for issue in summary["issues"]))
            self.assertEqual(os.path.getsize(aw.audit_path(root)), size)
            self.assertNotIn(broken.LK_UNLCK, [call.args[1] for call in broken.locking.call_args_list])
            self.assertTrue(aw.audit_summary(root, now=102)["valid"])


@unittest.skipUnless(os.name == "nt", "real Windows filesystem and msvcrt behaviour")
class TestAcceptanceWaiverWindowsNative(unittest.TestCase):
    def test_junction_sage_directory_is_rejected(self):
        import _winapi
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            _winapi.CreateJunction(outside, os.path.join(root, ".sage"))
            self.assertFalse(aw.audit_summary(root)["valid"])
            with self.assertRaises(OSError):
                aw.grant(root, "feature", "A1", "r", "s", "e", "sejon", ttl_seconds=3600, now=100)
            self.assertEqual(os.listdir(outside), [])

    def test_lock_held_by_another_process_waits_then_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            aw.grant(root, "feature", "A1", "r", "s", "e", "sejon", ttl_seconds=3600, now=100)
            size = os.path.getsize(aw.audit_path(root))
            holder = subprocess.Popen(
                [sys.executable, "-c",
                 "import msvcrt, os, sys, time\n"
                 "fd = os.open(sys.argv[1], os.O_RDWR | os.O_BINARY)\n"
                 "msvcrt.locking(fd, msvcrt.LK_LOCK, 1)\n"
                 "print('locked', flush=True)\n"
                 "time.sleep(60)\n",
                 aw.audit_path(root) + aw.LOCK_SUFFIX],
                stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(holder.stdout.readline().strip(), "locked")
                started = time.monotonic()
                summary = aw.audit_summary(root, now=101)
                waited = time.monotonic() - started
                self.assertFalse(summary["valid"])
                self.assertGreater(waited, 5, "LK_LOCK 이 기다리지 않고 바로 포기했다")
                with self.assertRaises(OSError):
                    aw._append(root, {"event": "probe"})
            finally:
                holder.kill()
                holder.wait()
            self.assertEqual(os.path.getsize(aw.audit_path(root)), size)
            self.assertTrue(aw.audit_summary(root, now=103)["valid"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
