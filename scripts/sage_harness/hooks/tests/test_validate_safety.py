#!/usr/bin/env python3
"""validate 안전성 검증 (audit 4회차 P1-1: 오염 manifest test 경로 임의 실행 차단)."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import validate as V  # noqa: E402
from sage.commands.validate import _safe_test_path, _schema_check, _validate_hook_runtime_hash, _validate_interpretive  # noqa: E402
from sage.hook_runtime_hash import calculate_hook_runtime_hash  # noqa: E402

try:
    import yaml  # noqa: F401
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

ROOT = REPO  # sage_project (실제 구조 사용)

try:
    import jsonschema  # noqa: F401
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


class TestSafeTestPath(unittest.TestCase):
    def test_reject_absolute(self):
        self.assertIsNone(_safe_test_path(ROOT, "/tmp/payload.sh"))

    def test_reject_parent_traversal(self):
        self.assertIsNone(_safe_test_path(ROOT, "../../payload.py"))

    def test_reject_outside_scripts(self):
        # root 내부지만 scripts/sage_harness 밖 → 거부
        self.assertIsNone(_safe_test_path(ROOT, "sage/cli.py"))

    def test_reject_bad_extension(self):
        self.assertIsNone(_safe_test_path(ROOT, "scripts/sage_harness/hooks/tests/cases.tsv"))

    def test_accept_valid(self):
        p = _safe_test_path(ROOT, "scripts/sage_harness/hooks/tests/test_conformance.py")
        self.assertIsNotNone(p)
        self.assertTrue(p.endswith("test_conformance.py"))

    def test_reject_missing(self):
        self.assertIsNone(_safe_test_path(ROOT, "scripts/sage_harness/hooks/tests/nope.py"))

    def test_reject_non_str(self):
        # 오염 manifest 의 test: 123 등 비문자열 — isabs/split 가 죽지 않고 안전하게 거부.
        self.assertIsNone(_safe_test_path(ROOT, 123))
        self.assertIsNone(_safe_test_path(ROOT, ["x"]))


class _VArgs:
    def __init__(self, root, strict=False):
        self.check = True; self.schema = False; self.strict = strict
        self.kind = "all"; self.id = None; self.root = root


def _write_manifest(d, manifest, installed=False, empty_profile=False):
    mp = os.path.join(d, "docs", "sage_harness")
    os.makedirs(mp, exist_ok=True)
    Path(os.path.join(mp, ".manifest.json")).write_text(json.dumps(manifest), encoding="utf-8")
    if installed:
        Path(os.path.join(d, "AGENT_GUIDE.md")).write_text("# guide\n", encoding="utf-8")
    if empty_profile:
        os.makedirs(os.path.join(d, "sage"), exist_ok=True)
        Path(os.path.join(d, "sage", "project-profile.yaml")).write_text('project: { name: "" }\n', encoding="utf-8")


class TestCorruptEntryTolerance(unittest.TestCase):
    """오염 manifest entry(내부 필드 타입 손상)에 validate 가 traceback 없이 판정을 낸다.

    --force 보존 경로가 손상 entry 를 살려도 게이트가 죽지 않아야 한다 — 크래시면 이 테스트가 예외로 에러난다.
    """
    def test_run_malformed_assets_not_downgraded_by_bootstrap_warn(self):
        # 설치 인스턴스 + 미부트스트랩(빈 name) + 손상 assets → bootstrap WARN 이 assets FAIL 을 덮으면 안 됨.
        with tempfile.TemporaryDirectory() as d:
            _write_manifest(d, {"sage_version": "0.1.0", "host_runtime": "claude",
                                "installed_instance": True, "assets": []}, installed=True, empty_profile=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = V.run(_VArgs(d))
            out = buf.getvalue()
            # bootstrap WARN 이 실제 발화(비-vacuous 증명)했는데도 FAIL 이 살아남는지 확인.
            self.assertIn("profile 미부트스트랩", out)
            self.assertIn("manifest.assets 구조 오류", out)
            self.assertEqual(rc, 1)   # FAIL — WARN(비게이팅)으로 다운그레이드되지 않음

    def test_run_tolerates_corrupt_runtime_targets(self):
        # mcp entry 의 runtime_targets 가 비-list(123) 여도 ownership 단계가 크래시하지 않는다.
        with tempfile.TemporaryDirectory() as d:
            _write_manifest(d, {"sage_version": "0.1.0", "host_runtime": "claude",
                                "assets": {"mcps/x": {"runtime_targets": 123}}})
            with redirect_stdout(io.StringIO()):
                rc = V.run(_VArgs(d))
            self.assertIsInstance(rc, int)   # 크래시(TypeError) 없이 완주
            self.assertNotEqual(rc, 2)       # TOOL_ERR 도 아님

    def test_run_rejects_non_dict_root_manifest(self):
        # manifest 최상위가 object 아님([]/null/문자열) → manifest.get() 크래시 대신 TOOL_ERR(2).
        for bad in ([], None, "corrupt"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as d:
                mp = os.path.join(d, "docs", "sage_harness")
                os.makedirs(mp, exist_ok=True)
                Path(os.path.join(mp, ".manifest.json")).write_text(json.dumps(bad), encoding="utf-8")
                with redirect_stdout(io.StringIO()):
                    rc = V.run(_VArgs(d))
                self.assertEqual(rc, 2)   # 크래시가 아니라 TOOL ERROR
    def test_hook_tolerates_corrupt_adapter_hash(self):
        # adapter_hash:"bad"(비-dict) 은 (…).get(rt) 에서 크래시할 수 있다 — 가드가 {} 로 처리.
        with tempfile.TemporaryDirectory() as d:
            sev, _ = V._validate_hook(d, "hooks/x", {"form": "core_adapter", "adapter_hash": "bad"}, run_regression=False)
            self.assertEqual(sev, "FAIL")   # spec/canonical/adapter 부재 → FAIL, 크래시 아님

    def test_interpretive_tolerates_corrupt_unresolved(self):
        with tempfile.TemporaryDirectory() as d:
            docs = os.path.join(d, "docs", "sage_harness", "agents")
            os.makedirs(docs, exist_ok=True)
            Path(os.path.join(docs, "x.md")).write_text("# spec\n", encoding="utf-8")
            Path(os.path.join(docs, "x.claims.yml")).write_text("required_claims: []\nunresolved: []\n", encoding="utf-8")
            # unresolved:1(비-list) 은 순회·len 양쪽에서 크래시할 수 있다 — 가드가 무시해야 한다.
            sev, _ = V._validate_interpretive(d, "agents/x", {"unresolved": 1}, run_regression=False)
            self.assertEqual(sev, "STALE")   # spec/claims 존재 + hashless → 미스탬프 STALE(크래시 아님)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 미설치 — mcp spec 파싱 불가")
    def test_mcp_tolerates_corrupt_render_hash(self):
        with tempfile.TemporaryDirectory() as d:
            mdir = os.path.join(d, "docs", "sage_harness", "mcps")
            os.makedirs(mdir, exist_ok=True)
            Path(os.path.join(mdir, "x.md")).write_text(
                "---\nid: x\nkind: mcp\ntransport: stdio\nruntime_targets: [claude]\nserver_binding: { command: x }\n---\n",
                encoding="utf-8")
            # render_hash:"bad"(비-dict) 은 rh.get(tgt) 에서 크래시할 수 있다 — 가드가 {} 로 처리해야 한다.
            sev, msgs = V._validate_mcp(d, "mcps/x", {"spec_hash": "s", "render_hash": "bad"})
            self.assertEqual(sev, "STALE")   # spec 변경/render 미스탬프 → STALE, 크래시 아님
            self.assertTrue(any("render_hash" in m for m in msgs), msgs)   # render_hash 가드 경로 도달 증명

    def test_run_tolerates_non_dict_assets(self):
        # assets 가 dict 아님(list/str) → traceback 대신 FAIL 로 표면화하고 완주.
        for bad in ([], "corrupt"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as d:
                _write_manifest(d, {"sage_version": "0.1.0", "host_runtime": "claude", "assets": bad})
                rc = V.run(_VArgs(d))
                self.assertEqual(rc, 1)   # FAIL(구조 오류) — TOOL_ERR(2)나 크래시가 아니라 판정

    def test_run_tolerates_non_dict_entry(self):
        # entry 가 dict 아님 → 해당 자산만 FAIL, 게이트는 완주.
        with tempfile.TemporaryDirectory() as d:
            _write_manifest(d, {"sage_version": "0.1.0", "host_runtime": "claude",
                                "assets": {"hooks/bad": [], "mcps/bad2": "x"}})
            rc = V.run(_VArgs(d))
            self.assertIsInstance(rc, int)
            self.assertNotEqual(rc, 2)   # 크래시/TOOL_ERR 아님

    def test_strict_promotes_bootstrap_but_default_keeps_warn_nonzero_free(self):
        with tempfile.TemporaryDirectory() as d:
            _write_manifest(d, {"sage_version": "0.1.0", "host_runtime": "claude",
                                "installed_instance": True, "assets": {}},
                            installed=True, empty_profile=True)
            normal_args = _VArgs(d, strict=False); normal_args.kind = "skill"
            strict_args = _VArgs(d, strict=True); strict_args.kind = "skill"
            with redirect_stdout(io.StringIO()):
                normal = V.run(normal_args)
            strict_out = io.StringIO()
            with redirect_stdout(strict_out):
                strict = V.run(strict_args)
            self.assertEqual(normal, 0)
            self.assertEqual(strict, 1)
            self.assertIn("bootstrap-invalid", strict_out.getvalue())

    def test_gate_relax_suspected_remains_advisory_under_strict(self):
        with tempfile.TemporaryDirectory() as d:
            _write_manifest(d, {"sage_version": "0.1.0", "host_runtime": "claude", "assets": {}},
                            installed=False)
            overlay = os.path.join(d, "sage", "asset_overrides", "agents")
            os.makedirs(overlay, exist_ok=True)
            Path(os.path.join(overlay, "leader.md")).write_text("skip the required review gate\n")
            args = _VArgs(d, strict=True); args.kind = "skill"
            with redirect_stdout(io.StringIO()):
                rc = V.run(args)
            self.assertEqual(rc, 0)


class TestSchemaCheck(unittest.TestCase):
    """sage validate --schema (manifest JSON Schema 구조검증)."""
    def test_no_jsonschema_warns(self):
        # jsonschema 미설치 환경: WARN(skip) — 결정론적 검증 불가하므로 설치 시에만 PASS/FAIL 단정
        if _HAS_JSONSCHEMA:
            self.skipTest("jsonschema 설치됨")
        with tempfile.TemporaryDirectory() as d:
            sev, _ = _schema_check(d, {"sage_version": "0.1.0", "host_runtime": "claude", "assets": {}})
            self.assertEqual(sev, "WARN")

    @unittest.skipUnless(_HAS_JSONSCHEMA, "jsonschema 필요")
    def test_valid_manifest_pass(self):
        # root/schema 없으면 _resources(SAGE 번들) schema 사용
        with tempfile.TemporaryDirectory() as d:
            m = {"sage_version": "0.1.0", "host_runtime": "claude",
                 "assets": {"hooks/x": {"conformance": "PASS", "form": "native"}}}
            self.assertEqual(_schema_check(d, m)[0], "PASS")

    @unittest.skipUnless(_HAS_JSONSCHEMA, "jsonschema 필요")
    def test_invalid_manifest_fail(self):
        with tempfile.TemporaryDirectory() as d:
            m = {"sage_version": "0.1.0", "host_runtime": "claude",
                 "assets": {"hooks/x": {"conformance": "BOGUS", "form": "native"}}}  # enum 위반
            self.assertEqual(_schema_check(d, m)[0], "FAIL")

    @unittest.skipUnless(_HAS_JSONSCHEMA, "jsonschema 필요")
    def test_manifest_accepts_hook_runtime_hash(self):
        with tempfile.TemporaryDirectory() as d:
            sha = "sha256:" + ("a" * 64)
            m = {"sage_version": "0.1.0", "host_runtime": "claude",
                 "hook_runtime_hash": {"shared": sha, "claude": sha, "codex": sha},
                 "assets": {"hooks/x": {"conformance": "PASS", "form": "native"}}}
            self.assertEqual(_schema_check(d, m)[0], "PASS")

    @unittest.skipUnless(_HAS_JSONSCHEMA, "jsonschema 필요")
    def test_manifest_accepts_installed_hosts(self):
        with tempfile.TemporaryDirectory() as d:
            m = {"sage_version": "0.1.0", "host_runtime": "claude",
                 "installed_hosts": ["claude", "codex"], "assets": {}}
            self.assertEqual(_schema_check(d, m)[0], "PASS")


def _runtime_root(d):
    runtime = os.path.join(d, "scripts", "sage_harness", "hooks", "runtime")
    policies = os.path.join(d, "scripts", "sage_harness", "hooks", "policies")
    os.makedirs(runtime, exist_ok=True)
    os.makedirs(policies, exist_ok=True)
    for fn in ("run_hook.py", "hook_runtime.py", "loop_audit.py", "retro_audit.py", "messages.py",
               "io_claude.py", "io_codex.py"):
        Path(os.path.join(runtime, fn)).write_text(f"# {fn}\n", encoding="utf-8")
    Path(os.path.join(policies, "retro_gate.py")).write_text("# retro_gate\n", encoding="utf-8")


class TestHookRuntimeHash(unittest.TestCase):
    def test_missing_stamp_is_stale(self):
        with tempfile.TemporaryDirectory() as d:
            _runtime_root(d)
            sev, msgs = _validate_hook_runtime_hash(d, {"assets": {}})
            self.assertEqual(sev, "STALE")
            self.assertTrue(any("미스탬프" in m for m in msgs))

    def test_runtime_file_drift_is_stale(self):
        with tempfile.TemporaryDirectory() as d:
            _runtime_root(d)
            hashes, missing = calculate_hook_runtime_hash(d)
            self.assertEqual(missing, [])
            Path(os.path.join(d, "scripts", "sage_harness", "hooks", "runtime", "io_codex.py")).write_text(
                "# changed\n", encoding="utf-8")
            sev, msgs = _validate_hook_runtime_hash(d, {"hook_runtime_hash": hashes, "assets": {}})
            self.assertEqual(sev, "STALE")
            self.assertTrue(any("codex" in m for m in msgs))

    def test_runtime_missing_file_is_fail(self):
        with tempfile.TemporaryDirectory() as d:
            _runtime_root(d)
            hashes, _missing = calculate_hook_runtime_hash(d)
            os.remove(os.path.join(d, "scripts", "sage_harness", "hooks", "runtime", "run_hook.py"))
            sev, msgs = _validate_hook_runtime_hash(d, {"hook_runtime_hash": hashes, "assets": {}})
            self.assertEqual(sev, "FAIL")
            self.assertTrue(any("run_hook.py" in m for m in msgs))

    def test_non_dict_stamp_is_stale(self):
        with tempfile.TemporaryDirectory() as d:
            _runtime_root(d)
            sev, msgs = _validate_hook_runtime_hash(d, {"hook_runtime_hash": "bad", "assets": {}})
            self.assertEqual(sev, "FAIL")
            self.assertTrue(any("구조 오류" in m for m in msgs))

    def test_missing_retro_gate_policy_is_caught(self):
        # codex 구현리뷰 2R P0: enforce 게이트 자체인 policies/retro_gate.py 가 빠지면 hash 대상에서
        # 누락돼 validate 통과 → enforce 조용히 무동작. 이제 shared 그룹에 포함되므로 삭제 시 FAIL.
        with tempfile.TemporaryDirectory() as d:
            _runtime_root(d)
            hashes, _missing = calculate_hook_runtime_hash(d)
            os.remove(os.path.join(d, "scripts", "sage_harness", "hooks", "policies", "retro_gate.py"))
            sev, msgs = _validate_hook_runtime_hash(d, {"hook_runtime_hash": hashes, "assets": {}})
            self.assertEqual(sev, "FAIL")
            self.assertTrue(any("retro_gate.py" in m for m in msgs))


class TestDescriptiveUnresolved(unittest.TestCase):
    """descriptive unresolved(비게이팅) 가 INFO 로 가시화되되 severity 는 안 올리는지."""
    def test_info_surfaced_not_gating(self):
        with tempfile.TemporaryDirectory() as d:
            sk = os.path.join(d, "docs", "sage_harness", "skills")
            os.makedirs(sk)
            Path(os.path.join(sk, "x.md")).write_text("# x\n")
            Path(os.path.join(sk, "x.claims.yml")).write_text(
                'required_claims:\n'
                '  - { type: procedure_step, value: "a", confidence: unresolved }\n'
                '  - { type: procedure_step, value: "b", confidence: unresolved }\n'
                'forbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n')
            # 정상 스탬프 entry(hashless→STALE 와 분리) — descriptive unresolved INFO 만 격리 검사.
            entry = {"form": "interpretive", "unresolved": [],
                     "spec_hash": V._sha(os.path.join(sk, "x.md")),
                     "claims_hash": V._sha(os.path.join(sk, "x.claims.yml"))}
            sev, msgs = _validate_interpretive(d, "skills/x", entry, run_regression=False)
            self.assertTrue(any("descriptive unresolved 2건" in m for m in msgs))
            self.assertEqual(sev, "PASS")   # INFO 는 게이팅 아님


if __name__ == "__main__":
    unittest.main(verbosity=2)
