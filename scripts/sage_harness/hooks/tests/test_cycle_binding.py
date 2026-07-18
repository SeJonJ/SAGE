#!/usr/bin/env python3
import os
import sys
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.dirname(HERE)
sys.path.insert(0, HOOKS)

import cycle_binding as binding  # noqa: E402


PDCA = {"phases": [
    {"id": "01", "glob": "plan_docs/01-plan/**/*.md"},
    {"id": "04", "glob": "plan_docs/04-analyze/**/*.md"},
    {"id": "06", "glob": "plan_docs/06-report/**/*.md"},
]}


def doc(phase, stem, declared=None):
    value = stem if declared is None else declared
    return {"path": f"plan_docs/{phase}/{stem}.md",
            "content": f"Cycle-Stem: `{value}`\n", "recent": True}


class TestCycleBinding(unittest.TestCase):
    def test_recursive_phase_glob_matches_markdown_only(self):
        pattern = "plan_docs/01-plan/**/*.md"
        self.assertTrue(binding.matches_glob("plan_docs/01-plan/feature.md", pattern))
        self.assertTrue(binding.matches_glob("plan_docs/01-plan/nested/feature.md", pattern))
        self.assertFalse(binding.matches_glob("plan_docs/01-plan/notes.txt", pattern))

    def test_recursive_glob_matches_zero_segments_at_leading_and_trailing_positions(self):
        self.assertTrue(binding.matches_glob("01-feature.md", "**/01-*.md"))
        self.assertTrue(binding.matches_glob("plan_docs", "plan_docs/**"))
        self.assertTrue(binding.matches_glob("plan_docs/a/b.md", "plan_docs/**"))
        self.assertFalse(binding.matches_glob("other/a.md", "plan_docs/**"))

    def test_phase_glob_normalizes_equivalent_relative_paths(self):
        pattern = "plan_docs/06-report/**/*.md"
        for path in (
            "plan_docs/./06-report/feature.md",
            "plan_docs//06-report/feature.md",
            "plan_docs/05-expert-review/../06-report/feature.md",
        ):
            with self.subTest(path=path):
                self.assertTrue(binding.matches_glob(path, pattern))
        self.assertFalse(binding.matches_glob("../outside/06-report/feature.md", pattern))
        self.assertFalse(binding.matches_glob("..plan_docs/06-report/feature.md", pattern))

    def test_ticketless_branch_leaf_resolves_exactly(self):
        result = binding.resolve({"branch": "feat/weather-search", "changes": [{"path": "src/a.py"}]}, {}, PDCA)
        self.assertEqual(result, {"stem": "weather-search", "error": None, "source": ["branch-leaf"]})

    def test_phase_write_uses_path_and_declaration_not_branch(self):
        event = {"branch": "main", "changes": [{
            "path": "plan_docs/06-report/weather-search.md",
            "content": "Cycle-Stem: `weather-search`\nStatus: COMPLETE\n",
        }]}
        self.assertEqual(binding.resolve(event, {}, PDCA)["stem"], "weather-search")

    def test_existing_update_can_use_snapshot_declaration(self):
        existing = doc("06-report", "weather-search")
        event = {"branch": "main", "changes": [{"path": existing["path"], "content": "Status: COMPLETE\n"}]}
        snapshot = {"phase_docs": {"06": [existing]}}
        self.assertEqual(binding.resolve(event, snapshot, PDCA)["stem"], "weather-search")

    def test_fenced_declaration_is_not_document_identity(self):
        fenced_only = "```yaml\nCycle-Stem: `weather-search`\n```\n"
        self.assertIn("declaration missing", binding.declared_stem(fenced_only)[1])
        self.assertIn("declaration missing", binding.document_identity({
            "path": "weather-search.md", "content": fenced_only,
        })[1])

    def test_indented_code_declaration_is_not_document_identity(self):
        for label, indented in (
            ("spaces", "    Cycle-Stem: `weather-search`\n"),
            ("tab", "\tCycle-Stem: `weather-search`\n"),
        ):
            with self.subTest(label=label):
                self.assertIn("declaration missing", binding.declared_stem(indented)[1])
                self.assertIn("declaration missing", binding.document_identity({
                    "path": "weather-search.md", "content": indented,
                })[1])

    def test_partial_update_with_fenced_example_can_use_real_snapshot_declaration(self):
        existing = doc("06-report", "weather-search")
        event = {"branch": "main", "changes": [{
            "path": existing["path"], "op": "update",
            "content": "```yaml\nCycle-Stem: `example`\n```\n",
        }]}
        snapshot = {"phase_docs": {"06": [existing]}}
        self.assertEqual(binding.resolve(event, snapshot, PDCA)["stem"], "weather-search")

    def test_existing_full_write_without_declaration_fails_closed(self):
        existing = doc("06-report", "weather-search")
        event = {"branch": "main", "changes": [{
            "path": existing["path"], "op": "write", "content": "Status: COMPLETE\n",
        }]}
        snapshot = {"phase_docs": {"06": [existing]}}
        self.assertIn("declaration missing", binding.resolve(event, snapshot, PDCA)["error"])

    def test_existing_update_cannot_remove_or_duplicate_declaration(self):
        existing = doc("06-report", "weather-search")
        snapshot = {"phase_docs": {"06": [existing]}}
        removed = {"branch": "main", "changes": [{
            "path": existing["path"], "op": "update", "content": "Status: COMPLETE\n",
            "removed_content": "Cycle-Stem: `weather-search`\n",
        }]}
        duplicate = {"branch": "main", "changes": [{
            "path": existing["path"], "op": "update",
            "content": "Cycle-Stem: `weather-search`\nCycle-Stem: `evil`\n",
        }]}
        self.assertIn("declaration missing", binding.resolve(removed, snapshot, PDCA)["error"])
        self.assertIn("exactly once", binding.resolve(duplicate, snapshot, PDCA)["error"])

    def test_phase_document_delete_binds_to_valid_snapshot(self):
        existing = doc("06-report", "weather-search")
        event = {"branch": "main", "changes": [{
            "path": existing["path"], "op": "delete", "content": "",
        }]}
        snapshot = {"phase_docs": {"06": [existing]}}
        self.assertEqual(binding.resolve(event, snapshot, PDCA)["stem"], "weather-search")

    def test_new_phase_document_without_declaration_fails(self):
        event = {"branch": "main", "changes": [{
            "path": "plan_docs/06-report/weather-search.md", "content": "Status: COMPLETE\n"}]}
        self.assertIn("declaration missing", binding.resolve(event, {}, PDCA)["error"])

    def test_path_declaration_conflict_fails(self):
        event = {"branch": "main", "changes": [{
            "path": "plan_docs/06-report/weather-search.md",
            "content": "Cycle-Stem: `other-cycle`\n",
        }]}
        self.assertIn("path stem", binding.resolve(event, {}, PDCA)["error"])

    def test_multiple_changed_cycle_stems_are_ambiguous(self):
        event = {"branch": "main", "changes": [
            {"path": "plan_docs/01-plan/a.md", "content": "Cycle-Stem: `a`\n"},
            {"path": "plan_docs/04-analyze/b.md", "content": "Cycle-Stem: `b`\n"},
        ]}
        self.assertIn("candidate count", binding.resolve(event, {}, PDCA)["error"])

    def test_select_rejects_duplicate_same_stem(self):
        docs = [doc("01-plan", "x"), doc("nested", "x")]
        selected, error = binding.select_document(docs, "x")
        self.assertIsNone(selected)
        self.assertIn("ambiguous", error)

    def test_select_rejects_declaration_drift(self):
        selected, error = binding.select_document([doc("01-plan", "x", declared="y")], "x")
        self.assertIsNone(selected)
        self.assertIn("path stem", error)

    def test_branch_numbers_are_not_split(self):
        first = binding.resolve({"branch": "feat/141-sd3", "changes": [{"path": "src/a.py"}]}, {}, PDCA)
        second = binding.resolve({"branch": "release/v2", "changes": [{"path": "src/a.py"}]}, {}, PDCA)
        self.assertEqual(first["stem"], "141-sd3")
        self.assertEqual(second["stem"], "v2")

    def test_non_markdown_file_under_phase_directory_is_not_a_phase_write(self):
        result = binding.resolve({"branch": "feat/current", "changes": [{
            "path": "plan_docs/01-plan/notes.txt", "content": "plain attachment",
        }]}, {}, PDCA)
        self.assertEqual(result["stem"], "current")


if __name__ == "__main__":
    unittest.main(verbosity=2)
