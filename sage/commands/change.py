"""sage change "자연어 의도" — 최소 라우터 (v1, 결정론 키워드 매칭, LLM 배제).

최종검증 A3 + Codex 2R: v1 은 라우팅 안내까지(실제 spec 편집/generate 실행 X).
의도 → action(absorb|generate) 분류 + 자산 매칭(exact id / 토큰점수+kind보너스 / 모호·무매칭 분기) +
실행 명령 예시 + 매칭자산 review 상태(auto/review). 완전 NL 파싱은 v1.1.
"""

import json
import os
import re
import sys
from pathlib import Path

from sage.commands import validate as V
from sage.commands import review as R

# action 분류 — absorb 를 generate 보다 먼저 판정(이미 고친 산출물 흡수 우선). 그 외는 generate (default).
_ABSORB_KW = ["이미 고쳤", "이미 수정", "직접 수정", "직접수정", "생성물", "산출물", "blocked", "되돌려", "흡수"]
_KIND_HINT = {"hook": "hook", "hooks": "hook", "agent": "agent", "agents": "agent", "skill": "skill", "skills": "skill"}


def register(sub):
    p = sub.add_parser("change", help="하고 싶은 변경을 어떤 SAGE 명령으로 처리할지 안내합니다")
    p.add_argument("intent", help='예: "capture-declared-risk hook 고쳐줘"')
    p.add_argument("--root", default=None)
    p.set_defaults(func=run)


def _tokens(s):
    return {t for t in re.split(r"[\s/_\-]+", s.lower()) if len(t) >= 2}


def _classify_action(intent_low):
    if any(k in intent_low for k in _ABSORB_KW):
        return "absorb"
    return "generate"


def _kind_hint(intent_low):
    for k, v in _KIND_HINT.items():
        if k in intent_low:
            return v
    return None


def _score(intent_tokens, asset_id, kind_hint):
    body = asset_id.split("/", 1)[1] if "/" in asset_id else asset_id
    atoks = _tokens(body)
    if not atoks:
        return 0.0
    if body.lower() in " ".join(intent_tokens) or body.lower() in intent_tokens:
        return 1.0
    matched = len(intent_tokens & atoks)
    if matched == 0:
        return 0.0  # 토큰 매칭 0 → kind 보너스만으로 후보가 되지 않게(신규 흐름 유도)
    score = matched / len(atoks)
    if kind_hint and asset_id.startswith(kind_hint + "s/"):
        score += 0.15
    return score


def run(args):
    root = V._find_root(args.root)
    if not root:
        print("[sage change] TOOL ERROR: manifest 없음", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).read_text())
    except Exception as e:
        print(f"[sage change] TOOL ERROR: manifest 파싱 실패: {e}", file=sys.stderr)
        return 2
    assets = manifest.get("assets", {})

    intent = args.intent
    low = intent.lower()
    itoks = _tokens(intent)
    # exact id 우선
    exact = next((a for a in assets if (a.split("/", 1)[1].lower() in low)), None)
    action = _classify_action(low)
    kind = _kind_hint(low)

    print(f'== sage change — "{intent}" ==')
    print(f"의도 분류: action={action}" + (f", kind={kind}" if kind else ""))

    if action == "absorb":
        tgt = exact or "<id>"
        k = (exact.split("/")[0][:-1] if exact else (kind or "<kind>"))
        print("→ 결정: ABSORB (이미 고친 산출물을 spec 으로 흡수)")
        print(f"   명령: sage absorb --kind {k} --id {tgt.split('/')[-1] if exact else '<id>'} --from-blocked-diff")
        return 0

    # generate 경로: 매칭 점수
    scored = sorted(((_score(itoks, a, kind), a) for a in assets), reverse=True)
    top = scored[0] if scored else (0.0, None)
    ties = [a for s, a in scored if s == top[0] and s > 0]

    if exact or (top[0] >= 0.4 and len(ties) == 1):
        tgt = exact or top[1]
        # review 상태
        entry = assets[tgt]
        if tgt.startswith("hooks/"):
            sev, _ = V._validate_hook(root, tgt, entry, run_regression=False)
        else:
            sev, _ = V._validate_interpretive(root, tgt, entry, run_regression=False)
        dec = R.auto_approve_decision(tgt, sev, entry)
        k = tgt.split("/")[0][:-1]
        print(f"→ 결정: GENERATE (기존 자산 수정) — 대상: {tgt}")
        print(f"   흐름: docs/sage_harness/{tgt.split('/')[0]}/{tgt.split('/')[-1]}.md (spec) 수정 → sage generate --kind {k} --id {tgt.split('/')[-1]} --write")
        print("   ※ generate 는 v1 stub(render=런타임 AI 영역). 현재는 spec 수정 후 런타임이 산출물을 렌더, validate/review 로 검증.")
        print(f"   현재 승인상태: {dec['decision']}" + (f" ({', '.join(dec['reasons'])})" if dec["reasons"] else ""))
        return 0

    if top[0] > 0 and (len(ties) > 1 or top[0] < 0.4):
        print("→ 모호: 후보 (—id 로 재시도)")
        for s, a in scored[:5]:
            if s > 0:
                print(f"   - {a} (score={s:.2f})")
        return 0

    # 무매칭 → 신규
    if kind:
        print(f"→ 결정: GENERATE (신규 {kind}) — sage generate --kind {kind} --id <id> --write")
        print(f"   먼저 docs/sage_harness/{kind}s/<id>.md (spec) 작성")
    else:
        print("→ 무매칭: --kind hook|agent|skill 를 지정하거나 자산 id 를 포함해 다시 시도하세요")
    return 0
