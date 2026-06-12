"""sage change "자연어 의도" — 최소 라우터 (v1.1, 골격만).

최종검증 §5-9: 자산 종류/영향도를 판별해 generate 또는 absorb 로 분기.
완전한 자연어 의도 파싱은 v1.1. v1 은 라우팅 골격만.
"""

from sage.commands._common import not_implemented


def register(sub):
    p = sub.add_parser("change", help='자연어 의도 → generate/absorb 라우팅 (v1.1)')
    p.add_argument("intent", help='예: "backend agent 가 테스트도 보게 해줘"')
    p.set_defaults(func=run)


def run(args) -> int:
    return not_implemented(
        "change",
        f'"{args.intent}" → 자산 종류/영향도 판별 후 spec 수정 + generate(또는 absorb) 분기',
    )
