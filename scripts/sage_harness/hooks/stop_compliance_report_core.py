"""stop-compliance-report — canonical core (pure, 부분추출).

SAGE 에 stop hook 없음 → ChatForYou 실측 기반 신규 SAGE stop hook 설계(Codex 2R 합의).
공유 core 만 canonical: JSONL 집계 → activity_summary → gate compliance 3종 → report_model → markdown.

⚠️ policy_delta(병합금지, Codex-only/OPTION — 별도 정책모듈 보존):
- output_contract_check: transcript 결합 → Codex-only (CORE 승격 보류, unresolved)
- knowledge_capture: obsidian OPTION (vault_path 비면 N/A)

계약: decide(event, profile, snapshot) -> report_model / render_markdown(report_model) -> str. (둘 다 pure)
snapshot = { entries[], today, branch, runtime }. L3 패턴 단일소스 = profile.risk.l3_filename_globs.
"""

from collections import defaultdict

CONTRACT_VERSION = "1"


def _l3_tokens(profile: dict) -> list:
    """profile.risk.l3_filename_globs('*kurento*' 등) → substring 토큰('kurento'). 단일소스 재사용."""
    out = []
    for g in (profile.get("risk", {}) or {}).get("l3_filename_globs", []):
        t = g.strip("*").lower()
        if t:
            out.append(t)
    return out


def decide(event: dict, profile: dict, snapshot: dict) -> dict:
    entries = snapshot.get("entries") or []
    today = snapshot.get("today", "")
    branch = snapshot.get("branch") or "unknown"

    by_type = defaultdict(list)
    for e in entries:
        by_type[e.get("type", "other")].append(e.get("file", ""))

    backend_main = sorted(set(by_type["backend-main"]))
    backend_test = sorted(set(by_type["backend-test"]))
    frontend = sorted(set(by_type["frontend-js"] + by_type["frontend-server"] + by_type["frontend-config"]))
    plan_docs = sorted(set(by_type["plan-doc"]))

    l3_tokens = _l3_tokens(profile)
    l3_files = sorted({f for f in (backend_main + frontend)
                       if any(t in f.lower() for t in l3_tokens)})

    issues = []
    if backend_main and not plan_docs:
        issues.append({"severity": "WARN", "key": "backend_without_plan",
                       "text": "백엔드 소스 수정이 있었으나 plan_docs 활동 없음 (L2 gate 참조)"})
    if l3_files:
        issues.append({"severity": "NOTICE", "key": "l3_pattern_detected",
                       "text": f"L3 패턴 파일 수정 감지: {', '.join(l3_files)} → L3 리뷰 프로토콜(2라운드) 확인 필요"})
    if backend_main:
        issues.append({"severity": "INFO", "key": "backend_convention_reminder",
                       "text": "백엔드 변경: backend-convention-checker 실행 여부 수동 확인 권장"})

    modified = sorted({e.get("file", "") for e in entries if e.get("file")})

    return {
        "kind": "stop_compliance",
        "sections": {
            "header": {"date": today, "branch": branch, "total_tool_calls": len(entries)},
            "activity_summary": {
                "backend_main": {"count": len(backend_main), "files": backend_main},
                "backend_test": {"count": len(backend_test), "files": backend_test},
                "frontend": {"count": len(frontend), "files": frontend},
                "plan_docs": {"count": len(plan_docs), "files": plan_docs},
            },
            "gate_compliance": {"issues": issues},
            "modified_files": modified,
            "policy_results": [],  # 확장 슬롯 — output_contract/knowledge_capture 등 OPTION/Codex policy 가 붙임 (core 미해석)
        },
        "exit_code": 0,
    }


def render_markdown(report_model: dict) -> str:
    s = report_model["sections"]
    h = s["header"]
    a = s["activity_summary"]
    lines = [
        f"# Compliance Report — {h['date']}",
        f"Branch: {h['branch']}  |  Total tool calls logged: {h['total_tool_calls']}",
        "",
        "## Activity Summary",
        "| 구분 | 파일 수 |", "|---|---|",
        f"| Backend src/main | {a['backend_main']['count']} |",
        f"| Backend src/test | {a['backend_test']['count']} |",
        f"| Frontend JS/server | {a['frontend']['count']} |",
        f"| Plan docs | {a['plan_docs']['count']} |",
        "",
        "## Gate Compliance",
    ]
    issues = s["gate_compliance"]["issues"]
    if not issues:
        lines.append("✅ 감지된 위반 없음")
    else:
        for it in issues:
            lines.append(f"[{it['severity']}] {it['text']}")
    lines += ["", "## Modified Files"]
    for f in s["modified_files"]:
        lines.append(f"- {f}")
    # policy_results (OPTION/Codex 확장이 붙인 경우만)
    if s.get("policy_results"):
        lines += ["", "## Policy Results"]
        for pr in s["policy_results"]:
            lines.append(f"[{pr.get('severity','INFO')}] {pr.get('name','')}: {pr.get('text','')}")
    return "\n".join(lines) + "\n"
