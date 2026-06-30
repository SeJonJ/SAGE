"""manifest_util — docs/sage_harness/.manifest.json 읽기/해시/엔트리 갱신 공용 헬퍼.

여러 곳(extract_agent, generate, 인라인 스크립트)에 흩어졌던 manifest hash 계산·엔트리 작성을 단일화.
schema/manifest.schema.json 의 필드 규약을 따른다. 결정론(정렬 + indent=2).
"""
import hashlib
import json
import os
import sys

MANIFEST_REL = os.path.join("docs", "sage_harness", ".manifest.json")


def sha256_of(path: str) -> str:
    with open(path, "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


def _derived_contract_version(module_name: str) -> str:
    """interpretive(agent/skill) adapter_contract_version 을 reverse_extract 모듈의 CONTRACT_VERSION 에서
    파생한다(하드코딩 '1' 제거 — R3 잔여 5-2). hook 의 contract_version_of(core) 와 같은 취지: 추출 계약이
    바뀌면 스탬프가 따라가 drift 를 표면화.
    하R1 반영: ① manifest_util 디렉토리를 sys.path 에 보장 → 스크립트·번들 양쪽에서 sibling 해석(번들에서
    영구 '1' 폴백 방지). ② ModuleNotFoundError 만 '1' 폴백 — 모듈 자체 깨짐(syntax 등)은 가리지 않고 surface.
    ③ CONTRACT_VERSION 이 비문자열/빈 값이면 '1' 폴백(None→'None' 스탬프 방지)."""
    import importlib
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return "1"
    cv = getattr(mod, "CONTRACT_VERSION", None)
    if isinstance(cv, str) and cv.strip():
        return cv
    if isinstance(cv, int):
        return str(cv)
    return "1"


def find_root(start: str = None) -> str | None:
    """가장 가까운 상위에서 .manifest.json 보유 디렉토리(SAGE 루트) 탐색."""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(cur, MANIFEST_REL)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def load(root: str) -> dict:
    with open(os.path.join(root, MANIFEST_REL), encoding="utf-8") as f:
        return json.load(f)


def save(root: str, manifest: dict) -> None:
    with open(os.path.join(root, MANIFEST_REL), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def upsert_agent(root: str, agent_id: str, *, claude_render: str, codex_render: str,
                 test: str, unresolved: list) -> dict:
    """agent(form:interpretive) 엔트리 갱신. spec/claims 는 docs/sage_harness/agents 에서 해시.

    claude_render/codex_render: 렌더 산출물(.claude/.codex agent .md) 경로(있으면 해시, 없으면 생략).
    """
    spec = os.path.join(root, "docs", "sage_harness", "agents", f"{agent_id}.md")
    claims = os.path.join(root, "docs", "sage_harness", "agents", f"{agent_id}.claims.yml")
    render = {}
    if claude_render and os.path.exists(claude_render):
        render["claude"] = sha256_of(claude_render)
    if codex_render and os.path.exists(codex_render):
        render["codex"] = sha256_of(codex_render)

    m = load(root)
    entry = m["assets"].get(f"agents/{agent_id}", {})
    entry.update({
        "spec_hash": sha256_of(spec),
        "claims_hash": sha256_of(claims),
        "adapter_contract_version": _derived_contract_version("reverse_extract_agent"),
        "conformance": "PASS",
        "form": "interpretive",
        "test": test,
        "risk": entry.get("risk", []),
        "unresolved": unresolved,
    })
    if render:
        entry["render_hash"] = render
    elif "render_hash" not in entry:
        entry["render_hash"] = {"claude": entry.get("spec_hash")}  # fallback: 최소 1키(schema minProperties)
    m["assets"][f"agents/{agent_id}"] = entry
    save(root, m)
    return entry


def upsert_skill(root: str, skill_id: str, *, claude_render: str, codex_render: str,
                 test: str, unresolved: list) -> dict:
    """skill(form:interpretive) 엔트리 갱신. agent 와 동일 구조, 경로만 skills/."""
    spec = os.path.join(root, "docs", "sage_harness", "skills", f"{skill_id}.md")
    claims = os.path.join(root, "docs", "sage_harness", "skills", f"{skill_id}.claims.yml")
    render = {}
    if claude_render and os.path.exists(claude_render):
        render["claude"] = sha256_of(claude_render)
    if codex_render and os.path.exists(codex_render):
        render["codex"] = sha256_of(codex_render)
    m = load(root)
    entry = m["assets"].get(f"skills/{skill_id}", {})
    entry.update({
        "spec_hash": sha256_of(spec),
        "claims_hash": sha256_of(claims),
        "adapter_contract_version": _derived_contract_version("reverse_extract_skill"),
        "conformance": "PASS",
        "form": "interpretive",
        "test": test,
        "risk": entry.get("risk", []),
        "unresolved": unresolved,
    })
    entry["render_hash"] = render or {"claude": entry["spec_hash"]}
    m["assets"][f"skills/{skill_id}"] = entry
    save(root, m)
    return entry


def refresh_hashes(root: str, asset_key: str, paths: dict) -> dict:
    """주어진 paths{field:filepath} 의 현재 해시로 manifest 엔트리 갱신(STALE 해소용 범용)."""
    m = load(root)
    entry = m["assets"][asset_key]
    for field, p in paths.items():
        if "." in field:  # nested 예: render_hash.claude
            top, sub = field.split(".", 1)
            entry.setdefault(top, {})[sub] = sha256_of(p)
        else:
            entry[field] = sha256_of(p)
    save(root, m)
    return entry
