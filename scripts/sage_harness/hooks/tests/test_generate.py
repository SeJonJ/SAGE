#!/usr/bin/env python3
"""sage generate 검증 (상 등급 — hook 등록 산출물 + manifest 스탬프, Codex 2R).

self-contained: 임시 SAGE 루트(hook spec frontmatter + adapter stub + manifest)로 등록 생성 확인.
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

try:
    import yaml  # noqa: F401
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

SPEC_A = """---
id: aaa-hook
kind: hook
runtime_bindings:
  claude: { event: PreToolUse, matcher: "Write|Edit|MultiEdit", timeout: 10 }
  codex: { event: PreToolUse, matcher: "apply_patch", timeout: 10 }
---
## intent
test
"""
SPEC_B = """---
id: bbb-hook
kind: hook
runtime_bindings:
  claude: { event: Stop, matcher: "", timeout: 15 }
  codex: { event: Stop, matcher: "", timeout: 15 }
---
## intent
test
"""


def make_root(d, with_adapter=True):
    os.makedirs(os.path.join(d, "docs", "sage_harness", "hooks"), exist_ok=True)
    os.makedirs(os.path.join(d, "scripts", "sage_harness", "hooks", "adapters", "claude"), exist_ok=True)
    os.makedirs(os.path.join(d, "scripts", "sage_harness", "hooks", "adapters", "codex"), exist_ok=True)
    Path(os.path.join(d, "docs", "sage_harness", "hooks", "aaa-hook.md")).write_text(SPEC_A)
    Path(os.path.join(d, "docs", "sage_harness", "hooks", "bbb-hook.md")).write_text(SPEC_B)
    Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).write_text(json.dumps({
        "sage_version": "0.1.0", "host_runtime": "claude", "assets": {
            "hooks/aaa-hook": {"form": "core_adapter", "spec_hash": "x", "render_hash": {"claude": "x"}, "conformance": "PASS"},
            "hooks/bbb-hook": {"form": "core_adapter", "spec_hash": "x", "render_hash": {"claude": "x"}, "conformance": "PASS"},
        }}))
    if with_adapter:
        for hid in ("aaa-hook", "bbb-hook"):
            for rt in ("claude", "codex"):
                Path(os.path.join(d, "scripts", "sage_harness", "hooks", "adapters", rt, f"{hid}.sh")).write_text("#!/bin/bash\n")


class Args:
    def __init__(self, **kw):
        self.kind = "hook"; self.id = None; self.write = False
        self.target = "claude"; self.dest = "."; self.root = None
        self.__dict__.update(kw)


class TestGenerate(unittest.TestCase):
    def test_parse_runtime_bindings(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d)
            rb = gen._parse_runtime_bindings(os.path.join(d, "docs", "sage_harness", "hooks", "aaa-hook.md"))
            self.assertEqual(rb["claude"]["event"], "PreToolUse")
            self.assertEqual(rb["claude"]["matcher"], "Write|Edit|MultiEdit")
            self.assertEqual(rb["claude"]["timeout"], 10)
            self.assertEqual(rb["codex"]["matcher"], "apply_patch")

    def test_build_registration_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d)
            reg, missing = gen._build_registration(d, "claude", ["bbb-hook", "aaa-hook"])
            self.assertEqual(missing, [])
            # PreToolUse(aaa) + Stop(bbb), event 정렬
            self.assertIn("PreToolUse", reg)
            self.assertIn("Stop", reg)
            self.assertIn("aaa-hook", reg["PreToolUse"][0]["hooks"][0]["command"])

    def test_missing_adapter_fail(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d, with_adapter=False)
            reg, missing = gen._build_registration(d, "claude", ["aaa-hook"])
            self.assertTrue(any("adapter" in m for m in missing))

    def test_write_creates_settings(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            make_root(d)
            rc = gen.run(Args(target="both", dest=dest, root=d, write=True))
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(dest, ".claude", "settings.json")))
            self.assertTrue(os.path.exists(os.path.join(dest, ".codex", "hooks.json")))
            s = json.loads(Path(os.path.join(dest, ".claude", "settings.json")).read_text())
            self.assertIn("hooks", s)
            # codex wrapper 형식
            x = json.loads(Path(os.path.join(dest, ".codex", "hooks.json")).read_text())
            cmd = x["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            self.assertIn("CODEX_HOME", cmd)

    def test_single_id_preserves_all_registrations(self):
        # F6 회귀: generate --id <단일hook> 가 settings.json 을 그 hook 하나로 재생성하면 나머지
        # hook 등록이 사라져 조용히 비활성화된다. --id 는 "스탬프 범위"만 좁히고, 등록(settings.json)/
        # shim 은 항상 전체 hook 을 담아야 한다.
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            make_root(d)
            os.makedirs(os.path.join(dest, ".claude"), exist_ok=True)
            Path(os.path.join(dest, ".claude", "settings.json")).write_text(
                json.dumps({"model": "opus", "hooks": {}}))   # 사용자 커스텀 설정(보존 대상)
            rc = gen.run(Args(id="aaa-hook", target="claude", dest=dest, root=d, write=True))
            self.assertEqual(rc, 0)
            s = json.loads(Path(os.path.join(dest, ".claude", "settings.json")).read_text())
            # 두 hook 등록 모두 유지(aaa=PreToolUse, bbb=Stop) — 단일 --id 가 클로버하지 않음
            self.assertIn("PreToolUse", s["hooks"])
            self.assertIn("Stop", s["hooks"])
            self.assertEqual(s.get("model"), "opus")          # 비-hooks 사용자 설정 보존
            # shim 도 전체 생성(등록과 일관)
            self.assertTrue(os.path.exists(os.path.join(dest, ".claude", "hooks", "aaa-hook.sh")))
            self.assertTrue(os.path.exists(os.path.join(dest, ".claude", "hooks", "bbb-hook.sh")))
            # 스탬프는 --id 범위만: aaa 만 갱신, bbb 는 원본("x") 유지
            m = json.loads(Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).read_text())
            self.assertTrue(m["assets"]["hooks/aaa-hook"]["spec_hash"].startswith("sha256:"))
            self.assertEqual(m["assets"]["hooks/bbb-hook"]["spec_hash"], "x")

    def test_root_defaults_to_dest(self):
        # Codex P1: --root 없이 --dest 만 → dest 의 manifest 를 stamp (cwd 의 다른 manifest 아님)
        with tempfile.TemporaryDirectory() as dest:
            make_root(dest)
            rc = gen.run(Args(target="claude", dest=dest, write=True))  # root=None
            self.assertEqual(rc, 0)
            m = json.loads(Path(os.path.join(dest, "docs", "sage_harness", ".manifest.json")).read_text())
            # make_root 가 둔 "x" 가 실제 sha 로 스탬프됨 → dest manifest 가 갱신됐다는 증거
            self.assertTrue(m["assets"]["hooks/aaa-hook"]["spec_hash"].startswith("sha256:"))

    def test_profile_compile_failclosed(self):
        # 손상 profile(잘못된 YAML)은 부트스트랩 게이트가 먼저 차단(rc 2) → profile.json 미생성.
        # (게이트가 compile-failclosed 보다 바깥 방어선 — 손상 profile 로 산출물 생성 봉쇄)
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            make_root(d)
            os.makedirs(os.path.join(dest, "sage"), exist_ok=True)
            Path(os.path.join(dest, "sage", "project-profile.yaml")).write_text("risk:\n  l3_filename_globs: [unclosed\n")
            rc = gen.run(Args(target="claude", dest=dest, root=d, write=True))
            self.assertEqual(rc, 2)
            self.assertFalse(os.path.exists(os.path.join(dest, "sage", "project-profile.json")))

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요(generate 빌드 의존성)")
    def test_profile_compiles_to_json(self):
        # profile.yaml(유효) → project-profile.json 컴파일(hook 런타임 입력, 의존성 0)
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            make_root(d)
            os.makedirs(os.path.join(dest, "sage"), exist_ok=True)
            Path(os.path.join(dest, "sage", "project-profile.yaml")).write_text(
                "project: { name: t }\nrisk:\n  l3_filename_globs: ['*payment*']\n  l2_path_globs: ['src/*']\n")
            rc = gen.run(Args(target="claude", dest=dest, root=d, write=True))
            self.assertEqual(rc, 0)
            prof = json.loads(Path(os.path.join(dest, "sage", "project-profile.json")).read_text())
            self.assertEqual(prof["risk"]["l3_filename_globs"], ["*payment*"])

    def test_agent_generate_guidance(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d)
            rc = gen.run(Args(kind="agent", root=d))
            self.assertEqual(rc, 0)  # 안내 + exit 0

    def test_deterministic_output(self):
        with tempfile.TemporaryDirectory() as d:
            make_root(d)
            r1, _ = gen._build_registration(d, "claude", ["aaa-hook", "bbb-hook"])
            r2, _ = gen._build_registration(d, "claude", ["bbb-hook", "aaa-hook"])
            self.assertEqual(json.dumps(r1, sort_keys=True), json.dumps(r2, sort_keys=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
