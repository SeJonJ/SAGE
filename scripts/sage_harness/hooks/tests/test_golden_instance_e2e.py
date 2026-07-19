#!/usr/bin/env python3
"""golden-instance e2e — install→profile→generate→validate→설치된 shim 구동 전체 파이프라인.

런타임 스모크(test_runtime_smoke)는 **레포 어댑터 + 손으로 만든 profile JSON**을 직접 구동했다.
이 e2e 는 한 단계 위 — **실제 CLI 파이프라인이 만든 산출물**(컴파일된 profile.json, settings.json,
설치된 shim)을 그대로 구동해, install→generate→runtime 통합층(스모크가 못 닿는 곳)을 박제한다:

  1. sage install → 자기완결 인스턴스 트리(profile yaml + framework + 어댑터 + manifest)
  2. 대표 golden profile(2컴포넌트·L1/L2/L3·pdca·중립값) 기입
  3. sage generate --write → profile.yaml→json 컴파일 + settings.json + shim 6 + 스탬프
  4. sage validate --check --schema → PASS(STALE 없음)
  5. 설치된 shim(.claude/hooks/{id}.sh) 을 CLAUDE_PROJECT_DIR 만 주고 구동 →
     shim 이 SAGE_PROFILE/CORE_DIR 를 스스로 해석 → adapter → core 까지 폐루프로 PDCA 강제 확인

= "설치·generate 는 통과하나 런타임은 죽어있다"(Pattern A)를 파이프라인 끝단에서 잡는 golden 가드.
profile 은 도메인 토큰 0 의 중립 합성(독립성 유지).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HOOKS_DIR)))  # scripts/sage_harness/hooks → repo

# 중립 합성 golden profile(.src 스택, 도메인 토큰 0). 2 컴포넌트(core/ui) + L1/L2/L3 + pdca.
GOLDEN_PROFILE = """project:
  name: "gold"
  prefix: "gold"
components:
  - { id: core, paths: ["app/core/**"] }
  - { id: ui,   paths: ["app/ui/**"] }
risk:
  l0_pass_globs: ["*.md", "plan_docs/*"]
  l1_path_globs: ["*ui/*.src"]
  l2_path_globs: ["*core/*.src"]
  l3_filename_globs: ["*secret*"]
  l2_content_keywords: ["@SynthData"]
  l3_content_keywords: ["synthSecretCall"]
  plan_glob: "plan_docs/00-base_plan/**/*.md"
  l3_review_strategy: "claude_grep_first"
  review_patterns: ["review"]
file_type_map:
  - { glob: "*ui/*.src",   type: ui }
  - { glob: "*core/*.src", type: core }
skip_untyped: true
compliance:
  plan_gate_code_types: [core, ui]
pdca:
  enabled: true
  phases:
    - { id: "00", glob: "plan_docs/00-base_plan/**/*.md" }
    - { id: "01", glob: "plan_docs/01-plan/**/*.md" }
    - { id: "02", glob: "plan_docs/02-design/**/*.md" }
    - { id: "03", glob: "plan_docs/03-implementation/**/*.md" }
    - { id: "04", glob: "plan_docs/04-analyze/**/*.md" }
    - { id: "05", glob: "plan_docs/05-expert-review/**/*.md" }
    - { id: "06", glob: "plan_docs/06-report/**/*.md" }
  pre_implementation_required:
    L1: ["00"]
    L2: ["00", "01", "02"]
    L3: ["00", "01", "02"]
  report_phase: "06"
  approve_phase: "05"
  approve_marker: "APPROVED"
knowledge_capture:
  vault_path: ""
  provider: obsidian
  note_convention: { folder: "wiki", filename_pattern: "{prefix} - {title}.md", flat: true }
"""


def _sage(args, cwd):
    env = dict(os.environ, PYTHONPATH=REPO)
    return subprocess.run([sys.executable, "-m", "sage", *args], cwd=cwd, env=env,
                          capture_output=True, text=True)


def _run_shim(inst, hook_id, raw, branch="main"):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=inst, SAGE_GATE_BRANCH=branch)
    shim = os.path.join(inst, ".claude", "hooks", f"{hook_id}.sh")
    return subprocess.run(["bash", shim], input=json.dumps(raw), capture_output=True, text=True, env=env)


def _write(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _claude_write(path, content="x"):
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}, "session_id": "gold"}


class TestGoldenInstanceE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        cls.inst = os.path.join(cls._tmp, "inst")
        # 1. install
        cls.install = _sage(["install", "--host", "claude", "--prefix", "gold", "--dest", cls.inst], cwd=REPO)
        # 2. golden profile 기입
        _write(os.path.join(cls.inst, "sage", "project-profile.yaml"), GOLDEN_PROFILE)
        # 3. generate --write
        cls.generate = _sage(["generate", "--kind", "hook", "--write"], cwd=cls.inst)
        # 4. validate
        cls.validate = _sage(["validate", "--check", "--schema"], cwd=cls.inst)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_pipeline_succeeds(self):
        self.assertEqual(self.install.returncode, 0, f"install\n{self.install.stderr}")
        self.assertEqual(self.generate.returncode, 0, f"generate\n{self.generate.stderr}")
        self.assertTrue(os.path.exists(os.path.join(self.inst, "sage", "project-profile.json")), "compiled profile.json")
        self.assertTrue(os.path.exists(os.path.join(self.inst, ".claude", "settings.json")), "settings.json")

    def test_validate_pass_not_stale(self):
        self.assertEqual(self.validate.returncode, 0, f"validate 종합 PASS 기대\n{self.validate.stdout}\n{self.validate.stderr}")
        self.assertIn("SCHEMA PASS", self.validate.stdout)

    def test_all_hooks_registered(self):
        # F6 가드: generate 가 7 hook 전부 등록(클로버 없음)
        with open(os.path.join(self.inst, ".claude", "settings.json"), encoding="utf-8") as f:
            cmds = json.dumps(json.load(f))
        for hid in ("generated-artifact-write-guard", "pre-implementation-gate", "pre-phase4-checklist-gate",
                    "post-tool-logger", "stop-compliance-report", "capture-declared-risk", "session-start-snapshot"):
            self.assertIn(hid, cmds, f"{hid} 등록 누락(클로버)")

    def test_install_tree_no_domain_tokens(self):
        # 독립성(제약 #2): 설치 트리에 스택 누출 토큰 0
        p = subprocess.run(["grep", "-rilE", "springboot|nodejs|kurento|webrtc|electron|chatforyou|jquery",
                            self.inst], capture_output=True, text=True)
        self.assertEqual(p.stdout.strip(), "", f"도메인 토큰 누출:\n{p.stdout}")

    def test_installed_shim_enforces_pdca_at_runtime(self):
        # 설치된 shim 폐루프: L2 코드 변경 + phase 문서 없음 → 실제 BLOCK(exit2)
        p = _run_shim(self.inst, "pre-implementation-gate", _claude_write("app/core/data.src"))
        self.assertEqual(p.returncode, 2, f"L2 phase 결핍 BLOCK 기대\n{p.stdout}\n{p.stderr}")
        self.assertIn("PDCA phase 미작성", p.stdout + p.stderr)

    def test_installed_shim_l1_passes(self):
        p = _run_shim(self.inst, "pre-implementation-gate", _claude_write("app/ui/screen.src"))
        self.assertEqual(p.returncode, 0, f"L1 통과 기대\n{p.stdout}\n{p.stderr}")

    def test_installed_shim_phases_present_passes(self):
        # 인스턴스에 00/01/02 phase 문서를 두면 shim glob 스캔이 잡아 phase 게이트 통과
        for pid, sub in (("00", "00-base_plan"), ("01", "01-plan"), ("02", "02-design")):
            _write(os.path.join(self.inst, "plan_docs", sub, "feature.md"),
                   f"# phase {pid}\n\nCycle-Stem: `feature`\n")
        try:
            p = _run_shim(self.inst, "pre-implementation-gate", _claude_write("app/core/data.src"),
                          branch="feature")
            self.assertEqual(p.returncode, 0, f"phase 충족 통과 기대\n{p.stdout}\n{p.stderr}")
            self.assertNotIn("phase 미작성", p.stdout + p.stderr)
        finally:
            import shutil
            shutil.rmtree(os.path.join(self.inst, "plan_docs"), ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
