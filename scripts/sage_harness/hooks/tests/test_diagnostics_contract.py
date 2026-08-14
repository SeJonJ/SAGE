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
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
RUNTIME = REPO / "scripts/sage_harness/hooks/runtime"

from sage.diagnostics import Diagnostic, render          # noqa: E402
from sage.i18n.validation import (CLI_CONSUMED_RUNTIME_MODULES,  # noqa: E402
                                  KOREAN_IN_ENGLISH_DEBT, KOREAN_JUDGEMENT_DEBT,
                                  korean_returning_runtime_functions, release_debt_issues,
                                  runtime_judgement_issues)

# `profile_compile` 은 hook 진입점이 직접 import 한다 — 진입점만 깨끗해도 그 아래가 catalog 를
# 끌어오면 같은 의존이 그대로 따라 들어온다. 계약은 진입점이 아니라 **경로 전체**에 걸린다.
HOOK_REACHABLE = ("sage/hook_entry.py", "sage/context_packet.py", "sage/feedback.py",
                  "sage/profile_compile.py")
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


class TestEveryEmittedCodeIsRenderable(unittest.TestCase):
    """엔진 전역: `Diagnostic("x")` 를 내면 어느 도메인에서든 문장이 나와야 한다.

    도메인별 oracle(`TestBothDomainsRenderEveryCode`)은 hook 이 닿는 모듈만 본다. 이관이
    모듈 단위로 진행되므로 CLI 전용 모듈에서 catalog 등록을 빠뜨리면 화면에
    `[SAGE] message_key=...` 가 뜬다 — 판정은 맞는데 사용자가 원인을 못 읽는 상태다.
    그건 조용한 결함이라 여기서 전역으로 막는다.
    """

    def _emitted(self):
        """`Diagnostic("code", ...)` 의 첫 인자가 상수 문자열인 것만 센다.

        `Diagnostic(f"{prefix}.marker_duplicated")` 처럼 조립된 code 는 여기서 볼 수 없다.
        그건 상수 목록을 세는 정적 검사의 한계이고, 그런 자리는 모듈 집중 테스트가 실제
        호출로 확인한다.
        """
        found = {}
        for path in sorted((REPO / "sage").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "Diagnostic" and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    found.setdefault(node.args[0].value,
                                     f"{path.relative_to(REPO)}:{node.lineno}")
        return found

    def test_every_constant_code_renders_in_both_languages(self):
        from sage.i18n import CATALOGS
        sys.path.insert(0, str(RUNTIME))
        import i18n as hook_i18n
        missing = []
        for code, where in sorted(self._emitted().items()):
            for language in ("ko", "en"):
                if (f"cli.{code}" not in CATALOGS[language]
                        and f"hook.{code}" not in hook_i18n.FRAGMENTS[language]):
                    missing.append(f"{language}:{code} ({where})")
        self.assertEqual(missing, [], f"어느 catalog 에도 없는 code: {missing}")

    def test_the_oracle_actually_sees_the_engine(self):
        """스캔이 0건이면 위 검사는 아무것도 지키지 않는다 — 빈 통과를 막는다."""
        self.assertGreater(len(self._emitted()), 50)

    def test_no_diagnostic_uses_the_reserved_key_argument_name(self):
        """`Diagnostic(..., key=...)` 는 렌더 시점에 항상 깨진다 — 정적으로 막는다.

        `render_issue`/hook `translate` 는 모두 `lambda key, **arguments: tr(context, key,
        **arguments)` 형태다. 진단의 `arguments` 에 `key` 가 들어 있으면 위치 인자 `key`
        (catalog key 자체)와 이름이 겹쳐 `TypeError: got multiple values for argument 'key'`
        가 난다. 실제로 두 모듈(`runtime_hosts`·`overlay_materialize`)에서 이 형태로 터졌었다
        — 코드 리뷰로는 걸러지지 않았고 렌더를 실제로 실행해야만 드러났다. 다음 모듈이 같은
        이름을 또 쓰지 않도록 여기서 정적으로 막는다.
        """
        offenders = []
        for path in sorted((REPO / "sage").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "Diagnostic"):
                    for kw in node.keywords:
                        if kw.arg == "key":
                            offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
        self.assertEqual(offenders, [],
                         f"Diagnostic(key=...) 는 렌더 시 항상 TypeError 를 낸다: {offenders}")

    def test_no_tr_call_uses_the_reserved_key_argument_name(self):
        """`tr(context, key, **arguments)` 호출에 `key=...` 를 또 주면 렌더 시 항상 TypeError 다.

        `Diagnostic(key=...)` 와 같은 계열의 사고이지만 다른 지점에서 난다 — `tr()` 을 직접
        호출하며 catalog placeholder 이름으로 우연히 `key` 를 고르는 경우다. `_validate_hook_
        runtime_hash`(validate.py)·`_asset_entry_issue`/`_manifest_structure_issue`(install.py)
        에서 실제로 이 형태로 터졌다(다음엔 `field` 등 다른 이름을 쓰게 막는다) — 위
        `Diagnostic(key=...)` oracle 은 `tr()` 직접 호출은 못 본다."""
        offenders = []
        targets = list((REPO / "sage").rglob("*.py")) + list(RUNTIME.glob("*.py"))
        for path in sorted(targets):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "tr"):
                    for kw in node.keywords:
                        if kw.arg == "key":
                            offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
        self.assertEqual(offenders, [],
                         f"tr(key=...) 는 렌더 시 항상 TypeError 를 낸다: {offenders}")


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


class TestRuntimeJudgementReachesTheCliCatalog(unittest.TestCase):
    """설치 runtime 이 CLI 로 올려보내는 판정도 언어 중립이어야 한다.

    인벤토리는 `sage/` 를 파일 단위로 스캔한다. 그래서 CLI 모듈에 한국어 literal 이 0건이어도,
    그 모듈이 부른 runtime 함수가 완성된 한국어 문장을 돌려주면 `--lang en` 화면에 그대로
    실린다 — 인벤토리 0 이 "영어 화면에 한국어가 없다"를 뜻하지 못하는 구멍이다.

    runtime 은 `sage.i18n` 을 import 할 수 없으므로(엔진 없이 단독 실행) 진단을
    `{"code", "arguments", "evidence"}` 매핑으로 올리고 문장은 부른 쪽 catalog 가 만든다.
    """

    def test_korean_returning_runtime_functions_are_an_exact_declared_set(self):
        """검사 로직과 부채 목록은 build-time oracle 이 소유한다 — 테스트는 그걸 부른다.

        테스트 파일 안에만 있으면 릴리스 게이트가 같은 사실을 판정하지 못한다.
        """
        self.assertEqual([], runtime_judgement_issues(str(REPO)))

    def test_the_scan_actually_reads_the_runtime(self):
        """스캔이 빈 통과로 떨어지면 위 검사는 아무것도 지키지 않는다.

        실제 저장소의 KOREAN_JUDGEMENT_DEBT 는 이관이 끝나면 정당하게 빈 집합이 된다(6배치
        완료 시점 실제로 그렇다) — 그래서 "실제 부채가 5건보다 많다"로 스캐너를 증명할 수
        없다. 대신 통제된 fixture(한국어를 완성 문장으로 돌려주는 함수 1개를 심은 가짜
        runtime 트리)로 스캐너가 진짜로 찾아내는지 직접 확인한다."""
        found, errors = korean_returning_runtime_functions(str(REPO))
        self.assertEqual([], errors)
        self.assertEqual(KOREAN_JUDGEMENT_DEBT, found)

        with tempfile.TemporaryDirectory() as fake_root:
            runtime_dir = os.path.join(fake_root, "scripts", "sage_harness", "hooks", "runtime")
            os.makedirs(runtime_dir)
            for module in CLI_CONSUMED_RUNTIME_MODULES:
                path = os.path.join(runtime_dir, f"{module}.py")
                if module == "loop_audit":
                    Path(path).write_text(
                        "def planted(x):\n    return '이 문장은 완성된 한국어다'\n",
                        encoding="utf-8")
                else:
                    Path(path).write_text("# empty fixture module\n", encoding="utf-8")
            fixture_found, fixture_errors = korean_returning_runtime_functions(fake_root)
        self.assertEqual([], fixture_errors)
        self.assertEqual({"loop_audit.planted"}, fixture_found)

    def test_a_missing_runtime_module_is_an_error_not_a_pass(self):
        """파일을 못 읽었는데 빈 집합이 통과로 떨어지면 게이트가 사라진다."""
        with tempfile.TemporaryDirectory() as empty:
            found, errors = korean_returning_runtime_functions(empty)
            self.assertEqual(set(), found)
            self.assertEqual(len(CLI_CONSUMED_RUNTIME_MODULES), len(errors), errors)

    def test_remaining_debt_blocks_the_release_even_while_tracking_passes(self):
        """추적은 통과해도 publish 는 남은 부채 자체를 실패로 봐야 한다.

        실제 저장소는 6배치 완료 시점에 KOREAN_JUDGEMENT_DEBT 가 정당하게 비어 있어(모든
        runtime 판정이 이관됨) 추적·릴리스 둘 다 자연히 통과한다 — 그 상태로는 "추적은
        통과해도 릴리스는 막는다"는 이 게이트의 핵심 성질을 증명할 수 없다. 그래서 스캐너가
        부채 1건을 찾아냈고 그게 **선언된 목록과 정확히 일치**하는(=추적은 통과하는) 상태를
        mock 으로 재현해, 그래도 release_debt_issues 는 선언 여부와 무관하게 실제 잔존을
        그대로 차단한다는 것을 확인한다."""
        self.assertEqual([], runtime_judgement_issues(str(REPO)))     # 실제 저장소: 추적 통과(부채 0)
        self.assertEqual([], release_debt_issues(str(REPO)))          # 실제 저장소: 릴리스도 통과(부채 0)

        import sage.i18n.validation as validation_module
        with mock.patch.object(validation_module, "korean_returning_runtime_functions",
                               return_value=({"loop_audit.planted"}, [])), \
             mock.patch.object(validation_module, "KOREAN_JUDGEMENT_DEBT", frozenset({"loop_audit.planted"})):
            self.assertEqual([], validation_module.runtime_judgement_issues(str(REPO)),
                             "선언과 정확히 일치하면 추적은 통과해야 한다")
            blocking = validation_module.release_debt_issues(str(REPO))
        self.assertTrue(any("loop_audit.planted" in issue for issue in blocking), blocking)
        for key in sorted(KOREAN_IN_ENGLISH_DEBT):
            self.assertTrue(any(key in issue for issue in blocking), key)

    def test_loop_audit_is_migrated_and_its_codes_render_in_both_languages(self):
        from sage.i18n import CATALOGS
        tree = ast.parse((RUNTIME / "loop_audit.py").read_text(encoding="utf-8"))
        codes = {node.args[0].value for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id == "_diagnostic" and node.args
                 and isinstance(node.args[0], ast.Constant)}

        self.assertGreaterEqual(len(codes), 7)
        for code in sorted(codes):
            for language in ("ko", "en"):
                self.assertIn(f"cli.{code}", CATALOGS[language])

    def test_a_runtime_diagnostic_mapping_renders_like_a_diagnostic(self):
        """runtime 은 Diagnostic 을 만들 수 없다 — 매핑을 같은 계약으로 받아야 한다."""
        from sage.i18n import LanguageContext, render_issue
        mapping = {"code": "loop_audit.orphan_event", "evidence": "line 3: malformed JSON",
                   "arguments": {"event": "round", "run_id": "'rl-ghost'"}}

        english = render_issue(LanguageContext(language="en"), mapping)

        self.assertIn("rl-ghost", english)
        self.assertIn("line 3: malformed JSON", english)     # evidence 는 원문 그대로
        self.assertNotRegex(english, r"[가-힣]")
        self.assertNotEqual(english, render_issue(LanguageContext(language="ko"), mapping))


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
