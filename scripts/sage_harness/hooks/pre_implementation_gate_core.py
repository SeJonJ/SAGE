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
    # 사유(reason)는 범용 규칙 참조형(제약 #2 독립). 특정 스택/도메인명 금지 —
    # "어느 매칭 규칙이 발동했는지"만 기술한다. 도메인 명칭은 profile.risk(글롭/키워드)가 정의, core 는 중립.
    for g in r.get("l3_filename_globs", []):
        if _imatch(path, g):
            risk, reason, is_l3_filename = "L3", "L3 filename 패턴", True
            break
    if risk == "none":
        for g in r.get("l2_path_globs", []):
            if _imatch(path, g):
                risk, reason = "L2", "L2 소스/설정"      # 중립: l2_path_globs 매치(스택 무관)
                break
    if risk == "none":
        for g in r.get("l1_path_globs", []):
            if _imatch(path, g):
                risk, reason = "L1", "L1 저위험"          # 중립: l1_path_globs 매치(스택 무관)
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


def _doc_match(docs: list, event: dict) -> str:
    """문서 목록에서 ticket(브랜치 숫자) 매칭 → 없으면 최근(recent=7일 이내) fallback.

    plan/phase 문서 존재 판정의 공통 규칙. docs = [{path, content, recent}].
    (원본 Claude 충실성: ticket 매칭은 전체 대상, fallback 은 -mtime -7 제한.)
    """
    import re
    branch = event.get("branch") or ""
    m = re.search(r"[0-9]+", branch)
    ticket = m.group(0) if m else ""
    if ticket:
        for d in docs:
            if ticket in (d.get("content") or ""):
                return d.get("path", "")
    for d in docs:
        if d.get("recent"):
            return d.get("path", "")
    return ""


def _plan_exists(event: dict, snapshot: dict) -> str:
    """snapshot.plan_files 에서 ticket→recent 매칭(기존 계약 유지)."""
    return _doc_match(snapshot.get("plan_files") or [], event)


def _pdca_cfg(profile: dict):
    """PDCA phase 강제 설정. 비활성(enabled=false 또는 phases 없음)이면 None → 게이트는 기존 동작(하위호환)."""
    p = profile.get("pdca") or {}
    if not p.get("enabled"):
        return None
    if not p.get("phases"):
        return None
    return p


def _missing_pre_impl_phases(event: dict, profile: dict, snapshot: dict, risk: str):
    """구현 전 의무 phase 중 문서가 없는 것 목록. pdca 비활성이면 None(=강제 안 함).

    빈 리스트 = 강제 활성이나 결핍 없음(또는 해당 레벨 요구 phase 없음). 비어있지 않으면 결핍.
    phase 문서 존재는 _doc_match(ticket→recent) 규칙 — plan 존재 판정과 동일.
    """
    cfg = _pdca_cfg(profile)
    if cfg is None:
        return None
    required = (cfg.get("pre_implementation_required") or {}).get(risk) or []
    if not required:
        return []
    phase_docs = snapshot.get("phase_docs") or {}
    return [pid for pid in required if not _doc_match(phase_docs.get(pid) or [], event)]


def _glob_base(pattern: str) -> str:
    """glob 메타문자(*?[]) 이전까지의 디렉토리 prefix. 예: plan_docs/06-report/**/*.md → plan_docs/06-report.

    report-write 감지는 fnmatch(`**` 미지원, glob.glob 와 의미 불일치) 대신 base 디렉토리 prefix 로 판정한다.
    """
    parts = []
    for seg in pattern.split("/"):
        if any(ch in seg for ch in "*?[]"):
            break
        parts.append(seg)
    return "/".join(parts)


def _under_dir(path: str, base: str) -> bool:
    p = (path or "").lower().lstrip("./")
    b = (base or "").lower()
    return bool(b) and (p == b or p.startswith(b + "/"))


def _report_gate(event: dict, profile: dict, snapshot: dict):
    """report phase 문서를 쓰는 변경이면 approve phase 의 승인 마커 존재 여부 판정.

    반환: None(비활성/해당없음) | {"approved": bool, "report_phase", "approve_phase"}.
    report/approve phase 미설정이면 None. 06(report) 작성 전 05(approve) APPROVED 강제용.
    """
    cfg = _pdca_cfg(profile)
    if cfg is None:
        return None
    report_phase = cfg.get("report_phase") or ""
    approve_phase = cfg.get("approve_phase") or ""
    if not report_phase or not approve_phase:
        return None
    phases = {p.get("id"): p for p in (cfg.get("phases") or [])}
    rglob = (phases.get(report_phase) or {}).get("glob") or ""
    if not rglob:
        return None
    base = _glob_base(rglob)   # base 디렉토리 prefix(=glob.glob 스캔과 일치, fnmatch ** 불일치 회피)
    writing_report = any(_under_dir(ch.get("path") or "", base) for ch in (event.get("changes") or []))
    if not writing_report:
        return None
    marker = (cfg.get("approve_marker") or "APPROVED").lower()
    approve_docs = (snapshot.get("phase_docs") or {}).get(approve_phase) or []
    approved = any(marker in (d.get("content") or "").lower() for d in approve_docs)
    return {"approved": approved, "report_phase": report_phase, "approve_phase": approve_phase}


def decide(event: dict, profile: dict, snapshot: dict, strategy_result) -> dict:
    """risk-gate 판정. strategy_result: None=미선택 / {found:bool, path?} = 선택된 전략 실행결과."""
    c = classify_risk(event, profile)
    risk = c["risk"]

    if risk == "DESKTOP_BLOCK":
        return {"status": "block", "exit_code": 2, "risk": "DESKTOP",
                "message_key": "block_desktop", "reason": c["reason"], "file_short": c["file_short"]}

    # PDCA report←approve 게이트: report phase 문서 작성은 L0(plan_docs)이라 아래 단축 전에 검사.
    # (pdca 비활성이거나 report/approve 미설정 → None → skip, 하위호환)
    rg = _report_gate(event, profile, snapshot)
    if rg is not None and not rg["approved"]:
        return {"status": "block", "exit_code": 2, "risk": "PDCA",
                "message_key": "block_report_without_approval",
                "reason": f"{rg['report_phase']} 작성 전 {rg['approve_phase']} 승인(APPROVED) 필요",
                "file_short": c["file_short"]}

    if risk in ("none", "L0"):
        return {"status": "ok", "exit_code": 0, "risk": risk, "message_key": None, "reason": c["reason"]}

    # PDCA 의무 phase 강제: 구현 전 필수 phase 결핍 시 L2/L3 BLOCK, L1 WARN.
    # missing=None(pdca 비활성) 또는 [](충족) → falsy → 기존 per-level 로직으로 (하위호환).
    missing = _missing_pre_impl_phases(event, profile, snapshot, risk)
    if missing:
        if risk in ("L2", "L3"):
            return {"status": "block", "exit_code": 2, "risk": risk,
                    "message_key": "block_phase_incomplete", "missing_phases": missing,
                    "reason": c["reason"], "file_short": c["file_short"]}
        return {"status": "warn", "exit_code": 0, "risk": "L1",
                "message_key": "warn_phase_incomplete", "missing_phases": missing,
                "reason": c["reason"], "file_short": c["file_short"]}

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
