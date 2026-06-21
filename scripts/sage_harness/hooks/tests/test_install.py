#!/usr/bin/env python3
"""sage install 검증 (중 등급 — 부트스트랩).

self-contained: 임시 dest 에 install 후 산출물/치환/멱등 확인.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import install  # noqa: E402


class Args:
    def __init__(self, host, dest, prefix="sage", force=False, no_global_skill=False):
        self.host = host; self.dest = dest; self.prefix = prefix; self.force = force
        self.no_global_skill = no_global_skill


class TestInstall(unittest.TestCase):
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
                # CORE skill spec 2종 → docs/sage_harness/skills/
                "docs/sage_harness/skills/pdca-start.md",
                "docs/sage_harness/skills/sage-review.md",
                # CORE skill 렌더 (Claude Code .claude/skills/ 자동발견)
                ".claude/skills/pdca-start/SKILL.md",
                ".claude/skills/sage-review/SKILL.md",
            ):
                self.assertTrue(os.path.exists(os.path.join(d, rel)), rel)
            # tests/ 는 배치하지 않음(런타임 불필요)
            self.assertFalse(os.path.exists(os.path.join(d, "scripts/sage_harness/hooks/tests")))

    def test_host_prefix_substitution(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("codex", d, prefix="myapp"))
            prof = Path(os.path.join(d, "sage", "project-profile.yaml")).read_text(encoding="utf-8")
            self.assertIn("host: codex", prof)
            self.assertIn('prefix: "myapp"', prof)
            # codex host → CODEX.md wrapper (CLAUDE.md 아님)
            self.assertTrue(os.path.exists(os.path.join(d, "CODEX.md")))
            self.assertFalse(os.path.exists(os.path.join(d, "CLAUDE.md")))
            m = json.loads(Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).read_text(encoding="utf-8"))
            self.assertEqual(m["host_runtime"], "codex")
            # manifest 는 CORE hook 6종 등록(빈 assets 아님) → generate 가 동작 가능
            self.assertEqual(len([k for k in m["assets"] if k.startswith("hooks/")]), 6)
            self.assertEqual(m["assets"]["hooks/pre-implementation-gate"]["form"], "core_adapter")
            self.assertEqual(m["assets"]["hooks/generated-artifact-write-guard"]["form"], "native")

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
        """Gap-2 mutation teeth: CORE skill spec 2종이 docs/sage_harness/skills/ 에 배치된다."""
        _CORE_SKILLS = ["pdca-start", "sage-review"]
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
        _CORE_SKILLS = ["pdca-start", "sage-review"]
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            for sid in _CORE_SKILLS:
                path = os.path.join(d, ".claude", "skills", sid, "SKILL.md")
                self.assertTrue(os.path.exists(path), f".claude/skills/{sid}/SKILL.md 미배치")
                body = Path(path).read_text(encoding="utf-8")
                self.assertIn(f"name: {sid}", body, f"{sid} SKILL.md name 누락")

    def test_codex_host_installs_core_skills_globally(self):
        """Gap-2 P1.2: codex host 는 CORE skill 렌더를 $CODEX_HOME/skills 전역에 설치한다.

        codex 는 repo-스코프 스킬을 자동발견하지 않으므로(sage-init 과 동일 비대칭),
        CORE skill 도 전역 설치되어야 codex 프로젝트에서 호출 가능하다."""
        import unittest.mock as mock
        _CORE_SKILLS = ["pdca-start", "sage-review"]
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                install.run(Args("codex", d))
            for sid in _CORE_SKILLS:
                path = os.path.join(codex_home, "skills", sid, "SKILL.md")
                self.assertTrue(os.path.exists(path), f"전역 codex CORE skill {sid} 미설치")
                self.assertIn(f"name: {sid}", Path(path).read_text(encoding="utf-8"))
            # codex host 는 repo .claude/skills/ 에 CORE skill 렌더를 두지 않는다
            self.assertFalse(os.path.exists(os.path.join(d, ".claude", "skills", "pdca-start")))

    def test_codex_no_global_skill_skips_core_skills(self):
        """--no-global-skill 이면 CORE skill 전역 설치도 생략(CI/샌드박스)."""
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                install.run(Args("codex", d, no_global_skill=True))
            self.assertFalse(os.path.exists(os.path.join(codex_home, "skills", "pdca-start")))
            self.assertFalse(os.path.exists(os.path.join(codex_home, "skills", "sage-review")))
            # spec 은 host 무관이라 codex host 에도 docs/ 에 배치된다
            self.assertTrue(os.path.exists(os.path.join(d, "docs", "sage_harness", "skills", "pdca-start.md")))

    def test_claude_agent_renders_create_only(self):
        """Gap-1 create-only 안전성: 사용자 커스터마이즈 렌더는 --force 없이 보존된다."""
        with tempfile.TemporaryDirectory() as d:
            install.run(Args("claude", d))
            leader_path = os.path.join(d, ".claude", "agents", "leader.md")
            # 사용자가 렌더를 수정했다고 가정
            Path(leader_path).write_text("USER_CUSTOM_RENDER\n", encoding="utf-8")
            install.run(Args("claude", d))  # --force 없이 재설치
            self.assertIn("USER_CUSTOM_RENDER", Path(leader_path).read_text(encoding="utf-8"))
            install.run(Args("claude", d, force=True))  # --force 는 갱신
            self.assertNotIn("USER_CUSTOM_RENDER", Path(leader_path).read_text(encoding="utf-8"))

    def test_codex_agents_md_collision_preserved(self):
        # 기존 AGENTS.md 는 create-only 로 보존(codex 협의 R4: 자동 덮어쓰기 금지)
        with tempfile.TemporaryDirectory() as d:
            agents = os.path.join(d, "AGENTS.md")
            Path(agents).write_text("USER_AGENTS_MARKER\n", encoding="utf-8")
            install.run(Args("codex", d))
            self.assertIn("USER_AGENTS_MARKER", Path(agents).read_text(encoding="utf-8"))

    def test_codex_host_installs_global_skill(self):
        # codex 는 repo-스코프 스킬 자동발견 불가 → $sage-init 을 $CODEX_HOME/skills 전역 설치
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                install.run(Args("codex", d))
            skill = os.path.join(codex_home, "skills", "sage-init", "SKILL.md")
            self.assertTrue(os.path.exists(skill))
            self.assertIn("sage-init", Path(skill).read_text(encoding="utf-8"))

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
            Path(prof_path).write_text("CUSTOM_PROFILE_MARKER\n", encoding="utf-8")   # 사용자 커스터마이즈
            Path(guide_path).write_text("STALE_ENGINE\n", encoding="utf-8")           # 엔진 파일 훼손
            install.run(Args("claude", d, force=True))
            self.assertIn("CUSTOM_PROFILE_MARKER", Path(prof_path).read_text(encoding="utf-8"))     # profile 보존
            self.assertNotIn("STALE_ENGINE", Path(guide_path).read_text(encoding="utf-8"))          # 엔진은 force 갱신


if __name__ == "__main__":
    unittest.main(verbosity=2)
