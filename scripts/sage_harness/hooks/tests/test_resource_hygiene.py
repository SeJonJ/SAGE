#!/usr/bin/env python3
"""Every `open()` in the repository releases its handle.

`open(p).read()` leaks the file object until the garbage collector happens to reach it, and
CPython emits a ResourceWarning when it does. That warning is not a usable gate: it fires from
__del__ at a moment nobody controls, `-W error::ResourceWarning` still exits 0 because the
exception is raised in a context that only prints "Exception ignored", and under some
interpreter shutdown orders it never prints at all. A guard built on observing the warning
therefore reports success when it sees nothing — which is exactly the state a leak produces.

So this checks the source instead. An `open()` call is accounted for when it is the context
expression of a `with`, or when its result is closed immediately. Anything else is a leak
unless it appears in ALLOWLIST with the reason it must hold a handle open.
"""
import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]

# Directory fragments that are not repository-owned source: build output, vendored copies,
# and detached worktrees each carry their own history and are not this suite's to police.
SKIP_PARTS = ("build", "dist", ".venv", "__pycache__", ".git", "worktrees", "node_modules")

# "<repo-relative path>:<line>" -> reason the handle must outlive the call.
ALLOWLIST: dict[str, str] = {}


def _source_files():
    for path in sorted(REPO.rglob("*.py")):
        if any(part in SKIP_PARTS for part in path.relative_to(REPO).parts):
            continue
        yield path


def _is_open(node) -> bool:
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open")


def leaks_in(source: str, filename: str) -> list[str]:
    """Locations of open() calls whose handle is never released."""
    tree = ast.parse(source, filename=filename)

    managed = {id(item.context_expr)
               for node in ast.walk(tree)
               for item in getattr(node, "items", [])
               if _is_open(item.context_expr)}

    # open(...).close() releases immediately; open(...).read() does not.
    closed = {id(node.func.value)
              for node in ast.walk(tree)
              if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute)
              and node.func.attr == "close"
              and _is_open(node.func.value)}

    return [f"{filename}:{node.lineno}"
            for node in ast.walk(tree)
            if _is_open(node) and id(node) not in managed and id(node) not in closed]


class TestResourceHygiene(unittest.TestCase):
    def test_no_unreleased_open_handles(self):
        found = []
        for path in _source_files():
            rel = str(path.relative_to(REPO))
            found += leaks_in(path.read_text(encoding="utf-8"), rel)
        leaks = sorted(set(found) - set(ALLOWLIST))
        self.assertEqual(
            leaks, [],
            "open() calls that never release the handle — use `with open(...)`, "
            f"Path.read_text/write_text, or add an ALLOWLIST reason: {leaks}")

    def test_no_stale_allowlist_entries(self):
        """An allowlist that outlives its site silently re-opens the hole it documented."""
        live = set()
        for path in _source_files():
            rel = str(path.relative_to(REPO))
            live.update(leaks_in(path.read_text(encoding="utf-8"), rel))
        stale = sorted(set(ALLOWLIST) - live)
        self.assertEqual(stale, [], f"ALLOWLIST entries no longer correspond to a site: {stale}")

    def test_every_allowlist_entry_states_a_reason(self):
        blank = sorted(loc for loc, reason in ALLOWLIST.items() if not reason.strip())
        self.assertEqual(blank, [], f"allowlisted without a reason: {blank}")

    def test_guard_flags_a_leaked_read(self):
        """Mutation teeth — the checker must actually catch the pattern it was built for."""
        self.assertEqual(leaks_in('text = open(p, encoding="utf-8").read()\n', "s.py"), ["s.py:1"])
        self.assertEqual(leaks_in('open(p, "w").write(body)\n', "s.py"), ["s.py:1"])
        self.assertEqual(leaks_in('cfg = yaml.safe_load(open(p))\n', "s.py"), ["s.py:1"])

    def test_guard_accepts_released_handles(self):
        self.assertEqual(leaks_in('with open(p) as f:\n    body = f.read()\n', "s.py"), [])
        self.assertEqual(leaks_in('open(marker, "w").close()\n', "s.py"), [])
        self.assertEqual(leaks_in('body = Path(p).read_text(encoding="utf-8")\n', "s.py"), [])

    def test_scan_covers_both_engine_and_harness_source(self):
        """A scan rooted at the wrong directory would pass by finding nothing."""
        scanned = {str(p.relative_to(REPO)) for p in _source_files()}
        self.assertIn("sage/cli.py", scanned)
        self.assertIn("scripts/sage_harness/hooks/tests/test_resource_hygiene.py", scanned)
        self.assertGreater(len(scanned), 100)


if __name__ == "__main__":
    unittest.main()
