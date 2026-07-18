"""sage models: show host model candidates without network/model probes."""
import json

from sage.model_catalog import discover


def register(sub):
    parser = sub.add_parser("models", help="host 모델 후보와 검증 출처를 표시합니다")
    parser.add_argument("--host", choices=["claude", "codex"], required=True)
    parser.add_argument("--output", choices=["text", "json"], default="text")
    parser.add_argument("--codex-home", default=None, help="Codex cache root (기본 CODEX_HOME 또는 ~/.codex)")
    parser.set_defaults(func=run)


def run(args):
    result = discover(args.host, getattr(args, "codex_home", None))
    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"== sage models ({result['host']}) ==")
    print(f"  source       : {result['source']}")
    print(f"  verification : {result['verification']}")
    if result.get("fetched_at"):
        print(f"  fetched_at   : {result['fetched_at']} (stale={result['stale']})")
    for candidate in result["candidates"]:
        efforts = ",".join(candidate.get("reasoning_efforts") or []) or "n/a"
        print(f"  - {candidate['id']} ({candidate['display_name']}; effort={efforts})")
    for issue in result["issues"]:
        print(f"  note: {issue}")
    return 0

