#!/usr/bin/env python3
"""sage generate --kind roster 단위 (EH-1 동적 컴포넌트 파생 roster).

핵심: profile.components → 컴포넌트당 implementer-<id>.md spec 결정론 생성.
naming=implementer-<comp>(접두, 함수역할 충돌 회피) / 빈 components=폴백(생성 없음) /
create-only(기존 손편집 보존) / dry-run(--write 없으면 미기록) / malformed component fail-closed.
"""
import contextlib
import io
import os
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import generate as G  # noqa: E402
from sage import overlay_common as oc  # noqa: E402
from sage.i18n.context import LanguageContext  # noqa: E402


class Args:
    def __init__(self, dest, write=False, from_existing=None, language=None):
        self.dest = dest
        self.write = write
        self.root = dest
        self.from_existing = from_existing
        if language:
            self._language_context = LanguageContext(language=language, source="cli")


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

    def test_mode_label_follows_language(self):
        """dry-run/생성 모드 문구도 language_of() 를 따른다."""
        with tempfile.TemporaryDirectory() as tmp:
            _instance(tmp, _TWO)
            buf = io.StringIO()
            with redirect_stdout(buf):
                G._gen_roster(Args(tmp, write=False, language="en"), tmp)
            text = buf.getvalue()
            self.assertIn("would generate (dry-run", text)
            self.assertNotIn("생성예정", text)

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


_PROFILE = ('project: { name: x }\n'
            'components:\n  - { id: payment, paths: ["src/payment/**"], model: opus }\n')

_SRC_RENDER = """---
name: implementer-a
description: "SAGE implementer A — one assigned component. 사용자가 구현자A 라고 말할 때."
---

# implementer-a — SAGE Component Implementer A

Your ownership boundary is the component in `profile.team.core.implementer-a.owns`.
Coordinate at integration points with implementer-b.
"""

_OVERLAY = "- 결제 도메인은 PG 규약 문서를 먼저 읽는다.\n"


class TestPromoteFromExisting(unittest.TestCase):
    """10-a-B: 새 컴포넌트 implementer 가 기존 워커에 쌓인 프로젝트 규칙을 물려받는 경로.

    빈 spec 만 만들고 렌더를 처음부터 재저작하게 하면, `implementer-a` 에 쌓인 CORE 렌더 +
    오버레이(실 프로젝트 규칙)가 통째로 버려진다.
    """

    def _project(self, tmp, overlay=_OVERLAY, render=_SRC_RENDER):
        _instance(tmp, _PROFILE)
        agents = os.path.join(tmp, ".claude", "agents")
        os.makedirs(agents, exist_ok=True)
        if render is not None:
            Path(agents, "implementer-a.md").write_text(render, encoding="utf-8")
        if overlay is not None:
            over = os.path.join(tmp, "sage", "asset_overrides", "agents")
            os.makedirs(over, exist_ok=True)
            Path(over, "implementer-a.md").write_text(overlay, encoding="utf-8")
        return os.path.join(agents, "implementer-payment.md")

    def test_seeded_render_carries_base_and_overlay_with_new_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._project(tmp)
            self.assertEqual(G._gen_roster(Args(tmp, write=True, from_existing="implementer-a"), tmp), 0)
            text = Path(out).read_text(encoding="utf-8")
            self.assertIn("name: implementer-payment", text)
            self.assertIn("PG 규약 문서", text)                 # 오버레이 규칙 승계
            self.assertIn("src/payment/**", text)               # 소유 경계가 시드 시점에 확정
            self.assertNotIn("team.core.implementer-payment.owns", text)   # 죽은 필드 승계 금지

    def test_seed_does_not_carry_overlay_markers(self):
        # 마커를 옮기면 install/validate 가 프로젝트 소유 렌더를 CORE 관리 구간으로 오인한다.
        composed = _SRC_RENDER + oc.compose_block(_OVERLAY, "agents", "implementer-a")
        with tempfile.TemporaryDirectory() as tmp:
            out = self._project(tmp, overlay=None, render=composed)
            self.assertEqual(G._gen_roster(Args(tmp, write=True, from_existing="implementer-a"), tmp), 0)
            text = Path(out).read_text(encoding="utf-8")
            self.assertNotIn("SAGE OVERLAY", text)
            self.assertIn("PG 규약 문서", text)                 # 내용은 살아서 넘어온다

    def test_self_identity_lines_are_regenerated_not_inherited(self):
        """description·제목은 자기소개 자리라 원본 산문을 물려주면 안 된다.

        description 은 host 가 이 워커를 언제 부를지 판정하는 **호출 트리거**다. 원본을 물려주면
        결제 워커가 자기를 "Implementer A"·"구현자A" 로 소개해 트리거가 원본을 가리킨다. 둘 다
        id·컴포넌트만으로 완전히 재생성되는 자리라 추측이 없다.
        """
        with tempfile.TemporaryDirectory() as tmp:
            out = self._project(tmp)
            self.assertEqual(G._gen_roster(Args(tmp, write=True, from_existing="implementer-a"), tmp), 0)
            text = Path(out).read_text(encoding="utf-8")
            head = text.split("\n---\n", 1)[0]
            self.assertIn("`payment` component", head)
            self.assertIn("/implementer-payment", head)
            for stale in ("Implementer A", "implementer A", "구현자A"):
                self.assertNotIn(stale, text, f"{stale!r} 가 시드 렌더에 남았다")
            self.assertIn("# implementer-payment — SAGE implementer for the `payment` component", text)

    def test_description_without_frontmatter_is_left_alone(self):
        # frontmatter 가 없거나 깨진 렌더에서 억지로 자르면 host 가 렌더를 통째로 못 읽는다.
        text, _, err = G._promoted_render("# implementer-a\n본문\n", "", "implementer-a",
                                          "implementer-payment", "payment", ["src/**"])
        self.assertIsNone(err)
        self.assertIn("본문", text)

    def test_unguessable_references_are_reported_not_guessed(self):
        """재생성할 수 없는 참조만 잔존으로 보고한다.

        `implementer-b` 는 CORE 2인 로스터 전제의 협업/경계 문장이다. 컴포넌트 로스터는 N개라
        실제 상대가 누구인지 프로젝트 구성을 봐야 알 수 있다 — 여기서 추측해 채우면 존재하지
        않는 워커와 협업하라는 지시를 조용히 심는다.
        """
        _, residuals, err = G._promoted_render(_SRC_RENDER, _OVERLAY, "implementer-a",
                                               "implementer-payment", "payment",
                                               ["src/payment/**"])
        self.assertIsNone(err)
        self.assertEqual(residuals, ["implementer-b"])

    def test_seeding_runs_even_when_the_spec_already_exists(self):
        """spec create-only 가 시드까지 막으면 승격 경로가 영원히 닫힌다.

        `--kind roster` 를 한 번 돌린 프로젝트는 spec 만 있고 렌더는 없다. 그 상태에서
        `--from-existing` 을 붙여도 spec 존재를 이유로 건너뛰면, rc=0 · 시드 0건으로 끝나
        사용자는 승계가 완료됐다고 오인한다.
        """
        with tempfile.TemporaryDirectory() as tmp:
            out = self._project(tmp)
            # 1회차: 플래그 없이 spec 만 생성
            self.assertEqual(G._gen_roster(Args(tmp, write=True), tmp), 0)
            self.assertTrue(os.path.exists(_agent(tmp, "implementer-payment")))
            self.assertFalse(Path(out).exists())
            # 2회차: 이제 승격이 실제로 일어나야 한다
            self.assertEqual(G._gen_roster(Args(tmp, write=True, from_existing="implementer-a"), tmp), 0)
            self.assertTrue(Path(out).exists(), "spec 이 있다는 이유로 시드가 건너뛰어졌다")
            self.assertIn("PG 규약 문서", Path(out).read_text(encoding="utf-8"))

    def test_existing_render_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._project(tmp)
            Path(out).write_text("손편집 렌더\n", encoding="utf-8")
            self.assertEqual(G._gen_roster(Args(tmp, write=True, from_existing="implementer-a"), tmp), 0)
            self.assertEqual(Path(out).read_text(encoding="utf-8"), "손편집 렌더\n")

    def test_skip_existing_note_follows_language(self):
        """"skip(기존 렌더 보존)" 노트도 language_of() 를 따른다."""
        with tempfile.TemporaryDirectory() as tmp:
            out = self._project(tmp)
            Path(out).write_text("손편집 렌더\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                G._gen_roster(Args(tmp, write=True, from_existing="implementer-a", language="en"), tmp)
            text = buf.getvalue()
            self.assertIn("kept existing render", text)
            self.assertNotIn("기존 렌더 보존", text)

    def test_missing_source_render_error_follows_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp, render=None)
            buf = io.StringIO()
            with redirect_stdout(io.StringIO()), contextlib.redirect_stderr(buf):
                G._gen_roster(Args(tmp, write=True, from_existing="implementer-a", language="en"), tmp)
            text = buf.getvalue()
            self.assertIn("source render not found", text)
            self.assertNotIn("원본 렌더를 찾지 못함", text)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._project(tmp)
            self.assertEqual(G._gen_roster(Args(tmp, from_existing="implementer-a"), tmp), 0)
            self.assertFalse(Path(out).exists())

    def test_missing_source_render_fails_instead_of_seeding_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp, render=None)
            self.assertEqual(G._gen_roster(Args(tmp, write=True, from_existing="implementer-a"), tmp), 1)

    def test_malformed_source_markers_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = _SRC_RENDER + oc.MARKER_START + "\n짝 없는 시작\n"
            out = self._project(tmp, overlay=None, render=broken)
            self.assertEqual(G._gen_roster(Args(tmp, write=True, from_existing="implementer-a"), tmp), 1)
            self.assertFalse(Path(out).exists())

    def test_injected_source_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._project(tmp)
            self.assertEqual(
                G._gen_roster(Args(tmp, write=True, from_existing="../../etc/passwd"), tmp), 1)

    def test_without_the_flag_behaviour_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._project(tmp)
            self.assertEqual(G._gen_roster(Args(tmp, write=True), tmp), 0)
            self.assertFalse(Path(out).exists())          # 시드는 명시 opt-in


if __name__ == "__main__":
    unittest.main(verbosity=2)
