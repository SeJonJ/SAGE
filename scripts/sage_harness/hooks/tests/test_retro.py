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
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


def sage_review_loop(*args, root):
    subprocess.run([sys.executable, "-m", "sage", "review-loop", *args, "--root", root],
                   cwd=REPO, capture_output=True, text=True)


def retro(*args, root, cwd=None):
    cmd = [sys.executable, "-m", "sage", "retro", *args]
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

    def _run_loop(self, risk="L3"):
        r = subprocess.run([sys.executable, "-m", "sage", "review-loop", "open", "--risk", risk, "--root", self.tmp],
                           cwd=REPO, capture_output=True, text=True)
        rid = r.stdout.strip().splitlines()[0]
        sage_review_loop("round", "--run-id", rid, "--iteration", "1", "--found", "7",
                         "--survived", "3", "--accepted", "3", "--tokens", "48000", root=self.tmp)
        sage_review_loop("close", "--run-id", rid, "--result", "APPROVED", "--reason", "DRY",
                         "--iterations", "1", root=self.tmp)
        return rid


class TestRetro(_ProjectFixture, unittest.TestCase):
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
        # orphan round(라이브러리 직접) → retro 가 무결성 경고 표면화.
        sys.path.insert(0, os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime"))
        import loop_audit as la
        la.record_round(self.tmp, "rl-ghost", 1, 1, 0, 0, 0, 10)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
