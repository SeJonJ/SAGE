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
import unicodedata
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

    def _gate_with_change(self, docs, change, language=None):
        event = self._event(language)
        event["changes"] = [change]
        return self.core._document_language_gate(
            event, self.PROFILE, self._snapshot(docs), "demo")

    def test_the_marker_this_change_writes_is_judged(self):
        """디스크 snapshot 만 보면 이번 쓰기가 바꾸는 선언이 검사에서 통째로 빠진다 —
        en 사이클의 문서를 ko 로 돌려놓는 쓰기가 조용히 통과한다."""
        result = self._gate_with_change(
            {"00": "Document-Language: en\n", "01": "Document-Language: en\n"},
            {"path": "plan_docs/01-x/demo.md", "op": "write", "full_content": True,
             "content": "Cycle-Stem: `demo`\nDocument-Language: ko\n\nEnglish body.\n"},
            language="en")
        self.assertEqual(result["status"], "block")

    def test_a_reconstructed_partial_edit_marker_change_is_judged(self):
        """전체 쓰기만 보면 되짚어 만든 post-image 경로가 그대로 비어 있다."""
        result = self._gate_with_change(
            {"00": "Document-Language: en\n", "01": "Document-Language: en\n"},
            {"path": "plan_docs/01-x/demo.md", "op": "update",
             "content": "Document-Language: ko\n",
             "post_image": "Cycle-Stem: `demo`\nDocument-Language: ko\n"},
            language="en")
        self.assertEqual(result["status"], "block")

    def test_a_marker_duplicated_by_this_change_blocks(self):
        result = self._gate_with_change(
            {"00": "Document-Language: en\n", "01": "Document-Language: en\n"},
            {"path": "plan_docs/01-x/demo.md", "op": "write", "full_content": True,
             "content": "Cycle-Stem: `demo`\nDocument-Language: en\nDocument-Language: ko\n"},
            language="en")
        self.assertEqual(result["status"], "block")

    def test_a_new_phase_document_with_a_conflicting_marker_blocks(self):
        result = self._gate_with_change(
            {"00": "Document-Language: en\n"},
            {"path": "plan_docs/02-x/demo.md", "op": "add", "full_content": True,
             "content": "Cycle-Stem: `demo`\nDocument-Language: ko\n"},
            language="en")
        self.assertEqual(result["status"], "block")

    def test_a_change_that_keeps_the_same_language_still_passes(self):
        self.assertIsNone(self._gate_with_change(
            {"00": "Document-Language: en\n", "01": "Document-Language: en\n"},
            {"path": "plan_docs/01-x/demo.md", "op": "write", "full_content": True,
             "content": "Cycle-Stem: `demo`\nDocument-Language: en\n\nEnglish body.\n"},
            language="en"))

    def test_a_deleted_document_leaves_the_comparison_set(self):
        """지워지는 문서의 선언으로 남은 문서를 막으면 잘못 선언된 문서를 치울 방법이 없어진다."""
        self.assertIsNone(self._gate_with_change(
            {"00": "Document-Language: en\n", "01": "Document-Language: ko\n"},
            {"path": "plan_docs/01-x/demo.md", "op": "delete"},
            language="en"))

    def test_a_non_phase_document_is_not_pulled_into_the_set(self):
        """stem 이 같아도 phase 문서가 아니면 사이클 문서 집합이 아니다."""
        self.assertIsNone(self._gate_with_change(
            {"00": "Document-Language: en\n"},
            {"path": "docs/scratch/demo.md", "op": "write", "full_content": True,
             "content": "Cycle-Stem: `demo`\nDocument-Language: ko\n"},
            language="en"))

    def test_an_unreconstructible_change_leaves_the_marker_check_alone(self):
        """재구성 실패는 본문 게이트가 fail-closed 로 잡는다 — 여기서 조각을 문서로 오해하면
        정상 부분 편집이 전부 marker 미선언으로 떨어진다."""
        self.assertIsNone(self._gate_with_change(
            {"00": "Document-Language: en\n", "01": "Document-Language: en\n"},
            {"path": "plan_docs/01-x/demo.md", "op": "update",
             "content": "some English sentence\n", "post_image_error": "unreconstructible"},
            language="en"))

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
        self.assertTrue(pl.foreign_prose(text, "en"))

    def test_pure_english_prose_passes_for_english(self):
        text = "Document-Language: en\n\nThis is a plain english sentence.\n"
        self.assertEqual(pl.foreign_prose(text, "en"), [])

    def test_korean_prose_passes_for_korean(self):
        text = ("Document-Language: ko\n\n"
                "이 문서는 충분히 긴 한국어 문장으로 구성돼 있어 최소 표본 기준을 넘긴다.\n")
        self.assertFalse(pl.lacks_native_prose(text, "ko"))

    def test_all_english_body_is_flagged_for_korean(self):
        text = ("Document-Language: ko\n\n" +
               "This entire document is written in English even though it is declared "
               "Korean, which is exactly the structural mistake this smoke test exists "
               "to catch before anything lands on disk.\n")
        self.assertTrue(pl.lacks_native_prose(text, "ko"))

    def test_short_korean_document_is_not_flagged_by_the_smoke_threshold(self):
        """표본이 너무 작으면(제목뿐인 skeleton 등) 과차단하지 않는다."""
        text = "Document-Language: ko\n\n# Title\n"
        self.assertFalse(pl.lacks_native_prose(text, "ko"))

    def test_fenced_code_is_excluded(self):
        text = "Document-Language: en\n\n```text\n한글 예시\n```\nPlain english line here.\n"
        self.assertEqual(pl.foreign_prose(text, "en"), [])

    def test_inline_code_is_excluded(self):
        text = "Document-Language: en\n\nRun `한글명령어` now, in otherwise english prose.\n"
        self.assertEqual(pl.foreign_prose(text, "en"), [])

    def test_link_destination_is_excluded_but_link_text_is_not(self):
        text = "Document-Language: en\n\nSee [link](경로/한글.md) in otherwise english prose.\n"
        self.assertEqual(pl.foreign_prose(text, "en"), [])

    def test_blockquoted_external_evidence_is_excluded(self):
        text = "Document-Language: en\n\n> 한글 원문 인용\n\nEnglish prose continues here.\n"
        self.assertEqual(pl.foreign_prose(text, "en"), [])

    def test_machine_marker_values_are_not_korean(self):
        text = "Cycle-Stem: `stem`\nDocument-Language: en\nRisk Level: L2\n\nEnglish prose.\n"
        self.assertEqual(pl.foreign_prose(text, "en"), [])

    def test_korean_explanation_after_a_marker_value_is_still_prose(self):
        """고정 enum 뒤에 붙는 설명은 선택 언어로 쓰는 사람 글이다 — marker 줄이라는 이유로
        통째로 빼면 `Status:` 뒤에 무엇을 쓰든 검사에서 사라진다."""
        for line in ("Status: NOT READY — 아직 구현되지 않음",
                     "Final Status: FAIL — 재현 절차가 빠져 있음",
                     "Risk Level: L2 (문서만 바꾸므로 상향하지 않음)"):
            with self.subTest(line=line):
                text = f"Document-Language: en\n{line}\n\nEnglish body.\n"
                self.assertTrue(pl.foreign_prose(text, "en"), line)

    def test_marker_machine_values_do_not_count_toward_the_korean_sample(self):
        """marker 의 기계값을 표본에 세면 marker 만 늘어놓은 문서가 임계값을 넘어 오탐이 된다."""
        text = ("Document-Language: ko\nCycle-Stem: `some-fairly-long-cycle-stem`\n"
                "Final Status: NOT TESTED\nPhase00-Hash: sha256:0123456789abcdef\n")
        self.assertFalse(pl.lacks_native_prose(text, "ko"))

    def test_multi_backtick_inline_code_matches_the_same_length_run(self):
        """``…`` 안의 원문을 단일 backtick 규칙으로 자르면 안쪽 한글이 prose 로 샌다."""
        text = "Document-Language: en\n\nWrite ``한글 예시`` verbatim in english prose.\n"
        self.assertEqual(pl.foreign_prose(text, "en"), [])

    def test_an_unmatched_backtick_does_not_hide_korean(self):
        text = "Document-Language: en\n\nA stray ` and then 이것은 한글입니다 remains prose.\n"
        self.assertTrue(pl.foreign_prose(text, "en"))

    def test_backtick_runs_of_different_lengths_never_pair(self):
        """길이가 다른 run 을 code span 으로 오인하면, 잘못 쓴 Markdown 한 줄이 검사를 끈다."""
        for body in ("A `한글 `` B", "A 한글``` `` B", "A ```한글 `` B", "A ``한글 ` B"):
            with self.subTest(body=body):
                self.assertTrue(pl.foreign_prose(f"Document-Language: en\n\n{body}\n", "en"), body)

    def test_a_backtick_fence_with_a_backtick_in_its_info_string_is_not_a_fence(self):
        """CommonMark 는 backtick fence 의 info string 에 backtick 을 허용하지 않는다. 이걸
        열림으로 인정하면 ```lang` 한 줄이 뒤 본문 전체를 code 로 삼켜 검사에서 지운다."""
        text = "Document-Language: en\n\n```lang`\n이것은 한국어 본문입니다.\n"
        self.assertTrue(pl.foreign_prose(text, "en"))
        self.assertIsNone(pl.unclosed_fence(text))

    def test_a_tilde_fence_info_string_may_contain_backticks(self):
        """~~~ fence 는 info string 제약이 없다 — backtick 하나로 fence 를 깨면 그건 과차단이다."""
        text = "Document-Language: en\n\n~~~lang`\n한글 예시\n~~~\nEnglish prose.\n"
        self.assertEqual(pl.foreign_prose(text, "en"), [])

    def test_a_korean_marker_suffix_is_not_evidence_of_korean_prose(self):
        """marker suffix 한 줄로 구조 검사를 통과할 수 있으면, 본문 전체가 영어여도 막히지 않는다.
        같은 suffix 가 en 의 외국어 누출 검사에는 그대로 걸려야 한다(질문이 다르다)."""
        text = ("Document-Language: ko\nStatus: NOT READY — 한국어 설명\n\n"
                "The real body of this document is written entirely in English and is "
                "comfortably longer than the minimum prose sample.\n")
        self.assertTrue(pl.lacks_native_prose(text, "ko"))
        self.assertTrue(pl.foreign_prose(text.replace("ko", "en", 1), "en"))

    def test_every_declared_hangul_range_is_detected(self):
        """지원 범위를 상수로 모아둔 이유 — 범위마다 실제로 걸리는지 여기서 감사한다."""
        for low, high in pl.HANGUL_RANGES:
            for char in (low, high):
                with self.subTest(char=hex(ord(char))):
                    self.assertTrue(
                        pl.foreign_prose(f"Document-Language: en\n\nx {char} y\n", "en"))

    def test_declared_hangul_ranges_contain_only_assigned_hangul(self):
        """블록째로 잡으면 미할당 코드 포인트(U+3130 등)까지 한국어로 판정해, 쓰지도 않은 글자
        하나로 문서가 막힌다. 구간이 정말 전부 할당된 한글인지 unicodedata 로 감사한다."""
        offenders = []
        for low, high in pl.HANGUL_RANGES:
            for point in range(ord(low), ord(high) + 1):
                try:
                    name = unicodedata.name(chr(point))
                except ValueError:
                    offenders.append((hex(point), "UNASSIGNED"))
                    continue
                if "HANGUL" not in name and "KOREAN" not in name:
                    offenders.append((hex(point), name))
        self.assertEqual(offenders, [], f"한글이 아닌 코드 포인트가 범위에 있다: {offenders[:5]}")

    def test_known_unassigned_neighbours_are_not_detected(self):
        """경계 바로 밖의 미할당·비한글 코드 포인트가 새어 들어오지 않는지 반대편에서 고정한다."""
        for point in (0x3130, 0x318F, 0x321F, 0x327F, 0xA97D, 0xD7C7, 0xD7FC):
            with self.subTest(point=hex(point)):
                self.assertEqual(
                    pl.foreign_prose(f"Document-Language: en\n\nx {chr(point)} y\n", "en"), [])

    def test_a_shorter_fence_inside_a_longer_one_does_not_close_it(self):
        text = ("Document-Language: en\n\n````\n```\n한글 예시\n```\n````\n"
                "English prose after the nested fence.\n")
        self.assertEqual(pl.foreign_prose(text, "en"), [])
        self.assertIsNone(pl.unclosed_fence(text))

    def test_a_tilde_fence_is_not_closed_by_a_backtick_fence(self):
        text = "Document-Language: en\n\n~~~\nsample\n```\n"
        self.assertEqual(pl.unclosed_fence(text), 3)

    def test_an_unclosed_fence_is_reported_instead_of_swallowing_the_rest(self):
        text = "Document-Language: en\n\n```text\n예시\n\n이것은 본문입니다.\n"
        self.assertEqual(pl.unclosed_fence(text), 3)

    def test_a_closed_fence_reports_nothing(self):
        self.assertIsNone(pl.unclosed_fence("a\n```\nx\n```\nb\n"))

    def test_decomposed_hangul_is_detected(self):
        """NFD 로 분해된 한글은 완성형 범위에 안 걸린다 — 정규화 없이는 조용히 통과한다."""
        text = "Document-Language: en\n\n" + unicodedata.normalize("NFD", "이것은 한글입니다.") + "\n"
        self.assertTrue(pl.foreign_prose(text, "en"))

    def test_unresolved_language_never_blocks(self):
        for language in (None, "fr", "ko"):
            self.assertEqual(pl.foreign_prose("아무 내용", language), [])
        for language in (None, "fr", "en"):
            self.assertFalse(pl.lacks_native_prose("x" * 200, language))


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

    def _event(self, path, content, language=None, full=True):
        """full=True 는 Write / apply_patch Add File — content 가 곧 변경 후 전체 본문이다."""
        change = {"path": path, "content": content}
        if full and content is not None:
            change["full_content"] = True
        return {"hook_id": "pre-implementation-gate", "branch": "feat/demo",
                "cycle_stem": "demo", "cycle_stem_origin": "cli",
                "cycle_document_language": language, "declared_max": "",
                "changes": [change]}

    def _prose(self, path, content, phase00_language, declared=None, full=True):
        return self.core._document_prose_gate(
            self._event(path, content, declared, full), self._snapshot(phase00_language), "demo")

    def test_korean_prose_in_english_cycle_blocks(self):
        result = self._prose(
            "plan_docs/03-x/demo.md",
            "Cycle-Stem: `demo`\nDocument-Language: en\n\n이것은 한글 문장입니다.\n",
            phase00_language="en")
        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "block_document_prose_language")
        self.assertIn("이것은 한글 문장입니다", result["evidence"])

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
        self.assertEqual(result["key"], "block_document_prose_structure")

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

    def _partial(self, content, before, after, phase00_language):
        """되짚기가 성립한 부분 diff — content 는 조각, before/after 는 변경 전·후 전체 문서."""
        return self.core._document_prose_gate(
            {"cycle_document_language": phase00_language,
             "changes": [{"path": "plan_docs/03-x/demo.md", "content": content,
                          "pre_image": before, "post_image": after}]},
            self._snapshot(phase00_language), "demo")

    def test_a_partial_english_fragment_added_to_a_korean_document_does_not_block(self):
        """Claude Edit 의 new_string·Codex Update File 의 추가 줄은 문서 조각이지 문서가 아니다.
        조각을 문서 전체로 오해하면 정상 한국어 문서에 영어 한 문단을 더하는 편집이 곧바로 막힌다."""
        fragment = ("This appendix quotes the upstream release note verbatim because "
                    "translating it would change the evidence being cited here.\n")
        before = ("Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
                  "이 문서는 한국어로 작성된 정상 계획 문서이며 표본을 넘길 만큼 충분히 깁니다.\n")
        self.assertIsNone(self._partial(fragment, before, before + fragment, "ko"))

    def test_korean_added_inside_an_existing_fence_is_not_flagged(self):
        """추가된 조각만 떼어 보면 그 줄이 fence 안이었는지 알 수 없다 — 기존 code fence 에
        한국어 예시를 한 줄 넣는 정상 편집이 곧바로 차단된다."""
        head = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                "The tool prints the following:\n```text\n기존 예시\n")
        tail = "```\nEnglish narrative continues after the example block.\n"
        self.assertIsNone(self._partial("추가된 한국어 예시\n", head + tail,
                                        head + "추가된 한국어 예시\n" + tail, "en"))

    def test_korean_added_outside_the_fence_is_still_flagged(self):
        """fence 문맥을 존중한다는 것이 검사를 끄는 것이면 안 된다 — 바로 옆 줄은 여전히 걸린다."""
        before = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                  "The tool prints the following:\n```text\n기존 예시\n```\n")
        result = self._partial("이것은 fence 밖의 한국어 문장입니다.\n", before,
                               before + "이것은 fence 밖의 한국어 문장입니다.\n", "en")
        self.assertIsNotNone(result)
        self.assertEqual((result["key"], result["line"]), ("block_document_prose_language", 8))

    def test_pre_existing_korean_is_not_retroactively_flagged(self):
        """이미 있던 위반은 그대로 통과시킨다 — 아니면 legacy 문서 하나가 이후 모든 편집을
        막는다(§7.7). 차단하는 것은 이번 변경이 **늘린** 부채뿐이다."""
        before = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                  "예전에 남아 있던 한국어 문장입니다.\n")
        added = "This line is the one being added right now.\n"
        self.assertIsNone(self._partial(added, before, before + added, "en"))

    def test_deleting_a_fence_that_exposes_existing_korean_is_flagged(self):
        """새 줄이 하나도 없어도 부채는 늘어난다 — fence 를 지우면 안에 있던 한국어가 본문이
        된다. "추가된 줄" 만 보는 모델은 이 경로를 통째로 놓친다."""
        before = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                  "```text\n한글 원문\n```\nEnglish narrative.\n")
        after = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                 "한글 원문\nEnglish narrative.\n")
        result = self._partial("", before, after, "en")
        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "block_document_prose_language")

    def test_removing_a_blockquote_marker_that_exposes_korean_is_flagged(self):
        before = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                  "> 인용된 한국어 원문\nEnglish narrative.\n")
        after = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                 "인용된 한국어 원문\nEnglish narrative.\n")
        self.assertIsNotNone(self._partial("", before, after, "en"))

    def test_removing_inline_backticks_that_expose_korean_is_flagged(self):
        before = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                  "Run `한글명령어` to reproduce.\n")
        after = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                 "Run 한글명령어 to reproduce.\n")
        self.assertIsNotNone(self._partial("", before, after, "en"))

    def test_removing_link_syntax_that_exposes_korean_is_flagged(self):
        before = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                  "See [the doc](경로/한글.md) for background.\n")
        after = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                 "See 경로/한글.md for background.\n")
        self.assertIsNotNone(self._partial("", before, after, "en"))

    def test_an_inherited_unclosed_fence_does_not_block_later_edits(self):
        """물려받은 결함으로 편집을 막으면 고칠 방법이 없어진다."""
        before = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n```text\nsample\n")
        self.assertIsNone(self._partial("more\n", before, before + "more\n", "en"))

    def test_an_already_all_english_korean_document_does_not_block_later_edits(self):
        """ko 선언인데 이미 한국어가 없던 문서 — 편집할 때마다 막으면 고칠 수가 없다."""
        before = ("Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
                  "This document was already written entirely in English before this edit, "
                  "and the sample is long enough to trip the structural smoke check.\n")
        self.assertIsNone(self._partial("More English.\n", before, before + "More English.\n", "ko"))

    def test_a_move_only_destination_is_judged_on_the_moved_body(self):
        """hunk 없는 rename 으로 사이클 안에 들어오는 문서 — 목적지에는 아직 아무것도 없었으니
        옮겨온 내용 전체가 새 부채다. 실물 shim 에서는 결속이 먼저 막지만, 판정 계층 자체가
        이 경로를 비워두면 결속 조건이 다른 구성에서 그대로 우회로가 된다."""
        moved = ("Document-Language: ko\n\nThis document is entirely English even though "
                 "the cycle it lands in declares Korean.\n")
        result = self.core._document_prose_gate(
            {"cycle_document_language": "ko",
             "changes": [{"path": "plan_docs/03-x/demo.md", "op": "move", "content": "",
                          "source_path": "docs/scratch.md",
                          "pre_image": "", "post_image": moved}]},
            self._snapshot("ko"), "demo")
        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "block_document_prose_structure")

    def test_a_move_only_destination_with_a_proper_korean_body_passes(self):
        moved = ("Document-Language: ko\n\n"
                 "이 문서는 한국어로 작성된 정상 계획 문서이며 표본을 넘길 만큼 충분히 깁니다.\n")
        self.assertIsNone(self.core._document_prose_gate(
            {"cycle_document_language": "ko",
             "changes": [{"path": "plan_docs/03-x/demo.md", "op": "move", "content": "",
                          "source_path": "docs/scratch.md",
                          "pre_image": "", "post_image": moved}]},
            self._snapshot("ko"), "demo"))

    def test_a_write_without_any_post_image_contract_fails_closed(self):
        """쓰기는 하는데 변경 후 문서를 알 수 없는 도구가 있으면, 그 도구가 곧 우회로다."""
        result = self.core._document_prose_gate(
            {"cycle_document_language": "en",
             "changes": [{"path": "plan_docs/03-x/demo.md", "content": "이것은 한글입니다.\n"}]},
            self._snapshot("en"), "demo")
        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "block_document_post_image")

    def test_a_full_write_that_leaves_no_korean_in_a_korean_document_blocks(self):
        """반대로 변경 후 전체 본문을 알 때는 반드시 판정한다 — 부분 diff 라는 이유로 이 자리를
        비워두면 한국어를 걷어내는 편집이 조용히 통과한다(검수 재현 사례)."""
        image = ("Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
                 "The Korean narrative that used to live here was replaced wholesale by "
                 "this English paragraph, leaving the document without any Korean prose.\n")
        result = self.core._document_prose_gate(
            {"cycle_document_language": "ko",
             "changes": [{"path": "plan_docs/03-x/demo.md", "content": "English paragraph.\n",
                          "post_image": image}]},
            self._snapshot("ko"), "demo")
        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "block_document_prose_structure")

    def test_an_unclosed_fence_in_the_post_image_blocks(self):
        content = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n```text\nsample\n\n"
                   "이것은 fence 뒤에 삼켜지는 한국어 본문입니다.\n")
        result = self._prose("plan_docs/03-x/demo.md", content, phase00_language="en")
        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "block_document_unclosed_fence")

    def test_a_partial_diff_that_closes_an_open_fence_is_not_judged_as_unclosed(self):
        """조각만 보면 fence 짝이 맞지 않는다 — fence 를 닫는 정상 편집이 오히려 차단된다.
        판정은 되짚은 전체 문서에 대해서만 성립한다."""
        image = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n```text\nsample\n```\n"
                 "English narrative after the block.\n")
        before = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n```text\nsample\n")
        self.assertIsNone(self._partial("```\n", before, image, "en"))

    def test_an_unreconstructible_post_image_fails_closed(self):
        """되짚기 실패를 "못 봤으니 통과" 로 처리하면, 되짚기를 깨뜨리는 것이 곧 우회로가 된다."""
        result = self.core._document_prose_gate(
            {"cycle_document_language": "ko",
             "changes": [{"path": "plan_docs/03-x/demo.md", "content": "x\n",
                          "post_image_error": "unreconstructible"}]},
            self._snapshot("ko"), "demo")
        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "block_document_post_image")

    def test_a_non_markdown_file_with_the_same_stem_is_not_prose_checked(self):
        """이 모듈의 규칙은 전부 Markdown 구조다 — 같은 stem 의 소스 파일에 적용하면 주석 한 줄로
        차단되거나 되짚기 실패로 막힌다."""
        for change in ({"path": "backend/demo.java", "content": "// 한글 주석\n",
                        "full_content": True},
                       {"path": "backend/demo.java", "content": "x\n",
                        "post_image_error": "unreconstructible"}):
            with self.subTest(change=change):
                self.assertIsNone(self.core._document_prose_gate(
                    {"cycle_document_language": "en", "changes": [change]},
                    self._snapshot("en"), "demo"))

    def test_a_missing_prose_module_fails_closed_instead_of_passing(self):
        """판정 정본이 사라졌는데 통과시키면 파일 하나 지우는 것이 게이트를 끄는 스위치가 된다."""
        saved = sys.modules.get("prose_language")
        sys.modules["prose_language"] = None          # import 시 ImportError
        try:
            event = self._event(
                "plan_docs/03-x/demo.md",
                "Cycle-Stem: `demo`\nDocument-Language: en\n\n이것은 한글 문장입니다.\n", "en")
            result = self.core._document_prose_gate(event, self._snapshot("en"), "demo")
            decision = self.core.decide(event, self.PROFILE, self._snapshot("en"), None)
        finally:
            if saved is None:
                del sys.modules["prose_language"]
            else:
                sys.modules["prose_language"] = saved
        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "block_prose_scanner_unavailable")
        self.assertEqual((decision["status"], decision["exit_code"]), ("block", 2))
        # 판정이 만드는 것은 원문 예외뿐이다. 여기서 영어 문장을 지어내면 한국어 화면에
        # 그 문장이 그대로 실려 나간다(영어 화면에 한국어가 새는 것과 같은 결함, 방향만 반대).
        self.assertTrue(result["evidence"].split(":")[0].endswith("Error"), result["evidence"])
        sys.path.insert(0, str(RUNTIME))
        import messages
        text = messages.gate_text(decision, {}, "claude", language="ko")
        self.assertNotIn("import failed", text)
        self.assertIn("본문 언어 판정 모듈", text)

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

    def test_all_prose_message_keys_render_in_both_locales(self):
        sys.path.insert(0, str(RUNTIME))
        import messages
        for key in ("block_document_prose_language", "block_document_prose_structure",
                    "block_document_unclosed_fence", "block_document_post_image",
                    "block_prose_scanner_unavailable"):
            for language in ("ko", "en"):
                text = messages.gate_text(
                    {"message_key": key, "status": "block",
                     "reason": "r", "cycle_stem": "demo", "risk": "PDCA"},
                    {}, "claude", language=language)
                self.assertTrue(text and "message_key=" not in text, (key, language))

    def test_the_english_render_carries_no_generated_korean_explanation(self):
        """설명 문장을 판정 계층이 만들면 영어 화면에 그대로 실려 나간다. 두 언어에서 같아야
        하는 것은 **원문 조각(evidence)** 뿐이고, 나머지 글자는 catalog 소유여야 한다."""
        sys.path.insert(0, str(RUNTIME))
        import messages
        event = self._event(
            "plan_docs/03-x/demo.md",
            "Cycle-Stem: `demo`\nDocument-Language: en\n\n이것은 한글 문장입니다.\n", "en")
        decision = self.core.decide(event, self.PROFILE, self._snapshot("en"), None)
        text = messages.gate_text(decision, {}, "claude", language="en")
        # evidence 로 인용된 원문 조각만 제거하면 영어 화면에는 한글이 한 글자도 남지 않아야 한다.
        self.assertIn("이것은 한글 문장입니다", text)
        self.assertNotRegex(text.replace(decision["reason"], ""), r"[가-힣]")

    def test_an_all_english_korean_document_also_renders_hangul_free_in_english(self):
        sys.path.insert(0, str(RUNTIME))
        import messages
        event = self._event(
            "plan_docs/03-x/demo.md",
            "Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
            "This whole document is English even though the cycle declares Korean, and "
            "the sample is long enough to trip the structural smoke check.\n", "ko")
        decision = self.core.decide(event, self.PROFILE, self._snapshot("ko"), None)
        self.assertEqual(decision["message_key"], "block_document_prose_structure")
        text = messages.gate_text(decision, {}, "claude", language="en")
        self.assertNotRegex(text, r"[가-힣]")


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
