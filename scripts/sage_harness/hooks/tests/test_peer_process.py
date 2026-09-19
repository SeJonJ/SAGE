#!/usr/bin/env python3
"""Phase 05 peer 프로세스 — 비용 통제·부분 결과·사용량·감사·폴백.

- 순수 함수 직격(stream 요약, 버전 게이트, argv)
- 실제 프로세스 트리 종료(POSIX): peer 가 띄운 자식이 timeout 뒤 고아로 남지 않는지
- 가짜 claude CLI 를 PATH 에 두고 run_peer 종단(통제 플래그·계약 헤더·작업 디렉터리·거부 사유)
- cross-check 폴백(`--on-peer-failure`)은 `_invoke_peer` monkeypatch 로
"""
import io
import json
import os
import stat
import sys
import tempfile
import textwrap
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage import peer_process as P  # noqa: E402
from sage.commands import review as RV  # noqa: E402
from sage.diagnostics import Diagnostic  # noqa: E402


def _stream(*events):
    return "\n".join(json.dumps(e) for e in events) + "\n"


_RESULT_OK = {"type": "result", "subtype": "success", "is_error": False, "result": "VERDICT: APPROVED",
              "num_turns": 3, "total_cost_usd": 0.12,
              "usage": {"input_tokens": 10, "cache_creation_input_tokens": 900,
                        "cache_read_input_tokens": 5000, "output_tokens": 70},
              "subagent_stats": {"spawned": 0}}


class TestClaudeStream(unittest.TestCase):
    def test_success_usage_split_into_new_and_cached(self):
        s = P.summarize_claude_stream(_stream(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "FINDING: a"},
                                                          {"type": "tool_use", "name": "Read"}]}},
            _RESULT_OK))
        self.assertEqual(s["review"], "VERDICT: APPROVED")
        self.assertEqual(s["usage"]["new_input"], 910)
        self.assertEqual(s["usage"]["cached_input"], 5000)
        self.assertEqual(s["usage"]["output"], 70)
        self.assertEqual(s["tool_calls"], 1)
        self.assertEqual(s["violations"], [])

    def test_cut_off_stream_keeps_partial_but_no_review(self):
        s = P.summarize_claude_stream(_stream(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "FINDING: P1 x.py:3"}]}}))
        self.assertIsNone(s["review"])
        self.assertIn("FINDING: P1", s["partial"])
        self.assertIsNone(s["usage"])

    def test_error_result_is_not_a_review(self):
        s = P.summarize_claude_stream(_stream(dict(_RESULT_OK, is_error=True, result="API Error")))
        self.assertIsNone(s["review"])

    def test_controls_failure_is_a_violation(self):
        s = P.summarize_claude_stream(_stream(
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}},
            dict(_RESULT_OK, subagent_stats={"spawned": 2})))
        self.assertIn("forbidden_tool:Bash", s["violations"])
        self.assertIn("subagent_spawned:2", s["violations"])

    def test_rate_limit_event_marks_limit(self):
        s = P.summarize_claude_stream(_stream(
            {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}}))
        self.assertTrue(s["rate_limited"])
        s = P.summarize_claude_stream(_stream(
            {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}}, _RESULT_OK))
        self.assertFalse(s["rate_limited"])


class TestTokensLine(unittest.TestCase):
    def test_missing_usage_is_unknown_not_zero(self):
        # 0 으로 쓰면 예산 게이트가 "여유 있음"으로 읽는다.
        self.assertEqual(P.PeerRun("codex").tokens_line(), "unknown")
        self.assertEqual(P.PeerRun.from_legacy("codex", True, "ok", None).tokens_line(), "unknown")

    def test_measured_usage(self):
        run = P.PeerRun("claude", usage={"new_input": 5, "cached_input": 6, "output": 7, "turns": 2},
                        tool_calls=3, wall_s=12.4)
        self.assertEqual(run.tokens_line(), "new_input=5 cached_input=6 output=7 turns=2 tool_calls=3 wall_s=12")

    def test_legacy_reason_from_diagnostic_code(self):
        run = P.PeerRun.from_legacy("codex", False, None, Diagnostic("review.peer_timeout", peer="codex", timeout=1))
        self.assertEqual(run.reason, "timeout")
        self.assertEqual(P.PeerRun.from_legacy("codex", False, None, "문자열 오류").reason, "unknown")


class TestVersionGate(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(P.parse_version("2.1.278 (Claude Code)"), (2, 1, 278))
        self.assertEqual(P.parse_version("codex-cli 0.155.1"), (0, 155, 1))
        self.assertIsNone(P.parse_version("garbage"))

    def test_only_confirmed_old_version_skips_controls(self):
        self.assertFalse(P.controls_supported("claude", (2, 1, 200)))
        self.assertTrue(P.controls_supported("claude", (2, 1, 275)))
        # 버전을 못 읽으면 통제를 건다 — 모르는 플래그면 peer 가 명시적으로 거부한다.
        self.assertTrue(P.controls_supported("claude", None))

    def test_controlled_claude_argv(self):
        cmd = P.peer_command("claude", "high", None, root="/r", controlled=True)
        for flag in ("--restricted", "--no-session-persistence", "--strict-mcp-config",
                     "--disable-slash-commands", "--verbose"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "stream-json")
        self.assertEqual(cmd[cmd.index("--add-dir") + 1], "/r")
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "")
        i = cmd.index("--disallowedTools")
        self.assertEqual(cmd[i + 1:i + 3], ["Agent", "Task"])
        self.assertEqual(cmd[-2:], ["--effort", "high"])


@unittest.skipIf(os.name == "nt", "프로세스 그룹 종료는 POSIX 경로를 검증한다")
class TestProcessTree(unittest.TestCase):
    def test_timeout_kills_grandchildren_and_keeps_partial_output(self):
        script = ("import subprocess,sys,time\n"
                  "p=subprocess.Popen(['sleep','30'])\n"
                  "print('child', p.pid, flush=True)\n"
                  "time.sleep(30)\n")
        code, out, _err, timed_out, wall = P.run_process([sys.executable, "-c", script], "", 2)
        self.assertTrue(timed_out)
        # 자식이 stdout 파이프를 쥐고 있으면 peer 만 죽여서는 출력 수집이 자식이 끝날 때까지 멈춘다.
        self.assertLess(wall, 15, "timeout 뒤 출력 수집이 손자 프로세스를 기다렸다")
        self.assertIsNone(code)
        pid = int(out.split()[1])
        deadline = time.time() + 5
        alive = True
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                alive = False
                break
            # 좀비는 부모(init)가 거둘 때까지 남을 수 있다 — 상태로 판별한다.
            try:
                with os.popen(f"ps -o stat= -p {pid}") as f:
                    if f.read().strip().startswith("Z"):
                        alive = False
                        break
            except Exception:
                pass
            time.sleep(0.1)
        self.assertFalse(alive, "peer 가 띄운 자식이 timeout 뒤에도 살아 있다")


_FAKE_CLAUDE = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    if "--version" in sys.argv:
        print(os.environ.get("FAKE_VERSION", "2.1.278 (Claude Code)")); sys.exit(0)
    mode = os.environ.get("FAKE_MODE", "ok")
    if mode == "reject":
        print("error: unknown option '--restricted'", file=sys.stderr); sys.exit(1)
    prompt = sys.stdin.read()
    with open(os.environ["FAKE_LOG"], "w") as f:
        json.dump({{"argv": sys.argv[1:], "cwd": os.getcwd(), "prompt": prompt}}, f)
    def emit(o): print(json.dumps(o), flush=True)
    emit({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": "FINDING: P2 a.py:1"}}]}}}})
    if mode == "hang":
        import time; time.sleep(30)
    if mode == "limit":
        emit({{"type": "rate_limit_event", "rate_limit_info": {{"status": "rejected"}}}})
        emit({{"type": "result", "is_error": True, "result": "usage limit"}}); sys.exit(1)
    emit({{"type": "result", "is_error": False, "result": "VERDICT: APPROVED", "num_turns": 2,
          "usage": {{"input_tokens": 1, "cache_creation_input_tokens": 2, "cache_read_input_tokens": 3,
                    "output_tokens": 4}}, "subagent_stats": {{"spawned": 0}}}})
''')


class TestRunPeerWithFakeClaude(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        bindir = os.path.join(self.tmp.name, "bin")
        os.makedirs(bindir)
        if os.name == "nt":
            self.skipTest("가짜 CLI 실행 파일은 POSIX shebang 으로 만든다")
        path = os.path.join(bindir, "claude")
        with open(path, "w") as f:
            f.write(_FAKE_CLAUDE.format(python=sys.executable))
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        self.log = os.path.join(self.tmp.name, "log.json")
        self.root = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.root)
        env = {"PATH": bindir + os.pathsep + os.environ.get("PATH", ""), "FAKE_LOG": self.log}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, timeout=30, **env):
        with mock.patch.dict(os.environ, env):
            return P.run_peer("claude", "PACKET BODY", timeout, "high", root=self.root, env=dict(os.environ))

    def test_controlled_success(self):
        run = self._run()
        self.assertTrue(run.ok, run.error)
        self.assertEqual(run.controls, "full")
        self.assertEqual(run.review, "VERDICT: APPROVED")
        self.assertEqual(run.usage["new_input"], 3)
        with open(self.log) as f:
            seen = json.load(f)
        self.assertIn("--restricted", seen["argv"])
        # 프로젝트 지침(CLAUDE.md) 자동 주입을 피하려고 저장소 밖에서 띄운다.
        self.assertNotEqual(os.path.realpath(seen["cwd"]), os.path.realpath(self.root))
        self.assertTrue(seen["prompt"].startswith("# SAGE reviewer contract"))
        self.assertIn(self.root, seen["prompt"])
        self.assertTrue(seen["prompt"].rstrip().endswith("PACKET BODY"))

    def test_old_version_runs_without_controls(self):
        run = self._run(FAKE_VERSION="2.1.100", FAKE_MODE="ok")
        self.assertEqual(run.controls, "none")
        with open(self.log) as f:
            seen = json.load(f)
        self.assertNotIn("--restricted", seen["argv"])
        self.assertEqual(seen["prompt"], "PACKET BODY")

    def test_rejected_flags_have_their_own_reason(self):
        run = self._run(FAKE_MODE="reject")
        self.assertFalse(run.ok)
        self.assertEqual(run.reason, "flags_rejected")

    def test_usage_limit_is_distinguished(self):
        run = self._run(FAKE_MODE="limit")
        self.assertFalse(run.ok)
        self.assertEqual(run.reason, "usage_limit")

    def test_timeout_keeps_emitted_findings(self):
        run = self._run(timeout=3, FAKE_MODE="hang")
        self.assertFalse(run.ok)
        self.assertEqual(run.reason, "timeout")
        self.assertIn("FINDING: P2", run.partial)


class _Args:
    def __init__(self, root, packet_file, on_peer_failure="block", timeout=540):
        self.root = root; self.packet_file = packet_file; self.timeout = timeout
        self.strict = False; self.host = None; self.on_peer_failure = on_peer_failure


class TestCrossCheckFallback(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"SAGE_HOST": "claude"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = self.tmp.name
        self._write_profile("")
        self.packet = os.path.join(self.d, "packet.md")
        with open(self.packet, "w", encoding="utf-8") as f:
            f.write("diff")
        self.calls = []
        self.orig = RV._invoke_peer
        self.addCleanup(lambda: setattr(RV, "_invoke_peer", self.orig))

    def _write_profile(self, extra):
        os.makedirs(os.path.join(self.d, "sage"), exist_ok=True)
        with open(os.path.join(self.d, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("runtime: { host: claude }\noptions: { cross_model: true }\n"
                    "capabilities: { codex: true }\n" + extra)

    def _fake(self, peer_error):
        def fake(peer, prompt, timeout, effort=None, model=None):
            self.calls.append((peer, timeout))
            if peer == "codex":
                return False, None, peer_error
            return True, "SAME RUNTIME VERDICT", None
        RV._invoke_peer = fake

    def _run(self, mode):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = RV.run_cross_check(_Args(self.d, self.packet, mode))
        return rc, out.getvalue()

    def test_default_blocks_and_names_the_reason(self):
        self._fake(Diagnostic("review.peer_timeout", peer="codex", timeout=540))
        rc, out = self._run("block")
        self.assertEqual(rc, 3)
        self.assertIn("REVIEWER_BLOCK_REASON: timeout", out)
        self.assertIn("REVIEWER_STATUS: BLOCKED", out)
        self.assertEqual([c[0] for c in self.calls], ["codex"])

    def test_same_runtime_fallback_is_recorded_as_degraded(self):
        self._fake(Diagnostic("review.peer_exit_nonzero", peer="codex", code=1))
        rc, out = self._run("same-runtime")
        self.assertEqual(rc, 0)
        self.assertEqual([c[0] for c in self.calls], ["codex", "claude"])
        self.assertEqual(self.calls[1][1], 270, "폴백은 제한 시간의 절반")
        self.assertIn("SAME RUNTIME VERDICT", out)
        self.assertIn("REVIEWER_FALLBACK_FROM: codex", out)
        self.assertIn("REVIEWER_BLOCK_REASON: exit_nonzero", out)
        self.assertIn("REVIEWER_ACTUAL: same_runtime", out)
        self.assertIn("REVIEWER_STATUS: COMPLETE_DEGRADED", out)
        self.assertNotIn("REVIEWER_ACTUAL: cross_model", out)

    def test_parse_failure_is_not_covered_by_fallback(self):
        # peer 는 답했는데 수집에 실패했다 — 자체 리뷰로 덮지 않고 원인을 조사한다.
        self._fake(Diagnostic("review.peer_parse_failed", peer="codex"))
        rc, out = self._run("same-runtime")
        self.assertEqual(rc, 3)
        self.assertIn("REVIEWER_BLOCK_REASON: parse_failed", out)
        self.assertEqual([c[0] for c in self.calls], ["codex"])

    def test_required_policy_never_falls_back(self):
        self._write_profile("cross_model: { policy: required }\n")
        self._fake(Diagnostic("review.peer_timeout", peer="codex", timeout=540))
        rc, out = self._run("same-runtime")
        self.assertEqual(rc, 3)
        self.assertEqual([c[0] for c in self.calls], ["codex"])

    def test_success_reports_unknown_usage_for_patched_peer(self):
        RV._invoke_peer = lambda peer, prompt, timeout, effort=None, model=None: (True, "SHIP", None)
        rc, out = self._run("block")
        self.assertEqual(rc, 0)
        self.assertIn("REVIEWER_TOKENS: unknown", out)
        self.assertIn("REVIEWER_AUDIT: unknown", out)
        self.assertIn("REVIEWER_STATUS: COMPLETE", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
