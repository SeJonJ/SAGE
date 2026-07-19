#!/usr/bin/env python3
"""sage generate --kind roster 단위 (EH-1 동적 컴포넌트 파생 roster).

핵심: profile.components → 컴포넌트당 implementer-<id>.md spec 결정론 생성.
naming=implementer-<comp>(접두, 함수역할 충돌 회피) / 빈 components=폴백(생성 없음) /
create-only(기존 손편집 보존) / dry-run(--write 없으면 미기록) / malformed component fail-closed.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import generate as G  # noqa: E402


class Args:
    def __init__(self, dest, write=False):
        self.dest = dest
        self.write = write
        self.root = dest


def _instance(tmp, profile_yaml):
    os.makedirs(os.path.join(tmp, "docs", "sage_harness", "agents"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "sage"), exist_ok=True)
    with open(os.path.join(tmp, "docs", "sage_harness", ".manifest.json"), "w") as f:
        f.write('{"assets":{}}')
    with open(os.path.join(tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
        f.write(profile_yaml)
    return tmp


def _agent(tmp, aid):
    return os.path.join(tmp, "docs", "sage_harness", "agents", f"{aid}.md")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


_TWO = """project: { name: x }
components:
  - { id: core, paths: ["src/core/**"] }
  - { id: ui, paths: ["src/ui/**"], model: sonnet }
"""


class TestImplementerSpec(unittest.TestCase):
    def test_owns_and_id_and_model(self):
        md = G._implementer_spec_md("core", ["src/core/**", "lib/**"], "opus", "codex", "gpt-picked")
        self.assertIn("id: implementer-core", md)
        self.assertIn("owns: src/core/**, lib/**", md)
        self.assertIn("model: opus", md)
        self.assertIn("active_host: codex", md)
        self.assertIn("runtime_model: gpt-picked", md)
        self.assertIn("the `core` component", md)
        self.assertIn("{id}.claims.yml", md)   # 리터럴 보존(f-string escape)


class TestGenRoster(unittest.TestCase):
    def test_components_generate_prefixed_specs(self):
        with tempfile.TemporaryDirectory() as tmp:
            _instance(tmp, _TWO)
            rc = G._gen_roster(Args(tmp, write=True), tmp)
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(_agent(tmp, "implementer-core")))
            self.assertTrue(os.path.exists(_agent(tmp, "implementer-ui")))
            ui = _read(_agent(tmp, "implementer-ui"))
            self.assertIn("owns: src/ui/**", ui)
            self.assertIn("model: sonnet", ui)   # component.model 오버라이드

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _instance(tmp, _TWO)
            G._gen_roster(Args(tmp, write=False), tmp)
            self.assertFalse(os.path.exists(_agent(tmp, "implementer-core")))

    def test_empty_components_fallback_no_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _instance(tmp, "project: { name: x }\ncomponents: []\n")
            rc = G._gen_roster(Args(tmp, write=True), tmp)
            self.assertEqual(rc, 0)
            self.assertEqual(os.listdir(os.path.join(tmp, "docs", "sage_harness", "agents")), [])

    def test_create_only_preserves_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _instance(tmp, _TWO)
            with open(_agent(tmp, "implementer-core"), "w", encoding="utf-8") as f:
                f.write("HANDEDITED")
            G._gen_roster(Args(tmp, write=True), tmp)
            self.assertEqual(_read(_agent(tmp, "implementer-core")), "HANDEDITED")
            self.assertTrue(os.path.exists(_agent(tmp, "implementer-ui")))   # 신규는 생성

    def test_component_without_id_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _instance(tmp, 'project: { name: x }\ncomponents:\n  - { paths: ["a/**"] }\n  - { id: ui, paths: ["src/ui/**"] }\n')
            rc = G._gen_roster(Args(tmp, write=True), tmp)
            files = sorted(os.listdir(os.path.join(tmp, "docs", "sage_harness", "agents")))
            self.assertEqual(rc, 1)
            self.assertEqual(files, [])

    def test_unsafe_component_id_cannot_escape_roster_directory(self):
        with tempfile.TemporaryDirectory() as parent:
            tmp = os.path.join(parent, "project")
            _instance(tmp, 'project: { name: x }\ncomponents:\n  - { id: "x/../../../../../escaped", paths: ["src/**"] }\n')
            Path(tmp, "docs/sage_harness/agents/implementer-x").mkdir()

            rc = G._gen_roster(Args(tmp, write=True), tmp)

            self.assertEqual(rc, 1)
            self.assertFalse(Path(parent, "escaped.md").exists())

    def test_invalid_runtime_model_fails_before_roster_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            _instance(tmp, 'project: { name: x }\ncomponents:\n  - { id: core, paths: ["src/**"], runtime_models: {claude: "bad model"} }\n')

            self.assertEqual(G._gen_roster(Args(tmp, write=True), tmp), 1)
            self.assertEqual(os.listdir(os.path.join(tmp, "docs", "sage_harness", "agents")), [])

    def test_injected_component_path_fails_before_roster_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            _instance(tmp, 'project: { name: x }\ncomponents:\n  - id: core\n    paths: ["src/**\\n---\\nid: injected"]\n')

            self.assertEqual(G._gen_roster(Args(tmp, write=True), tmp), 1)
            self.assertEqual(os.listdir(os.path.join(tmp, "docs", "sage_harness", "agents")), [])

    def test_parse_error_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            _instance(tmp, "{ this is not: valid: yaml: [")
            self.assertEqual(G._gen_roster(Args(tmp, write=True), tmp), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
