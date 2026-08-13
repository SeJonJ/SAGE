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

    def test_exported_key_set_matches_the_gate_table(self):
        self.assertEqual(set(HOOK_MESSAGE_KEYS), _emitted_keys())


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
        for key in sorted(HOOK_MESSAGE_KEYS):
            decision = self._decision(key)
            before = dict(decision)
            rendered = {lang: messages.gate_text(decision, {}, "claude", lang)
                        for lang in ("ko", "en")}
            self.assertEqual(decision, before, f"{key}: 렌더가 decision 을 변형했다")
            self.assertTrue(rendered["ko"] and rendered["en"], key)

    def test_severity_tag_and_exit_are_locale_invariant(self):
        import messages
        for key in sorted(HOOK_MESSAGE_KEYS):
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


if __name__ == "__main__":
    unittest.main()
