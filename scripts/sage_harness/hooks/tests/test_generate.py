#!/usr/bin/env python3
"""sage generate 검증 (상 등급 — hook 등록 산출물 + manifest 스탬프, Codex 2R).

self-contained: 임시 SAGE 루트(hook spec frontmatter + adapter stub + manifest)로 등록 생성 확인.
"""
import json
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import generate as gen  # noqa: E402

SPEC_A = """---
id: aaa-hook
kind: hook
runtime_bindings:
  claude: { event: PreToolUse, matcher: "Write|Edit|MultiEdit", timeout: 10 }
  codex: { event: PreToolUse, matcher: "apply_patch", timeout: 10 }
---
## intent
test
"""
SPEC_B = """---
id: bbb-hook
kind: hook
runtime_bindings:
  claude: { event: Stop, matcher: "", timeout: 15 }
  codex: { event: Stop, matcher: "", timeout: 15 }
---
## intent
test
"""


def make_root(d, with_adapter=True):
    os.makedirs(os.path.join(d, "docs", "sage_harness", "hooks"), exist_ok=True)
    os.makedirs(os.path.join(d, "scripts", "sage_harness", "hooks", "adapters", "claude"), exist_ok=True)
    os.makedirs(os.path.join(d, "scripts", "sage_harness", "hooks", "adapters", "codex"), exist_ok=True)
    open(os.path.join(d, "docs", "sage_harness", "hooks", "aaa-hook.md"), "w").write(SPEC_A)
    open(os.path.join(d, "docs", "sage_harness", "hooks", "bbb-hook.md"), "w").write(SPEC_B)
    json.dump({"sage_version": "0.1.0", "host_runtime": "claude", "assets": {
        "hooks/aaa-hook": {"form": "core_adapter", "spec_hash": "x", "render_hash": {"claude": "x"}, "conformance": "PASS"},
        "hooks/bbb-hook": {"form": "core_adapter", "spec_hash": "x", "render_hash": {"claude": "x"}, "conformance": "PASS"},
    }}, open(os.path.join(d, "docs", "sage_harness", ".manifest.json"), "w"))
    if with_adapter:
        for hid in ("aaa-hook", "bbb-hook"):
            for rt in ("claude", "codex"):
                open(os.path.join(d, "scripts", "sage_harness", "hooks", "adapters", rt, f"{hid}.sh"), "w").write("#!/bin/bash\n")


class Args:
    def __init__(self, **kw):
        self.kind = "hook"; self.id = None; self.write = False
        self.target = "claude"; self.dest = "."; self.root = None
        self.__dict__.update(kw)


class TestGenerate(unittest.TestCase):
    def test_parse_runtime_bindings(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d)
            rb = gen._parse_runtime_bindings(os.path.join(d, "docs", "sage_harness", "hooks", "aaa-hook.md"))
            self.assertEqual(rb["claude"]["event"], "PreToolUse")
            self.assertEqual(rb["claude"]["matcher"], "Write|Edit|MultiEdit")
            self.assertEqual(rb["claude"]["timeout"], 10)
            self.assertEqual(rb["codex"]["matcher"], "apply_patch")

    def test_build_registration_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d)
            reg, missing = gen._build_registration(d, "claude", ["bbb-hook", "aaa-hook"])
            self.assertEqual(missing, [])
            # PreToolUse(aaa) + Stop(bbb), event 정렬
            self.assertIn("PreToolUse", reg)
            self.assertIn("Stop", reg)
            self.assertIn("aaa-hook", reg["PreToolUse"][0]["hooks"][0]["command"])

    def test_missing_adapter_fail(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d, with_adapter=False)
            reg, missing = gen._build_registration(d, "claude", ["aaa-hook"])
            self.assertTrue(any("adapter" in m for m in missing))

    def test_write_creates_settings(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            make_root(d)
            rc = gen.run(Args(target="both", dest=dest, root=d, write=True))
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(dest, ".claude", "settings.json")))
            self.assertTrue(os.path.exists(os.path.join(dest, ".codex", "hooks.json")))
            s = json.load(open(os.path.join(dest, ".claude", "settings.json")))
            self.assertIn("hooks", s)
            # codex wrapper 형식
            x = json.load(open(os.path.join(dest, ".codex", "hooks.json")))
            cmd = x["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            self.assertIn("CODEX_HOME", cmd)

    def test_agent_generate_guidance(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d)
            rc = gen.run(Args(kind="agent", root=d))
            self.assertEqual(rc, 0)  # 안내 + exit 0

    def test_deterministic_output(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d)
            r1, _ = gen._build_registration(d, "claude", ["aaa-hook", "bbb-hook"])
            r2, _ = gen._build_registration(d, "claude", ["bbb-hook", "aaa-hook"])
            self.assertEqual(json.dumps(r1, sort_keys=True), json.dumps(r2, sort_keys=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
