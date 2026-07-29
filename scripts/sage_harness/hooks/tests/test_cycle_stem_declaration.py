#!/usr/bin/env python3
"""EH-7 — 장수 브랜치 cycle stem 해석: 안내 정확성 + 선언 통로 감사.

배경(ChatForYou 실측): 사이클마다 브랜치를 따지 않는 장수 브랜치에서는 비-phase 편집의 stem 이
브랜치 leaf 에서 추론되어 실제 사이클과 영영 어긋난다. 00~03 문서가 전부 있는데도 "의무 PDCA
phase 미작성" BLOCK 이 걸리고, 안내는 "문서를 작성하세요" 라 방향이 틀렸다. 탈출구인
SAGE_CYCLE_STEM 은 문서에도 출력에도 없었고, 그 선언이 게이트를 통과시킨 사실도 남지 않았다.

여기서 못박는 것:
  1. 추론(branch-leaf) BLOCK 은 추론 사실과 선언 경로를 안내한다 — 경로 유래 stem 에는 오안내 없음
  2. 선언하면 같은 스냅샷이 통과한다(게이트를 끄는 게 아니라 올바른 사이클을 주는 것)
  3. 선언된 stem 은 판정에 스탬프되고, OK 줄에도 노출된다(낡은 선언이 보이게)
  4. 선언 사용은 .sage/override.jsonl 에 세션·stem 단위 1회 기록되며, 기록 실패 시 통과 금지
"""
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
import io as _io
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
RUNTIME = os.path.join(HOOKS_DIR, "runtime")
sys.path.insert(0, RUNTIME)
sys.path.insert(0, HOOKS_DIR)
import pre_implementation_gate_core as core   # noqa: E402
import messages                               # noqa: E402


# 권한 캐시가 저장소 밖 상태 디렉터리로 옮겨졌다(10-e). 격리하지 않으면 테스트가 개발자의 실제
# ~/.local/state/sage 를 오염시킨다. 파일 전체에 강제한다.
_STATE_TMP = None


def setUpModule():
    global _STATE_TMP
    _STATE_TMP = tempfile.TemporaryDirectory()
    os.environ["SAGE_STATE_HOME"] = _STATE_TMP.name


def tearDownModule():
    os.environ.pop("SAGE_STATE_HOME", None)
    _STATE_TMP.cleanup()

import override_audit as ov                   # noqa: E402
import hook_runtime as hr                     # noqa: E402

GATE = "pre-implementation-gate"
LONG_BRANCH = "chatforyou_v2_sage"
REAL_STEM = "sage_project_profile_refresh"

PDCA_PROFILE = {
    "risk": {"l0_pass_globs": ["*plan_docs/*", "*.md"], "l2_path_globs": ["*backend/*.java"]},
    "pdca": {
        "enabled": True,
        "phases": [{"id": pid, "glob": f"plan_docs/{pid}-x/**/*.md"} for pid in
                   ("00", "01", "02", "03")],
        "pre_implementation_required": {"L2": ["00", "01", "02", "03"]},
    },
}


def _pdoc(stem, risk=""):
    risk_line = f"Risk Level: {risk}\n" if risk else ""
    return {"path": f"{stem}.md",
            "content": f"Cycle-Stem: `{stem}`\n{risk_line}", "recent": True}


def _complete_snapshot(stem):
    """실제 사이클 stem 으로 00~03 이 모두 갖춰진 스냅샷 — 결핍이 아닌 상태."""
    return {"plan_files": [_pdoc(stem)], "review_candidates": [],
            "phase_docs": {
                "00": [_pdoc(stem, risk="L2")],
                "01": [_pdoc(stem)],
                "02": [_pdoc(stem)],
                "03": [_pdoc(stem)],
            }}


def _event(cycle_stem="", branch=LONG_BRANCH, path="backend/App.java"):
    return {"hook_id": GATE, "runtime": "test", "branch": branch, "session_id": "sess-1",
            "cycle_stem": cycle_stem, "declared_max": None,
            "changes": [{"path": path, "op": "write", "content": "x"}]}


class TestLongLivedBranchMisbinding(unittest.TestCase):
    """장수 브랜치에서 문서가 다 있는데도 막히는 상태를 재현하고, 안내가 맞는지 본다."""

    def test_complete_cycle_still_blocks_when_stem_is_inferred_from_branch(self):
        d = core.decide(_event(), PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        self.assertEqual(d["message_key"], "block_cycle_risk_declaration")
        # 판정은 그대로지만 출처는 이제 밖으로 나온다 — 이게 오안내를 고칠 재료다.
        self.assertEqual(d["cycle_source"], ["branch-leaf"])
        self.assertEqual(d["cycle_stem"], LONG_BRANCH)
        self.assertFalse(d["cycle_stem_declared"])

    def test_declaring_the_real_stem_passes_the_same_snapshot(self):
        d = core.decide(_event(cycle_stem=REAL_STEM), PDCA_PROFILE,
                        _complete_snapshot(REAL_STEM), None)
        self.assertEqual(d["message_key"], "ok_l2")
        self.assertEqual(d["exit_code"], 0)
        self.assertEqual(d["cycle_stem"], REAL_STEM)
        self.assertTrue(d["cycle_stem_declared"])
        self.assertEqual(d["cycle_source"], ["event"])

    def test_phase_write_binds_from_path_not_branch(self):
        # phase 문서 편집은 경로에서 stem 을 얻는다(위조 불가) — 브랜치는 신호가 아니다.
        event = {"hook_id": GATE, "branch": LONG_BRANCH, "session_id": "s",
                 "changes": [{"path": f"plan_docs/01-x/{REAL_STEM}.md", "op": "write",
                              "content": f"Cycle-Stem: `{REAL_STEM}`\n"}]}
        d = core.decide(event, PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        self.assertEqual(d["cycle_stem"], REAL_STEM)
        self.assertEqual(d["cycle_source"], [f"plan_docs/01-x/{REAL_STEM}.md"])

    def test_pdca_disabled_is_not_stamped(self):
        d = core.decide(_event(), {"risk": {"l2_paths": ["**/*.java"]}}, {}, None)
        self.assertNotIn("cycle_stem", d)
        self.assertNotIn("cycle_stem_declared", d)


class TestHintPointsAtTheRealEscape(unittest.TestCase):
    """차단 안내가 원인에 맞는 탈출구를 가리키는지. 오안내는 없는 문서를 다시 쓰게 만든다."""

    def _render(self, decision):
        return messages.gate_text(decision, {}, "claude")

    def test_inferred_stem_block_names_declaration_and_the_inferred_leaf(self):
        d = core.decide(_event(), PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        text = self._render(d)
        self.assertIn("SAGE_CYCLE_STEM", text)
        self.assertIn(LONG_BRANCH, text)          # 무엇으로 추론했는지 보여야 함
        self.assertIn("추론", text)

    def test_path_bound_stem_block_does_not_suggest_declaration(self):
        # 경로에서 stem 을 얻은 결핍은 진짜 문서 부재다 — 여기서 선언을 권하면 우회를 가르치는 셈이다.
        docs = {"00": [_pdoc(REAL_STEM, risk="L2")]}
        event = {"hook_id": GATE, "branch": LONG_BRANCH, "session_id": "s",
                 "changes": [{"path": f"plan_docs/00-x/{REAL_STEM}.md", "op": "write",
                              "content": f"Cycle-Stem: `{REAL_STEM}`\n"},
                             {"path": "backend/App.java", "op": "write", "content": "x"}]}
        d = core.decide(event, PDCA_PROFILE,
                        {"plan_files": [], "review_candidates": [], "phase_docs": docs}, None)
        self.assertEqual(d["message_key"], "block_phase_incomplete")
        text = self._render(d)
        self.assertNotIn("SAGE_CYCLE_STEM", text)
        self.assertIn("pdca-templates.md", text)

    def test_binding_failure_on_non_phase_edit_offers_declaration(self):
        # 브랜치 leaf 조차 못 쓰는 상태(브랜치 없음) → "파일명을 맞추라" 만으로는 나갈 길이 없다.
        event = dict(_event(), branch="")
        d = core.decide(event, PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        self.assertEqual(d["message_key"], "block_cycle_binding")
        self.assertIn("SAGE_CYCLE_STEM", self._render(d))

    def test_declared_stem_is_visible_on_pass(self):
        d = core.decide(_event(cycle_stem=REAL_STEM), PDCA_PROFILE,
                        _complete_snapshot(REAL_STEM), None)
        text = self._render(d)
        self.assertIn(REAL_STEM, text)
        self.assertIn("SAGE_CYCLE_STEM 선언", text)

    def test_both_runtimes_carry_the_same_guidance(self):
        d = core.decide(_event(), PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        for runtime in ("claude", "codex"):
            self.assertIn("SAGE_CYCLE_STEM", messages.gate_text(d, {}, runtime), runtime)


class TestDeclarationIsAudited(unittest.TestCase):
    """선언 통로 자체는 막지 않는다. 다만 무흔적 통과는 남기지 않는다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def _records(self):
        return [r for r in ov.read_records(self.root) if r.get("event") == "cycle_stem_declared"]

    def test_declaration_is_recorded_once_per_session_and_stem(self):
        first = ov.record_cycle_stem_declaration(self.root, GATE, REAL_STEM, "sess-1", status="ok")
        again = ov.record_cycle_stem_declaration(self.root, GATE, REAL_STEM, "sess-1", status="ok")
        self.assertIsNotNone(first)
        self.assertIsNone(again)           # 게이트는 편집마다 발동한다 — 같은 사실로 부풀지 않아야
        self.assertEqual(len(self._records()), 1)
        self.assertEqual(first["cycle_stem"], REAL_STEM)

    def test_different_session_or_stem_is_a_separate_fact(self):
        ov.record_cycle_stem_declaration(self.root, GATE, REAL_STEM, "sess-1")
        ov.record_cycle_stem_declaration(self.root, GATE, REAL_STEM, "sess-2")
        ov.record_cycle_stem_declaration(self.root, GATE, "other_cycle", "sess-1")
        self.assertEqual(len(self._records()), 3)

    def test_audit_lives_in_the_committed_log_not_the_local_grant_cache(self):
        # 선언은 권한 부여가 아니라 사후 추적이다 — 권한 캐시를 오염시키면 안 된다.
        ov.record_cycle_stem_declaration(self.root, GATE, REAL_STEM, "sess-1")
        self.assertTrue(os.path.exists(ov.audit_path(self.root)))
        self.assertFalse(os.path.exists(ov.grants_path(self.root)))
        self.assertEqual(ov.active_grants(self.root), [])

    def test_reused_completed_cycle_leaves_a_trace(self):
        # 이게 이 변경의 이유다: 완결된 과거 사이클을 지목한 통과가 기록에 남는다.
        decision = core.decide(_event(cycle_stem=REAL_STEM), PDCA_PROFILE,
                               _complete_snapshot(REAL_STEM), None)
        out = hr._record_declared_cycle_stem(GATE, self.root, decision, "sess-1")
        self.assertEqual(out["message_key"], "ok_l2")
        rec = self._records()
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["cycle_stem"], REAL_STEM)
        self.assertEqual(rec[0]["status"], "ok")
        self.assertEqual(rec[0]["session_id"], "sess-1")

    def test_inferred_stem_is_not_recorded(self):
        decision = core.decide(_event(), PDCA_PROFILE, _complete_snapshot(REAL_STEM), None)
        hr._record_declared_cycle_stem(GATE, self.root, decision, "sess-1")
        self.assertEqual(self._records(), [])

    def test_unrecordable_declaration_does_not_pass(self):
        # waiver 소비 기록 실패와 같은 성질의 무감사 통과다 → fail-closed.
        decision = {"status": "ok", "exit_code": 0, "message_key": "ok_l2",
                    "cycle_stem": REAL_STEM, "cycle_stem_declared": True, "file_short": "App.java"}
        with mock.patch.object(ov, "record_cycle_stem_declaration",
                               side_effect=OSError("read-only fs")):
            with redirect_stderr(_io.StringIO()) as err:
                out = hr._record_declared_cycle_stem(GATE, self.root, decision, "sess-1")
        self.assertEqual(out["status"], "block")
        self.assertEqual(out["exit_code"], 2)
        self.assertEqual(out["message_key"], "block_cycle_stem_audit_failure")
        self.assertIn("fail-closed", err.getvalue())
        self.assertIn(".sage/override.jsonl", messages.gate_text(out, {}, "claude"))

    def test_audit_failure_leaves_an_existing_block_alone(self):
        decision = {"status": "block", "exit_code": 2, "message_key": "block_phase_incomplete",
                    "cycle_stem": REAL_STEM, "cycle_stem_declared": True}
        with mock.patch.object(ov, "record_cycle_stem_declaration",
                               side_effect=OSError("read-only fs")):
            with redirect_stderr(_io.StringIO()):
                out = hr._record_declared_cycle_stem(GATE, self.root, decision, "s")
        self.assertEqual(out["message_key"], "block_phase_incomplete")

    def test_missing_session_id_does_not_dedupe_forever(self):
        """session_id 없는 입력을 빈 키로 dedupe 하면 첫 레코드가 이후 전부를 삼킨다 → 무기록 통과."""
        day = 1_700_000_000                      # 고정 시각(같은 UTC 날짜)
        self.assertIsNotNone(ov.record_cycle_stem_declaration(
            self.root, GATE, REAL_STEM, "", now=day))
        self.assertIsNone(ov.record_cycle_stem_declaration(   # 같은 날 = 같은 사실
            self.root, GATE, REAL_STEM, "", now=day + 60))
        self.assertIsNotNone(ov.record_cycle_stem_declaration(  # 다음 날은 별개 사실
            self.root, GATE, REAL_STEM, "", now=day + 86_400))
        self.assertEqual(len(self._records()), 2)

    def test_audit_failure_block_survives_an_active_override_grant(self):
        """감사 실패 BLOCK 을 일반 override grant 가 통과시키면 fail-closed 가 무의미해진다.

        override 는 그 자체가 감사에 남는 우회다 — 감사를 못 쓰는 상태에서 감사로 우회한다는 건
        성립하지 않는다. `_record_declared_cycle_stem` 직후 `_maybe_override` 가 오는 실제 순서로 본다.
        """
        ov.grant(self.root, "긴급 우회", 10000, gate="all")
        decision = {"status": "ok", "exit_code": 0, "message_key": "ok_l2",
                    "cycle_stem": REAL_STEM, "cycle_stem_declared": True, "file_short": "App.java"}
        with mock.patch.object(ov, "record_cycle_stem_declaration",
                               side_effect=OSError("read-only fs")):
            with redirect_stderr(_io.StringIO()):
                decision = hr._record_declared_cycle_stem(GATE, self.root, decision, "sess-1")
                bypassed = hr._maybe_override(GATE, self.root, decision, [{"path": "App.java"}])
        self.assertEqual(decision["message_key"], "block_cycle_stem_audit_failure")
        self.assertFalse(bypassed)
        self.assertEqual([r for r in ov.read_records(self.root) if r.get("event") == "bypass"], [])

    def test_records_are_valid_jsonl(self):
        ov.record_cycle_stem_declaration(self.root, GATE, REAL_STEM, "sess-1")
        with open(ov.audit_path(self.root), encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(lines[0]["event"], "cycle_stem_declared")
        self.assertIn("ts", lines[0])
        self.assertIn("user", lines[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
