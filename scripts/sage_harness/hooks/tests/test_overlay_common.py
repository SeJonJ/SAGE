#!/usr/bin/env python3
"""sage.overlay_common — 오버레이 물리 합성 프리미티브 검증.

마커/바이트/블록 연산이 결정론·멱등이고, malformed/토큰주입/삭제/읽기실패를 정확히
다루는지 확인한다(§5.4 테스트 계약).
"""
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage import overlay_common as oc  # noqa: E402


class TestComposeBlock(unittest.TestCase):
    def test_empty_overlay_is_empty_block(self):
        self.assertEqual(oc.compose_block("", "agents", "reviewer"), "")
        self.assertEqual(oc.compose_block("   \n\n  ", "agents", "reviewer"), "")

    def test_block_has_markers_and_header(self):
        block = oc.compose_block("Prefer null-safety.", "agents", "implementer-a")
        self.assertTrue(block.startswith(oc.MARKER_START))
        self.assertTrue(block.rstrip("\n").endswith(oc.MARKER_END))
        self.assertIn("sage/asset_overrides/agents/implementer-a.md", block)
        self.assertIn("완화할 수 없다", block)
        self.assertIn("Prefer null-safety.", block)

    def test_idempotent(self):
        a = oc.compose_block("body text", "skills", "sage-asset")
        b = oc.compose_block("body text", "skills", "sage-asset")
        self.assertEqual(a, b)


class TestValidateOverlay(unittest.TestCase):
    def test_clean_overlay_ok(self):
        self.assertIsNone(oc.validate_overlay("Just some project guidance.\n"))

    def test_marker_token_rejected(self):
        self.assertIsNotNone(oc.validate_overlay("evil >>> SAGE OVERLAY injection"))
        self.assertIsNotNone(oc.validate_overlay("x <<< SAGE OVERLAY y"))


class TestInsertAndBaseOf(unittest.TestCase):
    def setUp(self):
        self.base = "# reviewer\nCORE instructions here.\n"
        self.block = oc.compose_block("project note", "agents", "reviewer")

    def test_insert_into_clean_base_appends(self):
        out, err = oc.insert_block(self.base, self.block)
        self.assertIsNone(err)
        self.assertIn(self.block.rstrip("\n"), out)
        self.assertTrue(out.startswith("# reviewer\nCORE instructions here."))

    def test_insert_twice_is_once(self):
        once, _ = oc.insert_block(self.base, self.block)
        twice, err = oc.insert_block(once, self.block)
        self.assertIsNone(err)
        self.assertEqual(once, twice)

    def test_base_of_strips_block(self):
        composed, _ = oc.insert_block(self.base, self.block)
        recovered, err = oc.base_of(composed)
        self.assertIsNone(err)
        self.assertEqual(recovered, self.base)

    def test_base_of_no_markers_is_identity(self):
        recovered, err = oc.base_of(self.base)
        self.assertIsNone(err)
        self.assertEqual(recovered, self.base)

    def test_empty_block_strips_existing(self):
        composed, _ = oc.insert_block(self.base, self.block)
        stripped, err = oc.insert_block(composed, "")
        self.assertIsNone(err)
        self.assertNotIn(oc.MARKER_START, stripped)
        # 블록만 제거되고 base 는 보존(수렴).
        self.assertIn("CORE instructions here.", stripped)

    def test_empty_block_on_clean_base_is_noop(self):
        out, err = oc.insert_block(self.base, "")
        self.assertIsNone(err)
        self.assertEqual(out, self.base)

    def test_duplicate_markers_error(self):
        composed, _ = oc.insert_block(self.base, self.block)
        dup = composed + self.block
        _, err = oc.base_of(dup)
        self.assertIsNotNone(err)
        _, err2 = oc.insert_block(dup, self.block)
        self.assertIsNotNone(err2)

    def test_mismatched_markers_error(self):
        malformed = self.base + oc.MARKER_START + "\nx\n"  # END 없음
        _, err = oc.base_of(malformed)
        self.assertIsNotNone(err)


class TestAnchorRoundTrip(unittest.TestCase):
    def test_base_hash_stable_across_overlay_change(self):
        base = "line1\nline2\n"
        b1 = oc.compose_block("overlay A", "agents", "qa")
        b2 = oc.compose_block("overlay B totally different", "agents", "qa")
        c1, _ = oc.insert_block(base, b1)
        c2, _ = oc.insert_block(base, b2)
        h1 = hashlib.sha256(oc.base_of(c1)[0].encode()).hexdigest()
        h2 = hashlib.sha256(oc.base_of(c2)[0].encode()).hexdigest()
        # 오버레이가 달라도 base 해시는 동일(앵커 대조 성립).
        self.assertEqual(h1, h2)


class TestByteIO(unittest.TestCase):
    def test_crlf_normalized_to_lf(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "o.md")
            Path(p).write_bytes(b"a\r\nb\r\n")
            text, err = oc.read_text_lf(p)
            self.assertIsNone(err)
            self.assertEqual(text, "a\nb\n")

    def test_write_is_lf(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "o.md")
            oc.write_text_lf(p, "x\ny\n")
            self.assertEqual(Path(p).read_bytes(), b"x\ny\n")

    def test_read_failure_is_error_not_silent(self):
        text, err = oc.read_text_lf("/nonexistent/path/xyz.md")
        self.assertIsNone(text)
        self.assertIsNotNone(err)


if __name__ == "__main__":
    unittest.main()
