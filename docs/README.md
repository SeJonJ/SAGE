# SAGE 문서

[English](README.en.md) | [프로젝트 README](../README.md)

필요한 작업에 따라 아래 문서부터 읽으세요.

| 대상 | 시작 문서 |
|---|---|
| 처음 설치하는 사용자 | [퀵스타트](quickstart.md) |
| 매일 CLI를 사용하는 개발자 | [CLI 레퍼런스](cli-reference.md) |
| 팀 공유 지침과 Git 제외 개인 지침을 나누는 개발자 | [개인 overlay·수동 이행](cli-reference.md#개인-overlay) |
| 표준·Fast overlay의 자동 공급과 한도를 확인하는 개발자 | [대상별 문맥 공급](ARCHITECTURE.md#대상별-overlay-문맥-공급) |
| 프로젝트 정책을 설정하는 관리자 | [Profile 레퍼런스](profile-reference.md) |
| Phase 05 리뷰 방식과 비용을 이해하려는 개발자 | [교차 리뷰](cross-review.md) |
| 설치·실행 오류를 해결하는 사용자 | [문제 해결](troubleshooting.md) |
| SAGE에 기여하는 개발자 | [Architecture](ARCHITECTURE.md) |
| 생성물 위치·소유권과 커밋 대상을 확인하는 개발자 | [Artifacts](ARTIFACTS.md) |
| 릴리스 가능 여부를 판단하는 관리자 | [릴리스 준비 상태](release-readiness.md) |

## 거버넌스 하네스

`docs/sage_harness/`는 설치되는 hook·agent·skill·MCP spec과 manifest의 정본입니다. 일반 사용자
설명서가 아니라 SAGE 엔진과 생성기가 소비하는 자산이므로 직접 구조를 바꿀 때는 `sage generate`와
`sage validate`를 함께 실행해야 합니다.

## 에이전트 프레임워크

엔진 저장소의 정본은 `templates/core/framework/docs/agent/`에 있습니다. `sage install`은 그 내용을
설치 대상 저장소의 `docs/agent/`로 배포합니다. 프로젝트별 정책은 설치된 파일을 직접 수정하지 않고
`sage/project-profile.yaml`과 프로젝트 소유 governance 문서에 둡니다.

## 개발 검증 기록

[계획·검증 기록 인덱스](plan_docs/README.md)는 overlay 단독·#36 통합·후속 복구 후보의 승인 범위를
구분합니다. 플랫폼 테스트, 현재 PR의 CI, 독립 리뷰, 릴리스 승인은 각각 별도 근거입니다.
