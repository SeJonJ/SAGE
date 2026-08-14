#!/usr/bin/env python3
"""사용자 표시 literal 인벤토리가 코드와 어긋나지 않는다.

인벤토리는 catalog 이관의 진척을 세는 유일한 근거다. 코드가 앞서가면 새로 생긴 문구가 목록에
없는 채로 "남은 게 없다"가 되고, 인벤토리가 앞서가면 이미 옮긴 것이 계속 남은 것으로 세어진다.
둘 중 어느 쪽이든 남은 개수가 사실이 아니게 되므로 재생성 여부를 결정론으로 검사한다.
"""
import json
import os
import subprocess
import sys
import tempfile
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

    def test_korean_hidden_behind_an_assign_then_print_is_counted(self):
        """실측 재현 고정: `suffix = "..." if cond else "..."` 뒤 `print(f"...{suffix}...")`.

        `print()` 직접 인자만 보면 이 형태를 놓친다 — `{suffix}` 자리만 인자에 있고 한국어
        자체는 그 앞의 `ast.Assign`(삼항식)에 있다. `sage/commands/sync_overlays.py:100`이
        정확히 이 형태였고, 인벤토리는 0인데 `sage --lang en sync-overlays`의 hard-fail 분기는
        한국어를 냈다. 스캐너가 다시 `print()` 인자만 보는 좁은 방식으로 되돌아가면 이 테스트가
        잡는다.
        """
        inv = self._generate()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "probe.py")
            Path(path).write_text(
                'def run():\n'
                '    suffix = "정리됨" if True else "기본"\n'
                '    print(f"result: {suffix}")\n',
                encoding="utf-8")
            entries, _exclusions = inv._scan_korean_literals(
                path, "probe.py", id_prefix="cmd", required_tests=[],
                direct_classification="command_output",
                indirect_classification="command_output_indirect")
        texts = {e["text"] for e in entries}
        self.assertIn("정리됨", texts, "삼항식의 참 분기를 놓쳤다")
        self.assertIn("기본", texts, "삼항식의 거짓 분기를 놓쳤다")
        self.assertTrue(all(e["classification"] == "command_output_indirect" for e in entries),
                        "print() 인자에 없는데 direct로 분류됐다")

    def test_comment_between_concatenated_fstring_fragments_is_not_counted(self):
        """실측 오탐 고정: 괄호로 이어진 f-string 조각 사이의 코드 주석은 값에 안 들어간다.

        `ast.get_source_segment(source, node)` 는 노드 시작~끝의 원본 소스를 그대로 슬라이스한다.
        조각 사이에 주석이 끼면(합법적 문법) 그 주석 원문까지 슬라이스에 포함돼, 실행 시 전혀
        출력되지 않는 한국어가 있다고 오판한다(`generate.py::_promoted_render` 배너 조립에서
        실측). `_joinedstr_text()` 로 조각 단위 재구성하면 이 오탐이 없어야 한다.
        """
        inv = self._generate()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "probe.py")
            Path(path).write_text(
                'def run():\n'
                '    banner = (f"<!-- all-ascii banner {1} -->"\n'
                '              # 한국어 주석 — 실행 시 값에 안 들어간다\n'
                '              f"\\nmore-ascii\\n")\n'
                '    print(banner)\n',
                encoding="utf-8")
            entries, _exclusions = inv._scan_korean_literals(
                path, "probe.py", id_prefix="cmd", required_tests=[],
                direct_classification="command_output",
                indirect_classification="command_output_indirect")
        self.assertEqual(entries, [], f"주석의 한국어를 값으로 오판했다: {entries}")

    def test_scan_korean_literals_does_not_double_count_fstring_fragments(self):
        """실측 회귀 고정: `_scan_korean_literals`(전체 파일 스캐너)가 한 f-string 문장을
        조각(Constant) 마다 또 세서 부풀렸다 — 511건 중 210건(41%)이 이 중복이었다.

        `_korean_literals()` 자신은 JoinedStr 를 만나면 조각을 안 세고 통째로 반환하지만,
        `_scan_korean_literals` 의 바깥 `ast.walk(tree)` 루프는 그 조각(Constant) 을 독립
        노드로 다시 방문해 "문장 전체 + 조각들"이 각각 별도 entry 로 잡혔다(`review_loop.py`
        의 `# SAGE Loop A 감사 대시보드{title_suffix}` 에서 실측). `_joinedstr_fragment_ids()`
        로 조각을 제외해 원천 차단했다 — 되돌아가면 이 테스트가 잡는다.
        """
        inv = self._generate()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "probe.py")
            Path(path).write_text(
                'def run():\n'
                '    x = "suffix"\n'
                '    body = [f"제목{x}", "", "앞부분 " "뒷부분"]\n'
                '    print("\\n".join(body))\n',
                encoding="utf-8")
            entries, _exclusions = inv._scan_korean_literals(
                path, "probe.py", id_prefix="cmd", required_tests=[],
                direct_classification="command_output",
                indirect_classification="command_output_indirect")
        texts = [e["text"] for e in entries]
        self.assertEqual(len(entries), 2, f"조각이 중복 카운트됐다: {texts}")
        self.assertIn("제목{x}", texts)
        self.assertIn("앞부분 뒷부분", texts)

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

    def test_the_hook_reachable_boundary_stays_visible_and_empty(self):
        """hook 경로에 `sage.i18n` 이 들어오면 hook 이 엔진 의존이 된다 — 그 경계가 데이터로 보여야 한다.

        이관이 끝나 표시 대상이 0건인 것과, 경계를 **세지 않아서** 0건인 것은 다르다. 그래서
        필드의 존재와 0 을 함께 확인한다 — 필드가 사라지면 다음 회귀가 조용히 들어온다.
        """
        entries = _document()["entries"]
        validation = [e for e in entries if e["classification"] == "validation_message"]
        self.assertTrue(all("hook_reachable" in e for e in validation),
                        "hook_reachable 표시가 빠진 항목이 있다")
        remaining = [e for e in validation if e["hook_reachable"]]
        self.assertEqual(remaining, [],
                         f"hook 경로에 미이관 literal 이 남았다: "
                         f"{[(e['source_file'], e['source_line']) for e in remaining[:3]]}")

        # 경계를 세는 목록 자체는 살아 있어야 한다 — 비면 다음에 추가되는 hook 경로 모듈이
        # 아무 표시 없이 들어온다.
        import importlib.util
        spec = importlib.util.spec_from_file_location("_inv", GENERATOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(module.HOOK_REACHABLE, "hook 경로 모듈 목록이 비었다")

    def test_sync_overlays_has_no_remaining_korean(self):
        """이번 회귀의 진원지. 다시 늘어나면 즉시 잡는다."""
        entries = _document()["entries"]
        remaining = [e for e in entries if e["source_file"] == "sage/commands/sync_overlays.py"]
        self.assertEqual(remaining, [], f"sync_overlays.py 에 한국어가 다시 생겼다: {remaining[:3]}")

    def test_commands_layer_backlog_does_not_grow_past_the_known_baseline(self):
        """`sync_overlays.py` 밖의 나머지는 아직 이관 전이다 — 이 배치의 범위가 아니다.

        스캐너를 print() 인자 밖(대입·반환값)까지 넓히자 `sage/commands` 전체에서 약 540건이
        새로 드러났다(`validate.py`·`install.py`·`cycle.py`·`review_loop.py` 등 — 반환한
        `(severity, message)` 를 몇 프레임 떨어진 곳에서 찍는 구조라 print() 인자 스캔으로는
        처음부터 안 보였다). 이 배치는 스캐너를 정확하게 만드는 것까지만 하고 이관은 다음
        배치로 미룬다(plan_docs/04-analyze §4). 그래도 조용히 더 늘면 안 되므로 상한을 고정한다
        — 늘면 이 테스트가 잡고, 줄면(이관 진행) 이 숫자를 낮춰서 갱신한다.

        540 → 539: 1건(`generate.py::_promoted_render`)은 실제 누출이 아니라 스캐너 오탐이었다
        — 괄호로 이어진 f-string 조각 사이의 **코드 주석**이 `ast.get_source_segment` 슬라이스에
        끼어든 것(실행 시 값에는 전혀 안 들어감). `_joinedstr_text()` 로 조각 단위 재구성해 고쳤다.

        539 → 530: 4갈래 분류(plan_docs/04-analyze §4c) 중 (d) 파서/명령어 literal 9건을
        `NOT_TRANSLATED` 로 등록했다 — `change.py::_ABSORB_KW`(8, 한국어 자연어 입력 키워드
        매처) + `generate.py::_OVERLAY_HEADER_PREFIXES`(1, CORE 렌더 헤더 prefix 매처). 남은
        (d) 3건(`retro.py`·`absorb.py` 의 노트 heading 정규식·placeholder)은 (b) vault 노트
        언어 정책이 먼저 확정돼야 한다 — 지금 등록하면 그 정규식이 이미 permanent 라고 잘못
        선언하는 것이다.

        진행 기록(요약, plan_docs/04-analyze §4d 에 상세):
        540 → 539 스캐너 오탐 1건 제거 → 530 (d) 9건 NOT_TRANSLATED 등록 →
        300 f-string 조각 중복 카운트 버그 수정 →
        286 배치 B-1(knowledge·fast_cycle·feedback) → 278 배치 A(_common.py, 8건) →
        273 배치 A(upgrade.py, 5건) → 270 배치 A(asset_check.py, 3건) →
        259 배치 A(generate.py, 10건 catalog + shim 주석 1건 직접 번역) →
        250 배치 A(absorb.py, 9건 — `<module>` 의 `## 제안` 정규식 1건은 (d) 보류로 유지).
        모듈 하나를 이관할 때마다 이 상한을 그 모듈의 실측 감소량만큼 낮춘다.
        """
        entries = _document()["entries"]
        remaining = [e for e in entries
                     if e["source_file"].replace("\\", "/").startswith("sage/commands/")
                     and e["source_file"] != "sage/commands/sync_overlays.py"]
        self.assertLessEqual(len(remaining), 250,
                             f"sage/commands 잔여 한국어가 알려진 상한(250)을 넘었다: "
                             f"{len(remaining)}건")

if __name__ == "__main__":
    unittest.main()
