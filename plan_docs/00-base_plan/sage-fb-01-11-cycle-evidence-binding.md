# [Base Plan] SAGE-FB-01/11 cycle evidence 결정론 결속

Cycle-Stem: `sage-fb-01-11-cycle-evidence-binding`
Risk Level: L3
Status: IN_PROGRESS

## 1. Context

현재 phase 문서 선택은 브랜치의 첫 숫자가 본문에 포함됐는지 확인한 뒤 최근 7일 문서로 fallback한다.
L3 review는 브랜치의 모든 숫자와 branch/leaf를 cycle 후보로 만든다. 따라서 ticket 없는 브랜치에서는
서로 다른 cycle의 01/04/05/06이 결합될 수 있고, `feat/141-sd3`의 부수 숫자 `3`이 과거 review 증거를
현재 증거처럼 통과시킬 수 있다.

## 2. Goal

- phase 문서를 explicit cycle stem으로만 선택한다.
- 06 작성 시 동일 cycle의 01 acceptance, 04 evidence, 05 approval/audit만 결속한다.
- cycle 후보가 없거나 모호하면 fail-closed로 차단한다.
- L3 review evidence를 exact cycle stem에 결속하고 branch 숫자 수집을 제거한다.
- Phase 01 acceptance ID와 Phase 04 evidence ID의 동일성·유일성을 검증한다.

## 3. Scope

In scope:

- pre-implementation pure core의 cycle resolver와 phase selector
- runtime strategy signal과 `cycle_domain_review` frontmatter 계약
- acceptance matrix/evidence ID 추적
- PDCA/review authoring template와 hook spec 정합화
- Claude 우선 3회 independent review 및 fallback 검증

Out of scope:

- server-side PR attestation/branch protection
- 자동 branch 생성 또는 자동 host 전환
- 기존 프로젝트 phase 문서 자동 rewrite
- acceptance 위험도별 waiver(SAGE-FB-02)

## 4. Component Impact

- SAGE engine/hooks/templates: affected.
- ChatForYou Backend: N/A, application source is not changed.
- ChatForYou Frontend: N/A, application source is not changed.
- ChatForYou Desktop: N/A, application source is not changed.

## 5. Done Criteria

1. phase path stem과 `Cycle-Stem` 선언이 정확히 일치한다.
2. current stem은 changed phase path/declaration 또는 exact branch leaf/explicit signal로 하나만 결정된다.
3. missing/conflicting/ambiguous cycle binding blocks governed work.
4. 01/04/05/06 gates cannot mix documents from different stems.
5. L3 review requires exact `cycle_stem`; incidental branch numbers never satisfy it.
6. acceptance required IDs are present exactly once in 04; unknown/duplicate/malformed IDs fail.
7. three independent review rounds and final closure complete.
