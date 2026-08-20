#!/usr/bin/env python3
"""Phase 00 Risk Level 선언 파서의 단일 정본 계약.

이 파서가 생기기 전에는 gate 와 hook runtime 이 각자 정규식을 들고 서로 다르게 읽었다.
gate 쪽은 문서 전체를 훑어 본문 산문의 `Risk Level` 언급까지 선언 후보로 잡았고, 그 결과
이 저장소의 Phase 00 38개 중 6개가 실제로 오판된다(§2.3 실측). hook runtime 쪽은 헤더만
보지만 label 강조와 오류 종류 구분이 없다. 두 규칙의 옳은 쪽만 모아 여기서 고정한다.
"""

import os
import re
import sys
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HOOKS_DIR)))
sys.path.insert(0, HOOKS_DIR)

import risk_declaration as rd  # noqa: E402


def header(*lines):
    """헤더 metadata 영역만으로 이뤄진 최소 문서."""
    return "# Title\n\n" + "\n".join(lines) + "\n"


class TestValidDeclaration(unittest.TestCase):
    def test_plain_declaration_reports_tier_and_line(self):
        d = rd.parse("# Title\n\nCycle-Stem: `x`\nRisk Level: L3\n")
        self.assertEqual(d.status, "valid")
        self.assertEqual(d.tier, "L3")
        self.assertEqual(d.line, 4)

    def test_every_tier_including_l0_is_recognized(self):
        for tier in ("L0", "L1", "L2", "L3"):
            d = rd.parse(header(f"Risk Level: {tier}"))
            self.assertEqual((d.status, d.tier), ("valid", tier), tier)
        self.assertEqual(rd.TIERS, ("L0", "L1", "L2", "L3"))

    def test_label_emphasis_stays_compatible(self):
        for raw in ("**Risk Level**: L2", "__Risk Level__: L2", "*Risk Level*: L2"):
            d = rd.parse(header(raw))
            self.assertEqual((d.status, d.tier), ("valid", "L2"), raw)

    def test_zero_width_and_bom_prefix_do_not_hide_the_declaration(self):
        for prefix in ("﻿", "​", "⁠"):
            d = rd.parse(header(prefix + "Risk Level: L3"))
            self.assertEqual((d.status, d.tier), ("valid", "L3"), repr(prefix))

    def test_zero_width_inside_the_declaration_does_not_change_what_it_says(self):
        """앞머리 제로폭은 label 정규식이 unanchored 라 제거 없이도 읽힌다 — 그것만 고정하면
        제거를 통째로 없애도 통과한다. 제거가 실제로 필요한 곳은 label 내부와 값 앞이다.

        사람이 `Risk Level: L3` 으로 읽는 줄은 게이트도 그렇게 읽어야 한다. 보이지 않는 문자
        하나로 판정이 갈리면 문서와 게이트가 다른 것을 보게 된다.
        """
        for name, body in (("label 내부", "Risk\ufeff Level: L3"),
                           ("단어 내부", "Ri\u200bsk Level: L3"),
                           ("값 앞", "Risk Level: \ufeffL3"),
                           ("값 뒤", "Risk Level: L3\u200b")):
            with self.subTest(name):
                d = rd.parse(header(body))
                self.assertEqual((d.status, d.tier), ("valid", "L3"))

    def test_h1_title_is_part_of_the_header_region(self):
        d = rd.parse("# [기본 계획] 제목\nRisk Level: L1\n")
        self.assertEqual((d.status, d.tier), ("valid", "L1"))


class TestProseIsNotADeclaration(unittest.TestCase):
    """실제 오판 6건의 원인 — 본문·인용문·코드·bullet 의 언급."""

    def test_body_after_first_h2_is_ignored(self):
        d = rd.parse(header("Risk Level: L1") + "\n## 본문\n\nRisk Level: L3\n")
        self.assertEqual((d.status, d.tier), ("valid", "L1"))

    def test_trailing_colon_in_prose_is_not_a_candidate(self):
        content = header("Risk Level: L1") + (
            "\n## 설명\n\n"
            "> 위 `Risk Level`은 `l1_path_globs: src/**/*.js` 판정에 따른다.\n")
        self.assertEqual(rd.parse(content).status, "valid")

    def test_blockquote_in_the_header_region_is_ignored(self):
        d = rd.parse(header("Risk Level: L2", "> Risk Level: L3"))
        self.assertEqual((d.status, d.tier), ("valid", "L2"))

    def test_a_bullet_mention_in_the_body_is_ignored(self):
        # 실제 오탐이 나오던 자리 — 본문 설명 bullet. 영역 밖이라 후보가 아니다.
        content = header("Risk Level: L2") + "\n## 설명\n\n- `Risk Level: L3`는 00에 직접 선언한다.\n"
        d = rd.parse(content)
        self.assertEqual((d.status, d.tier), ("valid", "L2"))

    def test_legacy_authoring_forms_stay_readable_in_the_header(self):
        """설치된 소비 프로젝트의 기존 00 이 실제로 쓰는 형태 — 문법은 좁히지 않는다.

        고친 것은 영역이지 문법이 아니다. 이 형태들을 막으면 실제 오탐은 그대로 두고 멀쩡한
        문서만 깨진다.
        """
        for raw in ("- Risk Level: L2",
                    "Risk Level: L2 — 기존 프로젝트 설명",
                    "* 위험도: L2 (legacy label)"):
            d = rd.parse(header(raw))
            self.assertEqual((d.status, d.tier), ("valid", "L2"), raw)

    def test_fenced_examples_are_skipped_for_both_fence_kinds(self):
        for fence in ("```", "~~~"):
            content = header("Risk Level: L2", fence + "text", "Risk Level: L3", fence)
            d = rd.parse(content)
            self.assertEqual((d.status, d.tier), ("valid", "L2"), fence)

    def test_a_different_fence_kind_does_not_close_an_open_fence(self):
        content = header("Risk Level: L2", "```text", "~~~", "Risk Level: L3", "```")
        self.assertEqual((rd.parse(content).status, rd.parse(content).tier), ("valid", "L2"))

    def test_an_indented_code_block_is_not_a_declaration(self):
        """빈 줄 뒤 4칸 들여쓰기는 markdown 코드블록이다 — 리스트 하위 항목과 다르다.

        헤더에 예시만 있고 실제 선언이 없으면 `missing` 으로 막혀야 한다. 예시를 선언으로
        채택하면 문서가 설명하려던 값이 그 사이클의 위험도로 확정된다.
        """
        only_example = (
            "# Phase 00\n\nCycle-Stem: `x`\n\n"
            "게이트가 읽는 형태는 다음과 같다:\n\n"
            "    Risk Level: L3\n\n## 본문\n")
        self.assertEqual(rd.parse(only_example).status, "missing")

        with_real_declaration = (
            "# Phase 00\n\nCycle-Stem: `x`\nRisk Level: L1\n\n"
            "예시:\n\n    Risk Level: L3\n\n## 본문\n")
        d = rd.parse(with_real_declaration)
        self.assertEqual((d.status, d.tier), ("valid", "L1"))

    def test_a_multi_line_indented_code_block_stays_excluded(self):
        content = ("# Phase 00\n\nCycle-Stem: `x`\nRisk Level: L1\n\n예시:\n\n"
                   "    Risk Level: L2\n    Risk Level: L3\n\n## 본문\n")
        d = rd.parse(content)
        self.assertEqual((d.status, d.tier), ("valid", "L1"))

    def test_a_loose_list_sub_item_is_not_a_code_block(self):
        """항목 사이에 빈 줄을 둔 리스트(느슨한 리스트)의 하위 항목도 여전히 리스트다.

        빈 줄만 보고 코드블록으로 판정하면 이 형태가 통째로 사라진다.
        """
        content = ("# Phase 00\n\nCycle-Stem: `x`\n\n- 사전 선언\n\n"
                   "    - Risk Level: L3\n\n## 본문\n")
        d = rd.parse(content)
        self.assertEqual((d.status, d.tier), ("valid", "L3"))

    def test_an_indented_continuation_line_is_not_a_code_block(self):
        """빈 줄 없이 이어지는 들여쓴 줄은 앞 문단의 연속이다 — 코드블록의 조건은 빈 줄 뒤다."""
        content = "# Phase 00\n\nCycle-Stem: `x`\n    Risk Level: L3\n\n## 본문\n"
        d = rd.parse(content)
        self.assertEqual((d.status, d.tier), ("valid", "L3"))

    def test_an_indented_list_item_is_not_silently_dropped(self):
        """Markdown 에서 리스트 하위 항목의 4칸 들여쓰기는 코드블록이 아니다.

        버리면 사람이 L3 로 읽는 문서를 게이트가 옆의 L2 로 확정한다. 실제 코드 예시는 fence 가
        이미 걸러내므로, 들여쓰기를 제외 사유로 삼을 이유가 없다.
        """
        d = rd.parse(header("- Risk Level: L2", "- detail", "    - Risk Level: L3"))
        self.assertEqual(d.status, "duplicate")
        tiers = [tier for _line, tier in rd.declarations(
            header("- Risk Level: L2", "- detail", "    - Risk Level: L3"))]
        self.assertEqual(tiers, ["L2", "L3"])


class TestErrorKinds(unittest.TestCase):
    def test_missing_reports_no_line(self):
        d = rd.parse("# Title\n\nCycle-Stem: `x`\n")
        self.assertEqual(d.status, "missing")
        self.assertIsNone(d.tier)
        self.assertIsNone(d.line)

    def test_duplicate_points_at_the_second_declaration(self):
        d = rd.parse("# Title\n\nRisk Level: L2\nRisk Level: L3\n")
        self.assertEqual(d.status, "duplicate")
        self.assertIsNone(d.tier)
        self.assertEqual(d.line, 4)

    def test_placeholder_alternatives_are_not_read_as_the_first_option(self):
        for raw in ("Risk Level: L1|L2|L3", "Risk Level: L1/L2/L3"):
            d = rd.parse(header(raw))
            self.assertEqual(d.status, "placeholder", raw)
            self.assertIsNone(d.tier)

    def test_unsupported_tier_and_empty_value_are_malformed(self):
        for raw in ("Risk Level: L9", "Risk Level:", "Risk Level: high"):
            d = rd.parse(header(raw))
            self.assertEqual(d.status, "malformed", raw)
            self.assertIsNone(d.tier)

    def test_near_miss_declarations_fail_closed_instead_of_being_skipped(self):
        """선언을 의도한 게 분명하지만 문법을 벗어난 줄.

        후보에서 빼면 "선언이 없다"가 아니라 "옆의 정상 선언이 채택됨"이 되어, 잘못 쓴 tier 가
        조용히 통과한다. 부재는 안전한 방향이 아니다.
        """
        self.assertEqual(rd.parse(header("Risk Level [custom]: L3")).status, "malformed")
        both = rd.parse(header("Risk Level: L2", "Risk Level [custom]: L3"))
        self.assertEqual(both.status, "malformed")
        self.assertIsNone(both.tier)
        self.assertEqual(rd.parse(header("Risk Level: L1 and Risk Level: L3")).status, "malformed")

    def test_excerpt_is_bounded_and_single_line(self):
        d = rd.parse(header("Risk Level: " + "L9" * 200))
        self.assertEqual(d.status, "malformed")
        self.assertLessEqual(len(d.excerpt), 80)
        self.assertNotIn("\n", d.excerpt)

    def test_error_line_numbers_follow_the_original_document(self):
        content = "# Title\n\n```text\nRisk Level: L1\n```\n\nRisk Level: L9\n"
        d = rd.parse(content)
        self.assertEqual((d.status, d.line), ("malformed", 7))


class TestScanIsExhaustive(unittest.TestCase):
    """오류 한 줄이 그 뒤 선언을 가려 tier 를 낮추면 안 된다."""

    HEADER = ("# T\n\nCycle-Stem: `x`\n"
              "Risk Level: L1\n"
              "Risk Level [scope note]: L3\n"
              "Risk Level: L3\n")

    def test_declarations_survive_an_error_line(self):
        found = rd.declarations(self.HEADER)
        self.assertEqual([tier for _line, tier in found], ["L1", "L3"])

    def test_scan_reports_the_first_error_but_keeps_the_full_list(self):
        found, error = rd.scan(self.HEADER)
        self.assertEqual(len(found), 2)
        self.assertEqual(error.status, "malformed")
        self.assertEqual(error.line, 5)

    def test_the_max_tier_consumer_does_not_read_low_because_of_an_error(self):
        tiers = [tier for _line, tier in rd.declarations(self.HEADER)]
        self.assertEqual(max(tiers, key=("L0", "L1", "L2", "L3").index), "L3")

    def test_parse_still_fails_closed_on_the_error(self):
        self.assertEqual(rd.parse(self.HEADER).status, "malformed")


class TestRepositoryCorpus(unittest.TestCase):
    """합성 fixture 대신 저장소의 실제 Phase 00 문서 전체를 회귀로 쓴다."""

    BASE = Path(REPO, "plan_docs", "00-base_plan")

    # 문서 전체를 훑던 기존 파서가 실제로 오판하던 문서들.
    KNOWN_FALSE_POSITIVES = (
        "sage-declared-risk-precision.md",
        "sage-fb-07-l0-domain-risk-exception.md",
        "sage-fb-13-raw-profile-types.md",
        "sage-fb25-project-routing-block.md",
        "sage-risk-level-effective-max-gate.md",
        "sage-stabilization-localization-readiness.md",
    )

    def test_every_phase00_document_declares_exactly_one_tier(self):
        docs = sorted(self.BASE.glob("*.md"))
        self.assertGreaterEqual(len(docs), 30, "corpus 가 사라졌다면 이 회귀는 의미가 없다")
        bad = []
        for path in docs:
            d = rd.parse(path.read_text(encoding="utf-8"))
            if d.status != "valid" or d.tier not in ("L1", "L2", "L3"):
                bad.append((path.name, d.status, d.tier))
        self.assertEqual(bad, [], f"Phase 00 문서가 오판된다: {bad}")

    def test_previously_misread_documents_are_now_valid(self):
        for name in self.KNOWN_FALSE_POSITIVES:
            path = self.BASE / name
            if not path.exists():
                continue
            d = rd.parse(path.read_text(encoding="utf-8"))
            self.assertEqual(d.status, "valid", f"{name}: {d.status}")


class TestNoSecondParser(unittest.TestCase):
    """Risk 선언을 자체 해석하는 정규식이 이 모듈 밖에 남아 있지 않은가.

    같은 선언을 읽는 구현이 둘이 되는 순간 두 판정이 갈린다 — 이 사이클이 고친 결함이 정확히
    그것이었다. 새 소비자가 정규식을 하나 더 만들면 여기서 실패한다.
    """

    ROOTS = ("scripts/sage_harness/hooks", "sage")
    # capture_declared_risk_core 는 입력 도메인이 다르다 — 사용자가 대화창에 쓴 자연어("L3 로
    # 개발할게요")에서 세션 선언을 포착한다. 문서 metadata 문법과 합치면 둘 다 망가진다.
    ALLOWED = ("risk_declaration.py", "capture_declared_risk_core.py")

    def _sources(self):
        for root in self.ROOTS:
            for path in sorted(Path(REPO, root).rglob("*.py")):
                parts = path.parts
                if "tests" in parts or "__pycache__" in parts:
                    continue
                if path.name in self.ALLOWED:
                    continue
                yield path

    def test_the_guard_catches_regex_forms_other_than_compile(self):
        """`re.compile` 리터럴만 보면 `re.search(r"Risk Level: (L[0-3])", ...)` 한 줄로
        두 번째 해석이 들어온다. 실수로 다시 만드는 경로는 compile 만이 아니다."""
        import ast

        module = ast.parse(
            "import re\n"
            "def a(c):\n"
            "    return re.search(r'(?i)Risk\\s*Level\\s*[:：]\\s*(L[0-3])', c)\n"
            "def b(c):\n"
            "    return re.match(r'위험도\\s*[:：]', c)\n"
            "def d(c):\n"
            "    return re.compile(r'(?i)risk\\s*' + r'level\\s*[:：]')\n")
        self.assertEqual(len(TestNoSecondParser._risk_patterns(module, "probe.py")), 3)

    # 해석은 `compile` 로만 들어오지 않는다. 모듈 수준 상수 없이 호출부에서 바로 읽는 형태가
    # 실수로 다시 만들어지는 흔한 경로다.
    _REGEX_FUNCS = ("compile", "search", "match", "fullmatch", "findall", "finditer",
                    "sub", "subn", "split")

    @staticmethod
    def _pattern_text(node):
        """리터럴로 확정되는 패턴 문자열. 런타임 조립은 정적 검사의 사정거리 밖이다."""
        import ast

        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = TestNoSecondParser._pattern_text(node.left)
            right = TestNoSecondParser._pattern_text(node.right)
            return None if left is None or right is None else left + right
        return None

    @staticmethod
    def _risk_patterns(tree, label):
        import ast

        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name not in TestNoSecondParser._REGEX_FUNCS:
                continue
            for arg in node.args[:1]:
                pattern = TestNoSecondParser._pattern_text(arg)
                if pattern and re.search(r"risk\s*\\?s?\*?\s*level|위험도",
                                         pattern, re.IGNORECASE):
                    offenders.append(f"{label}:{node.lineno} {pattern!r}")
        return offenders

    def test_no_other_module_compiles_a_risk_declaration_pattern(self):
        import ast

        offenders = []
        for path in self._sources():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            offenders.extend(self._risk_patterns(tree, path.relative_to(REPO)))
        self.assertEqual(offenders, [],
                         "Risk 선언 해석은 risk_declaration 하나만 소유한다: " + "; ".join(offenders))


class TestConsumerParity(unittest.TestCase):
    """같은 Phase 00 을 네 소비자가 어떻게 읽는가 — 파서가 하나라도 소비 방식은 넷이다.

    `TestNoSecondParser` 는 "두 번째 정규식이 없다" 를 보고, 이 클래스는 "그 하나를 넷이 같은
    문서에 대해 어떻게 쓰는가" 를 고정한다. 게이트·Fast·authority 는 **정확히 1개**를 요구하고,
    write-back 은 **최대**를 취한다(놓친 선언이 tier 를 낮추면 06 검증이 얕아지므로 그쪽이
    fail-closed 다). 이 방향 차이는 의도한 것이라 값으로 못박아 둔다 — 누가 한쪽을 다른 쪽에
    맞추면 여기서 실패하고, 그때 이 주석을 읽게 된다.
    """

    def setUp(self):
        sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))
        sys.path.insert(0, REPO)
        import hook_runtime  # noqa: PLC0415
        import pre_implementation_gate_core as gate  # noqa: PLC0415

        from sage.commands import fast_cycle  # noqa: PLC0415

        self.hook_runtime = hook_runtime
        self.gate = gate
        self.fast_cycle = fast_cycle

    def _four_readings(self, content):
        """(gate, fast, write-back, authority) 각 소비자의 판정. 거부는 예외 종류가 아니라 None."""
        gate_declaration = rd.parse(content)
        gate_reading = gate_declaration.tier if gate_declaration.status == "valid" else None
        try:
            fast_reading = self.fast_cycle._convert_risk(content)
        except ValueError:
            fast_reading = None
        writeback = self.hook_runtime._doc_risk_tier(content)
        declarations, error = rd.scan(content)
        tiers = {tier for _line, tier in declarations}
        authority = tiers.pop() if (not error and len(tiers) == 1) else None
        return gate_reading, fast_reading, writeback, authority

    def test_a_single_clean_declaration_reads_the_same_everywhere(self):
        for tier in ("L1", "L2", "L3"):
            with self.subTest(tier=tier):
                readings = self._four_readings(header(f"Risk Level: {tier}"))
                self.assertEqual(readings, (tier, tier, tier, tier))

    def test_prose_is_a_declaration_for_nobody(self):
        content = ("# Title\n\nRisk Level: L1\n\n## 본문\n\n"
                   "escalation rejected — Risk Level: L3 로 올리자는 제안은 기각했다.\n")
        self.assertEqual(self._four_readings(content), ("L1", "L1", "L1", "L1"))

    def test_two_header_declarations_split_the_consumers_by_design(self):
        """게이트·Fast·authority 는 모호함을 거부하고, write-back 만 최대를 취한다."""
        content = header("Risk Level: L1", "Risk Level: L3")
        gate_reading, fast_reading, writeback, authority = self._four_readings(content)
        self.assertIsNone(gate_reading)
        self.assertIsNone(fast_reading)
        self.assertIsNone(authority)
        self.assertEqual(writeback, "L3")

    def test_no_declaration_is_absent_for_all_four(self):
        content = "# Title\n\n## 본문\n\n내용만 있다.\n"
        self.assertEqual(self._four_readings(content), (None, None, None, None))

    def test_l0_is_read_but_refused_by_the_fast_transition(self):
        """L0 은 유효한 선언이지만 전환 대상이 아니다 — 파싱 실패와 정책 거부는 다른 층이다."""
        gate_reading, fast_reading, writeback, authority = self._four_readings(
            header("Risk Level: L0"))
        self.assertEqual(gate_reading, "L0")
        self.assertEqual(writeback, "L0")
        self.assertEqual(authority, "L0")
        self.assertIsNone(fast_reading)



if __name__ == "__main__":
    unittest.main(verbosity=2)
