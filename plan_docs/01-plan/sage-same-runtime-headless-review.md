# [Plan] Phase 05 same-runtime headless 리뷰 결정론 실행

Cycle-Stem: `sage-same-runtime-headless-review`
Risk Level: L3

## 1. Acceptance Matrix

| ID | Requirement | Required? |
|---|---|:---:|
| SRH-AC1 | `sage review`는 packet file과 active host를 입력받아 새 headless process를 실행한다. | yes |
| SRH-AC2 | Codex/Claude command는 shell 없이 stdin으로 packet을 전달한다. | yes |
| SRH-AC3 | 성공 출력은 review 본문과 process/host/model/mode evidence를 포함한다. | yes |
| SRH-AC4 | timeout, CLI 없음, nonzero, parse 실패는 review 성공으로 기록되지 않는다. | yes |
| SRH-AC5 | required+local false 또는 required+peer 미가용은 BLOCKED/nonzero다. | yes |
| SRH-AC6 | recommended+local false는 active host same-runtime headless를 실행한다. | yes |
| SRH-AC7 | policy off는 cross-model을 호출하지 않고 same-runtime headless를 실행한다. | yes |
| SRH-AC8 | legacy shared bool은 local 파일이 없을 때 기존 routing을 유지한다. | yes |

## 2. Failure Contract

same-runtime 실행 실패를 기존처럼 `REVIEWER_ACTUAL: same_runtime` 성공으로 출력하지 않는다. stderr에 원인을
기록하고 `REVIEWER_STATUS: BLOCKED`, nonzero exit를 반환한다. required cross-model 실패도 same-runtime으로
자동 완화하지 않는다. recommended만 명시적 local opt-out에서 same-runtime을 정상 모드로 인정한다.
