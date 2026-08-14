#!/usr/bin/env python3
"""sage-feedback 마커 스캔(§10-a-C) 검증.

핵심 계약 셋:
  1. 주석 기호가 아니라 토큰을 찾는다 → 언어 무관.
  2. 심각도(`!`)를 단일 정규식의 optional 그룹으로 뽑는다 → 차단성 마커가 advisory 로 새지 않는다.
  3. 스캔 범위는 git 추적 파일 + plan_docs 제외 → 기록 노트의 토큰이 다시 마커가 되는 자기증식 차단.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage import feedback as fb  # noqa: E402
from sage.profile_validate import _feedback_issues  # noqa: E402


class TestMarkerParsing(unittest.TestCase):
    def test_token_scan_is_language_agnostic(self):
        text = "\n".join([
            "// sage-feedback :: java 주석",
            "# sage-feedback :: python 주석",
            "-- sage-feedback :: sql 주석",
            "<!-- sage-feedback :: html 주석 -->",
            "  ;; sage-feedback :: lisp 주석",
        ])
        markers = fb.scan_text(text)
        self.assertEqual(len(markers), 5)
        self.assertEqual([m.blocking for m in markers], [False] * 5)
        # 블록 주석 종료자는 본문에서 제거(판정에는 무관하지만 기록 노이즈).
        self.assertEqual(markers[3].text, "html 주석")

    def test_severity_captured_without_leaking_into_advisory(self):
        markers = fb.scan_text("# !sage-feedback :: 차단성\n// sage-feedback :: advisory")
        self.assertEqual([m.blocking for m in markers], [True, False])
        self.assertEqual(len(fb.blocking(markers)), 1)

    def test_separator_is_required_so_bare_word_is_not_a_marker(self):
        text = '\n'.join(['log.info("관련 없는 sage-feedback 문자열")',
                          "# sage-feedback 구분자 없음",
                          "// TODO: 무관"])
        self.assertEqual(fb.scan_text(text), [])

    def test_separator_spacing_variants(self):
        for line in ("#sage-feedback::붙임", "# sage-feedback   ::  넓힘", "# !sage-feedback::차단"):
            with self.subTest(line=line):
                self.assertEqual(len(fb.scan_text(line)), 1)


class TestScanScope(unittest.TestCase):
    def _repo(self, tmp):
        subprocess.run(["git", "init", "-q", tmp], check=True)
        for key, value in (("user.email", "t@t"), ("user.name", "t")):
            subprocess.run(["git", "-C", tmp, "config", key, value], check=True)

    def _write(self, root, rel, content, binary=False):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode, data = ("wb", content) if binary else ("w", content)
        with open(path, mode, **({} if binary else {"encoding": "utf-8"})) as handle:
            handle.write(data)

    def _commit(self, root):
        subprocess.run(["git", "-C", root, "add", "-A"], check=True)
        subprocess.run(["git", "-C", root, "commit", "-qm", "t"], check=True)

    def test_untracked_and_plan_docs_and_binary_are_excluded(self):
        profile = {"paths": {"plan_docs": "plan_docs"}}
        with tempfile.TemporaryDirectory() as root:
            self._repo(root)
            self._write(root, "src/a.py", "# sage-feedback :: 추적됨")
            # 설계·계획 문서는 마커 예시를 담아 오탐원 — 제외되어야 한다.
            self._write(root, "plan_docs/00-design/x.md", "# sage-feedback :: 계획문서 예시")
            # NUL 바이트 = 바이너리. NUL 은 유효한 UTF-8 이라 decode 만으로는 안 걸러진다.
            self._write(root, "src/blob.bin", b"bin\x00 sage-feedback :: \xea\xb0\x80", binary=True)
            self._commit(root)
            # 미추적 파일은 커밋 뒤에 만들어 git ls-files 에 안 잡히게 한다.
            self._write(root, "src/untracked.py", "# sage-feedback :: 미추적")

            markers = fb.scan(root, profile)
            self.assertEqual([m.path for m in markers], ["src/a.py"])

    def test_audit_log_is_excluded_even_though_it_is_tracked(self):
        # 기록은 override.jsonl 과 같이 커밋된다 → 추적 파일이 되고, 레코드에 담긴 마커 원문이
        # 다음 스캔에서 새 마커가 되는 자기증식이 생긴다. `.sage/` 상시 제외로 구조적으로 막는다.
        with tempfile.TemporaryDirectory() as root:
            self._repo(root)
            self._write(root, "src/a.py", "# sage-feedback :: 실제 마커")
            self._write(root, ".sage/feedback.jsonl",
                        json.dumps({"marker_text": "sage-feedback :: 기록된 원문"}) + "\n")
            self._commit(root)
            self.assertEqual([m.path for m in fb.scan(root, {})], ["src/a.py"])

    def test_non_git_directory_yields_no_markers(self):
        with tempfile.TemporaryDirectory() as root:
            self._write(root, "a.py", "# sage-feedback :: git 아님")
            self.assertEqual(fb.scan(root, {}), [])

    def test_git_failure_raises_instead_of_looking_empty(self):
        # 실패를 빈 결과로 뭉개면 "마커를 못 본 것" 이 "마커가 없는 것" 으로 둔갑해 게이트가 통과한다.
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.object(fb.subprocess, "run",
                                   side_effect=fb.subprocess.TimeoutExpired("git", 30)):
                with self.assertRaises(fb.ScanError):
                    fb.scan(root, {})
            with mock.patch.object(fb.subprocess, "run", side_effect=OSError("git 없음")):
                with self.assertRaises(fb.ScanError):
                    fb.scan(root, {})

    def test_unreadable_tracked_file_raises(self):
        # 존재하는데 못 읽는 파일은 "마커 없음" 이 아니라 모름이다.
        with tempfile.TemporaryDirectory() as root:
            self._repo(root)
            self._write(root, "a.py", "# sage-feedback :: x")
            self._commit(root)
            os.chmod(os.path.join(root, "a.py"), 0o000)
            try:
                if os.access(os.path.join(root, "a.py"), os.R_OK):
                    self.skipTest("root 권한 — 권한 거부를 재현할 수 없음")
                with self.assertRaises(fb.ScanError):
                    fb.scan(root, {})
            finally:
                os.chmod(os.path.join(root, "a.py"), 0o644)

    def test_staged_deletion_is_not_a_scan_failure(self):
        # 인덱스에 있고 워크트리에 없는 파일은 흔한 정상 상태다 — 여기서 막으면 오차단.
        with tempfile.TemporaryDirectory() as root:
            self._repo(root)
            self._write(root, "a.py", "# sage-feedback :: 남는 마커")
            self._write(root, "gone.py", "x = 1")
            self._commit(root)
            os.remove(os.path.join(root, "gone.py"))
            self.assertEqual([m.path for m in fb.scan(root, {})], ["a.py"])


class TestProfileGate(unittest.TestCase):
    def test_enabled_requires_explicit_true(self):
        self.assertFalse(fb.enabled({}))                             # 섹션 없음 = 하위호환 off
        self.assertFalse(fb.enabled({"feedback": {}}))
        self.assertFalse(fb.enabled({"feedback": {"enabled": False}}))
        self.assertTrue(fb.enabled({"feedback": {"enabled": True}}))

    def test_validator_fails_closed_on_gate_bearing_keys(self):
        # enabled/block_release 는 게이트 강제력에 직접 관여 → 비-bool 은 침묵 off 되므로 FAIL.
        for key in ("enabled", "block_release"):
            with self.subTest(key=key):
                issues = _feedback_issues({"feedback": {key: "yes"}})
                self.assertTrue(any(sev == "FAIL" for sev, _ in issues), issues)

    def test_validator_rejects_unknown_key(self):
        issues = _feedback_issues({"feedback": {"enabled": True, "blockRelease": True}})
        self.assertTrue(any(sev == "FAIL" and getattr(msg, "code", "") == "validate.feedback_unknown_keys"
                            for sev, msg in issues), issues)

    def test_validator_warns_when_block_release_has_no_scanner(self):
        issues = _feedback_issues({"feedback": {"block_release": True}})
        self.assertTrue(any(sev == "WARN"
                            and getattr(msg, "code", "") == "validate.feedback_block_release_ineffective"
                            for sev, msg in issues), issues)

    def test_valid_section_is_clean(self):
        self.assertEqual(_feedback_issues({"feedback": {
            "enabled": True, "block_release": False, "record": False, "record_target": "auto"}}), [])
        self.assertEqual(_feedback_issues({}), [])


class TestCli(unittest.TestCase):
    def _run(self, root, *extra, lang=None):
        prefix = ["--lang", lang] if lang else []
        return subprocess.run([sys.executable, "-m", "sage.cli", *prefix, "feedback",
                               "--root", root, *extra],
                              capture_output=True, text=True, cwd=REPO)

    def _project(self, root, enabled=True, **feedback):
        subprocess.run(["git", "init", "-q", root], check=True)
        for key, value in (("user.email", "t@t"), ("user.name", "t")):
            subprocess.run(["git", "-C", root, "config", key, value], check=True)
        os.makedirs(os.path.join(root, "sage"), exist_ok=True)
        section = {"enabled": enabled, **feedback}
        rendered = ", ".join(f"{k}: {str(v).lower() if isinstance(v, bool) else v}"
                             for k, v in section.items())
        with open(os.path.join(root, "sage", "project-profile.yaml"), "w", encoding="utf-8") as handle:
            handle.write("project: { name: demo }\npaths: { plan_docs: plan_docs }\n"
                         f"feedback: {{ {rendered} }}\n")
        with open(os.path.join(root, "a.py"), "w", encoding="utf-8") as handle:
            handle.write("# !sage-feedback :: 차단성\n# sage-feedback :: advisory\n")
        subprocess.run(["git", "-C", root, "add", "-A"], check=True)
        subprocess.run(["git", "-C", root, "commit", "-qm", "t"], check=True)

    def test_json_output_reports_counts(self):
        with tempfile.TemporaryDirectory() as root:
            self._project(root)
            result = self._run(root, "--output", "json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["counts"], {"total": 2, "blocking": 1})

    def test_exit_code_flag_signals_blocking_markers(self):
        with tempfile.TemporaryDirectory() as root:
            self._project(root)
            self.assertEqual(self._run(root).returncode, 0)              # 기본은 보고만
            self.assertEqual(self._run(root, "--exit-code").returncode, 2)

    def test_release_gate_defers_to_profile(self):
        with tempfile.TemporaryDirectory() as root:
            self._project(root)                      # block_release 미설정 = false
            self.assertEqual(self._run(root, "--release-gate").returncode, 0)
        with tempfile.TemporaryDirectory() as root:
            # CI 는 항상 같은 명령을 호출하고, 막을지는 프로필이 정한다.
            self._project(root, block_release=True)
            self.assertEqual(self._run(root, "--release-gate").returncode, 2)

    def test_record_is_noop_when_record_is_false(self):
        with tempfile.TemporaryDirectory() as root:
            self._project(root)
            result = self._run(root, "--record", "--path", "a.py", "--line", "1",
                               "--verdict", "fixed", "--note", "고침")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(os.path.exists(fb.record_path(root)))

    def test_record_writes_audit_log(self):
        with tempfile.TemporaryDirectory() as root:
            self._project(root, record=True)
            result = self._run(root, "--record", "--path", "a.py", "--line", "2",
                               "--verdict", "intentional", "--note", "00 설계 근거 있음",
                               "--cycle-stem", "2026-07-25-x")
            self.assertEqual(result.returncode, 0, result.stderr)
            records = fb.read_records(root)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["cycle_stem"], "2026-07-25-x")
            # advisory 마커가 그 줄에 살아있으므로 심각도·원문이 레코드에 잡힌다.
            self.assertEqual(records[0]["marker_text"], "advisory")
            self.assertFalse(records[0]["blocking"])

    def test_record_rejects_incomplete_and_escaping_arguments(self):
        with tempfile.TemporaryDirectory() as root:
            self._project(root, record=True)
            self.assertEqual(self._run(root, "--record", "--path", "a.py").returncode, 2)
            self.assertEqual(self._run(root, "--record", "--path", "../outside.py", "--line", "1",
                                       "--verdict", "fixed", "--note", "x").returncode, 2)
            self.assertFalse(os.path.exists(fb.record_path(root)))

    def test_record_is_refused_when_feature_is_disabled(self):
        # 스캔은 조용히 무동작이지만 기록은 명시 요청 — 침묵하면 기록됐다고 오인한다.
        with tempfile.TemporaryDirectory() as root:
            self._project(root, enabled=False, record=True)
            result = self._run(root, "--record", "--path", "a.py", "--line", "1",
                               "--verdict", "fixed", "--note", "x")
            self.assertEqual(result.returncode, 2)
            self.assertFalse(os.path.exists(fb.record_path(root)))

    def test_record_writes_vault_cycle_note(self):
        with tempfile.TemporaryDirectory() as root:
            self._project(root, record=True)
            vault = os.path.join(root, "vault")
            result = self._run(root, "--record", "--path", "a.py", "--line", "1",
                               "--verdict", "fixed", "--note", "TTL 로 복구",
                               "--cycle-stem", "2026-07-25-x", "--vault", vault)
            self.assertEqual(result.returncode, 0, result.stderr)
            note = os.path.join(vault, "wiki", "SAGE - demo feedback 2026-07-25-x.md")
            self.assertTrue(os.path.exists(note), os.listdir(os.path.join(vault, "wiki")))
            body = Path(note).read_text(encoding="utf-8")
            self.assertIn("TTL 로 복구", body)
            # 같은 사이클의 두 번째 마커는 새 노트가 아니라 같은 노트에 누적된다.
            self._run(root, "--record", "--path", "a.py", "--line", "2",
                      "--verdict", "undetermined", "--note", "근거 없음",
                      "--cycle-stem", "2026-07-25-x", "--vault", vault)
            self.assertEqual(len(os.listdir(os.path.join(vault, "wiki"))), 1)
            self.assertIn("근거 없음", Path(note).read_text(encoding="utf-8"))

    def test_record_writes_vault_cycle_note_in_english_when_lang_en(self):
        """vault 노트 본문도 language_of() 를 따른다 — --lang en 이면 헤더·verdict·라벨이 영어."""
        with tempfile.TemporaryDirectory() as root:
            self._project(root, record=True)
            vault = os.path.join(root, "vault")
            result = self._run(root, "--record", "--path", "a.py", "--line", "1",
                               "--verdict", "fixed", "--note", "restored via TTL",
                               "--cycle-stem", "2026-07-25-x", "--vault", vault, lang="en")
            self.assertEqual(result.returncode, 0, result.stderr)
            note = os.path.join(vault, "wiki", "SAGE - demo feedback 2026-07-25-x.md")
            body = Path(note).read_text(encoding="utf-8")
            self.assertIn("developer feedback marker history", body)
            self.assertIn("- note: restored via TTL", body)
            self.assertIn(" — fixed", body)
            self.assertNotIn("처리 이력", body)
            self.assertNotIn("수정함", body)
            self.assertNotIn("판단:", body)

    def test_scan_failure_is_fail_closed_for_enforcing_callers(self):
        # git 이 없는 PATH 로 실행해 스캔 불능을 만든다. "마커 0건" 으로 통과시키면 안 된다.
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as empty_bin:
            self._project(root)
            env = os.environ.copy()
            env["PATH"] = empty_bin                    # git 실행 불가
            def run(*extra):
                return subprocess.run([sys.executable, "-m", "sage.cli", "feedback",
                                       "--root", root, *extra],
                                      capture_output=True, text=True, cwd=REPO, env=env)
            self.assertEqual(run("--exit-code").returncode, 2)
            self.assertEqual(run("--release-gate").returncode, 2)
            self.assertEqual(run().returncode, 1)      # 단순 조회도 성공(0)으로 위장하지 않는다

    def test_record_always_writes_the_audit_log_even_for_vault_target(self):
        # vault 는 저장소 밖(별도 git)이라 노트만 남기면 이 저장소엔 이력이 하나도 안 남는다.
        with tempfile.TemporaryDirectory() as root:
            self._project(root, record=True, record_target="vault")
            vault = os.path.join(root, "vault")
            result = self._run(root, "--record", "--path", "a.py", "--line", "1",
                               "--verdict", "fixed", "--note", "고침",
                               "--cycle-stem", "s", "--vault", vault)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(fb.read_records(root)), 1)
            self.assertTrue(os.path.isdir(os.path.join(vault, "wiki")))

    def test_vault_target_without_a_vault_warns_and_exits_non_zero(self):
        # 조용한 폴백은 설정이 지켜졌다고 오인하게 만든다.
        with tempfile.TemporaryDirectory() as root:
            self._project(root, record=True, record_target="vault")
            result = self._run(root, "--record", "--path", "a.py", "--line", "1",
                               "--verdict", "fixed", "--note", "고침")
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(len(fb.read_records(root)), 1)   # 감사 로그는 그대로 남는다

    def test_vault_note_cannot_escape_through_a_symlinked_folder(self):
        # 중간 디렉토리 심링크로 vault 밖을 가리키면 append 가 그대로 밖으로 샌다.
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            self._project(root, record=True)
            vault = os.path.join(root, "vault")
            os.makedirs(vault)
            os.symlink(outside, os.path.join(vault, "wiki"))   # wiki/ → vault 밖
            for line, note in (("1", "첫"), ("2", "둘")):       # 생성 경로 + append 경로 둘 다
                result = self._run(root, "--record", "--path", "a.py", "--line", line,
                                   "--verdict", "fixed", "--note", note,
                                   "--cycle-stem", "s", "--vault", vault)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(os.listdir(outside), [], "vault 밖에 기록이 새어나갔다")
            # 노트는 vault 루트로 접혀 저장된다(기록 자체는 유실되지 않는다).
            self.assertTrue(any(n.endswith(".md") for n in os.listdir(vault)), os.listdir(vault))

    def test_disabled_profile_does_not_scan(self):
        with tempfile.TemporaryDirectory() as root:
            self._project(root, enabled=False)
            result = self._run(root, "--output", "json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"enabled": False, "markers": []})


class TestRecord(unittest.TestCase):
    """기록은 감사 축이라 verdict 와 어긋난 주장이 남을 수 없어야 한다."""

    def test_resolved_is_derived_from_verdict_not_asserted(self):
        for verdict, resolved in ((fb.VERDICT_FIXED, True), (fb.VERDICT_INTENTIONAL, True),
                                  (fb.VERDICT_UNDETERMINED, False)):
            with self.subTest(verdict=verdict):
                record = fb.build_record("a.py", 3, verdict, "근거")
                self.assertEqual(record["resolved"], resolved)

    def test_append_only_accumulates(self):
        with tempfile.TemporaryDirectory() as root:
            fb.append_record(root, fb.build_record("a.py", 1, fb.VERDICT_FIXED, "첫"))
            fb.append_record(root, fb.build_record("a.py", 2, fb.VERDICT_UNDETERMINED, "둘"))
            records = fb.read_records(root)
            self.assertEqual([r["note"] for r in records], ["첫", "둘"])
            self.assertTrue(os.path.exists(fb.record_path(root)))

    def test_corrupt_line_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as root:
            fb.append_record(root, fb.build_record("a.py", 1, fb.VERDICT_FIXED, "정상"))
            with open(fb.record_path(root), "a", encoding="utf-8") as handle:
                handle.write("{깨진 줄\n\n")
            self.assertEqual([r["note"] for r in fb.read_records(root)], ["정상"])

    def test_record_requires_both_enabled_and_record(self):
        self.assertFalse(fb.record_enabled({"feedback": {"record": True}}))          # enabled off
        self.assertFalse(fb.record_enabled({"feedback": {"enabled": True}}))
        self.assertTrue(fb.record_enabled({"feedback": {"enabled": True, "record": True}}))

    def test_block_release_requires_enabled(self):
        self.assertFalse(fb.block_release({"feedback": {"block_release": True}}))
        self.assertTrue(fb.block_release({"feedback": {"enabled": True, "block_release": True}}))

    def test_invalid_record_target_degrades_to_auto(self):
        self.assertEqual(fb.record_target({"feedback": {"record_target": "wiki"}}), "auto")
        self.assertEqual(fb.record_target({}), "auto")
        self.assertEqual(fb.record_target({"feedback": {"record_target": "sage"}}), "sage")


class TestGateResolutionRule(unittest.TestCase):
    """게이트 규칙 = "마커 있는 파일 금지" 가 아니라 "고친 뒤에도 마커가 남는가".

    전자로 만들면 마커를 걷어내려는 편집까지 막혀 영원히 해소할 수 없다(자기차단).
    """

    def setUp(self):
        runtime = os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime")
        if runtime not in sys.path:
            sys.path.insert(0, runtime)
        import feedback_markers
        self.fm = feedback_markers
        self.marker = "# !sage-feedback :: 설계와 다름\n"
        self.on_disk = self.marker + "def retry(): pass\n"

    def test_write_that_keeps_marker_is_not_resolving(self):
        change = {"full_content": True, "content": self.marker + "def retry(): pass\ndef extra(): pass\n"}
        self.assertFalse(self.fm.resolves_blocking(change, self.on_disk))

    def test_write_that_drops_marker_is_resolving(self):
        change = {"full_content": True, "content": "def retry():\n    backoff()\n"}
        self.assertTrue(self.fm.resolves_blocking(change, self.on_disk))

    def test_edit_removing_the_marker_is_resolving(self):
        change = {"content": "", "removed_content": self.marker}
        self.assertTrue(self.fm.resolves_blocking(change, self.on_disk))

    def test_edit_elsewhere_leaves_marker_and_is_blocked(self):
        change = {"content": "def retry(): pass\ndef extra(): pass",
                  "removed_content": "def retry(): pass"}
        self.assertFalse(self.fm.resolves_blocking(change, self.on_disk))

    def test_edit_that_reintroduces_a_marker_is_not_resolving(self):
        # 마커를 지우면서 다른 차단성 마커를 새로 심는 편집은 해소가 아니다.
        change = {"content": "# !sage-feedback :: 새 의문", "removed_content": self.marker}
        self.assertFalse(self.fm.resolves_blocking(change, self.on_disk))

    def test_removing_one_of_several_markers_is_not_resolving(self):
        # 마커 3개 중 1개만 지우는 편집이 통과하면 나머지 2개 위에 새 구현을 쌓게 된다(우회).
        on_disk = ("# !sage-feedback :: 첫째\n"
                   "def a(): pass\n"
                   "# !sage-feedback :: 둘째\n"
                   "def b(): pass\n"
                   "# !sage-feedback :: 셋째\n")
        change = {"content": "", "removed_content": "# !sage-feedback :: 첫째\n"}
        self.assertFalse(self.fm.resolves_blocking(change, on_disk))

    def test_removing_every_marker_is_resolving(self):
        on_disk = "# !sage-feedback :: 첫째\ndef a(): pass\n# !sage-feedback :: 둘째\n"
        change = {"content": "",
                  "removed_content": "# !sage-feedback :: 첫째\n# !sage-feedback :: 둘째\n"}
        self.assertTrue(self.fm.resolves_blocking(change, on_disk))

    def test_advisory_markers_do_not_raise_the_bar(self):
        # advisory 는 세지 않는다 — 강제력은 `!` 에만 있다.
        on_disk = "# sage-feedback :: 참고\n# !sage-feedback :: 차단\n"
        change = {"content": "", "removed_content": "# !sage-feedback :: 차단\n"}
        self.assertTrue(self.fm.resolves_blocking(change, on_disk))

    def test_file_without_blocking_marker_is_always_allowed(self):
        # advisory 마커만 있는 파일은 아무것도 막지 않는다.
        change = {"full_content": True, "content": "# sage-feedback :: advisory 그대로"}
        self.assertTrue(self.fm.resolves_blocking(change, "# sage-feedback :: advisory\n"))


class TestGateDecision(unittest.TestCase):
    """core.decide 가 snapshot 주입만으로 판정하는지(순수 함수 계약 유지)."""

    def setUp(self):
        hooks = os.path.join(REPO, "scripts", "sage_harness", "hooks")
        for path in (os.path.join(hooks, "runtime"), hooks):
            if path not in sys.path:
                sys.path.insert(0, path)
        import pre_implementation_gate_core
        self.core = pre_implementation_gate_core
        self.on_disk = "# !sage-feedback :: 설계와 다름\ndef retry(): pass\n"
        self.snapshot = {"feedback": {"enabled": True, "targets": {"src/pay.py": {
            "on_disk": self.on_disk,
            "markers": [{"path": "src/pay.py", "line": 1, "blocking": True, "text": "설계와 다름"}]}}}}

    def _event(self, change):
        change.setdefault("path", "src/pay.py")
        return {"changes": [change]}

    def test_blocks_write_that_keeps_marker(self):
        result = self.core._feedback_gate(
            self._event({"full_content": True, "content": self.on_disk + "def extra(): pass"}),
            {}, self.snapshot)
        self.assertIsNotNone(result)
        self.assertEqual(result["files"], ["src/pay.py"])

    def test_allows_write_that_removes_marker(self):
        result = self.core._feedback_gate(
            self._event({"full_content": True, "content": "def retry(): pass"}), {}, self.snapshot)
        self.assertIsNone(result)

    def test_skips_when_snapshot_has_no_feedback_state(self):
        # 어댑터가 주입 안 함(기능 off·구형 코어) → 판정하지 않는다(하위호환).
        event = self._event({"full_content": True, "content": self.on_disk})
        self.assertIsNone(self.core._feedback_gate(event, {}, {}))
        self.assertIsNone(self.core._feedback_gate(event, {}, {"feedback": {"enabled": False}}))

    def test_untouched_files_do_not_block(self):
        result = self.core._feedback_gate(
            {"changes": [{"path": "src/other.py", "full_content": True, "content": "x"}]},
            {}, self.snapshot)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
