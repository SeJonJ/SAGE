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
PROFILE_PATH = os.path.join(HERE, "fixtures", "pre_phase4", "example.profile.json")

sys.path.insert(0, HOOKS_DIR)
import pre_phase4_checklist_gate_core as core  # noqa: E402

with open(PROFILE_PATH, encoding="utf-8") as _f:
    PROFILE = json.load(_f)

G_IMPL = "plan_docs/03-implementation/*.md"
G_BE = "backend/plan_docs/*.md"
G_FE = "frontend/plan_docs/*.md"


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
                  G_BE: ["backend/plan_docs/feature.md"], G_FE: []},
                 {"plan_docs/03-implementation/feature.md": "- [x] ok",
                  "backend/plan_docs/feature.md": "- [ ] a\n- [ ] b"})
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


def run_adapter(runtime, raw, root, profile_path=PROFILE_PATH):
    env_root = "CLAUDE_PROJECT_DIR" if runtime == "claude" else "CODEX_PROJECT_ROOT"
    env = dict(os.environ, **{env_root: root, "SAGE_HOOK_CORE_DIR": HOOKS_DIR,
                             "SAGE_PROFILE": profile_path})
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

    def test_codex_move_into_phase4_triggers_gate(self):
        # apply_patch 이동으로 04 문서가 생겨도 다른 생성 경로와 같은 판정을 받아야 한다.
        four = "plan_docs/04-analyze/feature_analyze.md"
        raw = {"tool_name": "apply_patch", "session_id": "t", "tool_input": {
            "command": f"*** Update File: docs/scratch.md\n*** Move to: {four}\n+x\n"}}
        with tempfile.TemporaryDirectory() as root:
            setup_tree(root, "- [ ] todo")
            self.assertEqual(run_adapter("codex", raw, root).returncode, 2)
        with tempfile.TemporaryDirectory() as root:
            setup_tree(root, "- [x] done")
            self.assertEqual(run_adapter("codex", raw, root).returncode, 0)

    def test_codex_delete_of_phase4_does_not_trigger_gate(self):
        raw = {"tool_name": "apply_patch", "session_id": "t", "tool_input": {
            "command": "*** Delete File: plan_docs/04-analyze/feature_analyze.md\n"}}
        with tempfile.TemporaryDirectory() as root:
            setup_tree(root, "- [ ] todo")
            self.assertEqual(run_adapter("codex", raw, root).returncode, 0)

    def test_block_reason_reaches_host_channel(self):
        # 판정과 문구가 맞아도 채널이 틀리면 사용자는 사유를 못 본다. claude 는 exit 2 의
        # 사유를 stderr 에서 읽고, codex 도 block 은 stderr 다.
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as root:
                setup_tree(root, "- [ ] todo")
                p = run_adapter(runtime, self._raw(runtime), root)
                self.assertEqual(p.returncode, 2)
                self.assertIn("체크리스트 미완료", p.stderr)
                self.assertEqual(p.stdout, "")

    def test_ok_reaches_the_context_channel_on_both_runtimes(self):
        """비차단은 양 런타임 모두 hookSpecificOutput 이어야 host 가 컨텍스트로 읽는다.

        stdout 이 비어 있지 않은지만 보면 평문과 JSON 을 구분하지 못한다 — claude 평문은
        디버그 로그로만 가므로 그 단언은 미도달을 통과시킨다.
        """
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as root:
                setup_tree(root, "- [x] done")
                p = run_adapter(runtime, self._raw(runtime), root)
                self.assertEqual(p.returncode, 0)
                self.assertEqual(p.stderr, "")
                doc = json.loads(p.stdout)              # 평문이면 여기서 실패한다
                self.assertEqual(doc["hookSpecificOutput"]["hookEventName"], "PreToolUse")
                self.assertIn("[GATE", doc["hookSpecificOutput"]["additionalContext"])

    def test_malformed_compiled_profile_blocks_without_traceback(self):
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as root:
                profile_path = os.path.join(root, "broken-profile.json")
                with open(profile_path, "w", encoding="utf-8") as stream:
                    stream.write("{")
                p = run_adapter(runtime, self._raw(runtime), root, profile_path)
                self.assertEqual(p.returncode, 2)
                self.assertIn("profile/snapshot 계약 오류", p.stderr)
                self.assertNotIn("Traceback", p.stderr)

    def test_symlink_escape_match_blocks_both_runtimes(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as root, \
                    tempfile.TemporaryDirectory() as outside:
                with open(os.path.join(outside, "private.md"), "w", encoding="utf-8") as stream:
                    stream.write("- [x] hidden")
                os.symlink(outside, os.path.join(root, "linked"))
                profile_path = os.path.join(root, "profile.json")
                profile = dict(PROFILE)
                profile["checklist_scan_targets"] = [
                    {"label": "outside", "glob": "linked/*.md"},
                ]
                with open(profile_path, "w", encoding="utf-8") as stream:
                    json.dump(profile, stream)
                p = run_adapter(runtime, self._raw(runtime), root, profile_path)
                self.assertEqual(p.returncode, 2)
                self.assertIn("root 밖 symlink", p.stderr)
                self.assertNotIn("Traceback", p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
