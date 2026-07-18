# [Design] SAGE-FB-01/11 cycle evidence 결정론 결속

Cycle-Stem: `sage-fb-01-11-cycle-evidence-binding`
Risk Level: L3

## 1. Architecture

- `cycle_binding.py`: pure parser/resolver shared by gate core and runtime strategy orchestration.
- `pre_implementation_gate_core.py`: binding gate, exact phase selection, report/acceptance/audit decisions.
- `hook_runtime.py`: current binding을 L3 strategy signal로 전달하며 branch 숫자 extraction을 하지 않는다.
- `cycle_domain_review.py`: review frontmatter의 exact `cycle_stem`과 matched domains/rounds를 검증한다.

## 2. Resolution Algorithm

1. PDCA phase glob을 filesystem-style path segment와 recursive `**` 의미로 직접 매칭한다.
2. changed phase path마다 basename stem과 fenced block 밖의 event 또는 existing snapshot `Cycle-Stem`을 읽는다.
   전체 쓰기와 선언을 수정한 부분 패치는 snapshot fallback을 허용하지 않는다.
3. path stem/declaration 불일치를 오류로 기록한다.
4. phase write가 아니면 explicit event stem, 없으면 branch final segment를 사용한다.
5. valid candidate가 정확히 하나가 아니거나 오류가 있으면 unresolved/ambiguous로 반환한다.
6. phase selector는 path stem과 declaration이 모두 current stem인 문서가 정확히 하나일 때만 선택한다.

## 3. Report and Acceptance Flow

- report gate: current 06 stem -> exact 05 -> approval marker.
- acceptance gate: current 06 stem -> exact 01 matrix + exact 04 fence 밖 evidence.
- audit gate: current 06 stem -> exact 05 -> same-document fence 밖 단일 `Loop-Run` -> audit record.
- acceptance/audit 결과를 모두 계산하고 enforce BLOCK을 advisory WARN보다 우선한다.
- 06은 snapshot 의존성을 가진 모든 00–05 phase update와 분리한다.
- matrix parser는 all IDs와 required IDs를 함께 반환한다.
- evidence parser는 duplicate, unknown, invalid ID와 N/A 사유를 보존해 fail detail로 전달한다.
- cycle risk는 같은 stem의 모든 신뢰 입력 중 최댓값을 사용한다.

## 4. L3 Review Flow

- runtime resolves one cycle stem before strategy invocation.
- strategy input contains `cycle_stem` and optional binding error, not `cycle_ids` or numeric tickets.
- review frontmatter requires `cycle_stem`, `round: [1, 2]`, and registered `domain_ref`.
- a review with legacy-only `cycle_id` is not evidence for the new contract.

## 5. Failure Policy

- Cycle binding failure: BLOCK/exit 2 for governed phase/source changes.
- Exact phase doc absent or duplicate: corresponding report/acceptance/audit gate fails.
- L3 strategy binding unavailable: enforce failure.
- Non-PDCA projects retain legacy plan existence behavior for compatibility.
