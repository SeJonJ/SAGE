# hooks/strategies — ChatForYou 인스턴스 전략 후보 (프레임워크 아님)

> [!important] 제약 #2(SAGE 독립): 이 디렉토리의 전략은 **ChatForYou 인스턴스 후보**다. 프레임워크 generic 전략이 아니다.

`pre_implementation_gate` 의 "L3 review doc 매칭"은 `.claude`↔`.codex` 간 **algorithm_delta**(병합 금지)다.
두 런타임의 갈라진 알고리즘을 **둘 다 보존**하되 **canonical 미선택(unresolved)** 상태로 둔다(설계: drift 비병합).

- `claude_grep_first.py` — grep-first 매칭 (ChatForYou .claude hook 알고리즘. `webrtc.*review` 등 ChatForYou 패턴 포함)
- `codex_feature_signal.py` — feature-signal 스코어링 (ChatForYou .codex hook 알고리즘. Spring/Node 토큰 필터 포함)

**현재 미선택**: core 는 `strategy_result=None` → L3 review 확인 불가 → 안전 BLOCK(override-required).
manifest `.unresolved` 에 "canonical 사람 결정 필요"로 표기됨.

**다른 프로젝트**: 이 전략을 그대로 쓰지 말고(ChatForYou/WebRTC 편향), 자기 프로젝트의 review-doc 매칭 전략을
별도로 작성해 선택한다. 즉 이 파일들은 SAGE 프레임워크가 제공하는 generic 전략이 **아니라** ChatForYou 추출 후보다.
