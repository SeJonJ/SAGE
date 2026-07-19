"""SAGE CLI 진입점 — 서브커맨드 디스패치.

각 서브커맨드 모듈은 `register(subparsers)` 와 `run(args) -> int` 를 제공한다.
현 단계는 스캐폴드: 시그니처는 최종검증 §5 / 마스터 설계 §13 부트스트랩에 맞추되
로직은 단계적으로 채운다.
"""

import argparse
import sys
import textwrap

from sage import __version__
from sage.commands import (install, generate, validate, asset_check, review, absorb, doctor, change,
                           override, review_loop, retro, knowledge, sync_overlays, acceptance_waiver,
                           authority, models, context)

_COMMANDS = [install, generate, validate, asset_check, review, absorb, doctor, change, override,
             review_loop, retro, knowledge, sync_overlays, acceptance_waiver, authority, models, context]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sage",
        description="SAGE는 Claude/Codex 프로젝트에 규칙 파일, hook, agent spec을 설치하고 검증하는 CLI입니다.",
        epilog=textwrap.dedent("""\
            기본 사용 순서:
              1. sage install --host codex --skill-scope project-local
                                                 # 또는 --skill-scope global
              2. sage generate --kind hook --write
              3. sage validate

            각 명령의 자세한 옵션:
              sage <command> --help
            """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help="도움말을 보여주고 종료합니다")
    parser.add_argument("--version", action="version", version=f"sage {__version__}", help="설치된 SAGE 버전을 보여줍니다")
    parser._positionals.title = "명령어"
    parser._optionals.title = "옵션"
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


def main(argv: list[str] | None = None) -> int:
    _harden_io_encoding()
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
