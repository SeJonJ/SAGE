#!/usr/bin/env python3
"""사용자 표시 literal 인벤토리 생성 — catalog 이관의 선행 기록.

이관을 먼저 하면 무엇을 옮겼고 무엇이 남았는지 세는 근거가 코드 자체밖에 없어진다. 그러면
"안 옮긴 것"과 "옮길 필요가 없던 것"이 구분되지 않고, 남은 개수가 0이 아닌 이유를 매번 다시
판별해야 한다. 그래서 옮기기 전에 대상과 그 성질을 먼저 고정한다.

`key` 는 비워 둔다. 의미 기반 이름은 사람이 붙이는 것이고, 기계가 만든 `cli.doctor.17` 같은
이름은 한 번 박히면 catalog 전체를 읽기 어렵게 만든다. 이관하면서 채운다.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import string
import sys
from pathlib import Path

HANGUL = re.compile(r"[가-힣]")
COMMANDS_REL = ("sage", "commands")
HELP_KEYWORDS = ("help", "description", "epilog")


def _placeholders(text: str) -> list[str]:
    try:
        return sorted({n for _, n, _, _ in string.Formatter().parse(text) if n})
    except ValueError:
        return []


def _enclosing(tree: ast.AST) -> dict[int, str]:
    """node id -> 그 노드를 감싼 최상위 함수 이름."""
    owner: dict[int, str] = {}

    def walk(node, name):
        for child in ast.iter_child_nodes(node):
            child_name = child.name if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef)) else name
            owner[id(child)] = child_name
            walk(child, child_name)

    walk(tree, "<module>")
    return owner


def _channel(call: ast.Call) -> str:
    """print(file=sys.stderr) 만 stderr. 나머지는 stdout."""
    for kw in call.keywords:
        if kw.arg == "file":
            segment = ast.dump(kw.value)
            return "stderr" if "stderr" in segment else "stdout"
    return "stdout"


def _korean_literals(node: ast.AST, source: str) -> list[tuple[str, bool]]:
    """(텍스트, 보간 여부). f-string 은 조각이 아니라 통째로 하나의 문장이다."""
    found: list[tuple[str, bool]] = []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if HANGUL.search(node.value):
            found.append((node.value, False))
    elif isinstance(node, ast.JoinedStr):
        segment = ast.get_source_segment(source, node) or ""
        if HANGUL.search(segment):
            found.append((segment, True))
    elif isinstance(node, (ast.BinOp, ast.Call)):
        for child in ast.iter_child_nodes(node):
            found.extend(_korean_literals(child, source))
    return found


def collect(repo_root: str) -> list[dict]:
    entries: list[dict] = []
    commands_dir = os.path.join(repo_root, *COMMANDS_REL)
    for name in sorted(os.listdir(commands_dir)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(commands_dir, name)
        source = Path(path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=path)
        owner = _enclosing(tree)
        module = name[:-3]
        rel = os.path.join(*COMMANDS_REL, name)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            symbol = owner.get(id(node), "<module>")

            for kw in node.keywords:
                if kw.arg not in HELP_KEYWORDS:
                    continue
                if not (isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, str)
                        and HANGUL.search(kw.value.value)):
                    continue
                entries.append({
                    "id": f"{module}:{node.lineno}:{kw.arg}",
                    "domain": "cli",
                    "key": None,
                    "source_file": rel,
                    "source_symbol": symbol,
                    "source_line": node.lineno,
                    "channel": "stdout",
                    "exit_contract": "unchanged",
                    "format": "static",
                    "placeholders": _placeholders(kw.value.value),
                    "machine_consumer": None,
                    "classification": f"argparse.{kw.arg}",
                    "text": kw.value.value,
                    "required_tests": ["help_tree"],
                })

            if isinstance(node.func, ast.Name) and node.func.id == "print":
                channel = _channel(node)
                for index, argument in enumerate(node.args):
                    for text, interpolated in _korean_literals(argument, source):
                        entries.append({
                            "id": f"{module}:{node.lineno}:print{index}",
                            "domain": "cli",
                            "key": None,
                            "source_file": rel,
                            "source_symbol": symbol,
                            "source_line": node.lineno,
                            "channel": channel,
                            "exit_contract": "unchanged",
                            "format": "interpolated" if interpolated else "static",
                            "placeholders": _placeholders(text) if not interpolated else [],
                            "machine_consumer": None,
                            "classification": "command_output",
                            "text": text,
                            "required_tests": ["ko_parity", "en_snapshot", "no_leakage"],
                        })
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default=os.path.join("docs", "sage_harness",
                                                      "localization-inventory.json"))
    parser.add_argument("--check", action="store_true",
                        help="파일을 쓰지 않고 현재 파일과 일치하는지만 검사")
    args = parser.parse_args()

    entries = collect(args.root)
    document = {
        "schema_version": 1,
        "domain_owner": {"cli": "sage/i18n", "hook": "scripts/sage_harness/hooks/runtime/i18n"},
        "total": len(entries),
        "entries": entries,
    }
    rendered = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    out_path = os.path.join(args.root, args.out)

    if args.check:
        if not os.path.isfile(out_path):
            print(f"[inventory] 파일 없음: {out_path}", file=sys.stderr)
            return 1
        current = Path(out_path).read_text(encoding="utf-8")
        if current != rendered:
            print("[inventory] 코드와 인벤토리가 어긋남 — 재생성이 필요합니다", file=sys.stderr)
            return 1
        print(f"[inventory] OK ({len(entries)} entries)")
        return 0

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(rendered)
    print(f"[inventory] {len(entries)} entries → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
