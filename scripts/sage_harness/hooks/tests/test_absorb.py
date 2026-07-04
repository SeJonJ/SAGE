#!/usr/bin/env python3
"""sage absorb 검증 (중 등급 — 직접수정 → spec patch 제안).

self-contained: 임시 SAGE 루트 + 합성 산출물로 claims diff 흡수 제안 확인.
파일 IO 는 pathlib(write_text/read_bytes) — 핸들 누수(ResourceWarning) 없음.
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

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


def _w(path, text):
    """텍스트 쓰고 경로 반환(누수 없는 한 줄 헬퍼)."""
    Path(path).write_text(text, encoding="utf-8")
    return path


def _sha(p):
    return "sha256:" + hashlib.sha256(Path(p).read_bytes()).hexdigest()


def setup_hook_root(d, edited=False):
    """native hook(demo.sh) + manifest 스탬프. edited=True 면 스탬프 후 정본 변경(divergence)."""
    H = os.path.join(d, "scripts", "sage_harness", "hooks")
    os.makedirs(H, exist_ok=True)
    os.makedirs(os.path.join(d, "docs", "sage_harness"), exist_ok=True)
    native = _w(os.path.join(H, "demo.sh"), "#!/bin/bash\necho ok\n")
    h = _sha(native)
    if edited:
        _w(native, "#!/bin/bash\necho EDITED\n")   # 스탬프 후 직접수정
    _w(os.path.join(d, "docs", "sage_harness", ".manifest.json"),
       json.dumps({"sage_version": "0.1.0", "host_runtime": "claude", "assets": {
           "hooks/demo": {"form": "native", "canonical_hash": h, "render_hash": {"native": h}, "conformance": "PASS"}}}))


def setup_root(d, claims_yaml):
    os.makedirs(os.path.join(d, "docs", "sage_harness", "agents"), exist_ok=True)
    _w(os.path.join(d, "docs", "sage_harness", ".manifest.json"),
       json.dumps({"sage_version": "0.1.0", "host_runtime": "claude", "assets": {}}))
    _w(os.path.join(d, "docs", "sage_harness", "agents", "demo.claims.yml"), claims_yaml)
    # config 모듈은 테스트 임시 root 에 쓴다(소스트리 오염 금지 — read-only 샌드박스 격리).
    # absorb 가 root/scripts/sage_harness 를 sys.path 에 추가하므로 거기서 import 됨.
    sh = os.path.join(d, "scripts", "sage_harness")
    os.makedirs(sh, exist_ok=True)
    _w(os.path.join(sh, "extract_config_demo_absorb.py"),
       'CFG = {"component_path_globs": [r"myapp/[\\w./-]+"], "guide_boundary_tokens": ["commit","push"], "signal_rules": []}\n')


class Args:
    def __init__(self, **kw):
        self.kind = "agent"; self.id = "demo"; self.from_blocked_diff = False; self.from_retro = None
        self.claude = ""; self.codex = ""; self.guide = ""; self.config = DEMO_CONFIG; self.root = None
        self.__dict__.update(kw)


def run_absorb(args):
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(out):
        rc = absorb.run(args)
    return rc, out.getvalue()


class TestAbsorb(unittest.TestCase):
    def tearDown(self):
        # tempdir 별 config 재import 보장(캐시 격리). 소스트리엔 더는 쓰지 않음.
        sys.modules.pop("extract_config_demo_absorb", None)

    def test_no_change(self):
        with tempfile.TemporaryDirectory() as d:
            # 현 claims 에 myapp/src/core + docs/a.md 이미 있음 → 변경 없음
            setup_root(d, 'required_claims:\n  - { type: owned_paths, value: "myapp/src/core", confidence: high }\n'
                          '  - { type: convention_doc, value: "docs/a.md", confidence: high }\n'
                          'forbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n')
            g = _w(os.path.join(d, "g.md"), GUIDE)
            c = _w(os.path.join(d, "c.md"), BASE)
            x = _w(os.path.join(d, "x.md"), BASE)
            rc, out = run_absorb(Args(claude=c, codex=x, guide=g, root=d))
            self.assertEqual(rc, 0)
            self.assertIn("변경 없음", out)

    def test_added_claim(self):
        with tempfile.TemporaryDirectory() as d:
            setup_root(d, 'required_claims:\n  - { type: owned_paths, value: "myapp/src/core", confidence: high }\n'
                          'forbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n')
            g = _w(os.path.join(d, "g.md"), GUIDE)
            # 양쪽에 docs/a.md 추가 → +required 제안
            c = _w(os.path.join(d, "c.md"), BASE)
            x = _w(os.path.join(d, "x.md"), BASE)
            rc, out = run_absorb(Args(claude=c, codex=x, guide=g, root=d))
            self.assertEqual(rc, 0)
            self.assertIn("+ required:   docs/a.md", out)

    def test_one_sided_unresolved(self):
        with tempfile.TemporaryDirectory() as d:
            setup_root(d, 'required_claims:\n  - { type: owned_paths, value: "myapp/src/core", confidence: high }\n'
                          '  - { type: convention_doc, value: "docs/a.md", confidence: high }\n'
                          'forbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n')
            g = _w(os.path.join(d, "g.md"), GUIDE)
            c = _w(os.path.join(d, "c.md"), BASE + "소유: myapp/src/onlyc\n")
            x = _w(os.path.join(d, "x.md"), BASE)
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
            _w(os.path.join(d, "docs", "sage_harness", ".manifest.json"),
               json.dumps({"sage_version": "0.1.0", "host_runtime": "claude", "assets": {}}))
            _w(os.path.join(d, "docs", "sage_harness", "skills", "demo.claims.yml"),
               "required_claims:\nforbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n")
            g = _w(os.path.join(d, "g.md"), GUIDE)
            c = _w(os.path.join(d, "c.md"), SKILL_C)
            x = _w(os.path.join(d, "x.md"), SKILL_C)
            rc, out = run_absorb(Args(kind="skill", id="demo", claude=c, codex=x, guide=g, config="", root=d))
            self.assertEqual(rc, 0)
            self.assertIn("docs/demo_conv.md", out)   # uses(convention doc) +required
            self.assertIn("skill:demo", out)          # 헤더가 skill 경로

    def test_agent_missing_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            setup_root(d, "required_claims:\nforbidden_claims:\nruntime_delta_allowlist:\nunresolved: []\n")
            rc, out = run_absorb(Args(root=d))  # claude/codex 없음
            self.assertEqual(rc, 2)

    def test_missing_kind_id_without_retro(self):
        # --from-retro 없이 --kind/--id 누락 → 안내(exit 2).
        rc, out = run_absorb(Args(kind=None, id=None))
        self.assertEqual(rc, 2)
        self.assertIn("--kind", out)


# --- 7.8단계 B: absorb --from-retro (승인 retro 노트 → 자산 patch 후보) ---
_RETRO_NOTE = ('---\napproved: {approved}\nstatus: "pending-review"\n---\n'
               '## 증거\n```\naccepted=3\n```\n'
               '## 제안 (proposals)\n```json\n{proposals}\n```\n')


def _retro_note(d, approved="true", proposals=None):
    if proposals is None:
        proposals = ('[{"pattern":"payment null 누락","target":"profile",'
                     '"proposed_change":"risk.l3_content_keywords += payment","confidence":"high","evidence":["f-1"]},'
                     '{"target":"agent","proposed_change":"reviewer 경계값 체크리스트","confidence":"med"}]')
    p = os.path.join(d, "sage-retro-x.md")
    Path(p).write_text(_RETRO_NOTE.format(approved=approved, proposals=proposals), encoding="utf-8")
    return p


class TestAbsorbFromRetro(unittest.TestCase):
    def test_approved_emits_grouped_proposals(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out = run_absorb(Args(from_retro=_retro_note(d, "true")))
            self.assertEqual(rc, 0, out)
            self.assertIn("기계적 누락 → profile / hook", out)
            self.assertIn("risk.l3_content_keywords", out)
            self.assertIn("의미적 누락 → agent / skill", out)
            self.assertIn("자동 반영하지 않음", out)

    def test_proposals_anchored_to_heading_not_decoy(self):
        # codex P2: 안내문의 백틱 `## 제안` 언급 + `## 요약` 안의 JSON 코드블록(decoy)이 있어도
        # 실제 `## 제안` 헤딩 라인에서만 잘라 진짜 제안을 흡수해야 한다.
        with tempfile.TemporaryDirectory() as d:
            note = ('---\napproved: true\nstatus: "x"\n---\n'
                    '> 안내: `## 제안` JSON 을 채우세요.\n\n'
                    '## 요약\n```json\n[{"pattern":"DECOY","target":"profile","proposed_change":"WRONG"}]\n```\n\n'
                    '## 제안 (proposals)\n```json\n[{"pattern":"REAL","target":"agent","proposed_change":"RIGHT","confidence":"high","evidence":["f-1"]}]\n```\n')
            p = os.path.join(d, "n.md")
            Path(p).write_text(note, encoding="utf-8")
            rc, out = run_absorb(Args(from_retro=p))
            self.assertEqual(rc, 0, out)
            self.assertIn("RIGHT", out)
            self.assertNotIn("WRONG", out)

    def test_unapproved_refused(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out = run_absorb(Args(from_retro=_retro_note(d, "false")))
            self.assertEqual(rc, 2)
            self.assertIn("승인되지 않음", out)

    def test_missing_note(self):
        rc, out = run_absorb(Args(from_retro="/no/such/note.md"))
        self.assertEqual(rc, 2)
        self.assertIn("없음", out)

    def test_no_proposals_block(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "n.md")
            Path(p).write_text('---\napproved: true\n---\n## 증거\n```\nx\n```\n', encoding="utf-8")
            rc, out = run_absorb(Args(from_retro=p))
            self.assertEqual(rc, 2)
            self.assertIn("제안", out)

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out = run_absorb(Args(from_retro=_retro_note(d, "true", proposals="[not json")))
            self.assertEqual(rc, 2)
            self.assertIn("파싱 실패", out)

    def test_unknown_target_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            props = '[{"target":"weird","proposed_change":"x"}]'
            rc, out = run_absorb(Args(from_retro=_retro_note(d, "true", proposals=props)))
            self.assertEqual(rc, 0, out)
            self.assertIn("target 미지", out)

    def test_empty_proposals(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out = run_absorb(Args(from_retro=_retro_note(d, "true", proposals="[]")))
            self.assertEqual(rc, 0, out)
            self.assertIn("제안 없음", out)

    # --- codex B 후속 ---
    def test_non_dict_item_no_crash(self):
        # P1: 배열에 비-dict 항목(숫자) 섞여도 크래시 없이 처리(skipped 로 표시).
        with tempfile.TemporaryDirectory() as d:
            props = '[1, {"target":"profile","proposed_change":"x"}]'
            rc, out = run_absorb(Args(from_retro=_retro_note(d, "true", proposals=props)))
            self.assertEqual(rc, 0, out)
            self.assertIn("dict 아님", out)
            self.assertIn("risk", out) if "risk" in out else None   # profile 제안은 정상 표시

    def test_unhashable_target_no_crash(self):
        # codex B: target 이 list(unhashable)여도 set membership 크래시 없이 skipped 처리.
        with tempfile.TemporaryDirectory() as d:
            props = '[{"target":["profile"],"proposed_change":"x"}, {"target":"profile","proposed_change":"y"}]'
            rc, out = run_absorb(Args(from_retro=_retro_note(d, "true", proposals=props)))
            self.assertEqual(rc, 0, out)
            self.assertIn("target 미지", out)   # 비-str target → skipped
            self.assertIn("y", out)              # 정상 proposal 은 분류됨

    def test_explanatory_block_before_json(self):
        # P2: ## 제안 뒤 설명용 비-json 블록이 먼저 와도 뒤의 JSON 배열 블록을 찾음.
        note = ('---\napproved: true\n---\n## 증거\n```\nx\n```\n'
                '## 제안 (proposals)\n```text\n여기에 설명\n```\n'
                '```json\n[{"target":"profile","proposed_change":"risk += y"}]\n```\n')
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "n.md"); Path(p).write_text(note, encoding="utf-8")
            rc, out = run_absorb(Args(from_retro=p))
            self.assertEqual(rc, 0, out)
            self.assertIn("risk += y", out)

    def test_no_auto_apply_writes_nothing(self):
        # 자동반영 금지: --from-retro 가 어떤 파일도 생성/수정하지 않음.
        with tempfile.TemporaryDirectory() as d:
            note = _retro_note(d, "true")
            before = {p: os.path.getmtime(p) for p in [note]}
            files_before = set(os.listdir(d))
            run_absorb(Args(from_retro=note))
            self.assertEqual(set(os.listdir(d)), files_before)   # 새 파일 없음
            self.assertEqual(os.path.getmtime(note), before[note])  # 노트 불변


if __name__ == "__main__":
    unittest.main(verbosity=2)
