"""sage absorb — 직접수정(산출물) → spec patch 제안 (반자동, §5.5 M3 / §5.6).

급한 직접수정/blocked diff 를 spec(SSOT)으로 되흡수. 자동 흡수 금지 → spec patch 제안만 출력,
사람 승인 후 generate/재추출.
- agent/skill(interpretive): 수정된 산출물에서 claims 재추출 → 현 claims.yml 과 typed claim 단위 diff
  (렌더 문장이 아니라 claim 비교 — interpretive 비결정성 회피).
- hook: 정본(core/adapter)은 hand-edit SSOT. manifest 스탬프 대비 hash divergence 감지 → 흡수 절차
  (spec 갱신 + generate 재스탬프/재생성 + validate) 제안.

unresolved 처리: 새로 한쪽-only 가 된 claim 은 unresolved 로 플래그(hard block 금지).
"""
import json
import os
import sys
from pathlib import Path

from sage.asset_paths import AssetPaths


def register(sub):
    p = sub.add_parser("absorb", help="직접 고친 생성 파일을 spec 수정안으로 되돌려 제안합니다")
    # --kind/--id 는 기본 absorb 에 필수, --from-retro 모드에선 불요(아래 run 에서 검증).
    p.add_argument("--kind", choices=["hook", "agent", "skill"])
    p.add_argument("--id")
    p.add_argument("--from-blocked-diff", action="store_true",
                   help="write guard 에 막힌 diff 를 재입력 없이 바로 patch 후보로 변환")
    p.add_argument("--from-retro", default=None, metavar="NOTE",
                   help="승인된(approved:true) retro human-gate 노트를 읽어 제안→자산 patch 후보로 변환(Loop C)")
    p.add_argument("--claude", default="", help="(agent/skill) 수정된 .claude 산출물 경로")
    p.add_argument("--codex", default="", help="(agent/skill) 수정된 .codex 산출물 경로")
    p.add_argument("--guide", default="", help="(agent/skill) AGENT_GUIDE 경로")
    p.add_argument("--config", default="", help="(agent/skill) ExtractConfig (module:VAR | *.json)")
    p.add_argument("--root", default=None)
    p.set_defaults(func=run)


def _claims_value_sets(path):
    """{id}.claims.yml → required/forbidden/allowlist/unresolved value 집합 (absorb diff 용).

    P2-7: 단일 canonical 리더(reverse_extract_common.load_claims_yaml) 경유 — 이전의 lossy 정규식
    파서를 제거하고 emitter(claims_to_yaml)와 같은 코덱으로 통일. caller 가 sys.path 에 harness 추가 후 호출."""
    import reverse_extract_common as rc
    d = rc.load_claims_yaml(path)
    pick = lambda key: {c["value"] for c in d.get(key, []) if isinstance(c, dict) and "value" in c}
    return {"required": pick("required_claims"), "forbidden": pick("forbidden_claims"),
            "allowlist": pick("runtime_delta_allowlist"), "unresolved": set(d.get("unresolved", []))}


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
    guide = Path(args.guide).read_text(encoding="utf-8") if args.guide and os.path.exists(args.guide) else ""
    new = rx.extract_claims(Path(args.claude).read_text(encoding="utf-8"),
                            Path(args.codex).read_text(encoding="utf-8"), guide, config)
    new_req = {c["value"] for c in new["required_claims"]}
    new_fb = {c["value"] for c in new["forbidden_claims"] if "value" in c}

    cur = _claims_value_sets(os.path.join(root, "docs", "sage_harness", subdir, f"{args.id}.claims.yml"))
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
        return ("sha256:" + hashlib.sha256(Path(p).read_bytes()).hexdigest()) if os.path.exists(p) else None

    manifest = json.loads(Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).read_text())
    entry = manifest.get("assets", {}).get(f"hooks/{args.id}")
    if not entry:
        print(f"[sage absorb] manifest 에 hooks/{args.id} 없음", file=sys.stderr)
        return 2

    paths = AssetPaths(root, "hook", args.id)   # 경로 규약 단일소스(P2-6)
    form = entry.get("form", "core_adapter")
    diverged, unstamped = [], []

    canon = paths.native if form == "native" else paths.core
    rec = entry.get("canonical_hash")
    if os.path.exists(canon):
        if not rec:
            unstamped.append(os.path.relpath(canon, root))
        elif sha(canon) != rec:
            diverged.append(("canonical", os.path.relpath(canon, root)))
    if form == "core_adapter":
        for rt in ("claude", "codex"):
            ap = paths.adapter(rt)
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


_RETRO_MECHANICAL = {"profile", "hook"}   # 결정론 강제 — profile 키 / hook spec
_RETRO_SEMANTIC = {"agent", "skill"}      # interpretive — spec intent/advisory_scope 보강


def _overlay_hint(p):
    """agent/skill retro proposal 의 install-safe overlay 후보 경로.

    retro JSON 은 아직 schema-less human-gate 제안이라 asset_id 가 없을 수 있다. 있으면 구체 경로,
    없으면 placeholder 로 출력해 사람이 어느 CORE 자산에 적용할지 정하게 한다.
    """
    target = p.get("target") if isinstance(p, dict) else None
    raw = p.get("asset_id") or p.get("id") or p.get("asset") or f"<{target}-id>"
    aid = str(raw).strip() or f"<{target}-id>"
    if aid.startswith("<") and aid.endswith(">"):
        safe = aid
    else:
        safe = "".join(ch if (ch.isalnum() or ch in "._-") else "-" for ch in os.path.basename(aid))
        safe = safe.strip(".-") or f"<{target}-id>"
    subdir = "agents" if target == "agent" else "skills"
    return f"sage/asset_overrides/{subdir}/{safe}.md"


def _parse_frontmatter_approved(text):
    """노트 frontmatter 의 approved 값 → True/False/None(없음). 의존성 0(미니 파서)."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fm = text[3:end]
    for line in fm.splitlines():
        s = line.strip()
        if s.startswith("approved:"):
            v = s.split(":", 1)[1].strip().strip('"').strip("'").lower()
            return v == "true"
    return None


def _extract_proposals(text):
    """`## 제안` 섹션 이후의 펜스 코드블록들을 순서대로 시도 → 첫 'JSON 배열' 블록 채택 → (list, None).
    설명용 비-json 블록이 앞서거나 fence 언어가 달라도 견고(codex B P2). 없음/실패 → (None, 사유)."""
    import re
    # 실제 헤딩 라인(줄 시작 '## 제안')에서만 자른다 — 안내문 안의 백틱 `## 제안` 언급이나
    # 그 앞 `## 요약` 섹션의 코드블록을 제안으로 오파싱하지 않도록(codex P2).
    sec = re.split(r"(?m)^##\s*제안.*$", text, maxsplit=1)
    if len(sec) < 2:
        return None, "## 제안 섹션을 찾지 못함"
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)\n```", sec[1], re.S)
    if not blocks:
        return None, "## 제안 섹션에 코드블록이 없음"
    last_err = "유효한 JSON 배열 블록 없음"
    for raw in blocks:
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception as e:
            last_err = f"제안 JSON 파싱 실패: {e}"
            continue
        if isinstance(data, list):
            return data, None
        last_err = "제안 블록이 JSON 배열이 아님"
    return None, last_err


def _absorb_from_retro(args) -> int:
    """승인된 retro 노트(Loop C)의 제안을 target 별 자산 patch *후보*로 변환(자동반영 없음, absorb 철학)."""
    path = args.from_retro
    if not os.path.exists(path):
        print(f"[sage absorb] retro 노트 없음: {path}", file=sys.stderr)
        return 2
    text = Path(path).read_text(encoding="utf-8")
    approved = _parse_frontmatter_approved(text)
    if approved is not True:
        print(f"[sage absorb] retro 노트가 승인되지 않음(frontmatter approved={approved}) — "
              f"사람이 검토 후 approved: true 로 바꿔야 반영 후보를 출력합니다(human gate)", file=sys.stderr)
        return 2
    proposals, err = _extract_proposals(text)
    if err:
        print(f"[sage absorb] {err}", file=sys.stderr)
        return 2

    print(f"== sage absorb --from-retro ({os.path.basename(path)}) — 자산 patch 후보 (자동반영 없음) ==")
    # target 이 str 일 때만 분류 — list/dict 등 unhashable target 의 set membership 크래시 방지(codex B).
    def _bucket(p):
        if not isinstance(p, dict) or not isinstance(p.get("target"), str):
            return "skip"
        t = p["target"]
        return "mech" if t in _RETRO_MECHANICAL else "sem" if t in _RETRO_SEMANTIC else "skip"
    mech = [p for p in proposals if _bucket(p) == "mech"]
    sem = [p for p in proposals if _bucket(p) == "sem"]
    skipped = [p for p in proposals if _bucket(p) == "skip"]

    if not proposals:
        print("제안 없음(빈 배열) — distill 결과가 비어 있습니다.")
        return 0

    def _show(p):
        ev = p.get("evidence") or []
        ev_s = ("; ".join(map(str, ev)) if isinstance(ev, list) else str(ev))
        print(f"  · [{p.get('target')}] {p.get('proposed_change', '(변경안 없음)')} "
              f"(confidence={p.get('confidence', '?')})")
        if p.get("pattern"):
            print(f"      패턴: {p['pattern']}")
        if ev_s:
            print(f"      근거: {ev_s}")

    if mech:
        print("\n【 기계적 누락 → profile / hook (결정론 강제) 】")
        for p in mech:
            _show(p)
        print("  적용: profile 키 수정(/sage-profile-modify) 또는 hook spec/코드 수정 → sage generate → sage validate")
        print("  주의: hook 은 결정론 런타임이므로 overlay 파일만으로 실행 동작을 바꾸지 않습니다.")
    if sem:
        print("\n【 의미적 누락 → agent / skill (install-safe overlay 우선) 】")
        for p in sem:
            _show(p)
            print(f"      overlay 후보: {_overlay_hint(p)}")
        print("  적용: CORE 렌더 직접수정 금지. 위 overlay 파일에 프로젝트별 규칙을 작성하세요.")
        print("        host 는 CORE 자산을 읽은 뒤 overlay 가 있으면 우선 적용합니다. install --force 에도 보존됩니다.")
        print("        범용화할 내용이면 이후 spec/CORE 반영은 별도 변경으로 승격하세요.")
    if skipped:
        print(f"\n⚠️  target 미지/누락 {len(skipped)}건 — target ∈ {{profile,hook,agent,skill}} 이어야 분류됨:")
        for p in skipped:
            if isinstance(p, dict):   # 비-dict 항목(예: 숫자)도 크래시 없이 표시(codex B P1)
                print(f"  · {p.get('proposed_change', '(변경안 없음)')!r} (target={p.get('target')})")
            else:
                print(f"  · {p!r} (dict 아님 — 제안 항목은 객체여야)")

    print("\n자동 반영하지 않음(SSOT 보호). 위 후보를 사람이 검토·적용 후 generate/validate 로 닫으세요.")
    return 0


def run(args) -> int:
    # --from-retro 모드: 승인 노트 → patch 후보(--kind/--id 불요).
    if args.from_retro:
        return _absorb_from_retro(args)
    if not args.kind or not args.id:
        print("[sage absorb] --kind 와 --id 가 필요합니다 (또는 --from-retro <노트>)", file=sys.stderr)
        return 2

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
