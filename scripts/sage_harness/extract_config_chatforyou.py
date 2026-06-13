"""ChatForYou 인스턴스용 ExtractConfig (엔진 밖 — 제약 #2: SAGE 독립).

reverse_extract_agent 엔진은 도메인값 0. ChatForYou 고유 컴포넌트 경로·컨벤션 휴리스틱은 여기 분리한다.
다른 프로젝트는 자기 config 를 만들어 주입하면 같은 엔진이 동작한다(독립 입증).
이 파일은 ChatForYou 전용 인스턴스 설정일 뿐 프레임워크 코드가 아니다.
"""

CHATFORYOU_EXTRACT_CONFIG = {
    "component_path_globs": [r"(?:springboot-backend|nodejs-frontend|chatforyou-desktop)/[\w./-]+"],
    "not_owned_substrings": ["chatforyou-desktop/src"],   # 동기화 산출물/금지(소유 아님)
    "planning_path_substrings": ["plan_docs"],
    "guide_boundary_tokens": ["commit", "push", "chatforyou-desktop/src"],
    "runtime_policy_tokens": {"codex": ["gstack"]},
    "signal_rules": [
        # 테스트 계층 경계(통합/HTTP/경계값/시나리오 = QA 영역, backend-expert 미담당)
        {"type": "safety_forbid", "value": "forbid:integration/http/boundary/scenario tests",
         "require_any": [r"금지|미담당|하지\s*않는다|영역이다|영역"],
         "match_any": [r"(통합|http|경계값|시나리오)\s*테스트"], "exclude_persona": True},
        # 미배분 파일 수정 금지
        {"type": "safety_forbid", "value": "forbid:unassigned files",
         "require_any": [r"금지|미담당|하지\s*않는다|영역이다|영역"],
         "match_any": [r"nodejs-frontend", r"미배분"], "exclude_persona": True},
        # Service 단위 테스트만 담당
        {"type": "test_scope", "value": "test_scope:service unit only",
         "match_any": [r"(service|서비스).*(단위\s*테스트|unit test)", r"MockitoExtension"]},
        # QA 인계 경계
        {"type": "role_boundary", "value": "boundary:integration/scenario → qa",
         "require_any": [r"(?i)qa"], "match_any": [r"영역", r"인계", r"전문가"]},
        # 구현 가이드 작성 워크플로우
        {"type": "workflow_step", "value": "workflow:write impl guide",
         "match_any": [r"구현 가이드"]},
    ],
}
