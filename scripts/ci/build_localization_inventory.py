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

# 검증·계약 계층. 여기 문자열은 `(severity, message)` 로 올라와 doctor/validate/generate 가
# 그대로 화면에 찍는다. `sage/commands` 만 세면 남은 규모가 화면보다 작게 보인다 — 실제로
# commands 가 0 이 된 시점에도 `sage --lang en doctor` 는 한국어를 냈다.
#
# 이 계층은 이관 대상 판정이 commands 와 다르다. 일부 모듈은 설치된 hook 이 엔진 없이 import
# 하는 경로에 있어 `sage.i18n` 을 끌어오면 hook 이 엔진 의존이 된다. 그래서 세기만 하고
# 이관 여부는 모듈별로 판정한다 — `hook_reachable` 에 그 사실을 실어 둔다.
VALIDATION_RELS = (
    ("sage", "profile_validate.py"),
    ("sage", "profile_layers.py"),
    ("sage", "profile_compile.py"),
    ("sage", "model_routing.py"),
    ("sage", "runtime_hosts.py"),
    ("sage", "mcp_common.py"),
    ("sage", "project_hook_contract.py"),
    ("sage", "overlay_materialize.py"),
    ("sage", "overlay_lint.py"),
    ("sage", "overlay_common.py"),
    ("sage", "overlay_classify.py"),
    ("sage", "routing_block.py"),
    ("sage", "install_transaction.py"),
    ("sage", "version_contract.py"),
    ("sage", "context_packet.py"),
    ("sage", "feedback.py"),
    ("sage", "hook_entry.py"),
)
# 설치된 hook 이 엔진 없이 import 하는 경로에 있는 모듈. 여기에 `sage.i18n` 을 넣으면
# B6 이 세운 "hook 은 엔진 없이 돈다" 가 무너진다.
HOOK_REACHABLE = frozenset({"hook_entry.py", "feedback.py", "context_packet.py"})

# 번역 대상이 아닌 한국어. **화면 문장이 아니라 형식 계약이거나 산출물 본문**이라 언어에 따라
# 달라지면 안 되는 것들이다. 세지 않고 넘기면 잔여가 0 으로 보이는 방법이 생기므로, 빼는
# 대신 이유와 함께 따로 기록해 검토 가능하게 남긴다.
#
# (파일, 심볼) → 이유. 심볼 하나가 통째로 제외되므로 그 심볼에 화면 문장을 새로 넣으면
# 조용히 함께 빠진다 — 선언 하나가 무엇도 걸러내지 않으면 실패하게 해 죽은 선언을 막는다.
NOT_TRANSLATED = {
    ("sage/overlay_common.py", "<module>"):
        "관리 블록 마커 문자열. 파서가 직접 비교하고 기존 설치본에 그대로 박혀 있어, 번역하면 "
        "모든 설치본의 마커 짝이 깨진다.",
    ("sage/overlay_common.py", "compose_block"):
        "렌더 산출물에 기록되는 본문. base 해시 앵커의 입력이라 표시 언어에 따라 달라지면 같은 "
        "프로젝트에서 사용자마다 다른 drift 가 잡힌다.",
}


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
    """(텍스트, 보간 여부). f-string 은 조각이 아니라 통째로 하나의 문장이다.

    **모든 자식으로 내려간다.** 예전에는 `BinOp`/`Call` 만 따라갔고, 그래서
    `print(tr(...) + (f", 갱신필요 {n}" if n else ""))` 처럼 조건식 안에 있는 한국어를 통째로
    놓쳤다. 인벤토리가 0 을 보고하는데 화면에는 한국어가 남는 상태가 됐고, 그건 이 프로젝트가
    반복해서 반증한 "부재는 안전 방향" 의 자리다. 세는 범위가 화면보다 좁으면 셈이 거짓이 된다.
    """
    found: list[tuple[str, bool]] = []
    if isinstance(node, ast.JoinedStr):
        segment = ast.get_source_segment(source, node) or ""
        if HANGUL.search(segment):
            found.append((segment, True))
        return found                     # 안쪽 조각까지 세면 한 문장이 여러 건으로 쪼개진다
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str) and HANGUL.search(node.value):
            found.append((node.value, False))
        return found
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
    validation, exclusions = _collect_validation(repo_root)
    entries.extend(validation)
    return entries, exclusions


def _collect_validation(repo_root: str) -> tuple[list[dict], list[dict]]:
    """검증·계약 계층의 한국어 문자열. 세는 것이 목적이고 이관 판정은 모듈별이다."""
    entries: list[dict] = []
    exclusions: list[dict] = []
    for rel_parts in VALIDATION_RELS:
        path = os.path.join(repo_root, *rel_parts)
        if not os.path.isfile(path):
            continue
        source = Path(path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=path)
        owner = _enclosing(tree)
        module = rel_parts[-1][:-3]
        rel = os.path.join(*rel_parts)
        docstrings = {id(n) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                        ast.AsyncFunctionDef))
                      and n.body and isinstance(n.body[0], ast.Expr)
                      for n in [n.body[0].value]}
        # 한 줄에 문자열이 여러 개면 줄 번호만으로는 id 가 겹친다 — 겹치면 진척 계산이 어긋난다.
        seen_lines: dict[int, int] = {}
        for node in ast.walk(tree):
            if id(node) in docstrings:
                continue      # 주석·docstring 은 한국어가 기본 정책이다
            if not isinstance(node, (ast.Constant, ast.JoinedStr)):
                continue
            for text, interpolated in _korean_literals(node, source):
                symbol = owner.get(id(node), "<module>")
                reason = NOT_TRANSLATED.get((rel.replace(os.sep, "/"), symbol))
                if reason:
                    exclusions.append({"source_file": rel, "source_symbol": symbol,
                                       "source_line": node.lineno, "text": text,
                                       "reason": reason})
                    continue
                seen_lines[node.lineno] = seen_lines.get(node.lineno, 0) + 1
                ordinal = seen_lines[node.lineno]
                entries.append({
                    "id": f"{module}:{node.lineno}:validation{ordinal}",
                    "domain": "cli",
                    "key": None,
                    "source_file": rel,
                    "source_symbol": symbol,
                    "source_line": node.lineno,
                    "channel": "stdout",
                    "exit_contract": "unchanged",
                    "format": "interpolated" if interpolated else "static",
                    "placeholders": _placeholders(text) if not interpolated else [],
                    "machine_consumer": None,
                    "classification": "validation_message",
                    "hook_reachable": rel_parts[-1] in HOOK_REACHABLE,
                    "text": text,
                    "required_tests": ["ko_parity", "en_snapshot"],
                })
    return entries, exclusions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default=os.path.join("docs", "sage_harness",
                                                      "localization-inventory.json"))
    parser.add_argument("--check", action="store_true",
                        help="파일을 쓰지 않고 현재 파일과 일치하는지만 검사")
    args = parser.parse_args()

    entries, exclusions = collect(args.root)
    declared = {(rel, symbol) for rel, symbol in NOT_TRANSLATED}
    matched = {(item["source_file"].replace(os.sep, "/"), item["source_symbol"])
               for item in exclusions}
    if declared - matched:
        # 아무것도 걸러내지 않는 제외 선언은 다음 사람에게 "여긴 검토됐다"고 잘못 말한다.
        print(f"[inventory] 아무 문자열도 제외하지 못한 선언: {sorted(declared - matched)}",
              file=sys.stderr)
        return 1
    document = {
        "schema_version": 1,
        "domain_owner": {"cli": "sage/i18n", "hook": "scripts/sage_harness/hooks/runtime/i18n"},
        "total": len(entries),
        "entries": entries,
        "not_translated": exclusions,
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
