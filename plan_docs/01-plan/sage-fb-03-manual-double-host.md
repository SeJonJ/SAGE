# [Plan] SAGE-FB-03 Manual Double-Host 운영 모델

Cycle-Stem: `sage-fb-03-manual-double-host`
Risk Level: L3

## 1. Acceptance Matrix

| ID | Requirement | Required? |
|---|---|:---:|
| FB03-AC1 | profile은 desired installed hosts와 single active host를 구분한다. | yes |
| FB03-AC2 | legacy runtime.host는 계속 동작하며 active_host와 충돌하면 FAIL한다. | yes |
| FB03-AC3 | active host가 codex면 claude, claude면 codex가 cross reviewer다. | yes |
| FB03-AC4 | double-host + cross_model false를 doctor/validate가 강하게 경고한다. | yes |
| FB03-AC5 | doctor는 desired hosts, actual manifest hosts, active host 불일치를 진단한다. | yes |
| FB03-AC6 | generate/review/host-specific doctor 경로는 active_host를 공통 해석한다. | yes |
| FB03-AC7 | 문서는 동시 실행·자동 handoff를 지원하지 않고 exact phase 문서 수동 재개를 안내한다. | yes |
| FB03-AC8 | three independent Claude review rounds와 finding triage를 완료한다. | yes |

## 2. Migration

기존 `runtime.host`만 있는 profile은 동일하게 동작한다. 신규 profile은 `installed_hosts`와 `active_host`를 사용한다.
두 alias를 함께 둘 때 값이 다르면 어느 host가 실제 정본인지 알 수 없으므로 fail-closed한다.

