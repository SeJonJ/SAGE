"""SAGE CLI 진입점 — 서브커맨드 디스패치.

각 서브커맨드 모듈은 `register(subparsers)` 와 `run(args) -> int` 를 제공한다.
현 단계는 스캐폴드: 시그니처는 최종검증 §5 / 마스터 설계 §13 부트스트랩에 맞추되
로직은 단계적으로 채운다.
"""

import argparse
import re
import sys

from sage import __version__
from sage.i18n import LanguageContext, tr
from sage.i18n.context import INTERFACE_LANGUAGES
from sage.i18n.parser import LanguageArgumentError, context_for
from sage.commands import (install, generate, validate, asset_check, review, absorb, doctor, change,
                           override, review_loop, retro, knowledge, sync_overlays, acceptance_waiver,
                           authority, models, context, feedback, cycle, fast_cycle,
                           upgrade, status, explain, audit, uninstall)

_COMMANDS = [install, generate, validate, asset_check, review, absorb, doctor, change, override,
             review_loop, retro, knowledge, sync_overlays, acceptance_waiver, authority, models, context,
             feedback, cycle, fast_cycle, upgrade, status, explain, audit, uninstall]


# argparse 는 자기 문장을 gettext 로 만들고 그 catalog 는 SAGE 것이 아니다. 그래서 `--lang ko`
# 로 고른 사용자도 `unrecognized arguments` 를 영어로 받는다 — 오타 한 번이면 누구나 보는
# 화면 하나가 언어 선택 밖에 있는 셈이다. 여기서 **알아본 문장만** 옮기고, 못 알아본 것은
# 원문 그대로 통과시킨다. Python 이 문구를 바꿔도 메시지가 사라지지 않고 영어로 남을 뿐이다.
_ARGPARSE_MESSAGES = (
    (re.compile(r"\Aunrecognized arguments: (?P<value>.*)\Z", re.S), "cli.argparse.unrecognized"),
    (re.compile(r"\Athe following arguments are required: (?P<value>.*)\Z", re.S),
     "cli.argparse.required"),
    (re.compile(r"\Aargument (?P<name>.+?): expected one argument\Z", re.S),
     "cli.argparse.expected_one"),
    (re.compile(r"\Aargument (?P<name>.+?): expected at least one argument\Z", re.S),
     "cli.argparse.expected_at_least_one"),
    (re.compile(r"\Aargument (?P<name>.+?): invalid choice: (?P<value>.+) "
                r"\(choose from (?P<choices>.*)\)\Z", re.S), "cli.argparse.invalid_choice"),
    (re.compile(r"\Aargument (?P<name>.+?): ignored explicit argument (?P<value>.*)\Z", re.S),
     "cli.argparse.ignored_explicit"),
    (re.compile(r"\Aargument (?P<name>.+?): not allowed with argument (?P<value>.*)\Z", re.S),
     "cli.argparse.not_allowed_with"),
    (re.compile(r"\Aargument (?P<name>.+?): invalid (?P<kind>\S+) value: (?P<value>.*)\Z", re.S),
     "cli.argparse.invalid_value"),
)


def localize_argparse_message(language: str, message: str) -> str:
    for pattern, key in _ARGPARSE_MESSAGES:
        match = pattern.match(message or "")
        if match:
            return tr(language, key, **match.groupdict())
    return message


class LocalizedParser(argparse.ArgumentParser):
    """usage 오류를 선택 언어로 내는 parser.

    언어를 **class 속성**으로 두는 이유는 subparser 때문이다. `add_subparsers()` 는
    `type(self)` 로 하위 parser 를 만들지만 생성 인자를 물려주지는 않아서, 인스턴스에 달면
    `sage cycle --nope` 같은 하위 명령 오류만 영어로 남는다. `build_parser` 가 매번 다시
    세팅하므로 값과 화면은 어긋나지 않는다.

    `usage:` 줄은 건드리지 않는다. 그 줄이 보여주는 것은 문장이 아니라 명령 문법
    (`sage [--lang {ko,en}] <command> ...`)이고, 명령·옵션은 어느 언어에서도 그대로다.
    """

    language: str = "ko"

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("{}: {}: {}\n".format(
            self.prog, tr(self.language, "cli.argparse.error_label"),
            localize_argparse_message(self.language, message)))
        raise SystemExit(2)


def build_parser(context: LanguageContext | None = None) -> argparse.ArgumentParser:
    context = context or LanguageContext()
    LocalizedParser.language = context.language
    parser = LocalizedParser(
        prog="sage",
        description=tr(context, "cli.root.description"),
        epilog=(tr(context, "cli.root.epilog") + "\n"
                + tr(context, "cli.root.switch_hint") + "\n"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help=tr(context, "cli.root.help_option"))
    parser.add_argument("--version", action="version", version=f"sage {__version__}",
                        help=tr(context, "cli.root.version_option"))
    # scan 이 이미 읽었지만 parser 에도 선언해야 한다 — 없으면 argparse 가 unknown option 으로
    # 거부하고, help 에도 안 보여 사용자가 존재를 알 방법이 없다.
    parser.add_argument("--lang", choices=list(INTERFACE_LANGUAGES),
                        help=tr(context, "cli.root.lang_option"))
    parser._positionals.title = tr(context, "cli.root.positionals_title")
    parser._optionals.title = tr(context, "cli.root.optionals_title")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True
    for mod in _COMMANDS:
        mod.register(sub, context)
    return parser


def _harden_io_encoding():
    # audit 3회차 P1: 비 UTF-8 로케일(PYTHONIOENCODING=ascii 등)에서 한글/이모지 출력 시
    # UnicodeEncodeError 스택트레이스 노출 방지 → errors="replace" 로 재구성.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


# 인자 없이 `sage` 만 친 사람은 아직 이 도구의 언어를 고른 적이 없다. 그래서 이 한 화면만
# 한영을 함께 낸다. argparse 의 usage 오류(exit 2)로 끝내면 "명령이 틀렸다"로 읽혀 다음에
# 무엇을 할지가 안 보인다.
_DISCOVERY = (
    "SAGE 명령을 시작하려면 도움말을 확인하세요.\n"
    "한국어 도움말: sage --help\n"
    "\n"
    "To get started with SAGE, open the help page.\n"
    "English help: sage --lang en --help"
)


def main(argv: list[str] | None = None) -> int:
    _harden_io_encoding()
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print(_DISCOVERY)
        return 0
    try:
        context = context_for(argv)
    except LanguageArgumentError as error:
        # 언어 선택 자체가 실패했으므로 어느 언어로 말해야 할지 모른다 — 양쪽으로 말한다.
        print(error.bilingual(), file=sys.stderr)
        return 2
    if context.fallback_used:
        # 손상은 부재와 다르다. 부재는 정상이고 한국어가 계약이지만, 손상은 사용자가 골라 둔
        # 언어를 읽지 못한 상태다. 조용히 한국어로 뭉개면 `en` 으로 설정해 둔 사람은 설정이
        # 사라진 것을 알 방법이 없다. 어느 언어를 고르려 했는지 모르므로 `--lang` 실패와 같은
        # 이유로 한영을 함께 낸다. **판정은 바꾸지 않는다** — 경고만 내고 명령은 그대로 간다.
        print("\n".join(tr(lang, "cli.lang.local_damaged") for lang in ("ko", "en")),
              file=sys.stderr)
    parser = build_parser(context)
    args = parser.parse_args(argv)
    args._language_context = context
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
