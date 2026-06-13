"""sage absorb — 직접수정(산출물) → spec patch 제안 (반자동, §5.5 M3 / §5.6).

급한 직접수정/blocked diff 를 spec(SSOT)으로 되흡수. 자동 흡수 금지 → spec patch 제안만 출력,
사람 승인 후 generate/재추출. agent(interpretive): 수정된 산출물에서 claims 재추출 → 현 claims.yml 과
diff 를 결정론적으로 산출(렌더 문장이 아니라 typed claim 단위 비교 — interpretive 비결정성 회피).
hook: canonical script 직접 비교는 후속(v1 미구현 안내).

unresolved 처리: 새로 한쪽-only 가 된 claim 은 unresolved 로 플래그(hard block 금지).
"""
import os
import sys


def register(sub):
    p = sub.add_parser("absorb", help="직접수정 diff → spec patch 제안 (자동반영 없음)")
    p.add_argument("--kind", choices=["hook", "agent", "skill"], required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--from-blocked-diff", action="store_true",
                   help="write guard 에 막힌 diff 를 재입력 없이 바로 patch 후보로 변환")
    p.add_argument("--claude", default="", help="(agent) 수정된 .claude 산출물 경로")
    p.add_argument("--codex", default="", help="(agent) 수정된 .codex 산출물 경로")
    p.add_argument("--guide", default="", help="(agent) AGENT_GUIDE 경로")
    p.add_argument("--config", default="", help="(agent) ExtractConfig (module:VAR | *.json)")
    p.add_argument("--root", default=None)
    p.set_defaults(func=run)


def _load_claims_yaml(path):
    """{id}.claims.yml 의 required/forbidden/allowlist value 집합 추출 (간이 파서)."""
    vals = {"required": set(), "forbidden": set(), "allowlist": set(), "unresolved": set()}
    if not os.path.exists(path):
        return vals
    section = None
    import re
    for line in open(path, encoding="utf-8"):
        s = line.strip()
        if s.startswith("required_claims:"): section = "required"; continue
        if s.startswith("forbidden_claims:"): section = "forbidden"; continue
        if s.startswith("runtime_delta_allowlist:"): section = "allowlist"; continue
        if s.startswith("unresolved:"):
            m = re.search(r"\[(.*)\]", s)
            if m and m.group(1).strip():
                vals["unresolved"] = {x.strip().strip('"') for x in m.group(1).split(",")}
            section = None; continue
        if section and s.startswith("- "):
            mv = re.search(r'value:\s*"([^"]*)"', s)
            if mv:
                vals[section].add(mv.group(1))
    return vals


def _absorb_agent(args, root):
    """수정된 산출물에서 claims 재추출 → 현 spec claims.yml 과 typed diff → patch 제안."""
    sys.path.insert(0, os.path.join(root, "scripts", "sage_harness"))
    import reverse_extract_agent as rx
    from extract_agent import load_config

    if not (args.claude and args.codex):
        print("[sage absorb] agent 는 --claude/--codex (수정된 산출물 경로) 필요", file=sys.stderr)
        return 2
    config = load_config(args.config) if args.config else None
    guide = open(args.guide, encoding="utf-8").read() if args.guide and os.path.exists(args.guide) else ""
    new = rx.extract_claims(open(args.claude, encoding="utf-8").read(),
                            open(args.codex, encoding="utf-8").read(), guide, config)
    new_req = {c["value"] for c in new["required_claims"]}
    new_fb = {c["value"] for c in new["forbidden_claims"] if "value" in c}

    cur = _load_claims_yaml(os.path.join(root, "docs", "sage_harness", "agents", f"{args.id}.claims.yml"))
    added_req = sorted(new_req - cur["required"])
    removed_req = sorted(cur["required"] - new_req)
    added_fb = sorted(new_fb - cur["forbidden"])
    removed_fb = sorted(cur["forbidden"] - new_fb)
    new_unresolved = sorted(set(new["unresolved"]) - cur["unresolved"])

    print(f"== sage absorb (agent:{args.id}) — spec patch 제안 (자동반영 없음) ==")
    if not any([added_req, removed_req, added_fb, removed_fb, new_unresolved]):
        print("변경 없음 — 수정 산출물의 claims 가 현 spec 과 동일. (absorb 불필요)")
        return 0
    print("【 제안: docs/sage_harness/agents/%s.claims.yml 패치 】" % args.id)
    for v in added_req:   print(f"  + required:   {v}")
    for v in removed_req: print(f"  - required:   {v}")
    for v in added_fb:    print(f"  + forbidden:  {v}")
    for v in removed_fb:  print(f"  - forbidden:  {v}")
    for v in new_unresolved:
        print(f"  ⚠ unresolved: {v} (한쪽-only/근거부족 — 사람 확인 필요)")
    print("\n승인 시: 위 의도를 spec(intent/advisory_scope)에 반영 → "
          "sage 재추출(extract_agent --register) → validate. 자동 반영하지 않음(SSOT 보호).")
    return 0


def run(args) -> int:
    root = args.root or os.getcwd()
    # SAGE 루트 탐색
    cur = os.path.abspath(root)
    while not os.path.exists(os.path.join(cur, "docs", "sage_harness", ".manifest.json")):
        parent = os.path.dirname(cur)
        if parent == cur:
            print("[sage absorb] TOOL ERROR: manifest 미발견", file=sys.stderr)
            return 2
        cur = parent
    root = cur

    if args.kind == "agent":
        return _absorb_agent(args, root)
    # hook/skill: canonical 비교는 후속
    print(f"== sage absorb ({args.kind}:{args.id}) ==", file=sys.stderr)
    print(f"[미구현] {args.kind} absorb 는 후속. v1 은 agent claims diff 흡수만 구현.", file=sys.stderr)
    print("  hook: canonical script(.sh) 직접 비교 + spec/등록 재생성 / skill: procedure diff — 설계 후속.", file=sys.stderr)
    return 2
