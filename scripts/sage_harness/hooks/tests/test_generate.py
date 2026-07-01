#!/usr/bin/env python3
"""sage generate 검증 (상 등급 — hook 등록 산출물 + manifest 스탬프, Codex 2R).

self-contained: 임시 SAGE 루트(hook spec frontmatter + adapter stub + manifest)로 등록 생성 확인.
"""
import json
import os
import shutil
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
    os.makedirs(os.path.join(d, "scripts", "sage_harness", "hooks", "runtime"), exist_ok=True)
    Path(os.path.join(d, "docs", "sage_harness", "hooks", "aaa-hook.md")).write_text(SPEC_A)
    Path(os.path.join(d, "docs", "sage_harness", "hooks", "bbb-hook.md")).write_text(SPEC_B)
    for fn in ("run_hook.py", "hook_runtime.py", "loop_audit.py", "messages.py", "io_claude.py", "io_codex.py"):
        Path(os.path.join(d, "scripts", "sage_harness", "hooks", "runtime", fn)).write_text(f"# {fn}\n")
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

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요(deploy 는 profile.runtime.host 판독)")
    def test_skill_deploy_codex_global(self):
        # Part C: --deploy-codex → repo .codex/skills 정본을 $CODEX_HOME/skills/<prefix>-<id> 전역 배포
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as ch:
            make_interpretive_root(d)
            os.makedirs(os.path.join(d, "sage"))
            Path(os.path.join(d, "sage", "project-profile.yaml")).write_text(
                'project:\n  name: "t"\n  prefix: "px"\nruntime:\n  host: codex\n')
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
            shutil.rmtree(os.path.join(d, "scripts", "sage_harness", "hooks", "runtime"))
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
