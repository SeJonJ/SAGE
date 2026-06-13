"""sage absorb — 직접수정(산출물) → spec patch 제안 (반자동, §5.5 M3 / §5.6).

급한 직접수정/blocked diff 를 spec(SSOT)으로 되흡수. 자동 흡수 금지 → spec patch 제안만 출력,
사람 승인 후 generate/재추출.
- agent/skill(interpretive): 수정된 산출물에서 claims 재추출 → 현 claims.yml 과 typed claim 단위 diff
  (렌더 문장이 아니라 claim 비교 — interpretive 비결정성 회피).
- hook: 정본(core/adapter)은 hand-edit SSOT. manifest 스탬프 대비 hash divergence 감지 → 흡수 절차
  (spec 갱신 + generate 재스탬프/재생성 + validate) 제안.

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
    p.add_argument("--claude", default="", help="(agent/skill) 수정된 .claude 산출물 경로")
    p.add_argument("--codex", default="", help="(agent/skill) 수정된 .codex 산출물 경로")
    p.add_argument("--guide", default="", help="(agent/skill) AGENT_GUIDE 경로")
    p.add_argument("--config", default="", help="(agent/skill) ExtractConfig (module:VAR | *.json)")
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


def _absorb_interpretive(args, root, kind):
    """interpretive 자산(agent/skill): 수정된 산출물에서 claims 재추출 → 현 claims.yml 과 typed diff → patch 제안.

    agent/skill 는 추출기만 다름(reverse_extract_agent / reverse_extract_skill). 렌더 문장이 아니라
    typed claim 단위 비교(interpretive 비결정성 회피)."""
    sys.path.insert(0, os.path.join(root, "scripts", "sage_harness"))
    from extract_agent import load_config
    if kind == "agent":
        import reverse_extract_agent as rx
        subdir, driver = "agents", "extract_agent"
    else:
        import reverse_extract_skill as rx
        subdir, driver = "skills", "extract_skill"

    if not (args.claude and args.codex):
        print(f"[sage absorb] {kind} 는 --claude/--codex (수정된 산출물 경로) 필요", file=sys.stderr)
        return 2
    config = load_config(args.config) if args.config else None
    guide = open(args.guide, encoding="utf-8").read() if args.guide and os.path.exists(args.guide) else ""
    new = rx.extract_claims(open(args.claude, encoding="utf-8").read(),
                            open(args.codex, encoding="utf-8").read(), guide, config)
    new_req = {c["value"] for c in new["required_claims"]}
    new_fb = {c["value"] for c in new["forbidden_claims"] if "value" in c}

    cur = _load_claims_yaml(os.path.join(root, "docs", "sage_harness", subdir, f"{args.id}.claims.yml"))
    added_req = sorted(new_req - cur["required"])
    removed_req = sorted(cur["required"] - new_req)
    added_fb = sorted(new_fb - cur["forbidden"])
    removed_fb = sorted(cur["forbidden"] - new_fb)
    new_unresolved = sorted(set(new["unresolved"]) - cur["unresolved"])

    print(f"== sage absorb ({kind}:{args.id}) — spec patch 제안 (자동반영 없음) ==")
    if not any([added_req, removed_req, added_fb, removed_fb, new_unresolved]):
        print("변경 없음 — 수정 산출물의 claims 가 현 spec 과 동일. (absorb 불필요)")
        return 0
    print(f"【 제안: docs/sage_harness/{subdir}/{args.id}.claims.yml 패치 】")
    for v in added_req:   print(f"  + required:   {v}")
    for v in removed_req: print(f"  - required:   {v}")
    for v in added_fb:    print(f"  + forbidden:  {v}")
    for v in removed_fb:  print(f"  - forbidden:  {v}")
    for v in new_unresolved:
        print(f"  ⚠ unresolved: {v} (한쪽-only/근거부족 — 사람 확인 필요)")
    print(f"\n승인 시: 위 의도를 spec(intent/advisory_scope)에 반영 → "
          f"sage 재추출({driver} --register) → validate. 자동 반영하지 않음(SSOT 보호).")
    return 0


def _absorb_hook(args, root):
    """hook: canonical/adapter 정본은 hand-edit SSOT. manifest 스탬프 대비 divergence 를 감지해
    흡수 절차(spec 갱신 + 재생성/재스탬프)를 제안한다(자동반영 없음). interpretive 와 달리 claims 가 아니라
    hash 비교 — 정본을 직접 고친 경우 무엇이 바뀌었는지와 후속 절차를 알려준다."""
    import hashlib
    import json

    def sha(p):
        return ("sha256:" + hashlib.sha256(open(p, "rb").read()).hexdigest()) if os.path.exists(p) else None

    manifest = json.load(open(os.path.join(root, "docs", "sage_harness", ".manifest.json")))
    entry = manifest.get("assets", {}).get(f"hooks/{args.id}")
    if not entry:
        print(f"[sage absorb] manifest 에 hooks/{args.id} 없음", file=sys.stderr)
        return 2

    H = os.path.join(root, "scripts", "sage_harness", "hooks")
    snake = args.id.replace("-", "_")
    form = entry.get("form", "core_adapter")
    diverged, unstamped = [], []

    canon = os.path.join(H, f"{args.id}.sh") if form == "native" else os.path.join(H, f"{snake}_core.py")
    rec = entry.get("canonical_hash")
    if os.path.exists(canon):
        if not rec:
            unstamped.append(os.path.relpath(canon, root))
        elif sha(canon) != rec:
            diverged.append(("canonical", os.path.relpath(canon, root)))
    if form == "core_adapter":
        for rt in ("claude", "codex"):
            ap = os.path.join(H, "adapters", rt, f"{args.id}.sh")
            arec = (entry.get("adapter_hash") or {}).get(rt)
            if os.path.exists(ap):
                if not arec:
                    unstamped.append(os.path.relpath(ap, root))
                elif sha(ap) != arec:
                    diverged.append((f"adapter:{rt}", os.path.relpath(ap, root)))

    print(f"== sage absorb (hook:{args.id}) — 정본 직접수정 비교 (자동반영 없음) ==")
    if not diverged and not unstamped:
        print("변경 없음 — canonical/adapter 가 manifest 스탬프와 일치. (absorb 불필요)")
        return 0
    if unstamped:
        print("【 미스탬프(아직 hash 없음) — generate 로 스탬프 필요 】")
        for p in unstamped:
            print(f"  · {p}")
    if diverged:
        print("【 정본 직접수정 감지 — manifest 스탬프와 다름 】")
        for what, path in diverged:
            print(f"  ~ {what}: {path}")
    print("\n흡수 절차(자동 아님):")
    print(f"  1. 동작/계약이 바뀌었으면 spec 갱신: docs/sage_harness/hooks/{args.id}.md (intent/runtime_bindings/tests)")
    print(f"  2. sage generate --kind hook --id {args.id} --write   → shim 재생성 + manifest 재스탬프")
    print(f"  3. sage validate --kind hook --id {args.id}           → drift/regression 확인")
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

    if args.kind in ("agent", "skill"):
        return _absorb_interpretive(args, root, args.kind)
    return _absorb_hook(args, root)
