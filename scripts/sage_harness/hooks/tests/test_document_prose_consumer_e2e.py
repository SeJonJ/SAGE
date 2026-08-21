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


def _claude_edit_payload(old, new):
    return {"tool_name": "Edit", "session_id": "e2e",
            "tool_input": {"file_path": "plan_docs/01-plan/demo.md",
                           "old_string": old, "new_string": new}}


def _codex_update_payload(removed, added, context=()):
    """apply_patch(v4a) Update File hunk. context 는 문맥줄(공백 접두)로, 실제 Codex 가 내는
    형태와 같다 — 문맥이 없으면 붙는 위치를 확정할 수 없어 게이트가 fail-closed 로 떨어진다."""
    lines = ["@@"]
    lines += [f" {line}" for line in context]
    lines += [f"-{line}" for line in removed.splitlines()]
    lines += [f"+{line}" for line in added.splitlines()]
    body = "\n".join(lines)
    return {"tool_name": "apply_patch", "session_id": "e2e",
            "tool_input": {"command": ("*** Begin Patch\n"
                                       "*** Update File: plan_docs/01-plan/demo.md\n"
                                       f"{body}\n*** End Patch\n")}}


def _run_payload(root, host, payload):
    shim = os.path.join(root, f".{host}", "hooks", "pre-implementation-gate.sh")
    done = subprocess.run(["bash", shim], input=json.dumps(payload),
                          capture_output=True, text=True, env=_consumer_env(root, host))
    return done.returncode, (done.stdout + done.stderr)


def _run_shim(root, host, body):
    return _run_payload(root, host,
                        _claude_payload(body) if host == "claude" else _codex_payload(body))


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

    def test_a_korean_explanation_after_a_status_marker_is_blocked(self):
        """`Status:` 뒤 고정 enum 만 기계값이다 — 그 뒤 설명까지 marker 라는 이유로 빼면
        선언 언어와 다른 글을 marker 줄에 적는 것으로 검사를 통째로 우회할 수 있다."""
        body = ("Cycle-Stem: `demo`\nDocument-Language: en\n"
               "Status: NOT READY — 아직 구현되지 않음\n\nEnglish body.\n")
        for host in self.hosts:
            code, text = _run_shim(self.root, host, body)
            self.assertEqual(code, 2, f"{host}: marker 뒤 한글 설명을 놓쳤다\n{text}")

    def test_the_english_screen_carries_no_generated_korean(self):
        """표시 언어가 en 이면 설명은 전부 영어여야 한다 — 인용된 원문 조각만 한글로 남는다."""
        path = os.path.join(self.root, "sage", "project-profile.local.yaml")
        _write(path, "interface:\n  language: en\n")
        try:
            body = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                   "이것은 한글 문장입니다.\n")
            for host in self.hosts:
                code, text = _run_shim(self.root, host, body)
                self.assertEqual(code, 2, f"{host}: 막지 못했다\n{text}")
                self.assertIn("이것은 한글 문장입니다", text, f"{host}: 원문 조각이 사라졌다")
                residue = text.replace("이것은 한글 문장입니다", "")
                self.assertNotRegex(residue, r"[가-힣]",
                                    f"{host}: 영어 화면에 생성된 한국어가 섞였다\n{text}")
        finally:
            os.unlink(path)

    KOREAN_LAST_LINE = "이 문서는 한국어로 작성된 정상 계획 문서입니다. 표본을 넘길 만큼 충분히 깁니다."
    ENGLISH_PARAGRAPH = ("The upstream release note is quoted here verbatim because "
                         "translating it would change the evidence being cited.")

    def _korean_cycle(self):
        """00·01 이 모두 ko 로 선언된 사이클을 디스크에 놓고, 정리까지 등록한다."""
        _write(os.path.join(self.root, "plan_docs", "00-base_plan", "demo.md"),
               "Cycle-Stem: `demo`\nRisk Level: L1\nDocument-Language: ko\n\n"
               "한국어로 작성된 기준 계획입니다. 이 문서 역시 충분한 분량을 갖추고 있습니다.\n")
        phase01 = os.path.join(self.root, "plan_docs", "01-plan", "demo.md")
        _write(phase01, "Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
                        f"{self.KOREAN_LAST_LINE}\n")
        self.addCleanup(_write, os.path.join(self.root, "plan_docs", "00-base_plan", "demo.md"),
                        PHASE00)
        self.addCleanup(lambda: os.path.exists(phase01) and os.unlink(phase01))
        return phase01

    def test_a_partial_english_edit_to_a_korean_document_is_not_blocked(self):
        """부분 diff 를 문서 전체로 오해하면, 정상 한국어 문서에 영어 한 문단을 더하는 편집이
        곧바로 막힌다. 두 host 의 부분 diff 경로(Edit / Update File)를 모두 태운다."""
        self._korean_cycle()
        keep, added = self.KOREAN_LAST_LINE, self.ENGLISH_PARAGRAPH
        for host, payload in (
                ("claude", _claude_edit_payload(keep, f"{keep}\n\n{added}")),
                ("codex", _codex_update_payload("", f"\n{added}", context=[keep]))):
            code, text = _run_payload(self.root, host, payload)
            self.assertEqual(code, 0, f"{host}: 부분 diff 를 문서 전체로 오해해 막았다\n{text}")

    def test_replacing_the_last_korean_line_blocks_on_both_hosts(self):
        """검수 재현 1 — 마지막 한국어 본문을 영어로 교체하면 문서에 한국어가 남지 않는다.
        부분 diff 를 되짚지 않으면 이 편집이 조용히 통과한다."""
        self._korean_cycle()
        gone, added = self.KOREAN_LAST_LINE, self.ENGLISH_PARAGRAPH
        for host, payload in (("claude", _claude_edit_payload(gone, added)),
                              ("codex", _codex_update_payload(f"{gone}\n", f"{added}\n"))):
            code, text = _run_payload(self.root, host, payload)
            self.assertEqual(code, 2, f"{host}: 마지막 한국어 제거를 놓쳤다\n{text}")

    def test_appending_after_an_unclosed_fence_blocks_on_both_hosts(self):
        """검수 재현 2 — 닫히지 않은 fence 뒤에 본문을 추가하면 그 뒤가 전부 code 로 삼켜진다.
        되짚은 전체 본문에 물어야만 이 상태가 드러난다."""
        self._korean_cycle()
        keep = self.KOREAN_LAST_LINE
        appended = "\n```text\n추가된 한국어 본문입니다.\n"
        for host, payload in (
                ("claude", _claude_edit_payload(keep, keep + appended)),
                ("codex", _codex_update_payload("", appended, context=[keep]))):
            code, text = _run_payload(self.root, host, payload)
            self.assertEqual(code, 2, f"{host}: 닫히지 않은 fence 를 놓쳤다\n{text}")

    @staticmethod
    def _codex_move_payload(source, destination, removed, added):
        """`Update File` + `Move to` — 이동과 수정을 한 번에 하는 실제 apply_patch 형태."""
        lines = ([f"-{line}" for line in removed.splitlines()]
                 + [f"+{line}" for line in added.splitlines()])
        body = "\n".join(["@@"] + lines)
        return {"tool_name": "apply_patch", "session_id": "e2e",
                "tool_input": {"command": (f"*** Begin Patch\n*** Update File: {source}\n"
                                           f"*** Move to: {destination}\n{body}\n*** End Patch\n")}}

    def _scratch_move(self, body):
        """사이클 밖 이름(scratch)에서 사이클 문서 이름(demo)으로 옮기면서 본문을 바꾼다."""
        self._korean_cycle()
        os.unlink(os.path.join(self.root, "plan_docs", "01-plan", "demo.md"))
        source = os.path.join(self.root, "docs", "scratch.md")
        original = "Document-Language: ko\n\n임시로 적어둔 한국어 초안입니다.\n"
        _write(source, original)
        self.addCleanup(lambda: os.path.exists(source) and os.unlink(source))
        return _run_payload(self.root, "codex", self._codex_move_payload(
            "docs/scratch.md", "plan_docs/01-plan/demo.md", original, body))

    def test_moving_an_english_only_body_into_a_korean_cycle_blocks(self):
        """검수 재현 — 판정을 source stem 기준으로 하면 `scratch` 로 걸러져 사이클 밖으로 빠지고,
        목적지는 move 라 post-image 가 없어 구조 검사를 건너뛴다. 그 조합이 검사 전체를 우회한다."""
        code, text = self._scratch_move(
            "Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
            "This document is written entirely in English even though the cycle it lands "
            "in declares Korean, which is exactly the structural mistake to catch.\n")
        self.assertEqual(code, 2, f"이동+수정으로 문서 검사를 우회했다\n{text}")

    def test_moving_a_proper_korean_body_into_a_korean_cycle_passes(self):
        code, text = self._scratch_move(
            "Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
            "이 문서는 한국어로 작성된 정상 계획 문서이며 표본을 넘길 만큼 충분히 깁니다.\n")
        self.assertEqual(code, 0, f"정상 한국어 이동을 막았다\n{text}")

    def _move_only(self, body):
        """hunk 없는 순수 rename — 내용은 그대로 목적지로 간다."""
        self._korean_cycle()
        os.unlink(os.path.join(self.root, "plan_docs", "01-plan", "demo.md"))
        source = os.path.join(self.root, "docs", "scratch.md")
        _write(source, body)
        self.addCleanup(lambda: os.path.exists(source) and os.unlink(source))
        return _run_payload(self.root, "codex", {
            "tool_name": "apply_patch", "session_id": "e2e",
            "tool_input": {"command": ("*** Begin Patch\n*** Update File: docs/scratch.md\n"
                                       "*** Move to: plan_docs/01-plan/demo.md\n"
                                       "*** End Patch\n")}})

    def test_a_move_only_rename_of_a_proper_korean_document_passes(self):
        """hunk 없는 rename 의 목적지 content 는 비어 있다. 되짚은 본문을 결속에 연결하지 않으면
        정상 rename 이 `Cycle-Stem:` 을 못 읽어 결속 단계에서 막힌다 — 제품 결함이다."""
        code, text = self._move_only(
            "Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
            "한국어로 충분히 길게 작성된 정상 계획 본문이며 표본 하한을 넘깁니다.\n")
        self.assertEqual(code, 0, f"정상 move-only rename 을 막았다\n{text}")

    def test_a_move_only_rename_of_an_english_body_blocks_on_the_body(self):
        code, text = self._move_only(
            "Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
            "This document is written entirely in English even though the cycle it lands "
            "in declares Korean, which is exactly the structural mistake to catch.\n")
        self.assertEqual(code, 2, f"move-only 로 본문 언어 검사를 우회했다\n{text}")
        self.assertNotIn("binding", text)       # 결속이 아니라 본문 언어 사유여야 한다

    def test_a_move_only_rename_with_a_damaged_marker_blocks(self):
        code, text = self._move_only(
            "Cycle-Stem: `demo`\nDocument-Language: ko\nDocument-Language: en\n\n"
            "한국어로 충분히 길게 작성된 정상 계획 본문이며 표본 하한을 넘깁니다.\n")
        self.assertEqual(code, 2, f"move-only 로 손상된 marker 를 통과시켰다\n{text}")

    def test_a_move_only_rename_without_a_stem_declaration_still_blocks(self):
        """되짚은 본문을 쓴다고 해서 결속 검사가 느슨해지지는 않는다."""
        code, text = self._move_only(
            "Document-Language: ko\n\n선언 없이 옮겨온 한국어 초안입니다. 충분히 깁니다.\n")
        self.assertEqual(code, 2, text)
        self.assertIn("binding", text)

    def test_deleting_a_fence_that_exposes_korean_blocks_on_both_hosts(self):
        """검수 재현 — 새 줄이 하나도 없어도 부채는 늘어난다. fence 를 지우면 안에 있던
        한국어가 본문이 되는데, '추가된 줄' 만 보는 모델은 이 경로를 놓친다."""
        phase01 = self._english_cycle_with_a_fence()
        _write(phase01, "Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                        "The tool prints the following output:\n"
                        "```text\n기존 한글 예시 출력\n```\n"
                        "The English narrative continues after the example block.\n")
        for host, payload in (
                ("claude", _claude_edit_payload("```text\n기존 한글 예시 출력\n```",
                                                "기존 한글 예시 출력")),
                ("codex", _codex_update_payload("```text\n", "",
                                                context=["The tool prints the following output:"]))):
            code, text = _run_payload(self.root, host, payload)
            self.assertEqual(code, 2, f"{host}: fence 삭제로 드러난 한국어를 놓쳤다\n{text}")

    def test_a_move_whose_source_hunk_does_not_match_fails_closed(self):
        self._korean_cycle()
        os.unlink(os.path.join(self.root, "plan_docs", "01-plan", "demo.md"))
        source = os.path.join(self.root, "docs", "scratch.md")
        _write(source, "Document-Language: ko\n\n임시로 적어둔 한국어 초안입니다.\n")
        self.addCleanup(lambda: os.path.exists(source) and os.unlink(source))
        code, text = _run_payload(self.root, "codex", self._codex_move_payload(
            "docs/scratch.md", "plan_docs/01-plan/demo.md",
            "디스크에 없는 줄입니다.\n", "English replacement.\n"))
        self.assertEqual(code, 2, f"이동 경로의 재구성 실패가 조용한 통과로 떨어졌다\n{text}")

    def _english_cycle_with_a_fence(self):
        """00·01 이 모두 en 이고, 01 에 이미 code fence 가 있는 사이클."""
        phase01 = os.path.join(self.root, "plan_docs", "01-plan", "demo.md")
        _write(phase01, "Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                        "The tool prints the following output:\n"
                        "```text\n기존 한글 예시 출력\n```\n"
                        "The English narrative continues after the example block.\n")
        self.addCleanup(lambda: os.path.exists(phase01) and os.unlink(phase01))
        return phase01

    def _english_cycle(self):
        """00·01 이 모두 en 으로 선언된 사이클."""
        phase01 = os.path.join(self.root, "plan_docs", "01-plan", "demo.md")
        _write(phase01, "Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                        "The existing plan body is written in English throughout.\n")
        self.addCleanup(lambda: os.path.exists(phase01) and os.unlink(phase01))
        return phase01

    def test_flipping_the_language_marker_of_an_english_cycle_blocks(self):
        """검수 재현 — 쓰기 **전** snapshot 만 비교하면 이번 쓰기가 바꾸는 선언 자체가 검사에서
        빠져, en 사이클의 문서를 ko 로 되돌리는 쓰기가 조용히 통과한다."""
        self._english_cycle()
        body = ("Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
                "The body stays English while the declaration flips to Korean.\n")
        for host in self.hosts:
            code, text = _run_shim(self.root, host, body)
            self.assertEqual(code, 2, f"{host}: 이번 변경이 만든 선언 충돌을 놓쳤다\n{text}")

    def test_flipping_the_marker_through_a_partial_edit_blocks(self):
        """전체 쓰기만 보면 되짚어 만든 post-image 경로가 그대로 비어 있다."""
        self._english_cycle()
        for host, payload in (
                ("claude", _claude_edit_payload("Document-Language: en",
                                                "Document-Language: ko")),
                ("codex", _codex_update_payload("Document-Language: en\n",
                                                "Document-Language: ko\n",
                                                context=["Cycle-Stem: `demo`"]))):
            code, text = _run_payload(self.root, host, payload)
            self.assertEqual(code, 2, f"{host}: 부분 편집으로 바뀐 선언을 놓쳤다\n{text}")

    def test_a_marker_damaged_by_this_write_blocks(self):
        self._english_cycle()
        for marker in ("Document-Language: en\nDocument-Language: ko",
                       "Document-Language: fr"):
            body = f"Cycle-Stem: `demo`\n{marker}\n\nThe body stays English throughout.\n"
            for host in self.hosts:
                code, text = _run_shim(self.root, host, body)
                self.assertEqual(code, 2, f"{host}: 이번 쓰기가 만든 손상 선언을 놓쳤다\n{text}")

    def test_a_write_that_keeps_the_declared_language_passes(self):
        self._english_cycle()
        body = ("Cycle-Stem: `demo`\nDocument-Language: en\n\n"
                "The rewritten plan body stays entirely in English and is long enough "
                "to clear the native-prose sample floor without any objection.\n")
        for host in self.hosts:
            code, text = _run_shim(self.root, host, body)
            self.assertEqual(code, 0, f"{host}: 동일 언어 유지 쓰기를 막았다\n{text}")

    @staticmethod
    def _codex_move_only_payload(source, destination):
        return {"tool_name": "apply_patch", "session_id": "e2e",
                "tool_input": {"command": (f"*** Begin Patch\n*** Update File: {source}\n"
                                           f"*** Move to: {destination}\n*** End Patch\n")}}

    def test_moving_a_wrongly_declared_phase_document_out_of_the_cycle_passes(self):
        """검수 재현 — move 는 source(Update File) + destination(Move to) 두 변경이다.
        source 를 일반 수정으로 처리하면, 사라질 문서의 선언이 최종 문서처럼 검사돼
        잘못 선언된 문서를 사이클 밖으로 빼내는 정리 작업 자체가 막힌다."""
        phase01 = os.path.join(self.root, "plan_docs", "01-plan", "demo.md")
        _write(phase01, "Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
                        "잘못된 언어로 선언된 채 남아 있는 문서입니다. 사이클 밖으로 뺍니다.\n")
        self.addCleanup(lambda: os.path.exists(phase01) and os.unlink(phase01))
        archive = os.path.join(self.root, "docs", "archive.md")
        self.addCleanup(lambda: os.path.exists(archive) and os.unlink(archive))
        code, text = _run_payload(self.root, "codex", self._codex_move_only_payload(
            "plan_docs/01-plan/demo.md", "docs/archive.md"))
        self.assertEqual(code, 0, f"사이클 밖으로 빼는 이동을 marker 충돌로 막았다\n{text}")

    def test_moving_a_phase_document_out_while_editing_it_passes(self):
        """최종 목적지가 비-phase 문서인데 source 의 본문을 검사하면, 밖으로 빼면서 정리하는
        편집이 남아 있던 한국어 때문에 막힌다."""
        self._english_cycle_with_a_fence()
        archive = os.path.join(self.root, "docs", "archive.md")
        self.addCleanup(lambda: os.path.exists(archive) and os.unlink(archive))
        code, text = _run_payload(self.root, "codex", self._codex_move_payload(
            "plan_docs/01-plan/demo.md", "docs/archive.md", "```text\n", ""))
        self.assertEqual(code, 0, f"밖으로 빼는 편집을 source 본문 검사로 막았다\n{text}")

    def test_moving_between_phase_paths_judges_the_destination(self):
        """phase → phase 이동은 목적지가 여전히 사이클 문서다 — 검사가 사라지면 안 된다."""
        phase01 = os.path.join(self.root, "plan_docs", "01-plan", "demo.md")
        _write(phase01, "Cycle-Stem: `demo`\nRisk Level: L1\nDocument-Language: ko\n\n"
                        "목적지에서도 여전히 ko 로 선언된 채로 남는 문서입니다.\n")
        self.addCleanup(lambda: os.path.exists(phase01) and os.unlink(phase01))
        self.addCleanup(_write, os.path.join(self.root, "plan_docs", "00-base_plan", "demo.md"),
                        PHASE00)
        code, text = _run_payload(self.root, "codex", self._codex_move_only_payload(
            "plan_docs/01-plan/demo.md", "plan_docs/00-base_plan/demo.md"))
        self.assertEqual(code, 2, f"목적지가 phase 문서인 이동에서 검사가 사라졌다\n{text}")

    def test_moving_between_phase_paths_passes_when_the_destination_is_sound(self):
        """반대 방향 — 옮기면서 선언을 맞추면 통과해야 한다."""
        phase01 = os.path.join(self.root, "plan_docs", "01-plan", "demo.md")
        _write(phase01, "Cycle-Stem: `demo`\nRisk Level: L1\nDocument-Language: ko\n\n"
                        "옮기면서 선언을 사이클에 맞추는 문서입니다.\n")
        self.addCleanup(lambda: os.path.exists(phase01) and os.unlink(phase01))
        self.addCleanup(_write, os.path.join(self.root, "plan_docs", "00-base_plan", "demo.md"),
                        PHASE00)
        code, text = _run_payload(self.root, "codex", self._codex_move_payload(
            "plan_docs/01-plan/demo.md", "plan_docs/00-base_plan/demo.md",
            "Document-Language: ko\n\n옮기면서 선언을 사이클에 맞추는 문서입니다.\n",
            "Document-Language: en\n\nThe relocated base plan is written in English "
            "and is long enough to clear the sample floor.\n"))
        self.assertEqual(code, 0, f"목적지가 건전한 phase 이동을 막았다\n{text}")

    @staticmethod
    def _codex_move_out_and_readd_payload(source, destination, body):
        """같은 패치에서 원래 경로를 비우고 그 자리에 새 문서를 만든다 — 실제 apply_patch 형태."""
        added = "\n".join(f"+{line}" for line in body.splitlines())
        return {"tool_name": "apply_patch", "session_id": "e2e",
                "tool_input": {"command": (f"*** Begin Patch\n*** Update File: {source}\n"
                                           f"*** Move to: {destination}\n"
                                           f"*** Add File: {source}\n{added}\n*** End Patch\n")}}

    def _move_out_and_readd(self, body):
        self._english_cycle()
        archive = os.path.join(self.root, "docs", "archive.md")
        self.addCleanup(lambda: os.path.exists(archive) and os.unlink(archive))
        return _run_payload(self.root, "codex", self._codex_move_out_and_readd_payload(
            "plan_docs/01-plan/demo.md", "docs/archive.md", body))

    def test_recreating_a_moved_out_path_with_a_conflicting_marker_blocks(self):
        """검수 재현 — 이동을 **경로** 집합으로 기억하면, 같은 패치에서 그 경로에 새로 만든
        문서까지 통째로 검사에서 빠진다. 이동은 경로가 아니라 그 **변경**의 성질이다."""
        code, text = self._move_out_and_readd(
            "Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
            "The recreated document declares Korean while the cycle is English.\n")
        self.assertEqual(code, 2, f"move-out 뒤 재생성한 문서의 선언을 검사하지 않았다\n{text}")

    def test_recreating_a_moved_out_path_with_foreign_prose_blocks(self):
        code, text = self._move_out_and_readd(
            "Cycle-Stem: `demo`\nDocument-Language: en\n\n"
            "재생성된 문서의 본문이 선언 언어와 다릅니다. 표본을 넘길 만큼 충분히 깁니다.\n")
        self.assertEqual(code, 2, f"move-out 뒤 재생성한 문서의 본문을 검사하지 않았다\n{text}")

    def test_recreating_a_moved_out_path_with_a_sound_document_passes(self):
        code, text = self._move_out_and_readd(
            "Cycle-Stem: `demo`\nDocument-Language: en\n\n"
            "The recreated plan document is written entirely in English and is long "
            "enough to clear the native-prose sample floor.\n")
        self.assertEqual(code, 0, f"move-out 뒤 정상 재생성을 막았다\n{text}")

    def test_korean_added_inside_an_existing_fence_is_not_blocked(self):
        """검수 재현 — 추가된 조각만 떼어 보면 그 줄이 fence 안이었는지 알 수 없다.
        기존 code fence 에 한국어 예시를 한 줄 넣는 정상 편집이 곧바로 차단된다."""
        keep = "```text"
        added = "추가된 한글 예시 출력"
        self._english_cycle_with_a_fence()
        for host, payload in (
                ("claude", _claude_edit_payload(keep, f"{keep}\n{added}")),
                ("codex", _codex_update_payload("", f"{added}\n", context=[keep]))):
            code, text = _run_payload(self.root, host, payload)
            self.assertEqual(code, 0, f"{host}: fence 안 한국어 예시를 과차단했다\n{text}")

    def test_korean_added_outside_the_fence_is_still_blocked(self):
        """fence 문맥을 존중한다는 것이 검사를 끄는 것이면 안 된다."""
        keep = "The English narrative continues after the example block."
        self._english_cycle_with_a_fence()
        for host, payload in (
                ("claude", _claude_edit_payload(keep, f"{keep}\n\n이것은 fence 밖 한국어입니다.")),
                ("codex", _codex_update_payload("", "\n이것은 fence 밖 한국어입니다.\n",
                                                context=[keep]))):
            code, text = _run_payload(self.root, host, payload)
            self.assertEqual(code, 2, f"{host}: fence 밖 한국어를 놓쳤다\n{text}")

    def test_replace_all_removing_every_korean_line_blocks(self):
        """검수 재현 — `replace_all: true` 는 host 가 전부 바꾼다. 첫 하나만 바꾼 결과를 최종
        문서라고 넘기면, 모든 한국어를 걷어내는 편집이 '아직 남아 있다' 로 읽혀 통과한다."""
        self._korean_cycle()
        line = self.KOREAN_LAST_LINE
        phase01 = os.path.join(self.root, "plan_docs", "01-plan", "demo.md")
        _write(phase01, f"Cycle-Stem: `demo`\nDocument-Language: ko\n\n{line}\n{line}\n")
        payload = _claude_edit_payload(line, self.ENGLISH_PARAGRAPH)
        payload["tool_input"]["replace_all"] = True
        code, text = _run_payload(self.root, "claude", payload)
        self.assertEqual(code, 2, f"replace_all 로 한국어를 전부 걷어낸 편집을 놓쳤다\n{text}")

    def test_replace_all_that_leaves_korean_behind_still_passes(self):
        """반대 방향 — 전부 치환해도 한국어가 남으면 정상 편집이다."""
        self._korean_cycle()
        phase01 = os.path.join(self.root, "plan_docs", "01-plan", "demo.md")
        _write(phase01, f"Cycle-Stem: `demo`\nDocument-Language: ko\n\n"
                        f"{self.KOREAN_LAST_LINE}\nTODO\nTODO\n")
        payload = _claude_edit_payload("TODO", "완료")
        payload["tool_input"]["replace_all"] = True
        code, text = _run_payload(self.root, "claude", payload)
        self.assertEqual(code, 0, f"정상 replace_all 편집을 막았다\n{text}")

    def test_a_pure_addition_anchored_at_end_of_file_is_not_blocked(self):
        """검수 재현 — anchor·EOF 가 자리를 잡아준 순수 추가는 쓸 수 있는 패치다."""
        self._korean_cycle()
        command = ("*** Begin Patch\n*** Update File: plan_docs/01-plan/demo.md\n@@\n"
                   "+이 문단은 파일 끝에 덧붙이는 한국어 본문입니다.\n*** End of File\n"
                   "*** End Patch\n")
        code, text = _run_payload(self.root, "codex", {
            "tool_name": "apply_patch", "session_id": "e2e",
            "tool_input": {"command": command}})
        self.assertEqual(code, 0, f"EOF 로 자리가 확정된 순수 추가를 차단했다\n{text}")

    def test_a_codex_hunk_that_does_not_match_the_disk_fails_closed(self):
        """되짚기가 성립하지 않으면 "못 봤으니 통과" 가 아니라 차단이다 — 그 경로가 곧 우회로다."""
        self._korean_cycle()
        code, text = _run_payload(self.root, "codex", _codex_update_payload(
            "이 줄은 디스크에 존재하지 않습니다.\n", "replacement\n"))
        self.assertEqual(code, 2, f"문맥 불일치가 조용한 통과로 떨어졌다\n{text}")

    def test_deleting_the_installed_scanner_is_detected_and_fails_closed(self):
        """판정 정본 파일 하나를 지우는 것이 이 게이트를 끄는 스위치가 되면 안 된다 —
        validate 가 지문 불일치로 잡고, 게이트 자체도 통과가 아니라 차단으로 떨어져야 한다."""
        path = os.path.join(self.root, "scripts", "sage_harness", "hooks", "runtime",
                            "prose_language.py")
        with open(path, encoding="utf-8") as handle:
            saved = handle.read()
        body = "Cycle-Stem: `demo`\nDocument-Language: en\n\n이것은 한글 문장입니다.\n"
        os.unlink(path)
        try:
            validate = _sage(["validate"], cwd=self.root)
            self.assertNotEqual(validate.returncode, 0,
                                f"삭제를 validate 가 감지하지 못했다\n{validate.stdout}")
            self.assertIn("prose_language.py", validate.stdout + validate.stderr)
            for host in self.hosts:
                code, text = _run_shim(self.root, host, body)
                self.assertEqual(code, 2, f"{host}: 정본 부재가 조용한 통과로 떨어졌다\n{text}")
        finally:
            _write(path, saved)

    def test_tampering_with_the_installed_scanner_is_detected(self):
        path = os.path.join(self.root, "scripts", "sage_harness", "hooks", "runtime",
                            "prose_language.py")
        with open(path, encoding="utf-8") as handle:
            saved = handle.read()
        _write(path, "def foreign_prose(text, language):\n    return []\n"
                     "def unclosed_fence(text):\n    return None\n"
                     "def lacks_native_prose(text, language):\n    return False\n")
        try:
            validate = _sage(["validate"], cwd=self.root)
            self.assertNotEqual(validate.returncode, 0,
                                f"변조를 validate 가 감지하지 못했다\n{validate.stdout}")
        finally:
            _write(path, saved)


if __name__ == "__main__":
    unittest.main()
