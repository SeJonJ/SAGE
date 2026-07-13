#!/usr/bin/env python3
"""sage knowledge 검증 — vault scan/write-back PDCA boundary automation."""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import knowledge  # noqa: E402


class ScanArgs:
    action = "scan"
    query_file = None
    profile = None
    vault = None
    limit = 8

    def __init__(self, root, query):
        self.root = root
        self.query = query


class WriteArgs:
    action = "write-back"
    summary_file = None
    profile = None
    vault = None
    prefix = "TECH"
    tags = None
    append_log = True

    def __init__(self, root, title, summary):
        self.root = root
        self.title = title
        self.summary = summary


def _profile(root, vault, scan=True, write=True):
    os.makedirs(os.path.join(root, "sage"), exist_ok=True)
    Path(os.path.join(root, "sage", "project-profile.yaml")).write_text(
        "knowledge_capture:\n"
        f"  vault_path: \"{vault}\"\n"
        f"  scan_before_dev: {'true' if scan else 'false'}\n"
        f"  update_after_dev: {'true' if write else 'false'}\n"
        "  note_convention: { folder: \"wiki\", filename_pattern: \"{prefix} - {title}.md\" }\n",
        encoding="utf-8",
    )


def _count_summary_headers(body):
    """정본 Summary 헤더 라인 수 — 변형('## summary'/'##  Summary')까지 세어 canonicalize 검증을 강화한다.
    body.count('## Summary') 는 대소문자/공백 변형을 놓친다(codex 리뷰)."""
    return sum(1 for ln in body.splitlines() if knowledge._SUMMARY_HEADER_RE.match(ln.strip()))


def _profile_with_structure(root, vault):
    """required_structure(PREFIX→필수 마커) 를 포함한 profile — advisory 구조 검증 테스트용."""
    os.makedirs(os.path.join(root, "sage"), exist_ok=True)
    Path(os.path.join(root, "sage", "project-profile.yaml")).write_text(
        "knowledge_capture:\n"
        f"  vault_path: \"{vault}\"\n"
        "  scan_before_dev: true\n"
        "  update_after_dev: true\n"
        "  note_convention:\n"
        "    folder: \"wiki\"\n"
        "    filename_pattern: \"{prefix} - {title}.md\"\n"
        "    required_structure:\n"
        "      BUG: [\"> [!summary]\", \"## 증상\", \"## 원인\", \"## 수정\", \"## 재발 방지\"]\n",
        encoding="utf-8",
    )


class TestKnowledge(unittest.TestCase):
    def test_scan_writes_matches_deterministically(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            os.makedirs(os.path.join(vault, "wiki"))
            Path(os.path.join(vault, "wiki", "TECH - Alpha.md")).write_text("weather api city search\n", encoding="utf-8")
            Path(os.path.join(vault, "wiki", "TECH - Beta.md")).write_text("city search search\n", encoding="utf-8")
            _profile(root, vault)
            rc = knowledge._run_scan(ScanArgs(root, "city search"))
            self.assertEqual(rc, 0)
            body = Path(os.path.join(root, ".sage", "knowledge_scan.md")).read_text(encoding="utf-8")
            self.assertIn("status: ran", body)
            self.assertLess(body.index("TECH - Beta.md"), body.index("TECH - Alpha.md"))

    def test_scan_query_file_and_folder_traversal_stays_in_vault(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault, tempfile.TemporaryDirectory() as outside:
            os.makedirs(os.path.join(vault, "wiki"))
            Path(os.path.join(vault, "wiki", "TECH - Root.md")).write_text("needle root\n", encoding="utf-8")
            Path(os.path.join(outside, "TECH - Outside.md")).write_text("needle outside\n", encoding="utf-8")
            _profile(root, vault)
            prof = Path(os.path.join(root, "sage", "project-profile.yaml")).read_text(encoding="utf-8")
            Path(os.path.join(root, "sage", "project-profile.yaml")).write_text(
                prof.replace('folder: "wiki"', 'folder: "../../.."'), encoding="utf-8")
            q = os.path.join(root, "q.txt")
            Path(q).write_text("needle", encoding="utf-8")
            args = ScanArgs(root, "")
            args.query_file = q
            rc = knowledge._run_scan(args)
            self.assertEqual(rc, 0)
            body = Path(os.path.join(root, ".sage", "knowledge_scan.md")).read_text(encoding="utf-8")
            self.assertIn("TECH - Root.md", body)
            self.assertNotIn("TECH - Outside.md", body)

    def test_scan_na_overwrites_stale_report(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            os.makedirs(os.path.join(root, ".sage"))
            Path(os.path.join(root, ".sage", "knowledge_scan.md")).write_text("OLD_MATCH\n", encoding="utf-8")
            _profile(root, vault, scan=False)
            rc = knowledge._run_scan(ScanArgs(root, "anything"))
            self.assertEqual(rc, 0)
            body = Path(os.path.join(root, ".sage", "knowledge_scan.md")).read_text(encoding="utf-8")
            self.assertIn("status: n/a", body)
            self.assertNotIn("OLD_MATCH", body)

    def test_write_back_note_and_log_idempotent(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            _profile(root, vault)
            args = WriteArgs(root, "SAGE 5차 보완", "scan and write-back added")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(knowledge._run_write_back(args), 0)
                self.assertEqual(knowledge._run_write_back(args), 0)
            note = os.path.join(vault, "wiki", "TECH - SAGE 5차 보완.md")
            log = os.path.join(vault, "wiki", "log.md")
            self.assertTrue(os.path.exists(note))
            log_body = Path(log).read_text(encoding="utf-8")
            self.assertEqual(log_body.count("[[TECH - SAGE 5차 보완]]"), 1)

    def test_write_back_summary_header_not_duplicated(self):
        # summary 가 '## Summary' 로 시작하면(spec "Lead with a ## Summary" 지시) CLI 가 헤더를
        # 다시 붙이지 않아 노트에 '## Summary' 가 1회만 나온다.
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            _profile(root, vault)
            args = WriteArgs(root, "Dup", "## Summary\n\n실제 요약 본문")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(knowledge._run_write_back(args), 0)
            body = Path(os.path.join(vault, "wiki", "TECH - Dup.md")).read_text(encoding="utf-8")
            self.assertEqual(_count_summary_headers(body), 1)
            self.assertIn("실제 요약 본문", body)

    def test_write_back_summary_header_inserted_when_absent(self):
        # summary 가 헤더 없이 오면 CLI 가 '## Summary' 를 1회 삽입한다(기존 동작 유지).
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            _profile(root, vault)
            args = WriteArgs(root, "NoHdr", "헤더 없는 요약")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(knowledge._run_write_back(args), 0)
            body = Path(os.path.join(vault, "wiki", "TECH - NoHdr.md")).read_text(encoding="utf-8")
            self.assertEqual(_count_summary_headers(body), 1)
            self.assertIn("## Summary\n\n헤더 없는 요약", body)

    def test_write_back_concurrent_create_none_is_graceful(self):
        # write_note 가 경쟁 생성으로 None 반환 → 크래시 없음, 'note written: None' 오보 없음, 구조검증 미실행,
        # 후속(append_log) 지속, rc 0.
        from unittest import mock
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            _profile_with_structure(root, vault)
            args = WriteArgs(root, "Race", "요약")
            args.prefix = "BUG"
            out = io.StringIO()
            with mock.patch.object(knowledge._vault, "write_note", return_value=None), redirect_stdout(out):
                self.assertEqual(knowledge._run_write_back(args), 0)
            output = out.getvalue()
            self.assertNotIn("note written: None", output)
            self.assertIn("동시 생성", output)
            self.assertNotIn("advisory", output)       # 신규 아님 → 구조검증 skip
            self.assertIn("log", output)               # append_log 후속은 지속

    def test_write_back_structure_advisory_warns_on_missing(self):
        # required_structure 설정 + 얕은 요약(필수 마커 누락) → advisory WARN, 그러나 차단 안 함(rc 0).
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            _profile_with_structure(root, vault)
            args = WriteArgs(root, "Shallow", "그냥 얕은 요약")
            args.prefix = "BUG"
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(knowledge._run_write_back(args), 0)
            self.assertIn("advisory", out.getvalue())
            self.assertIn("증상", out.getvalue())   # 누락 마커가 표면화됨

    def test_write_back_structure_advisory_passes_when_complete(self):
        # 필수 마커를 모두 담은 요약 → 구조 검증 통과, advisory WARN 없음.
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            _profile_with_structure(root, vault)
            summary = "> [!summary]\n\n## 증상\n\nx\n\n## 원인\n\nx\n\n## 수정\n\nx\n\n## 재발 방지\n\nx"
            args = WriteArgs(root, "Full", summary)
            args.prefix = "BUG"
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(knowledge._run_write_back(args), 0)
            self.assertIn("구조 검증 통과", out.getvalue())
            self.assertNotIn("advisory", out.getvalue())

    def test_write_back_no_structure_config_skips_check(self):
        # required_structure 미설정(기본) → 구조 검증 자체를 하지 않는다(동작 불변).
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            _profile(root, vault)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(knowledge._run_write_back(WriteArgs(root, "Plain", "s")), 0)
            self.assertNotIn("advisory", out.getvalue())
            self.assertNotIn("구조 검증", out.getvalue())

    def test_write_back_tolerates_non_dict_note_convention(self):
        # note_convention 이 손상(list) 이어도 write-back 이 크래시하지 않고 기본값으로 진행(rc 0, fail-open).
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            os.makedirs(os.path.join(root, "sage"), exist_ok=True)
            Path(os.path.join(root, "sage", "project-profile.yaml")).write_text(
                "knowledge_capture:\n"
                f"  vault_path: \"{vault}\"\n"
                "  update_after_dev: true\n"
                "  note_convention: [\"bad\"]\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(knowledge._run_write_back(WriteArgs(root, "Corrupt", "s")), 0)
            self.assertTrue(os.path.exists(os.path.join(vault, "wiki", "TECH - Corrupt.md")))

    def test_write_back_titled_summary_header_preserved(self):
        # '## Summary of X'(제목 붙은 별개 헤더)는 정확 매칭이 아니라 CLI 정본 '## Summary' 를 별도로 붙이고 보존.
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            _profile(root, vault)
            args = WriteArgs(root, "Titled", "## Summary of X\n\n본문")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(knowledge._run_write_back(args), 0)
            body = Path(os.path.join(vault, "wiki", "TECH - Titled.md")).read_text(encoding="utf-8")
            self.assertEqual(sum(1 for ln in body.splitlines() if ln.strip() == "## Summary"), 1)
            self.assertIn("## Summary of X", body)

    def test_write_back_summary_header_variants_canonicalized(self):
        # 대소문자/공백/BOM/다중 변형도 정본 헤더 정확히 1개로 통일(유사 중복 방지). 헤더 라인 수로 단언.
        for variant in ("## summary\n\n본문", "##  Summary\n\n본문",
                        "﻿## Summary\n\n본문", "## Summary\n\n## summary\n\n본문"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
                _profile(root, vault)
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(knowledge._run_write_back(WriteArgs(root, "Var", variant)), 0)
                body = Path(os.path.join(vault, "wiki", "TECH - Var.md")).read_text(encoding="utf-8")
                self.assertEqual(_count_summary_headers(body), 1, body)
                self.assertIn("본문", body)

    def test_write_back_structure_marker_no_substring_false_pass(self):
        # '## 증상들' 은 필수 마커 '## 증상' 을 충족하지 않는다(startswith 오탐 방지) → 증상 누락 WARN.
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            _profile_with_structure(root, vault)
            summary = "> [!summary]\n\n## 증상들\n\nx\n\n## 원인\n\nx\n\n## 수정\n\nx\n\n## 재발 방지\n\nx"
            args = WriteArgs(root, "Sub", summary)
            args.prefix = "BUG"
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(knowledge._run_write_back(args), 0)
            self.assertIn("advisory", out.getvalue())
            self.assertIn("## 증상", out.getvalue())   # 증상 누락 보고(증상들은 불충족)

    def test_write_back_append_skips_structure_check(self):
        # 기존 노트 append 는 구조검증 대상 아님(사람 저작 본문에 WARN 소음 방지).
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            _profile_with_structure(root, vault)
            os.makedirs(os.path.join(vault, "wiki"), exist_ok=True)
            Path(os.path.join(vault, "wiki", "BUG - Exists.md")).write_text("# BUG - Exists\n\n기존 본문\n", encoding="utf-8")
            args = WriteArgs(root, "Exists", "추가 요약")
            args.prefix = "BUG"
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(knowledge._run_write_back(args), 0)
            self.assertNotIn("advisory", out.getvalue())
            self.assertNotIn("구조 검증", out.getvalue())

    def test_write_back_existing_note_is_appended_not_clobbered(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            _profile(root, vault)
            os.makedirs(os.path.join(vault, "wiki"))
            note = os.path.join(vault, "wiki", "TECH - Existing.md")
            Path(note).write_text("# Existing\n\nHUMAN CONTENT\n", encoding="utf-8")
            args = WriteArgs(root, "Existing", "")
            sf = os.path.join(root, "summary.md")
            Path(sf).write_text("new summary", encoding="utf-8")
            args.summary_file = sf
            self.assertEqual(knowledge._run_write_back(args), 0)
            self.assertEqual(knowledge._run_write_back(args), 0)
            body = Path(note).read_text(encoding="utf-8")
            self.assertIn("HUMAN CONTENT", body)
            self.assertEqual(body.count("SAGE-KNOWLEDGE-WRITEBACK"), 1)
            self.assertEqual(body.count("new summary"), 1)

    def test_write_back_log_symlink_is_replaced(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault, tempfile.TemporaryDirectory() as outside:
            _profile(root, vault)
            os.makedirs(os.path.join(vault, "wiki"))
            target = os.path.join(outside, "outside-log.md")
            Path(target).write_text("outside\n", encoding="utf-8")
            os.symlink(target, os.path.join(vault, "wiki", "log.md"))
            self.assertEqual(knowledge._run_write_back(WriteArgs(root, "Safe", "summary")), 0)
            self.assertFalse(os.path.islink(os.path.join(vault, "wiki", "log.md")))
            self.assertEqual(Path(target).read_text(encoding="utf-8"), "outside\n")

    def test_write_back_disabled_is_na(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            _profile(root, vault, write=False)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = knowledge._run_write_back(WriteArgs(root, "T", "S"))
            self.assertEqual(rc, 0)
            self.assertIn("N/A", out.getvalue())

    # --- 7차 배치2 4-2/4-3: note_convention tags_style + index ---
    def _profile_conv(self, root, vault, extra):
        os.makedirs(os.path.join(root, "sage"), exist_ok=True)
        Path(os.path.join(root, "sage", "project-profile.yaml")).write_text(
            "knowledge_capture:\n"
            f"  vault_path: \"{vault}\"\n"
            "  update_after_dev: true\n"
            "  note_convention: { folder: \"wiki\", filename_pattern: \"{prefix} - {title}.md\", " + extra + " }\n",
            encoding="utf-8")

    def test_tags_style_frontmatter_default(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            self._profile_conv(root, vault, 'tags_style: frontmatter')
            with redirect_stdout(io.StringIO()):
                knowledge._run_write_back(WriteArgs(root, "FM", "s"))
            body = Path(os.path.join(vault, "wiki", "TECH - FM.md")).read_text(encoding="utf-8")
            self.assertTrue(body.startswith("---"))            # frontmatter 블록
            self.assertIn("tags:", body.split("---")[1])       # tags 가 frontmatter 안
            self.assertNotIn("태그: #", body)

    def test_write_back_custom_tags_override_default(self):
        # host 가 벌트 가이드대로 --tags 전달 → 하드코딩 기본(tech,sage,knowledge-capture) 대신 그 값 사용.
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            self._profile_conv(root, vault, 'tags_style: frontmatter')
            a = WriteArgs(root, "CT", "s"); a.tags = "bug, 녹화, chatforyou"
            with redirect_stdout(io.StringIO()):
                knowledge._run_write_back(a)
            fm = Path(os.path.join(vault, "wiki", "TECH - CT.md")).read_text(encoding="utf-8").split("---")[1]
            self.assertIn("bug", fm); self.assertIn("녹화", fm); self.assertIn("chatforyou", fm)
            self.assertNotIn("knowledge-capture", fm)          # 기본 태그로 덮이지 않음

    def test_write_back_tags_empty_or_commas_fall_back_to_default(self):
        # --tags ",," / 공백만 → 정규화 후 비면 빈 tags 대신 기본값(빈 tags: [] 방지, codex P2)
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            self._profile_conv(root, vault, 'tags_style: frontmatter')
            a = WriteArgs(root, "ET", "s"); a.tags = " , ,"
            with redirect_stdout(io.StringIO()):
                knowledge._run_write_back(a)
            fm = Path(os.path.join(vault, "wiki", "TECH - ET.md")).read_text(encoding="utf-8").split("---")[1]
            self.assertIn("knowledge-capture", fm)             # 기본값 fallback
            self.assertNotIn("tags: []", fm)

    def test_write_back_tags_dedup_preserves_order(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            self._profile_conv(root, vault, 'tags_style: inline')
            a = WriteArgs(root, "DD", "s"); a.tags = "bug, bug, 녹화, bug"
            with redirect_stdout(io.StringIO()):
                knowledge._run_write_back(a)
            body = Path(os.path.join(vault, "wiki", "TECH - DD.md")).read_text(encoding="utf-8")
            self.assertEqual(body.count("#bug"), 1)             # 중복 제거
            self.assertIn("#녹화", body)

    def test_write_back_default_tags_when_no_flag(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            self._profile_conv(root, vault, 'tags_style: frontmatter')
            with redirect_stdout(io.StringIO()):
                knowledge._run_write_back(WriteArgs(root, "DT", "s"))   # tags 미지정
            fm = Path(os.path.join(vault, "wiki", "TECH - DT.md")).read_text(encoding="utf-8").split("---")[1]
            self.assertIn("knowledge-capture", fm)             # 기본값 fallback

    def test_tags_style_inline(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            self._profile_conv(root, vault, 'tags_style: inline')
            with redirect_stdout(io.StringIO()):
                knowledge._run_write_back(WriteArgs(root, "IN", "s"))
            body = Path(os.path.join(vault, "wiki", "TECH - IN.md")).read_text(encoding="utf-8")
            self.assertIn("태그: #tech #sage #knowledge-capture", body)   # 본문 인라인 태그
            fm = body.split("---")[1] if body.startswith("---") else ""
            self.assertNotIn("tags:", fm)                                  # frontmatter 엔 tags 없음

    def test_tags_style_none(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            self._profile_conv(root, vault, 'tags_style: none')
            with redirect_stdout(io.StringIO()):
                knowledge._run_write_back(WriteArgs(root, "NO", "s"))
            body = Path(os.path.join(vault, "wiki", "TECH - NO.md")).read_text(encoding="utf-8")
            self.assertNotIn("태그: #", body)
            fm = body.split("---")[1] if body.startswith("---") else ""
            self.assertNotIn("tags:", fm)

    def test_index_append_when_configured(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            self._profile_conv(root, vault, 'index: "index.md"')
            with redirect_stdout(io.StringIO()):
                knowledge._run_write_back(WriteArgs(root, "IDX", "s"))
                knowledge._run_write_back(WriteArgs(root, "IDX", "s"))   # 멱등
            idx = Path(os.path.join(vault, "wiki", "index.md")).read_text(encoding="utf-8")
            self.assertEqual(idx.count("[[TECH - IDX]]"), 1)

    def test_index_skipped_when_unset(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            self._profile_conv(root, vault, 'flat: true')   # index 미설정
            with redirect_stdout(io.StringIO()):
                knowledge._run_write_back(WriteArgs(root, "NOIDX", "s"))
            self.assertFalse(os.path.exists(os.path.join(vault, "wiki", "index.md")))

    def test_index_invalid_dot_does_not_crash(self):
        # index: "." → 무효 처리, write-back 정상 완료(폴더 open IsADirectoryError abort 방지, codex 중R1 P1).
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            self._profile_conv(root, vault, 'index: "."')
            with redirect_stdout(io.StringIO()):
                rc = knowledge._run_write_back(WriteArgs(root, "DOT", "s"))
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(vault, "wiki", "TECH - DOT.md")))

    def test_inline_tag_added_to_existing_note(self):
        # inline 전환 후 태그줄 없던 기존 노트에 append 시 태그줄 1회 보강(codex 중R1 P2).
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as vault:
            self._profile_conv(root, vault, 'tags_style: inline')
            os.makedirs(os.path.join(vault, "wiki"))
            note = os.path.join(vault, "wiki", "TECH - Pre.md")
            Path(note).write_text("# Pre\n\nHUMAN\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                knowledge._run_write_back(WriteArgs(root, "Pre", "s1"))
                knowledge._run_write_back(WriteArgs(root, "Pre", "s1"))   # 멱등(태그 1회만)
            body = Path(note).read_text(encoding="utf-8")
            self.assertIn("HUMAN", body)
            self.assertEqual(body.count("태그: #tech #sage #knowledge-capture"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
