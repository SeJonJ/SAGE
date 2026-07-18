# [Plan] 프로젝트 SAGE 버전 계약과 실행 불일치 알림

Cycle-Stem: `sage-version-contract`
Risk Level: L3

## 1. Acceptance Matrix

| ID | Requirement | Required? |
|---|---|:---:|
| SVC-AC1 | shared profile의 exact required version을 스키마가 검증한다. | yes |
| SVC-AC2 | install은 신규 빈 프로필에 현재 package version을 기록한다. | yes |
| SVC-AC3 | doctor는 required, installed/generated, runtime 버전을 각각 출력한다. | yes |
| SVC-AC4 | validate는 불일치를 WARN으로 보고하고 정정 명령을 제공한다. | yes |
| SVC-AC5 | SessionStart의 `sage-hook`은 불일치를 notification으로 출력한다. | yes |
| SVC-AC6 | local profile은 required version을 선언하거나 변경할 수 없다. | yes |
| SVC-AC7 | manifest가 없는 레거시 프로젝트는 unknown을 거짓 일치로 보고하지 않는다. | yes |

## 2. Severity Policy

버전 불일치는 이번 단계에서 WARN이다. 개발 세션 자체를 막지는 않지만 현재값과 `sage install --force`,
`sage generate --kind hook --write` 등 상황별 정정 명령을 함께 제시한다. profile 형식 오류나 local의 정책
소유권 침범은 WARN이 아니라 FAIL이다.
