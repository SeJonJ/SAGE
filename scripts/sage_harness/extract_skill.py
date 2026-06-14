#!/usr/bin/env python3
"""extract_skill — skill 자산 reverse-extract 재현 가능 드라이버 (커밋 진입점).

엔진(reverse_extract_skill)은 도메인값 0. config 주입형이라 어떤 프로젝트든 자기 config 로 사용(독립).
claude=`.claude/skills/{id}.md`, codex=`.codex/skills/{id}/SKILL.md`.

사용:
  python3 extract_skill.py --id <id> --claude <a.md> --codex <b/SKILL.md> --guide <AGENT_GUIDE.md> \
      --config <yourproject>:YOUR_EXTRACT_CONFIG --out-dir docs/sage_harness/skills [--write] [--register]
"""
import argparse
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reverse_extract_skill as rs  # noqa: E402


def load_config(spec):
    if not spec:
        return None
    if spec.endswith(".json"):
        import json
        with open(spec, encoding="utf-8") as f:
            return json.load(f)
    mod, _, var = spec.partition(":")
    m = importlib.import_module(mod)
    return getattr(m, var) if var else getattr(m, "CONFIG")


def extract(skill_id, claude_path, codex_path, guide_path, config):
    claude = Path(claude_path).read_text(encoding="utf-8")
    codex = Path(codex_path).read_text(encoding="utf-8")
    guide = Path(guide_path).read_text(encoding="utf-8") if guide_path and os.path.exists(guide_path) else ""
    claims = rs.extract_claims(claude, codex, guide, config)
    return rs.spec_draft(skill_id, claude, codex, claims), rs.claims_to_yaml(claims), claims


def main(argv=None):
    p = argparse.ArgumentParser(description="skill reverse-extract 드라이버 (재현 가능)")
    p.add_argument("--id", required=True)
    p.add_argument("--claude", required=True)
    p.add_argument("--codex", required=True)
    p.add_argument("--guide", default="")
    p.add_argument("--config", default="")
    p.add_argument("--out-dir", default="docs/sage_harness/skills")
    p.add_argument("--write", action="store_true")
    p.add_argument("--register", action="store_true")
    p.add_argument("--render-claude", default="")
    p.add_argument("--render-codex", default="")
    p.add_argument("--test", default="scripts/sage_harness/hooks/tests/test_reverse_extract_skill.py")
    args = p.parse_args(argv)

    config = load_config(args.config)
    spec_md, claims_yaml, claims = extract(args.id, args.claude, args.codex, args.guide, config)
    if args.write:
        os.makedirs(args.out_dir, exist_ok=True)
        Path(os.path.join(args.out_dir, f"{args.id}.md")).write_text(spec_md, encoding="utf-8")
        Path(os.path.join(args.out_dir, f"{args.id}.claims.yml")).write_text(claims_yaml, encoding="utf-8")
        print(f"✅ wrote {args.out_dir}/{args.id}.md + .claims.yml "
              f"(required={len(claims['required_claims'])}, unresolved={len(claims['unresolved'])})")
        if args.register:
            import manifest_util as mu
            root = mu.find_root(os.getcwd())
            if root:
                mu.upsert_skill(root, args.id, claude_render=args.render_claude, codex_render=args.render_codex,
                                test=args.test, unresolved=claims["unresolved"])
                print(f"✅ manifest 등록: skills/{args.id} (form:interpretive)")
            else:
                print("   ⚠️ manifest 미발견 — 등록 건너뜀", file=sys.stderr)
    else:
        print("=== spec.md (draft) ===\n" + spec_md)
        print("=== claims.yml ===\n" + claims_yaml)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
