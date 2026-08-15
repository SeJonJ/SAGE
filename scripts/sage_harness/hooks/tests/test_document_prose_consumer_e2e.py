#!/usr/bin/env python3
"""AC20·AC24·AC25 — 실제 설치된 shim(엔진 in-process 호출이 아니라 물리 hook 스크립트)이
Claude/Codex 두 host 에서 문서 언어·본문 언어 위반을 쓰기 전에 막는가.

`test_document_language.py::TestProseGateWiring` 은 `pre_implementation_gate_core.decide()`
를 직접 부른다 — core 함수가 옳다는 증거이지 조립품(설치된 `.claude/hooks/*.sh` ·
`.codex/hooks/*.sh` 가 실제로 그 core 를 불러 같은 판정을 내는가)의 증거는 아니다.
`test_locale_consumer_e2e.py` 가 그 조립품 축을 이미 증명하지만 대상은 marker 충돌·표시
언어뿐이다. 여기서는 같은 방식으로 **본문(prose) 언어 위반**을 태운다.

Claude-host 축만 실제로 확인 가능하다(이 세션 자체가 Claude host 다). Codex 어댑터는 같은
shim 계약으로 함께 태우되, 실제 Codex 런타임에서의 사람 판단·자연어 품질까지는 확인하지
않는다 — Phase 04 acceptance 는 이 한계를 "Claude-host 축 완료, Codex/human 축 잔존"으로
기록하고, 이 파일 하나로 AC20/24/34 전체를 PASS 로 올리지 않는다.
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
  l0_pass_globs: ["*.md", "plan_docs/**"]
  l2_path_globs: ["*core/*.src"]
  plan_glob: "plan_docs/00-base_plan/**/*.md"
pdca:
  enabled: true
  phases:
    - { id: "00", glob: "plan_docs/00-base_plan/**/*.md" }
    - { id: "01", glob: "plan_docs/01-plan/**/*.md" }
"""

PHASE00 = ("Cycle-Stem: `demo`\nRisk Level: L1\nDocument-Language: en\n\n"
          "English narrative for the base plan.\n")


def _write(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _sage(args, cwd):
    return subprocess.run([sys.executable, "-m", "sage", *args], cwd=cwd,
                          env=dict(os.environ, PYTHONPATH=REPO),
                          capture_output=True, text=True)


def _consumer_env(root, host):
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["PYTHONPATH"] = REPO
    env["SAGE_GATE_BRANCH"] = "main"
    env["CLAUDE_PROJECT_DIR" if host == "claude" else "CODEX_PROJECT_ROOT"] = root
    return env


def _claude_payload(body):
    return {"tool_name": "Write", "session_id": "e2e",
            "tool_input": {"file_path": "plan_docs/01-plan/demo.md", "content": body}}


def _codex_payload(body):
    added = "\n".join(f"+{line}" for line in body.splitlines())
    return {"tool_name": "apply_patch", "session_id": "e2e",
            "tool_input": {"command": ("*** Begin Patch\n"
                                       "*** Add File: plan_docs/01-plan/demo.md\n"
                                       f"{added}\n*** End Patch\n")}}


def _run_shim(root, host, body):
    shim = os.path.join(root, f".{host}", "hooks", "pre-implementation-gate.sh")
    payload = _claude_payload(body) if host == "claude" else _codex_payload(body)
    done = subprocess.run(["bash", shim], input=json.dumps(payload),
                          capture_output=True, text=True, env=_consumer_env(root, host))
    return done.returncode, (done.stdout + done.stderr)


class TestDocumentProseConsumerE2E(unittest.TestCase):
    """실제 설치된 shim 을 통한 AC25 조립품 증거(Claude-host 축)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        cls.root = os.path.join(cls._tmp, "consumer")
        cls.install = _sage(["install", "--host", "claude", "--prefix", "consumer",
                             "--dest", cls.root], cwd=REPO)
        _write(os.path.join(cls.root, "sage", "project-profile.yaml"), PROFILE)
        cls.generate = _sage(["generate", "--kind", "hook", "--write", "--target", "both"],
                             cwd=cls.root)
        cls.hosts = ("claude", "codex")
        _write(os.path.join(cls.root, "plan_docs", "00-base_plan", "demo.md"), PHASE00)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_pipeline_installed_cleanly(self):
        self.assertEqual(self.install.returncode, 0, self.install.stderr)
        self.assertEqual(self.generate.returncode, 0, self.generate.stderr)

    def test_korean_prose_in_a_declared_english_cycle_is_blocked_before_write(self):
        """marker 는 맞아도(`Document-Language: en`) 본문이 한글이면 실제 shim 이 exit 2 로 막는가."""
        body = "Cycle-Stem: `demo`\nDocument-Language: en\n\n이것은 한글 문장입니다.\n"
        for host in self.hosts:
            code, text = _run_shim(self.root, host, body)
            self.assertEqual(code, 2, f"{host}: 한글 본문을 막지 못했다\n{text}")
            self.assertNotIn("message_key=", text, f"{host}: catalog 미등록 key 노출")
            self.assertTrue(text.strip(), f"{host}: 출력이 비었다")

    def test_matching_english_prose_passes(self):
        """marker 도 맞고 본문도 영어면 실제 shim 이 통과시키는가."""
        body = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
               "This plan document is written entirely in English, matching the declared "
               "cycle language, and should pass the gate without any prose objection.\n")
        for host in self.hosts:
            code, text = _run_shim(self.root, host, body)
            self.assertEqual(code, 0, f"{host}: 정상 영어 본문을 막았다\n{text}")

    def test_quoted_external_evidence_does_not_false_positive_through_the_real_shim(self):
        """인용된 외부 evidence(blockquote)는 실제 shim 경로에서도 과차단하지 않는가."""
        body = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
               "The tool printed the following Korean message verbatim during testing:\n\n"
               "> 이것은 외부 도구가 실제로 출력한 한글 원문입니다\n\n"
               "The English narrative around the quoted evidence continues here without "
               "any issue at all, describing what happened next in the plan.\n")
        for host in self.hosts:
            code, text = _run_shim(self.root, host, body)
            self.assertEqual(code, 0, f"{host}: 인용된 외부 evidence 를 과차단했다\n{text}")


if __name__ == "__main__":
    unittest.main()
