#!/usr/bin/env python3
"""언어 중립 판정 계약 — hook 경로 모듈이 문장이 아니라 code 를 돌려준다.

`hook_entry`·`context_packet`·`feedback` 은 설치된 hook 이 닿는 경로에 있다. 여기에
`sage.i18n` 이 들어오면 hook 이 엔진 없이는 못 도는 물건이 되고, 그건 이 사이클이 세운
"hook locale 은 엔진 비의존" 계약이 무너지는 유일한 경로다.

그래서 판정은 **무엇이 잘못됐는지**(code + named arguments + evidence)만 말하고, 문장은
호출부가 자기 도메인 catalog 로 만든다. 같은 code 가 CLI 에서는 `cli.<code>`, hook 에서는
`hook.<code>` 로 렌더된다 — 공통 code 는 판정 계약이고 catalog key 는 출력 도메인의 소유다.
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
RUNTIME = REPO / "scripts/sage_harness/hooks/runtime"

from sage.diagnostics import Diagnostic, render          # noqa: E402

HOOK_REACHABLE = ("sage/hook_entry.py", "sage/context_packet.py", "sage/feedback.py")
HANGUL = re.compile(r"[가-힣]")


class TestJudgementLayerStaysLanguageNeutral(unittest.TestCase):
    def test_hook_reachable_modules_never_import_the_engine_catalog(self):
        """import 한 줄이 hook 을 엔진 의존으로 만든다 — 그게 이 계약의 유일한 파괴 경로다."""
        offenders = []
        for rel in HOOK_REACHABLE:
            tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sage.i18n"):
                    offenders.append(f"{rel}:{node.lineno}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("sage.i18n"):
                            offenders.append(f"{rel}:{node.lineno}")
        self.assertEqual(offenders, [], f"판정 모듈이 엔진 catalog 를 import 한다: {offenders}")

    def test_the_judgement_layer_emits_no_korean_string_literals(self):
        """완성 문장을 담으면 판정 계층이 언어를 갖게 된다.

        주석과 docstring 은 대상이 아니다 — 한국어가 기본 정책이고 화면에 나가지 않는다.
        검사 대상은 **값으로 흘러나갈 수 있는 문자열 literal** 이다.
        """
        offenders = []
        for rel in ("sage/diagnostics.py",) + HOOK_REACHABLE:
            source = (REPO / rel).read_text(encoding="utf-8")
            tree = ast.parse(source)
            docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                          if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                               ast.AsyncFunctionDef))
                          and node.body and isinstance(node.body[0], ast.Expr)
                          and isinstance(node.body[0].value, ast.Constant)}
            for node in ast.walk(tree):
                if id(node) in docstrings:
                    continue
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and HANGUL.search(node.value)):
                    offenders.append(f"{rel}:{node.lineno} {node.value[:40]}")
                if isinstance(node, ast.JoinedStr):
                    segment = ast.get_source_segment(source, node) or ""
                    if HANGUL.search(segment):
                        offenders.append(f"{rel}:{node.lineno} {segment[:40]}")
        self.assertEqual(offenders, [], f"판정 계층에 한국어 문자열이 남았다: {offenders}")

    def test_judgement_functions_return_codes_not_text(self):
        from sage.context_packet import profile_issues
        issues = profile_issues({"context_management": {"unknown_key": 1}})
        self.assertTrue(issues)
        for _severity, item in issues:
            self.assertIsInstance(item, Diagnostic, f"문장을 돌려준다: {item!r}")
            self.assertIsNone(HANGUL.search(item.code))

    def test_scan_errors_carry_a_diagnostic(self):
        from sage import feedback
        error = feedback.ScanError(Diagnostic("feedback.git_exit", code=128, evidence="fatal: x"))
        self.assertEqual(error.diagnostic.code, "feedback.git_exit")
        self.assertEqual(error.diagnostic.arguments, {"code": 128})


class TestBothDomainsRenderEveryCode(unittest.TestCase):
    """CLI 와 hook 이 각자 catalog 를 갖되 **같은 key 를 중복 등록하지 않는다.**"""

    def _emitted_codes(self):
        codes = set()
        for rel in HOOK_REACHABLE:
            tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "Diagnostic" and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    codes.add(node.args[0].value)
        return codes

    def test_every_emitted_code_renders_in_both_languages(self):
        from sage.i18n import CATALOGS
        sys.path.insert(0, str(RUNTIME))
        import i18n as hook_i18n
        missing = []
        for code in sorted(self._emitted_codes()):
            for language in ("ko", "en"):
                if f"cli.{code}" not in CATALOGS[language] and f"hook.{code}" not in hook_i18n.FRAGMENTS[language]:
                    missing.append(f"{language}:{code}")
        self.assertEqual(missing, [], f"어느 도메인에서도 렌더되지 않는 code: {missing}")

    def test_the_two_domains_do_not_share_keys(self):
        """같은 key 를 둘 다 들고 있으면 같은 문장의 소유자가 둘이 된다."""
        from sage.i18n import CATALOGS
        sys.path.insert(0, str(RUNTIME))
        import i18n as hook_i18n
        overlap = set(CATALOGS["ko"]) & (set(hook_i18n.CATALOGS["ko"]) | set(hook_i18n.FRAGMENTS["ko"]))
        self.assertEqual(overlap, set(), f"두 도메인이 같은 key 를 등록했다: {sorted(overlap)[:5]}")

    def test_evidence_is_never_translated(self):
        """외부 도구 원문을 번역하면 사용자가 검색할 수 있는 문자열이 사라진다."""
        raw = "fatal: not a git repository"
        rendered = {}
        from sage.i18n import LanguageContext, render_issue
        for language in ("ko", "en"):
            rendered[language] = render_issue(
                LanguageContext(language=language),
                Diagnostic("feedback.git_exit", code=128, evidence=raw))
            self.assertIn(raw, rendered[language])
        self.assertNotEqual(rendered["ko"], rendered["en"], "문장이 언어에 따라 달라지지 않았다")


class TestHookRendersWithoutTheEngineCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        cls.root = os.path.join(cls._tmp, "consumer")
        os.makedirs(cls.root)
        done = subprocess.run(
            [sys.executable, "-m", "sage", "install", "--host", "claude",
             "--prefix", "t", "--dest", cls.root],
            cwd=str(REPO), env=dict(os.environ, PYTHONPATH=str(REPO)),
            capture_output=True, text=True)
        assert done.returncode == 0, done.stderr

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _help(self, language):
        Path(self.root, "sage", "project-profile.local.yaml").write_text(
            f"interface:\n  language: {language}\n", encoding="utf-8")
        done = subprocess.run(
            [sys.executable, "-m", "sage.hook_entry", "--help"],
            cwd=self.root, env=dict(os.environ, PYTHONPATH=str(REPO)),
            capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_the_consumer_profile_changes_the_hook_entry_language(self):
        korean, english = self._help("ko"), self._help("en")
        self.assertNotEqual(korean, english,
                            "local profile 을 en 으로 둬도 hook 진입점 출력이 그대로다")
        self.assertIsNone(HANGUL.search(english), f"en 화면에 한국어가 남았다:\n{english}")
        self.assertIsNotNone(HANGUL.search(korean))

    def test_removing_the_render_wiring_is_detected(self):
        """배선을 지우면 실패해야 한다 — 이 사이클에서 세 번 나온 실패 형태다."""
        source = (REPO / "sage" / "hook_entry.py").read_text(encoding="utf-8")
        self.assertIn("_hook_locale", source)
        self.assertIn("help_say(", source)
        self.assertIn('render(diagnostic, translate, "hook")', source,
                      "hook 진입점이 hook 도메인으로 렌더하지 않는다")
        self.assertIn("_say(core_dir, root", source,
                      "진단을 화면으로 옮기는 호출이 없다")


class TestNoHookReachableLiteralsRemain(unittest.TestCase):
    def test_the_inventory_reports_zero_hook_reachable_entries(self):
        entries = json.loads(
            (REPO / "docs" / "sage_harness" / "localization-inventory.json").read_text(
                encoding="utf-8"))["entries"]
        remaining = [e for e in entries if e.get("hook_reachable")]
        self.assertEqual(remaining, [],
                         f"hook 경로에 미이관 literal 이 남았다: "
                         f"{[(e['source_file'], e['source_line']) for e in remaining[:5]]}")


class TestRunAllRegistration(unittest.TestCase):
    def test_this_suite_is_wired(self):
        self.assertIn("test_diagnostics_contract.py",
                      (HERE / "run-all.sh").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
