# [Analyze] SAGE-FB-07 L0 Domain Risk Exception

Cycle-Stem: `sage-fb-07-l0-domain-risk-exception`

## Gap Analysis

- The implementation adds a narrow L0 bypass rather than changing global priority. Existing profiles without
  `l0_exclude_globs` retain their exact L0-first behavior.
- Domain paths are materialized to both their configured tier and the exclusion set, so they cannot become `none`.
- Explicit orphan exclusions fail profile validation. The pure core independently classifies a malformed orphan match
  as L3 with `invalid_profile`, preventing runtime fail-open if validation was skipped.
- Domain declarations with invalid or missing `risk_level` fail during raw materialization before they can disappear
  from both the higher-risk owner and L0 exclusion sets, including generate paths that skipped validation.
- Protected CI now materializes validated base/head profiles before classification, aligning server authority with
  local hook behavior.

## QA Coverage

| Scenario | Status | Evidence |
|---|---|---|
| generic image remains L0 | Covered | classifier test |
| domain image becomes L3 | Covered | compiler + classifier test |
| no exclusion preserves old L0-first | Covered | compatibility test |
| L1/L2/L3 domain materialization | Covered | compiler test |
| scalar/blank exclusion rejection | Covered | compiler/profile tests |
| invalid/missing domain risk level | Covered | compiler fail-closed regression |
| orphan exclusion | Covered | validator FAIL + runtime L3 fallback |
| authority adapter parity | Covered | protected adapter materialization test |
| three Claude reviews | Covered | three fresh rounds plus closure review |

## Acceptance Evidence

| ID | Status | Evidence |
|---|---|---|
| FB07-AC1 | PASS | `assets/common/logo.png` remains L0. |
| FB07-AC2 | PASS | excluded `assets/game/board.png` resolves L3. |
| FB07-AC3 | PASS | compiler deduplicates domain paths into `l0_exclude_globs`. |
| FB07-AC4 | PASS | exact higher-risk binding required; orphan fails and runtime escalates. |
| FB07-AC5 | PASS | explicit compatibility test without exclusion. |
| FB07-AC6 | PASS | raw scalar/null/non-string values fail before materialization. |
| FB07-AC7 | PASS | result includes `l0_excluded` provenance. |
| FB07-AC8 | PASS | Three fresh Claude rounds plus closure review completed with findings triaged. |

No Phase-05 verdict is issued here.

## Broad External Review Round 1 Triage

Claude session `7103906f-8bd3-484c-bb8c-937e92496f5a`의 P2는 타당했다. 기존 orphan fallback은 이미 생성된
exclusion에 owner가 없을 때만 동작하므로, compiler가 invalid domain 전체를 버려 exclusion 자체가 사라지는
경우를 방어하지 못했다. Compiler raw contract에서 위험도 enum을 강제해 validation 생략 경로도 BLOCK하도록
수정했고 focused compiler/generate/authority tests로 확인했다.

## External Review Closure

Fresh closure session `ead09722-14af-4538-b8b0-155761c95973` marked FB07 CLEAN. Invalid or missing domain
risk declarations fail during raw compilation, and the authority path consumes the same validated materialization.
