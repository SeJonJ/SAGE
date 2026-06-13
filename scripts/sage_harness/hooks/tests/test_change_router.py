#!/usr/bin/env python3
"""sage change 라우터 검증 (step9 — 결정론 키워드 라우팅).

4케이스: 매칭→generate 수정 / 무매칭+kind→신규 generate / 모호→후보 / absorb 키워드→absorb.
순수 함수(_classify_action/_kind_hint/_score) 단위 검증 + run() 통합(exit 0).
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import change as C  # noqa: E402


class Args:
    def __init__(self, intent):
        self.intent = intent
        self.root = None


def run_change(intent):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = C.run(Args(intent))
    return rc, buf.getvalue()


class TestPure(unittest.TestCase):
    def test_action_absorb_priority(self):
        self.assertEqual(C._classify_action("이미 직접 수정했어"), "absorb")
        self.assertEqual(C._classify_action("기능 수정해줘"), "generate")

    def test_kind_hint(self):
        self.assertEqual(C._kind_hint("새 hook 만들어"), "hook")
        self.assertEqual(C._kind_hint("agent 고쳐"), "agent")
        self.assertIsNone(C._kind_hint("그냥 고쳐"))

    def test_score_no_token_no_bonus(self):
        # 토큰 매칭 0 → kind 보너스만으로 후보 안 됨
        self.assertEqual(C._score({"새", "만들어"}, "hooks/capture-declared-risk", "hook"), 0.0)

    def test_score_match(self):
        s = C._score({"capture", "declared", "risk"}, "hooks/capture-declared-risk", "hook")
        self.assertGreaterEqual(s, 1.0)


class TestRun(unittest.TestCase):
    def test_match_modify(self):
        rc, out = run_change("capture-declared-risk hook 고쳐줘")
        self.assertEqual(rc, 0)
        self.assertIn("GENERATE (기존 자산 수정)", out)
        self.assertIn("hooks/capture-declared-risk", out)
        self.assertIn("승인상태", out)

    def test_new(self):
        rc, out = run_change("새 hook 만들어줘")
        self.assertEqual(rc, 0)
        self.assertIn("신규 hook", out)

    def test_ambiguous(self):
        # 'convention' 은 backend-convention/frontend-convention 동점 → 모호 (skill 등록 후 셋 반영)
        rc, out = run_change("convention 수정")
        self.assertEqual(rc, 0)
        self.assertIn("후보", out)

    def test_absorb(self):
        rc, out = run_change("이미 .claude/agents 직접 수정했어")
        self.assertEqual(rc, 0)
        self.assertIn("ABSORB", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
