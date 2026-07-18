# [Plan] SAGE 공유 정책과 로컬 capability 프로필 분리

Cycle-Stem: `sage-profile-layering`
Risk Level: L3

## 1. Acceptance Matrix

| ID | Requirement | Required? |
|---|---|:---:|
| SPL-AC1 | shared가 미부트스트랩이면 full init이 shared와 local 작성 절차를 제공한다. | yes |
| SPL-AC2 | shared가 부트스트랩됐으면 full init을 차단하고 local init만 허용한다. | yes |
| SPL-AC3 | local init은 유효한 shared가 없으면 차단한다. | yes |
| SPL-AC4 | local은 installed hosts, host capability, cross-model 개인 선택, Obsidian 활성화·경로만 소유한다. | yes |
| SPL-AC5 | local의 risk, PDCA, gate, component, 요구 버전 변경 시도는 FAIL이다. | yes |
| SPL-AC6 | shared compiled JSON에는 local 경로와 capability가 포함되지 않는다. | yes |
| SPL-AC7 | local이 없는 기존 프로젝트는 기존 프로필 동작을 유지한다. | yes |
| SPL-AC8 | local 파일은 설치·초기화 절차에서 Git 제외되고 추적 상태가 진단된다. | yes |
| SPL-AC9 | 양 runtime의 init/profile-modify 문서가 동일 상태 전이를 설명한다. | yes |

## 2. Profile Ownership

Shared owns project identity, components, risk, PDCA, verification, gates, review policy, model selection and
required SAGE version. Local owns only machine capability: installed hosts, CLI capability, cross-model opt-in,
Obsidian enabled/path and local model availability metadata. Runtime의 실제 active host는 저장된 `both` 값이
아니라 현재 명령의 명시적 host 입력으로 해석한다.

## 3. Initialization States

- shared missing/unbootstrapped: `sage-init` 허용, `sage-init-local` 차단
- shared valid + local missing: `sage-init` 차단, `sage-init-local` 허용
- shared valid + local valid: `sage-init` 차단, `sage-init-local` 재인터뷰·갱신 허용
- shared invalid: 두 init 모두 정책을 추측하지 않고 shared 수정 안내

## 4. Failure Contract

- local parse/schema/ownership 오류는 effective profile을 만들지 않는다.
- local이 required 정책을 완화하면 init 단계와 런타임 검증 단계 모두 BLOCK한다.
- local 내용을 shared JSON에 합치거나 manifest에 기록하지 않는다.
