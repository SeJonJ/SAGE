#!/usr/bin/env python3
"""sage retro 단위 — Loop C(Act→Plan process-absorb) 증거 수집 + distiller 제시(자동반영 없음).

검증:
  1. loop_audit run + 05 문서 → 감사요약·문서경로·distiller 프롬프트·human-gate 경로 출력
  2. --run-id 특정 / --feature 경로 필터
  3. loop_audit 없음 → 안내(여전히 05 문서/프롬프트 제시)
  4. 05 문서 없음 → 안내
  5. proposal-only: 어떤 파일도 쓰지 않음(자동반영 없음)
  6. 루트 자동탐색(profile 마커)
  7. 무결성 경고 표면화
  8. 노트 제목 stem: --feature > 유일한 05 문서명 > run_id 폴백(+힌트)
  9. --check: 빈 템플릿/무효 제안 non-zero, 채워진 노트 0
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import retro as retro_command  # noqa: E402


def sage_review_loop(*args, root):
    subprocess.run([sys.executable, "-m", "sage", "review-loop", *args, "--root", root],
                   cwd=REPO, capture_output=True, text=True)


def retro(*args, root, cwd=None):
    cmd = [sys.executable, "-m", "sage", "retro", *args]
    if root:
        cmd += ["--root", root]
    return subprocess.run(cmd, cwd=cwd or REPO, capture_output=True, text=True)


def retro_lang(lang, *args, root, cwd=None):
    cmd = [sys.executable, "-m", "sage", "--lang", lang, "retro", *args]
    if root:
        cmd += ["--root", root]
    return subprocess.run(cmd, cwd=cwd or REPO, capture_output=True, text=True)


class _ProjectFixture:
    """profile 마커 + 05 문서 + 닫힌 loop_audit run 을 갖춘 임시 프로젝트(테스트 클래스 간 공유)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "sage"), exist_ok=True)
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("pdca:\n  approve_phase: \"05\"\n  phases:\n"
                    "    - { id: \"05\", glob: \"plan_docs/05-expert-review/**/*.md\" }\n"
                    "  review_loop: { enabled: true, lenses: [security], refuters: 2 }\n")

    def _add_05(self, stem="feat-x"):
        d = os.path.join(self.tmp, "plan_docs", "05-expert-review")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"{stem}-review.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("## Phase-05 Review\nFinal Status: APPROVED\n")
        return p

    def _vault(self):
        v = os.path.join(self.tmp, "vault")
        os.makedirs(v, exist_ok=True)
        return v

    def _note_path(self, vault):
        hits = [os.path.join(dp, fn) for dp, _, fs in os.walk(vault) for fn in fs
                if fn.endswith(".md") and " retro " in fn]
        self.assertEqual(len(hits), 1, f"retro 노트 1건이어야: {hits}")
        return hits[0]

    def _run_loop(self, risk="L3", cycle_stem=None):
        cmd = [sys.executable, "-m", "sage", "review-loop", "open", "--risk", risk, "--root", self.tmp]
        if cycle_stem:
            cmd += ["--cycle-stem", cycle_stem]
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        rid = r.stdout.strip().splitlines()[0]
        sage_review_loop("round", "--run-id", rid, "--iteration", "1", "--found", "7",
                         "--survived", "3", "--accepted", "3", "--tokens", "48000", root=self.tmp)
        sage_review_loop("close", "--run-id", rid, "--result", "APPROVED", "--reason", "DRY",
                         "--iterations", "1", root=self.tmp)
        return rid


class TestRetro(_ProjectFixture, unittest.TestCase):
    def test_profile_loader_applies_local_knowledge_disable(self):
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "a", encoding="utf-8") as f:
            f.write("knowledge_capture:\n  retro_note: true\n  vault_path: /shared-vault\n")
        with open(os.path.join(self.tmp, "sage", "project-profile.local.yaml"), "w", encoding="utf-8") as f:
            f.write("knowledge_capture:\n  enabled: false\n")

        profile, broken = retro_command._load_profile(self.tmp)

        self.assertIsNone(broken)
        self.assertFalse(profile["knowledge_capture"]["enabled"])
        self.assertEqual(profile["knowledge_capture"]["vault_path"], "")

    def test_full_evidence_and_prompt(self):
        rid = self._run_loop()
        self._add_05()
        r = retro(root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(rid, r.stdout)
        self.assertIn("accepted=3", r.stdout)         # 감사 요약
        self.assertIn("feat-x-review.md", r.stdout)   # 05 문서
        self.assertIn("distiller", r.stdout)          # 프롬프트
        self.assertIn("자동반영", r.stdout)            # human-gate 경고
        self.assertIn("COMPOSE_ALLOWED", r.stdout)    # blocked 자산에 overlay 경로를 권장하지 않음
        self.assertIn("blocked/gate-bearing", r.stdout)

    def test_proposal_only_writes_nothing(self):
        self._run_loop()
        self._add_05()
        before = set()
        for dp, _, fs in os.walk(self.tmp):
            for fn in fs:
                before.add(os.path.join(dp, fn))
        retro(root=self.tmp)
        after = set()
        for dp, _, fs in os.walk(self.tmp):
            for fn in fs:
                after.add(os.path.join(dp, fn))
        self.assertEqual(before, after, "retro 가 파일을 생성/수정함(자동반영 금지 위반)")

    def test_no_loop_audit_still_runs(self):
        self._add_05()
        r = retro(root=self.tmp)   # loop_audit 없음
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("기록 없음", r.stdout)
        self.assertIn("feat-x-review.md", r.stdout)   # 05 문서는 여전히 제시

    def test_no_05_doc_noted(self):
        self._run_loop()           # 05 문서 없음
        r = retro(root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("없음", r.stdout)

    def test_feature_filter(self):
        self._run_loop()
        self._add_05("alpha")
        self._add_05("beta")
        r = retro("--feature", "alpha", root=self.tmp)
        self.assertIn("alpha-review.md", r.stdout)
        self.assertNotIn("beta-review.md", r.stdout)

    def test_feature_filter_token_boundary(self):
        # codex S4 P3: 'loop' 이 'preloop' 을 오매치하면 안 됨(토큰 경계 매치).
        self._run_loop()
        self._add_05("loop-engineering")
        self._add_05("preloop")
        r = retro("--feature", "loop", root=self.tmp)
        self.assertIn("loop-engineering-review.md", r.stdout)
        self.assertNotIn("preloop-review.md", r.stdout)

    def test_feature_filter_dot_left_boundary(self):
        # codex S4: 좌측 경계 '.' 포함 — alpha.loop-review.md 가 --feature loop 에 매치(주석 -/_/. 일치).
        self._run_loop()
        self._add_05("alpha.loop")
        r = retro("--feature", "loop", root=self.tmp)
        self.assertIn("alpha.loop-review.md", r.stdout)

    def _read_audit(self):
        import json as _json
        p = os.path.join(self.tmp, ".sage", "retro_audit.jsonl")
        if not os.path.isfile(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [_json.loads(l) for l in f if l.strip()]

    def test_no_vault_records_skip_event(self):
        # W4: --no-vault 실행이 이 run 의 skip 이벤트(reason=no_vault)를 retro_audit.jsonl 에 남긴다 →
        # Stop 게이트가 없는 노트의 --check 를 요구하지 않는다(--no-vault↔enforce 충돌 해소).
        rid = self._run_loop()
        self._add_05()
        r = retro("--no-vault", "--run-id", rid, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        recs = self._read_audit()
        self.assertEqual([(x["event"], x["run_id"], x.get("reason")) for x in recs],
                         [("retro_check_skipped", rid, "no_vault")])

    def test_no_vault_single_run_auto_binds(self):
        # run 이 정확히 1개면 --run-id 없이도 자동 결속(skip 기록).
        rid = self._run_loop()
        self._add_05()
        r = retro("--no-vault", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([(x["event"], x["run_id"]) for x in self._read_audit()],
                         [("retro_check_skipped", rid)])

    def test_no_vault_multi_run_requires_run_id(self):
        # run 이 2개↑인데 --run-id 없으면 모호 → rc 2, skip 미기록(엉뚱한 최신 run 자동 면제 방지).
        self._run_loop(); self._run_loop()
        self._add_05()
        r = retro("--no-vault", root=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self._read_audit(), [])   # 아무것도 안 남김

    def test_no_vault_multi_run_explicit_run_id_binds_only_that(self):
        # run 2개 + 명시 유효 --run-id → 그 run 만 skipped.
        rid1 = self._run_loop(); rid2 = self._run_loop()
        self._add_05()
        r = retro("--no-vault", "--run-id", rid1, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        recs = self._read_audit()
        self.assertEqual([x["run_id"] for x in recs], [rid1])   # rid2 는 건드리지 않음
        self.assertNotIn(rid2, [x["run_id"] for x in recs])

    def test_no_vault_feature_does_not_auto_skip_latest(self):
        # --feature 가 있어도 복수 run 에서 최신 run 이 자동 skip 되지 않는다(--run-id 필수 유지).
        self._run_loop(); self._run_loop()
        self._add_05("alpha")
        r = retro("--no-vault", "--feature", "alpha", root=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self._read_audit(), [])

    def test_no_vault_writes_no_note(self):
        # --no-vault 는 노트를 만들지 않는다(skip 기록만) — 파일 생성은 audit 한 줄뿐.
        rid = self._run_loop()
        self._add_05()
        retro("--no-vault", "--run-id", rid, root=self.tmp)
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "vault")))

    def test_no_vault_bogus_run_id_refused(self):
        # W4 게이트 우회 차단: 실재하지 않는 --run-id 로 skip 을 기록하려 하면 거부(rc 2)하고 아무것도 안 남긴다.
        self._run_loop()
        self._add_05()
        r = retro("--no-vault", "--run-id", "rl-victim", root=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, ".sage", "retro_audit.jsonl")))

    def test_no_vault_no_loop_run_records_nothing(self):
        # 결속할 loop_audit run 이 없으면(단발 리뷰) skip 미기록 — false 우회도 false BLOCK 도 아님(안내만).
        self._add_05()   # loop 없음
        r = retro("--no-vault", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, ".sage", "retro_audit.jsonl")))

    def test_no_vault_skip_write_failure_returns_2(self):
        # codex P1(teeth): skip 기록 실패는 rc 2(fail-fast) — 기록 안 된 skip 은 게이트가 못 봐 false BLOCK.
        rid = self._run_loop()
        self._add_05()
        # .sage/retro_audit.jsonl 자리에 디렉토리를 두어 append 를 실패시킨다.
        os.makedirs(os.path.join(self.tmp, ".sage", "retro_audit.jsonl"), exist_ok=True)
        r = retro("--no-vault", "--run-id", rid, root=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_corrupt_audit_line_surfaced(self):
        # codex S4 P2: 손상/비-dict 줄이 silent drop 되어도 retro 가 증거 불완전을 경고.
        self._run_loop()
        self._add_05()
        path = os.path.join(self.tmp, ".sage", "loop_audit.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write("{ truncated not json\n")
            f.write("42\n")   # valid-but-non-dict
        r = retro(root=self.tmp)
        self.assertIn("무결성", r.stdout)
        self.assertIn("손상", r.stdout)

    def test_root_autodiscovery_from_subdir(self):
        self._run_loop()
        self._add_05()
        subdir = os.path.join(self.tmp, "src", "deep")
        os.makedirs(subdir, exist_ok=True)
        r = subprocess.run([sys.executable, "-m", "sage", "retro"], cwd=subdir,
                           capture_output=True, text=True, env={**os.environ, "PYTHONPATH": REPO})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("feat-x-review.md", r.stdout)   # 루트 자동탐색 성공

    def test_integrity_warning_surfaced(self):
        # orphan round → retro 가 무결성 경고 표면화. `record_round` 는 lock 안에서 open 없는
        # run 을 거부하므로, 수기 편집이나 옛 클라이언트가 남긴 기록을 흉내 내 직접 append 한다.
        sys.path.insert(0, os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime"))
        import loop_audit as la
        la._append(la.audit_path(self.tmp),
                   {"event": "round", "run_id": "rl-ghost", "ts": "t", "epoch": 1,
                    "iteration": 1, "found": 1, "survived": 0, "accepted": 0,
                    "arch": 0, "tokens": 10})
        self._add_05()
        r = retro(root=self.tmp)
        self.assertIn("무결성", r.stdout)


class TestRetroNoteStem(_ProjectFixture, unittest.TestCase):
    """human-gate 노트 파일명이 사이클을 식별해야 한다(run_id 폴백은 최후수단)."""

    def _vault(self):
        v = os.path.join(self.tmp, "vault")
        os.makedirs(v, exist_ok=True)
        return v

    def _note(self, vault):
        hits = [os.path.join(dp, fn) for dp, _, fs in os.walk(vault) for fn in fs
                if fn.endswith(".md") and " retro " in fn]
        self.assertEqual(len(hits), 1, f"retro 노트 1건이어야: {hits}")
        return hits[0]

    def test_stem_from_single_05_doc(self):
        self._run_loop()
        self._add_05("feat-x")
        v = self._vault()
        r = retro("--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("feat-x-review", os.path.basename(self._note(v)))

    def test_feature_beats_doc_derivation(self):
        self._run_loop()
        self._add_05("alpha")
        self._add_05("beta")
        v = self._vault()
        retro("--feature", "alpha", "--vault", v, root=self.tmp)
        self.assertIn("alpha", os.path.basename(self._note(v)))

    def test_runid_fallback_emits_feature_hint(self):
        rid = self._run_loop()
        self._add_05("alpha")
        self._add_05("beta")   # 사이클 특정 불가 → run_id 폴백
        v = self._vault()
        r = retro("--vault", v, root=self.tmp)
        self.assertIn(rid, os.path.basename(self._note(v)))
        self.assertIn("--feature", r.stderr)

    def test_unicode_stem_preserved(self):
        # ASCII-only 로 깎으면 한글 사이클명이 통째로 사라져 제목이 다시 식별 불가가 된다.
        self._run_loop()
        self._add_05()
        v = self._vault()
        retro("--feature", "녹화-정리", "--vault", v, root=self.tmp)
        self.assertIn("녹화-정리", os.path.basename(self._note(v)))

    def test_second_run_same_day_gets_its_own_note(self):
        """codex P1: 파일명에 run_id 가 없어 create-only 가 앞 run 의 채워진 노트를 재사용 →
        이번 run 이 회고 없이 완료 게이트를 통과하던 우회."""
        rid1 = self._run_loop()
        self._add_05("alpha")
        v = self._vault()
        retro("--feature", "alpha", "--vault", v, root=self.tmp)
        rid2 = self._run_loop()
        self.assertNotEqual(rid1, rid2)
        retro("--feature", "alpha", "--run-id", rid2, "--vault", v, root=self.tmp)
        notes = [f for dp, _, fs in os.walk(v) for f in fs if " retro " in f]
        self.assertEqual(len(notes), 2, f"run 마다 별도 노트여야: {notes}")
        self.assertTrue(any(rid2 in n for n in notes), f"2번째 run 노트에 run suffix: {notes}")


class TestRetroCheck(unittest.TestCase):
    """--check: CLI 가 위임한 '노트 채우기'가 조용히 실패했는지 결정론 검사."""

    PROPOSALS = ('## 제안 (proposals)\n```json\n%s\n```\n')
    # 실제 노트는 제안 뒤에 구분선 + <details> 증거 블록이 붙는다.
    EVIDENCE = "\n---\n<details>\n<summary>증거</summary>\n\n```\n%s\n```\n\n</details>\n"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _head(self, run_id=None):
        rid = f"run_id: {run_id}\n" if run_id else ""
        return f"---\ntags: [sage]\napproved: false\n{rid}---\n\n"

    def _note(self, summary, proposals_json, evidence=None, run_id=None):
        p = os.path.join(self.tmp, "note.md")
        body = self._head(run_id) + "## 요약\n" + summary + "\n\n" + self.PROPOSALS % proposals_json
        if evidence is not None:
            body += self.EVIDENCE % evidence
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        return p

    def _check(self, path, *extra):
        # --root self.tmp: 9-C 부터 --check 성공이 .sage/retro_audit.jsonl 에 기록을 남긴다.
        # --root 없으면 root 가 cwd(REPO)로 폴백해 이 저장소 자신의 .sage/ 를 오염시킨다.
        return subprocess.run([sys.executable, "-m", "sage", "retro", "--check", path,
                               "--root", self.tmp, *extra],
                              cwd=REPO, capture_output=True, text=True)

    def test_untouched_template_fails(self):
        placeholder = "_이번 사이클에 체계적으로 놓친 것과 바꾸기로 한 것을 사람이 읽을 1~2줄로 (absorb 파싱 대상 아님)._"
        r = self._check(self._note(placeholder, "[]"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("요약", r.stderr)

    def test_filled_note_passes(self):
        r = self._check(self._note(
            "게이트 우회 패턴을 반복해 놓쳤다. hook 으로 승격.",
            '[{"pattern":"p","target":"hook","proposed_change":"pre-gate 확장","confidence":"high"}]'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("제안 1건", r.stdout)

    def test_summary_appended_below_placeholder_passes(self):
        placeholder = "_이번 사이클에 체계적으로 놓친 것과 바꾸기로 한 것을 사람이 읽을 1~2줄로 (absorb 파싱 대상 아님)._"
        r = self._check(self._note(
            placeholder + "\n\n리뷰가 잡은 누락은 전부 컨벤션 계열.",
            '[{"pattern":"p","target":"skill","proposed_change":"체크리스트 추가"}]'))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_empty_proposals_with_summary_passes_with_warning(self):
        r = self._check(self._note("구조적 패턴 없음 — 1회성 실수뿐.", "[]"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("제안 0건", r.stdout)

    def test_bad_target_fails(self):
        r = self._check(self._note("요약 있음.", '[{"pattern":"p","target":"readme","proposed_change":"x"}]'))
        self.assertEqual(r.returncode, 1)
        self.assertIn("target", r.stderr)

    def test_empty_proposed_change_fails(self):
        r = self._check(self._note("요약 있음.", '[{"pattern":"p","target":"hook","proposed_change":"  "}]'))
        self.assertEqual(r.returncode, 1)
        self.assertIn("proposed_change", r.stderr)

    def test_malformed_json_fails(self):
        r = self._check(self._note("요약 있음.", "{not json"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("제안", r.stderr)

    def test_missing_note_is_tool_error(self):
        r = self._check(os.path.join(self.tmp, "nope.md"))
        self.assertEqual(r.returncode, 2)

    def test_directory_path_is_tool_error_not_traceback(self):
        # exists() 는 디렉토리에도 참 → read() 가 IsADirectoryError 로 터졌었다(e2e 발견).
        r = self._check(self.tmp)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_malformed_proposals_not_masked_by_later_json_block(self):
        """codex P1: 파서가 문서 끝까지 훑어, 뒤 <details> 의 `[]` 가 망가진 제안을 덮고
        '제안 0건 PASS' 로 통과시켰다. 섹션 경계 + JSON 유사 블록 하드실패로 차단."""
        r = self._check(self._note("요약 있음.", "{ broken json", evidence="[]"))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("파싱 실패", r.stderr)

    def test_evidence_json_array_is_not_read_as_proposals(self):
        # 증거 블록이 우연히 JSON 배열이어도 제안으로 채택되면 안 된다(섹션 경계).
        r = self._check(self._note("요약 있음.", "[]",
                                   evidence='[{"target":"hook","proposed_change":"증거일 뿐"}]'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("제안 0건", r.stdout)   # 증거 블록을 제안으로 오독하지 않음

    def _write(self, body):
        p = os.path.join(self.tmp, "note.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        return p

    def test_prose_block_before_json_still_accepted(self):
        # 기존 계약 보존(absorb codex B P2): 설명용 프로즈 블록이 앞서도 뒤의 JSON 배열을 찾는다.
        r = self._check(self._write(
            self._head() + "## 요약\n요약 있음.\n\n## 제안 (proposals)\n"
            "```text\n여기에 설명\n```\n"
            '```json\n[{"target":"profile","proposed_change":"risk += y"}]\n```\n'))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_brace_prose_block_is_skipped_not_hard_failed(self):
        # codex 재검토 P1 회귀: `{` 로 시작하는 설명 블록을 JSON 후보로 오인해 하드실패시켰다.
        r = self._check(self._write(
            self._head() + "## 요약\n요약 있음.\n\n## 제안 (proposals)\n"
            "```text\n{패턴을 여기 적으세요}\n```\n"
            '```json\n[{"target":"hook","proposed_change":"x"}]\n```\n'))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_hr_inside_fence_does_not_end_section(self):
        # codex 재검토 P1 회귀: 펜스 안의 `---` 를 섹션 끝으로 오인해 '코드블록 없음' 이 됐다.
        r = self._check(self._write(
            self._head() + "## 요약\n요약 있음.\n\n## 제안 (proposals)\n"
            "```text\n설명\n---\n더 설명\n```\n"
            '```json\n[{"target":"hook","proposed_change":"x"}]\n```\n'))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_h3_heading_bounds_section(self):
        # codex 재검토 P1 회귀: h3 는 경계로 안 봐서 `### 증거` 아래 `[]` 를 제안으로 채택했다.
        r = self._check(self._write(
            self._head() + "## 요약\n요약 있음.\n\n## 제안 (proposals)\n"
            "```text\n아직 안 채움\n```\n"
            "### 증거\n```json\n[]\n```\n"))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("제안", r.stderr)

    def test_run_id_mismatch_fails(self):
        """codex P1: 같은 stem/날짜의 앞 run 노트가 재사용되면 이미 채워져 있어 통과한다.
        --run-id 대조로 '다른 사이클의 회고'를 차단."""
        note = self._note("요약 있음.", '[{"target":"hook","proposed_change":"x"}]', run_id="rl-aaa")
        self.assertEqual(self._check(note, "--run-id", "rl-aaa").returncode, 0)
        r = self._check(note, "--run-id", "rl-bbb")
        self.assertEqual(r.returncode, 1)
        self.assertIn("run_id", r.stderr)

    def test_missing_run_id_on_bound_note_fails(self):
        # codex 재검토 P1: --run-id 를 빠뜨리면 결속 검사가 통째로 꺼진다 → 생략 자체를 실패로.
        note = self._note("요약 있음.", '[{"target":"hook","proposed_change":"x"}]', run_id="rl-aaa")
        r = self._check(note)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--run-id", r.stderr)

    def test_frontmatter_inline_comment_not_misread(self):
        # codex 재검토 P2: `run_id: "rl-aaa" # 메모` 가 `rl-aaa" # 메모` 로 오독되면 false mismatch.
        p = os.path.join(self.tmp, "note.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write('---\napproved: false\nrun_id: "rl-aaa"   # 사람이 단 메모\n---\n\n'
                    "## 요약\n요약 있음.\n\n" + self.PROPOSALS % '[{"target":"hook","proposed_change":"x"}]')
        r = self._check(p, "--run-id", "rl-aaa")
        self.assertEqual(r.returncode, 0, r.stderr)

    def _audit_records(self):
        import json
        path = os.path.join(self.tmp, ".sage", "retro_audit.jsonl")
        if not os.path.isfile(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def test_success_appends_retro_audit_record(self):
        # 9-C: Stop 훅(retro_gate)이 대조할 성공 증거. run_id·note_path·digest·ts 필요.
        note = self._note("요약 있음.", '[{"target":"hook","proposed_change":"x"}]', run_id="rl-aaa")
        r = self._check(note, "--run-id", "rl-aaa")
        self.assertEqual(r.returncode, 0, r.stderr)
        recs = self._audit_records()
        self.assertEqual(1, len(recs))
        self.assertEqual(recs[0]["run_id"], "rl-aaa")
        self.assertEqual(recs[0]["event"], "retro_check_ok")
        self.assertTrue(recs[0]["digest"])
        self.assertEqual(64, len(recs[0]["digest"]))   # 전체 SHA-256(잘라쓰지 않음)

    def test_failure_does_not_append_retro_audit_record(self):
        # 내용검사가 실패하면 audit 에 "성공했다"는 흔적을 남기면 안 된다.
        note = self._note(
            "_이번 사이클에 체계적으로 놓친 것과 바꾸기로 한 것을 사람이 읽을 1~2줄로 (absorb 파싱 대상 아님)._",
            "[]", run_id="rl-aaa")
        r = self._check(note, "--run-id", "rl-aaa")
        self.assertEqual(r.returncode, 1)
        self.assertEqual([], self._audit_records())

    def test_no_resolvable_run_id_skips_audit_silently(self):
        # --run-id 도 없고 노트도 run_id 를 선언 안 하면(임시/수기 실행) 대조 대상이 없어 조용히 건너뛴다.
        note = self._note("요약 있음.", '[{"target":"hook","proposed_change":"x"}]')
        r = self._check(note)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([], self._audit_records())

    def test_audit_append_failure_is_fail_closed(self):
        # 기록 자체가 실패하면(디스크 문제 등) 내용검사가 통과해도 --check 는 실패해야 한다 —
        # 기록되지 않은 성공은 게이트가 못 보는 성공과 같다.
        os.makedirs(os.path.join(self.tmp, ".sage"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, ".sage", "retro_audit.jsonl"), exist_ok=True)   # 파일 자리에 디렉토리
        note = self._note("요약 있음.", '[{"target":"hook","proposed_change":"x"}]', run_id="rl-aaa")
        r = self._check(note, "--run-id", "rl-aaa")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("retro_audit", r.stderr)


class TestRetroLanguageContract(_ProjectFixture, unittest.TestCase):
    """retro heading/placeholder 계약이 ko/en 양쪽에서 대칭으로 동작해야 한다(§4c/§4d SSOT).

    heading 텍스트는 catalog(cli.retro.heading_summary/heading_proposals) 가 유일한 소스이고,
    _summary_body/absorb._PROPOSAL_HEADING 은 거기서 정규식을 조립한다 — 노트 판정(placeholder 검출,
    heading 인식)은 --lang 이 아니라 노트가 실제로 어떤 언어로 쓰였는지에 매인다."""

    def test_ko_note_has_ko_headings_and_placeholder(self):
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro("--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self._note_path(v)).read_text(encoding="utf-8")
        self.assertIn("## 요약\n", text)
        self.assertIn("## 제안", text)
        self.assertIn("이번 사이클에 체계적으로 놓친 것", text)

    def test_en_note_under_lang_en_when_the_cycle_declares_nothing(self):
        # 이 fixture 는 Phase 00 계약이 없어 사이클이 문서 언어를 선언하지 않은 상태다. 그때만
        # 노트가 표시 언어를 따른다 — 선언이 있으면 선언이 이긴다
        # (TestRetroNoteFollowsDocumentLanguage 가 그쪽 계약을 고정한다).
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro_lang("en", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self._note_path(v)).read_text(encoding="utf-8")
        self.assertIn("## Summary\n", text)
        self.assertIn("## Proposals", text)
        self.assertIn("systematically missed", text)
        # heading·placeholder·안내문 자체는 영어 — distiller 프롬프트([LANGUAGE] 계약, (c) 분류)는
        # 표시 언어와 무관하게 원문(한국어)을 유지하므로 <details> 블록에는 한국어가 남는다(의도됨).
        self.assertNotIn("## 요약", text)
        self.assertNotIn("## 제안", text)

    def test_en_note_passes_check_under_default_ko(self):
        # 노트가 영어로 작성돼도 --check 는 기본(ko) 표시 언어에서 통과해야 한다 — 노트 구조 판정은
        # 표시 언어가 아니라 노트가 실제로 쓰인 언어에 매인다.
        note = os.path.join(self.tmp, "note.md")
        Path(note).write_text(
            '---\napproved: false\n---\n\n'
            '## Summary\nRepeatedly missed a gate-bypass pattern. Promoting to hook.\n\n'
            '## Proposals\n```json\n'
            '[{"pattern":"p","target":"hook","proposed_change":"extend pre-gate","confidence":"high"}]\n'
            '```\n', encoding="utf-8")
        r = retro("--check", note, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_ko_note_passes_check_under_lang_en(self):
        # 기존(레거시) 한국어 노트가 --lang en 에서도 --check 를 통과해야 한다.
        note = os.path.join(self.tmp, "note.md")
        Path(note).write_text(
            '---\napproved: false\n---\n\n'
            '## 요약\n게이트 우회 패턴을 반복해 놓쳤다. hook 으로 승격.\n\n'
            '## 제안 (proposals)\n```json\n'
            '[{"pattern":"p","target":"hook","proposed_change":"pre-gate 확장","confidence":"high"}]\n'
            '```\n', encoding="utf-8")
        r = retro_lang("en", "--check", note, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_wrong_language_placeholder_still_fails_default_ko(self):
        # EN placeholder 가 그대로 남아 있으면(사람이 안 지움) 기본(ko) --check 도 실패해야 한다 —
        # placeholder 판정은 ko/en 어느 catalog 값이든(--lang 과 무관하게) 검출한다.
        placeholder_en = ("_A one- or two-line, human-readable note on what this cycle "
                          "systematically missed and what you're changing (not parsed by absorb)._")
        note = os.path.join(self.tmp, "note.md")
        Path(note).write_text(
            f'---\napproved: false\n---\n\n## 요약\n{placeholder_en}\n\n'
            '## 제안 (proposals)\n```json\n[]\n```\n', encoding="utf-8")
        r = retro("--check", note, root=self.tmp)
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_wrong_language_placeholder_still_fails_lang_en(self):
        placeholder_ko = ("_이번 사이클에 체계적으로 놓친 것과 바꾸기로 한 것을 사람이 읽을 "
                          "1~2줄로 (absorb 파싱 대상 아님)._")
        note = os.path.join(self.tmp, "note.md")
        Path(note).write_text(
            f'---\napproved: false\n---\n\n## Summary\n{placeholder_ko}\n\n'
            '## Proposals\n```json\n[]\n```\n', encoding="utf-8")
        r = retro_lang("en", "--check", note, root=self.tmp)
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_judgment_and_run_id_binding_unchanged_under_lang_en(self):
        # 판정 계층(run_id 결속·감사 기록)이 --lang 과 무관하게 동일해야 한다.
        rid = self._run_loop()
        self._add_05()
        note = os.path.join(self.tmp, "note.md")
        Path(note).write_text(
            f'---\napproved: false\nrun_id: {rid}\n---\n\n'
            '## Summary\nfilled.\n\n'
            '## Proposals\n```json\n[{"target":"hook","proposed_change":"x"}]\n```\n', encoding="utf-8")
        r = retro_lang("en", "--check", note, "--run-id", rid, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        p = os.path.join(self.tmp, ".sage", "retro_audit.jsonl")
        with open(p, encoding="utf-8") as f:
            recs = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(recs[0]["run_id"], rid)
        self.assertEqual(recs[0]["event"], "retro_check_ok")


class TestRetroNoteFollowsDocumentLanguage(_ProjectFixture, unittest.TestCase):
    """노트 *안으로* 들어가는 문자열은 표시 언어가 아니라 사이클의 선언 언어를 따른다.

    표시 언어는 실행 하나의 성질이고 문서 언어는 사이클 전체의 성질이다. 노트를 표시 언어로 쓰면
    `Document-Language: en` 사이클의 증거에 한국어 산문이 남고, 역사 증거는 나중에 재번역하지
    않으므로 그대로 굳는다. 특히 [LANGUAGE] 지시문은 문서 언어가 무엇인지 *단언*하는 문장이라,
    표시 언어로 렌더하면 사실과 반대되는 지시가 distiller 에게 나간다.

    stderr 안내·경고는 화면이므로 표시 언어를 유지한다(같은 실행에서 두 언어가 갈린다).
    """

    def _profile_with_phase00(self, glob="plan_docs/00-base_plan/**/*.md"):
        with open(os.path.join(self.tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
            f.write("pdca:\n  approve_phase: \"05\"\n  phases:\n"
                    f"    - {{ id: \"00\", glob: \"{glob}\" }}\n"
                    "    - { id: \"05\", glob: \"plan_docs/05-expert-review/**/*.md\" }\n"
                    "  review_loop: { enabled: true, lenses: [security], refuters: 2 }\n")

    def _add_00(self, stem="feat-x", document_language=None):
        """Phase 00 문서. document_language=None 이면 마커 이전 사이클(미선언)."""
        self._profile_with_phase00()
        d = os.path.join(self.tmp, "plan_docs", "00-base_plan")
        os.makedirs(d, exist_ok=True)
        marker = f"Document-Language: {document_language}\n" if document_language else ""
        path = os.path.join(d, f"{stem}.md")
        Path(path).write_text(f"# [Base Plan] {stem}\n\n{marker}Cycle-Stem: `{stem}`\n"
                              "Risk Level: L3\nStatus: DRAFT\n", encoding="utf-8")
        return path

    def _write_mirror(self, stem, document_language):
        """`.sage/cycle.json` 미러 — 스키마 드리프트를 피하려고 정본 writer 를 그대로 쓴다."""
        hooks = os.path.join(REPO, "scripts", "sage_harness", "hooks")
        for path in (os.path.join(hooks, "runtime"), hooks):
            if path not in sys.path:
                sys.path.insert(0, path)
        import cycle_state
        cycle_state.write_declaration(self.tmp, stem, document_language=document_language)

    def _raw_mirror(self, text):
        """정본 writer 가 만들 수 없는 상태(손상·v1 legacy)를 직접 심는다."""
        d = os.path.join(self.tmp, ".sage")
        os.makedirs(d, exist_ok=True)
        Path(os.path.join(d, "cycle.json")).write_text(text, encoding="utf-8")

    def _files_in(self, vault):
        return [fn for _, _, fs in os.walk(vault) for fn in fs]

    def _add_05_named(self, stem):
        """05 문서를 Phase 00 과 같은 basename 으로 둔다 — 모든 phase 문서가 같은 stem 을 쓰는
        실제 사이클 규약이다(`_add_05` 는 `-review` 를 붙이는 느슨한 fixture)."""
        d = os.path.join(self.tmp, "plan_docs", "05-expert-review")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{stem}.md")
        Path(path).write_text("## Phase-05 Review\nFinal Status: APPROVED\n", encoding="utf-8")
        return path

    def test_en_cycle_writes_an_en_note_under_default_display_ko(self):
        self._add_00("feat-x", "en")
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self._note_path(v)).read_text(encoding="utf-8")
        self.assertIn("## Summary\n", text)
        self.assertNotIn("## 요약\n", text)
        self.assertIn("This cycle's document language is English", text)
        self.assertNotIn("이 사이클의 문서 언어는", text)

    def test_ko_cycle_keeps_a_ko_note_under_lang_en(self):
        self._add_00("feat-x", "ko")
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro_lang("en", "--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self._note_path(v)).read_text(encoding="utf-8")
        self.assertIn("## 요약\n", text)
        self.assertNotIn("## Summary\n", text)
        self.assertIn("이 사이클의 문서 언어는 한국어입니다", text)

    def test_declaration_recorded_only_by_the_loop_still_wins(self):
        # --feature 없이도 loop_open 이 기록한 cycle_stem 으로 선언을 찾아야 한다.
        self._add_00("feat-y", "en")
        self._run_loop(cycle_stem="feat-y")
        self._add_05()
        v = self._vault()
        r = retro("--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self._note_path(v)).read_text(encoding="utf-8")
        self.assertIn("## Summary\n", text)
        self.assertIn("This cycle's document language is English", text)

    def test_an_undeclared_cycle_is_not_told_it_chose_korean(self):
        self._add_00("feat-x", None)
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self._note_path(v)).read_text(encoding="utf-8")
        self.assertIn("문서 언어를 선언하지 않았습니다", text)
        self.assertNotIn("이 사이클의 문서 언어는", text)

    def test_a_mirror_that_agrees_is_not_a_conflict(self):
        # 과차단 방향 회귀 — 미러와 Phase 00 이 같은 답이면 아무것도 막지 않는다.
        self._add_00("feat-x", "ko")
        self._write_mirror("feat-x", "ko")
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("## 요약\n", Path(self._note_path(v)).read_text(encoding="utf-8"))

    def test_a_mirror_that_disagrees_blocks_before_the_note_is_written(self):
        self._add_00("feat-x", "en")
        self._write_mirror("feat-x", "ko")
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("state-mismatch", r.stderr)
        self.assertEqual([], [fn for _, _, fs in os.walk(v) for fn in fs],
                         "차단됐는데 노트가 남았다 — 쓰기 전에 멈춰야 한다")

    def test_two_candidate_stems_that_disagree_block(self):
        # --feature 와 loop_open 의 cycle_stem 이 서로 다른 언어를 선언한 사이클을 가리킨다.
        self._add_00("feat-x", "ko")
        self._add_00("feat-y", "en")
        self._run_loop(cycle_stem="feat-y")
        self._add_05()
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("mismatch", r.stderr)
        self.assertEqual([], [fn for _, _, fs in os.walk(v) for fn in fs])

    def test_screen_language_stays_the_display_language(self):
        # 노트는 en, 화면 안내는 ko — 같은 실행에서 두 축이 갈리는 것이 계약이다.
        self._add_00("feat-x", "en")
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Obsidian retro human-gate 노트 작성", r.stderr)
        self.assertIn("## Summary", r.stderr)   # 화면 문장 안의 헤딩 이름은 노트의 실제 헤딩

    def test_a_mirror_alone_does_not_declare_a_language(self):
        # 미러는 교차검증 상대이지 답의 출처가 아니다. 정본이 말하지 않은 것을 미러가 대신
        # 말하면, 마커 없는 사이클이 파일 한 줄로 en 을 선언한 사이클이 된다.
        self._add_00("feat-x", None)
        self._write_mirror("feat-x", "en")
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self._note_path(v)).read_text(encoding="utf-8")
        self.assertIn("문서 언어를 선언하지 않았습니다", text)
        self.assertNotIn("This cycle's document language", text)

    def test_a_mirror_alone_does_not_declare_korean_either(self):
        # 반대 방향도 같다 — 표시 언어가 en 이어도 미러의 ko 를 선언으로 승격시키지 않는다.
        self._add_00("feat-x", None)
        self._write_mirror("feat-x", "ko")
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro_lang("en", "--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self._note_path(v)).read_text(encoding="utf-8")
        self.assertIn("declares no document language", text)
        self.assertNotIn("이 사이클의 문서 언어는", text)

    def test_a_legacy_mirror_without_a_language_is_not_a_failure(self):
        # 과차단 방향 회귀 — v1 미러는 손상이 아니라 이행 전 상태다. 정본이 답을 갖고 있다.
        self._add_00("feat-x", "en")
        self._raw_mirror('{"version": 1, "cycle_stem": "feat-x"}\n')
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("## Summary\n", Path(self._note_path(v)).read_text(encoding="utf-8"))

    def test_a_corrupt_cycle_state_blocks_instead_of_reading_as_absent(self):
        # 손상을 부재로 뭉개면 파일을 1바이트 자르는 것이 교차검증을 끄는 레버가 된다.
        self._add_00("feat-x", "en")
        self._raw_mirror("{not json")
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("cycle.json", r.stderr)
        self.assertEqual([], self._files_in(v), "차단됐는데 노트가 남았다")

    def test_an_unsafe_phase00_glob_blocks_instead_of_reading_as_absent(self):
        # 계약이 없는 것과 계약을 읽지 못하는 것은 다른 상태다. 뒤쪽을 통과시키면 확인하지
        # 못한 채로 언어가 정해진다.
        self._add_00("feat-x", "en")
        self._profile_with_phase00("../outside/**/*.md")
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("unreadable", r.stderr)
        self.assertEqual([], self._files_in(v), "차단됐는데 노트가 남았다")

    def test_a_phase00_that_cannot_be_decoded_blocks(self):
        path = self._add_00("feat-x", "en")
        with open(path, "ab") as fh:
            fh.write(b"\xff\xfe invalid utf-8\n")
        self._run_loop()
        self._add_05()
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("unreadable", r.stderr)
        self.assertEqual([], self._files_in(v), "차단됐는데 노트가 남았다")

    def test_a_broken_shared_profile_blocks_instead_of_reading_as_absent(self):
        # 손상된 profile 은 pdca.phases 를 통째로 지운다. 그것을 부재로 받으면 `en` 을 선언한
        # 사이클이 미선언으로 보이고, 한국어 노트가 "선언한 적 없다"고 증거에 적는다.
        self._add_00("feat-x", "en")
        self._run_loop()
        self._add_05()
        Path(os.path.join(self.tmp, "sage", "project-profile.yaml")).write_text(
            "pdca: [unclosed\n", encoding="utf-8")
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("project-profile.yaml", r.stderr)
        self.assertEqual([], self._files_in(v), "차단됐는데 노트가 남았다")

    def test_an_unreadable_local_profile_blocks(self):
        # local 계층도 shared 와 같다 — 파싱되지 않으면 vault 경로도 언어도 신뢰할 수 없다.
        # 차단 사유는 화면이므로 표시 언어로 말한다(local 이 깨졌을 때의 표시 언어는 폴백 ko).
        self._add_00("feat-x", "en")
        self._run_loop()
        self._add_05()
        Path(os.path.join(self.tmp, "sage", "project-profile.local.yaml")).write_text(
            "interface: [unclosed\n", encoding="utf-8")
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("profile 을 읽지 못했습니다", r.stderr)
        self.assertIn("project-profile.local.yaml", r.stderr)
        self.assertEqual([], self._files_in(v), "차단됐는데 노트가 남았다")

    def test_a_project_without_any_profile_still_runs(self):
        # 과차단 방향 회귀 — SAGE 가 설치되지 않은 저장소의 단발 retro 는 기존 계약대로 돈다.
        # 부재는 판독 실패가 아니고, 여기서 막으면 이 명령이 쓸 수 없어진다.
        bare = os.path.join(self.tmp, "bare")
        os.makedirs(os.path.join(bare, "plan_docs", "05-expert-review"))
        Path(os.path.join(bare, "plan_docs", "05-expert-review", "feat-x-review.md")).write_text(
            "## Phase-05 Review\nFinal Status: APPROVED\n", encoding="utf-8")
        v = os.path.join(bare, "vault")
        os.makedirs(v)
        r = retro("--feature", "feat-x", "--vault", v, root=bare)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_cycle_identified_only_by_its_single_05_doc_still_finds_the_marker(self):
        # loop run 도 --feature 도 없다. 05 문서 하나가 유일한 사이클 식별자이고, 노트 제목은 이미
        # 그것을 쓴다. 언어 판정만 그것을 못 보면 제목은 이 사이클, 언어는 "선언 없음"이 된다.
        self._add_00("feat-x", "en")
        self._add_05_named("feat-x")
        v = self._vault()
        r = retro("--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self._note_path(v)).read_text(encoding="utf-8")
        self.assertIn("## Summary\n", text)
        self.assertNotIn("## 요약\n", text)
        self.assertIn("This cycle's document language is English", text)

    def test_a_partial_feature_token_still_finds_the_marker(self):
        # 부분 토큰 --feature 는 지원 계약이다. 그런데 Phase 00 결속은 exact stem 비교라
        # 'loop' 문자열 자체는 어떤 Phase 00 과도 매치하지 않는다 — 필터가 고른 문서의 stem 을
        # 써야 부분 필터를 깨지 않고 정확한 stem 을 얻는다.
        self._add_00("loop-engineering", "en")
        self._add_05_named("loop-engineering")
        v = self._vault()
        r = retro("--feature", "loop", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self._note_path(v)).read_text(encoding="utf-8")
        self.assertIn("## Summary\n", text)
        self.assertNotIn("## 요약\n", text)

    def test_several_05_docs_do_not_lend_a_stem(self):
        # 어느 것이 이 사이클인지 모르면 문서에서 stem 을 얻지 않는다. alpha 는 `en` 을 선언했지만
        # 이 실행이 alpha 의 회고라는 근거가 없다 — 아무거나 고르면 남의 사이클 선언 언어로
        # 회고가 쓰인다. 미선언으로 두고 통과시킨다(막지도 않는다).
        self._add_00("alpha", "en")
        self._add_05_named("alpha")
        self._add_05_named("beta")
        v = self._vault()
        r = retro("--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self._note_path(v)).read_text(encoding="utf-8")
        self.assertIn("## 요약\n", text)
        self.assertNotIn("## Summary\n", text)

    def test_an_invalid_display_language_does_not_change_the_exit(self):
        # 표시 언어는 개인 설정이다. catalog 경고문과 상세 설계가 "판정과 exit code 는 영향받지
        # 않는다" 로 계약돼 있고, 오타 한 줄이 회고를 막는 것은 그 계약을 깨는 과차단이다.
        self._add_00("feat-x", "en")
        self._run_loop()
        self._add_05()
        Path(os.path.join(self.tmp, "sage", "project-profile.local.yaml")).write_text(
            "interface:\n  language: EN\n", encoding="utf-8")
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = Path(self._note_path(v)).read_text(encoding="utf-8")
        # 표시 언어는 한국어로 폴백하되, 노트 안은 사이클이 선언한 영어를 그대로 따른다.
        self.assertIn("## Summary\n", text)
        self.assertIn("interface.language", r.stderr)

    def test_a_local_profile_without_its_shared_layer_is_not_absence(self):
        # local 만 남고 shared 가 사라진 것은 무설치가 아니라 계층이 깨진 상태다. 부재로 받으면
        # 파일 하나를 지우는 것이 다시 언어 판정을 건너뛰는 레버가 된다.
        self._add_00("feat-x", "en")
        self._run_loop()
        self._add_05()
        Path(os.path.join(self.tmp, "sage", "project-profile.local.yaml")).write_text(
            "interface:\n  language: en\n", encoding="utf-8")
        os.remove(os.path.join(self.tmp, "sage", "project-profile.yaml"))
        v = self._vault()
        r = retro("--feature", "feat-x", "--vault", v, root=self.tmp)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual([], self._files_in(v), "차단됐는데 노트가 남았다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
