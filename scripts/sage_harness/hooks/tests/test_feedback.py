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

    def test_non_git_directory_yields_no_markers(self):
        with tempfile.TemporaryDirectory() as root:
            self._write(root, "a.py", "# sage-feedback :: git 아님")
            self.assertEqual(fb.scan(root, {}), [])


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
        self.assertTrue(any(sev == "FAIL" and "미지 키" in msg for sev, msg in issues), issues)

    def test_validator_warns_when_block_release_has_no_scanner(self):
        issues = _feedback_issues({"feedback": {"block_release": True}})
        self.assertTrue(any(sev == "WARN" and "무동작" in msg for sev, msg in issues), issues)

    def test_valid_section_is_clean(self):
        self.assertEqual(_feedback_issues({"feedback": {
            "enabled": True, "block_release": False, "record": False, "record_target": "auto"}}), [])
        self.assertEqual(_feedback_issues({}), [])


class TestCli(unittest.TestCase):
    def _run(self, root, *extra):
        return subprocess.run([sys.executable, "-m", "sage.cli", "feedback", "--root", root, *extra],
                              capture_output=True, text=True, cwd=REPO)

    def _project(self, root, enabled=True):
        subprocess.run(["git", "init", "-q", root], check=True)
        for key, value in (("user.email", "t@t"), ("user.name", "t")):
            subprocess.run(["git", "-C", root, "config", key, value], check=True)
        os.makedirs(os.path.join(root, "sage"), exist_ok=True)
        with open(os.path.join(root, "sage", "project-profile.yaml"), "w", encoding="utf-8") as handle:
            handle.write("project: { name: demo }\npaths: { plan_docs: plan_docs }\n"
                         f"feedback: {{ enabled: {'true' if enabled else 'false'} }}\n")
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

    def test_disabled_profile_does_not_scan(self):
        with tempfile.TemporaryDirectory() as root:
            self._project(root, enabled=False)
            result = self._run(root, "--output", "json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"enabled": False, "markers": []})


if __name__ == "__main__":
    unittest.main(verbosity=2)
