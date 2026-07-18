# [Plan] SAGE-FB-01/11 cycle evidence 결정론 결속

Cycle-Stem: `sage-fb-01-11-cycle-evidence-binding`
Risk Level: L3

## 1. User Stories & Requirements

- Ticket 없는 branch에서도 cycle stem이 phase 문서를 결정해야 한다.
- 06 report는 같은 cycle의 01·04·05만 소비해야 한다.
- 여러 cycle 후보가 동시에 보이면 임의 선택하지 않고 BLOCK해야 한다.
- branch의 부수 숫자가 과거 L3 review evidence를 만족시키면 안 된다.
- 04 acceptance evidence는 01 ID를 exact하게 추적해야 한다.

## 2. Cycle Identity Contract

- Canonical key: 안전한 단일 token의 `Cycle-Stem`.
- Phase document path basename과 본문의 `Cycle-Stem:`은 같아야 한다.
- Phase write에서는 changed path/declaration이 current stem을 제공한다.
- Source/config write에서는 explicit event stem 또는 branch final segment가 current stem을 제공한다.
- 여러 signal이 다르면 ambiguous binding으로 BLOCK한다.
- 숫자 substring 검색과 mtime/recent fallback은 PDCA document binding에 사용하지 않는다.

## 3. Acceptance Matrix

| ID | User Requirement | Required Evidence | Owner | Required? |
|---|---|---|---|---|
| FB011-AC1 | exact cycle stem resolver | resolver unit tests | engine | yes |
| FB011-AC2 | missing/conflicting/ambiguous binding BLOCK | decision regressions | engine | yes |
| FB011-AC3 | same-stem 01/04/05/06 binding | report/acceptance/audit tests | engine | yes |
| FB011-AC4 | `feat/141-sd3` cannot bind stale cycle `3` | strategy/runtime regression | engine | yes |
| FB011-AC5 | `v2` cannot bind cycle `2` | strategy/runtime regression | engine | yes |
| FB011-AC6 | exact L3 review cycle stem passes | strategy tests | engine | yes |
| FB011-AC7 | acceptance missing/unknown/duplicate/malformed IDs fail | acceptance gate tests | engine | yes |
| FB011-AC8 | templates/spec document the executable contract | roster/resource tests | docs | yes |
| FB011-AC9 | three independent reviews plus final closure | Phase 05 evidence | reviewer | yes |
