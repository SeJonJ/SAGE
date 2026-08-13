"""hook 한국어 catalog.

한국어가 호환 기본값이다. 이 문장들은 catalog 도입 전의 출력을 그대로 재현한다. 기존 key 이름
(`ok_l1`·`ok_l0` 등)은 호환 계약이라 바꾸지 않는다 — 이름이 바뀌면 이 key 를 읽는 소비자와
과거 감사 기록이 함께 끊긴다.

`{rs}` 는 판정 core 가 만든 언어 중립 근거 문자열이다. 여기서 번역하지 않고 그대로 싣는다.
"""

MESSAGES = {
    "block_desktop": "동기화 산출물/금지 경로 직접수정 금지.",
    "block_feedback_unresolved": "미해결 개발자 피드백 마커(!sage-feedback) 위에 새 구현 금지.",
    "block_l3_no_plan": "L3 작업 + plan 문서 없음.",
    "block_l3_strategy_unresolved": "L3 review 매칭 전략 미선택(unresolved) → 리뷰 확인 불가.",
    "block_l3_review_evidence": "현재 cycle의 L3 review 증거 미충족.",
    "warn_l3_no_review": "2라운드 리뷰 문서 미확인.",
    "warn_l2_no_plan": "소스/설정 변경인데 plan 문서 없음.",
    "warn_l0_l3_content": "문서/plan 에 L3 내용 키워드 감지 — 민감정보 노출 점검.",
    "block_phase_incomplete": "의무 PDCA phase 미작성: [{miss}].",
    "warn_phase_incomplete": "권장 PDCA phase 미작성: [{miss}].",
    "block_cycle_risk_declaration": "cycle `{cycle_stem}`의 Phase 00 Risk Level 선언이 없거나 유효하지 않습니다.",
    "block_cycle_risk_reconciliation": "Phase 00 Risk Level {phase00_risk}보다 계산 위험도 {required_risk}가 높습니다.",
    "block_report_without_approval": "{rs}.",
    "block_report_mixed_evidence": "{rs}.",
    "block_phase00_mixed_evidence": "{rs}.",
    "warn_phase00_mixed_evidence": "{rs}.",
    "block_report_without_audit": "{rs}.",
    "warn_report_without_audit": "{rs}.",
    "block_invalid_done_criteria": "{rs}.",
    "warn_invalid_done_criteria": "{rs}.",
    "warn_done_criteria_progress": "{rs}.",
    "block_stale_done_criteria_revision": "{rs}.",
    "warn_stale_done_criteria_revision": "{rs}.",
    "block_report_without_done_criteria": "{rs}.",
    "warn_report_without_done_criteria": "{rs}.",
    "block_stale_done_criteria_approval": "{rs}.",
    "warn_stale_done_criteria_approval": "{rs}.",
    "block_cycle_binding": "{rs}.",
    "block_cycle_closed": "cycle `{cycle_stem}` 은 이미 완결된 사이클입니다 — 새 소스 편집을 여기에 결속할 수 없습니다.",
    "block_report_without_acceptance": "{rs}.",
    "warn_report_without_acceptance": "{rs}.",
    "warn_report_with_l3_waiver": "{rs}.",
    "block_report_waiver_audit_failure": "{rs}.",
    "block_fast_cycle_audit": "Fast Cycle 감사·composite 결속 실패: {rs}.",
    "warn_fast_cycle": "Fast Cycle 축약 절차 사용: {rs}.",
    "block_cycle_stem_audit_failure": "{rs}.",
    "block_gate_runtime_error": "{rs}.",
    "ok_l3": "review 확인됨",
    "ok_l2": "plan 확인",
    "ok_l1": "결속 확인",
    "ok_l0": "결속 확인",
}
