#!/usr/bin/env python3
"""pre-implementation-gate 폐루프 검증 (부분추출: 공유 risk-gate core + unresolved 전략슬롯).

검증(Codex Q2 — core 중심):
  1. classify_risk: L0/L1/L2/L3 분류, 내용 escalation, desktop block, declared 상향, case-insensitive
  2. decide: desktop block / L3+no-plan block / L3+전략미선택 BLOCK(safety_degraded) / L3+found ok / L3+notfound warn /
             L2 no-plan warn / L2 plan ok / L1 ok
  3. 전략 후보 보존: claude_grep_first / codex_feature_signal find_l3_review 동작(병합 안 함)
  4. adapter: claude file_path & codex apply_patch → L3 미선택 BLOCK 동일
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
PROFILE_PATH = os.path.join(HERE, "fixtures", "pre_impl_gate", "chatforyou.profile.json")

sys.path.insert(0, HOOKS_DIR)
sys.path.insert(0, os.path.join(HOOKS_DIR, "strategies", "pre_implementation_gate"))
import pre_implementation_gate_core as core  # noqa: E402
import claude_grep_first  # noqa: E402
import codex_feature_signal  # noqa: E402

with open(PROFILE_PATH, encoding="utf-8") as _f:
    PROFILE = json.load(_f)


def ev(path, content="", branch="main", declared=None):
    return {"hook_id": "pre-implementation-gate", "runtime": "test", "branch": branch,
            "declared_max": declared, "changes": [{"path": path, "op": "write", "content": content}]}


class TestClassify(unittest.TestCase):
    def test_levels(self):
        cases = [
            ("docs/x.md", "", "L0"),
            ("nodejs-frontend/static/js/app.js", "", "L1"),
            ("springboot-backend/src/main/java/Foo.java", "", "L2"),
            ("springboot-backend/Kurento/Svc.java", "", "L3"),       # filename 패턴
        ]
        for path, content, exp in cases:
            self.assertEqual(core.classify_risk(ev(path, content), PROFILE)["risk"], exp, path)

    def test_content_escalation(self):
        self.assertEqual(core.classify_risk(ev("nodejs-frontend/static/js/x.js", "addIceCandidate()"), PROFILE)["risk"], "L3")
        self.assertEqual(core.classify_risk(ev("nodejs-frontend/static/js/x.js", "JwtTokenProvider"), PROFILE)["risk"], "L2")

    def test_case_insensitive(self):
        # 소문자 키워드도 잡혀야(canonical=case-insensitive, 더 안전)
        self.assertEqual(core.classify_risk(ev("springboot-backend/src/main/java/F.java", "webrtcendpoint"), PROFILE)["risk"], "L3")
        self.assertEqual(core.classify_risk(ev("x/SDPOFFER_handler.txt", ""), PROFILE)["risk"], "L3")  # filename 대문자

    def test_desktop_block(self):
        self.assertEqual(core.classify_risk(ev("chatforyou-desktop/src/x.js"), PROFILE)["risk"], "DESKTOP_BLOCK")

    def test_declared_escalation(self):
        self.assertEqual(core.classify_risk(ev("nodejs-frontend/static/js/x.js", "", declared="L3"), PROFILE)["risk"], "L3")


def snap(plan=None, review=None):
    return {"plan_files": plan or [], "review_candidates": review or []}


class TestDecide(unittest.TestCase):
    def test_desktop(self):
        d = core.decide(ev("chatforyou-desktop/src/x.js"), PROFILE, snap(), None)
        self.assertEqual((d["status"], d["exit_code"]), ("block", 2))

    def test_l3_no_plan_block(self):
        d = core.decide(ev("a/Kurento.java"), PROFILE, snap(plan=[]), None)
        self.assertEqual(d["message_key"], "block_l3_no_plan")
        self.assertEqual(d["exit_code"], 2)

    def test_l3_strategy_unselected_block(self):
        # plan 있음 → no-plan block 회피, 전략 미선택 → safety BLOCK
        plan = [{"path": "plan_docs/00-base_plan/x.md", "content": "#127 feature"}]
        d = core.decide(ev("a/Kurento.java", branch="bug/127"), PROFILE, snap(plan=plan), None)
        self.assertEqual(d["message_key"], "block_l3_strategy_unresolved")
        self.assertTrue(d["safety_degraded"])
        self.assertEqual(d["exit_code"], 2)

    def test_l3_strategy_found_ok(self):
        plan = [{"path": "plan_docs/00-base_plan/x.md", "content": "#127"}]
        d = core.decide(ev("a/Kurento.java", branch="bug/127"), PROFILE, snap(plan=plan), {"found": True, "path": "r.md"})
        self.assertEqual((d["status"], d["exit_code"]), ("ok", 0))

    def test_l3_strategy_notfound_warn(self):
        plan = [{"path": "plan_docs/00-base_plan/x.md", "content": "#127"}]
        d = core.decide(ev("a/Kurento.java", branch="bug/127"), PROFILE, snap(plan=plan), {"found": False})
        self.assertEqual((d["status"], d["exit_code"]), ("warn", 0))

    def test_l2_plan_gate(self):
        f = "springboot-backend/src/main/java/Foo.java"
        self.assertEqual(core.decide(ev(f), PROFILE, snap(plan=[]), None)["message_key"], "warn_l2_no_plan")
        plan = [{"path": "p.md", "content": "#127"}]
        self.assertEqual(core.decide(ev(f, branch="bug/127"), PROFILE, snap(plan=plan), None)["status"], "ok")

    def test_l1_ok(self):
        self.assertEqual(core.decide(ev("nodejs-frontend/static/js/x.js"), PROFILE, snap(), None)["status"], "ok")


class TestStrategies(unittest.TestCase):
    def test_grep_first(self):
        r = claude_grep_first.find_l3_review({}, snap(review=[{"path": "a.md", "content": "Round 1 review 완료"}]))
        self.assertTrue(r["found"])
        self.assertFalse(claude_grep_first.find_l3_review({}, snap(review=[{"path": "b.md", "content": "무관"}]))["found"])

    def test_feature_signal(self):
        r = codex_feature_signal.find_l3_review(
            {"files": ["recording"]}, snap(review=[{"path": "recording_review.md", "content": "recording 기능 review"}]))
        self.assertTrue(r["found"])


def run_adapter(runtime, raw, root):
    env_root = "CLAUDE_PROJECT_DIR" if runtime == "claude" else "CODEX_PROJECT_ROOT"
    env = dict(os.environ, **{env_root: root, "SAGE_HOOK_CORE_DIR": HOOKS_DIR,
                              "SAGE_PROFILE": PROFILE_PATH, "SAGE_GATE_BRANCH": "main"})
    adapter = os.path.join(ADAPTERS, runtime, "pre-implementation-gate.sh")
    return subprocess.run(["bash", adapter], input=json.dumps(raw), capture_output=True, text=True, env=env)


class TestAdapters(unittest.TestCase):
    def test_l3_block_both(self):
        for runtime, raw in [
            ("claude", {"tool_name": "Write", "tool_input": {"file_path": "a/KurentoSvc.java"}, "session_id": "t"}),
            ("codex", {"tool_name": "apply_patch", "tool_input": {"command": "*** Add File: a/KurentoSvc.java\n+x\n"}, "session_id": "t"}),
        ]:
            with tempfile.TemporaryDirectory() as root:
                p = run_adapter(runtime, raw, root)
                self.assertEqual(p.returncode, 2, f"{runtime} L3 no-plan block")

    def test_l1_pass_both(self):
        for runtime, raw in [
            ("claude", {"tool_name": "Write", "tool_input": {"file_path": "nodejs-frontend/static/js/x.js"}, "session_id": "t"}),
            ("codex", {"tool_name": "apply_patch", "tool_input": {"command": "*** Add File: nodejs-frontend/static/js/x.js\n+x\n"}, "session_id": "t"}),
        ]:
            with tempfile.TemporaryDirectory() as root:
                p = run_adapter(runtime, raw, root)
                self.assertEqual(p.returncode, 0, f"{runtime} L1 pass")


if __name__ == "__main__":
    unittest.main(verbosity=2)
