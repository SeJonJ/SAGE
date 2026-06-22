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


if __name__ == "__main__":
    unittest.main(verbosity=2)
