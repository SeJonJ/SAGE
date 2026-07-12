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
        # 제약 #2: compliance config 없는 profile(특정 프로젝트 가정 없음) → raw type 별 generic 그룹
        m = core.decide({}, {"risk": {}}, snap([{"type": "python-main", "file": "app/views.py"}]))
        labels = [g["label"] for g in m["sections"]["activity_summary"]]
        self.assertIn("python-main", labels)  # 특정 프로젝트 타입 가정 없이 동작
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
        # 5마커 hit>=4 → OK (중립 기본값에서도 동일 — full 은 impact/검증 test 로 매칭)
        self.assertEqual(output_contract_check.check("", False)["severity"], "INFO")  # 코드변경 없음 N/A
        self.assertEqual(output_contract_check.check("", True)["severity"], "INFO")    # transcript 없음 N/A
        full = "작업 요약. risk level L2. impact backend. 변경 파일 목록. 검증 test 통과."
        self.assertEqual(output_contract_check.check(full, True)["severity"], "OK")
        self.assertEqual(output_contract_check.check("요약만 있음", True)["severity"], "WARN")

    def test_output_contract_markers_neutral_and_injectable(self):
        # EH-2(제약#2): 기본 마커에 스택/빌드툴 토큰 0
        flat = [t for v in output_contract_check._DEFAULT_MARKERS.values() for t in v]
        for stack_tok in ("backend", "frontend", "desktop", "gradlew"):
            self.assertNotIn(stack_tok, flat, f"중립 기본값에 스택토큰 '{stack_tok}' 잔존")
        # profile.output_contract.markers 주입 시 그 마커 사용(임계 = 마커수-1 일반화)
        custom = {"A": ["alpha"], "B": ["beta"], "C": ["gamma"]}
        self.assertEqual(output_contract_check.check("alpha beta only", True, custom)["severity"], "OK")   # 2/3 ≥ max(1,2)
        self.assertEqual(output_contract_check.check("alpha only", True, custom)["severity"], "WARN")      # 1/3 < 2
        # 빈/None markers → 중립 기본값 폴백
        self.assertEqual(output_contract_check.check("alpha", True, {})["severity"],
                         output_contract_check.check("alpha", True, None)["severity"])

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

    def test_claude_wires_knowledge_capture(self):
        # F7: claude adapter 도 knowledge_capture 를 policy_results 에 주입(이전엔 codex 만 = 갭).
        # output_contract 는 claude 에 미적용(Codex-only 설계 + 마커 비독립) → 비대칭도 가드.
        with tempfile.TemporaryDirectory() as root:
            vault = os.path.join(root, "vault")
            os.makedirs(os.path.join(vault, "wiki"), exist_ok=True)
            Path(os.path.join(vault, "wiki", "log.md")).write_text("captured\n", encoding="utf-8")  # 코드변경 이후 mtime → OK
            prof = os.path.join(root, "profile.json")
            with open(prof, "w", encoding="utf-8") as f:
                json.dump({"file_type_map": [{"glob": "*.src", "type": "src"}],
                           "compliance": {"plan_gate_code_types": ["src"]},
                           "knowledge_capture": {"vault_path": vault}}, f)
            log_dir = os.path.join(root, ".claude", "logs")
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, f"session-{TODAY}.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"ts": f"{TODAY}T00:00:00Z", "tool": "Write",
                                    "file": "a.src", "type": "src", "branch": "main"}) + "\n")
            env = dict(os.environ, CLAUDE_PROJECT_DIR=root, SAGE_HOOK_CORE_DIR=HOOKS_DIR,
                       SAGE_PROFILE=prof, SAGE_TODAY=TODAY, SAGE_GATE_BRANCH="main")
            adapter = os.path.join(ADAPTERS, "claude", "stop-compliance-report.sh")
            p = subprocess.run(["bash", adapter], input="", capture_output=True, text=True, env=env)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertEqual(p.returncode, 0)
            self.assertIn("Policy Results", report)
            self.assertIn("knowledge_capture", report)
            self.assertNotIn("output_contract", report)  # claude 비대칭 가드


class TestRetroGateWiring(unittest.TestCase):
    """9-C v1: Stop 훅이 retro --check 미실행을 실제로 감지·(최대 1회)block 하는지 e2e."""

    RUN_ID = "rl-test123"

    def _setup(self, root, mode="enforce", has_loop_run=True, session_matches=True, log_06=True,
               glob06="plan_docs/06-*.md", doc06="plan_docs/06-cycle.md", glob05="plan_docs/05-*.md",
               log_05=True, doc05="plan_docs/05-cycle.md", retro_note=True, vault_path=None,
               run_id=None):
        run_id = run_id or self.RUN_ID
        if vault_path is None:   # 게이트 활성엔 usable(디렉토리) vault 가 필요(isdir) — 실제 디렉토리 생성
            vault_path = os.path.join(root, "vault")
            os.makedirs(vault_path, exist_ok=True)
        prof = {"pdca": {"phases": [{"id": "05", "glob": glob05},
                                     {"id": "06", "glob": glob06}],
                         "retro": {"report_gate_enforce": mode}},
                # retro_note 켜져야 게이트가 유효(노트가 생성돼야 --check 가능). off 는 별도 테스트.
                # 게이트 활성은 retro CLI 와 동일: retro_note is True + vault_path 실존(codex 7R P1).
                "knowledge_capture": {"retro_note": retro_note, "vault_path": vault_path}}
        prof_path = os.path.join(root, "profile.json")
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump(prof, f)

        os.makedirs(os.path.join(root, "plan_docs"), exist_ok=True)
        # 05 는 retro 게이트에서 더 이상 스캔하지 않는다(06 이 Loop-Run 을 자가선언 — codex W1). 05 는
        # 존재해도 결과에 무영향(review_loop 게이트 대상). run_id 는 06 이 스스로 기록한다.
        abs05 = os.path.join(root, doc05)
        os.makedirs(os.path.dirname(abs05), exist_ok=True)
        with open(abs05, "w", encoding="utf-8") as f:
            f.write("Phase 05 리뷰\n")

        sess = "sess-1" if session_matches else "sess-OTHER"
        log_dir = os.path.join(root, ".claude", "logs")
        os.makedirs(log_dir, exist_ok=True)
        entries = []
        if log_05:
            entries.append({"ts": f"{TODAY}T00:00:00Z", "tool": "Write", "file": doc05,
                            "type": "plan-doc", "branch": "main", "session": sess})
        if log_06:
            abs06 = os.path.join(root, doc06)
            os.makedirs(os.path.dirname(abs06), exist_ok=True)
            marker = f"Loop-Run: {run_id}\n" if has_loop_run else "마커 없음\n"
            with open(abs06, "w", encoding="utf-8") as f:
                f.write("완료 보고\n" + marker)
            entries.append({"ts": f"{TODAY}T00:00:01Z", "tool": "Write", "file": doc06,
                            "type": "plan-doc", "branch": "main", "session": sess})
        with open(os.path.join(log_dir, f"session-{TODAY}.jsonl"), "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return prof_path, log_dir

    def _run(self, root, prof_path, stop_hook_active=False, baseline=True, session_id="sess-1"):
        # 실사용에선 SessionStart 가 Stop 前 항상 발화한다 → 기본으로 baseline 을 확보(status ok)해 degraded
        # 정책이 오작동하지 않게 한다. degraded/absent 를 테스트하는 케이스만 baseline=False 로 옵트아웃.
        if baseline:
            self._run_session_start(root, prof_path, session_id=session_id)
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root, SAGE_HOOK_CORE_DIR=HOOKS_DIR,
                   SAGE_PROFILE=prof_path, SAGE_TODAY=TODAY, SAGE_GATE_BRANCH="main")
        adapter = os.path.join(ADAPTERS, "claude", "stop-compliance-report.sh")
        stdin = json.dumps({"session_id": session_id, "stop_hook_active": stop_hook_active})
        return subprocess.run(["bash", adapter], input=stdin, capture_output=True, text=True, env=env)

    def test_enforce_first_attempt_blocks_when_unchecked(self):
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2)
            self.assertIn(self.RUN_ID, p.stdout)

    def test_enforce_retry_never_blocks_twice(self):
        # 플랫폼 제약(stop_hook_active): 세션당 block 은 정확히 1회.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            p = self._run(root, prof_path, stop_hook_active=True)
            self.assertEqual(p.returncode, 0)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("retro_gate", report)

    def test_enforce_passes_when_check_recorded(self):
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))
            import retro_audit
            retro_audit.record_check(root, self.RUN_ID, "wiki/note.md", "본문")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("[OK] retro_gate", report)

    def test_advisory_never_blocks(self):
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="advisory")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("[WARN] retro_gate", report)

    def test_off_mode_never_blocks(self):
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="off")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("[INFO] retro_gate", report)

    def test_enforce_with_retro_note_off_is_inactive(self):
        # codex 구현리뷰 6R P1: retro_note off 면 노트가 안 만들어져 --check 불가 → enforce 라도 게이트
        # 무동작(sage-team 이 vault off 면 retro skip 하라 안내하는 정상 흐름과 충돌 방지).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", retro_note=False)
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("[INFO] retro_gate", report)
            self.assertIn("retro_note off", report)
            self.assertEqual([], [r for r in self._audit_records(root) if r["event"] == "retro_check_missing"])

    def test_no_06_this_session_does_not_block(self):
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_06=False)
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0)

    def test_06_from_other_session_does_not_block(self):
        # 로그에 06 이 있어도 이번 세션(session_id) 것이 아니면 무시 — 그날 전체가 아니라 세션 스코프.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", session_matches=False)
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0)

    def test_no_loop_run_marker_binding_impossible_blocks(self):
        # 06 이 이번 세션에 쓰였는데 Loop-Run 을 자기선언하지 않아 run_id 특정 불가 = 결속 불가.
        # 조용한 skip 은 게이트 우회이므로 enforce 에서 BLOCK(외부 보완 피드백 Item 2).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", has_loop_run=False)
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)
            self.assertIn("결속 불가", p.stdout)

    def test_05_content_is_ignored_gate_reads_only_06(self):
        # codex W1: 게이트는 06 자기선언만 읽는다 — 05 문서의 Loop-Run(rl-different)은 무관하다.
        # 06 이 rl-test123 을 선언했으니 그 run 에만 결속/기록되고 rl-different 는 절대 새지 않는다.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            with open(os.path.join(root, "plan_docs", "05-other.md"), "w", encoding="utf-8") as f:
                f.write("Loop-Run: rl-different\n")
            log_file = os.path.join(log_dir, f"session-{TODAY}.jsonl")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": f"{TODAY}T00:00:00Z", "tool": "Write", "file": "plan_docs/05-other.md",
                                    "type": "plan-doc", "branch": "main", "session": "sess-1"}) + "\n")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # 06 이 선언한 rl-test123 미확인 → BLOCK
            self.assertIn(self.RUN_ID, p.stdout)
            self.assertNotIn("rl-different", p.stdout)
            missing_ids = {r["run_id"] for r in self._audit_records(root) if r["event"] == "retro_check_missing"}
            self.assertEqual({self.RUN_ID}, missing_ids)   # 미완료도 05 의 rl-different 아닌 06 의 rl-test123

    def test_selfdeclared_06_ignores_old_same_basename_05(self):
        # codex W1 P1: 과거/타 디렉토리의 동명 05(rl-old, 확인됨)가 이번 06 에 오결속돼 false OK 되면 안 된다.
        # 05 를 stem 으로 스캔하던 옛 설계는 archive/05-cycle 의 rl-old 를 채택해 통과시켰다. 이제 06 만
        # 읽으므로 이번 06 이 사이클 미선언이면 결속 불가로 BLOCK — rl-old 는 완전히 무관.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(
                root, mode="enforce", has_loop_run=False,
                glob05="plan_docs/**/05-cycle.md", doc05="plan_docs/archive/05-cycle.md",
                glob06="plan_docs/06-report/**/*.md", doc06="plan_docs/06-report/cycle.md")
            with open(os.path.join(root, "plan_docs", "archive", "05-cycle.md"), "w", encoding="utf-8") as f:
                f.write("Loop-Run: rl-old\n")
            sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))
            import retro_audit
            retro_audit.record_check(root, "rl-old", "wiki/old.md", "본문")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # 옛 설계였다면 rl-old 로 오통과(exit 0)
            self.assertIn("결속 불가", p.stdout)
            self.assertNotIn("rl-old", p.stdout)

    def _run_codex_stop(self, root, prof_path, stop_hook_active=False):
        log_dir = os.path.join(root, ".codex", "logs")
        os.makedirs(log_dir, exist_ok=True)
        claude_log = os.path.join(root, ".claude", "logs", f"session-{TODAY}.jsonl")
        codex_log = os.path.join(log_dir, f"session-{TODAY}.jsonl")
        if os.path.exists(claude_log):
            os.rename(claude_log, codex_log)
        env = dict(os.environ, CODEX_PROJECT_ROOT=root, SAGE_HOOK_CORE_DIR=HOOKS_DIR,
                   SAGE_PROFILE=prof_path, SAGE_TODAY=TODAY, SAGE_GATE_BRANCH="main")
        start_adapter = os.path.join(ADAPTERS, "codex", "session-start-snapshot.sh")
        start = subprocess.run(["bash", start_adapter], input=json.dumps({"session_id": "sess-1"}),
                               capture_output=True, text=True, env=env)
        self.assertEqual(0, start.returncode, start.stderr)
        adapter = os.path.join(ADAPTERS, "codex", "stop-compliance-report.sh")
        stdin = json.dumps({"session_id": "sess-1", "stop_hook_active": stop_hook_active})
        result = subprocess.run(["bash", adapter], input=stdin, capture_output=True, text=True, env=env)
        return result, log_dir

    def test_codex_enforce_emits_block_decision(self):
        # Codex Stop 차단 wire: exit 0 + stdout 단일 JSON decision:block. exit 2는 Claude 전용 계약이다.
        with tempfile.TemporaryDirectory() as root:
            prof_path, _ = self._setup(root, mode="enforce")
            p, log_dir = self._run_codex_stop(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0, p.stderr)
            wire = json.loads(p.stdout)
            self.assertEqual("block", wire["decision"])
            self.assertIn(self.RUN_ID, wire["reason"])
            self.assertIn("compliance-", wire["reason"])
            self.assertNotIn("hookSpecificOutput", wire)   # 결합하면 Codex가 hook failure로 처리
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("[BLOCK] retro_gate", report)

    def test_codex_enforce_retry_is_silent_pass(self):
        # decision:block 뒤 Codex 재호출은 stop_hook_active=true. Stop 통과 wire는 무출력 exit 0이어야 한다.
        with tempfile.TemporaryDirectory() as root:
            prof_path, _ = self._setup(root, mode="enforce")
            p, log_dir = self._run_codex_stop(root, prof_path, stop_hook_active=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual("", p.stdout)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("[WARN] retro_gate", report)

    def test_codex_advisory_is_silent_pass(self):
        with tempfile.TemporaryDirectory() as root:
            prof_path, _ = self._setup(root, mode="advisory")
            p, log_dir = self._run_codex_stop(root, prof_path)
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertEqual("", p.stdout)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("[WARN] retro_gate", report)

    def test_codex_checked_run_is_silent_pass(self):
        with tempfile.TemporaryDirectory() as root:
            prof_path, _ = self._setup(root, mode="enforce")
            sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))
            import retro_audit
            retro_audit.record_check(root, self.RUN_ID, "wiki/note.md", "본문")
            p, log_dir = self._run_codex_stop(root, prof_path)
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertEqual("", p.stdout)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("[OK] retro_gate", report)

    def test_resumed_06_self_binds_across_sessions(self):
        # 재개 가능 PDCA(외부 보완 피드백 Item 2): 05 는 이전 세션, 06 만 이번 세션에 쓰였다. 06 이 자기선언한
        # Loop-Run 으로 결속하므로 05 세션 여부와 무관하게 미확인 BLOCK — 05 를 세션 로그에서 찾을 필요가 없다.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_05=False)   # 05 는 이전 세션(로그엔 없음)
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # 06 자기선언 결속 → 미확인 BLOCK
            self.assertIn(self.RUN_ID, p.stdout)
            missing_ids = {r["run_id"] for r in self._audit_records(root) if r["event"] == "retro_check_missing"}
            self.assertEqual({self.RUN_ID}, missing_ids)

    def test_resumed_06_self_binds_and_passes_when_checked(self):
        # 재개 회귀: 이전 세션 05 + 이번 세션 06(자기선언) + 정상 check 기록 → PASS.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_05=False)
            sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))
            import retro_audit
            retro_audit.record_check(root, self.RUN_ID, "wiki/note.md", "본문")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0, p.stdout)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("[OK] retro_gate", report)

    def test_standard_recursive_glob_06_is_detected(self):
        # codex 구현리뷰 P0(teeth): 표준 `plan_docs/06-report/**/*.md` 가 06 을 직속 자식으로 두면
        # fnmatch 로는 영원히 매치 안 돼 게이트가 무동작. glob.glob 은 ** 제로디렉토리를 올바로 매치.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(
                root, mode="enforce", glob06="plan_docs/06-report/**/*.md",
                doc06="plan_docs/06-report/cycle.md")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # fnmatch 였다면 0(무동작)

    def _add_second_06(self, root, log_dir, name, body):
        # 이번 세션에 두 번째 06 문서를 추가(다중 06 시나리오용).
        with open(os.path.join(root, "plan_docs", name), "w", encoding="utf-8") as f:
            f.write(body)
        with open(os.path.join(log_dir, f"session-{TODAY}.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": f"{TODAY}T00:00:02Z", "tool": "Write", "file": f"plan_docs/{name}",
                                "type": "plan-doc", "branch": "main", "session": "sess-1"}) + "\n")

    def test_multi_06_undeclared_not_masked_by_checked_06(self):
        # codex W1 P1(teeth): 한 세션 다중 06 에서 확인된 06 이 미선언 06 을 가리면 안 된다. 옛 집계 설계는
        # run_id 집합이 {rl-test123} 하나라 resolved·확인됨으로 통과시켜, 06-beta 의 미선언을 삼켰다.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")   # 06-cycle → rl-test123
            sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))
            import retro_audit
            retro_audit.record_check(root, self.RUN_ID, "wiki/note.md", "본문")
            self._add_second_06(root, log_dir, "06-beta.md", "완료 보고\n마커 없음\n")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # 집계였다면 exit 0(가림)
            self.assertIn("결속 불가", p.stdout)

    def test_multi_06_all_declared_and_checked_passes(self):
        # codex W1 P1(teeth): 정상 다중 사이클(각 06 유일 선언·확인)을 모호로 오판해 차단하면 안 된다.
        # 옛 집계 설계는 run_id 가 둘({rl-test123, rl-beta})이라 ambiguous 로 정상 흐름을 막았다.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")   # 06-cycle → rl-test123
            sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))
            import retro_audit
            retro_audit.record_check(root, self.RUN_ID, "wiki/a.md", "본문")
            retro_audit.record_check(root, "rl-beta", "wiki/b.md", "본문")
            self._add_second_06(root, log_dir, "06-beta.md", "완료 보고\nLoop-Run: rl-beta\n")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0, p.stdout)   # 집계였다면 모호로 오차단(exit 2)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("[OK] retro_gate", report)

    def test_stop_hook_active_string_false_still_blocks(self):
        # codex 구현리뷰 P1(teeth): bool("false")==True 라 문자열 "false" 를 재시도로 오인하면
        # 첫 block 이 사라진다. "false" 는 not-active 로 봐 첫 시도의 teeth 를 지켜야 한다.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            p = self._run(root, prof_path, stop_hook_active="false")
            self.assertEqual(p.returncode, 2, p.stdout)

    def test_stop_hook_active_string_true_does_not_block(self):
        # 재시도는 플랫폼이 true 를 보낼 때 성립 — 문자열 "true" 도 active 로 봐 루프-안전 유지.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            p = self._run(root, prof_path, stop_hook_active="true")
            self.assertEqual(p.returncode, 0)

    def test_two_conflicting_markers_in_one_06_is_ambiguous_blocks(self):
        # 한 06 문서에 서로 다른 Loop-Run 이 둘이면 사이클 모호(ambiguous) → 잘못 결속하지 않되 조용히
        # skip 하지도 않는다. 06 이 이번 세션에 쓰였으니 결속 불가로 enforce BLOCK.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            with open(os.path.join(root, "plan_docs", "06-cycle.md"), "w", encoding="utf-8") as f:
                f.write("완료 보고\nLoop-Run: rl-aaa\n임의 본문\nLoop-Run: rl-bbb\n")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)
            self.assertIn("모호", p.stdout)

    def _audit_records(self, root):
        path = os.path.join(root, ".sage", "retro_audit.jsonl")
        if not os.path.isfile(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def test_unchecked_stop_records_missing_in_audit(self):
        # codex 구현리뷰 2R P1(teeth): 미완료 종료가 retro_audit.jsonl 에 영구 기록돼야 한다(유저 스코프).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            self._run(root, prof_path, stop_hook_active=False)
            recs = self._audit_records(root)
            self.assertTrue(any(r["event"] == "retro_check_missing" and r["run_id"] == self.RUN_ID for r in recs))

    def test_missing_record_not_duplicated_across_stops(self):
        # 여러 번 Stop 해도 상태변화 시에만 기록 — 파일이 불어나지 않는다.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="advisory")   # advisory 도 미완료면 기록
            self._run(root, prof_path, stop_hook_active=False)
            self._run(root, prof_path, stop_hook_active=False)
            missing = [r for r in self._audit_records(root) if r["event"] == "retro_check_missing"]
            self.assertEqual(1, len(missing))

    def test_checked_stop_records_no_missing(self):
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))
            import retro_audit
            retro_audit.record_check(root, self.RUN_ID, "wiki/note.md", "본문")
            self._run(root, prof_path, stop_hook_active=False)
            missing = [r for r in self._audit_records(root) if r["event"] == "retro_check_missing"]
            self.assertEqual([], missing)

    def test_dot_prefixed_log_path_still_matches_06(self):
        # codex 구현리뷰 2R P1(teeth): 로그 경로가 `./plan_docs/...` 로 저장돼도 glob relpath 와
        # 정규화돼 교집합이 성립해야 한다(한쪽만 정규화하면 조용히 공집합→무동작).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_06=False)   # 05 는 세션로그에 있음
            os.makedirs(os.path.join(root, "plan_docs"), exist_ok=True)
            with open(os.path.join(root, "plan_docs", "06-cycle.md"), "w", encoding="utf-8") as f:
                f.write(f"완료\nLoop-Run: {self.RUN_ID}\n")
            # 06 을 dot-prefix 경로로 로그에 추가(05 로그는 _setup 이 이미 남김).
            with open(os.path.join(log_dir, f"session-{TODAY}.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": f"{TODAY}T00:00:01Z", "tool": "Write",
                                    "file": "./plan_docs/06-cycle.md", "type": "plan-doc",
                                    "branch": "main", "session": "sess-1"}) + "\n")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # 정규화 안 하면 공집합→exit 0

    def test_audit_write_failure_surfaced_not_silent(self):
        # codex 구현리뷰 3R P1(teeth): 감사파일이 디렉토리라 기록 불가면, 리포트에 유실을 명시해야 한다
        # (조용한 no-op 금지 — 재차단은 안 하되 영구기록·doctor 가시성 상실을 감춰선 안 됨).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="advisory")   # advisory: exit 0 이라 write 만 관찰
            os.makedirs(os.path.join(root, ".sage", "retro_audit.jsonl"), exist_ok=True)  # 파일 자리에 디렉토리
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("retro_audit 기록 실패", report)

    def test_gate_runs_when_session_log_is_different_date_file(self):
        # codex 7R P0(teeth): 로거는 UTC 날짜로 session-*.jsonl 을 쓰고 Stop 은 로컬 날짜 파일을 연다.
        # 양수 오프셋(KST) 자정 경계에서 오늘자(로컬) 파일이 없어도, 이번 세션이 다른 날짜 파일에 있으면
        # 게이트가 돌아야 한다 — 오늘자 파일만 보고 早期 return 하면 enforce 가 조용히 무동작한다.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            os.rename(os.path.join(log_dir, f"session-{TODAY}.jsonl"),
                      os.path.join(log_dir, "session-2020-01-01.jsonl"))   # 로거가 다른 날짜로 씀
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # 세션 스코프 감지→block(오늘자 파일 부재 무관)

    def test_enforce_retro_note_true_but_vault_empty_is_inactive(self):
        # codex 7R P1(teeth): retro_note=true 라도 vault_path 가 비면 retro CLI 는 노트를 안 써(--check
        # 불가) → 게이트가 통과 불가능한 걸 강제하면 안 된다. bool(retro_note) 만 보던 오판을 교정.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", vault_path="")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0, p.stdout)
            self.assertEqual([], [r for r in self._audit_records(root) if r["event"] == "retro_check_missing"])

    def test_enforce_retro_note_string_false_is_inactive(self):
        # codex 7R P1(teeth): retro_note 가 문자열 "false" 면 CLI 는 `is True` 로 비활성인데 bool("false")
        # 은 truthy 라 게이트만 활성으로 오판해 정상 흐름을 막았다. `is True` 로 CLI 와 일치시킴.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", retro_note="false")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0, p.stdout)

    def test_enforce_vault_path_is_regular_file_is_inactive(self):
        # codex W1 R2 P1(teeth): vault_path 가 비어있지 않아도 일반 파일이면 노트 디렉토리를 못 만들어
        # --check 불가 → 게이트가 통과 불가능한 걸 강제하면 안 된다. isdir 로 usable vault 만 활성.
        with tempfile.TemporaryDirectory() as root:
            vfile = os.path.join(root, "not_a_dir")
            with open(vfile, "w", encoding="utf-8") as f:
                f.write("i am a file\n")
            prof_path, log_dir = self._setup(root, mode="enforce", vault_path=vfile)
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0, p.stdout)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("[INFO] retro_gate", report)
            self.assertEqual([], [r for r in self._audit_records(root) if r["event"] == "retro_check_missing"])

    def test_multi_06_all_unchecked_records_every_missing_run(self):
        # codex W1 R2 P1(teeth): 다중 06 이 각기 미확인이면 대표 하나만 기록하던 옛 코드는 나머지를
        # 재시도 dedup 뒤 doctor 가시성에서 잃었다. 미확인 run 전부 record_missing 되어야 한다.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")   # 06-cycle → rl-test123(미확인)
            self._add_second_06(root, log_dir, "06-beta.md", "완료 보고\nLoop-Run: rl-beta\n")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)
            missing = {r["run_id"] for r in self._audit_records(root) if r["event"] == "retro_check_missing"}
            self.assertEqual({self.RUN_ID, "rl-beta"}, missing)

    def test_no_candidate_still_records_resolved_unchecked_run(self):
        # codex W1 R2 재검 P1: 미선언 06(결속 불가) + 유효 선언·미확인 06 이 한 세션에 있으면, 게이트는
        # 결속 불가로 BLOCK 하되 유효 선언된 미확인 run 은 감사에 기록돼야 한다(doctor 가시성 유지).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")   # 06-cycle → rl-test123(미확인)
            self._add_second_06(root, log_dir, "06-beta.md", "완료 보고\n마커 없음\n")   # 미선언
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)
            self.assertIn("결속 불가", p.stdout)
            missing = {r["run_id"] for r in self._audit_records(root) if r["event"] == "retro_check_missing"}
            self.assertEqual({self.RUN_ID}, missing)   # 유효 선언·미확인 run 은 기록됨

    def test_relative_vault_path_resolved_against_root(self):
        # codex W1 R2 재검 P1: 상대 vault_path 는 project root 기준으로 판정 — 어댑터가 cd 안 해도
        # hook CWD 가 아니라 root/vlt 로 본다. root/vlt 실존 → 게이트 활성 → 미확인 BLOCK.
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "vlt"), exist_ok=True)
            prof_path, log_dir = self._setup(root, mode="enforce", vault_path="vlt")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # raw 상대 isdir 였다면 CWD 기준→INFO(exit0)

    def test_loop_run_in_body_code_block_is_ignored(self):
        # codex W1 R2 P2(teeth): 헤더의 실제 Loop-Run 뒤 본문 코드블록의 예시 Loop-Run 이 상충으로 잡혀
        # false ambiguous BLOCK 이 나면 안 된다. 첫 `## ` 섹션 전 헤더만 파싱한다.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            with open(os.path.join(root, "plan_docs", "06-cycle.md"), "w", encoding="utf-8") as f:
                f.write(f"# 완료 보고\nLoop-Run: {self.RUN_ID}\n\n## 예시\n```\nLoop-Run: rl-example\n```\n")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # 모호 아님 — rl-test123 로 유일 결속 후 미확인 BLOCK
            self.assertIn(self.RUN_ID, p.stdout)
            self.assertNotIn("모호", p.stdout)

    # --- W2: writer-독립 06 감지 (SessionStart 스냅샷) ---
    def _run_session_start(self, root, prof_path, session_id="sess-1"):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root, SAGE_HOOK_CORE_DIR=HOOKS_DIR,
                   SAGE_PROFILE=prof_path, SAGE_TODAY=TODAY, SAGE_GATE_BRANCH="main")
        adapter = os.path.join(ADAPTERS, "claude", "session-start-snapshot.sh")
        return subprocess.run(["bash", adapter], input=json.dumps({"session_id": session_id}),
                              capture_output=True, text=True, env=env)

    def _bash_write_06(self, root, name="06-cycle.md", run_id=None):
        # post-tool-logger 를 거치지 않는 06 작성(Bash 리다이렉트 모사) — 세션 로그에 엔트리가 안 남는다.
        with open(os.path.join(root, "plan_docs", name), "w", encoding="utf-8") as f:
            f.write(f"완료 보고\nLoop-Run: {run_id or self.RUN_ID}\n")

    def _plant_snapshot(self, root, session_id, body):
        # 특정 내용의 스냅샷 파일을 직접 심는다(손상 baseline 테스트용). _run(baseline=False) 와 함께 쓴다.
        snap = os.path.join(root, ".claude", "logs", f"session-snapshot-{session_id}.json")
        os.makedirs(os.path.dirname(snap), exist_ok=True)
        with open(snap, "w", encoding="utf-8") as f:
            f.write(body)

    def test_bash_written_06_detected_via_snapshot(self):
        # W2/P0-b(teeth): 로그에 안 남는 Bash 작성 06 도 SessionStart baseline 대비 신규로 감지돼 BLOCK.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_06=False)   # 06 미작성·미로깅
            self._run_session_start(root, prof_path)                               # baseline: 06 없음
            self._bash_write_06(root)                                              # 로그 없이 06 생성
            p = self._run(root, prof_path, baseline=False)                         # 위 baseline 유지
            self.assertEqual(p.returncode, 2, p.stdout)   # 스냅샷 diff 로 06 포착 → 미확인 enforce BLOCK
            self.assertIn(self.RUN_ID, p.stdout)

    def test_snapshot_write_once_preserves_baseline(self):
        # write-once(teeth): baseline 을 찍은 뒤 06 이 생겨도 재-SessionStart 가 baseline 을 덮지 않는다.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_06=False)
            self._run_session_start(root, prof_path)     # baseline #1: 06 없음
            self._bash_write_06(root)                    # 06 생성
            self._run_session_start(root, prof_path)     # 재-SessionStart — write-once 로 baseline 보존돼야
            p = self._run(root, prof_path, baseline=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # baseline 이 덮였다면 감지 실패

    def test_unchanged_06_not_flagged_by_snapshot(self):
        # SessionStart 시점부터 있던(이번 세션 미변경) 06 은 스냅샷 diff 로 안 잡힌다. baseline 정상이라
        # degraded 도 아님 → 게이트 무동작(false block 방지).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_06=False)
            self._bash_write_06(root)                     # SessionStart 前부터 존재
            self._run_session_start(root, prof_path)      # baseline: 06 이미 포함(같은 내용)
            p = self._run(root, prof_path, baseline=False)
            self.assertEqual(p.returncode, 0, p.stdout)   # 변경 없음·baseline 정상 → 이번 세션 06 아님

    def test_baseline_ok_no_degraded_note(self):
        # baseline 정상(SessionStart 실행) + 06 없음 → degraded 노이즈 없음(정상 경로).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_06=False)
            self._run_session_start(root, prof_path)      # baseline 정상 기록
            p = self._run(root, prof_path, baseline=False)
            self.assertEqual(p.returncode, 0, p.stdout)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertNotIn("writer-독립 06 감지 불가", report)

    # --- W2 degraded baseline 정책: enforce=BLOCK / advisory=WARN / 재시도=WARN (fail-closed) ---
    def test_absent_baseline_enforce_blocks(self):
        # baseline 없음(SessionStart 미발화) + Bash 06 + enforce → fail-closed BLOCK(놓친 06 가능성).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_06=False)
            self._bash_write_06(root)
            p = self._run(root, prof_path, baseline=False)
            self.assertEqual(p.returncode, 2, p.stdout)
            self.assertIn("writer-독립 06 감지 불가", p.stdout)

    def test_corrupt_baseline_enforce_blocks(self):
        # 손상 baseline + enforce → BLOCK(읽기 불가 baseline 은 신뢰 불가 → fail-closed).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_06=False)
            self._bash_write_06(root)
            self._plant_snapshot(root, "sess-1", '{"sha256": {trunc')   # 잘린 JSON
            p = self._run(root, prof_path, baseline=False)
            self.assertEqual(p.returncode, 2, p.stdout)

    def test_no_session_id_enforce_blocks(self):
        # session_id 없음 → 상관 불가(no_session) + enforce → BLOCK.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_06=False)
            self._bash_write_06(root)
            p = self._run(root, prof_path, baseline=False, session_id="")
            self.assertEqual(p.returncode, 2, p.stdout)

    def test_absent_baseline_advisory_warns_not_blocks(self):
        # advisory 는 같은 degraded 조건에서 차단하지 않고 WARN(rc 0) — 표면화만.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="advisory", log_06=False)
            self._bash_write_06(root)
            p = self._run(root, prof_path, baseline=False)
            self.assertEqual(p.returncode, 0, p.stdout)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("writer-독립 06 감지 불가", report)

    def test_degraded_retry_does_not_block_twice(self):
        # stop_hook_active=true(이미 1회 차단) 재시도에서는 WARN 으로 완화 — 무한 Stop 재호출 방지.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_06=False)
            self._bash_write_06(root)
            p = self._run(root, prof_path, baseline=False, stop_hook_active=True)
            self.assertEqual(p.returncode, 0, p.stdout)   # 재시도 → 차단 안 함(플랫폼 제약)

    def test_corrupt_baseline_blocks_even_with_checked_logged_06(self):
        # 로그로 확인된 06 이 있어도 baseline 손상이면 숨은 두 번째 06 가능성 때문에 enforce BLOCK.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")   # 06-cycle 로그됨 → rl-test123
            sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))
            import retro_audit
            retro_audit.record_check(root, self.RUN_ID, "wiki/note.md", "본문")   # 로그된 06 은 확인됨
            self._plant_snapshot(root, "sess-1", "{ broken")
            p = self._run(root, prof_path, baseline=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # 확인된 06 이 있어도 손상 baseline → BLOCK
            self.assertIn("writer-독립 06 감지 불가", p.stdout)

    # --- W4: --no-vault run 예외 (skip 이벤트) ---
    def test_no_vault_skip_passes_gate(self):
        # W4(teeth): retro_note=on 이라 게이트 활성이지만 이 run 은 --no-vault 로 노트를 생략(skip 기록).
        # --check 없이 종료해도 BLOCK 이 아니라 통과(노트 생략은 미완료가 아님).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")   # 06-cycle → rl-test123(미확인)
            sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))
            import retro_audit
            retro_audit.record_skip(root, self.RUN_ID)               # --no-vault 가 남기는 skip
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0, p.stdout)              # skip 이므로 통과(BLOCK 아님)
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("no-vault", report)                        # 통과 사유 = 노트 생략
            self.assertEqual([], [r for r in self._audit_records(root) if r["event"] == "retro_check_missing"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
