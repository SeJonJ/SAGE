#!/usr/bin/env python3
"""표시 언어 계약 — 우선순위·격리·채널·catalog 정합성.

언어는 표현만 바꾸고 판단은 바꾸지 않는다. 그래서 여기서 고정하는 것은 "무엇이 어떤 언어로
보이는가"가 아니라 그 반대다: 언어가 달라져도 공유 산출물과 exit 계약이 그대로인가.

설정 부재가 조용히 통과로 떨어지지 않도록, 기본값 `ko` 는 fallback 이 아니라 명시적으로
검사되는 계약이다.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from sage.i18n import CATALOGS, LanguageContext, tr  # noqa: E402
from sage.i18n.context import DEFAULT_LANGUAGE, read_local_language, resolve  # noqa: E402
from sage.i18n.parser import LanguageArgumentError, context_for, scan  # noqa: E402
from sage.i18n.validation import catalog_issues  # noqa: E402
from sage.profile_layers import effective_profile, profile_layer_issues  # noqa: E402


def _run(args, cwd=None):
    return subprocess.run([sys.executable, "-m", "sage", *args], capture_output=True, text=True,
                          input="", cwd=str(cwd or REPO),
                          env=dict(os.environ, PYTHONPATH=str(REPO)))


def _project(root, language=None, raw=None):
    os.makedirs(os.path.join(root, "sage"), exist_ok=True)
    path = os.path.join(root, "sage", "project-profile.local.yaml")
    if raw is not None:
        Path(path).write_text(raw, encoding="utf-8")
    elif language is not None:
        Path(path).write_text(f"interface:\n  language: {language}\n", encoding="utf-8")
    return root


class TestResolutionOrder(unittest.TestCase):
    def test_absent_configuration_is_korean(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(resolve(None, root).language, "ko")
            self.assertEqual(resolve(None, root).source, "default")

    def test_local_profile_selects_the_language(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root, "en")
            context = resolve(None, root)
            self.assertEqual((context.language, context.source), ("en", "local_profile"))

    def test_explicit_flag_outranks_the_local_profile(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root, "en")
            context = resolve("ko", root)
            self.assertEqual((context.language, context.source), ("ko", "cli"))

    def test_damaged_local_falls_back_without_hiding_it(self):
        """부재와 손상이 똑같이 조용하면 한 글자만 깨뜨려도 설정이 사라진 걸 아무도 모른다."""
        for raw in ("interface:\n  language: fr\n", "interface: 3\n", "[not a mapping]\n"):
            with tempfile.TemporaryDirectory() as root:
                _project(root, raw=raw)
                language, damaged = read_local_language(root)
                self.assertIsNone(language, raw)
                self.assertTrue(damaged, raw)
                context = resolve(None, root)
                self.assertEqual(context.language, DEFAULT_LANGUAGE)
                self.assertTrue(context.fallback_used)

    def test_root_hint_is_read_from_registered_options(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root, "en")
            self.assertEqual(context_for(["--root", root, "doctor"]).language, "en")
            self.assertEqual(context_for(["--dest", root, "install"]).language, "en")


class TestBootstrapScan(unittest.TestCase):
    def test_both_flag_spellings(self):
        self.assertEqual(scan(["--lang", "en", "doctor"])[0], "en")
        self.assertEqual(scan(["--lang=en", "doctor"])[0], "en")

    def test_unsupported_missing_and_duplicate_are_rejected(self):
        for argv in (["--lang", "fr"], ["--lang=fr"], ["--lang"],
                     ["--lang", "ko", "--lang", "en"]):
            with self.assertRaises(LanguageArgumentError, msg=argv):
                scan(argv)

    def test_rejection_is_bilingual(self):
        """어느 언어를 고르려 했는지 모르는 상태라 한쪽만 내면 절반은 못 읽는다."""
        with self.assertRaises(LanguageArgumentError) as caught:
            scan(["--lang", "fr"])
        message = caught.exception.bilingual()
        self.assertIn("지원하지 않는 언어", message)
        self.assertIn("Unsupported language", message)


class TestSharedArtifactIsolation(unittest.TestCase):
    def test_interface_never_enters_the_effective_profile(self):
        shared = {"project": {"name": "x"}}
        for local in (None, {"interface": {"language": "en"}}, {"interface": {"language": "ko"}}):
            self.assertNotIn("interface", effective_profile(shared, local))

    def test_effective_profile_is_identical_across_languages(self):
        """언어가 공유 산출물을 1바이트라도 바꾸면 profile hash 가 개인 설정에 물린다."""
        shared = {"project": {"name": "x"}, "options": {}}
        rendered = {json.dumps(effective_profile(shared, local), sort_keys=True)
                    for local in (None, {"interface": {"language": "ko"}},
                                  {"interface": {"language": "en"}})}
        self.assertEqual(len(rendered), 1)

    def test_local_schema_accepts_only_exact_lowercase_values(self):
        self.assertEqual(profile_layer_issues({'project': {'name': 'x'}}, {"interface": {"language": "en"}}), [])
        for bad in ("EN", "en ", "fr", "", None, 3):
            issues = profile_layer_issues({'project': {'name': 'x'}}, {"interface": {"language": bad}})
            self.assertTrue(issues, f"거부되어야 함: {bad!r}")

    def test_unknown_interface_key_is_rejected(self):
        self.assertTrue(profile_layer_issues({'project': {'name': 'x'}}, {"interface": {"lang": "en"}}))


class TestChannelContract(unittest.TestCase):
    def test_bare_sage_is_bilingual_on_stdout_and_exits_zero(self):
        result = _run([])
        self.assertEqual(result.returncode, 0)
        self.assertIn("한국어 도움말", result.stdout)
        self.assertIn("English help", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_unsupported_language_is_bilingual_on_stderr_and_exits_two(self):
        result = _run(["--lang", "fr", "--help"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("지원하지 않는 언어", result.stderr)
        self.assertIn("Unsupported language", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_help_names_the_other_language(self):
        korean = _run(["--help"])
        english = _run(["--lang", "en", "--help"])
        self.assertEqual((korean.returncode, english.returncode), (0, 0))
        self.assertIn("sage --lang en --help", korean.stdout)
        self.assertIn("sage --help", english.stdout)
        self.assertIn("설치하고 검증하는", korean.stdout)
        self.assertIn("installs and verifies", english.stdout)

    def test_version_is_language_neutral(self):
        self.assertEqual(_run(["--version"]).stdout, _run(["--lang", "en", "--version"]).stdout)


class TestCatalog(unittest.TestCase):
    def test_catalogs_agree(self):
        self.assertEqual(catalog_issues(str(REPO)), [])

    def test_missing_key_falls_back_without_losing_the_key_name(self):
        """알 수 없는 key 를 조용히 버리면 문장 하나가 사라진 채 성공처럼 보인다."""
        self.assertEqual(tr(LanguageContext(language="en"), "cli.nope"),
                         "[SAGE] message_key=cli.nope")

    def test_selected_language_gap_falls_back_to_korean(self):
        original = CATALOGS["en"].pop("cli.root.help_option")
        try:
            self.assertEqual(tr(LanguageContext(language="en"), "cli.root.help_option"),
                             CATALOGS["ko"]["cli.root.help_option"])
        finally:
            CATALOGS["en"]["cli.root.help_option"] = original

    def test_argument_mismatch_does_not_raise(self):
        self.assertEqual(tr(LanguageContext(), "cli.lang.unsupported"),
                         "[SAGE] message_key=cli.lang.unsupported")


if __name__ == "__main__":
    unittest.main()
