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
KOREAN_IN_ENGLISH_DEBT = frozenset()

_RUNTIME_REL = ("scripts", "sage_harness", "hooks", "runtime")

# CLI 가 판정 결과를 화면에 싣는 설치 runtime 모듈. 인벤토리는 `sage/` 를 파일 단위로 스캔하므로
# 여기서 올라온 완성 문장은 세지 못한다 — CLI 모듈이 0건이어도 영어 화면에 한국어가 실린다.
CLI_CONSUMED_RUNTIME_MODULES = ("loop_audit", "fast_cycle_audit", "cycle_state", "retro_audit",
                                "override_audit", "document_language", "checklist_contract")

# 아직 완성 한국어 문장을 돌려주는 runtime 함수. catalog 부채와 같은 규칙 — **정확한 집합**이고
# 해소하면 반드시 지운다. 해당 명령 배치에서 비운다.
KOREAN_JUDGEMENT_DEBT = frozenset()


def _placeholders(template: str) -> set[str]:
    """named placeholder 집합. positional 은 이름이 없어 번역자가 순서를 맞출 근거가 없다."""
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def _positional_placeholders(template: str) -> list[str]:
    return [name for _, name, _, _ in string.Formatter().parse(template)
            if name is not None and (name == "" or name.isdigit())]


def load_hook_fragments(repo_root: str) -> dict[str, dict]:
    """설치 hook 의 `FRAGMENTS` 테이블. `MESSAGES` 와 다른 물건이다 —
    `MESSAGES` 는 게이트 결정이 싣는 message_key 의 표이고, `FRAGMENTS` 는 그 문장에 붙는
    조각(hint·복구 설명·guard 사유)의 표다. 둘을 같은 것으로 보면 있는 문구를 없다고 한다.
    """
    locale_dir = os.path.join(repo_root, *_HOOK_LOCALE_REL)
    fragments: dict[str, dict] = {}
    for language in ("ko", "en"):
        path = os.path.join(locale_dir, f"{language}.py")
        if not os.path.isfile(path):
            continue
        namespace: dict = {}
        with open(path, encoding="utf-8") as handle:
            exec(compile(handle.read(), path, "exec"), namespace)  # noqa: S102
        table = namespace.get("FRAGMENTS")
        if isinstance(table, dict):
            fragments[language] = table
    return fragments


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



# 진단 code 로 승격되면 안 되는 이름들. `block_*` 패턴으로 잡히지만 메시지 키가 아니다 —
# 함수명·함수 파라미터·profile 설정 키·다른 키의 prefix 다. 기계 변환을 채택했다면 이 넷에서
# `gate.message`·`gate.reason`·`gate.release`·`gate.stale` 이라는 안정 식별자가 만들어졌을
# 것이고, 안정 식별자는 한 번 나가면 되돌릴 수 없다.
# 한쪽 표에만 있어도 되는 recovery id. **여기 이름이 적혀 있어야** 통과한다 — 비대칭을
# 자동으로 허용하면 rename 으로 사라진 id 와 의도된 비대칭이 구분되지 않는다.
# hook 만 내는 복구: 게이트·문서 판정에서만 발생하는 상황이다. CLI 에는 그 진단이 없다.
HOOK_ONLY_RECOVERY_IDS = frozenset({
    "cycle-clear", "explain", "fast-open", "fix-document", "fix-report",
    "fix-risk-declaration", "move-off-desktop", "resolve-feedback", "run-review",
    "select-l3-strategy", "write-plan",
})
# CLI 만 내는 복구: 설치·버전·프로필 정합처럼 hook 이 진단하지 않는 축이다.
CLI_ONLY_RECOVERY_IDS = frozenset({
    "doctor", "fast-cycle-show", "fix-required-version", "fix-sage-section",
    "regenerate-hook", "upgrade-check", "upgrade-package",
})

NOT_MESSAGE_KEYS = frozenset({"block_message", "block_reason", "block_release", "block_stale"})


def _load_hook_recovery(repo_root: str):
    import importlib.util
    path = os.path.join(repo_root, *_RUNTIME_REL, "recovery.py")
    spec = importlib.util.spec_from_file_location("_sage_hook_recovery", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def recovery_issues(repo_root: str) -> list[str]:
    """BLOCK 에 다음 행동이 있는가 — CLI·hook 두 벌이 어긋나지 않는가.

    두 벌인 이유는 설치된 hook 이 엔진 없이 돌아야 하기 때문이다(`sage.diagnostic_contract` 를
    import 할 수 없다). 공통인 것은 code 와 recovery id 의 **형태와 의미**이고, 그 일치는
    런타임이 아니라 여기서 대조한다.
    """
    from sage.diagnostic_contract import (BLOCK, FORBIDDEN_COMMAND,
                                          RECOVERY as CLI_RECOVERY, SEVERITY,
                                          contract_issues)

    issues = [f"cli/diagnostic_contract: {issue}" for issue in contract_issues()]

    try:
        hook = _load_hook_recovery(repo_root)
    except Exception as exc:
        return issues + [f"hook/recovery: 불러오지 못했다 ({type(exc).__name__})"]
    if hook is None:
        return issues + ["hook/recovery: runtime/recovery.py 가 없다"]

    fragments = load_hook_fragments(repo_root)

    # 1. 모든 hook BLOCK code 에 실행 가능한 명령이 최소 하나 있다.
    for code in sorted(set(hook.CODE_OF.values()) | set(hook.GUARD_CODES)):
        steps = hook.steps_for(code)
        if not steps:
            issues.append(f"hook/recovery: {code} 에 복구 순서가 없다")
            continue
        if not any(command for _id, command, _key, _mut in steps):
            issues.append(f"hook/recovery: {code} 의 복구가 전부 수동 지시다")

    # 2a. catalog 에 있는 모든 `block_*` 메시지 키가 code 를 갖는다. 이 방향이 핵심이다 —
    #     새 BLOCK 을 추가하고 code 를 잊으면 그 차단만 조용히 `Next:` 없이 나간다.
    catalogs = load_hook_catalogs(repo_root)
    for key in sorted(catalogs.get("ko", {})):
        if not key.startswith("block_") or key in NOT_MESSAGE_KEYS:
            continue
        if key not in hook.CODE_OF:
            issues.append(f"hook/recovery: 메시지 키 {key} 에 진단 code 매핑이 없다 — "
                          "이 차단은 `Next:` 없이 나간다")

    # 2. 메시지 키가 아닌 이름이 code 로 승격되지 않았다.
    for name in sorted(NOT_MESSAGE_KEYS & set(hook.CODE_OF)):
        issues.append(f"hook/recovery: {name} 은 메시지 키가 아닌데 code 로 승격됐다")

    # 3. 같은 recovery id 는 양쪽에서 같은 명령을 낸다.
    #
    # 교집합만 비교하면 이빨이 빠진다 — id 를 rename 하면서 명령도 함께 바꾸면 그 id 가
    # 교집합에서 빠져나가고, 검사는 아무 말도 하지 않는다. 그래서 집합 자체를 양방향으로
    # 대조하고, 한쪽에만 있어도 되는 id 는 아래 목록에 **이름을 적어** 선언하게 한다.
    cli_commands = {}
    for steps in CLI_RECOVERY.values():
        for step in steps:
            cli_commands.setdefault(step.id, step.command)
    hook_commands = {}
    for steps in hook.RECOVERY.values():
        for step_id, command, _key, _mut in steps:
            hook_commands.setdefault(step_id, command)

    for step_id in sorted(set(hook_commands) & set(cli_commands)):
        if cli_commands[step_id] != hook_commands[step_id]:
            issues.append(f"recovery id {step_id!r} 가 CLI 와 hook 에서 다른 명령을 낸다 — "
                          f"{cli_commands[step_id]!r} vs {hook_commands[step_id]!r}")
    for step_id in sorted(set(hook_commands) - set(cli_commands) - HOOK_ONLY_RECOVERY_IDS):
        issues.append(f"recovery id {step_id!r} 가 hook 에만 있다 — CLI 에도 두거나 "
                      "HOOK_ONLY_RECOVERY_IDS 에 선언하라")
    for step_id in sorted(set(cli_commands) - set(hook_commands) - CLI_ONLY_RECOVERY_IDS):
        issues.append(f"recovery id {step_id!r} 가 CLI 에만 있다 — hook 에도 두거나 "
                      "CLI_ONLY_RECOVERY_IDS 에 선언하라")
    # 선언과 실제 차집합을 **정확히** 대조한다. 한쪽 방향만 보면 선언이 실제보다 넓어져도
    # 통과한다 — 예외 목록이 좁혀지지 않고 낡은 채로 남는 통로다.
    for step_id in sorted(HOOK_ONLY_RECOVERY_IDS - (set(hook_commands) - set(cli_commands))):
        issues.append(f"HOOK_ONLY_RECOVERY_IDS 의 {step_id!r} 가 더 이상 hook 전용이 아니다 — "
                      "선언에서 지워라")
    for step_id in sorted(CLI_ONLY_RECOVERY_IDS - (set(cli_commands) - set(hook_commands))):
        issues.append(f"CLI_ONLY_RECOVERY_IDS 의 {step_id!r} 가 더 이상 CLI 전용이 아니다 — "
                      "선언에서 지워라")

    # 3b. hook 쪽 명령에도 CLI 와 같은 금지 규칙을 적용한다. 두 표가 같은 화면에 나가는데
    #     한쪽만 검사하면, 파괴적 명령은 검사되지 않는 쪽으로 흘러간다.
    for code, steps in sorted(hook.RECOVERY.items()):
        for step_id, command, _key, _mut in steps:
            if command and FORBIDDEN_COMMAND.search(command):
                issues.append(f"hook/recovery: {code} 의 {step_id!r} 가 금지된 명령을 낸다 — "
                              f"{command!r}")

    # 4. Action 단계의 설명 key 가 두 hook catalog 에 모두 있다.
    for code, steps in sorted(hook.RECOVERY.items()):
        for step_id, command, description_key, _mut in steps:
            if command:
                continue
            for language in ("ko", "en"):
                if description_key not in fragments.get(language, {}):
                    issues.append(f"hook/{description_key}[{language}]: "
                                  f"복구 설명 문구가 없다 ({code} / {step_id})")

    # 5. CLI 쪽 BLOCK code 도 recovery 를 가진다(contract_issues 가 이미 보지만, 두 검사가
    #    같은 사실을 보는 편이 낫다 — 한쪽이 조용히 꺼져도 다른 쪽이 남는다).
    for code, level in sorted(SEVERITY.items()):
        if level == BLOCK and not CLI_RECOVERY.get(code):
            issues.append(f"cli/recovery: {code} 가 BLOCK 인데 복구 순서가 없다")
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
        issues.extend(recovery_issues(repo_root))

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
