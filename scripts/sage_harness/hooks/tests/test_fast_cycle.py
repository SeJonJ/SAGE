#!/usr/bin/env python3
"""Fast Cycle integrated contract tests."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)

from sage.profile_validate import severity_of, validate_profile  # noqa: E402
from sage.fast_cycle_contract import bind_run_id  # noqa: E402

RUNTIME = os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime")
sys.path.insert(0, RUNTIME)

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional schema dependency
    jsonschema = None


def _valid_fast(enabled=True):
    return {
        "enabled": enabled,
        "reason_required": True,
        "minimum_rounds": {"L2": 1, "L3": 1},
        "minimum_lenses": {"L2": 2, "L3": 2},
        "lenses": {
            "L2": ["correctness", "error_handling", "convention"],
            "L3": ["correctness", "security", "data_integrity"],
        },
    }


class TestFastProfile(unittest.TestCase):
    def _issues(self, fast):
        return validate_profile({"pdca": {"fast_cycle": fast}}, REPO)

    def test_valid_policy_passes_manual_and_schema_validation(self):
        profile = {"pdca": {"fast_cycle": _valid_fast()}}
        self.assertNotEqual(severity_of(validate_profile(profile, REPO)), "FAIL")
        if jsonschema is not None:
            schema = json.loads(Path(REPO, "schema", "profile.schema.json").read_text(encoding="utf-8"))
            jsonschema.validate(profile, schema)

    def test_unknown_keys_bool_as_int_and_disabled_reason_are_rejected(self):
        samples = []
        unknown = _valid_fast(); unknown["typo"] = True; samples.append(unknown)
        bad_round = _valid_fast(); bad_round["minimum_rounds"]["L2"] = True; samples.append(bad_round)
        bad_lenses = _valid_fast(); bad_lenses["minimum_lenses"]["L3"] = 1; samples.append(bad_lenses)
        no_reason = _valid_fast(); no_reason["reason_required"] = False; samples.append(no_reason)
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(severity_of(self._issues(sample)), "FAIL")

    def test_tier_maps_and_lens_vocabulary_are_closed(self):
        samples = []
        missing = _valid_fast(); del missing["minimum_rounds"]["L3"]; samples.append(missing)
        extra = _valid_fast(); extra["minimum_lenses"]["L1"] = 2; samples.append(extra)
        duplicate = _valid_fast(); duplicate["lenses"]["L2"] = ["correctness", "correctness"]; samples.append(duplicate)
        unknown = _valid_fast(); unknown["lenses"]["L3"] = ["correctness", "security", "guessing"]; samples.append(unknown)
        short = _valid_fast(); short["lenses"]["L2"] = ["correctness"]; samples.append(short)
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(severity_of(self._issues(sample)), "FAIL")


class TestFastAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_strict_state_machine_and_chain(self):
        import fast_cycle_audit as fa
        rid = fa.open_fast(self.root, cycle_stem="hotfix", actual_risk="L3",
                           fast_review_level="L2", reason="production outage",
                           minimum_rounds=1, lenses=["correctness", "security"],
                           profile_hash="p" * 64, plan_hash_open="a" * 64,
                           run_id="fc-test")
        self.assertEqual(rid, "fc-test")
        fa.record_review(self.root, rid, loop_run_id="rl-test", actual_risk="L3",
                         rounds=1, lens_receipts_hash="b" * 64,
                         plan_hash_before_review="c" * 64, result="APPROVED")
        fa.close_fast(self.root, rid, loop_run_id="rl-test", actual_risk="L3",
                      plan_hash_final="c" * 64, report_path="plan_docs/06-report/hotfix.md")
        summary = fa.audit_summary(self.root)
        self.assertTrue(summary["file_ok"])
        self.assertEqual(summary["active"], [])
        self.assertTrue(summary["runs"][rid]["clean"])
        self.assertTrue(summary["runs"][rid]["chain_ok"])
        self.assertTrue(summary["runs"][rid]["seq_ok"])
        with self.assertRaises(fa.AuditWriteError):
            fa.record_review(self.root, rid, loop_run_id="rl-test", actual_risk="L3",
                             rounds=2, lens_receipts_hash="d" * 64,
                             plan_hash_before_review="c" * 64, result="APPROVED")

    def test_tamper_and_missing_trailing_newline_are_handled(self):
        import fast_cycle_audit as fa
        rid = fa.open_fast(self.root, cycle_stem="hotfix", actual_risk="L2",
                           fast_review_level="L2", reason="urgent",
                           minimum_rounds=1, lenses=["correctness", "security"],
                           profile_hash="p" * 64, plan_hash_open="a" * 64,
                           run_id="fc-test")
        path = fa.audit_path(self.root)
        raw = Path(path).read_bytes().rstrip(b"\n")
        Path(path).write_bytes(raw)
        fa.abort_fast(self.root, rid, reason="cancelled", stage="implementation",
                      actual_risk="L2")
        self.assertTrue(fa.audit_summary(self.root)["file_ok"])
        data = Path(path).read_text(encoding="utf-8").replace("urgent", "hidden", 1)
        Path(path).write_text(data, encoding="utf-8")
        self.assertFalse(fa.audit_summary(self.root)["runs"][rid]["chain_ok"])

    def test_concurrent_open_and_close_keep_state_transitions_unique(self):
        import fast_cycle_audit as fa

        barrier = threading.Barrier(2)
        original_summary = fa.audit_summary

        def synchronized_summary(root):
            result = original_summary(root)
            barrier.wait(timeout=5)
            return result

        def open_one(run_id):
            try:
                return fa.open_fast(
                    self.root, cycle_stem="hotfix", actual_risk="L3",
                    fast_review_level="L2", reason="production outage",
                    minimum_rounds=1, lenses=["correctness", "security"],
                    profile_hash="p" * 64, plan_hash_open="a" * 64, run_id=run_id)
            except fa.AuditWriteError:
                return None

        with mock.patch.object(fa, "audit_summary", side_effect=synchronized_summary):
            with ThreadPoolExecutor(max_workers=2) as pool:
                opened = list(pool.map(open_one, ("fc-race-a", "fc-race-b")))
        self.assertEqual(sum(item is not None for item in opened), 1)
        run_id = next(item for item in opened if item is not None)
        fa.record_review(self.root, run_id, loop_run_id="rl-race", actual_risk="L3",
                         rounds=1, lens_receipts_hash="b" * 64,
                         plan_hash_before_review="c" * 64, result="APPROVED")

        close_barrier = threading.Barrier(2)
        original_state = fa._state

        def synchronized_state(root, rid):
            result = original_state(root, rid)
            close_barrier.wait(timeout=5)
            return result

        def close_one(_):
            try:
                fa.close_fast(self.root, run_id, loop_run_id="rl-race", actual_risk="L3",
                              plan_hash_final="c" * 64, report_path="plan_docs/06-report/hotfix.md")
                return True
            except fa.AuditWriteError:
                return False

        with mock.patch.object(fa, "_state", side_effect=synchronized_state):
            with ThreadPoolExecutor(max_workers=2) as pool:
                closed = list(pool.map(close_one, range(2)))
        self.assertEqual(sum(closed), 1)
        records = fa.read_records(self.root)
        terminals = [record for record in records
                     if record.get("run_id") == run_id and record.get("event") == "fast_close"]
        self.assertEqual(len(terminals), 1)
        self.assertEqual(fa.integrity_issues(self.root), [])


class TestFastCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        Path(self.root, "sage").mkdir()
        Path(self.root, "plan_docs", "00-base_plan").mkdir(parents=True)
        profile = {
            "pdca": {
                "phases": [
                    {"id": "00", "glob": "plan_docs/00-base_plan/**/*.md"},
                    {"id": "05", "glob": "plan_docs/05-expert-review/**/*.md"},
                    {"id": "06", "glob": "plan_docs/06-report/**/*.md"},
                ],
                "fast_cycle": _valid_fast(),
            }
        }
        import yaml
        Path(self.root, "sage", "project-profile.yaml").write_text(
            yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
        runtime = Path(REPO, "scripts", "sage_harness", "hooks", "runtime")
        sys.path.insert(0, str(runtime))
        import cycle_state
        cycle_state.write_declaration(self.root, "hotfix", document_language="ko")
        Path(self.root, "plan_docs", "00-base_plan", "hotfix.md").write_text(
            self._plan(), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _plan():
        return """# [Fast Base Plan] hotfix

Cycle-Stem: `hotfix`
Cycle-Mode: FAST
Risk Level: L3
Fast-Review-Level: L2
Fast-Minimum-Rounds: 1
Fast-Lens-Count: 2
Fast-Lenses: correctness, error_handling
Fast-Reason: production outage
Fast-Audit-Run: pending
Status: IN PROGRESS
Done-Criteria-Revision: 1

## Phase 00 — Base Plan
### Done Criteria
- [ ] hotfix behavior is verified

### Document Mapping (Checklist)
- [x] Phase 00 context complete
- [x] Phase 01 requirements and acceptance matrix embedded
- [x] Phase 02 design and failure handling embedded
- [x] Phase 03 ownership, implementation checklist, and verification plan ready
## Phase 01 — Requirements
| ID | User Requirement | Required Evidence | Owner | Required? |
| A1 | fix | test | dev | yes |
## Phase 02 — Design
design
## Phase 03 — Implementation
- [x] File ownership assigned before source edits
- [x] Acceptance IDs mapped to implementation tasks
- [x] Verification command plan recorded
Acceptance: A1
## Phase 04 — Analyze
Status: PENDING — implementation not started
"""

    def _run(self, *args):
        env = dict(os.environ, PYTHONPATH=REPO)
        return subprocess.run([sys.executable, "-m", "sage", *args, "--root", self.root],
                              text=True, capture_output=True, env=env, cwd=self.root)

    def _set_done_mode(self, mode):
        import yaml
        path = Path(self.root, "sage", "project-profile.yaml")
        profile = yaml.safe_load(path.read_text(encoding="utf-8"))
        profile["pdca"]["base_plan"] = {"done_criteria_gate": mode}
        path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    def test_done_criteria_mode_controls_fast_open(self):
        plan_path = Path(self.root, "plan_docs", "00-base_plan", "hotfix.md")
        without_done = plan_path.read_text(encoding="utf-8").replace(
            "### Done Criteria\n- [ ] hotfix behavior is verified\n\n", "")
        plan_path.write_text(without_done, encoding="utf-8")

        off = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L2",
                        "--lens-count", "2", "--reason", "production outage")
        self.assertEqual(off.returncode, 0, off.stderr)
        self.assertNotIn("Done Criteria advisory", off.stderr)
        run_id = off.stdout.strip()
        self.assertEqual(self._run("fast-cycle", "abort", "--run-id", run_id,
                                   "--reason", "mode check").returncode, 0)

        Path(self.root, ".sage", "fast_cycle.jsonl").unlink()
        plan_path.write_text(without_done.replace(f"Fast-Audit-Run: {run_id}",
                                                  "Fast-Audit-Run: pending"), encoding="utf-8")
        self._set_done_mode("advisory")
        advisory = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L2",
                             "--lens-count", "2", "--reason", "production outage")
        self.assertEqual(advisory.returncode, 0, advisory.stderr)
        self.assertIn("Done Criteria advisory", advisory.stderr)
        advisory_run = advisory.stdout.strip()
        self.assertEqual(self._run("fast-cycle", "abort", "--run-id", advisory_run,
                                   "--reason", "mode check").returncode, 0)

        Path(self.root, ".sage", "fast_cycle.jsonl").unlink()
        plan_path.write_text(without_done.replace(f"Fast-Audit-Run: {advisory_run}",
                                                  "Fast-Audit-Run: pending"), encoding="utf-8")
        self._set_done_mode("enforce")
        enforced = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L2",
                             "--lens-count", "2", "--reason", "production outage")
        self.assertEqual(enforced.returncode, 2)
        self.assertIn("Done Criteria", enforced.stderr)
        self.assertFalse(Path(self.root, ".sage", "fast_cycle.jsonl").exists())

    def test_open_binds_plan_and_writes_warning_and_audit(self):
        proc = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L2",
                         "--lens-count", "2", "--reason", "production outage")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        run_id = proc.stdout.strip()
        self.assertTrue(run_id.startswith("fc-"))
        self.assertIn("SAGE FAST L3", proc.stderr)
        self.assertIn(f"Fast-Audit-Run: {run_id}",
                      Path(self.root, "plan_docs", "00-base_plan", "hotfix.md").read_text(encoding="utf-8"))
        self.assertTrue(Path(self.root, ".sage", "fast_cycle.jsonl").is_file())

    def test_reopen_rejects_values_that_differ_from_the_audit_snapshot(self):
        opened = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L2",
                           "--lens-count", "2", "--reason", "production outage")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        plan_path = Path(self.root, "plan_docs", "00-base_plan", "hotfix.md")
        changed = plan_path.read_text(encoding="utf-8")
        changed = changed.replace("Fast-Review-Level: L2", "Fast-Review-Level: L3")
        changed = changed.replace("Fast-Lens-Count: 2", "Fast-Lens-Count: 3")
        changed = changed.replace(
            "Fast-Lenses: correctness, error_handling",
            "Fast-Lenses: correctness, security, data_integrity")
        changed = changed.replace("Fast-Reason: production outage", "Fast-Reason: elevated scope")
        plan_path.write_text(changed, encoding="utf-8")

        reopened = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L3",
                            "--lens-count", "3", "--reason", "elevated scope")
        self.assertEqual(reopened.returncode, 2)
        self.assertIn("does not match its audit snapshot", reopened.stderr)

    def test_pending_plan_recovers_the_single_matching_active_audit_run(self):
        import fast_cycle_audit as fa

        run_id = "fc-123456789abc"
        plan_path = Path(self.root, "plan_docs", "00-base_plan", "hotfix.md")
        content = plan_path.read_text(encoding="utf-8")
        bound = bind_run_id(content, run_id)
        from sage.profile_layers import load_profile_layers
        profile = load_profile_layers(
            str(Path(self.root, "sage", "project-profile.yaml"))).effective
        profile_payload = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        fa.open_fast(
            self.root, cycle_stem="hotfix", actual_risk="L3", fast_review_level="L2",
            reason="production outage", minimum_rounds=1,
            lenses=["correctness", "error_handling"],
            profile_hash=__import__("hashlib").sha256(profile_payload.encode("utf-8")).hexdigest(),
            plan_hash_open=__import__("hashlib").sha256(bound.encode("utf-8")).hexdigest(),
            run_id=run_id)

        recovered = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L2",
                              "--lens-count", "2", "--reason", "production outage")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(recovered.stdout.strip(), run_id)
        self.assertIn(f"Fast-Audit-Run: {run_id}", plan_path.read_text(encoding="utf-8"))
        self.assertEqual(len(fa.read_records(self.root)), 1)

    def test_plan_binding_failure_aborts_the_new_audit_run(self):
        import fast_cycle_audit as fa
        from sage.commands import fast_cycle

        args = SimpleNamespace(
            root=self.root, stem="hotfix", level="L2", lens_count=2,
            reason="production outage")
        with (mock.patch.object(fast_cycle.overlay_common, "write_text_lf",
                                side_effect=OSError("injected write failure")),
              mock.patch("builtins.print")):
            self.assertEqual(fast_cycle._run_open(args), 2)
        plan_text = Path(self.root, "plan_docs", "00-base_plan", "hotfix.md").read_text(
            encoding="utf-8")
        self.assertIn("Fast-Audit-Run: pending", plan_text)
        summary = fa.audit_summary(self.root)
        self.assertEqual(summary["active"], [])
        self.assertEqual(len(summary["runs"]), 1)
        self.assertEqual(next(iter(summary["runs"].values()))["result"], "ABORTED")

    def test_recovery_plan_binding_serializes_a_concurrent_abort(self):
        import fast_cycle_audit as fa
        from sage.commands import fast_cycle
        from sage.profile_layers import load_profile_layers

        run_id = "fc-123456789abc"
        plan_path = Path(self.root, "plan_docs", "00-base_plan", "hotfix.md")
        content = plan_path.read_text(encoding="utf-8")
        bound = bind_run_id(content, run_id)
        profile = load_profile_layers(
            str(Path(self.root, "sage", "project-profile.yaml"))).effective
        payload = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        fa.open_fast(
            self.root, cycle_stem="hotfix", actual_risk="L3", fast_review_level="L2",
            reason="production outage", minimum_rounds=1,
            lenses=["correctness", "error_handling"],
            profile_hash=__import__("hashlib").sha256(payload.encode("utf-8")).hexdigest(),
            plan_hash_open=__import__("hashlib").sha256(bound.encode("utf-8")).hexdigest(),
            run_id=run_id)
        entered_write = threading.Event()
        release_write = threading.Event()
        original_write = fast_cycle.overlay_common.write_text_lf

        def paused_write(path, text):
            entered_write.set()
            self.assertTrue(release_write.wait(timeout=5))
            return original_write(path, text)

        open_args = SimpleNamespace(
            root=self.root, stem="hotfix", level="L2", lens_count=2,
            reason="production outage")
        abort_args = SimpleNamespace(root=self.root, run_id=run_id, reason="cancelled")
        results = {}
        with (mock.patch.object(fast_cycle.overlay_common, "write_text_lf", side_effect=paused_write),
              mock.patch("builtins.print")):
            open_thread = threading.Thread(
                target=lambda: results.setdefault("open", fast_cycle._run_open(open_args)))
            abort_thread = threading.Thread(
                target=lambda: results.setdefault("abort", fast_cycle._run_abort(abort_args)))
            open_thread.start()
            self.assertTrue(entered_write.wait(timeout=5))
            abort_thread.start()
            abort_thread.join(timeout=0.2)
            self.assertTrue(abort_thread.is_alive(), "abort must wait for plan recovery binding")
            release_write.set()
            open_thread.join(timeout=5)
            abort_thread.join(timeout=5)
        self.assertEqual(results, {"open": 0, "abort": 0})
        self.assertIn(f"Fast-Audit-Run: {run_id}", plan_path.read_text(encoding="utf-8"))
        self.assertEqual(fa.audit_summary(self.root)["runs"][run_id]["result"], "ABORTED")

    def test_missing_reason_or_disabled_profile_writes_nothing(self):
        missing = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L2",
                            "--lens-count", "2")
        self.assertEqual(missing.returncode, 2)
        self.assertFalse(Path(self.root, ".sage", "fast_cycle.jsonl").exists())

        profile_path = Path(self.root, "sage", "project-profile.yaml")
        profile_path.write_text(profile_path.read_text(encoding="utf-8").replace("enabled: true", "enabled: false"),
                                encoding="utf-8")
        disabled = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L2",
                             "--lens-count", "2", "--reason", "urgent")
        self.assertEqual(disabled.returncode, 2)
        self.assertFalse(Path(self.root, ".sage", "fast_cycle.jsonl").exists())

    def test_active_run_blocks_cycle_clear_and_stem_switch_until_abort(self):
        opened = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L2",
                           "--lens-count", "2", "--reason", "production outage")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        run_id = opened.stdout.strip()
        blocked_clear = self._run("cycle", "clear")
        self.assertEqual(blocked_clear.returncode, 2)
        self.assertIn("Fast", blocked_clear.stderr)
        blocked_set = self._run("cycle", "set", "another")
        self.assertEqual(blocked_set.returncode, 2)
        self.assertIn("Fast", blocked_set.stderr)
        aborted = self._run("fast-cycle", "abort", "--run-id", run_id, "--reason", "scope cancelled")
        self.assertEqual(aborted.returncode, 0, aborted.stderr)
        cleared = self._run("cycle", "clear")
        self.assertEqual(cleared.returncode, 0, cleared.stderr)

    def test_review_requires_loop_lens_receipts_and_close_rejects_plan_drift(self):
        opened = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L2",
                           "--lens-count", "2", "--reason", "production outage")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        fast_run = opened.stdout.strip()
        plan_path = Path(self.root, "plan_docs", "00-base_plan", "hotfix.md")
        plan_path.write_text(plan_path.read_text(encoding="utf-8").replace(
            "Status: PENDING — implementation not started", "Status: COMPLETE\nEvidence: A1 PASS").replace(
            "- [ ] hotfix behavior is verified", "- [x] hotfix behavior is verified"),
            encoding="utf-8")
        Path(self.root, "plan_docs", "05-expert-review").mkdir(parents=True)
        review_path = Path(self.root, "plan_docs", "05-expert-review", "hotfix.md")

        import loop_audit as la
        loop_run = la.open_loop(self.root, "L3", run_id="rl-fast-1", cycle_stem="hotfix",
                                lenses=["correctness", "error_handling"])
        la.record_round(self.root, loop_run, 1, 0, 0, 0,
                        lens_receipts=["correctness", "error_handling"])
        la.close_loop(self.root, loop_run, "APPROVED", "DRY", 1)
        review_path.write_text(
            f"# Review\n\n```text\nFast-Run: {fast_run}\nLoop-Run: {loop_run}\n"
            "Final Status: APPROVED\n```\n",
            encoding="utf-8")
        fenced = self._run("fast-cycle", "review", "--run-id", fast_run,
                           "--loop-run-id", loop_run)
        self.assertEqual(fenced.returncode, 2)
        self.assertIn("outside Markdown fences", fenced.stderr)
        review_path.write_text(
            f"# Review\n\nFast-Run: {fast_run}\nLoop-Run: {loop_run}\nFinal Status: APPROVED\n",
            encoding="utf-8")
        reviewed = self._run("fast-cycle", "review", "--run-id", fast_run,
                             "--loop-run-id", loop_run)
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)

        Path(self.root, "plan_docs", "06-report").mkdir(parents=True)
        report_path = Path(self.root, "plan_docs", "06-report", "hotfix.md")
        report_path.write_text(
            f"# Report\n\nFast-Run: {fast_run}\nLoop-Run: {loop_run}\nFinal Status: APPROVED\n",
            encoding="utf-8")
        plan_path.write_text(plan_path.read_text(encoding="utf-8") + "\npost-review correction\n",
                             encoding="utf-8")
        drifted = self._run("fast-cycle", "close", "--run-id", fast_run)
        self.assertEqual(drifted.returncode, 2)
        self.assertIn("changed", drifted.stderr)

        loop_run2 = la.open_loop(self.root, "L3", run_id="rl-fast-2", cycle_stem="hotfix",
                                 lenses=["correctness", "error_handling"])
        la.record_round(self.root, loop_run2, 1, 0, 0, 0,
                        lens_receipts=["correctness", "error_handling"])
        la.close_loop(self.root, loop_run2, "APPROVED", "DRY", 1)
        review_path.write_text(
            f"# Review\n\nFast-Run: {fast_run}\nLoop-Run: {loop_run2}\nFinal Status: APPROVED\n",
            encoding="utf-8")
        report_path.write_text(
            f"# Report\n\nFast-Run: {fast_run}\nLoop-Run: {loop_run2}\nFinal Status: APPROVED\n",
            encoding="utf-8")
        rereviewed = self._run("fast-cycle", "review", "--run-id", fast_run,
                               "--loop-run-id", loop_run2)
        self.assertEqual(rereviewed.returncode, 0, rereviewed.stderr)
        closed = self._run("fast-cycle", "close", "--run-id", fast_run)
        self.assertEqual(closed.returncode, 0, closed.stderr)

    def test_done_criteria_advisory_does_not_block_fast_review_or_close(self):
        self._set_done_mode("advisory")
        opened = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L2",
                           "--lens-count", "2", "--reason", "production outage")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        fast_run = opened.stdout.strip()
        plan_path = Path(self.root, "plan_docs", "00-base_plan", "hotfix.md")
        plan_path.write_text(plan_path.read_text(encoding="utf-8").replace(
            "Status: PENDING — implementation not started", "Status: COMPLETE\nEvidence: A1 PASS"),
            encoding="utf-8")

        Path(self.root, "plan_docs", "05-expert-review").mkdir(parents=True)
        review_path = Path(self.root, "plan_docs", "05-expert-review", "hotfix.md")
        import loop_audit as la
        loop_run = la.open_loop(self.root, "L3", run_id="rl-fast-advisory", cycle_stem="hotfix",
                                lenses=["correctness", "error_handling"])
        la.record_round(self.root, loop_run, 1, 0, 0, 0,
                        lens_receipts=["correctness", "error_handling"])
        la.close_loop(self.root, loop_run, "APPROVED", "DRY", 1)
        evidence = (f"Fast-Run: {fast_run}\nLoop-Run: {loop_run}\n"
                    "Final Status: APPROVED\n")
        review_path.write_text(evidence, encoding="utf-8")

        reviewed = self._run("fast-cycle", "review", "--run-id", fast_run,
                             "--loop-run-id", loop_run)
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
        self.assertIn("Done Criteria advisory at review", reviewed.stderr)

        Path(self.root, "plan_docs", "06-report").mkdir(parents=True)
        Path(self.root, "plan_docs", "06-report", "hotfix.md").write_text(
            evidence, encoding="utf-8")
        closed = self._run("fast-cycle", "close", "--run-id", fast_run)
        self.assertEqual(closed.returncode, 0, closed.stderr)
        self.assertIn("Done Criteria advisory at close", closed.stderr)

    def test_show_can_derive_one_project_dashboard_in_explicit_vault(self):
        opened = self._run("fast-cycle", "open", "--stem", "hotfix", "--level", "L2",
                           "--lens-count", "2", "--reason", "production outage")
        run_id = opened.stdout.strip()
        self.assertEqual(self._run("fast-cycle", "abort", "--run-id", run_id,
                                   "--reason", "cancelled").returncode, 0)
        vault = Path(self.root, "vault")
        shown = self._run("fast-cycle", "show", "--vault", str(vault))
        self.assertEqual(shown.returncode, 0, shown.stderr)
        notes = list(vault.rglob("*.md"))
        self.assertEqual(len(notes), 1)
        text = notes[0].read_text(encoding="utf-8")
        self.assertIn(run_id, text)
        self.assertIn(".sage/fast_cycle.jsonl", text)


class TestFastSourceGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        hooks = os.path.join(REPO, "scripts", "sage_harness", "hooks")
        sys.path.insert(0, hooks)
        import pre_implementation_gate_core
        cls.core = pre_implementation_gate_core

    def _profile(self):
        return {
            "risk": {"l2_path_globs": ["src/**"]},
            "pdca": {
                "enabled": True,
                "phases": [
                    {"id": "00", "glob": "plan_docs/00-base_plan/**/*.md"},
                    {"id": "01", "glob": "plan_docs/01-plan/**/*.md"},
                    {"id": "02", "glob": "plan_docs/02-design/**/*.md"},
                    {"id": "03", "glob": "plan_docs/03-implementation/**/*.md"},
                ],
                "pre_implementation_required": {"L2": ["00", "01", "02", "03"]},
                "fast_cycle": _valid_fast(),
            },
        }

    def _event(self):
        return {"changes": [{"path": "src/app.py", "content": "+change"}],
                "cycle_stem": "hotfix", "cycle_stem_origin": "cli", "declared_max": None,
                "branch": "main"}

    def _snapshot(self, active=True, chain_ok=True):
        content = TestFastCLI._plan().replace("Fast-Audit-Run: pending", "Fast-Audit-Run: fc-123456789abc")
        state = {"cycle_stem": "hotfix", "terminal": False, "clean": True,
                 "chain_ok": chain_ok, "seq_ok": True, "actual_risk": "L3",
                 "fast_review_level": "L2", "minimum_rounds": 1,
                 "lenses": ["correctness", "error_handling"], "reason": "production outage"}
        return {
            "plan_files": [{"path": "plan_docs/00-base_plan/hotfix.md", "content": content}],
            "phase_docs": {"00": [{"path": "plan_docs/00-base_plan/hotfix.md", "content": content}]},
            "fast_cycle_audit": {"file_ok": True, "file_issues": [],
                                 "active": ["fc-123456789abc"] if active else [],
                                 "runs": {"fc-123456789abc": state} if active else {}},
        }

    def test_open_composite_plan_satisfies_virtual_preimplementation_phases(self):
        decision = self.core.decide(self._event(), self._profile(), self._snapshot(), None)
        self.assertEqual(decision["exit_code"], 0, decision)
        self.assertEqual(decision["message_key"], "warn_fast_cycle")

    def test_missing_or_damaged_fast_audit_blocks(self):
        missing = self.core.decide(self._event(), self._profile(), self._snapshot(active=False), None)
        self.assertEqual(missing["exit_code"], 2)
        self.assertEqual(missing["message_key"], "block_fast_cycle_audit")
        damaged = self.core.decide(self._event(), self._profile(), self._snapshot(chain_ok=False), None)
        self.assertEqual(damaged["exit_code"], 2)
        self.assertEqual(damaged["message_key"], "block_fast_cycle_audit")


class TestFastAuthority(unittest.TestCase):
    def test_server_uses_same_composite_parser_for_virtual_phases(self):
        from sage import ci_authority
        content = TestFastCLI._plan()
        docs = {"00": [{"path": "plan_docs/00-base_plan/hotfix.md", "content": content}],
                "01": [], "02": [], "03": [], "04": [], "05": []}
        expanded, issues = ci_authority._expand_fast_phase_docs(docs)
        self.assertEqual(issues, [])
        for phase in ("01", "02", "03", "04"):
            self.assertEqual(len(expanded[phase]), 1)
            self.assertTrue(expanded[phase][0]["virtual_fast"])
            self.assertIn("Cycle-Stem: `hotfix`", expanded[phase][0]["content"])

    def test_server_verifies_committed_fast_and_loop_audit_bindings(self):
        from sage import ci_authority
        import fast_cycle_audit as fa
        import loop_audit as la
        with tempfile.TemporaryDirectory() as root:
            run_id = "fc-123456789abc"
            loop_id = "rl-server"
            content = TestFastCLI._plan().replace("Fast-Audit-Run: pending", f"Fast-Audit-Run: {run_id}")
            content = content.replace("Status: PENDING — implementation not started",
                                      "Status: COMPLETE\nEvidence: A1 PASS")
            plan_hash = __import__("hashlib").sha256(content.encode("utf-8")).hexdigest()
            la.open_loop(root, "L3", run_id=loop_id, cycle_stem="hotfix",
                         lenses=["correctness", "error_handling"])
            la.record_round(root, loop_id, 1, 0, 0, 0,
                            lens_receipts=["correctness", "error_handling"])
            la.close_loop(root, loop_id, "APPROVED", "DRY", 1)
            fa.open_fast(root, cycle_stem="hotfix", actual_risk="L3",
                         fast_review_level="L2", reason="production outage",
                         minimum_rounds=1, lenses=["correctness", "error_handling"],
                         profile_hash="p" * 64, plan_hash_open=plan_hash, run_id=run_id)
            receipts_payload = json.dumps(
                [{"iteration": 1, "lenses": ["correctness", "error_handling"]}],
                ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            receipts_hash = __import__("hashlib").sha256(receipts_payload.encode("utf-8")).hexdigest()
            fa.record_review(root, run_id, loop_run_id=loop_id, actual_risk="L3", rounds=1,
                             lens_receipts_hash=receipts_hash,
                             plan_hash_before_review=plan_hash, result="APPROVED")
            fa.close_fast(root, run_id, loop_run_id=loop_id, actual_risk="L3",
                          plan_hash_final=plan_hash, report_path="plan_docs/06-report/hotfix.md")
            selected = {
                "00": {"path": "plan_docs/00-base_plan/hotfix.md", "content": content},
                "05": {"path": "plan_docs/05-expert-review/hotfix.md",
                       "content": f"Fast-Run: {run_id}\nLoop-Run: {loop_id}\nFinal Status: APPROVED\n"},
            }
            request = {
                "fast_cycle_audit": Path(fa.audit_path(root)).read_text(encoding="utf-8"),
                "loop_audit": Path(la.audit_path(root)).read_text(encoding="utf-8"),
            }
            self.assertEqual(ci_authority._fast_evidence_reasons(request, selected, "hotfix"), [])
            selected["05"]["content"] = (
                f"```text\nFast-Run: {run_id}\nLoop-Run: {loop_id}\nFinal Status: APPROVED\n```\n")
            self.assertTrue(ci_authority._fast_evidence_reasons(request, selected, "hotfix"))
            selected["05"]["content"] = (
                f"Fast-Run: {run_id}\nLoop-Run: {loop_id}\nFinal Status: APPROVED\n")
            request["fast_cycle_audit"] = request["fast_cycle_audit"].replace("production outage", "hidden")
            self.assertTrue(ci_authority._fast_evidence_reasons(request, selected, "hotfix"))


class TestFastSkills(unittest.TestCase):
    def test_fast_skills_are_core_assets_with_expected_delegation(self):
        from sage.commands import install
        ids = install.core_skill_ids()
        for skill_id in ("sage-cycle-fast", "sage-plan-fast", "sage-team-fast"):
            self.assertIn(skill_id, ids)
            render = Path(REPO, "templates", "core", "framework", ".claude", "skills",
                          skill_id, "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("CORE framework bootstrap asset", render)
        umbrella = Path(REPO, "templates", "core", "framework", ".claude", "skills",
                        "sage-cycle-fast", "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("sage-plan-fast", umbrella)
        self.assertIn("sage-team-fast", umbrella)
        self.assertNotIn("sage fast-cycle open", umbrella)

    def test_fast_profile_questions_have_exact_conversational_owners(self):
        init = Path(REPO, "templates", "core", "framework", ".claude", "skills",
                    "sage-init", "SKILL.md").read_text(encoding="utf-8")
        modify = Path(REPO, "templates", "core", "framework", ".claude", "skills",
                      "sage-profile-modify", "SKILL.md").read_text(encoding="utf-8")
        local = Path(REPO, "templates", "core", "framework", ".claude", "skills",
                     "sage-init-local", "SKILL.md").read_text(encoding="utf-8")
        for text in (init, modify):
            self.assertIn("pdca.fast_cycle", text)
            self.assertIn("minimum_rounds", text)
            self.assertIn("minimum_lenses", text)
            self.assertIn("fast_cycle_dashboard", text)
        self.assertNotIn("pdca.fast_cycle", local)

if __name__ == "__main__":
    unittest.main(verbosity=2)
