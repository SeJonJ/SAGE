# Overlay 전달·#36 통합 검증 기록

이 디렉터리는 개발 당시의 계획과 실행 근거를 보존합니다. 과거 기록의 `COMPLETE`나 `APPROVED`를
다른 제품 hash의 승인으로 옮겨 쓰지 않습니다.

## 현재 후보와 승인 경계

현재 후보는 `fix/overlay-context-delivery`의 overlay 수정과 #36 구 레이아웃 업그레이드 통합본입니다.
2026-11-09 사용자는 문서 정리, 커밋·푸시, PR 생성과 CI 확인을 승인했습니다. 이 지시는 독립 리뷰
차단을 해제하거나 main 병합·릴리스를 승인한 것으로 기록하지 않습니다. PR은 Draft로 제출합니다.

| 기록 | 적용 범위 | 판정 |
|---|---|---|
| [Overlay 단독 05](05/overlay-context-delivery.md)·[06](06/overlay-context-delivery.md) | 제품 hash `93d541024b737af26048290415aa8b513855330ef411aa9e591d2ded5efbb611` | 당시 후보의 독립 승인·완료 기록 |
| [통합 03](03/overlay-issue36-integration.md)·[04](04/overlay-issue36-integration.md) | #36을 포함한 제품 hash `205ba39f9b2f587573fb44c31f313a2f3c7975a2dabc1e2d6b9941785282ae70` | 구현·로컬 검증 수행 |
| [통합 05](05/overlay-issue36-integration.md) | 같은 통합 제품 후보 | `BLOCKED`: 유효 Claude peer 결과·반박 절차 미완료, 리뷰 예산 초과 |
| [플랫폼 검증 요약](04/platform-validation.md) | 2026-11-07 Windows·Mac 실행 | 원본 실패, 수정 후 재검증, 건너뜀을 분리 |

통합 후보의 06 문서는 작성하지 않았습니다. 2026-11-09 후속 작업에서는 사용자 설명서만 추가
정리했으며 제품 동작을 더 확장하지 않았습니다. CI 결과는 PR의 정확한 commit checks를 확인합니다.
과거 문서의 ‘미커밋·CI 미실행’은 해당 문서가 작성된 시점의 상태입니다.

## 해석할 때 주의할 점

- 테스트 실행 완료와 전체 통과는 다릅니다. Windows 전체 회귀는 전부 통과하지 않았습니다.
- 설치 CLI·hook 프로토콜 검증과 실제 Claude/Codex 모델의 새 대화 세션 검증을 구분합니다.
- CI 성공은 독립 L3 승인, Windows 데스크톱 전체 검증, 사용자 최종 인수나 출시 승인을 대신하지 않습니다.
- 원자료의 로컬 경로·로그 hash는 당시 근거를 추적하기 위한 정보입니다. 재현 가능한 공개 요약은
  플랫폼 검증 문서와 저장소의 테스트·CI 스크립트를 함께 읽습니다.
