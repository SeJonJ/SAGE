#!/usr/bin/env python3
"""사이클 문서 언어 — Phase 00 정본, cycle state 미러, legacy 해석.

사이클 중간에 문서 언어가 바뀌면 00~06 이 섞여 검토가 성립하지 않는다. 그래서 여기서 고정하는
것은 "무슨 언어인가"가 아니라 "한 번 정해진 뒤 바뀌지 않는가"와 "어긋났을 때 조용히 넘어가지
않는가"다.

부재와 손상을 구분하는 것도 계약이다. 둘이 똑같이 조용하면 파일 한 글자만 깨뜨려도 선언이
사라지고, 그게 곧 우회 레버가 된다.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
RUNTIME = REPO / "scripts/sage_harness/hooks/runtime"
sys.path.insert(0, str(RUNTIME))

import cycle_state as cs  # noqa: E402
import document_language as dl  # noqa: E402


class TestMarkerScan(unittest.TestCase):
    def test_exact_marker_is_read(self):
        for language in ("ko", "en"):
            self.assertEqual(dl.scan(f"# 제목\n\nDocument-Language: {language}\n"),
                             (language, ""))

    def test_marker_inside_a_fence_does_not_count(self):
        """문서에 사용법을 적는 순간 중복이 되면 안내를 쓸 수 없다."""
        text = ("Document-Language: ko\n\n"
                "```text\nDocument-Language: en\n```\n")
        self.assertEqual(dl.scan(text), ("ko", ""))

    def test_missing_duplicate_and_invalid_are_distinguished(self):
        self.assertEqual(dl.scan("# 제목\n")[1], dl.MISSING)
        self.assertEqual(dl.scan("Document-Language: ko\nDocument-Language: en\n")[1],
                         dl.DUPLICATE)
        self.assertEqual(dl.scan("Document-Language: fr\n")[1], dl.INVALID)

    def test_marker_must_stand_alone_on_its_line(self):
        self.assertEqual(dl.scan("본문 중 Document-Language: ko 언급\n")[1], dl.MISSING)

    def test_locale_catalog_is_not_imported(self):
        """표시 언어와 문서 언어는 수명이 다르다 — 한 곳에서 섞이면 안 된다."""
        source = (RUNTIME / "document_language.py").read_text(encoding="utf-8")
        for line in source.splitlines():
            if line.strip().startswith(("import ", "from ")):
                self.assertNotIn("i18n", line)


class TestConsistency(unittest.TestCase):
    def test_matching_documents_pass(self):
        docs = {f"{n}.md": "Document-Language: en\n" for n in ("00", "01", "02")}
        self.assertEqual(dl.consistency_issues(docs), [])

    def test_mixed_languages_are_reported_for_every_document(self):
        docs = {"00.md": "Document-Language: ko\n", "01.md": "Document-Language: en\n"}
        issues = dl.consistency_issues(docs)
        self.assertEqual(len(issues), 2)
        self.assertTrue(all("mismatch" in reason for _, reason in issues))

    def test_state_mirror_disagreement_is_a_conflict_not_a_tiebreak(self):
        docs = {"00.md": "Document-Language: en\n"}
        issues = dl.consistency_issues(docs, declared="ko")
        self.assertEqual(len(issues), 1)
        self.assertIn("state-mismatch", issues[0][1])

    def test_a_missing_marker_is_reported_per_document(self):
        docs = {"00.md": "Document-Language: ko\n", "01.md": "# 제목\n"}
        issues = dl.consistency_issues(docs)
        self.assertEqual([p for p, _ in issues], ["01.md"])


class TestDeclarationRecord(unittest.TestCase):
    def _root(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
        return root

    def test_absent_declaration_is_not_an_error(self):
        record = cs.read_declaration_record(self._root())
        self.assertEqual((record.stem, record.document_language, record.error), ("", None, ""))
        self.assertFalse(record.legacy)

    def test_v2_round_trip_carries_the_language(self):
        root = self._root()
        cs.write_declaration(root, "demo", document_language="en")
        record = cs.read_declaration_record(root)
        self.assertEqual((record.stem, record.document_language, record.schema_version),
                         ("demo", "en", 2))
        self.assertFalse(record.legacy)

    def test_version_one_reads_as_legacy_without_inventing_a_language(self):
        """None 을 ko 로 채우면 '선언한 적 없음'과 '한국어로 선언함'이 같은 값이 된다."""
        import json
        root = self._root()
        Path(root, ".sage", "cycle.json").write_text(
            json.dumps({"version": 1, "cycle_stem": "demo"}), encoding="utf-8")
        record = cs.read_declaration_record(root)
        self.assertEqual(record.stem, "demo")
        self.assertIsNone(record.document_language)
        self.assertTrue(record.legacy)

    def test_stem_only_read_stays_compatible_across_versions(self):
        import json
        root = self._root()
        Path(root, ".sage", "cycle.json").write_text(
            json.dumps({"version": 1, "cycle_stem": "demo"}), encoding="utf-8")
        self.assertEqual(cs.read_declaration(root), ("demo", ""))
        cs.write_declaration(root, "demo", document_language="ko")
        self.assertEqual(cs.read_declaration(root), ("demo", ""))

    def test_invalid_language_is_an_error_not_a_fallback(self):
        import json
        root = self._root()
        Path(root, ".sage", "cycle.json").write_text(
            json.dumps({"version": 2, "cycle_stem": "demo", "document_language": "fr"}),
            encoding="utf-8")
        record = cs.read_declaration_record(root)
        self.assertTrue(record.error)
        self.assertIsNone(record.document_language)

    def test_write_refuses_an_unsupported_language(self):
        root = self._root()
        for bad in ("fr", "KO", "", None):
            with self.assertRaises(ValueError, msg=bad):
                cs.write_declaration(root, "demo", document_language=bad)

    def test_write_requires_the_language_explicitly(self):
        """누락을 ko 로 조용히 채우면 마이그레이션이 언제 끝났는지 셀 수 없다."""
        with self.assertRaises(TypeError):
            cs.write_declaration(self._root(), "demo")


class TestProductionCallSites(unittest.TestCase):
    def test_every_production_write_passes_a_language(self):
        """정적 call-site 검사 — 새 호출부가 인자를 빠뜨리면 런타임 전에 잡는다."""
        import ast
        offenders = []
        for path in sorted((REPO / "sage").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "write_declaration"):
                    if "document_language" not in {kw.arg for kw in node.keywords}:
                        offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
        self.assertEqual(offenders, [], f"document_language 없이 선언을 쓰는 곳: {offenders}")


if __name__ == "__main__":
    unittest.main()
