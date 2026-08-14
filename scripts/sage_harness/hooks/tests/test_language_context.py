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
import re
import pathlib
import unittest
from unittest import mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from sage.i18n import CATALOGS, LanguageContext, tr  # noqa: E402
from sage.i18n.context import DEFAULT_LANGUAGE, read_local_language, resolve  # noqa: E402
from sage.i18n.parser import LanguageArgumentError, context_for, scan  # noqa: E402
from sage.i18n.validation import (KOREAN_IN_ENGLISH_ALLOWED,  # noqa: E402
                                  KOREAN_IN_ENGLISH_DEBT, catalog_issues)
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


class TestCatalogContent(unittest.TestCase):
    """key 집합이 맞아도 값이 잘못될 수 있다 — catalog 내용 자체를 게이트한다.

    인벤토리는 코드를 스캔하므로 영어 catalog 안에 남은 한국어를 세지 못한다. 이관이 끝나
    인벤토리가 0 이 되어도 그 누출은 그대로 `--lang en` 화면에 나간다. 그래서 이 검사는 건수가
    아니라 **정확한 key 집합**으로 관리한다 — 건수 baseline 은 한 건을 고치면서 다른 한 건이
    새로 들어와도 총계가 같아 통과한다.
    """
    def _mutated(self, language, key, text):
        """catalog 를 한 건만 바꿔 `catalog_issues` 가 그걸 잡는지 본다(원복 보장)."""
        original = CATALOGS[language].get(key)
        CATALOGS[language][key] = text
        try:
            return catalog_issues(str(REPO))
        finally:
            if original is None:
                del CATALOGS[language][key]
            else:
                CATALOGS[language][key] = original

    def test_known_english_korean_debt_is_an_exact_key_set(self):
        korean = re.compile(r"[가-힣]")
        actual = {key for key, text in CATALOGS["en"].items() if korean.search(text)}
        self.assertEqual(KOREAN_IN_ENGLISH_DEBT | KOREAN_IN_ENGLISH_ALLOWED, actual)

    def test_the_only_intended_korean_english_value_points_at_the_other_language(self):
        # 영어 도움말에서 한국어로 가는 안내라 en 값이 한국어인 것이 맞다.
        self.assertEqual({"cli.root.switch_hint"}, set(KOREAN_IN_ENGLISH_ALLOWED))
        self.assertIn("--lang en", CATALOGS["ko"]["cli.root.switch_hint"])
        self.assertNotIn("--lang", CATALOGS["en"]["cli.root.switch_hint"])

    def test_a_new_korean_english_value_fails_immediately(self):
        issues = self._mutated("en", "cli.root.help_option", "이 문장은 영어여야 한다")
        self.assertTrue(any("cli.root.help_option[en]" in issue and "한국어" in issue
                            for issue in issues), issues)

    def test_resolved_debt_must_be_removed_from_the_list(self):
        # 부채를 고치고 목록을 그대로 두면 다음 사람이 남은 건수를 신뢰할 수 없다.
        # KOREAN_IN_ENGLISH_DEBT 가 실제로 비어 있을 수 있으므로(이관 완료 시점), 이미 깨끗한
        # key 를 임시로 부채 선언에 넣어 "해소된 부채가 목록에 남으면 잡힌다"를 재현한다.
        import sage.i18n.validation as validation_module
        debt_key = "cli.root.help_option"
        with mock.patch.object(validation_module, "KOREAN_IN_ENGLISH_DEBT", frozenset({debt_key})):
            issues = catalog_issues(str(REPO))
        self.assertTrue(any(debt_key in issue and "KOREAN_IN_ENGLISH_DEBT" in issue
                            for issue in issues), issues)

    def test_escaped_newline_in_any_catalog_fails(self):
        for language in ("ko", "en"):
            with self.subTest(language=language):
                issues = self._mutated(language, "cli.root.help_option", "first\\nsecond")
                self.assertTrue(any(f"cli.root.help_option[{language}]" in issue
                                    and "개행" in issue for issue in issues), issues)

    def test_english_catalog_prints_real_newlines(self):
        # 리터럴 두 글자가 남아 있으면 영어 사용자는 줄바꿈 대신 `\n` 을 읽는다.
        for key, korean in CATALOGS["ko"].items():
            with self.subTest(key=key):
                self.assertEqual(korean.count("\n"), CATALOGS["en"][key].count("\n"))


class TestDriftDiagnosticInvariance(unittest.TestCase):
    """라벨만 번역한다. 경로·건수가 언어마다 다르면 같은 drift 가 다른 증거로 보인다."""

    def _rendered(self, language):
        from sage.build_identity import describe_content_drift
        before = {f"p{i}": str(i) for i in range(9)}
        after = {**{f"p{i}": "x" for i in range(7)}, "new": "1"}
        return describe_content_drift(before, after, language)

    def test_paths_and_counts_are_identical_across_locales(self):
        import re as _re
        korean, english = self._rendered("ko"), self._rendered("en")
        token = _re.compile(r"p\d+|new|\d+")
        self.assertEqual(token.findall(korean), token.findall(english))
        self.assertEqual(korean.count("|"), english.count("|"))

    def test_only_the_label_words_differ(self):
        self.assertIn("변경", self._rendered("ko"))
        self.assertIn("changed", self._rendered("en"))

    def test_identical_snapshots_describe_nothing_in_both_locales(self):
        from sage.build_identity import describe_content_drift
        same = {"a": "1"}
        for language in ("ko", "en"):
            self.assertEqual(describe_content_drift(same, same, language), "")



class TestHelpTreeIsLocalized(unittest.TestCase):
    """`--lang en --help` 이 실제로 영어를 내는가 — 루트 화면만이 아니라 하위 명령까지.

    B4 는 루트 help 만 catalog 를 거쳤다. 사용자가 실제로 읽는 화면은 `sage <cmd> --help` 쪽이라
    그 상태로는 "언어를 고를 수 있다"가 화면에서 거짓이었다.
    """

    HANGUL = re.compile(r"[가-힣]")

    def _tree(self, language):
        from sage.cli import build_parser
        from sage.i18n.context import LanguageContext
        parser = build_parser(LanguageContext(language=language))
        pages = {"": parser.format_help()}
        for name, sub in parser._subparsers._group_actions[0].choices.items():
            pages[name] = sub.format_help()
            nested = [a for a in sub._actions if hasattr(a, "choices") and isinstance(a.choices, dict)]
            for action in nested:
                for inner, page in (action.choices or {}).items():
                    if hasattr(page, "format_help"):
                        pages[f"{name} {inner}"] = page.format_help()
        return pages

    def test_english_help_has_no_korean_left(self):
        offenders = []
        for name, page in self._tree("en").items():
            # 한국어 도움말로 건너가는 안내 한 줄은 의도적으로 한국어다 — 영어를 읽는 사람에게
            # 한국어 화면의 존재를 알리는 유일한 통로라 번역하면 목적이 사라진다.
            body = page.replace("한국어 도움말: sage --help", "")
            found = self.HANGUL.search(body)
            if found:
                offenders.append((name, found.group(), body[max(0, found.start() - 40):found.start() + 40]))
        self.assertEqual(offenders, [], f"en help 에 한글이 남았다: {offenders[:5]}")

    def test_korean_help_is_the_compatibility_default(self):
        """ko 는 catalog 도입 전 출력을 그대로 재현해야 한다 — 언어 배선과 문구 변경은 별개다."""
        for name, page in self._tree("ko").items():
            self.assertTrue(page.strip(), name)
            self.assertNotIn("message_key=", page, name)

    def test_every_command_registers_with_a_context(self):
        """register(sub) 시그니처가 하나라도 남으면 그 명령만 조용히 한국어로 남는다."""
        import ast
        offenders = []
        for path in sorted(pathlib.Path("sage/commands").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name == "register":
                    names = [a.arg for a in node.args.args]
                    if names != ["sub", "context"]:
                        offenders.append((path.name, names))
        self.assertEqual(offenders, [], f"context 를 받지 않는 register: {offenders}")

if __name__ == "__main__":
    unittest.main()
