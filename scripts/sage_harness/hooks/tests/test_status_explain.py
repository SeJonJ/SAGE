#!/usr/bin/env python3
"""`sage status` 와 `sage explain --path` — 조회는 조회여야 한다.

이 스위트가 지키는 것은 넷이다.

1. **아무것도 쓰지 않는다.** 진단 명령이 상태를 바꾸면, 사용자는 문제를 보기 위해 문제를
   건드려야 한다. 실행 전후 바이트 스냅샷으로 고정한다.
2. **판정 정본을 늘리지 않는다.** `explain` 의 위험도는 게이트가 쓰는 바로 그 함수에서 온다.
   두 벌이 되면 언젠가 갈리고, 갈린 뒤에는 어느 쪽이 진짜 게이트인지 알 수 없다.
3. **허용을 약속하지 않는다.** 출력 어디에도 `ALLOW` 가 없다. 출력 계약에 `verdict` 필드
   자체가 없어서 들어갈 자리가 없다.
4. **JSON 은 언어를 타지 않는다.** 같은 저장소 상태가 사용자 언어에 따라 다른 기계 판독
   결과를 내면, 그건 기계가 대조할 수 없는 값이다.
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
HOOKS = os.path.join(REPO, "scripts", "sage_harness", "hooks")
for _p in (os.path.join(HOOKS, "runtime"), HOOKS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sage.commands import explain as E  # noqa: E402
from sage.commands import status as S  # noqa: E402
from sage.diagnostic_contract import BLOCK, INFO, WARN, severity_of  # noqa: E402
from sage.profile_compile import materialize_profile  # noqa: E402
from sage.runtime_api import HOOK_RUNTIME_API  # noqa: E402

import path_risk  # noqa: E402
import pre_implementation_gate_core as GATE  # noqa: E402

PROFILE = {
    "risk": {
        "l0_pass_globs": ["docs/**", "plan_docs/**"],
        "l1_path_globs": ["config/**"],
        "l2_path_globs": ["src/**"],
        "l3_filename_globs": ["**/*secret*", "**/auth/**"],
        "l3_content_keywords": ["PRIVATE KEY"],
        "l2_content_keywords": ["migration"],
    },
    "components": [{"id": "payment", "paths": ["src/payment/**"]}],
    "pdca": {
        "enabled": True,
        "phases": [{"id": "00", "glob": "plan_docs/00-base_plan/*.md"},
                   {"id": "01", "glob": "plan_docs/01-plan/*.md"},
                   {"id": "02", "glob": "plan_docs/02-design/*.md"}],
        "pre_implementation_required": {"L2": ["00", "01"], "L3": ["00", "01", "02"]},
    },
}


class Args:
    def __init__(self, **kw):
        self.root = None
        self.json = False
        self.path = None
        self.__dict__.update(kw)


def _project(root, profile=PROFILE, with_manifest=True):
    os.makedirs(os.path.join(root, "sage"), exist_ok=True)
    with open(os.path.join(root, "sage", "project-profile.yaml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump(profile, fh)
    with open(os.path.join(root, "sage", "project-profile.json"), "w", encoding="utf-8") as fh:
        json.dump(materialize_profile(profile), fh)
    if with_manifest:
        os.makedirs(os.path.join(root, "docs", "sage_harness"), exist_ok=True)
        with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"sage_version": "1.0.0", "host_runtime": "codex", "assets": {},
                       "generator_version": "1.0.0",
                       "runtime_api": {"required": HOOK_RUNTIME_API}}, fh)
    return root


def _snapshot(root):
    """디렉터리 전체의 (상대경로 → 내용 해시). 무엇이 바뀌었는지까지 보여준다."""
    seen = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            full = os.path.join(base, name)
            rel = os.path.relpath(full, root)
            try:
                with open(full, "rb") as fh:
                    seen[rel] = hashlib.sha256(fh.read()).hexdigest()
            except OSError:
                seen[rel] = "unreadable"
    return seen


def _run(command, **kw):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = command.run(Args(**kw))
    return rc, out.getvalue(), err.getvalue()


class TestReadOnly(unittest.TestCase):
    def test_status_changes_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            before = _snapshot(root)
            _run(S, root=root)
            self.assertEqual(_snapshot(root), before)

    def test_explain_changes_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            before = _snapshot(root)
            _run(E, root=root, path="src/payment/Login.java")
            self.assertEqual(_snapshot(root), before)

    def test_explain_does_not_create_the_path_it_explains(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _run(E, root=root, path="src/does/not/exist.java")
            self.assertFalse(os.path.exists(os.path.join(root, "src")))


class TestGateParity(unittest.TestCase):
    """`explain` 의 위험도는 게이트가 쓰는 바로 그 함수에서 온다."""

    PATHS = ["src/a.py", "src/payment/Login.java", "docs/x.md", "config/app.yml",
             "lib/secret_store.py", "app/auth/session.py", "unmatched/thing.txt",
             "plan_docs/00-base_plan/x.md"]

    def test_the_gate_and_the_floor_agree_when_there_is_no_content(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                gate_risk, _, _ = GATE._classify_one(path, "", PROFILE)
                self.assertEqual(path_risk.path_risk_floor(path, PROFILE).risk, gate_risk)

    def test_content_can_only_raise_the_floor_never_lower_it(self):
        rank = {"none": -1, "L0": 0, "L1": 1, "L2": 2, "L3": 3}
        for path in self.PATHS:
            for content in ("", "migration", "PRIVATE KEY", "harmless"):
                with self.subTest(path=path, content=content):
                    floor = path_risk.path_risk_floor(path, PROFILE).risk
                    gate_risk, _, _ = GATE._classify_one(path, content, PROFILE)
                    self.assertGreaterEqual(rank[gate_risk], rank[floor])

    def test_orphan_l0_exclusion_is_l3_not_a_pass(self):
        # "제외한다" 고만 적힌 규칙을 통과로 읽으면 profile 오타 하나가 게이트를 연다.
        profile = {"risk": {"l0_exclude_globs": ["src/**"], "l0_pass_globs": ["src/**"]}}
        self.assertEqual(path_risk.path_risk_floor("src/a.py", profile).risk, "L3")
        self.assertEqual(GATE._classify_one("src/a.py", "", profile)[0], "L3")

    def test_the_matched_rule_names_the_glob_that_fired(self):
        result = path_risk.path_risk_floor("src/payment/Login.java", PROFILE)
        self.assertEqual(result.matched_rule[0], "risk.l2_path_globs")
        self.assertEqual(result.matched_rule[2], "src/**")


class TestExplainPromisesNothing(unittest.TestCase):
    def test_the_word_allow_never_appears(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            for path in ("docs/a.md", "src/a.py", "config/a.yml", "app/auth/s.py"):
                with self.subTest(path=path):
                    _, out, _ = _run(E, root=root, path=path)
                    self.assertNotIn("ALLOW", out)

    def test_the_json_contract_has_no_verdict_field(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _, out, _ = _run(E, root=root, path="src/a.py", json=True)
            self.assertNotIn("verdict", json.loads(out))

    def test_the_dynamic_limitation_is_always_stated(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            for path in ("docs/a.md", "src/a.py"):
                _, out, _ = _run(E, root=root, path=path, json=True)
                self.assertEqual(json.loads(out)["dynamic_checks"],
                                 list(E.DYNAMIC_CHECKS))

    def test_explain_exits_zero_even_when_it_reports_a_block(self):
        # 설명은 판정이 아니다. exit 1 로 끝내면 "이 경로는 못 쓴다" 로 읽힌다.
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            rc, out, _ = _run(E, root=root, path="src/a.py")
            self.assertEqual(rc, 0)
            self.assertIn("gate.phase_incomplete", out)


class TestExplainNeverReadsContent(unittest.TestCase):
    def test_existing_content_does_not_raise_the_reported_floor(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            os.makedirs(os.path.join(root, "config"))
            with open(os.path.join(root, "config", "app.yml"), "w", encoding="utf-8") as fh:
                fh.write("PRIVATE KEY = 1\n")     # 읽었다면 L3 으로 올라간다
            _, out, _ = _run(E, root=root, path="config/app.yml", json=True)
            self.assertEqual(json.loads(out)["path_risk_floor"], "L1")

    def test_an_absent_path_is_explained_just_the_same(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _, out, _ = _run(E, root=root, path="config/never-written.yml", json=True)
            self.assertEqual(json.loads(out)["path_risk_floor"], "L1")


class TestExplainPathSafety(unittest.TestCase):
    def test_escaping_the_root_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            for path in ("../outside.txt", "src/../../outside.txt", "/etc/hosts"):
                with self.subTest(path=path):
                    rc, _, err = _run(E, root=root, path=path)
                    self.assertEqual(rc, 2)
                    self.assertIn("explain.path_outside_root", err)

    def test_a_symlink_segment_is_refused_and_not_followed(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            outside = os.path.join(root, "outside")
            os.makedirs(outside)
            os.symlink(outside, os.path.join(root, "link"))
            rc, _, err = _run(E, root=root, path="link/a.py")
            self.assertEqual(rc, 2)
            self.assertIn("explain.path_symlink", err)

    def test_an_empty_path_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            rc, _, err = _run(E, root=root, path="   ")
            self.assertEqual(rc, 2)
            self.assertIn("explain.path_empty", err)

    def test_a_refused_path_is_reported_with_its_code(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            _, _, err = _run(E, root=root, path="../x")
            self.assertTrue(err.startswith("["), err)


class TestStatusAggregation(unittest.TestCase):
    def test_a_healthy_project_is_not_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            rc, out, _ = _run(S, root=root)
            self.assertIn(rc, (0,), out)
            self.assertNotIn("BLOCKED", out)

    def test_a_missing_shared_profile_blocks_with_exit_one(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "docs", "sage_harness"))
            with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"assets": {}, "generator_version": "1.0.0",
                           "runtime_api": {"required": HOOK_RUNTIME_API}}, fh)
            rc, out, _ = _run(S, root=root)
            self.assertEqual(rc, 1)
            self.assertIn("BLOCKED", out)
            self.assertIn("profile.shared_missing", out)

    def test_an_unreadable_manifest_never_becomes_ready(self):
        # 부재를 안전한 방향으로 읽으면 READY 가 거짓말이 된다.
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                      encoding="utf-8") as fh:
                fh.write("{")
            rc, out, _ = _run(S, root=root)
            self.assertEqual(rc, 1)
            self.assertIn("project.manifest_unreadable", out)

    def test_a_stale_compiled_profile_is_a_warning_not_a_pass(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            with open(os.path.join(root, "sage", "project-profile.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"risk": {}}, fh)
            rc, out, _ = _run(S, root=root)
            self.assertEqual(rc, 0)
            self.assertIn("profile.compiled_stale", out)

    def test_status_does_not_reuse_the_validate_stale_exit_three(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            with open(os.path.join(root, "sage", "project-profile.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"risk": {}}, fh)
            rc, _, _ = _run(S, root=root)
            self.assertNotEqual(rc, 3)


class TestCycleFacts(unittest.TestCase):
    """cycle 영역은 stem·mode·risk 를 함께 보여준다.

    셋 다 보여야 "지금 어떤 절차로 무슨 위험도의 일을 하는 중인가" 가 한 줄에 선다. stem 만
    있으면 사용자는 그걸 알아내려고 다시 다른 명령을 쳐야 한다.
    """

    def _declare(self, root, stem, risk_line="Risk Level: L3"):
        os.makedirs(os.path.join(root, "plan_docs", "00-base_plan"), exist_ok=True)
        with open(os.path.join(root, "plan_docs", "00-base_plan", f"{stem}.md"), "w",
                  encoding="utf-8") as fh:
            fh.write(f"# [기본 계획] {stem}\n\nCycle-Stem: `{stem}`\n{risk_line}\n\n## 1. 목표\n")
        with open(os.path.join(root, ".sage", "cycle.json"), "w", encoding="utf-8") as fh:
            json.dump({"schema_version": 2, "cycle_stem": stem, "document_language": "ko"}, fh)

    def _facts(self, root):
        _, out, _ = _run(S, root=root, json=True)
        return json.loads(out)["cycle"]

    def test_a_declared_cycle_reports_stem_and_risk(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
            self._declare(root, "demo-stem")
            facts = self._facts(root)
            self.assertEqual(facts["stem"], "demo-stem")
            self.assertEqual(facts["risk"], "L3")
            # mode 는 싣지 않는다 — Fast 감사는 읽기에도 lock 을 잡아 읽기 전용 계약을 깬다.
            self.assertNotIn("mode", facts)

    def test_the_risk_comes_from_the_phase00_declaration(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
            self._declare(root, "demo-stem", "Risk Level: L2")
            self.assertEqual(self._facts(root)["risk"], "L2")

    def test_an_unreadable_declaration_reports_none_not_a_guess(self):
        # 모르는 것을 채우면 화면이 사실이 아닌 것을 단정한다.
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
            self._declare(root, "demo-stem", "Risk Level: 없음")
            self.assertIsNone(self._facts(root)["risk"])

    def test_no_declaration_means_no_mode_and_no_risk(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            facts = self._facts(root)
            self.assertIsNone(facts["stem"])
            self.assertIsNone(facts["risk"])

    def test_reading_the_cycle_does_not_write_anything(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
            self._declare(root, "demo-stem")
            before = _snapshot(root)
            _run(S, root=root)
            self.assertEqual(_snapshot(root), before)


class TestStatusStaysFast(unittest.TestCase):
    """빠른 요약이라는 약속을 구조로 지킨다."""

    def test_status_never_takes_an_audit_lock(self):
        """읽기 전용 조회가 실제 작업과 락 경쟁을 하면 안 된다.

        감사 모듈은 읽기에도 lock 을 잡는다 — 일관된 스냅샷을 위한 옳은 설계다. 그래서
        `status` 는 그 모듈을 부르지 않는다. 부르면 `.sage` 에 lock 파일이 생기고, 진행
        중인 Fast 전이를 기다리게 된다.
        """
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
            _run(S, root=root)
            leftovers = [name for name in os.listdir(os.path.join(root, ".sage"))
                         if name.endswith(".lock")]
            self.assertEqual(leftovers, [])

    def test_status_spawns_no_child_process(self):
        """child process 가 없으면 timeout 도 필요 없다.

        승인 설계는 "불가피한 child process 에 5초 timeout" 을 요구했다. 구현은 그보다 강한
        답을 냈다 — child process 자체가 없다. 그 사실을 여기서 고정한다. 나중에 누가 하나
        들이면 이 테스트가 실패하고, 그때 timeout 을 함께 들이게 된다.
        """
        import subprocess
        from unittest import mock
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            with mock.patch.object(subprocess, "run") as run, \
                 mock.patch.object(subprocess, "Popen") as popen, \
                 mock.patch.object(subprocess, "check_output") as check_output:
                _run(S, root=root)
            run.assert_not_called()
            popen.assert_not_called()
            check_output.assert_not_called()

    def test_explain_spawns_no_child_process(self):
        import subprocess
        from unittest import mock
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            with mock.patch.object(subprocess, "run") as run, \
                 mock.patch.object(subprocess, "Popen") as popen:
                _run(E, root=root, path="src/a.py")
            run.assert_not_called()
            popen.assert_not_called()


class TestStatusJson(unittest.TestCase):
    def _payload(self, root, **kw):
        _, out, _ = _run(S, root=root, json=True, **kw)
        return json.loads(out)

    def test_schema_v1_top_level_keys_are_fixed(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            self.assertEqual(
                set(self._payload(root)),
                {"schema_version", "status", "exit_code", "project", "version", "runtime_api",
                 "host", "cycle", "profile", "diagnostics"})

    def _render(self, root, language, as_json):
        from sage.i18n.context import LanguageContext
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            S.run(Args(root=root, json=as_json,
                       _language_context=LanguageContext(language=language)))
        return out.getvalue()

    def test_the_payload_is_byte_identical_across_languages(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                      encoding="utf-8") as fh:
                fh.write("{")                     # BLOCK 진단을 만들어 recovery 까지 싣게 한다
            self.assertEqual(self._render(root, "ko", True), self._render(root, "en", True))

    def test_the_language_switch_is_real(self):
        """위 테스트가 무치가 아님을 증명한다.

        언어 전환이 실제로 일어나지 않으면 JSON 동일성은 공짜로 성립한다. 같은 상태의 text
        출력은 언어에 따라 **달라져야** 하고, 그래야 JSON 동일성이 의미를 갖는다.
        """
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                      encoding="utf-8") as fh:
                fh.write("{")
            self.assertNotEqual(self._render(root, "ko", False), self._render(root, "en", False))

    def test_code_command_and_exit_stay_the_same_across_languages(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), "w",
                      encoding="utf-8") as fh:
                fh.write("{")
            lines = {}
            for language in ("ko", "en"):
                text = self._render(root, language, False)
                lines[language] = ([ln for ln in text.splitlines() if ln.startswith("Next: ")],
                                   [ln.split("]")[0] for ln in text.splitlines()
                                    if ln.startswith("[")])
            self.assertEqual(lines["ko"], lines["en"])

    def test_diagnostics_carry_no_translated_sentence(self):
        with tempfile.TemporaryDirectory() as root:
            _project(root)
            for entry in self._payload(root)["diagnostics"]:
                self.assertEqual(set(entry), {"code", "severity", "evidence", "recovery"})

    def test_ordering_is_block_then_warn_then_info(self):
        rank = {BLOCK: 0, WARN: 1, INFO: 2}
        with tempfile.TemporaryDirectory() as root:
            _project(root, profile={"risk": {}})
            codes = [e["code"] for e in self._payload(root)["diagnostics"]]
            ranks = [rank[severity_of(c)] for c in codes]
            self.assertEqual(ranks, sorted(ranks))
            for a, b in zip(codes, codes[1:]):
                if severity_of(a) == severity_of(b):
                    self.assertLessEqual(a, b)


class TestSeverityMatchesTheVersionContract(unittest.TestCase):
    """version 축의 severity 정본은 `version_contract` 다 — 여기 값은 그 판정의 사본이다."""

    def test_every_version_issue_severity_maps_one_to_one(self):
        from sage.version_contract import version_contract_issues
        mapping = {"FAIL": BLOCK, "WARN": WARN, "INFO": INFO}
        cases = [
            ({"sage": "not-a-mapping"}, {}),
            ({"sage": {"required_version": "1.x"}}, {}),
            ({}, {}),
            ({"sage": {"required_version": "1.0.0"}},
             {"sage_version": "0.9.0", "generator_version": "0.9.0"}),
        ]
        for profile, manifest in cases:
            for issue in version_contract_issues(profile, manifest, "0.9.84"):
                with self.subTest(code=issue.message.code, severity=issue.severity):
                    self.assertEqual(severity_of(issue.message.code),
                                     mapping[issue.severity],
                                     f"{issue.message.code} 의 severity 가 두 곳에서 갈렸다")


class TestNoVaultDependency(unittest.TestCase):
    """Obsidian 이 없어도 이 세 기능은 같은 답을 낸다.

    좁은 회귀다 — knowledge·retro·audit 전체의 no-vault Golden 은 후속 사이클이 소유한다.
    여기서 재는 것은 "이번에 추가한 조회 경로가 vault 를 필요로 하게 되지 않았는가" 뿐이다.
    """

    MODULES = ("sage/commands/status.py", "sage/commands/explain.py",
               "sage/diagnostic_collectors.py", "sage/diagnostic_contract.py",
               "sage/runtime_api.py")

    def test_the_new_modules_never_reach_for_a_vault(self):
        for relative in self.MODULES:
            with self.subTest(module=relative):
                with open(os.path.join(REPO, relative), encoding="utf-8") as handle:
                    source = handle.read()
                for token in ("vault", "obsidian", "_vault"):
                    self.assertNotIn(token, source.lower(),
                                     f"{relative} 가 vault 를 참조한다")

    def test_results_are_identical_with_and_without_a_vault_setting(self):
        with tempfile.TemporaryDirectory() as root:
            profile = dict(PROFILE)
            _project(root, profile)
            _, without, _ = _run(S, root=root, json=True)
            profile_with_vault = dict(PROFILE)
            profile_with_vault["knowledge_capture"] = {"vault_path": "/nonexistent/vault"}
            _project(root, profile_with_vault)
            _, with_vault, _ = _run(S, root=root, json=True)
        self.assertEqual(json.loads(without)["diagnostics"],
                         json.loads(with_vault)["diagnostics"])


class TestRunAllRegistration(unittest.TestCase):
    def test_this_suite_is_wired(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run-all.sh"),
                  encoding="utf-8") as fh:
            self.assertIn("test_status_explain.py", fh.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
