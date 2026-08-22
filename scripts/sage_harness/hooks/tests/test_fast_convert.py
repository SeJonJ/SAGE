#!/usr/bin/env python3
"""Standard→Fast 명시 전환 계약.

전환은 자동 모드 변경도 게이트 override 도 아니다. 이미 시작한 Standard Cycle 의 남은 절차를
개발자의 명시 확인과 사유로 Fast 계약으로 바꾸는 감사 가능한 상태 전이다. 그래서 이 파일이 지키는
것은 세 가지다 — 실제 위험도가 낮아지지 않을 것, 문서가 한 바이트도 바뀌지 않을 것, 확인 없이는
아무것도 기록되지 않을 것.
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HOOKS_DIR)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))

from sage.profile_validate import severity_of, validate_profile  # noqa: E402

import fast_cycle_audit as fca  # noqa: E402

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional schema dependency
    jsonschema = None

SCHEMA = json.loads(Path(REPO, "schema", "profile.schema.json").read_text(encoding="utf-8"))


def _fast(**extra):
    fast = {
        "enabled": True,
        "reason_required": True,
        "minimum_rounds": {"L2": 1, "L3": 1},
        "minimum_lenses": {"L2": 2, "L3": 2},
        "lenses": {"L2": ["correctness", "error_handling"],
                   "L3": ["correctness", "security", "data_integrity"]},
    }
    fast.update(extra)
    return {"pdca": {"fast_cycle": fast}}


class TestStandardTransitionOptIn(unittest.TestCase):
    """전환은 shared profile 에서 명시적으로 켜야 열린다. 키 부재는 비활성이다."""

    def _fails(self, profile):
        return [str(message) for severity, message in validate_profile(profile, REPO)
                if severity == "FAIL"]

    def test_absent_block_stays_valid_for_existing_profiles(self):
        self.assertEqual(self._fails(_fast()), [])

    def test_explicit_enabled_flag_validates_in_both_directions(self):
        for value in (True, False):
            profile = _fast(standard_transition={"enabled": value})
            self.assertEqual(self._fails(profile), [], value)
            if jsonschema is not None:
                jsonschema.validate(profile, SCHEMA)

    def test_non_bool_enabled_is_rejected_rather_than_read_as_truthy(self):
        for value in (1, "true", None, [True]):
            profile = _fast(standard_transition={"enabled": value})
            self.assertNotEqual(self._fails(profile), [], repr(value))

    def test_unknown_key_and_non_mapping_are_rejected(self):
        self.assertNotEqual(self._fails(_fast(standard_transition={"enabled": True, "typo": 1})), [])
        self.assertNotEqual(self._fails(_fast(standard_transition=True)), [])

    def test_local_profile_cannot_carry_the_opt_in(self):
        """local 계층에 pdca 가 오면 unknown top key 로 막힌다 — 개인 설정으로 못 연다."""
        from sage.profile_layers import _unknown_key_issues

        issues = _unknown_key_issues({"pdca": {"fast_cycle": {"standard_transition":
                                                              {"enabled": True}}}})
        self.assertTrue(any(severity == "FAIL" for severity, _ in issues), issues)


def _sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _phase_snapshot(root, phases=("00", "01", "02", "03", "04")):
    out = {}
    for phase in phases:
        rel = f"plan_docs/{phase}-x/demo.md"
        path = Path(root, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = f"Cycle-Stem: `demo`\n# {phase}\n"
        path.write_text(body, encoding="utf-8")
        out[phase] = {"path": rel, "sha256": _sha(body), "size": len(body.encode("utf-8"))}
    return out


class TestConvertAudit(unittest.TestCase):
    """전환의 정본은 `.sage/fast_cycle.jsonl` 의 `fast_convert` opener 하나다."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, ".sage"))
        self.sources = _phase_snapshot(self.root)

    def _convert(self, **extra):
        kwargs = dict(cycle_stem="demo", current_phase="04", actual_risk="L3",
                      fast_review_level="L2", reason="긴급 배포", confirmed_by="sejon",
                      minimum_rounds=1, lenses=["correctness", "error_handling"],
                      source_phases=self.sources)
        kwargs.update(extra)
        return fca.convert_fast(self.root, **kwargs)

    def test_convert_is_an_opener_and_records_provenance(self):
        run_id = self._convert()
        records = fca.read_records(self.root)
        self.assertEqual([r["event"] for r in records], ["fast_convert"])
        record = records[0]
        self.assertEqual(record["entry_mode"], "FAST-CONVERTED")
        self.assertEqual(record["actual_risk_open"], "L3")
        self.assertEqual(record["fast_review_level"], "L2")
        self.assertEqual(record["current_phase"], "04")
        self.assertEqual(record["attestation"], "self_asserted_local")
        self.assertEqual(record["source_phases_open"], self.sources)
        self.assertEqual(fca.audit_summary(self.root)["active"], [run_id])

    def test_the_dashboard_finds_the_open_time_of_a_converted_run(self):
        """opener 가 둘이 됐는데 한쪽만 아는 sweep 이 남으면, 전환 run 만 열이 비어 보인다."""
        from sage.commands import fast_cycle as fc  # noqa: PLC0415

        run_id = self._convert()
        opened = fca.read_records(self.root)[0]["ts"]
        body = fc._dashboard_body(self.root)
        row = next(line for line in body.splitlines() if run_id in line)
        self.assertIn(opened, row)

    def test_the_dashboard_stays_off_until_the_project_opts_in(self):
        """opt-in 이 없으면 vault 에 아무것도 쓰지 않는다 — 조용한 부수효과가 되면 안 된다."""
        from unittest import mock  # noqa: PLC0415

        from sage.commands import fast_cycle as fc  # noqa: PLC0415

        for profile in ({}, {"knowledge_capture": {}},
                        {"knowledge_capture": {"fast_cycle_dashboard": False}},
                        {"knowledge_capture": {"fast_cycle_dashboard": "true"}}):
            with self.subTest(profile=profile), \
                 mock.patch.object(fc, "_profile", return_value=profile), \
                 mock.patch.object(fc, "_write_dashboard") as writer:
                fc._auto_dashboard(self.root)
                self.assertEqual(writer.call_count, 0, profile)

    def test_the_dashboard_says_how_the_run_entered_fast(self):
        """전환 run 과 fresh run 은 감사에서만 구분됐다. 대시보드를 읽는 사람에게는
        composite 계획을 쓴 run 인지 Standard 를 전환한 run 인지가 판단 근거다."""
        from sage.commands import fast_cycle as fc  # noqa: PLC0415

        converted = self._convert()
        fresh = fca.open_fast(self.root, cycle_stem="other", actual_risk="L3",
                              fast_review_level="L2", reason="fresh", minimum_rounds=1,
                              lenses=["correctness", "error_handling"],
                              profile_hash="sha256:p", plan_hash_open="sha256:q")
        body = fc._dashboard_body(self.root)
        rows = {line.split("|")[1].strip(): line for line in body.splitlines() if "| fc-" in line}
        self.assertIn("FAST-CONVERTED", rows[converted])
        self.assertIn("FAST", rows[fresh])
        self.assertNotIn("FAST-CONVERTED", rows[fresh])

    def test_the_dashboard_and_show_never_disagree_about_entry(self):
        """opener 없이 남은 run 을 대시보드가 FAST 로 단정하면 `show` 와 반대 답이 된다.

        노트만 읽는 사람은 전환 run 을 fresh 로 읽고 composite 00 을 찾으러 간다. 확신에 찬
        오답이 UNKNOWN 보다 나쁘다.
        """
        from sage.commands import fast_cycle as fc  # noqa: PLC0415

        run_id = self._convert()
        path = Path(self.root, ".sage", "fast_cycle.jsonl")
        records = [json.loads(line) for line in
                   path.read_text(encoding="utf-8").splitlines() if line]
        # opener 줄이 사라진 상태 — 손으로 자른 감사나 앞부분이 유실된 파일이 이 모양이다.
        kept = [dict(record, event="fast_review") for record in records]
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept),
                        encoding="utf-8")
        state = fca.audit_summary(self.root)["runs"][run_id]
        self.assertIsNone(state["entry_mode"])

        row = next(line for line in fc._dashboard_body(self.root).splitlines() if run_id in line)
        self.assertIn("UNKNOWN", row)
        self.assertNotIn("FAST-CONVERTED", row)

    def test_the_dashboard_stays_off_until_the_project_opts_in(self):
        """opt-in 이 없으면 vault 에 아무것도 쓰지 않는다 — 조용한 부수효과가 되면 안 된다."""
        from unittest import mock  # noqa: PLC0415

        from sage.commands import fast_cycle as fc  # noqa: PLC0415

        for profile in ({}, {"knowledge_capture": {}},
                        {"knowledge_capture": {"fast_cycle_dashboard": False}},
                        {"knowledge_capture": {"fast_cycle_dashboard": "true"}}):
            with self.subTest(profile=profile), \
                 mock.patch.object(fc, "_profile", return_value=profile), \
                 mock.patch.object(fc, "_write_dashboard") as writer:
                fc._auto_dashboard(self.root)
                self.assertEqual(writer.call_count, 0, profile)

    def test_the_dashboard_says_how_the_run_entered_fast(self):
        """전환 run 과 fresh run 은 감사에서만 구분됐다. 대시보드를 읽는 사람에게는
        composite 계획을 쓴 run 인지 Standard 를 전환한 run 인지가 판단 근거다."""
        from sage.commands import fast_cycle as fc  # noqa: PLC0415

        converted = self._convert()
        fresh = fca.open_fast(self.root, cycle_stem="other", actual_risk="L3",
                              fast_review_level="L2", reason="fresh", minimum_rounds=1,
                              lenses=["correctness", "error_handling"],
                              profile_hash="sha256:p", plan_hash_open="sha256:q")
        body = fc._dashboard_body(self.root)
        rows = {line.split("|")[1].strip(): line for line in body.splitlines() if "| fc-" in line}
        self.assertIn("FAST-CONVERTED", rows[converted])
        self.assertIn("FAST", rows[fresh])
        self.assertNotIn("FAST-CONVERTED", rows[fresh])

    def test_show_tells_how_the_run_entered_fast(self):
        """스킬이 "문서에 `Fast-Audit-Run` 이 없는 게 정상" 을 판단하려면 판별자가 필요하다.

        판별자가 없으면 전환 run 과 스탬프에 실패한 fresh open 이 같아 보이고, 결속 확인 하나가
        조용히 꺼진다.
        """
        from sage.commands import fast_cycle as fc  # noqa: PLC0415
        from types import SimpleNamespace  # noqa: PLC0415
        import contextlib, io  # noqa: PLC0415

        run_id = self._convert()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = fc._run_show(SimpleNamespace(root=self.root, run_id=run_id, vault=None, lang=None))
        self.assertEqual(rc, 0)
        self.assertIn("entry=FAST-CONVERTED", out.getvalue())

    def test_actual_risk_is_pinned_separately_from_the_fast_review_level(self):
        self._convert(actual_risk="L3", fast_review_level="L2")
        record = fca.read_records(self.root)[0]
        self.assertEqual(record["actual_risk_open"], "L3")
        self.assertNotEqual(record["actual_risk_open"], record["fast_review_level"])

    def test_review_and_close_are_shared_with_a_fresh_run(self):
        run_id = self._convert()
        fca.record_review(self.root, run_id, loop_run_id="rl-1", actual_risk="L3", rounds=1,
                          lens_receipts_hash="sha256:x", plan_hash_before_review="sha256:y",
                          result="APPROVED", source_phases_review=self.sources)
        fca.close_fast(self.root, run_id, loop_run_id="rl-1", actual_risk="L3",
                       plan_hash_final="sha256:z", report_path="plan_docs/06-report/demo.md")
        state = fca.audit_summary(self.root)["runs"][run_id]
        self.assertTrue(state["terminal"])
        self.assertEqual(state["result"], "APPROVED")
        self.assertTrue(state["clean"])
        self.assertIs(state["chain_ok"], True)

    def test_converted_review_rejects_an_incomplete_or_malformed_snapshot(self):
        run_id = self._convert()
        malformed = dict(self.sources)
        malformed["00"] = {}
        for snapshot in ({"00": self.sources["00"]}, malformed):
            with self.subTest(snapshot=snapshot), self.assertRaises(fca.AuditWriteError):
                fca.record_review(
                    self.root, run_id, loop_run_id="rl-1", actual_risk="L3", rounds=1,
                    lens_receipts_hash="sha256:x", plan_hash_before_review="sha256:y",
                    result="APPROVED", source_phases_review=snapshot)

    def test_review_re_records_the_snapshot_so_the_delta_is_structured(self):
        """전환 뒤에도 문서는 정상 개발로 바뀐다. 리뷰가 무엇을 봤는지는 그 시점 스냅샷이 정본이다.

        전환 시점 스냅샷만 남기면 리뷰가 실제로 읽은 문서가 무엇이었는지 사후에 알 수 없다.
        """
        run_id = self._convert()
        changed = dict(self.sources)
        changed["02"] = dict(changed["02"], sha256="sha256:" + "f" * 64, size=999)
        changed["04"] = dict(changed["04"])
        fca.record_review(self.root, run_id, loop_run_id="rl-1", actual_risk="L3", rounds=1,
                          lens_receipts_hash="sha256:x", plan_hash_before_review="sha256:y",
                          result="APPROVED", source_phases_review=changed)
        review = [r for r in fca.read_records(self.root) if r["event"] == "fast_review"][-1]
        self.assertEqual(review["source_phases_review"], changed)
        delta = review["source_phases_delta"]
        self.assertEqual(delta["changed"], ["02"])
        self.assertEqual(delta["removed"], [])
        self.assertEqual(delta["added"], [])

    def test_a_moved_document_counts_as_changed_even_with_identical_bytes(self):
        """같은 내용이 다른 경로에 있으면 리뷰가 본 것은 다른 문서다.

        `sha256` 만 비교하면 파일을 옮긴 사실이 delta 에서 사라지고, 전환 시점 provenance 가
        가리키는 경로와 리뷰가 실제로 읽은 경로가 조용히 갈린다.
        """
        run_id = self._convert()
        moved = dict(self.sources)
        moved["02"] = dict(moved["02"], path="plan_docs/02-x/renamed.md")
        fca.record_review(self.root, run_id, loop_run_id="rl-1", actual_risk="L3", rounds=1,
                          lens_receipts_hash="sha256:x", plan_hash_before_review="sha256:y",
                          result="APPROVED", source_phases_review=moved)
        review = [r for r in fca.read_records(self.root) if r["event"] == "fast_review"][-1]
        self.assertEqual(review["source_phases_delta"]["changed"], ["02"])

    def test_a_fresh_run_records_no_snapshot_delta(self):
        """fresh Fast 의 정본은 composite 문서 hash 다 — 없는 스냅샷을 지어내지 않는다."""
        run_id = fca.open_fast(self.root, cycle_stem="fresh", actual_risk="L3",
                               fast_review_level="L2", reason="x", minimum_rounds=1,
                               lenses=["correctness", "error_handling"],
                               profile_hash="sha256:p", plan_hash_open="sha256:q")
        fca.record_review(self.root, run_id, loop_run_id="rl-1", actual_risk="L3", rounds=1,
                          lens_receipts_hash="sha256:x", plan_hash_before_review="sha256:y",
                          result="APPROVED")
        review = [r for r in fca.read_records(self.root) if r["event"] == "fast_review"][-1]
        self.assertNotIn("source_phases_review", review)
        self.assertNotIn("source_phases_delta", review)

    def test_a_second_opener_on_the_same_stem_is_refused(self):
        self._convert()
        with self.assertRaises(fca.AuditWriteError):
            self._convert()
        with self.assertRaises(fca.AuditWriteError):
            fca.open_fast(self.root, cycle_stem="demo", actual_risk="L3", fast_review_level="L2",
                          reason="x", minimum_rounds=1, lenses=["correctness", "security"],
                          profile_hash="sha256:p", plan_hash_open="sha256:q")

    def test_fresh_and_converted_openers_are_distinguishable(self):
        run_id = self._convert()
        state = fca.audit_summary(self.root)["runs"][run_id]
        self.assertEqual(state["entry_mode"], "FAST-CONVERTED")
        other = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, other, True)
        os.makedirs(os.path.join(other, ".sage"))
        fresh = fca.open_fast(other, cycle_stem="demo", actual_risk="L3", fast_review_level="L2",
                              reason="x", minimum_rounds=1, lenses=["correctness", "security"],
                              profile_hash="sha256:p", plan_hash_open="sha256:q")
        self.assertEqual(fca.audit_summary(other)["runs"][fresh]["entry_mode"], "FAST")

    def test_documents_are_not_touched_by_the_transition(self):
        before = {path: Path(self.root, path).read_bytes()
                  for path in (item["path"] for item in self.sources.values())}
        self._convert()
        for path, payload in before.items():
            self.assertEqual(Path(self.root, path).read_bytes(), payload, path)
        composite = list(Path(self.root, "plan_docs").rglob("*"))
        self.assertEqual(len([p for p in composite if p.is_file()]), len(self.sources))

    def test_concurrent_conversions_produce_exactly_one_run(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = [pool.submit(self._convert) for _ in range(4)]
        ok = [r for r in results if not r.exception()]
        self.assertEqual(len(ok), 1, [str(r.exception()) for r in results])
        self.assertEqual(len(fca.read_records(self.root)), 1)

    def test_append_failure_leaves_no_record(self):
        os.chmod(os.path.join(self.root, ".sage"), 0o500)
        self.addCleanup(os.chmod, os.path.join(self.root, ".sage"), 0o700)
        with self.assertRaises(Exception):  # noqa: B017 - 어떤 실패든 기록이 남지 않아야 한다
            self._convert()
        self.assertEqual(fca.read_records(self.root), [])

    def test_a_half_written_opener_is_rolled_back(self):
        """디렉터리 권한 차단은 "쓰기가 시작되지 않았다" 다 — rollback 을 증명하지 않는다.

        전환은 감사에 첫 줄을 얹는 조작이라, 절반만 쓰고 죽으면 뒤따르는 모든 판정이 손상된
        파일을 읽는다. 실제로 절반을 써 보고 파일이 원래 바이트로 돌아오는지 본다.
        """
        from unittest import mock  # noqa: PLC0415

        path = Path(self.root, ".sage", "fast_cycle.jsonl")
        first = self._convert()
        before = path.read_bytes()
        self.assertNotEqual(before, b"")

        def partial_write(fd, payload):
            return os.write(fd, payload[:len(payload) // 2])

        chain = sys.modules[fca._chain.__name__]
        with mock.patch.object(chain, "_write_once", side_effect=partial_write), \
             self.assertRaises(Exception):  # noqa: B017
            fca.record_review(self.root, first, loop_run_id="rl-1", actual_risk="L3", rounds=1,
                              lens_receipts_hash="sha256:x", plan_hash_before_review="sha256:y",
                              result="APPROVED", source_phases_review=self.sources)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual([r["event"] for r in fca.read_records(self.root)], ["fast_convert"])


class TestConvertCLI(unittest.TestCase):
    """CLI preflight — 확인 없이는 아무것도 기록되지 않는다."""

    STEM = "welstory-login"

    def setUp(self):
        import subprocess  # noqa: PLC0415 - CLI 경계 테스트에서만 필요
        import yaml        # noqa: PLC0415

        self.subprocess = subprocess
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        Path(self.root, "sage").mkdir()
        phases = [{"id": pid, "glob": f"plan_docs/{pid}-x/**/*.md"}
                  for pid in ("00", "01", "02", "03", "04", "05", "06")]
        self.profile = {"pdca": {
            "phases": phases,
            "approve_phase": "05",
            "approve_marker": "APPROVED",
            "report_phase": "06",
            "fast_cycle": dict(_fast()["pdca"]["fast_cycle"],
                               standard_transition={"enabled": True}),
        }}
        self._write_profile()
        sys.path.insert(0, os.path.join(HOOKS_DIR, "runtime"))
        import cycle_state  # noqa: PLC0415
        cycle_state.write_declaration(self.root, self.STEM, document_language="ko")
        for phase in ("00", "01", "02", "03", "04"):
            self._write_phase(phase)

    def _write_profile(self):
        import yaml  # noqa: PLC0415
        Path(self.root, "sage", "project-profile.yaml").write_text(
            yaml.safe_dump(self.profile, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def _write_phase(self, phase, risk="L3", extra=""):
        path = Path(self.root, "plan_docs", f"{phase}-x", f"{self.STEM}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        header = f"# Phase {phase}\n\nCycle-Stem: `{self.STEM}`\nDocument-Language: ko\n"
        if phase == "00":
            header += f"Risk Level: {risk}\n"
        path.write_text(header + "\n## 본문\n\n" + extra, encoding="utf-8")
        return path

    def _run(self, *args):
        env = dict(os.environ, PYTHONPATH=REPO)
        return self.subprocess.run([sys.executable, "-m", "sage", *args, "--root", self.root],
                                   text=True, capture_output=True, env=env, cwd=self.root)

    def _convert(self, **over):
        argv = {"--stem": self.STEM, "--current-phase": "04", "--level": "L2",
                "--lens-count": "2", "--reason": "긴급 배포 창구가 닫힌다",
                "--confirmed-by": "sejon", "--confirm": "FAST-CONVERTED"}
        argv.update(over)
        flat = [item for pair in argv.items() for item in pair if item is not None]
        return self._run("fast-cycle", "convert", *flat)

    def _audit(self):
        path = Path(self.root, ".sage", "fast_cycle.jsonl")
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def test_happy_path_records_a_converted_opener_and_touches_no_document(self):
        before = {p: p.read_bytes() for p in Path(self.root, "plan_docs").rglob("*.md")}
        result = self._convert()
        self.assertEqual(result.returncode, 0, result.stderr)
        records = self._audit()
        self.assertEqual([r["event"] for r in records], ["fast_convert"])
        self.assertEqual(records[0]["entry_mode"], "FAST-CONVERTED")
        self.assertEqual(records[0]["actual_risk_open"], "L3")
        self.assertEqual(records[0]["fast_review_level"], "L2")
        snapshot = records[0]["source_phases_open"]
        self.assertEqual(sorted(snapshot), ["00", "01", "02", "03", "04"])
        # 경로·크기·해시는 감사가 가리키는 대상이 실제 그 파일이라는 유일한 증거다. 키만 확인하면
        # `path` 를 상수로 바꾸거나 `size` 를 지워도 아무도 모른다.
        for phase, entry in snapshot.items():
            with self.subTest(phase=phase):
                payload = Path(self.root, "plan_docs", f"{phase}-x", f"{self.STEM}.md").read_bytes()
                self.assertEqual(entry["path"], f"plan_docs/{phase}-x/{self.STEM}.md")
                self.assertEqual(entry["size"], len(payload))
                self.assertEqual(entry["sha256"],
                                 "sha256:" + hashlib.sha256(payload).hexdigest())
        self.assertEqual(records[0]["confirmed_by"], "sejon")
        for path, payload in before.items():
            self.assertEqual(path.read_bytes(), payload, path)
        self.assertEqual(len(list(Path(self.root, "plan_docs").rglob("*.md"))), len(before))

    def test_a_tampered_audit_chain_refuses_the_conversion(self):
        """`file_ok` 는 JSON 이 읽히는지만 본다. 레코드 값을 고쳐도 참이다.

        전환은 감사 위에 새 opener 를 얹는 조작이므로, 밑에 깔린 기록이 손상됐으면 얹으면 안 된다.
        """
        first = self._convert()
        self.assertEqual(first.returncode, 0, first.stderr)
        path = Path(self.root, ".sage", "fast_cycle.jsonl")
        original = path.read_text(encoding="utf-8")
        path.write_text(original.replace('"L3"', '"L1"'), encoding="utf-8")
        tampered = path.read_text(encoding="utf-8")

        result = self._convert(**{"--stem": self.STEM})
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(path.read_text(encoding="utf-8"), tampered)
        self.assertIn("integrity", (result.stderr or "").lower())

    def test_every_missing_or_wrong_input_writes_nothing(self):
        cases = {
            "confirm token": {"--confirm": "yes"},
            # 조기 종료 승인 토큰이 전환을 열지 않는다 — 두 확인은 서로의 승인이 아니다.
            "the other feature's token": {"--confirm": "USER_AUTHORIZED_EARLY"},
            "empty reason": {"--reason": "   "},
            "empty approver": {"--confirmed-by": " "},
            "lens below minimum": {"--lens-count": "1"},
            "lens above candidates": {"--lens-count": "9"},
            "other stem": {"--stem": "other-cycle"},
        }
        for label, over in cases.items():
            with self.subTest(label=label):
                result = self._convert(**over)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(self._audit(), [], label)

    def test_transition_stays_closed_until_the_profile_opts_in(self):
        self.profile["pdca"]["fast_cycle"].pop("standard_transition")
        self._write_profile()
        self.assertEqual(self._convert().returncode, 2)
        self.assertEqual(self._audit(), [])
        self.profile["pdca"]["fast_cycle"]["standard_transition"] = {"enabled": False}
        self._write_profile()
        self.assertEqual(self._convert().returncode, 2)
        self.assertEqual(self._audit(), [])

    def test_an_l1_cycle_is_not_converted(self):
        self._write_phase("00", risk="L1")
        result = self._convert()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self._audit(), [])

    def test_a_broken_risk_declaration_blocks_the_transition(self):
        self._write_phase("00", risk="L1|L2|L3")
        self.assertEqual(self._convert().returncode, 2)
        self.assertEqual(self._audit(), [])

    def test_a_completed_cycle_is_refused(self):
        self._write_phase("05", extra="Final Status: APPROVED\n")
        result = self._convert()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self._audit(), [])

    def test_a_symlinked_phase_document_blocks_the_snapshot(self):
        """provenance 는 감사가 가리키는 경로가 실제로 읽은 파일이라는 보장 위에 선다.

        symlink 를 허용하면 감사에 남는 경로와 해시가 서로 다른 파일을 가리킬 수 있다.
        """
        path = Path(self.root, "plan_docs", "02-x", f"{self.STEM}.md")
        target = Path(self.root, "plan_docs", "02-x", "elsewhere.md")
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.unlink()
        try:
            os.symlink(target, path)
        except (OSError, NotImplementedError):
            self.skipTest("symlink 미지원 환경")
        result = self._convert()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("symlink", result.stderr)
        self.assertEqual(self._audit(), [])

    def test_a_missing_intermediate_phase_blocks_the_snapshot(self):
        Path(self.root, "plan_docs", "02-x", f"{self.STEM}.md").unlink()
        self.assertEqual(self._convert().returncode, 2)
        self.assertEqual(self._audit(), [])
        # 그 phase 를 요구하지 않는 지점까지면 전환할 수 있다.
        self.assertEqual(self._convert(**{"--current-phase": "01"}).returncode, 0)
        self.assertEqual(len(self._audit()), 1)

    def test_a_composite_fast_plan_is_not_convertible(self):
        """이미 composite 인 사이클을 전환하면 review 가 composite 검사를 통째로 건너뛴다 —
        Phase 04 PENDING, run-id 결속, 문서 선언과 인자 대조가 전부 사라진다."""
        composite = (f"# Fast Base Plan\n\nCycle-Stem: `{self.STEM}`\nCycle-Mode: FAST\n"
                     "Risk Level: L3\nFast-Review-Level: L2\nFast-Minimum-Rounds: 1\n"
                     "Fast-Lens-Count: 2\nFast-Lenses: correctness, error_handling\n"
                     "Fast-Reason: outage\nFast-Audit-Run: pending\nDocument-Language: ko\n"
                     "\n## Phase 00 — Base Plan\n### Done Criteria\n- [ ] a\n"
                     "\n## Phase 01 — Requirements\n## Phase 02 — Design\n"
                     "## Phase 03 — Implementation\n## Phase 04 — Analyze\n")
        Path(self.root, "plan_docs", "00-x", f"{self.STEM}.md").write_text(
            composite, encoding="utf-8")
        result = self._convert()
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("already a composite Fast Plan", result.stderr)
        self.assertEqual(self._audit(), [])

    def test_a_second_transition_on_the_same_stem_is_refused(self):
        self.assertEqual(self._convert().returncode, 0)
        self.assertEqual(self._convert().returncode, 2)
        self.assertEqual(len(self._audit()), 1)

    def test_current_phase_outside_the_convertible_range_is_rejected_by_the_parser(self):
        result = self._convert(**{"--current-phase": "05"})
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self._audit(), [])


class TestConvertedRunCompletesItsLifecycle(unittest.TestCase):
    """전환은 시작이지 끝이 아니다 — review·close 까지 CLI 로 갈 수 있어야 기능이다.

    감사 층만 보면 `record_review`/`close_fast` 가 fresh 와 공유되므로 통과한 것처럼 보인다.
    CLI 는 composite 문서를 파싱해서 위험도·hash·Done Criteria 를 얻는데, 전환 run 에는 그
    문서가 없다. 여기서 막히면 전환한 사이클은 abort 말고 나갈 길이 없다.
    """

    STEM = TestConvertCLI.STEM
    setUp = TestConvertCLI.setUp
    _write_profile = TestConvertCLI._write_profile
    _write_phase = TestConvertCLI._write_phase
    _run = TestConvertCLI._run
    _convert = TestConvertCLI._convert
    _audit = TestConvertCLI._audit

    def _loop(self, run_id):
        import loop_audit as la  # noqa: PLC0415

        loop_run = la.open_loop(self.root, "L3", run_id="rl-converted-1", cycle_stem=self.STEM,
                                lenses=["correctness", "error_handling"])
        la.record_round(self.root, loop_run, 1, 0, 0, 0,
                        lens_receipts=["correctness", "error_handling"])
        la.close_loop(self.root, loop_run, "APPROVED", "DRY", 1)
        return loop_run

    def _evidence(self, phase, fast_run, loop_run):
        path = Path(self.root, "plan_docs", f"{phase}-x", f"{self.STEM}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Phase {phase}\n\nCycle-Stem: `{self.STEM}`\nDocument-Language: ko\n"
                        f"Fast-Run: {fast_run}\nLoop-Run: {loop_run}\n"
                        "Final Status: APPROVED\n", encoding="utf-8")

    def test_convert_review_and_close_complete_without_a_composite_plan(self):
        self.assertEqual(self._convert().returncode, 0)
        fast_run = self._audit()[0]["run_id"]
        loop_run = self._loop(fast_run)
        self._evidence("05", fast_run, loop_run)

        reviewed = self._run("fast-cycle", "review", "--run-id", fast_run,
                             "--loop-run-id", loop_run)
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
        review = [r for r in self._audit() if r["event"] == "fast_review"][-1]
        self.assertIn("source_phases_review", review)
        self.assertEqual(review["source_phases_delta"]["removed"], [])

        self._evidence("06", fast_run, loop_run)
        closed = self._run("fast-cycle", "close", "--run-id", fast_run)
        self.assertEqual(closed.returncode, 0, closed.stderr)
        self.assertEqual([r["event"] for r in self._audit()][-1], "fast_close")

    def test_close_refuses_when_a_phase_document_changed_after_review(self):
        """전환 run 의 계획·설계·구현 기록은 Phase 00 밖에 있다. Phase 00 해시만 대조하면
        리뷰 뒤 01~04 가 바뀌어도 닫힌다 — fresh 는 composite 하나라 그 자리가 없었다."""
        self.assertEqual(self._convert().returncode, 0)
        fast_run = self._audit()[0]["run_id"]
        loop_run = self._loop(fast_run)
        self._evidence("05", fast_run, loop_run)
        self.assertEqual(self._run("fast-cycle", "review", "--run-id", fast_run,
                                   "--loop-run-id", loop_run).returncode, 0)
        self._evidence("06", fast_run, loop_run)
        self._write_phase("03", extra="리뷰 뒤에 바뀐 구현 기록\n")

        closed = self._run("fast-cycle", "close", "--run-id", fast_run)
        self.assertEqual(closed.returncode, 2, closed.stdout)
        self.assertIn("changed after the latest review", closed.stderr)
        self.assertNotIn("fast_close", [record["event"] for record in self._audit()])

    def test_close_refuses_a_converted_review_without_a_document_snapshot(self):
        """전환 review의 snapshot 부재는 '변경 없음'이 아니라 '결속 불가'다.

        정상 CLI는 snapshot을 쓰지만 감사 writer의 기본값은 None이다. 그 레코드도 체인상 유효하므로
        local close가 부재를 건너뛰면 서버 권위를 쓰지 않는 프로젝트에서 00~04 결속 없이 닫힌다.
        """
        self.assertEqual(self._convert().returncode, 0)
        fast_run = self._audit()[0]["run_id"]
        loop_run = self._loop(fast_run)
        phase00 = Path(self.root, "plan_docs", "00-x", f"{self.STEM}.md").read_text(
            encoding="utf-8")
        # 현재 writer는 이 상태를 거부한다. 과거 writer나 수기 append로 이미 존재하는 체인상 유효
        # 레코드도 close 검출층이 막는지 보기 위해 저장 primitive로 직접 재현한다.
        record = fca._base("fast_review", fast_run, self.STEM)
        record.update({
            "loop_run_id": loop_run,
            "actual_risk_review": "L3",
            "rounds": 1,
            "lens_receipts_hash": "sha256:test",
            "plan_hash_before_review": hashlib.sha256(phase00.encode("utf-8")).hexdigest(),
            "result": "APPROVED",
        })
        fca._append(self.root, record)
        self._evidence("05", fast_run, loop_run)
        self._evidence("06", fast_run, loop_run)

        closed = self._run("fast-cycle", "close", "--run-id", fast_run)
        self.assertEqual(closed.returncode, 2, closed.stderr)
        self.assertIn("snapshot", closed.stderr.lower())
        self.assertNotIn("fast_close", [record["event"] for record in self._audit()])

    def test_a_phase00_conversion_reviews_later_phase_documents_too(self):
        """전환 시점은 provenance 범위이지 이후 리뷰 범위의 상한이 아니다.

        Phase 00에서 전환해도 소스 편집 전 01~03을 작성하고 리뷰 전 04까지 작성한다. 리뷰가
        opener의 current_phase만 다시 읽으면 이후 문서는 승인 결속에서 영구히 빠진다.
        """
        self.assertEqual(self._convert(**{"--current-phase": "00"}).returncode, 0)
        fast_run = self._audit()[0]["run_id"]
        loop_run = self._loop(fast_run)
        self._evidence("05", fast_run, loop_run)

        reviewed = self._run("fast-cycle", "review", "--run-id", fast_run,
                             "--loop-run-id", loop_run)
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
        review = [record for record in self._audit()
                  if record["event"] == "fast_review"][-1]
        self.assertEqual(set(review["source_phases_review"]), {"00", "01", "02", "03", "04"})

        self._evidence("06", fast_run, loop_run)
        self._write_phase("03", extra="리뷰 뒤에 바뀐 구현 기록\n")
        closed = self._run("fast-cycle", "close", "--run-id", fast_run)
        self.assertEqual(closed.returncode, 2, closed.stderr)
        self.assertIn("changed after the latest review", closed.stderr)

    def test_evidence_is_read_from_the_run_s_own_cycle_not_the_declared_one(self):
        """run-id 는 사이클 사이를 넘지 않는다.

        stem 을 선언 상태에서 가져오면 다른 사이클의 05 문서가 이 run 의 승인 근거가 될 수 있다.
        그러면 감사에는 한 run 이 두 사이클에 걸친 기록만 남아 사후 판별이 불가능해진다. stem 은
        감사 run 자신이 들고 있어야 하고, 다른 사이클에만 증거가 있으면 통과하지 못해야 한다.
        """
        import cycle_state  # noqa: PLC0415

        self.assertEqual(self._convert().returncode, 0)
        fast_run = self._audit()[0]["run_id"]
        loop_run = self._loop(fast_run)

        # 증거는 다른 사이클에만 둔다 — 이 run 의 사이클 05 는 표기가 없다.
        other = "other-cycle"
        for phase in ("00", "05"):
            path = Path(self.root, "plan_docs", f"{phase}-x", f"{other}.md")
            path.parent.mkdir(parents=True, exist_ok=True)
            body = f"# Phase {phase}\n\nCycle-Stem: `{other}`\nDocument-Language: ko\n"
            body += ("Risk Level: L3\n" if phase == "00" else
                     f"Fast-Run: {fast_run}\nLoop-Run: {loop_run}\nFinal Status: APPROVED\n")
            path.write_text(body, encoding="utf-8")
        cycle_state.write_declaration(self.root, other, document_language="ko")

        before = [record["event"] for record in self._audit()]
        reviewed = self._run("fast-cycle", "review", "--run-id", fast_run,
                             "--loop-run-id", loop_run)
        self.assertEqual(reviewed.returncode, 2, reviewed.stdout)
        # 이 run 의 사이클 05 가 없다는 진단이어야 한다 — 다른 사이클 문서를 대신 읽었다면
        # 통과했을 자리다.
        self.assertIn(self.STEM, reviewed.stderr)
        self.assertNotIn("other-cycle", reviewed.stderr)
        self.assertEqual([record["event"] for record in self._audit()], before)

    def test_a_document_changed_after_conversion_is_recorded_as_a_delta(self):
        self.assertEqual(self._convert().returncode, 0)
        fast_run = self._audit()[0]["run_id"]
        loop_run = self._loop(fast_run)
        self._evidence("05", fast_run, loop_run)
        self._write_phase("02", extra="전환 뒤 정상 개발로 바뀐 부분\n")

        reviewed = self._run("fast-cycle", "review", "--run-id", fast_run,
                             "--loop-run-id", loop_run)
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
        review = [r for r in self._audit() if r["event"] == "fast_review"][-1]
        self.assertEqual(review["source_phases_delta"]["changed"], ["02"])


class TestConvertedRunAtTheGate(unittest.TestCase):
    """전환 run 은 Standard 문서를 그대로 둔다 — 게이트가 그걸 composite Fast Plan 으로 읽으면 안 된다.

    전환의 목적은 남은 절차를 Fast 계약으로 바꾸는 것이다. 게이트가 전환 run 을 fresh Fast 경로로
    강제하면 전환 직후 그 사이클에서 소스를 한 줄도 못 쓰게 되고, 유일한 해소책이 설계가 금지한
    composite 00 재작성이 된다.
    """

    STEM = "welstory-login"

    def setUp(self):
        sys.path.insert(0, HOOKS_DIR)
        import pre_implementation_gate_core as core  # noqa: PLC0415

        self.core = core
        self.profile = {
            "risk": {"l0_pass_globs": ["*plan_docs/*", "*.md"],
                     "l2_path_globs": ["*src/*.py"]},
            "pdca": {
                "enabled": True,
                "phases": [{"id": pid, "glob": f"plan_docs/{pid}-x/**/*.md"}
                           for pid in ("00", "01", "02", "03")],
                "pre_implementation_required": {"L2": ["00", "01", "02", "03"],
                                                "L3": ["00", "01", "02", "03"]},
                "fast_cycle": _fast()["pdca"]["fast_cycle"],
            },
        }

    def _phase00(self):
        return {"path": f"{self.STEM}.md",
                "content": f"Cycle-Stem: `{self.STEM}`\nRisk Level: L2\n", "recent": True}

    def _snapshot(self, fast_audit=None):
        snapshot = {"plan_files": [self._phase00()], "review_candidates": [],
                    "phase_docs": {"00": [self._phase00()]}}
        if fast_audit is not None:
            snapshot["fast_cycle_audit"] = fast_audit
        return snapshot

    def _converted_audit(self, **over):
        run = {"cycle_stem": self.STEM, "entry_mode": "FAST-CONVERTED", "terminal": False,
               "clean": True, "chain_ok": True, "seq_ok": True, "actual_risk": "L2",
               "fast_review_level": "L2", "minimum_rounds": 1,
               "lenses": ["correctness", "error_handling"], "current_phase": "04"}
        run.update(over)
        return {"active": ["fc-abc"], "runs": {"fc-abc": run}, "file_ok": True,
                "has_any_records": True}

    def _event(self, path="src/app.py"):
        return {"hook_id": "pre-implementation-gate", "runtime": "test", "branch": "main",
                "session_id": "s", "cycle_stem": self.STEM, "cycle_stem_origin": "env",
                "declared_max": None,
                "changes": [{"path": path, "op": "write", "content": "x = 1\n"}]}

    def test_a_converted_run_is_not_parsed_as_a_composite_fast_plan(self):
        decision = self.core.decide(self._event(), self.profile,
                                    self._snapshot(self._converted_audit()), None)
        self.assertNotEqual(decision.get("message_key"), "block_fast_cycle_audit",
                            decision.get("reason"))

    def test_a_converted_run_relaxes_the_pre_implementation_requirement(self):
        """Fast 계약으로 바뀐 사이클이므로 00~03 전부를 다시 요구하지 않는다."""
        state, detail = self.core._fast_cycle_state(
            self._event(), self.profile, self._snapshot(self._converted_audit()),
            self.profile["pdca"])
        self.assertIsNone(detail, detail)
        self.assertIsNotNone(state)
        self.assertEqual(state.get("entry_mode"), "FAST-CONVERTED")

    def test_a_damaged_or_terminal_converted_run_still_blocks(self):
        for label, over in (("dirty", {"clean": False}),
                            ("chain", {"chain_ok": False}),
                            ("seq", {"seq_ok": False}),
                            ("terminal", {"terminal": True})):
            with self.subTest(label=label):
                audit = self._converted_audit(**over)
                if label == "terminal":
                    audit["active"] = []
                state, detail = self.core._fast_cycle_state(
                    self._event(), self.profile, self._snapshot(audit), self.profile["pdca"])
                self.assertIsNone(state, label)

    def test_a_risk_mismatch_between_phase00_and_the_audit_blocks(self):
        audit = self._converted_audit(actual_risk="L3")
        state, detail = self.core._fast_cycle_state(
            self._event(), self.profile, self._snapshot(audit), self.profile["pdca"])
        self.assertIsNone(state)
        self.assertIsNotNone(detail)

    def test_another_stems_active_run_does_not_block_this_cycle(self):
        """비교 대상은 같은 stem 의 active run 이다. 전역과 비교하면 남이 방치한 run 하나가
        이 사이클의 모든 쓰기를 막고, 진단문은 관계없는 run 을 가리킨다."""
        audit = self._converted_audit()
        audit["runs"]["fc-other"] = dict(audit["runs"]["fc-abc"],
                                         cycle_stem="other-stem", entry_mode="FAST")
        audit["active"] = ["fc-abc", "fc-other"]
        state, detail = self.core._fast_cycle_state(
            self._event(), self.profile, self._snapshot(audit), self.profile["pdca"])
        self.assertIsNotNone(state, detail)
        self.assertIsNone(detail)

    def test_two_active_converted_runs_on_one_stem_block(self):
        audit = self._converted_audit()
        audit["runs"]["fc-def"] = dict(audit["runs"]["fc-abc"])
        audit["active"] = ["fc-abc", "fc-def"]
        state, detail = self.core._fast_cycle_state(
            self._event(), self.profile, self._snapshot(audit), self.profile["pdca"])
        self.assertIsNone(state)
        self.assertIsNotNone(detail)

    def test_converting_early_does_not_waive_the_planning_it_never_did(self):
        """Phase 00 하나만 쓰고 전환해 계획 요구를 통째로 면제받을 수 없다.

        fresh Fast 의 면제는 composite 00 이 00~04 를 담고 있다는 것을 파서가 확인한 뒤에 성립한다.
        전환 run 에는 composite 문서가 없고 담보는 전환 시점 실재 문서 목록뿐이다. 그걸 안 보면
        전환이 계획을 건너뛰는 통로가 된다.
        """
        audit = self._converted_audit(current_phase="00",
                                      source_phases_open={"00": {"path": "plan_docs/00-x/x.md"}})
        snapshot = self._snapshot(audit)
        state, detail = self.core._fast_cycle_state(self._event(), self.profile, snapshot,
                                                   self.profile["pdca"])
        self.assertIsNotNone(state, detail)
        missing = self.core._missing_pre_impl_phases(self._event(), self.profile, snapshot,
                                                     "L2", state)
        self.assertEqual(missing, ["01", "02", "03"])
        decision = self.core.decide(self._event(), self.profile, snapshot, None)
        self.assertEqual(decision["message_key"], "block_phase_incomplete")

    def test_converting_late_waives_what_the_standard_cycle_already_produced(self):
        audit = self._converted_audit(
            current_phase="04",
            source_phases_open={pid: {"path": f"plan_docs/{pid}-x/x.md"}
                                for pid in ("00", "01", "02", "03", "04")})
        snapshot = self._snapshot(audit)
        state, _detail = self.core._fast_cycle_state(self._event(), self.profile, snapshot,
                                                    self.profile["pdca"])
        self.assertEqual(self.core._missing_pre_impl_phases(self._event(), self.profile,
                                                            snapshot, "L2", state), [])

    def test_writing_the_missing_phase_documents_stays_possible_after_an_early_conversion(self):
        """면제를 좁히면서 B 가 푼 교착을 되살리면 안 된다."""
        audit = self._converted_audit(current_phase="00",
                                      source_phases_open={"00": {"path": "plan_docs/00-x/x.md"}})
        event = self._event(path=f"plan_docs/02-x/{self.STEM}.md")
        event["changes"][0]["content"] = f"Cycle-Stem: `{self.STEM}`\n# 02\n"
        decision = self.core.decide(event, self.profile, self._snapshot(audit), None)
        self.assertNotEqual(decision.get("message_key"), "block_phase_incomplete")

    def test_a_converted_run_without_a_source_snapshot_gets_no_waiver(self):
        audit = self._converted_audit(source_phases_open=None)
        snapshot = self._snapshot(audit)
        state, _detail = self.core._fast_cycle_state(self._event(), self.profile, snapshot,
                                                    self.profile["pdca"])
        self.assertNotEqual(self.core._missing_pre_impl_phases(self._event(), self.profile,
                                                               snapshot, "L2", state), [])

    def test_a_fresh_fast_run_still_requires_its_composite_plan(self):
        """전환 경로를 열면서 fresh Fast 의 문서 결속을 느슨하게 만들면 안 된다."""
        audit = self._converted_audit(entry_mode="FAST")
        state, detail = self.core._fast_cycle_state(
            self._event(), self.profile, self._snapshot(audit), self.profile["pdca"])
        self.assertIsNone(state)
        self.assertIsNotNone(detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
