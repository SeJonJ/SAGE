# Overlay 전달·통합·복구 검증 기록

이 디렉터리는 개발 당시의 계획과 실행 근거를 보존합니다. 과거 기록의 `COMPLETE`나 `APPROVED`를
다른 제품 hash의 승인으로 옮겨 쓰지 않습니다.

## 현재 후보와 승인 경계

2026-11-15 현재 후보는 [overlay 복구 경계 완료 기록](06/overlay-recovery-boundary.md)입니다.
이전 통합본은 PR #37/#38로 main에 병합됐지만 1.3.7 태그·PyPI 출하는 후속 오류 수정 때문에
보류됐습니다. 이번 후보는 그 main을 기준으로 세션 봉쇄 해소·적용 전 검사·host 검증을 보완했습니다.
사용자는 이번 사이클 종료·문서 갱신·커밋/푸시·머지·릴리즈를 명시 승인했습니다.

| 기록 | 적용 범위 | 판정 |
|---|---|---|
| [현재 00](00/overlay-recovery-boundary.md)·[03](03/overlay-recovery-boundary.md)·[04](04/overlay-recovery-boundary.md) | 현재 복구 후보의 C1–C6와 추가 보완·[영수증](04/overlay-recovery-boundary.validation.json) | Mac 회귀, 실제 모델 대표 사례, Windows 11 실기기 검증 완료 |
| [현재 05](05/overlay-recovery-boundary.md)·[06](06/overlay-recovery-boundary.md) | 고정 source의 same-runtime 리뷰와 후속 실행 근거 | 3라운드 완료, 최종 APPROVED, 개발 사이클 종료 |
| [Overlay 단독 05](05/overlay-context-delivery.md)·[06](06/overlay-context-delivery.md) | 이전 overlay 전달 후보 | 당시 hash의 독립 승인·완료 기록 |
| [통합 05](05/overlay-issue36-integration.md)·[06](06/overlay-issue36-integration.md) | 이전 #36 통합 후보·Windows checklist 수정 | 해당 단계의 승인·완료 기록; 현재 후보에 자동 상속하지 않음 |
| [이전 플랫폼 검증](04/platform-validation.md)·[원문](04/windows-phase4-paths.validation.json) | 2026-11-07~11의 후보 | 이전 실행 실패·수정·scope를 보존 |

개발 사이클 종료와 배포는 별도입니다. 실제 머지·배포 상태는 현재 PR의 정확한 commit checks와
[릴리즈](https://github.com/SeJonJ/SAGE/releases/tag/v1.3.7), PyPI에서 확인합니다. 문서 작성 당시
아직 실행하지 않은 CI/게시를 성공 실적으로 미리 세지 않습니다.

## 해석할 때 주의할 점

- 테스트 실행 완료와 전체 통과는 다릅니다. Windows 전체 회귀는 전부 통과하지 않았습니다.
- 설치 CLI·hook 프로토콜 검증과 실제 Claude/Codex 모델의 새 대화 세션 검증을 구분합니다.
- CI 성공은 독립 L3 승인, Windows 데스크톱 전체 검증, 사용자 최종 인수나 출시 승인을 대신하지 않습니다.
- 원자료의 로컬 경로·로그 hash는 당시 근거를 추적하기 위한 정보입니다. 재현 가능한 공개 요약은
  플랫폼 검증 문서와 저장소의 테스트·CI 스크립트를 함께 읽습니다.

2026-11-10 재개 리뷰는 이전 비용을 보존한 새 원장으로 수행했습니다. 컴파일 예외 진단1건을
최소 수정했고, Python3.12에서 확인한 새 테스트의 인터프리터 가정도 수정했습니다.
제품 기능 범위는 확대하지 않았으며 2e79f77의 독립 승인을 완료했습니다. 새 리뷰 사용량은365,312/400,000토큰입니다. 후속 문서 head CI는 PR에서 확인합니다. [검토 원문과 비용](05/overlay-issue36-integration.review.json)을 함께 보존합니다.
