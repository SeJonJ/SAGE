#!/usr/bin/env python3
"""Regression tests for protected CI authority and attestation."""
from __future__ import annotations

from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import yaml

from sage import ci_authority
from sage.done_criteria_contract import phase00_text_hash
from sage.cli import main as cli_main
from sage.commands import authority


STEM = "sage-fb-08-server-authority-attestation"
KEY = b"authority-test-key-with-at-least-32-bytes"
BASE = "1" * 40
HEAD = "2" * 40
BASE_SOURCE = "".join(f"value_{index} = 1\n" for index in range(40))
HEAD_SOURCE = BASE_SOURCE.replace("value_39 = 1", "value_39 = 2")


def _classifier(_event, profile):
    return {"risk": profile["test_risk"], "reason": "test", "trigger_sources": []}


def _phase_docs(status04="PASS", status05="APPROVED", declared="L3"):
    docs = {}
    for phase, folder in (
        ("00", "00-base_plan"), ("01", "01-plan"), ("02", "02-design"),
        ("03", "03-implementation"), ("04", "04-analyze"),
        ("05", "05-expert-review"),
    ):
        body = f"Cycle-Stem: `{STEM}`\nRisk Level: {declared}\n"
        if phase == "01":
            body += """\n## Acceptance Matrix
| ID | Requirement | Required? |
|---|---|:---:|
| AC1 | protected result | yes |
"""
        if phase == "04":
            body += f"""\n## Acceptance Evidence
| ID | Status | Evidence |
|---|:---:|---|
| AC1 | {status04} | deterministic proof |
"""
        if phase == "05":
            body += f"\nFinal Status: {status05}\n"
        docs[phase] = [{"path": f"plan_docs/{folder}/{STEM}.md", "content": body}]
    return docs


def _change(path="src/security.py", base="old", head="new", op="modify", old_path=""):
    return {
        "op": op,
        "path": path,
        "old_path": old_path or path,
        "base_oid": "a" * 40 if base else "",
        "head_oid": "b" * 40 if head else "",
        "base_content": base,
        "head_content": head,
    }


def _request(base_risk="L3", head_risk="L1"):
    return {
        "base_profile": {"test_risk": base_risk},
        "head_profile": {"test_risk": head_risk},
        "changes": [_change()],
        "phase_docs": _phase_docs(),
        "cycle_stem": STEM,
        "repository": "owner/repo",
        "base_sha": BASE,
        "head_sha": HEAD,
        "expected_issuer": "protected-ci",
    }


def _claims(result, now=None):
    issued = int(time.time()) if now is None else now
    return {
        "version": 1,
        "issuer": "protected-ci",
        "repository": "owner/repo",
        "base_sha": BASE,
        "head_sha": HEAD,
        "diff_sha256": result["diff_sha256"],
        "cycle_stem": STEM,
        "risk": result["risk"],
        "reviewer": "authority-job",
        "verdict": "APPROVED",
        "nonce": "nonce-0123456789abcdef",
        "issued_at": issued,
        "expires_at": issued + 300,
    }


class PureAuthorityTests(unittest.TestCase):
    def test_a_converted_run_is_not_invisible_to_the_authority(self):
        """전환 run 의 Phase 00 은 Standard 문서라 `Cycle-Mode: FAST` 가 없다.

        composite 여부만 보고 빠져나가면, 축약된 Fast 리뷰로 닫은 run 이 서버 권위에서 Fast 증거
        검증을 **하나도** 받지 않고 표준 경로로 통과한다. 감사에 전환 opener 가 있으면 결속한다.
        """
        import tempfile  # noqa: PLC0415
        from pathlib import Path as _Path  # noqa: PLC0415

        ci_authority._trusted_gate_modules()
        import fast_cycle_audit as fca  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as root:
            _Path(root, ".sage").mkdir()
            sources = {"00": {"path": "plan_docs/00-base_plan/x.md",
                              "sha256": "sha256:" + "0" * 64, "size": 1}}
            fca.convert_fast(root, cycle_stem=STEM, current_phase="04", actual_risk="L3",
                             fast_review_level="L2", reason="긴급", confirmed_by="sejon",
                             minimum_rounds=1, lenses=["correctness", "error_handling"],
                             source_phases=sources)
            fast_text = _Path(root, ".sage", "fast_cycle.jsonl").read_text(encoding="utf-8")

        request = _request()
        request["fast_cycle_audit"] = fast_text
        request["loop_audit"] = ""
        core, _binding, _risk = ci_authority._trusted_gate_modules()
        reasons = ci_authority._fast_evidence_reasons(
            request, {"00": request["phase_docs"]["00"][0],
                      "05": request["phase_docs"]["05"][0]}, STEM)
        self.assertNotEqual(reasons, [], "전환 run 이 검증 없이 통과했다")
        self.assertTrue(any("not clean terminal APPROVED evidence" in reason
                            for reason in reasons), reasons)

    def _converted_audit(self, aborts=0, converts=1, stem=None):
        import tempfile  # noqa: PLC0415
        from pathlib import Path as _Path  # noqa: PLC0415

        ci_authority._trusted_gate_modules()
        import fast_cycle_audit as fca  # noqa: PLC0415

        stem = stem or STEM
        sources = {"00": {"path": "plan_docs/00-base_plan/x.md",
                          "sha256": "sha256:" + "0" * 64, "size": 1}}
        with tempfile.TemporaryDirectory() as root:
            _Path(root, ".sage").mkdir()
            for index in range(converts):
                rid = fca.convert_fast(root, cycle_stem=stem, current_phase="04",
                                       actual_risk="L3", fast_review_level="L2", reason="긴급",
                                       confirmed_by="sejon", minimum_rounds=1,
                                       lenses=["correctness", "error_handling"],
                                       source_phases=sources)
                if index < aborts:
                    fca.abort_fast(root, rid, reason="취소", stage="manual", actual_risk="L3")
            return _Path(root, ".sage", "fast_cycle.jsonl").read_text(encoding="utf-8")

    def _fast_reasons(self, fast_text, phase05=None):
        request = _request()
        request["fast_cycle_audit"] = fast_text
        request["loop_audit"] = ""
        review = dict(request["phase_docs"]["05"][0])
        if phase05 is not None:
            review["content"] = phase05
        return ci_authority._fast_evidence_reasons(
            request, {"00": request["phase_docs"]["00"][0], "05": review}, STEM)

    def test_an_uncommitted_audit_cannot_hide_a_fast_run(self):
        """전환 run 의 Fast 성은 감사에만 있다 — `.gitignore` 한 줄로 CI 검증을 끌 수 있었다.

        커밋 트리에 남는 신호는 Phase 05 의 `Fast-Run:` 표기다(`fast-cycle review` 가 강제한다).
        """
        reasons = self._fast_reasons("", phase05="Fast-Run: fc-deadbeef0001\nFinal Status: APPROVED\n")
        self.assertNotEqual(reasons, [])
        self.assertTrue(any("no committed Fast audit" in reason for reason in reasons), reasons)

    def test_two_live_converted_runs_on_one_stem_fail_closed(self):
        """어느 쪽 증거인지 정할 수 없는 상태에서 조용히 결속을 포기하면 검증이 통째로 꺼진다.

        엔진은 같은 stem 에 active run 을 둘 만들지 못하므로, 이 상태는 손으로 고친 감사에서만
        나온다. run 단위로 도는 무결성 검사는 서로 다른 run 이 같은 stem 을 쓰는 것을 보지 못한다.
        """
        tampered = self._converted_audit(converts=2, aborts=1).replace("fast_abort", "fast_noop")
        reasons = self._fast_reasons(tampered)
        self.assertNotEqual(reasons, [])
        self.assertTrue(any("cannot tell which one" in reason for reason in reasons), reasons)

    def test_an_aborted_conversion_returns_the_cycle_to_the_standard_path(self):
        """abort 는 전환을 취소하는 정규 수단이다. 잔재가 남아 영구 차단되면 출구가 없다."""
        self.assertEqual(self._fast_reasons(self._converted_audit(converts=1, aborts=1)), [])

    def test_a_plain_standard_cycle_stays_out_of_the_fast_path(self):
        """전환 opener 가 없으면 Standard 사이클이다 — 없던 Fast 요구를 새로 만들지 않는다."""
        request = _request()
        request["fast_cycle_audit"] = ""
        request["loop_audit"] = ""
        reasons = ci_authority._fast_evidence_reasons(
            request, {"00": request["phase_docs"]["00"][0],
                      "05": request["phase_docs"]["05"][0]}, STEM)
        self.assertEqual(reasons, [])

    def _complete_converted_run(self, *, review_snapshot, phase_docs, run_id="fc-cc01",
                                loop_run_id="rl-cc01", open_snapshot=None,
                                current_phase="04"):
        """전환 run 한 건의 온전한 Fast·Loop 감사 원문 — convert→review→close 를 다 걷는다."""
        import hashlib as _hashlib  # noqa: PLC0415
        import tempfile  # noqa: PLC0415
        from pathlib import Path as _Path  # noqa: PLC0415

        ci_authority._trusted_gate_modules()
        import fast_cycle_audit as fca  # noqa: PLC0415
        import loop_audit as la  # noqa: PLC0415

        lenses = ["correctness", "error_handling"]
        plan_hash = _hashlib.sha256(
            phase_docs["00"][0]["content"].encode("utf-8")).hexdigest()
        receipts_hash = _hashlib.sha256(json.dumps(
            [{"iteration": 1, "lenses": lenses}],
            ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as root:
            _Path(root, ".sage").mkdir()
            fca.convert_fast(root, cycle_stem=STEM, current_phase=current_phase, actual_risk="L3",
                             fast_review_level="L2", reason="긴급", confirmed_by="sejon",
                             minimum_rounds=1, lenses=lenses,
                             source_phases=(review_snapshot if open_snapshot is None
                                            else open_snapshot),
                             run_id=run_id)
            la.open_loop(root, "L3", run_id=loop_run_id, cycle_stem=STEM, lenses=lenses)
            la.record_round(root, loop_run_id, 1, 0, 0, 0, lens_receipts=lenses,
                            survived_by_severity={"P0": 0, "P1": 0, "P2": 0, "P3": 0})
            la.close_loop(root, loop_run_id, "APPROVED", "CONVERGED", 1)
            fca.record_review(root, run_id, loop_run_id=loop_run_id, actual_risk="L3", rounds=1,
                              lens_receipts_hash=receipts_hash,
                              plan_hash_before_review=plan_hash, result="APPROVED",
                              source_phases_review=review_snapshot)
            fca.close_fast(root, run_id, loop_run_id=loop_run_id, actual_risk="L3",
                           plan_hash_final=plan_hash,
                           report_path=f"plan_docs/06-report/{STEM}.md")
            return (_Path(root, ".sage", "fast_cycle.jsonl").read_text(encoding="utf-8"),
                    _Path(root, ".sage", "loop_audit.jsonl").read_text(encoding="utf-8"))

    def test_a_converted_run_binds_its_reviewed_phase_documents(self):
        """전환 run 의 계획·설계·구현 기록은 Phase 00 밖에 있다.

        이 층은 00 의 `plan_hash` 만 대조했으므로, 리뷰 뒤 03 을 갈아끼워도 증거가 그대로
        통과했다 — fresh Fast 는 composite 문서 하나라 그 자리가 아예 없었고, 전환 run 이
        생기면서 열린 구멍이다. 로컬 close 는 같은 대조를 하지만 이 층은 그 로컬 훅이
        변조됐을 때를 위해 존재한다.
        """
        import hashlib as _hashlib  # noqa: PLC0415

        request = _request()
        docs = request["phase_docs"]
        snapshot = {}
        for phase in ("00", "01", "02", "03", "04"):
            document = docs[phase][0]
            payload = document["content"].encode("utf-8")
            snapshot[phase] = {
                "path": document["path"],
                "sha256": "sha256:" + _hashlib.sha256(payload).hexdigest(),
                "size": len(payload)}
        fast_text, loop_text = self._complete_converted_run(
            review_snapshot=snapshot, phase_docs=docs)
        request["fast_cycle_audit"] = fast_text
        request["loop_audit"] = loop_text
        review = dict(docs["05"][0])
        review["content"] += ("Fast-Run: fc-cc01\nLoop-Run: rl-cc01\n")
        selected = {phase: docs[phase][0] for phase in ("00", "01", "02", "03", "04")}
        selected["05"] = review

        self.assertEqual(ci_authority._fast_evidence_reasons(request, selected, STEM), [])

        drifted = dict(docs["03"][0])
        drifted["content"] += "\n리뷰가 보지 못한 한 줄.\n"
        reasons = ci_authority._fast_evidence_reasons(
            request, {**selected, "03": drifted}, STEM)
        self.assertTrue(any("changed after the converted Fast review" in reason
                            for reason in reasons), reasons)

        size_only = copy.deepcopy(snapshot)
        size_only["03"]["size"] += 999
        reasons = ci_authority._converted_snapshot_reasons(
            {"current_phase": "04", "source_phases_open": snapshot},
            {"source_phases_review": size_only}, selected)
        self.assertTrue(any("changed after the converted Fast review" in reason
                            for reason in reasons), reasons)

    def test_a_converted_snapshot_cannot_shrink_its_own_scope(self):
        """대조 범위를 스냅샷 자신이 정하게 두면 검사를 지우는 것이 곧 통과하는 방법이 된다.

        있는 키만 순회하던 판정에서는 `source_phases_review` 에서 01~04 를 지우고 00 만 남기면
        01~04 는 아무것도 대조되지 않은 채 통과했다 — 리뷰 뒤 03 을 갈아끼우는 것과 같은 결과를
        훨씬 싸게 얻는다. 기대 집합은 opener 의 `current_phase` 가 정한다.
        """
        import hashlib as _hashlib  # noqa: PLC0415

        request = _request()
        docs = request["phase_docs"]
        snapshot = {}
        for phase in ("00", "01", "02", "03", "04"):
            document = docs[phase][0]
            payload = document["content"].encode("utf-8")
            snapshot[phase] = {
                "path": document["path"],
                "sha256": "sha256:" + _hashlib.sha256(payload).hexdigest(),
                "size": len(payload)}
        selected = {phase: docs[phase][0] for phase in ("00", "01", "02", "03", "04")}
        review = dict(docs["05"][0])
        review["content"] += "Fast-Run: fc-cc01\nLoop-Run: rl-cc01\n"
        selected["05"] = review

        for label, review_snapshot, open_snapshot in (
                ("리뷰 스냅샷만 축소", {"00": snapshot["00"]}, snapshot),
                ("opener 스냅샷만 축소", snapshot, {"00": snapshot["00"]}),
                ("양쪽 다 축소", {"00": snapshot["00"]}, {"00": snapshot["00"]})):
            with self.subTest(label):
                reasons = ci_authority._converted_snapshot_reasons(
                    {"current_phase": "04", "source_phases_open": open_snapshot},
                    {"source_phases_review": review_snapshot}, selected)
                self.assertTrue(
                    any("does not cover the recorded source phases" in reason
                        for reason in reasons), (label, reasons))

    def test_a_phase00_conversion_still_binds_every_document_reviewed_later(self):
        """opener는 전환 당시 00만 증언해도 review는 최종 00~04를 모두 증언해야 한다."""
        import hashlib as _hashlib  # noqa: PLC0415

        request = _request()
        docs = request["phase_docs"]
        snapshot = {}
        for phase in ("00", "01", "02", "03", "04"):
            document = docs[phase][0]
            payload = document["content"].encode("utf-8")
            snapshot[phase] = {
                "path": document["path"],
                "sha256": "sha256:" + _hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
            }
        fast_text, loop_text = self._complete_converted_run(
            review_snapshot=snapshot, open_snapshot={"00": snapshot["00"]},
            phase_docs=docs, current_phase="00")
        review = dict(docs["05"][0])
        review["content"] += "Fast-Run: fc-cc01\nLoop-Run: rl-cc01\n"
        selected = {phase: docs[phase][0] for phase in ("00", "01", "02", "03", "04")}
        selected["05"] = review
        reasons = ci_authority._fast_evidence_reasons(
            {**request, "fast_cycle_audit": fast_text, "loop_audit": loop_text},
            selected, STEM)
        self.assertEqual(reasons, [])

        drifted = dict(docs["03"][0])
        drifted["content"] += "\n리뷰 뒤 변경\n"
        reasons = ci_authority._fast_evidence_reasons(
            {**request, "fast_cycle_audit": fast_text, "loop_audit": loop_text},
            {**selected, "03": drifted}, STEM)
        self.assertTrue(any("changed after the converted Fast review" in reason
                            for reason in reasons), reasons)

    def test_an_opener_with_no_readable_current_phase_is_refused_not_crashed(self):
        """기대 집합의 근거가 없으면 판정이 불가능하다 — 진단으로 막지, 예외로 죽지 않는다.

        `current_phase` 가 손질된 opener 에서 그대로 `index()` 를 부르면 authority 전체가
        `ValueError` 로 죽는다. 결과는 차단이지만 무엇이 문제인지 읽을 수 없고, 그 상태는
        "권위가 고장났다" 와 구분되지 않는다.
        """
        for current in (None, "05", "", 4):
            with self.subTest(current=current):
                reasons = ci_authority._converted_snapshot_reasons(
                    {"current_phase": current, "source_phases_open": {}},
                    {"source_phases_review": {"00": {}}}, {})
                self.assertTrue(any("no usable current_phase" in reason for reason in reasons),
                                reasons)

    def _loop_audit_text(self, *, reason="CONVERGED", rounds=2, receipt=None, run_id="rl-aa01",
                         result="APPROVED", cycle_stem=STEM):
        """실제 라이브러리가 쓴 Loop 감사 원문 — 권위는 커밋 트리의 이 텍스트만 본다."""
        import tempfile  # noqa: PLC0415
        from pathlib import Path as _Path  # noqa: PLC0415

        ci_authority._trusted_gate_modules()
        import loop_audit as la  # noqa: PLC0415

        receipt = receipt or {"P0": 0, "P1": 0, "P2": 2, "P3": 0}
        with tempfile.TemporaryDirectory() as root:
            _Path(root, ".sage").mkdir()
            la.open_loop(root, "L3", run_id=run_id, cycle_stem=cycle_stem,
                         lenses=["correctness", "error_handling"])
            for iteration in range(1, rounds + 1):
                la.record_round(root, run_id, iteration, sum(receipt.values()),
                                sum(receipt.values()), 0, survived_by_severity=receipt)
            authorization = None
            if reason == la.EARLY_CLOSE_REASON:
                authorization = {
                    "authorization_reason": "일정 마감", "confirmed_by": "sejon",
                    "completed_rounds": rounds, "configured_max_iterations": 3,
                    "survived_by_severity": receipt, "actual_risk": "L3", "mode": "STANDARD",
                }
            la.close_loop(root, run_id, result, reason, rounds,
                          authorization=authorization)
            return _Path(root, ".sage", "loop_audit.jsonl").read_text(encoding="utf-8")

    _EARLY_MARKERS = ("Review-Assurance: REDUCED_BY_USER_AUTHORIZATION\n"
                      "Review-Close-Reason: USER_AUTHORIZED_EARLY\n"
                      "Review-Rounds: 2 (configured max: 3)\n"
                      "Residual-Findings: P0=0, P1=0, P2=2, P3=0\n")

    def _assurance(self, review_body, loop_text):
        request = _request()
        request["loop_audit"] = loop_text
        core, _binding, _risk = ci_authority._trusted_gate_modules()
        selected = {"05": {"path": "plan_docs/05-expert-review/x.md", "content": review_body}}
        return ci_authority._review_assurance(request, selected, core)

    def test_unread_phase_05_is_unknown_not_standard(self):
        """05 를 못 읽은 상태는 "표준 보증" 이 아니다. 미확인을 STANDARD 로 적으면 조기 종료
        승인이 서버 권위에서 일반 승인과 같은 무게로 남는다.

        05 를 요구하지 않는 위험도가 있으므로 이유(reason)는 만들지 않는다 — 값만 정직해진다.
        """
        core, _binding, _risk = ci_authority._trusted_gate_modules()
        for selected in ({}, {"05": {}}, {"05": {"content": "   \n"}}):
            with self.subTest(selected=selected):
                self.assertEqual(
                    ci_authority._review_assurance(_request(), selected, core), ("UNKNOWN", []))

    def test_the_two_assurance_levels_are_told_apart(self):
        """조기 완료 승인과 일반 승인은 같은 `APPROVED` 토큰을 쓴다.

        권위가 둘을 구분하지 못하면 보증이 낮은 승인이 표준 승인과 같은 무게로 통과한다.
        판정 기준은 문서의 자칭이 아니라 감사가 적은 종료 사유다.
        """
        converged = self._loop_audit_text(reason="CONVERGED")
        early = self._loop_audit_text(reason="USER_AUTHORIZED_EARLY")
        core, _binding, _risk = ci_authority._trusted_gate_modules()
        head = "Loop-Run: rl-aa01\nFinal Status: APPROVED\n"
        for neutral in ("", "Review-Rounds: 3\n",
                        "Residual-Findings: P0=0, P1=0, P2=0, P3=0\n",
                        "Review-Assurance: STANDARD\nReview-Close-Reason: CONVERGED\n"):
            with self.subTest(neutral=neutral):
                self.assertEqual(self._assurance(head + neutral, converged), ("STANDARD", []))
        self.assertEqual(self._assurance(head + self._EARLY_MARKERS, early),
                         (core.REVIEW_ASSURANCE_REDUCED, []))
        level, reasons = self._assurance(
            head + "Review-Assurance: REDUCED_BY_USER_AUTHORIZATION\n", early)
        self.assertEqual(level, "UNKNOWN")
        self.assertNotEqual(reasons, [])

    def test_an_early_close_cannot_pass_as_standard_by_saying_nothing(self):
        """이 층에서 위험한 방향은 자칭이 아니라 **침묵**이다.

        감사가 `USER_AUTHORIZED_EARLY` 로 닫혔는데 05 가 네 표기를 통째로 생략하면, 자칭이 없으니
        문서만 읽는 판정은 STANDARD 를 준다 — 보증이 낮은 승인이 표준 승인과 같은 무게로 남는다.
        로컬 게이트는 같은 상황을 감사와 대조해 막는데, 변조된 로컬 훅을 전제로 존재하는 이 층에만
        그 축이 없었다.
        """
        early = self._loop_audit_text(reason="USER_AUTHORIZED_EARLY")
        level, reasons = self._assurance("Loop-Run: rl-aa01\nFinal Status: APPROVED\n", early)
        self.assertNotEqual(level, "STANDARD")
        self.assertNotEqual(reasons, [])

    def test_a_document_claim_must_match_the_audit_in_both_directions(self):
        """문서와 감사가 어긋나면 어느 쪽도 신뢰할 수 없다 — 라운드 수와 잔여도 같은 축이다."""
        converged = self._loop_audit_text(reason="CONVERGED")
        early = self._loop_audit_text(reason="USER_AUTHORIZED_EARLY")
        head = "Loop-Run: rl-aa01\nFinal Status: APPROVED\n"

        level, reasons = self._assurance(head + self._EARLY_MARKERS, converged)
        self.assertEqual(level, "UNKNOWN")
        self.assertNotEqual(reasons, [])

        drifted = self._EARLY_MARKERS.replace("Review-Rounds: 2", "Review-Rounds: 9")
        level, reasons = self._assurance(head + drifted, early)
        self.assertEqual(level, "UNKNOWN")
        self.assertNotEqual(reasons, [])

        residual = self._EARLY_MARKERS.replace("P2=2", "P2=0")
        level, reasons = self._assurance(head + residual, early)
        self.assertEqual(level, "UNKNOWN")
        self.assertNotEqual(reasons, [])

    def test_an_uncorroborated_claim_is_refused_and_an_unbindable_silence_is_not_standard(self):
        """감사에 결속하지 못하는 두 갈래는 서로 다르게 다뤄야 한다.

        자칭이 있으면 뒷받침 없는 주장이니 막는다. 자칭이 없으면 차단 폭을 넓히지 않되 값은
        `UNKNOWN` 이다 — 확인하지 못한 것을 STANDARD 로 적는 것이 곧 조용한 통과다.
        """
        head = "Loop-Run: rl-aa01\nFinal Status: APPROVED\n"
        level, reasons = self._assurance(head + self._EARLY_MARKERS, "")
        self.assertEqual(level, "UNKNOWN")
        self.assertNotEqual(reasons, [])

        self.assertEqual(self._assurance(head, ""), ("UNKNOWN", []))
        self.assertEqual(self._assurance("Final Status: APPROVED\n",
                                         self._loop_audit_text()), ("UNKNOWN", []))

    def test_l3_early_completion_opt_in_cannot_pass_without_loop_evidence(self):
        """기능을 명시 활성화한 L3는 증거를 지워 일반 승인처럼 보이게 할 수 없다."""
        for enabled_side in ("base_profile", "head_profile"):
            with self.subTest(enabled_side=enabled_side):
                request = _request()
                request[enabled_side]["pdca"] = {
                    "review_loop": {"early_completion": {"enabled": True}}}
                request["loop_audit"] = ""
                result = ci_authority.analyze(request, classifier=_classifier)
                self.assertEqual(result["status"], "BLOCK", result)
                self.assertEqual(result["review_assurance"], "UNKNOWN")
                self.assertTrue(any("review assurance" in reason.lower()
                                    for reason in result["reasons"]), result)

        # 기본 false인 기존 프로젝트에는 없던 감사 요구를 만들지 않는다.
        unchanged = ci_authority.analyze(_request(), classifier=_classifier)
        self.assertEqual(unchanged["status"], "PASS", unchanged)

    def test_a_blocked_or_other_cycle_loop_cannot_be_standard_assurance(self):
        head = "Loop-Run: rl-aa01\nFinal Status: APPROVED\n"
        blocked_audit = self._loop_audit_text(result="BLOCKED", reason="BLOCKED_ARCH")
        for label, audit in (
                ("blocked", blocked_audit),
                ("other cycle", self._loop_audit_text(cycle_stem="other-cycle"))):
            with self.subTest(label=label):
                level, reasons = self._assurance(head, audit)
                self.assertEqual(level, "UNKNOWN")
                self.assertNotEqual(reasons, [])

        request = _request()
        request["base_profile"]["pdca"] = {
            "review_loop": {"early_completion": {"enabled": True}}}
        request["phase_docs"]["05"][0]["content"] += "Loop-Run: rl-aa01\n"
        request["loop_audit"] = blocked_audit
        result = ci_authority.analyze(request, classifier=_classifier)
        self.assertEqual(result["status"], "BLOCK", result)
        self.assertEqual(result["review_assurance"], "UNKNOWN")

    def test_a_tampered_loop_audit_cannot_justify_the_document(self):
        """조작된 감사를 보증 수준의 근거로 쓰면, 감사를 고치는 것이 곧 문서를 정당화하는 통로다."""
        early = self._loop_audit_text(reason="USER_AUTHORIZED_EARLY")
        head = "Loop-Run: rl-aa01\nFinal Status: APPROVED\n"
        tampered = early.replace('"iteration": 2', '"iteration": 7')
        level, reasons = self._assurance(head + self._EARLY_MARKERS, tampered)
        self.assertEqual(level, "UNKNOWN")
        self.assertNotEqual(reasons, [])

    def _done_request(self, mode="enforce", unresolved=False, revision=1,
                      phase05_revision=None, approve_marker="APPROVED"):
        request = _request()
        request["head_profile"]["pdca"] = {
            "approve_marker": approve_marker,
            "base_plan": {"done_criteria_gate": mode}}
        plan = (
            f"Cycle-Stem: `{STEM}`\nRisk Level: L3\n"
            f"Done-Criteria-Revision: {revision}\n\n## 5. Done Criteria\n\n"
            + ("- [ ] protected result\n" if unresolved else "- [x] protected result\n")
        )
        if revision > 1:
            plan += (f"\n## 6. Done Criteria Revision Log\n\n### Revision {revision}\n"
                     "- Changed-At: Phase 05\n- Reason: approval scope changed\n"
                     "- Affected-Phases: 05\n- Summary: rerun independent review\n")
        digest = phase00_text_hash(plan)
        request["phase_docs"]["00"][0]["content"] = plan
        request["phase_docs"]["05"][0]["content"] = request["phase_docs"]["05"][0][
            "content"].replace("Final Status: APPROVED", f"Final Status: {approve_marker}")
        if phase05_revision is not None:
            request["phase_docs"]["05"][0]["content"] += (
                f"Done-Criteria-Revision: {phase05_revision}\n")
        request["phase_docs"]["05"][0]["content"] += (
            f"Loop-Run: rl-authority-done\nPhase00-Hash: {digest}\n")
        ci_authority._trusted_gate_modules()
        import loop_audit
        with tempfile.TemporaryDirectory() as root:
            loop_audit.open_loop(
                root, "L3", run_id="rl-authority-done", cycle_stem=STEM)
            loop_audit.record_round(root, "rl-authority-done", 1, 0, 0, 0)
            loop_audit.close_loop(
                root, "rl-authority-done", "APPROVED", "DRY", 1,
                phase00_hash=digest)
            request["loop_audit"] = Path(loop_audit.audit_path(root)).read_text(encoding="utf-8")
        return request

    def test_done_criteria_authority_honours_custom_approve_marker(self):
        request = self._done_request(approve_marker="SHIPPED")
        result = ci_authority.analyze(request, classifier=_classifier)
        self.assertEqual("PASS", result["status"], result["reasons"])

    def test_done_criteria_enforce_binds_current_plan_review_and_loop(self):
        request = self._done_request()
        result = ci_authority.analyze(request, classifier=_classifier)
        self.assertEqual("PASS", result["status"], result["reasons"])

        request["phase_docs"]["00"][0]["content"] += "\nchanged after approval\n"
        result = ci_authority.analyze(request, classifier=_classifier)
        self.assertEqual("BLOCK", result["status"])
        self.assertTrue(any("Phase00-Hash" in reason for reason in result["reasons"]))

    def test_done_criteria_unresolved_is_block_or_advisory_by_mode(self):
        enforced = ci_authority.analyze(
            self._done_request(unresolved=True), classifier=_classifier)
        self.assertEqual("BLOCK", enforced["status"])
        self.assertTrue(any("unresolved" in reason for reason in enforced["reasons"]))

        advisory = ci_authority.analyze(
            self._done_request(mode="advisory", unresolved=True), classifier=_classifier)
        self.assertEqual("PASS", advisory["status"], advisory["reasons"])
        self.assertTrue(any("unresolved" in item for item in advisory["advisories"]))

    def test_done_criteria_authority_requires_affected_phase05_current_revision(self):
        stale = ci_authority.analyze(
            self._done_request(revision=2, phase05_revision=1), classifier=_classifier)
        self.assertEqual("BLOCK", stale["status"])
        self.assertTrue(any("Phase 05" in reason and "revision" in reason
                            for reason in stale["reasons"]), stale["reasons"])

        current = ci_authority.analyze(
            self._done_request(revision=2, phase05_revision=2), classifier=_classifier)
        self.assertEqual("PASS", current["status"], current["reasons"])

    def test_protected_adapter_materializes_domain_l0_exclusions(self):
        profile = {
            "risk": {
                "l0_pass_globs": ["**/*.png"],
                "domains": [{
                    "id": "game", "risk_level": "L3",
                    "path_globs": ["assets/game/**"],
                    "protocol_pointer": "sage/game.md",
                }],
            }
        }
        tree = {"sage/project-profile.yaml": {
            "mode": "100644", "kind": "blob", "oid": "a" * 40,
        }}
        raw = yaml.safe_dump(profile).encode("utf-8")
        with mock.patch.object(authority, "_blob", return_value=raw):
            compiled = authority._profile("/unused", tree, "head")
        self.assertEqual(compiled["risk"]["l0_exclude_globs"], ["assets/game/**"])
        self.assertEqual(compiled["risk"]["l3_filename_globs"], ["assets/game/**"])

    def test_base_head_policy_uses_max_and_l3_evidence(self):
        result = ci_authority.analyze(_request(), classifier=_classifier)
        self.assertEqual("PASS", result["status"])
        self.assertEqual("L3", result["risk"])
        self.assertEqual("L3", result["base_risk"])
        self.assertEqual("L1", result["head_risk"])
        self.assertEqual(set(("00", "01", "02", "03", "04", "05")),
                         set(result["selected_phases"]))

    def test_risk_declarations_share_gate_core_normalization_and_unknown_floor(self):
        cases = (
            ("**Risk Level:** L3", "L3"),
            # plain-text near-miss가 있으면 낮은 선언을 authoritative tier로 채택하지 않는다.
            ("Residual risk: acceptable", "L3"),
            ("Risk Level 결정: L3", "L3"),
            ("Risk Level: L0", "L3"),
        )
        for declaration, expected in cases:
            with self.subTest(declaration=declaration):
                request = _request(base_risk="L1", head_risk="L1")
                request["phase_docs"] = _phase_docs(declared="L1")
                request["phase_docs"]["00"][0]["content"] += declaration + "\n"

                result = ci_authority.analyze(request, classifier=_classifier)

                self.assertEqual("PASS", result["status"], result["reasons"])
                self.assertEqual(expected, result["risk"])

    def test_declared_l3_is_not_lost_when_other_phase_is_missing(self):
        request = _request(base_risk="L1", head_risk="L1")
        request["phase_docs"]["02"] = []
        result = ci_authority.analyze(request, classifier=_classifier)
        self.assertEqual("BLOCK", result["status"])
        self.assertEqual("L3", result["risk"])
        self.assertTrue(any("Phase 02" in reason for reason in result["reasons"]))

    def test_deleted_content_and_rename_source_are_classified(self):
        profile = {
            "risk": {
                "desktop_block_glob": "",
                "l0_pass_globs": [],
                "l1_path_globs": ["**"],
                "l2_path_globs": [],
                "l2_content_keywords": [],
                "l3_filename_globs": ["secrets/**"],
                "l3_content_keywords": ["PRIVATE_TOKEN"],
            }
        }
        deleted = _request()
        deleted["base_profile"] = deleted["head_profile"] = profile
        deleted["changes"] = [_change(path="src/old.py", base="PRIVATE_TOKEN = 1", head="", op="delete")]
        self.assertEqual("L3", ci_authority.analyze(deleted)["risk"])

        renamed = _request()
        renamed["base_profile"] = renamed["head_profile"] = profile
        renamed["changes"] = [_change(path="docs/public.md", old_path="secrets/key.py",
                                             base="safe", head="safe", op="rename")]
        self.assertEqual("L3", ci_authority.analyze(renamed)["risk"])

        removed_from_modify = _request()
        removed_from_modify["base_profile"] = removed_from_modify["head_profile"] = profile
        removed_from_modify["changes"] = [
            _change(path="src/old.py", base="PRIVATE_TOKEN = 1", head="value = 1", op="modify")
        ]
        self.assertEqual("L3", ci_authority.analyze(removed_from_modify)["risk"])

    def test_acceptance_and_final_review_fail_closed(self):
        for status04, status05 in (("NOT TESTED", "APPROVED"), ("SKIPPED", "APPROVED"),
                                   ("PASS", "FAIL")):
            with self.subTest(status04=status04, status05=status05):
                request = _request()
                request["phase_docs"] = _phase_docs(status04=status04, status05=status05)
                result = ci_authority.analyze(request, classifier=_classifier)
                self.assertEqual("BLOCK", result["status"])

    def test_reasoned_na_is_canonical_resolved_evidence(self):
        request = _request()
        request["phase_docs"] = _phase_docs(status04="N/A")
        request["phase_docs"]["04"][0]["content"] = request["phase_docs"]["04"][0]["content"].replace(
            "deterministic proof", "not applicable because no production endpoint exists")
        self.assertEqual("PASS", ci_authority.analyze(request, classifier=_classifier)["status"])

    def test_local_override_and_waiver_inputs_have_no_effect(self):
        request = _request()
        request["local_override"] = {"risk": "L0", "allow": True}
        request["acceptance_waiver"] = {"AC1": "PASS"}
        request["phase_docs"] = _phase_docs(status04="NOT TESTED")
        result = ci_authority.analyze(request, classifier=_classifier)
        self.assertEqual("BLOCK", result["status"])
        self.assertEqual("L3", result["risk"])

    def test_attestation_exact_binding_tamper_expiry_and_missing_key(self):
        request = _request()
        analyzed = ci_authority.analyze(request, classifier=_classifier)
        now = 2_000_000_000
        token = ci_authority.issue_attestation(_claims(analyzed, now), KEY)
        request.update(attestation_token=token, attestation_key=KEY, now=now)
        passed = ci_authority.evaluate(request, classifier=_classifier)
        self.assertEqual("PASS", passed["status"])

        for field, value in (("repository", "owner/other"), ("head_sha", "3" * 40),
                             ("expected_issuer", "other-ci")):
            with self.subTest(field=field):
                changed = copy.deepcopy(request)
                changed[field] = value
                self.assertEqual("BLOCK", ci_authority.evaluate(changed, classifier=_classifier)["status"])

        expired = copy.deepcopy(request)
        expired["now"] = now + 400
        self.assertEqual("BLOCK", ci_authority.evaluate(expired, classifier=_classifier)["status"])
        missing = copy.deepcopy(request)
        missing["attestation_key"] = b""
        self.assertEqual("BLOCK", ci_authority.evaluate(missing, classifier=_classifier)["status"])

        payload, signature = token.split(".")
        forged = copy.deepcopy(request)
        forged["attestation_token"] = payload + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
        self.assertEqual("BLOCK", ci_authority.evaluate(forged, classifier=_classifier)["status"])

    def test_attestation_rejects_short_key_excess_ttl_and_noncanonical_payload(self):
        result = ci_authority.analyze(_request(), classifier=_classifier)
        claims = _claims(result, 2_000_000_000)
        with self.assertRaises(ci_authority.AuthorityError):
            ci_authority.issue_attestation(claims, b"short")
        claims["expires_at"] = claims["issued_at"] + 3601
        with self.assertRaises(ci_authority.AuthorityError):
            ci_authority.issue_attestation(claims, KEY)

    def test_structured_diff_rejects_unknown_operation_and_invalid_oid(self):
        change = _change()
        change["op"] = "chmod"
        with self.assertRaises(ci_authority.AuthorityError):
            ci_authority.diff_digest([change])
        change["base_oid"] = "a" * 40
        change["path"] = "src/../escape.py"
        with self.assertRaises(ci_authority.AuthorityError):
            ci_authority.diff_digest([change])
        added = _change(path="src/new.py", base="", head="new", op="add", old_path="")
        added["old_path"] = "src/old.py"
        with self.assertRaises(ci_authority.AuthorityError):
            ci_authority.diff_digest([added])
        change["op"] = "modify"
        change["base_oid"] = "not-a-full-oid"
        with self.assertRaises(ci_authority.AuthorityError):
            ci_authority.diff_digest([change])


class GitAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source_root = Path(__file__).resolve().parents[4]
        self.profile = yaml.safe_load((self.source_root / "templates/project-profile.yaml").read_text())
        self.profile["project"]["name"] = "authority-fixture"
        self.profile["risk"]["l1_path_globs"] = ["src/**"]
        self.profile["risk"]["l3_filename_globs"] = ["src/**"]
        self._git("init", "-q")
        self._git("config", "user.name", "SAGE Test")
        self._git("config", "user.email", "sage@example.invalid")
        (self.root / "sage").mkdir()
        (self.root / "src").mkdir()
        self._write_profile(self.profile)
        (self.root / "src/security.py").write_text(BASE_SOURCE)
        self._git("add", ".")
        self._git("commit", "-qm", "base")
        self.base = self._git("rev-parse", "HEAD").strip()

        head_profile = copy.deepcopy(self.profile)
        head_profile["risk"]["l3_filename_globs"] = []
        self._write_profile(head_profile)
        (self.root / "src/security.py").write_text(HEAD_SOURCE)
        self._write_phases()
        self._git("add", ".")
        self._git("commit", "-qm", "head")
        self.head = self._git("rev-parse", "HEAD").strip()

    def tearDown(self):
        self.tmp.cleanup()

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, text=True, check=True,
                              stdout=subprocess.PIPE).stdout

    def _write_profile(self, profile):
        (self.root / "sage/project-profile.yaml").write_text(
            yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    def _write_phases(self):
        for phase, folder in (("00", "00-base_plan"), ("01", "01-plan"), ("02", "02-design"),
                              ("03", "03-implementation"), ("04", "04-analyze"),
                              ("05", "05-expert-review")):
            target = self.root / "plan_docs" / folder
            target.mkdir(parents=True)
            body = f"Cycle-Stem: `{STEM}`\nRisk Level: L3\n"
            if phase == "01":
                body += "\n## Acceptance Matrix\n| ID | Required? |\n|---|:---:|\n| AC1 | yes |\n"
            if phase == "04":
                body += "\n## Acceptance Evidence\n| ID | Status | Evidence |\n|---|:---:|---|\n| AC1 | PASS | fixture |\n"
            if phase == "05":
                body += "\nFinal Status: APPROVED\n"
            (target / f"{STEM}.md").write_text(body, encoding="utf-8")

    def _args(self, action, extra=None):
        return ["authority", action, "--root", str(self.root), "--base", self.base,
                "--head", self.head, "--repository", "owner/repo", "--cycle-stem", STEM,
                "--issuer", "protected-ci", *(extra or [])]

    def _invoke(self, args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli_main(args)
        return code, output.getvalue().strip()

    def test_inspect_reads_git_objects_and_uses_base_policy(self):
        code, output = self._invoke(self._args("inspect"))
        result = json.loads(output)
        self.assertEqual(0, code, result)
        self.assertEqual("PASS", result["status"])
        self.assertEqual("L3", result["risk"])
        self.assertEqual("L3", result["base_risk"])
        self.assertEqual("L1", result["head_risk"])

    def test_gate_requires_secret_and_exact_token(self):
        code, output = self._invoke(self._args("inspect"))
        self.assertEqual(0, code)
        inspected = json.loads(output)
        claims = {
            "version": 1, "issuer": "protected-ci", "repository": "owner/repo",
            "base_sha": self.base, "head_sha": self.head,
            "diff_sha256": inspected["diff_sha256"], "cycle_stem": STEM,
            "risk": "L3", "reviewer": "fixture", "verdict": "APPROVED",
            "nonce": "fixture-0123456789abcdef", "issued_at": int(time.time()) - 1,
            "expires_at": int(time.time()) + 300,
        }
        token_path = self.root / "attestation.token"
        token_path.write_text(ci_authority.issue_attestation(claims, KEY), encoding="utf-8")
        args = self._args("gate", ["--attestation-file", str(token_path)])
        with mock.patch.dict(os.environ, {}, clear=True):
            code, output = self._invoke(args)
        self.assertEqual(2, code)
        self.assertEqual("BLOCK", json.loads(output)["status"])
        with mock.patch.dict(os.environ, {"SAGE_ATTESTATION_KEY": KEY.decode()}, clear=False):
            code, output = self._invoke(args)
        self.assertEqual(0, code, output)
        self.assertEqual("PASS", json.loads(output)["status"])

    def test_head_tree_code_is_never_executed(self):
        marker = self.root / "executed"
        (self.root / "src/security.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n", encoding="utf-8")
        self._git("add", "src/security.py")
        self._git("commit", "-qm", "malicious-head")
        self.head = self._git("rev-parse", "HEAD").strip()
        self._invoke(self._args("inspect"))
        self.assertFalse(marker.exists())

    def test_head_phase_symlink_is_not_accepted_as_authority_evidence(self):
        review = self.root / "plan_docs/05-expert-review" / f"{STEM}.md"
        review.unlink()
        review.symlink_to(f"Cycle-Stem: `{STEM}`\nFinal Status: APPROVED\n")
        self._git("add", "plan_docs/05-expert-review")
        self._git("commit", "-qm", "replace review evidence with symlink")
        self.head = self._git("rev-parse", "HEAD").strip()

        with self.assertRaisesRegex(authority.AuthorityCliError, "regular git file"):
            authority._request(mock.Mock(
                root=str(self.root), base=self.base, head=self.head,
                repository="owner/repo", cycle_stem=STEM, issuer="protected-ci",
            ))

    def test_adapter_materializes_deleted_base_blob(self):
        (self.root / "src/security.py").unlink()
        self._git("add", "-A")
        self._git("commit", "-qm", "delete source")
        self.head = self._git("rev-parse", "HEAD").strip()
        args = mock.Mock(root=str(self.root), base=self.base, head=self.head,
                         repository="owner/repo", cycle_stem=STEM, issuer="protected-ci")
        request = authority._request(args)
        deleted = next(change for change in request["changes"] if change["path"] == "src/security.py")
        self.assertEqual("delete", deleted["op"])
        self.assertEqual(BASE_SOURCE, deleted["base_content"])
        self.assertEqual("", deleted["head_content"])

    def test_adapter_materializes_rename_source_and_destination(self):
        (self.root / "docs").mkdir()
        (self.root / "src/security.py").write_text(BASE_SOURCE, encoding="utf-8")
        self._git("add", "src/security.py")
        self._git("mv", "src/security.py", "docs/security.py")
        self._git("commit", "-qm", "rename source")
        self.head = self._git("rev-parse", "HEAD").strip()
        args = mock.Mock(root=str(self.root), base=self.base, head=self.head,
                         repository="owner/repo", cycle_stem=STEM, issuer="protected-ci")
        request = authority._request(args)
        renamed = next(change for change in request["changes"] if change["path"] == "docs/security.py")
        self.assertEqual("rename", renamed["op"])
        self.assertEqual("src/security.py", renamed["old_path"])
        self.assertEqual(BASE_SOURCE, renamed["base_content"])
        self.assertEqual(BASE_SOURCE, renamed["head_content"])

    def test_full_sha_and_regular_token_file_are_mandatory(self):
        args = self._args("inspect")
        args[args.index("--head") + 1] = "HEAD"
        code, output = self._invoke(args)
        self.assertEqual(2, code)
        self.assertIn("full lowercase commit SHA", output)

        target = self.root / "real.token"
        target.write_text("invalid")
        link = self.root / "link.token"
        link.symlink_to(target)
        with mock.patch.dict(os.environ, {"SAGE_ATTESTATION_KEY": KEY.decode()}, clear=False):
            code, output = self._invoke(self._args("gate", ["--attestation-file", str(link)]))
        self.assertEqual(2, code)
        self.assertIn("non-symlink regular file", output)


if __name__ == "__main__":
    unittest.main()
