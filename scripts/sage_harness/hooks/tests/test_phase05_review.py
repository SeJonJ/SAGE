#!/usr/bin/env python3
"""sage review / sage cross-check 검증 (7차 배치2).

- 순수 파서/argv 빌더 직격(_parse_codex_jsonl/_parse_claude_json/_peer_command)
- run_cross_check: cross off→폴백 / peer 성공→cross_model / peer 실패→same_runtime(침묵 안 함)
- run_review: same_runtime 표면화
peer subprocess(_invoke_peer)는 monkeypatch — 실제 codex/claude 미호출.
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import review as RV  # noqa: E402


class _Args:
    def __init__(self, root=None, packet_file=None, timeout=540):
        self.root = root; self.packet_file = packet_file; self.timeout = timeout


def _mkprofile(d, host="claude", cross=False):
    os.makedirs(os.path.join(d, "sage"), exist_ok=True)
    with open(os.path.join(d, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
        f.write(f"runtime: {{ host: {host} }}\noptions: {{ cross_model: {str(cross).lower()} }}\n")


class TestParsers(unittest.TestCase):
    def test_codex_jsonl_last_agent_message(self):
        text = "\n".join([
            '{"type":"item.completed","item":{"type":"reasoning","text":"thinking"}}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"first"}}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"FINDINGS: none\\nVERDICT: SHIP"}}',
        ])
        self.assertEqual(RV._parse_codex_jsonl(text), "FINDINGS: none\nVERDICT: SHIP")

    def test_codex_jsonl_empty_and_garbage(self):
        self.assertIsNone(RV._parse_codex_jsonl(""))
        self.assertIsNone(RV._parse_codex_jsonl("not json\n{bad"))

    def test_claude_json_result(self):
        self.assertEqual(RV._parse_claude_json('{"result":"VERDICT: SHIP","x":1}'), "VERDICT: SHIP")

    def test_claude_json_missing_result(self):
        self.assertIsNone(RV._parse_claude_json('{"x":1}'))
        self.assertIsNone(RV._parse_claude_json("not json"))

    def test_peer_command_codex(self):
        cmd = RV._peer_command("codex", "PROMPT")
        self.assertEqual(cmd[:5], ["codex", "exec", "--json", "-s", "read-only"])
        self.assertEqual(cmd[-1], "PROMPT")

    def test_peer_command_claude(self):
        cmd = RV._peer_command("claude", "PROMPT")
        self.assertEqual(cmd, ["claude", "-p", "--output-format", "json", "PROMPT"])

    def test_peer_command_unknown(self):
        with self.assertRaises(ValueError):
            RV._peer_command("gpt", "x")


class TestReview(unittest.TestCase):
    def test_review_same_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            _mkprofile(d, cross=False)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = RV.run_review(_Args(root=d))
            self.assertEqual(rc, 0)
            self.assertIn("REVIEWER_ACTUAL: same_runtime", buf.getvalue())


class TestCrossCheck(unittest.TestCase):
    def _packet(self, d):
        p = os.path.join(d, "pkt.txt")
        open(p, "w", encoding="utf-8").write("review this diff")
        return p

    def test_cross_off_fallback_surfaced(self):
        with tempfile.TemporaryDirectory() as d:
            _mkprofile(d, cross=False)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = RV.run_cross_check(_Args(root=d, packet_file=self._packet(d)))
            self.assertEqual(rc, 0)
            self.assertIn("REVIEWER_ACTUAL: same_runtime", out.getvalue())
            self.assertIn("폴백", err.getvalue())   # 침묵하지 않음

    def test_cross_on_peer_success(self):
        with tempfile.TemporaryDirectory() as d:
            _mkprofile(d, host="claude", cross=True)
            orig = RV._invoke_peer
            RV._invoke_peer = lambda peer, prompt, timeout: (True, f"{peer} says SHIP", None)
            # peer 가용성: caps 는 which 로 잡히지만 cross_model=true + opposite_runtime 판정에
            # codex 가용이 필요 → reviewer_resolution 이 which(codex) 로 판정. CI 에 codex 없을 수 있어
            # capabilities 로 강제 주입.
            with open(os.path.join(d, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
                f.write("runtime: { host: claude }\noptions: { cross_model: true }\n"
                        "capabilities: { codex: true }\n")
            try:
                out = io.StringIO()
                with redirect_stdout(out), redirect_stderr(io.StringIO()):
                    rc = RV.run_cross_check(_Args(root=d, packet_file=self._packet(d)))
                v = out.getvalue()
            finally:
                RV._invoke_peer = orig
            self.assertEqual(rc, 0)
            self.assertIn("REVIEWER_ACTUAL: cross_model", v)
            self.assertIn("codex says SHIP", v)
            self.assertIn("CROSS-MODEL REVIEW", v)

    def _profile_cross_codex(self, d):
        os.makedirs(os.path.join(d, "sage"), exist_ok=True)
        with open(os.path.join(d, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("runtime: { host: claude }\noptions: { cross_model: true }\n"
                    "capabilities: { codex: true }\n")

    def test_cross_on_peer_failure_falls_back_not_silent(self):
        with tempfile.TemporaryDirectory() as d:
            self._profile_cross_codex(d)
            orig = RV._invoke_peer
            RV._invoke_peer = lambda peer, prompt, timeout: (False, None, "codex 호출 timeout(540s)")
            try:
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    rc = RV.run_cross_check(_Args(root=d, packet_file=self._packet(d)))
            finally:
                RV._invoke_peer = orig
            self.assertEqual(rc, 0)
            self.assertIn("REVIEWER_ACTUAL: same_runtime", out.getvalue())   # degraded 근거
            self.assertIn("timeout", err.getvalue())                          # 실패 사유 표면화

    def test_cross_empty_packet_toolerror(self):
        with tempfile.TemporaryDirectory() as d:
            self._profile_cross_codex(d)
            p = os.path.join(d, "empty.txt")
            open(p, "w").write("   ")
            with redirect_stderr(io.StringIO()):
                rc = RV.run_cross_check(_Args(root=d, packet_file=p))
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
