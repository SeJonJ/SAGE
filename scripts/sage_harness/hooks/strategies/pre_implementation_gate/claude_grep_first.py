"""L3 review-doc 매칭 전략 후보 A — claude_grep_first (보존, 병합금지).

원본 .claude/hooks/pre-implementation-gate.sh 의 알고리즘:
  find plan_docs -name *.md -mtime -30 | xargs grep -l "Round 1|Round 2|L3 review|webrtc review" | head -1
순수화: snapshot.review_candidates = [{path, content}] (adapter 가 mtime<30d 필터해서 제공)에서
패턴 매칭되는 첫 후보를 found 로 본다.

⚠️ UNRESOLVED: codex_feature_signal 과 algorithm_delta. canonical 미선택 — 사람 결정 대기.
"""

import re

_PATTERNS = re.compile(r"Round 1|Round 2|L3.*[Rr]eview|webrtc.*review", re.IGNORECASE)


def find_l3_review(signals: dict, snapshot: dict) -> dict:
    for cand in snapshot.get("review_candidates") or []:
        if _PATTERNS.search(cand.get("content") or ""):
            return {"found": True, "path": cand.get("path", ""), "strategy": "claude_grep_first"}
    return {"found": False, "path": None, "strategy": "claude_grep_first"}
