#!/usr/bin/env python3
"""sage review-loop CLI 단위 — Loop A 감사 기록의 SAGE-owned 진입점(어휘 강제 레이어).

loop_audit 라이브러리(permissive)는 test_loop_audit.py 가 검증. 여기선 CLI 가 추가하는 계약:
  1. open → stdout 에 run_id, .sage/loop_audit.jsonl 기록
  2. round/close 누적, show 요약
  3. 어휘 강제: result/reason argparse choices, result↔reason 의미 짝(APPROVED↔CONVERGED/DRY 등)
  4. 카운트 음수/비정수 거부
  5. cfg 스냅샷(profile.pdca.review_loop)
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import review_loop as review_loop_command  # noqa: E402
from pathlib import Path

KOREAN = re.compile(r"[가-힣]")


def sage(*args, root=None, lang=None):
    """python3 -m sage [--lang L] review-loop <args> 실행 → CompletedProcess.

    `--lang` 은 전역 옵션이라 서브커맨드보다 앞에 와야 한다(argparse 계약).
    """
    cmd = [sys.executable, "-m", "sage"]
    if lang:
        cmd += ["--lang", lang]
    cmd += ["review-loop", *args]
    if root:
        cmd += ["--root", root]
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)


class TestReviewLoopCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _open(self, risk="L3"):
        r = sage("open", "--risk", risk, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip().splitlines()[0]   # 첫 줄 = run_id

    def test_profile_loader_applies_local_vault_path(self):
        os.makedirs(os.path.join(self.tmp, "sage"), exist_ok=True)
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("knowledge_capture:\n  loop_audit_dashboard: true\n  vault_path: /shared-vault\n")
        with open(os.path.join(self.tmp, "sage", "project-profile.local.yaml"), "w", encoding="utf-8") as f:
            f.write("knowledge_capture:\n  enabled: true\n  vault_path: /local-vault\n")

        profile = review_loop_command._load_profile(self.tmp)

        self.assertEqual(profile["knowledge_capture"]["vault_path"], "/local-vault")

    def test_open_emits_run_id_and_records(self):
        rid = self._open()
        self.assertTrue(rid.startswith("rl-"))
        path = os.path.join(self.tmp, ".sage", "loop_audit.jsonl")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            rec = json.loads(f.readline())
        self.assertEqual(rec["event"], "loop_open")
        self.assertEqual(rec["risk"], "L3")

    def test_open_rejects_bad_risk(self):
        r = sage("open", "--risk", "L1", root=self.tmp)   # 루프는 L2/L3 만(argparse choices)
        self.assertNotEqual(r.returncode, 0)

    def test_round_and_show(self):
        rid = self._open()
        r = sage("round", "--run-id", rid, "--iteration", "1", "--found", "5",
                 "--survived", "2", "--accepted", "2", "--tokens", "1000", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        s = sage("show", root=self.tmp)
        self.assertEqual(s.returncode, 0)
        self.assertIn(rid, s.stdout)
        self.assertIn("found=5", s.stdout)

    def test_round_rejects_negative_count(self):
        rid = self._open()
        r = sage("round", "--run-id", rid, "--iteration", "1", "--found", "-1",
                 "--survived", "0", "--accepted", "0", root=self.tmp)
        self.assertNotEqual(r.returncode, 0)

    def test_close_approved_with_converged_ok(self):
        rid = self._open()
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "2", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_close_approved_with_blocked_reason_rejected(self):
        # 의미 짝 강제: APPROVED 는 BUDGET_ITER 같은 BLOCKED reason 과 못 짝.
        rid = self._open()
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "BUDGET_ITER",
                 "--iterations", "3", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("APPROVED", r.stderr)

    def test_close_blocked_with_approved_reason_rejected(self):
        rid = self._open()
        r = sage("close", "--run-id", rid, "--result", "BLOCKED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 2)

    def test_close_blocked_arch_ok(self):
        rid = self._open()
        r = sage("close", "--run-id", rid, "--result", "BLOCKED", "--reason", "BLOCKED_ARCH",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_close_rejects_unknown_reason(self):
        rid = self._open()
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "NOPE",
                 "--iterations", "1", root=self.tmp)
        self.assertNotEqual(r.returncode, 0)   # argparse choices

    def test_cfg_snapshot_from_profile(self):
        os.makedirs(os.path.join(self.tmp, "sage"), exist_ok=True)
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("pdca:\n  review_loop:\n    enabled: true\n    refuters: 3\n    lenses: [security]\n")
        self._open()
        with open(os.path.join(self.tmp, ".sage", "loop_audit.jsonl"), encoding="utf-8") as f:
            rec = json.loads(f.readline())
        self.assertEqual(rec["cfg"]["refuters"], 3)
        self.assertEqual(rec["cfg"]["lenses"], ["security"])

    def test_open_blocks_malformed_local_profile(self):
        os.makedirs(os.path.join(self.tmp, "sage"), exist_ok=True)
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("pdca:\n  review_loop:\n    termination_enforce: enforce\n")
        with open(os.path.join(self.tmp, "sage", "project-profile.local.yaml"), "w", encoding="utf-8") as f:
            f.write("capabilties: {}\n")

        r = sage("open", "--risk", "L3", root=self.tmp)

        self.assertEqual(r.returncode, 2)
        self.assertIn("project-profile.local.yaml", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".sage", "loop_audit.jsonl")))

    def _corrupt_audit(self):
        path = os.path.join(self.tmp, ".sage", "loop_audit.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "ab") as f:
            f.write(b'{"partial":')

    def test_open_audit_write_failure_is_exit_2_without_traceback(self):
        self._corrupt_audit()

        r = sage("open", "--risk", "L3", root=self.tmp)

        self.assertEqual(r.returncode, 2)
        self.assertIn("audit write failed", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_round_audit_write_failure_is_exit_2_without_traceback(self):
        rid = self._open()
        self._corrupt_audit()

        r = sage("round", "--run-id", rid, "--iteration", "1", "--found", "1",
                 "--survived", "0", "--accepted", "0", root=self.tmp)

        self.assertEqual(r.returncode, 2)
        self.assertIn("audit write failed", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_close_audit_write_failure_is_exit_2_without_traceback(self):
        rid = self._open()
        self._corrupt_audit()

        r = sage("close", "--run-id", rid, "--result", "BLOCKED", "--reason", "BUDGET_ITER",
                 "--iterations", "1", root=self.tmp)

        self.assertEqual(r.returncode, 2)
        self.assertIn("audit write failed", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    # --- codex S3 후속: CLI 가 integrity 를 write 시점에 강제 ---
    def test_round_orphan_run_id_rejected(self):
        # open 없는 run_id 의 round → exit 2(orphan 차단).
        r = sage("round", "--run-id", "rl-ghost", "--iteration", "1", "--found", "1",
                 "--survived", "0", "--accepted", "0", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("orphan", r.stderr)

    def test_close_orphan_run_id_rejected(self):
        r = sage("close", "--run-id", "rl-ghost", "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 2)

    def test_duplicate_open_rejected(self):
        sage("open", "--risk", "L3", "--run-id", "rl-dup", root=self.tmp)
        r = sage("open", "--risk", "L2", "--run-id", "rl-dup", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("이미 open", r.stderr)

    def test_round_rejects_survived_gt_found(self):
        rid = self._open()
        r = sage("round", "--run-id", rid, "--iteration", "1", "--found", "2",
                 "--survived", "5", "--accepted", "0", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("survived", r.stderr)

    def test_round_rejects_accepted_gt_survived(self):
        rid = self._open()
        r = sage("round", "--run-id", rid, "--iteration", "1", "--found", "5",
                 "--survived", "2", "--accepted", "4", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("accepted", r.stderr)

    def test_close_after_close_rejected(self):
        rid = self._open()
        sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
             "--iterations", "1", root=self.tmp)
        r = sage("close", "--run-id", rid, "--result", "BLOCKED", "--reason", "BUDGET_ITER",
                 "--iterations", "2", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("이미 종료", r.stderr)

    def test_round_after_close_rejected(self):
        rid = self._open()
        sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
             "--iterations", "1", root=self.tmp)
        r = sage("round", "--run-id", rid, "--iteration", "2", "--found", "1",
                 "--survived", "0", "--accepted", "0", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("이미 종료", r.stderr)

    def test_root_autodiscovery_from_subdir(self):
        # 프로젝트 루트에 profile, 서브디렉토리에서 --root 없이 실행해도 같은 .sage 에 기록(P1).
        os.makedirs(os.path.join(self.tmp, "sage"), exist_ok=True)
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("pdca:\n  review_loop:\n    enabled: true\n    refuters: 2\n")
        subdir = os.path.join(self.tmp, "src", "deep")
        os.makedirs(subdir, exist_ok=True)
        # --root 생략 + cwd=서브디렉토리 → 루트 자동 탐색
        r = subprocess.run([sys.executable, "-m", "sage", "review-loop", "open", "--risk", "L3"],
                           cwd=subdir, capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": REPO})
        self.assertEqual(r.returncode, 0, r.stderr)
        # 루트(.tmp)의 .sage 에 기록됐는지 — 서브디렉토리가 아니라
        self.assertTrue(os.path.exists(os.path.join(self.tmp, ".sage", "loop_audit.jsonl")))
        self.assertFalse(os.path.exists(os.path.join(subdir, ".sage", "loop_audit.jsonl")))
        # cfg 스냅샷도 루트 profile 에서 잡힘
        with open(os.path.join(self.tmp, ".sage", "loop_audit.jsonl"), encoding="utf-8") as f:
            rec = json.loads(f.readline())
        self.assertEqual(rec["cfg"]["refuters"], 2)


class TestTerminationEnforcement(unittest.TestCase):
    """7.8단계 A — close 종료 결정론 검산(기록된 라운드 + cfg vs result/reason)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "sage"), exist_ok=True)

    def _profile(self, mode):
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("pdca:\n  review_loop:\n    enabled: true\n"
                    "    budget_tokens: { L3: 600000 }\n    max_iterations: { L3: 3 }\n"
                    "    dry_rounds: 1\n"
                    f"    termination_enforce: {mode}\n")

    def _open_round(self, survived, found=5, tokens=50000, accepted=0):
        rid = sage("open", "--risk", "L3", root=self.tmp).stdout.strip().splitlines()[0]
        sage("round", "--run-id", rid, "--iteration", "1", "--found", str(found),
             "--survived", str(survived), "--accepted", str(accepted), "--tokens", str(tokens), root=self.tmp)
        return rid

    def test_enforce_rejects_approved_with_survivors(self):
        self._profile("enforce")
        rid = self._open_round(survived=2)   # 미해결 남음
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("불일치", r.stderr)
        # 거부됐으니 close 레코드 없음
        self.assertNotIn("loop_close", Path(os.path.join(self.tmp, ".sage", "loop_audit.jsonl")).read_text(encoding="utf-8"))

    def test_close_blocks_when_local_profile_becomes_malformed(self):
        self._profile("enforce")
        rid = self._open_round(survived=2)
        with open(os.path.join(self.tmp, "sage", "project-profile.local.yaml"), "w", encoding="utf-8") as f:
            f.write("capabilties: {}\n")

        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)

        self.assertEqual(r.returncode, 2)
        self.assertIn("project-profile.local.yaml", r.stderr)
        self.assertNotIn("loop_close", Path(os.path.join(self.tmp, ".sage", "loop_audit.jsonl")).read_text(encoding="utf-8"))

    def test_advisory_warns_but_proceeds(self):
        self._profile("advisory")
        rid = self._open_round(survived=2)
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("불일치", r.stderr)
        self.assertIn("advisory", r.stderr)
        self.assertIn("loop_close", Path(os.path.join(self.tmp, ".sage", "loop_audit.jsonl")).read_text(encoding="utf-8"))

    def test_enforce_passes_consistent_close(self):
        self._profile("enforce")
        rid = self._open_round(survived=0, accepted=0)   # 수렴(발견했으나 전부 반증/처리, 미해결 0)
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_enforce_rejects_approved_over_budget(self):
        self._profile("enforce")
        rid = self._open_round(survived=0, tokens=700000)   # 예산(600k) 초과인데 APPROVED
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("budget", r.stderr)

    def test_enforce_blocked_arch_requires_arch_round(self):
        self._profile("enforce")
        rid = self._open_round(survived=1)   # arch 0
        r = sage("close", "--run-id", rid, "--result", "BLOCKED", "--reason", "BLOCKED_ARCH",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED_ARCH", r.stderr)

    def test_no_cfg_skips_check(self):
        # profile/cfg 없으면 검산 skip(기본 advisory) — close 통과.
        rid = self._open_round(survived=2)   # profile 안 씀
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)
        # cfg 없음 → budget/max 검사 skip, 하지만 survived>0 은 cfg 불요 검사라 advisory WARN + 진행
        self.assertEqual(r.returncode, 0, r.stderr)

    # --- codex 리뷰 A 후속 ---
    def test_enforce_rejects_no_rounds_approved(self):
        # P1: 라운드 0인데 APPROVED/CONVERGED → 근거 없음 → enforce 거부.
        self._profile("enforce")
        rid = sage("open", "--risk", "L3", root=self.tmp).stdout.strip().splitlines()[0]   # 라운드 없이
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "0", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("라운드 기록 0", r.stderr)

    def test_enforce_rejects_budget_iter_when_converged(self):
        # P1: BUDGET_ITER 인데 마지막 survived=0(수렴) → 모순(CONVERGED 여야).
        self._profile("enforce")
        rid = self._open_round(survived=0)   # 수렴 상태
        r = sage("close", "--run-id", rid, "--result", "BLOCKED", "--reason", "BUDGET_ITER",
                 "--iterations", "3", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("BUDGET_ITER", r.stderr)

    def test_enforce_refuses_close_on_integrity_warning(self):
        # 손상 줄을 skip하고 append하면 삽입 탐지가 무력화되므로 close 자체를 거부한다.
        self._profile("enforce")
        rid = self._open_round(survived=2)   # APPROVED 와 모순될 상태
        path = os.path.join(self.tmp, ".sage", "loop_audit.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write("{ corrupt line\n")   # 무결성 경고 유발
        before = Path(path).read_bytes()
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("audit write failed", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(Path(path).read_bytes(), before)

    def test_missing_budget_cfg_skip_warn(self):
        # P2: budget 미설정인데 APPROVED → 예산 검산 skip + WARN(차단 안 함).
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("pdca:\n  review_loop:\n    enabled: true\n    termination_enforce: enforce\n")  # budget 없음
        rid = self._open_round(survived=0)
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)   # 예산 검사 skip → 통과
        self.assertIn("skip", r.stderr)

    def test_unknown_mode_warns_advisory(self):
        # P2: 미지 termination_enforce 값 → 침묵 말고 WARN + advisory.
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("pdca:\n  review_loop:\n    enabled: true\n    termination_enforce: strict\n")
        rid = self._open_round(survived=2)
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)   # advisory 처리 → 진행
        self.assertIn("미지원", r.stderr)


class TestReviewLoopNext(unittest.TestCase):
    """`review-loop next` — 기록된 라운드 + cfg 로 계속/종료 결정론 권고(감사 기록 안 함)."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "sage"), exist_ok=True)
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("pdca:\n  review_loop:\n    enabled: true\n    lenses: [security]\n    refuters: 2\n"
                    "    max_iterations: { L3: 3 }\n    budget_tokens: { L3: 100000 }\n    dry_rounds: 1\n")

    def _open(self, risk="L3"):
        return sage("open", "--risk", risk, root=self.tmp).stdout.strip().splitlines()[0]

    def _round(self, rid, it, found, survived, accepted=0, tokens=0, arch=0):
        sage("round", "--run-id", rid, "--iteration", str(it), "--found", str(found),
             "--survived", str(survived), "--accepted", str(accepted), "--tokens", str(tokens),
             "--arch", str(arch), root=self.tmp)

    def test_no_rounds_continue(self):
        rid = self._open()
        r = sage("next", "--run-id", rid, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("NEXT: CONTINUE", r.stdout)

    def test_unresolved_continue(self):
        rid = self._open()
        self._round(rid, 1, found=5, survived=2, tokens=1000)
        r = sage("next", "--run-id", rid, root=self.tmp)
        self.assertIn("NEXT: CONTINUE", r.stdout)

    def test_converged_stop_approved(self):
        rid = self._open()
        self._round(rid, 1, found=2, survived=2, accepted=2, tokens=1000)   # 발견→전부 채택
        self._round(rid, 2, found=0, survived=0, accepted=0, tokens=2000)   # 신규·미해결 0 = 수렴
        r = sage("next", "--run-id", rid, root=self.tmp)
        self.assertIn("NEXT: STOP result=APPROVED reason=CONVERGED", r.stdout)

    def test_budget_stop_blocked(self):
        rid = self._open()
        self._round(rid, 1, found=5, survived=2, tokens=100000)   # ≥ budget[L3]
        r = sage("next", "--run-id", rid, root=self.tmp)
        self.assertIn("NEXT: STOP result=BLOCKED reason=BUDGET_TOK", r.stdout)

    def test_max_iter_unresolved_stop_blocked(self):
        rid = self._open()
        for it in (1, 2, 3):                      # max_iterations[L3]=3
            self._round(rid, it, found=2, survived=1, tokens=1000)
        r = sage("next", "--run-id", rid, root=self.tmp)
        self.assertIn("NEXT: STOP result=BLOCKED reason=BUDGET_ITER", r.stdout)

    def test_arch_stop_blocked(self):
        rid = self._open()
        self._round(rid, 1, found=2, survived=1, tokens=1000, arch=1)
        r = sage("next", "--run-id", rid, root=self.tmp)
        self.assertIn("NEXT: STOP result=BLOCKED reason=BLOCKED_ARCH", r.stdout)

    def test_orphan_rejected(self):
        r = sage("next", "--run-id", "rl-nope", root=self.tmp)
        self.assertEqual(r.returncode, 2)

    def test_closed_reports_done(self):
        rid = self._open()
        self._round(rid, 1, found=0, survived=0, accepted=0, tokens=1000)
        sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
             "--iterations", "1", root=self.tmp)
        r = sage("next", "--run-id", rid, root=self.tmp)
        self.assertIn("NEXT: DONE", r.stdout)

    def test_next_does_not_mutate_audit(self):
        rid = self._open()
        self._round(rid, 1, found=5, survived=2, tokens=1000)
        path = os.path.join(self.tmp, ".sage", "loop_audit.jsonl")
        before = Path(path).read_text(encoding="utf-8")
        sage("next", "--run-id", rid, root=self.tmp)
        self.assertEqual(Path(path).read_text(encoding="utf-8"), before)   # 감사 로그 불변


class TestReviewLoopDisplayLanguage(unittest.TestCase):
    """`--lang en` 에서 종료 검산·권고·요약이 한국어를 흘리지 않고, 판정은 그대로여야 한다.

    이 명령의 판정 문장은 `_termination_discrepancies`·`_next_recommendation` 이 만든다 —
    둘 다 화면 문구를 직접 들고 있었으므로, 언어를 바꿔도 문장만 바뀌고 exit code 와 기계
    판독 줄(`NEXT:`)은 바뀌지 않는지 같은 실행을 두 언어로 대조해 확인한다.
    """
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _profile(self, body):
        os.makedirs(os.path.join(self.tmp, "sage"), exist_ok=True)
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write(body)

    def _open(self, risk="L3", lang=None):
        return sage("open", "--risk", risk, root=self.tmp, lang=lang).stdout.strip().splitlines()[0]

    def _round(self, rid, it=1, found=5, survived=2, accepted=0, tokens=0, arch=0):
        sage("round", "--run-id", rid, "--iteration", str(it), "--found", str(found),
             "--survived", str(survived), "--accepted", str(accepted), "--tokens", str(tokens),
             "--arch", str(arch), root=self.tmp)

    def _assertNoKorean(self, text, label):
        leaked = [line for line in text.splitlines() if KOREAN.search(line)]
        self.assertEqual([], leaked, f"{label} 에 한국어가 남았다: {leaked}")

    def test_termination_mismatch_and_skip_are_english_with_same_exit(self):
        # budget 미설정(=skip) + survived>0 인데 APPROVED(=mismatch) → 두 종류가 한 실행에 다 나온다.
        self._profile("pdca:\n  review_loop:\n    enabled: true\n    termination_enforce: advisory\n")
        args = ("close", "--result", "APPROVED", "--reason", "CONVERGED", "--iterations", "1")

        ko_rid = self._open()
        self._round(ko_rid, survived=2)
        ko = sage(*args, "--run-id", ko_rid, root=self.tmp)
        en_rid = self._open()
        self._round(en_rid, survived=2)
        en = sage(*args, "--run-id", en_rid, root=self.tmp, lang="en")

        self.assertEqual(0, ko.returncode, ko.stderr)
        self.assertEqual(ko.returncode, en.returncode)          # 판정 불변
        self.assertIn("불일치", ko.stderr)                       # 기본은 한국어 유지
        self._assertNoKorean(en.stderr, "close --lang en stderr")
        self.assertIn("mismatch", en.stderr)
        self.assertIn("survived=2", en.stderr)                  # 사실 조각은 언어 무관
        self.assertIn("skipped", en.stderr)

    def test_enforce_refusal_is_english_and_still_exit_2(self):
        # 라운드 0 + APPROVED → 근거 없음. enforce 면 거부(exit 2) — 문장만 영어여야 한다.
        self._profile("pdca:\n  review_loop:\n    enabled: true\n    termination_enforce: enforce\n")
        args = ("close", "--result", "APPROVED", "--reason", "CONVERGED", "--iterations", "0")

        ko = sage(*args, "--run-id", self._open(), root=self.tmp)
        en = sage(*args, "--run-id", self._open(), root=self.tmp, lang="en")

        self.assertEqual(2, ko.returncode)
        self.assertEqual(2, en.returncode)
        self.assertIn("라운드 기록 0", ko.stderr)
        self._assertNoKorean(en.stderr, "close enforce --lang en stderr")
        self.assertIn("no rounds", en.stderr)
        audit = Path(os.path.join(self.tmp, ".sage", "loop_audit.jsonl")).read_text(encoding="utf-8")
        self.assertNotIn("loop_close", audit)                   # 거부는 기록하지 않는다(부작용 불변)

    def test_next_recommendation_is_english_with_identical_machine_line(self):
        self._profile("pdca:\n  review_loop:\n    enabled: true\n"
                      "    max_iterations: { L3: 3 }\n")   # budget 미설정 → 권고 skip 도 함께 나온다
        rid = self._open()
        self._round(rid, survived=2)

        ko = sage("next", "--run-id", rid, root=self.tmp)
        en = sage("next", "--run-id", rid, root=self.tmp, lang="en")

        self.assertEqual(0, ko.returncode, ko.stderr)
        self.assertEqual(ko.returncode, en.returncode)
        self.assertIn("NEXT: CONTINUE", ko.stdout)
        self.assertEqual(ko.stdout, en.stdout)                  # 기계 판독 줄은 언어 중립
        self._assertNoKorean(en.stderr, "next --lang en stderr")
        self.assertIn("budget_tokens[L3]", en.stderr)            # cfg key 는 번역하지 않는다

    def test_next_stop_recommendation_is_english(self):
        self._profile("pdca:\n  review_loop:\n    enabled: true\n"
                      "    max_iterations: { L3: 1 }\n    budget_tokens: { L3: 100 }\n")
        rid = self._open()
        self._round(rid, survived=0, tokens=10)                 # 수렴 → STOP/APPROVED/CONVERGED

        en = sage("next", "--run-id", rid, root=self.tmp, lang="en")

        self.assertIn("NEXT: STOP result=APPROVED reason=CONVERGED", en.stdout)
        self._assertNoKorean(en.stderr, "next STOP --lang en stderr")

    def test_show_status_is_english_for_open_and_closed_runs(self):
        open_rid = self._open()                                  # 미종료 = '진행중'
        closed_rid = self._open()
        self._round(closed_rid, survived=0)
        sage("close", "--run-id", closed_rid, "--result", "APPROVED", "--reason", "CONVERGED",
             "--iterations", "1", root=self.tmp)

        ko = sage("show", root=self.tmp)
        en = sage("show", root=self.tmp, lang="en")

        self.assertEqual(ko.returncode, en.returncode)
        self.assertIn("진행중", ko.stdout)
        self._assertNoKorean(en.stdout, "show --lang en stdout")
        self.assertIn(open_rid, en.stdout)
        self.assertIn("APPROVED/CONVERGED", en.stdout)           # 어휘는 감사 계약 — 번역 안 함

    def test_argparse_count_rejection_is_english(self):
        rid = self._open()
        common = ("round", "--run-id", rid, "--iteration", "1", "--survived", "0", "--accepted", "0")

        ko = sage(*common, "--found", "-1", root=self.tmp)
        en = sage(*common, "--found", "-1", root=self.tmp, lang="en")
        en_type = sage(*common, "--found", "abc", root=self.tmp, lang="en")

        self.assertEqual(ko.returncode, en.returncode)
        self.assertNotEqual(0, en.returncode)
        self._assertNoKorean(en.stderr, "round --found -1 --lang en stderr")
        self._assertNoKorean(en_type.stderr, "round --found abc --lang en stderr")


if __name__ == "__main__":
    unittest.main(verbosity=2)
