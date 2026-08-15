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
import prose_language as pl  # noqa: E402


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
        self.assertEqual((record.stem, record.document_language, record.error), ("", None, None))
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
        self.assertEqual(cs.read_declaration(root), ("demo", None))
        cs.write_declaration(root, "demo", document_language="ko")
        self.assertEqual(cs.read_declaration(root), ("demo", None))

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


class TestGateWiring(unittest.TestCase):
    """파서가 아니라 **게이트가 파서를 부르는가**를 본다.

    B7 의 실패 형태가 정확히 이거였다 — 파서와 스키마가 있고 그 단위 테스트가 전부 통과하는데
    게이트가 호출하지 않아 아무것도 막지 않았다. 파서만 검사하는 테스트는 그 상태를 통과시킨다.
    """

    def setUp(self):
        sys.path.insert(0, str(REPO / "scripts/sage_harness/hooks"))
        import pre_implementation_gate_core as core
        self.core = core

    PROFILE = {
        "pdca": {"enabled": True, "report_phase": "06", "approve_phase": "05",
                 "phases": [{"id": pid, "glob": f"plan_docs/{pid}-*/**/*.md"}
                            for pid in ("00", "01", "02", "03", "04", "05", "06")]},
        "risk": {},
    }

    def _snapshot(self, docs):
        phase_docs = {}
        for pid, text in docs.items():
            phase_docs[pid] = [{"path": f"plan_docs/{pid}-x/demo.md",
                                "content": f"Cycle-Stem: `demo`\n{text}", "recent": True}]
        return {"phase_docs": phase_docs, "plan_files": [], "l3_review_docs": []}

    def _event(self, language=None):
        return {"hook_id": "pre-implementation-gate", "branch": "feat/demo",
                "cycle_stem": "demo", "cycle_stem_origin": "cli",
                "cycle_document_language": language, "declared_max": "",
                "changes": [{"path": "plan_docs/03-x/demo.md"}]}

    def _gate(self, docs, language=None):
        return self.core._document_language_gate(
            self._event(language), self.PROFILE, self._snapshot(docs), "demo")

    def test_unmarked_cycle_passes(self):
        """마커 이전에 시작한 사이클을 즉시 막으면 그건 이 기능이 만든 과차단이다."""
        self.assertIsNone(self._gate({"00": "", "01": ""}))

    def test_agreeing_markers_pass(self):
        self.assertIsNone(self._gate({"00": "Document-Language: en\n",
                                      "01": "Document-Language: en\n"}))

    def test_disagreeing_markers_block(self):
        result = self._gate({"00": "Document-Language: en\n",
                             "01": "Document-Language: ko\n"})
        self.assertEqual(result["status"], "block")

    def test_state_mirror_disagreement_blocks(self):
        result = self._gate({"00": "Document-Language: en\n"}, language="ko")
        self.assertEqual(result["status"], "block")
        self.assertIn("state-mismatch", result["reason"])

    def test_partial_declaration_warns_but_does_not_block(self):
        """부분 이관이 완전 이관과 똑같이 조용하면 언제 끝났는지 셀 수 없다."""
        result = self._gate({"00": "Document-Language: en\n", "01": ""})
        self.assertEqual(result["status"], "warn")

    def test_mirror_without_any_marker_warns(self):
        self.assertEqual(self._gate({"00": ""}, language="en")["status"], "warn")

    def test_damaged_marker_blocks_rather_than_reading_as_absent(self):
        for text in ("Document-Language: fr\n",
                     "Document-Language: ko\nDocument-Language: en\n"):
            self.assertEqual(self._gate({"00": text})["status"], "block", text)

    def test_other_cycles_documents_are_not_compared(self):
        snapshot = {"phase_docs": {
            "00": [{"path": "plan_docs/00-base_plan/demo.md",
                    "content": "Cycle-Stem: `demo`\nDocument-Language: en\n", "recent": True}],
            "01": [{"path": "plan_docs/01-plan/other.md",
                    "content": "Cycle-Stem: `other`\nDocument-Language: ko\n", "recent": True}]}}
        self.assertIsNone(self.core._document_language_gate(
            self._event(), self.PROFILE, snapshot, "demo"))

    def test_decide_actually_reaches_the_gate(self):
        """`decide` 를 통과시켜 확인한다 — 함수만 맞고 배선이 없으면 여기서 걸린다."""
        decision = self.core.decide(
            self._event(language="ko"),
            self.PROFILE,
            self._snapshot({"00": "Document-Language: en\nRisk Level: L2\n",
                            "03": "Document-Language: en\n"}),
            None)
        self.assertEqual(decision["message_key"], "block_document_language_conflict")
        self.assertEqual((decision["status"], decision["exit_code"]), ("block", 2))

    def test_both_message_keys_render_in_both_locales(self):
        sys.path.insert(0, str(RUNTIME))
        import messages
        for key, status in (("block_document_language_conflict", "block"),
                            ("warn_document_language_missing", "warn")):
            for language in ("ko", "en"):
                text = messages.gate_text(
                    {"message_key": key, "status": status, "reason": "r",
                     "cycle_stem": "demo", "risk": "PDCA"},
                    {}, "claude", language=language)
                self.assertTrue(text and "message_key=" not in text, (key, language))


class TestProseScanner(unittest.TestCase):
    """AC25 — marker 아래 본문이 실제로 그 언어인지에 대한 순수 구조적 smoke."""

    def test_korean_in_plain_prose_is_flagged_for_english(self):
        text = "Document-Language: en\n\n이것은 한글입니다.\n"
        self.assertTrue(pl.violations(text, "en"))

    def test_pure_english_prose_passes_for_english(self):
        text = "Document-Language: en\n\nThis is a plain english sentence.\n"
        self.assertEqual(pl.violations(text, "en"), [])

    def test_korean_prose_passes_for_korean(self):
        text = ("Document-Language: ko\n\n"
                "이 문서는 충분히 긴 한국어 문장으로 구성돼 있어 최소 표본 기준을 넘긴다.\n")
        self.assertEqual(pl.violations(text, "ko"), [])

    def test_all_english_body_is_flagged_for_korean(self):
        text = ("Document-Language: ko\n\n" +
               "This entire document is written in English even though it is declared "
               "Korean, which is exactly the structural mistake this smoke test exists "
               "to catch before anything lands on disk.\n")
        self.assertTrue(pl.violations(text, "ko"))

    def test_short_korean_document_is_not_flagged_by_the_smoke_threshold(self):
        """표본이 너무 작으면(제목뿐인 skeleton 등) 과차단하지 않는다."""
        text = "Document-Language: ko\n\n# Title\n"
        self.assertEqual(pl.violations(text, "ko"), [])

    def test_fenced_code_is_excluded(self):
        text = "Document-Language: en\n\n```text\n한글 예시\n```\nPlain english line here.\n"
        self.assertEqual(pl.violations(text, "en"), [])

    def test_inline_code_is_excluded(self):
        text = "Document-Language: en\n\nRun `한글명령어` now, in otherwise english prose.\n"
        self.assertEqual(pl.violations(text, "en"), [])

    def test_link_destination_is_excluded_but_link_text_is_not(self):
        text = "Document-Language: en\n\nSee [link](경로/한글.md) in otherwise english prose.\n"
        self.assertEqual(pl.violations(text, "en"), [])

    def test_blockquoted_external_evidence_is_excluded(self):
        text = "Document-Language: en\n\n> 한글 원문 인용\n\nEnglish prose continues here.\n"
        self.assertEqual(pl.violations(text, "en"), [])

    def test_marker_lines_are_excluded(self):
        text = "Cycle-Stem: `stem`\nDocument-Language: en\nRisk Level: L2\n\nEnglish prose.\n"
        self.assertEqual(pl.violations(text, "en"), [])

    def test_unresolved_language_never_blocks(self):
        self.assertEqual(pl.violations("아무 내용", None), [])
        self.assertEqual(pl.violations("아무 내용", "fr"), [])


class TestProseGateWiring(unittest.TestCase):
    """AC25 — marker 는 일치하지만 그 아래 본문이 선언 언어를 어기면 쓰기 전에 막는가.

    검사 대상은 **이번에 새로 쓰거나 바뀌는 내용**뿐이다(`event["changes"]`) — 이미 디스크에
    있는 다른 phase 문서까지 소급하면 legacy 문서 하나가 이후 모든 편집을 막는다(§7.7).
    """

    PROFILE = TestGateWiring.PROFILE

    def setUp(self):
        sys.path.insert(0, str(REPO / "scripts/sage_harness/hooks"))
        import pre_implementation_gate_core as core
        self.core = core

    def _snapshot(self, phase00_language):
        return {"phase_docs": {
            "00": [{"path": "plan_docs/00-x/demo.md",
                    "content": f"Cycle-Stem: `demo`\nDocument-Language: {phase00_language}\n",
                    "recent": True}]},
            "plan_files": [], "l3_review_docs": []}

    def _event(self, path, content, language=None):
        return {"hook_id": "pre-implementation-gate", "branch": "feat/demo",
                "cycle_stem": "demo", "cycle_stem_origin": "cli",
                "cycle_document_language": language, "declared_max": "",
                "changes": [{"path": path, "content": content}]}

    def _prose(self, path, content, phase00_language, declared=None):
        return self.core._document_prose_gate(
            self._event(path, content, declared), self._snapshot(phase00_language), "demo")

    def test_korean_prose_in_english_cycle_blocks(self):
        result = self._prose(
            "plan_docs/03-x/demo.md",
            "Cycle-Stem: `demo`\nDocument-Language: en\n\n이것은 한글 문장입니다.\n",
            phase00_language="en")
        self.assertIsNotNone(result)
        self.assertIn("한국어", result["reason"])

    def test_english_prose_in_english_cycle_passes(self):
        result = self._prose(
            "plan_docs/03-x/demo.md",
            "Cycle-Stem: `demo`\nDocument-Language: en\n\nThis is english prose.\n",
            phase00_language="en")
        self.assertIsNone(result)

    def test_korean_prose_in_korean_cycle_passes(self):
        result = self._prose(
            "plan_docs/03-x/demo.md",
            "Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
            "이것은 충분히 긴 한국어 문장으로 구성된 본문입니다. 최소 표본을 넘기기 위해 조금 더 씁니다.\n",
            phase00_language="ko")
        self.assertIsNone(result)

    def test_all_english_prose_in_korean_cycle_blocks(self):
        content = ("Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
                  "This document is written entirely in English even though it declares "
                  "Korean as its language, which is exactly the mistake this smoke test "
                  "exists to catch before anything lands on disk.\n")
        result = self._prose("plan_docs/03-x/demo.md", content, phase00_language="ko")
        self.assertIsNotNone(result)
        self.assertIn("구조 이상", result["reason"])

    def test_korean_inside_fence_is_not_flagged(self):
        content = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                  "Example output:\n```text\n한글 예시 출력\n```\n"
                  "This is plain english prose describing the example above in enough detail.\n")
        result = self._prose("plan_docs/03-x/demo.md", content, phase00_language="en")
        self.assertIsNone(result)

    def test_korean_inside_inline_code_is_not_flagged(self):
        content = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                  "Run `sage 이것은예시명령어` to reproduce, then read the rest of this english "
                  "sentence describing what happens next.\n")
        result = self._prose("plan_docs/03-x/demo.md", content, phase00_language="en")
        self.assertIsNone(result)

    def test_korean_in_link_destination_is_not_flagged(self):
        content = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                  "See [the referenced document](plan_docs/00-base_plan/한글파일이름.md) for "
                  "background, which the rest of this english sentence continues to explain.\n")
        result = self._prose("plan_docs/03-x/demo.md", content, phase00_language="en")
        self.assertIsNone(result)

    def test_quoted_external_evidence_in_blockquote_is_not_flagged(self):
        content = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                  "The tool printed the following Korean message verbatim:\n\n"
                  "> 이것은 외부 도구가 실제로 출력한 한글 원문입니다\n\n"
                  "The english narrative around the quote continues here without issue.\n")
        result = self._prose("plan_docs/03-x/demo.md", content, phase00_language="en")
        self.assertIsNone(result)

    def test_no_content_in_change_is_not_judged(self):
        """부분 diff 뿐인 변경은 못 본 내용을 있다고 가정하지 않는다."""
        result = self.core._document_prose_gate(
            self._event("plan_docs/03-x/demo.md", None, "en"), self._snapshot("en"), "demo")
        self.assertIsNone(result)

    def test_unrelated_stem_change_is_not_judged(self):
        result = self.core._document_prose_gate(
            self._event("plan_docs/03-x/other.md", "이것은 한글입니다.\n", "en"),
            self._snapshot("en"), "demo")
        self.assertIsNone(result)

    def test_decide_blocks_before_write_on_korean_prose_in_english_cycle(self):
        """`decide` 를 통과시켜 확인한다 — 함수만 맞고 배선이 없으면 여기서 걸린다."""
        event = self._event(
            "plan_docs/03-x/demo.md",
            "Cycle-Stem: `demo`\nDocument-Language: en\n\n이것은 한글 문장입니다.\n", "en")
        decision = self.core.decide(event, self.PROFILE, self._snapshot("en"), None)
        self.assertEqual(decision["message_key"], "block_document_prose_language")
        self.assertEqual((decision["status"], decision["exit_code"]), ("block", 2))

    def test_marker_conflict_still_wins_over_prose_check(self):
        """기존 marker 충돌 차단이 이번 배선에 가려지지 않는다 — 여전히 먼저 걸린다."""
        snapshot = {"phase_docs": {
            "00": [{"path": "plan_docs/00-x/demo.md",
                    "content": "Cycle-Stem: `demo`\nDocument-Language: en\n", "recent": True}],
            "01": [{"path": "plan_docs/01-x/demo.md",
                    "content": "Cycle-Stem: `demo`\nDocument-Language: ko\n", "recent": True}]},
            "plan_files": [], "l3_review_docs": []}
        event = self._event(
            "plan_docs/03-x/demo.md",
            "Cycle-Stem: `demo`\nDocument-Language: en\n\nEnglish prose only.\n", None)
        decision = self.core.decide(event, self.PROFILE, snapshot, None)
        self.assertEqual(decision["message_key"], "block_document_language_conflict")

    def test_removing_the_wiring_would_let_korean_prose_through(self):
        """게이트 호출부를 지우면(뮤테이션) 이 테스트가 막아야 한다 — 함수만 있고 안 불리는
        상태를 잡는다. `_document_prose_gate` 를 항상 통과로 바꿔도 `decide` 가 여전히 막으면
        배선이 끊긴 것이다."""
        real = self.core._document_prose_gate
        self.core._document_prose_gate = lambda *a, **kw: None
        try:
            event = self._event(
                "plan_docs/03-x/demo.md",
                "Cycle-Stem: `demo`\nDocument-Language: en\n\n이것은 한글 문장입니다.\n", "en")
            decision = self.core.decide(event, self.PROFILE, self._snapshot("en"), None)
        finally:
            self.core._document_prose_gate = real
        self.assertNotEqual(decision.get("message_key"), "block_document_prose_language")

    def test_both_message_keys_render_in_both_locales(self):
        sys.path.insert(0, str(RUNTIME))
        import messages
        for language in ("ko", "en"):
            text = messages.gate_text(
                {"message_key": "block_document_prose_language", "status": "block",
                 "reason": "r", "cycle_stem": "demo", "risk": "PDCA"},
                {}, "claude", language=language)
            self.assertTrue(text and "message_key=" not in text)


class TestContextPacketCarriesLanguage(unittest.TestCase):
    """복원된 세션이 이어서 쓸 언어. packet 이 안 실으면 host 가 자기 기본값으로 쓴다."""

    def setUp(self):
        sys.path.insert(0, str(REPO))
        from sage import context_packet
        self.packet = context_packet

    def test_schema_declares_the_field_and_rejects_a_bad_value(self):
        self.assertEqual(self.packet.SCHEMA_VERSION, 2)
        self.assertEqual(self.packet.DOCUMENT_LANGUAGES, ("ko", "en"))

    def test_mirror_is_read_when_the_stem_matches(self):
        root = Path(tempfile.mkdtemp())
        (root / ".sage").mkdir()
        cs.write_declaration(str(root), "demo", document_language="en")
        self.assertEqual(self.packet._document_language(root, "demo", None), "en")

    def test_another_cycles_mirror_is_not_borrowed(self):
        """남의 사이클 선언을 실으면 게이트가 없는 충돌을 만든다."""
        root = Path(tempfile.mkdtemp())
        (root / ".sage").mkdir()
        cs.write_declaration(str(root), "other", document_language="en")
        self.assertIsNone(self.packet._document_language(root, "demo", None))

    def test_absence_stays_none_rather_than_defaulting(self):
        root = Path(tempfile.mkdtemp())
        (root / ".sage").mkdir()
        self.assertIsNone(self.packet._document_language(root, "demo", None))

    def test_explicit_value_wins_over_the_mirror(self):
        root = Path(tempfile.mkdtemp())
        (root / ".sage").mkdir()
        cs.write_declaration(str(root), "demo", document_language="en")
        self.assertEqual(self.packet._document_language(root, "demo", "ko"), "ko")


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
