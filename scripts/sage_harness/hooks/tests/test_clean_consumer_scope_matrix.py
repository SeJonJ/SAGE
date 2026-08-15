#!/usr/bin/env python3
"""소비 프로젝트 e2e — Claude/Codex × global/project-local/dual scope 가 clean 하게 서는가.

`test_locale_consumer_e2e.py`가 host 2 × locale 2 축에서 게이트 판정이 갈라지지 않음을 증명한다면,
여기서는 다른 축이다: Codex CORE skill scope(global/project-local/dual)를 실제 `sage install`
subprocess로 골라 설치한 뒤, `sage doctor`가 실제로 그 상태를 clean 하게(또는 dual 이면 명시적으로
드러나게) 보고하는가. `test_install.py`의 scope 테스트는 `install.run(Args(...))`를 직접 불러
파일 배치·manifest 값을 촘촘히 본다 — 그건 부품이 맞다는 증명이고, 이 파일이 보는 것은 실제 CLI
진입점(`python -m sage install`)으로 설치한 뒤 실제 CLI 진입점(`python -m sage doctor`)이 그 결과를
스스로 어떻게 판독하는지, 즉 조립품이다.

dual(전역+project-local 동시 존재)은 실패가 아니다 — `sage doctor`가 "duplicate; precedence=ambiguous"
로 **드러내는 것**이 계약이다. 조용히 한쪽을 골라버리면 사용자가 실제로 어느 스킬이 host 에 읽히는지
모른 채로 넘어간다.
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))


def _sage(args, cwd, env=None):
    full_env = {**os.environ, "PYTHONPATH": REPO}
    full_env.pop("CODEX_HOME", None)
    if env:
        full_env.update(env)
    return subprocess.run([sys.executable, "-m", "sage", *args], cwd=cwd, env=full_env,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)


class TestCleanConsumerScopeMatrix(unittest.TestCase):
    def _dest(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return tmp.name

    def _doctor(self, dest, env=None):
        return _sage(["doctor"], cwd=dest, env=env)

    def test_claude_clean_install_reports_healthy(self):
        dest = self._dest()
        install = _sage(["install", "--host", "claude", "--prefix", "consumer",
                         "--dest", dest], cwd=REPO)
        self.assertEqual(install.returncode, 0, install.stdout + install.stderr)

        doctor = self._doctor(dest)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertNotIn("duplicate", doctor.stdout)

    def test_codex_global_scope_clean_install_reports_healthy(self):
        dest = self._dest()
        codex_home = self._dest()
        install = _sage(["install", "--host", "codex", "--prefix", "consumer",
                         "--dest", dest, "--skill-scope", "global"],
                        cwd=REPO, env={"CODEX_HOME": codex_home})
        self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
        self.assertTrue(os.path.isfile(
            os.path.join(codex_home, "skills", "sage-init", "SKILL.md")))
        self.assertFalse(os.path.exists(
            os.path.join(dest, ".codex", "skills", "sage-init", "SKILL.md")))

        doctor = self._doctor(dest, env={"CODEX_HOME": codex_home})
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertIn("intended scope: global", doctor.stdout)
        self.assertNotIn("duplicate", doctor.stdout)

    def test_codex_project_local_scope_clean_install_reports_healthy(self):
        dest = self._dest()
        codex_home = self._dest()
        install = _sage(["install", "--host", "codex", "--prefix", "consumer",
                         "--dest", dest, "--skill-scope", "project-local"],
                        cwd=REPO, env={"CODEX_HOME": codex_home})
        self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
        self.assertTrue(os.path.isfile(
            os.path.join(dest, ".codex", "skills", "sage-init", "SKILL.md")))
        self.assertFalse(os.path.exists(
            os.path.join(codex_home, "skills", "sage-init", "SKILL.md")))

        doctor = self._doctor(dest, env={"CODEX_HOME": codex_home})
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertIn("intended scope: project-local", doctor.stdout)
        self.assertNotIn("duplicate", doctor.stdout)

    def test_codex_dual_scope_is_reported_not_silently_dropped(self):
        """scope 전환은 이전 사본을 지우지 않는다(§ test_install.py 기존 계약) — doctor 가
        이 상태를 조용히 넘기면 사용자는 실제 host 가 어느 사본을 읽는지 알 방법이 없다."""
        dest = self._dest()
        codex_home = self._dest()
        env = {"CODEX_HOME": codex_home}
        first = _sage(["install", "--host", "codex", "--prefix", "consumer",
                      "--dest", dest, "--skill-scope", "project-local"], cwd=REPO, env=env)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = _sage(["install", "--host", "codex", "--prefix", "consumer",
                       "--dest", dest, "--skill-scope", "global", "--force"], cwd=REPO, env=env)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

        # 전환이 실제로 두 사본을 남겼는지 먼저 확인 — 그래야 아래 doctor 단언이 dual 을 본다.
        self.assertTrue(os.path.isfile(
            os.path.join(dest, ".codex", "skills", "sage-init", "SKILL.md")))
        self.assertTrue(os.path.isfile(
            os.path.join(codex_home, "skills", "sage-init", "SKILL.md")))

        doctor = self._doctor(dest, env=env)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertIn("duplicate", doctor.stdout)
        self.assertIn("precedence=ambiguous", doctor.stdout)
        self.assertIn("intended scope: global", doctor.stdout)


if __name__ == "__main__":
    unittest.main()
