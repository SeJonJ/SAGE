#!/usr/bin/env python3
"""sage absorb 검증 (중 등급 — 직접수정 → spec patch 제안).

self-contained: 임시 SAGE 루트 + 합성 산출물로 claims diff 흡수 제안 확인.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts", "sage_harness"))
from sage.commands import absorb  # noqa: E402

GUIDE = "Do not run git commit or git push."
BASE = '---\nname: "demo"\ndescription: "데모"\n---\n소유: myapp/src/core\ndocs/a.md 준수\n'
DEMO_CONFIG = "extract_config_demo_absorb:CFG"
# skill 입력(DEFAULT skill config 로 추출 — 소스트리 config 모듈 불필요)
SKILL_C = ('---\nname: "demo"\ndescription: >\n  "데모 수행" 에 사용.\n---\n'
           '## 목적\n검증.\n## 실행 방법\n`backend-convention-checker` 로 docs/demo_conv.md 기준 검증.\n')


def _sha(p):
    import hashlib
    return "sha256:" + hashlib.sha256(open(p, "rb").read()).hexdigest()


def setup_hook_root(d, edited=False):
    """native hook(demo.sh) + manifest 스탬프. edited=True 면 스탬프 후 정본 변경(divergence)."""
    H = os.path.join(d, "scripts", "sage_harness", "hooks")
    os.makedirs(H, exist_ok=True)
    os.makedirs(os.path.join(d, "docs", "sage_harness"), exist_ok=True)
    native = os.path.join(H, "demo.sh")
    open(native, "w").write("#!/bin/bash\necho ok\n")
    h = _sha(native)
    if edited:
        open(native, "w").write("#!/bin/bash\necho EDITED\n")   # 스탬프 후 직접수정
    json.dump({"sage_version": "0.1.0", "host_runtime": "claude", "assets": {
        "hooks/demo": {"form": "native", "canonical_hash": h, "render_hash": {"native": h}, "conformance": "PASS"}}},
        open(os.path.join(d, "docs", "sage_harness", ".manifest.json"), "w"))


def setup_root(d, claims_yaml):
    os.makedirs(os.path.join(d, "docs", "sage_harness", "agents"), exist_ok=True)
    json.dump({"sage_version": "0.1.0", "host_runtime": "claude", "assets": {}},
              open(os.path.join(d, "docs", "sage_harness", ".manifest.json"), "w"))
    open(os.path.join(d, "docs", "sage_harness", "agents", "demo.claims.yml"), "w").write(claims_yaml)
    # 임시 config 모듈
    cfgp = os.path.join(REPO, "scripts", "sage_harness", "extract_config_demo_absorb.py")
    open(cfgp, "w").write('CFG = {"component_path_globs": [r"myapp/[\\w./-]+"], "guide_boundary_tokens": ["commit","push"], "signal_rules": []}\n')


class Args:
    def __init__(self, **kw):
        self.kind = "agent"; self.id = "demo"; self.from_blocked_diff = False
        self.claude = ""; self.codex = ""; self.guide = ""; self.config = DEMO_CONFIG; self.root = None
        self.__dict__.update(kw)


def run_absorb(args):
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(out):
        rc = absorb.run(args)
    return rc, out.getvalue()


class TestAbsorb(unittest.TestCase):
    def tearDown(self):
        cfgp = os.path.join(REPO, "scripts", "sage_harness", "extract_config_demo_absorb.py")
        if os.path.exists(cfgp):
            os.remove(cfgp)

    def test_no_change(self):
        with tempfile.TemporaryDirectory() as d:
            # 현 claims 에 myapp/src/core + docs/a.md 이미 있음 → 변경 없음
            setup_root(d, 'required_claims:\n  - { type: owned_paths, value: "myapp/src/core", confidence: high }\n'
                          '  - { type: convention_doc, value: "docs/a.md", confidence: high }\n'
                          'forbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n')
            g = os.path.join(d, "g.md"); open(g, "w").write(GUIDE)
            c = os.path.join(d, "c.md"); open(c, "w").write(BASE)
            x = os.path.join(d, "x.md"); open(x, "w").write(BASE)
            rc, out = run_absorb(Args(claude=c, codex=x, guide=g, root=d))
            self.assertEqual(rc, 0)
            self.assertIn("변경 없음", out)

    def test_added_claim(self):
        with tempfile.TemporaryDirectory() as d:
            setup_root(d, 'required_claims:\n  - { type: owned_paths, value: "myapp/src/core", confidence: high }\n'
                          'forbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n')
            g = os.path.join(d, "g.md"); open(g, "w").write(GUIDE)
            # 양쪽에 docs/a.md 추가 → +required 제안
            mod = BASE
            c = os.path.join(d, "c.md"); open(c, "w").write(mod)
            x = os.path.join(d, "x.md"); open(x, "w").write(mod)
            rc, out = run_absorb(Args(claude=c, codex=x, guide=g, root=d))
            self.assertEqual(rc, 0)
            self.assertIn("+ required:   docs/a.md", out)

    def test_one_sided_unresolved(self):
        with tempfile.TemporaryDirectory() as d:
            setup_root(d, 'required_claims:\n  - { type: owned_paths, value: "myapp/src/core", confidence: high }\n'
                          '  - { type: convention_doc, value: "docs/a.md", confidence: high }\n'
                          'forbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n')
            g = os.path.join(d, "g.md"); open(g, "w").write(GUIDE)
            c = os.path.join(d, "c.md"); open(c, "w").write(BASE + "소유: myapp/src/onlyc\n")
            x = os.path.join(d, "x.md"); open(x, "w").write(BASE)
            rc, out = run_absorb(Args(claude=c, codex=x, guide=g, root=d))
            self.assertIn("unresolved", out)
            self.assertIn("myapp/src/onlyc", out)

    def test_hook_no_divergence(self):
        # 정본이 스탬프와 일치 → 변경 없음
        with tempfile.TemporaryDirectory() as d:
            setup_hook_root(d, edited=False)
            rc, out = run_absorb(Args(kind="hook", id="demo", root=d))
            self.assertEqual(rc, 0)
            self.assertIn("변경 없음", out)

    def test_hook_divergence_detected(self):
        # 정본 직접수정(스탬프 후) → divergence 감지 + 흡수 절차 제안
        with tempfile.TemporaryDirectory() as d:
            setup_hook_root(d, edited=True)
            rc, out = run_absorb(Args(kind="hook", id="demo", root=d))
            self.assertEqual(rc, 0)
            self.assertIn("정본 직접수정 감지", out)
            self.assertIn("demo.sh", out)
            self.assertIn("generate --kind hook", out)

    def test_hook_missing_entry(self):
        with tempfile.TemporaryDirectory() as d:
            setup_hook_root(d)
            rc, out = run_absorb(Args(kind="hook", id="nope", root=d))
            self.assertEqual(rc, 2)

    def test_skill_added_claim(self):
        # skill(interpretive) — 빈 claims 에 수정 산출물의 convention doc 가 +required 제안
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "docs", "sage_harness", "skills"), exist_ok=True)
            json.dump({"sage_version": "0.1.0", "host_runtime": "claude", "assets": {}},
                      open(os.path.join(d, "docs", "sage_harness", ".manifest.json"), "w"))
            open(os.path.join(d, "docs", "sage_harness", "skills", "demo.claims.yml"), "w").write(
                "required_claims:\nforbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n")
            g = os.path.join(d, "g.md"); open(g, "w").write(GUIDE)
            c = os.path.join(d, "c.md"); open(c, "w").write(SKILL_C)
            x = os.path.join(d, "x.md"); open(x, "w").write(SKILL_C)
            rc, out = run_absorb(Args(kind="skill", id="demo", claude=c, codex=x, guide=g, config="", root=d))
            self.assertEqual(rc, 0)
            self.assertIn("docs/demo_conv.md", out)   # uses(convention doc) +required
            self.assertIn("skill:demo", out)          # 헤더가 skill 경로

    def test_agent_missing_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            setup_root(d, "required_claims:\nforbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n")
            rc, out = run_absorb(Args(root=d))  # claude/codex 없음
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
