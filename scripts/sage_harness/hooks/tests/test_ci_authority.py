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
