"""sage validate — 스키마 · drift · staleness 검사.

마스터 §5.4/§5.6, 최종검증 §3/§6:
- hook: byte/parity + fixture regression + exit/output snapshot
- agent/skill: conformance(required/forbidden claim presence) + runtime_delta_allowlist + spec_hash staleness
- staleness = spec_hash 동일하나 render_hash 불일치 / generator·template version 불일치 / 스탬프 불일치 (세대 차이)
- conformance PASS/FAIL 은 deterministic checker 만. LLM judge 금지.
"""

from sage.commands._common import not_implemented


def register(sub):
    p = sub.add_parser("validate", help="스키마/drift/staleness 결정론 검사")
    p.add_argument("--check", action="store_true",
                   help="변경 감지/staleness 만 (수정 없음, CI/hook용)")
    p.add_argument("--kind", choices=["hook", "agent", "skill", "all"], default="all")
    p.add_argument("--id", default=None, help="단일 자산 검사")
    p.set_defaults(func=run)


def run(args) -> int:
    scope = f"{args.kind}:{args.id}" if args.id else args.kind
    return not_implemented(
        "validate",
        f"{scope} — manifest staleness + conformance(claim presence) + allowlist 위반 결정론 검사"
        f"{' (--check 모드)' if args.check else ''}",
    )
