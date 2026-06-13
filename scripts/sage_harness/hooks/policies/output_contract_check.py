"""stop-compliance 확장 정책 — output_contract_check (보존, Codex-only policy_delta).

원본 .codex/hooks/stop-compliance-report.sh 의 Output Contract 검사를 충실 이식:
transcript 마지막 assistant 텍스트에서 5개 핵심 섹션 마커를 세어 hit>=4 → OK / else WARN.

⚠️ Codex runtime 결합(transcript_path 의존). canonical CORE 미병합(promote 보류, manifest.unresolved).
   Codex adapter 만 이 정책을 policy_results 에 주입(claude adapter 는 미적용 — Claude 엔 대응 검사 없음).
"""

CONTRACT_VERSION = "1"

# 원본과 동일한 5개 마커 (hit>=4 → OK)
_MARKERS = {
    "Task Summary / 요약": ["task summary", "작업 요약", "요약"],
    "Risk Level": ["risk level", "risk", "위험", "l0", "l1", "l2", "l3"],
    "Impact (BE/FE/Desktop)": ["impact", "영향", "backend", "frontend", "desktop"],
    "Modified Files": ["modified files", "변경 파일", "수정 파일", "변경된 파일"],
    "Validation": ["validation", "검증", "build", "test", "gradlew"],
}


def check(last_assistant_text, has_code_changes: bool) -> dict:
    if not has_code_changes:
        return {"name": "output_contract", "severity": "INFO", "text": "N/A — 코드 변경 없음 (적용 대상 아님)"}
    if not last_assistant_text:
        return {"name": "output_contract", "severity": "INFO", "text": "N/A — transcript 접근 불가 또는 추출 실패"}
    lt = last_assistant_text.lower()
    present = {k: any(t in lt for t in v) for k, v in _MARKERS.items()}
    missing = [k for k, ok in present.items() if not ok]
    hit = len(present) - len(missing)
    if hit >= 4:
        return {"name": "output_contract", "severity": "OK", "text": f"output contract 핵심 섹션 {hit}/5 충족"}
    return {"name": "output_contract", "severity": "WARN",
            "text": f"output contract 섹션 {hit}/5 만 감지 (누락 추정: {', '.join(missing)}) → docs/agent/output-contract.md 형식 권장"}
