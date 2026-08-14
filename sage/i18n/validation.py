"""catalog 정합성 — CLI 와 설치 hook 두 도메인의 build-time 단일 oracle.

두 도메인은 의도적으로 다른 key 집합을 갖는다. CLI 는 `cli.*` 를 쓰고, hook 은 기존 호환 key
(`ok_l1` 등)를 그대로 유지한다. 그래서 검사는 "두 도메인이 같은가"가 아니라 각 도메인 **안에서**
한영이 같은가, 그리고 두 도메인이 **겹치지 않는가**이다.

설치된 hook runtime 은 이 모듈을 import 하지 않는다(소비 프로젝트에서 main package 없이 단독
실행되어야 한다). 역방향으로 이 모듈이 hook catalog 를 읽는 것만 허용해, 런타임 독립성과
build-time 전체 정합성을 동시에 만족시킨다.
"""
from __future__ import annotations

import ast
import os
import re
import string

from sage.i18n import CATALOGS

CLI_NAMESPACE = "cli."

_HOOK_LOCALE_REL = ("scripts", "sage_harness", "hooks", "runtime", "i18n")

_KOREAN = re.compile(r"[가-힣]")

# 영어 catalog 값 안에 이스케이프된 개행 두 글자가 들어오면 사용자는 줄바꿈 대신 `\n` 을 읽는다.
# 한국어 쪽이 실제 개행인데 영어 쪽만 리터럴이면 같은 문장이 언어마다 다른 모양으로 깨진다.
_ESCAPED_NEWLINE = re.compile(r"\\n")

# 영어 값이 한국어인 것이 **의도**인 key. 다른 언어로 가는 안내라 문안 자체가 반대 언어다.
KOREAN_IN_ENGLISH_ALLOWED = frozenset({"cli.root.switch_hint"})

# 아직 이관되지 않은 영어 catalog 부채. **건수가 아니라 정확한 key 집합**이다 — 건수만 세면
# 한 건을 고치면서 다른 한 건이 새로 들어와도 총계가 같아 통과한다. 해소한 key 는 반드시 이
# 집합에서 지워야 하고(낡은 항목도 실패로 보고한다), 이관이 끝나면 비어야 한다.
KOREAN_IN_ENGLISH_DEBT = frozenset({
    "cli.validate.review_loop_arch_escalation_ineffective",   # en 값이 ko 원문 그대로 복사됨
    "cli.validate.review_loop_cross_model_ineffective",       # 같은 복사
})

_RUNTIME_REL = ("scripts", "sage_harness", "hooks", "runtime")

# CLI 가 판정 결과를 화면에 싣는 설치 runtime 모듈. 인벤토리는 `sage/` 를 파일 단위로 스캔하므로
# 여기서 올라온 완성 문장은 세지 못한다 — CLI 모듈이 0건이어도 영어 화면에 한국어가 실린다.
CLI_CONSUMED_RUNTIME_MODULES = ("loop_audit", "fast_cycle_audit", "cycle_state", "retro_audit",
                                "override_audit", "document_language", "checklist_contract")

# 아직 완성 한국어 문장을 돌려주는 runtime 함수. catalog 부채와 같은 규칙 — **정확한 집합**이고
# 해소하면 반드시 지운다. 해당 명령 배치에서 비운다.
KOREAN_JUDGEMENT_DEBT = frozenset({
    "cycle_state.read_declaration",             # sage cycle / fast-cycle 화면
    "cycle_state.read_declaration_record",
    "cycle_state.write_declaration",
    "override_audit.state_home",                # sage override 화면
    "override_audit._probe_gitdir",
    "override_audit._gitdir",
    "override_audit._repo_id",
    "override_audit.grants_path",
    "override_audit.grant",
    "document_language.consistency_issues",     # hook·CLI 양쪽
    "checklist_contract.unsafe_glob",           # hook 게이트
    "checklist_contract.checklist_target_issues",
})


def _placeholders(template: str) -> set[str]:
    """named placeholder 집합. positional 은 이름이 없어 번역자가 순서를 맞출 근거가 없다."""
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def _positional_placeholders(template: str) -> list[str]:
    return [name for _, name, _, _ in string.Formatter().parse(template)
            if name is not None and (name == "" or name.isdigit())]


def load_hook_catalogs(repo_root: str) -> dict[str, dict]:
    """설치 hook locale 을 resource 로 읽는다. 아직 없으면 빈 dict — 배치 순서를 막지 않는다."""
    locale_dir = os.path.join(repo_root, *_HOOK_LOCALE_REL)
    catalogs: dict[str, dict] = {}
    for language in ("ko", "en"):
        path = os.path.join(locale_dir, f"{language}.py")
        if not os.path.isfile(path):
            continue
        namespace: dict = {}
        with open(path, encoding="utf-8") as handle:
            exec(compile(handle.read(), path, "exec"), namespace)  # noqa: S102
        messages = namespace.get("MESSAGES")
        if isinstance(messages, dict):
            catalogs[language] = messages
    return catalogs


def _domain_issues(label: str, catalogs: dict[str, dict]) -> list[str]:
    issues: list[str] = []
    if set(catalogs) != {"ko", "en"}:
        if catalogs:
            issues.append(f"{label}: ko 와 en catalog 가 모두 있어야 함 (현재 {sorted(catalogs)})")
        return issues

    ko, en = catalogs["ko"], catalogs["en"]
    only_ko = sorted(set(ko) - set(en))
    only_en = sorted(set(en) - set(ko))
    if only_ko:
        issues.append(f"{label}: en 에 없는 key {only_ko}")
    if only_en:
        issues.append(f"{label}: ko 에 없는 key {only_en}")

    for key in sorted(set(ko) & set(en)):
        ko_names, en_names = _placeholders(ko[key]), _placeholders(en[key])
        if ko_names != en_names:
            issues.append(f"{label}/{key}: placeholder 불일치 ko={sorted(ko_names)} en={sorted(en_names)}")
        for language, template in (("ko", ko[key]), ("en", en[key])):
            if _positional_placeholders(template):
                issues.append(f"{label}/{key}[{language}]: positional placeholder 금지 — 이름을 붙이세요")
            try:
                string.Formatter().parse(template)
            except ValueError as exc:
                issues.append(f"{label}/{key}[{language}]: format 오류 {exc}")
    return issues


def _content_issues(label: str, catalogs: dict[str, dict], *,
                    korean_debt: frozenset[str] = frozenset()) -> list[str]:
    """catalog **내용** 검사 — key 집합이 맞아도 값 자체가 잘못될 수 있다.

    인벤토리는 코드를 스캔하므로 영어 catalog 안에 한국어가 남은 누출을 세지 못한다. 그 상태로
    이관이 끝나면 인벤토리 0 인데도 `--lang en` 화면에 한국어가 나간다 — 부재가 통과로 떨어지는
    바로 그 형태라, 여기서 값을 직접 본다.
    """
    issues: list[str] = []
    if set(catalogs) != {"ko", "en"}:
        return issues

    leaked = {key for key, text in catalogs["en"].items()
              if isinstance(text, str) and _KOREAN.search(text)}
    for key in sorted(leaked - KOREAN_IN_ENGLISH_ALLOWED - korean_debt):
        issues.append(f"{label}/{key}[en]: 영어 값에 한국어가 남아 있음 — `--lang en` 화면에 그대로 나간다")
    for key in sorted(korean_debt - leaked):
        issues.append(f"{label}/{key}[en]: 한국어가 해소됐다 — KOREAN_IN_ENGLISH_DEBT 에서 지우세요")

    for language in ("ko", "en"):
        for key, text in sorted(catalogs[language].items()):
            if isinstance(text, str) and _ESCAPED_NEWLINE.search(text):
                issues.append(f"{label}/{key}[{language}]: 이스케이프된 개행 두 글자 — 실제 개행을 쓰세요")
    return issues


def korean_returning_runtime_functions(repo_root: str) -> tuple[set[str], list[str]]:
    """runtime 판정 함수 중 완성 한국어 문장을 들고 있는 것 → (집합, 스캔 오류).

    docstring 은 제외한다 — 코드 주석·docstring 의 한국어는 유지 정책이고, 문제는 사용자에게
    돌려주는 문자열이다. 스캔이 파일을 못 읽으면 빈 집합을 통과로 돌려주지 않고 오류로 남긴다:
    부재가 통과로 떨어지면 게이트가 아무것도 지키지 않는다.
    """
    runtime_dir = os.path.join(repo_root, *_RUNTIME_REL)
    found: set[str] = set()
    errors: list[str] = []
    for module in CLI_CONSUMED_RUNTIME_MODULES:
        path = os.path.join(runtime_dir, f"{module}.py")
        try:
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), path)
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"runtime/{module}: 스캔하지 못했다 ({type(exc).__name__})")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            docstring = (node.body[0].value
                         if node.body and isinstance(node.body[0], ast.Expr)
                         and isinstance(node.body[0].value, ast.Constant) else None)
            if any(isinstance(inner, ast.Constant) and isinstance(inner.value, str)
                   and _KOREAN.search(inner.value) and inner is not docstring
                   for inner in ast.walk(node)):
                found.add(f"{module}.{node.name}")
    return found, errors


def runtime_judgement_issues(repo_root: str) -> list[str]:
    """개발 중 추적 검사 — 선언한 부채 집합과 실제가 정확히 같은가."""
    found, issues = korean_returning_runtime_functions(repo_root)
    for name in sorted(found - KOREAN_JUDGEMENT_DEBT):
        issues.append(f"runtime/{name}: 판정이 완성 한국어 문장을 돌려준다 — "
                      "code + arguments + evidence 로 올리세요")
    for name in sorted(KOREAN_JUDGEMENT_DEBT - found):
        issues.append(f"runtime/{name}: 한국어가 해소됐다 — KOREAN_JUDGEMENT_DEBT 에서 지우세요")
    return issues


def release_debt_issues(repo_root: str) -> list[str]:
    """release 게이트 — 추적되는 부채라도 남아 있으면 publish 는 실패다.

    개발 중에는 "알려진 부채가 그대로인가"를 통과로 본다. 그건 진행을 막지 않기 위한 것이지
    출하해도 된다는 뜻이 아니다. 여기서는 선언 목록이 아니라 **실제 남은 누출**을 세므로,
    목록에 적어두는 것만으로는 게이트를 통과할 수 없다.
    """
    issues: list[str] = []
    leaked = {key for key, text in CATALOGS.get("en", {}).items()
              if isinstance(text, str) and _KOREAN.search(text)}
    for key in sorted(leaked - KOREAN_IN_ENGLISH_ALLOWED):
        issues.append(f"cli/{key}[en]: 영어 catalog 에 한국어가 남아 있다 — 이관 전 publish 차단")
    found, errors = korean_returning_runtime_functions(repo_root)
    issues.extend(errors)
    for name in sorted(found):
        issues.append(f"runtime/{name}: 판정이 한국어 문장을 돌려준다 — 이관 전 publish 차단")
    return issues


def catalog_issues(repo_root: str | None = None, hook_message_keys: set[str] | None = None) -> list[str]:
    """전체 검사 결과. 빈 리스트가 통과다."""
    issues = _domain_issues("cli", CATALOGS)
    issues.extend(_content_issues("cli", CATALOGS, korean_debt=KOREAN_IN_ENGLISH_DEBT))

    for key in sorted(CATALOGS.get("ko", {})):
        if not key.startswith(CLI_NAMESPACE):
            issues.append(f"cli/{key}: CLI key 는 '{CLI_NAMESPACE}' namespace 를 써야 함")

    hooks = load_hook_catalogs(repo_root) if repo_root else {}
    issues.extend(_domain_issues("hook", hooks))
    issues.extend(_content_issues("hook", hooks))
    if repo_root:
        issues.extend(runtime_judgement_issues(repo_root))

    if hooks:
        overlap = sorted(set(CATALOGS.get("ko", {})) & set(hooks.get("ko", {})))
        if overlap:
            issues.append(f"cli 와 hook catalog 가 같은 key 를 씀 — 소유자가 둘이 됨: {overlap}")

    # 코드가 emit 할 수 있는 hook key 는 두 hook catalog 에 모두 있어야 한다. 번역 문자열을
    # 뒤지거나 AST 를 추측해 찾지 않고, hook 경계가 내보내는 언어 중립 key 집합과 대조한다.
    if hook_message_keys is not None and hooks:
        for language in ("ko", "en"):
            missing = sorted(hook_message_keys - set(hooks.get(language, {})))
            if missing:
                issues.append(f"hook[{language}]: emit 가능한데 catalog 에 없는 key {missing}")
    return issues
