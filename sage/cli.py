"""SAGE CLI 진입점 — 서브커맨드 디스패치.

각 서브커맨드 모듈은 `register(subparsers)` 와 `run(args) -> int` 를 제공한다.
현 단계는 스캐폴드: 시그니처는 최종검증 §5 / 마스터 설계 §13 부트스트랩에 맞추되
로직은 단계적으로 채운다.
"""

import argparse
import sys

from sage import __version__
from sage.commands import install, generate, validate, review, absorb, doctor, change

_COMMANDS = [install, generate, validate, review, absorb, doctor, change]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sage",
        description="System for Agentic Governance & Engineering",
    )
    parser.add_argument("--version", action="version", version=f"sage {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True
    for mod in _COMMANDS:
        mod.register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
