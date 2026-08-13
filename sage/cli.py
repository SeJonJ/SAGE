"""SAGE CLI 진입점 — 서브커맨드 디스패치.

각 서브커맨드 모듈은 `register(subparsers)` 와 `run(args) -> int` 를 제공한다.
현 단계는 스캐폴드: 시그니처는 최종검증 §5 / 마스터 설계 §13 부트스트랩에 맞추되
로직은 단계적으로 채운다.
"""

import argparse
import sys

from sage import __version__
from sage.i18n import LanguageContext, tr
from sage.i18n.context import INTERFACE_LANGUAGES
from sage.i18n.parser import LanguageArgumentError, context_for
from sage.commands import (install, generate, validate, asset_check, review, absorb, doctor, change,
                           override, review_loop, retro, knowledge, sync_overlays, acceptance_waiver,
                           authority, models, context, feedback, cycle, fast_cycle)

_COMMANDS = [install, generate, validate, asset_check, review, absorb, doctor, change, override,
             review_loop, retro, knowledge, sync_overlays, acceptance_waiver, authority, models, context,
             feedback, cycle, fast_cycle]


def build_parser(context: LanguageContext | None = None) -> argparse.ArgumentParser:
    context = context or LanguageContext()
    parser = argparse.ArgumentParser(
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
        mod.register(sub)
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
    parser = build_parser(context)
    args = parser.parse_args(argv)
    args._language_context = context
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
