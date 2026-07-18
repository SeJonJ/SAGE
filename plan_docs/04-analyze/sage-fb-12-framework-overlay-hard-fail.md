# [Analyze] SAGE-FB-12 framework overlay 게이트 완화 hard-fail

Cycle-Stem: `sage-fb-12-framework-overlay-hard-fail`

## 1. Baseline Reproduction

- framework 4종은 `COMPOSE_ALLOWED`에 직접 등록돼 있었다.
- domain contract만 통과한 `AGENT_GUIDE` overlay는 실제 render에 materialize됐다.
- `test_gate_relax_suspected_remains_advisory_under_strict`는 suspect text에도 strict rc=0을 기대했다.
- materialization preflight는 marker injection만 검사하고 gate-relax scanner를 호출하지 않았다.

## 2. Acceptance Evidence

| Acceptance ID | Status | Evidence |
|---|:---:|---|
| FB12-AC1 | PASS | classification test가 framework 4종의 oracle 미등록과 blocked 판정을 검증한다. |
| FB12-AC2 | PASS | eligible implementer gate-relax overlay가 empty receipt/plan/error를 반환하고 render bytes를 보존한다. |
| FB12-AC3 | PASS | strict validate가 `overlay-gate-relaxation`을 출력하고 rc=1이다. |
| FB12-AC4 | PASS | 같은 eligible overlay의 default validate는 WARN을 출력하고 rc=0이다. |
| FB12-AC5 | PASS | preflight와 validate가 모두 `overlay_lint.scan_text` 결과를 소비한다. |
| FB12-AC6 | PASS | clean failure는 eligible render/receipt를 보존하고, pre-FB12 blocked managed block은 exact marker 구간만 제거하며 manifest receipt는 갱신하지 않는다. |
| FB12-AC7 | PASS | shipped skill/guide/write-guard가 framework 및 explicit confirmation bypass를 제거했다. |
| FB12-AC8 | PASS | Claude quota failure was recorded; three required fresh fallback reviews and three closure reviews completed, with final CLEAN. |

## 3. Static Analysis

- `domain_refs`는 domain registry drift 계약으로 유지되지만 composition oracle로 취급하지 않는다.
- `COMPOSE_ALLOWED` 재개방은 explicit executable-oracle set에 코드+fixture를 함께 추가해야 한다.
- preflight는 overlay file을 한 번 읽은 text로 marker와 gate-relaxation을 모두 검사한다.
- 일반 preflight errors가 존재하면 `plan_materialize`가 eligible plans/receipts를 폐기한다.
- blocked managed block 정리는 독립 보안 pre-step이다. exact marker만 제거하고 malformed target은 hard-stop하며,
  다른 안전한 blocked target 정리와 manifest 미갱신을 보장한다.
- validate의 default/strict 차이는 detection이 아니라 policy layer에만 존재한다.
- install 전체 copy/prune 이전 preflight는 FB-15 범위이므로 이 사이클은 materialization apply 이전 무변경만 보장한다.

## 4. Verification

- 관련 Python suite에서 399 pass, 1 optional-dependency skip.
- generated write guard shell suite에서 66 pass.
- install module 단독 89 pass.
- `git diff --check`: pass.

## 5. Review Boundary

Phase 04 does not approve. Phase 05 records three required independent reviews, closure re-reviews, finding triage,
and final acceptance.
