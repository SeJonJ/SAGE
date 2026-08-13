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
            self.assertTrue(entry["classification"].startswith(("argparse.", "command_")),
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


if __name__ == "__main__":
    unittest.main()
