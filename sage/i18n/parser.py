"""bootstrap scan 과 argparse bridge.

전체 parser 를 만들려면 언어가 필요하고, 언어를 알려면 argv 를 봐야 한다. 그래서 parser 생성
**전에** 아무것도 출력하지 않는 scan 을 한 번 돌려 `--lang` 과 대상 root 힌트만 뽑는다. 이
scan 이 없으면 잘못된 `--lang` 이 한국어 parser 를 다 만든 뒤에야 드러나고, 그때의 오류 문구는
사용자가 고르려던 언어가 아니게 된다.
"""
from __future__ import annotations

from sage.i18n import tr
from sage.i18n.context import INTERFACE_LANGUAGES, LanguageContext, resolve, supported

LANG_FLAG = "--lang"
_LANG_PREFIX = f"{LANG_FLAG}="

# `--lang` 뒤에 subcommand 가 오는 전역 옵션이다. subcommand 뒤의 `--lang` 은 그 subcommand 의
# 옵션이라 여기서 보지 않는다 — 두 자리를 모두 받으면 어느 쪽이 이기는지가 명령마다 갈린다.
_TARGET_HINTS = ("--root", "--dest", "--profile")


class LanguageArgumentError(Exception):
    """언어 선택 자체가 실패. 판정 이전이라 부작용 없이 exit 2 로 끝난다."""

    def __init__(self, key: str, **arguments):
        super().__init__(key)
        self.key = key
        self.arguments = arguments

    def bilingual(self) -> str:
        """한영 병기. 사용자가 고르려던 언어를 모르는 상태라 한쪽만 내면 절반은 못 읽는다."""
        return "\n".join((tr("ko", self.key, **self.arguments),
                          tr("en", self.key, **self.arguments)))


def scan(argv: list[str]) -> tuple[str | None, str | None]:
    """(명시 언어, root 힌트). 출력하지 않고 예외만 올린다."""
    explicit: str | None = None
    root: str | None = None
    supported_list = ", ".join(INTERFACE_LANGUAGES)
    index = 0
    while index < len(argv):
        token = argv[index]
        value = None
        if token == LANG_FLAG:
            if index + 1 >= len(argv):
                raise LanguageArgumentError("cli.lang.missing_value", supported=supported_list)
            value = argv[index + 1]
            index += 1
        elif token.startswith(_LANG_PREFIX):
            value = token[len(_LANG_PREFIX):]
        elif token in _TARGET_HINTS and index + 1 < len(argv):
            root = argv[index + 1]
            index += 1
        if value is not None:
            if explicit is not None:
                raise LanguageArgumentError("cli.lang.duplicated")
            if not supported(value):
                raise LanguageArgumentError("cli.lang.unsupported", value=value,
                                            supported=supported_list)
            explicit = value
        index += 1
    return explicit, root


def context_for(argv: list[str], cwd: str | None = None) -> LanguageContext:
    """argv 를 훑어 이 실행의 표시 언어를 확정한다."""
    explicit, root_hint = scan(argv)
    import os
    return resolve(explicit, root_hint or cwd or os.getcwd())
