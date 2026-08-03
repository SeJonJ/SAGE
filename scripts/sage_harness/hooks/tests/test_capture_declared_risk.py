#!/usr/bin/env python3
"""capture-declared-risk reverse_extract 폐루프 검증.

3종 검증(설계 합의):
  1. core decision parity  — fixture 3종에 대해 core.decide 결정이 기대값과 일치 (런타임 중립)
  2. adapter end-to-end     — claude/codex adapter 를 실제 실행해 exit/state file/stdout snapshot 검증
  3. behavior parity        — 동일 입력에 claude/codex 의 decision(level/exit/state)은 동일, 출력 렌더만 다름

now_utc 는 SAGE_NOW_UTC 로 고정해 timestamp 결정론 확보.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)                      # scripts/sage_harness/hooks
FIXTURES = os.path.join(HERE, "fixtures", "capture_declared_risk")
ADAPTERS = os.path.join(HOOKS_DIR, "adapters")
FIXED_TS = "2026-06-13T00:00:00Z"

sys.path.insert(0, HOOKS_DIR)
import capture_declared_risk_core as core  # noqa: E402


def load_fixture(name):
    with open(os.path.join(FIXTURES, name + ".event.json"), encoding="utf-8") as f:
        return json.load(f)


# (fixture, expected_action, expected_level)
CASES = [
    ("capture_l3", "capture", "L3"),
    ("capture_meta", "noop", None),
    ("capture_none", "noop", None),
]


class TestCore(unittest.TestCase):
    def test_decision_parity(self):
        for name, action, level in CASES:
            ev = load_fixture(name)
            d = core.decide(ev)
            self.assertEqual(d["action"], action, name)
            self.assertEqual(d["level"], level, name)
            if action == "capture":
                self.assertEqual(d["state"]["ts"], FIXED_TS, name)
                self.assertEqual(d["state_file"], "declared-risk-test.json", name)
            else:
                self.assertIsNone(d["state"], name)

    def test_cleanup_declared(self):
        # cleanup 정책은 항상 선언됨 (capture/noop 무관)
        for name, _, _ in CASES:
            d = core.decide(load_fixture(name))
            self.assertEqual(d["cleanup"]["older_than_seconds"], 2 * 86400, name)


def run_adapter(runtime, fixture, project_root):
    """adapter 를 실제 실행. 런타임 raw stdin = {prompt, session_id}."""
    ev = load_fixture(fixture)
    raw = json.dumps({"prompt": ev["prompt"], "session_id": ev["session_id"]})
    env_root = "CLAUDE_PROJECT_DIR" if runtime == "claude" else "CODEX_PROJECT_ROOT"
    env = dict(os.environ, **{
        env_root: project_root,
        "SAGE_HOOK_CORE_DIR": HOOKS_DIR,
        "SAGE_NOW_UTC": FIXED_TS,
    })
    adapter = os.path.join(ADAPTERS, runtime, "capture-declared-risk.sh")
    p = subprocess.run(["bash", adapter], input=raw, capture_output=True, text=True, env=env)
    return p


def state_path(runtime, project_root):
    sub = ".claude" if runtime == "claude" else ".codex"
    return os.path.join(project_root, sub, "logs", "declared-risk-test.json")


def run_prompt(runtime, prompt, project_root, session_id="test"):
    """fixture 없이 임의 프롬프트로 adapter 실행 — 포착 규칙 코퍼스용."""
    raw = json.dumps({"prompt": prompt, "session_id": session_id})
    env_root = "CLAUDE_PROJECT_DIR" if runtime == "claude" else "CODEX_PROJECT_ROOT"
    env = dict(os.environ, **{env_root: project_root, "SAGE_HOOK_CORE_DIR": HOOKS_DIR,
                              "SAGE_NOW_UTC": FIXED_TS})
    adapter = os.path.join(ADAPTERS, runtime, "capture-declared-risk.sh")
    return subprocess.run(["bash", adapter], input=raw, capture_output=True, text=True, env=env)


# 실측 오탐. 가정 질문 한 문장이 L3 선언으로 잡혀 L2 사이클의 모든 편집이 2일간 막혔다.
MEASURED_FALSE_POSITIVE = ("특정 버그가 있을때 L3 개발을 1차로 한후 추가 개선을 위해 "
                           "다시 L2 로 개발을 하면 어떻게 되나요")


class TestCapturePrecision(unittest.TestCase):
    """포착은 좁히기만 한다 — 미포착은 다시 선언하면 되지만 오탐은 세션을 묶는다."""

    def _action(self, prompt):
        return core.decide({"prompt": prompt, "session_id": "s", "now_utc": FIXED_TS})

    def test_measured_false_positive_is_not_a_declaration(self):
        self.assertEqual(self._action(MEASURED_FALSE_POSITIVE)["action"], "noop")

    def test_plain_single_level_declaration_still_captured(self):
        for prompt, level in (("이번엔 L2 로 진행할게", "L2"), ("이 작업 L3 야", "L3"),
                              ("risk level 3 으로 진행", "L3"),
                              ("L2 로 시작해서 L2 로 마무리하자", "L2")):
            with self.subTest(prompt=prompt):
                d = self._action(prompt)
                self.assertEqual(d["action"], "capture")
                self.assertEqual(d["level"], level)

    def test_question_and_hypothetical_are_rejected(self):
        for prompt in ("L3 로 개발하면 어떻게 되나요?", "만약 L3 로 개발한다고 치면",
                       "L2 로 할까", "what if we go L3 로 개발"):
            with self.subTest(prompt=prompt):
                self.assertEqual(self._action(prompt)["action"], "noop")

    def test_multiple_declared_levels_are_ambiguous_not_max(self):
        # 옛 규칙은 max() 로 가장 높은 레벨을 골랐다. 서로 다른 레벨을 함께 선언하는 문장은
        # 비교·설명이므로 아무것도 고르지 않는다.
        for prompt in ("L2 로 하다가 L3 로 올릴 수도", "L2 로 진행할게. 아니 L3 로 할게."):
            with self.subTest(prompt=prompt):
                self.assertEqual(self._action(prompt)["action"], "noop")

    def test_bare_level_mention_does_not_discard_a_real_declaration(self):
        """모호함은 선언 시도로만 판정한다.

        접미사 없는 언급(캐시 레벨·파일명·코드블록)까지 세면 개발자 프롬프트에서 흔한 레벨
        언급 하나가 정당한 선언을 통째로 폐기한다 — 독립 리뷰가 재현한 회귀다.
        """
        cases = [("캐시는 L2 유지, 이번 작업은 L3 로 진행할게요.", "L3"),
                 ("L3.java 파일 수정 먼저 하고 이 작업은 L2 로 진행할게", "L2"),
                 ("이번 작업은 L2 로 진행할게.\n```python\ndef f(): pass  # L3 example\n```", "L2")]
        for prompt, level in cases:
            with self.subTest(prompt=prompt):
                d = self._action(prompt)
                self.assertEqual(d["action"], "capture")
                self.assertEqual(d["level"], level)

    def test_question_endings_only_count_at_sentence_end(self):
        """종결 어미를 무경계로 잡으면 평서형 동사에 걸려 같은 문장의 선언을 버린다.

        `지나가요`·`만나요` 안의 `가요`/`나요` 가 그 예다 — 독립 리뷰가 재현한 회귀다.
        """
        self.assertEqual(self._action("이슈가 지나가요 이번 작업은 L2 로 진행할게")["action"], "capture")
        self.assertEqual(self._action("L2 로 진행하나요")["action"], "noop")

    def test_version_and_filename_dots_do_not_split_sentences(self):
        """소수점·버전 표기에서 문장이 쪼개지면 가정 표지가 레벨과 분리돼 오탐이 된다.

        `만약 3.5 버전이면 L2 로 진행` 은 naive 분리에서 `만약 3.` / `5 … L2 로 진행` 이 되고,
        뒤 조각에는 가정 표지가 없으므로 L2 가 포착된다.
        """
        for prompt in ("만약 3.5 버전이면 L2 로 진행", "예를 들어 3.14 라면 L2 로 진행",
                       "만약 L3.java 라면 L2 로 진행"):
            with self.subTest(prompt=prompt):
                self.assertEqual(self._action(prompt)["action"], "noop")

    def test_ambiguous_rejection_is_announced_not_silent(self):
        """기각을 조용히 넘기면 선언했다고 믿은 채 진행하게 된다.

        포착 확인 메시지의 *부재* 가 유일한 신호인데 부재는 눈치채기 어렵다.
        UserPromptSubmit 은 exit 0 stdout 이 컨텍스트로 올라가는 이벤트라 안내가 실제로 보인다.
        """
        for prompt in ("로그 레벨은 L2 로 두고, 이 작업은 L3 로 진행할게요.",
                       "L2 로 하다가 L3 로 올릴 수도"):
            with self.subTest(prompt=prompt):
                d = self._action(prompt)
                self.assertEqual(d["action"], "noop")
                self.assertEqual(d["message_key"], "risk_declaration_ambiguous")

    def test_non_declaration_prompts_stay_silent(self):
        # 안내는 모호 기각에만 붙는다. 레벨을 말하지 않은 프롬프트나 가정 질문까지 알리면 잡음이 된다.
        for prompt in ("이거 고쳐줘", MEASURED_FALSE_POSITIVE, "L3 로 개발하면 어떻게 되나요?"):
            with self.subTest(prompt=prompt):
                self.assertIsNone(self._action(prompt)["message_key"])

    def test_ambiguous_advisory_reaches_both_runtimes(self):
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as root:
                p = run_prompt(runtime, "로그 레벨은 L2 로 두고, 이 작업은 L3 로 진행할게요.", root)
                self.assertEqual(p.returncode, 0)
                self.assertIn("미포착", p.stdout)
                self.assertFalse(os.path.exists(state_path(runtime, root)))

    def test_declaration_survives_a_neighbouring_question(self):
        # 문장 단위 판정이다 — 같은 프롬프트에 질문이 있어도 선언 문장은 살아야 한다.
        d = self._action("L3 는 뭐야? 아무튼 L3 로 진행할게")
        self.assertEqual(d["action"], "capture")
        self.assertEqual(d["level"], "L3")


class TestDeclarationClear(unittest.TestCase):
    """잘못 잡힌 선언의 탈출구. UserPromptSubmit 은 게이트 대상이 아니라 닭-달걀이 없다."""

    def test_clear_phrase_is_not_captured_as_declaration(self):
        for prompt in ("위험도 선언 해제", "risk 선언 취소해줘", "L3 아니야 위험도 선언 해제"):
            with self.subTest(prompt=prompt):
                d = core.decide({"prompt": prompt, "session_id": "s", "now_utc": FIXED_TS})
                self.assertEqual(d["action"], "clear")
                self.assertIsNone(d["level"])

    def test_clear_is_rejected_in_questions_and_negations(self):
        """해제는 안전장치를 끄는 행동이다. 질문·부정에서 발동하면 오탐 포착보다 나쁘다 —
        사용자가 명시적으로 반대한 방향으로 게이트를 약화시킨다. 독립 리뷰가 찾은 결함이다."""
        for prompt in ("위험도 선언 해제해야 하나요?", "위험도 선언 해제 안 하는 게 맞을까요?",
                       "위험도 선언 해제하지 않을 거예요", "위험도 선언 해제하지 마",
                       "이 프로젝트에는 위험도 선언 해제 기능이 있다던데, 그게 뭔가요?"):
            with self.subTest(prompt=prompt):
                d = core.decide({"prompt": prompt, "session_id": "s", "now_utc": FIXED_TS})
                self.assertEqual(d["action"], "noop")

    def test_clear_message_distinguishes_nothing_to_clear(self):
        # 지울 것이 없었는데 "지웠습니다" 로 안내하면 사용자가 원인 파악에 헤맨다.
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as root:
                absent = run_prompt(runtime, "위험도 선언 해제", root)
                self.assertIn("없었습니다", absent.stdout)
                run_prompt(runtime, "L3 로 진행할게", root)
                present = run_prompt(runtime, "위험도 선언 해제", root)
                self.assertIn("지웠습니다", present.stdout)

    def test_clear_wins_over_a_capturable_level_in_the_same_prompt(self):
        # 사용자는 무엇이 잘못 잡혔는지 말하면서 해제한다. 포착을 먼저 보면 그 설명이 다시
        # 선언으로 잡혀 탈출구가 닫힌다 — 해제 판정이 포착보다 앞서야 하는 이유다.
        d = core.decide({"prompt": "L3 로 잘못 잡혔어 위험도 선언 해제",
                         "session_id": "s", "now_utc": FIXED_TS})
        self.assertEqual(d["action"], "clear")
        self.assertIsNone(d["level"])

    def test_clear_removes_state_on_both_runtimes(self):
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as root:
                self.assertEqual(run_prompt(runtime, "L3 로 진행할게", root).returncode, 0)
                self.assertTrue(os.path.exists(state_path(runtime, root)))
                p = run_prompt(runtime, "위험도 선언 해제", root)
                self.assertEqual(p.returncode, 0)
                self.assertFalse(os.path.exists(state_path(runtime, root)))
                self.assertIn("해제", p.stdout)

    def test_clear_without_existing_state_is_not_an_error(self):
        # 사용자가 원한 최종 상태(선언 없음)는 파일 유무와 무관하게 같다.
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as root:
                p = run_prompt(runtime, "위험도 선언 해제", root)
                self.assertEqual(p.returncode, 0)
                self.assertEqual(p.stderr, "")


class TestAdapters(unittest.TestCase):
    def test_end_to_end(self):
        for runtime in ("claude", "codex"):
            for name, action, level in CASES:
                with tempfile.TemporaryDirectory() as root:
                    p = run_adapter(runtime, name, root)
                    self.assertEqual(p.returncode, 0, f"{runtime}/{name} exit")
                    sp = state_path(runtime, root)
                    if action == "capture":
                        self.assertTrue(os.path.exists(sp), f"{runtime}/{name} state file 생성")
                        with open(sp, encoding="utf-8") as f:
                            st = json.load(f)
                        self.assertEqual(st["level"], level, f"{runtime}/{name} level")
                        self.assertEqual(st["ts"], FIXED_TS, f"{runtime}/{name} ts 결정론")
                        # 출력 프로토콜은 런타임마다 다름
                        if runtime == "claude":
                            self.assertIn("[Risk 선언 포착]", p.stdout)
                            self.assertNotIn("hookSpecificOutput", p.stdout)
                        else:
                            self.assertIn("hookSpecificOutput", p.stdout)
                            doc = json.loads(p.stdout)
                            self.assertIn("additionalContext", doc["hookSpecificOutput"])
                    else:
                        self.assertFalse(os.path.exists(sp), f"{runtime}/{name} 파일 미생성")
                        self.assertNotIn("포착", p.stdout, f"{runtime}/{name} 출력 없음")

    def test_behavior_parity_between_runtimes(self):
        # 동일 입력: claude/codex 의 state(level/ts)는 동일, stdout 렌더만 다름
        for name, action, level in CASES:
            if action != "capture":
                continue
            with tempfile.TemporaryDirectory() as r1, tempfile.TemporaryDirectory() as r2:
                pc = run_adapter("claude", name, r1)
                px = run_adapter("codex", name, r2)
                with open(state_path("claude", r1), encoding="utf-8") as f:
                    sc = json.load(f)
                with open(state_path("codex", r2), encoding="utf-8") as f:
                    sx = json.load(f)
                self.assertEqual(sc, sx, f"{name} state 동일(behavior parity)")
                self.assertNotEqual(pc.stdout, px.stdout, f"{name} 출력 렌더는 달라야")


if __name__ == "__main__":
    unittest.main(verbosity=2)
