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
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
ADAPTERS = os.path.join(HOOKS_DIR, "adapters")
PROFILE_PATH = os.path.join(HERE, "fixtures", "stop_compliance", "example.profile.json")
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


def group_count(m, label):
    for g in m["sections"]["activity_summary"]:
        if g["label"] == label:
            return g["count"]
    return None


class TestCore(unittest.TestCase):
    def test_backend_without_plan(self):
        m = core.decide({}, PROFILE, snap([{"type": "backend-main", "file": "backend/src/main/A.java"}]))
        self.assertIn("code_without_plan", keys(m))
        self.assertIn("convention_reminder", keys(m))

    def test_backend_with_plan_no_warn(self):
        m = core.decide({}, PROFILE, snap([
            {"type": "backend-main", "file": "a/A.java"},
            {"type": "plan-doc", "file": "plan_docs/x.md"},
        ]))
        self.assertNotIn("code_without_plan", keys(m))

    def test_l3_pattern_detected(self):
        m = core.decide({}, PROFILE, snap([{"type": "backend-main", "file": "a/PaymentService.java"}]))
        self.assertIn("l3_pattern_detected", keys(m))

    def test_activity_counts(self):
        m = core.decide({}, PROFILE, snap([
            {"type": "backend-main", "file": "a.java"},
            {"type": "backend-main", "file": "a.java"},  # 중복 → set
            {"type": "frontend-js", "file": "b.js"},
        ]))
        self.assertEqual(group_count(m, "Backend src/main"), 1)
        self.assertEqual(group_count(m, "Frontend JS/server"), 1)

    def test_independence_generic_grouping(self):
        # 제약 #2: compliance config 없는 profile(비-ChatForYou) → raw type 별 generic 그룹
        m = core.decide({}, {"risk": {}}, snap([{"type": "python-main", "file": "app/views.py"}]))
        labels = [g["label"] for g in m["sections"]["activity_summary"]]
        self.assertIn("python-main", labels)  # ChatForYou 타입 가정 없이 동작
        self.assertEqual(group_count(m, "python-main"), 1)

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
        # 원본 충실: 5마커 hit>=4 → OK
        self.assertEqual(output_contract_check.check("", False)["severity"], "INFO")  # 코드변경 없음 N/A
        self.assertEqual(output_contract_check.check("", True)["severity"], "INFO")    # transcript 없음 N/A
        full = "작업 요약. risk level L2. impact backend. 변경 파일 목록. 검증 test 통과."
        self.assertEqual(output_contract_check.check(full, True)["severity"], "OK")
        self.assertEqual(output_contract_check.check("요약만 있음", True)["severity"], "WARN")

    def test_knowledge_capture(self):
        # 새 시그니처: check(vault_root, has_code, wiki_log_mtime, earliest_code_ts)
        self.assertEqual(knowledge_capture.check("", True, None, None)["severity"], "INFO")        # vault 없음
        self.assertEqual(knowledge_capture.check("/v", False, None, None)["severity"], "INFO")     # 코드변경 없음
        self.assertEqual(knowledge_capture.check("/v", True, None, 100)["severity"], "WARN")       # wiki/log.md 없음
        self.assertEqual(knowledge_capture.check("/v", True, 200, 100)["severity"], "OK")          # 갱신됨
        self.assertEqual(knowledge_capture.check("/v", True, 50, 100)["severity"], "WARN")         # 미갱신


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
    p = subprocess.run(["bash", adapter], input="", capture_output=True, text=True, env=env)  # codex adapter stdin(transcript) 안전
    report = os.path.join(log_dir, f"compliance-{TODAY}.md")
    return p, (Path(report).read_text(encoding="utf-8") if os.path.exists(report) else "")


class TestAdapters(unittest.TestCase):
    def test_e2e_both(self):
        entries = [{"type": "backend-main", "file": "a/PaymentSvc.java", "branch": "main"}]
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
