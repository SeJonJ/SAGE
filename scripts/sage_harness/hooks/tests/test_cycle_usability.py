#!/usr/bin/env python3
"""10-k cycle CLI usability contract: set/create, lifecycle wiring, and docs."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

HERE = Path(__file__).resolve().parent
HOOKS_DIR = HERE.parent
RUNTIME = HOOKS_DIR / "runtime"
PROJECT_ROOT = HOOKS_DIR.parents[2]
sys.path[:0] = [str(PROJECT_ROOT), str(RUNTIME), str(HOOKS_DIR)]

import cycle_state as cs  # noqa: E402
from sage.commands import cycle  # noqa: E402


STEM = "payment-fix"
PHASES = [
    {"id": "00", "glob": "plan_docs/00-base_plan/**/*.md"},
    {"id": "01", "glob": "plan_docs/01-plan/**/*.md"},
    {"id": "02", "glob": "plan_docs/02-design/**/*.md"},
    {"id": "03", "glob": "plan_docs/03-implementation/**/*.md"},
    {"id": "04", "glob": "plan_docs/04-analyze/**/*.md"},
    {"id": "05", "glob": "plan_docs/05-review/**/*.md"},
    {"id": "06", "glob": "plan_docs/06-report/**/*.md"},
]


def _mark_project(root):
    marker = Path(root, cs.MARKER_REL)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text('{"assets": {}}\n', encoding="utf-8")


def _profile(phases=None, **extra):
    data = {
        "project": {"name": "cycle-test"},
        "pdca": {
            "enabled": True,
            "phases": phases or PHASES,
            "pre_implementation_required": {"L2": ["00"]},
        },
        "risk": {
            "l0_pass_globs": ["*plan_docs/*"],
            "l2_path_globs": ["*src/*"],
        },
    }
    data.update(extra)
    return data


class CycleCliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        _mark_project(self.root)
        self.write_profiles()

    def write_profiles(self, yaml_data=None, json_data=None, *, compiled=True):
        profile_dir = self.root / "sage"
        profile_dir.mkdir(parents=True, exist_ok=True)
        yaml_data = _profile() if yaml_data is None else yaml_data
        (profile_dir / "project-profile.yaml").write_text(
            yaml.safe_dump(yaml_data, sort_keys=False), encoding="utf-8")
        json_path = profile_dir / "project-profile.json"
        if compiled:
            json_data = yaml_data if json_data is None else json_data
            json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        elif json_path.exists():
            json_path.unlink()

    def cli(self, *args, cwd=None, env=None):
        command = [sys.executable, "-m", "sage", "cycle", *args]
        child_env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT), "SAGE_CYCLE_STEM": ""}
        child_env.update(env or {})
        return subprocess.run(command, cwd=cwd or self.root, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, env=child_env)

    def cli_lang(self, lang, *args, cwd=None, env=None):
        command = [sys.executable, "-m", "sage", "--lang", lang, "cycle", *args]
        child_env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT), "SAGE_CYCLE_STEM": ""}
        child_env.update(env or {})
        return subprocess.run(command, cwd=cwd or self.root, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, env=child_env)

    def phase00(self, stem=STEM):
        return self.root / "plan_docs" / "00-base_plan" / f"{stem}.md"


class TestRenameAndGrammar(CycleCliCase):
    def test_use_is_a_hidden_migration_error_not_an_alias(self):
        proc = self.cli("use", STEM)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("sage cycle set", proc.stderr)
        self.assertNotIn("v0.9.80", proc.stderr)
        self.assertFalse(Path(cs.declaration_path(self.root)).exists())
        help_text = self.cli("--help").stdout
        self.assertNotIn("use <stem>", help_text)

    def test_set_rejects_missing_or_document_unsafe_stem(self):
        proc = self.cli("set")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("sage cycle set <stem>", proc.stderr)

        for stem in ("a\u0085b", "a\u2028b", "a\u2029b", "a\udcffb"):
            with self.subTest(stem=repr(stem)):
                proc = self.cli("set", stem)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertIn("cycle stem 형식 오류", proc.stderr)
                self.assertFalse(Path(cs.declaration_path(self.root)).exists())

    def test_option_grammar_rejects_every_meaningless_combination(self):
        cases = [
            (("show", "extra"), "sage cycle show"),
            (("clear", "extra"), "sage cycle clear"),
            (("set", STEM, "extra"), f"sage cycle set {STEM}"),
            (("show", "--create", "--risk", "L2"), "sage cycle show"),
            (("clear", "--path", "plan_docs"), "sage cycle clear"),
            (("set", STEM, "--risk", "L2"), "--create"),
            (("set", STEM, "--path", "plan_docs"), "--create"),
            (("set", STEM, "--create"), "--risk"),
            (("set", STEM, "--create", "--risk", "L0"), "L1|L2|L3"),
        ]
        for argv, correction in cases:
            with self.subTest(argv=argv):
                proc = self.cli(*argv)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertIn(correction, proc.stderr)

    def test_use_never_executes_create_options(self):
        proc = self.cli("use", STEM, "--create", "--risk", "L2")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("sage cycle set", proc.stderr)
        self.assertFalse(self.phase00().exists())


class TestCreateProfileAndPath(CycleCliCase):
    def test_create_derives_a_matching_phase00_path_and_declares_it(self):
        proc = self.cli("set", STEM, "--create", "--risk", "L2")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        path = self.phase00()
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(f"Cycle-Stem: `{STEM}`"), 1)
        self.assertEqual(text.count("Risk Level: L2"), 1)
        self.assertEqual(text.count("Done-Criteria-Revision: 1"), 1)
        self.assertEqual(text.count("## 5. Done Criteria"), 1)
        self.assertIn("- [ ] TODO: replace with a concrete completion criterion", text)
        self.assertNotIn("<L1|L2|L3>", text)
        self.assertEqual(cs.read_declaration(self.root)[0], STEM)

    def test_ambiguous_derived_glob_requires_path(self):
        phases = [{"id": "00", "glob": "*/plan_docs/00/**/*.md"}, *PHASES[1:]]
        self.write_profiles(_profile(phases), _profile(phases))
        proc = self.cli("set", STEM, "--create", "--risk", "L2")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--path", proc.stderr)
        self.assertFalse(self.phase00().exists())

    def test_path_is_a_directory_and_forces_the_stem_filename(self):
        phases = [{"id": "00", "glob": "plans/**/*.md"}, *PHASES[1:]]
        self.write_profiles(_profile(phases), _profile(phases))
        proc = self.cli("set", STEM, "--create", "--risk", "L1", "--path", "plans/new")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((self.root / "plans" / "new" / f"{STEM}.md").is_file())

    def test_path_rejects_absolute_parent_escape_and_glob_mismatch(self):
        for value in (str(self.root / "outside"), "../outside", "other"):
            with self.subTest(path=value):
                proc = self.cli("set", STEM, "--create", "--risk", "L2", "--path", value)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertFalse(self.phase00().exists())

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_path_rejects_a_symlink_escape(self):
        outside = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: outside.exists() and outside.rmdir())
        (self.root / "plan_docs").mkdir(exist_ok=True)
        os.symlink(outside, self.root / "plan_docs" / "00-base_plan")
        proc = self.cli("set", STEM, "--create", "--risk", "L2",
                        "--path", "plan_docs/00-base_plan")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("프로젝트 root", proc.stderr)
        self.assertFalse((outside / f"{STEM}.md").exists())

    def test_yaml_missing_or_broken_blocks_create_but_plain_set_survives(self):
        yaml_path = self.root / "sage" / "project-profile.yaml"
        for broken in (None, "pdca: ["):
            with self.subTest(broken=broken):
                if broken is None:
                    yaml_path.unlink(missing_ok=True)
                else:
                    yaml_path.write_text(broken, encoding="utf-8")
                create = self.cli("set", STEM, "--create", "--risk", "L2")
                self.assertEqual(create.returncode, 2)
                plain = self.cli("set", STEM)
                self.assertEqual(plain.returncode, 0, plain.stdout + plain.stderr)
                cs.clear_declaration(self.root)

    def test_duplicate_or_non_string_phase00_entries_are_not_ignored(self):
        invalid_sets = [
            [PHASES[0], {"id": "00", "glob": "other/**/*.md"}, *PHASES[1:]],
            [PHASES[0], {"id": "00", "glob": 42}, *PHASES[1:]],
        ]
        for phases in invalid_sets:
            with self.subTest(phases=phases[:2]):
                profile = _profile(phases)
                self.write_profiles(profile, profile)
                proc = self.cli("set", STEM, "--create", "--risk", "L2")
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertFalse(self.phase00().exists())

    def test_compiled_profile_absence_is_bootstrap_but_damage_or_glob_drift_blocks(self):
        self.write_profiles(compiled=False)
        absent = self.cli("set", STEM, "--create", "--risk", "L2")
        self.assertEqual(absent.returncode, 0, absent.stdout + absent.stderr)
        self.assertIn("sage generate --kind hook --write", absent.stdout + absent.stderr)

        cs.clear_declaration(self.root)
        self.phase00().unlink()
        json_path = self.root / "sage" / "project-profile.json"
        json_path.write_text("{", encoding="utf-8")
        damaged = self.cli("set", STEM, "--create", "--risk", "L2")
        self.assertEqual(damaged.returncode, 2)

        json_path.write_text(json.dumps(_profile([
            {"id": "00", "glob": "different/**/*.md"}, *PHASES[1:]
        ])), encoding="utf-8")
        drift = self.cli("set", STEM, "--create", "--risk", "L2")
        self.assertEqual(drift.returncode, 2)
        self.assertIn("sage generate --kind hook --write", drift.stderr)

    def test_unrelated_yaml_json_drift_is_not_a_cycle_create_blocker(self):
        yaml_profile = _profile(team={"core": ["leader"]})
        json_profile = _profile(team={"core": ["leader", "qa"]})
        self.write_profiles(yaml_profile, json_profile)
        proc = self.cli("set", STEM, "--create", "--risk", "L2")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestExistenceAndSuggestions(CycleCliCase):
    def _write_doc(self, rel, content):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_plain_set_warns_for_zero_or_ambiguous_valid_phase00_docs(self):
        zero = self.cli("set", STEM)
        self.assertEqual(zero.returncode, 0)
        self.assertIn(PHASES[0]["glob"], zero.stdout)
        cs.clear_declaration(self.root)

        a = self._write_doc("plan_docs/00-base_plan/a/payment-fix.md",
                            f"Cycle-Stem: `{STEM}`\nRisk Level: L2\n")
        b = self._write_doc("plan_docs/00-base_plan/b/payment-fix.md",
                            f"Cycle-Stem: `{STEM}`\nRisk Level: L2\n")
        ambiguous = self.cli("set", STEM)
        self.assertEqual(ambiguous.returncode, 0)
        self.assertIn(str(a.relative_to(self.root)), ambiguous.stdout)
        self.assertIn(str(b.relative_to(self.root)), ambiguous.stdout)

    def test_plain_set_has_no_missing_warning_for_exactly_one_valid_doc(self):
        self._write_doc("plan_docs/00-base_plan/payment-fix.md",
                        f"Cycle-Stem: `{STEM}`\nRisk Level: L2\n")
        proc = self.cli("set", STEM)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("Phase 00 후보", proc.stdout)
        self.assertNotIn("찾지 못", proc.stdout)

    def test_broken_identity_still_refuses_create_without_overwrite(self):
        path = self._write_doc("plan_docs/00-base_plan/payment-fix.md",
                               "Cycle-Stem: `different`\nRisk Level: L2\n")
        before = path.read_bytes()
        proc = self.cli("set", STEM, "--create", "--risk", "L2")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(path.read_bytes(), before)

    @unittest.skipIf(os.name == "nt", "POSIX entry types")
    def test_every_existing_target_entry_type_is_preserved(self):
        target = self.phase00()
        target.parent.mkdir(parents=True, exist_ok=True)
        constructors = {
            "file": lambda: target.write_text("keep", encoding="utf-8"),
            "directory": lambda: target.mkdir(),
            "symlink": lambda: os.symlink(self.root / "elsewhere", target),
            "dangling": lambda: os.symlink(self.root / "missing", target),
        }
        for label, create in constructors.items():
            with self.subTest(kind=label):
                if os.path.lexists(target):
                    if target.is_dir() and not target.is_symlink():
                        target.rmdir()
                    else:
                        target.unlink()
                create()
                stat_before = os.lstat(target)
                proc = self.cli("set", STEM, "--create", "--risk", "L2")
                self.assertEqual(proc.returncode, 2)
                stat_after = os.lstat(target)
                self.assertEqual((stat_before.st_mode, stat_before.st_ino),
                                 (stat_after.st_mode, stat_after.st_ino))

    def test_duplicate_paths_and_three_cross_phase_candidates_are_reported(self):
        a = self._write_doc("plan_docs/00-base_plan/payment-fix.md", "broken\n")
        b = self._write_doc("plan_docs/00-base_plan/archive/payment-fix.md", "broken\n")
        self._write_doc("plan_docs/03-implementation/payment-fix-2.md", "old\n")
        proc = self.cli("set", STEM, "--create", "--risk", "L2")
        self.assertEqual(proc.returncode, 2)
        text = proc.stdout + proc.stderr
        self.assertIn(str(a.relative_to(self.root)), text)
        self.assertIn(str(b.relative_to(self.root)), text)
        self.assertNotIn("payment-fix-2\n", text)
        for candidate in ("payment-fix-3", "payment-fix-4", "payment-fix-5"):
            self.assertIn(candidate, text)
        self.assertFalse((self.root / ".sage" / "cycle.json").exists())


class TestFailureSemantics(CycleCliCase):
    def _direct_create(self):
        args = SimpleNamespace(action="set", stem=STEM, extra=[], create=True, risk="L2",
                               path=None, root=str(self.root))
        import contextlib
        import io
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            rc = cycle.run(args)
        return rc, output.getvalue()

    def test_document_write_failure_leaves_no_declaration(self):
        with mock.patch.object(cycle, "_write_phase00_exclusive",
                               side_effect=OSError("injected write failure")):
            rc, _text = self._direct_create()
        self.assertEqual(rc, 2)
        self.assertFalse(self.phase00().exists())
        self.assertFalse(Path(cs.declaration_path(self.root)).exists())

    def test_declaration_failure_preserves_the_successful_document_and_prints_recovery(self):
        with mock.patch.object(cs, "write_declaration",
                               side_effect=PermissionError("injected declaration failure")):
            rc, text = self._direct_create()
        self.assertEqual(rc, 2)
        self.assertTrue(self.phase00().is_file())
        self.assertIn(f"sage cycle set {STEM}", text)

    def test_short_write_or_flush_failure_removes_only_its_incomplete_entry(self):
        writer = getattr(cycle, "_write_phase00_exclusive", None)
        self.assertIsNotNone(writer, "exclusive Phase 00 writer is missing")
        target = self.phase00()
        target.parent.mkdir(parents=True, exist_ok=True)
        real_write = os.write
        calls = 0

        def short_then_zero(fd, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_write(fd, data[: max(1, len(data) // 2)])
            return 0

        with mock.patch.object(cycle.os, "write", side_effect=short_then_zero):
            with self.assertRaises(OSError):
                writer(str(target), b"complete document\n")
        self.assertFalse(os.path.lexists(target))

        with mock.patch.object(cycle.os, "fsync", side_effect=OSError("injected flush failure")):
            with self.assertRaises(OSError):
                writer(str(target), b"complete document\n")
        self.assertFalse(os.path.lexists(target))


class TestFullGateAndTransition(CycleCliCase):
    def test_create_then_real_gate_uses_the_declared_cycle(self):
        proc = self.cli("set", STEM, "--create", "--risk", "L2")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(cs.resolve_stem(self.root, environ={})[:2], (STEM, "cli"))

        import contextlib
        import io
        import hook_runtime as runtime
        import io_claude

        raw = json.dumps({
            "session_id": "cycle-usability-e2e",
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "src" / "app.py"),
                "content": "print('ok')\n",
            },
        })
        env = {
            "SAGE_PROFILE": str(self.root / "sage" / "project-profile.json"),
            "SAGE_GATE_BRANCH": "long-lived-branch",
            "SAGE_CYCLE_STEM": "",
        }
        previous = {key: os.environ.get(key) for key in env}
        os.environ.update(env)
        try:
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                rc = runtime.run_pre_implementation_gate(
                    io_claude, str(self.root), str(HOOKS_DIR), raw)
            self.assertEqual(rc, 0, output.getvalue())
            self.assertIn(STEM, output.getvalue())
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_a_to_b_to_a_changes_only_the_pointer(self):
        a = self._write_phase("a-cycle")
        before = a.read_bytes()
        for stem in ("a-cycle", "b-cycle", "a-cycle"):
            proc = self.cli("set", stem)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(a.read_bytes(), before)
        self.assertEqual(cs.read_declaration(self.root)[0], "a-cycle")

    def _write_phase(self, stem):
        path = self.root / "plan_docs" / "00-base_plan" / f"{stem}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Cycle-Stem: `{stem}`\nRisk Level: L2\n", encoding="utf-8")
        return path


class TestSkillsAndDocumentation(unittest.TestCase):
    def _read(self, rel):
        return (PROJECT_ROOT / rel).read_text(encoding="utf-8")

    def test_skill_calls_and_order_are_explicit(self):
        plan = self._read("templates/core/framework/.claude/skills/sage-plan/SKILL.md")
        team = self._read("templates/core/framework/.claude/skills/sage-team/SKILL.md")
        umbrella = self._read("templates/core/framework/.claude/skills/sage-cycle/SKILL.md")
        self.assertIn("sage cycle set <stem>", plan)
        self.assertLess(plan.index("Cycle-Stem"), plan.index("sage cycle set <stem>"))
        show = team.index("sage cycle show")
        identity = team.index("stems are a hard stop.")
        evidence = team.index("Then find the first incomplete stage using **evidence anchors**")
        self.assertLess(identity, show)
        self.assertLess(show, evidence)
        clear = team.index("sage cycle clear")
        self.assertGreater(clear, team.index("python -m sage retro"))
        self.assertGreater(clear, team.index("sage context snapshot"))
        self.assertNotIn("sage cycle set <stem>", umbrella)
        self.assertNotIn("sage cycle clear\n", umbrella)
        self.assertIn("does not run `sage cycle set` or `sage cycle clear` directly", umbrella)

    def test_korean_and_english_user_docs_explain_umbrella_ownership(self):
        pairs = [
            ("docs/cli-reference.md", "docs/cli-reference.en.md"),
            ("docs/troubleshooting.md", "docs/troubleshooting.en.md"),
        ]
        for ko, en in pairs:
            with self.subTest(pair=(ko, en)):
                for document in (ko, en):
                    text = self._read(document)
                    self.assertIn("sage cycle set", text, document)
                    self.assertIn("sage cycle show", text, document)
                    self.assertIn("sage cycle clear", text, document)
                    self.assertIn("SAGE_CYCLE_STEM", text, document)
                    self.assertTrue("sage-plan" in text and "sage-team" in text, document)

    def test_active_runtime_and_guard_guidance_have_no_use_command(self):
        active = [
            "sage/commands/cycle.py",
            "scripts/sage_harness/hooks/runtime/messages.py",
            "scripts/sage_harness/hooks/generated_artifact_write_guard_core.py",
            "docs/sage_harness/hooks/pre-implementation-gate.md",
            "templates/core/framework/AGENT_GUIDE.md",
            "templates/core/framework/docs/agent/pdca-templates.md",
        ]
        for rel in active:
            with self.subTest(path=rel):
                self.assertNotIn("sage cycle use", self._read(rel))

    def test_run_all_executes_this_suite(self):
        runner = self._read("scripts/sage_harness/hooks/tests/run-all.sh")
        lines = [line for line in runner.splitlines()
                 if "test_cycle_usability.py" in line and not line.lstrip().startswith("#")]
        self.assertEqual(len(lines), 1)
        self.assertIn("|| rc=1", lines[0])


_HANGUL = re.compile(r"[가-힣]")


class TestCycleLanguageContract(CycleCliCase):
    """cycle_state 판정(read_declaration/read_declaration_record)과 cycle.py 자체 오류가
    --lang en 화면에서 한국어를 남기지 않아야 한다(§ 배치 2 — 언어 중립 진단 이관)."""

    def test_bad_stem_error_has_no_korean_under_lang_en(self):
        proc = self.cli_lang("en", "set", "bad/stem")
        self.assertEqual(proc.returncode, 2)
        self.assertNotRegex(proc.stderr, _HANGUL)
        self.assertIn("invalid cycle stem format", proc.stderr)

    def test_bad_stem_error_stays_korean_under_default(self):
        proc = self.cli("set", "bad/stem")
        self.assertEqual(proc.returncode, 2)
        self.assertRegex(proc.stderr, _HANGUL)
        self.assertIn("cycle stem 형식 오류", proc.stderr)

    def test_corrupt_declaration_notice_has_no_korean_under_lang_en(self):
        path = Path(cs.declaration_path(self.root))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"cycle_stem": "x"', encoding="utf-8")   # truncated JSON
        proc = self.cli_lang("en", "show")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotRegex(proc.stdout, _HANGUL)
        self.assertIn("JSON parse failed", proc.stdout)

    def test_corrupt_declaration_notice_stays_korean_under_default(self):
        path = Path(cs.declaration_path(self.root))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"cycle_stem": "x"', encoding="utf-8")
        proc = self.cli("show")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("JSON 파싱 실패", proc.stdout)

    def test_gate_declaration_notice_renders_in_both_languages(self):
        """hook_runtime → messages.py 경로(사람이 읽는 게이트 안내)도 언어별로 갈라져야 한다."""
        sys.path.insert(0, str(RUNTIME))
        import messages
        decision = {"status": "ok", "exit_code": 0,
                    "cycle_declaration_error": {"code": "cycle_state.json_invalid",
                                                "arguments": {"path": "/p/.sage/cycle.json"},
                                                "evidence": ""},
                    "file_short": "a.java"}
        ko = messages.gate_text(decision, {}, "claude", "ko")
        en = messages.gate_text(decision, {}, "claude", "en")
        self.assertRegex(ko, _HANGUL)
        self.assertNotRegex(en, _HANGUL)
        self.assertIn("JSON parse failed", en)


if __name__ == "__main__":
    unittest.main(verbosity=2)
