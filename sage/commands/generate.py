"""sage generate — spec-SSOT → 런타임 산출물 생성.

마스터 §5.4/§5.5: hook=결정론 생성(spec+canonical→adapter+등록), agent/skill=interpretive render.
이 CLI는 AI 편집도구(Write/Edit/apply_patch) 밖의 별도 프로세스 → write guard 대상이 아님 (§5.6 G3).
"""

from sage.commands._common import not_implemented


def register(sub):
    p = sub.add_parser("generate", help="spec → .claude/.codex 산출물 생성")
    p.add_argument("--kind", choices=["hook", "agent", "skill"], required=True)
    p.add_argument("--id", required=True, help="자산 id (docs/sage_harness/<kind>s/<id>.md)")
    p.add_argument("--write", action="store_true",
                   help="실제 파일 기록 (없으면 dry-run/diff)")
    p.add_argument("--target", choices=["host", "opposite", "both"], default="host",
                   help="opposite/both 는 cross_model on 일 때만")
    p.set_defaults(func=run)


def run(args) -> int:
    mode = "write" if args.write else "dry-run(diff)"
    return not_implemented(
        "generate",
        f"{args.kind}:{args.id} → target={args.target} ({mode}). "
        f"생성 후 .manifest.json 에 spec_hash/render_hash/claims_hash 스탬프",
    )
