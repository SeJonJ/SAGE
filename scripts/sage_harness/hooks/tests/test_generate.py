#!/usr/bin/env python3
"""sage generate 검증 (상 등급 — hook 등록 산출물 + manifest 스탬프, Codex 2R).

self-contained: 임시 SAGE 루트(hook spec frontmatter + adapter stub + manifest)로 등록 생성 확인.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import generate as gen  # noqa: E402
from sage import __version__  # noqa: E402

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
    os.makedirs(os.path.join(d, "sage_harness", "hooks", "adapters", "claude"), exist_ok=True)
    os.makedirs(os.path.join(d, "sage_harness", "hooks", "adapters", "codex"), exist_ok=True)
    os.makedirs(os.path.join(d, "sage_harness", "hooks", "runtime"), exist_ok=True)
    os.makedirs(os.path.join(d, "sage_harness", "hooks", "policies"), exist_ok=True)
    strategies = os.path.join(d, "sage_harness", "hooks", "strategies", "pre_implementation_gate")
    os.makedirs(strategies, exist_ok=True)
    Path(os.path.join(d, "docs", "sage_harness", "hooks", "aaa-hook.md")).write_text(SPEC_A)
    Path(os.path.join(d, "docs", "sage_harness", "hooks", "bbb-hook.md")).write_text(SPEC_B)
    for fn in ("run_hook.py", "hook_runtime.py", "loop_audit.py", "retro_audit.py",
               "acceptance_waiver.py", "override_audit.py", "messages.py", "recovery.py", "cycle_state.py",
               "document_language.py", "prose_language.py", "compact_reentry.py",
               "io_claude.py", "io_codex.py"):
        Path(os.path.join(d, "sage_harness", "hooks", "runtime", fn)).write_text(f"# {fn}\n")
    shutil.copyfile(
        os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime", "checklist_contract.py"),
        os.path.join(d, "sage_harness", "hooks", "runtime", "checklist_contract.py"),
    )
    Path(os.path.join(d, "sage_harness", "hooks", "cycle_binding.py")).write_text(
        "# cycle_binding.py\n")
    Path(os.path.join(d, "sage_harness", "hooks", "risk_declaration.py")).write_text(
        "# risk_declaration.py\n")
    Path(os.path.join(d, "sage_harness", "hooks", "path_risk.py")).write_text(
        "# path_risk.py\n")
    Path(os.path.join(d, "sage_harness", "hooks", "policies", "retro_gate.py")).write_text("# retro_gate\n")
    Path(os.path.join(d, "sage_harness", "hooks", "policies", "writeback_depth_gate.py")).write_text("# writeback_depth_gate\n")
    for fn in ("claude_grep_first.py", "codex_feature_signal.py", "cycle_domain_review.py"):
        Path(os.path.join(strategies, fn)).write_text(f"# {fn}\n")
    Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).write_text(json.dumps({
        "sage_version": "0.1.0", "host_runtime": "claude", "assets": {
            "hooks/aaa-hook": {"form": "core_adapter", "spec_hash": "x", "render_hash": {"claude": "x"}, "conformance": "PASS"},
            "hooks/bbb-hook": {"form": "core_adapter", "spec_hash": "x", "render_hash": {"claude": "x"}, "conformance": "PASS"},
        }}))
    if with_adapter:
        for hid in ("aaa-hook", "bbb-hook"):
            for rt in ("claude", "codex"):
                Path(os.path.join(d, "sage_harness", "hooks", "adapters", rt, f"{hid}.sh")).write_text("#!/bin/bash\n")


class Args:
    def __init__(self, **kw):
        self.kind = "hook"; self.id = None; self.write = False
        self.target = "claude"; self.dest = "."; self.root = None
        self.deploy_codex = False
        self.__dict__.update(kw)


def _render_md(name):
    return (f"---\nname: {name}\n"
            f"description: \"Test {name} asset. Invoke for {name}.\"\n---\n"
            f"# {name}\n## procedure\n1. step one\n2. step two\n## Role\nDoes {name} work.\n")


def make_interpretive_root(d):
    """agent/skill 추출+등록 테스트용 최소 루트 — manifest + AGENT_GUIDE."""
    os.makedirs(os.path.join(d, "docs", "sage_harness", "skills"), exist_ok=True)
    os.makedirs(os.path.join(d, "docs", "sage_harness", "agents"), exist_ok=True)
    Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).write_text(json.dumps({
        "sage_version": "0.1.0", "host_runtime": "claude", "assets": {}}))
    Path(os.path.join(d, "AGENT_GUIDE.md")).write_text("# guide\n")


class TestGenerateInterpretive(unittest.TestCase):
    """Gap-3: generate --kind agent/skill extract+register (Part B) + codex 전역화(Part C)."""

    def test_agent_extract_register_both_renders(self):
        with tempfile.TemporaryDirectory() as d:
            make_interpretive_root(d)
            os.makedirs(os.path.join(d, ".claude", "agents"))
            os.makedirs(os.path.join(d, ".codex", "agents"))
            Path(os.path.join(d, ".claude", "agents", "payment.md")).write_text(_render_md("payment"))
            Path(os.path.join(d, ".codex", "agents", "payment.md")).write_text(_render_md("payment"))
            rc = gen._gen_interpretive(Args(kind="agent", id="payment", write=True, dest=d, root=d), d, "agent")
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(d, "docs", "sage_harness", "agents", "payment.md")))
            self.assertTrue(os.path.exists(os.path.join(d, "docs", "sage_harness", "agents", "payment.claims.yml")))
            m = json.loads(Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).read_text())
            self.assertIn("agents/payment", m["assets"])
            rh = m["assets"]["agents/payment"]["render_hash"]
            self.assertIn("claude", rh); self.assertIn("codex", rh)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요(profile.components 판독)")
    def test_owned_paths_extracted_from_profile_components(self):
        # Part B P1: profile.components 에서 component_path_globs 파생 → owned_paths claim 추출(config=None 약화 방지)
        with tempfile.TemporaryDirectory() as d:
            make_interpretive_root(d)
            os.makedirs(os.path.join(d, "sage"))
            Path(os.path.join(d, "sage", "project-profile.yaml")).write_text(
                'project: { name: "t" }\ncomponents:\n  - { id: backend, paths: ["src/backend/**"] }\n')
            os.makedirs(os.path.join(d, ".claude", "agents"))
            os.makedirs(os.path.join(d, ".codex", "agents"))
            # 양 렌더가 컴포넌트 경로를 언급 → owned_paths 교집합 required claim 기대
            rtxt = ("---\nname: be\ndescription: \"x\"\n---\n# be\n"
                    "Owns src/backend/service paths. Follows docs/backend.md conventions.\n")
            Path(os.path.join(d, ".claude", "agents", "be.md")).write_text(rtxt)
            Path(os.path.join(d, ".codex", "agents", "be.md")).write_text(rtxt)
            rc = gen._gen_interpretive(Args(kind="agent", id="be", write=True, dest=d, root=d), d, "agent")
            self.assertEqual(rc, 0)
            claims = Path(os.path.join(d, "docs", "sage_harness", "agents", "be.claims.yml")).read_text()
            self.assertIn("owned_paths", claims)
            self.assertIn("src/backend", claims)

    def test_extract_config_from_profile_derives_globs(self):
        # 단위: 컴포넌트 글롭의 리터럴 디렉토리 prefix → owned_paths 인식 regex 파생
        cfg = gen._extract_config_from_profile(
            {"components": [{"id": "be", "paths": ["src/backend/**", "**/skip"]}]}, ".", ".")
        self.assertIsNotNone(cfg)
        self.assertTrue(any("src/backend" in g for g in cfg["component_path_globs"]))
        # 빈 components → None(엔진 DEFAULT graceful)
        self.assertIsNone(gen._extract_config_from_profile({}, ".", "."))

    def test_extract_config_skips_overmatch_globs(self):
        # 과매칭 위험 글롭 전부 제외(codex 리뷰 P2): 중간 와일드카드 / 선행 와일드카드 / 세그먼트 내 와일드카드
        for bad in ("src/*/service/**", "**/skip", "src/foo*.py", "src/[ab]/**"):
            self.assertIsNone(
                gen._extract_config_from_profile({"components": [{"id": "z", "paths": [bad]}]}, ".", "."),
                f"{bad} 는 과매칭이라 파생 제외돼야 함")
        # 안전 케이스는 파생됨
        self.assertIsNotNone(
            gen._extract_config_from_profile({"components": [{"id": "z", "paths": ["a/b/*"]}]}, ".", "."))

    def test_component_glob_token_boundaries(self):
        # codex 리뷰 P2: 좌/우 경계 — substring 과매칭 차단
        import re as _re
        g = gen._component_path_glob("src/backend/**")
        self.assertIsNotNone(_re.search(g, "owns src/backend/svc.py here"))   # 정상 매칭
        self.assertIsNone(_re.search(g, "asrc/backend/svc.py"))               # 좌 경계(앞 글자)
        self.assertIsNotNone(_re.search(g, "owns ./src/backend/svc.py"))     # 앵커 ./ 허용
        self.assertIsNotNone(_re.search(g, "at /src/backend/svc.py"))        # 앵커 / 허용
        g2 = gen._component_path_glob("src/x/util.py")
        self.assertIsNone(_re.search(g2, "src/x/util.py2"))                   # 우 경계(뒤 글자)
        self.assertIsNotNone(_re.search(g2, "see src/x/util.py."))            # 정상(뒤 마침표)

    def test_extract_config_explicit_json_merge(self):
        # extraction.config(repo-상대 json) 로드 → 파생값 위에 병합(명시 우선), 루트 기준 해석
        import json as _json
        with tempfile.TemporaryDirectory() as d:
            Path(os.path.join(d, "ec.json")).write_text(_json.dumps({"input_scope_patterns": ["git diff"]}))
            cfg = gen._extract_config_from_profile(
                {"components": [{"id": "be", "paths": ["src/be/**"]}], "extraction": {"config": "ec.json"}},
                d, d)
            self.assertIn("component_path_globs", cfg)        # 파생
            self.assertEqual(cfg["input_scope_patterns"], ["git diff"])   # 명시 병합

    def test_fail_closed_missing_codex_render(self):
        # Part B: 한쪽 렌더만 있으면 fail-closed(부분등록 금지)
        with tempfile.TemporaryDirectory() as d:
            make_interpretive_root(d)
            os.makedirs(os.path.join(d, ".claude", "agents"))
            Path(os.path.join(d, ".claude", "agents", "solo.md")).write_text(_render_md("solo"))
            rc = gen._gen_interpretive(Args(kind="agent", id="solo", write=True, dest=d, root=d), d, "agent")
            self.assertEqual(rc, 1)
            m = json.loads(Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).read_text())
            self.assertNotIn("agents/solo", m["assets"])

    def test_scan_excludes_core_bootstrap(self):
        # --id 없이 스캔 시 CORE 부트스트랩 렌더(leader 등)는 제외(manifest 비추적)
        with tempfile.TemporaryDirectory() as d:
            make_interpretive_root(d)
            os.makedirs(os.path.join(d, ".claude", "agents"))
            os.makedirs(os.path.join(d, ".codex", "agents"))
            for nm in ("leader", "qa", "myproj-agent"):
                Path(os.path.join(d, ".claude", "agents", f"{nm}.md")).write_text(_render_md(nm))
                Path(os.path.join(d, ".codex", "agents", f"{nm}.md")).write_text(_render_md(nm))
            rc = gen._gen_interpretive(Args(kind="agent", write=True, dest=d, root=d), d, "agent")
            self.assertEqual(rc, 0)
            m = json.loads(Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).read_text())
            self.assertIn("agents/myproj-agent", m["assets"])     # 프로젝트 자산만 등록
            self.assertNotIn("agents/leader", m["assets"])         # CORE 부트스트랩 제외
            self.assertNotIn("agents/qa", m["assets"])

    def test_skill_scan_excludes_both_init_bootstrap_renders(self):
        with tempfile.TemporaryDirectory() as d:
            make_interpretive_root(d)
            for host_dir in (".claude", ".codex"):
                for name in ("sage-init", "sage-init-local", "myproj-skill"):
                    skill = Path(d, host_dir, "skills", name, "SKILL.md")
                    skill.parent.mkdir(parents=True, exist_ok=True)
                    skill.write_text(_render_md(name), encoding="utf-8")

            rc = gen._gen_interpretive(
                Args(kind="skill", write=True, dest=d, root=d), d, "skill")

            self.assertEqual(rc, 0)
            manifest = json.loads(Path(
                d, "docs", "sage_harness", ".manifest.json").read_text(encoding="utf-8"))
            self.assertIn("skills/myproj-skill", manifest["assets"])
            self.assertNotIn("skills/sage-init", manifest["assets"])
            self.assertNotIn("skills/sage-init-local", manifest["assets"])

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요(deploy 는 profile.runtime.host 판독)")
    def test_skill_deploy_codex_global(self):
        # Part C: --deploy-codex → repo .codex/skills 정본을 $CODEX_HOME/skills/<prefix>-<id> 전역 배포
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as ch:
            make_interpretive_root(d)
            os.makedirs(os.path.join(d, "sage"))
            Path(os.path.join(d, "sage", "project-profile.yaml")).write_text(
                'project:\n  name: "t"\n  prefix: "px"\nruntime:\n'
                '  installed_hosts: [claude, codex]\n  active_host: codex\n')
            os.makedirs(os.path.join(d, ".claude", "skills", "deployer"))
            os.makedirs(os.path.join(d, ".codex", "skills", "deployer"))
            Path(os.path.join(d, ".claude", "skills", "deployer", "SKILL.md")).write_text(_render_md("deployer"))
            Path(os.path.join(d, ".codex", "skills", "deployer", "SKILL.md")).write_text(_render_md("deployer"))
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                rc = gen._gen_interpretive(
                    Args(kind="skill", id="deployer", write=True, deploy_codex=True, dest=d, root=d), d, "skill")
            self.assertEqual(rc, 0)
            # 전역 배포(prefix 네임스페이스)
            self.assertTrue(os.path.exists(os.path.join(ch, "skills", "px-deployer", "SKILL.md")))
            # manifest 는 repo 정본만 추적(전역 경로 아님)
            m = json.loads(Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).read_text())
            self.assertIn("skills/deployer", m["assets"])

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요(deploy 는 profile.runtime.host 판독)")
    def test_deploy_codex_empty_prefix_fail_closed(self):
        # Part C P1: 빈 prefix 로 --deploy-codex → 전역 네임스페이스 충돌 위험 → fail-closed(rc=1, 미배포)
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as ch:
            make_interpretive_root(d)
            os.makedirs(os.path.join(d, "sage"))
            Path(os.path.join(d, "sage", "project-profile.yaml")).write_text(
                'project:\n  name: "t"\n  prefix: ""\nruntime:\n  host: codex\n')   # prefix 빈값, codex-host
            os.makedirs(os.path.join(d, ".claude", "skills", "sk1"))
            os.makedirs(os.path.join(d, ".codex", "skills", "sk1"))
            Path(os.path.join(d, ".claude", "skills", "sk1", "SKILL.md")).write_text(_render_md("sk1"))
            Path(os.path.join(d, ".codex", "skills", "sk1", "SKILL.md")).write_text(_render_md("sk1"))
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                rc = gen._gen_interpretive(
                    Args(kind="skill", id="sk1", write=True, deploy_codex=True, dest=d, root=d), d, "skill")
            self.assertEqual(rc, 1)                                          # fail-closed
            self.assertFalse(os.path.isdir(os.path.join(ch, "skills")))      # 전역 배포 없음(충돌 방지)

    def test_unsafe_id_rejected_before_path_build(self):
        # Part C P2: 경로탈출 id 는 렌더/spec/claims 경로 조립 전에 거부(fail, repo-local 쓰기 차단)
        with tempfile.TemporaryDirectory() as d:
            make_interpretive_root(d)
            rc = gen._gen_interpretive(Args(kind="skill", id="../../escape", write=True, dest=d, root=d), d, "skill")
            self.assertEqual(rc, 1)
            # docs/sage_harness 밖으로 spec 이 새지 않았는지 — 상위 경로에 파일 미생성
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(d), "escape.md")))

    def test_deploy_codex_ignored_for_agent(self):
        # --deploy-codex 는 skill 전용 — agent 엔 무시(전역 배포 없음)
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as ch:
            make_interpretive_root(d)
            os.makedirs(os.path.join(d, ".claude", "agents"))
            os.makedirs(os.path.join(d, ".codex", "agents"))
            Path(os.path.join(d, ".claude", "agents", "a1.md")).write_text(_render_md("a1"))
            Path(os.path.join(d, ".codex", "agents", "a1.md")).write_text(_render_md("a1"))
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                rc = gen._gen_interpretive(
                    Args(kind="agent", id="a1", write=True, deploy_codex=True, dest=d, root=d), d, "agent")
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.isdir(os.path.join(ch, "skills")))   # agent 는 전역 배포 안 함


# 「되돌리지 못한 경로」 보고의 언어 중립 표지. 메시지는 표시 언어를 따르므로 한 언어의 문구로
# 단언하면 다른 언어에서는 아무것도 확인하지 않는다.
UNRESTORED_MARKERS = ("되돌리지 못했습니다", "could not be restored")


def _reports_unrestored(err):
    return any(marker in err for marker in UNRESTORED_MARKERS)


class TestGenerateFromDrafts(unittest.TestCase):
    """`/sage-asset` 의 출구 — write guard 가 렌더 자리를 막으므로 AI 는 초안에 쓰고 CLI 가 배치한다.

    차단 메시지에 `sage generate` 가 들어 있는지만 보던 시험은 그 안내를 따라가면 실제로 자산이
    만들어지는지는 보지 않았다. 여기서는 초안부터 manifest 등록까지 끝까지 간다.
    """

    def setUp(self):
        scripts_dir = os.path.join(REPO, "scripts", "sage_harness")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import manifest_util  # noqa: PLC0415
        self.mu = manifest_util
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = self.tmp.name
        make_interpretive_root(self.d)

    def _drafts(self, kind, aid, claude=None, codex=None):
        base = Path(self.d, "sage", "asset_drafts", f"{kind}s", aid)
        base.mkdir(parents=True, exist_ok=True)
        if claude is not False:
            Path(base, "claude-render.md").write_text(claude or _render_md(aid), encoding="utf-8")
        if codex is not False:
            Path(base, "codex-render.md").write_text(codex or _render_md(aid), encoding="utf-8")
        return base

    def _gen(self, kind, aid, **kw):
        args = Args(kind=kind, id=aid, write=True, dest=self.d, root=self.d, from_drafts=True,
                    replace=False)
        args.__dict__.update(kw)
        err = StringIO()
        with redirect_stdout(StringIO()), redirect_stderr(err):
            rc = gen._gen_interpretive(args, self.d, kind)
        return rc, err.getvalue()

    def _renders(self, kind, aid):
        return gen._interpretive_render_paths(self.d, kind, aid)

    def _manifest(self):
        return json.loads(Path(self.d, "docs", "sage_harness", ".manifest.json").read_text())

    def _snapshot(self):
        out = {}
        for path in Path(self.d).rglob("*"):
            if path.is_file():
                out[str(path.relative_to(self.d))] = path.read_bytes()
        return out

    def test_a_new_skill_is_placed_and_registered_and_its_drafts_are_left(self):
        base = self._drafts("skill", "deploy-check")
        rc, err = self._gen("skill", "deploy-check")
        self.assertEqual(rc, 0, err)
        claude_r, codex_r = self._renders("skill", "deploy-check")
        self.assertEqual(Path(claude_r).read_text(encoding="utf-8"), _render_md("deploy-check"))
        self.assertTrue(os.path.exists(codex_r))
        self.assertTrue(Path(self.d, "docs", "sage_harness", "skills", "deploy-check.md").exists())
        self.assertTrue(Path(self.d, "docs", "sage_harness", "skills",
                             "deploy-check.claims.yml").exists())
        entry = self._manifest()["assets"]["skills/deploy-check"]
        self.assertEqual(entry["render_hash"], {"claude": self.mu.sha256_of(claude_r),
                                                "codex": self.mu.sha256_of(codex_r)})
        # 초안은 지우지 않는다 — 지우는 순간 동시에 고친 초안이 사라질 수 있다.
        self.assertEqual(sorted(p.name for p in base.iterdir()),
                         ["claude-render.md", "codex-render.md"])
        self._assert_validates("skills/deploy-check")

    def _assert_validates(self, asset_key):
        """등록된 자산이 validate 의 interpretive 검사(해시·계약·conformance)를 통과하는가."""
        from sage.commands import validate as val  # noqa: PLC0415
        entry = self._manifest()["assets"][asset_key]
        sev, msgs = val._validate_interpretive(self.d, asset_key, entry, run_regression=False)
        self.assertIn(sev, ("PASS", "WARN"), "\n".join(msgs))

    def test_a_new_agent_follows_the_same_path(self):
        self._drafts("agent", "payment")
        rc, err = self._gen("agent", "payment")
        self.assertEqual(rc, 0, err)
        claude_r, codex_r = self._renders("agent", "payment")
        self.assertTrue(os.path.exists(claude_r) and os.path.exists(codex_r))
        self.assertIn("agents/payment", self._manifest()["assets"])
        self._assert_validates("agents/payment")

    def test_existing_renders_are_not_overwritten_without_replace(self):
        self._drafts("skill", "deploy-check")
        self.assertEqual(self._gen("skill", "deploy-check")[0], 0)
        self._drafts("skill", "deploy-check", claude=_render_md("deploy-check") + "changed\n")
        before = self._snapshot()
        rc, err = self._gen("skill", "deploy-check")
        self.assertEqual(rc, 1)
        self.assertIn("--replace", err)
        self.assertEqual(self._snapshot(), before)

    def test_replace_swaps_the_renders_and_refreshes_the_hash(self):
        self._drafts("skill", "deploy-check")
        self.assertEqual(self._gen("skill", "deploy-check")[0], 0)
        changed = _render_md("deploy-check") + "## Extra\nAlso checks rollback.\n"
        self._drafts("skill", "deploy-check", claude=changed, codex=changed)
        rc, err = self._gen("skill", "deploy-check", replace=True)
        self.assertEqual(rc, 0, err)
        claude_r, _codex_r = self._renders("skill", "deploy-check")
        self.assertEqual(Path(claude_r).read_text(encoding="utf-8"), changed)
        self.assertEqual(self._manifest()["assets"]["skills/deploy-check"]["render_hash"]["claude"],
                         self.mu.sha256_of(claude_r))
        self._assert_validates("skills/deploy-check")

    def test_core_names_and_unsafe_ids_are_refused_before_any_copy(self):
        for aid in ("sage-asset", "sage-review", "../escape"):
            with self.subTest(aid=aid):
                if "/" not in aid:
                    self._drafts("skill", aid)
                before = self._snapshot()
                rc, _err = self._gen("skill", aid)
                self.assertEqual(rc, 1)
                self.assertEqual(self._snapshot(), before)
        self._drafts("agent", "leader")
        before = self._snapshot()
        self.assertEqual(self._gen("agent", "leader")[0], 1)
        self.assertEqual(self._snapshot(), before)

    def test_usage_is_checked_before_anything_else(self):
        for kw in ({"kind": "hook", "id": "x", "from_drafts": True},
                   {"kind": "skill", "id": None, "from_drafts": True},
                   {"kind": "skill", "id": "x", "replace": True}):
            with self.subTest(**{k: str(v) for k, v in kw.items()}):
                args = Args(dest=self.d, root=self.d, from_drafts=False, replace=False)
                args.__dict__.update(kw)
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    self.assertEqual(gen.run(args), 2)

    def test_a_missing_or_unextractable_draft_changes_nothing(self):
        self._drafts("skill", "half", codex=False)
        before = self._snapshot()
        rc, err = self._gen("skill", "half")
        self.assertEqual(rc, 1)
        self.assertIn("codex-render.md", err)
        self.assertEqual(self._snapshot(), before)
        self._drafts("skill", "broken")
        before = self._snapshot()
        with mock.patch("extract_skill.extract", side_effect=ValueError("bad render")):
            rc, err = self._gen("skill", "broken")
        self.assertEqual(rc, 1)
        self.assertIn("bad render", err)
        self.assertEqual(self._snapshot(), before)

    def test_without_write_only_the_plan_is_shown(self):
        self._drafts("skill", "deploy-check")
        before = self._snapshot()
        args = Args(kind="skill", id="deploy-check", write=False, dest=self.d, root=self.d,
                    from_drafts=True, replace=False)
        out = StringIO()
        with redirect_stdout(out), redirect_stderr(StringIO()):
            self.assertEqual(gen._gen_interpretive(args, self.d, "skill"), 0)
        self.assertIn(os.path.join(".claude", "skills", "deploy-check", "SKILL.md"), out.getvalue())
        self.assertEqual(self._snapshot(), before)

    @unittest.skipIf(os.name == "nt", "symlink 생성 권한이 환경마다 다르다")
    def test_linked_drafts_are_refused(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        Path(outside.name, "claude-render.md").write_text(_render_md("linked"), encoding="utf-8")
        base = self._drafts("skill", "linked", claude=False)
        os.symlink(os.path.join(outside.name, "claude-render.md"), base / "claude-render.md")
        before = self._snapshot()
        rc, err = self._gen("skill", "linked")
        self.assertEqual(rc, 1)
        self.assertIn("claude-render.md", err)
        self.assertEqual(self._snapshot(), before)
        # 초안 폴더 자체가 밖을 가리키는 경우도 같다.
        shutil.rmtree(Path(self.d, "sage", "asset_drafts"))
        Path(outside.name, "codex-render.md").write_text(_render_md("linked"), encoding="utf-8")
        Path(self.d, "sage", "asset_drafts", "skills").mkdir(parents=True)
        os.symlink(outside.name, Path(self.d, "sage", "asset_drafts", "skills", "linked"))
        self.assertEqual(self._gen("skill", "linked")[0], 1)
        self.assertFalse(os.path.exists(self._renders("skill", "linked")[0]))

    def test_a_failed_second_replace_restores_the_first_render(self):
        self._drafts("skill", "deploy-check")
        self.assertEqual(self._gen("skill", "deploy-check")[0], 0)
        claude_r, codex_r = self._renders("skill", "deploy-check")
        original = (Path(claude_r).read_bytes(), Path(codex_r).read_bytes())
        changed = _render_md("deploy-check") + "changed\n"
        self._drafts("skill", "deploy-check", claude=changed, codex=changed)
        real_replace = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError("disk full")
            return real_replace(src, dst)

        with mock.patch.object(gen.os, "replace", side_effect=flaky):
            rc, err = self._gen("skill", "deploy-check", replace=True)
        self.assertEqual(rc, 1)
        self.assertIn("disk full", err)
        self.assertEqual((Path(claude_r).read_bytes(), Path(codex_r).read_bytes()), original)
        self.assertEqual([p.name for p in Path(claude_r).parent.iterdir()], ["SKILL.md"])
        self.assertTrue(Path(self.d, "sage", "asset_drafts", "skills", "deploy-check").exists())

    def test_a_case_alias_of_a_core_name_is_refused(self):
        """대소문자를 가리지 않는 파일시스템에서 `SAGE-REVIEW` 는 CORE `sage-review` 와 같은 파일이다."""
        for kind, aid in (("skill", "SAGE-REVIEW"), ("skill", "Sage-Asset"), ("agent", "LEADER")):
            with self.subTest(aid=aid):
                self._drafts(kind, aid)
                before = self._snapshot()
                rc, err = self._gen(kind, aid, replace=True)
                self.assertEqual(rc, 1)
                self.assertIn("CORE", err)
                self.assertEqual(self._snapshot(), before)

    def test_a_registration_failure_restores_everything(self):
        """렌더만 놓이고 등록이 실패하면 새 렌더는 manifest 에 없고, 다시 하려면 --replace 가 필요해진다."""
        self._drafts("skill", "deploy-check")
        before = self._snapshot()
        with mock.patch.object(self.mu, "save", side_effect=OSError("manifest disk full")):
            rc, err = self._gen("skill", "deploy-check")
        self.assertEqual(rc, 1)
        self.assertIn("manifest disk full", err)
        self.assertEqual(self._snapshot(), before)
        # 수정(--replace)에서도 원래 렌더·spec·claims 로 돌아간다.
        self.assertEqual(self._gen("skill", "deploy-check")[0], 0)
        self._drafts("skill", "deploy-check", claude=_render_md("deploy-check") + "x\n",
                     codex=_render_md("deploy-check") + "x\n")
        before = self._snapshot()
        with mock.patch.object(self.mu, "save", side_effect=OSError("manifest disk full")):
            rc, _err = self._gen("skill", "deploy-check", replace=True)
        self.assertEqual(rc, 1)
        self.assertEqual(self._snapshot(), before)

    def test_a_failed_temp_write_leaves_no_temp_file(self):
        self._drafts("skill", "deploy-check")
        before = self._snapshot()
        real_fdopen = os.fdopen
        calls = []

        class Exploding:
            def __init__(self, fh):
                self.fh = fh

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.fh.close()
                return False

            def write(self, data):
                self.fh.write(data[:3])
                raise OSError("disk full while staging")

        def fdopen(fd, mode="r", *a, **kw):
            calls.append(fd)
            handle = real_fdopen(fd, mode, *a, **kw)
            return Exploding(handle) if len(calls) == 2 else handle

        with mock.patch.object(gen.os, "fdopen", side_effect=fdopen):
            rc, err = self._gen("skill", "deploy-check")
        self.assertEqual(rc, 1)
        self.assertIn("disk full while staging", err)
        self.assertEqual(self._snapshot(), before)

    def test_a_render_created_after_the_check_is_not_overwritten(self):
        """존재 검사 뒤 배치 전에 생긴 렌더를 --replace 없이 덮지 않는다."""
        self._drafts("skill", "deploy-check")
        claude_r, _codex_r = self._renders("skill", "deploy-check")
        import extract_skill  # noqa: PLC0415
        real = extract_skill.extract

        def extract_then_race(*args, **kw):
            Path(claude_r).parent.mkdir(parents=True, exist_ok=True)
            Path(claude_r).write_text("someone else\n", encoding="utf-8")
            return real(*args, **kw)

        with mock.patch("extract_skill.extract", side_effect=extract_then_race):
            rc, _err = self._gen("skill", "deploy-check")
        self.assertEqual(rc, 1)
        self.assertEqual(Path(claude_r).read_text(encoding="utf-8"), "someone else\n")
        self.assertNotIn("skills/deploy-check", self._manifest()["assets"])

    def test_rollback_leaves_a_render_someone_else_changed(self):
        """되돌리기는 우리가 쓴 그대로일 때만 한다. 그 사이 바뀐 파일을 지우면 남의 결과가 사라진다."""
        self._drafts("skill", "deploy-check")
        claude_r, codex_r = self._renders("skill", "deploy-check")

        def upsert_after_someone_edits(*args, **kw):
            Path(claude_r).write_text("someone else\n", encoding="utf-8")
            raise OSError("manifest disk full")

        with mock.patch.object(self.mu, "upsert_skill", side_effect=upsert_after_someone_edits):
            rc, err = self._gen("skill", "deploy-check")
        self.assertEqual(rc, 1)
        self.assertEqual(Path(claude_r).read_text(encoding="utf-8"), "someone else\n")
        self.assertFalse(os.path.exists(codex_r))
        self.assertIn(os.path.join(".claude", "skills", "deploy-check", "SKILL.md"), err)
        self.assertTrue(_reports_unrestored(err), err)
        self.assertNotIn("skills/deploy-check", self._manifest()["assets"])

    def test_the_no_link_fallback_leaves_no_empty_render(self):
        """하드 링크를 못 쓰는 파일시스템에서 채우기 전에 실패해도 빈 렌더를 남기지 않는다."""
        self._drafts("skill", "deploy-check")
        before = self._snapshot()
        real_replace = os.replace

        def replace(src, dst):
            if dst.endswith("SKILL.md"):
                raise OSError("replace failed")
            return real_replace(src, dst)

        with mock.patch.object(gen.os, "link", side_effect=PermissionError("no hard links")), \
                mock.patch.object(gen.os, "replace", side_effect=replace):
            rc, err = self._gen("skill", "deploy-check")
        self.assertEqual(rc, 1)
        self.assertFalse(_reports_unrestored(err), err)
        self.assertEqual(self._snapshot(), before)

    def test_the_no_link_fallback_still_places_the_renders(self):
        self._drafts("skill", "deploy-check")
        with mock.patch.object(gen.os, "link", side_effect=PermissionError("no hard links")):
            rc, err = self._gen("skill", "deploy-check")
        self.assertEqual(rc, 0, err)
        self._assert_validates("skills/deploy-check")

    def test_a_failed_spec_write_keeps_the_original_spec(self):
        """spec 을 제자리에 쓰다 실패하면 잘린 원본을 되돌리지 못한다 — 임시 파일로 쓴 뒤 교체한다."""
        self._drafts("skill", "deploy-check")
        self.assertEqual(self._gen("skill", "deploy-check")[0], 0)
        self._drafts("skill", "deploy-check", claude=_render_md("deploy-check") + "x\n",
                     codex=_render_md("deploy-check") + "x\n")
        before = self._snapshot()
        real_replace = os.replace

        def replace(src, dst):
            if dst.endswith("deploy-check.md") and "docs" in dst:
                raise OSError("spec disk full")
            return real_replace(src, dst)

        with mock.patch.object(gen.os, "replace", side_effect=replace):
            rc, err = self._gen("skill", "deploy-check", replace=True)
        self.assertEqual(rc, 1)
        self.assertIn("spec disk full", err)
        self.assertFalse(_reports_unrestored(err), err)
        self.assertEqual(self._snapshot(), before)

    def test_a_failed_replace_does_not_report_the_untouched_original(self):
        """교체가 실패하면 원본은 그대로다 — 그것을 「되돌리지 못함」으로 알리면 사용자가 멀쩡한 파일을 고친다."""
        self._drafts("skill", "deploy-check")
        self.assertEqual(self._gen("skill", "deploy-check")[0], 0)
        self._drafts("skill", "deploy-check", claude=_render_md("deploy-check") + "x\n",
                     codex=_render_md("deploy-check") + "x\n")
        before = self._snapshot()
        with mock.patch.object(gen.os, "replace", side_effect=OSError("replace refused")):
            rc, err = self._gen("skill", "deploy-check", replace=True)
        self.assertEqual(rc, 1)
        self.assertIn("replace refused", err)
        self.assertFalse(_reports_unrestored(err), err)
        self.assertEqual(self._snapshot(), before)

    def test_a_busy_destination_lock_changes_nothing(self):
        """초안 배치는 hook generate·install 과 같은 잠금 안에서 마지막 스탬프까지 한다."""
        from sage.install_transaction import InstallBusyError  # noqa: PLC0415
        self._drafts("skill", "deploy-check")
        before = self._snapshot()
        args = Args(kind="skill", id="deploy-check", write=True, dest=self.d, root=self.d,
                    from_drafts=True, replace=False)
        called = []
        with mock.patch.object(gen.DestinationLock, "acquire",
                               side_effect=InstallBusyError("busy")), \
                redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            rc = gen._locked(args, self.d, lambda: called.append(1) or 0)
        self.assertEqual(rc, 1)
        self.assertEqual(called, [])
        self.assertEqual(self._snapshot(), before)

    @unittest.skipIf(os.name == "nt", "symlink 생성 권한이 환경마다 다르다")
    def test_a_linked_render_or_render_directory_is_refused(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        victim = Path(outside.name, "victim.md")
        victim.write_text("outside\n", encoding="utf-8")
        self._drafts("skill", "deploy-check")
        claude_r, _codex_r = self._renders("skill", "deploy-check")
        Path(claude_r).parent.mkdir(parents=True)
        os.symlink(victim, claude_r)
        rc, _err = self._gen("skill", "deploy-check", replace=True)
        self.assertEqual(rc, 1)
        self.assertEqual(victim.read_text(encoding="utf-8"), "outside\n")
        self.assertTrue(os.path.islink(claude_r))
        # 렌더 디렉터리 자체가 밖을 가리키는 경우.
        shutil.rmtree(Path(self.d, ".claude"))
        Path(self.d, ".claude", "skills").mkdir(parents=True)
        os.symlink(outside.name, Path(self.d, ".claude", "skills", "deploy-check"))
        rc, _err = self._gen("skill", "deploy-check", replace=True)
        self.assertEqual(rc, 1)
        self.assertEqual(sorted(os.listdir(outside.name)), ["victim.md"])


class TestGenerate(unittest.TestCase):
    def test_manifest_stamp_records_current_generator_version(self):
        with tempfile.TemporaryDirectory() as root:
            make_root(root)

            self.assertEqual(gen.run(Args(target="claude", dest=root, root=root, write=True)), 0)

            manifest = json.loads(
                Path(root, "docs", "sage_harness", ".manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(__version__, manifest["generator_version"])

    def test_hook_manifest_transaction_preserves_manifest_when_write_fails(self):
        import unittest.mock as mock

        with tempfile.TemporaryDirectory() as root:
            make_root(root)
            manifest_path = Path(root, "docs", "sage_harness", ".manifest.json")
            before = manifest_path.read_bytes()

            original_write = gen._oc.write_text_lf

            def fail_manifest(path, body, mode=None):
                if os.path.abspath(path) == os.path.abspath(manifest_path):
                    raise OSError("injected")
                return original_write(path, body, mode=mode)

            with mock.patch.object(gen._oc, "write_text_lf", side_effect=fail_manifest), \
                    redirect_stderr(StringIO()), redirect_stdout(StringIO()):
                self.assertEqual(
                    gen.run(Args(target="claude", dest=root, root=root, write=True)), 1)

            self.assertEqual(before, manifest_path.read_bytes())

    def test_generator_version_stamp_preserves_manifest_when_replace_fails(self):
        import unittest.mock as mock
        from sage import manifest_io

        with tempfile.TemporaryDirectory() as root:
            make_root(root)
            manifest_path = Path(root, "docs", "sage_harness", ".manifest.json")
            before = manifest_path.read_bytes()

            with mock.patch.object(manifest_io.os, "replace", side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    gen._stamp_generator_version(root)

            self.assertEqual(before, manifest_path.read_bytes())
            self.assertEqual([], list(manifest_path.parent.glob(".sage-manifest-*")))

    def test_atomic_manifest_write_works_without_fchmod(self):
        import unittest.mock as mock
        from sage import manifest_io

        with tempfile.TemporaryDirectory() as root:
            make_root(root)
            manifest_path = Path(root, "docs", "sage_harness", ".manifest.json")

            with mock.patch.object(manifest_io.os, "fchmod", None):
                gen._stamp_generator_version(root)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(__version__, manifest["generator_version"])

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

    def test_command_template_rejects_shell_metacharacters_in_hook_id(self):
        with self.assertRaisesRegex(ValueError, "hook id"):
            gen._command_template("codex", "x$(printf injected)")

    @unittest.skipIf(os.name == "nt", "POSIX launcher contract")
    def test_posix_command_finds_pipx_default_bin_when_path_is_restricted(self):
        with tempfile.TemporaryDirectory() as home:
            bin_dir = Path(home, ".local", "bin")
            bin_dir.mkdir(parents=True)
            launcher = bin_dir / "sage-hook"
            launcher.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$@" > "$HOME/invocation.txt"\n',
                encoding="utf-8",
            )
            launcher.chmod(0o755)
            env = {"HOME": home, "PATH": "/usr/bin:/bin"}

            result = subprocess.run(
                gen._command_template("codex", "capture-declared-risk"),
                shell=True,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                ["--runtime", "codex", "--hook", "capture-declared-risk"],
                Path(home, "invocation.txt").read_text(encoding="utf-8").splitlines(),
            )

    @unittest.skipIf(os.name == "nt", "POSIX launcher contract")
    def test_posix_command_uses_absolute_sage_hook_bin(self):
        with tempfile.TemporaryDirectory() as home:
            launcher = Path(home, "custom-sage-hook")
            launcher.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$@" > "$HOME/invocation.txt"\n',
                encoding="utf-8",
            )
            launcher.chmod(0o755)
            env = {
                "HOME": home,
                "PATH": "/usr/bin:/bin",
                "SAGE_HOOK_BIN": str(launcher),
            }

            result = subprocess.run(
                gen._command_template("codex", "capture-declared-risk"),
                shell=True,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                ["--runtime", "codex", "--hook", "capture-declared-risk"],
                Path(home, "invocation.txt").read_text(encoding="utf-8").splitlines(),
            )

    @unittest.skipIf(os.name == "nt", "POSIX launcher contract")
    def test_posix_command_ignores_relative_sage_hook_bin(self):
        with tempfile.TemporaryDirectory() as home:
            bin_dir = Path(home, ".local", "bin")
            bin_dir.mkdir(parents=True)
            launcher = bin_dir / "sage-hook"
            launcher.write_text(
                '#!/bin/sh\nprintf "fallback\\n" > "$HOME/source.txt"\n',
                encoding="utf-8",
            )
            launcher.chmod(0o755)
            env = {
                "HOME": home,
                "PATH": "/usr/bin:/bin",
                "SAGE_HOOK_BIN": "relative-sage-hook",
            }

            result = subprocess.run(
                gen._command_template("codex", "capture-declared-risk"),
                shell=True,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                "fallback\n",
                Path(home, "source.txt").read_text(encoding="utf-8"),
            )

    @unittest.skipIf(os.name == "nt", "POSIX launcher contract")
    def test_posix_command_reports_missing_launcher_before_exit_127(self):
        with tempfile.TemporaryDirectory() as home:
            result = subprocess.run(
                gen._command_template("codex", "capture-declared-risk"),
                shell=True,
                capture_output=True,
                text=True,
                env={"HOME": home, "PATH": "/usr/bin:/bin"},
            )

            self.assertEqual(127, result.returncode)
            self.assertIn("set absolute SAGE_HOOK_BIN", result.stderr)

    def test_windows_command_keeps_console_entrypoint_without_bash(self):
        with mock.patch.object(gen.os, "name", "nt"):
            command = gen._command_template("codex", "capture-declared-risk")

        self.assertEqual(
            "sage-hook --runtime codex --hook capture-declared-risk",
            command,
        )

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
            x = json.loads(Path(os.path.join(dest, ".codex", "hooks.json")).read_text())
            cmd = x["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            self.assertEqual(gen._command_template("codex", "aaa-hook"), cmd)

            if os.name != "nt":
                home = Path(dest, "home")
                launcher = home / ".local" / "bin" / "sage-hook"
                launcher.parent.mkdir(parents=True)
                launcher.write_text(
                    '#!/bin/sh\nprintf "%s\\n" "$@" > "$HOME/invocation.txt"\n',
                    encoding="utf-8",
                )
                launcher.chmod(0o755)
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(
                    ["--runtime", "codex", "--hook", "aaa-hook"],
                    Path(home, "invocation.txt").read_text(encoding="utf-8").splitlines(),
                )

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
            self.assertEqual(set(m["hook_runtime_hash"]), {"shared", "claude", "codex"})
            self.assertTrue(m["hook_runtime_hash"]["shared"].startswith("sha256:"))

    def test_root_defaults_to_dest(self):
        # Codex P1: --root 없이 --dest 만 → dest 의 manifest 를 stamp (cwd 의 다른 manifest 아님)
        with tempfile.TemporaryDirectory() as dest:
            make_root(dest)
            rc = gen.run(Args(target="claude", dest=dest, write=True))  # root=None
            self.assertEqual(rc, 0)
            m = json.loads(Path(os.path.join(dest, "docs", "sage_harness", ".manifest.json")).read_text())
            # make_root 가 둔 "x" 가 실제 sha 로 스탬프됨 → dest manifest 가 갱신됐다는 증거
            self.assertTrue(m["assets"]["hooks/aaa-hook"]["spec_hash"].startswith("sha256:"))
            self.assertIn("hook_runtime_hash", m)

    def test_missing_runtime_files_fail_closed(self):
        # runtime/run_hook.py 등 공용 실행층이 없으면 registration 만 생성하고 manifest 미스탬프로
        # 남기면 안 된다. generate 는 비정상 종료를 반환해 CI/호출자가 즉시 알 수 있어야 한다.
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            make_root(d)
            shutil.rmtree(os.path.join(d, "sage_harness", "hooks", "runtime"))
            rc = gen.run(Args(target="claude", dest=dest, root=d, write=True))
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(os.path.join(dest, ".claude", "settings.json")))
            m = json.loads(Path(os.path.join(d, "docs", "sage_harness", ".manifest.json")).read_text())
            self.assertNotIn("hook_runtime_hash", m)

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
    def test_profile_scalar_trigger_fails_before_any_output_write(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            make_root(d)
            os.makedirs(os.path.join(dest, "sage"), exist_ok=True)
            Path(os.path.join(dest, "sage", "project-profile.yaml")).write_text(
                "project: { name: t }\nrisk:\n  l3_filename_globs: auth\n", encoding="utf-8")

            rc = gen.run(Args(target="both", dest=dest, root=d, write=True))

            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(os.path.join(dest, "sage", "project-profile.json")))
            self.assertFalse(os.path.exists(os.path.join(dest, ".claude", "settings.json")))
            self.assertFalse(os.path.exists(os.path.join(dest, ".codex", "hooks.json")))

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요(generate 빌드 의존성)")
    def test_invalid_checklist_profile_preserves_all_existing_outputs(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            make_root(d)
            os.makedirs(os.path.join(dest, "sage"), exist_ok=True)
            compiled = os.path.join(dest, "sage", "project-profile.json")
            settings = os.path.join(dest, ".claude", "settings.json")
            hooks = os.path.join(dest, ".codex", "hooks.json")
            os.makedirs(os.path.dirname(settings), exist_ok=True)
            os.makedirs(os.path.dirname(hooks), exist_ok=True)
            Path(compiled).write_text('{"old": true}\n', encoding="utf-8")
            Path(settings).write_text('{"old": "claude"}\n', encoding="utf-8")
            Path(hooks).write_text('{"old": "codex"}\n', encoding="utf-8")
            os.chmod(compiled, 0o600)
            before = {
                path: (Path(path).read_bytes(), os.stat(path).st_mode & 0o777,
                       os.stat(path).st_mtime_ns)
                for path in (compiled, settings, hooks)
            }
            Path(os.path.join(dest, "sage", "project-profile.yaml")).write_text(
                "project: { name: t }\n"
                "checklist_scan_targets:\n"
                "  - { label: implementation, glob: 'C:private\\\\*.md' }\n",
                encoding="utf-8",
            )

            rc = gen.run(Args(target="both", dest=dest, root=d, write=True))

            self.assertEqual(rc, 1)
            for path, expected in before.items():
                self.assertEqual((Path(path).read_bytes(), os.stat(path).st_mode & 0o777,
                                  os.stat(path).st_mtime_ns),
                                 expected, path)
            self.assertFalse(os.path.exists(os.path.join(dest, ".claude", "hooks")))
            self.assertFalse(os.path.exists(os.path.join(dest, ".codex", "hooks")))

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요(generate 빌드 의존성)")
    def test_profile_compiles_to_json(self):
        # profile.yaml(유효) → project-profile.json 컴파일(hook 런타임 입력, 의존성 0)
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as dest:
            make_root(d)
            os.makedirs(os.path.join(dest, "sage"), exist_ok=True)
            compiled = os.path.join(dest, "sage", "project-profile.json")
            Path(compiled).write_text('{"old": true}\n', encoding="utf-8")
            os.chmod(compiled, 0o644)
            shim = os.path.join(dest, ".claude", "hooks", "aaa-hook.sh")
            os.makedirs(os.path.dirname(shim), exist_ok=True)
            Path(shim).write_text("old shim\n", encoding="utf-8")
            os.chmod(shim, 0o644)
            Path(os.path.join(dest, "sage", "project-profile.yaml")).write_text(
                "project: { name: t }\nrisk:\n  l3_filename_globs: ['*payment*']\n  l2_path_globs: ['src/*']\n")
            rc = gen.run(Args(target="claude", dest=dest, root=d, write=True))
            self.assertEqual(rc, 0)
            prof = json.loads(Path(compiled).read_text())
            self.assertEqual(prof["risk"]["l3_filename_globs"], ["*payment*"])
            self.assertEqual(os.stat(compiled).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(shim).st_mode & 0o777, 0o755)

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
