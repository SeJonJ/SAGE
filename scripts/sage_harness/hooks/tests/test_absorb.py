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

    def test_hook_not_implemented(self):
        with tempfile.TemporaryDirectory() as d:
            setup_root(d, "required_claims:\nforbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n")
            rc, out = run_absorb(Args(kind="hook", id="x", root=d))
            self.assertEqual(rc, 2)
            self.assertIn("미구현", out)

    def test_agent_missing_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            setup_root(d, "required_claims:\nforbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n")
            rc, out = run_absorb(Args(root=d))  # claude/codex 없음
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
