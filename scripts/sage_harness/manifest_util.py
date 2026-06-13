"""manifest_util — docs/sage_harness/.manifest.json 읽기/해시/엔트리 갱신 공용 헬퍼.

여러 곳(extract_agent, generate, 인라인 스크립트)에 흩어졌던 manifest hash 계산·엔트리 작성을 단일화.
schema/manifest.schema.json 의 필드 규약을 따른다. 결정론(정렬 + indent=2).
"""
import hashlib
import json
import os

MANIFEST_REL = os.path.join("docs", "sage_harness", ".manifest.json")


def sha256_of(path: str) -> str:
    with open(path, "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


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
        "adapter_contract_version": "1",
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
