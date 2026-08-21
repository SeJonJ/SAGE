#!/usr/bin/env python3
"""설치 hook locale — 독립 실행성과 두 도메인 정합.

hook 은 소비 프로젝트에 설치된 runtime 으로 돈다. 거기에 엔진이 있으리라는 보장이 없어서,
`sage` 를 import 하는 순간 hook 은 엔진 없이는 못 도는 물건이 된다. 그건 게이트가 조용히
사라지는 경로라 import 가능 여부 자체를 고정한다.

CLI 와 key 를 공유하지 않는 것도 계약이다. 같은 문장의 소유자가 둘이 되면 한쪽만 고쳐도
다른 쪽이 남아 어느 것이 실제로 나가는지 알 수 없다.
"""
import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
RUNTIME = REPO / "scripts/sage_harness/hooks/runtime"
LOCALE = RUNTIME / "i18n"
MESSAGES = RUNTIME / "messages.py"

sys.path.insert(0, str(RUNTIME))
from i18n import CATALOGS, HOOK_MESSAGE_KEYS, tr  # noqa: E402


def _emitted_keys():
    """messages.py 의 게이트 표에 실제로 등장하는 message_key 집합."""
    source = MESSAGES.read_text(encoding="utf-8")
    tree = ast.parse(source)
    keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                # (sev, scope, show_reason, hint) — 문구는 catalog 소유라 여기 없다.
                if (isinstance(key, ast.Constant) and isinstance(key.value, str)
                        and isinstance(value, ast.Tuple) and len(value.elts) == 4
                        and isinstance(value.elts[0], ast.Constant)
                        and value.elts[0].value in ("BLOCK", "WARN", "OK")):
                    keys.add(key.value)
    return keys


# 이 모듈들의 `_diagnostic(...)` code 만 hook 자체 catalog(messages.py 의 _i18n.tr)로 렌더된다.
# loop_audit·fast_cycle_audit 도 같은 `_diagnostic()` 패턴을 쓰지만 그 진단은 CLI(sage.i18n,
# `cli.<code>`)에서만 소비된다 — hook_runtime.py 가 직접 부르지 않는다(retro/cycle 배치에서
# 확인). 여기 없는 모듈의 code 를 hook catalog 에 요구하면 안 된다. 새 모듈이 hook 게이트에서
# 직접 렌더되기 시작하면(예: 이후 배치의 checklist_contract) 이 튜플에 추가한다.
_HOOK_RENDERED_DIAGNOSTIC_MODULES = ("cycle_state.py",)


def _diagnostic_keys():
    """`_HOOK_RENDERED_DIAGNOSTIC_MODULES` 의 `_diagnostic("literal", ...)` 호출에서 code 를 모은다.

    이 code 들은 게이트 표를 거치지 않고 `_i18n.tr(language, diagnostic["code"],
    **diagnostic["arguments"])` 로 직접 렌더된다(sage.diagnostics 를 import 할 수 없는 hook
    runtime 이 code+arguments dict 로 진단을 올리는 공통 패턴, retro 배치의 loop_audit
    이관에서 시작됐다). `diagnostic["code"]` 는 런타임 값이라 messages.py 만 봐서는 무엇이
    나가는지 알 수 없고, code 리터럴 자체를 아는 유일한 자리는 이 `_diagnostic(...)` 호출부뿐이다.
    """
    keys = set()
    for name in _HOOK_RENDERED_DIAGNOSTIC_MODULES:
        tree = ast.parse((RUNTIME / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_diagnostic" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                keys.add(node.args[0].value)
    return keys


def _direct_tr_keys():
    """messages.py 가 게이트 표 밖에서 `_i18n.tr(language, "literal", ...)` 로 직접 부르는 key.

    `cycle_declaration_ignored` 같은 진단-래핑 문장이 여기 해당한다 — 진단 자체(code+arguments)는
    `_diagnostic_keys()` 가 잡고, 그걸 감싸는 고정 문장은 여기서 리터럴로 잡힌다.
    """
    tree = ast.parse(MESSAGES.read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "tr"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "_i18n"
                and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)):
            keys.add(node.args[1].value)
    return keys


class TestRuntimeIndependence(unittest.TestCase):
    def test_locale_imports_without_the_engine_package(self):
        """`sage` import 를 실패하게 만든 상태에서도 locale 이 살아야 한다."""
        script = (
            "import sys\n"
            "class Block:\n"
            "    def find_module(self, name, path=None):\n"
            "        if name == 'sage' or name.startswith('sage.'):\n"
            "            raise ImportError('engine package is not installed here')\n"
            "sys.meta_path.insert(0, Block())\n"
            f"sys.path.insert(0, {str(RUNTIME)!r})\n"
            "from i18n import CATALOGS, HOOK_MESSAGE_KEYS, tr\n"
            "assert len(HOOK_MESSAGE_KEYS) > 0\n"
            "assert tr('en', 'ok_l1')\n"
            "print('ok')\n"
        )
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                                input="", cwd=str(REPO))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)

    def test_locale_source_never_names_the_engine_package(self):
        for path in sorted(LOCALE.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            for line in source.splitlines():
                stripped = line.strip()
                if stripped.startswith(("import ", "from ")):
                    self.assertNotRegex(stripped, r"\bsage\b",
                                        f"{path.name}: hook locale 은 엔진을 import 하지 않는다")


class TestDomainSeparation(unittest.TestCase):
    def test_hook_keys_stay_out_of_the_cli_catalog(self):
        sys.path.insert(0, str(REPO))
        from sage.i18n import CATALOGS as CLI  # noqa: E402
        overlap = sorted(set(CLI["ko"]) & set(CATALOGS["ko"]))
        self.assertEqual(overlap, [], f"두 도메인이 같은 key 를 씀: {overlap}")

    def test_compatibility_keys_are_preserved(self):
        """이름이 바뀌면 이 key 를 읽는 소비자와 과거 감사 기록이 함께 끊긴다."""
        for key in ("ok_l0", "ok_l1", "ok_l2", "ok_l3"):
            self.assertIn(key, CATALOGS["ko"])
            self.assertIn(key, CATALOGS["en"])


class TestCatalogParity(unittest.TestCase):
    def test_key_sets_match(self):
        self.assertEqual(set(CATALOGS["ko"]), set(CATALOGS["en"]))

    def test_placeholders_match(self):
        import string
        for key in sorted(CATALOGS["ko"]):
            names = []
            for language in ("ko", "en"):
                names.append({n for _, n, _, _ in
                              string.Formatter().parse(CATALOGS[language][key]) if n})
            self.assertEqual(names[0], names[1], key)

    def test_every_emitted_key_exists_in_both_catalogs(self):
        """번역 문자열을 뒤지지 않고 판정 표의 key 집합과 직접 대조한다."""
        emitted = _emitted_keys()
        self.assertTrue(emitted, "게이트 표를 읽지 못했다 — 검사기가 빈 집합을 통과시키면 안 된다")
        for language in ("ko", "en"):
            missing = sorted(emitted - set(CATALOGS[language]))
            self.assertEqual(missing, [], f"{language} catalog 에 없는 emit key: {missing}")

    def test_exported_key_set_matches_actual_usage(self):
        """catalog 의 모든 key 는 실제로 나가는 경로(게이트 표 · 진단 code · 직접 tr 호출)
        중 하나에 있어야 한다 — 아무도 안 부르는 죽은 key 나, 등록 안 된 채 나가는 key 가
        조용히 남으면 안 된다."""
        self.assertEqual(set(HOOK_MESSAGE_KEYS),
                         _emitted_keys() | _diagnostic_keys() | _direct_tr_keys())


class TestFallback(unittest.TestCase):
    def test_unknown_key_surfaces_its_name(self):
        self.assertEqual(tr("en", "nope"), "[SAGE] message_key=nope")

    def test_missing_selected_language_falls_back_to_korean(self):
        original = CATALOGS["en"].pop("ok_l1")
        try:
            self.assertEqual(tr("en", "ok_l1"), CATALOGS["ko"]["ok_l1"])
        finally:
            CATALOGS["en"]["ok_l1"] = original

    def test_argument_mismatch_does_not_raise(self):
        self.assertEqual(tr("ko", "block_phase_incomplete"),
                         "[SAGE] message_key=block_phase_incomplete")


class TestLanguageResolution(unittest.TestCase):
    def test_absent_local_profile_is_korean(self):
        from i18n.context import resolve
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(resolve(root), ("ko", False))

    def test_local_profile_selects_and_damage_is_reported(self):
        from i18n.context import resolve
        import os
        import tempfile
        cases = [("interface:\n  language: en\n", ("en", False)),
                 ("interface:\n  language: fr\n", ("ko", True)),
                 ("interface:\n", ("ko", True)),
                 ("runtime:\n  installed_hosts: [claude]\n", ("ko", False))]
        for raw, expected in cases:
            with tempfile.TemporaryDirectory() as root:
                os.makedirs(os.path.join(root, "sage"))
                Path(root, "sage", "project-profile.local.yaml").write_text(raw, encoding="utf-8")
                self.assertEqual(resolve(root), expected, raw)

    def test_resolution_needs_no_yaml_dependency(self):
        """pyyaml 부재가 게이트를 멈추게 하면 안 된다 — 언어 한 줄에 의존성을 요구하지 않는다."""
        source = (LOCALE / "context.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"^\s*import yaml", )
        self.assertIsNotNone(re.search(r"^import re$", source, re.M))


class TestDecisionIndependence(unittest.TestCase):
    """언어가 판정에 닿으면 같은 입력이 사람마다 다른 결과를 낸다 — 거버넌스가 개인 설정에 물린다."""

    def _decision(self, key):
        return {"message_key": key, "status": "block", "exit_code": 2,
                "risk": "L3", "file_short": "a/b.py", "reason": "근거",
                "missing_phases": ["01", "02"], "cycle_stem": "demo"}

    def test_only_the_sentence_differs_between_locales(self):
        import messages
        for key in sorted(_emitted_keys()):
            decision = self._decision(key)
            before = dict(decision)
            rendered = {lang: messages.gate_text(decision, {}, "claude", lang)
                        for lang in ("ko", "en")}
            self.assertEqual(decision, before, f"{key}: 렌더가 decision 을 변형했다")
            self.assertTrue(rendered["ko"] and rendered["en"], key)

    def test_severity_tag_and_exit_are_locale_invariant(self):
        import messages
        for key in sorted(_emitted_keys()):
            decision = self._decision(key)
            tags = set()
            for lang in ("ko", "en"):
                line = messages.gate_text(decision, {}, "claude", lang)
                tags.add(line.split("]")[0] + "]")
            self.assertEqual(len(tags), 1, f"{key}: locale 별 GATE 태그가 다르다 — {tags}")

    def test_unknown_locale_falls_back_without_changing_the_tag(self):
        import messages
        decision = self._decision("block_l3_no_plan")
        korean = messages.gate_text(decision, {}, "claude", "ko")
        unknown = messages.gate_text(decision, {}, "claude", "fr")
        self.assertEqual(korean, unknown)



class TestEnglishRenderHasNoKoreanLeftovers(unittest.TestCase):
    """en 렌더에 한글이 남는지 본다 — 이관은 "옮겼다"가 아니라 "남은 게 없다"로만 끝난다.

    key 대조만으로는 부족하다. 표에 문구가 한 벌 더 남아 있으면 두 catalog 는 완전히 일치하는데
    화면에는 표의 한국어가 나간다. 실제로 hint 가 그 상태였고, catalog 정합 테스트는 통과했다.

    `reason` 은 예외다. 판정 core 가 만든 언어 중립 증거이고 두 언어가 **같아야** 하므로 여기서
    번역 대상이 아니다 — 그래서 인자를 비워 렌더한다.
    """

    HANGUL = re.compile(r"[가-힣]")
    # 백틱 안은 사용자가 **그대로 입력하거나 실행해야 하는 토큰**이다. `위험도 선언 해제` 는
    # capture_declared_risk_core 가 실제로 매칭하는 구절이라, 번역하면 안내대로 따라한 사용자가
    # 아무 일도 일어나지 않는 문구를 입력하게 된다. 번역 대상 문장과 불변 토큰의 경계다
    # (docs/agent/language-policy.md).
    TOKEN = re.compile(r"`[^`]*`")

    def _prose(self, text):
        return self.TOKEN.sub("", text or "")

    def test_no_message_key_renders_korean_in_english(self):
        offenders = []
        import messages
        for key in sorted(_emitted_keys()):
            for runtime in ("claude", "codex"):
                decision = {"message_key": key, "status": _status_of(key), "risk": "L2",
                            "reason": "", "file_short": "a.src", "missing_phases": ["01"],
                            "cycle_stem": "demo", "cycle_source": ["branch-leaf"],
                            "phase00_risk": "L1", "required_risk": "L2"}
                text = messages.gate_text(decision, {}, runtime, language="en")
                found = self.HANGUL.search(self._prose(text))
                if found:
                    offenders.append((key, runtime, found.group()))
        self.assertEqual(offenders, [], f"en 렌더에 한글이 남았다: {offenders}")

    def test_the_declaration_repair_path_is_also_english(self):
        """계산 hint 는 분기마다 다른 조각을 쓴다 — 한 분기만 보면 나머지가 한국어로 남는다."""
        import messages
        for source in (["branch-leaf"], ["event"], []):
            for flag in (True, False):
                decision = {"message_key": "block_cycle_risk_reconciliation", "status": "block",
                            "risk": "L2", "reason": "", "file_short": "a.src",
                            "cycle_stem": "demo", "cycle_source": source,
                            "phase00_risk": "L1", "required_risk": "L2",
                            "risk_from_declaration": flag, "phase00_path": "p.md"}
                text = messages.gate_text(decision, {}, "claude", language="en")
                self.assertIsNone(self.HANGUL.search(self._prose(text)),
                                  f"source={source} flag={flag}: {text}")


def _status_of(key):
    return "block" if key.startswith("block") else ("warn" if key.startswith("warn") else "ok")

if __name__ == "__main__":
    unittest.main()
