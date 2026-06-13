"""stop-compliance 확장 정책 — knowledge_capture (보존, OPTION-gated).

원본 .codex/hooks/stop-compliance-report.sh 의 vault capture 검사를 일반화.
OPTION(knowledge_capture, provider=obsidian). vault_path 비면 graceful N/A.

⚠️ CORE 아님 — OPTION 레이어 소속. v1 미병합 — 정책모듈로 보존만.
"""

CONTRACT_VERSION = "1"


def check(vault_path: str, has_code_changes: bool, capture_done: bool) -> dict:
    if not vault_path:
        return {"name": "knowledge_capture", "severity": "INFO", "text": "N/A — vault_path 미설정(OPTION off)"}
    if not has_code_changes:
        return {"name": "knowledge_capture", "severity": "INFO", "text": "N/A — 코드 변경 없음"}
    if capture_done:
        return {"name": "knowledge_capture", "severity": "OK", "text": "vault 지식 캡처 완료"}
    return {"name": "knowledge_capture", "severity": "WARN", "text": "코드 변경 세션 — vault 지식 캡처 미확인"}
