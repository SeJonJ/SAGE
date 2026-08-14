#!/usr/bin/env python3
"""실행 host 판별과 active_host: auto — cross-check 리뷰어 오선택 차단.

배경: `sage cross-check` 가 프로필 `runtime.active_host` 만 보고 peer 를 정해서, 프로필과 실제
실행 host 가 어긋나면 현재 실행 중인 host 자신이 리뷰어로 뽑혔다(cross-model 독립성 무력화).

`active_host` 를 손으로 맞추게 하는 해법은 성립하지 않는다 — 이 키는 shared profile 에만 둘 수
있고(local 이 덮지 못함) 그 파일은 커밋되며 게이트 정책 소스라 L2 다. host 를 옮길 때마다 PDCA
게이트를 통과해 공유 파일을 고치라는 뜻이 된다. 그래서 `auto` + 실행 관측으로 답한다.

여기서 못박는 것:
  1. env 표식으로 실행 host 판별. 두 계열이 동시에 보이면(중첩) 모호 → 판별 실패
  2. peer spawn 시 부모 표식 제거 — 상속으로 인한 자기 host 오인 차단
  3. `auto` 해석 순서: 선언 → 관측 → 단일 installed_hosts
  4. 리뷰어 선택은 감지가 pin 을 이긴다(pin 만 믿으면 원래 버그가 그대로 재발)
  5. 불일치는 차단이 아니라 통지, 그리고 stdout 오염 금지
"""
import os
import sys
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)

from sage.commands.review import (_model_for_peer, cross_model_issues,        # noqa: E402
                                  host_detection_notes, possible_peers)
from sage.model_routing import peer_candidates, reviewer_selection  # noqa: E402
from sage.runtime_hosts import (AUTO, HOST_ENV_VAR, active_host, declared_active_host,  # noqa: E402
                                declared_installed_hosts, detect_current_host, peer_env,
                                profile_issues, running_host)

CLAUDE_ENV = {"CLAUDECODE": "1"}
CODEX_ENV = {"CODEX_SANDBOX": "seatbelt", "CODEX_CI": "1", "CODEX_THREAD_ID": "t-1"}


def _profile(installed=("claude", "codex"), active=AUTO, **extra):
    profile = {"runtime": {"installed_hosts": list(installed), "active_host": active},
               "options": {"cross_model": True}}
    profile.update(extra)
    return profile


class TestDetection(unittest.TestCase):
    def test_single_family_resolves(self):
        self.assertEqual("claude", detect_current_host(dict(CLAUDE_ENV)))
        self.assertEqual("codex", detect_current_host(dict(CODEX_ENV)))

    def test_any_single_codex_marker_is_enough(self):
        for marker in CODEX_ENV:
            self.assertEqual("codex", detect_current_host({marker: "1"}), marker)

    def test_nested_execution_is_ambiguous_not_a_guess(self):
        """자식이 부모 env 를 상속하므로 두 계열이 동시에 보인다(실측). 방향은 알 수 없다.

        한쪽을 고르면 조용히 틀린 답이 나오므로 판별 실패로 둔다.
        """
        nested = dict(CLAUDE_ENV, **CODEX_ENV)
        self.assertIsNone(detect_current_host(nested))

    def test_no_markers_is_not_a_guess(self):
        self.assertIsNone(detect_current_host({}))
        self.assertIsNone(detect_current_host({"PATH": "/usr/bin"}))

    def test_explicit_marker_resolves_nesting(self):
        # SAGE 가 peer 를 띄울 때 심는 값 — 상속으로 흐려진 상태를 되돌린다.
        nested = dict(CLAUDE_ENV, **CODEX_ENV)
        nested[HOST_ENV_VAR] = "codex"
        self.assertEqual("codex", detect_current_host(nested))

    def test_explicit_marker_is_validated(self):
        self.assertIsNone(detect_current_host({HOST_ENV_VAR: "bogus"}))


class TestPeerEnv(unittest.TestCase):
    def test_parent_markers_are_stripped_and_child_declared(self):
        env = peer_env("codex", dict(CLAUDE_ENV, PATH="/usr/bin"))
        self.assertNotIn("CLAUDECODE", env)
        self.assertEqual("codex", env[HOST_ENV_VAR])
        self.assertEqual("/usr/bin", env["PATH"])          # 나머지 환경은 보존
        self.assertEqual("codex", detect_current_host(env))

    def test_both_families_are_stripped(self):
        env = peer_env("claude", dict(CLAUDE_ENV, **CODEX_ENV))
        self.assertEqual("claude", detect_current_host(env))


class TestAutoResolution(unittest.TestCase):
    def test_declared_pin_is_reported_and_auto_is_not(self):
        self.assertEqual("codex", declared_active_host(_profile(active="codex")))
        self.assertIsNone(declared_active_host(_profile(active=AUTO)))
        self.assertIsNone(declared_active_host({"runtime": {}}))

    def test_auto_uses_observation(self):
        with mock.patch.dict(os.environ, {HOST_ENV_VAR: "codex"}):
            self.assertEqual("codex", active_host(_profile(active=AUTO)))

    def test_auto_without_observation_falls_back_to_sole_installed_host(self):
        profile = _profile(installed=["codex"], active=AUTO)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual("codex", active_host(profile))

    def test_explicit_pin_still_wins_for_active_host(self):
        # 하위호환: 이미 값을 박아둔 프로필은 그대로 동작해야 한다.
        with mock.patch.dict(os.environ, {HOST_ENV_VAR: "codex"}):
            self.assertEqual("claude", active_host(_profile(active="claude")))

    def test_auto_passes_profile_validation(self):
        self.assertEqual([], [m for sev, m in profile_issues(_profile(active=AUTO)) if sev == "FAIL"])

    def test_auto_membership_is_not_judged_statically(self):
        """auto 는 실행 시점에 정해지므로 installed_hosts 소속을 정적으로 따질 대상이 없다.

        여기서 실측을 끌어들이면 같은 프로필이 도는 host 에 따라 통과/실패가 갈린다.
        """
        profile = _profile(installed=["codex"], active=AUTO)
        with mock.patch.dict(os.environ, dict(CLAUDE_ENV)):
            self.assertEqual([], [m for sev, m in profile_issues(profile) if sev == "FAIL"])

    def test_invalid_active_host_still_fails(self):
        failures = [m for sev, m in profile_issues(_profile(active="gpt")) if sev == "FAIL"]
        # 판정은 언어 중립 code 다. 문구는 catalog 소유라 여기서 고정하지 않는다.
        codes = {getattr(m, "code", m) for m in failures}
        self.assertTrue(any("active_host" in code or "invalid_value" in code for code in codes),
                        f"active_host 판정이 없다: {codes}")

    def test_declared_installed_hosts_separates_claim_from_fallback(self):
        self.assertEqual(["claude", "codex"], declared_installed_hosts(_profile()))
        self.assertIsNone(declared_installed_hosts({"runtime": {"host": "claude"}}))
        self.assertIsNone(declared_installed_hosts({"runtime": {"installed_hosts": "both"}}))


class TestReviewerNeverReviewsItself(unittest.TestCase):
    def test_detection_beats_a_stale_pin(self):
        """pin 만 믿으면 원래 버그가 그대로 재발한다 — 감지가 이겨야 한다."""
        stale = _profile(active="claude")      # 프로필은 claude, 실제로는 codex 실행
        self.assertEqual("claude", reviewer_selection(stale, "codex")[0])
        self.assertEqual("codex", reviewer_selection(stale, "claude")[0])

    def test_peer_is_never_the_running_host(self):
        for current in ("claude", "codex"):
            for active in ("claude", "codex", AUTO):
                peer, _ = reviewer_selection(_profile(active=active), current)
                self.assertNotEqual(current, peer, f"current={current} active={active}")

    def test_explicit_reviewer_host_is_dropped_when_it_is_the_running_host(self):
        profile = _profile(active=AUTO)
        profile["cross_model"] = {"reviewer": {"host": "codex", "model": "m"}}
        self.assertEqual("codex", reviewer_selection(profile, "claude")[0])   # 충돌 없음
        self.assertEqual("claude", reviewer_selection(profile, "codex")[0])   # 자기리뷰 → 무시
        self.assertEqual("m", reviewer_selection(profile, "codex")[1])        # model 은 그대로

    def test_single_installed_host_leaves_no_peer(self):
        profile = _profile(installed=["claude"], active="claude")
        self.assertEqual([], peer_candidates(profile, "claude"))
        # 후보가 없어도 자기 자신을 돌려주지는 않는다 — CLI 가용성 검사가 걸러 BLOCKED 가 된다.
        self.assertEqual("codex", reviewer_selection(profile, "claude")[0])

    def test_selection_is_pure(self):
        """같은 입력이면 실행 환경과 무관하게 같은 답. env 를 읽으면 테스트조차 host 에 좌우된다."""
        profile = _profile(active="claude")
        for env in ({}, dict(CLAUDE_ENV), dict(CODEX_ENV)):
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual("codex", reviewer_selection(profile, "claude")[0])
                # 판별 불가면 프로필로 내려간다: pin=claude 의 반대는 codex.
                self.assertEqual("codex", reviewer_selection(profile, None)[0])


class TestUnknownRunningHostIsNotGuessed(unittest.TestCase):
    """Codex 리뷰가 잡은 구멍: 판별 실패 후 프로필 폴백이 실행 host 를 peer 로 되돌렸다.

    중첩 실행(실측된 상태)에서 감지는 None 이 되고, `active_host()` 는 dual-host 라 default
    `claude` 를 돌려주며, opposite 는 `codex` 가 된다 — 실제 실행이 codex 면 자기리뷰다.
    독립성이 걸린 경로는 근거가 없으면 고르지 말고 멈춰야 한다.
    """

    def test_running_host_refuses_to_guess_when_nested(self):
        nested = dict(CLAUDE_ENV, **CODEX_ENV)
        with mock.patch.dict(os.environ, nested, clear=True):
            self.assertIsNone(running_host(_profile(active=AUTO)))

    def test_explicit_host_resolves_the_ambiguity(self):
        nested = dict(CLAUDE_ENV, **CODEX_ENV)
        with mock.patch.dict(os.environ, nested, clear=True):
            self.assertEqual("codex", running_host(_profile(active=AUTO), "codex"))

    def test_pin_is_used_only_when_nothing_was_observed(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual("claude", running_host(_profile(active="claude")))
        # 관측이 있으면 pin 보다 관측이 앞선다.
        with mock.patch.dict(os.environ, dict(CODEX_ENV), clear=True):
            self.assertEqual("codex", running_host(_profile(active="claude")))

    def test_sole_installed_host_is_the_last_resort(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual("codex", running_host(_profile(installed=["codex"], active=AUTO)))
            self.assertIsNone(running_host(_profile(active=AUTO)))   # dual + 근거 없음 → 추측 금지

    def test_the_reported_self_review_path_is_closed(self):
        """BLOCK 재현 시나리오 전체 — 이제 peer 를 고르는 지점에 도달하지 않는다."""
        nested = dict(CLAUDE_ENV, **CODEX_ENV)
        profile = _profile(active=AUTO)
        with mock.patch.dict(os.environ, nested, clear=True):
            self.assertIsNone(detect_current_host())
            self.assertEqual("claude", active_host(profile))          # default 폴백은 그대로지만
            self.assertIsNone(running_host(profile))                  # 독립성 판정은 이걸 안 쓴다


class TestPeerSpecificSettings(unittest.TestCase):
    """model·effort 는 peer 런타임 종속이라 실제 peer 기준으로 해석해야 한다."""

    def test_model_is_dropped_when_chosen_for_another_peer(self):
        profile = _profile(active=AUTO)
        profile["cross_model"] = {"reviewer": {"host": "codex", "model": "gpt-5.6-terra"}}
        model, note = _model_for_peer(profile, "codex", "gpt-5.6-terra")
        self.assertEqual("gpt-5.6-terra", model)
        self.assertIsNone(note)
        model, note = _model_for_peer(profile, "claude", "gpt-5.6-terra")
        self.assertIsNone(model)                     # codex 용 모델을 claude 에 넘기지 않는다
        # 판정은 문구가 아니라 code·인자로 확인한다 — 문안은 catalog 소유다.
        self.assertEqual("review.model_for_other_peer", note.code)
        self.assertEqual("codex", note.arguments["chosen_for"])
        self.assertEqual("claude", note.arguments["peer"])

    def test_possible_peers_widen_under_auto(self):
        self.assertEqual(["codex"], possible_peers(_profile(active="claude")))
        self.assertEqual(["claude", "codex"], possible_peers(_profile(active=AUTO)))

    def test_effort_must_be_valid_for_every_possible_peer_under_auto(self):
        # max 는 claude 어휘, minimal 은 codex 어휘 — auto 면 어느 쪽이 peer 가 될지 모른다.
        for effort in ("max", "minimal"):
            profile = _profile(active=AUTO)
            profile["cross_model"] = {"effort": effort}
            fails = [m for sev, m in cross_model_issues(profile) if sev == "FAIL"]
            self.assertTrue(fails, effort)

    def test_shared_vocabulary_passes_under_auto(self):
        for effort in ("low", "medium", "high", "xhigh"):
            profile = _profile(active=AUTO)
            profile["cross_model"] = {"effort": effort}
            fails = [m for sev, m in cross_model_issues(profile) if sev == "FAIL"]
            self.assertEqual([], fails, effort)


class TestMismatchIsToldNotEnforced(unittest.TestCase):
    def test_stale_pin_produces_a_note_with_the_escape(self):
        notes = host_detection_notes(_profile(active="claude"), "codex")
        self.assertEqual(1, len(notes))
        self.assertEqual("review.host_declared_mismatch", notes[0].code)
        self.assertEqual("claude", notes[0].arguments["declared"])
        self.assertEqual("codex", notes[0].arguments["detected"])
        # 다음 행동 안내(auto 로 두면 사라진다)는 catalog 문안이 담는다 — 양 언어 모두에 있어야 한다.
        from sage.i18n import ko as _ko, en as _en
        self.assertIn("auto", _ko.MESSAGES["cli.review.host_declared_mismatch"])
        self.assertIn("auto", _en.MESSAGES["cli.review.host_declared_mismatch"])

    def test_auto_profile_is_silent(self):
        self.assertEqual([], host_detection_notes(_profile(active=AUTO), "codex"))

    def test_detected_host_missing_from_receipt_is_reported(self):
        notes = host_detection_notes(_profile(installed=["claude"], active=AUTO), "codex")
        self.assertEqual(1, len(notes))
        self.assertEqual("review.host_not_in_installed", notes[0].code)
        self.assertEqual("codex", notes[0].arguments["detected"])
        self.assertEqual(["claude"], notes[0].arguments["installed"])

    def test_no_detection_means_nothing_to_say(self):
        self.assertEqual([], host_detection_notes(_profile(active="claude"), None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
