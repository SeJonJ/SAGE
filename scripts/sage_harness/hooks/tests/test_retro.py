#!/usr/bin/env python3
"""sage retro 단위 — Loop C(Act→Plan process-absorb) 증거 수집 + distiller 제시(자동반영 없음).

검증:
  1. loop_audit run + 05 문서 → 감사요약·문서경로·distiller 프롬프트·human-gate 경로 출력
  2. --run-id 특정 / --feature 경로 필터
  3. loop_audit 없음 → 안내(여전히 05 문서/프롬프트 제시)
  4. 05 문서 없음 → 안내
  5. proposal-only: 어떤 파일도 쓰지 않음(자동반영 없음)
  6. 루트 자동탐색(profile 마커)
  7. 무결성 경고 표면화
"""
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


def sage_review_loop(*args, root):
    subprocess.run([sys.executable, "-m", "sage", "review-loop", *args, "--root", root],
                   cwd=REPO, capture_output=True, text=True)


def retro(*args, root, cwd=None):
    cmd = [sys.executable, "-m", "sage", "retro", *args]
    if root:
        cmd += ["--root", root]
    return subprocess.run(cmd, cwd=cwd or REPO, capture_output=True, text=True)


class TestRetro(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "sage"), exist_ok=True)
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("pdca:\n  approve_phase: \"05\"\n  phases:\n"
                    "    - { id: \"05\", glob: \"plan_docs/05-expert-review/**/*.md\" }\n"
                    "  review_loop: { enabled: true, lenses: [security], refuters: 2 }\n")

    def _add_05(self, stem="feat-x"):
        d = os.path.join(self.tmp, "plan_docs", "05-expert-review")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"{stem}-review.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("## Phase-05 Review\nFinal Status: APPROVED\n")
        return p

    def _run_loop(self, risk="L3"):
        r = subprocess.run([sys.executable, "-m", "sage", "review-loop", "open", "--risk", risk, "--root", self.tmp],
                           cwd=REPO, capture_output=True, text=True)
        rid = r.stdout.strip().splitlines()[0]
        sage_review_loop("round", "--run-id", rid, "--iteration", "1", "--found", "7",
                         "--survived", "3", "--accepted", "3", "--tokens", "48000", root=self.tmp)
        sage_review_loop("close", "--run-id", rid, "--result", "APPROVED", "--reason", "DRY",
                         "--iterations", "1", root=self.tmp)
        return rid

    def test_full_evidence_and_prompt(self):
        rid = self._run_loop()
        self._add_05()
        r = retro(root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(rid, r.stdout)
        self.assertIn("accepted=3", r.stdout)         # 감사 요약
        self.assertIn("feat-x-review.md", r.stdout)   # 05 문서
        self.assertIn("distiller", r.stdout)          # 프롬프트
        self.assertIn("자동반영", r.stdout)            # human-gate 경고

    def test_proposal_only_writes_nothing(self):
        self._run_loop()
        self._add_05()
        before = set()
        for dp, _, fs in os.walk(self.tmp):
            for fn in fs:
                before.add(os.path.join(dp, fn))
        retro(root=self.tmp)
        after = set()
        for dp, _, fs in os.walk(self.tmp):
            for fn in fs:
                after.add(os.path.join(dp, fn))
        self.assertEqual(before, after, "retro 가 파일을 생성/수정함(자동반영 금지 위반)")

    def test_no_loop_audit_still_runs(self):
        self._add_05()
        r = retro(root=self.tmp)   # loop_audit 없음
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("기록 없음", r.stdout)
        self.assertIn("feat-x-review.md", r.stdout)   # 05 문서는 여전히 제시

    def test_no_05_doc_noted(self):
        self._run_loop()           # 05 문서 없음
        r = retro(root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("없음", r.stdout)

    def test_feature_filter(self):
        self._run_loop()
        self._add_05("alpha")
        self._add_05("beta")
        r = retro("--feature", "alpha", root=self.tmp)
        self.assertIn("alpha-review.md", r.stdout)
        self.assertNotIn("beta-review.md", r.stdout)

    def test_feature_filter_token_boundary(self):
        # codex S4 P3: 'loop' 이 'preloop' 을 오매치하면 안 됨(토큰 경계 매치).
        self._run_loop()
        self._add_05("loop-engineering")
        self._add_05("preloop")
        r = retro("--feature", "loop", root=self.tmp)
        self.assertIn("loop-engineering-review.md", r.stdout)
        self.assertNotIn("preloop-review.md", r.stdout)

    def test_feature_filter_dot_left_boundary(self):
        # codex S4: 좌측 경계 '.' 포함 — alpha.loop-review.md 가 --feature loop 에 매치(주석 -/_/. 일치).
        self._run_loop()
        self._add_05("alpha.loop")
        r = retro("--feature", "loop", root=self.tmp)
        self.assertIn("alpha.loop-review.md", r.stdout)

    def test_corrupt_audit_line_surfaced(self):
        # codex S4 P2: 손상/비-dict 줄이 silent drop 되어도 retro 가 증거 불완전을 경고.
        self._run_loop()
        self._add_05()
        path = os.path.join(self.tmp, ".sage", "loop_audit.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write("{ truncated not json\n")
            f.write("42\n")   # valid-but-non-dict
        r = retro(root=self.tmp)
        self.assertIn("무결성", r.stdout)
        self.assertIn("손상", r.stdout)

    def test_root_autodiscovery_from_subdir(self):
        self._run_loop()
        self._add_05()
        subdir = os.path.join(self.tmp, "src", "deep")
        os.makedirs(subdir, exist_ok=True)
        r = subprocess.run([sys.executable, "-m", "sage", "retro"], cwd=subdir,
                           capture_output=True, text=True, env={**os.environ, "PYTHONPATH": REPO})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("feat-x-review.md", r.stdout)   # 루트 자동탐색 성공

    def test_integrity_warning_surfaced(self):
        # orphan round(라이브러리 직접) → retro 가 무결성 경고 표면화.
        sys.path.insert(0, os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime"))
        import loop_audit as la
        la.record_round(self.tmp, "rl-ghost", 1, 1, 0, 0, 0, 10)
        self._add_05()
        r = retro(root=self.tmp)
        self.assertIn("무결성", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
