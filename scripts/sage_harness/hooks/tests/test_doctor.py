#!/usr/bin/env python3
"""sage doctor 검증 (중 등급 — profile 로드 실패 원인 구분, Codex P1).

parse_error(설정 무시됨) = FAIL(exit 1) / missing_file·missing_pyyaml = WARN/INFO(exit 0).
"""
import io
import os
import sys
import tempfile
import unittest
import json
from contextlib import redirect_stdout
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import doctor, install  # noqa: E402

try:
    import yaml  # noqa: F401
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


class Args:
    def __init__(self, profile=None):
        self.profile = profile


def run_doctor(profile_path):
    out = io.StringIO()
    with redirect_stdout(out):
        rc = doctor.run(Args(profile=profile_path))
    return rc, out.getvalue()


class TestDoctor(unittest.TestCase):
    def test_load_profile_missing_file(self):
        self.assertEqual(doctor._load_profile("/no/such/profile.yaml")[1], "missing_file")

    def test_missing_file_exit0(self):
        rc, out = run_doctor("/no/such/profile.yaml")
        self.assertEqual(rc, 0)
        self.assertIn("profile 없음", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요(parse 단계 도달)")
    def test_parse_error_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.yaml")
            Path(p).write_text("risk:\n  globs: [unclosed\n")   # 잘못된 flow sequence
            rc, out = run_doctor(p)
            self.assertEqual(rc, 1)            # 설정이 깨졌으면 FAIL
            self.assertIn("파싱 오류", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_ok_profile_exit0(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.yaml")
            Path(p).write_text("runtime: { host: codex }\noptions: { cross_model: false }\n")
            rc, out = run_doctor(p)
            self.assertEqual(rc, 0)
            self.assertEqual(doctor._load_profile(p)[1], "ok")

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_local_profile_controls_effective_cross_model(self):
        with tempfile.TemporaryDirectory() as root:
            sage_dir = Path(root, "sage")
            sage_dir.mkdir()
            profile = sage_dir / "project-profile.yaml"
            profile.write_text(
                "runtime: { host: codex }\n"
                "options: { cross_model: false }\n"
                "cross_model: { policy: recommended }\n",
                encoding="utf-8",
            )
            Path(sage_dir, "project-profile.local.yaml").write_text(
                "cross_model: { enabled: false }\n",
                encoding="utf-8",
            )

            rc, out = run_doctor(str(profile))

            self.assertEqual(0, rc, out)
            self.assertIn("local profile", out)
            self.assertIn("cross_model : False", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_required_policy_local_opt_out_fails_doctor(self):
        with tempfile.TemporaryDirectory() as root:
            sage_dir = Path(root, "sage")
            sage_dir.mkdir()
            profile = sage_dir / "project-profile.yaml"
            profile.write_text(
                "runtime: { host: codex }\n"
                "cross_model: { policy: required }\n",
                encoding="utf-8",
            )
            Path(sage_dir, "project-profile.local.yaml").write_text(
                "cross_model: { enabled: false }\n",
                encoding="utf-8",
            )

            rc, out = run_doctor(str(profile))

            self.assertEqual(1, rc, out)
            self.assertIn("완화할 수 없음", out)

    def test_env_section_reports_sage_hook(self):
        # W2b: hook 등록이 sage-hook 콘솔 스크립트에 의존 → doctor 실행환경이 이를 진단해야.
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.yaml")
            Path(p).write_text("runtime: { host: codex }\noptions: { cross_model: false }\n")
            _, out = run_doctor(p)
            self.assertIn("## 실행 환경", out)
            self.assertIn("sage-hook", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_model_routing_reports_confirmed_and_unverified_status(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as ch:
            Path(ch, "models_cache.json").write_text(json.dumps({
                "fetched_at": "2026-07-17T00:00:00Z",
                "models": [{"slug": "gpt-picked", "visibility": "list"}],
            }), encoding="utf-8")
            p = os.path.join(d, "p.yaml")
            Path(p).write_text(
                "runtime: { installed_hosts: [claude, codex], active_host: codex }\n"
                "options: { cross_model: true }\n"
                "components:\n  - id: backend\n    runtime_models: { codex: gpt-picked }\n"
                "cross_model: { reviewer: { host: claude, model: opus } }\n",
                encoding="utf-8")
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                rc, out = run_doctor(p)
        self.assertEqual(rc, 0)
        self.assertIn("component:backend : codex/gpt-picked → confirmed", out)
        self.assertIn("cross-reviewer : claude/opus → syntax-only/account-unverified", out)

    def test_overlay_drift_hint_syncs_before_strict_validate(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(install.run(_InstallArgs("claude", root)), 0)
            overlay = Path(root, "sage", "asset_overrides", "agents", "implementer-a.md")
            overlay.parent.mkdir(parents=True, exist_ok=True)
            overlay.write_text("Prefer null-safe implementation.\n", encoding="utf-8")

            _, out = run_doctor(os.path.join(root, "sage", "project-profile.yaml"))

            self.assertIn("`sage sync-overlays` → `sage validate --strict`", out)

    def _codex_skill_project(self, root):
        import json
        os.makedirs(os.path.join(root, "sage"))
        os.makedirs(os.path.join(root, "docs", "sage_harness"))
        os.makedirs(os.path.join(root, ".codex", "skills", "sk1"))
        Path(os.path.join(root, ".codex", "skills", "sk1", "SKILL.md")).write_text("---\nname: sk1\n---\nbody\n")
        Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).write_text(
            json.dumps({"assets": {"skills/sk1": {"form": "interpretive"}}}))

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_codex_skill_deployment_warns_when_missing(self):
        # Part C P1: codex-host + manifest skill + repo 정본 있으나 전역 미배포 → WARN
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as ch:
            self._codex_skill_project(root)
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "px" }\nruntime: { host: codex }\n')
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                rc, out = run_doctor(prof)
            self.assertIn("sk1", out)
            self.assertIn("전역 미배포", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_codex_skill_deployment_ok_when_deployed(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as ch:
            self._codex_skill_project(root)
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "px" }\nruntime: { host: codex }\n')
            gdir = os.path.join(ch, "skills", "px-sk1"); os.makedirs(gdir)
            Path(os.path.join(gdir, "SKILL.md")).write_text("---\nname: sk1\n---\nbody\n")   # 정본과 동일
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                rc, out = run_doctor(prof)
            self.assertIn("전역 배포 최신", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_codex_skill_deployment_empty_prefix_blocks(self):
        # Part C P2: 빈 prefix → bare-id 점검 금지(generate fail-closed 와 일관), prefix 설정 안내
        with tempfile.TemporaryDirectory() as root:
            self._codex_skill_project(root)
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "" }\nruntime: { host: codex }\n')
            rc, out = run_doctor(prof)
            self.assertIn("project.prefix 미설정", out)
            self.assertNotIn("전역 미배포", out)   # bare-id 점검 안 함

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_claude_host_skips_codex_deployment_check(self):
        # Part C P1: claude-host 는 codex skill 배포 점검을 건너뜀(거짓 WARN 금지)
        with tempfile.TemporaryDirectory() as root:
            self._codex_skill_project(root)
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "px" }\nruntime: { host: claude }\n')
            rc, out = run_doctor(prof)
            self.assertNotIn("codex skill 전역 배포", out)
            self.assertNotIn("codex CORE skill 전역 설치 상태", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_codex_core_skill_drift_warns_when_stale(self):
        # 5차 root cause: manifest 추적 skill 이 아니라 hand-shipped CORE skill($sage-init 등)이 stale 이어도
        # doctor 가 직접 보여줘야 한다.
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as ch:
            os.makedirs(os.path.join(root, "sage"))
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "px" }\nruntime: { host: codex }\n')
            stale = os.path.join(ch, "skills", "sage-init")
            os.makedirs(stale)
            Path(os.path.join(stale, "SKILL.md")).write_text("OLD_STALE\n", encoding="utf-8")
            manifest_dir = Path(root, "docs", "sage_harness")
            manifest_dir.mkdir(parents=True)
            Path(manifest_dir, ".manifest.json").write_text(json.dumps({
                "host_runtime": "codex",
                "installed_hosts": ["codex"],
                "core_skill_receipts": {
                    "codex": {"scope": "global", "sage_version": install.__version__},
                },
            }), encoding="utf-8")
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                rc, out = run_doctor(prof)
            self.assertEqual(rc, 0)
            self.assertIn("CORE 렌더 drift 점검", out)
            self.assertIn("sage-init", out)
            self.assertIn("stale", out)
            self.assertIn("sage install --host codex --skill-scope global --force", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_claude_host_core_render_drift_detected(self):
        # claude host 도 CORE 렌더 drift 를 점검한다(이전엔 codex 스킬만 → 사각지대였음).
        # install(claude) 로 렌더 배치 후 한 스킬 렌더를 변조하면 stale, 한 에이전트 렌더를 지우면 missing.
        with tempfile.TemporaryDirectory() as root:
            class IArgs:
                host = "claude"; dest = root; prefix = "px"; force = True; no_global_skill = False
            os.makedirs(os.path.join(root, "sage"))
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "px" }\nruntime: { host: claude }\n')
            install.run(IArgs())
            # 스킬 렌더 변조 → stale
            Path(os.path.join(root, ".claude", "skills", "sage-cycle", "SKILL.md")).write_text(
                "LOCAL_EDIT\n", encoding="utf-8")
            # 에이전트 렌더 제거 → missing
            os.remove(os.path.join(root, ".claude", "agents", "leader.md"))
            rc, out = run_doctor(prof)
            self.assertEqual(rc, 0)
            self.assertIn("CORE 렌더 drift 점검", out)
            self.assertIn("[skill] sage-cycle", out)
            self.assertIn("stale", out)
            self.assertIn("[agent] leader", out)
            self.assertIn("sage install --host claude --force", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_codex_core_skill_doctor_agrees_with_install_status(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as ch:
            class IArgs:
                host = "codex"; dest = root; prefix = "px"; force = True; no_global_skill = False
                skill_scope = "global"
            os.makedirs(os.path.join(root, "sage"))
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "px" }\nruntime: { host: codex }\n')
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                install.run(IArgs())
                for sid in install.core_skill_ids():
                    self.assertEqual(install.codex_core_skill_status(sid)[0], "ok", sid)
                rc, out = run_doctor(prof)
            self.assertEqual(rc, 0)
            for sid in install.core_skill_ids():
                self.assertIn(f"{sid}: 최신", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_codex_duplicate_scope_reports_ambiguous_precedence_and_cleanup(self):
        import shutil
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as ch:
            class IArgs:
                host = "codex"; dest = root; prefix = "px"; force = True; no_global_skill = False
                skill_scope = "global"
            os.makedirs(os.path.join(root, "sage"))
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "px" }\nruntime: { host: codex }\n')
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                self.assertEqual(install.run(IArgs()), 0)
                for sid in install.core_skill_ids():
                    source = Path(ch, "skills", sid, "SKILL.md")
                    duplicate = Path(root, ".codex", "skills", sid, "SKILL.md")
                    duplicate.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, duplicate)
                Path(root, ".codex", "skills", "sage-init", "SKILL.md").write_text(
                    "stale duplicate\n", encoding="utf-8")
                rc, out = run_doctor(prof)

            self.assertEqual(rc, 0)
            self.assertIn("intended scope: global", out)
            self.assertIn("$sage-init: duplicate; precedence=ambiguous", out)
            self.assertIn("version/content conflict", out)
            self.assertIn(str(Path(root, ".codex", "skills", "sage-init")), out)
            self.assertIn("자동 삭제하지 않습니다", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_doctor_checks_every_manifest_installed_host(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as ch:
            os.makedirs(os.path.join(root, "sage"))
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text(
                'project: { name: "t", prefix: "px" }\nruntime: { host: codex }\n',
                encoding="utf-8",
            )

            class ClaudeArgs:
                host = "claude"; dest = root; prefix = "px"; force = True; no_global_skill = False

            class CodexArgs:
                host = "codex"; dest = root; prefix = "px"; force = True; no_global_skill = False
                skill_scope = "global"

            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                install.run(ClaudeArgs())
                install.run(CodexArgs())
                rc, out = run_doctor(prof)

            self.assertEqual(rc, 0)
            self.assertIn("installed_hosts=['claude', 'codex']", out)
            self.assertIn("[claude] discovery surface", out)
            self.assertIn("[codex] discovery surface", out)

    def test_codex_core_skill_status_rejects_unsafe_id(self):
        status, info = install.codex_core_skill_status("../escape")
        self.assertEqual(status, "error")
        self.assertIn("unsafe", info)

    def test_codex_core_skill_status_missing(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as ch:
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                status, dst = install.codex_core_skill_status("sage-init")
            self.assertEqual(status, "missing")
            self.assertIn("sage-init", dst)

    def test_codex_core_skill_status_source_missing(self):
        import unittest.mock as mock
        with mock.patch("sage.commands.install._core_skill_source", return_value="/no/such/SKILL.md"):
            status, dst = install.codex_core_skill_status("sage-init")
        self.assertEqual(status, "source_missing")
        self.assertIsNone(dst)


class TestProfileDiscovery(unittest.TestCase):
    """맨손 `sage doctor` 가 프로젝트 profile 을 못 찾으면 로스터 에이전트 drift 점검을 통째로 건너뛴다
    (프로젝트 루트를 profile 경로에서 파생하므로). 그러면 stale 안내가 사실상 동작하지 않는다."""

    def test_finds_profile_in_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sage", "project-profile.yaml")
            os.makedirs(os.path.dirname(p)); Path(p).write_text("runtime: { host: claude }\n", encoding="utf-8")
            self.assertEqual(os.path.realpath(doctor._discover_profile(d)), os.path.realpath(p))

    def test_walks_up_from_subdirectory(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sage", "project-profile.yaml")
            os.makedirs(os.path.dirname(p)); Path(p).write_text("runtime: { host: claude }\n", encoding="utf-8")
            deep = os.path.join(d, "a", "b", "c"); os.makedirs(deep)
            self.assertEqual(os.path.realpath(doctor._discover_profile(deep)), os.path.realpath(p))

    def test_returns_none_outside_a_project(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(doctor._discover_profile(os.path.join(d)))

    def test_stops_at_repo_boundary(self):
        # 상위 저장소의 profile 을 집어 남의 프로젝트를 진단하면 안 된다.
        with tempfile.TemporaryDirectory() as d:
            outer = os.path.join(d, "sage"); os.makedirs(outer)
            Path(os.path.join(outer, "project-profile.yaml")).write_text("runtime: {}\n", encoding="utf-8")
            inner = os.path.join(d, "vendor", "nested"); os.makedirs(inner)
            Path(os.path.join(inner, ".git")).write_text("gitdir: x\n", encoding="utf-8")
            self.assertIsNone(doctor._discover_profile(inner))
            # 경계가 없으면 상위 profile 을 집는다(중첩 repo 가 아닐 때의 정상 동작).
            plain = os.path.join(d, "vendor", "plain"); os.makedirs(plain)
            self.assertIsNotNone(doctor._discover_profile(plain))

    def test_bare_repo_is_a_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sage"))
            Path(os.path.join(d, "sage", "project-profile.yaml")).write_text("runtime: {}\n", encoding="utf-8")
            bare = os.path.join(d, "mirror.git")
            for n in ("objects", "refs"):
                os.makedirs(os.path.join(bare, n))
            Path(os.path.join(bare, "HEAD")).write_text("ref: refs/heads/main\n", encoding="utf-8")
            self.assertIsNone(doctor._discover_profile(bare))

    def test_invalid_agent_runtime_is_error_not_stale(self):
        # ❌ 를 stale 로 세면 doctor 가 rc=0 으로 `install --force` 를 권하는데 install 은 거부한다.
        with tempfile.TemporaryDirectory() as d:
            install.run(_InstallArgs("claude", d))
            Path(os.path.join(d, "sage", "project-profile.yaml")).write_text(
                "runtime: { host: claude }\n"
                "team: { core: { reviewer: { runtime: { model: opuss } } } }\n", encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                rc = doctor.run(Args(profile=os.path.join(d, "sage", "project-profile.yaml")))
            v = out.getvalue()
            self.assertEqual(rc, 1)
            self.assertIn("profile 오류", v)
            self.assertIn("opuss", v)
            self.assertNotIn("갱신 필요", v)   # --force 를 권하지 않는다

    def test_invalid_suppresses_force_advice_even_with_real_stale(self):
        # invalid + 진짜 stale 이 섞여도 실패할 `install --force` 를 권하면 안 된다.
        with tempfile.TemporaryDirectory() as d:
            install.run(_InstallArgs("claude", d))
            Path(os.path.join(d, ".claude", "skills", "sage-review", "SKILL.md")).write_text(
                "STALE\n", encoding="utf-8")   # 실제 drift 유발
            Path(os.path.join(d, "sage", "project-profile.yaml")).write_text(
                "runtime: { host: claude }\n"
                "team: { core: { reviewer: { runtime: { modle: opus } } } }\n", encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                rc = doctor.run(Args(profile=os.path.join(d, "sage", "project-profile.yaml")))
            v = out.getvalue()
            self.assertEqual(rc, 1)
            self.assertIn("modle", v)
            self.assertNotIn("갱신 필요", v)
            self.assertIn("다시 진단", v)

    def test_bare_doctor_checks_roster_agents_in_installed_project(self):
        with tempfile.TemporaryDirectory() as d:
            install.run(_InstallArgs("claude", d))
            cwd = os.getcwd()
            try:
                os.chdir(d)
                out = io.StringIO()
                with redirect_stdout(out):
                    doctor.run(Args(profile=None))   # --profile 없이
            finally:
                os.chdir(cwd)
            v = out.getvalue()
            self.assertIn("[agent] reviewer", v)          # 점검을 건너뛰지 않음
            self.assertNotIn("로스터 에이전트 점검 생략", v)


class _InstallArgs:
    def __init__(self, host, dest, prefix="sage", force=False, no_global_skill=True):
        self.host = host; self.dest = dest; self.prefix = prefix; self.force = force
        self.no_global_skill = no_global_skill
        self.skill_scope = None


class TestRetroGateVisibility(unittest.TestCase):
    """doctor 가 retro_audit 의 미완료 사이클(retro --check 누락)을 표면화하는지(9-C v1 유저 스코프)."""

    def _project(self, d):
        os.makedirs(os.path.join(d, "sage"), exist_ok=True)
        Path(os.path.join(d, "sage", "project-profile.yaml")).write_text(
            "runtime: { host: claude }\npdca: { retro: { report_gate_enforce: enforce } }\n", encoding="utf-8")
        return os.path.join(d, "sage", "project-profile.yaml")

    def test_missing_run_surfaced(self):
        with tempfile.TemporaryDirectory() as d:
            prof = self._project(d)
            sys.path.insert(0, os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime"))
            import retro_audit
            retro_audit.record_missing(d, "rl-xyz")
            _, out = run_doctor(prof)
            self.assertIn("Loop C (retro gate)", out)
            self.assertIn("rl-xyz", out)
            self.assertIn("retro --check 미실행", out)

    def test_checked_run_not_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            prof = self._project(d)
            sys.path.insert(0, os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime"))
            import retro_audit
            retro_audit.record_check(d, "rl-ok", "note.md", "본문")
            _, out = run_doctor(prof)
            self.assertIn("미완료(retro --check 누락) 사이클 없음", out)

    def test_audit_unavailable_not_reported_as_none(self):
        # codex 구현리뷰 3R P1: 감사파일이 파일이 아니면(디렉토리) '미완료 없음' 으로 오보하지 않는다.
        with tempfile.TemporaryDirectory() as d:
            prof = self._project(d)
            os.makedirs(os.path.join(d, ".sage", "retro_audit.jsonl"), exist_ok=True)
            _, out = run_doctor(prof)
            self.assertIn("신뢰할 수 없음", out)
            self.assertNotIn("미완료(retro --check 누락) 사이클 없음", out)


class TestAcceptancePolicyVisibility(unittest.TestCase):
    def _profile(self, root, acceptance):
        os.makedirs(os.path.join(root, "sage"), exist_ok=True)
        path = os.path.join(root, "sage", "project-profile.yaml")
        Path(path).write_text("runtime: { host: claude }\nverification:\n  acceptance:\n" + acceptance,
                              encoding="utf-8")
        return path

    def test_legacy_policy_prints_migration(self):
        with tempfile.TemporaryDirectory() as root:
            profile = self._profile(root, "    enabled: true\n    report_gate_enforce: advisory\n")
            _, out = run_doctor(profile)
            self.assertIn("legacy report_gate_enforce=advisory", out)
            self.assertIn("report_gate_by_risk", out)

    def test_risk_policy_and_waiver_visibility(self):
        with tempfile.TemporaryDirectory() as root:
            profile = self._profile(root, "    enabled: true\n"
                                    "    report_gate_by_risk: { L2: advisory, L3: enforce }\n"
                                    "    waiver: { enabled: true }\n")
            _, out = run_doctor(profile)
            self.assertIn("L2=advisory L3=enforce", out)
            self.assertIn("waiver  : enabled", out)
            self.assertIn("active  : 0", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
