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
        # 기본 문서 언어는 ko 이고, 초안의 사람용 문구는 그 언어를 따른다.
        self.assertIn("- [ ] TODO: 구체적인 완료 기준으로 바꾸세요", text)
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
_DOCUMENT_LANGUAGE_RE = re.compile(r"^Document-Language:\s*(\S+)\s*$", re.MULTILINE)


class TestDocumentLanguageResolutionMatrix(CycleCliCase):
    """AC24 — `sage cycle set --create` 의 문서 언어 결정: explicit > context(--lang/local
    profile) > 기본값(ko). 표준 사이클의 explicit/local/default 조합을 실제 CLI 호출로 검증한다.
    Fast Cycle 도 같은 함수(`cycle._document_language`)를 거치므로 별도 코드 경로는 없다 —
    Fast 쪽 잔여는 CORE skill 지시문(`sage-plan-fast`) 정적 존재 확인으로 다룬다."""

    def _local_profile(self, language):
        (self.root / "sage" / "project-profile.local.yaml").write_text(
            yaml.safe_dump({"interface": {"language": language}}), encoding="utf-8")

    def _created_language(self, *extra_args, lang=None):
        args = ["set", STEM, "--create", "--risk", "L2", *extra_args]
        proc = self.cli_lang(lang, *args) if lang else self.cli(*args)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = self.phase00().read_text(encoding="utf-8")
        match = _DOCUMENT_LANGUAGE_RE.search(text)
        self.assertIsNotNone(match, text)
        return match.group(1)

    def test_no_explicit_no_context_defaults_to_ko(self):
        self.assertEqual(self._created_language(), "ko")

    def test_local_profile_language_becomes_the_default_without_an_explicit_flag(self):
        self._local_profile("en")
        self.assertEqual(self._created_language(), "en")

    def test_cli_lang_flag_becomes_the_default_without_an_explicit_flag(self):
        self.assertEqual(self._created_language(lang="en"), "en")

    def test_explicit_flag_wins_over_local_profile(self):
        self._local_profile("en")
        self.assertEqual(self._created_language("--document-language", "ko"), "ko")

    def test_explicit_flag_wins_over_cli_lang(self):
        self.assertEqual(
            self._created_language("--document-language", "ko", lang="en"), "ko")


class TestPhase00SkeletonLanguage(unittest.TestCase):
    """AC24 — `--create` 가 만드는 Phase 00 초안의 **사람용** 문구가 선언 언어를 따르는가.

    marker 만 ko 로 박고 heading·TODO 를 영어로 두면, 사용자는 한국어 문서를 열자마자 영어
    제목을 마주하고 그 위에 한국어를 쓴다 — 실측된 혼용의 출발점이 이 초안이었다.

    **두 heading 은 번역하지 않는다**: `## 5. Done Criteria` 와 `## 6. Done Criteria Revision Log`
    는 `done_criteria_contract` 가 문자열로 직접 찾는 파서 가시 marker 다(language-policy.md 의
    "Parser-visible section markers"). 번역하면 파서에게는 heading 이 사라진 것으로 읽힌다."""

    PARSED = ("## 5. Done Criteria", "## 6. Done Criteria Revision Log")
    MARKERS = ("Cycle-Stem:", "Risk Level:", "Status: DRAFT", "Done-Criteria-Revision: 1")

    def test_korean_skeleton_has_korean_headings(self):
        text = cycle._phase00_skeleton(STEM, "L2", "ko")
        self.assertIn("Document-Language: ko", text)
        for english in ("## 1. Context", "## 2. Goal", "## 3. Acceptance Criteria",
                        "## 4. Final Conclusion & UX Guide", "[Base Plan]"):
            self.assertNotIn(english, text)
        self.assertRegex(text, _HANGUL)

    def test_english_skeleton_has_no_korean(self):
        text = cycle._phase00_skeleton(STEM, "L2", "en")
        self.assertIn("Document-Language: en", text)
        self.assertIn("## 1. Context", text)
        self.assertNotRegex(text, _HANGUL)

    def test_parser_visible_headings_are_never_translated(self):
        for language in ("ko", "en"):
            text = cycle._phase00_skeleton(STEM, "L2", language)
            for heading in self.PARSED:
                self.assertIn(heading, text, language)

    def test_machine_markers_survive_both_languages(self):
        for language in ("ko", "en"):
            text = cycle._phase00_skeleton(STEM, "L2", language)
            for marker in self.MARKERS:
                self.assertIn(marker, text, language)

    def test_the_korean_skeleton_still_parses_as_a_done_criteria_document(self):
        """번역이 파서를 깨지 않았는지 계약 자체에 물어본다."""
        from sage import done_criteria_contract as dcc
        result = dcc.parse_done_criteria(cycle._phase00_skeleton(STEM, "L2", "ko"),
                                         mode="standard")
        self.assertEqual(result.status, "valid", result.issues)


class TestCoreSkillConversationLanguageDirective(unittest.TestCase):
    """AC20 — 13개 CORE skill 이 **배포 렌더에서** 대화 언어 resolver 를 갖는가.

    문서 언어(`Document-Language:`)와 대화 언어는 별개 결정이다. 문서 언어만 지시하면 실제
    host 실행에서 문서 본문은 영어로 쓰면서 질문·진행 설명·요약은 한국어로 내는 상태가 되고,
    그게 AC20 사람 검토에서 실측된 결함이다. 설계 SSOT(`templates/core/skills/*.md`)에만
    적어두면 **배포되는 것은 그 파일이 아니라서** 아무 효과가 없다 — 그래서 렌더를 본다.

    이 확인은 LLM 이 실제로 지시를 따르는지는 증명하지 못한다. 그건 사람 검토의 몫이다."""

    FRAMEWORK_SKILLS = PROJECT_ROOT / "templates" / "core" / "framework" / ".claude" / "skills"
    POLICY = "docs/agent/language-policy.md"

    def _skills(self):
        return sorted(p for p in self.FRAMEWORK_SKILLS.iterdir() if (p / "SKILL.md").is_file())

    def test_every_shipped_skill_is_covered(self):
        """개수를 고정한다 — skill 이 늘 때 지시문 없이 조용히 배포되는 것을 막는다."""
        self.assertEqual(len(self._skills()), 13)

    def test_every_skill_resolves_the_conversation_language(self):
        for skill in self._skills():
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill.name):
                self.assertIn("--lang", text)
                self.assertIn("interface.language", text)
                self.assertIn(self.POLICY, text)

    def test_no_skill_hardcodes_the_conversation_language(self):
        """`en` 을 골라도 한국어로 대화하라고 적혀 있으면 resolver 가 있어도 무의미하다."""
        for skill in self._skills():
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill.name):
                self.assertNotIn("in Korean**", text)
                self.assertNotIn("default to Korean", text)
                self.assertNotIn("not yet active", text)


class TestCoreSkillDocumentLanguageDirective(unittest.TestCase):
    """AC24/AC25 — Fast Cycle·리뷰 CORE skill 이 표준 skill 과 같은 언어 지시문을 갖는가.

    `_document_language()` 결정 함수는 표준/Fast 가 공유하지만(코드 경로는 위 matrix 로 이미
    검증됨), Fast·리뷰 skill 이 그 결과를 실제로 사용하려면 프롬프트 자체가 사용자에게 언어를
    묻고 `--document-language` 를 명시하도록 지시해야 한다. 이 확인은 LLM 이 실제로 지시를
    따르는지(host 실행 결과)는 증명하지 못한다 — 그건 AC20/34 사람 검토의 몫이다."""

    ROOT = PROJECT_ROOT
    FRAMEWORK_SKILLS = ROOT / "templates" / "core" / "framework" / ".claude" / "skills"

    def _read(self, skill_id):
        return (self.FRAMEWORK_SKILLS / skill_id / "SKILL.md").read_text(encoding="utf-8")

    def test_plan_fast_settles_and_declares_document_language(self):
        text = self._read("sage-plan-fast")
        self.assertIn("Document-Language", text)
        self.assertIn("--document-language", text)

    def test_team_fast_reads_document_language_before_writing(self):
        text = self._read("sage-team-fast")
        self.assertIn("Document-Language", text)

    def test_review_reads_document_language_before_writing(self):
        text = self._read("sage-review")
        self.assertIn("Document-Language", text)

    AUTHORING = ("sage-plan", "sage-plan-fast", "sage-team", "sage-team-fast", "sage-review")

    def test_authoring_skills_say_headings_follow_the_document_language(self):
        """AC24 — '본문을 그 언어로' 만 적으면 host 가 heading 은 영어로 남긴다(실측).
        사람용 제목도 prose 라는 것을 문서 작성 skill 이 직접 말해야 한다."""
        for skill in self.AUTHORING:
            with self.subTest(skill=skill):
                self.assertIn("heading", self._read(skill))

    def test_the_language_policy_states_the_heading_rule_and_its_exceptions(self):
        policy = (PROJECT_ROOT / "templates" / "core" / "framework" / "docs" / "agent"
                  / "language-policy.md").read_text(encoding="utf-8")
        self.assertIn("section headings", policy)
        self.assertIn("## 5. Done Criteria", policy)
        self.assertIn("## 6. Done Criteria Revision Log", policy)


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
