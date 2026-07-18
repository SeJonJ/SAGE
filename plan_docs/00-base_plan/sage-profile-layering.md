# [Base Plan] SAGE 공유 정책과 로컬 capability 프로필 분리

Cycle-Stem: `sage-profile-layering`
Risk Level: L3
Status: PLANNED

## 1. Context

현재 `sage/project-profile.yaml`은 저장소 정책과 개인 실행환경을 함께 표현한다. 팀원이 같은 저장소를
사용하더라도 설치 host, cross-model 사용 여부, Obsidian 경로는 다를 수 있다. 이를 하나의 Git 추적 파일에
두면 개인 경로가 노출되거나, 개인 설정 차이 때문에 공통 위험·PDCA 정책이 흔들린다.

또한 `sage install`은 빈 공유 프로필을 미리 배치하므로 초기화 가능 여부는 파일 존재가 아니라 실제
부트스트랩 완료 상태로 판정해야 한다.

## 2. Goal

- Git 추적 공유 프로필과 Git 제외 로컬 프로필을 분리한다.
- local은 명시된 capability 필드만 소유하고 공통 안전정책을 완화하지 못하게 한다.
- `sage-init`은 미부트스트랩 프로젝트의 shared+local을 작성한다.
- `sage-init-local`은 이미 부트스트랩된 프로젝트에서 local만 작성·갱신한다.
- shared, local, effective 세 상태를 `validate`와 `doctor`가 구분해 보고한다.

## 3. Scope

In scope:

- `sage/project-profile.local.yaml` 로딩·스키마·allowlist·effective 해석
- full init과 local-only init의 상태 전이 및 CORE skill 문서
- local 파일 Git 제외 보장과 누락/추적 상태 진단
- required 정책에 대한 local 완화 시도 차단
- 기존 단일 프로필 프로젝트의 하위 호환

Out of scope:

- ChatForYou 프로필 실제 마이그레이션
- 두 host의 동시 사이클 실행 또는 자동 handoff
- 개인 credential, API key, 인증 토큰 저장

## 4. Impact

- 애플리케이션 Backend/Frontend/Desktop: N/A. SAGE 프로필 엔진·설치 자산만 변경한다.
- Security: 개인 경로를 공유 compiled JSON에 넣지 않고 local 완화를 fail-closed 처리한다.
- Compatibility: local 파일이 없는 기존 프로젝트는 기존 `options.cross_model` 의미를 유지한다.

## 5. Done Criteria

1. shared와 local을 중앙 로더가 결정론적으로 읽고 effective profile을 만든다.
2. local의 알 수 없는 키와 정책 소유 필드는 FAIL이다.
3. 부트스트랩된 shared에 `sage-init`을 실행하면 차단하고 `sage-init-local`을 안내한다.
4. shared가 없거나 미부트스트랩이면 `sage-init-local`을 차단하고 `sage-init`을 안내한다.
5. local 파일이 Git에 추적되거나 ignore되지 않으면 doctor/validate가 경고한다.
6. Claude/Codex 양쪽에서 새 CORE skill을 발견할 수 있다.
7. 세 번의 독립 headless 리뷰를 거쳐 승인된 finding만 반영한다.
