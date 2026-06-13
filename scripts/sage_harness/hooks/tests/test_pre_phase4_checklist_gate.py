#!/usr/bin/env python3
"""pre-phase4-checklist-gate 폐루프 검증 (IO-bound gate: 2단계 pure core).

검증:
  1. core(in-memory snapshot): all checked→ok / 03 missing→warn / unchecked(03·backend)→block+count
  2. core: suffix 반복제거 base, exact 우선, prefix 양방향 match, read_error 추적
  3. adapter(temp tree): claude file_path & codex apply_patch → 동일 status/exit
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
PROFILE_PATH = os.path.join(HERE, "fixtures", "pre_phase4", "chatforyou.profile.json")

sys.path.insert(0, HOOKS_DIR)
import pre_phase4_checklist_gate_core as core  # noqa: E402

with open(PROFILE_PATH, encoding="utf-8") as _f:
    PROFILE = json.load(_f)

G_IMPL = "plan_docs/03-implementation/*.md"
G_BE = "springboot-backend/plan_docs/*.md"
G_FE = "nodejs-frontend/plan_docs/*.md"


def ev(four="plan_docs/04-analyze/feature_analyze.md"):
    return {"hook_id": "pre-phase4-checklist-gate", "runtime": "test",
            "changes": [{"path": four, "op": "write"}]}


def snap(glob_results=None, files=None):
    return {"glob_results": glob_results or {}, "files": files or {}}


class TestCore(unittest.TestCase):
    def test_ok_all_checked(self):
        s = snap({G_IMPL: ["plan_docs/03-implementation/feature.md"], G_BE: [], G_FE: []},
                 {"plan_docs/03-implementation/feature.md": "- [x] done\n- [x] more"})
        d = core.decide(ev(), PROFILE, s)
        self.assertEqual(d["status"], "ok")
        self.assertEqual(d["exit_code"], 0)
        self.assertEqual(d["base"], "feature")

    def test_warn_no_impl(self):
        d = core.decide(ev(), PROFILE, snap({G_IMPL: [], G_BE: [], G_FE: []}, {}))
        self.assertEqual(d["status"], "warn")
        self.assertEqual(d["exit_code"], 0)

    def test_block_unchecked_impl(self):
        s = snap({G_IMPL: ["plan_docs/03-implementation/feature.md"], G_BE: [], G_FE: []},
                 {"plan_docs/03-implementation/feature.md": "- [ ] todo\n- [x] done"})
        d = core.decide(ev(), PROFILE, s)
        self.assertEqual(d["status"], "block")
        self.assertEqual(d["exit_code"], 2)
        self.assertEqual(d["total_unchecked"], 1)

    def test_block_unchecked_backend(self):
        s = snap({G_IMPL: ["plan_docs/03-implementation/feature.md"],
                  G_BE: ["springboot-backend/plan_docs/feature.md"], G_FE: []},
                 {"plan_docs/03-implementation/feature.md": "- [x] ok",
                  "springboot-backend/plan_docs/feature.md": "- [ ] a\n- [ ] b"})
        d = core.decide(ev(), PROFILE, s)
        self.assertEqual(d["status"], "block")
        self.assertEqual(d["total_unchecked"], 2)

    def test_suffix_stripping(self):
        # 실제 04-analyze 산출물 네이밍 (원본 알고리즘과 동일하게 단일 접미사 제거)
        for stem, expected in [
            ("feature_backend_eval", "feature"),
            ("feature-gap", "feature"),
            ("feature_analyze", "feature"),
        ]:
            d = core.decide(ev(f"plan_docs/04-analyze/{stem}.md"), PROFILE,
                            snap({G_IMPL: [], G_BE: [], G_FE: []}, {}))
            self.assertEqual(d["base"], expected, stem)

    def test_exact_priority(self):
        s = snap({G_IMPL: ["plan_docs/03-implementation/feature_extra.md",
                           "plan_docs/03-implementation/feature.md"], G_BE: [], G_FE: []},
                 {"plan_docs/03-implementation/feature.md": "- [x] ok",
                  "plan_docs/03-implementation/feature_extra.md": "- [ ] no"})
        d = core.decide(ev(), PROFILE, s)
        self.assertEqual(d["status"], "ok")  # exact feature.md(checked) 우선, feature_extra 무시

    def test_read_error_tracked(self):
        s = snap({G_IMPL: ["plan_docs/03-implementation/feature.md"], G_BE: [], G_FE: []},
                 {"plan_docs/03-implementation/feature.md": None})  # read 실패
        d = core.decide(ev(), PROFILE, s)
        self.assertTrue(any(e.get("read_error") for e in d["evidence"]))


def run_adapter(runtime, raw, root):
    env_root = "CLAUDE_PROJECT_DIR" if runtime == "claude" else "CODEX_PROJECT_ROOT"
    env = dict(os.environ, **{env_root: root, "SAGE_HOOK_CORE_DIR": HOOKS_DIR, "SAGE_PROFILE": PROFILE_PATH})
    adapter = os.path.join(ADAPTERS, runtime, "pre-phase4-checklist-gate.sh")
    return subprocess.run(["bash", adapter], input=json.dumps(raw), capture_output=True, text=True, env=env)


def setup_tree(root, impl_content):
    d = os.path.join(root, "plan_docs", "03-implementation")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "feature.md"), "w", encoding="utf-8") as f:
        f.write(impl_content)


class TestAdapters(unittest.TestCase):
    def _raw(self, runtime):
        four = "plan_docs/04-analyze/feature_analyze.md"
        if runtime == "claude":
            return {"tool_name": "Write", "tool_input": {"file_path": four}, "session_id": "t"}
        return {"tool_name": "apply_patch", "tool_input": {"command": f"*** Update File: {four}\n+x\n"}, "session_id": "t"}

    def test_block_both_runtimes(self):
        for runtime in ("claude", "codex"):
            with tempfile.TemporaryDirectory() as root:
                setup_tree(root, "- [ ] todo")
                p = run_adapter(runtime, self._raw(runtime), root)
                self.assertEqual(p.returncode, 2, f"{runtime} block exit2")

    def test_ok_both_runtimes(self):
        for runtime in ("claude", "codex"):
            with tempfile.TemporaryDirectory() as root:
                setup_tree(root, "- [x] done")
                p = run_adapter(runtime, self._raw(runtime), root)
                self.assertEqual(p.returncode, 0, f"{runtime} ok exit0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
