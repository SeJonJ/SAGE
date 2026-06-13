"""pre-implementation-gate — canonical core (pure, IO-bound gate, 부분추출).

Codex 2R 합의: 공유 risk-gate 만 canonical 추출. "L3 review doc 매칭"은 algorithm_delta(병합금지)
→ find_l3_review 전략 슬롯(claude_grep_first / codex_feature_signal 둘 다 보존, v1 미선택).

계약(2단계 pure core):
  classify_risk(event, profile)                              -> {risk, reason, is_l3_filename, declared_l3, file_short}
  decide(event, profile, snapshot, strategy_result)          -> {status, exit_code, risk, message_key, safety_degraded?}
- core 는 fs/time 의존 0. plan 후보(내용)·strategy 실행결과는 adapter 가 snapshot/strategy_result 로 주입.

안전 합의(G1): strategy 미선택(unresolved)이면 L3 review 확인 불가 → BLOCK + override-required + safety_degraded.
키워드/파일패턴 매칭은 case-insensitive(G2 canonical, 더 많은 L3 포착 = 안전 방향).
risk trigger(글롭/키워드)는 profile_bound(G3) — core 에 도메인값 0.
"""

import fnmatch

CONTRACT_VERSION = "1"
_RANK = {"none": -1, "L0": 0, "L1": 1, "L2": 2, "L3": 3}


def _imatch(path: str, glob: str) -> bool:
    return fnmatch.fnmatch(path.lower(), glob.lower())


def _has_kw(content: str, keywords: list) -> bool:
    c = (content or "").lower()
    return any(kw.lower() in c for kw in keywords)


def _classify_one(path: str, content: str, profile: dict) -> tuple:
    """단일 변경의 (risk, reason, is_l3_filename) — desktop 은 별도(여기선 분류만)."""
    r = profile.get("risk", {})
    # L0 즉시통과
    for g in r.get("l0_pass_globs", []):
        if _imatch(path, g):
            return ("L0", "문서/plan", False)

    risk, reason, is_l3_filename = "none", "", False
    for g in r.get("l3_filename_globs", []):
        if _imatch(path, g):
            # 라벨은 범용(제약 #2 독립). 도메인명(WebRTC/Kurento 등)은 profile.risk 가 정의, core 는 중립 라벨.
            risk, reason, is_l3_filename = "L3", "L3 filename 패턴", True
            break
    if risk == "none":
        for g in r.get("l2_path_globs", []):
            if _imatch(path, g):
                risk, reason = "L2", "백엔드 소스/설정"
                break
    if risk == "none":
        for g in r.get("l1_path_globs", []):
            if _imatch(path, g):
                risk, reason = "L1", "프론트 JS/UI"
                break
    if risk == "none":
        return ("none", "", False)

    # 내용 escalation (L1/L2 → L3, L1 → L2)
    if risk in ("L1", "L2") and _has_kw(content, r.get("l3_content_keywords", [])):
        risk, reason = "L3", reason + " + 내용 L3 키워드"
    elif risk == "L1" and _has_kw(content, r.get("l2_content_keywords", [])):
        risk, reason = "L2", reason + " + 내용 L2 키워드"
    return (risk, reason, is_l3_filename)


def classify_risk(event: dict, profile: dict) -> dict:
    """changes 중 최고 위험 분류. desktop 직접수정은 risk='DESKTOP_BLOCK'."""
    r = profile.get("risk", {})
    desktop_glob = r.get("desktop_block_glob", "")
    changes = event.get("changes") or []

    best = {"risk": "none", "reason": "", "is_l3_filename": False, "file_short": ""}
    for ch in changes:
        path = ch.get("path") or ""
        if desktop_glob and _imatch(path, desktop_glob):
            return {"risk": "DESKTOP_BLOCK", "reason": f"동기화 산출물/금지 경로 직접수정 금지: {path}",
                    "is_l3_filename": False, "declared_l3": False, "file_short": path}
        risk, reason, is_l3 = _classify_one(path, ch.get("content") or "", profile)
        if _RANK.get(risk, -1) > _RANK.get(best["risk"], -1):
            best = {"risk": risk, "reason": reason, "is_l3_filename": is_l3, "file_short": path}

    # 유저 선언 레벨 반영 (effective = max(감지, 선언), 상향만)
    declared = event.get("declared_max")  # "L0".."L3" or None
    declared_l3 = declared == "L3"
    if declared and _RANK.get(declared, -1) > _RANK.get(best["risk"], -1):
        best["risk"] = declared
        best["reason"] = (best["reason"] + " + " if best["reason"] else "") + f"유저 선언 {declared}"
    best["declared_l3"] = declared_l3
    return best


def _plan_exists(event: dict, snapshot: dict) -> str:
    """ticket(브랜치 숫자) 매칭 plan → 없으면 **최근(7일 이내) fallback**.

    원본 Claude 충실성(audit 1회차 P1): ticket 매칭은 전체 plan 대상, fallback 은 -mtime -7 제한.
    snapshot.plan_files = [{path, content, recent}] (recent=adapter 가 mtime<7일 판정, 최근순).
    """
    plan_files = snapshot.get("plan_files") or []
    branch = event.get("branch") or ""
    import re
    m = re.search(r"[0-9]+", branch)
    ticket = m.group(0) if m else ""
    if ticket:
        for pf in plan_files:
            if ticket in (pf.get("content") or ""):
                return pf.get("path", "")
    # fallback: 7일 이내(recent) plan 만 인정 (오래된 plan 은 게이트 충족 안 됨)
    for pf in plan_files:
        if pf.get("recent"):
            return pf.get("path", "")
    return ""


def decide(event: dict, profile: dict, snapshot: dict, strategy_result) -> dict:
    """risk-gate 판정. strategy_result: None=미선택 / {found:bool, path?} = 선택된 전략 실행결과."""
    c = classify_risk(event, profile)
    risk = c["risk"]

    if risk == "DESKTOP_BLOCK":
        return {"status": "block", "exit_code": 2, "risk": "DESKTOP",
                "message_key": "block_desktop", "reason": c["reason"], "file_short": c["file_short"]}
    if risk in ("none", "L0"):
        return {"status": "ok", "exit_code": 0, "risk": risk, "message_key": None, "reason": c["reason"]}

    plan_exists = _plan_exists(event, snapshot)

    if risk == "L3":
        # 강신호 + plan 없음 → 하드 블록 (공유)
        if (c["is_l3_filename"] or c["declared_l3"]) and not plan_exists:
            return {"status": "block", "exit_code": 2, "risk": "L3",
                    "message_key": "block_l3_no_plan", "reason": c["reason"], "file_short": c["file_short"]}
        # review doc 확인 = 전략. 미선택이면 확인 불가 → 안전 바닥(BLOCK + override)
        if strategy_result is None:
            return {"status": "block", "exit_code": 2, "risk": "L3",
                    "message_key": "block_l3_strategy_unresolved", "safety_degraded": True,
                    "reason": c["reason"], "file_short": c["file_short"]}
        if strategy_result.get("found"):
            return {"status": "ok", "exit_code": 0, "risk": "L3",
                    "message_key": "ok_l3", "reason": c["reason"], "file_short": c["file_short"]}
        return {"status": "warn", "exit_code": 0, "risk": "L3",
                "message_key": "warn_l3_no_review", "reason": c["reason"], "file_short": c["file_short"]}

    if risk == "L2":
        if not plan_exists:
            return {"status": "warn", "exit_code": 0, "risk": "L2",
                    "message_key": "warn_l2_no_plan", "reason": c["reason"], "file_short": c["file_short"]}
        return {"status": "ok", "exit_code": 0, "risk": "L2",
                "message_key": "ok_l2", "reason": c["reason"], "file_short": c["file_short"]}

    # L1 통과
    return {"status": "ok", "exit_code": 0, "risk": "L1", "message_key": None, "reason": c["reason"]}
