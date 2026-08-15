#!/usr/bin/env python3
"""사이클 선언 통로 — `<root>/.sage/cycle.json` 의 실패 매트릭스.

env(`SAGE_CYCLE_STEM`) 하나뿐이던 선언 통로를 파일로 옮긴다. env 는 자식 프로세스를 전부 따라가고,
셸이 사이클보다 오래 살고, 조회할 방법이 없었다. 파일은 그 셋을 해소하는 대신 새 성질을 셋 들여온다 —
세션을 넘겨 살아남고, 편집 도구로 심을 수 있고, 손상될 수 있다.

여기서 못박는 것은 "깨지면 이 기능이 무의미해지는" 성질이고, **양방향**으로 고정한다. 넓히기만 하면
정상 작업이 막히고, 좁히기만 하면 게이트가 조용히 꺼진다. 둘 다 이 프로젝트가 실제로 겪은 실패다.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
RUNTIME = os.path.join(HOOKS_DIR, "runtime")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HOOKS_DIR)))
sys.path.insert(0, RUNTIME)
sys.path.insert(0, HOOKS_DIR)
sys.path.insert(0, PROJECT_ROOT)

import cycle_state as cs                                  # noqa: E402
import generated_artifact_write_guard_core as guard       # noqa: E402
import messages                                           # noqa: E402
import override_audit as ov                               # noqa: E402
import pre_implementation_gate_core as core               # noqa: E402

_STATE_TMP = None


def setUpModule():
    # 권한 캐시는 저장소 밖 상태 디렉터리에 산다 — 격리하지 않으면 개발자의 실제 ~/.local/state 를 오염시킨다.
    global _STATE_TMP
    _STATE_TMP = tempfile.TemporaryDirectory()
    os.environ["SAGE_STATE_HOME"] = _STATE_TMP.name


def tearDownModule():
    os.environ.pop("SAGE_STATE_HOME", None)
    _STATE_TMP.cleanup()


GATE = "pre-implementation-gate"
STEM = "sage-cycle-declaration"
BRANCH = "chatforyou_v2_sage"


def _mark_project(root):
    """SAGE 표식 — `sage install` 이 만드는 manifest. git 과 무관하다."""
    path = os.path.join(root, cs.MARKER_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text('{"assets": {}}\n', encoding="utf-8")
    return root


class TestRootResolution(unittest.TestCase):
    """T1·T2 — 선언이 놓이는 자리. 조용히 다른 자리로 떨어지는 것이 가장 나쁜 실패다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = _mark_project(os.path.realpath(self.tmp.name))

    def test_subdirectory_resolves_to_the_same_root(self):
        deep = os.path.join(self.root, "a", "b", "c")
        os.makedirs(deep)
        self.assertEqual(cs.find_project_root(deep), self.root)

    def test_symlinked_paths_resolve_into_the_project_not_out_of_it(self):
        """`abspath` 만 쓰면 symlink 를 거슬러 올라가 프로젝트 밖으로 나간다.

        실측에서 8갈래 중 4갈래가 틀렸고, 그중 하나는 정상 프로젝트를 `None` 으로 **거부**했다.
        macOS 의 `/tmp`→`/private/tmp` 가 일상적 사례라 흔한 구성이다.
        """
        inner = os.path.join(self.root, "pkg")
        os.makedirs(inner)
        outside = tempfile.mkdtemp()
        self.addCleanup(lambda: os.path.exists(link) and os.unlink(link))
        link = os.path.join(outside, "link-to-pkg")
        os.symlink(inner, link)
        self.assertEqual(cs.find_project_root(link), self.root)

    def test_a_directory_without_the_marker_is_refused(self):
        plain = tempfile.mkdtemp()
        self.addCleanup(lambda: os.rmdir(plain))
        self.assertIsNone(cs.find_project_root(plain))

    def test_the_nearest_marker_wins(self):
        # 모노레포 하위 설치: 상위에도 표식이 있어도 가까운 쪽이 정본이다.
        nested = _mark_project(os.path.join(self.root, "services", "api"))
        os.makedirs(os.path.join(nested, "src"), exist_ok=True)
        self.assertEqual(cs.find_project_root(os.path.join(nested, "src")), nested)

    def test_declaration_never_leaves_the_root(self):
        # 상위 탐색으로 쓰기 자리를 옮기면 install 이 .gitignore 를 쓴 앵커 밖에 놓여 커밋된다.
        self.assertEqual(cs.declaration_path(self.root),
                         os.path.join(self.root, ".sage", "cycle.json"))


class TestReadWriteClear(unittest.TestCase):
    """T7·T8·T8b — 쓰기·읽기의 양방향."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = _mark_project(os.path.realpath(self.tmp.name))

    def test_round_trip(self):
        cs.write_declaration(self.root, STEM, document_language="ko")
        self.assertEqual(cs.read_declaration(self.root), (STEM, None))

    def test_absent_declaration_is_not_an_error(self):
        self.assertEqual(cs.read_declaration(self.root), ("", None))

    def test_clear_reports_whether_it_existed(self):
        cs.write_declaration(self.root, STEM, document_language="ko")
        self.assertTrue(cs.clear_declaration(self.root))
        self.assertFalse(cs.clear_declaration(self.root))
        self.assertEqual(cs.read_declaration(self.root), ("", None))

    def test_malformed_stems_are_refused_at_write_time(self):
        # 게이트가 문서 부재로 걸러주긴 하지만, 경로 구분자·제어문자는 형식 자체가 틀렸다.
        for bad in ("", "   ", "a/b", "a\\b", "..", ".", "x\ty", "z" * 161):
            with self.assertRaises(ValueError, msg=bad):
                cs.write_declaration(self.root, bad, document_language="ko")
        self.assertEqual(cs.read_declaration(self.root), ("", None))

    def test_corruption_is_reported_not_silently_absent(self):
        """부재와 손상이 똑같이 `None` 으로 뭉개지면 파일을 1바이트만 잘라도 선언이 조용히 사라진다.

        선언이 차단 근거로 승격됐으므로(완결 사이클) 그 침묵이 곧 우회 레버다.
        """
        path = cs.declaration_path(self.root)
        cs.write_declaration(self.root, STEM, document_language="ko")
        for label, blob in (("잘린 JSON", '{"cycle_stem": "x"'),
                            ("객체 아님", '["x"]'),
                            ("stem 없음", '{"version": 1}'),
                            ("stem 형식 오류", '{"cycle_stem": "a/b"}')):
            Path(path).write_text(blob, encoding="utf-8")
            stem, error = cs.read_declaration(self.root)
            self.assertEqual(stem, "", label)
            self.assertTrue(error, label)
            self.assertEqual(error["arguments"].get("path"), path, label)

    def test_interrupted_write_keeps_the_previous_declaration(self):
        """원자적 쓰기 — 직접 `open(w)` 으로 되돌리면 이 갈래에서 선언이 사라진다.

        `open(w)` 은 여는 순간 대상을 잘라내므로, 쓰기가 중단되면 게이트가 읽는 자리에 잘린
        파일이 남는다. `mkstemp` + `os.replace` 는 온전한 파일을 만든 뒤 한 번에 갈아끼운다.
        """
        cs.write_declaration(self.root, STEM, document_language="ko")
        with mock.patch.object(os, "replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                cs.write_declaration(self.root, "other-cycle", document_language="ko")
        self.assertEqual(cs.read_declaration(self.root), (STEM, None))
        leftovers = [n for n in os.listdir(os.path.join(self.root, ".sage")) if n != "cycle.json"]
        self.assertEqual(leftovers, [])          # 실패한 임시 파일이 남으면 다음 진단을 흐린다

    def test_a_stale_entry_at_a_predictable_temp_name_does_not_block_writes(self):
        # 고정 tmp 이름으로 되돌리면 크래시가 남긴 잔해가 이후 모든 선언을 영구히 막는다.
        os.makedirs(os.path.join(self.root, ".sage", "cycle.json.tmp"))
        cs.write_declaration(self.root, STEM, document_language="ko")
        self.assertEqual(cs.read_declaration(self.root), (STEM, None))


class TestPrecedenceAndIsolation(unittest.TestCase):
    """T4·T5·T6 — 무엇이 이기는가, 그리고 어디까지 미치는가."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = _mark_project(os.path.realpath(self.tmp.name))

    def test_env_beats_file_beats_nothing(self):
        self.assertEqual(cs.resolve_stem(self.root, environ={}), ("", "", None))
        cs.write_declaration(self.root, STEM, document_language="ko")
        self.assertEqual(cs.resolve_stem(self.root, environ={}), (STEM, "cli", None))
        self.assertEqual(cs.resolve_stem(self.root, environ={"SAGE_CYCLE_STEM": "from-env"}),
                         ("from-env", "env", None))
        cs.clear_declaration(self.root)
        self.assertEqual(cs.resolve_stem(self.root, environ={"SAGE_CYCLE_STEM": "from-env"}),
                         ("from-env", "env", None))

    def test_env_winning_still_reports_a_corrupt_file(self):
        # 지금 판정에 안 쓰였을 뿐 깨진 파일은 남아 있고, env 가 사라지는 순간 조용히 발화한다.
        Path(cs.declaration_path(self.root)).parent.mkdir(parents=True, exist_ok=True)
        Path(cs.declaration_path(self.root)).write_text("{", encoding="utf-8")
        stem, origin, error = cs.resolve_stem(self.root, environ={"SAGE_CYCLE_STEM": "e"})
        self.assertEqual((stem, origin), ("e", "env"))
        self.assertTrue(error)

    def test_declaring_does_not_export_anything_to_child_processes(self):
        # env 와 다를 게 없어지면 이 기능의 존재 이유가 사라진다.
        os.environ.pop("SAGE_CYCLE_STEM", None)
        cs.write_declaration(self.root, STEM, document_language="ko")
        self.assertIsNone(os.environ.get("SAGE_CYCLE_STEM"))
        child = subprocess.run(
            [sys.executable, "-c",
             "import os; print(os.environ.get('SAGE_CYCLE_STEM', '<unset>'))"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(child.stdout.strip(), "<unset>")

    def test_one_projects_declaration_does_not_reach_another(self):
        other = _mark_project(os.path.realpath(tempfile.mkdtemp()))
        cs.write_declaration(self.root, STEM, document_language="ko")
        self.assertEqual(cs.resolve_stem(other, environ={}), ("", "", None))


class TestDeclarationFileIsGuarded(unittest.TestCase):
    """T9 — 편집 도구로 선언을 심는 경로. env 통로에서는 불가능했던 구멍이다."""

    def test_the_declaration_is_guarded(self):
        for path in (".sage/cycle.json", "/abs/proj/.sage/cycle.json",
                     "./.sage/cycle.json", ".sage\\cycle.json",
                     "services/api/.sage/cycle.json"):
            self.assertTrue(guard.is_guarded(path), path)

    def test_other_cycle_json_files_are_not_over_blocked(self):
        # `.mcp.json` 처럼 basename 으로 매칭하면 프로젝트의 아무 cycle.json 이나 걸린다.
        for path in ("src/cycle.json", "config/cycle.json", "cycle.json",
                     ".sage/override.jsonl", ".sage/tmp/cycle.jsonl"):
            self.assertFalse(guard.is_guarded(path), path)

    def test_the_block_message_points_at_the_cli(self):
        message = guard.block_message(".sage/cycle.json")
        self.assertIn("sage cycle set", message)
        self.assertIn("sage cycle clear", message)

    def test_a_write_attempt_blocks_with_exit_two(self):
        raw = json.dumps({"tool_name": "Write",
                          "tool_input": {"file_path": "/proj/.sage/cycle.json"}})
        decision = guard.decide_json(raw)
        self.assertEqual((decision["status"], decision["exit_code"]), ("block", 2))


class TestDisplayAndAuditNameTheChannel(unittest.TestCase):
    """T13·T13b — 확인한 것만 말한다. 통로가 둘이므로 뭉치면 거짓이 된다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def _suffix(self, origin):
        decision = {"status": "ok", "exit_code": 0, "message_key": "ok_l2", "file_short": "a.java",
                    "cycle_stem": STEM, "cycle_source": ["event"], "cycle_stem_origin": origin}
        return messages.gate_text(decision, {}, "claude")

    def test_each_channel_is_named_as_itself(self):
        self.assertIn("SAGE_CYCLE_STEM 선언", self._suffix("env"))
        self.assertIn(".sage/cycle.json 선언", self._suffix("cli"))
        self.assertNotIn("SAGE_CYCLE_STEM", self._suffix("cli"))

    def test_the_display_does_not_claim_who_wrote_it(self):
        # 선언 파일은 프로젝트 안에 있어 무엇이든 직접 쓸 수 있다 — "sage cycle set 으로 선언했다" 는
        # 확인 불가능한 단언이다. 게이트가 아는 것은 읽은 자리뿐이다.
        self.assertNotIn("sage cycle set", self._suffix("cli"))

    def test_the_audit_dedupe_key_separates_the_two_channels(self):
        """기원을 dedupe 키에서 빼면 먼저 걸린 쪽만 남아, 세션을 넘겨 살아남는 파일 선언이
        일회성 env 선언으로 기록된다 — 구분하려고 넣은 필드가 정확히 뒤집힌다."""
        self.assertIsNotNone(ov.record_cycle_stem_declaration(
            self.root, GATE, STEM, "s-1", origin="env"))
        self.assertIsNotNone(ov.record_cycle_stem_declaration(
            self.root, GATE, STEM, "s-1", origin="cli"))
        self.assertIsNone(ov.record_cycle_stem_declaration(
            self.root, GATE, STEM, "s-1", origin="cli"))
        records = [r for r in ov.read_records(self.root)
                   if r.get("event") == "cycle_stem_declared"]
        self.assertEqual(sorted(r["origin"] for r in records), ["cli", "env"])


class TestBlockGuidanceHasNoDeadEnd(unittest.TestCase):
    """T11·T12 — 두 안내가 서로를 가리키면 사용자는 나갈 길이 없다."""

    def _binding_block(self, source):
        return {"status": "block", "exit_code": 2, "risk": "PDCA",
                "message_key": "block_cycle_binding", "file_short": "a.java",
                "reason": "cycle binding 실패: 후보 2개", "cycle_source": source}

    def test_binding_failure_names_the_release_channel_on_both_paths(self):
        # 완결 차단 안내("새 사이클의 Phase 00 을 쓰라")를 따르면 여기서 후보 2개로 다시 막힌다.
        for source in (["branch-leaf"], ["plan_docs/00-x/a.md"]):
            for runtime in ("claude", "codex"):
                text = messages.gate_text(self._binding_block(source), {}, runtime)
                self.assertIn("sage cycle clear", text, (source, runtime))

    def test_binding_failure_does_not_assert_the_cause(self):
        """`resolve` 는 문서 오류를 후보 개수보다 **먼저** 반환하므로 source 로 원인을 역추론할 수
        없다. 원인을 단정하면 무효 처방이 된다 — 확인 통로만 가리킨다."""
        text = messages.gate_text(self._binding_block(["branch-leaf"]), {}, "claude")
        self.assertIn("sage cycle show", text)
        self.assertNotIn("선언 때문", text)


class TestCorruptionIsSurfaced(unittest.TestCase):
    """T8 양방향 — degrade 하되(BLOCK 아님) 조용하지는 않게."""

    def _decision(self, **kw):
        return {"status": "ok", "exit_code": 0,
                "cycle_declaration_error": {"code": "cycle_state.json_invalid",
                                            "arguments": {"path": "/p/.sage/cycle.json"}, "evidence": ""},
                "file_short": "a.java", **kw}

    def test_a_pass_with_no_gate_line_still_carries_the_notice(self):
        # L1/L0 통과는 message_key 가 없어 줄 자체가 안 생긴다 — 거기가 바로 깨진 선언이
        # 조용히 무시되는 자리다.
        text = messages.gate_text(self._decision(), {}, "claude")
        self.assertIn("사이클 선언 무시됨", text)
        self.assertIn("sage cycle set", text)

    def test_the_notice_rides_along_with_an_existing_gate_line(self):
        text = messages.gate_text(
            self._decision(message_key="ok_l2", cycle_stem=STEM, cycle_source=["branch-leaf"]),
            {}, "claude")
        self.assertIn("사이클 선언 무시됨", text)
        self.assertIn("GATE OK", text)

    def test_a_healthy_declaration_makes_no_noise(self):
        decision = {"status": "ok", "exit_code": 0, "message_key": "ok_l2", "file_short": "a.java",
                    "cycle_stem": STEM, "cycle_source": ["event"], "cycle_stem_origin": "cli"}
        self.assertNotIn("사이클 선언 무시됨", messages.gate_text(decision, {}, "claude"))

    def test_corruption_degrades_to_inference_instead_of_blocking(self):
        # 파일 하나 깨진 것으로 모든 편집을 멈추면 자가 DoS 다. 판정은 선언 부재와 같아야 한다.
        event = {"hook_id": GATE, "branch": BRANCH, "session_id": "s", "cycle_stem": "",
                 "cycle_stem_origin": "",
                 "changes": [{"path": "backend/App.java", "op": "write", "content": "x"}]}
        profile = {"risk": {"l2_path_globs": ["*backend/*.java"]},
                   "pdca": {"enabled": True,
                            "phases": [{"id": "00", "glob": "plan_docs/00-x/**/*.md"}]}}
        decision = core.decide(event, profile, {"plan_files": [], "review_candidates": [],
                                                "phase_docs": {}}, None)
        self.assertEqual(decision["cycle_stem"], BRANCH)      # 추론으로 계속 간다


class TestFullWiring(unittest.TestCase):
    """T15 — 실제 `run_pre_implementation_gate` 와 실제 `python -m sage` 로 태운다.

    잎 함수만 덮으면 배선이 끊긴 채로 전 항목이 통과한다. 이 사이클이 실제로 고치려는 것은
    "선언이 게이트 판정에 도달하는가" 하나다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = _mark_project(os.path.realpath(self.tmp.name))
        os.makedirs(os.path.join(self.root, "sage"), exist_ok=True)
        Path(os.path.join(self.root, "sage", "project-profile.yaml")).write_text(
            "project: t\n", encoding="utf-8")
        for phase in ("00", "01", "02", "03"):
            doc = os.path.join(self.root, "plan_docs", f"{phase}-x", f"{STEM}.md")
            os.makedirs(os.path.dirname(doc), exist_ok=True)
            risk = "Risk Level: L2\n" if phase == "00" else ""
            Path(doc).write_text(f"Cycle-Stem: `{STEM}`\n{risk}", encoding="utf-8")
        self.profile = {
            "risk": {"l0_pass_globs": ["*plan_docs/*"], "l2_path_globs": ["*backend/*.java"]},
            "pdca": {"enabled": True,
                     "phases": [{"id": p, "glob": f"plan_docs/{p}-x/**/*.md"}
                                for p in ("00", "01", "02", "03")],
                     "pre_implementation_required": {"L2": ["00", "01", "02", "03"]}},
        }
        profile_path = os.path.join(self.root, "profile.json")
        Path(profile_path).write_text(json.dumps(self.profile), encoding="utf-8")
        self._env(SAGE_PROFILE=profile_path, SAGE_GATE_BRANCH=BRANCH)
        os.environ.pop("SAGE_CYCLE_STEM", None)

    def _env(self, **kw):
        for key, value in kw.items():
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(
                lambda k=key, o=old: os.environ.__setitem__(k, o) if o is not None
                else os.environ.pop(k, None))

    def _run_gate(self):
        import hook_runtime as hr
        import io_claude
        raw = json.dumps({"session_id": "s-1", "tool_name": "Write",
                          "tool_input": {"file_path": os.path.join(self.root, "backend", "App.java"),
                                         "content": "class App {}"}})
        from contextlib import redirect_stdout, redirect_stderr
        import io as _io
        out, err = _io.StringIO(), _io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = hr.run_pre_implementation_gate(io_claude, self.root, HOOKS_DIR, raw)
        return rc, out.getvalue() + err.getvalue()

    def test_without_a_declaration_the_branch_leaf_misbinds_and_blocks(self):
        rc, text = self._run_gate()
        self.assertEqual(rc, 2)
        self.assertIn(BRANCH, text)              # 존재하지 않는 사이클에 결속돼 있다

    def test_the_cli_declaration_reaches_the_real_gate(self):
        proc = subprocess.run([sys.executable, "-m", "sage", "cycle", "set", STEM],
                              cwd=os.path.join(self.root, "plan_docs"), capture_output=True,
                              text=True, stdin=subprocess.DEVNULL,
                              env={**os.environ, "PYTHONPATH": PROJECT_ROOT})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.exists(cs.declaration_path(self.root)), proc.stdout)
        rc, text = self._run_gate()
        self.assertEqual(rc, 0, text)
        self.assertIn(STEM, text)
        self.assertIn(".sage/cycle.json 선언", text)

    def test_clear_returns_the_gate_to_inference(self):
        cs.write_declaration(self.root, STEM, document_language="ko")
        self.assertEqual(self._run_gate()[0], 0)
        proc = subprocess.run([sys.executable, "-m", "sage", "cycle", "clear"],
                              cwd=self.root, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL,
                              env={**os.environ, "PYTHONPATH": PROJECT_ROOT})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self._run_gate()[0], 2)

    def test_a_corrupt_declaration_degrades_and_says_so_through_the_real_gate(self):
        cs.write_declaration(self.root, STEM, document_language="ko")
        Path(cs.declaration_path(self.root)).write_text('{"cycle_stem"', encoding="utf-8")
        rc, text = self._run_gate()
        self.assertEqual(rc, 2)                  # 선언 부재와 같은 판정 — 차단이 아니라 degrade
        self.assertIn("사이클 선언 무시됨", text)


class TestDocumentLanguageCrossHostParity(unittest.TestCase):
    """AC25 — 같은 사이클의 문서 언어 충돌이 Claude/Codex 두 host 에서 동일하게 막히는가.

    `_document_language_gate` 자체는 host 를 모른다. 하지만 그걸 부르는
    `run_pre_implementation_gate`가 `io_claude`/`io_codex` 어댑터별로 다른 이벤트를 조립하므로,
    잎 함수 단위 테스트(`test_document_language.py::TestGateWiring`)만으로는 이 배선이 한쪽
    host 에서만 끊겨도 통과한다. 실제 두 어댑터를 태워 판정이 갈라지지 않는지 확인한다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = _mark_project(os.path.realpath(self.tmp.name))
        os.makedirs(os.path.join(self.root, "sage"), exist_ok=True)
        Path(os.path.join(self.root, "sage", "project-profile.yaml")).write_text(
            "project: t\n", encoding="utf-8")
        self.profile = {
            "risk": {"l0_pass_globs": ["*plan_docs/*"], "l2_path_globs": ["*backend/*"]},
            "pdca": {"enabled": True,
                     "phases": [{"id": p, "glob": f"plan_docs/{p}-x/**/*.md"}
                                for p in ("00", "01")],
                     "report_phase": "06", "approve_phase": "05"},
        }
        profile_path = os.path.join(self.root, "profile.json")
        Path(profile_path).write_text(json.dumps(self.profile), encoding="utf-8")
        for key, value in {"SAGE_PROFILE": profile_path, "SAGE_GATE_BRANCH": BRANCH}.items():
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, o=old: os.environ.__setitem__(k, o) if o is not None
                            else os.environ.pop(k, None))
        os.environ.pop("SAGE_CYCLE_STEM", None)

    def _write_docs(self, languages):
        for phase, language in languages.items():
            doc = os.path.join(self.root, "plan_docs", f"{phase}-x", f"{STEM}.md")
            os.makedirs(os.path.dirname(doc), exist_ok=True)
            risk = "Risk Level: L2\n" if phase == "00" else ""
            Path(doc).write_text(
                f"Cycle-Stem: `{STEM}`\n{risk}Document-Language: {language}\n", encoding="utf-8")

    @staticmethod
    def _capture(fn):
        from contextlib import redirect_stdout, redirect_stderr
        import io as _io
        out, err = _io.StringIO(), _io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = fn()
        return rc, out.getvalue() + err.getvalue()

    def _run_claude(self):
        import hook_runtime as hr
        import io_claude
        raw = json.dumps({"session_id": "s-1", "tool_name": "Write",
                          "tool_input": {"file_path": os.path.join(self.root, "backend", "App.java"),
                                         "content": "class App {}"}})
        return self._capture(lambda: hr.run_pre_implementation_gate(io_claude, self.root, HOOKS_DIR, raw))

    def _run_codex(self):
        import hook_runtime as hr
        import io_codex
        cmd = "*** Begin Patch\n*** Add File: backend/App.java\n+class App {}\n*** End Patch"
        raw = json.dumps({"session_id": "s-1", "tool_name": "apply_patch",
                          "tool_input": {"command": cmd}})
        return self._capture(lambda: hr.run_pre_implementation_gate(io_codex, self.root, HOOKS_DIR, raw))

    def test_conflicting_document_language_blocks_on_both_hosts(self):
        self._write_docs({"00": "en", "01": "ko"})
        cs.write_declaration(self.root, STEM, document_language="en")
        rc_claude, text_claude = self._run_claude()
        rc_codex, text_codex = self._run_codex()
        self.assertEqual(rc_claude, 2, text_claude)
        self.assertEqual(rc_codex, 2, text_codex)
        self.assertIn("문서 언어", text_claude)
        self.assertIn("문서 언어", text_codex)

    def test_agreeing_document_language_passes_on_both_hosts(self):
        self._write_docs({"00": "en", "01": "en"})
        cs.write_declaration(self.root, STEM, document_language="en")
        rc_claude, text_claude = self._run_claude()
        rc_codex, text_codex = self._run_codex()
        self.assertEqual(rc_claude, 0, text_claude)
        self.assertEqual(rc_codex, 0, text_codex)


class TestCliSurfacesWhatItChecked(unittest.TestCase):
    """T3·T14 — 어긋난 구성에서 사람이 볼 수 있는 유일한 단서."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = _mark_project(os.path.realpath(self.tmp.name))

    def _cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-m", "sage", "cycle", *args],
                              cwd=cwd or self.root, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL,
                              env={**os.environ, "PYTHONPATH": PROJECT_ROOT,
                                   "SAGE_CYCLE_STEM": ""})

    def _git_repo_with_managed_ignore(self):
        from sage.commands import install
        subprocess.run(["git", "init", "-q", self.root], check=True, capture_output=True)
        Path(os.path.join(self.root, ".gitignore")).write_text(
            install._render_local_profile_gitignore(""), encoding="utf-8")
        return install._LOCAL_STATE_IGNORE_ENTRIES

    def test_set_prints_the_absolute_root_and_file(self):
        # CLI root 와 게이트 root 가 어긋날 수 있다는 것이 이 설계의 알려진 한계다.
        # 보장할 수 없는 것은 보이게 한다.
        proc = self._cli("set", STEM)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(self.root, proc.stdout)
        self.assertIn(os.path.join(self.root, ".sage", "cycle.json"), proc.stdout)

    def test_set_warns_when_the_profile_pair_is_absent(self):
        # 표식(manifest)과 게이트의 전제조건(profile 쌍)이 다르다 — 그 어긋남의 유일한 노출 지점.
        self.assertIn("project-profile", self._cli("set", STEM).stdout)

    def test_set_refuses_a_malformed_stem(self):
        proc = self._cli("set", "a/b")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("형식 오류", proc.stderr)

    def test_outside_a_sage_project_the_cli_refuses(self):
        # cwd 로 떨어지면 게이트가 영영 읽지 않는 자리에 파일이 놓이고 사용자는 선언했다고 믿는다.
        plain = tempfile.mkdtemp()
        self.addCleanup(lambda: os.rmdir(plain))
        proc = self._cli("set", STEM, cwd=plain)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("SAGE 프로젝트가 아닙니다", proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(plain, ".sage")))

    def test_the_declaration_leaves_the_working_tree_clean(self):
        """무시 규칙은 `install` 상수에서 가져온다 — 상수가 `.sage/cycle.json` 을 더 이상 덮지
        않게 바뀌면 이 이빨이 죽어야 한다. 커밋되면 남의 clone 에서 엉뚱하게 결속된다."""
        entries = self._git_repo_with_managed_ignore()
        self.assertIn("/.sage/*", entries)
        self.assertEqual(self._cli("set", STEM).returncode, 0)
        status = subprocess.run(["git", "-C", self.root, "status", "--porcelain"],
                                capture_output=True, text=True).stdout
        self.assertNotIn(".sage", status)
        ignored = subprocess.run(
            ["git", "-C", self.root, "check-ignore", "-q", cs.declaration_path(self.root)])
        self.assertEqual(ignored.returncode, 0)

    def test_set_warns_when_the_file_is_not_ignored(self):
        # D2 의 안전 근거가 install 이 쓴 관리 블록이므로 검증 없이 약속하지 않는다.
        subprocess.run(["git", "init", "-q", self.root], check=True, capture_output=True)
        stdout = self._cli("set", STEM).stdout
        self.assertIn("git 에 무시되지 않습니다", stdout)
        self.assertIn("sage install --force", stdout)     # 실측: 이 상태는 실제로 복구된다

    def test_show_reports_the_channel_and_the_losing_file(self):
        self.assertEqual(self._cli("set", STEM).returncode, 0)
        proc = subprocess.run([sys.executable, "-m", "sage", "cycle", "show"],
                              cwd=self.root, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL,
                              env={**os.environ, "PYTHONPATH": PROJECT_ROOT,
                                   "SAGE_CYCLE_STEM": "from-env"})
        self.assertIn("from-env", proc.stdout)
        self.assertIn("SAGE_CYCLE_STEM", proc.stdout)
        self.assertIn(STEM, proc.stdout)                  # 밀린 파일 선언도 보여야 한다

    def test_clear_reminds_that_env_survives(self):
        proc = subprocess.run([sys.executable, "-m", "sage", "cycle", "clear"],
                              cwd=self.root, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL,
                              env={**os.environ, "PYTHONPATH": PROJECT_ROOT,
                                   "SAGE_CYCLE_STEM": "leftover"})
        self.assertIn("unset SAGE_CYCLE_STEM", proc.stdout)


class TestSuiteIsWiredIntoCi(unittest.TestCase):
    """T17 — 등록 안 된 스위트는 CI 가 영영 안 돌린다(주석 처리·종료코드 버림도 orphan)."""

    def test_run_all_executes_this_file_and_keeps_its_exit_code(self):
        text = Path(os.path.join(HERE, "run-all.sh")).read_text(encoding="utf-8")
        line = next((ln.strip() for ln in text.splitlines()
                     if "test_cycle_state.py" in ln and not ln.strip().startswith("#")), "")
        self.assertTrue(line, "run-all.sh 에 test_cycle_state.py 가 등록되지 않았다")
        self.assertIn("|| rc=1", line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
