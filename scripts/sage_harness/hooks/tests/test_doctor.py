#!/usr/bin/env python3
"""sage doctor 검증 (중 등급 — profile 로드 실패 원인 구분, Codex P1).

parse_error(설정 무시됨) = FAIL(exit 1) / missing_file·missing_pyyaml = WARN/INFO(exit 0).
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import doctor, install  # noqa: E402

try:
    import yaml  # noqa: F401
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


class Args:
    def __init__(self, profile=None):
        self.profile = profile


def run_doctor(profile_path):
    out = io.StringIO()
    with redirect_stdout(out):
        rc = doctor.run(Args(profile=profile_path))
    return rc, out.getvalue()


class TestDoctor(unittest.TestCase):
    def test_load_profile_missing_file(self):
        self.assertEqual(doctor._load_profile("/no/such/profile.yaml")[1], "missing_file")

    def test_missing_file_exit0(self):
        rc, out = run_doctor("/no/such/profile.yaml")
        self.assertEqual(rc, 0)
        self.assertIn("profile 없음", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요(parse 단계 도달)")
    def test_parse_error_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.yaml")
            Path(p).write_text("risk:\n  globs: [unclosed\n")   # 잘못된 flow sequence
            rc, out = run_doctor(p)
            self.assertEqual(rc, 1)            # 설정이 깨졌으면 FAIL
            self.assertIn("파싱 오류", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_ok_profile_exit0(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.yaml")
            Path(p).write_text("runtime: { host: codex }\noptions: { cross_model: false }\n")
            rc, out = run_doctor(p)
            self.assertEqual(rc, 0)
            self.assertEqual(doctor._load_profile(p)[1], "ok")

    def test_env_section_reports_sage_hook(self):
        # W2b: hook 등록이 sage-hook 콘솔 스크립트에 의존 → doctor 실행환경이 이를 진단해야.
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.yaml")
            Path(p).write_text("runtime: { host: codex }\noptions: { cross_model: false }\n")
            _, out = run_doctor(p)
            self.assertIn("## 실행 환경", out)
            self.assertIn("sage-hook", out)

    def _codex_skill_project(self, root):
        import json
        os.makedirs(os.path.join(root, "sage"))
        os.makedirs(os.path.join(root, "docs", "sage_harness"))
        os.makedirs(os.path.join(root, ".codex", "skills", "sk1"))
        Path(os.path.join(root, ".codex", "skills", "sk1", "SKILL.md")).write_text("---\nname: sk1\n---\nbody\n")
        Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).write_text(
            json.dumps({"assets": {"skills/sk1": {"form": "interpretive"}}}))

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_codex_skill_deployment_warns_when_missing(self):
        # Part C P1: codex-host + manifest skill + repo 정본 있으나 전역 미배포 → WARN
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as ch:
            self._codex_skill_project(root)
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "px" }\nruntime: { host: codex }\n')
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                rc, out = run_doctor(prof)
            self.assertIn("sk1", out)
            self.assertIn("전역 미배포", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_codex_skill_deployment_ok_when_deployed(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as ch:
            self._codex_skill_project(root)
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "px" }\nruntime: { host: codex }\n')
            gdir = os.path.join(ch, "skills", "px-sk1"); os.makedirs(gdir)
            Path(os.path.join(gdir, "SKILL.md")).write_text("---\nname: sk1\n---\nbody\n")   # 정본과 동일
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                rc, out = run_doctor(prof)
            self.assertIn("전역 배포 최신", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_codex_skill_deployment_empty_prefix_blocks(self):
        # Part C P2: 빈 prefix → bare-id 점검 금지(generate fail-closed 와 일관), prefix 설정 안내
        with tempfile.TemporaryDirectory() as root:
            self._codex_skill_project(root)
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "" }\nruntime: { host: codex }\n')
            rc, out = run_doctor(prof)
            self.assertIn("project.prefix 미설정", out)
            self.assertNotIn("전역 미배포", out)   # bare-id 점검 안 함

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_claude_host_skips_codex_deployment_check(self):
        # Part C P1: claude-host 는 codex skill 배포 점검을 건너뜀(거짓 WARN 금지)
        with tempfile.TemporaryDirectory() as root:
            self._codex_skill_project(root)
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "px" }\nruntime: { host: claude }\n')
            rc, out = run_doctor(prof)
            self.assertNotIn("codex skill 전역 배포", out)
            self.assertNotIn("codex CORE skill 전역 설치 상태", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_codex_core_skill_drift_warns_when_stale(self):
        # 5차 root cause: manifest 추적 skill 이 아니라 hand-shipped CORE skill($sage-init 등)이 stale 이어도
        # doctor 가 직접 보여줘야 한다.
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as ch:
            os.makedirs(os.path.join(root, "sage"))
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "px" }\nruntime: { host: codex }\n')
            stale = os.path.join(ch, "skills", "sage-init")
            os.makedirs(stale)
            Path(os.path.join(stale, "SKILL.md")).write_text("OLD_STALE\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                rc, out = run_doctor(prof)
            self.assertEqual(rc, 0)
            self.assertIn("codex CORE skill 전역 설치 상태", out)
            self.assertIn("sage-init", out)
            self.assertIn("stale", out)
            self.assertIn("sage install --host codex --force", out)

    @unittest.skipUnless(_HAS_YAML, "pyyaml 필요")
    def test_codex_core_skill_doctor_agrees_with_install_status(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as ch:
            class IArgs:
                host = "codex"; dest = root; prefix = "px"; force = True; no_global_skill = False
            os.makedirs(os.path.join(root, "sage"))
            prof = os.path.join(root, "sage", "project-profile.yaml")
            Path(prof).write_text('project: { name: "t", prefix: "px" }\nruntime: { host: codex }\n')
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                install.run(IArgs())
                for sid in install.core_skill_ids():
                    self.assertEqual(install.codex_core_skill_status(sid)[0], "ok", sid)
                rc, out = run_doctor(prof)
            self.assertEqual(rc, 0)
            for sid in install.core_skill_ids():
                self.assertIn(f"{sid}: 최신", out)

    def test_codex_core_skill_status_rejects_unsafe_id(self):
        status, info = install.codex_core_skill_status("../escape")
        self.assertEqual(status, "error")
        self.assertIn("unsafe", info)

    def test_codex_core_skill_status_missing(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as ch:
            with mock.patch.dict(os.environ, {"CODEX_HOME": ch}):
                status, dst = install.codex_core_skill_status("sage-init")
            self.assertEqual(status, "missing")
            self.assertIn("sage-init", dst)

    def test_codex_core_skill_status_source_missing(self):
        import unittest.mock as mock
        with mock.patch("sage.commands.install._core_skill_source", return_value="/no/such/SKILL.md"):
            status, dst = install.codex_core_skill_status("sage-init")
        self.assertEqual(status, "source_missing")
        self.assertIsNone(dst)


if __name__ == "__main__":
    unittest.main(verbosity=2)
