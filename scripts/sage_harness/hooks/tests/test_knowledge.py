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
