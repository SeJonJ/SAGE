# [Analyze] SAGE-FB-10 Codex rename 목적지 L3 분류 우회 차단

Cycle-Stem: `sage-fb-10-codex-rename-risk`

## 1. Design vs. Implementation Gap

Match Rate: 100% after Claude review rounds 1~3 and closure verification.

| Design Requirement | Implementation | Gap |
|---|---|---|
| source + destination 보존 | update change와 move change를 순서대로 생성 | none |
| destination L3 분류 | 실제 `classify_risk` 연결 테스트 | none |
| rename content 양쪽 귀속 | canonical fan-out + Move-after-hunk backfill | none after R1 rework |
| orphan move fail-safe | source 없이 destination target 생성 | none |
| 기존 marker 회귀 방지 | 전체 hook runtime suite 통과 | none |

## 2. QA Coverage

| Scenario | Status | Evidence |
|---|:---:|---|
| ordinary add/update/delete | PASS | existing extraction test + 65-test suite |
| source -> destination rename extraction | PASS | dedicated unit test |
| destination-only L3 filename match | PASS | gate core classification test |
| rename content-L3 escalation | PASS | gate core classification test |
| orphan Move to marker | PASS | dedicated unit test |
| Claude runtime parity | N/A | Claude IO does not parse apply_patch Move markers |

## 3. Acceptance Evidence

| Acceptance ID | Status | Evidence |
|---|:---:|---|
| FB10-AC1 | PASS | source/destination tuple assertion |
| FB10-AC2 | PASS | destination filename-L3 retained under existing risk precedence; L0/L3 overlap deferred to FB-07 |
| FB10-AC3 | PASS | Move-after-hunk backfill + canonical fan-out tests |
| FB10-AC4 | PASS | orphan destination exact-output assertion |
| FB10-AC5 | PASS | 151 tests + 24 subtests across relevant suites |
| FB10-AC6 | PASS | three required fresh headless reviews completed; post-R3 closure review CLEAN |

## 4. Review Context for External Model

### Original User Intent

Codex rename이 destination filename L3 gate를 우회하지 못하게 하고, 완료 전 Claude의 독립 리뷰를
세 번 받아 발견을 무조건 수용하지 말고 타당성을 검토한 후 수정한다.

### Key Decisions During Implementation

- rename을 source replacement가 아니라 source update + destination move 두 change로 모델링했다.
- patch의 추가 내용은 source/destination 양쪽에 연결해 path+content 조합을 보수적으로 분류한다.
- malformed pre-tool payload에서도 destination marker는 버리지 않는다.

### Scope Changes / Deferred Items

- scope change 없음.
- phase4 extractor rename 지원, cycle binding, raw profile validation은 별도 피드백 사이클이다.

### Design vs Implementation Notes

R1에서 marker ordering과 equal-rank provenance gap 두 건을 재현했다. 두 P1과 관련 P2를 모두
수용해 02 설계와 구현을 수정했다. 동일 rank trigger는 ordered union하고 filename-L3 경로를
operator-facing 대표로 유지한다.

R2에서 두 R1 P1의 closure를 확인했다. 새 P2 네 건 중 L0/L3 overlap은 FB-07로 defer하고,
provenance 정확성·message attribution·decision-level coverage 세 건은 수용해 수정했다.

### QA Coverage Summary

R2 rework 후 관련 151 tests + 24 subtests가 통과했고 `git diff --check`도 통과했다.

### Final Review Closure

- Required R1: CHANGES_REQUIRED, 0 P0 / 2 P1 / 2 P2.
- Required R2: CHANGES_REQUIRED, 0 P0 / 0 P1 / 4 P2.
- Required R3: CHANGES_REQUIRED, 0 P0 / 1 P1 / 4 P2 (code clean, acceptance docs rework).
- Post-R3 closure: CLEAN, no P0/P1; all R3 findings fixed.

### Known Risks / Open Questions

- added content를 두 change에 복제하는 것이 downstream audit/override file list에 중복 의미를 만들지 검토가 필요하다.
- apply_patch grammar가 Move marker 이후 추가 marker를 허용할 때 target reset이 올바른지 검토가 필요하다.

### Files External Reviewer Must Inspect

- `plan_docs/00-base_plan/sage-fb-10-codex-rename-risk.md`
- `plan_docs/01-plan/sage-fb-10-codex-rename-risk.md`
- `plan_docs/02-design/sage-fb-10-codex-rename-risk.md`
- `plan_docs/03-implementation/sage-fb-10-codex-rename-risk.md`
- `plan_docs/04-analyze/sage-fb-10-codex-rename-risk.md`
- `scripts/sage_harness/hooks/runtime/io_codex.py`
- `scripts/sage_harness/hooks/tests/test_hook_runtime.py`
- `scripts/sage_harness/hooks/pre_implementation_gate_core.py`

## 5. Verdict Boundary

Phase 04는 최종 승인 판정을 내리지 않는다. 최종 상태는 세 번의 Claude 리뷰와 타당성 triage를
기록한 Phase 05에서만 결정한다.
