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
# (파일, 심볼) → (건수, 이유). 심볼 하나가 통째로 제외되므로 그 심볼에 화면 문장을 새로 넣으면
# 조용히 함께 빠진다. **건수를 함께 못 박아** 하나라도 늘거나 줄면 빌드가 선다 — 제외가
# 미이관을 숨기는 통로가 되지 않게 하는 유일한 장치다. 걸러내는 게 없는 선언도 실패다.
NOT_TRANSLATED = {
    ("sage/overlay_common.py", "<module>"): (1,
        "관리 블록 마커 문자열. 파서가 직접 비교하고 기존 설치본에 그대로 박혀 있어, 번역하면 "
        "모든 설치본의 마커 짝이 깨진다."),
    ("sage/overlay_common.py", "compose_block"): (1,
        "렌더 산출물에 기록되는 본문. base 해시 앵커의 입력이라 표시 언어에 따라 달라지면 같은 "
        "프로젝트에서 사용자마다 다른 drift 가 잡힌다."),
    ("sage/overlay_lint.py", "<module>"): (5,
        "게이트 완화 표현을 잡는 탐지 정규식. 한국어는 화면 문장이 아니라 탐지 대상이라, "
        "번역하면 한국어로 쓰인 완화 지시를 더 이상 잡지 못한다."),
    ("sage/routing_block.py", "render_routing_body"): (4,
        "AGENT_GUIDE 에 물리 삽입되는 라우팅 블록 본문. CLI 표시 언어가 아니라 프로젝트 산출물이고, "
        "base 해시 앵커의 입력이라 표시 언어에 따라 달라지면 같은 프로젝트에서 사용자마다 다른 "
        "drift 가 잡힌다."),
    ("sage/commands/change.py", "<module>"): (8,
        "_ABSORB_KW — `sage change \"자연어 의도\"` 라우터가 사용자의 한국어 자연어 입력에서 "
        "매칭하는 키워드 리스트. 화면 출력이 아니라 입력 파서 literal 이라 번역하면 매칭 자체가 "
        "깨진다. 영어 자연어 입력 지원은 이 키워드를 '번역'하는 문제가 아니라 별도 영어 키워드 "
        "세트를 병행 등록할지를 정하는 기능 결정이다 — 이번 배치 범위 밖."),
    ("sage/commands/generate.py", "<module>"): (1,
        "_OVERLAY_HEADER_PREFIXES — 렌더 본문에서 compose_block 고지 헤더를 걷어내는 prefix 매처. "
        "CORE 렌더 헤더는 overlay_common.compose_block 과 동일하게 표시 언어에 매이지 않는 산출물 "
        "본문(해시 앵커 입력)이라 번역 대상이 아니다."),
    ("sage/commands/cycle.py", "_phase00_prose"): (12,
        "`--create` 가 만드는 Phase 00 초안의 사람용 heading·TODO. 화면에 찍히지 않고 문서 파일 "
        "안으로 들어가며, 언어를 고르는 것은 `--lang` 표시 언어가 아니라 그 사이클의 "
        "`Document-Language:` 선언이다. 표시 카탈로그로 보내면 표시가 ko 인 사용자가 en 사이클을 "
        "열 때 영어 문서에 한국어 heading 이 박힌다 — 막으려는 혼용을 도구가 직접 만든다."),
    ("sage/commands/retro.py", "<module>"): (2,
        "_DISTILLER_PROMPT + _APPLY_PATH — host AI 를 대상으로 한 고정 LLM 프롬프트/절차 설명. "
        "화면에 표시되는 문장이 아니라 host AI 가 읽는 지시문이라 표시 언어와 무관하게 항상 원문을 "
        "유지한다. 언어 신호는 프롬프트 뒤에 붙는 [LANGUAGE] 부록 한 줄(cli.retro.distiller_"
        "language_directive, catalog 이관됨)만 담당하고, _APPLY_PATH 는 순수 구조 설명이라 언어 "
        "지시 자체가 불필요하다. 요약 placeholder(_SUMMARY_PLACEHOLDER)는 반대로 catalog 로 이관됐다 "
        "— 이건 노트에 실제로 표시되는 문장이라 이 예외에 포함되지 않는다."),
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


def _joinedstr_text(node: ast.JoinedStr, source: str) -> str:
    """JoinedStr 의 실제 런타임 문자열에 가깝게 재구성한다(리터럴 조각 + `{expr}` 자리).

    `ast.get_source_segment(source, node)` 는 노드의 시작~끝 사이 **원본 소스를 그대로 슬라이스**
    한다. 인접 문자열 리터럴이 괄호 안에서 줄바꿈되며 그 사이에 주석이 끼면(허용된 문법), 그
    주석의 원문까지 슬라이스에 포함된다 — 실행 시 그 주석은 값에 전혀 안 들어가는데도 스캐너가
    "한국어가 있다"고 오판한다(`generate.py::_promoted_render` 의 배너 조립에서 실측). 조각
    단위로 다시 조립하면 이 문제가 원천적으로 없다.
    """
    parts = []
    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
        elif isinstance(value, ast.FormattedValue):
            expr_src = ast.get_source_segment(source, value.value) or "..."
            parts.append("{" + expr_src + "}")
    return "".join(parts)


def _korean_literals(node: ast.AST, source: str) -> list[tuple[str, bool]]:
    """(텍스트, 보간 여부). f-string 은 조각이 아니라 통째로 하나의 문장이다.

    **모든 자식으로 내려간다.** 예전에는 `BinOp`/`Call` 만 따라갔고, 그래서
    `print(tr(...) + (f", 갱신필요 {n}" if n else ""))` 처럼 조건식 안에 있는 한국어를 통째로
    놓쳤다. 인벤토리가 0 을 보고하는데 화면에는 한국어가 남는 상태가 됐고, 그건 이 프로젝트가
    반복해서 반증한 "부재는 안전 방향" 의 자리다. 세는 범위가 화면보다 좁으면 셈이 거짓이 된다.
    """
    found: list[tuple[str, bool]] = []
    if isinstance(node, ast.JoinedStr):
        segment = _joinedstr_text(node, source)
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


def _joinedstr_fragment_ids(tree: ast.AST) -> set[int]:
    """모든 JoinedStr 의 **직접** 리터럴 조각(Constant) id.

    `_scan_korean_literals` 의 바깥 루프는 `ast.walk(tree)` 로 파일의 모든 노드를 훑는다.
    `_korean_literals` 자체는 JoinedStr 를 만나면 조각을 안 세고 통째로 하나로 반환하지만,
    `ast.walk` 는 이 노드가 JoinedStr **안**에 있다는 맥락을 모른 채 그 조각(Constant) 도
    독립 노드로 다시 방문한다 — 결과가 "한 문장(JoinedStr 전체) + 그 조각들"이 각각 별도
    entry 로 잡혀 같은 문장이 여러 건으로 부풀려진다(실측: 511건 중 210건이 이 중복이었다).
    직접 조각만 제외한다 — `{expr}` 안쪽(`FormattedValue.value`)의 별도 리터럴(예: 삼항식)은
    그 자체로 독립적인 한국어일 수 있어 제외하지 않는다.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.Constant):
                    ids.add(id(value))
    return ids


def _print_arg_owner(tree: ast.AST) -> dict[int, str]:
    """print() 호출 인자 서브트리에 속한 모든 노드 id → 그 print 의 channel.

    `print("...")` 처럼 literal 이 직접 인자인 경우만 여기 걸린다. `msg = "..."; print(msg)`
    처럼 한 다리 건너 조립되는 경우는 걸리지 않는다 — 그건 `_scan_korean_literals` 가 파일
    전체를 훑어 별도로 잡는다(classification 이 `command_output` 대신 `command_output_indirect`
    로 갈린다).
    """
    owner: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            channel = _channel(node)
            for arg in node.args:
                for sub in ast.walk(arg):
                    owner[id(sub)] = channel
    return owner


def _scan_korean_literals(path: str, rel: str, *, id_prefix: str, required_tests: list[str],
                           direct_classification: str | None, indirect_classification: str,
                           default_channel_owner: dict[int, str] | None = None,
                           hook_reachable_of: str | None = None,
                           claimed: set[int] = frozenset()) -> tuple[list[dict], list[dict]]:
    """파일 전체에서 한국어 literal 을 훑는다 — `print()` 인자뿐 아니라 어디서든.

    좁게(→ `print()` 직접 인자만) 보면 `ast.Assign`/`ast.IfExp` 로 조립된 뒤 몇 프레임 떨어진
    곳에서 출력되는 형태(예: `_validate_hook()` 이 문자열을 반환하고 `validate.py` 의 `run()`
    이 나중에 `for m in msgs: print(m)` 로 찍는 형태)를 놓친다. 실측: `sync_overlays.py` 의
    `suffix = "..." if cond else "..."` → `print(f"...{suffix}...")` 가 정확히 이 형태였고,
    인벤토리는 0 인데 화면에는 한국어가 남았다. 전체를 훑으면 스코프·호출 깊이에 상관없이
    잡힌다 — `sage/*.py` 검증 계층(`VALIDATION_RELS`)이 이미 쓰던 방식과 같다.
    """
    entries: list[dict] = []
    exclusions: list[dict] = []
    source = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=path)
    owner = _enclosing(tree)
    module = os.path.basename(path)[:-3]
    docstrings = {id(n) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                    ast.AsyncFunctionDef))
                  and n.body and isinstance(n.body[0], ast.Expr)
                  for n in [n.body[0].value]}
    print_owner = default_channel_owner if default_channel_owner is not None else {}
    fragment_ids = _joinedstr_fragment_ids(tree)
    seen_lines: dict[int, int] = {}
    for node in ast.walk(tree):
        if id(node) in docstrings or id(node) in claimed:
            continue      # 주석·docstring 은 한국어가 기본 정책이다
        if id(node) in fragment_ids:
            continue      # 부모 JoinedStr 가 이미 통째로 셌다 — 조각을 또 세면 중복이다
        if not isinstance(node, (ast.Constant, ast.JoinedStr)):
            continue
        for text, interpolated in _korean_literals(node, source):
            symbol = owner.get(id(node), "<module>")
            declared = NOT_TRANSLATED.get((rel.replace(os.sep, "/"), symbol))
            if declared:
                reason = declared[1]
                exclusions.append({"source_file": rel, "source_symbol": symbol,
                                   "source_line": node.lineno, "text": text,
                                   "reason": reason})
                continue
            seen_lines[node.lineno] = seen_lines.get(node.lineno, 0) + 1
            ordinal = seen_lines[node.lineno]
            direct = id(node) in print_owner
            entry = {
                "id": f"{module}:{node.lineno}:{id_prefix}{ordinal}",
                "domain": "cli",
                "key": None,
                "source_file": rel,
                "source_symbol": symbol,
                "source_line": node.lineno,
                "channel": print_owner.get(id(node), "stdout"),
                "exit_contract": "unchanged",
                "format": "interpolated" if interpolated else "static",
                "placeholders": _placeholders(text) if not interpolated else [],
                "machine_consumer": None,
                "classification": (direct_classification if direct and direct_classification
                                   else indirect_classification),
                "text": text,
                "required_tests": required_tests,
            }
            if hook_reachable_of is not None:
                entry["hook_reachable"] = hook_reachable_of in HOOK_REACHABLE
            entries.append(entry)
    return entries, exclusions


def collect(repo_root: str) -> list[dict]:
    entries: list[dict] = []
    exclusions: list[dict] = []
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

        claimed: set[int] = set()
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
                claimed.add(id(kw.value))
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

        command_entries, command_exclusions = _scan_korean_literals(
            path, rel,
            id_prefix="cmd",
            required_tests=["ko_parity", "en_snapshot", "no_leakage"],
            direct_classification="command_output",
            indirect_classification="command_output_indirect",
            default_channel_owner=_print_arg_owner(tree),
            claimed=claimed,
        )
        entries.extend(command_entries)
        exclusions.extend(command_exclusions)

    validation, validation_exclusions = _collect_validation(repo_root)
    entries.extend(validation)
    exclusions.extend(validation_exclusions)
    return entries, exclusions


def _collect_validation(repo_root: str) -> tuple[list[dict], list[dict]]:
    """검증·계약 계층의 한국어 문자열. 세는 것이 목적이고 이관 판정은 모듈별이다."""
    entries: list[dict] = []
    exclusions: list[dict] = []
    for rel_parts in VALIDATION_RELS:
        path = os.path.join(repo_root, *rel_parts)
        if not os.path.isfile(path):
            continue
        rel = os.path.join(*rel_parts)
        module_entries, module_exclusions = _scan_korean_literals(
            path, rel,
            id_prefix="validation",
            required_tests=["ko_parity", "en_snapshot"],
            direct_classification=None,
            indirect_classification="validation_message",
            hook_reachable_of=rel_parts[-1],
        )
        entries.extend(module_entries)
        exclusions.extend(module_exclusions)
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
    counted: dict[tuple[str, str], int] = {}
    for item in exclusions:
        key = (item["source_file"].replace(os.sep, "/"), item["source_symbol"])
        counted[key] = counted.get(key, 0) + 1
    # 선언한 건수와 실제 제외 건수가 다르면 세운다. 0 건(죽은 선언)도 여기서 걸린다.
    drifted = {key: (expected, counted.get(key, 0))
               for key, (expected, _reason) in NOT_TRANSLATED.items()
               if counted.get(key, 0) != expected}
    if drifted:
        print(f"[inventory] 제외 선언과 실제 건수가 다릅니다 (선언, 실제): {drifted}",
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
