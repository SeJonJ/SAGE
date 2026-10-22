#!/usr/bin/env python3
"""코드 블록 닫힘·확인 안 된 밖 경로·선언 등급 순서.

세 가지 모두 사람이 보는 것과 SAGE 가 판정하는 것이 어긋나던 자리다.

- 코드 블록: 블록 안의 ```` ```python ```` 같은 줄을 닫는 펜스로 읽어, 예시의 `Cycle-Stem`·
  `Final Status`·Done Criteria·Fast 증거를 진짜 선언으로 셌다. CommonMark 는 닫는 펜스 뒤에
  공백·탭 말고는 허용하지 않는다. 바뀌는 판정은 양쪽 방향 모두 「사람이 보는 판정」 쪽이다.
- 경로: 링크·대소문자·짧은 이름으로 쓴 프로젝트 파일은 `<outside-project>` 가 되어 위험 규칙을
  조용히 비켜 갔다. 판정은 그대로 두고, 확실히 밖인지 확인하지 못한 경로를 경고로 보인다.
- 등급 순서: 높은 등급이 더 적게 요구하는 profile 에서는 높은 선언이 낮은 선언에서 막히던 소스
  편집을 통과시킨다. 게이트는 바꾸지 않고 `sage validate` 가 그 profile 을 경고한다.
"""

import io as _io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
RUNTIME = os.path.join(HOOKS_DIR, "runtime")
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HOOKS_DIR)))
sys.path.insert(0, REPO)
sys.path.insert(0, RUNTIME)
sys.path.insert(0, HOOKS_DIR)
sys.path.insert(0, HERE)

import cycle_binding                             # noqa: E402
import done_criteria_contract as dc              # noqa: E402
import fast_cycle_contract as fc                 # noqa: E402
import pre_implementation_gate_core as core      # noqa: E402
import messages                                  # noqa: E402
import hook_runtime as hr                        # noqa: E402
import io_claude                                 # noqa: E402
import io_codex                                  # noqa: E402
import override_audit as ov                      # noqa: E402
import test_declared_risk_scope as ds            # noqa: E402  (fixture 만 — 시험 클래스를 끌어오지 않는다)
from sage.diagnostics import Diagnostic          # noqa: E402
from sage.profile_validate import validate_profile  # noqa: E402

_STATE_TMP = None


def setUpModule():
    global _STATE_TMP
    _STATE_TMP = tempfile.TemporaryDirectory()
    os.environ["SAGE_STATE_HOME"] = _STATE_TMP.name


def tearDownModule():
    os.environ.pop("SAGE_STATE_HOME", None)
    _STATE_TMP.cleanup()


FENCE = "```"


def _md(*lines):
    return "\n".join(lines) + "\n"


def _binding_visible(content):
    return [line.rstrip() for line in cycle_binding.non_fenced_lines(content)]


def _criteria_visible(content):
    return [line for _, line in dc._visible_lines(content)]


def _evidence_count(content, marker="Final Status: APPROVED"):
    """Fast 증거 검사가 블록 밖에서 센 `marker` 의 수."""
    for issue in fc.evidence_marker_issues(content, fast_run_id="f", loop_run_id="l"):
        if issue.startswith(repr(marker)):
            return int(issue.rsplit("found ", 1)[1].rstrip(")"))
    return 1


class TestClosingFence(unittest.TestCase):
    """닫는 펜스 뒤에는 공백·탭만. 세 판정의 블록 경계가 같다."""

    def _all_visible(self, content):
        return _binding_visible(content), _criteria_visible(content)

    def test_text_after_a_fence_does_not_close(self):
        for tail in ("python", " 끝", "yaml ", "`x`"):
            content = _md(FENCE, FENCE + tail, "Cycle-Stem: example", FENCE, "after")
            for visible in self._all_visible(content):
                self.assertEqual(visible, ["after"], tail)

    def test_spaces_and_longer_fences_close(self):
        for closer in (FENCE, FENCE + "   ", FENCE + "\t", "````", "  " + FENCE):
            content = _md(FENCE, "inside", closer, "after")
            for visible in self._all_visible(content):
                self.assertEqual(visible, ["after"], repr(closer))

    def test_other_fence_characters_still_do_not_close(self):
        for opener, inner in (("~~~", FENCE), (FENCE, "~~~"), ("````", FENCE)):
            content = _md(opener, inner, "inside", opener, "after")
            for visible in self._all_visible(content):
                self.assertEqual(visible, ["after"], (opener, inner))

    def test_unicode_space_after_a_fence_does_not_close(self):
        # CommonMark 의 공백은 ASCII 공백·탭이다. `str.strip()` 은 U+00A0 도 지운다.
        for space in (" ", "　", " "):
            content = _md(FENCE, FENCE + space, "inside", FENCE, "after")
            for visible in self._all_visible(content):
                self.assertEqual(visible, ["after"], repr(space))

    def test_the_three_readers_agree(self):
        # HTML 주석·들여쓴 줄이 없는 입력에서 블록 경계가 같아야 한다. Fast 증거 검사는 줄을
        # 돌려주지 않으므로, 본문 줄을 전부 증거 줄로 채우고 센 수로 비교한다.
        bodies = (
            [FENCE, FENCE + "python", "B", FENCE, "B"],
            ["B", FENCE + "yaml", "B", FENCE + "  ", "B"],
            ["~~~~", "~~~", "B", "~~~~~", "B"],
            [FENCE, FENCE + " ", "B", FENCE, FENCE, "B"],
            ["B", "````md", FENCE, "B", "````", "B", FENCE + " 끝", "B"],
        )
        for body in bodies:
            content = _md(*body)
            binding, criteria = self._all_visible(content)
            self.assertEqual(binding, criteria, body)
            evidence = _md(*["Final Status: APPROVED" if line == "B" else line for line in body])
            self.assertEqual(_evidence_count(evidence), binding.count("B"), body)

    def test_one_declaration_binds_and_none_stays_none(self):
        example = (FENCE, FENCE + "yaml", "Cycle-Stem: example", FENCE)
        self.assertEqual(cycle_binding.declared_stem(_md("Cycle-Stem: `real`", *example)),
                         ("real", None))
        self.assertEqual(cycle_binding.declared_stem(
            _md("Cycle-Stem: `real`", FENCE, FENCE + " 끝", "Cycle-Stem: example", FENCE)),
            ("real", None))
        stem, error = cycle_binding.declared_stem(_md("# notes", *example))
        self.assertIsNone(stem)
        self.assertEqual(error, "Cycle-Stem declaration missing")


def _report_write(review_content):
    """05 문서 내용만 바꾼 채 06 문서를 쓰는 판정."""
    snapshot = ds._snapshot("open")
    snapshot["phase_docs"]["04"] = [ds._doc(ds.STEM)]
    snapshot["phase_docs"]["05"] = [{"path": f"{ds.STEM}.md", "content": review_content, "recent": True}]
    event = ds._event([f"plan_docs/06-x/{ds.STEM}.md"], content=f"Cycle-Stem: `{ds.STEM}`\n")
    return core.decide(event, ds.PROFILE, snapshot, None)


class TestExampleBlocksAreNotRead(unittest.TestCase):
    """바뀌는 판정의 두 방향 — 둘 다 사람이 보는 판정과 같아진다."""

    HEAD = f"Cycle-Stem: `{ds.STEM}`"

    def test_example_approval_is_not_an_approval(self):
        review = _md(self.HEAD, FENCE, FENCE + "yaml", "Final Status: APPROVED", FENCE)
        self.assertEqual(_report_write(review)["message_key"], "block_report_without_approval")

    def test_real_approval_beside_an_example_is_an_approval(self):
        review = _md(self.HEAD, "Final Status: APPROVED", FENCE, FENCE + "yaml",
                     "Final Status: BLOCKED", FENCE)
        self.assertEqual(core._final_status(review), ("APPROVED", None))
        self.assertEqual(_report_write(review)["status"], "ok")

    def test_example_criteria_are_not_counted(self):
        content = _md("Cycle-Stem: `x`", "Done-Criteria-Revision: 1", "", "## 5. Done Criteria",
                      "- [x] real", FENCE + "text", FENCE + "python", "- [ ] example", FENCE)
        result = dc.parse_done_criteria(content, mode="standard")
        self.assertEqual(result.status, "valid", result.issues)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(len(result.unresolved), 0)

    def test_example_evidence_is_not_a_duplicate(self):
        content = _md("Fast-Run: f", "Loop-Run: l", "Final Status: APPROVED",
                      FENCE, FENCE + "yaml", "Final Status: APPROVED", FENCE)
        self.assertEqual(fc.evidence_marker_issues(content, fast_run_id="f", loop_run_id="l"), [])

    def test_only_lf_cr_and_crlf_end_a_line(self):
        # `str.splitlines()` 는 U+2028·U+0085·VT·FF 에서도 줄을 나눈다. 그러면 블록 안의 한 줄
        # (```` ```python<LS>``` ````)이 「닫히지 않는 줄 + 닫는 펜스」로 읽혀 뒤의 예시가 드러난다.
        for sep in (" ", " ", "\u0085", "\x0b", "\x0c", "\x1c"):
            body = (FENCE, FENCE + "python" + sep + FENCE)
            review = _md(self.HEAD, *body, "Final Status: APPROVED")
            self.assertEqual(core._final_status(review)[0], None, repr(sep))
            self.assertEqual(_report_write(review)["message_key"], "block_report_without_approval", repr(sep))
            self.assertEqual(cycle_binding.declared_stem(_md(self.HEAD, *body, "Cycle-Stem: example")),
                             (ds.STEM, None), repr(sep))
            criteria = _md("Cycle-Stem: `x`", "Done-Criteria-Revision: 1", "", "## 5. Done Criteria",
                           "- [x] real", *body, "- [ ] example")
            self.assertEqual(len(dc.parse_done_criteria(criteria, mode="standard").unresolved), 0, repr(sep))
            evidence = _md("Fast-Run: f", "Loop-Run: l", "Final Status: APPROVED", *body,
                           "Final Status: APPROVED")
            self.assertEqual(fc.evidence_marker_issues(evidence, fast_run_id="f", loop_run_id="l"), [],
                             repr(sep))
        for newline in ("\r\n", "\r"):
            review = newline.join((self.HEAD, FENCE, "x", FENCE, "Final Status: APPROVED", ""))
            self.assertEqual(core._final_status(review), ("APPROVED", None), repr(newline))


class TestUnconfirmedOutsideInTheCore(unittest.TestCase):
    """판정 키는 바꾸지 않는다. 통과만 경고로 올리고, 그 밖에는 경로를 실어 표시가 붙인다."""

    ALIAS = "/elsewhere/PROJ/src/x.py"

    def _event(self, paths, declared=None, unconfirmed=(ALIAS,)):
        event = ds._event(paths, declared)
        event["outside_unconfirmed"] = list(unconfirmed)
        return event

    def test_a_pass_becomes_a_warning(self):
        d = core.decide(self._event([core.OUTSIDE_PROJECT]), ds.PROFILE, ds._snapshot("open"), None)
        self.assertEqual((d["status"], d["message_key"], d["exit_code"]),
                         ("warn", "warn_path_outside_unconfirmed", 0))
        self.assertEqual(d["outside_unconfirmed"], [self.ALIAS])
        self.assertEqual(d["file_short"], self.ALIAS)

    def test_confirmed_outside_has_no_warning(self):
        d = core.decide(self._event([core.OUTSIDE_PROJECT], unconfirmed=()), ds.PROFILE,
                        ds._snapshot("open"), None)
        self.assertEqual(d["status"], "ok")
        self.assertNotIn("outside_unconfirmed", d)

    def test_a_block_stays_the_same_block(self):
        event = self._event([core.OUTSIDE_PROJECT], declared="L3")
        base = dict(event)
        base.pop("outside_unconfirmed")
        expected = core.decide(base, ds.PROFILE, ds._snapshot("closed"), None)
        d = core.decide(event, ds.PROFILE, ds._snapshot("closed"), None)
        self.assertEqual(expected["message_key"], "block_cycle_closed")
        self.assertEqual({k: v for k, v in d.items() if k != "outside_unconfirmed"}, expected)
        self.assertEqual(d["outside_unconfirmed"], [self.ALIAS])

    def test_the_notice_survives_another_warning(self):
        # 경고 병합은 첫 키만 남기고 `warn_phase_incomplete` 는 근거를 출력하지 않는다.
        profile = dict(ds.PROFILE, pdca=dict(ds.PROFILE["pdca"],
                                             pre_implementation_required={"L1": ["00", "01"]}))
        profile["risk"] = dict(ds.PROFILE["risk"], l1_path_globs=["*src/*"])
        d = core.decide(self._event(["src/a.py", core.OUTSIDE_PROJECT]), profile,
                        ds._snapshot("partial"), None)
        self.assertEqual(d["message_key"], "warn_phase_incomplete")
        for host in ("claude", "codex"):
            for language in ("ko", "en"):
                text = messages.gate_text(d, profile, host, language=language)
                self.assertIn(self.ALIAS, text, (host, language))
                self.assertEqual(text.count(self.ALIAS), 1, (host, language))
                if host == "codex":
                    self.assertNotIn("\n", text)

    def test_block_text_carries_the_notice_before_the_next_step(self):
        d = core.decide(self._event([core.OUTSIDE_PROJECT], declared="L3"), ds.PROFILE,
                        ds._snapshot("closed"), None)
        text = messages.gate_text(d, ds.PROFILE, "claude", language="en")
        self.assertIn(self.ALIAS, text)
        self.assertLess(text.index(self.ALIAS), text.index("[cycle."))

    def test_the_warning_reads_in_both_languages(self):
        d = core.outside_unconfirmed_warning([self.ALIAS])
        ko = messages.gate_text(d, {}, "claude", language="ko")
        en = messages.gate_text(d, {}, "claude", language="en")
        self.assertIn("[GATE WARN]", ko)
        self.assertIn(self.ALIAS, en)
        self.assertNotRegex(en, "[가-힣]")
        self.assertNotIn("Next:", en)
        self.assertNotIn("[", en.split("[GATE WARN]", 1)[1].split(self.ALIAS)[0])

    def test_many_paths_are_cut_in_the_line(self):
        paths = [f"/x/{i}.py" for i in range(5)]
        d = core.outside_unconfirmed_warning(paths)
        self.assertEqual(d["outside_unconfirmed"], paths)
        self.assertTrue(d["reason"].endswith("(+2)"))
        block = dict(core.decide(self._event([core.OUTSIDE_PROJECT], declared="L3", unconfirmed=paths),
                                 ds.PROFILE, ds._snapshot("closed"), None))
        text = messages.gate_text(block, ds.PROFILE, "codex", language="en")
        self.assertIn("/x/2.py (+2)", text)
        self.assertNotIn("/x/3.py", text)


class TestUnconfirmedOutsideThroughTheHook(unittest.TestCase):
    """실제 `run_pre_implementation_gate` 로, 두 host 에서."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = os.path.realpath(tmp.name)
        self.root = ds._mark_project(os.path.join(self.base, "proj"))
        os.makedirs(os.path.join(self.root, "src"))
        Path(self.root, "src", "x.py").write_text("x", encoding="utf-8")
        for pid in ("00", "01", "02", "03", "04", "05", "06"):
            doc = Path(self.root, "plan_docs", f"{pid}-x", f"{ds.STEM}.md")
            doc.parent.mkdir(parents=True, exist_ok=True)
            extra = "Risk Level: L2\n" if pid == "00" else ("Final Status: APPROVED\n" if pid == "05" else "")
            doc.write_text(f"Cycle-Stem: `{ds.STEM}`\n{extra}", encoding="utf-8")
        profile = Path(self.root, "profile.json")
        profile.write_text(json.dumps(ds.PROFILE), encoding="utf-8")
        for key, value in {"SAGE_PROFILE": str(profile), "SAGE_GATE_BRANCH": ds.STEM}.items():
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, o=old: os.environ.__setitem__(k, o) if o is not None
                            else os.environ.pop(k, None))
        os.environ.pop("SAGE_CYCLE_STEM", None)
        self.alias = self._alias()
        self.outside = os.path.join(self.base, "notes.md")

    def _alias(self):
        """프로젝트 파일을 가리키지만 글자로는 루트 밖인 경로.

        macOS·Linux 는 루트의 대소문자 변형이다. 대소문자를 무시하는 볼륨에서는 프로젝트 파일이고,
        구분하는 볼륨에서는 없는 경로다 — 어느 쪽이든 「확실히 밖」이 아니다. Windows 는 `ntpath` 가
        대소문자를 무시해 변형도 프로젝트 안이므로, 루트의 짧은 이름(8.3)을 쓴다.
        """
        if os.name != "nt":
            return os.path.join(self.base, "PROJ", "src", "x.py")
        import ctypes
        buffer = ctypes.create_unicode_buffer(1024)
        if not ctypes.windll.kernel32.GetShortPathNameW(self.root, buffer, 1024):
            self.skipTest("짧은 이름을 조회할 수 없다")
        if buffer.value.casefold() == self.root.casefold():
            self.skipTest("이 볼륨은 짧은 이름을 만들지 않는다")
        return os.path.join(buffer.value, "src", "x.py")

    def _declare(self, level):
        for host in (".claude", ".codex"):
            logs = Path(self.root, host, "logs")
            logs.mkdir(parents=True, exist_ok=True)
            (logs / "declared-risk-s-1.json").write_text(json.dumps({"level": level}), encoding="utf-8")

    @staticmethod
    def _capture(fn):
        out, err = _io.StringIO(), _io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = fn()
        return rc, out.getvalue(), err.getvalue()

    def _claude(self, target):
        raw = json.dumps({"session_id": "s-1", "tool_name": "Write",
                          "tool_input": {"file_path": target, "content": "x"}})
        return self._capture(lambda: hr.run_pre_implementation_gate(io_claude, self.root, HOOKS_DIR, raw))

    def _codex(self, target):
        cmd = f"*** Begin Patch\n*** Add File: {target}\n+x\n*** End Patch"
        raw = json.dumps({"session_id": "s-1", "tool_name": "apply_patch", "tool_input": {"command": cmd}})
        return self._capture(lambda: hr.run_pre_implementation_gate(io_codex, self.root, HOOKS_DIR, raw))

    def _context(self, stdout):
        """비차단 컨텍스트 봉투(두 host 같은 wire)의 글."""
        lines = [line for line in stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, stdout)
        envelope = json.loads(lines[0])
        self.assertEqual(envelope["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        return envelope["hookSpecificOutput"]["additionalContext"]

    def _targets(self):
        targets = [self.alias]
        if os.name != "nt":
            alias = os.path.join(self.base, "alias")
            os.symlink(self.root, alias)
            targets.append(os.path.join(alias, "src", "x.py"))
        return targets

    def test_an_alias_of_the_project_is_warned(self):
        for target in self._targets():
            for run in (self._claude, self._codex):
                rc, out, _err = run(target)
                self.assertEqual(rc, 0, (run.__name__, target))
                self.assertIn(target, self._context(out), (run.__name__, target))

    def test_a_confirmed_outside_path_is_quiet(self):
        for run in (self._claude, self._codex):
            rc, out, err = run(self.outside)
            self.assertEqual((rc, out, err), (0, "", ""), run.__name__)

    def test_a_block_keeps_its_exit_and_names_the_path(self):
        self._declare("L3")
        for run in (self._claude, self._codex):
            rc, out, err = run(self.alias)
            self.assertEqual(rc, 2, (run.__name__, err))
            self.assertIn(self.alias, err, run.__name__)

    def test_an_override_still_delivers_the_notice(self):
        self._declare("L3")
        ov.grant(self.root, "긴급 우회", 10000, gate="all")
        for run in (self._claude, self._codex):
            rc, out, err = run(self.alias)
            self.assertEqual(rc, 0, (run.__name__, err))
            self.assertIn("override", err, run.__name__)
            self.assertIn(self.alias, self._context(out), run.__name__)

    def test_a_replaced_verdict_still_names_the_path(self):
        # 감사 기록 실패·코어 예외는 판정을 새 차단으로 통째로 바꾼다 — 경로 진단도 함께 남아야 한다.
        from unittest import mock
        os.environ["SAGE_CYCLE_STEM"] = ds.STEM
        self.addCleanup(os.environ.pop, "SAGE_CYCLE_STEM", None)
        waiver_block = {"status": "block", "exit_code": 2, "risk": "PDCA",
                        "message_key": "block_report_waiver_audit_failure", "reason": "x", "file_short": ""}
        failures = (
            mock.patch.object(ov, "record_cycle_stem_declaration", side_effect=OSError("read-only fs")),
            mock.patch.object(hr, "_record_acceptance_waiver_uses", return_value=waiver_block),
            mock.patch.object(core, "decide", side_effect=RuntimeError("boom")),
        )
        for failure in failures:
            for run in (self._claude, self._codex):
                with failure:
                    rc, out, err = run(self.alias)
                self.assertEqual((rc, out), (2, ""), (failure, run.__name__, err))
                self.assertIn(self.alias, err, (failure, run.__name__))

    def test_the_path_seen_by_the_gate_is_unchanged(self):
        seen = []
        original = core.decide

        def spy(event, *args):
            seen.append(([c.get("path") for c in event["changes"]], event["outside_unconfirmed"]))
            return original(event, *args)
        core.decide = spy
        self.addCleanup(setattr, core, "decide", original)
        self._claude(self.alias)
        self._claude(self.outside)
        self._claude(os.path.join(self.root, "src", "x.py"))
        self.assertEqual(seen, [([core.OUTSIDE_PROJECT], [self.alias]),
                                ([core.OUTSIDE_PROJECT], []), (["src/x.py"], [])])


def _codes(issues, code):
    return [message.arguments for sev, message in issues
            if sev == "WARN" and isinstance(message, Diagnostic) and message.code == code]


NOT_MONOTONIC = "validate.pre_implementation_not_monotonic"
PHASES = [{"id": pid, "glob": f"plan_docs/{pid}-x/**/*.md"} for pid in ("00", "01", "02", "03")]


def _profile(required, enabled=True):
    return {"risk": {"l2_path_globs": ["*src/*"]},
            "pdca": {"enabled": enabled, "phases": PHASES, "pre_implementation_required": required}}


class TestLevelOrderIsValidated(unittest.TestCase):
    """높은 등급이 낮은 등급의 필수 phase 를 모두 요구하지 않으면 경고한다."""

    def test_a_higher_level_that_requires_less_is_warned(self):
        issues = validate_profile(_profile({"L1": ["00"], "L2": ["00", "01"], "L3": ["00"]}), REPO)
        self.assertEqual(_codes(issues, NOT_MONOTONIC),
                         [{"lower": "L2", "higher": "L3", "phases": ["01"]}])

    def test_an_omitted_level_is_an_empty_list(self):
        issues = validate_profile(_profile({"L2": ["00", "01"]}), REPO)
        self.assertEqual(_codes(issues, NOT_MONOTONIC),
                         [{"lower": "L2", "higher": "L3", "phases": ["00", "01"]}])

    def test_monotonic_profiles_are_quiet(self):
        for required in ({"L1": ["00"], "L2": ["00", "01", "02", "03"], "L3": ["00", "01", "02", "03"]},
                         {"L2": ["00", "01", "02"], "L3": ["00", "01", "02"]},
                         {"L1": ["00", "02"], "L2": ["00", "01", "02"], "L3": ["00", "01", "02", "03"]},
                         {}):
            self.assertEqual(_codes(validate_profile(_profile(required), REPO), NOT_MONOTONIC), [],
                             required)

    def test_the_default_template_is_quiet(self):
        import yaml
        template = yaml.safe_load(Path(REPO, "templates", "project-profile.yaml").read_text(encoding="utf-8"))
        self.assertEqual(_codes(validate_profile(template, REPO), NOT_MONOTONIC), [])

    def test_disabled_pdca_is_not_asked(self):
        required = {"L2": ["00", "01"], "L3": ["00"]}
        self.assertEqual(_codes(validate_profile(_profile(required, enabled=False), REPO), NOT_MONOTONIC), [])

    def test_the_message_names_the_levels(self):
        issue = Diagnostic(NOT_MONOTONIC, lower="L2", higher="L3", phases=["01"])
        from sage import i18n
        for language in ("ko", "en"):
            text = i18n.tr(language, "cli." + NOT_MONOTONIC, **issue.arguments)
            self.assertIn("L3", text)
            self.assertIn("01", text)
            self.assertNotIn("{", text)

    def test_the_warned_profile_really_lets_the_higher_declaration_through(self):
        # 게이트는 바꾸지 않는다 — 이 profile 에서 L3 선언이 L2 선언의 소스 편집 차단을 푼다는
        # 사실을 남기고, validate 가 바로 그 profile 에 경고하는지 함께 본다.
        profile = _profile({"L1": ["00"], "L2": ["00", "01"], "L3": ["00"]})
        snapshot = ds._snapshot("partial", risk00="L3")
        found = {"found": True, "path": "plan_docs/00-x/p.md"}
        l2 = core.decide(ds._event(["docs/x.py"], "L2"), profile, snapshot, found)
        l3 = core.decide(ds._event(["docs/x.py"], "L3"), profile, snapshot, found)
        self.assertEqual(l2["message_key"], "block_phase_incomplete")
        self.assertEqual(l3["status"], "ok")
        self.assertTrue(_codes(validate_profile(profile, REPO), NOT_MONOTONIC))


if __name__ == "__main__":
    unittest.main()
