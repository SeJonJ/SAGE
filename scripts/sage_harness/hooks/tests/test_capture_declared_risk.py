#!/usr/bin/env python3
"""capture-declared-risk reverse_extract 폐루프 검증.

3종 검증(설계 합의):
  1. core decision parity  — fixture 3종에 대해 core.decide 결정이 기대값과 일치 (런타임 중립)
  2. adapter end-to-end     — claude/codex adapter 를 실제 실행해 exit/state file/stdout snapshot 검증
  3. behavior parity        — 동일 입력에 claude/codex 의 decision(level/exit/state)은 동일, 출력 렌더만 다름

now_utc 는 SAGE_NOW_UTC 로 고정해 timestamp 결정론 확보.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)                      # scripts/sage_harness/hooks
FIXTURES = os.path.join(HERE, "fixtures", "capture_declared_risk")
ADAPTERS = os.path.join(HOOKS_DIR, "adapters")
FIXED_TS = "2026-06-13T00:00:00Z"

sys.path.insert(0, HOOKS_DIR)
import capture_declared_risk_core as core  # noqa: E402


def load_fixture(name):
    with open(os.path.join(FIXTURES, name + ".event.json"), encoding="utf-8") as f:
        return json.load(f)


# (fixture, expected_action, expected_level)
CASES = [
    ("capture_l3", "capture", "L3"),
    ("capture_meta", "noop", None),
    ("capture_none", "noop", None),
]


class TestCore(unittest.TestCase):
    def test_decision_parity(self):
        for name, action, level in CASES:
            ev = load_fixture(name)
            d = core.decide(ev)
            self.assertEqual(d["action"], action, name)
            self.assertEqual(d["level"], level, name)
            if action == "capture":
                self.assertEqual(d["state"]["ts"], FIXED_TS, name)
                self.assertEqual(d["state_file"], "declared-risk-test.json", name)
            else:
                self.assertIsNone(d["state"], name)

    def test_cleanup_declared(self):
        # cleanup 정책은 항상 선언됨 (capture/noop 무관)
        for name, _, _ in CASES:
            d = core.decide(load_fixture(name))
            self.assertEqual(d["cleanup"]["older_than_seconds"], 2 * 86400, name)


def run_adapter(runtime, fixture, project_root):
    """adapter 를 실제 실행. 런타임 raw stdin = {prompt, session_id}."""
    ev = load_fixture(fixture)
    raw = json.dumps({"prompt": ev["prompt"], "session_id": ev["session_id"]})
    env_root = "CLAUDE_PROJECT_DIR" if runtime == "claude" else "CODEX_PROJECT_ROOT"
    env = dict(os.environ, **{
        env_root: project_root,
        "SAGE_HOOK_CORE_DIR": HOOKS_DIR,
        "SAGE_NOW_UTC": FIXED_TS,
    })
    adapter = os.path.join(ADAPTERS, runtime, "capture-declared-risk.sh")
    p = subprocess.run(["bash", adapter], input=raw, capture_output=True, text=True, env=env)
    return p


def state_path(runtime, project_root):
    sub = ".claude" if runtime == "claude" else ".codex"
    return os.path.join(project_root, sub, "logs", "declared-risk-test.json")


class TestAdapters(unittest.TestCase):
    def test_end_to_end(self):
        for runtime in ("claude", "codex"):
            for name, action, level in CASES:
                with tempfile.TemporaryDirectory() as root:
                    p = run_adapter(runtime, name, root)
                    self.assertEqual(p.returncode, 0, f"{runtime}/{name} exit")
                    sp = state_path(runtime, root)
                    if action == "capture":
                        self.assertTrue(os.path.exists(sp), f"{runtime}/{name} state file 생성")
                        with open(sp, encoding="utf-8") as f:
                            st = json.load(f)
                        self.assertEqual(st["level"], level, f"{runtime}/{name} level")
                        self.assertEqual(st["ts"], FIXED_TS, f"{runtime}/{name} ts 결정론")
                        # 출력 프로토콜은 런타임마다 다름
                        if runtime == "claude":
                            self.assertIn("[Risk 선언 포착]", p.stdout)
                            self.assertNotIn("hookSpecificOutput", p.stdout)
                        else:
                            self.assertIn("hookSpecificOutput", p.stdout)
                            doc = json.loads(p.stdout)
                            self.assertIn("additionalContext", doc["hookSpecificOutput"])
                    else:
                        self.assertFalse(os.path.exists(sp), f"{runtime}/{name} 파일 미생성")
                        self.assertNotIn("포착", p.stdout, f"{runtime}/{name} 출력 없음")

    def test_behavior_parity_between_runtimes(self):
        # 동일 입력: claude/codex 의 state(level/ts)는 동일, stdout 렌더만 다름
        for name, action, level in CASES:
            if action != "capture":
                continue
            with tempfile.TemporaryDirectory() as r1, tempfile.TemporaryDirectory() as r2:
                pc = run_adapter("claude", name, r1)
                px = run_adapter("codex", name, r2)
                with open(state_path("claude", r1), encoding="utf-8") as f:
                    sc = json.load(f)
                with open(state_path("codex", r2), encoding="utf-8") as f:
                    sx = json.load(f)
                self.assertEqual(sc, sx, f"{name} state 동일(behavior parity)")
                self.assertNotEqual(pc.stdout, px.stdout, f"{name} 출력 렌더는 달라야")


if __name__ == "__main__":
    unittest.main(verbosity=2)
