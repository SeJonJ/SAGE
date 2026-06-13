"""L3 review-doc 매칭 전략 후보 B — codex_feature_signal (보존, 병합금지).

원본 .codex/hooks/pre-implementation-gate.sh 의 알고리즘:
  branch/plan/changed-path 를 토큰화 → generic 토큰 제거 → 후보 plan 문서의 토큰 겹침으로 점수화,
  feature signal 이 충분히 겹치는 후보를 review 로 본다 (grep-first 보다 정교).
순수화: signals(tickets/plan/files 토큰) + snapshot.review_candidates 로 점수 최고 후보 선택.

⚠️ UNRESOLVED: claude_grep_first 와 algorithm_delta. canonical 미선택 — 사람 결정 대기.
"""

import re

GENERIC_SIGNAL_TOKENS = {
    "src", "main", "test", "java", "static", "nodejs", "frontend",
    "springboot", "backend", "service", "controller", "config",
    "js", "scss", "html", "json", "true", "false",
    "plan", "plans", "docs", "base", "design", "review",
}


def _tokens(value: str) -> set:
    parts = re.split(r"[^A-Za-z0-9가-힣]+", value or "")
    return {p.lower() for p in parts if len(p) >= 3}


def _specific(value: str) -> set:
    return {t for t in _tokens(value) if t not in GENERIC_SIGNAL_TOKENS}


def find_l3_review(signals: dict, snapshot: dict) -> dict:
    want = set()
    for key in ("tickets", "plan", "files"):
        want |= set(signals.get(key) or [])
    if not want:
        return {"found": False, "path": None, "strategy": "codex_feature_signal"}

    best, best_score = None, 0
    for cand in snapshot.get("review_candidates") or []:
        have = _specific(cand.get("content") or "") | _specific(cand.get("path") or "")
        score = len(want & have)
        if score > best_score:
            best, best_score = cand.get("path", ""), score
    if best and best_score >= 1:
        return {"found": True, "path": best, "score": best_score, "strategy": "codex_feature_signal"}
    return {"found": False, "path": None, "strategy": "codex_feature_signal"}
