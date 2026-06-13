#!/usr/bin/env python3
"""post-tool-logger reverse_extract 폐루프 검증 (첫 structural_io_adapter + profile_bound 케이스).

검증:
  1. core decision parity   — decide(event, profile): changes 분류/skip_untyped/today 결정론
  2. profile classification — 6개 type 글롭 매칭 + plan-doc drift canonical(*plan_docs/* = 컴포넌트 포함)
  3. adapter e2e structural — claude 단일 file_path vs codex apply_patch 다중파일 → 동일 분류
  4. skip parity            — 미분류(README) 양쪽 0건
  5. behavior parity        — 동일 변경 파일이면 (file,type) 동일(tool 필드만 런타임차이)
now_utc=SAGE_NOW_UTC, branch=SAGE_GATE_BRANCH 로 결정론.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
ADAPTERS = os.path.join(HOOKS_DIR, "adapters")
PROFILE_PATH = os.path.join(HERE, "fixtures", "post_tool_logger", "chatforyou.profile.json")
FIXED_TS = "2026-06-13T00:00:00Z"
BRANCH = "testbranch"

sys.path.insert(0, HOOKS_DIR)
import post_tool_logger_core as core  # noqa: E402

with open(PROFILE_PATH, encoding="utf-8") as _f:
    PROFILE = json.load(_f)


def mk_event(changes, tool="Write", runtime="claude"):
    return {
        "hook_id": "post-tool-logger", "hook_event_name": "PostToolUse", "runtime": runtime,
        "session_id": "test", "tool": tool, "branch": BRANCH, "now_utc": FIXED_TS,
        "changes": changes,
    }


class TestCore(unittest.TestCase):
    def test_classification(self):
        cases = [
            ("springboot-backend/src/main/java/webChat/Foo.java", "backend-main"),
            ("springboot-backend/src/test/java/webChat/FooTest.java", "backend-test"),
            ("nodejs-frontend/static/js/rtc/x.js", "frontend-js"),
            ("nodejs-frontend/server.js", "frontend-server"),
            ("nodejs-frontend/config/app.js", "frontend-config"),
            ("plan_docs/00-base/x.md", "plan-doc"),
            # plan-doc drift canonical: 컴포넌트 plan_docs 도 포함 (*plan_docs/*)
            ("springboot-backend/plan_docs/feature.md", "plan-doc"),
        ]
        for path, expected_type in cases:
            d = core.decide(mk_event([{"path": path, "op": "write"}]), PROFILE)
            self.assertEqual(d["action"], "log", path)
            self.assertEqual(d["log_entries"][0]["type"], expected_type, path)
            self.assertEqual(d["log_entries"][0]["ts"], FIXED_TS, path)
        self.assertEqual(core.decide(mk_event([]), PROFILE)["log_file"], "session-2026-06-13.jsonl")

    def test_skip_untyped(self):
        d = core.decide(mk_event([{"path": "README.md", "op": "write"}]), PROFILE)
        self.assertEqual(d["action"], "noop")
        self.assertEqual(d["log_entries"], [])

    def test_multi_changes(self):
        d = core.decide(mk_event([
            {"path": "springboot-backend/src/main/java/A.java", "op": "add"},
            {"path": "README.md", "op": "update"},                 # 미분류 → skip
            {"path": "nodejs-frontend/static/js/b.js", "op": "update"},
        ]), PROFILE)
        types = [e["type"] for e in d["log_entries"]]
        self.assertEqual(types, ["backend-main", "frontend-js"])  # README skip


def run_adapter(runtime, raw, project_root):
    env_root = "CLAUDE_PROJECT_DIR" if runtime == "claude" else "CODEX_PROJECT_ROOT"
    env = dict(os.environ, **{
        env_root: project_root, "SAGE_HOOK_CORE_DIR": HOOKS_DIR,
        "SAGE_NOW_UTC": FIXED_TS, "SAGE_GATE_BRANCH": BRANCH, "SAGE_PROFILE": PROFILE_PATH,
    })
    adapter = os.path.join(ADAPTERS, runtime, "post-tool-logger.sh")
    return subprocess.run(["bash", adapter], input=json.dumps(raw), capture_output=True, text=True, env=env)


def read_log(runtime, project_root):
    sub = ".claude" if runtime == "claude" else ".codex"
    p = os.path.join(project_root, sub, "logs", "session-2026-06-13.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestAdapters(unittest.TestCase):
    def test_claude_single(self):
        with tempfile.TemporaryDirectory() as root:
            fp = os.path.join(root, "springboot-backend/src/main/java/webChat/Foo.java")
            p = run_adapter("claude", {"tool_name": "Write", "tool_input": {"file_path": fp}, "session_id": "test"}, root)
            self.assertEqual(p.returncode, 0)
            entries = read_log("claude", root)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["type"], "backend-main")
            self.assertEqual(entries[0]["file"], "springboot-backend/src/main/java/webChat/Foo.java")
            self.assertEqual(entries[0]["branch"], BRANCH)

    def test_codex_apply_patch_multi(self):
        with tempfile.TemporaryDirectory() as root:
            cmd = (
                "*** Begin Patch\n"
                "*** Add File: springboot-backend/src/main/java/A.java\n+x\n"
                "*** Update File: nodejs-frontend/static/js/b.js\n+y\n"
                "*** Add File: README.md\n+z\n"          # 미분류 → skip
                "*** End Patch\n"
            )
            p = run_adapter("codex", {"tool_name": "apply_patch", "tool_input": {"command": cmd}, "session_id": "test"}, root)
            self.assertEqual(p.returncode, 0)
            entries = read_log("codex", root)
            types = [e["type"] for e in entries]
            self.assertEqual(types, ["backend-main", "frontend-js"])  # README skip

    def test_skip_untyped_both(self):
        for runtime, raw in [
            ("claude", {"tool_name": "Write", "tool_input": {"file_path": "README.md"}, "session_id": "test"}),
            ("codex", {"tool_name": "apply_patch", "tool_input": {"command": "*** Add File: README.md\n+x\n"}, "session_id": "test"}),
        ]:
            with tempfile.TemporaryDirectory() as root:
                run_adapter(runtime, raw, root)
                self.assertEqual(read_log(runtime, root), [], runtime)

    def test_behavior_parity(self):
        # 동일 파일 변경 → (file,type) 동일, tool 필드만 런타임차이
        with tempfile.TemporaryDirectory() as r1, tempfile.TemporaryDirectory() as r2:
            fp = os.path.join(r1, "springboot-backend/src/main/java/A.java")
            run_adapter("claude", {"tool_name": "Write", "tool_input": {"file_path": fp}, "session_id": "test"}, r1)
            run_adapter("codex", {"tool_name": "apply_patch", "tool_input": {"command": "*** Add File: springboot-backend/src/main/java/A.java\n+x\n"}, "session_id": "test"}, r2)
            ec, ex = read_log("claude", r1), read_log("codex", r2)
            self.assertEqual([(e["file"], e["type"]) for e in ec], [(e["file"], e["type"]) for e in ex])
            self.assertEqual(ec[0]["tool"], "Write")
            self.assertEqual(ex[0]["tool"], "apply_patch")


if __name__ == "__main__":
    unittest.main(verbosity=2)
