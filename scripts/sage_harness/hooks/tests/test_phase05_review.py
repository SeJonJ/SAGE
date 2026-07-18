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
    def __init__(self, root=None, packet_file=None, timeout=540, strict=False,
                 kind=None, batch=False, gate=False):
        self.root = root; self.packet_file = packet_file; self.timeout = timeout; self.strict = strict
        self.kind = kind; self.batch = batch; self.gate = gate


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

    def test_claude_json_error_not_accepted(self):
        # is_error:true 응답의 result(에러 메시지)를 성공 리뷰로 오인하면 안 됨(codex 배치2 R5 P1).
        self.assertIsNone(RV._parse_claude_json('{"is_error":true,"result":"rate limit exceeded"}'))
        self.assertEqual(RV._parse_claude_json('{"is_error":false,"result":"VERDICT: SHIP"}'), "VERDICT: SHIP")

    def test_peer_command_codex_no_prompt_arg(self):
        # 프롬프트는 stdin 으로 — argv 에 포함되면 안 됨(ARG_MAX 회피, codex R1 P1).
        cmd = RV._peer_command("codex")
        self.assertEqual(cmd, ["codex", "exec", "--json", "-s", "read-only"])
        self.assertNotIn("PROMPT", cmd)

    def test_peer_command_default_overrides_nothing(self):
        # effort 미설정 → peer CLI 자신의 설정이 정한다. model 은 어느 경우에도 엔진이 정하지 않는다.
        for peer in ("codex", "claude"):
            argv = " ".join(RV._peer_command(peer))
            self.assertNotIn("model_reasoning_effort", argv)
            self.assertNotIn("--model", argv)
            self.assertNotIn("--effort", argv)

    def test_peer_command_appends_effort_when_set(self):
        self.assertEqual(RV._peer_command("codex", "low")[-2:], ["-c", 'model_reasoning_effort="low"'])
        self.assertEqual(RV._peer_command("claude", "max")[-2:], ["--effort", "max"])
        # effort 를 줘도 model 은 여전히 peer 몫.
        self.assertNotIn("--model", RV._peer_command("claude", "max"))

    def test_peer_command_appends_explicit_model_without_shell_interpolation(self):
        self.assertIn("gpt-picked", RV._peer_command("codex", "high", "gpt-picked"))
        self.assertEqual(RV._peer_command("codex", "high", "gpt-picked")[-2:], ["-m", "gpt-picked"])
        self.assertEqual(RV._peer_command("claude", "high", "opus")[-2:], ["--model", "opus"])

    def test_peer_command_claude_no_prompt_arg(self):
        self.assertEqual(RV._peer_command("claude"), ["claude", "-p", "--output-format", "json"])

    def test_peer_command_unknown(self):
        with self.assertRaises(ValueError):
            RV._peer_command("gpt")


class TestEffortIssue(unittest.TestCase):
    def test_unset_is_ok(self):
        self.assertIsNone(RV.effort_issue("codex", None))
        self.assertIsNone(RV.effort_issue("claude", ""))

    def test_valid_values_per_peer(self):
        self.assertIsNone(RV.effort_issue("codex", "minimal"))
        self.assertIsNone(RV.effort_issue("claude", "max"))

    def test_vocabularies_are_not_interchangeable(self):
        # 실측: codex 는 max 를, claude 는 minimal 을 모른다. 서로의 값을 빌려 쓰면 안 됨.
        self.assertIsNotNone(RV.effort_issue("codex", "max"))
        self.assertIsNotNone(RV.effort_issue("claude", "minimal"))

    def test_unknown_value_blocked_because_peer_ignores_it_silently(self):
        msg = RV.effort_issue("codex", "bogus")
        self.assertIn("bogus", msg)
        self.assertIn("조용히 무시", msg)

    def test_unknown_peer(self):
        self.assertIsNotNone(RV.effort_issue("gpt", "high"))


class TestReview(unittest.TestCase):
    def test_recommended_local_opt_out_resolves_same_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            _mkprofile(d, host="codex", cross=True)
            with open(os.path.join(d, "sage", "project-profile.yaml"), "a", encoding="utf-8") as f:
                f.write("cross_model: { policy: recommended }\n")
            with open(os.path.join(d, "sage", "project-profile.local.yaml"), "w", encoding="utf-8") as f:
                f.write("cross_model: { enabled: false }\n")

            profile, _, resolution = RV._load_profile_caps(d)

            self.assertFalse(profile["options"]["cross_model"])
            self.assertEqual("clean_context_same_runtime", resolution["reviewer_mode"])

    def test_required_local_opt_out_blocks_review_command(self):
        with tempfile.TemporaryDirectory() as d:
            _mkprofile(d, host="codex", cross=False)
            with open(os.path.join(d, "sage", "project-profile.yaml"), "a", encoding="utf-8") as f:
                f.write("cross_model: { policy: required }\n")
            with open(os.path.join(d, "sage", "project-profile.local.yaml"), "w", encoding="utf-8") as f:
                f.write("cross_model: { enabled: false }\n")
            err = io.StringIO()
            with redirect_stderr(err):
                rc = RV.run_review(_Args(root=d))

            self.assertEqual(2, rc)
            self.assertIn("완화할 수 없음", err.getvalue())

    def test_review_same_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            _mkprofile(d, cross=False)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = RV.run_review(_Args(root=d))
            self.assertEqual(rc, 0)
            self.assertIn("REVIEWER_ACTUAL: same_runtime", buf.getvalue())

    def test_review_legacy_flag_migration_message(self):
        # 구 `sage review --gate`(자산분류) → 친절한 asset-check 안내 + exit 2 (codex 배치2 R3 P1).
        err = io.StringIO()
        with redirect_stderr(err):
            rc = RV.run_review(_Args(gate=True))
        self.assertEqual(rc, 2)
        self.assertIn("asset-check", err.getvalue())


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
            RV._invoke_peer = lambda peer, prompt, timeout, effort=None: (True, f"{peer} says SHIP", None)
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

    def _profile_cross_codex(self, d, effort=None):
        os.makedirs(os.path.join(d, "sage"), exist_ok=True)
        extra = f"cross_model: {{ effort: {effort} }}\n" if effort else ""
        with open(os.path.join(d, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("runtime: { host: claude }\noptions: { cross_model: true }\n"
                    "capabilities: { codex: true }\n" + extra)

    def test_cross_effort_passed_to_peer(self):
        with tempfile.TemporaryDirectory() as d:
            self._profile_cross_codex(d, effort="low")
            seen = {}
            orig = RV._invoke_peer

            def fake(peer, prompt, timeout, effort=None):
                seen["effort"] = effort
                return True, "SHIP", None

            RV._invoke_peer = fake
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    rc = RV.run_cross_check(_Args(root=d, packet_file=self._packet(d)))
            finally:
                RV._invoke_peer = orig
            self.assertEqual(rc, 0)
            self.assertEqual(seen["effort"], "low")

    def test_explicit_reviewer_model_passed_to_peer(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sage"), exist_ok=True)
            with open(os.path.join(d, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
                f.write("runtime: { host: claude }\noptions: { cross_model: true }\n"
                        "capabilities: { codex: true }\n"
                        "cross_model: { effort: low, reviewer: { host: codex, model: gpt-picked } }\n")
            seen = {}
            orig = RV._invoke_peer

            def fake(peer, prompt, timeout, effort=None, model=None):
                seen.update(peer=peer, effort=effort, model=model)
                return True, "SHIP", None

            RV._invoke_peer = fake
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    rc = RV.run_cross_check(_Args(root=d, packet_file=self._packet(d)))
            finally:
                RV._invoke_peer = orig
            self.assertEqual(rc, 0)
            self.assertEqual(seen, {"peer": "codex", "effort": "low", "model": "gpt-picked"})

    def test_cross_effort_unset_uses_default_high(self):
        # peer CLI 기본값에 맡기지 않는다 — Phase 05 리뷰 강도가 조용히 낮아지면 안 됨.
        with tempfile.TemporaryDirectory() as d:
            self._profile_cross_codex(d)
            seen = {}
            orig = RV._invoke_peer

            def fake(peer, prompt, timeout, effort=None):
                seen["effort"] = effort
                return True, "SHIP", None

            RV._invoke_peer = fake
            try:
                err = io.StringIO()
                with redirect_stdout(io.StringIO()), redirect_stderr(err):
                    rc = RV.run_cross_check(_Args(root=d, packet_file=self._packet(d)))
            finally:
                RV._invoke_peer = orig
            self.assertEqual(rc, 0)
            self.assertEqual(seen["effort"], RV.DEFAULT_EFFORT)
            self.assertEqual(seen["effort"], "high")
            self.assertIn("기본값", err.getvalue())   # 설정값이 아님을 표면화

    def test_default_effort_valid_for_both_peers(self):
        # 기본값이 한쪽 peer 어휘에만 있으면 그 host 의 cross-check 가 전부 exit 2 로 죽는다.
        for peer in ("codex", "claude"):
            self.assertIsNone(RV.effort_issue(peer, RV.DEFAULT_EFFORT))

    def test_falsy_effort_is_not_read_as_unset(self):
        # `effort: false` / `effort: 0` 를 `or` 로 미설정 취급하면 기본값으로 흡수돼 fail-closed 가 깨진다.
        for bad in ("false", "0"):
            with tempfile.TemporaryDirectory() as d:
                self._profile_cross_codex(d, effort=bad)
                orig = RV._invoke_peer
                RV._invoke_peer = lambda *a, **k: self.fail(f"effort={bad} 인데 peer 를 호출함")
                try:
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        rc = RV.run_cross_check(_Args(root=d, packet_file=self._packet(d)))
                finally:
                    RV._invoke_peer = orig
                self.assertEqual(rc, 2, f"effort={bad} 는 TOOL ERROR 여야 함")

    def test_bad_effort_fails_even_when_peer_unreachable(self):
        # peer 가 마침 미가용이면 폴백이 먼저 return 해 잘못된 설정이 통과했다(codex 5R).
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sage"), exist_ok=True)
            with open(os.path.join(d, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
                f.write("runtime: { host: claude }\noptions: { cross_model: true }\n"
                        "cross_model: { effort: max }\n")   # max 는 claude 어휘, peer=codex 는 모름
            orig = RV._doctor.reviewer_resolution
            RV._doctor.reviewer_resolution = lambda p, c: {
                "reviewer_mode": "clean_context_same_runtime", "reviewer_runtime": "claude",
                "fallback_used": True, "reviewer_degraded": True,
                "reviewer_degrade_reason": "codex_cli_unavailable", "notice": "n/a"}
            try:
                err = io.StringIO()
                with redirect_stdout(io.StringIO()), redirect_stderr(err):
                    rc = RV.run_cross_check(_Args(root=d, packet_file=self._packet(d)))
            finally:
                RV._doctor.reviewer_resolution = orig
            self.assertEqual(rc, 2, "peer 미가용이어도 잘못된 effort 는 TOOL ERROR")
            self.assertIn("max", err.getvalue())

    def test_cross_check_enforces_the_same_cross_model_rules_as_validate(self):
        # validate 가 FAIL 이라 부르는 설정을 cross-check 가 조용히 무시한 채 기본값으로 돌면 안 된다.
        import sage.profile_validate as pv
        for line in ("cross_model: { effrot: xhigh }",
                     "cross_model: { on_unavailable: block }",
                     "cross_model: { peer: claude }",
                     "cross_model: [effort, max]"):
            with tempfile.TemporaryDirectory() as d:
                os.makedirs(os.path.join(d, "sage"), exist_ok=True)
                body = ("runtime: { host: claude }\noptions: { cross_model: true }\n"
                        "capabilities: { codex: true }\n" + line + "\n")
                with open(os.path.join(d, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
                    f.write(body)
                orig = RV._invoke_peer
                RV._invoke_peer = lambda *a, **k: self.fail(f"peer 를 호출하면 안 됨: {line}")
                try:
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        rc = RV.run_cross_check(_Args(root=d, packet_file=self._packet(d)))
                finally:
                    RV._invoke_peer = orig
                self.assertEqual(rc, 2, line)
                import yaml
                prof = yaml.safe_load(body)
                self.assertEqual(pv.severity_of(pv.validate_profile(prof, REPO)), "FAIL", line)

    def test_cross_bad_effort_is_tool_error_not_silent_ignore(self):
        # codex 는 모르는 effort 를 조용히 무시한다 → 설정대로 돈 것처럼 보이면 안 됨. peer 호출 전 차단.
        with tempfile.TemporaryDirectory() as d:
            self._profile_cross_codex(d, effort="max")   # max 는 claude 어휘, codex 는 모름
            orig = RV._invoke_peer
            RV._invoke_peer = lambda *a, **k: self.fail("peer 를 호출하면 안 됨")
            try:
                err = io.StringIO()
                with redirect_stdout(io.StringIO()), redirect_stderr(err):
                    rc = RV.run_cross_check(_Args(root=d, packet_file=self._packet(d)))
            finally:
                RV._invoke_peer = orig
            self.assertEqual(rc, 2)
            self.assertIn("max", err.getvalue())

    def test_cross_on_peer_failure_falls_back_not_silent(self):
        with tempfile.TemporaryDirectory() as d:
            self._profile_cross_codex(d)
            orig = RV._invoke_peer
            RV._invoke_peer = lambda peer, prompt, timeout, effort=None: (False, None, "codex 호출 timeout(540s)")
            try:
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    rc = RV.run_cross_check(_Args(root=d, packet_file=self._packet(d)))
            finally:
                RV._invoke_peer = orig
            self.assertEqual(rc, 0)
            self.assertIn("REVIEWER_ACTUAL: same_runtime", out.getvalue())   # degraded 근거
            self.assertIn("timeout", err.getvalue())                          # 실패 사유 표면화

    def test_cross_strict_nonzero_on_fallback(self):
        # --strict: cross-model 미수행(폴백) 시 exit 3 (stdout 센티넬 못 보는 caller 용).
        with tempfile.TemporaryDirectory() as d:
            _mkprofile(d, cross=False)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                rc = RV.run_cross_check(_Args(root=d, packet_file=self._packet(d), strict=True))
            self.assertEqual(rc, 3)

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
