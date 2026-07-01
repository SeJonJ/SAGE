#!/usr/bin/env python3
"""AssetPaths 단일 로케이터 검증 (P2-6 — generate/validate/absorb 경로 수렴).

핵심 가드: AssetPaths 의 각 경로가 **리팩터 이전 인라인 조립 결과와 바이트 동일**해야 한다.
(무위험 리팩터 전제) 아래 _legacy_* 는 generate/validate/absorb 에 흩어져 있던 옛 조립식을
독립 재현한 것 — AssetPaths 가 한 글자라도 달라지면 이 동치 테스트가 깨진다.
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.asset_paths import AssetPaths, hook_runtime_files  # noqa: E402

ROOT = "/tmp/sage-fake-root"


def _legacy_hook_spec(root, hid):
    return os.path.join(root, "docs", "sage_harness", "hooks", f"{hid}.md")


def _legacy_core(root, hid):
    H = os.path.join(root, "scripts", "sage_harness", "hooks")
    return os.path.join(H, f"{hid.replace('-', '_')}_core.py")


def _legacy_native(root, hid):
    H = os.path.join(root, "scripts", "sage_harness", "hooks")
    return os.path.join(H, f"{hid}.sh")


def _legacy_adapter(root, hid, rt):
    H = os.path.join(root, "scripts", "sage_harness", "hooks")
    return os.path.join(H, "adapters", rt, f"{hid}.sh")


class TestAssetPathsEquivalence(unittest.TestCase):
    """리팩터된 4사이트가 의존하는 경로가 옛 조립식과 동일함을 박제."""

    def setUp(self):
        self.ap = AssetPaths(ROOT, "hook", "pre-implementation-gate")

    def test_spec_matches_legacy(self):
        self.assertEqual(self.ap.spec, _legacy_hook_spec(ROOT, "pre-implementation-gate"))

    def test_core_matches_legacy_with_snake(self):
        # kebab → snake 변환 규약(generate/validate/absorb 공통)
        self.assertEqual(self.ap.core, _legacy_core(ROOT, "pre-implementation-gate"))
        self.assertTrue(self.ap.core.endswith("pre_implementation_gate_core.py"))

    def test_native_matches_legacy(self):
        self.assertEqual(self.ap.native, _legacy_native(ROOT, "pre-implementation-gate"))

    def test_adapter_per_runtime_matches_legacy(self):
        for rt in ("claude", "codex"):
            self.assertEqual(self.ap.adapter(rt), _legacy_adapter(ROOT, "pre-implementation-gate", rt))

    def test_snake_property(self):
        self.assertEqual(self.ap.snake, "pre_implementation_gate")


class TestAssetPathsKinds(unittest.TestCase):
    """agent/skill 은 docs 디렉토리가 kind 별로 갈린다(spec/claims)."""

    def test_docs_dir_per_kind(self):
        self.assertTrue(AssetPaths(ROOT, "hook", "h").spec.endswith(os.path.join("hooks", "h.md")))
        self.assertTrue(AssetPaths(ROOT, "agent", "a").spec.endswith(os.path.join("agents", "a.md")))
        self.assertTrue(AssetPaths(ROOT, "skill", "s").spec.endswith(os.path.join("skills", "s.md")))

    def test_claims_path(self):
        self.assertTrue(AssetPaths(ROOT, "agent", "a").claims.endswith(os.path.join("agents", "a.claims.yml")))

    def test_frozen_immutable(self):
        ap = AssetPaths(ROOT, "hook", "h")
        with self.assertRaises(Exception):
            ap.id = "x"  # frozen dataclass

    def test_hook_runtime_files_grouped(self):
        groups = hook_runtime_files(ROOT)
        self.assertEqual(
            [os.path.relpath(p, ROOT) for p in groups["shared"]],
            [
                os.path.join("scripts", "sage_harness", "hooks", "runtime", "run_hook.py"),
                os.path.join("scripts", "sage_harness", "hooks", "runtime", "hook_runtime.py"),
                os.path.join("scripts", "sage_harness", "hooks", "runtime", "loop_audit.py"),
                os.path.join("scripts", "sage_harness", "hooks", "runtime", "messages.py"),
            ],
        )
        self.assertEqual(os.path.basename(groups["claude"][0]), "io_claude.py")
        self.assertEqual(os.path.basename(groups["codex"][0]), "io_codex.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
