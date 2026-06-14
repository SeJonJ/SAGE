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
PROFILE_PATH = os.path.join(HERE, "fixtures", "pre_impl_gate", "example.profile.json")

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
            ("frontend/static/js/app.js", "", "L1"),
            ("backend/src/main/java/Foo.java", "", "L2"),
            ("backend/payment/Svc.java", "", "L3"),       # filename 패턴(고위험=payment)
        ]
        for path, content, exp in cases:
            self.assertEqual(core.classify_risk(ev(path, content), PROFILE)["risk"], exp, path)

    def test_content_escalation(self):
        self.assertEqual(core.classify_risk(ev("frontend/static/js/x.js", "encrypt()"), PROFILE)["risk"], "L3")
        self.assertEqual(core.classify_risk(ev("frontend/static/js/x.js", "Repository"), PROFILE)["risk"], "L2")

    def test_case_insensitive(self):
        # 소문자 키워드도 잡혀야(canonical=case-insensitive, 더 안전)
        self.assertEqual(core.classify_risk(ev("backend/src/main/java/F.java", "privatekey"), PROFILE)["risk"], "L3")
        self.assertEqual(core.classify_risk(ev("x/KEYSTORE_handler.txt", ""), PROFILE)["risk"], "L3")  # filename 대문자

    def test_desktop_block(self):
        self.assertEqual(core.classify_risk(ev("generated/x.js"), PROFILE)["risk"], "DESKTOP_BLOCK")

    def test_declared_escalation(self):
        self.assertEqual(core.classify_risk(ev("frontend/static/js/x.js", "", declared="L3"), PROFILE)["risk"], "L3")

    def test_reason_neutral_no_stack_leak(self):
        # 제약 #2: core 분류 사유는 스택/도메인 중립이어야 한다(엔진 도메인값 0).
        # Tier 2(weatherapp) 회귀 가드: L1/L2 사유에 '백엔드/프론트/java' 등 스택어가 박히면 실패.
        leak = ("백엔드", "프론트", "backend", "frontend", "springboot",
                "nodejs", "java", "js/ui", "kurento", "webrtc", "kotlin")
        l2 = core.classify_risk(ev("backend/src/main/java/Foo.java"), PROFILE)
        l1 = core.classify_risk(ev("frontend/static/js/app.js"), PROFILE)
        self.assertEqual(l2["risk"], "L2")
        self.assertEqual(l1["risk"], "L1")
        for label in (l2["reason"], l1["reason"]):
            for w in leak:
                self.assertNotIn(w, label.lower(), f"스택 누출: {label!r}")
        # 중립 라벨은 발동 규칙(L1/L2)만 기술
        self.assertEqual(l2["reason"], "L2 소스/설정")
        self.assertEqual(l1["reason"], "L1 저위험")


def snap(plan=None, review=None):
    return {"plan_files": plan or [], "review_candidates": review or []}


class TestDecide(unittest.TestCase):
    def test_desktop(self):
        d = core.decide(ev("generated/x.js"), PROFILE, snap(), None)
        self.assertEqual((d["status"], d["exit_code"]), ("block", 2))

    def test_l3_no_plan_block(self):
        d = core.decide(ev("a/payment.java"), PROFILE, snap(plan=[]), None)
        self.assertEqual(d["message_key"], "block_l3_no_plan")
        self.assertEqual(d["exit_code"], 2)

    def test_l3_strategy_unselected_block(self):
        # plan 있음 → no-plan block 회피, 전략 미선택 → safety BLOCK
        plan = [{"path": "plan_docs/00-base_plan/x.md", "content": "#127 feature"}]
        d = core.decide(ev("a/payment.java", branch="bug/127"), PROFILE, snap(plan=plan), None)
        self.assertEqual(d["message_key"], "block_l3_strategy_unresolved")
        self.assertTrue(d["safety_degraded"])
        self.assertEqual(d["exit_code"], 2)

    def test_l3_strategy_found_ok(self):
        plan = [{"path": "plan_docs/00-base_plan/x.md", "content": "#127"}]
        d = core.decide(ev("a/payment.java", branch="bug/127"), PROFILE, snap(plan=plan), {"found": True, "path": "r.md"})
        self.assertEqual((d["status"], d["exit_code"]), ("ok", 0))

    def test_l3_strategy_notfound_warn(self):
        plan = [{"path": "plan_docs/00-base_plan/x.md", "content": "#127"}]
        d = core.decide(ev("a/payment.java", branch="bug/127"), PROFILE, snap(plan=plan), {"found": False})
        self.assertEqual((d["status"], d["exit_code"]), ("warn", 0))

    def test_l2_plan_gate(self):
        f = "backend/src/main/java/Foo.java"
        self.assertEqual(core.decide(ev(f), PROFILE, snap(plan=[]), None)["message_key"], "warn_l2_no_plan")
        plan = [{"path": "p.md", "content": "#127"}]
        self.assertEqual(core.decide(ev(f, branch="bug/127"), PROFILE, snap(plan=plan), None)["status"], "ok")

    def test_plan_fallback_7day(self):
        # audit P1: ticket 미매칭 시 7일 이내(recent) plan 만 fallback 인정
        f = "backend/src/main/java/Foo.java"
        recent_plan = [{"path": "r.md", "content": "무관", "recent": True}]
        old_plan = [{"path": "o.md", "content": "무관", "recent": False}]
        # branch 에 ticket 없음 → fallback. recent=True → plan 인정(ok)
        self.assertEqual(core.decide(ev(f, branch="main"), PROFILE, snap(plan=recent_plan), None)["status"], "ok")
        # recent=False(오래된 plan) → plan 미인정 → warn_l2_no_plan
        self.assertEqual(core.decide(ev(f, branch="main"), PROFILE, snap(plan=old_plan), None)["message_key"], "warn_l2_no_plan")

    def test_l1_ok(self):
        self.assertEqual(core.decide(ev("frontend/static/js/x.js"), PROFILE, snap(), None)["status"], "ok")


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
            ("claude", {"tool_name": "Write", "tool_input": {"file_path": "a/payment.java"}, "session_id": "t"}),
            ("codex", {"tool_name": "apply_patch", "tool_input": {"command": "*** Add File: a/payment.java\n+x\n"}, "session_id": "t"}),
        ]:
            with tempfile.TemporaryDirectory() as root:
                p = run_adapter(runtime, raw, root)
                self.assertEqual(p.returncode, 2, f"{runtime} L3 no-plan block")

    def test_l1_pass_both(self):
        for runtime, raw in [
            ("claude", {"tool_name": "Write", "tool_input": {"file_path": "frontend/static/js/x.js"}, "session_id": "t"}),
            ("codex", {"tool_name": "apply_patch", "tool_input": {"command": "*** Add File: frontend/static/js/x.js\n+x\n"}, "session_id": "t"}),
        ]:
            with tempfile.TemporaryDirectory() as root:
                p = run_adapter(runtime, raw, root)
                self.assertEqual(p.returncode, 0, f"{runtime} L1 pass")


if __name__ == "__main__":
    unittest.main(verbosity=2)
