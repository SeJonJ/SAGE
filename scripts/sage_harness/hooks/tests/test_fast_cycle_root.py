#!/usr/bin/env python3
"""Fast CLI 의 profile 검증 root 정합.

`sage fast-cycle` 은 `_root(args)` 로 프로젝트 root 를 이미 확정한 뒤 `_profile(root)` 를 부른다.
그런데 `_profile` 이 검증만은 SAGE 번들 root 로 하고 있어서, 프로젝트 상대 `governance_docs` 가
실재해도 `profile invalid` 로 거부된다 — 정상 profile 이 Fast Cycle 진입을 막는다.

`sage validate` 와 `sage fast-cycle open` 은 같은 profile·root 에 같은 판정을 내야 한다.
"""

import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, REPO)

from sage import _resources  # noqa: E402
from sage.commands import fast_cycle  # noqa: E402
from sage.profile_layers import load_profile_layers  # noqa: E402
from sage.profile_validate import severity_of, validate_profile  # noqa: E402

TEMPLATE = os.path.join(REPO, "templates", "project-profile.yaml")
DOC = "docs/agent/output-contract.md"


def make_project(with_doc=True):
    """프로젝트 상대 governance_docs 를 가진 소비 프로젝트 형태의 임시 트리."""
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "sage"))
    os.makedirs(os.path.join(root, os.path.dirname(DOC)))
    if with_doc:
        with open(os.path.join(root, DOC), "w", encoding="utf-8") as handle:
            handle.write("# output contract\n")
    path = os.path.join(root, "sage", "project-profile.yaml")
    shutil.copy(TEMPLATE, path)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    text = text.replace(
        "governance_docs: []",
        f'governance_docs: [{{ doc: "{DOC}", label: "output contract" }}]')
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return root


def profile_fails(root, validate_root):
    layers = load_profile_layers(os.path.join(root, "sage", "project-profile.yaml"))
    return [str(message) for severity, message in validate_profile(layers.effective, validate_root)
            if severity == "FAIL"]


class TestValidateAndFastAgree(unittest.TestCase):
    def setUp(self):
        self.root = make_project()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_project_relative_governance_doc_validates_against_the_project_root(self):
        self.assertEqual(profile_fails(self.root, self.root), [])

    def test_bundle_root_is_the_wrong_yardstick_for_a_project_relative_doc(self):
        # 결함의 방향을 고정한다 — 번들 root 로 재면 실재하는 문서가 부재로 판정된다.
        self.assertNotEqual(profile_fails(self.root, _resources.sage_root()), [])

    def test_fast_cycle_accepts_the_profile_that_validate_accepts(self):
        self.assertEqual(profile_fails(self.root, self.root), [])
        # 이 호출이 ValueError 를 내면 Fast Cycle 진입이 막힌 상태다.
        effective = fast_cycle._profile(self.root)
        self.assertIsInstance(effective, dict)

    def test_missing_governance_doc_fails_on_both_paths(self):
        broken = make_project(with_doc=False)
        self.addCleanup(shutil.rmtree, broken, True)
        self.assertNotEqual(profile_fails(broken, broken), [])
        with self.assertRaises(ValueError):
            fast_cycle._profile(broken)

    def test_explicit_root_selects_that_project_not_the_cwd(self):
        other = make_project()
        self.addCleanup(shutil.rmtree, other, True)
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            chosen = fast_cycle._root(SimpleNamespace(root=other))
        finally:
            os.chdir(cwd)
        self.assertEqual(os.path.realpath(chosen), os.path.realpath(other))
        self.assertIsInstance(fast_cycle._profile(chosen), dict)

    def test_severity_agreement_between_validate_and_fast_entry(self):
        """같은 profile 에 대해 두 경로의 판정이 갈리지 않는다."""
        for root, expect_ok in ((self.root, True), (make_project(with_doc=False), False)):
            self.addCleanup(shutil.rmtree, root, True)
            layers = load_profile_layers(os.path.join(root, "sage", "project-profile.yaml"))
            validate_ok = severity_of(validate_profile(layers.effective, root)) != "FAIL"
            try:
                fast_cycle._profile(root)
                fast_ok = True
            except ValueError:
                fast_ok = False
            self.assertEqual(validate_ok, expect_ok, root)
            self.assertEqual(validate_ok, fast_ok, root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
