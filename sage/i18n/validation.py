"""catalog 정합성 — CLI 와 설치 hook 두 도메인의 build-time 단일 oracle.

두 도메인은 의도적으로 다른 key 집합을 갖는다. CLI 는 `cli.*` 를 쓰고, hook 은 기존 호환 key
(`ok_l1` 등)를 그대로 유지한다. 그래서 검사는 "두 도메인이 같은가"가 아니라 각 도메인 **안에서**
한영이 같은가, 그리고 두 도메인이 **겹치지 않는가**이다.

설치된 hook runtime 은 이 모듈을 import 하지 않는다(소비 프로젝트에서 main package 없이 단독
실행되어야 한다). 역방향으로 이 모듈이 hook catalog 를 읽는 것만 허용해, 런타임 독립성과
build-time 전체 정합성을 동시에 만족시킨다.
"""
from __future__ import annotations

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
    "cli.retro.msg04",     # `## 요약`/`## 제안` — retro heading 계약에서 en 이름으로 교체 예정
    "cli.retro.msg17",     # 같은 heading 이름
    "cli.validate.review_loop_arch_escalation_ineffective",   # en 값이 ko 원문 그대로 복사됨
    "cli.validate.review_loop_cross_model_ineffective",       # 같은 복사
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
