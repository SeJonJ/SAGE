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
import re
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


def frontmatter_value(text, key):
    """노트 frontmatter 의 <key> scalar 값 → str. 없음/비-scalar → None. 의존성 0(미니 파서).

    quote 인지 + 인라인 주석 제거. 순진하게 `strip('"')` 만 하면 `run_id: "rl-a" # note` 가
    `rl-a" # note` 로 읽혀, 사람이 주석 한 줄 달았다고 run 대조가 오탐한다(codex 재검토 P2).
    리스트/맵(`[`·`{` 시작)은 scalar 가 아니므로 None — 호출자가 불일치로 처리한다.
    """
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    for line in text[3:end].splitlines():
        s = line.strip()
        if not s.startswith(key + ":"):
            continue
        v = s.split(":", 1)[1].strip()
        if v[:1] in ('"', "'"):                 # 따옴표 안의 `:`·`#` 는 값의 일부
            q, rest = v[0], v[1:]
            eq = rest.find(q)
            return rest[:eq] if eq != -1 else rest
        v = v.split(" #", 1)[0].strip()         # 인라인 주석(` #` 앞 공백 필수 — YAML 규칙)
        return None if v[:1] in ("[", "{") else (v or None)
    return None


def _parse_frontmatter_approved(text):
    """노트 frontmatter 의 approved 값 → True/False/None(없음)."""
    v = frontmatter_value(text, "approved")
    return None if v is None else v.lower() == "true"


_FENCE = re.compile(r"^\s*```+\s*([A-Za-z0-9_+-]*)\s*$")
_PROPOSAL_HEADING = re.compile(r"^##\s*제안")
# 섹션 경계 — 임의 레벨 헤딩 / 수평선 / <details>. 반드시 **펜스 밖**에서만 판정한다:
# 코드블록 안의 `---` 나 `### …` 는 마크다운상 본문 텍스트지 경계가 아니다.
_SECTION_BOUNDARY = re.compile(r"^(?:#{1,6}\s|---+\s*$|<details\b)")


def _fenced_blocks_in_proposal_section(text):
    """`## 제안` 섹션(펜스 밖 경계까지)의 코드블록 → [(lang, content)]. 섹션 없음 → None.

    fence 상태를 추적하는 단일 스캐너다. 이전의 정규식 split 방식은 펜스를 모르기 때문에
    ① 설명용 블록 안의 `---` 를 섹션 끝으로 오인하고 ② `### 증거` 같은 h3 를 경계로 못 봐서
    증거 블록의 `[]` 를 제안으로 오독했다(둘 다 codex 재검토에서 실증).
    """
    lines = text.splitlines()
    in_fence = False
    fence_lang = ""
    started = False          # `## 제안` 헤딩을 지났는가
    buf, blocks = [], []
    for line in lines:
        m = _FENCE.match(line)
        if m:
            if in_fence:
                if started:
                    blocks.append((fence_lang, "\n".join(buf)))
                in_fence, buf = False, []
            else:
                in_fence, fence_lang, buf = True, (m.group(1) or "").lower(), []
            continue
        if in_fence:
            buf.append(line)
            continue
        # --- 여기부터는 펜스 밖 ---
        if not started:
            if _PROPOSAL_HEADING.match(line):
                started = True
            continue
        if _SECTION_BOUNDARY.match(line):
            break            # 섹션 끝(다음 헤딩/구분선/<details>)
    if not started:
        return None
    return blocks


def _is_proposal_candidate(lang, content):
    """제안 데이터로 볼 블록인가. `json` 펜스이거나 JSON 배열처럼 시작하는 블록만.

    `{` 로 시작하는 설명용 프로즈(예: `{패턴을 여기 적으세요}`)를 데이터로 오인해 하드 실패시키면,
    '프로즈 블록은 건너뛴다'는 기존 계약이 깨진다(codex 재검토 P1). 제안은 항상 JSON *배열*이므로
    무-언어 블록은 `[` 로 시작할 때만 후보로 본다.
    """
    return lang == "json" or content.lstrip().startswith("[")


def _extract_proposals(text):
    """`## 제안` 섹션의 첫 제안 후보 블록 → (list, None). 없음/실패 → (None, 사유).

    마스킹 금지: 후보 블록이 파싱에 실패하면 뒤 블록으로 구제하지 않고 즉시 실패한다. 그러지 않으면
    뒤쪽 증거 블록의 `[]` 가 망가진 제안을 덮어 '제안 0건'으로 통과한다(codex P1).
    """
    blocks = _fenced_blocks_in_proposal_section(text)
    if blocks is None:
        return None, "## 제안 섹션을 찾지 못함"
    if not blocks:
        return None, "## 제안 섹션에 코드블록이 없음"
    for lang, content in blocks:
        raw = content.strip()
        if not raw or not _is_proposal_candidate(lang, raw):
            continue         # 설명용 프로즈 블록 — 데이터 아님
        try:
            data = json.loads(raw)
        except Exception as e:
            return None, f"제안 JSON 파싱 실패: {e}"
        if not isinstance(data, list):
            return None, "제안 블록이 JSON 배열이 아님"
        return data, None
    return None, "유효한 JSON 배열 블록 없음"


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
        print("  적용: CORE 렌더 직접수정 금지. `/sage-asset-override` 로 위 overlay 파일을 작성하세요")
        print("        (게이트 완화 여부를 확인하고 sage/asset_overrides/** 에 기록).")
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
