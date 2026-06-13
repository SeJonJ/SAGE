"""stop-compliance 확장 정책 — output_contract_check (보존, 병합금지).

원본 .codex/hooks/stop-compliance-report.sh 의 Codex-only 검사:
transcript 의 마지막 assistant 텍스트에서 output-contract 핵심 섹션 hit/5 를 세어 OK/WARN.

⚠️ UNRESOLVED: transcript_path 의존 → Codex runtime 결합. CORE 승격 보류(promote_output_contract_semantics?).
Claude stop hook 엔 대응 검사 없음. v1 미병합 — 정책모듈로 보존만.
"""

CONTRACT_SECTIONS = ["요약", "변경", "검증", "리스크", "다음"]  # output-contract.md 핵심 5섹션(예시)


def check(last_assistant_text, has_code_changes: bool) -> dict:
    if not has_code_changes:
        return {"name": "output_contract", "severity": "INFO", "text": "N/A — 코드 변경 없음"}
    if not last_assistant_text:
        return {"name": "output_contract", "severity": "INFO", "text": "N/A — transcript 접근 불가"}
    hit = sum(1 for s in CONTRACT_SECTIONS if s in last_assistant_text)
    if hit >= 5:
        return {"name": "output_contract", "severity": "OK", "text": f"output contract 섹션 {hit}/5 충족"}
    return {"name": "output_contract", "severity": "WARN",
            "text": f"output contract 섹션 {hit}/5 만 감지 → docs/agent/output-contract.md 형식 권장"}
