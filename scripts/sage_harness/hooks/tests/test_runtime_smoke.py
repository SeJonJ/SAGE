#!/usr/bin/env python3
"""런타임 스모크 — 어댑터 subprocess 를 synthetic 최소 인스턴스(디스크)로 구동해
'설치·코어테스트는 통과하나 런타임은 죽어있다'(Pattern A) 류 회귀를 잡는다.

기존 테스트의 사각지대:
  - TestPdcaEnforcement 는 core.decide() 를 손으로 만든 dict 로 호출 → 어댑터가 디스크에서
    profile.pdca.phases 를 glob 스캔해 snapshot.phase_docs 를 구성하는 '배선 층'이 미검증.
    그 루프가 깨지면 코어 PDCA 테스트는 전부 통과하는데 런타임 강제만 사망(F9 무력화).
  - 전략 import/실행 실패를 어댑터가 stderr 로 표면화(F8b)하는지도 subprocess 레벨 미검증.

본 스모크는 어댑터를 실제 bash 로 띄워 디스크 상태→exit code/채널을 검증한다.
profile 은 도메인 토큰 0 의 중립 합성(독립성 유지). 단일 hook 등록 보존(F6)은 test_generate 가 담당.
"""
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
ADAPTERS = os.path.join(HOOKS_DIR, "adapters")

# 중립 합성 스택(.src) — 어떤 도메인/스택 토큰도 쓰지 않는다(제약 #2).
L1_FILE = "app/ui/screen.src"          # *ui/*.src → L1
L2_FILE = "app/core/data.src"          # *core/*.src → L2
L3_FILE = "app/core/secret_store.src"  # *secret* 파일명 → L3
PHASE_GLOBS = {
    "00": "plan_docs/00-base_plan/**/*.md",
    "01": "plan_docs/01-plan/**/*.md",
    "02": "plan_docs/02-design/**/*.md",
    "03": "plan_docs/03-implementation/**/*.md",
    "04": "plan_docs/04-analyze/**/*.md",
    "05": "plan_docs/05-expert-review/**/*.md",
    "06": "plan_docs/06-report/**/*.md",
}


def make_profile(pdca_enabled=True, l3_strategy="claude_grep_first"):
    return {
        "risk": {
            "desktop_block_glob": "*generated/*",
            "l0_pass_globs": ["*.md", "plan_docs/*"],
            "l1_path_globs": ["*ui/*.src"],
            "l2_path_globs": ["*core/*.src"],
            "l3_filename_globs": ["*secret*"],
            "l2_content_keywords": ["@SynthData"],     # 합성(테스트 내용에 안 나타남)
            "l3_content_keywords": ["synthSecretCall"],
            "plan_glob": "plan_docs/00-base_plan/**/*.md",
            "l3_review_strategy": l3_strategy,
            "review_patterns": ["review"],
        },
        "pdca": {
            "enabled": pdca_enabled,
            "phases": [{"id": pid, "glob": g} for pid, g in PHASE_GLOBS.items()],
            "pre_implementation_required": {"L1": ["00"], "L2": ["00", "01", "02"], "L3": ["00", "01", "02"]},
            "report_phase": "06",
            "approve_phase": "05",
            "approve_marker": "APPROVED",
        },
    }


def write_instance(root, profile, phases=(), approve_content=None):
    """root 에 합성 인스턴스 구성: profile JSON + 요청한 phase 문서들."""
    prof_path = os.path.join(root, "profile.json")
    with open(prof_path, "w", encoding="utf-8") as f:
        json.dump(profile, f)
    for pid in phases:
        sub = PHASE_GLOBS[pid].split("/**", 1)[0]            # 예: plan_docs/00-base_plan
        d = os.path.join(root, sub)
        os.makedirs(d, exist_ok=True)
        body = approve_content if (pid == "05" and approve_content) else f"# phase {pid} 합성 문서\n"
        with open(os.path.join(d, "feature.md"), "w", encoding="utf-8") as f:
            f.write(body)
    return prof_path


def run_adapter(runtime, raw, root, prof_path, branch="main"):
    env_root = "CLAUDE_PROJECT_DIR" if runtime == "claude" else "CODEX_PROJECT_ROOT"
    env = dict(os.environ, **{env_root: root, "SAGE_HOOK_CORE_DIR": HOOKS_DIR,
                              "SAGE_PROFILE": prof_path, "SAGE_GATE_BRANCH": branch})
    adapter = os.path.join(ADAPTERS, runtime, "pre-implementation-gate.sh")
    return subprocess.run(["bash", adapter], input=json.dumps(raw), capture_output=True, text=True, env=env)


def event(runtime, path, content="placeholder"):
    if runtime == "claude":
        return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}, "session_id": "smoke"}
    return {"tool_name": "apply_patch",
            "tool_input": {"command": f"*** Add File: {path}\n+{content}\n"}, "session_id": "smoke"}


def both(self, fn):
    """claude/codex 양 런타임에서 동일 단언(block 메시지 채널 차이는 stdout+stderr 결합으로 흡수)."""
    for rt in ("claude", "codex"):
        with self.subTest(runtime=rt):
            fn(rt)


class TestPdcaEnforcementAlive(unittest.TestCase):
    """F9 런타임 가드 — 어댑터가 디스크 phase 문서를 실제로 스캔/강제하는가."""

    def test_l2_missing_phases_blocks_at_runtime(self):
        def check(rt):
            with tempfile.TemporaryDirectory() as root:
                prof = write_instance(root, make_profile(), phases=())   # phase 문서 0개
                p = run_adapter(rt, event(rt, L2_FILE), root, prof)
                self.assertEqual(p.returncode, 2, f"{rt} L2 phase 결핍 BLOCK 기대\n{p.stdout}\n{p.stderr}")
                self.assertIn("PDCA phase 미작성", p.stdout + p.stderr)
        both(self, check)

    def test_l3_missing_phases_blocks_at_runtime(self):
        def check(rt):
            with tempfile.TemporaryDirectory() as root:
                prof = write_instance(root, make_profile(), phases=())
                p = run_adapter(rt, event(rt, L3_FILE), root, prof)
                self.assertEqual(p.returncode, 2, f"{rt} L3 phase 결핍 BLOCK 기대\n{p.stdout}\n{p.stderr}")
                self.assertIn("PDCA phase 미작성", p.stdout + p.stderr)
        both(self, check)

    def test_l2_phases_present_passes_phase_gate(self):
        # 00/01/02 문서가 디스크에 있으면 어댑터 glob 스캔이 이를 잡아 phase 게이트 통과(plan=00 도 충족 → ok_l2).
        def check(rt):
            with tempfile.TemporaryDirectory() as root:
                prof = write_instance(root, make_profile(), phases=("00", "01", "02"))
                p = run_adapter(rt, event(rt, L2_FILE), root, prof)
                self.assertEqual(p.returncode, 0, f"{rt} phase 충족 통과 기대\n{p.stdout}\n{p.stderr}")
                self.assertNotIn("phase 미작성", p.stdout + p.stderr)
        both(self, check)

    def test_l1_missing_phases_warns_not_blocks(self):
        def check(rt):
            with tempfile.TemporaryDirectory() as root:
                prof = write_instance(root, make_profile(), phases=())
                p = run_adapter(rt, event(rt, L1_FILE), root, prof)
                self.assertEqual(p.returncode, 0, f"{rt} L1 은 warn(차단X) 기대\n{p.stdout}\n{p.stderr}")
        both(self, check)


class TestStrategyExceptionSurfaced(unittest.TestCase):
    """F8b 런타임 가드 — 전략 import/실행 실패가 silent None 으로 둔갑하지 않고 stderr 로 표면화 + fail-closed."""

    def test_broken_strategy_surfaces_to_stderr_and_fails_closed(self):
        bad = "no_such_strategy_module_zzz"
        def check(rt):
            with tempfile.TemporaryDirectory() as root:
                prof = write_instance(root, make_profile(l3_strategy=bad), phases=("00", "01", "02"))
                p = run_adapter(rt, event(rt, L3_FILE), root, prof)
                self.assertEqual(p.returncode, 2, f"{rt} 전략 크래시 → fail-closed BLOCK 기대\n{p.stdout}\n{p.stderr}")
                self.assertIn("fail-closed", p.stderr, f"{rt} 예외가 stderr 로 표면화돼야 함(F8b)")
                self.assertIn(bad, p.stderr, f"{rt} stderr 가 실패한 전략명을 담아야 함")
        both(self, check)


class TestReportApproveGate(unittest.TestCase):
    """F9 report←approve 런타임 가드 — 06 작성 시 05 APPROVED 없으면 어댑터가 실제 차단(R1 글롭버그 회귀 가드)."""

    def test_report_blocked_without_approval(self):
        def check(rt):
            with tempfile.TemporaryDirectory() as root:
                prof = write_instance(root, make_profile(), phases=("05",),
                                      approve_content="Final Status: FAIL\n")
                p = run_adapter(rt, event(rt, "plan_docs/06-report/feature.md"), root, prof)
                self.assertEqual(p.returncode, 2, f"{rt} 05 미승인 → 06 차단 기대\n{p.stdout}\n{p.stderr}")
        both(self, check)

    def test_report_allowed_with_approval(self):
        def check(rt):
            with tempfile.TemporaryDirectory() as root:
                prof = write_instance(root, make_profile(), phases=("05",),
                                      approve_content="Final Status: APPROVED\n")
                p = run_adapter(rt, event(rt, "plan_docs/06-report/feature.md"), root, prof)
                self.assertEqual(p.returncode, 0, f"{rt} 05 APPROVED → 06 통과 기대\n{p.stdout}\n{p.stderr}")
        both(self, check)


class TestPdcaDisabledBackwardCompatible(unittest.TestCase):
    """pdca 비활성 → phase 강제 skip(기존 동작 보존). 과차단 회귀 가드."""

    def test_disabled_pdca_does_not_block_on_missing_phases(self):
        def check(rt):
            with tempfile.TemporaryDirectory() as root:
                prof = write_instance(root, make_profile(pdca_enabled=False), phases=())
                p = run_adapter(rt, event(rt, L2_FILE), root, prof)
                self.assertEqual(p.returncode, 0, f"{rt} pdca off → phase 비강제 기대\n{p.stdout}\n{p.stderr}")
                self.assertNotIn("phase 미작성", p.stdout + p.stderr)
        both(self, check)


class TestMalformedInputHardening(unittest.TestCase):
    """malformed-JSON hardening — 게이트 무력화가 silent/크래시(exit1) 아닌 fail-open(exit0)+surface 인가.
    fail-closed 는 profile 수정 Edit 자체를 막는 deadlock 이라 채택 안 함 → 무력화를 LOUD 하게 가시화."""

    def _run_raw(self, runtime, raw_stdin, root, prof_path):
        env_root = "CLAUDE_PROJECT_DIR" if runtime == "claude" else "CODEX_PROJECT_ROOT"
        env = dict(os.environ, **{env_root: root, "SAGE_HOOK_CORE_DIR": HOOKS_DIR,
                                  "SAGE_PROFILE": prof_path, "SAGE_GATE_BRANCH": "main"})
        adapter = os.path.join(ADAPTERS, runtime, "pre-implementation-gate.sh")
        return subprocess.run(["bash", adapter], input=raw_stdin, capture_output=True, text=True, env=env)

    def test_malformed_profile_fails_open_with_surface(self):
        def check(rt):
            with tempfile.TemporaryDirectory() as root:
                prof = os.path.join(root, "profile.json")
                with open(prof, "w", encoding="utf-8") as f:
                    f.write("{ this is not valid json ")   # 깨진 profile (이전엔 uncaught → exit1 크래시)
                p = self._run_raw(rt, json.dumps(event(rt, L2_FILE)), root, prof)
                self.assertEqual(p.returncode, 0, f"{rt} 깨진 profile → fail-open(exit0, not crash-exit1)\n{p.stderr}")
                self.assertIn("profile 파싱 실패", p.stderr, f"{rt} 무력화 상태가 surface 돼야 함")
        both(self, check)

    def test_malformed_input_fails_open_with_surface(self):
        def check(rt):
            with tempfile.TemporaryDirectory() as root:
                prof = write_instance(root, make_profile(), phases=("00", "01", "02"))
                p = self._run_raw(rt, "{ not json at all ", root, prof)
                self.assertEqual(p.returncode, 0, f"{rt} 깨진 입력 → fail-open(exit0)\n{p.stderr}")
                self.assertIn("입력 JSON 파싱 실패", p.stderr, f"{rt} 입력 파싱 실패가 surface 돼야 함")
        both(self, check)


if __name__ == "__main__":
    unittest.main(verbosity=2)
