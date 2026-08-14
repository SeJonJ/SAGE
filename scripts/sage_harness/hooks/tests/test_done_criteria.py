#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
HOOKS = os.path.join(REPO, "scripts", "sage_harness", "hooks")
if HOOKS not in sys.path:
    sys.path.insert(0, HOOKS)
RUNTIME = os.path.join(HOOKS, "runtime")
if RUNTIME not in sys.path:
    sys.path.insert(0, RUNTIME)

from sage.done_criteria_contract import parse_done_criteria, phase00_text_hash  # noqa: E402
import sage.profile_validate as profile_validate  # noqa: E402
import pre_implementation_gate_core as pre_gate  # noqa: E402
import hook_runtime  # noqa: E402
import loop_audit  # noqa: E402


def standard(items, *, revision=1, log=""):
    return (
        "# Plan\n\nCycle-Stem: `feature`\nRisk Level: L3\n"
        f"Done-Criteria-Revision: {revision}\n\n"
        "## 5. Done Criteria\n\n"
        f"{items}\n\n"
        f"{log}"
    )


def fast(items, *, revision=1, log=""):
    return (
        "# Fast\nCycle-Stem: `feature`\nCycle-Mode: FAST\nRisk Level: L3\n"
        f"Done-Criteria-Revision: {revision}\n\n"
        "## Phase 00\n\n### Done Criteria\n"
        f"{items}\n\n{log}\n"
        "### Document Mapping (Checklist)\n- [x] Phase 00 context complete\n\n"
        "## Phase 01\n\n| ID | Requirement |\n|---|---|\n| A1 | x |\n\n"
        "## Phase 02\n\ndesign\n\n"
        "## Phase 03\n\nA1\n\n"
        "## Phase 04\n\nStatus: PENDING — implementation not started\n"
    )


class DoneCriteriaParserTests(unittest.TestCase):
    def test_standard_three_states_and_progress(self):
        result = parse_done_criteria(standard(
            "- [ ] implementation\n"
            "- [x] tests\n"
            "- [~] mobile UI (N/A: server-only change)"), mode="standard")

        self.assertEqual(result.status, "valid")
        self.assertEqual(result.revision, 1)
        self.assertEqual([item.state for item in result.items], ["pending", "done", "na"])
        self.assertEqual([item.text for item in result.unresolved], ["implementation"])

    def test_reason_after_pending_does_not_resolve_it(self):
        result = parse_done_criteria(
            standard("- [ ] implementation (reason: later)"), mode="standard")
        self.assertEqual([item.state for item in result.unresolved], ["pending"])

    def test_reasonless_na_and_unknown_marker_are_invalid(self):
        result = parse_done_criteria(
            standard("- [~] mobile UI\n- [?] unknown"), mode="standard")
        self.assertEqual(result.status, "invalid")
        self.assertTrue(any("N/A" in issue for issue in result.issues))
        self.assertTrue(any("unknown task state" in issue for issue in result.issues))

    def test_only_exact_section_is_scanned_and_fences_comments_are_ignored(self):
        content = standard("- [x] real") + (
            "\n## Other\n- [ ] unrelated\n"
            "```markdown\n## 5. Done Criteria\n- [ ] fenced\n```\n"
            "<!--\n## 5. Done Criteria\n- [ ] commented\n-->\n"
        )
        result = parse_done_criteria(content, mode="standard")
        self.assertEqual(result.status, "valid")
        self.assertEqual([item.text for item in result.items], ["real"])

    def test_missing_duplicate_empty_and_duplicate_items_are_invalid(self):
        cases = (
            "Done-Criteria-Revision: 1\n## Other\n- [x] x\n",
            standard("- [x] x") + "\n## 5. Done Criteria\n- [x] y\n",
            standard(""),
            standard("- [x] Same   item\n- [ ] same item"),
        )
        for content in cases:
            with self.subTest(content=content):
                self.assertEqual(parse_done_criteria(content, mode="standard").status, "invalid")

    def test_task_like_alternate_bullets_are_not_silently_ignored(self):
        for malformed in ("* [ ] hidden", "+ [x] hidden", "1. [ ] hidden", "-[ ] hidden"):
            with self.subTest(malformed=malformed):
                result = parse_done_criteria(
                    standard(f"- [x] visible\n{malformed}"), mode="standard")
                self.assertEqual(result.status, "invalid")
                self.assertTrue(any("task item must use" in issue for issue in result.issues))

    def test_revision_two_requires_complete_latest_log(self):
        good_log = (
            "## 6. Done Criteria Revision Log\n\n"
            "### Revision 2\n"
            "- Changed-At: Phase 04\n"
            "- Reason: missing cancellation invariant\n"
            "- Affected-Phases: 02, 03, 04, 05\n"
            "- Summary: add the invariant and rerun verification\n"
        )
        result = parse_done_criteria(standard("- [ ] x", revision=2, log=good_log), mode="standard")
        self.assertEqual(result.status, "valid")
        self.assertEqual(result.latest_revision.affected_phases, ("02", "03", "04", "05"))

        bad = good_log.replace("02, 03, 04, 05", "03, 02, 03, 06")
        result = parse_done_criteria(standard("- [ ] x", revision=2, log=bad), mode="standard")
        self.assertEqual(result.status, "invalid")
        self.assertTrue(any("Affected-Phases" in issue for issue in result.issues))

    def test_revision_declaration_is_exactly_one_positive_integer(self):
        for declaration in ("", "Done-Criteria-Revision: 0\n", "Done-Criteria-Revision: true\n"):
            content = standard("- [x] x").replace("Done-Criteria-Revision: 1\n", declaration)
            with self.subTest(declaration=declaration):
                self.assertEqual(parse_done_criteria(content, mode="standard").status, "invalid")
        duplicate = standard("- [x] x") + "\nDone-Criteria-Revision: 1\n"
        self.assertEqual(parse_done_criteria(duplicate, mode="standard").status, "invalid")

    def test_fast_uses_done_criteria_inside_phase00_only(self):
        result = parse_done_criteria(fast("- [ ] fast result"), mode="fast")
        self.assertEqual(result.status, "valid")
        self.assertEqual([item.text for item in result.unresolved], ["fast result"])

        missing = fast("- [ ] fast result").replace("### Done Criteria", "### Completion")
        self.assertEqual(parse_done_criteria(missing, mode="fast").status, "invalid")

    def test_fast_accepts_shipped_phase_heading_suffixes(self):
        content = fast("- [ ] fast result")
        for phase, suffix in (("00", "Base Plan"), ("01", "Requirements"),
                              ("02", "Design"), ("03", "Implementation"),
                              ("04", "Analyze")):
            content = content.replace(f"## Phase {phase}", f"## Phase {phase} — {suffix}")
        result = parse_done_criteria(content, mode="fast")
        self.assertEqual(result.status, "valid", result.issues)
        self.assertEqual([item.text for item in result.unresolved], ["fast result"])

    def test_fast_parser_failure_is_not_reinterpreted_as_standard(self):
        malformed = fast("- [x] x").replace("## Phase 02", "## Broken 02")
        result = parse_done_criteria(malformed, mode="fast")
        self.assertEqual(result.status, "invalid")
        self.assertTrue(any("Fast Plan" in issue for issue in result.issues))

    def test_hash_normalizes_only_line_endings(self):
        self.assertEqual(phase00_text_hash("a\r\nb\r"), phase00_text_hash("a\nb\n"))
        self.assertNotEqual(phase00_text_hash("a\nb\n"), phase00_text_hash("a\nb \n"))
        self.assertNotEqual(phase00_text_hash("- [ ] x\n"), phase00_text_hash("- [x] x\n"))
        self.assertRegex(phase00_text_hash("x"), r"^sha256:[0-9a-f]{64}$")


class DoneCriteriaProfileTests(unittest.TestCase):
    def test_schema_accepts_only_three_done_criteria_modes(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        schema = json.loads(Path(REPO, "schema", "profile.schema.json").read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        for mode in ("off", "advisory", "enforce"):
            self.assertTrue(validator.is_valid({"pdca": {"base_plan": {"done_criteria_gate": mode}}}))
        for value in (True, "warn", "", 1, {"mode": "enforce"}):
            self.assertFalse(validator.is_valid({"pdca": {"base_plan": {"done_criteria_gate": value}}}))

    def test_manual_validator_matches_schema_without_jsonschema(self):
        for mode in ("off", "advisory", "enforce"):
            with mock.patch.object(profile_validate, "_schema_issues", return_value=[]):
                issues = profile_validate.validate_profile(
                    {"pdca": {"base_plan": {"done_criteria_gate": mode}}}, REPO)
            self.assertFalse(any(severity == "FAIL"
                                 and getattr(message, "code", "").startswith("validate.base_plan")
                                 for severity, message in issues))
        for value in (True, "warn", "", 1, {"mode": "enforce"}):
            with self.subTest(value=value), mock.patch.object(
                    profile_validate, "_schema_issues", return_value=[]):
                issues = profile_validate.validate_profile(
                    {"pdca": {"base_plan": {"done_criteria_gate": value}}}, REPO)
            self.assertTrue(any(severity == "FAIL"
                                and getattr(message, "code", "") == "validate.done_criteria_gate_invalid"
                                for severity, message in issues))

    def test_unknown_base_plan_key_fails_without_schema(self):
        with mock.patch.object(profile_validate, "_schema_issues", return_value=[]):
            issues = profile_validate.validate_profile(
                {"pdca": {"base_plan": {"done_criteria_gte": "enforce"}}}, REPO)
        self.assertTrue(any(severity == "FAIL"
                            and getattr(message, "code", "") == "validate.base_plan_unknown_keys"
                            and "done_criteria_gte" in message.arguments.get("keys", [])
                            for severity, message in issues))

    def test_project_profile_template_uses_advisory_for_new_projects(self):
        import yaml
        profile = yaml.safe_load(Path(REPO, "templates", "project-profile.yaml").read_text(encoding="utf-8"))
        self.assertEqual(profile["pdca"]["base_plan"]["done_criteria_gate"], "advisory")


def gate_profile(mode="enforce"):
    return {"pdca": {"enabled": True,
                     "phases": [
                         {"id": phase, "glob": f"plan_docs/{phase}-*/**/*.md"}
                         for phase in ("00", "01", "02", "03", "04", "05", "06")
                     ],
                     "report_phase": "06", "approve_phase": "05", "approve_marker": "APPROVED",
                     "base_plan": {"done_criteria_gate": mode}}}


def phase_event(phase):
    return {"branch": "feature", "changes": [
        {"path": f"plan_docs/{phase}-x/feature.md", "content": "Cycle-Stem: `feature`\nwrite"}
    ]}


def gate_snapshot(phase00, *, phase02=None, phase03=None, phase04=None,
                  phase05=None, loop_run=None):
    docs = {"00": [{"path": "plan_docs/00-base_plan/feature.md", "content": phase00}]}
    for phase, content in (("02", phase02), ("03", phase03), ("04", phase04), ("05", phase05)):
        if content is not None:
            docs[phase] = [{"path": f"plan_docs/{phase}-x/feature.md", "content": content}]
    runs = {"run-new": loop_run} if loop_run is not None else {}
    return {"phase_docs": docs, "plan_files": docs["00"],
            "loop_audit": {"runs": runs, "file_ok": True, "has_any_records": bool(runs)}}


class DoneCriteriaGateTests(unittest.TestCase):
    def test_off_skips_all_done_criteria_checks(self):
        result = pre_gate._done_criteria_gate(
            phase_event("06"), gate_profile("off"), gate_snapshot("malformed"))
        self.assertIsNone(result)

    def test_phase03_allows_valid_unresolved_with_progress_warning(self):
        plan = standard("- [ ] implementation\n- [x] design")
        result = pre_gate._done_criteria_gate(
            phase_event("03"), gate_profile(), gate_snapshot(plan))
        self.assertEqual(result["status"], "warn")
        self.assertEqual(result["message_key"], "warn_done_criteria_progress")
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["total"], 2)

    def test_invalid_structure_blocks_enforce_and_warns_advisory(self):
        malformed = "Cycle-Stem: `feature`\nRisk Level: L3\n"
        blocked = pre_gate._done_criteria_gate(
            phase_event("03"), gate_profile("enforce"), gate_snapshot(malformed))
        warned = pre_gate._done_criteria_gate(
            phase_event("03"), gate_profile("advisory"), gate_snapshot(malformed))
        self.assertEqual((blocked["status"], blocked["exit_code"]), ("block", 2))
        self.assertEqual((warned["status"], warned["exit_code"]), ("warn", 0))

    def test_phase00_only_repair_is_never_self_blocked(self):
        result = pre_gate._done_criteria_gate(
            phase_event("00"), gate_profile(), gate_snapshot("malformed"))
        self.assertIsNone(result)

    def test_phase00_and_later_phase_cannot_share_one_write(self):
        plan = standard("- [ ] implementation")
        event = {"branch": "feature", "changes": [
            {"path": "plan_docs/00-base_plan/feature.md", "content": plan},
            {"path": "plan_docs/03-x/feature.md", "content": "Cycle-Stem: `feature`\n"},
        ]}

        result = pre_gate._done_criteria_gate(
            event, gate_profile(), gate_snapshot(plan))
        advisory = pre_gate._done_criteria_gate(
            event, gate_profile("advisory"), gate_snapshot(plan))

        self.assertEqual(result["status"], "block")
        self.assertEqual(result["message_key"], "block_phase00_mixed_evidence")
        self.assertEqual((advisory["status"], advisory["exit_code"]), ("warn", 0))
        self.assertEqual(advisory["message_key"], "warn_phase00_mixed_evidence")

    def test_revision_requires_affected_prior_phase_to_be_refreshed(self):
        log = (
            "## 6. Done Criteria Revision Log\n\n### Revision 2\n"
            "- Changed-At: Phase 03\n- Reason: missing invariant\n"
            "- Affected-Phases: 02, 03, 04, 05\n- Summary: rerun design onward\n"
        )
        plan = standard("- [ ] implementation", revision=2, log=log)
        stale = pre_gate._done_criteria_gate(
            phase_event("03"), gate_profile(),
            gate_snapshot(plan, phase02="Cycle-Stem: `feature`\nDone-Criteria-Revision: 1\n"))
        self.assertEqual(stale["message_key"], "block_stale_done_criteria_revision")

        current = pre_gate._done_criteria_gate(
            phase_event("03"), gate_profile(),
            gate_snapshot(plan, phase02="Cycle-Stem: `feature`\nDone-Criteria-Revision: 2\n"))
        self.assertEqual(current["message_key"], "warn_done_criteria_progress")

    def test_report_blocks_unresolved_in_enforce(self):
        result = pre_gate._done_criteria_gate(
            phase_event("06"), gate_profile(), gate_snapshot(standard("- [ ] implementation")))
        self.assertEqual(result["message_key"], "block_report_without_done_criteria")
        self.assertEqual(result["exit_code"], 2)

    def test_report_requires_current_phase00_hash_in_phase05_and_loop(self):
        plan = standard("- [x] implementation")
        digest = phase00_text_hash(plan)
        review = ("Cycle-Stem: `feature`\nDone-Criteria-Revision: 1\n"
                  "Final Status: APPROVED\nLoop-Run: run-new\n"
                  f"Phase00-Hash: {digest}\n")
        loop = {"closed": True, "result": "APPROVED", "clean": True,
                "seq_ok": True, "chain_ok": True, "phase00_hash": digest}
        ok = pre_gate._done_criteria_gate(
            phase_event("06"), gate_profile(), gate_snapshot(plan, phase05=review, loop_run=loop))
        self.assertIsNone(ok)

        changed = plan + "\n"
        stale = pre_gate._done_criteria_gate(
            phase_event("06"), gate_profile(), gate_snapshot(changed, phase05=review, loop_run=loop))
        self.assertEqual(stale["message_key"], "block_stale_done_criteria_approval")

    def test_report_hash_binding_requires_strict_approved_loop_evidence(self):
        plan = standard("- [x] implementation")
        digest = phase00_text_hash(plan)
        review = ("Cycle-Stem: `feature`\nDone-Criteria-Revision: 1\n"
                  "Final Status: APPROVED\nLoop-Run: run-new\n"
                  f"Phase00-Hash: {digest}\n")
        valid = {"closed": True, "result": "APPROVED", "clean": True,
                 "seq_ok": True, "chain_ok": True, "phase00_hash": digest}
        for field, value in (("closed", False), ("result", "BLOCKED"), ("clean", False),
                             ("seq_ok", False), ("chain_ok", False)):
            with self.subTest(field=field):
                run = dict(valid, **{field: value})
                result = pre_gate._done_criteria_gate(
                    phase_event("06"), gate_profile(),
                    gate_snapshot(plan, phase05=review, loop_run=run))
                self.assertEqual(result["message_key"], "block_stale_done_criteria_approval")
        snapshot = gate_snapshot(plan, phase05=review, loop_run=valid)
        snapshot["loop_audit"]["file_ok"] = False
        result = pre_gate._done_criteria_gate(
            phase_event("06"), gate_profile(), snapshot)
        self.assertEqual(result["message_key"], "block_stale_done_criteria_approval")

    def test_real_decide_entrypoint_invokes_progress_gate(self):
        plan = standard("- [ ] implementation")
        decision = pre_gate.decide(
            phase_event("03"), gate_profile(), gate_snapshot(plan), strategy_result=None)
        self.assertEqual(decision["message_key"], "warn_done_criteria_progress")
        self.assertEqual(decision["cycle_stem"], "feature")

    def test_enforce_blocks_cannot_use_generic_override(self):
        expected = {
            "block_invalid_done_criteria",
            "block_phase00_mixed_evidence",
            "block_report_without_done_criteria",
            "block_stale_done_criteria_revision",
            "block_stale_done_criteria_approval",
        }
        self.assertTrue(expected.issubset(hook_runtime._NON_OVERRIDABLE_BLOCKS))


class DoneCriteriaReviewLoopTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        Path(self.root, "sage").mkdir()
        Path(self.root, "plan_docs", "00-base_plan").mkdir(parents=True)
        Path(self.root, "plan_docs", "02-design").mkdir(parents=True)
        Path(self.root, "plan_docs", "05-expert-review").mkdir(parents=True)
        Path(self.root, "sage", "project-profile.yaml").write_text(
            "pdca:\n"
            "  enabled: true\n"
            "  phases:\n"
            "    - { id: \"00\", glob: \"plan_docs/00-base_plan/**/*.md\" }\n"
            "    - { id: \"02\", glob: \"plan_docs/02-design/**/*.md\" }\n"
            "    - { id: \"05\", glob: \"plan_docs/05-expert-review/**/*.md\" }\n"
            "  base_plan:\n"
            "    done_criteria_gate: enforce\n"
            "  review_loop:\n"
            "    enabled: true\n",
            encoding="utf-8")

    def _sage(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "sage", "review-loop", *args, "--root", self.root],
            cwd=REPO, capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": REPO})

    def _open_and_round(self, run_id="rl-done-criteria"):
        opened = self._sage("open", "--risk", "L3", "--run-id", run_id,
                            "--cycle-stem", "feature")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        rounded = self._sage("round", "--run-id", run_id, "--iteration", "1",
                             "--found", "0", "--survived", "0", "--accepted", "0")
        self.assertEqual(rounded.returncode, 0, rounded.stderr)
        return run_id

    def test_approved_close_rejects_unresolved_done_criteria(self):
        Path(self.root, "plan_docs", "00-base_plan", "feature.md").write_text(
            standard("- [ ] implementation"), encoding="utf-8")
        run_id = self._open_and_round()

        closed = self._sage("close", "--run-id", run_id, "--result", "APPROVED",
                            "--reason", "DRY", "--iterations", "1")

        self.assertEqual(closed.returncode, 2)
        self.assertIn("Done Criteria", closed.stderr)
        self.assertIsNone(loop_audit.close_of(self.root, run_id))

    def test_approved_close_records_current_phase00_hash(self):
        content = standard("- [x] implementation")
        Path(self.root, "plan_docs", "00-base_plan", "feature.md").write_text(
            content, encoding="utf-8")
        run_id = self._open_and_round()

        closed = self._sage("close", "--run-id", run_id, "--result", "APPROVED",
                            "--reason", "DRY", "--iterations", "1")

        self.assertEqual(closed.returncode, 0, closed.stderr)
        expected = phase00_text_hash(content)
        self.assertIn(f"Phase00-Hash: {expected}", closed.stderr)
        self.assertEqual(loop_audit.close_of(self.root, run_id)["phase00_hash"], expected)
        self.assertEqual(loop_audit.audit_summary(self.root)["runs"][run_id]["phase00_hash"], expected)

    def test_approved_close_requires_affected_phase_current_revision(self):
        log = (
            "## 6. Done Criteria Revision Log\n\n### Revision 2\n"
            "- Changed-At: Phase 02\n- Reason: missing failure invariant\n"
            "- Affected-Phases: 02, 05\n- Summary: rerun design and review\n"
        )
        Path(self.root, "plan_docs", "00-base_plan", "feature.md").write_text(
            standard("- [x] implementation", revision=2, log=log), encoding="utf-8")
        Path(self.root, "plan_docs", "02-design", "feature.md").write_text(
            "Cycle-Stem: `feature`\nDone-Criteria-Revision: 1\n", encoding="utf-8")
        run_id = self._open_and_round("rl-stale-revision")

        stale = self._sage("close", "--run-id", run_id, "--result", "APPROVED",
                           "--reason", "DRY", "--iterations", "1")
        self.assertEqual(stale.returncode, 2)
        self.assertIn("affected Phase", stale.stderr)

        Path(self.root, "plan_docs", "02-design", "feature.md").write_text(
            "Cycle-Stem: `feature`\nDone-Criteria-Revision: 2\n", encoding="utf-8")
        stale_review = self._sage("close", "--run-id", run_id, "--result", "APPROVED",
                                  "--reason", "DRY", "--iterations", "1")
        self.assertEqual(stale_review.returncode, 2)
        self.assertIn("05: no phase document", stale_review.stderr)

        Path(self.root, "plan_docs", "05-expert-review", "feature.md").write_text(
            "Cycle-Stem: `feature`\nDone-Criteria-Revision: 2\n", encoding="utf-8")
        current = self._sage("close", "--run-id", run_id, "--result", "APPROVED",
                             "--reason", "DRY", "--iterations", "1")
        self.assertEqual(current.returncode, 0, current.stderr)

    def test_enforce_approved_close_requires_open_cycle_stem(self):
        Path(self.root, "plan_docs", "00-base_plan", "feature.md").write_text(
            standard("- [x] implementation"), encoding="utf-8")
        opened = self._sage("open", "--risk", "L3", "--run-id", "rl-no-stem")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        rounded = self._sage("round", "--run-id", "rl-no-stem", "--iteration", "1",
                             "--found", "0", "--survived", "0", "--accepted", "0")
        self.assertEqual(rounded.returncode, 0, rounded.stderr)
        closed = self._sage("close", "--run-id", "rl-no-stem", "--result", "APPROVED",
                            "--reason", "DRY", "--iterations", "1")
        self.assertEqual(closed.returncode, 2)
        self.assertIn("--cycle-stem", closed.stderr)

    def test_approved_close_rejects_phase_document_outside_root_via_symlink(self):
        outside = tempfile.mkdtemp()
        Path(outside, "feature.md").write_text(
            standard("- [x] external plan"), encoding="utf-8")
        link = Path(self.root, "plan_docs", "00-base_plan", "escaped")
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        run_id = self._open_and_round("rl-symlink-escape")

        closed = self._sage("close", "--run-id", run_id, "--result", "APPROVED",
                            "--reason", "DRY", "--iterations", "1")

        self.assertEqual(closed.returncode, 2)
        self.assertIn("escapes project root", closed.stderr)
        self.assertIsNone(loop_audit.close_of(self.root, run_id))


class DoneCriteriaDistributionTests(unittest.TestCase):
    def test_skills_and_init_expose_the_full_workflow(self):
        paths = {
            "plan": "templates/core/framework/.claude/skills/sage-plan/SKILL.md",
            "team": "templates/core/framework/.claude/skills/sage-team/SKILL.md",
            "review": "templates/core/framework/.claude/skills/sage-review/SKILL.md",
            "init": "templates/core/framework/.claude/skills/sage-init/SKILL.md",
        }
        texts = {name: Path(REPO, path).read_text(encoding="utf-8")
                 for name, path in paths.items()}
        self.assertIn("Done-Criteria-Revision: 1", texts["plan"])
        self.assertIn("every boundary", texts["team"])
        self.assertIn("--cycle-stem <stem>", texts["review"])
        self.assertIn("Phase00-Hash: sha256:...", texts["review"])
        self.assertIn("pdca.base_plan.done_criteria_gate", texts["init"])

    def test_user_docs_are_bilingual_and_suite_registers_contract(self):
        self.assertIn("완료 기준", Path(REPO, "README.md").read_text(encoding="utf-8"))
        self.assertIn("completion criteria", Path(REPO, "README.en.md").read_text(encoding="utf-8"))
        for korean, english in (("docs/profile-reference.md", "docs/profile-reference.en.md"),
                                ("docs/quickstart.md", "docs/quickstart.en.md"),
                                ("docs/troubleshooting.md", "docs/troubleshooting.en.md")):
            with self.subTest(korean=korean):
                self.assertIn("Done-Criteria-Revision", Path(REPO, korean).read_text(encoding="utf-8"))
                self.assertIn("Done-Criteria-Revision", Path(REPO, english).read_text(encoding="utf-8"))
        run_all = Path(REPO, "scripts", "sage_harness", "hooks", "tests", "run-all.sh").read_text(
            encoding="utf-8")
        self.assertIn('test_done_criteria.py', run_all)


if __name__ == "__main__":
    unittest.main()
