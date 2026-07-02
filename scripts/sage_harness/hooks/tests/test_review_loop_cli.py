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
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


def sage(*args, root=None):
    """python3 -m sage review-loop <args> 실행 → CompletedProcess."""
    cmd = [sys.executable, "-m", "sage", "review-loop", *args]
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
        rid = self._open()
        with open(os.path.join(self.tmp, ".sage", "loop_audit.jsonl"), encoding="utf-8") as f:
            rec = json.loads(f.readline())
        self.assertEqual(rec["cfg"]["refuters"], 3)
        self.assertEqual(rec["cfg"]["lenses"], ["security"])

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
        self.assertNotIn("loop_close", open(os.path.join(self.tmp, ".sage", "loop_audit.jsonl"), encoding="utf-8").read())

    def test_advisory_warns_but_proceeds(self):
        self._profile("advisory")
        rid = self._open_round(survived=2)
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("불일치", r.stderr)
        self.assertIn("advisory", r.stderr)
        self.assertIn("loop_close", open(os.path.join(self.tmp, ".sage", "loop_audit.jsonl"), encoding="utf-8").read())

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

    def test_enforce_degrades_on_integrity_warning(self):
        # P1: audit 무결성 경고(손상 줄) 있으면 enforce 라도 advisory 로 degrade → 불일치여도 진행.
        self._profile("enforce")
        rid = self._open_round(survived=2)   # APPROVED 와 모순될 상태
        with open(os.path.join(self.tmp, ".sage", "loop_audit.jsonl"), "a", encoding="utf-8") as f:
            f.write("{ corrupt line\n")   # 무결성 경고 유발
        r = sage("close", "--run-id", rid, "--result", "APPROVED", "--reason", "CONVERGED",
                 "--iterations", "1", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)   # degrade → 진행
        self.assertIn("degrade", r.stderr)

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
        before = open(path, encoding="utf-8").read()
        sage("next", "--run-id", rid, root=self.tmp)
        self.assertEqual(open(path, encoding="utf-8").read(), before)   # 감사 로그 불변


if __name__ == "__main__":
    unittest.main(verbosity=2)
