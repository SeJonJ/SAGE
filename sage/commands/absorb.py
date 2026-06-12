"""sage absorb — 직접수정(산출물) → spec patch 제안 (반자동).

마스터 §5.5 M3 / §5.6: 급한 직접수정/blocked diff 를 spec(SSOT)으로 되흡수.
- 자동 흡수 금지 → spec patch 제안 후 사람 승인 → 재생성 → regression.
- {{PEER_*}} placeholder 복원 실패 시 hard block 금지 → unresolved_questions 로 플래그.
"""

from sage.commands._common import not_implemented


def register(sub):
    p = sub.add_parser("absorb", help="직접수정 diff → spec patch 제안")
    p.add_argument("--kind", choices=["hook", "agent", "skill"], required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--from-blocked-diff", action="store_true",
                   help="write guard 에 막힌 diff 를 재입력 없이 바로 patch 후보로 변환")
    p.set_defaults(func=run)


def run(args) -> int:
    src = "blocked diff" if args.from_blocked_diff else "산출물 현재상태 vs 마지막 render"
    return not_implemented(
        "absorb",
        f"{args.kind}:{args.id} — {src} 를 분석해 spec patch 제안 생성 "
        f"(placeholder reverse-map, 복원불가 시 unresolved). 자동반영 없음, 사람 승인 대기",
    )
