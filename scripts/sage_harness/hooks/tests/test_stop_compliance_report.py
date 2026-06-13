#!/usr/bin/env python3
"""stop-compliance-report 폐루프 검증 (부분추출: 공유 집계 core + policy_delta 보존).

검증:
  1. core decide: 활동요약 집계 / gate 3종(backend_without_plan, l3_pattern_detected, backend_convention_reminder)
  2. render_markdown: 섹션 구조
  3. 빈/없는 로그 처리
  4. adapter e2e: claude/codex JSONL → 동일 report_model → compliance-{today}.md 생성, exit 0
  5. policy_delta 보존(미병합): output_contract_check / knowledge_capture 동작
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
PROFILE_PATH = os.path.join(HERE, "fixtures", "stop_compliance", "chatforyou.profile.json")
TODAY = "2026-06-13"

sys.path.insert(0, HOOKS_DIR)
sys.path.insert(0, os.path.join(HOOKS_DIR, "policies"))
import stop_compliance_report_core as core  # noqa: E402
import output_contract_check  # noqa: E402
import knowledge_capture  # noqa: E402

with open(PROFILE_PATH, encoding="utf-8") as _f:
    PROFILE = json.load(_f)


def snap(entries, branch="main"):
    return {"entries": entries, "today": TODAY, "branch": branch, "runtime": "test"}


def keys(model):
    return {i["key"] for i in model["sections"]["gate_compliance"]["issues"]}


class TestCore(unittest.TestCase):
    def test_backend_without_plan(self):
        m = core.decide({}, PROFILE, snap([{"type": "backend-main", "file": "springboot-backend/src/main/java/A.java"}]))
        self.assertIn("backend_without_plan", keys(m))
        self.assertIn("backend_convention_reminder", keys(m))

    def test_backend_with_plan_no_warn(self):
        m = core.decide({}, PROFILE, snap([
            {"type": "backend-main", "file": "a/A.java"},
            {"type": "plan-doc", "file": "plan_docs/x.md"},
        ]))
        self.assertNotIn("backend_without_plan", keys(m))

    def test_l3_pattern_detected(self):
        m = core.decide({}, PROFILE, snap([{"type": "backend-main", "file": "a/KurentoService.java"}]))
        self.assertIn("l3_pattern_detected", keys(m))

    def test_activity_counts(self):
        m = core.decide({}, PROFILE, snap([
            {"type": "backend-main", "file": "a.java"},
            {"type": "backend-main", "file": "a.java"},  # 중복 → set
            {"type": "frontend-js", "file": "b.js"},
        ]))
        a = m["sections"]["activity_summary"]
        self.assertEqual(a["backend_main"]["count"], 1)
        self.assertEqual(a["frontend"]["count"], 1)

    def test_empty(self):
        m = core.decide({}, PROFILE, snap([]))
        self.assertEqual(m["sections"]["gate_compliance"]["issues"], [])
        self.assertEqual(m["exit_code"], 0)

    def test_render_markdown(self):
        m = core.decide({}, PROFILE, snap([{"type": "backend-main", "file": "a/Kurento.java"}]))
        md = core.render_markdown(m)
        self.assertIn("# Compliance Report — 2026-06-13", md)
        self.assertIn("## Activity Summary", md)
        self.assertIn("## Gate Compliance", md)
        self.assertIn("## Modified Files", md)


class TestPolicyModulesPreserved(unittest.TestCase):
    def test_output_contract(self):
        self.assertEqual(output_contract_check.check("", False)["text"][:3], "N/A")
        full = "요약 변경 검증 리스크 다음"
        self.assertEqual(output_contract_check.check(full, True)["severity"], "OK")
        self.assertEqual(output_contract_check.check("요약만", True)["severity"], "WARN")

    def test_knowledge_capture(self):
        self.assertIn("N/A", knowledge_capture.check("", True, False)["text"])
        self.assertEqual(knowledge_capture.check("/vault", True, True)["severity"], "OK")
        self.assertEqual(knowledge_capture.check("/vault", True, False)["severity"], "WARN")


def run_adapter(runtime, root, entries):
    sub = ".claude" if runtime == "claude" else ".codex"
    log_dir = os.path.join(root, sub, "logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, f"session-{TODAY}.jsonl"), "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    env_root = "CLAUDE_PROJECT_DIR" if runtime == "claude" else "CODEX_PROJECT_ROOT"
    env = dict(os.environ, **{env_root: root, "SAGE_HOOK_CORE_DIR": HOOKS_DIR,
                              "SAGE_PROFILE": PROFILE_PATH, "SAGE_TODAY": TODAY, "SAGE_GATE_BRANCH": "main"})
    adapter = os.path.join(ADAPTERS, runtime, "stop-compliance-report.sh")
    p = subprocess.run(["bash", adapter], capture_output=True, text=True, env=env)
    report = os.path.join(log_dir, f"compliance-{TODAY}.md")
    return p, (open(report, encoding="utf-8").read() if os.path.exists(report) else "")


class TestAdapters(unittest.TestCase):
    def test_e2e_both(self):
        entries = [{"type": "backend-main", "file": "a/KurentoSvc.java", "branch": "main"}]
        for runtime in ("claude", "codex"):
            with tempfile.TemporaryDirectory() as root:
                p, report = run_adapter(runtime, root, entries)
                self.assertEqual(p.returncode, 0, runtime)
                self.assertIn("# Compliance Report", report, runtime)
                self.assertIn("L3 패턴 파일 수정 감지", report, runtime)

    def test_no_log_skips(self):
        # 로그 파일 없으면 리포트 생략(exit 0)
        for runtime in ("claude", "codex"):
            with tempfile.TemporaryDirectory() as root:
                env_root = "CLAUDE_PROJECT_DIR" if runtime == "claude" else "CODEX_PROJECT_ROOT"
                env = dict(os.environ, **{env_root: root, "SAGE_HOOK_CORE_DIR": HOOKS_DIR,
                                          "SAGE_PROFILE": PROFILE_PATH, "SAGE_TODAY": TODAY})
                adapter = os.path.join(ADAPTERS, runtime, "stop-compliance-report.sh")
                p = subprocess.run(["bash", adapter], capture_output=True, text=True, env=env)
                self.assertEqual(p.returncode, 0, runtime)


if __name__ == "__main__":
    unittest.main(verbosity=2)
