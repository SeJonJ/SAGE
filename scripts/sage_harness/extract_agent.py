#!/usr/bin/env python3
"""extract_agent — agent 자산 reverse-extract 재현 가능 드라이버 (커밋된 진입점, 자가점검 R5).

엔진(reverse_extract_agent)은 도메인값 0. 이 드라이버가 입력(claude/codex/guide)+ExtractConfig 를 받아
결정론적으로 spec.md 초안 + {id}.claims.yml 을 산출한다. config 주입형이라 **어떤 프로젝트든** 자기 config 로 사용 가능(독립).

사용:
  python3 extract_agent.py --id <id> --claude <a.md> --codex <b.md> --guide <AGENT_GUIDE.md> \
      --config <yourproject_config>:YOUR_EXTRACT_CONFIG --out-dir docs/sage_harness/agents [--write]
  --config 미지정 시 엔진 DEFAULT(범용, owned_paths 미추출). JSON 파일 경로도 허용.
  (ChatForYou 참조 인스턴스는 extract_config_chatforyou:CHATFORYOU_EXTRACT_CONFIG)
"""
import argparse
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reverse_extract_agent as rx  # noqa: E402


def load_config(spec):
    """config 로드: 'module:VAR'(python) | '*.json'(파일) | None(DEFAULT)."""
    if not spec:
        return None
    if spec.endswith(".json"):
        with open(spec, encoding="utf-8") as f:
            return json.load(f)
    mod, _, var = spec.partition(":")
    m = importlib.import_module(mod)
    return getattr(m, var) if var else getattr(m, "CONFIG")


def extract(agent_id, claude_path, codex_path, guide_path, config):
    """입력 → (spec_md, claims_yaml) 결정론 산출. (write 는 호출자가)."""
    claude = open(claude_path, encoding="utf-8").read()
    codex = open(codex_path, encoding="utf-8").read()
    guide = open(guide_path, encoding="utf-8").read() if guide_path and os.path.exists(guide_path) else ""
    claims = rx.extract_claims(claude, codex, guide, config)
    return rx.spec_draft(agent_id, claude, codex, claims), rx.claims_to_yaml(claims), claims


def main(argv=None):
    p = argparse.ArgumentParser(description="agent reverse-extract 드라이버 (재현 가능)")
    p.add_argument("--id", required=True)
    p.add_argument("--claude", required=True)
    p.add_argument("--codex", required=True)
    p.add_argument("--guide", default="")
    p.add_argument("--config", default="", help="module:VAR | *.json | (없으면 DEFAULT 범용)")
    p.add_argument("--out-dir", default="docs/sage_harness/agents")
    p.add_argument("--write", action="store_true", help="파일 기록 (없으면 stdout 미리보기)")
    args = p.parse_args(argv)

    config = load_config(args.config)
    spec_md, claims_yaml, claims = extract(args.id, args.claude, args.codex, args.guide, config)

    if args.write:
        os.makedirs(args.out_dir, exist_ok=True)
        with open(os.path.join(args.out_dir, f"{args.id}.md"), "w", encoding="utf-8") as f:
            f.write(spec_md)
        with open(os.path.join(args.out_dir, f"{args.id}.claims.yml"), "w", encoding="utf-8") as f:
            f.write(claims_yaml)
        print(f"✅ wrote {args.out_dir}/{args.id}.md + .claims.yml "
              f"(required={len(claims['required_claims'])}, unresolved={len(claims['unresolved'])})")
        print("   ※ manifest 등록은 sage generate/validate 흐름에서. spec_hash/claims_hash 갱신 필요.")
    else:
        print("=== spec.md (draft) ===\n" + spec_md)
        print("=== claims.yml ===\n" + claims_yaml)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
