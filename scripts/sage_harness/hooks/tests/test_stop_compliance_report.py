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
               log_05=True, doc05="plan_docs/05-cycle.md", retro_note=True):
        prof = {"pdca": {"phases": [{"id": "05", "glob": glob05},
                                     {"id": "06", "glob": glob06}],
                         "retro": {"report_gate_enforce": mode}},
                # retro_note 켜져야 게이트가 유효(노트가 생성돼야 --check 가능). off 는 별도 테스트.
                "knowledge_capture": {"retro_note": retro_note, "vault_path": "/tmp/v"}}
        prof_path = os.path.join(root, "profile.json")
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump(prof, f)

        os.makedirs(os.path.join(root, "plan_docs"), exist_ok=True)
        body = f"Loop-Run: {self.RUN_ID}\n" if has_loop_run else "본문만 있고 마커 없음\n"
        abs05 = os.path.join(root, doc05)
        os.makedirs(os.path.dirname(abs05), exist_ok=True)
        with open(abs05, "w", encoding="utf-8") as f:
            f.write(body)

        sess = "sess-1" if session_matches else "sess-OTHER"
        log_dir = os.path.join(root, ".claude", "logs")
        os.makedirs(log_dir, exist_ok=True)
        entries = []
        # 05·06 모두 이번 세션 로그에 있어야 게이트가 결속한다(session-scoped run_id — 다른 세션의 05 를
        # 이번 06 에 오결속하지 않도록). 디스크에도 실재해야 함(글롭 매치 기준).
        if log_05:
            entries.append({"ts": f"{TODAY}T00:00:00Z", "tool": "Write", "file": doc05,
                            "type": "plan-doc", "branch": "main", "session": sess})
        if log_06:
            abs06 = os.path.join(root, doc06)
            os.makedirs(os.path.dirname(abs06), exist_ok=True)
            with open(abs06, "w", encoding="utf-8") as f:
                f.write("완료 보고\n")
            entries.append({"ts": f"{TODAY}T00:00:01Z", "tool": "Write", "file": doc06,
                            "type": "plan-doc", "branch": "main", "session": sess})
        with open(os.path.join(log_dir, f"session-{TODAY}.jsonl"), "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return prof_path, log_dir

    def _run(self, root, prof_path, stop_hook_active=False):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root, SAGE_HOOK_CORE_DIR=HOOKS_DIR,
                   SAGE_PROFILE=prof_path, SAGE_TODAY=TODAY, SAGE_GATE_BRANCH="main")
        adapter = os.path.join(ADAPTERS, "claude", "stop-compliance-report.sh")
        stdin = json.dumps({"session_id": "sess-1", "stop_hook_active": stop_hook_active})
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

    def test_no_loop_run_marker_does_not_block(self):
        # run_id 특정 불가 → fail-open(skip), block 아님.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", has_loop_run=False)
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0)

    def test_unrelated_05_different_stem_is_ignored(self):
        # 같은 세션에 다른 stem 의 05(rl-different, stem=other)가 있어도 06(stem=cycle)은 stem 이 맞는
        # 05-cycle(rl-test123)에만 결속된다 — 다른 사이클의 05 는 무시(codex 4R stem-binding).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            with open(os.path.join(root, "plan_docs", "05-other.md"), "w", encoding="utf-8") as f:
                f.write("Loop-Run: rl-different\n")
            log_file = os.path.join(log_dir, f"session-{TODAY}.jsonl")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": f"{TODAY}T00:00:00Z", "tool": "Write", "file": "plan_docs/05-other.md",
                                    "type": "plan-doc", "branch": "main", "session": "sess-1"}) + "\n")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # rl-test123 에만 결속 → BLOCK
            self.assertIn(self.RUN_ID, p.stdout)
            self.assertNotIn("rl-different", p.stdout)
            missing_ids = {r["run_id"] for r in self._audit_records(root) if r["event"] == "retro_check_missing"}
            self.assertEqual({self.RUN_ID}, missing_ids)   # 미완료도 rl-different 아닌 rl-test123 에만

    def test_same_session_different_cycle_06_does_not_bind(self):
        # codex 구현리뷰 4R P1(teeth): 같은 세션에 05-alpha(rl-alpha)와 06-beta(다른 사이클)만 있으면
        # stem 불일치라 06-beta 가 rl-alpha 에 오결속돼 block/기록되면 안 된다 → skip.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(
                root, mode="enforce", has_loop_run=True,
                doc05="plan_docs/05-alpha.md", doc06="plan_docs/06-beta.md")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0, p.stdout)   # stem alpha≠beta → skip
            self.assertEqual([], [r for r in self._audit_records(root) if r["event"] == "retro_check_missing"])

    def test_codex_reports_block_but_never_exits_2(self):
        # v1 스코프: codex 의 Stop exit-2 차단은 이 저장소에서 실검증된 적이 없다 — claude 만 실제 차단.
        with tempfile.TemporaryDirectory() as root:
            prof_path, _ = self._setup(root, mode="enforce")
            log_dir = os.path.join(root, ".codex", "logs")
            os.makedirs(log_dir, exist_ok=True)
            os.rename(os.path.join(root, ".claude", "logs", f"session-{TODAY}.jsonl"),
                      os.path.join(log_dir, f"session-{TODAY}.jsonl"))
            env = dict(os.environ, CODEX_PROJECT_ROOT=root, SAGE_HOOK_CORE_DIR=HOOKS_DIR,
                       SAGE_PROFILE=prof_path, SAGE_TODAY=TODAY, SAGE_GATE_BRANCH="main")
            adapter = os.path.join(ADAPTERS, "codex", "stop-compliance-report.sh")
            stdin = json.dumps({"session_id": "sess-1", "stop_hook_active": False})
            p = subprocess.run(["bash", adapter], input=stdin, capture_output=True, text=True, env=env)
            self.assertEqual(p.returncode, 0)   # claude 였다면 2
            report = Path(os.path.join(log_dir, f"compliance-{TODAY}.md")).read_text(encoding="utf-8")
            self.assertIn("[BLOCK] retro_gate", report)   # 리포트엔 사실대로 남음(미차단이지 미탐지 아님)

    def test_05_not_in_this_session_skips(self):
        # codex 구현리뷰 3R P1(teeth): 05 가 이번 세션 로그에 없으면(다른 세션의 05 만 디스크에 있음)
        # run_id 를 이번 06 에 결속하지 않는다 → skip(잘못된 cross-session block 방지).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce", log_05=False)   # 05 는 디스크엔 있으나 세션로그엔 없음
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0)
            # missing 감사도 남의 run 에 잘못 기록되면 안 됨.
            self.assertEqual([], [r for r in self._audit_records(root) if r["event"] == "retro_check_missing"])

    def test_standard_recursive_glob_06_is_detected(self):
        # codex 구현리뷰 P0(teeth): 표준 `plan_docs/06-report/**/*.md` 가 06 을 직속 자식으로 두면
        # fnmatch 로는 영원히 매치 안 돼 게이트가 무동작. glob.glob 은 ** 제로디렉토리를 올바로 매치.
        # 05·06 stem 을 `cycle` 로 맞춤(nested 06 basename=cycle, flat 05=05-cycle → 둘 다 stem cycle).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(
                root, mode="enforce", glob06="plan_docs/06-report/**/*.md",
                doc06="plan_docs/06-report/cycle.md")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # fnmatch 였다면 0(무동작)

    def test_nested_numeric_ticket_different_cycles_do_not_bind(self):
        # codex 구현리뷰 5R P1(teeth): nested `[ticket]-[feature].md` 에서 05-138·06-139 는 다른 티켓
        # (다른 사이클)이다. 임의 선행숫자를 지우면 둘 다 `webrtc` 로 축약돼 오결속된다 → phase 번호만 제거.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(
                root, mode="enforce",
                glob05="plan_docs/05-review/**/*.md", doc05="plan_docs/05-review/138-webrtc.md",
                glob06="plan_docs/06-report/**/*.md", doc06="plan_docs/06-report/139-webrtc.md")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0, p.stdout)   # 138≠139 → skip
            self.assertEqual([], [r for r in self._audit_records(root) if r["event"] == "retro_check_missing"])

    def test_nested_numeric_ticket_same_cycle_binds(self):
        # 같은 티켓(138)의 05·06 은 같은 사이클 → 결속·BLOCK.
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(
                root, mode="enforce",
                glob05="plan_docs/05-review/**/*.md", doc05="plan_docs/05-review/138-webrtc.md",
                glob06="plan_docs/06-report/**/*.md", doc06="plan_docs/06-report/138-webrtc.md")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)

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

    def test_two_conflicting_markers_in_one_doc_skips(self):
        # codex 구현리뷰 P1(teeth): 한 05 문서에 서로 다른 Loop-Run 이 둘이면 모호 → skip(잘못 결속 금지).
        with tempfile.TemporaryDirectory() as root:
            prof_path, log_dir = self._setup(root, mode="enforce")
            with open(os.path.join(root, "plan_docs", "05-cycle.md"), "w", encoding="utf-8") as f:
                f.write("Loop-Run: rl-aaa\n임의 본문\nLoop-Run: rl-bbb\n")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0)

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
                f.write("완료\n")
            # 06 을 dot-prefix 경로로 로그에 추가(05 로그는 _setup 이 이미 남김).
            with open(os.path.join(log_dir, f"session-{TODAY}.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": f"{TODAY}T00:00:01Z", "tool": "Write",
                                    "file": "./plan_docs/06-cycle.md", "type": "plan-doc",
                                    "branch": "main", "session": "sess-1"}) + "\n")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 2, p.stdout)   # 정규화 안 하면 공집합→exit 0

    def test_other_session_05_does_not_bind_to_this_06(self):
        # codex 구현리뷰 3R P1(teeth): 다른 세션의 05(rl-other)만 디스크·로그에 있고 이번 세션은 06 만
        # 쓴 경우, 이번 06 이 rl-other 에 오결속돼 block 되거나 missing 이 rl-other 에 잘못 남으면 안 된다.
        with tempfile.TemporaryDirectory() as root:
            # 05 는 sess-OTHER, 06 은 sess-1(현재). _setup 은 05·06 을 같은 세션에 두므로 수동 구성.
            prof_path, log_dir = self._setup(root, mode="enforce", log_05=False, log_06=False)
            with open(os.path.join(log_dir, f"session-{TODAY}.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"ts": f"{TODAY}T00:00:00Z", "tool": "Write", "file": "plan_docs/05-cycle.md",
                                    "type": "plan-doc", "branch": "main", "session": "sess-OTHER"}) + "\n")
                f.write(json.dumps({"ts": f"{TODAY}T00:00:01Z", "tool": "Write", "file": "plan_docs/06-cycle.md",
                                    "type": "plan-doc", "branch": "main", "session": "sess-1"}) + "\n")
            with open(os.path.join(root, "plan_docs", "06-cycle.md"), "w", encoding="utf-8") as f:
                f.write("완료\n")
            p = self._run(root, prof_path, stop_hook_active=False)
            self.assertEqual(p.returncode, 0, p.stdout)   # 오결속 block 아님
            self.assertEqual([], [r for r in self._audit_records(root) if r["event"] == "retro_check_missing"])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
