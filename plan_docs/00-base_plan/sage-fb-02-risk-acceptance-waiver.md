# [Base Plan] SAGE-FB-02 위험도별 acceptance와 명시적 L3 waiver

Cycle-Stem: `sage-fb-02-risk-acceptance-waiver`
Risk Level: L3
Status: PLANNED

## 1. Context

현재 acceptance report gate는 `report_gate_enforce` 단일 값만 가져 L2와 L3를 분리할 수 없다. 운영 배포,
외부 인증 시스템, 실제 네트워크 등 로컬에서 검증할 수 없는 L3 acceptance가 하나라도 `NOT TESTED`이면
전체 06을 영구 차단하거나, 반대로 전역 advisory로 내려 모든 L3를 약화해야 한다.

## 2. Goal

- 기본 정책을 L2 advisory, L3 enforce로 분리한다.
- 로컬에서 확정 불가능한 특정 L3 acceptance ID만 사용자 명시 승인으로 advisory 처리한다.
- waiver가 PASS를 위조하지 않고 `NOT TESTED`와 남은 증거를 그대로 보존한다.
- 자동/묵시적 하향과 FAIL 상태 waiver를 금지한다.
- 승인 사유, 범위, 남은 증거, cycle/id와 사용자를 append-only 감사 기록에 남긴다.

## 3. Scope

In scope:

- acceptance profile의 risk별 mode
- L3 ID 단위 waiver grant/revoke/list/audit
- report gate의 exact cycle/id waiver 결속
- profile/compiler/schema/doctor/template/guidance
- 양 host runtime snapshot과 regression tests
- 세 번의 independent headless review-rework

Out of scope:

- FAIL acceptance 통과
- cycle 전체 또는 모든 L3를 한 번에 하향하는 wildcard waiver
- 원격 사용자 신원 attestation(SAGE-FB-08)
- 실제 운영 배포 자동 실행

## 4. Impact

- Backend/Frontend/Desktop: N/A. SAGE governance engine만 변경한다.
- 운영 검증 전 완료 보고는 PASS가 아니라 명시적 residual evidence를 가진 advisory completion으로 남는다.

## 5. Done Criteria

1. 기본 L2 unresolved evidence는 WARN, L3는 BLOCK한다.
2. unknown risk는 L3와 같은 enforce로 처리한다.
3. exact cycle stem + acceptance ID의 active waiver만 L3 `NOT TESTED`를 WARN으로 낮춘다.
4. FAIL, wildcard, 누락 reason/scope/remaining evidence, implicit profile flag는 waiver되지 않는다.
5. grant/use/revoke가 append-only 감사에 남고 gate와 CLI가 같은 parser를 사용한다.
6. Claude 또는 지정 fallback 독립 리뷰 3회를 완료한다.
