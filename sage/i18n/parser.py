"""bootstrap scan 과 argparse bridge.

전체 parser 를 만들려면 언어가 필요하고, 언어를 알려면 argv 를 봐야 한다. 그래서 parser 생성
**전에** 아무것도 출력하지 않는 scan 을 한 번 돌려 `--lang` 과 대상 root 힌트만 뽑는다. 이
scan 이 없으면 잘못된 `--lang` 이 한국어 parser 를 다 만든 뒤에야 드러나고, 그때의 오류 문구는
사용자가 고르려던 언어가 아니게 된다.
"""
from __future__ import annotations

import os

from sage.i18n import tr
from sage.i18n.context import INTERFACE_LANGUAGES, LanguageContext, resolve, supported

LANG_FLAG = "--lang"
_LANG_PREFIX = f"{LANG_FLAG}="

# `--lang` 뒤에 subcommand 가 오는 전역 옵션이다. subcommand 뒤의 `--lang` 은 그 subcommand 의
# 옵션이라 여기서 보지 않는다 — 두 자리를 모두 받으면 어느 쪽이 이기는지가 명령마다 갈린다.
#
# 두 종류를 갈라 둔다. `--root`/`--dest` 는 프로젝트 루트고, `--profile` 은 그 **안의 파일**
# 경로다. 같은 자리에 넣으면 `--profile sage/project-profile.yaml` 이 루트로 읽혀 그 아래에서
# local profile 을 찾다가 못 찾고 `ko` 로 떨어진다 — 사용자가 설정한 `en` 이 조용히 무시된다.
_ROOT_HINTS = ("--root", "--dest")
_PROFILE_HINTS = ("--profile",)


def _root_of_profile(path: str) -> str | None:
    """`<root>/sage/<name>.yaml` → `<root>`. 그 모양이 아니면 힌트를 만들지 않는다.

    임의 경로의 상위 두 단계를 루트라고 부르면 엉뚱한 디렉터리의 local profile 을 읽게 된다.
    부모가 `sage` 일 때만 인정하고, 아니면 `None` 을 돌려 cwd 로 떨어뜨린다 — 모르는 것을
    추측하는 것보다 기존 동작으로 남는 편이 낫다.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if os.path.basename(parent) != "sage":
        return None
    return os.path.dirname(parent)


def _option_value(token, names, argv, index):
    """`--opt VALUE` 와 `--opt=VALUE` 를 같게 읽는다. (값, 추가로 소비한 토큰 수) 또는 None.

    argparse 는 두 표기를 같은 것으로 받는다. 여기서 공백형만 보면 등호로 쓴 사용자만 root 힌트를
    잃고 조용히 `ko` 로 떨어진다 — 같은 명령이 표기 하나 때문에 다른 언어를 낸다. 표기별로 갈리는
    것은 사용자가 재현하기도 어렵다.
    """
    for name in names:
        if token == name:
            return (argv[index + 1], 1) if index + 1 < len(argv) else None
        prefix = f"{name}="
        if token.startswith(prefix):
            return token[len(prefix):], 0
    return None


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
        elif (hint := _option_value(token, _ROOT_HINTS, argv, index)) is not None:
            root = hint[0]
            index += hint[1]
        elif (hint := _option_value(token, _PROFILE_HINTS, argv, index)) is not None:
            root = _root_of_profile(hint[0]) or root
            index += hint[1]
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
    return resolve(explicit, root_hint or cwd or os.getcwd())
