#!/usr/bin/env python3
"""sage install 검증 (중 등급 — 부트스트랩).

self-contained: 임시 dest 에 install 후 산출물/치환/멱등 확인.
"""
import hashlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stderr
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import install  # noqa: E402


class Args:
    def __init__(self, host, dest, prefix="sage", force=False, no_global_skill=False,
                 skill_scope=None):
        self.host = host; self.dest = dest; self.prefix = prefix; self.force = force
        self.no_global_skill = no_global_skill
        # Existing Codex test cases now state their legacy intent explicitly. Claude does not use this option.
        self.skill_scope = ("global" if host == "codex" and skill_scope is None
                            and not no_global_skill else skill_scope)


def _tree_snapshot(root):
    snapshot = {}
    base = Path(root)
    for path in sorted(base.rglob("*")):
        rel = str(path.relative_to(base))
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            snapshot[rel] = ("symlink", stat.S_IMODE(mode), os.readlink(path))
        elif stat.S_ISDIR(mode):
            snapshot[rel] = ("dir", stat.S_IMODE(mode))
        elif stat.S_ISREG(mode):
            snapshot[rel] = ("file", stat.S_IMODE(mode), path.read_bytes())
        else:
            snapshot[rel] = ("special", stat.S_IFMT(mode), stat.S_IMODE(mode))
    return snapshot


class TestInstall(unittest.TestCase):
    def test_bootstrap_skill_inventory_contains_full_and_local_init(self):
        self.assertIn("sage-init", install.core_skill_ids())
        self.assertIn("sage-init-local", install.core_skill_ids())

    def test_both_init_skills_deploy_to_every_supported_discovery_scope(self):
        with tempfile.TemporaryDirectory() as claude_root:
            self.assertEqual(install.run(Args("claude", claude_root)), 0)
            for skill_id in ("sage-init", "sage-init-local"):
                self.assertTrue(Path(claude_root, ".claude", "skills", skill_id, "SKILL.md").is_file())

        with tempfile.TemporaryDirectory() as global_root, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                self.assertEqual(install.run(Args("codex", global_root, skill_scope="global")), 0)
            for skill_id in ("sage-init", "sage-init-local"):
                self.assertTrue(Path(codex_home, "skills", skill_id, "SKILL.md").is_file())

        with tempfile.TemporaryDirectory() as local_root, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                self.assertEqual(
                    install.run(Args("codex", local_root, skill_scope="project-local")), 0)
            for skill_id in ("sage-init", "sage-init-local"):
                self.assertTrue(Path(local_root, ".codex", "skills", skill_id, "SKILL.md").is_file())

    def test_init_skill_contracts_enforce_shared_and_local_ownership(self):
        full = Path(
            REPO, "templates", "core", "framework", ".claude", "skills", "sage-init", "SKILL.md"
        ).read_text(encoding="utf-8")
        local = Path(
            REPO, "templates", "core", "framework", ".claude", "skills", "sage-init-local", "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("project.name", full)
        self.assertIn("risk", full)
        self.assertIn("components", full)
        self.assertIn("sage-init-local", full)
        self.assertIn("project-profile.local.yaml", full)
        self.assertIn("required", full)
        self.assertIn("false", full)
        self.assertIn("BLOCKED", full)

        self.assertIn("bootstrapped shared", local)
        self.assertIn("project-profile.local.yaml", local)
        self.assertIn("project-profile.yaml을 수정하지", local)
        self.assertIn("required", local)
        self.assertIn("false", local)
        self.assertIn("BLOCKED", local)

    def test_install_packages_local_schema_and_ignores_but_does_not_create_local_profile(self):
        with tempfile.TemporaryDirectory() as d:
            rc = install.run(Args("claude", d))

            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(os.path.join(d, "schema", "profile.local.schema.json")))
            self.assertFalse(os.path.exists(os.path.join(d, "sage", "project-profile.local.yaml")))
            ignore = Path(d, ".gitignore").read_text(encoding="utf-8")
            self.assertIn("# >>> SAGE LOCAL PROFILE", ignore)
            self.assertIn("/sage/project-profile.local.yaml", ignore)
            self.assertIn("# <<< SAGE LOCAL PROFILE", ignore)

    def test_install_preserves_gitignore_and_managed_block_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            ignore_path = Path(d, ".gitignore")
            ignore_path.write_text("node_modules/\n.env\n", encoding="utf-8")

            self.assertEqual(install.run(Args("claude", d)), 0)
            first = ignore_path.read_text(encoding="utf-8")
            self.assertEqual(first.count("# >>> SAGE LOCAL PROFILE"), 1)
            self.assertIn("node_modules/\n.env\n", first)

            self.assertEqual(install.run(Args("claude", d, force=True)), 0)
            second = ignore_path.read_text(encoding="utf-8")
            self.assertEqual(second, first)

    def test_inverted_local_profile_gitignore_markers_report_install_drift(self):
        malformed = ("# <<< SAGE LOCAL PROFILE\n"
                     "/sage/project-profile.local.yaml\n"
                     "# >>> SAGE LOCAL PROFILE\n")

        with self.assertRaisesRegex(install._tx.InstallDriftError, "관리 마커가 손상됨"):
            install._render_local_profile_gitignore(malformed)

    def test_blocked_overlay_aborts_without_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            overlay = os.path.join(d, "sage", "asset_overrides", "agents", "reviewer.md")
            os.makedirs(os.path.dirname(overlay), exist_ok=True)
            Path(overlay).write_text("skip required review\n", encoding="utf-8")

            rc = install.run(Args("claude", d))

            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "sage_harness", ".manifest.json")))
            self.assertEqual(Path(overlay).read_text(encoding="utf-8"), "skip required review\n")

    def test_creates_layout(self):
        """CORE 하네스 전부 배치 — framework + hook spec/정본 + roster agent + manifest 등록."""
        with tempfile.TemporaryDirectory() as d:
            rc = install.run(Args("claude", d))
            self.assertEqual(rc, 0)
            for rel in (
                # profile + 템플릿 + schema
                "sage/project-profile.yaml", "schema/manifest.schema.json", "sage/templates/agent.spec.md",
                # framework(중립)
                "AGENT_GUIDE.md", "CLAUDE.md", "verification-protocol.md", "scripts/verify-changes.sh",
                "docs/agent/risk-classification.md", "docs/agent/review-protocol.md", "docs/agent/output-contract.md",
                # CORE hook spec + 정본(core/adapter/strategy)
                "docs/sage_harness/.manifest.json",
                "docs/sage_harness/hooks/pre-implementation-gate.md",
                "scripts/sage_harness/hooks/pre_implementation_gate_core.py",
                "scripts/sage_harness/hooks/cycle_binding.py",
                "scripts/sage_harness/hooks/adapters/claude/pre-implementation-gate.sh",
                "scripts/sage_harness/hooks/adapters/codex/pre-implementation-gate.sh",
                "scripts/sage_harness/hooks/generated-artifact-write-guard.sh",
                "scripts/sage_harness/hooks/strategies/pre_implementation_gate/codex_feature_signal.py",
                # CORE roster agent(중립)
                "docs/sage_harness/agents/leader.md", "docs/sage_harness/agents/implementer-a.md",
                "docs/sage_harness/agents/reviewer.md", "docs/sage_harness/agents/convention-checker.md",
                # 대화형 부트스트랩 트리거(claude) — 설계상 진입점
                ".claude/skills/sage-init/SKILL.md",
                # CORE 6인 에이전트 렌더 (Claude Code .claude/agents/ 자동발견)
                ".claude/agents/leader.md",
                ".claude/agents/implementer-a.md",
                ".claude/agents/implementer-b.md",
                ".claude/agents/qa.md",
                ".claude/agents/reviewer.md",
                ".claude/agents/convention-checker.md",
                # CORE skill spec 6종 → docs/sage_harness/skills/ (3분할: cycle/plan/team)
                "docs/sage_harness/skills/sage-cycle.md",
                "docs/sage_harness/skills/sage-plan.md",
                "docs/sage_harness/skills/sage-team.md",
                "docs/sage_harness/skills/sage-review.md",
                "docs/sage_harness/skills/sage-asset.md",
                "docs/sage_harness/skills/sage-profile-modify.md",
                # CORE skill 렌더 (Claude Code .claude/skills/ 자동발견)
                ".claude/skills/sage-cycle/SKILL.md",
                ".claude/skills/sage-plan/SKILL.md",
                ".claude/skills/sage-team/SKILL.md",
                ".claude/skills/sage-review/SKILL.md",
                ".claude/skills/sage-asset/SKILL.md",
                ".claude/skills/sage-profile-modify/SKILL.md",
            ):
                self.assertTrue(os.path.exists(os.path.join(d, rel)), rel)
            guide = Path(d, "AGENT_GUIDE.md").read_text(encoding="utf-8")
            review = Path(d, "docs", "agent", "review-protocol.md").read_text(encoding="utf-8")
            verify = Path(d, "verification-protocol.md").read_text(encoding="utf-8")
            self.assertIn("exact stem", guide)
            self.assertIn("recent-file/mtime fallback are not cycle", guide)
            self.assertIn("exact same-`Cycle-Stem` Phase 01", review)
            self.assertIn("Phase 04 cannot introduce unknown IDs", verify)
            # tests/ 는 배치하지 않음(런타임 불필요)
            self.assertFalse(os.path.exists(os.path.join(d, "scripts/sage_harness/hooks/tests")))

    def test_host_prefix_substitution(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("codex", d, prefix="myapp"))
            prof = Path(os.path.join(d, "sage", "project-profile.yaml")).read_text(encoding="utf-8")
            self.assertIn("installed_hosts: [codex]", prof)
            self.assertIn("active_host: codex", prof)
            self.assertIn('prefix: "myapp"', prof)
            # codex host → CODEX.md wrapper (CLAUDE.md 아님)
            self.assertTrue(os.path.exists(os.path.join(d, "CODEX.md")))
            self.assertFalse(os.path.exists(os.path.join(d, "CLAUDE.md")))
            m = json.loads(Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).read_text(encoding="utf-8"))
            self.assertEqual(m["host_runtime"], "codex")
            self.assertEqual(m["installed_hosts"], ["codex"])
            self.assertRegex(m["source_core_content_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(m["source_core_content_hash"], m["installed_core_content_hash"])
            self.assertIn("dirty_flag", m)
            self.assertIn("sage_source_commit", m)
            # manifest 는 CORE hook 7종 등록(빈 assets 아님) → generate 가 동작 가능
            self.assertEqual(len([k for k in m["assets"] if k.startswith("hooks/")]), 7)
            self.assertEqual(m["assets"]["hooks/pre-implementation-gate"]["form"], "core_adapter")
            self.assertEqual(m["assets"]["hooks/generated-artifact-write-guard"]["form"], "native")

    def test_sequential_install_preserves_primary_and_tracks_both_hosts(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            self.assertEqual(install.run(Args("codex", d, force=True, no_global_skill=True)), 0)
            manifest = json.loads(Path(os.path.join(
                d, "docs", "sage_harness", ".manifest.json")).read_text(encoding="utf-8"))
            self.assertEqual(manifest["host_runtime"], "claude")
            self.assertEqual(manifest["installed_hosts"], ["claude", "codex"])
            self.assertTrue(os.path.isdir(os.path.join(d, ".claude")))
            self.assertTrue(os.path.isdir(os.path.join(d, ".codex")))
            receipt_hosts = {key.split("/", 1)[0] for key in manifest["core_renders"]}
            self.assertEqual(receipt_hosts, {"claude", "codex"})
            self.assertEqual(manifest["core_renders"]["claude/framework/AGENT_GUIDE"],
                             manifest["core_renders"]["codex/framework/AGENT_GUIDE"])

    def test_manifest_refreshes_shared_guide_receipt_for_both_hosts(self):
        old_receipt = {"base_sha256": "old", "sage_version": "old"}
        new_receipt = {"base_sha256": "new", "sage_version": "new"}
        existing = {
            "host_runtime": "claude",
            "installed_hosts": ["claude", "codex"],
            "assets": {},
            "core_renders": {
                "claude/framework/AGENT_GUIDE": dict(old_receipt),
                "codex/framework/AGENT_GUIDE": dict(old_receipt),
            },
        }

        manifest = install._manifest(
            "codex", existing, {"codex/framework/AGENT_GUIDE": dict(new_receipt)})

        self.assertEqual(manifest["core_renders"]["claude/framework/AGENT_GUIDE"], new_receipt)
        self.assertEqual(manifest["core_renders"]["codex/framework/AGENT_GUIDE"], new_receipt)

    def test_second_host_without_force_still_updates_manifest_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            self.assertEqual(install.run(Args("codex", d, no_global_skill=True)), 0)
            manifest = json.loads(Path(os.path.join(
                d, "docs", "sage_harness", ".manifest.json")).read_text(encoding="utf-8"))
            self.assertEqual(manifest["installed_hosts"], ["claude", "codex"])
            receipt_hosts = {key.split("/", 1)[0] for key in manifest["core_renders"]}
            self.assertEqual(receipt_hosts, {"claude", "codex"})

    def test_legacy_manifest_seeds_installed_hosts_before_append(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            manifest_path = os.path.join(d, "docs", "sage_harness", ".manifest.json")
            legacy = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            legacy.pop("installed_hosts")
            legacy.pop("core_renders")
            self.assertIsNone(install._manifest_structure_issue(legacy))
            Path(manifest_path).write_text(json.dumps(legacy), encoding="utf-8")

            self.assertEqual(install.run(Args("codex", d, no_global_skill=True)), 0)

            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["host_runtime"], "claude")
            self.assertEqual(manifest["installed_hosts"], ["claude", "codex"])
    def test_codex_host_deploys_agents_md(self):
        # codex 부트스트랩 라우터: codex 가 auto-read 하는 AGENTS.md 배치(codex 협의 c+).
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("codex", d))
            agents = os.path.join(d, "AGENTS.md")
            self.assertTrue(os.path.exists(agents))
            body = Path(agents).read_text(encoding="utf-8")
            self.assertIn("bootstrap-authoring.md", body)
            self.assertIn("AGENT_GUIDE.md", body)

    def test_claude_host_no_agents_md(self):
        # claude 는 /sage-init 스킬 사용 → AGENTS.md 미배치(스킬만)
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            self.assertFalse(os.path.exists(os.path.join(d, "AGENTS.md")))
            self.assertTrue(os.path.exists(os.path.join(d, ".claude", "skills", "sage-init", "SKILL.md")))

    def test_claude_host_deploys_core_agent_renders(self):
        """Gap-1 mutation teeth: claude install 시 6인 에이전트 렌더가 .claude/agents/ 에 배치된다."""
        _CORE_AGENTS = ["leader", "implementer-a", "implementer-b", "qa", "reviewer", "convention-checker"]
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            for aid in _CORE_AGENTS:
                path = os.path.join(d, ".claude", "agents", f"{aid}.md")
                self.assertTrue(os.path.exists(path), f".claude/agents/{aid}.md 미배치")
                body = Path(path).read_text(encoding="utf-8")
                self.assertIn(f"name: {aid}", body, f"{aid}.md frontmatter name 누락")
                self.assertIn("description:", body, f"{aid}.md frontmatter description 누락")

    def test_codex_host_deploys_codex_agent_renders(self):
        """사용자 지침: codex install 도 CORE 6인 에이전트 렌더를 받는다(리소스 생성 시 codex 누락 금지).

        host 택1이라 codex 는 .claude/agents/ 는 두지 않고(.claude 는 Claude Code 전용), 동일 소스를
        repo .codex/agents/<id>.md 로 배포한다(SAGE 설계 정본 — write-guard·reverse_extract)."""
        _CORE_AGENTS = ["leader", "implementer-a", "implementer-b", "qa", "reviewer", "convention-checker"]
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("codex", d, no_global_skill=True))
            self.assertFalse(os.path.exists(os.path.join(d, ".claude", "agents")))  # claude 전용 경로는 미배치
            for aid in _CORE_AGENTS:
                path = os.path.join(d, ".codex", "agents", f"{aid}.md")
                self.assertTrue(os.path.exists(path), f".codex/agents/{aid}.md 미배치")
                self.assertIn(f"name: {aid}", Path(path).read_text(encoding="utf-8"))

    def test_deploys_core_skill_specs(self):
        """Gap-2 mutation teeth: CORE skill spec 6종이 docs/sage_harness/skills/ 에 배치된다."""
        _CORE_SKILLS = list(install._CORE_SKILLS)   # 런타임 목록에서 파생 — rename/추가 시 자동 동기(desync 방지)
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            for sid in _CORE_SKILLS:
                path = os.path.join(d, "docs", "sage_harness", "skills", f"{sid}.md")
                self.assertTrue(os.path.exists(path), f"docs/sage_harness/skills/{sid}.md 미배치")
                body = Path(path).read_text(encoding="utf-8")
                self.assertIn(f"id: {sid}", body, f"{sid}.md spec id 누락")
                self.assertIn("kind: skill", body, f"{sid}.md spec kind 누락")
                self.assertIn("## procedure", body, f"{sid}.md procedure 누락")

    def test_claude_host_deploys_core_skill_renders(self):
        """Gap-2 mutation teeth: claude install 시 CORE skill 렌더가 .claude/skills/ 에 배치된다."""
        _CORE_SKILLS = list(install._CORE_SKILLS)   # 런타임 목록에서 파생 — rename/추가 시 자동 동기(desync 방지)
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            for sid in _CORE_SKILLS:
                path = os.path.join(d, ".claude", "skills", sid, "SKILL.md")
                self.assertTrue(os.path.exists(path), f".claude/skills/{sid}/SKILL.md 미배치")
                body = Path(path).read_text(encoding="utf-8")
                self.assertIn(f"name: {sid}", body, f"{sid} SKILL.md name 누락")

    # SAGE 가 ship 한 legacy SKILL.md 에 들어있던 시그니처(정리 자격 판정용)
    _LEGACY_SIG = "name: pdca-start\nThis skill is a CORE framework bootstrap asset.\n"

    def test_claude_install_prunes_legacy_core_skill(self):
        """rename 수렴: claude install 은 은퇴한 SAGE CORE skill 잔존 사본을 .claude/skills/ 에서 제거한다.
        _LEGACY_CORE_SKILLS 전체(pdca-start·sage-pdca-start)를 검증 — 목록의 어느 항목이 깨져도 빨갛게."""
        for legacy_name in install._LEGACY_CORE_SKILLS:
            with self.subTest(legacy=legacy_name), tempfile.TemporaryDirectory() as d:
                legacy = os.path.join(d, ".claude", "skills", legacy_name)
                os.makedirs(legacy)
                Path(os.path.join(legacy, "SKILL.md")).write_text(self._LEGACY_SIG, encoding="utf-8")
                install.run(Args("claude", d))
                self.assertFalse(os.path.exists(legacy), f"은퇴한 {legacy_name} 잔존 사본 미제거")
                self.assertTrue(os.path.exists(os.path.join(d, ".claude", "skills", "sage-plan", "SKILL.md")))

    def test_codex_install_prunes_legacy_global_core_skill(self):
        """rename 수렴: codex install 은 은퇴한 SAGE CORE skill 잔존 사본을 전역 $CODEX_HOME/skills 에서 제거한다.
        _LEGACY_CORE_SKILLS 전체를 검증(런타임 목록과 테스트 매트릭스 일치)."""
        import unittest.mock as mock
        for legacy_name in install._LEGACY_CORE_SKILLS:
            with self.subTest(legacy=legacy_name), tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
                legacy = os.path.join(codex_home, "skills", legacy_name)
                os.makedirs(legacy)
                Path(os.path.join(legacy, "SKILL.md")).write_text(self._LEGACY_SIG, encoding="utf-8")
                with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                    install.run(Args("codex", d))
                self.assertFalse(os.path.exists(legacy), f"은퇴한 전역 {legacy_name} 잔존 사본 미제거")
                self.assertTrue(os.path.exists(os.path.join(codex_home, "skills", "sage-plan", "SKILL.md")))

    def test_install_preserves_foreign_skill_named_pdca_start(self):
        """안전: SAGE 시그니처가 없는 사용자 동명 skill(pdca-start)은 정리하지 않는다(codex R2-P2).
        codex 전역 $CODEX_HOME/skills 는 공유 공간이라 오삭제 시 피해가 크다."""
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            foreign = os.path.join(codex_home, "skills", "pdca-start")
            os.makedirs(foreign)
            Path(os.path.join(foreign, "SKILL.md")).write_text(
                "name: pdca-start\nmy own personal pdca helper\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                install.run(Args("codex", d))
            self.assertTrue(os.path.exists(foreign), "SAGE 자산 아닌 사용자 동명 skill 을 오삭제함")

    def test_legacy_prune_does_not_follow_skill_marker_symlink(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            skill_dir = Path(root, "pdca-start")
            skill_dir.mkdir()
            marker = Path(outside, "SKILL.md")
            marker.write_text(self._LEGACY_SIG, encoding="utf-8")
            (skill_dir / "SKILL.md").symlink_to(marker)
            pruned = []

            install._prune_legacy_skill(str(skill_dir), pruned)

            self.assertTrue(skill_dir.is_dir())
            self.assertTrue((skill_dir / "SKILL.md").is_symlink())
            self.assertEqual(pruned, [])

    def test_codex_no_global_skill_does_not_prune(self):
        """--no-global-skill 이면 전역 미접근 — 은퇴한 전역 사본도 건드리지 않는다(legacy 목록 전체)."""
        import unittest.mock as mock
        for legacy_name in install._LEGACY_CORE_SKILLS:
            with self.subTest(legacy=legacy_name), tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
                legacy = os.path.join(codex_home, "skills", legacy_name)
                os.makedirs(legacy)
                Path(os.path.join(legacy, "SKILL.md")).write_text(self._LEGACY_SIG, encoding="utf-8")
                with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                    install.run(Args("codex", d, no_global_skill=True))
                self.assertTrue(os.path.exists(legacy), f"--no-global-skill 인데 전역 {legacy_name} 사본을 건드림")

    def test_codex_host_installs_core_skills_globally(self):
        """Explicit global scope installs every CORE skill under `$CODEX_HOME/skills`."""
        import unittest.mock as mock
        _CORE_SKILLS = list(install._CORE_SKILLS)   # 런타임 목록에서 파생 — rename/추가 시 자동 동기(desync 방지)
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                install.run(Args("codex", d))
            for sid in _CORE_SKILLS:
                path = os.path.join(codex_home, "skills", sid, "SKILL.md")
                self.assertTrue(os.path.exists(path), f"전역 codex CORE skill {sid} 미설치")
                self.assertIn(f"name: {sid}", Path(path).read_text(encoding="utf-8"))
            # codex host 는 repo .claude/skills/ 에 CORE skill 렌더를 두지 않는다
            self.assertFalse(os.path.exists(os.path.join(d, ".claude", "skills", "sage-plan")))

    def test_asset_overrides_not_shipped_and_preserved_by_force_both_hosts(self):
        """Q2 overlay: project-local sage/asset_overrides 는 install 이 만들지도 덮지도 않는다.

        CORE 는 업그레이드 가능하고, loop/retro 가 만든 프로젝트별 overlay 는 --force 에도 생존해야 한다.
        """
        import unittest.mock as mock
        for host in ("claude", "codex"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
                with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                    install.run(Args(host, d, no_global_skill=(host == "codex")))
                    self.assertFalse(os.path.exists(os.path.join(d, "sage", "asset_overrides")))
                    overlay = os.path.join(d, "sage", "asset_overrides", "agents", "implementer-a.md")
                    os.makedirs(os.path.dirname(overlay), exist_ok=True)
                    Path(overlay).write_text("PROJECT_OVERLAY\n", encoding="utf-8")
                    self.assertEqual(
                        install.run(Args(host, d, force=True, no_global_skill=(host == "codex"))), 0)
                self.assertEqual(Path(overlay).read_text(encoding="utf-8"), "PROJECT_OVERLAY\n")

    def test_framework_overlay_is_preserved_but_install_blocks_it(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            overlay = os.path.join(d, "sage", "asset_overrides", "framework", "AGENT_GUIDE.md")
            os.makedirs(os.path.dirname(overlay), exist_ok=True)
            content = "---\ndomain_refs: [webrtc]\n---\nProject guidance.\n"
            Path(overlay).write_text(content, encoding="utf-8")
            manifest_path = os.path.join(d, "docs", "sage_harness", ".manifest.json")
            before = Path(manifest_path).read_bytes()

            self.assertEqual(install.run(Args("claude", d, force=True)), 1)

            self.assertEqual(Path(overlay).read_text(encoding="utf-8"), content)
            self.assertEqual(Path(manifest_path).read_bytes(), before)

    def test_force_reinstall_preserves_generated_kind_manifest_entries(self):
        """--force 재설치가 sage generate 로 등록된 mcp/agent/skill manifest 항목을 보존한다(이슈 #1).

        엔진 자산(CORE hook)은 미스탬프 스켈레톤으로 리셋되지만, 인스턴스가 등록한 다른 kind 는
        profile.yaml 과 같은 보존 정책을 따라야 한다 — 안 그러면 --force 가 등록을 지워 orphan drift 가 난다.
        """
        import unittest.mock as mock
        manifest_rel = os.path.join("docs", "sage_harness", ".manifest.json")
        for host in ("claude", "codex"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
                with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                    install.run(Args(host, d, no_global_skill=(host == "codex")))
                    mpath = os.path.join(d, manifest_rel)
                    m = json.loads(Path(mpath).read_text(encoding="utf-8"))
                    # sage generate --kind {mcp,agent,skill} --write 가 stamp 하는 항목을 모사
                    m["assets"]["mcps/weather"] = {"form": "declarative", "conformance": "PASS"}
                    m["assets"]["agents/analyst"] = {"form": "native", "conformance": "PASS"}
                    m["assets"]["skills/summarize"] = {"form": "native", "conformance": "PASS"}
                    a_core_hook = next(k for k in m["assets"] if k.startswith("hooks/"))
                    m["assets"][a_core_hook]["conformance"] = "PASS"  # 스탬프된 상태 모사
                    Path(mpath).write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

                    install.run(Args(host, d, force=True, no_global_skill=(host == "codex")))
                    m2 = json.loads(Path(mpath).read_text(encoding="utf-8"))
                # 등록 자산 보존
                self.assertEqual(m2["assets"].get("mcps/weather"), {"form": "declarative", "conformance": "PASS"})
                self.assertEqual(m2["assets"].get("agents/analyst"), {"form": "native", "conformance": "PASS"})
                self.assertEqual(m2["assets"].get("skills/summarize"), {"form": "native", "conformance": "PASS"})
                # CORE hook 은 엔진 자산 → 미스탬프 스켈레톤으로 리셋
                self.assertEqual(m2["assets"][a_core_hook]["conformance"], "UNKNOWN")
                self.assertEqual(len([k for k in m2["assets"] if k.startswith("hooks/")]), len(install._CORE_HOOKS))

    def test_force_reinstall_drops_corrupt_entries_and_validate_survives(self):
        """--force 보존이 손상 항목(non-dict)을 버려 이후 sage validate 가 크래시하지 않는다(codex R1-P1).

        보존을 무검증 얕은 복사로 하면 assets["agents/x"]=[] 같은 항목이 살아남아 validate 의 .get() 이
        AttributeError 로 게이트를 죽인다. dict 항목만 보존하고 실물 spec 은 orphan(WARN)으로 처리돼야 한다.
        """
        from sage.commands import validate as V

        class VArgs:
            def __init__(self, root):
                self.check = True; self.schema = False; self.kind = "all"; self.id = None; self.root = root

        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            mpath = os.path.join(d, "docs", "sage_harness", ".manifest.json")
            m = json.loads(Path(mpath).read_text(encoding="utf-8"))
            m["assets"]["mcps/good"] = {"form": "declarative", "conformance": "PASS"}
            m["assets"]["agents/bad_list"] = []       # 최상위 손상: dict 아님 → install 이 버림
            m["assets"]["skills/bad_null"] = None     # 최상위 손상: dict 아님 → install 이 버림
            # 내부 필드 손상(dict 라 install 필터를 통과) → validate 의 방어 가드가 크래시를 막아야 한다.
            m["assets"]["mcps/inner_render"] = {"render_hash": "not-a-dict"}
            m["assets"]["hooks/inner_adapter"] = {"adapter_hash": "bad", "form": "core_adapter"}
            m["assets"]["agents/inner_unres"] = {"unresolved": 1}
            m["assets"]["skills/inner_test"] = {"test": 123}
            Path(mpath).write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            self.assertEqual(install.run(Args("claude", d, force=True)), 0)
            m2 = json.loads(Path(mpath).read_text(encoding="utf-8"))
            self.assertEqual(m2["assets"].get("mcps/good"), {"form": "declarative", "conformance": "PASS"})
            self.assertNotIn("agents/bad_list", m2["assets"])   # 최상위 손상 항목은 버려짐
            self.assertNotIn("skills/bad_null", m2["assets"])
            self.assertTrue(all(isinstance(v, dict) for v in m2["assets"].values()))
            # 핵심 회귀: 내부 손상 dict 가 보존돼도 validate 게이트가 예외 없이 완주한다.
            # 크래시면 V.run 이 예외를 던져 테스트가 에러난다. TOOL_ERR(2)가 아니라 실제 자산 판정을
            # 냈음(STALE/FAIL)을 확인해 "게이트가 죽지 않고 완주"를 단언한다.
            rc = V.run(VArgs(d))
            self.assertIsInstance(rc, int)
            self.assertNotEqual(rc, 2)

    def test_force_reinstall_tolerates_unreadable_manifest(self):
        """기존 manifest 가 손상 JSON/비-dict 여도 --force 는 새 스켈레톤으로 폴백(install fail-open)."""
        for corrupt in ("{ not json", "[]", "null"):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as d:
                install.run(Args("claude", d))
                mpath = os.path.join(d, "docs", "sage_harness", ".manifest.json")
                Path(mpath).write_text(corrupt, encoding="utf-8")
                self.assertEqual(install.run(Args("claude", d, force=True)), 0)
                m = json.loads(Path(mpath).read_text(encoding="utf-8"))
                self.assertIs(m.get("installed_instance"), True)
                self.assertEqual(sorted(m["assets"].keys()),
                                 sorted(f"hooks/{hid}" for hid, _ in install._CORE_HOOKS))

    def test_non_force_reinstall_preserves_malformed_manifest_and_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            manifest_path = os.path.join(d, "docs", "sage_harness", ".manifest.json")
            malformed = b"{NOT JSON\n"
            Path(manifest_path).write_bytes(malformed)
            guide_path = os.path.join(d, "AGENT_GUIDE.md")
            guide_before = Path(guide_path).read_bytes()
            err = io.StringIO()

            with redirect_stderr(err):
                rc = install.run(Args("claude", d))

            self.assertEqual(rc, 1)
            self.assertEqual(Path(manifest_path).read_bytes(), malformed)
            self.assertEqual(Path(guide_path).read_bytes(), guide_before)
            self.assertIn("non-force install을 차단", err.getvalue())

    def test_non_force_reinstall_blocks_mapping_shaped_manifest_damage(self):
        mutations = {
            "core_renders": lambda manifest: manifest.__setitem__("core_renders", []),
            "assets": lambda manifest: manifest.__setitem__("assets", []),
            "host_history": lambda manifest: manifest.__setitem__("installed_hosts", {}),
            "asset_entry": lambda manifest: manifest["assets"].__setitem__("agents/bad", []),
            "asset_nested_type": lambda manifest: manifest["assets"].__setitem__(
                "agents/bad", {"form": "interpretive", "conformance": "PASS", "render_hash": []}),
            "asset_extra_field": lambda manifest: manifest["assets"].__setitem__(
                "agents/bad", {"form": "interpretive", "conformance": "PASS", "extra": True}),
            "receipt_extra_field": lambda manifest: manifest["core_renders"].__setitem__(
                "codex/agents/leader", {
                    "base_sha256": "0" * 64,
                    "sage_version": "1",
                    "unexpected": True,
                }),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                self.assertEqual(install.run(Args("claude", d)), 0)
                manifest_path = os.path.join(d, "docs", "sage_harness", ".manifest.json")
                manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
                mutate(manifest)
                damaged = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                Path(manifest_path).write_bytes(damaged)

                rc = install.run(Args("claude", d))

                self.assertEqual(rc, 1)
                self.assertEqual(Path(manifest_path).read_bytes(), damaged)

    def test_force_reinstall_sanitizes_mapping_shaped_manifest_damage(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            self.assertEqual(install.run(Args("codex", d, no_global_skill=True)), 0)
            manifest_path = os.path.join(d, "docs", "sage_harness", ".manifest.json")
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            manifest["assets"]["agents/bad"] = {}
            manifest["assets"]["agents/bad-nested"] = {
                "form": "interpretive", "conformance": "PASS", "render_hash": []}
            manifest["assets"]["agents/bad-extra"] = {
                "form": "interpretive", "conformance": "PASS", "extra": True}
            manifest["core_renders"]["codex/agents/leader"] = {}
            manifest["core_renders"]["codex/agents/reviewer"] = {
                "base_sha256": "0" * 64,
                "sage_version": "1",
                "unexpected": True,
            }
            manifest["installed_hosts"] = ["codex"]
            Path(manifest_path).write_text(json.dumps(manifest), encoding="utf-8")

            self.assertEqual(install.run(Args("claude", d, force=True)), 0)

            recovered = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            self.assertIsNone(install._manifest_structure_issue(recovered))
            self.assertNotIn("agents/bad", recovered["assets"])
            self.assertNotIn("agents/bad-nested", recovered["assets"])
            self.assertNotIn("agents/bad-extra", recovered["assets"])
            self.assertNotIn("codex/agents/leader", recovered["core_renders"])
            self.assertNotIn("codex/agents/reviewer", recovered["core_renders"])
            self.assertEqual(recovered["installed_hosts"], ["claude", "codex"])
            self.assertEqual(recovered["core_renders"]["claude/framework/AGENT_GUIDE"],
                             recovered["core_renders"]["codex/framework/AGENT_GUIDE"])

    def test_first_install_manifest_has_only_core_hooks(self):
        """최초 install(기존 manifest 없음)은 CORE hook 만 등록 — --force 보존 로직이 동작을 바꾸지 않는다."""
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            m = json.loads(Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).read_text(encoding="utf-8"))
            self.assertEqual(sorted(m["assets"].keys()),
                             sorted(f"hooks/{hid}" for hid, _ in install._CORE_HOOKS))

    def test_core_renders_do_not_instruct_runtime_overlay_read(self):
        """materialize 모델(P0-3): CORE 렌더는 런타임 오버레이-읽기를 지시하지 않는다.

        오버레이는 SAGE 가 관리 블록으로 물리화한다(eligible 자산만). (c)/미분류 자산이 "read your
        overlay and apply it" 프로즈를 담으면 승인-조작 오버레이가 그 경로로 새므로 전부 제거됐다.
        blocked skill 렌더는 self-overlay 미지원 경계를 안내한다."""
        import unittest.mock as mock
        forbidden = ("Before acting, read optional project overlay",
                     "Apply it before the CORE instructions",
                     "Apply it before these CORE instructions")
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            leader = Path(os.path.join(d, ".claude", "agents", "leader.md")).read_text(encoding="utf-8")
            team = Path(os.path.join(d, ".claude", "skills", "sage-team", "SKILL.md")).read_text(encoding="utf-8")
            for txt in (leader, team):
                for f in forbidden:
                    self.assertNotIn(f, txt)
            self.assertIn("Self-overlay is unsupported", team)
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                install.run(Args("codex", d))
            leader = Path(os.path.join(d, ".codex", "agents", "leader.md")).read_text(encoding="utf-8")
            team = Path(os.path.join(codex_home, "skills", "sage-team", "SKILL.md")).read_text(encoding="utf-8")
            for txt in (leader, team):
                for f in forbidden:
                    self.assertNotIn(f, txt)
            self.assertIn("Self-overlay is unsupported", team)

    def test_codex_no_global_skill_skips_core_skills(self):
        """--no-global-skill 이면 CORE skill 전역 설치도 생략(CI/샌드박스)."""
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                install.run(Args("codex", d, no_global_skill=True))
            self.assertFalse(os.path.exists(os.path.join(codex_home, "skills", "sage-plan")))
            self.assertFalse(os.path.exists(os.path.join(codex_home, "skills", "sage-review")))
            # spec 은 host 무관이라 codex host 에도 docs/ 에 배치된다
            self.assertTrue(os.path.exists(os.path.join(d, "docs", "sage_harness", "skills", "sage-plan.md")))

    def test_claude_agent_renders_create_only(self):
        """Modified anchored render is preserved but cannot be silently re-anchored."""
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            leader_path = os.path.join(d, ".claude", "agents", "leader.md")
            Path(leader_path).write_text("USER_CUSTOM_RENDER\n", encoding="utf-8")
            manifest_path = os.path.join(d, "docs", "sage_harness", ".manifest.json")
            manifest_before = Path(manifest_path).read_bytes()

            self.assertEqual(install.run(Args("claude", d)), 1)

            self.assertIn("USER_CUSTOM_RENDER", Path(leader_path).read_text(encoding="utf-8"))
            self.assertEqual(Path(manifest_path).read_bytes(), manifest_before)
            install.run(Args("claude", d, force=True))
            self.assertNotIn("USER_CUSTOM_RENDER", Path(leader_path).read_text(encoding="utf-8"))

    def test_codex_agents_md_collision_is_preserved_but_blocks_trust(self):
        # Existing project AGENTS remains untouched, but is not blessed as a CORE anchor.
        with tempfile.TemporaryDirectory() as d:
            agents = os.path.join(d, "AGENTS.md")
            Path(agents).write_text("USER_AGENTS_MARKER\n", encoding="utf-8")

            rc = install.run(Args("codex", d, no_global_skill=True))

            self.assertEqual(rc, 1)
            self.assertIn("USER_AGENTS_MARKER", Path(agents).read_text(encoding="utf-8"))
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "sage_harness", ".manifest.json")))

    def test_first_install_unanchored_conflict_is_no_write_and_inventoried(self):
        with tempfile.TemporaryDirectory() as d:
            leader = os.path.join(d, ".claude", "agents", "leader.md")
            os.makedirs(os.path.dirname(leader), exist_ok=True)
            Path(leader).write_text("UNTRUSTED_EXISTING_RENDER\n", encoding="utf-8")
            err = io.StringIO()

            with redirect_stderr(err):
                rc = install.run(Args("claude", d))

            self.assertEqual(rc, 1)
            self.assertEqual(Path(leader).read_text(encoding="utf-8"), "UNTRUSTED_EXISTING_RENDER\n")
            self.assertFalse(os.path.exists(os.path.join(d, "sage", "project-profile.yaml")))
            self.assertFalse(os.path.exists(os.path.join(d, "AGENT_GUIDE.md")))
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "sage_harness", ".manifest.json")))
            output = err.getvalue()
            source = os.path.join(install._resources.core_dir(), "framework", ".claude", "agents", "leader.md")
            expected_text = install.render_core_agent(
                Path(source).read_text(encoding="utf-8"), {"effort": "high"})
            expected_text = expected_text.rstrip("\n") + "\n"
            expected_sha = hashlib.sha256(expected_text.encode("utf-8")).hexdigest()
            actual_sha = hashlib.sha256(b"UNTRUSTED_EXISTING_RENDER\n").hexdigest()
            self.assertIn("claude/agents/leader", output)
            self.assertIn(".claude/agents/leader.md", output)
            self.assertIn("reason: 신뢰 anchor가 없는 기존 CORE render가 현재 배포 base와 다름", output)
            self.assertIn(f"expected_sha256: {expected_sha}", output)
            self.assertIn(f"actual_sha256:   {actual_sha}", output)
            self.assertIn("--force", output)

    def test_multiple_codex_conflicts_have_exact_sorted_inventory_and_no_global_write(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            custom = {
                "AGENT_GUIDE.md": "CUSTOM_AGENT_GUIDE\n",
                "AGENTS.md": "CUSTOM_AGENTS\n",
            }
            for relpath, content in custom.items():
                Path(os.path.join(d, relpath)).write_text(content, encoding="utf-8")
            before_entries = sorted(str(path.relative_to(d)) for path in Path(d).rglob("*"))
            before_bytes = {relpath: Path(os.path.join(d, relpath)).read_bytes() for relpath in custom}
            err = io.StringIO()

            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                with redirect_stderr(err):
                    rc = install.run(Args("codex", d))

            self.assertEqual(rc, 1)
            self.assertEqual(sorted(str(path.relative_to(d)) for path in Path(d).rglob("*")), before_entries)
            self.assertEqual(
                {relpath: Path(os.path.join(d, relpath)).read_bytes() for relpath in custom}, before_bytes)
            self.assertEqual(list(Path(codex_home).rglob("*")), [])

            expected_items = []
            for asset_id, relpath in (("AGENTS", "AGENTS.md"), ("AGENT_GUIDE", "AGENT_GUIDE.md")):
                source = os.path.join(install._resources.core_dir(), "framework", f"{asset_id}.md")
                expected_base = Path(source).read_text(encoding="utf-8").rstrip("\n") + "\n"
                expected_sha = hashlib.sha256(expected_base.encode("utf-8")).hexdigest()
                actual_sha = hashlib.sha256(custom[relpath].encode("utf-8")).hexdigest()
                expected_items.append(
                    f"  - [codex/framework/{asset_id}] {relpath}\n"
                    "      reason: 신뢰 anchor가 없는 기존 CORE render가 현재 배포 base와 다름\n"
                    f"      expected_sha256: {expected_sha}\n"
                    f"      actual_sha256:   {actual_sha}\n")
            expected_stderr = (
                "❌ CORE trust preflight 충돌 — 기존 렌더를 정본 anchor로 기록하지 않습니다.\n"
                + "".join(expected_items)
                + "  선택 후 다시 실행하세요:\n"
                  "    1) 기존 파일을 inventory/백업하고 프로젝트 지침을 sage/asset_overrides 또는 absorb/migration 흐름으로 이전\n"
                  "    2) 기존 내용을 버리기로 명시한 경우에만 같은 명령에 --force 추가\n"
                  "  preflight 단계에서 project 파일과 manifest anchor는 변경되지 않았습니다.\n")
            self.assertEqual(err.getvalue(), expected_stderr)

    def test_first_install_allows_unanchored_current_bundle_base(self):
        with tempfile.TemporaryDirectory() as d:
            guide = os.path.join(d, "AGENT_GUIDE.md")
            source = os.path.join(install._resources.core_dir(), "framework", "AGENT_GUIDE.md")
            Path(guide).write_text(Path(source).read_text(encoding="utf-8"), encoding="utf-8")

            self.assertEqual(install.run(Args("claude", d)), 0)

            manifest = json.loads(Path(os.path.join(d, "docs", "sage_harness", ".manifest.json"))
                                  .read_text(encoding="utf-8"))
            self.assertIn("claude/framework/AGENT_GUIDE", manifest["core_renders"])

    def test_forged_matching_anchor_cannot_bless_non_bundle_base(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            leader = os.path.join(d, ".claude", "agents", "leader.md")
            Path(leader).write_text("OLD_OR_CUSTOM_BASE\n", encoding="utf-8")
            manifest_path = os.path.join(d, "docs", "sage_harness", ".manifest.json")
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            manifest["core_renders"]["claude/agents/leader"]["base_sha256"] = hashlib.sha256(
                b"OLD_OR_CUSTOM_BASE\n").hexdigest()
            Path(manifest_path).write_text(json.dumps(manifest), encoding="utf-8")
            manifest_before = Path(manifest_path).read_bytes()

            self.assertEqual(install.run(Args("claude", d)), 1)

            self.assertEqual(Path(manifest_path).read_bytes(), manifest_before)
            self.assertEqual(Path(leader).read_text(encoding="utf-8"), "OLD_OR_CUSTOM_BASE\n")

    def test_force_overwrites_unanchored_conflict_and_records_bundle_anchor(self):
        from sage import overlay_materialize
        with tempfile.TemporaryDirectory() as d:
            leader = os.path.join(d, ".claude", "agents", "leader.md")
            os.makedirs(os.path.dirname(leader), exist_ok=True)
            Path(leader).write_text("UNTRUSTED_EXISTING_RENDER\n", encoding="utf-8")

            self.assertEqual(install.run(Args("claude", d, force=True)), 0)

            manifest = json.loads(Path(os.path.join(d, "docs", "sage_harness", ".manifest.json"))
                                  .read_text(encoding="utf-8"))
            self.assertNotIn("UNTRUSTED_EXISTING_RENDER", Path(leader).read_text(encoding="utf-8"))
            self.assertEqual(overlay_materialize.check(d, "claude", manifest["core_renders"]), [])

    def test_symlink_core_render_is_not_trusted_and_force_replaces_link_only(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            external = os.path.join(outside, "leader.md")
            Path(external).write_text("OUTSIDE_MUST_SURVIVE\n", encoding="utf-8")
            leader = os.path.join(d, ".claude", "agents", "leader.md")
            os.makedirs(os.path.dirname(leader), exist_ok=True)
            os.symlink(external, leader)

            self.assertEqual(install.run(Args("claude", d)), 1)
            self.assertTrue(os.path.islink(leader))
            self.assertEqual(Path(external).read_text(encoding="utf-8"), "OUTSIDE_MUST_SURVIVE\n")

            self.assertEqual(install.run(Args("claude", d, force=True)), 0)
            self.assertFalse(os.path.islink(leader))
            self.assertNotIn("OUTSIDE_MUST_SURVIVE", Path(leader).read_text(encoding="utf-8"))
            self.assertEqual(Path(external).read_text(encoding="utf-8"), "OUTSIDE_MUST_SURVIVE\n")

    def test_force_replaces_hard_link_without_modifying_external_inode(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            external = os.path.join(outside, "leader.md")
            Path(external).write_text("OUTSIDE_HARD_LINK_MUST_SURVIVE\n", encoding="utf-8")
            leader = os.path.join(d, ".claude", "agents", "leader.md")
            os.makedirs(os.path.dirname(leader), exist_ok=True)
            os.link(external, leader)

            self.assertEqual(install.run(Args("claude", d, force=True)), 0)

            self.assertEqual(Path(external).read_text(encoding="utf-8"), "OUTSIDE_HARD_LINK_MUST_SURVIVE\n")
            self.assertNotIn("OUTSIDE_HARD_LINK_MUST_SURVIVE", Path(leader).read_text(encoding="utf-8"))
            self.assertNotEqual(os.stat(external).st_ino, os.stat(leader).st_ino)

    def test_atomic_force_write_preserves_regular_file_mode(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            guide = os.path.join(d, "AGENT_GUIDE.md")
            os.chmod(guide, 0o640)

            self.assertEqual(install.run(Args("claude", d, force=True)), 0)

            self.assertEqual(stat.S_IMODE(os.stat(guide).st_mode), 0o640)

    def test_first_install_mid_write_failure_rolls_back_all_new_paths(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            original = install._atomic_write
            calls = {"count": 0}

            def fail_after_write(path, content, executable=False, transaction=None):
                original(path, content, executable=executable, transaction=transaction)
                calls["count"] += 1
                if calls["count"] == 5:
                    raise OSError("injected first-install write failure")

            with mock.patch.object(install, "_atomic_write", side_effect=fail_after_write):
                self.assertEqual(install.run(Args("claude", d)), 1)

            self.assertEqual(_tree_snapshot(d), {})

    def test_keyboard_interrupt_after_write_rolls_back_and_propagates(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            original = install._atomic_write
            interrupted = {"done": False}

            def interrupt_after_write(path, content, executable=False, transaction=None):
                original(path, content, executable=executable, transaction=transaction)
                if not interrupted["done"]:
                    interrupted["done"] = True
                    raise KeyboardInterrupt("injected interrupt")

            with mock.patch.object(install, "_atomic_write", side_effect=interrupt_after_write):
                with self.assertRaises(KeyboardInterrupt):
                    install.run(Args("claude", d))

            self.assertTrue(interrupted["done"])
            self.assertEqual(_tree_snapshot(d), {})

    def test_keyboard_interrupt_between_atomic_replace_and_output_record_rolls_back(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            original = install.overlay_common.write_text_lf
            interrupted = {"done": False}

            def interrupt_after_replace(path, text, mode=None):
                original(path, text, mode=mode)
                if not interrupted["done"]:
                    interrupted["done"] = True
                    raise KeyboardInterrupt("injected after atomic replace")

            with mock.patch.object(install.overlay_common, "write_text_lf",
                                   side_effect=interrupt_after_replace):
                with self.assertRaises(KeyboardInterrupt):
                    install.run(Args("claude", d))

            self.assertTrue(interrupted["done"])
            self.assertEqual(_tree_snapshot(d), {})

    def test_force_mid_write_failure_restores_exact_project_tree(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            before = _tree_snapshot(d)
            original = install._atomic_write
            calls = {"count": 0}

            def fail_after_write(path, content, executable=False, transaction=None):
                original(path, content, executable=executable, transaction=transaction)
                calls["count"] += 1
                if calls["count"] == 9:
                    raise OSError("injected force write failure")

            with mock.patch.object(install, "_atomic_write", side_effect=fail_after_write):
                self.assertEqual(install.run(Args("claude", d, force=True)), 1)

            self.assertEqual(_tree_snapshot(d), before)
            self.assertFalse(any(".sage-install-backup-" in rel for rel in _tree_snapshot(d)))

    def test_failure_after_manifest_replace_restores_previous_manifest_and_tree(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            before = _tree_snapshot(d)
            manifest_path = os.path.join(d, "docs", "sage_harness", ".manifest.json")
            original = install._atomic_write

            def fail_after_manifest(path, content, executable=False, transaction=None):
                original(path, content, executable=executable, transaction=transaction)
                if os.path.abspath(path) == os.path.abspath(manifest_path):
                    raise OSError("injected failure after manifest replace")

            with mock.patch.object(install, "_atomic_write", side_effect=fail_after_manifest):
                self.assertEqual(install.run(Args("claude", d, force=True)), 1)

            self.assertEqual(_tree_snapshot(d), before)

    def test_materialization_mid_apply_failure_restores_render_and_manifest(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            overlay = Path(d, "sage", "asset_overrides", "agents", "implementer-a.md")
            overlay.parent.mkdir(parents=True)
            overlay.write_text("Additive implementation rule.\n", encoding="utf-8")
            protected = [Path(d, ".claude", "agents", "implementer-a.md"),
                         Path(d, "docs", "sage_harness", ".manifest.json")]
            before = {str(path): path.read_bytes() for path in protected}
            original_apply = install.overlay_materialize.apply_materialization

            def fail_after_first_plan(plans, writer=None):
                changed_plan = next(plan for plan in plans if plan[1] != plan[2])
                changed = original_apply([changed_plan], writer=writer)
                self.assertTrue(changed)
                raise OSError("injected materialization apply failure")

            with mock.patch.object(install.overlay_materialize, "apply_materialization",
                                   side_effect=fail_after_first_plan):
                self.assertEqual(install.run(Args("claude", d)), 1)

            self.assertEqual({str(path): path.read_bytes() for path in protected}, before)

    def test_concurrent_render_replacement_before_second_write_is_preserved(self):
        import unittest.mock as mock

        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            overlay = Path(d, "sage", "asset_overrides", "agents", "implementer-a.md")
            overlay.parent.mkdir(parents=True)
            overlay.write_text("Additive implementation rule.\n", encoding="utf-8")
            render = Path(d, ".claude", "agents", "implementer-a.md")
            original_apply = install.overlay_materialize.apply_materialization
            replaced = {"done": False}

            def replace_before_apply(plans, writer=None):
                changed_plan = next(plan for plan in plans if plan[1] != plan[2])
                Path(changed_plan[0]).write_text("CONCURRENT_RENDER\n", encoding="utf-8")
                replaced["done"] = True
                return original_apply(plans, writer=writer)

            with mock.patch.object(install.overlay_materialize, "apply_materialization",
                                   side_effect=replace_before_apply):
                self.assertEqual(install.run(Args("claude", d, force=True)), 1)

            self.assertTrue(replaced["done"])
            self.assertEqual(render.read_text(encoding="utf-8"), "CONCURRENT_RENDER\n")
            self.assertEqual(len(list(render.parent.glob(
                ".sage-install-backup-*-implementer-a.md"))), 1)

    def test_late_failure_restores_force_pruned_legacy_skill(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            legacy = Path(d, ".claude", "skills", "pdca-start", "SKILL.md")
            legacy.parent.mkdir(parents=True)
            legacy.write_text("# CORE framework bootstrap asset\nlegacy\n", encoding="utf-8")
            before = _tree_snapshot(d)

            with mock.patch.object(install, "_manifest", side_effect=RuntimeError("late manifest failure")):
                self.assertEqual(install.run(Args("claude", d, force=True)), 1)

            self.assertEqual(_tree_snapshot(d), before)
            self.assertEqual(legacy.read_text(encoding="utf-8"),
                             "# CORE framework bootstrap asset\nlegacy\n")

    def test_late_failure_restores_codex_global_skills_and_project(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                self.assertEqual(install.run(Args("codex", d)), 0)
                global_review = Path(codex_home, "skills", "sage-review", "SKILL.md")
                global_review.write_text("USER_GLOBAL_VERSION\n", encoding="utf-8")
                project_before = _tree_snapshot(d)
                global_before = _tree_snapshot(codex_home)

                with mock.patch.object(install, "_manifest", side_effect=RuntimeError("late manifest failure")):
                    self.assertEqual(install.run(Args("codex", d, force=True)), 1)

                self.assertEqual(_tree_snapshot(d), project_before)
                self.assertEqual(_tree_snapshot(codex_home), global_before)
                self.assertEqual(global_review.read_text(encoding="utf-8"), "USER_GLOBAL_VERSION\n")

    def test_late_failure_restores_codex_project_local_skills_and_project(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("codex", d, skill_scope="project-local")), 0)
            local_review = Path(d, ".codex", "skills", "sage-review", "SKILL.md")
            local_review.write_text("USER_PROJECT_VERSION\n", encoding="utf-8")
            before = _tree_snapshot(d)

            with mock.patch.object(install, "_manifest", side_effect=RuntimeError("late manifest failure")):
                self.assertEqual(install.run(Args("codex", d, force=True,
                                                  skill_scope="project-local")), 1)

            self.assertEqual(_tree_snapshot(d), before)
            self.assertEqual(local_review.read_text(encoding="utf-8"), "USER_PROJECT_VERSION\n")

    def test_force_overlay_preflight_failure_is_no_write(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            overlay = Path(d, "sage", "asset_overrides", "agents", "reviewer.md")
            overlay.parent.mkdir(parents=True)
            overlay.write_text("unsafe reviewer\n", encoding="utf-8")
            before = _tree_snapshot(d)

            self.assertEqual(install.run(Args("claude", d, force=True)), 1)

            self.assertEqual(_tree_snapshot(d), before)

    def test_overlay_drift_after_preflight_rolls_back_install_owned_changes(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            overlay = Path(d, "sage", "asset_overrides", "agents", "implementer-a.md")
            overlay.parent.mkdir(parents=True)
            overlay.write_text("Initial additive implementation rule.\n", encoding="utf-8")
            protected = [Path(d, "AGENT_GUIDE.md"),
                         Path(d, ".claude", "agents", "implementer-a.md"),
                         Path(d, "docs", "sage_harness", ".manifest.json")]
            before = {str(path): path.read_bytes() for path in protected}
            original_plan = install.overlay_materialize.plan_materialize

            def mutate_then_plan(dest, host):
                overlay.write_text("Changed additive implementation rule.\n", encoding="utf-8")
                return original_plan(dest, host)

            with mock.patch.object(install.overlay_materialize, "plan_materialize",
                                   side_effect=mutate_then_plan):
                self.assertEqual(install.run(Args("claude", d)), 1)

            self.assertEqual({str(path): path.read_bytes() for path in protected}, before)
            self.assertEqual(overlay.read_text(encoding="utf-8"),
                             "Changed additive implementation rule.\n")

    def test_source_resource_drift_before_manifest_rolls_back_first_install(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            with mock.patch("sage.build_identity.source_core_content_hash",
                            side_effect=["sha256:" + "1" * 64,
                                         "sha256:" + "2" * 64,
                                         "sha256:" + "2" * 64]):
                self.assertEqual(install.run(Args("claude", d)), 1)

            self.assertEqual(_tree_snapshot(d), {})

    def test_install_owned_output_drift_before_commit_rolls_back_force(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            before = _tree_snapshot(d)
            original_copy = install._copy_file
            changed = {"done": False}

            def mutate_one_installed_spec(src, dst, force, created, skipped, transaction=None):
                result = original_copy(src, dst, force, created, skipped, transaction=transaction)
                if (not changed["done"] and dst.endswith(
                        os.path.join("docs", "sage_harness", "hooks", "capture-declared-risk.md"))):
                    Path(dst).write_text("CONCURRENT_OUTPUT_DRIFT\n", encoding="utf-8")
                    changed["done"] = True
                return result

            with mock.patch.object(install, "_copy_file", side_effect=mutate_one_installed_spec):
                self.assertEqual(install.run(Args("claude", d, force=True)), 1)

            self.assertTrue(changed["done"])
            target = Path(d, "docs", "sage_harness", "hooks", "capture-declared-risk.md")
            self.assertEqual(target.read_text(encoding="utf-8"), "CONCURRENT_OUTPUT_DRIFT\n")
            backups = list(target.parent.glob(".sage-install-backup-*-capture-declared-risk.md"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), before[
                "docs/sage_harness/hooks/capture-declared-risk.md"][2])

    def test_commit_happens_before_success_reporting(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            args = Args("codex", d, no_global_skill=True)
            observed = []

            def inspect_commit(*_args, **_kwargs):
                observed.append(args._sage_install_transaction.committed)

            with mock.patch.object(install, "_print_codex_skill_summary",
                                   side_effect=inspect_commit):
                self.assertEqual(install.run(args), 0)

            self.assertEqual(observed, [True])

    def test_materialized_anchor_binding_rejects_changed_snapshot(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            original_plan = install.overlay_materialize.plan_materialize

            def tampered_plan(dest, host):
                Path(os.path.join(dest, ".claude", "agents", "leader.md")).write_text(
                    "CHANGED_AFTER_PREFLIGHT\n", encoding="utf-8")
                return original_plan(dest, host)

            with mock.patch.object(install.overlay_materialize, "plan_materialize", side_effect=tampered_plan):
                rc = install.run(Args("claude", d))

            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "sage_harness", ".manifest.json")))

    def test_parent_symlink_is_blocked_even_with_force(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            os.symlink(outside, os.path.join(d, ".claude"))

            self.assertEqual(install.run(Args("claude", d)), 1)
            self.assertEqual(os.listdir(outside), [])
            self.assertFalse(os.path.exists(os.path.join(d, "sage", "project-profile.yaml")))

            self.assertEqual(install.run(Args("claude", d, force=True)), 1)
            self.assertEqual(os.listdir(outside), [])
            self.assertFalse(os.path.exists(os.path.join(d, "docs", "sage_harness", ".manifest.json")))

    def test_non_render_docs_symlink_ancestor_is_never_followed(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            os.symlink(outside, os.path.join(d, "docs"))

            self.assertEqual(install.run(Args("claude", d, force=True)), 1)

            self.assertEqual(os.listdir(outside), [])
            self.assertTrue(os.path.islink(os.path.join(d, "docs")))
            self.assertFalse(os.path.exists(os.path.join(d, "sage", "project-profile.yaml")))

    def test_codex_global_skill_symlink_ancestor_is_never_followed(self):
        import unittest.mock as mock
        with (tempfile.TemporaryDirectory() as d,
              tempfile.TemporaryDirectory() as codex_home,
              tempfile.TemporaryDirectory() as outside):
            skill_dir = Path(codex_home, "skills", "sage-init")
            skill_dir.parent.mkdir(parents=True)
            skill_dir.symlink_to(outside, target_is_directory=True)

            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                self.assertEqual(install.run(Args("codex", d, force=True)), 1)

            self.assertEqual(os.listdir(outside), [])
            self.assertTrue(skill_dir.is_symlink())
            self.assertEqual(_tree_snapshot(d), {})

    def test_malformed_json_profile_fails_before_install_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            profile = Path(d, "sage", "project-profile.json")
            profile.parent.mkdir()
            profile.write_text("{malformed", encoding="utf-8")
            before = _tree_snapshot(d)

            self.assertEqual(install.run(Args("claude", d, force=True)), 1)

            self.assertEqual(_tree_snapshot(d), before)

    def test_generated_json_profile_can_coexist_with_yaml_on_force_reinstall(self):
        import yaml
        from sage.profile_compile import materialize_profile

        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            yaml_path = Path(d, "sage", "project-profile.yaml")
            json_path = Path(d, "sage", "project-profile.json")
            raw_profile = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            json_path.write_text(
                json.dumps(materialize_profile(raw_profile), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")

            self.assertEqual(install.run(Args("claude", d, force=True)), 0)
            self.assertTrue(json_path.is_file())

    def test_stale_generated_json_profile_blocks_before_install_mutation(self):
        import yaml
        from sage.profile_compile import materialize_profile

        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            yaml_path = Path(d, "sage", "project-profile.yaml")
            json_path = Path(d, "sage", "project-profile.json")
            raw_profile = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            compiled = materialize_profile(raw_profile)
            compiled["stale_test_marker"] = True
            json_path.write_text(
                json.dumps(compiled, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            before = _tree_snapshot(d)

            self.assertEqual(install.run(Args("claude", d, force=True)), 1)

            self.assertEqual(_tree_snapshot(d), before)

    def test_type_coerced_generated_json_profile_blocks_before_install_mutation(self):
        import yaml
        from sage.profile_compile import materialize_profile

        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            yaml_path = Path(d, "sage", "project-profile.yaml")
            json_path = Path(d, "sage", "project-profile.json")
            raw_profile = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            compiled = materialize_profile(raw_profile)
            compiled["team"]["core"]["leader"]["enabled"] = 1
            json_path.write_text(
                json.dumps(compiled, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            before = _tree_snapshot(d)

            self.assertEqual(install.run(Args("claude", d, force=True)), 1)

            self.assertEqual(_tree_snapshot(d), before)

    def test_manifest_symlink_is_not_read_and_force_replaces_link_only(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            external = Path(outside, "manifest.json")
            external_body = json.dumps({
                "sage_version": "external",
                "host_runtime": "claude",
                "assets": {
                    "agents/external": {
                        "form": "declarative",
                        "conformance": "PASS",
                    },
                },
            })
            external.write_text(external_body, encoding="utf-8")
            manifest = Path(d, "docs", "sage_harness", ".manifest.json")
            manifest.parent.mkdir(parents=True)
            manifest.symlink_to(external)

            self.assertEqual(install.run(Args("claude", d)), 1)
            self.assertTrue(manifest.is_symlink())
            self.assertEqual(external.read_text(encoding="utf-8"), external_body)

            self.assertEqual(install.run(Args("claude", d, force=True)), 0)
            self.assertFalse(manifest.is_symlink())
            installed = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertNotIn("agents/external", installed["assets"])
            self.assertEqual(external.read_text(encoding="utf-8"), external_body)

    def test_new_atomic_write_does_not_query_or_mutate_process_umask(self):
        import unittest.mock as mock

        with tempfile.TemporaryDirectory() as d:
            target = Path(d, "new.md")
            with mock.patch("sage.commands.install.os.umask",
                            side_effect=AssertionError("process umask must not be queried")):
                install._atomic_write(target, "content\n")

            self.assertEqual(target.read_text(encoding="utf-8"), "content\n")

    def test_symlink_profile_is_rejected_without_reading_referent(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            external = Path(outside, "profile.yaml")
            external.write_text("runtime: {host: claude}\n", encoding="utf-8")
            profile = Path(d, "sage", "project-profile.yaml")
            profile.parent.mkdir()
            profile.symlink_to(external)
            before = _tree_snapshot(d)

            self.assertEqual(install.run(Args("claude", d)), 1)

            self.assertEqual(_tree_snapshot(d), before)
            self.assertEqual(external.read_text(encoding="utf-8"),
                             "runtime: {host: claude}\n")

    def test_fifo_core_render_is_rejected_without_reading(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO is not supported on this platform")
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            leader = os.path.join(d, ".claude", "agents", "leader.md")
            os.remove(leader)
            os.mkfifo(leader)
            manifest_path = os.path.join(d, "docs", "sage_harness", ".manifest.json")
            manifest_before = Path(manifest_path).read_bytes()

            self.assertEqual(install.run(Args("claude", d)), 1)

            self.assertTrue(stat.S_ISFIFO(os.lstat(leader).st_mode))
            self.assertEqual(Path(manifest_path).read_bytes(), manifest_before)

    def test_non_utf8_core_render_is_rejected_and_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            leader = os.path.join(d, ".claude", "agents", "leader.md")
            Path(leader).write_bytes(b"\xff\xfeUNTRUSTED")
            manifest_path = os.path.join(d, "docs", "sage_harness", ".manifest.json")
            manifest_before = Path(manifest_path).read_bytes()
            err = io.StringIO()

            with redirect_stderr(err):
                rc = install.run(Args("claude", d))

            self.assertEqual(rc, 1)
            self.assertEqual(Path(leader).read_bytes(), b"\xff\xfeUNTRUSTED")
            self.assertEqual(Path(manifest_path).read_bytes(), manifest_before)
            self.assertIn("오버레이/렌더 읽기 실패", err.getvalue())

    def test_malformed_marker_core_render_is_rejected_and_preserved(self):
        from sage import overlay_common
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            guide = os.path.join(d, "AGENT_GUIDE.md")
            malformed = f"CURRENT BASE\n{overlay_common.MARKER_START}\nUNTERMINATED\n"
            Path(guide).write_text(malformed, encoding="utf-8")
            manifest_path = os.path.join(d, "docs", "sage_harness", ".manifest.json")
            manifest_before = Path(manifest_path).read_bytes()
            err = io.StringIO()

            with redirect_stderr(err):
                rc = install.run(Args("claude", d))

            self.assertEqual(rc, 1)
            self.assertEqual(Path(guide).read_text(encoding="utf-8"), malformed)
            self.assertEqual(Path(manifest_path).read_bytes(), manifest_before)
            self.assertIn("blocked block 정리 실패", err.getvalue())
            self.assertIn("오버레이 마커 짝 불일치", err.getvalue())

    def test_non_force_install_cleans_blocked_block_before_overlay_failure(self):
        from sage import overlay_common
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            reviewer = Path(d, ".claude", "agents", "reviewer.md")
            reviewer.write_text(
                reviewer.read_text(encoding="utf-8")
                + "\n" + overlay_common.compose_block("unsafe reviewer", "agents", "reviewer"),
                encoding="utf-8")
            overlay = Path(d, "sage", "asset_overrides", "agents", "reviewer.md")
            overlay.parent.mkdir(parents=True, exist_ok=True)
            overlay.write_text("unsafe reviewer\n", encoding="utf-8")
            manifest = Path(d, "docs", "sage_harness", ".manifest.json")
            manifest_before = manifest.read_bytes()

            self.assertEqual(install.run(Args("claude", d)), 1)

            self.assertNotIn(overlay_common.MARKER_START, reviewer.read_text(encoding="utf-8"))
            self.assertEqual(manifest.read_bytes(), manifest_before)

    def test_non_force_install_cleans_blocked_block_before_profile_failures(self):
        from sage import overlay_common
        invalid_profiles = (
            "team: { core: {\n",
            "runtime: {host: claude}\nteam: {core: {leaderr: {runtime: {model: opus}}}}\n",
        )
        for body in invalid_profiles:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as d:
                self.assertEqual(install.run(Args("claude", d)), 0)
                reviewer = Path(d, ".claude", "agents", "reviewer.md")
                reviewer.write_text(
                    reviewer.read_text(encoding="utf-8")
                    + "\n" + overlay_common.compose_block("unsafe reviewer", "agents", "reviewer"),
                    encoding="utf-8")
                profile = Path(d, "sage", "project-profile.yaml")
                profile.write_text(body, encoding="utf-8")
                manifest = Path(d, "docs", "sage_harness", ".manifest.json")
                manifest_before = manifest.read_bytes()

                self.assertEqual(install.run(Args("claude", d)), 1)

                self.assertNotIn(overlay_common.MARKER_START, reviewer.read_text(encoding="utf-8"))
                self.assertEqual(profile.read_text(encoding="utf-8"), body)
                self.assertEqual(manifest.read_bytes(), manifest_before)

    def test_non_force_install_cleans_safe_sibling_when_other_marker_is_malformed(self):
        from sage import overlay_common
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(install.run(Args("claude", d)), 0)
            leader = Path(d, ".claude", "agents", "leader.md")
            reviewer = Path(d, ".claude", "agents", "reviewer.md")
            leader.write_text(
                leader.read_text(encoding="utf-8")
                + "\n" + overlay_common.compose_block("unsafe leader", "agents", "leader"),
                encoding="utf-8")
            reviewer.write_text(
                reviewer.read_text(encoding="utf-8")
                + "\n" + overlay_common.compose_block("unsafe one", "agents", "reviewer")
                + overlay_common.compose_block("unsafe two", "agents", "reviewer"),
                encoding="utf-8")
            manifest = Path(d, "docs", "sage_harness", ".manifest.json")
            manifest_before = manifest.read_bytes()

            self.assertEqual(install.run(Args("claude", d)), 1)

            self.assertNotIn(overlay_common.MARKER_START, leader.read_text(encoding="utf-8"))
            self.assertIn(overlay_common.MARKER_START, reviewer.read_text(encoding="utf-8"))
            self.assertEqual(manifest.read_bytes(), manifest_before)

    def test_profile_rendered_agent_is_valid_unanchored_base(self):
        with tempfile.TemporaryDirectory() as d:
            profile = {"runtime": {"host": "claude"},
                       "team": {"core": {"leader": {"runtime": {"effort": "low"}}}}}
            os.makedirs(os.path.join(d, "sage"), exist_ok=True)
            import yaml
            Path(os.path.join(d, "sage", "project-profile.yaml")).write_text(
                yaml.safe_dump(profile), encoding="utf-8")
            source = os.path.join(install._resources.core_dir(), "framework", ".claude", "agents", "leader.md")
            rendered = install.render_core_agent(Path(source).read_text(encoding="utf-8"), {"effort": "low"})
            leader = os.path.join(d, ".claude", "agents", "leader.md")
            os.makedirs(os.path.dirname(leader), exist_ok=True)
            Path(leader).write_text(rendered, encoding="utf-8")

            self.assertEqual(install.run(Args("claude", d)), 0)
            self.assertIn("effort: low", Path(leader).read_text(encoding="utf-8"))

    def test_codex_host_installs_global_skill(self):
        # Explicit global scope installs $sage-init under $CODEX_HOME/skills.
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                install.run(Args("codex", d))
            skill = os.path.join(codex_home, "skills", "sage-init", "SKILL.md")
            self.assertTrue(os.path.exists(skill))
            self.assertIn("sage-init", Path(skill).read_text(encoding="utf-8"))

    def test_codex_install_requires_explicit_normal_skill_scope(self):
        with tempfile.TemporaryDirectory() as d:
            args = Args("codex", d)
            args.skill_scope = None
            before = _tree_snapshot(d)

            self.assertEqual(install.run(args), 2)
            self.assertEqual(_tree_snapshot(d), before)

    def test_codex_global_scope_acquires_shared_skills_root_lock(self):
        with (tempfile.TemporaryDirectory() as dest,
              tempfile.TemporaryDirectory() as codex_home,
              mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}),
              mock.patch.object(install, "_run_locked") as run_locked):
            global_lock = install._tx.DestinationLock(install._codex_skills_root())
            global_lock.acquire()
            try:
                err = io.StringIO()
                with redirect_stderr(err):
                    rc = install.run(Args("codex", dest, skill_scope="global"))
            finally:
                global_lock.release()

            self.assertEqual(rc, 1)
            self.assertIn("lock", err.getvalue())
            run_locked.assert_not_called()
            self.assertEqual(_tree_snapshot(dest), {})

    def test_codex_project_local_scope_installs_and_receipts_core_skills(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                rc = install.run(Args("codex", d, skill_scope="project-local"))

            self.assertEqual(rc, 0)
            for skill_id in install.core_skill_ids():
                self.assertTrue(Path(d, ".codex", "skills", skill_id, "SKILL.md").is_file())
                self.assertFalse(Path(codex_home, "skills", skill_id, "SKILL.md").exists())
            manifest = json.loads(Path(d, "docs", "sage_harness", ".manifest.json").read_text())
            self.assertEqual(manifest["core_skill_receipts"]["codex"]["scope"], "project-local")
            self.assertEqual(manifest["core_skill_receipts"]["codex"]["sage_version"], install.__version__)
            onboarding = Path(d, "docs", "agent", "sage-onboarding.md").read_text()
            self.assertIn("Selected Codex CORE skill scope: `project-local`", onboarding)
            self.assertIn("does not install the `sage` or `sage-hook` executable", onboarding)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_codex_project_local_scope_rejects_symlink_escape_before_write(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            os.symlink(outside, Path(d, ".codex"))
            before = _tree_snapshot(d)

            rc = install.run(Args("codex", d, skill_scope="project-local"))

            self.assertEqual(rc, 1)
            self.assertEqual(_tree_snapshot(d), before)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_codex_global_scope_records_receipt_and_onboarding(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                rc = install.run(Args("codex", d, skill_scope="global"))

            self.assertEqual(rc, 0)
            manifest = json.loads(Path(d, "docs", "sage_harness", ".manifest.json").read_text())
            self.assertEqual(manifest["core_skill_receipts"]["codex"]["scope"], "global")
            onboarding = Path(d, "docs", "agent", "sage-onboarding.md").read_text()
            self.assertIn("Selected Codex CORE skill scope: `global`", onboarding)
            self.assertIn("each teammate", onboarding)

    def test_codex_scope_switch_updates_receipt_without_deleting_other_copy(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                self.assertEqual(install.run(Args("codex", d, skill_scope="global")), 0)
                self.assertEqual(install.run(Args("codex", d, force=True,
                                                  skill_scope="project-local")), 0)

            manifest = json.loads(Path(d, "docs", "sage_harness", ".manifest.json").read_text())
            self.assertEqual(manifest["core_skill_receipts"]["codex"]["scope"], "project-local")
            self.assertTrue(Path(d, ".codex", "skills", "sage-init", "SKILL.md").is_file())
            self.assertTrue(Path(codex_home, "skills", "sage-init", "SKILL.md").is_file())

    def test_codex_global_skill_create_only_then_force(self):
        # create-only: 기존 전역 스킬 보존. --force 면 갱신.
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            skill = os.path.join(codex_home, "skills", "sage-init", "SKILL.md")
            os.makedirs(os.path.dirname(skill))
            Path(skill).write_text("USER_SKILL_MARKER\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                install.run(Args("codex", d))                 # create-only → 보존
                self.assertIn("USER_SKILL_MARKER", Path(skill).read_text(encoding="utf-8"))
                install.run(Args("codex", d, force=True))      # --force → 갱신
                self.assertNotIn("USER_SKILL_MARKER", Path(skill).read_text(encoding="utf-8"))

    def test_claude_host_no_global_codex_skill(self):
        # claude host 는 codex 전역 스킬을 건드리지 않는다
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                install.run(Args("claude", d))
            self.assertFalse(os.path.exists(os.path.join(codex_home, "skills", "sage-init")))

    def test_no_global_skill_optout(self):
        # codex R1-P1: --no-global-skill 이면 전역 스킬 미설치(AGENTS.md 라우터만)
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                install.run(Args("codex", d, no_global_skill=True))
            self.assertFalse(os.path.exists(os.path.join(codex_home, "skills", "sage-init")))
            self.assertTrue(os.path.exists(os.path.join(d, "AGENTS.md")))   # 라우터는 여전히 배치

    def test_global_skill_stale_detection(self):
        # codex R1-P1: 기존 전역 스킬이 번들과 다르면 stale, force 없이는 보존
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as codex_home:
            src = os.path.join(codex_home, "src_SKILL.md")
            Path(src).write_text("CANON\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                dst = os.path.join(install._codex_skills_root(), "sage-init", "SKILL.md")
                os.makedirs(os.path.dirname(dst))
                Path(dst).write_text("OLD_DIFFERENT\n", encoding="utf-8")
                status, _ = install._install_codex_global_skill(src, force=False)
                self.assertEqual(status, "stale")
                self.assertEqual(Path(dst).read_text(encoding="utf-8"), "OLD_DIFFERENT\n")  # 보존
                status2, _ = install._install_codex_global_skill(src, force=True)
                self.assertEqual(status2, "installed")
                self.assertEqual(Path(dst).read_text(encoding="utf-8"), "CANON\n")  # 갱신

    def test_global_skill_write_error_nonfatal(self):
        # codex R1-P0: 전역 쓰기 실패는 install 을 깨지 않고 error 상태 반환
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as codex_home:
            src = os.path.join(codex_home, "src_SKILL.md")
            Path(src).write_text("CANON\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}), \
                 mock.patch("os.makedirs", side_effect=OSError("read-only")):
                status, info = install._install_codex_global_skill(src, force=False)
            self.assertEqual(status, "error")

    def test_global_skill_non_utf8_existing_nonfatal(self):
        # codex R2-P1: 기존 전역 스킬이 비-UTF-8 이면 UnicodeError → 비치명적 error
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as codex_home:
            src = os.path.join(codex_home, "src_SKILL.md")
            Path(src).write_text("CANON\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                dst = os.path.join(install._codex_skills_root(), "sage-init", "SKILL.md")
                os.makedirs(os.path.dirname(dst))
                with open(dst, "wb") as f:
                    f.write(b"\xff\xfe\x00invalid")   # 비-UTF-8
                status, _ = install._install_codex_global_skill(src, force=False)
            self.assertEqual(status, "error")

    def test_independence_no_domain_tokens(self):
        """제약 #2: 설치된 CORE 트리에 특정 스택/도메인 토큰 0 (정본/spec/agent 중립).

        CORE 는 어느 소비 프로젝트에도 종속되면 안 되므로, 특정 스택/프레임워크 마커가
        설치 트리에 새어들면 실패시킨다(회귀 가드)."""
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            # 설치 트리 전체에서 특정 스택/도메인 토큰 검색(테스트/캐시 제외 — 애초에 배치 안 함)
            hits = subprocess.run(
                ["grep", "-rniE", r"springboot|webchat|nodejs|kurento|webrtc|electron", d],
                capture_output=True, text=True).stdout.strip()
            self.assertEqual(hits, "", f"도메인 토큰 누출:\n{hits}")

    def test_unstamped_validate_stale(self):
        """Codex P2-6: install 직후(generate 전) hook 은 미스탬프 → validate STALE(exit 3), healthy 로 안 보임."""
        from sage.commands import validate

        class VArgs:
            kind = "hook"; check = True; id = None; schema = False

            def __init__(self, root):
                self.root = root
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            rc = validate.run(VArgs(d))
            self.assertEqual(rc, 3)  # STALE — generate --write 로 스탬프 필요

    def test_idempotent_skip(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            # 재실행: profile 내용 안 바뀜(skip)
            before = Path(os.path.join(d, "sage", "project-profile.yaml")).read_text(encoding="utf-8")
            install.run(Args("codex", d))  # host 바꿔도 skip 이라 안 덮어씀
            after = Path(os.path.join(d, "sage", "project-profile.yaml")).read_text(encoding="utf-8")
            self.assertEqual(before, after)

    def test_manifest_stamps_installed_instance(self):
        # 부트스트랩 게이트 다중 신호(codex R2-P0): install 이 manifest.installed_instance 를 스탬프.
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            m = json.loads(Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).read_text(encoding="utf-8"))
            self.assertIs(m.get("installed_instance"), True)

    def test_force_restamps_legacy_manifest(self):
        # codex R3-P2: 레거시 manifest(installed_instance 없음)는 install --force 로 재스탬프되어 복구.
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            mp = os.path.join(d, "docs", "sage_harness", ".manifest.json")
            m = json.loads(Path(mp).read_text(encoding="utf-8"))
            del m["installed_instance"]   # 레거시 상태 모사
            Path(mp).write_text(json.dumps(m), encoding="utf-8")
            install.run(Args("claude", d, force=True))
            m2 = json.loads(Path(mp).read_text(encoding="utf-8"))
            self.assertIs(m2.get("installed_instance"), True)

    def test_force_preserves_profile_updates_engine(self):
        # F5: --force 는 엔진 자산을 갱신하되 인스턴스 profile(커스터마이즈 SSOT)은 보존한다.
        # (이전 거동: force 가 profile 까지 덮어써 클린 엔진 업그레이드 불가 → 수정)
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            prof_path = os.path.join(d, "sage", "project-profile.yaml")
            guide_path = os.path.join(d, "AGENT_GUIDE.md")
            # 사용자 커스터마이즈. profile 은 매핑이어야 한다 — 스칼라면 install 이 fail-closed 로 거부한다.
            Path(prof_path).write_text("project: { name: CUSTOM_PROFILE_MARKER }\n", encoding="utf-8")
            Path(guide_path).write_text("STALE_ENGINE\n", encoding="utf-8")           # 엔진 파일 훼손
            self.assertEqual(install.run(Args("claude", d, force=True)), 0)
            self.assertIn("CUSTOM_PROFILE_MARKER", Path(prof_path).read_text(encoding="utf-8"))     # profile 보존
            self.assertNotIn("STALE_ENGINE", Path(guide_path).read_text(encoding="utf-8"))          # 엔진은 force 갱신


_AGENT_SRC = "---\nname: leader\ndescription: \"x\"\n---\n\n# leader\n"


class TestAgentRender(unittest.TestCase):
    def test_no_overrides_is_byte_identical(self):
        # 미설정이면 소스 그대로 → 기존 설치가 drift 로 뜨지 않는다.
        self.assertEqual(install.render_core_agent(_AGENT_SRC, {}), _AGENT_SRC)

    def test_injects_into_frontmatter_before_close(self):
        out = install.render_core_agent(_AGENT_SRC, {"model": "opus", "effort": "xhigh"})
        head = out.split("\n---\n", 1)[0]
        self.assertIn("model: opus", head)
        self.assertIn("effort: xhigh", head)
        self.assertIn("name: leader", head)      # 기존 키 보존
        self.assertTrue(out.endswith("# leader\n"))   # 본문 보존

    def test_reinjection_is_idempotent(self):
        once = install.render_core_agent(_AGENT_SRC, {"model": "opus"})
        twice = install.render_core_agent(once, {"model": "opus"})
        self.assertEqual(once, twice)
        self.assertEqual(1, once.count("model: opus"))

    def test_no_frontmatter_left_alone(self):
        self.assertEqual(install.render_core_agent("# plain\n", {"model": "opus"}), "# plain\n")

    def test_effort_defaults_to_high_model_does_not_default(self):
        # effort 는 미설정이어도 high. model 은 기본값 없음(host CLI 가 고른 모델 유지).
        for aid in install.core_agent_ids():
            self.assertEqual(install.agent_frontmatter_overrides({}, aid), {"effort": "high"})
        self.assertNotIn("model", install.agent_frontmatter_overrides({}, "reviewer"))

    def test_overrides_read_from_role_runtime(self):
        prof = {"team": {"core": {"qa": {"enabled": True, "runtime": {"model": "sonnet", "effort": "low"}}}}}
        self.assertEqual(install.agent_frontmatter_overrides(prof, "qa"), {"model": "sonnet", "effort": "low"})
        self.assertEqual(install.agent_frontmatter_overrides(prof, "leader"), {"effort": "high"})

    def test_legacy_role_level_model_is_never_promoted(self):
        # 옛 템플릿은 reviewer/qa 에 `model: sonnet` 을 박아뒀다(죽은 필드). 이걸 승격하면 업그레이드만으로
        # Phase 05 리뷰어가 조용히 다운그레이드된다 → runtime 아래가 아니면 무시해야 한다.
        legacy = {"team": {"core": {"reviewer": {"enabled": True, "model": "sonnet"}}}}
        self.assertEqual(install.agent_frontmatter_overrides(legacy, "reviewer"), {"effort": "high"})

    def test_non_core_agent_gets_nothing(self):
        self.assertEqual(install.agent_frontmatter_overrides({}, "not-a-core-agent"), {})

    def test_overrides_tolerate_malformed_profile(self):
        for bad in (None, "oops", {"team": "oops"}, {"team": {"core": "oops"}},
                    {"team": {"core": {"qa": "oops"}}}, {"team": {"core": {"qa": {"runtime": "oops"}}}}):
            self.assertEqual(install.agent_frontmatter_overrides(bad, "qa"), {"effort": "high"})

    def test_frontmatter_issue_rejects_bad_values(self):
        self.assertIsNone(install.agent_frontmatter_issue({"model": "opus", "effort": "max"}))
        self.assertIsNone(install.agent_frontmatter_issue({"model": "claude-opus-4-8", "effort": 8}))
        self.assertIsNone(install.agent_frontmatter_issue({}))
        self.assertIsNotNone(install.agent_frontmatter_issue({"model": "opuss"}))
        self.assertIsNotNone(install.agent_frontmatter_issue({"effort": "ultra"}))
        self.assertIsNotNone(install.agent_frontmatter_issue({"effort": True}))   # bool 은 int 서브클래스
        self.assertIsNotNone(install.agent_frontmatter_issue({"effort": 0}))

    def test_model_id_cannot_smuggle_extra_frontmatter_keys(self):
        # prefix 검사만 하면 `claude-x\nname: replaced` 가 통과해 frontmatter 에 키를 주입한다.
        for evil in ("claude-x\nname: replaced", "claude-x\n---\nbody", "claude-", "claude-x y", " claude-x"):
            self.assertIsNotNone(install.agent_frontmatter_issue({"model": evil}), f"{evil!r} 가 통과함")

    def test_quoted_and_spaced_keys_are_replaced_not_duplicated(self):
        # `"model": x` / `model : x` 도 정상 YAML 최상위 키다. 못 알아보면 제거를 놓쳐 중복 키가 된다.
        for line in ('"model": sonnet', "model : sonnet", "'model': sonnet"):
            out = install.render_core_agent(f"---\nname: x\n{line}\n---\nbody\n", {"model": "opus"})
            model_lines = [ln for ln in out.split("\n") if ln.split(":", 1)[0].strip().strip("'\"") == "model"]
            self.assertEqual(["model: opus"], model_lines, f"{line!r} → {out!r}")

    def test_boundary_allows_trailing_space_but_not_indent(self):
        self.assertTrue(install._is_fm_boundary("--- "))
        self.assertFalse(install._is_fm_boundary("  ---"))
        self.assertFalse(install._is_fm_boundary("----"))

    def test_shipped_core_renders_are_parseable(self):
        # 렌더가 BOM/CRLF/비-frontmatter 면 주입이 조용히 no-op 된다 → 배송 자산은 계약을 지켜야 한다.
        for aid in install.core_agent_ids():
            text = Path(install._core_agent_source(aid)).read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), f"{aid}: frontmatter 시작 아님")
            self.assertNotIn("\r", text, f"{aid}: CRLF")
            self.assertIn("effort: high", install.render_core_agent(text, {"effort": "high"}))

    def test_install_aborts_before_writing_invalid_frontmatter(self):
        # `sage validate` 를 건너뛰고 install --force 만 돌려도 잘못된 값이 배포되면 안 된다.
        # 오타 키/역할은 주입 직전 overrides 로는 기본값으로 축소돼 보이지 않는다 → 원본 구조를 봐야 한다.
        for bad in ("leader: { runtime: { model: opuss } }",
                    "leader: { runtime: { modle: opus } }",     # 키 오타
                    "leaderr: { runtime: { model: opus } }",    # 역할 오타
                    "leader: { runtime: oops }"):
            with tempfile.TemporaryDirectory() as d:
                install.run(Args("claude", d))
                leader = Path(os.path.join(d, ".claude", "agents", "leader.md"))
                before = leader.read_text(encoding="utf-8")
                Path(os.path.join(d, "sage", "project-profile.yaml")).write_text(
                    f"team: {{ core: {{ {bad} }} }}\n", encoding="utf-8")
                self.assertEqual(install.run(Args("claude", d, force=True)), 1, bad)
                self.assertEqual(leader.read_text(encoding="utf-8"), before, bad)   # 아무것도 안 씀

    def test_team_runtime_issues_never_raises(self):
        # totality: 어떤 profile 입력에도 크래시 금지. 숫자 키는 sorted(mixed) 에서 TypeError 였다.
        for prof in (None, "oops", {"team": "oops"}, {"team": {"core": "oops"}},
                     {"team": {"core": {"leader": "oops"}}},
                     {"team": {"core": {1: {"runtime": {"model": "opus"}}}}},
                     {"team": {"core": {"leader": {"runtime": {1: "x", "model": "opus"}}}}},
                     {"team": {"core": {"leader": {"runtime": {"model": ["a"]}}}}}):
            install.team_runtime_issues(prof)   # 예외 없이 반환하면 통과

    def test_non_mapping_role_spec_is_fail_not_silent_default(self):
        # 조용히 넘기면 그 역할 설정이 통째로 무시된 채 기본 렌더가 배포된다.
        fails = [m for s, m in install.team_runtime_issues({"team": {"core": {"leader": "oops"}}}) if s == "FAIL"]
        self.assertTrue(fails)

    def test_role_level_key_typo_is_fail(self):
        # `runtim:` 은 아무도 안 읽어 설정한 model 이 조용히 사라지고 기본 렌더가 나간다.
        prof = {"team": {"core": {"leader": {"runtim": {"model": "opus"}}}}}
        fails = [m for s, m in install.team_runtime_issues(prof) if s == "FAIL"]
        self.assertTrue(fails)
        self.assertIn("runtim", fails[0])

    def test_legitimate_role_keys_pass(self):
        prof = {"team": {"core": {"reviewer": {"enabled": True, "owns": ["x"], "runtime": {"effort": "max"},
                                               "cross_model": {"capability": "from_options.cross_model"}}}}}
        self.assertEqual([], [m for s, m in install.team_runtime_issues(prof) if s == "FAIL"])

    def test_install_and_validate_share_one_rule(self):
        # 두 곳이 다른 규칙을 쓰면 validate 를 건너뛴 install 이 오타를 조용히 통과시킨다.
        import sage.profile_validate as pv
        for prof in ({"team": {"core": {"reviewer": {"runtime": {"modle": "opus"}}}}},
                     {"team": {"core": {"reviewerr": {"runtime": {"model": "opus"}}}}},
                     {"team": {"core": {"reviewer": {"runtime": {"model": "opuss"}}}}}):
            self.assertTrue([m for s, m in install.team_runtime_issues(prof) if s == "FAIL"], prof)
            self.assertEqual(pv.severity_of(pv.validate_profile(prof, REPO)), "FAIL", prof)

    def test_corrupt_profile_aborts_install_not_silently_default_rendered(self):
        # 파싱 실패를 {} 로 삼키면 설정이 조용히 무시된 채 기본 렌더가 배포된다.
        for body in ("team: { core: {\n", "- just\n- a list\n", "false\n", "0\n", "[]\n", '""\n'):
            with tempfile.TemporaryDirectory() as d:
                install.run(Args("claude", d))
                leader = Path(os.path.join(d, ".claude", "agents", "leader.md"))
                before = leader.read_text(encoding="utf-8")
                Path(os.path.join(d, "sage", "project-profile.yaml")).write_text(body, encoding="utf-8")
                self.assertEqual(install.run(Args("claude", d, force=True)), 1, body)
                self.assertEqual(leader.read_text(encoding="utf-8"), before, body)

    def test_empty_profile_file_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            Path(os.path.join(d, "sage", "project-profile.yaml")).write_text("", encoding="utf-8")
            self.assertEqual(install.run(Args("claude", d, force=True)), 0)

    def test_codex_host_install_still_rejects_typo_role(self):
        # codex 는 주입하지 않지만, 오타 역할은 어느 host 에서든 설정을 죽인다.
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("codex", d, no_global_skill=True))
            Path(os.path.join(d, "sage", "project-profile.yaml")).write_text(
                "runtime: { host: codex }\nteam: { core: { leaderr: { runtime: { model: opus } } } }\n",
                encoding="utf-8")
            self.assertEqual(install.run(Args("codex", d, force=True, no_global_skill=True)), 1)

    def test_block_scalar_frontmatter_survives(self):
        # 줄 단위 파싱이 블록 스칼라 본문의 `  model:` 을 지우거나 들여쓴 `---` 를 종료로 오인하면 안 됨.
        src = "---\nname: x\ndescription: |\n  model: 이건 본문이다\n  ---\n  effort: 이것도 본문\n---\nbody\n"
        out = install.render_core_agent(src, {"effort": "high"})
        self.assertIn("  model: 이건 본문이다", out)
        self.assertIn("  effort: 이것도 본문", out)
        self.assertIn("\neffort: high\n", out)
        self.assertTrue(out.endswith("body\n"))

    def test_drift_status_compares_against_render_not_source(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "leader.md"); dst = os.path.join(d, "installed.md")
            Path(src).write_text(_AGENT_SRC, encoding="utf-8")
            ov = {"model": "opus"}
            Path(dst).write_text(install.render_core_agent(_AGENT_SRC, ov), encoding="utf-8")
            # 주입된 설치본은 소스와 다르지만, 같은 overrides 기준으로는 ok 여야 한다(영구 stale 방지).
            self.assertEqual(install.core_render_status(src, dst, ov)[0], "ok")
            self.assertEqual(install.core_render_status(src, dst)[0], "stale")   # overrides 없으면 drift

    def test_install_renders_agent_from_existing_profile(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            leader = Path(os.path.join(d, ".claude", "agents", "leader.md"))
            first = leader.read_text(encoding="utf-8")
            self.assertIn("effort: high", first)     # 템플릿 profile 미설정 → 기본 effort
            self.assertNotIn("model:", first)        # model 은 기본값 없음
            prof = os.path.join(d, "sage", "project-profile.yaml")
            Path(prof).write_text(
                "runtime: { host: claude }\n"
                "team: { core: { leader: { enabled: true, runtime: { model: opus, effort: max } } } }\n",
                encoding="utf-8")
            install.run(Args("claude", d, force=True))   # sage-init 후 재배포 경로
            text = leader.read_text(encoding="utf-8")
            self.assertIn("model: opus", text)
            self.assertIn("effort: max", text)
            self.assertNotIn("effort: high", text)   # 기본값이 남아 중복되지 않는다

    def test_codex_host_agents_get_no_frontmatter_injection(self):
        # .codex/agents/*.md 는 model/effort 해석 기전이 없다 → 주입하면 죽은 필드.
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("codex", d, no_global_skill=True))
            text = Path(os.path.join(d, ".codex", "agents", "leader.md")).read_text(encoding="utf-8")
            self.assertNotIn("effort:", text)
            self.assertNotIn("model:", text)

    def test_force_preserves_declared_project_local_verify_script(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            profile = os.path.join(d, "sage", "project-profile.yaml")
            Path(profile).write_text(
                "project: {name: test}\nverification:\n  project_local_script: scripts/verify-changes.sh\n",
                encoding="utf-8")
            script = os.path.join(d, "scripts", "verify-changes.sh")
            Path(script).write_text("#!/usr/bin/env bash\necho project-local\n", encoding="utf-8")
            self.assertEqual(install.run(Args("claude", d, force=True)), 0)
            self.assertIn("project-local", Path(script).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
