#!/usr/bin/env python3
"""독립 검토가 재현한 사각지대들 — 같은 반례가 다시 통과하지 못하게 한다.

이 스위트의 검사들은 전부 **한때 실제로 통과했던 반례**다. 기존 검사가 실패한 것이 아니라,
녹색 검사가 강제하지 않는 계약에 구멍이 있었다. 그러므로 각 검사는 "기능이 있다" 가 아니라
"그때 그 반례가 지금은 잡힌다" 를 확인한다.

1. malformed manifest 가 호환성 판정 없이 core import 로 넘어갔다.
2. `status` 가 필수 phase 부재를 비차단으로 표시했고 cycle mode 를 아예 싣지 않았다.
3. bootstrap·core-load·dispatch·write-guard 차단에 `Next:` 가 없었다.
4. recovery oracle 이 id rename 과 hook 전용 파괴적 명령을 놓쳤다.
5. `explain` 이 존재하지 않는 root 를 정상 프로젝트처럼 설명했다.
6. 한 collector 의 예외가 나머지 영역의 결과를 통째로 지웠다.
"""
import builtins
import io
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
HOOKS = os.path.join(REPO, "scripts", "sage_harness", "hooks")
RUNTIME = os.path.join(HOOKS, "runtime")
for _p in (RUNTIME, HOOKS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sage import hook_entry  # noqa: E402
from sage.commands import explain as E, status as S  # noqa: E402
from sage.diagnostic_contract import (SEVERITY, BLOCK, Finding, recovery_for,  # noqa: E402
                                     TOOL_FAILURE)  # noqa: E402
from sage.diagnostics import Diagnostic  # noqa: E402
import hook_runtime  # noqa: E402,F401
import recovery  # noqa: E402,F401
import pre_implementation_gate_core  # noqa: E402,F401


def _load_gate():
    return pre_implementation_gate_core
from sage.i18n import validation as V  # noqa: E402
from sage.profile_compile import materialize_profile  # noqa: E402
from sage.runtime_api import HOOK_RUNTIME_API  # noqa: E402
from sage.version_contract import ISSUE_SEVERITY  # noqa: E402

import fast_cycle_audit  # noqa: E402
import generated_artifact_write_guard_core as GUARD  # noqa: E402

PROFILE = {
    "risk": {"l2_path_globs": ["src/**"]},
    "pdca": {
        "enabled": True,
        "phases": [{"id": "00", "glob": "plan_docs/00-base_plan/*.md"},
                   {"id": "01", "glob": "plan_docs/01-plan/*.md"},
                   {"id": "02", "glob": "plan_docs/02-design/*.md"}],
        "pre_implementation_required": {"L3": ["00", "01", "02"]},
    },
}


class Args:
    def __init__(self, **kw):
        self.root = None
        self.json = False
        self.path = None
        self.__dict__.update(kw)


def _project(root, manifest=True):
    os.makedirs(os.path.join(root, "sage"), exist_ok=True)
    with open(os.path.join(root, "sage", "project-profile.yaml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump(PROFILE, fh)
    with open(os.path.join(root, "sage", "project-profile.json"), "w", encoding="utf-8") as fh:
        json.dump(materialize_profile(PROFILE), fh)
    if manifest:
        os.makedirs(os.path.join(root, "docs", "sage_harness"), exist_ok=True)
        with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"sage_version": "1.0.0", "host_runtime": "codex", "assets": {},
                       "generator_version": "1.0.0",
                       "runtime_api": {"required": HOOK_RUNTIME_API}}, fh)
    return root


def _phase00(root, stem, tier="L3"):
    d = os.path.join(root, "plan_docs", "00-base_plan")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{stem}.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# {stem}\n\nCycle-Stem: `{stem}`\nRisk Level: {tier}\n")
    os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
    with open(os.path.join(root, ".sage", "cycle.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema_version": 2, "cycle_stem": stem,
                   "document_language": "ko"}, fh)


def _run(command, **kw):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = command.run(Args(**kw))
    return rc, out.getvalue(), err.getvalue()


# 전환 문서 배치. PROFILE 의 phase glob 과 같은 폴더를 쓴다.
_PHASE_FOLDER = {"00": "00-base_plan", "01": "01-plan", "02": "02-design"}


def _write_source_docs(root, current_phase="02", stem="demo"):
    """`current_phase` 까지의 phase 문서를 **실제로** 만든다."""
    from sage.fast_cycle_contract import expected_source_phases
    phases, issue = expected_source_phases(current_phase)
    assert issue is None, issue
    for phase in phases:
        folder = os.path.join(root, "plan_docs", _PHASE_FOLDER[phase])
        os.makedirs(folder, exist_ok=True)
        # Phase 00 은 위험도 선언도 실어야 한다 — 전환 판정이 그것을 읽는다. 선언 없는
        # 00 을 쓰면 요구 phase 계산이 조용히 빈 목록으로 떨어지고, 검사가 아무것도 지키지 않는다.
        with open(os.path.join(folder, f"{stem}.md"), "w", encoding="utf-8") as fh:
            fh.write(f"# {stem} phase {phase}\n\nCycle-Stem: `{stem}`\nRisk Level: L3\n")
    return phases


def _source_phases(root, current_phase="02", stem="demo", profile=None):
    """실제 파일에서 계산한 provenance.

    이전 판은 문자열을 조립했다. writer 가 디스크와 대조하게 되면서 그 값은 통과하지 않는다 —
    그리고 그것이 요점이다: 손으로 지은 provenance 는 "저장소 안의 그 파일" 을 증언하지 않는다.
    """
    from sage.fast_cycle_sources import source_phase_snapshot
    _write_source_docs(root, current_phase, stem)
    return source_phase_snapshot(root, profile or PROFILE, stem, current_phase)


def _convert_fast(root, current_phase="02", stem="demo", profile=None, **over):
    """실제 API 로 전환 run 을 연다 — 문서를 만들고, 그 파일에서 provenance 를 계산해서."""
    profile = profile or PROFILE
    kwargs = dict(profile=profile, cycle_stem=stem, current_phase=current_phase,
                  actual_risk="L3", fast_review_level="L2", reason="테스트 전환",
                  confirmed_by="tester", minimum_rounds=1,
                  lenses=["correctness", "error_handling"],
                  source_phases=_source_phases(root, current_phase, stem, profile))
    kwargs.update(over)
    return fast_cycle_audit.convert_fast(root, **kwargs)


def _open_fast(root, stem="demo", risk="L3"):
    """실제 API 로 Fast run 을 연다.

    손으로 쓴 한 줄짜리 opener 를 정상 fixture 로 쓰면, 검사가 결함 상태를 정상으로
    박제한다 — 실제로 그렇게 해서 불완전 opener 가 FAST 로 통과하는 것을 놓쳤다.
    """
    return fast_cycle_audit.open_fast(
        root, cycle_stem=stem, actual_risk=risk, fast_review_level="L2",
        reason="테스트 fixture", minimum_rounds=2, lenses=["a", "b"],
        profile_hash="sha256:" + "0" * 64, plan_hash_open="sha256:" + "1" * 64)


class TestManifestUnreadableStopsBeforeCore(unittest.TestCase):
    """판정할 근거가 없는 상태를 통과로 읽지 않는다."""

    def _preflight(self, body, hook="pre-implementation-gate", enforcing=True):
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, "docs", "sage_harness")
            os.makedirs(d)
            if body is not None:
                with open(os.path.join(d, ".manifest.json"), "w", encoding="utf-8") as fh:
                    fh.write(body)
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                rc = hook_entry._runtime_api_preflight(
                    "claude", hook, root, HOOKS, enforcing)
            return rc, err.getvalue()

    def test_malformed_manifest_blocks(self):
        rc, err = self._preflight("{ not json")
        self.assertEqual(rc, 2)
        self.assertIn("runtime.manifest_unreadable", err)

    def test_malformed_manifest_names_the_next_action(self):
        _rc, err = self._preflight("{ not json")
        self.assertIn("Next:", err)

    def test_absent_manifest_is_not_the_same_as_unreadable(self):
        # 설치 전일 수 있다. 이 검사의 소관이 아니므로 계속 진행한다.
        self.assertEqual(self._preflight(None)[0], None)

    def test_a_manifest_that_is_not_an_object_blocks(self):
        self.assertEqual(self._preflight("[1, 2, 3]")[0], 2)

    def test_hooks_that_enforce_nothing_warn_instead_of_blocking(self):
        """session-start 는 아무 정책도 집행하지 않는다. 거기서 막으면 세션만 죽는다."""
        rc, err = self._preflight("{ not json", hook="session-start-snapshot")
        self.assertEqual(rc, 0)
        self.assertIn("runtime.manifest_unreadable", err)

    def test_the_exemption_only_subtracts_never_adds(self):
        """예외 목록은 호출부의 판단에서 **빼기만** 한다.

        위로 덮어쓰면(목록에 없으면 무조건 집행) 알림 hook 이 세션을 죽이고, 아래로
        덮어쓰면(목록에 없으면 무조건 통과) 이름 모르는 project 정책 hook 이 통과한다.
        """
        self.assertEqual(self._preflight("{ not json", hook="session-start-snapshot",
                                         enforcing=True)[0], 0)
        self.assertEqual(self._preflight("{ not json", hook="pre-implementation-gate",
                                         enforcing=False)[0], 0)
        self.assertEqual(self._preflight("{ not json", hook="pre-implementation-gate",
                                         enforcing=True)[0], 2)

    def test_the_write_guard_still_enforces(self):
        self.assertEqual(
            self._preflight("{ not json", hook="generated-artifact-write-guard")[0], 2)

    def test_the_unreadable_code_is_a_block_with_recovery(self):
        self.assertEqual(SEVERITY["runtime.manifest_unreadable"], BLOCK)
        self.assertTrue(recovery_for("runtime.manifest_unreadable"))

    def test_core_is_not_imported_when_the_manifest_is_unreadable(self):
        """실제 프로세스로 확인한다 — import 되면 sentinel 파일이 남는다."""
        with tempfile.TemporaryDirectory() as root:
            core = os.path.join(root, "core")
            os.makedirs(core)
            sentinel = os.path.join(root, "imported.marker")
            with open(os.path.join(core, "run_hook.py"), "w", encoding="utf-8") as fh:
                fh.write(f"open({sentinel!r}, 'w').write('yes')\n"
                         "raise RuntimeError('core exploded on import')\n")
            d = os.path.join(root, "docs", "sage_harness")
            os.makedirs(d)
            with open(os.path.join(d, ".manifest.json"), "w", encoding="utf-8") as fh:
                fh.write("{ not json")
            proc = subprocess.run(
                [sys.executable, "-c",
                 "import sys; sys.path.insert(0, %r);"
                 "from sage.hook_entry import _runtime_api_preflight as p;"
                 "sys.exit(p('claude','pre-implementation-gate',%r,%r,True) or 0)"
                 % (REPO, root, core)],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertFalse(os.path.exists(sentinel),
                             "판정 전에 project core 가 import 됐다")


class TestStatusGateReadiness(unittest.TestCase):
    """가장 흔한 차단 원인을 비차단으로 표시하지 않는다."""

    def test_missing_required_phases_block(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _phase00(root, "demo")
            rc, out, _ = _run(S, root=root, json=True)
            payload = json.loads(out)
            codes = [d["code"] for d in payload["diagnostics"]]
            self.assertIn("gate.phase_incomplete", codes)
            self.assertEqual(payload["status"], "BLOCKED")
            self.assertEqual(rc, 1)

    def test_the_missing_phases_are_named(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _phase00(root, "demo")
            _, out, _ = _run(S, root=root, json=True)
            payload = json.loads(out)
            self.assertEqual(list(payload["gate"]["missing"]), ["01", "02"])
            self.assertEqual(list(payload["gate"]["present"]), ["00"])

    def test_a_complete_cycle_has_no_gate_finding(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _phase00(root, "demo")
            for phase, folder in (("01", "01-plan"), ("02", "02-design")):
                d = os.path.join(root, "plan_docs", folder)
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, "demo.md"), "w", encoding="utf-8") as fh:
                    fh.write(f"# {phase}\n\nCycle-Stem: `demo`\n")
            _, out, _ = _run(S, root=root, json=True)
            codes = [d["code"] for d in json.loads(out)["diagnostics"]]
            self.assertNotIn("gate.phase_incomplete", codes)

    def test_gate_is_one_of_the_seven_collected_areas(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            facts, _ = S.collect(root)
            self.assertEqual(
                sorted(facts),
                ["cycle", "gate", "host", "profile", "project", "runtime_api", "version"])

    def test_status_and_explain_share_one_readiness_validator(self):
        """두 명령이 같은 질문에 다른 답을 내면 정본이 둘이다.

        같은 *출력*을 요구하지는 않는다 — `explain` 은 그 경로의 위험도를, `status` 는 이
        사이클의 선언 위험도를 묻는다. 요구가 다를 수 있는 것이 정상이다. 고정할 것은 둘이
        같은 판정 함수를 쓴다는 것과, 같은 위험도를 넣으면 같은 답이 나온다는 것이다.
        """
        from sage import gate_readiness

        self.assertIs(E.phase_readiness, gate_readiness.phase_readiness)
        self.assertIs(E.required_phases, gate_readiness.required_phases)
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _phase00(root, "demo")
            _, status_out, _ = _run(S, root=root, json=True)
            shared = gate_readiness.phase_readiness(
                root, PROFILE, "demo",
                gate_readiness.required_phases(PROFILE, "L3"))
            self.assertEqual(list(json.loads(status_out)["gate"]["missing"]), list(shared[1]))

    def test_explain_answers_for_the_paths_risk_not_the_declared_one(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _phase00(root, "demo", tier="L3")
            _, out, _ = _run(E, root=root, path="src/a.py", json=True)
            payload = json.loads(out)
            self.assertEqual(payload["path_risk_floor"], "L2")
            # L2 는 이 프로필에서 요구 phase 가 없다. L3 의 요구를 끌어오지 않는다.
            self.assertEqual(payload["required_phases"], [])


class TestCycleMode(unittest.TestCase):
    """mode 를 싣되, 그 대가로 읽기 전용 계약을 깨지 않는다."""

    def _audit(self, root, body):
        os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
        with open(os.path.join(root, ".sage", "fast_cycle.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(body)

    def test_an_active_run_for_this_stem_is_fast(self):
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "FAST")

    def test_a_converted_run_displays_as_fast_but_keeps_its_entry_mode(self):
        with tempfile.TemporaryDirectory() as root:
            _convert_fast(root, minimum_rounds=2)
            mode, evidence = fast_cycle_audit.mode_for_stem(root, "demo")
            self.assertEqual(mode, "FAST")
            self.assertEqual(evidence["entry_mode"], "FAST-CONVERTED")

    def test_a_terminal_run_is_standard(self):
        with tempfile.TemporaryDirectory() as root:
            run_id = _open_fast(root)
            fast_cycle_audit.abort_fast(root, run_id, reason="테스트 종료",
                                        stage="plan", actual_risk="L3")
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "STANDARD")

    def test_another_stems_active_run_is_not_this_cycles_mode(self):
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root, stem="other")
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "STANDARD")

    def test_an_absent_audit_is_standard(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "STANDARD")

    def test_a_malformed_audit_is_unknown_not_standard(self):
        with tempfile.TemporaryDirectory() as root:
            self._audit(root, '{"event":"fast_open"\n')
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")

    def test_a_partially_written_audit_is_unknown(self):
        """락 없이 읽으므로 append 중간을 볼 수 있다. 그 상태를 정상으로 위장하지 않는다."""
        with tempfile.TemporaryDirectory() as root:
            self._audit(root,
                        '{"event":"fast_open","run_id":"fc-1","cycle_stem":"demo","seq":0}\n'
                        '{"event":"fast_cl')
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")

    def test_an_oversized_audit_is_unknown(self):
        with tempfile.TemporaryDirectory() as root:
            self._audit(root, "\n" * (fast_cycle_audit._chain.READ_ONLY_MAX_BYTES + 10))
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")

    def test_a_symlinked_audit_is_unknown(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".sage"))
            real = os.path.join(root, "elsewhere.jsonl")
            with open(real, "w", encoding="utf-8") as fh:
                fh.write('{"event":"fast_open","run_id":"fc-1","cycle_stem":"demo","seq":0}\n')
            os.symlink(real, os.path.join(root, ".sage", "fast_cycle.jsonl"))
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")

    def test_reading_the_mode_creates_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            # 쓰기 경로가 남긴 락 파일은 정상이다. 조회 **전후**의 차이를 본다.
            before = sorted(os.listdir(os.path.join(root, ".sage")))
            fast_cycle_audit.mode_for_stem(root, "demo")
            self.assertEqual(sorted(os.listdir(os.path.join(root, ".sage"))), before)

    def test_reading_the_mode_never_creates_the_sage_directory(self):
        with tempfile.TemporaryDirectory() as root:
            fast_cycle_audit.mode_for_stem(root, "demo")
            self.assertFalse(os.path.exists(os.path.join(root, ".sage")))

    def test_the_snapshot_agrees_with_the_locked_summary(self):
        """두 경로가 같은 바이트에서 다른 상태를 내면 해석기가 둘이 된 것이다."""
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            locked = fast_cycle_audit.audit_summary(root)
            snapshot = fast_cycle_audit.snapshot(root)
            snapshot.pop("status")
            self.assertEqual(locked, snapshot)

    def test_status_reports_the_mode(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _phase00(root, "demo")
            _open_fast(root)
            _, out, _ = _run(S, root=root, json=True)
            self.assertEqual(json.loads(out)["cycle"]["mode"], "FAST")

    def test_status_still_takes_no_audit_lock(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _phase00(root, "demo")
            self._audit(root, '{"event":"fast_open","run_id":"fc-1","cycle_stem":"demo","seq":0}\n')
            before = sorted(os.listdir(os.path.join(root, ".sage")))
            _run(S, root=root, json=True)
            self.assertEqual(sorted(os.listdir(os.path.join(root, ".sage"))), before)

    def test_a_writer_holding_the_lock_does_not_delay_the_snapshot(self):
        """조회가 진행 중인 전이를 기다리면 1~2초 약속이 실제 작업에 인질로 잡힌다."""
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            path = fast_cycle_audit.audit_path(root)
            with fast_cycle_audit._chain._audit_lock(path):
                self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "FAST")


class TestEveryBlockNamesItsNextAction(unittest.TestCase):
    """차단 경로가 하나라도 렌더러를 우회하면 그 차단만 조용히 안내를 잃는다."""

    BOOTSTRAP = ("entry.profile_yaml_unreadable", "entry.compiled_profile_unreadable",
                 "entry.profile_not_mapping", "entry.raw_risk_type",
                 "entry.profile_pair_mismatch", "entry.core_load_failed",
                 "entry.dispatch_failed")

    def test_bootstrap_codes_are_declared_blocks(self):
        for code in self.BOOTSTRAP:
            self.assertEqual(SEVERITY.get(code), BLOCK, code)

    def test_bootstrap_codes_have_recovery(self):
        for code in self.BOOTSTRAP:
            self.assertTrue(recovery_for(code), code)

    def test_bootstrap_block_carries_code_and_next_on_both_hosts(self):
        for runtime in ("claude", "codex"):
            with tempfile.TemporaryDirectory() as root:
                err = io.StringIO()
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    rc = hook_entry._render_bootstrap_block(
                        runtime, "pre-implementation-gate",
                        Diagnostic("entry.profile_pair_mismatch"), HOOKS, root)
                self.assertEqual(rc, 2)
                self.assertIn("entry.profile_pair_mismatch", err.getvalue())
                self.assertIn("Next:", err.getvalue())

    def test_codex_bootstrap_block_stays_on_one_line(self):
        with tempfile.TemporaryDirectory() as root:
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                hook_entry._render_bootstrap_block(
                    "codex", "pre-implementation-gate",
                    Diagnostic("entry.profile_pair_mismatch"), HOOKS, root)
            self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
            self.assertIn(" | Next:", err.getvalue())

    def test_the_write_guard_keeps_its_next_when_the_catalog_is_gone(self):
        original = GUARD._hook_catalog
        GUARD._hook_catalog = lambda: None
        try:
            message = GUARD.block_message("templates/core/framework/docs/agent/x.md")
        finally:
            GUARD._hook_catalog = original
        self.assertIn("guard.generated_asset", message)
        self.assertIn("Next:", message)

    def test_the_write_guard_renders_body_and_next_normally(self):
        message = GUARD.block_message("templates/core/framework/docs/agent/x.md")
        self.assertIn("Next:", message)
        self.assertGreater(len(message.splitlines()), 2)


class TestRecoveryOracleHasTeeth(unittest.TestCase):
    """검사에 이빨이 있는지 확인하지 않으면, 검사가 무치여도 초록으로 보인다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for name in ("scripts", "sage"):
            shutil.copytree(os.path.join(REPO, name), os.path.join(self.tmp, name))
        self.recovery = os.path.join(self.tmp, "scripts", "sage_harness", "hooks",
                                     "runtime", "recovery.py")
        with open(self.recovery, encoding="utf-8") as fh:
            self.original = fh.read()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mutate(self, old, new):
        self.assertIn(old, self.original)
        with open(self.recovery, "w", encoding="utf-8") as fh:
            fh.write(self.original.replace(old, new))
        return V.recovery_issues(self.tmp)

    def test_the_unmutated_tree_passes(self):
        self.assertEqual(V.recovery_issues(self.tmp), [])

    def test_renaming_a_shared_recovery_id_is_caught(self):
        issues = self._mutate('CYCLE_SHOW = ("cycle-show", "sage cycle show"',
                              'CYCLE_SHOW = ("cycle-show-renamed", "sage cycle list"')
        self.assertTrue(any("cycle-show" in issue for issue in issues), issues)

    def test_a_destructive_hook_only_command_is_caught(self):
        issues = self._mutate('MOVE_OFF_DESKTOP = ("move-off-desktop", None,',
                              'MOVE_OFF_DESKTOP = ("move-off-desktop", "rm -rf .sage",')
        self.assertTrue(any("금지" in issue or "forbidden" in issue for issue in issues), issues)

    def test_dropping_a_declared_hook_only_id_is_caught(self):
        issues = self._mutate('    "guard.desktop_path": (EXPLAIN, MOVE_OFF_DESKTOP),\n', "")
        self.assertTrue(issues)

    def test_the_declared_asymmetries_are_all_real(self):
        """예외 목록이 실제 표와 어긋나면 그것도 드리프트다."""
        self.assertEqual(V.recovery_issues(REPO), [])

    def test_asymmetry_declarations_are_disjoint(self):
        self.assertFalse(V.HOOK_ONLY_RECOVERY_IDS & V.CLI_ONLY_RECOVERY_IDS)


class TestExplainRefusesAnUnrealRoot(unittest.TestCase):

    def test_a_missing_root_is_a_tool_error(self):
        rc, _out, err = _run(E, root=os.path.join(tempfile.gettempdir(), "sage-no-such-dir"),
                             path="src/a.py")
        self.assertEqual(rc, 2)
        self.assertTrue(err.strip())

    def test_it_does_not_describe_the_path_anyway(self):
        _rc, out, _ = _run(E, root=os.path.join(tempfile.gettempdir(), "sage-no-such-dir"),
                           path="src/a.py", json=True)
        self.assertEqual(out, "")

    def test_status_and_explain_refuse_the_same_root(self):
        missing = os.path.join(tempfile.gettempdir(), "sage-no-such-dir")
        self.assertEqual(_run(S, root=missing, json=True)[0],
                         _run(E, root=missing, path="a.py", json=True)[0])

    def test_a_real_root_still_works(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            self.assertEqual(_run(E, root=root, path="src/a.py", json=True)[0], 0)


class TestOneBrokenAreaDoesNotEraseTheRest(unittest.TestCase):
    """예외 하나가 이미 수집한 사실과 복구를 지우면 남는 건 예외 class 이름뿐이다."""

    def _with_broken_cycle(self, root):
        import sage.diagnostic_collectors as C
        original = C.collect_cycle

        def explode(*_a, **_kw):
            raise RuntimeError("collector exploded")
        C.collect_cycle = explode
        try:
            return _run(S, root=root, json=True)
        finally:
            C.collect_cycle = original

    def test_the_other_areas_survive(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _, out, _ = self._with_broken_cycle(root)
            payload = json.loads(out)
            self.assertEqual(payload["runtime_api"]["current"], HOOK_RUNTIME_API)
            self.assertTrue(payload["version"]["required"])

    def test_the_broken_area_is_named_by_a_stable_code(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _, out, _ = self._with_broken_cycle(root)
            payload = json.loads(out)
            broken = [d for d in payload["diagnostics"]
                      if d["code"] == "status.area_unavailable"]
            self.assertEqual(len(broken), 1)
            self.assertEqual(broken[0]["evidence"]["area"], "cycle")

    def test_the_broken_area_still_offers_a_next_action(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _, out, _ = self._with_broken_cycle(root)
            broken = [d for d in json.loads(out)["diagnostics"]
                      if d["code"] == "status.area_unavailable"][0]
            self.assertTrue(broken["recovery"])

    def test_a_collector_failure_exits_two_not_one(self):
        """프로젝트가 차단된 것이 아니라 도구가 자기 일을 못 한 것이다."""
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            rc, _out, _ = self._with_broken_cycle(root)
            self.assertEqual(rc, 2)

    def test_a_healthy_project_never_reports_an_unavailable_area(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _, out, _ = _run(S, root=root, json=True)
            codes = [d["code"] for d in json.loads(out)["diagnostics"]]
            self.assertNotIn("status.area_unavailable", codes)


class TestVersionSeverityHasOneOwner(unittest.TestCase):
    """정본이 가진 severity 를 버리고 다시 정하면 두 번째 판정이 생긴다."""

    def test_every_version_code_comes_from_the_contract_registry(self):
        declared = {code for code in SEVERITY if code.startswith("version.")}
        # `version.runtime_mismatch` 는 version_contract 가 아니라 hook preflight 의 code 다.
        self.assertEqual(declared - {"version.runtime_mismatch"}, set(ISSUE_SEVERITY))

    def test_the_mapping_is_exact(self):
        expected = {"FAIL": BLOCK, "WARN": "WARN", "INFO": "INFO"}
        for code, level in ISSUE_SEVERITY.items():
            self.assertEqual(SEVERITY[code], expected[level], code)

    def test_a_new_contract_code_cannot_default_to_info(self):
        """등록되지 않은 code 가 조용히 INFO 로 떨어지는 경로를 막는다."""
        import sage.version_contract as VC
        import importlib
        import sage.diagnostic_contract as DC
        VC.ISSUE_SEVERITY["version.invented_axis"] = "FAIL"
        try:
            importlib.reload(DC)
            self.assertEqual(DC.SEVERITY["version.invented_axis"], DC.BLOCK)
        finally:
            del VC.ISSUE_SEVERITY["version.invented_axis"]
            importlib.reload(DC)


class TestUnreadableManifestDoesNotFailOpenForProjectHooks(unittest.TestCase):
    """예외 목록은 **닫혀** 있어야 한다. 열어두면 이름을 모르는 정책 hook 이 통과한다."""

    def _rc(self, hook, enforcing):
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, "docs", "sage_harness")
            os.makedirs(d)
            with open(os.path.join(d, ".manifest.json"), "w", encoding="utf-8") as fh:
                fh.write("{ broken")
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                return hook_entry._runtime_api_preflight("claude", hook, root, HOOKS, enforcing)

    def test_an_unknown_project_hook_still_blocks(self):
        self.assertEqual(self._rc("custom-security-gate", True), 2)

    def test_a_built_in_gate_still_blocks(self):
        self.assertEqual(self._rc("pre-implementation-gate", True), 2)

    def test_only_named_built_ins_are_exempt(self):
        for hook in hook_entry._NON_ENFORCING_HOOKS:
            with self.subTest(hook=hook):
                self.assertEqual(self._rc(hook, True), 0)

    def test_the_exemption_list_is_a_subset_of_built_ins(self):
        self.assertTrue(hook_entry._NON_ENFORCING_HOOKS.isdisjoint(hook_entry._FAIL_CLOSED_HOOKS))

    def test_a_non_enforcing_caller_is_still_respected(self):
        self.assertEqual(self._rc("custom-security-gate", False), 0)


class TestGateReadinessMatchesTheRealGate(unittest.TestCase):
    """조회가 게이트보다 엄격하면 사용자는 존재하지 않는 차단을 고치러 간다."""

    def test_an_incomplete_fast_setup_is_not_exempt(self):
        """opener 만 있고 composite Fast Plan 이 없으면 게이트는 면제하지 않는다."""
        from sage import gate_readiness
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _phase00(root, "demo")
            _open_fast(root)
            exempt, detail = gate_readiness.fast_exemption(
                root, PROFILE, "demo", ["00", "01", "02"])
            self.assertFalse(exempt)
            # 사유가 있으면 게이트는 막는다 — 그 사유가 호출부까지 올라와야 한다.
            self.assertTrue(detail)

    def test_the_query_reports_the_gates_own_reason(self):
        from sage import gate_readiness
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _phase00(root, "demo")
            _open_fast(root)
            state, detail = gate_readiness.fast_state(root, PROFILE, "demo")
            self.assertIsNone(state)
            self.assertTrue(detail)

    def test_no_active_run_means_no_exemption(self):
        from sage import gate_readiness
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _phase00(root, "demo")
            self.assertEqual(gate_readiness.fast_exemption(
                root, PROFILE, "demo", ["00", "01", "02"]), (False, None))

    def test_status_reports_the_same_missing_list_as_the_gate(self):
        from sage import gate_readiness
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _phase00(root, "demo")
            _open_fast(root)
            _, out, _ = _run(S, root=root, json=True)
            payload = json.loads(out)
            _present, missing, _fast = gate_readiness.phase_readiness(
                root, PROFILE, "demo", ["00", "01", "02"])
            self.assertEqual(list(payload["gate"]["missing"]), list(missing))

    def test_a_standard_cycle_is_still_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _phase00(root, "demo")
            _, out, _ = _run(S, root=root, json=True)
            self.assertIn("gate.phase_incomplete",
                          [d["code"] for d in json.loads(out)["diagnostics"]])

    def test_unjudgeable_readiness_is_not_nonblocking(self):
        """판정하지 못한 것은 준비됐다는 뜻이 아니다."""
        from sage.diagnostic_contract import severity_of
        self.assertEqual(severity_of("gate.readiness_unavailable"), BLOCK)


class TestSemanticAuditDamageIsUnknown(unittest.TestCase):
    """줄이 전부 유효한 JSON 이어도 감사가 말이 안 되면 mode 를 지어내지 않는다."""

    def _audit(self, root, body):
        os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
        with open(os.path.join(root, ".sage", "fast_cycle.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(body)

    OPEN = '{"event":"fast_open","run_id":"%s","cycle_stem":"demo","seq":0}\n'

    def test_two_active_runs_for_one_stem_are_unknown(self):
        """감사 API 는 이 상태를 거부한다. 파일에 직접 만들어 조회 쪽을 확인한다."""
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            path = fast_cycle_audit.audit_path(root)
            with open(path, encoding="utf-8") as fh:
                first = fh.read()
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(first.replace('"run_id": "fc-', '"run_id": "fd-'))
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")

    def test_a_duplicated_opener_is_unknown(self):
        with tempfile.TemporaryDirectory() as root:
            self._audit(root, (self.OPEN % "fc-1") + (self.OPEN % "fc-1"))
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")

    def test_a_damaged_run_elsewhere_still_makes_it_unknown(self):
        """다른 run 이 깨졌는데 내 run 만 보고 FAST 라고 답하지 않는다."""
        with tempfile.TemporaryDirectory() as root:
            self._audit(root, (self.OPEN % "fc-1")
                        + '{"event":"fast_open","run_id":"fc-9","cycle_stem":"other","seq":0}\n'
                        + '{"event":"fast_open","run_id":"fc-9","cycle_stem":"other","seq":0}\n')
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")

    def test_one_clean_active_run_is_still_fast(self):
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "FAST")


class TestRuntimeDirectBlocksCarryRecovery(unittest.TestCase):
    """게이트를 세우지 못한 실패도 사용자에게는 BLOCK 이다."""

    def test_the_runtime_block_names_a_code(self):
        import hook_runtime
        text = hook_runtime._runtime_block("pre-phase4-checklist-gate",
                                           "runtime.core_failure", "KeyError: x")
        self.assertIn("runtime.core_failure", text)

    def test_the_runtime_block_names_a_next_action(self):
        import hook_runtime
        text = hook_runtime._runtime_block("pre-phase4-checklist-gate",
                                           "runtime.core_failure", "KeyError: x")
        self.assertIn("Next: ", text)

    def test_an_unmapped_code_still_falls_back_to_a_next(self):
        import hook_runtime
        text = hook_runtime._runtime_block("x", "runtime.invented_code", "boom")
        self.assertIn("Next: ", text)

    def test_the_runtime_codes_have_recovery_entries(self):
        import recovery
        for code in ("runtime.core_failure", "runtime.project_hook_contract"):
            with self.subTest(code=code):
                self.assertTrue(recovery.steps_for(code), code)


class TestCodexStopKeepsItsWireContract(unittest.TestCase):
    """차단 사유가 무엇이든 Codex Stop 은 stdout 단일 JSON + rc 0 이다."""

    def _render(self, runtime, hook, code):
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as root, \
                redirect_stdout(out), redirect_stderr(err):
            rc = hook_entry._render_bootstrap_block(
                runtime, hook, Diagnostic(code, path="x", hook=hook, evidence="E: y"),
                HOOKS, root)
        return rc, out.getvalue(), err.getvalue()

    def test_core_load_failure_on_codex_stop_is_json_with_rc_zero(self):
        rc, out, err = self._render("codex", "stop-compliance-report",
                                    "entry.core_load_failed")
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        self.assertEqual(json.loads(out)["decision"], "block")

    def test_dispatch_failure_on_codex_stop_is_json_with_rc_zero(self):
        rc, out, _ = self._render("codex", "stop-compliance-report",
                                  "entry.dispatch_failed")
        self.assertEqual(rc, 0)
        self.assertIn("Next: ", json.loads(out)["reason"])

    def test_claude_stop_still_uses_stderr_and_a_blocking_exit(self):
        rc, out, err = self._render("claude", "stop-compliance-report",
                                    "entry.core_load_failed")
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn("entry.core_load_failed", err)

    def test_codex_pretooluse_still_uses_stderr(self):
        rc, out, err = self._render("codex", "pre-implementation-gate",
                                    "entry.core_load_failed")
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn(" | ", err)


class TestToolFailureIsNotAPolicyBlock(unittest.TestCase):

    def test_a_broken_collector_reports_error_not_blocked(self):
        import sage.diagnostic_collectors as C
        original = C.collect_cycle
        C.collect_cycle = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with tempfile.TemporaryDirectory() as root:
                _project(root)
                rc, out, _ = _run(S, root=root, json=True)
        finally:
            C.collect_cycle = original
        self.assertEqual(json.loads(out)["status"], "ERROR")
        self.assertEqual(rc, 2)

    def test_error_is_a_declared_status_token(self):
        with open(os.path.join(REPO, "plan_docs", "01-plan",
                               "sage-operability-diagnostics.md"),
                  encoding="utf-8") as handle:
            self.assertIn("`ERROR`", handle.read())

class TestTheRealParserSeesEveryAcceptanceRow(unittest.TestCase):
    """저장소의 **실제** 파서로 대조한다.

    이전에는 내가 쓴 임시 regex 로 "92/92 대응" 을 확인했다. 그건 이 사이클이 내내 없애려던
    두 번째 해석기를 검증 쪽에 만든 것이고, 실제 파서는 61개만 읽으면서도 오류를 내지 않았다 —
    보이지 않는 행은 미해결로도 잡히지 않기 때문이다.
    """

    PLAN = os.path.join(REPO, "plan_docs", "01-plan", "sage-operability-diagnostics.md")
    REPORT = os.path.join(REPO, "plan_docs", "04-analyze", "sage-operability-diagnostics.md")
    POLICY = {"statuses": ("PASS", "FAIL", "NOT TESTED", "N/A"),
              "unresolved": ("FAIL", "NOT TESTED")}

    def setUp(self):
        if not (os.path.exists(self.PLAN) and os.path.exists(self.REPORT)):
            self.skipTest("phase 문서는 .gitignore 대상이라 소비 환경에는 없다")
        with open(self.PLAN, encoding="utf-8") as fh:
            self.plan = fh.read()
        with open(self.REPORT, encoding="utf-8") as fh:
            self.report = fh.read()

    def _text_ids(self, content):
        return [m.group(1) for m in re.finditer(r"^\| (OPD-AC\d+) \|", content, re.M)]

    def test_the_parser_sees_every_row_the_text_contains(self):
        gate = _load_gate()
        matrix = gate._acceptance_matrix(self.plan)
        self.assertEqual(len(matrix["all"]), len(self._text_ids(self.plan)))

    def test_the_evidence_parser_sees_every_row_too(self):
        gate = _load_gate()
        rows = gate._acceptance_evidence_rows(self.report)
        self.assertEqual(len(rows), len(self._text_ids(self.report)))

    def test_the_last_id_is_visible_to_the_parser(self):
        """마지막 ID 가 보이는지 본다 — 표가 중간에 잘리면 여기서 걸린다."""
        gate = _load_gate()
        text_last = self._text_ids(self.plan)[-1]
        self.assertEqual(gate._acceptance_matrix(self.plan)["all"][-1], text_last)
        self.assertEqual(gate._acceptance_evidence_rows(self.report)[-1]["id"], text_last)

    def test_both_sides_agree_exactly(self):
        gate = _load_gate()
        required = set(gate._acceptance_matrix(self.plan)["required"])
        evidence = {row["id"] for row in gate._acceptance_evidence_rows(self.report)}
        self.assertEqual(required - evidence, set())
        self.assertEqual(evidence - required, set())

    def test_the_gate_reports_no_structural_error_and_nothing_unresolved(self):
        gate = _load_gate()
        structural, unresolved = gate.acceptance_findings(
            self.plan, self.report, self.POLICY,
            plan_path="01", report_path="04")
        self.assertEqual(structural, [])
        self.assertEqual(unresolved, [])

    def test_an_id_only_in_the_plan_is_reported_as_missing_evidence(self):
        """검사에 이빨이 있는가 — 증거 없는 요구가 실제로 잡히는가.

        분류는 **구조 오류**다(`04 acceptance evidence 에 01 matrix required ID 누락`).
        `미해결` 은 증거 행이 있고 그 상태가 FAIL·NOT TESTED 인 경우의 분류이므로, 증거 행이
        아예 없는 이 반례는 그 통로로 오지 않는다. 이름이 분류와 어긋나면 다음 사람이 잡히는
        이유를 잘못 읽는다.

        이전 판은 이미 있는 ID 를 다시 끼워 넣어서 duplicate 로 통과했다. 그건 "증거 없는
        요구를 잡는다" 를 확인한 것이 아니라, 다른 검사가 켜진 것을 보고 이 검사가 살아
        있다고 결론지은 것이다.
        """
        gate = _load_gate()
        new_id = "OPD-AC900"
        self.assertNotIn(new_id, self.plan + self.report, "충돌하지 않는 ID 여야 한다")
        plan = self.plan.replace("| OPD-AC92 |",
                                 f"| {new_id} | 증거 없는 요구 | B3 |\n| OPD-AC92 |", 1)
        structural, unresolved = gate.acceptance_findings(
            plan, self.report, self.POLICY, plan_path="01", report_path="04")
        found = [item for item in structural + unresolved if new_id in str(item)]
        self.assertTrue(found, structural + unresolved)
        # 잡히는 이유까지 고정한다. duplicate 로 잡히면 이 검사는 다른 검사가 켜진 것을 본 것이다.
        self.assertNotIn("중복", " ".join(str(item) for item in found))


class TestRootResolutionIsTheSameForBothCommands(unittest.TestCase):
    """root 미확정은 판정이 아니라 도구 오류다."""

    def _run_in(self, cwd, argv):
        return subprocess.run([sys.executable, "-m", "sage.cli", *argv],
                              capture_output=True, text=True, cwd=cwd,
                              env={**os.environ, "PYTHONPATH": REPO})

    def test_status_refuses_an_unmarked_directory(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(self._run_in(empty, ["status", "--json"]).returncode, 2)

    def test_explain_refuses_the_same_directory(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(
                self._run_in(empty, ["explain", "--path", "a.py", "--json"]).returncode, 2)

    def test_explain_prints_nothing_when_the_root_is_unresolved(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(
                self._run_in(empty, ["explain", "--path", "a.py", "--json"]).stdout, "")

    def test_both_commands_agree(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(self._run_in(empty, ["status", "--json"]).returncode,
                             self._run_in(empty, ["explain", "--path", "a.py"]).returncode)

    def test_a_marked_project_still_resolves(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
            self.assertNotEqual(self._run_in(root, ["status", "--json"]).returncode, 2)


class TestOpenerCompletenessIsShared(unittest.TestCase):
    """opener 판정의 정본은 하나다 — 조회와 무결성이 같은 함수를 쓴다."""

    def _audit(self, root, body):
        os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
        with open(os.path.join(root, ".sage", "fast_cycle.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(body)

    def _real_open(self, root, stem="demo"):
        """실제 API 가 쓴 opener. 손으로 지은 dict 를 정상이라고 박제하지 않는다."""
        fast_cycle_audit.open_fast(
            root, cycle_stem=stem, actual_risk="L3", fast_review_level="L2",
            reason="테스트", minimum_rounds=2, lenses=["a", "b"],
            profile_hash="sha256:" + "0" * 64, plan_hash_open="sha256:" + "1" * 64)
        summary = fast_cycle_audit.audit_summary(root)
        return summary["runs"][summary["active"][0]]

    def test_a_hand_written_one_line_opener_is_unknown(self):
        with tempfile.TemporaryDirectory() as root:
            self._audit(root, '{"event":"fast_open","run_id":"fc-1",'
                              '"cycle_stem":"demo","seq":0}\n')
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")

    def test_the_same_one_line_opener_is_an_integrity_issue(self):
        """조회가 UNKNOWN 이라 한 것을 무결성이 무해하다고 하면 정본이 둘이다.

        실제로 그 상태였다. `mode_for_stem` 은 UNKNOWN, `integrity_issues()` 는 빈 목록.
        어느 쪽이 옳은지 판정할 근거가 없고, 사용자는 둘 다 믿지 못한다.
        """
        with tempfile.TemporaryDirectory() as root:
            self._audit(root, '{"event":"fast_open","run_id":"fc-1",'
                              '"cycle_stem":"demo","seq":0}\n')
            self.assertTrue(fast_cycle_audit.integrity_issues(root))

    def test_both_paths_flag_exactly_the_same_runs(self):
        with tempfile.TemporaryDirectory() as root:
            self._audit(root, '{"event":"fast_open","run_id":"fc-1",'
                              '"cycle_stem":"demo","seq":0}\n')
            summary = fast_cycle_audit.audit_summary(root)
            flagged = {rid for rid in summary["runs"]
                       if fast_cycle_audit.run_issues(summary["runs"][rid])}
            reported = {item["arguments"].get("run_id")
                        for item in fast_cycle_audit.integrity_issues(root)}
            self.assertEqual(flagged, reported - {None})

    def test_an_unverified_chain_is_not_treated_as_verified(self):
        """`chain_ok is None` 은 "검증했더니 괜찮다" 가 아니라 "검증할 것이 없었다" 다."""
        with tempfile.TemporaryDirectory() as root:
            state = dict(self._real_open(root), chain_ok=None)
        self.assertTrue(fast_cycle_audit.opener_issues(state))
        self.assertIn("fast_cycle_audit.chain_unverified",
                      [code for code, _ in fast_cycle_audit.run_issues(state)])

    def test_a_real_opener_written_by_the_api_is_fast(self):
        with tempfile.TemporaryDirectory() as root:
            self._real_open(root)
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "FAST")
            self.assertEqual(fast_cycle_audit.integrity_issues(root), [])

    def test_every_required_opener_field_is_checked(self):
        """base 는 실제 API 가 쓴 상태다. 손으로 지으면 빠뜨린 필드가 계약에서도 빠진다."""
        with tempfile.TemporaryDirectory() as root:
            base = self._real_open(root)
        self.assertEqual(fast_cycle_audit.opener_issues(base), [])
        required = (fast_cycle_audit.OPENER_REQUIRED
                    + fast_cycle_audit.OPENER_REQUIRED_BY_MODE["FAST"])
        for field in required:
            with self.subTest(field=field):
                self.assertIn(field, base, "계약이 요구하는 필드를 실제 opener 가 쓰지 않는다")
                self.assertTrue(fast_cycle_audit.opener_issues(dict(base, **{field: None})),
                                field)

    def test_an_opener_missing_its_lenses_or_plan_hash_is_not_fast(self):
        """chain 이 성해도 담보가 없으면 Fast 계약을 세운 run 이 아니다."""
        for field in ("lenses", "plan_hash_open"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as root:
                self._real_open(root)
                path = fast_cycle_audit.audit_path(root)
                with open(path, encoding="utf-8") as fh:
                    record = json.loads(fh.read().strip())
                record.pop(field, None)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")

    def test_a_converted_opener_keeps_its_own_collateral(self):
        """두 opener 는 담보가 다르다 — 한 집합으로 묶으면 정상 전환 run 이 손상이 된다."""
        with tempfile.TemporaryDirectory() as root:
            _convert_fast(root, minimum_rounds=2)
            self.assertEqual(fast_cycle_audit.integrity_issues(root), [])
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "FAST")


class TestFastReadinessUsesTheWholeGateValidation(unittest.TestCase):
    """leaf predicate 하나만 부르면 게이트가 막는 프로젝트를 준비됐다고 말한다."""

    PROFILE = {"pdca": {"enabled": True,
                        "phases": [{"id": "00", "glob": "plan_docs/00-base_plan/*.md"},
                                   {"id": "01", "glob": "plan_docs/01-plan/*.md"},
                                   {"id": "02", "glob": "plan_docs/02-design/*.md"}],
                        "pre_implementation_required": {"L3": ["00", "01", "02"]},
                        "fast_cycle": {"enabled": True}}}

    def _repo(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        d = os.path.join(root, "plan_docs", "00-base_plan")
        os.makedirs(d)
        with open(os.path.join(d, "demo.md"), "w", encoding="utf-8") as fh:
            fh.write("# demo\n\nCycle-Stem: `demo`\nRisk Level: L3\n")
        fast_cycle_audit.open_fast(
            root, cycle_stem="demo", actual_risk="L3", fast_review_level="L2",
            reason="테스트", minimum_rounds=2, lenses=["a", "b"],
            profile_hash="sha256:" + "0" * 64, plan_hash_open="sha256:" + "1" * 64)
        return root

    def test_a_non_composite_phase00_is_not_exempt(self):
        from sage import gate_readiness
        root = self._repo()
        exempt, detail = gate_readiness.fast_exemption(root, self.PROFILE, "demo",
                                                       ["00", "01", "02"])
        self.assertFalse(exempt)
        self.assertIn("composite Fast Plan invalid", detail)

    def test_the_query_and_the_gate_give_the_same_reason(self):
        from sage import gate_readiness
        root = self._repo()
        state, detail = gate_readiness.fast_state(root, self.PROFILE, "demo")
        self.assertIsNone(state)
        self.assertIn("composite Fast Plan invalid", detail)

    def test_the_missing_list_matches_the_gate(self):
        from sage import gate_readiness
        root = self._repo()
        _present, missing, fast_error = gate_readiness.phase_readiness(
            root, self.PROFILE, "demo", ["00", "01", "02"])
        self.assertEqual(missing, ["01", "02"])
        self.assertIn("composite Fast Plan invalid", fast_error)

    def test_the_exemption_is_not_granted_without_an_active_run(self):
        from sage import gate_readiness
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        # Fast 를 시도하지 않은 저장소다 — 면제도 없고 차단 사유도 없다.
        self.assertEqual(gate_readiness.fast_exemption(root, self.PROFILE, "demo",
                                                       ["00", "01", "02"]), (False, None))


class TestRuntimeBlockSurvivesAMissingRecoveryModule(unittest.TestCase):
    """가장 손상된 설치에서 최소 보장이 사라지면 안 된다."""

    def test_the_fallback_survives_without_the_recovery_module(self):
        import hook_runtime
        real = builtins.__import__

        def blocked(name, *a, **kw):
            if name == "recovery" or name.endswith(".recovery"):
                raise ModuleNotFoundError("No module named 'recovery'")
            return real(name, *a, **kw)

        import importlib
        real_import_module = importlib.import_module

        def blocked_module(name, package=None):
            if name.endswith("recovery"):
                raise ModuleNotFoundError("No module named 'recovery'")
            return real_import_module(name, package)

        builtins.__import__ = blocked
        importlib.import_module = blocked_module
        try:
            text = hook_runtime._runtime_block("x", "runtime.core_failure", "boom")
        finally:
            builtins.__import__ = real
            importlib.import_module = real_import_module
        self.assertIn("Next: sage status", text)
        self.assertIn("runtime.core_failure", text)

    def test_it_still_names_the_code_without_the_module(self):
        import hook_runtime
        text = hook_runtime._runtime_block("x", "runtime.core_failure", "boom")
        self.assertIn("runtime.core_failure", text)


def _phase_doc(root, folder, stem):
    d = os.path.join(root, "plan_docs", folder)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{stem}.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# {stem}\n\nCycle-Stem: `{stem}`\n")


class TestUnjudgeableReadinessIsNeverSilent(unittest.TestCase):
    """Fast 판정이 실패했는데 Standard 문서가 다 있으면 조용히 통과하던 자리.

    `_fast_cycle_state` 의 예외를 `(None, detail)` 로 접으면 "Fast 가 아니다" 라는 정상
    답과 모양이 같아진다. 호출부는 그 답을 받아 Standard 문서만 세고, 전부 있으면 아무
    진단도 내지 않는다 — 판정 실패가 화면에서 준비 완료와 구별되지 않는다.
    """

    # `explain` 은 선언 위험도가 아니라 **경로**의 위험도로 답한다. 그래서 이 검사에서는
    # L2 경로도 같은 요구를 받도록 profile 을 넓힌다 — 두 명령이 같은 판정 실패를 보는지가
    # 확인하려는 것이고, 위험도 계산은 여기서 볼 것이 아니다.
    PROFILE = dict(PROFILE, pdca=dict(
        PROFILE["pdca"],
        pre_implementation_required={"L2": ["00", "01", "02"], "L3": ["00", "01", "02"]}))

    def _complete(self, root):
        os.makedirs(os.path.join(root, "sage"), exist_ok=True)
        with open(os.path.join(root, "sage", "project-profile.yaml"), "w", encoding="utf-8") as fh:
            yaml.safe_dump(self.PROFILE, fh)
        with open(os.path.join(root, "sage", "project-profile.json"), "w", encoding="utf-8") as fh:
            json.dump(materialize_profile(self.PROFILE), fh)
        os.makedirs(os.path.join(root, "docs", "sage_harness"), exist_ok=True)
        with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"sage_version": "1.0.0", "host_runtime": "codex", "assets": {},
                       "generator_version": "1.0.0",
                       "runtime_api": {"required": HOOK_RUNTIME_API}}, fh)
        _phase00(root, "demo")
        _phase_doc(root, "01-plan", "demo")
        _phase_doc(root, "02-design", "demo")

    class _Boom:
        """`_fast_cycle_state` 만 터뜨린다. 나머지 게이트 동작은 그대로 둔다."""

        def __enter__(self):
            self.original = pre_implementation_gate_core._fast_cycle_state

            def explode(*_args, **_kw):
                raise RuntimeError("fast judgement exploded")

            pre_implementation_gate_core._fast_cycle_state = explode
            return self

        def __exit__(self, *_exc):
            pre_implementation_gate_core._fast_cycle_state = self.original
            return False

    def test_the_failure_is_not_folded_into_a_normal_answer(self):
        from sage import gate_readiness
        with tempfile.TemporaryDirectory() as root, self._Boom():
            self._complete(root)
            with self.assertRaises(gate_readiness.ReadinessUnavailable):
                gate_readiness.phase_readiness(root, self.PROFILE, "demo",
                                               ["00", "01", "02"])

    def test_a_complete_repository_still_reports_the_failure(self):
        """문서가 전부 있어도 판정하지 못했으면 통과가 아니다."""
        with tempfile.TemporaryDirectory() as root, self._Boom():
            self._complete(root)
            rc, out, _err = _run(S, root=root, json=True)
            payload = json.loads(out)
            self.assertIn("gate.readiness_unavailable",
                          [d["code"] for d in payload["diagnostics"]])
            self.assertNotEqual(rc, 0, "판정하지 못한 상태가 비차단으로 끝나면 안 된다")

    def test_it_does_not_report_an_empty_missing_list_as_readiness(self):
        with tempfile.TemporaryDirectory() as root, self._Boom():
            self._complete(root)
            _rc, out, _err = _run(S, root=root, json=True)
            payload = json.loads(out)
            self.assertNotEqual(payload["status"], "READY")
            self.assertEqual(list(payload["gate"]["present"]), [])

    def test_explain_says_it_too(self):
        with tempfile.TemporaryDirectory() as root, self._Boom():
            self._complete(root)
            _rc, out, _err = _run(E, root=root, path="src/a.py", json=True)
            payload = json.loads(out)
            self.assertIn("gate.readiness_unavailable",
                          [d["code"] for d in payload["diagnostics"]])
            self.assertIsNotNone(payload["phase_readiness"]["unavailable"])

    def test_the_healthy_path_is_unaffected(self):
        """이빨 확인의 반대쪽 — 터뜨리지 않으면 같은 저장소가 통과한다."""
        with tempfile.TemporaryDirectory() as root:
            self._complete(root)
            _rc, out, _err = _run(S, root=root, json=True)
            codes = [d["code"] for d in json.loads(out)["diagnostics"]]
            self.assertNotIn("gate.readiness_unavailable", codes)
            self.assertNotIn("gate.phase_incomplete", codes)


class TestLegacyInstallWarnsAtSessionStart(unittest.TestCase):
    """marker 없는 설치가 화면에서 정상 설치와 구별되지 않으면 고칠 이유를 알 수 없다."""

    LEGACY = {"sage_version": "0.9.0", "host_runtime": "codex", "assets": {},
              "generator_version": "0.9.0"}

    def _preflight(self, hook, runtime="claude"):
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, "docs", "sage_harness")
            os.makedirs(d)
            with open(os.path.join(d, ".manifest.json"), "w", encoding="utf-8") as fh:
                json.dump(self.LEGACY, fh)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stderr(err), redirect_stdout(out):
                rc = hook_entry._runtime_api_preflight(runtime, hook, root, HOOKS, True)
            return rc, out.getvalue(), err.getvalue()

    def test_session_start_warns_on_both_hosts(self):
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime):
                rc, _out, err = self._preflight("session-start-snapshot", runtime)
                self.assertIsNone(rc, "legacy 는 기존 동작이다 — 차단도 조기 종료도 아니다")
                self.assertIn("WARN", err)
                self.assertIn("runtime.api_marker_absent_legacy", err)

    def test_the_codex_warning_stays_on_one_line(self):
        _rc, _out, err = self._preflight("session-start-snapshot", "codex")
        self.assertEqual(len(err.strip().splitlines()), 1, err)

    def test_no_other_hook_repeats_it(self):
        """매 hook 마다 내면 경고가 배경 소음이 된다 — 세션 시작 한 번만 말한다."""
        for hook in ("pre-implementation-gate", "generated-artifact-write-guard",
                     "post-tool-logger", "stop-compliance-report"):
            with self.subTest(hook=hook):
                rc, out, err = self._preflight(hook)
                self.assertIsNone(rc)
                self.assertEqual(err, "")
                self.assertEqual(out, "")

    def test_the_gate_still_runs_on_a_legacy_install(self):
        """WARN 은 표시이지 차단이 아니다. 기존 동작이 그대로여야 시나리오가 성립한다."""
        rc, _out, _err = self._preflight("pre-implementation-gate")
        self.assertIsNone(rc)

    def test_the_warning_names_a_next_action(self):
        _rc, _out, err = self._preflight("session-start-snapshot")
        self.assertTrue("Next:" in err or "Action:" in err, err)



class TestAnInvalidFastDeclarationBlocksTheQueryToo(unittest.TestCase):
    """게이트가 막는 저장소를 조회가 비차단으로 표시하던 자리.

    `_fast_cycle_state` 가 사유를 돌려주면 게이트는 요구 phase 문서가 전부 있어도 막는다
    (`block_fast_cycle_audit`). 그 사유를 버리고 Standard 문서만 세면, 문서를 다 갖춘 덕에
    화면이 통과라고 말한다 — 게이트와 반대되는 답이다.
    """

    PROFILE = dict(PROFILE, pdca=dict(
        PROFILE["pdca"],
        pre_implementation_required={"L2": ["00", "01", "02"], "L3": ["00", "01", "02"]}))

    def _repo(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, "sage"), exist_ok=True)
        with open(os.path.join(root, "sage", "project-profile.yaml"), "w", encoding="utf-8") as fh:
            yaml.safe_dump(self.PROFILE, fh)
        with open(os.path.join(root, "sage", "project-profile.json"), "w", encoding="utf-8") as fh:
            json.dump(materialize_profile(self.PROFILE), fh)
        os.makedirs(os.path.join(root, "docs", "sage_harness"), exist_ok=True)
        with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"sage_version": "1.0.0", "host_runtime": "codex", "assets": {},
                       "generator_version": "1.0.0",
                       "runtime_api": {"required": HOOK_RUNTIME_API}}, fh)
        # Phase 00 은 Standard 문서다. Fast run 은 열려 있으나 composite Fast Plan 이 없다 —
        # 게이트가 `composite Fast Plan invalid` 로 막는 상태.
        _phase00(root, "demo")
        _phase_doc(root, "01-plan", "demo")
        _phase_doc(root, "02-design", "demo")
        _open_fast(root)
        return root

    def test_every_required_document_is_present(self):
        """전제 확인 — 문서를 세는 방식으로는 아무 문제가 없어야 이 반례가 성립한다."""
        from sage import gate_readiness
        root = self._repo()
        _present, missing, _fast = gate_readiness.phase_readiness(
            root, self.PROFILE, "demo", ["00", "01", "02"])
        self.assertEqual(missing, [])

    def test_the_gate_would_still_block(self):
        from sage import gate_readiness
        root = self._repo()
        _state, detail = gate_readiness.fast_state(root, self.PROFILE, "demo")
        self.assertTrue(detail)

    def test_status_does_not_report_it_as_non_blocking(self):
        root = self._repo()
        rc, out, _err = _run(S, root=root, json=True)
        payload = json.loads(out)
        self.assertIn("gate.fast_cycle_invalid", [d["code"] for d in payload["diagnostics"]])
        self.assertNotEqual(rc, 0)
        self.assertNotEqual(payload["status"], "READY")

    def test_the_reason_reaches_the_user(self):
        root = self._repo()
        _rc, out, _err = _run(S, root=root)
        self.assertIn("composite Fast Plan invalid", out)

    def test_explain_says_it_too(self):
        root = self._repo()
        _rc, out, _err = _run(E, root=root, path="src/a.py", json=True)
        payload = json.loads(out)
        self.assertIn("gate.fast_cycle_invalid", [d["code"] for d in payload["diagnostics"]])
        self.assertTrue(payload["phase_readiness"]["fast_cycle_error"])

    def test_explain_does_not_claim_readiness_is_ok(self):
        root = self._repo()
        _rc, out, _err = _run(E, root=root, path="src/a.py")
        self.assertNotIn("요구 문서가 모두 있습니다", out)

    def test_a_healthy_standard_cycle_is_unaffected(self):
        """이빨의 반대쪽 — Fast 를 시도하지 않은 저장소는 조용하다."""
        root = self._repo()
        os.remove(os.path.join(root, ".sage", "fast_cycle.jsonl"))
        _rc, out, _err = _run(S, root=root, json=True)
        codes = [d["code"] for d in json.loads(out)["diagnostics"]]
        self.assertNotIn("gate.fast_cycle_invalid", codes)


class TestEmptyCollateralIsNotCollateral(unittest.TestCase):
    """빈 목록·빈 dict 는 담보가 아니다. 필드가 존재하는 것과 값이 있는 것은 다르다."""

    def _write(self, root, record):
        os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
        with open(os.path.join(root, ".sage", "fast_cycle.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _real_state(self, root):
        _open_fast(root)
        summary = fast_cycle_audit.audit_summary(root)
        return summary["runs"][summary["active"][0]]

    def test_empty_values_count_as_absent(self):
        for value in (None, "", [], {}, (), set()):
            with self.subTest(value=value):
                self.assertTrue(fast_cycle_audit._absent(value))

    def test_zero_and_false_are_values_not_absences(self):
        """정책이 고른 숫자를 없는 것으로 읽으면 반대 방향의 거짓말이 된다."""
        for value in (0, False, 0.0):
            with self.subTest(value=value):
                self.assertFalse(fast_cycle_audit._absent(value))

    def test_an_empty_lens_list_is_not_a_valid_opener(self):
        with tempfile.TemporaryDirectory() as root:
            state = dict(self._real_state(root), lenses=[])
        self.assertTrue(fast_cycle_audit.opener_issues(state))

    def test_an_empty_source_snapshot_is_refused_by_the_writer(self):
        """이제는 기록되기 전에 막는다 — append-only 라 기록 뒤에는 지울 수 없다."""
        with tempfile.TemporaryDirectory() as root:
            _write_source_docs(root, "02")
            with self.assertRaises(fast_cycle_audit.AuditWriteError):
                fast_cycle_audit.convert_fast(
                    root, profile=PROFILE, cycle_stem="demo", current_phase="02",
                    actual_risk="L3", fast_review_level="L2", reason="테스트",
                    confirmed_by="tester", minimum_rounds=2,
                    lenses=["correctness", "error_handling"], source_phases={})
            self.assertFalse(os.path.exists(fast_cycle_audit.audit_path(root)))

    def test_a_real_converted_opener_still_passes(self):
        with tempfile.TemporaryDirectory() as root:
            _convert_fast(root, minimum_rounds=2)
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "FAST")
            self.assertEqual(fast_cycle_audit.integrity_issues(root), [])

    def test_the_common_record_fields_are_checked(self):
        """`ts`·`epoch`·`actor`·`cycle_stem` 이 없는 기록은 감사가 아니라 손으로 쓴 한 줄이다."""
        for field in ("ts", "epoch", "actor", "cycle_stem"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as root:
                _open_fast(root)
                path = fast_cycle_audit.audit_path(root)
                with open(path, encoding="utf-8") as fh:
                    record = json.loads(fh.read().strip())
                record.pop(field, None)
                self._write(root, record)
                self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")
                self.assertTrue(fast_cycle_audit.integrity_issues(root))


class TestToolFailureHasOneOwner(unittest.TestCase):
    """도구가 자기 일을 못 한 것은 정책 차단도 프로젝트 경고도 아니다 — ERROR / rc 2."""

    PROFILE = dict(PROFILE, pdca=dict(
        PROFILE["pdca"],
        pre_implementation_required={"L2": ["00", "01", "02"], "L3": ["00", "01", "02"]}))

    def _repo(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, "sage"), exist_ok=True)
        with open(os.path.join(root, "sage", "project-profile.yaml"), "w", encoding="utf-8") as fh:
            yaml.safe_dump(self.PROFILE, fh)
        with open(os.path.join(root, "sage", "project-profile.json"), "w", encoding="utf-8") as fh:
            json.dump(materialize_profile(self.PROFILE), fh)
        os.makedirs(os.path.join(root, "docs", "sage_harness"), exist_ok=True)
        with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"sage_version": "1.0.0", "host_runtime": "codex", "assets": {},
                       "generator_version": "1.0.0",
                       "runtime_api": {"required": HOOK_RUNTIME_API}}, fh)
        _phase00(root, "demo")
        _phase_doc(root, "01-plan", "demo")
        _phase_doc(root, "02-design", "demo")
        return root

    def test_the_owner_is_one_declared_set(self):
        from sage.diagnostic_contract import TOOL_FAILURE, severity_of, BLOCK as B
        self.assertIn("status.area_unavailable", TOOL_FAILURE)
        self.assertIn("gate.readiness_unavailable", TOOL_FAILURE)
        self.assertIn("cycle.mode_unavailable", TOOL_FAILURE)
        for code in TOOL_FAILURE:
            with self.subTest(code=code):
                # 도구 실패도 다음 행동을 준다 — 상태 토큰만 다르다.
                self.assertEqual(severity_of(code), B)
                self.assertTrue(recovery_for(code))

    def test_aggregate_maps_every_tool_failure_to_error_two(self):
        from sage.diagnostic_contract import TOOL_FAILURE
        for code in sorted(TOOL_FAILURE):
            with self.subTest(code=code):
                self.assertEqual(S.aggregate([Finding(code)]), ("ERROR", 2))

    def test_a_readiness_failure_is_error_not_blocked(self):
        root = self._repo()
        original = pre_implementation_gate_core._fast_cycle_state

        def explode(*_a, **_k):
            raise RuntimeError("boom")

        pre_implementation_gate_core._fast_cycle_state = explode
        try:
            rc, out, _err = _run(S, root=root, json=True)
        finally:
            pre_implementation_gate_core._fast_cycle_state = original
        payload = json.loads(out)
        self.assertEqual(payload["status"], "ERROR")
        self.assertEqual(rc, 2)

    def test_a_mode_failure_is_error_not_attention(self):
        root = self._repo()
        original = fast_cycle_audit.mode_for_stem

        def explode(*_a, **_k):
            raise RuntimeError("boom")

        fast_cycle_audit.mode_for_stem = explode
        try:
            rc, out, _err = _run(S, root=root, json=True)
        finally:
            fast_cycle_audit.mode_for_stem = original
        payload = json.loads(out)
        self.assertIn("cycle.mode_unavailable", [d["code"] for d in payload["diagnostics"]])
        self.assertEqual(payload["status"], "ERROR")
        self.assertEqual(rc, 2)

    def test_a_damaged_audit_is_still_only_a_warning(self):
        """손상된 감사는 프로젝트 상태다. 도구 실패와 같은 토큰을 쓰면 구분이 사라진다."""
        root = self._repo()
        with open(os.path.join(root, ".sage", "fast_cycle.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("{not json\n")
        _rc, out, _err = _run(S, root=root, json=True)
        codes = [d["code"] for d in json.loads(out)["diagnostics"]]
        self.assertIn("cycle.mode_unknown", codes)
        self.assertNotIn("cycle.mode_unavailable", codes)

    def test_explain_returns_two_on_a_tool_failure(self):
        """`explain` 은 판정을 내지 않지만, 설명하지 못한 것은 판정이 아니다."""
        root = self._repo()
        original = pre_implementation_gate_core._fast_cycle_state

        def explode(*_a, **_k):
            raise RuntimeError("boom")

        pre_implementation_gate_core._fast_cycle_state = explode
        try:
            rc, _out, _err = _run(E, root=root, path="src/a.py", json=True)
        finally:
            pre_implementation_gate_core._fast_cycle_state = original
        self.assertEqual(rc, 2)

    def test_explain_still_returns_zero_for_a_policy_block(self):
        root = self._repo()
        rc, out, _err = _run(E, root=root, path=".claude/hooks/x.sh", json=True)
        self.assertEqual(rc, 0)
        self.assertIn("guard.generated_asset",
                      [d["code"] for d in json.loads(out)["diagnostics"]])



FAST_POLICY = {"enabled": True, "reason_required": True,
               "minimum_rounds": {"L2": 1, "L3": 2},
               "minimum_lenses": {"L2": 2, "L3": 3},
               "lenses": {"L2": ["correctness", "error_handling", "security"],
                          "L3": ["correctness", "error_handling", "security", "perf"]}}


def _fast_project(root, profile):
    """Fast 정책이 켜진 프로젝트. profile 은 호출자가 준 것을 그대로 쓴다."""
    os.makedirs(os.path.join(root, "sage"), exist_ok=True)
    with open(os.path.join(root, "sage", "project-profile.yaml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump(profile, fh)
    with open(os.path.join(root, "sage", "project-profile.json"), "w", encoding="utf-8") as fh:
        json.dump(materialize_profile(profile), fh)
    os.makedirs(os.path.join(root, "docs", "sage_harness"), exist_ok=True)
    with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"sage_version": "1.0.0", "host_runtime": "codex", "assets": {},
                   "generator_version": "1.0.0",
                   "runtime_api": {"required": HOOK_RUNTIME_API}}, fh)
    return root


class TestAFastContractBelowThePolicyFloorIsNotFast(unittest.TestCase):
    """문서끼리의 일치와 정책 충족은 다른 질문이다.

    `open_issues` 는 Fast Plan 문서와 감사 open snapshot 이 **서로** 같은지만 본다. 둘이 같은
    값을 담고 있으면 그 값이 정책 하한 아래여도 통과했다 — 리뷰를 하나도 요구하지 않는
    0 round Fast 계약이 Standard 01·02 면제를 받는 통로였다.
    """

    PROFILE = dict(PROFILE, pdca=dict(
        PROFILE["pdca"], fast_cycle=FAST_POLICY,
        pre_implementation_required={"L2": ["00", "01", "02"], "L3": ["00", "01", "02"]}))

    def _state(self, **overrides):
        base = {"fast_review_level": "L2", "minimum_rounds": 1,
                "lenses": ["correctness", "error_handling"]}
        return dict(base, **overrides)

    def test_the_floor_check_accepts_a_compliant_contract(self):
        """이빨의 반대쪽 먼저 — 정책을 만족하는 계약은 통과한다."""
        self.assertIsNone(pre_implementation_gate_core._fast_policy_floor_issue(
            FAST_POLICY, self._state()))

    def test_zero_rounds_is_below_every_floor(self):
        issue = pre_implementation_gate_core._fast_policy_floor_issue(
            FAST_POLICY, self._state(minimum_rounds=0))
        self.assertIn("minimum_rounds", issue)

    def test_a_boolean_is_not_a_round_count(self):
        for value in (True, False, "1", 1.0, None):
            with self.subTest(value=value):
                self.assertTrue(pre_implementation_gate_core._fast_policy_floor_issue(
                    FAST_POLICY, self._state(minimum_rounds=value)))

    def test_too_few_lenses_is_below_the_floor(self):
        issue = pre_implementation_gate_core._fast_policy_floor_issue(
            FAST_POLICY, self._state(lenses=["correctness"]))
        self.assertIn("distinct declared lenses", issue)

    def test_lenses_the_policy_never_declared_do_not_count(self):
        """개수만 맞춘 렌즈 목록은 정책이 요구한 관점으로 본 것이 아니다."""
        issue = pre_implementation_gate_core._fast_policy_floor_issue(
            FAST_POLICY, self._state(lenses=["anything", "goes"]))
        self.assertTrue(issue)
        self.assertIn("0 distinct declared lenses", issue)

    def test_one_lens_written_twice_is_one_lens(self):
        issue = pre_implementation_gate_core._fast_policy_floor_issue(
            FAST_POLICY, self._state(lenses=["correctness", "correctness"]))
        self.assertIn("1 distinct declared lenses", issue)

    def test_a_declared_set_padded_with_an_undeclared_lens_is_reported(self):
        issue = pre_implementation_gate_core._fast_policy_floor_issue(
            FAST_POLICY, self._state(lenses=["correctness", "error_handling", "nope"]))
        self.assertIn("not declared", issue)

    def test_lenses_must_be_a_list(self):
        for value in ("correctness", 2, None, {"correctness": True}):
            with self.subTest(value=value):
                self.assertTrue(pre_implementation_gate_core._fast_policy_floor_issue(
                    FAST_POLICY, self._state(lenses=value)))

    def test_a_real_prefix_of_the_policy_candidates_passes(self):
        """이빨의 반대쪽 — 실제 CLI 가 싣는 값(`candidates[:n]`)은 통과한다."""
        candidates = FAST_POLICY["lenses"]["L2"]
        self.assertIsNone(pre_implementation_gate_core._fast_policy_floor_issue(
            FAST_POLICY, self._state(lenses=list(candidates[:2]))))

    def test_an_undeclared_level_has_no_knowable_floor(self):
        """하한을 모르는 상태를 통과로 읽지 않는다."""
        issue = pre_implementation_gate_core._fast_policy_floor_issue(
            FAST_POLICY, self._state(fast_review_level="standard"))
        self.assertIn("not declared", issue)

    def test_the_l3_floor_is_read_per_level(self):
        self.assertTrue(pre_implementation_gate_core._fast_policy_floor_issue(
            FAST_POLICY, self._state(fast_review_level="L3", minimum_rounds=1,
                                     lenses=["a", "b", "c"])))

    def test_a_zero_round_run_gets_no_exemption(self):
        """실제 `open_fast` 로 만든 0 round run 이 면제를 받지 못한다."""
        from sage import gate_readiness
        with tempfile.TemporaryDirectory() as root:
            _fast_project(root, self.PROFILE)
            _phase00(root, "demo")
            fast_cycle_audit.open_fast(
                root, cycle_stem="demo", actual_risk="L2", fast_review_level="L2",
                reason="테스트", minimum_rounds=0,
                lenses=["correctness", "error_handling"],
                profile_hash="sha256:" + "0" * 64, plan_hash_open="sha256:" + "1" * 64)
            exempt, detail = gate_readiness.fast_exemption(
                root, self.PROFILE, "demo", ["00", "01", "02"])
            self.assertFalse(exempt)
            self.assertTrue(detail)

    def test_status_blocks_a_zero_round_fast_cycle(self):
        with tempfile.TemporaryDirectory() as root:
            _fast_project(root, self.PROFILE)
            _phase00(root, "demo")
            fast_cycle_audit.open_fast(
                root, cycle_stem="demo", actual_risk="L2", fast_review_level="L2",
                reason="테스트", minimum_rounds=0,
                lenses=["correctness", "error_handling"],
                profile_hash="sha256:" + "0" * 64, plan_hash_open="sha256:" + "1" * 64)
            rc, out, _err = _run(S, root=root, json=True)
            payload = json.loads(out)
            self.assertNotEqual(rc, 0)
            self.assertNotEqual(payload["status"], "READY")

    def test_the_audit_layer_also_refuses_zero_rounds(self):
        """정책을 모르는 감사 계층에서도 0 은 계약 위반이다 — schema 하한이 1이다."""
        with tempfile.TemporaryDirectory() as root:
            fast_cycle_audit.open_fast(
                root, cycle_stem="demo", actual_risk="L2", fast_review_level="L2",
                reason="테스트", minimum_rounds=0, lenses=["a", "b"],
                profile_hash="sha256:" + "0" * 64, plan_hash_open="sha256:" + "1" * 64)
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")
            codes = [item["code"] for item in fast_cycle_audit.integrity_issues(root)]
            self.assertIn("fast_cycle_audit.opener_field_invalid", codes)

    def test_a_positive_round_count_still_passes_the_audit_layer(self):
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            self.assertEqual(fast_cycle_audit.integrity_issues(root), [])


class TestTheCycleModuleFailureIsAToolFailure(unittest.TestCase):
    """선언을 읽는 모듈을 못 불러온 것은 프로젝트가 선언을 잘못 쓴 것이 아니다."""

    class _NoCycleState:
        """`cycle_state` import 만 막는다."""

        def __enter__(self):
            self.real = builtins.__import__

            def blocked(name, *args, **kw):
                if name == "cycle_state":
                    raise ImportError("no module named 'cycle_state'")
                return self.real(name, *args, **kw)

            builtins.__import__ = blocked
            sys.modules.pop("cycle_state", None)
            return self

        def __exit__(self, *_exc):
            builtins.__import__ = self.real
            return False

    def _repo(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        return _fast_project(root, PROFILE)

    def test_the_code_is_declared_a_tool_failure(self):
        self.assertIn("cycle.state_unavailable", TOOL_FAILURE)

    def test_status_reports_error_not_a_policy_block(self):
        root = self._repo()
        with self._NoCycleState():
            rc, out, _err = _run(S, root=root, json=True)
        payload = json.loads(out)
        self.assertIn("cycle.state_unavailable", [d["code"] for d in payload["diagnostics"]])
        self.assertEqual(payload["status"], "ERROR")
        self.assertEqual(rc, 2)

    def test_explain_does_not_raise(self):
        root = self._repo()
        with self._NoCycleState():
            rc, out, _err = _run(E, root=root, path="src/a.py", json=True)
        self.assertEqual(rc, 2)
        json.loads(out)

    def test_explain_keeps_its_json_contract(self):
        root = self._repo()
        with self._NoCycleState():
            _rc, out, _err = _run(E, root=root, path="src/a.py", json=True)
        payload = json.loads(out)
        self.assertEqual(payload["schema_version"], 1)
        self.assertTrue(payload["diagnostics"])

    def test_the_last_resort_net_still_produces_parseable_json(self):
        """계층 안에서 잡히지 않은 예외가 와도 `--json` 계약은 깨지지 않는다."""
        root = self._repo()
        original = E.collect

        def explode(*_a, **_k):
            raise RuntimeError("boom")

        E.collect = explode
        try:
            rc, out, _err = _run(E, root=root, path="src/a.py", json=True)
        finally:
            E.collect = original
        self.assertEqual(rc, 2)
        payload = json.loads(out)
        self.assertIn("explain.unavailable", [d["code"] for d in payload["diagnostics"]])

    def test_a_healthy_repository_is_unaffected(self):
        root = self._repo()
        _rc, out, _err = _run(S, root=root, json=True)
        codes = [d["code"] for d in json.loads(out)["diagnostics"]]
        self.assertNotIn("cycle.state_unavailable", codes)



class TestTheGateUsesTheSameOpenerJudgement(unittest.TestCase):
    """게이트는 세 번째 소비자였고, 자기 조건문을 쓰고 있었다.

    `mode_for_stem` 과 `integrity_issues` 를 `run_issues` 하나로 통일했을 때 게이트는 여전히
    `clean`/`chain_ok`/`seq_ok`/`terminal` 넷을 직접 세고 있었다. 그 넷은 감사 **파일**이 말이
    되는가만 보고 opener 가 담보를 실었는가는 보지 않는다. 그래서 `ts` 를 지우고 해시를 다시
    계산한 감사가 조회에서는 손상, 게이트에서는 정상 Fast 였다 — 느슨한 쪽이 게이트였으므로
    그 상태가 Standard 01·02 면제를 받았다.
    """

    PROFILE = dict(PROFILE, pdca=dict(
        PROFILE["pdca"], fast_cycle=FAST_POLICY,
        pre_implementation_required={"L2": ["00", "01", "02"], "L3": ["00", "01", "02"]}))

    def _restamped_without(self, root, field):
        """실제 opener 를 쓰고 한 필드를 지운 뒤 **해시 체인을 다시 맞춘다.**

        지우기만 하면 chain_ok 가 False 가 되어 옛 조건문에도 걸린다. 다시 스탬프해야
        "파일은 말이 되는데 담보가 없는" 상태가 되고, 그게 게이트만 통과시키던 상태다.
        """
        import loop_audit
        _open_fast(root)
        path = fast_cycle_audit.audit_path(root)
        with open(path, encoding="utf-8") as fh:
            record = json.loads(fh.read().strip())
        record.pop(field, None)
        for key in ("prev_hash", "record_hash", "chain_version"):
            record.pop(key, None)
        stamped = loop_audit._stamp_record([], record)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(stamped, ensure_ascii=False) + "\n")
        return root

    def test_the_restamped_audit_really_has_a_valid_chain(self):
        """전제 확인 — 체인이 유효해야 이 반례가 옛 조건문을 통과한다."""
        with tempfile.TemporaryDirectory() as root:
            self._restamped_without(root, "ts")
            summary = fast_cycle_audit.audit_summary(root)
            state = summary["runs"][summary["active"][0]]
            self.assertIs(state["chain_ok"], True)
            self.assertTrue(state["clean"])
            self.assertIsNot(state["seq_ok"], False)
            self.assertFalse(state["terminal"])

    def test_the_query_calls_it_damaged(self):
        with tempfile.TemporaryDirectory() as root:
            self._restamped_without(root, "ts")
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")
            self.assertTrue(fast_cycle_audit.integrity_issues(root))

    def test_the_gate_calls_it_damaged_too(self):
        with tempfile.TemporaryDirectory() as root:
            self._restamped_without(root, "ts")
            summary = fast_cycle_audit.audit_summary(root)
            state = summary["runs"][summary["active"][0]]
            self.assertTrue(pre_implementation_gate_core._opener_contract_issue(state))

    def test_the_gate_grants_no_exemption(self):
        from sage import gate_readiness
        with tempfile.TemporaryDirectory() as root:
            _fast_project(root, self.PROFILE)
            _phase00(root, "demo")
            self._restamped_without(root, "ts")
            exempt, detail = gate_readiness.fast_exemption(
                root, self.PROFILE, "demo", ["00", "01", "02"])
            self.assertFalse(exempt)
            self.assertTrue(detail)

    def test_every_collateral_field_is_checked_at_the_gate(self):
        for field in ("ts", "epoch", "actor", "reason", "lenses", "profile_hash",
                      "plan_hash_open", "cycle_stem"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as root:
                self._restamped_without(root, field)
                summary = fast_cycle_audit.audit_summary(root)
                runs = summary.get("runs") or {}
                if not runs:
                    continue                       # cycle_stem 을 지우면 run 이 stem 을 잃는다
                state = list(runs.values())[0]
                self.assertTrue(
                    pre_implementation_gate_core._opener_contract_issue(state), field)

    def test_the_three_consumers_agree(self):
        """조회·무결성·게이트가 같은 판정을 쓴다."""
        with tempfile.TemporaryDirectory() as root:
            self._restamped_without(root, "actor")
            summary = fast_cycle_audit.audit_summary(root)
            state = summary["runs"][summary["active"][0]]
            self.assertTrue(fast_cycle_audit.run_issues(state))
            self.assertTrue(fast_cycle_audit.integrity_issues(root))
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")
            self.assertTrue(pre_implementation_gate_core._opener_contract_issue(state))

    def test_a_real_opener_passes_all_three(self):
        """이빨의 반대쪽 — 실제 API 가 쓴 opener 는 세 곳 모두 통과한다."""
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            summary = fast_cycle_audit.audit_summary(root)
            state = summary["runs"][summary["active"][0]]
            self.assertEqual(fast_cycle_audit.run_issues(state), [])
            self.assertEqual(fast_cycle_audit.integrity_issues(root), [])
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "FAST")
            self.assertIsNone(pre_implementation_gate_core._opener_contract_issue(state))

    def test_the_contract_has_one_definition(self):
        """감사 모듈과 게이트가 같은 함수를 가리킨다 — 사본이 아니다."""
        from sage.fast_cycle_contract import opener_run_issues
        self.assertIs(fast_cycle_audit.run_issues, opener_run_issues)

    def test_an_unavailable_contract_is_not_a_pass(self):
        """계약 모듈을 부르지 못하면 통과시키지 않는다."""
        real = builtins.__import__

        def blocked(name, *args, **kw):
            if name == "sage.fast_cycle_contract":
                raise ImportError("no contract")
            return real(name, *args, **kw)

        builtins.__import__ = blocked
        try:
            issue = pre_implementation_gate_core._opener_contract_issue({"clean": True})
        finally:
            builtins.__import__ = real
        self.assertTrue(issue)


class TestExplainSplitsItsBoundaryByOperation(unittest.TestCase):
    """예외 class 로 경계를 가르면 같은 연산의 실패가 종류에 따라 다른 축으로 떨어진다."""

    def _repo(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        return _fast_project(root, PROFILE)

    class _LoadFails:
        """`cycle_state` 로드만 주어진 예외로 터뜨린다."""

        def __init__(self, exception):
            self.exception = exception

        def __enter__(self):
            self.real = E._load

            def load(name):
                if name == "cycle_state":
                    raise self.exception
                return self.real(name)

            E._load = load
            return self

        def __exit__(self, *_exc):
            E._load = self.real
            return False

    def test_every_load_failure_is_a_tool_failure(self):
        """ImportError 든 RuntimeError 든 **모듈을 못 불러온 것**은 도구 실패다."""
        for exception in (ImportError("no module"), RuntimeError("boom"),
                          OSError("io"), ValueError("bad"), AttributeError("attr")):
            with self.subTest(exception=type(exception).__name__):
                root = self._repo()
                with self._LoadFails(exception):
                    rc, out, _err = _run(E, root=root, path="src/a.py", json=True)
                codes = [d["code"] for d in json.loads(out)["diagnostics"]]
                self.assertIn("cycle.state_unavailable", codes)
                self.assertNotIn("cycle.declaration_damaged", codes)
                self.assertEqual(rc, 2)

    def test_status_and_explain_agree_on_the_same_failure(self):
        root = self._repo()

        real = builtins.__import__

        def blocked(name, *args, **kw):
            if name == "cycle_state":
                raise RuntimeError("boom")
            return real(name, *args, **kw)

        builtins.__import__ = blocked
        sys.modules.pop("cycle_state", None)
        try:
            status_rc, status_out, _e = _run(S, root=root, json=True)
        finally:
            builtins.__import__ = real
        with self._LoadFails(RuntimeError("boom")):
            explain_rc, explain_out, _e = _run(E, root=root, path="src/a.py", json=True)
        self.assertEqual(status_rc, explain_rc)
        for out in (status_out, explain_out):
            self.assertIn("cycle.state_unavailable",
                          [d["code"] for d in json.loads(out)["diagnostics"]])

    def test_a_damaged_declaration_is_still_a_project_fact(self):
        """이빨의 반대쪽 — 읽어 보니 이상한 것은 도구 실패가 아니다."""
        root = self._repo()
        os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
        with open(os.path.join(root, ".sage", "cycle.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        rc, out, _err = _run(E, root=root, path="src/a.py", json=True)
        codes = [d["code"] for d in json.loads(out)["diagnostics"]]
        self.assertIn("cycle.declaration_damaged", codes)
        self.assertNotIn("cycle.state_unavailable", codes)
        self.assertEqual(rc, 0)



class TestAnUnknownEntryModeCarriesNoWaiver(unittest.TestCase):
    """모르는 mode 를 "요구 없음" 으로 읽지 않는다.

    `OPENER_REQUIRED_BY_MODE.get(mode, ())` 는 모르는 key 를 **빈 담보 집합**으로 돌려준다.
    그래서 `entry_mode` 가 아무 문자열이면 fresh 전용 담보(`profile_hash`·`plan_hash_open`)도
    전환 전용 담보(`source_phases_open`·`confirmed_by`)도 요구되지 않았다 — 부재를 안전
    방향으로 읽는 것과 같은 모양이 dict 조회에서 난 것이다.

    게이트 core 는 순수 함수라 감사를 직접 읽지 않고 adapter 가 준 snapshot 을 그대로 믿는다.
    그래서 이 계약은 **자기가 받은 state 를 검증해야 한다** — 상류가 항상 올바른 값을 준다는
    가정을 계약이 대신 세우면, 그 가정이 틀린 날 계약은 아무 말도 하지 않는다.
    """

    PROFILE = dict(PROFILE, pdca=dict(
        PROFILE["pdca"], fast_cycle=FAST_POLICY,
        pre_implementation_required={"L2": ["00", "01", "02"], "L3": ["00", "01", "02"]}))

    def _state(self, **over):
        """실제 `open_fast` 가 만든 state 에서 출발한다."""
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            summary = fast_cycle_audit.audit_summary(root)
            state = dict(summary["runs"][summary["active"][0]])
        state.update(over)
        return state

    def test_the_starting_state_is_a_real_one(self):
        """이빨의 반대쪽 — 손대지 않은 실제 state 는 통과한다."""
        self.assertEqual(fast_cycle_audit.run_issues(self._state()), [])

    def test_an_unknown_mode_is_an_opener_issue(self):
        codes = [code for code, _ in
                 fast_cycle_audit.run_issues(self._state(entry_mode="FORGED-MODE"))]
        self.assertIn("fast_cycle_audit.opener_mode_unknown", codes)

    def test_the_gate_refuses_it(self):
        self.assertTrue(pre_implementation_gate_core._opener_contract_issue(
            self._state(entry_mode="FORGED-MODE")))

    def test_a_forged_mode_cannot_shed_the_fresh_collateral(self):
        """mode 를 바꿔 `profile_hash`·`plan_hash_open` 요구를 벗어나는 경로."""
        state = self._state(entry_mode="FORGED-MODE", profile_hash=None,
                            plan_hash_open=None)
        self.assertTrue(fast_cycle_audit.run_issues(state))
        self.assertTrue(pre_implementation_gate_core._opener_contract_issue(state))

    def test_a_forged_mode_cannot_shed_the_converted_collateral(self):
        state = self._state(entry_mode="FORGED-MODE", source_phases_open=None,
                            confirmed_by=None)
        self.assertTrue(pre_implementation_gate_core._opener_contract_issue(state))

    def test_the_gate_grants_no_exemption_for_such_a_snapshot(self):
        """게이트가 실제로 소비하는 자리 — adapter 가 준 snapshot 그대로."""
        event = {"changes": [], "cycle_stem": "demo"}
        content = "# demo\n\nCycle-Stem: `demo`\nRisk Level: L2\n"
        snapshot = {"phase_docs": {"00": [{"path": "plan_docs/00-base_plan/demo.md",
                                           "content": content}]},
                    "fast_cycle_audit": {
                        "file_ok": True, "file_issues": [], "active": ["fc-1"],
                        "runs": {"fc-1": self._state(entry_mode="FORGED-MODE")}}}
        state, detail = pre_implementation_gate_core._fast_cycle_state(
            event, self.PROFILE, snapshot, self.PROFILE["pdca"])
        self.assertIsNone(state)
        self.assertTrue(detail)

    def test_the_writer_cannot_produce_an_unknown_mode(self):
        """상류도 닫혀 있는가 — `summarize_records` 는 event 이름에서 mode 를 **유도**한다.

        그래서 감사 파일의 `entry_mode` 필드를 위조해도 state 의 mode 는 바뀌지 않는다.
        이 검사는 그 유도가 계속 닫혀 있는지를 고정한다 — 열리면 위 계약 검사가 유일한
        방어선이 된다.
        """
        import loop_audit
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            path = fast_cycle_audit.audit_path(root)
            with open(path, encoding="utf-8") as fh:
                record = json.loads(fh.read().strip())
            record["entry_mode"] = "FORGED-MODE"
            for key in ("prev_hash", "record_hash", "chain_version"):
                record.pop(key, None)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(loop_audit._stamp_record([], record),
                                    ensure_ascii=False) + "\n")
            summary = fast_cycle_audit.audit_summary(root)
            state = summary["runs"][summary["active"][0]]
        self.assertIn(state["entry_mode"], set(fast_cycle_audit.ENTRY_MODES.values()))

    def test_the_known_modes_are_exactly_the_ones_the_writer_records(self):
        """계약이 아는 mode 와 감사가 쓰는 mode 가 갈리면 이 구멍이 다시 열린다."""
        from sage.fast_cycle_contract import OPENER_REQUIRED_BY_MODE
        self.assertEqual(set(fast_cycle_audit.ENTRY_MODES.values()),
                         set(OPENER_REQUIRED_BY_MODE))

    def test_both_real_modes_still_pass(self):
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            summary = fast_cycle_audit.audit_summary(root)
            self.assertEqual(
                fast_cycle_audit.run_issues(summary["runs"][summary["active"][0]]), [])
        with tempfile.TemporaryDirectory() as root:
            _convert_fast(root, minimum_rounds=2)
            summary = fast_cycle_audit.audit_summary(root)
            self.assertEqual(
                fast_cycle_audit.run_issues(summary["runs"][summary["active"][0]]), [])



def _valid_provenance(current_phase="02"):
    """구조 계약을 만족하는 값. 디스크와 일치하는지는 별개다."""
    from sage.fast_cycle_contract import expected_source_phases
    phases, issue = expected_source_phases(current_phase)
    assert issue is None, issue
    return {phase: {"path": f"plan_docs/{_PHASE_FOLDER[phase]}/demo.md",
                    "sha256": "sha256:" + f"{index}" * 64,
                    "size": 128 + index}
            for index, phase in enumerate(phases)}


def _entry(**over):
    base = {"path": "plan_docs/01-plan/demo.md", "sha256": "sha256:" + "a" * 64, "size": 1}
    base.update(over)
    return base


# 구조 계약이 거부하는 반례. (이름, current_phase, source_phases)
#
# 이 층은 **과거 기록**도 읽는다 — 감사와 게이트가 판정할 때 디스크에는 그 파일이 더 이상 같은
# 내용으로 없을 수 있다(전환 뒤 정상 개발을 허용하는 설계). 그래서 여기서 잡히는 것은 셋 모두에서
# 잡힌다.
STRUCTURAL_COUNTEREXAMPLES = [
    ("빈 스냅샷", "02", {}),
    ("구조 없는 entry", "02", {"00": {}, "01": {}, "02": {}}),
    ("phase 누락", "02", _valid_provenance("01")),
    ("현재 phase 초과", "01", _valid_provenance("02")),
    ("허용되지 않은 phase key", "02",
     dict(_valid_provenance("02"), **{"05": _entry(path="plan_docs/05-x/demo.md")})),
    ("entry 가 dict 아님", "02", dict(_valid_provenance("02"), **{"01": "sha256:abc"})),
    ("entry 가 목록", "02", dict(_valid_provenance("02"), **{"01": ["x"]})),
    ("path 가 `.`", "02",
     {phase: _entry(path=".") for phase in ("00", "01", "02")}),
    ("path 가 `./`", "02", dict(_valid_provenance("02"), **{"01": _entry(path="./")})),
    ("path 가 `./` 접두", "02",
     dict(_valid_provenance("02"), **{"01": _entry(path="./plan_docs/01-plan/demo.md")})),
    ("path 뒤 슬래시", "02",
     dict(_valid_provenance("02"), **{"01": _entry(path="plan_docs/01-plan/")})),
    ("path 빈 문자열", "02", dict(_valid_provenance("02"), **{"01": _entry(path="")})),
    ("path 공백뿐", "02", dict(_valid_provenance("02"), **{"01": _entry(path="   ")})),
    ("path 절대경로", "02", dict(_valid_provenance("02"), **{"01": _entry(path="/etc/passwd")})),
    ("path 상위 이탈", "02",
     dict(_valid_provenance("02"), **{"01": _entry(path="../outside/x.md")})),
    ("path 윈도 드라이브", "02", dict(_valid_provenance("02"), **{"01": _entry(path="C:/x.md")})),
    ("path 빈 성분", "02",
     dict(_valid_provenance("02"), **{"01": _entry(path="plan_docs//demo.md")})),
    ("sha256 누락", "02",
     dict(_valid_provenance("02"), **{"01": {"path": "plan_docs/01-plan/demo.md", "size": 1}})),
    ("sha256 접두 없음", "02", dict(_valid_provenance("02"), **{"01": _entry(sha256="a" * 64)})),
    ("sha256 길이 부족", "02",
     dict(_valid_provenance("02"), **{"01": _entry(sha256="sha256:" + "a" * 63)})),
    ("sha256 대문자", "02",
     dict(_valid_provenance("02"), **{"01": _entry(sha256="sha256:" + "A" * 64)})),
    ("size 누락", "02",
     dict(_valid_provenance("02"), **{"01": {"path": "plan_docs/01-plan/demo.md",
                                             "sha256": "sha256:" + "a" * 64}})),
    ("size 음수", "02", dict(_valid_provenance("02"), **{"01": _entry(size=-1)})),
    ("size 가 bool", "02", dict(_valid_provenance("02"), **{"01": _entry(size=True)})),
    ("size 가 float", "02", dict(_valid_provenance("02"), **{"01": _entry(size=1.0)})),
    ("size 가 문자열", "02", dict(_valid_provenance("02"), **{"01": _entry(size="1")})),
    ("entry 에 모르는 key", "02", dict(_valid_provenance("02"), **{"01": _entry(waived=True)})),
    ("스냅샷이 dict 아님", "02", ["00", "01", "02"]),
    ("스냅샷이 None", "02", None),
    ("current_phase 가 범위 밖", "05", _valid_provenance("02")),
    ("current_phase 가 None", None, _valid_provenance("02")),
]


class TestConvertedProvenanceContract(unittest.TestCase):
    """전환 담보의 **형태**를 계약으로 닫는다.

    `source_phases_open` 은 전환 run 이 Standard 01·02 요구를 면제받는 유일한 근거다. 그 run 은
    composite Fast Plan 문서를 갖지 않으므로, "그때 그 문서들이 실재했다" 는 기록 말고는 담보가
    없다.
    """

    PROFILE = dict(PROFILE, pdca=dict(
        PROFILE["pdca"], fast_cycle=FAST_POLICY,
        pre_implementation_required={"L2": ["00", "01", "02"], "L3": ["00", "01", "02"]}))

    def _state(self, current_phase, source_phases):
        return {"clean": True, "seq_ok": True, "chain_ok": True, "terminal": False,
                "cycle_stem": "demo", "actual_risk": "L2", "fast_review_level": "L2",
                "reason": "전환 사유", "minimum_rounds": 1, "entry_mode": "FAST-CONVERTED",
                "lenses": ["correctness", "error_handling"], "confirmed_by": "tester",
                "current_phase": current_phase, "source_phases_open": source_phases,
                "ts": "2026-08-25T00:00:00Z", "epoch": 1787616000, "actor": "tester"}

    # --- 계약 함수 자체 ---------------------------------------------------

    def test_the_contract_accepts_what_the_writer_produces(self):
        """이빨의 반대쪽 — 실제 writer 가 만든 값은 통과해야 한다."""
        from sage.fast_cycle_contract import converted_provenance_issue
        with tempfile.TemporaryDirectory() as root:
            for phase in ("00", "01", "02"):
                with self.subTest(current_phase=phase):
                    snapshot = _source_phases(root, phase)
                    self.assertIsNone(converted_provenance_issue(phase, snapshot))

    def test_the_legal_phase_set_is_the_contiguous_prefix(self):
        from sage.fast_cycle_contract import expected_source_phases
        self.assertEqual(expected_source_phases("00"), (("00",), None))
        self.assertEqual(expected_source_phases("02"), (("00", "01", "02"), None))
        self.assertEqual(expected_source_phases("04"),
                         (("00", "01", "02", "03", "04"), None))
        self.assertTrue(expected_source_phases("05")[1])

    def test_every_structural_counterexample_fails_the_contract(self):
        from sage.fast_cycle_contract import converted_provenance_issue
        for label, phase, snapshot in STRUCTURAL_COUNTEREXAMPLES:
            with self.subTest(label=label):
                self.assertTrue(converted_provenance_issue(phase, snapshot), label)

    # --- writer: 구조 ------------------------------------------------------

    def test_the_writer_refuses_every_structural_counterexample(self):
        for label, phase, snapshot in STRUCTURAL_COUNTEREXAMPLES:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as root:
                _write_source_docs(root, "02")
                with self.assertRaises(fast_cycle_audit.AuditWriteError, msg=label):
                    fast_cycle_audit.convert_fast(
                        root, profile=PROFILE, cycle_stem="demo", current_phase=phase,
                        actual_risk="L2", fast_review_level="L2", reason="테스트",
                        confirmed_by="tester", minimum_rounds=1,
                        lenses=["correctness", "error_handling"], source_phases=snapshot)
                self.assertFalse(os.path.exists(fast_cycle_audit.audit_path(root)), label)

    # --- writer: 실제 파일 -------------------------------------------------
    #
    # 아래 반례들은 **구조는 맞다.** 디스크의 실제 문서와 다를 뿐이다. 그래서 writer 만 잡을 수
    # 있고, 그것이 이 계층을 나눈 이유다.

    def _live_mismatches(self, root):
        live = _source_phases(root, "02")
        return [
            ("실제 path + 틀린 hash",
             dict(live, **{"01": dict(live["01"], sha256="sha256:" + "b" * 64)})),
            ("실제 path + 틀린 size",
             dict(live, **{"01": dict(live["01"], size=live["01"]["size"] + 1)})),
            ("phase 문서가 아닌 일반 파일",
             dict(live, **{"01": _entry(path="README.md")})),
            ("phase 어긋난 문서", dict(live, **{"01": dict(live["00"])})),
            ("stem 어긋난 문서",
             dict(live, **{"01": dict(live["01"], path="plan_docs/01-plan/other.md")})),
            ("`.` 이 실제로 존재하는 경우에도", {phase: _entry(path=".")
                                             for phase in ("00", "01", "02")}),
        ]

    def test_the_writer_refuses_values_that_do_not_match_the_documents(self):
        for label, snapshot in self._live_mismatches(tempfile.mkdtemp()):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as root:
                _write_source_docs(root, "02")
                with self.assertRaises(fast_cycle_audit.AuditWriteError, msg=label):
                    fast_cycle_audit.convert_fast(
                        root, profile=PROFILE, cycle_stem="demo", current_phase="02",
                        actual_risk="L2", fast_review_level="L2", reason="테스트",
                        confirmed_by="tester", minimum_rounds=1,
                        lenses=["correctness", "error_handling"], source_phases=snapshot)
                self.assertFalse(os.path.exists(fast_cycle_audit.audit_path(root)), label)

    def test_the_writer_refuses_a_symlinked_phase_document(self):
        """감사가 가리키는 대상이 그 파일이라는 보장이 사라진다."""
        from sage.fast_cycle_sources import SourceProvenanceError, source_phase_snapshot
        with tempfile.TemporaryDirectory() as root:
            _write_source_docs(root, "02")
            target = os.path.join(root, "elsewhere.md")
            with open(target, "w", encoding="utf-8") as fh:
                fh.write("# elsewhere\n")
            link = os.path.join(root, "plan_docs", "01-plan", "demo.md")
            os.remove(link)
            os.symlink(target, link)
            with self.assertRaises(SourceProvenanceError):
                source_phase_snapshot(root, PROFILE, "demo", "02")

    def test_the_writer_refuses_a_missing_phase_document(self):
        with tempfile.TemporaryDirectory() as root:
            _write_source_docs(root, "01")           # 02 문서를 만들지 않는다
            with self.assertRaises(fast_cycle_audit.AuditWriteError):
                fast_cycle_audit.convert_fast(
                    root, profile=PROFILE, cycle_stem="demo", current_phase="02",
                    actual_risk="L2", fast_review_level="L2", reason="테스트",
                    confirmed_by="tester", minimum_rounds=1,
                    lenses=["correctness", "error_handling"],
                    source_phases=_valid_provenance("02"))

    def test_the_writer_accepts_the_live_snapshot_for_every_phase(self):
        """이빨의 반대쪽 — 실제 writer 가 만드는 00·01·02 세 모양 전부 통과한다."""
        for phase in ("00", "01", "02"):
            with self.subTest(current_phase=phase), tempfile.TemporaryDirectory() as root:
                _convert_fast(root, current_phase=phase)
                self.assertEqual(fast_cycle_audit.integrity_issues(root), [])
                self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "FAST")

    def test_the_writer_needs_no_profile_hash_but_does_need_a_profile(self):
        """`profile` 을 요구하는 것이 계약이다 — CLI 밖의 직접 호출도 같은 문을 지난다."""
        with tempfile.TemporaryDirectory() as root:
            _write_source_docs(root, "02")
            with self.assertRaises(TypeError):
                fast_cycle_audit.convert_fast(
                    root, cycle_stem="demo", current_phase="02", actual_risk="L2",
                    fast_review_level="L2", reason="테스트", confirmed_by="tester",
                    minimum_rounds=1, lenses=["correctness", "error_handling"],
                    source_phases=_valid_provenance("02"))

    # --- 감사(이미 기록된 값) ---------------------------------------------

    def _recorded(self, root, phase, snapshot):
        """계약 이전에 기록됐을 값을 재현한다 — writer 를 우회해 직접 고치고 체인을 맞춘다."""
        import loop_audit
        _convert_fast(root, current_phase="02")
        path = fast_cycle_audit.audit_path(root)
        with open(path, encoding="utf-8") as fh:
            record = json.loads(fh.read().strip())
        record["current_phase"] = phase
        record["source_phases_open"] = snapshot
        for key in ("prev_hash", "record_hash", "chain_version"):
            record.pop(key, None)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(loop_audit._stamp_record([], record),
                                ensure_ascii=False) + "\n")
        return root

    def test_recorded_structural_counterexamples_are_unknown_and_flagged(self):
        for label, phase, snapshot in STRUCTURAL_COUNTEREXAMPLES:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as root:
                self._recorded(root, phase, snapshot)
                self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0],
                                 "UNKNOWN", label)
                self.assertTrue(fast_cycle_audit.integrity_issues(root), label)

    def test_the_recorded_chain_is_still_valid(self):
        """전제 확인 — 체인이 유효해야 이 반례가 구조 검사 말고는 걸리지 않는다."""
        with tempfile.TemporaryDirectory() as root:
            self._recorded(root, "02", {"00": {}, "01": {}, "02": {}})
            summary = fast_cycle_audit.audit_summary(root)
            state = summary["runs"][summary["active"][0]]
            self.assertIs(state["chain_ok"], True)
            self.assertTrue(state["clean"])

    def test_the_audit_does_not_re_read_the_documents(self):
        """전환 뒤 문서 변경은 정상이다. 감사가 디스크를 재검증하면 그것이 손상으로 보인다.

        이것이 `self-attested local provenance` 의 경계다 — 감사는 "기록이 구조적으로 유효한가"
        만 보고, "지금 파일이 그때와 같은가" 는 묻지 않는다.
        """
        with tempfile.TemporaryDirectory() as root:
            _convert_fast(root, current_phase="02")
            with open(os.path.join(root, "plan_docs", "01-plan", "demo.md"), "a",
                      encoding="utf-8") as fh:
                fh.write("\n전환 뒤 정상 개발\n")
            self.assertEqual(fast_cycle_audit.integrity_issues(root), [])
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "FAST")

    # --- 게이트 -----------------------------------------------------------

    def test_the_gate_refuses_every_structural_counterexample(self):
        for label, phase, snapshot in STRUCTURAL_COUNTEREXAMPLES:
            with self.subTest(label=label):
                self.assertTrue(pre_implementation_gate_core._opener_contract_issue(
                    self._state(phase, snapshot)), label)

    def test_the_gate_grants_no_waiver_for_a_structural_counterexample(self):
        """`_fast_covers_required` 도 key 집합만 보지 않는다."""
        for label, phase, snapshot in STRUCTURAL_COUNTEREXAMPLES:
            with self.subTest(label=label):
                self.assertFalse(pre_implementation_gate_core._fast_covers_required(
                    self._state(phase, snapshot), ["00", "01", "02"]), label)

    def test_the_gate_still_waives_for_a_real_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            snapshot = _source_phases(root, "02")
        self.assertTrue(pre_implementation_gate_core._fast_covers_required(
            self._state("02", snapshot), ["00", "01", "02"]))

    def test_the_converted_state_path_refuses_it(self):
        """게이트가 실제로 소비하는 자리 — adapter snapshot 의 전환 run."""
        event = {"changes": [], "cycle_stem": "demo"}
        content = "# demo\n\nCycle-Stem: `demo`\nRisk Level: L2\n"
        for label, phase, snapshot in STRUCTURAL_COUNTEREXAMPLES:
            with self.subTest(label=label):
                audit = {"file_ok": True, "file_issues": [], "active": ["fc-1"],
                         "runs": {"fc-1": self._state(phase, snapshot)}}
                state, detail = pre_implementation_gate_core._fast_cycle_state(
                    event, self.PROFILE,
                    {"phase_docs": {"00": [{"path": "plan_docs/00-base_plan/demo.md",
                                            "content": content}]},
                     "fast_cycle_audit": audit},
                    self.PROFILE["pdca"])
                self.assertIsNone(state, label)
                self.assertTrue(detail, label)

    # --- 실제 API → 감사 → 게이트 E2E -------------------------------------

    def test_end_to_end_a_structureless_provenance_never_waives_anything(self):
        """리뷰가 재현한 경로 그대로 — writer 부터 게이트까지."""
        from sage import gate_readiness
        with tempfile.TemporaryDirectory() as root:
            _fast_project(root, self.PROFILE)
            _phase00(root, "demo")
            _write_source_docs(root, "02")
            for snapshot in ({"00": {}, "01": {}, "02": {}},
                             {phase: _entry(path=".") for phase in ("00", "01", "02")}):
                with self.assertRaises(fast_cycle_audit.AuditWriteError):
                    fast_cycle_audit.convert_fast(
                        root, profile=self.PROFILE, cycle_stem="demo", current_phase="02",
                        actual_risk="L2", fast_review_level="L2", reason="테스트",
                        confirmed_by="tester", minimum_rounds=1,
                        lenses=["correctness", "error_handling"], source_phases=snapshot)
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "STANDARD")
            exempt, _detail = gate_readiness.fast_exemption(
                root, self.PROFILE, "demo", ["00", "01", "02"])
            self.assertFalse(exempt)

    def test_end_to_end_an_already_recorded_one_is_refused_everywhere(self):
        from sage import gate_readiness
        with tempfile.TemporaryDirectory() as root:
            _fast_project(root, self.PROFILE)
            _phase00(root, "demo")
            self._recorded(root, "02", {"00": {}, "01": {}, "02": {}})
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "UNKNOWN")
            self.assertTrue(fast_cycle_audit.integrity_issues(root))
            exempt, detail = gate_readiness.fast_exemption(
                root, self.PROFILE, "demo", ["00", "01", "02"])
            self.assertFalse(exempt)
            self.assertTrue(detail)
            rc, out, _err = _run(S, root=root, json=True)
            self.assertNotEqual(rc, 0)
            self.assertNotEqual(json.loads(out)["status"], "READY")

    def test_end_to_end_a_real_conversion_still_waives(self):
        """이빨의 반대쪽 — 실제 문서에서 만든 담보를 실은 전환은 여전히 면제된다."""
        from sage import gate_readiness
        with tempfile.TemporaryDirectory() as root:
            _fast_project(root, self.PROFILE)
            _phase00(root, "demo")
            _convert_fast(root, current_phase="02", profile=self.PROFILE)
            self.assertEqual(fast_cycle_audit.mode_for_stem(root, "demo")[0], "FAST")
            self.assertEqual(fast_cycle_audit.integrity_issues(root), [])
            exempt, detail = gate_readiness.fast_exemption(
                root, self.PROFILE, "demo", ["00", "01", "02"])
            self.assertTrue(exempt, detail)

    # --- 정본이 하나인가 ---------------------------------------------------

    def test_the_review_snapshot_uses_the_same_contract(self):
        """open 과 review 가 같은 모양의 데이터에 다른 검사를 쓰면 느슨한 쪽으로 들어온다."""
        from sage.fast_cycle_contract import PHASES, source_phase_snapshot_issue
        self.assertTrue(fast_cycle_audit._review_snapshot_issue({"00": {}}))
        self.assertEqual(fast_cycle_audit._review_snapshot_issue({"00": {}}),
                         source_phase_snapshot_issue({"00": {}}, PHASES))

    def test_the_io_layer_owns_the_disk_reading(self):
        """CLI 의 얇은 껍데기가 같은 구현을 쓴다 — 두 번째 스냅샷 계산기를 만들지 않는다."""
        from sage.commands import fast_cycle as fc
        with tempfile.TemporaryDirectory() as root:
            expected = _source_phases(root, "02")
            self.assertEqual(fc._source_phase_snapshot(root, PROFILE, "demo", "02"),
                             expected)

    def test_the_matrix_is_not_empty(self):
        """행렬이 비면 위 검사들은 아무것도 지키지 않는다."""
        self.assertGreaterEqual(len(STRUCTURAL_COUNTEREXAMPLES), 25)
        self.assertEqual(len({label for label, _, _ in STRUCTURAL_COUNTEREXAMPLES}),
                         len(STRUCTURAL_COUNTEREXAMPLES))


class TestAnUnknownEntryModeCarriesNoWaiver(unittest.TestCase):
    """모르는 mode 를 "요구 없음" 으로 읽지 않는다.

    `OPENER_REQUIRED_BY_MODE.get(mode, ())` 는 모르는 key 를 **빈 담보 집합**으로 돌려준다.
    그래서 `entry_mode` 가 아무 문자열이면 fresh 전용 담보(`profile_hash`·`plan_hash_open`)도
    전환 전용 담보(`source_phases_open`·`confirmed_by`)도 요구되지 않았다 — 부재를 안전
    방향으로 읽는 것과 같은 모양이 dict 조회에서 난 것이다.

    게이트 core 는 순수 함수라 감사를 직접 읽지 않고 adapter 가 준 snapshot 을 그대로 믿는다.
    그래서 이 계약은 **자기가 받은 state 를 검증해야 한다** — 상류가 항상 올바른 값을 준다는
    가정을 계약이 대신 세우면, 그 가정이 틀린 날 계약은 아무 말도 하지 않는다.
    """

    PROFILE = dict(PROFILE, pdca=dict(
        PROFILE["pdca"], fast_cycle=FAST_POLICY,
        pre_implementation_required={"L2": ["00", "01", "02"], "L3": ["00", "01", "02"]}))

    def _state(self, **over):
        """실제 `open_fast` 가 만든 state 에서 출발한다."""
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            summary = fast_cycle_audit.audit_summary(root)
            state = dict(summary["runs"][summary["active"][0]])
        state.update(over)
        return state

    def test_the_starting_state_is_a_real_one(self):
        """이빨의 반대쪽 — 손대지 않은 실제 state 는 통과한다."""
        self.assertEqual(fast_cycle_audit.run_issues(self._state()), [])

    def test_an_unknown_mode_is_an_opener_issue(self):
        codes = [code for code, _ in
                 fast_cycle_audit.run_issues(self._state(entry_mode="FORGED-MODE"))]
        self.assertIn("fast_cycle_audit.opener_mode_unknown", codes)

    def test_the_gate_refuses_it(self):
        self.assertTrue(pre_implementation_gate_core._opener_contract_issue(
            self._state(entry_mode="FORGED-MODE")))

    def test_a_forged_mode_cannot_shed_the_fresh_collateral(self):
        """mode 를 바꿔 `profile_hash`·`plan_hash_open` 요구를 벗어나는 경로."""
        state = self._state(entry_mode="FORGED-MODE", profile_hash=None,
                            plan_hash_open=None)
        self.assertTrue(fast_cycle_audit.run_issues(state))
        self.assertTrue(pre_implementation_gate_core._opener_contract_issue(state))

    def test_a_forged_mode_cannot_shed_the_converted_collateral(self):
        state = self._state(entry_mode="FORGED-MODE", source_phases_open=None,
                            confirmed_by=None)
        self.assertTrue(pre_implementation_gate_core._opener_contract_issue(state))

    def test_the_gate_grants_no_exemption_for_such_a_snapshot(self):
        """게이트가 실제로 소비하는 자리 — adapter 가 준 snapshot 그대로."""
        event = {"changes": [], "cycle_stem": "demo"}
        content = "# demo\n\nCycle-Stem: `demo`\nRisk Level: L2\n"
        snapshot = {"phase_docs": {"00": [{"path": "plan_docs/00-base_plan/demo.md",
                                           "content": content}]},
                    "fast_cycle_audit": {
                        "file_ok": True, "file_issues": [], "active": ["fc-1"],
                        "runs": {"fc-1": self._state(entry_mode="FORGED-MODE")}}}
        state, detail = pre_implementation_gate_core._fast_cycle_state(
            event, self.PROFILE, snapshot, self.PROFILE["pdca"])
        self.assertIsNone(state)
        self.assertTrue(detail)

    def test_the_writer_cannot_produce_an_unknown_mode(self):
        """상류도 닫혀 있는가 — `summarize_records` 는 event 이름에서 mode 를 **유도**한다.

        그래서 감사 파일의 `entry_mode` 필드를 위조해도 state 의 mode 는 바뀌지 않는다.
        이 검사는 그 유도가 계속 닫혀 있는지를 고정한다 — 열리면 위 계약 검사가 유일한
        방어선이 된다.
        """
        import loop_audit
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            path = fast_cycle_audit.audit_path(root)
            with open(path, encoding="utf-8") as fh:
                record = json.loads(fh.read().strip())
            record["entry_mode"] = "FORGED-MODE"
            for key in ("prev_hash", "record_hash", "chain_version"):
                record.pop(key, None)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(loop_audit._stamp_record([], record),
                                    ensure_ascii=False) + "\n")
            summary = fast_cycle_audit.audit_summary(root)
            state = summary["runs"][summary["active"][0]]
        self.assertIn(state["entry_mode"], set(fast_cycle_audit.ENTRY_MODES.values()))

    def test_the_known_modes_are_exactly_the_ones_the_writer_records(self):
        """계약이 아는 mode 와 감사가 쓰는 mode 가 갈리면 이 구멍이 다시 열린다."""
        from sage.fast_cycle_contract import OPENER_REQUIRED_BY_MODE
        self.assertEqual(set(fast_cycle_audit.ENTRY_MODES.values()),
                         set(OPENER_REQUIRED_BY_MODE))

    def test_both_real_modes_still_pass(self):
        with tempfile.TemporaryDirectory() as root:
            _open_fast(root)
            summary = fast_cycle_audit.audit_summary(root)
            self.assertEqual(
                fast_cycle_audit.run_issues(summary["runs"][summary["active"][0]]), [])
        with tempfile.TemporaryDirectory() as root:
            _convert_fast(root, minimum_rounds=2)
            summary = fast_cycle_audit.audit_summary(root)
            self.assertEqual(
                fast_cycle_audit.run_issues(summary["runs"][summary["active"][0]]), [])



if __name__ == "__main__":
    unittest.main(verbosity=2)
