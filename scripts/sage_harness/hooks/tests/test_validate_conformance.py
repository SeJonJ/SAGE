#!/usr/bin/env python3
"""validate conformance 배선 단위 (외부검토 P1-4 — agent/skill 폐루프 비대칭 해소).

핵심 teeth: render(.md) 가 required claim 을 누락하거나 금지위반을 포함하면 `_validate_interpretive`
(= sage validate 의 agent/skill 경로) 가 FAIL 을 반환한다. 이전엔 hash staleness 만 검사해 비대칭이었다.
render 부재 = skip(미렌더 interpretive 강제 안 함). WARN 약신호 = INFO 비게이팅(sev 불변).

pyyaml 선택의존 — 미설치면 conformance 가 INFO skip 되어 강제 teeth 가 무의미하므로 해당 테스트 skip.
"""
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import validate as V  # noqa: E402

try:
    import yaml  # noqa: F401
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_CLAIMS = """required_claims:
  - { type: owned_paths, value: "src/foo/**", confidence: high }
  - { type: convention_doc, value: "docs/backend.md", confidence: high }
forbidden_claims: []
runtime_delta_allowlist: []
unresolved: []
"""

_CLAIMS_FORBIDDEN = """required_claims:
  - { type: owned_paths, value: "src/foo/**", confidence: high }
forbidden_claims:
  - { type: forbidden, value: "forbidden:git commit/push", confidence: high }
runtime_delta_allowlist: []
unresolved: []
"""


def _stamped_entry(root, asset_id):
    """spec/claims hash 를 채운 정상 스탬프 entry — conformance 를 staleness 와 분리해 검사하기 위함.
    hashless entry 는 이제 STALE(미스탬프)로 판정되므로, conformance 만 격리하려면 hash 를 채워야 한다."""
    subdir, aid = asset_id.split("/", 1)
    docs = os.path.join(root, "docs", "sage_harness", subdir)
    return {"spec_hash": V._sha(os.path.join(docs, f"{aid}.md")),
            "claims_hash": V._sha(os.path.join(docs, f"{aid}.claims.yml"))}


def _mk_instance(tmp, asset_id, claims_text, render_text):
    """tmp 에 interpretive 자산 1건(spec + claims + claude render) 배치 → root 반환."""
    subdir, aid = asset_id.split("/", 1)
    docs = os.path.join(tmp, "docs", "sage_harness", subdir)
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, f"{aid}.md"), "w", encoding="utf-8") as f:
        f.write("# spec\n")
    with open(os.path.join(docs, f"{aid}.claims.yml"), "w", encoding="utf-8") as f:
        f.write(claims_text)
    if render_text is not None:
        # 렌더 경로는 kind 별로 다르다: agent=.claude/agents/<id>.md(flat), skill=.claude/skills/<id>/SKILL.md(dir).
        if subdir == "skills":
            host = os.path.join(tmp, ".claude", "skills", aid)
            os.makedirs(host, exist_ok=True)
            render_file = os.path.join(host, "SKILL.md")
        else:
            host = os.path.join(tmp, ".claude", subdir)
            os.makedirs(host, exist_ok=True)
            render_file = os.path.join(host, f"{aid}.md")
        with open(render_file, "w", encoding="utf-8") as f:
            f.write(render_text)
    return tmp


@unittest.skipUnless(_HAS_YAML, "pyyaml 미설치 — conformance INFO skip 되어 강제 teeth 무의미")
class TestConformanceWiring(unittest.TestCase):
    def test_render_absent_skips(self):
        # render(.md) 미존재 → conformance skip(미렌더 interpretive). 정상 스탬프 entry → staleness 무 → PASS.
        with tempfile.TemporaryDirectory() as tmp:
            root = _mk_instance(tmp, "agents/x", _CLAIMS, render_text=None)
            sev, msgs = V._validate_interpretive(root, "agents/x", _stamped_entry(root, "agents/x"), run_regression=False)
            self.assertEqual(sev, "PASS")

    def test_missing_required_claim_is_fail(self):
        # render 가 owned_paths(src/foo/**) 를 누락 → conformance FAIL → validate FAIL(강제).
        bad = "This agent follows docs/backend.md conventions but never declares its paths."
        with tempfile.TemporaryDirectory() as tmp:
            root = _mk_instance(tmp, "agents/x", _CLAIMS, render_text=bad)
            sev, msgs = V._validate_interpretive(root, "agents/x", {}, run_regression=False)
            self.assertEqual(sev, "FAIL")
            self.assertTrue(any("conformance" in m and "owned_paths" in m for m in msgs), msgs)

    def test_clean_render_passes(self):
        # render 가 모든 required token 포함 + 금지 claim 없음 + 정상 스탬프 → PASS.
        good = "Owns src/foo/** paths. Follows docs/backend.md conventions for the backend."
        with tempfile.TemporaryDirectory() as tmp:
            root = _mk_instance(tmp, "agents/x", _CLAIMS, render_text=good)
            sev, msgs = V._validate_interpretive(root, "agents/x", _stamped_entry(root, "agents/x"), run_regression=False)
            self.assertEqual(sev, "PASS", msgs)

    def test_forbidden_contradiction_is_fail(self):
        # render 가 금지(git commit/push) 위반 → conformance FAIL → validate FAIL.
        contra = "Owns src/foo/** paths. The agent will git commit changes automatically."
        with tempfile.TemporaryDirectory() as tmp:
            root = _mk_instance(tmp, "agents/x", _CLAIMS_FORBIDDEN, render_text=contra)
            sev, msgs = V._validate_interpretive(root, "agents/x", {}, run_regression=False)
            self.assertEqual(sev, "FAIL")
            self.assertTrue(any("금지위반" in m for m in msgs), msgs)

    def test_hashless_interpretive_is_stale(self):
        # spec/claims 는 있으나 hash 미등록(entry={}) → STALE(미스탬프) — hook/mcp 와 대칭.
        with tempfile.TemporaryDirectory() as tmp:
            root = _mk_instance(tmp, "agents/x", _CLAIMS, render_text=None)
            sev, msgs = V._validate_interpretive(root, "agents/x", {}, run_regression=False)
            self.assertEqual(sev, "STALE")
            self.assertTrue(any("미스탬프" in m for m in msgs), msgs)

    def test_partial_hash_interpretive_is_stale(self):
        # spec_hash 만 있고 claims_hash 부재(레거시 부분스탬프) → STALE(drift 마스킹 방지).
        with tempfile.TemporaryDirectory() as tmp:
            root = _mk_instance(tmp, "agents/x", _CLAIMS, render_text=None)
            spec = os.path.join(root, "docs", "sage_harness", "agents", "x.md")
            sev, msgs = V._validate_interpretive(root, "agents/x", {"spec_hash": V._sha(spec)}, run_regression=False)
            self.assertEqual(sev, "STALE")

    def test_skill_subdir_resolves(self):
        # skills/ prefix → .claude/skills/<id>/SKILL.md 경로 해석(dir 기반, flat 아님 — codex 리뷰 P2).
        bad = "A skill that does things without declaring its owned paths."
        with tempfile.TemporaryDirectory() as tmp:
            root = _mk_instance(tmp, "skills/y", _CLAIMS, render_text=bad)
            sev, msgs = V._validate_interpretive(root, "skills/y", {}, run_regression=False)
            self.assertEqual(sev, "FAIL")

    def test_helper_render_absent_returns_pass_empty(self):
        # _conformance_check 직접: render 부재 → ("PASS", []).
        with tempfile.TemporaryDirectory() as tmp:
            root = _mk_instance(tmp, "agents/z", _CLAIMS, render_text=None)
            claims_path = os.path.join(root, "docs", "sage_harness", "agents", "z.claims.yml")
            sev, msgs = V._conformance_check(root, "agents/z", claims_path)
            self.assertEqual((sev, msgs), ("PASS", []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
