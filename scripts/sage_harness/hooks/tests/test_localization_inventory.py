#!/usr/bin/env python3
"""사용자 표시 literal 인벤토리가 코드와 어긋나지 않는다.

인벤토리는 catalog 이관의 진척을 세는 유일한 근거다. 코드가 앞서가면 새로 생긴 문구가 목록에
없는 채로 "남은 게 없다"가 되고, 인벤토리가 앞서가면 이미 옮긴 것이 계속 남은 것으로 세어진다.
둘 중 어느 쪽이든 남은 개수가 사실이 아니게 되므로 재생성 여부를 결정론으로 검사한다.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
GENERATOR = REPO / "scripts/ci/build_localization_inventory.py"
INVENTORY = REPO / "docs/sage_harness/localization-inventory.json"

_REQUIRED_FIELDS = {"id", "domain", "key", "source_file", "source_symbol", "channel",
                    "exit_contract", "format", "placeholders", "machine_consumer",
                    "classification", "required_tests"}


def _document():
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


class TestLocalizationInventory(unittest.TestCase):
    def test_inventory_matches_the_code(self):
        result = subprocess.run([sys.executable, str(GENERATOR), "--root", str(REPO), "--check"],
                                capture_output=True, text=True, input="")
        self.assertEqual(result.returncode, 0,
                         f"{result.stdout}{result.stderr}\n"
                         f"재생성: python3 {GENERATOR.relative_to(REPO)}")

    def test_every_entry_carries_the_contract_fields(self):
        missing = [entry["id"] for entry in _document()["entries"]
                   if not _REQUIRED_FIELDS <= set(entry)]
        self.assertEqual(missing, [], f"필수 필드가 빠진 항목: {missing[:5]}")

    def test_ids_are_unique(self):
        ids = [entry["id"] for entry in _document()["entries"]]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(duplicates, [], f"id 중복 — 진척 계산이 어긋난다: {duplicates[:5]}")

    def test_channel_and_classification_are_closed_vocabularies(self):
        for entry in _document()["entries"]:
            self.assertIn(entry["channel"], ("stdout", "stderr"), entry["id"])
            self.assertTrue(
                entry["classification"].startswith(("argparse.", "command_", "validation_")),
                entry["id"])

    def test_assigned_keys_use_the_cli_namespace(self):
        """이관하면서 key 를 채울 때 namespace 를 벗어나면 hook 도메인과 충돌할 수 있다."""
        stray = [entry["id"] for entry in _document()["entries"]
                 if entry["key"] is not None and not entry["key"].startswith("cli.")]
        self.assertEqual(stray, [], f"cli. namespace 밖 key: {stray[:5]}")

    def test_domain_owner_matches_the_design(self):
        owner = _document()["domain_owner"]
        self.assertEqual(owner["cli"], "sage/i18n")
        self.assertEqual(owner["hook"], "scripts/sage_harness/hooks/runtime/i18n")



class TestInventoryCountsWhatTheScreenShows(unittest.TestCase):
    """세는 범위가 화면보다 좁으면 셈 자체가 거짓이 된다.

    실측된 실패: `sage/commands` 이관이 끝나 인벤토리가 **0 을 보고하는 시점**에도
    `sage --lang en doctor` 는 한국어를 냈다. 원인이 둘이었다.

      1. 깊이 — 조건식 안의 한국어(`... + (f", 갱신필요 {n}" if n else "")`)를 따라가지 않았다.
      2. 범위 — 검증 계층(`profile_validate` 등)이 화면에 찍히는데 세지 않았다.

    0 이 "남은 게 없다"로 읽히는 자리라, 이 두 구멍은 조용한 통과와 같은 값이었다.
    """

    def _generate(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_inv", GENERATOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_korean_inside_a_conditional_expression_is_counted(self):
        import ast
        inv = self._generate()
        source = 'print(f"a" + (f", 갱신필요 {n}" if n else ""))\n'
        node = ast.parse(source).body[0].value
        found = inv._korean_literals(node, source)
        self.assertTrue(found, "조건식 안의 한국어를 세지 않는다")

    def test_an_fstring_counts_once_not_per_fragment(self):
        import ast
        inv = self._generate()
        source = 'x = f"앞 {a} 뒤 {b} 끝"\n'
        node = ast.parse(source).body[0].value
        self.assertEqual(len(inv._korean_literals(node, source)), 1)

    def test_the_validation_layer_is_in_scope(self):
        inv = self._generate()
        modules = {parts[-1] for parts in inv.VALIDATION_RELS}
        self.assertIn("profile_validate.py", modules)
        self.assertIn("model_routing.py", modules)

    def test_hook_reachable_modules_are_marked(self):
        """hook 경로 모듈에 `sage.i18n` 을 넣으면 hook 이 엔진 의존이 된다 — 표시가 그 경계다."""
        entries = _document()["entries"]
        validation = [e for e in entries if e["classification"] == "validation_message"]
        if not validation:
            self.skipTest("검증 계층 이관 완료 — 표시할 항목이 없다")
        self.assertTrue(all("hook_reachable" in e for e in validation))
        marked = {e["source_file"] for e in validation if e["hook_reachable"]}
        self.assertTrue(marked, "hook 경로 모듈이 하나도 표시되지 않았다")

    def test_commands_layer_has_no_remaining_korean(self):
        """이관이 끝난 계층이 다시 늘어나면 즉시 잡는다."""
        entries = _document()["entries"]
        remaining = [e for e in entries
                     if e["source_file"].replace("\\", "/").startswith("sage/commands/")]
        self.assertEqual(remaining, [], f"sage/commands 에 한국어가 다시 생겼다: {remaining[:3]}")

if __name__ == "__main__":
    unittest.main()
