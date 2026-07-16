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

import yaml

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
    """<root>/sage/asset_overrides/{agents,skills,framework}/*.md 를 스캔.

    반환 [(relpath, [(pattern_id, 설명), ...]), ...] — 매칭된 파일만. 디렉토리 없으면 빈 리스트.
    """
    base = os.path.join(root, OVERLAY_SUBDIR)
    if not os.path.isdir(base):
        return []
    results = []
    for subdir in ("agents", "skills", "framework"):
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


def _split_frontmatter(text):
    if not text.startswith("---\n"):
        return None, text, "YAML frontmatter(---) 누락"
    end = text.find("\n---\n", 4)
    if end < 0:
        return None, text, "YAML frontmatter 종료(---) 누락"
    try:
        meta = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as e:
        return None, text, f"YAML frontmatter 파싱 실패: {e}"
    if not isinstance(meta, dict):
        return None, text, "YAML frontmatter 는 매핑(object)이어야 함"
    return meta, text[end + 5:], None


def _norm(value):
    return re.sub(r"[`\s]+", "", str(value).lower())


def scan_domain_contract(root, profile):
    """framework override 의 SD-4 domain_refs 계약을 검사한다.

    반환 [(check_id, relpath, message)]. `critical-domain-drift` 는 strict 승격 대상이다.
    framework override 는 domain id 만 참조할 수 있고 authoritative trigger 값을 복제할 수 없다.
    """
    risk = profile.get("risk") if isinstance(profile, dict) else {}
    risk = risk if isinstance(risk, dict) else {}
    domains = risk.get("domains") if isinstance(risk.get("domains"), list) else []
    registry = {d.get("id"): d for d in domains if isinstance(d, dict) and isinstance(d.get("id"), str)}
    base = os.path.join(root, OVERLAY_SUBDIR, "framework")
    if not os.path.isdir(base):
        return []
    findings = []
    for fn in sorted(os.listdir(base)):
        if not fn.endswith(".md"):
            continue
        path = os.path.join(base, fn)
        rel = os.path.relpath(path, root)
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as e:
            findings.append(("critical-domain-drift", rel, f"override 읽기 실패: {e}"))
            continue
        meta, body, err = _split_frontmatter(text)
        if err:
            findings.append(("critical-domain-drift", rel, err))
            continue
        unknown_keys = sorted(set(meta) - {"domain_refs"}, key=str)
        if unknown_keys:
            findings.append(("critical-domain-drift", rel,
                             f"framework override frontmatter 미허용 키 {unknown_keys}; domain_refs 만 허용"))
        refs = meta.get("domain_refs")
        if not isinstance(refs, list) or not all(isinstance(x, str) and x for x in refs):
            findings.append(("critical-domain-drift", rel, "domain_refs 는 비어있지 않은 문자열 리스트여야 함"))
            continue
        unknown = sorted(set(refs) - set(registry))
        if unknown:
            findings.append(("critical-domain-drift", rel, f"미등록 domain_refs {unknown}"))
        norm_body = _norm(body)
        for ref in refs:
            domain = registry.get(ref) or {}
            for field in ("path_globs", "content_keywords"):
                for trigger in domain.get(field) or []:
                    token = _norm(trigger)
                    if token and token in norm_body:
                        findings.append(("critical-domain-drift", rel,
                                         f"domain '{ref}' {field} trigger 재복제 금지: {trigger!r}"))
    return findings
