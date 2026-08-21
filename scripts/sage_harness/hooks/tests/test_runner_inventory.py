#!/usr/bin/env python3
"""Runner completeness: every test file on disk runs, or is excluded on the record.

A test that exists but is never invoked reports nothing. It passes review as "covered" while
guarding an empty room, and its rot is invisible until someone runs it by hand years later.
That is how `test_build_identity.py` and `test_profile_compile.py` sat outside `run-all.sh`:
both pass, so nothing ever complained.

Absence is not a safe direction here, so this guard is fail-closed in both directions. A new
test file must be wired into the runner or listed in EXCLUSIONS with a concrete reason; a
runner line must point at a file that exists; and an exclusion must name a file that is still
there, so the list cannot accumulate stale entries that quietly re-open the hole.
"""
import re
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
RUNNER = TESTS_DIR / "run-all.sh"

# Test files deliberately outside the official suite, each with the reason it cannot run there.
# An entry whose file no longer exists is itself a failure — see test_no_stale_exclusions.
EXCLUSIONS: dict[str, str] = {}

# The runner invokes each test as `python3 "$HERE/<name>.py"`. Keying on that exact form keeps
# a filename mentioned only in a comment or an echo banner from counting as wired.
_INVOCATION = re.compile(r'\$HERE/(test_[A-Za-z0-9_]+\.py)')


def _files_on_disk() -> set[str]:
    return {p.name for p in TESTS_DIR.glob("test_*.py")}


def _files_in_runner() -> set[str]:
    return set(_INVOCATION.findall(RUNNER.read_text(encoding="utf-8")))


class TestRunnerInventory(unittest.TestCase):
    def test_every_test_file_runs_or_is_excluded(self):
        unaccounted = sorted(_files_on_disk() - _files_in_runner() - set(EXCLUSIONS))
        self.assertEqual(
            unaccounted, [],
            "test files exist but the official runner never invokes them. Add them to "
            f"run-all.sh, or to EXCLUSIONS with a reason: {unaccounted}")

    def test_runner_references_resolve(self):
        dangling = sorted(_files_in_runner() - _files_on_disk())
        self.assertEqual(
            dangling, [],
            f"run-all.sh invokes test files that do not exist: {dangling}")

    def test_exclusions_do_not_overlap_the_runner(self):
        both = sorted(_files_in_runner() & set(EXCLUSIONS))
        self.assertEqual(
            both, [],
            "these files are both invoked by the runner and listed as excluded, so the "
            f"exclusion is misleading: {both}")

    def test_no_stale_exclusions(self):
        stale = sorted(set(EXCLUSIONS) - _files_on_disk())
        self.assertEqual(
            stale, [],
            f"EXCLUSIONS names test files that no longer exist: {stale}")

    def test_every_exclusion_states_a_reason(self):
        blank = sorted(name for name, reason in EXCLUSIONS.items() if not reason.strip())
        self.assertEqual(
            blank, [],
            f"an exclusion without a concrete reason is not a decision on the record: {blank}")

    def test_this_guard_is_itself_wired(self):
        """A completeness check that never runs is the exact hole it exists to close."""
        self.assertIn(Path(__file__).name, _files_in_runner())

    def test_parser_ignores_mentions_outside_an_invocation(self):
        """Mutation teeth — a banner or comment naming a file must not count as wired."""
        sample = (
            'echo "### 9. test_ghost.py coverage"\n'
            '# test_commented_out.py is disabled\n'
            'python3 "$HERE/test_real.py" || rc=1\n'
        )
        self.assertEqual(set(_INVOCATION.findall(sample)), {"test_real.py"})


if __name__ == "__main__":
    unittest.main()
