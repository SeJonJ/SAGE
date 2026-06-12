"""sage install — host 택1 + 빈 스키마 profile + framework 배치 (부트스트랩 1단계).

마스터 §13: install → host_runtime 선택 + CORE 템플릿(빈 스키마 profile + roles + framework) 배치.
"""

from sage.commands._common import not_implemented


def register(sub):
    p = sub.add_parser("install", help="SAGE CORE 설치 (host 택1 + 빈 스키마 배치)")
    p.add_argument("--host", choices=["claude", "codex"], required=True,
                   help="host_runtime — PDCA를 실행하는 주 런타임 (Claude 특권화 금지)")
    p.add_argument("--prefix", default="sage", help="자산 네이밍 prefix")
    p.add_argument("--dest", default=".", help="설치 대상 프로젝트 루트")
    p.set_defaults(func=run)


def run(args) -> int:
    return not_implemented(
        "install",
        f"host={args.host}, prefix={args.prefix} 로 templates/project-profile.yaml(빈 스키마) "
        f"+ framework + CORE roles spec + 코어 hook spec 을 {args.dest} 에 배치",
    )
