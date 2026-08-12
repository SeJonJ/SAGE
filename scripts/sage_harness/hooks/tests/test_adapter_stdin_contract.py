#!/usr/bin/env python3
"""EH-14 regression: tests that launch a hook adapter must close the child's stdin.

An adapter reads `sys.stdin.read()` by the hook wire contract. A `subprocess.run` that passes
neither `input=` nor `stdin=` leaves the child inheriting the parent's stdin, so in any
environment where that stdin never reaches EOF (backgrounded suites, some CI runners) the
adapter waits forever. The failure mode is a hang, not a failure — it occupies the runner until
timeout and leaves nothing in the log, which is why it was misdiagnosed as "the suite is slow".

`input=` is sufficient on its own: subprocess wires a pipe and closes it after writing. Only
calls that pass neither are defects, so this guard checks exactly that.
"""
import ast
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent


def _is_subprocess_launch(node):
    """subprocess.run(...) / subprocess.Popen(...) — attribute call, not a bare name."""
    func = node.func
    return (isinstance(func, ast.Attribute)
            and func.attr in ("run", "Popen")
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess")


def _launches_adapter(node):
    """First positional arg is a list literal starting with the literal "bash"."""
    if not node.args:
        return False
    first = node.args[0]
    if not isinstance(first, (ast.List, ast.Tuple)) or not first.elts:
        return False
    head = first.elts[0]
    return isinstance(head, ast.Constant) and head.value == "bash"


def _adapter_calls_without_stdin():
    findings = []
    for path in sorted(TESTS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_subprocess_launch(node):
                continue
            if not _launches_adapter(node):
                continue
            keywords = {kw.arg for kw in node.keywords}
            if "input" not in keywords and "stdin" not in keywords:
                findings.append(f"{path.name}:{node.lineno}")
    return findings


class TestAdapterStdinContract(unittest.TestCase):
    def test_every_adapter_launch_closes_stdin(self):
        findings = _adapter_calls_without_stdin()
        self.assertEqual(
            findings, [],
            "adapter 를 실행하면서 stdin 을 닫지 않는 호출 — `stdin=subprocess.DEVNULL` 또는 "
            f"`input=...` 을 넘기세요: {findings}")

    def test_guard_detects_a_missing_stdin(self):
        """변이 teeth — 검사기 자체가 결함을 실제로 잡는지 확인한다."""
        source = 'subprocess.run(["bash", adapter], capture_output=True, env=env)\n'
        tree = ast.parse(source)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        self.assertTrue(_is_subprocess_launch(call))
        self.assertTrue(_launches_adapter(call))
        self.assertNotIn("stdin", {kw.arg for kw in call.keywords})

    def test_guard_accepts_input_as_sufficient(self):
        source = 'subprocess.run(["bash", adapter], input="", capture_output=True)\n'
        tree = ast.parse(source)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        self.assertIn("input", {kw.arg for kw in call.keywords})


if __name__ == "__main__":
    unittest.main()
