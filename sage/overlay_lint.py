"""CORE 자산 오버레이(sage/asset_overrides/**) 게이트-완화 린트 — 결정론 WARN.

오버레이는 CORE agent/skill 렌더를 프로젝트 로컬로 덧대는 hand-authored 파일이다
(install 미ship, `sage install --force` 생존). CORE 렌더는 "must not relax AGENT_GUIDE,
phase, review, or verification gates" 를 프로즈로 요구하지만 그 프로즈만으로는 아무도
막지 않았다 — 게이트를 무력화하는 오버레이를 써도 조용히 통과했다.

이 모듈은 그 프로즈 규칙을 **결정론 체크로 승격**한다: 오버레이 본문에 게이트 완화로
읽히는 표현이 있으면 표면화한다. 판정은 휴리스틱(정규식)이라 오탐이 있을 수 있어
**WARN 만**(하드 FAIL 아님) — 저자가 의도를 재확인하게 하는 안전선이다. 하드 게이트
(phase/review/verification)는 여전히 hook·generate·validate 가 담당한다.

`/sage-asset-override` 스킬이 저작 흐름에서 참조하고, `sage validate` 가 CI 표면으로 쓴다.
"""
import os
import re
from pathlib import Path

# 게이트 완화로 읽히는 표현(영/한). IGNORECASE. 근접 매칭으로 문맥을 좁혀 오탐을 줄인다.
# (id, 정규식, 사람 설명) — 설명은 WARN 메시지에 그대로 노출.
_GATE_RELAX_PATTERNS = [
    ("skip-gate", r"\bskip\b[^.\n]{0,24}\b(phase|review|verification|validation|gate|validate)\b",
     "phase/review/verification/gate 스킵 지시로 읽힘"),
    ("bypass-gate", r"\bbypass\b[^.\n]{0,24}\b(gate|guard|review|phase|validation|verification)\b",
     "게이트/가드 우회 지시로 읽힘"),
    ("disable-gate", r"\bdisable\b[^.\n]{0,24}\b(gate|guard|hook|review|check)\b",
     "게이트/가드/hook 비활성 지시로 읽힘"),
    ("ignore-guide", r"\bignore\b[^.\n]{0,24}AGENT_GUIDE|AGENT_GUIDE[^.\n]{0,24}\b(ignore|무시|무력화)\b",
     "AGENT_GUIDE 무시 지시로 읽힘"),
    ("skip-phase-num", r"\bphase\s*0?[0-6]\b[^.\n]{0,16}(skip|건너|생략)|(skip|건너뛰|건너|생략)[^.\n]{0,16}\bphase\s*0?[0-6]\b",
     "특정 phase(00~06) 스킵 지시로 읽힘"),
    ("relax-ko", r"게이트[^.\n]{0,8}(우회|무력화|생략|비활성|끄|해제)|(우회|무력화|비활성)[^.\n]{0,8}게이트",
     "게이트 우회/무력화 표현"),
    ("skip-review-ko", r"(리뷰|검증|리뷰\s*루프|review\s*loop)[^.\n]{0,8}(생략|건너|스킵|끄)",
     "리뷰/검증 생략 표현"),
]

_COMPILED = [(pid, re.compile(pat, re.IGNORECASE), desc) for pid, pat, desc in _GATE_RELAX_PATTERNS]

# 오버레이 루트(프로젝트 로컬). install 이 ship 하지 않고 --force 에도 보존된다.
OVERLAY_SUBDIR = os.path.join("sage", "asset_overrides")


def scan_text(text):
    """오버레이 본문에서 게이트-완화 의심 표현을 찾아 [(pattern_id, 설명)] 반환(중복 제거)."""
    hits = []
    seen = set()
    for pid, rx, desc in _COMPILED:
        if rx.search(text) and pid not in seen:
            seen.add(pid)
            hits.append((pid, desc))
    return hits


def scan_overlays(root):
    """<root>/sage/asset_overrides/{agents,skills}/*.md 를 스캔.

    반환 [(relpath, [(pattern_id, 설명), ...]), ...] — 매칭된 파일만. 디렉토리 없으면 빈 리스트.
    """
    base = os.path.join(root, OVERLAY_SUBDIR)
    if not os.path.isdir(base):
        return []
    results = []
    for subdir in ("agents", "skills"):
        d = os.path.join(base, subdir)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md"):
                continue
            p = os.path.join(d, fn)
            try:
                text = Path(p).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            hits = scan_text(text)
            if hits:
                results.append((os.path.join(OVERLAY_SUBDIR, subdir, fn), hits))
    return results
