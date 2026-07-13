#!/usr/bin/env python3
"""부트스트랩 강제 게이트 검증 (상 등급 — 설계 핵심 진입점).

배경: profile 을 대화형(/sage-init)으로 채우기 전(project.name 빈값)에는 sage generate 가
동작하면 안 된다 — risk globs 0 → 모든 변경 L0 → 거버넌스 게이트 무력화(inert). generate 는
BLOCK(exit 2), validate 는 WARN 으로 표면화한다. 변이 teeth: name 채우면 통과해야 한다.

self-contained: 임시 SAGE 루트(manifest + hook spec + adapter stub)로 게이트만 검사.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import generate as gen  # noqa: E402
from sage.commands import validate as val  # noqa: E402
from sage.commands._common import is_bootstrapped  # noqa: E402

try:
    import yaml  # noqa: F401
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_SPEC = """---
id: aaa-hook
kind: hook
runtime_bindings:
  claude: { event: PreToolUse, matcher: "Write", timeout: 10 }
  codex: { event: PreToolUse, matcher: "apply_patch", timeout: 10 }
---
## intent
test
"""


def _root(d):
    os.makedirs(os.path.join(d, "docs", "sage_harness", "hooks"), exist_ok=True)
    for rt in ("claude", "codex"):
        os.makedirs(os.path.join(d, "scripts", "sage_harness", "hooks", "adapters", rt), exist_ok=True)
        Path(os.path.join(d, "scripts", "sage_harness", "hooks", "adapters", rt, "aaa-hook.sh")).write_text("#!/bin/bash\n")
    # generate --write 는 hook_runtime_hash 스탬프에 공용 런타임 파일을 요구한다(calculate_hook_runtime_hash).
    # 없으면 registration 은 되나 manifest 미스탬프로 rc 1 이 되어, 게이트 통과 케이스가 rc 0 을 못 받는다.
    os.makedirs(os.path.join(d, "scripts", "sage_harness", "hooks", "runtime"), exist_ok=True)
    os.makedirs(os.path.join(d, "scripts", "sage_harness", "hooks", "policies"), exist_ok=True)
    for fn in ("run_hook.py", "hook_runtime.py", "loop_audit.py", "retro_audit.py", "messages.py",
               "io_claude.py", "io_codex.py"):
        Path(os.path.join(d, "scripts", "sage_harness", "hooks", "runtime", fn)).write_text(f"# {fn}\n")
    Path(os.path.join(d, "scripts", "sage_harness", "hooks", "policies", "retro_gate.py")).write_text("# retro_gate\n")
    Path(os.path.join(d, "docs", "sage_harness", "hooks", "aaa-hook.md")).write_text(_SPEC)
    Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).write_text(json.dumps({
        "sage_version": "0.1.0", "host_runtime": "claude", "assets": {
            "hooks/aaa-hook": {"form": "core_adapter", "spec_hash": "x", "render_hash": {"claude": "x"}, "conformance": "PASS"},
        }}))


def _profile(d, body):
    os.makedirs(os.path.join(d, "sage"), exist_ok=True)
    Path(os.path.join(d, "sage", "project-profile.yaml")).write_text(body)


def _mark_installed(d):
    """설치 인스턴스 마커(AGENT_GUIDE.md) — install 이 항상 배치하는 파일."""
    Path(os.path.join(d, "AGENT_GUIDE.md")).write_text("# guide\n")


def _mark_installed_via_manifest(d):
    """AGENT_GUIDE 없이 manifest.installed_instance:true 만으로 설치 마킹(다중 신호 검증)."""
    mp = os.path.join(d, "docs", "sage_harness", ".manifest.json")
    m = json.loads(Path(mp).read_text())
    m["installed_instance"] = True
    Path(mp).write_text(json.dumps(m))


class GArgs:
    def __init__(self, dest, **kw):
        self.kind = "hook"; self.id = None; self.write = True
        self.target = "claude"; self.dest = dest; self.root = dest
        self.__dict__.update(kw)


class VArgs:
    def __init__(self, root, **kw):
        self.kind = "hook"; self.check = True; self.id = None; self.schema = False; self.root = root
        self.__dict__.update(kw)


class TestIsBootstrapped(unittest.TestCase):
    def test_signal(self):
        # 강한 신호(codex P0-2): name 만으론 부족 — risk 또는 components 필요.
        self.assertFalse(is_bootstrapped({"project": {"name": ""}}))
        self.assertFalse(is_bootstrapped({"project": {"name": "   "}}))
        self.assertFalse(is_bootstrapped({}))
        self.assertFalse(is_bootstrapped(None))
        self.assertFalse(is_bootstrapped({"project": {"name": "acme"}}))  # name 만 → toothless
        self.assertTrue(is_bootstrapped({"project": {"name": "acme"}, "risk": {"l2_path_globs": ["src/*"]}}))
        self.assertTrue(is_bootstrapped({"project": {"name": "acme"}, "components": [{"id": "be"}]}))


@unittest.skipUnless(_HAS_YAML, "pyyaml 필요(게이트 profile 파싱)")
class TestGenerateGateFramework(unittest.TestCase):
    """비설치 컨텍스트(AGENT_GUIDE 없음 = 픽스처/framework): 약한 신호(name)만 + 폴백 보존."""

    def test_empty_name_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            _root(d)
            _profile(d, 'project: { name: "" }\n')
            rc = gen.run(GArgs(d))
            self.assertEqual(rc, 2)
            self.assertFalse(os.path.exists(os.path.join(d, ".claude", "settings.json")))

    def test_name_only_passes_in_framework_ctx(self):
        # 비설치 컨텍스트는 부분 profile 픽스처 보존 — name 만 있어도 통과(폴백).
        with tempfile.TemporaryDirectory() as d:
            _root(d)
            _profile(d, 'project: { name: "acme" }\n')
            rc = gen.run(GArgs(d))
            self.assertEqual(rc, 0)

    def test_no_profile_file_not_blocked(self):
        # profile 파일 부재 + 비설치 → 기존 폴백(차단 안 함)
        with tempfile.TemporaryDirectory() as d:
            _root(d)
            rc = gen.run(GArgs(d))
            self.assertEqual(rc, 0)

    def test_parse_failure_blocks(self):
        # 손상 profile 은 두 컨텍스트 모두 차단(codex P1-1)
        with tempfile.TemporaryDirectory() as d:
            _root(d)
            _profile(d, "project: { name: [unclosed\n")
            rc = gen.run(GArgs(d))
            self.assertEqual(rc, 2)


@unittest.skipUnless(_HAS_YAML, "pyyaml 필요(게이트 profile 파싱)")
class TestGenerateGateInstalled(unittest.TestCase):
    """설치 컨텍스트(AGENT_GUIDE 존재): profile 필수 + 강한 신호."""

    def test_missing_profile_blocks(self):
        # codex P0-1: 설치 인스턴스에서 profile 삭제 = fail-open 우회 → 차단
        with tempfile.TemporaryDirectory() as d:
            _root(d); _mark_installed(d)
            rc = gen.run(GArgs(d))
            self.assertEqual(rc, 2)

    def test_name_only_blocks_when_installed(self):
        # codex P0-2: name 만 채우고 risk/components 비면 toothless → 차단
        with tempfile.TemporaryDirectory() as d:
            _root(d); _mark_installed(d)
            _profile(d, 'project: { name: "acme" }\n')
            rc = gen.run(GArgs(d))
            self.assertEqual(rc, 2)

    def test_name_plus_risk_passes(self):
        # 변이 teeth: name + risk glob → 통과 + 산출물 생성
        with tempfile.TemporaryDirectory() as d:
            _root(d); _mark_installed(d)
            _profile(d, 'project: { name: "acme" }\nrisk:\n  l2_path_globs: ["src/*"]\n')
            rc = gen.run(GArgs(d))
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(d, ".claude", "settings.json")))


@unittest.skipUnless(_HAS_YAML, "pyyaml 필요(게이트 profile 파싱)")
class TestValidateWarn(unittest.TestCase):
    def _warn_text(self, d):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            val.run(VArgs(d))
        return buf.getvalue()

    def test_empty_name_warns(self):
        # validate 는 읽기전용 → 차단 아닌 WARN. STALE 자산이 있으면 exit 는 STALE(3)이 우선.
        with tempfile.TemporaryDirectory() as d:
            _root(d)
            _profile(d, 'project: { name: "" }\n')
            self.assertIn("미부트스트랩", self._warn_text(d))

    def test_installed_missing_profile_warns(self):
        with tempfile.TemporaryDirectory() as d:
            _root(d); _mark_installed(d)
            self.assertIn("미설치", self._warn_text(d))


@unittest.skipUnless(_HAS_YAML, "pyyaml 필요(게이트 profile 파싱)")
class TestInstalledMarkerMultiSignal(unittest.TestCase):
    """codex R2-P0: AGENT_GUIDE 분실해도 manifest.installed_instance 로 설치 인식."""

    def test_manifest_marker_alone_blocks_missing_profile(self):
        # AGENT_GUIDE 없이 manifest 마커만 있어도 설치로 인식 → profile 부재 차단
        with tempfile.TemporaryDirectory() as d:
            _root(d); _mark_installed_via_manifest(d)
            self.assertFalse(os.path.exists(os.path.join(d, "AGENT_GUIDE.md")))
            rc = gen.run(GArgs(d))
            self.assertEqual(rc, 2)

    def test_manifest_marker_alone_blocks_name_only(self):
        # manifest 마커 + name-only(risk/components 없음) → 강한 신호 미충족 차단
        with tempfile.TemporaryDirectory() as d:
            _root(d); _mark_installed_via_manifest(d)
            _profile(d, 'project: { name: "acme" }\n')
            rc = gen.run(GArgs(d))
            self.assertEqual(rc, 2)

    def test_legacy_install_detected_via_wrapper(self):
        # codex R3-P1: 레거시 설치(installed_instance 스탬프 없음 + AGENT_GUIDE 분실)라도
        # wrapper(CLAUDE.md) 가 남아있으면 설치로 인식 → name-only 차단(약한 경로 우회 불가).
        with tempfile.TemporaryDirectory() as d:
            _root(d)   # manifest 에 installed_instance 없음(레거시)
            Path(os.path.join(d, "CLAUDE.md")).write_text("# wrapper\n")
            self.assertFalse(os.path.exists(os.path.join(d, "AGENT_GUIDE.md")))
            _profile(d, 'project: { name: "acme" }\n')   # name-only(toothless)
            rc = gen.run(GArgs(d))
            self.assertEqual(rc, 2)


class TestNoYamlFailClosed(unittest.TestCase):
    """codex R2-P1: pyyaml 부재 시 설치 컨텍스트는 fail-closed(차단), 비설치는 통과."""

    def test_no_yaml_blocks_when_installed(self):
        import unittest.mock as mock
        from sage.commands import _common
        with tempfile.TemporaryDirectory() as d:
            _root(d); _mark_installed(d)
            _profile(d, 'project: { name: "acme" }\nrisk:\n  l2_path_globs: ["src/*"]\n')
            with mock.patch.object(_common, "_load_profile_yaml", return_value="no_yaml"):
                self.assertEqual(_common.bootstrap_gate_reason(d, d), "no_yaml")

    def test_no_yaml_passes_when_not_installed(self):
        import unittest.mock as mock
        from sage.commands import _common
        with tempfile.TemporaryDirectory() as d:
            _root(d)
            _profile(d, 'project: { name: "acme" }\n')
            with mock.patch.object(_common, "_load_profile_yaml", return_value="no_yaml"):
                self.assertIsNone(_common.bootstrap_gate_reason(d, d))


if __name__ == "__main__":
    unittest.main(verbosity=2)
