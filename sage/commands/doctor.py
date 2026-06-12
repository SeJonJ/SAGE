"""sage doctor — 옵션 의존성 확인 + degrade 안내.

마스터 §13/§12: gstack / codegraph MCP / obsidian vault_path 설치 확인.
미충족은 에러가 아니라 degrade — 제한 기능을 명시한다 (graceful N/A).
"""

from sage.commands._common import not_implemented


def register(sub):
    p = sub.add_parser("doctor", help="옵션 의존성 점검 + degrade 안내")
    p.set_defaults(func=run)


def run(args) -> int:
    return not_implemented(
        "doctor",
        "cross_model(gstack/cross-invocation), codegraph(MCP), obsidian(vault_path) 설치 여부 점검 "
        "→ 미충족 옵션의 제한 기능 매트릭스 출력",
    )
