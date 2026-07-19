#!/usr/bin/env python3
"""Acceptance waiver audit/CLI regressions for SAGE-FB-02."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from argparse import Namespace
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
RUNTIME = os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime")
sys.path.insert(0, REPO)
sys.path.insert(0, RUNTIME)
import acceptance_waiver as aw  # noqa: E402


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
