# [Design] SAGE-FB-12 framework overlay 게이트 완화 hard-fail

Cycle-Stem: `sage-fb-12-framework-overlay-hard-fail`

## 1. Eligibility Model

Composition eligibility를 두 개의 명시 집합으로 분리한다.

```text
NON_GATE_COMPOSE_ALLOWED
  = agents/implementer-a, agents/implementer-b

INDEPENDENT_ORACLE_COMPOSE_ALLOWED
  = empty until an executable independent oracle is implemented and tested

COMPOSE_ALLOWED = union
```

Framework 4종은 auto-loaded governance surface이며 SD-4 `domain_refs` contract는 게이트 oracle이 아니므로
두 집합 어디에도 넣지 않는다. 향후 재개방은 자산별 executable oracle과 회귀 fixture를 같은 변경에서
등록해야 한다.

## 2. One Scanner, Two Policies

`overlay_lint.scan_text`가 pattern id와 설명의 단일 판정원이다.

- materialization preflight: hit가 하나라도 있으면 hard error, plans/receipts 없음.
- validate default: WARN, heuristic 오탐 가능성을 고려해 exit 0 유지.
- validate strict: stable check id `overlay-gate-relaxation`을 `strict_hits`에 넣어 FAIL/exit 1.

Scanner를 복제하거나 별도 regex를 두지 않는다. Preflight는 이미 읽은 overlay text를 scanner에 넘겨 TOCTOU
창을 늘리는 중복 read를 피한다.

## 3. Ordering

```text
plan_blocked_cleanup
  -> blocked CORE render의 정확한 SAGE managed block 제거 계획
  -> malformed/duplicate marker는 해당 target hard error
  -> 안전하게 식별된 다른 blocked target 계획은 적용

plan_materialize
  -> domain contract scan
  -> enumerate every overlay file
     -> unknown id / blocked eligibility
     -> read + marker validation
     -> gate-relaxation scan
  -> only when all preflight checks pass: compute render plans/receipts
  -> caller applies plans
```

일반 materialization 오류가 있으면 `{}`, `errors`를 반환하고 eligible plans/receipts를 적용하지 않는다.
단, FB12 이전 설치본의 gate-bearing managed block이 실행 지침으로 남지 않게 하는 보안 정리는 독립 pre-step이다.
정확한 SAGE marker 구간만 제거하며 base와 manifest receipt를 재축복하지 않는다. 이 정리는 source identity나
SAGE version skew 검사보다 먼저 수행하고, 한 target의 malformed marker가 다른 안전한 target의 정리를 막지
않는다.

## 4. Guidance Contract

- `/sage-asset-override`는 현재 eligible non-gate assets만 저작한다.
- gate-relaxation hit는 사용자 확인 질문이 아니라 수정/제거가 필요한 stop condition이다.
- CORE framework 직접 편집은 계속 write-guard로 차단하되, blocked framework overlay로 redirect하지 않는다.
- 프로젝트 값은 profile/conventions/critical-domain/project-local docs로 안내한다.
