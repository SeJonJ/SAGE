# [Analyze] SAGE-FB-13 raw profile 위험 필드 타입 선검증

Cycle-Stem: `sage-fb-13-raw-profile-types`

## 1. Design vs. Implementation Gap

Match Rate: 100% before independent review.

| Design | Implementation | Gap |
|---|---|---|
| pre-materialization raw check | `materialization_issues` before deepcopy/coercion | none |
| controlled compiler failure | aggregated `ProfileCompileError` | none |
| direct JSON semantic guard | validator reuses pure issue collector | none |
| schema defense in depth | top risk arrays require non-empty string items | none |
| caller-specific fail closed | generate rc1, validate FAIL, hook rc2 | none |
| valid compatibility | existing domain merge/dedupe test passes | none |

## 2. QA Coverage

| Layer | Status | Evidence |
|---|:---:|---|
| top-level scalar/null | PASS | all six fields parameterized |
| bad/blank list item | PASS | number, bool, empty, whitespace |
| domain trigger fields | PASS | scalar, null, item + missing-field compatibility |
| invalid input mutation | PASS | source dict unchanged after exception |
| generate pre-write atomicity | PASS | no JSON/settings/hooks |
| validate freshness severity | PASS | FAIL marker + rc1 |
| runtime gate bootstrap | PASS | Claude/Codex both rc2 |
| valid profile behavior | PASS | focused regression suites in dependency-complete Python |

## 3. Acceptance Evidence

| Acceptance ID | Status | Evidence |
|---|:---:|---|
| FB13-AC1 | PASS | compiler top-field matrix |
| FB13-AC2 | PASS | domain field matrix |
| FB13-AC3 | PASS | controlled exception and deterministic field paths |
| FB13-AC4 | PASS | generate no-output integration test |
| FB13-AC5 | PASS | validate + both-host hook integration tests |
| FB13-AC6 | PASS | semantic validator and schema item tests |
| FB13-AC7 | PASS | final focused suites: 188 tests, 1 skipped, all pass |
| FB13-AC8 | PASS | Claude quota exhausted; three distinct fresh Codex headless fallback rounds complete; R3 CLEAN |

## 4. Review Context for External Model

### Original User Intent

scalar risk value가 문자 배열로 coercion되어 L3 gate가 침묵 약화되는 결함을 fail-closed로 수정하고,
완료 전 Claude 독립 리뷰를 세 번 받아 findings를 타당성 검토 후 반영한다.

### Key Decisions During Implementation

- compiler가 소비하는 필드만 pure primitive로 검증한다.
- explicit null은 missing과 다르게 작성 오류로 본다.
- schema 설치 여부에 관계없이 semantic validator가 같은 계약을 강제한다.
- production caller는 library exception을 각 CLI/hook 실패 프로토콜로 변환한다.

### Scope Changes / Deferred Items

- profile 전체 list typing은 제외했다.
- 새 key/migration UX는 추가하지 않았다.

### QA Coverage Summary

Final focused suites: 188 tests, 1 skipped, all pass. `git diff --check` pass.

### Round 1 Rework Result

- domain missing-field P1: accepted and fixed; written compatibility contract restored.
- schema blank-item P2: accepted and fixed for top/domain fields.
- duplicate validate diagnostic P2: accepted and fixed with exact-count regression test.
- caller search found only generate/validate/hook production callers; all convert `ProfileCompileError` to controlled failure.
- dependency-complete verification: 5 suites, 186 tests, 1 skipped, all pass.

### Known Boundary

- explicit null remains intentionally different from missing and fails closed.

### Round 2 Rework Result

- duplicate semantic `risk` type P2: accepted; materialization primitive is now the single owner.
- missing-domain positive schema test P2: accepted; schema compatibility is now directly pinned.

### Round 3 Result

- fresh read-only headless session found P0 0 / P1 0 / P2 0 and returned `CLEAN`.
- malformed-value matrix had zero mismatches; compiler and dependency-complete validator suites passed in reviewer context.
- no code changes followed Round 3, so an additional closure round was not required.

### Files External Reviewer Must Inspect

- `plan_docs/00-base_plan/sage-fb-13-raw-profile-types.md` through this 04 document
- `sage/profile_compile.py`
- `sage/profile_validate.py`
- `sage/commands/generate.py`
- `sage/commands/validate.py`
- `sage/hook_entry.py`
- `schema/profile.schema.json`
- changed focused tests

## 5. Verdict Boundary

Phase 04는 verdict를 내리지 않는다. 독립 headless review-rework 3회와 최종 acceptance는 Phase 05에서 결정한다.
