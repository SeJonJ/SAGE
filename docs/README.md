# SAGE 문서

[English](README.en.md) | [프로젝트 README](../README.md)

필요한 작업에 따라 아래 문서부터 읽으세요.

| 대상 | 시작 문서 |
|---|---|
| 처음 설치하는 사용자 | [퀵스타트](quickstart.md) |
| 매일 CLI를 사용하는 개발자 | [CLI 레퍼런스](cli-reference.md) |
| 프로젝트 정책을 설정하는 관리자 | [Profile 레퍼런스](profile-reference.md) |
| 설치·실행 오류를 해결하는 사용자 | [문제 해결](troubleshooting.md) |
| SAGE에 기여하는 개발자 | [Architecture](ARCHITECTURE.md) |
| 생성물 위치와 소유권을 확인하는 개발자 | [Artifacts](ARTIFACTS.md) |

## 거버넌스 하네스

`docs/sage_harness/`는 설치되는 hook·agent·skill·MCP spec과 manifest의 정본입니다. 일반 사용자
설명서가 아니라 SAGE 엔진과 생성기가 소비하는 자산이므로 직접 구조를 바꿀 때는
`sage generate`와 `sage validate`를 함께 실행해야 합니다.

## 에이전트 프레임워크

`docs/agent/`는 SAGE가 대상 저장소에 설치하는 PDCA, 리뷰, risk, context-management 프로토콜입니다.
프로젝트별 정책은 이 파일을 직접 수정하지 않고 `sage/project-profile.yaml`과 프로젝트 소유
governance 문서에 둡니다.
