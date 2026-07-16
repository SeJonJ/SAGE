"""오버레이 합성 자격 분류(gate-classification) — 단일 resolver.

이슈 #5 봉쇄의 핵심: CORE 자산 오버레이가 물리 반영되면 "read overlay before CORE" 프로즈
보다 강하게 게이트-완화를 심을 수 있다(승인 조작 등). 그런데 게이트 완화 여부를 내용
린트로 막는 건 휴리스틱이라 우회 가능(theater). 그래서 **자격 단계**에서 막는다:

  (a) 게이트 비보유 or (b) 게이트가 자산 텍스트를 읽지 않는 독립 결정론 오라클(hook/CI)로
      강제됨 → 물리 합성 허용(compose).
  (c) 게이트 보유하나 아직 오라클 미보증 → 오버레이 경로 전면 차단(blocked): 합성도
      프로즈-read 도 없음. 오버레이 파일이 있으면 validate FAIL.

기본값은 fail-closed: **입증된 (a)/(b)만 compose**, 미분류/미지 자산은 전부 blocked.
(c)→(b) 재분류(오버레이 개방)는 SD-8 결정론 review/phase 오라클 완성에 의존한다.

install·sync·session-start(L1)·validate 는 오버레이를 다룰 때 반드시 이 모듈의 classify /
expected_block 을 경유한다 — 분류를 우회하는 합성 경로가 없어야 한다.
"""
import os

from sage import overlay_common as _oc

# CORE 자산 정본 roster. install._CORE_AGENTS / _CORE_SKILLS / _CORE_BOOTSTRAP_SKILL 과
# 일치해야 한다(test_overlay_classify 가 대조). 여기 두는 이유: install 이 이 모듈을 import
# 하므로 역참조(circular) 회피.
CORE_IDS = {
    "agents": frozenset({
        "leader", "implementer-a", "implementer-b", "qa", "reviewer", "convention-checker",
    }),
    "skills": frozenset({
        "sage-cycle", "sage-plan", "sage-team", "sage-review", "sage-asset",
        "sage-profile-modify", "sage-asset-override", "sage-init",
    }),
    "framework": frozenset({"AGENT_GUIDE", "CLAUDE", "CODEX", "AGENTS"}),
}

# 물리 합성 허용 자산 (a)/(b). Phase 1 은 입증된 비게이트 워커만 연다:
# implementer-a/-b 는 순수 실행 워커라 어떤 워크플로 게이트도 소유하지 않는다 → 오버레이가
# 텍스트로 게이트를 완화해도 완화할 게이트 자체가 없다. 나머지 CORE 자산은 게이트 보유
# 또는 미검증이라 전부 blocked(fail-closed) — (c)→(b) 개방은 SD-8 이후.
COMPOSE_ALLOWED = frozenset({
    ("agents", "implementer-a"),
    ("agents", "implementer-b"),
    ("framework", "AGENT_GUIDE"),
    ("framework", "CLAUDE"),
    ("framework", "CODEX"),
    ("framework", "AGENTS"),
})

# 명시적 (c) — 게이트 보유하나 오라클 미보증(문서화용; 실제 차단은 COMPOSE_ALLOWED 미포함으로 성립).
GATE_BEARING_UNBACKED = frozenset({
    ("agents", "leader"), ("agents", "qa"), ("agents", "reviewer"),
    ("skills", "sage-cycle"), ("skills", "sage-plan"), ("skills", "sage-team"),
    ("skills", "sage-review"), ("skills", "sage-profile-modify"),
})


def is_core(kind, id):
    """(kind,id) 가 유효한 CORE 자산인가. 오타/미지 id 하드-리포트 판정에 쓴다."""
    return id in CORE_IDS.get(kind, ())


def classify(kind, id):
    """오버레이 합성 자격 → 'compose' | 'blocked'. 미분류/미지는 전부 blocked(fail-closed)."""
    return "compose" if (kind, id) in COMPOSE_ALLOWED else "blocked"


def overlay_path(root, kind, id):
    """오버레이 파일 경로(존재 여부 무관)."""
    return os.path.join(root, "sage", "asset_overrides", kind, f"{id}.md")


def overlay_files(root):
    """sage/asset_overrides/{agents,skills,framework}/*.md 전부 열거 → [(kind, id, path)].

    render_targets(유효 CORE id 만) 와 달리 실제 존재하는 오버레이 파일을 그대로 연다 — 오타/미지
    id(예: reviwer.md) 도 잡아 하드-리포트할 수 있도록. install·sync·validate 가 공유.
    """
    found = []
    base = os.path.join(root, "sage", "asset_overrides")
    for kind in ("agents", "skills", "framework"):
        d = os.path.join(base, kind)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".md"):
                found.append((kind, fn[:-3], os.path.join(d, fn)))
    return found


def overlay_text(root, kind, id):
    """오버레이 파일을 LF 로 읽어 (text, error) 반환. 파일 없으면 (None, None)."""
    p = overlay_path(root, kind, id)
    if not os.path.isfile(p):
        return None, None
    return _oc.read_text_lf(p)


def expected_block(kind, id, root):
    """이 자산에 반영돼야 할 관리 블록 문자열 → str.

    - blocked((c)/미분류): 항상 '' — 합성하지 않는다(오버레이를 읽지도 넣지도 않음).
    - compose((a)/(b)): 오버레이가 있으면 compose_block, 없으면 ''.
    반환 (block, error). error 는 오버레이 읽기 실패/토큰 주입 시.
    """
    if classify(kind, id) == "blocked":
        return "", None
    text, err = overlay_text(root, kind, id)
    if err:
        return "", err
    if text is None:
        return "", None
    if kind == "framework":
        from sage.overlay_lint import _split_frontmatter
        _meta, text, ferr = _split_frontmatter(text)
        if ferr:
            return "", ferr
    verr = _oc.validate_overlay(text)
    if verr:
        return "", verr
    return _oc.compose_block(text, kind, id), None
