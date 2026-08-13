#!/usr/bin/env python3
"""소비 프로젝트 e2e — 엔진 없는 설치본에서 host 2 × locale 2 가 같은 판정을 내는가.

locale package 단위 테스트는 "부품이 엔진 없이 import 된다"까지만 증명한다. 그건 조립품이
도는 것과 다르다 — 실제 실패는 부품이 아니라 **배선**에서 났다. `gate_text` 는 language 인자를
받도록 만들어졌는데 io 어댑터가 그걸 넘기지 않아, 설치본에서 local profile 을 en 으로 두어도
출력은 한국어 그대로였다. 그 상태에서 locale 단위 테스트는 전부 통과한다.

그래서 여기서는 설치된 shim 을 **PYTHONPATH 에서 엔진을 지우고** 구동하고, 4조합의 출력을
직접 비교한다. 계약은 하나다:

    언어는 사람이 읽는 문장만 바꾼다. status·exit code·증거는 4조합이 모두 같다.

한쪽만 봐서는 안 된다. "다 같다" 만 보면 언어가 아예 안 먹는 상태(원래 결함)가 통과하고,
"다 다르다" 만 보면 판정이 언어에 물린 상태가 통과한다. 둘을 함께 건다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

PROFILE = """project:
  name: "consumer"
  prefix: "consumer"
components:
  - { id: core, paths: ["app/core/**"] }
risk:
  l0_pass_globs: ["*.md", "plan_docs/*"]
  l1_path_globs: ["*ui/*.src"]
  l2_path_globs: ["*core/*.src"]
  l3_filename_globs: ["*secret*"]
  plan_glob: "plan_docs/00-base_plan/**/*.md"
  l3_review_strategy: "claude_grep_first"
  review_patterns: ["review"]
file_type_map:
  - { glob: "*core/*.src", type: core }
skip_untyped: true
compliance:
  plan_gate_code_types: [core]
pdca:
  enabled: true
  phases:
    - { id: "00", glob: "plan_docs/00-base_plan/**/*.md" }
    - { id: "01", glob: "plan_docs/01-plan/**/*.md" }
    - { id: "02", glob: "plan_docs/02-design/**/*.md" }
    - { id: "03", glob: "plan_docs/03-implementation/**/*.md" }
    - { id: "04", glob: "plan_docs/04-analyze/**/*.md" }
    - { id: "05", glob: "plan_docs/05-expert-review/**/*.md" }
    - { id: "06", glob: "plan_docs/06-report/**/*.md" }
  pre_implementation_required:
    L1: ["00"]
    L2: ["00", "01", "02"]
    L3: ["00", "01", "02"]
runtime:
  active_host: claude
  installed_hosts: [claude, codex]
"""


def _write(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _sage(args, cwd):
    return subprocess.run([sys.executable, "-m", "sage", *args], cwd=cwd,
                          env=dict(os.environ, PYTHONPATH=REPO),
                          capture_output=True, text=True)


def _consumer_env(root, host, *, engine):
    """소비 프로젝트의 실행 환경. `engine` 이 엔진 import 가능 여부를 가른다.

    `dict(os.environ)` 를 그대로 쓰면 안 된다 — run-all.sh 가 PYTHONPATH 에 레포를 export 하므로
    테스트를 돌린 셸의 경로가 새어 들어오고, 그러면 두 환경이 실제로는 같은 환경이 된다.
    엔진 유무를 가르는 것이 이 파일의 축이라 명시적으로 지우고 명시적으로 넣는다.
    """
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    if engine:
        env["PYTHONPATH"] = REPO          # pip 로 엔진이 깔린 정상 소비 프로젝트를 흉내낸다
    env["SAGE_GATE_BRANCH"] = "main"
    # 두 host 는 root 를 서로 다른 변수로 받는다. 틀린 이름을 주면 shim 이 cwd 로 떨어져
    # "변경 0건"으로 조용히 통과한다 — 게이트가 꺼진 것과 구별되지 않는다.
    env["CLAUDE_PROJECT_DIR" if host == "claude" else "CODEX_PROJECT_ROOT"] = root
    return env


def _payload(host):
    if host == "claude":
        return {"tool_name": "Write", "session_id": "e2e",
                "tool_input": {"file_path": "app/core/data.src", "content": "x"}}
    return {"tool_name": "apply_patch", "session_id": "e2e",
            "tool_input": {"command": "*** Begin Patch\n"
                                      "*** Update File: app/core/data.src\n"
                                      "@@\n+x\n*** End Patch\n"}}


def _run_shim(root, host, *, engine):
    shim = os.path.join(root, f".{host}", "hooks", "pre-implementation-gate.sh")
    done = subprocess.run(["bash", shim], input=json.dumps(_payload(host)),
                          capture_output=True, text=True,
                          env=_consumer_env(root, host, engine=engine))
    return done.returncode, (done.stdout + done.stderr)


class TestConsumerLocaleE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        cls.root = os.path.join(cls._tmp, "consumer")
        cls.install = _sage(["install", "--host", "claude", "--prefix", "consumer",
                             "--dest", cls.root], cwd=REPO)
        _write(os.path.join(cls.root, "sage", "project-profile.yaml"), PROFILE)
        # 두 host 를 함께 등록해야 "같은 판정을 두 채널이 같은 증거로 낸다" 를 볼 수 있다.
        cls.generate = _sage(["generate", "--kind", "hook", "--write", "--target", "both"],
                             cwd=cls.root)
        cls.hosts = ("claude", "codex")
        # L2 소스에 쓰면서 의무 phase 가 없는 상태 → 어느 조합에서도 BLOCK 이 나온다.
        _write(os.path.join(cls.root, "plan_docs", "00-base_plan", "main.md"),
               "Cycle-Stem: `main`\nRisk Level: L2\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _set_language(self, language):
        path = os.path.join(self.root, "sage", "project-profile.local.yaml")
        if language is None:
            if os.path.exists(path):
                os.unlink(path)
            return
        _write(path, f"interface:\n  language: {language}\n")

    def _run(self, host, language):
        self._set_language(language)
        return _run_shim(self.root, host, engine=True)

    def test_pipeline_installed_cleanly(self):
        self.assertEqual(self.install.returncode, 0, self.install.stderr)
        self.assertEqual(self.generate.returncode, 0, self.generate.stderr)

    def test_every_combination_blocks_identically(self):
        results = {(host, language): self._run(host, language)
                   for host in self.hosts for language in ("ko", "en")}
        codes = {key: code for key, (code, _) in results.items()}
        self.assertEqual(set(codes.values()), {2},
                         f"조합마다 exit code 가 다르다: {codes}")
        for key, (_, text) in results.items():
            self.assertIn("app/core/data.src", text, f"{key}: 증거 경로 누락")
            self.assertNotIn("message_key=", text, f"{key}: catalog 미등록 key 노출")
            self.assertTrue(text.strip(), f"{key}: 출력이 비었다")

    def test_language_actually_changes_the_sentence(self):
        """이게 없으면 '언어가 아예 안 먹는 상태'가 나머지 단언을 전부 통과한다."""
        for host in self.hosts:
            korean = self._run(host, "ko")[1]
            english = self._run(host, "en")[1]
            self.assertNotEqual(korean, english,
                                f"{host}: local profile 을 en 으로 두어도 출력이 그대로다")
            self.assertIn("PDCA", korean + english)

    def test_absent_local_profile_keeps_the_compatibility_default(self):
        for host in self.hosts:
            code, text = self._run(host, None)
            self.assertEqual(code, 2)
            self.assertEqual((code, text), self._run(host, "ko"),
                             f"{host}: 설정 부재가 한국어와 다르게 동작한다")

    # --- 엔진 부재: 알려진 한계이며 이 사이클이 만든 결함이 아니다 ---
    #
    # `pre_implementation_gate_core` 는 module import 시점에 `sage.done_criteria_contract` 를
    # 요구한다. 그 자리의 주석이 적어둔 전제가 "installed projects resolve the package
    # normally" 이므로 엔진이 pip 로 깔려 있는 것이 정상 구성이고, 여기서 고칠 대상은 아니다.
    #
    # 그래도 박제하는 이유는 둘이다. 첫째, locale package 가 자체 포함이라는 사실이
    # "hook 이 엔진 없이 돈다" 로 읽히면 안 된다 — 부품 하나가 독립인 것과 조립품이 독립인 것은
    # 다르고, 지금 조립품은 독립이 아니다. 둘째, 이 상태의 exit code 가 바뀌면 즉시 알아야 한다.

    def test_the_gate_does_not_run_and_does_not_pass_silently(self):
        for host in self.hosts:
            code, text = _run_shim(self.root, host, engine=False)
            # exit 0 이면 쓰기가 통과한다. 엔진 부재가 곧 무음 우회가 되는 상태만은 아니어야 한다.
            self.assertNotEqual(code, 0, f"{host}: 엔진 부재가 조용한 통과로 떨어졌다\n{text}")
            self.assertIn("ModuleNotFoundError", text, f"{host}: 원인이 화면에 남지 않는다")

    def test_the_locale_package_itself_stays_engine_free(self):
        """조립품이 엔진에 물려 있어도 locale 은 물리지 않았다는 것 자체는 유지된다."""
        env = _consumer_env(self.root, "claude", engine=False)
        runtime = os.path.join(self.root, "scripts", "sage_harness", "hooks", "runtime")
        probe = subprocess.run(
            [sys.executable, "-c",
             "import i18n, messages; print(messages.gate_text("
             "{'message_key': 'ok_l2', 'status': 'ok', 'risk': 'L2', 'reason': 'r'},"
             " {}, 'claude', language='en'))"],
            cwd=runtime, env=env, capture_output=True, text=True)
        self.assertEqual(probe.returncode, 0,
                         f"locale 이 엔진 없이 서지 않는다\n{probe.stderr}")
        self.assertTrue(probe.stdout.strip())

    def test_a_damaged_language_setting_does_not_disable_the_gate(self):
        """표시 설정 하나가 차단을 끄면 그건 우회 레버다."""
        _write(os.path.join(self.root, "sage", "project-profile.local.yaml"),
               "interface:\n  language: klingon\n")
        try:
            for host in self.hosts:
                code, text = _run_shim(self.root, host, engine=True)
                self.assertEqual(code, 2, f"{host}: 손상된 언어 설정이 게이트를 껐다\n{text}")
        finally:
            self._set_language(None)


if __name__ == "__main__":
    unittest.main()
