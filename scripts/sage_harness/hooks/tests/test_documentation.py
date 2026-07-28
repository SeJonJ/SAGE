#!/usr/bin/env python3
"""Documentation structure and bilingual onboarding regression tests."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LOCAL_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


class TestDocumentationStructure(unittest.TestCase):
    def test_bilingual_readme_index_and_quickstart_pairs_exist(self):
        pairs = [
            ("README.md", "README.en.md"),
            ("docs/README.md", "docs/README.en.md"),
            ("docs/quickstart.md", "docs/quickstart.en.md"),
        ]
        for korean, english in pairs:
            with self.subTest(korean=korean, english=english):
                ko_text = (ROOT / korean).read_text(encoding="utf-8")
                en_text = (ROOT / english).read_text(encoding="utf-8")
                self.assertIn(Path(english).name, ko_text)
                self.assertIn(Path(korean).name, en_text)

    def test_root_readmes_stay_focused(self):
        for relative in ("README.md", "README.en.md"):
            with self.subTest(relative=relative):
                lines = (ROOT / relative).read_text(encoding="utf-8").splitlines()
                self.assertLessEqual(len(lines), 200)

    def test_reference_documents_exist(self):
        for relative in (
            "docs/cli-reference.md",
            "docs/profile-reference.md",
            "docs/troubleshooting.md",
            "docs/ARCHITECTURE.md",
            "docs/ARTIFACTS.md",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_source_distribution_includes_bilingual_docs(self):
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        self.assertIn("include README.md", manifest)
        self.assertIn("include README.en.md", manifest)
        self.assertIn("recursive-include docs ", manifest)

    def test_local_markdown_links_resolve(self):
        documents = [
            ROOT / "README.md",
            ROOT / "README.en.md",
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "README.en.md",
            ROOT / "docs" / "quickstart.md",
            ROOT / "docs" / "quickstart.en.md",
        ]
        for document in documents:
            for target in LOCAL_LINK.findall(document.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                clean = target.split("#", 1)[0]
                with self.subTest(document=document.name, target=target):
                    self.assertTrue((document.parent / clean).resolve().exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
