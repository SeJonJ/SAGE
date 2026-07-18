# [Implementation] SAGE-FB-07 L0 Domain Risk Exception

Cycle-Stem: `sage-fb-07-l0-domain-risk-exception`

## Ownership

| Owner | Files |
|---|---|
| Compiler/profile | `sage/profile_compile.py`, `sage/profile_validate.py`, `schema/profile.schema.json`, template profile |
| Risk core | `scripts/sage_harness/hooks/pre_implementation_gate_core.py` |
| QA | `test_profile_compile.py`, `test_profile_validate.py`, `test_pre_implementation_gate.py`, `run-all.sh` |

## Checklist

- [x] Write failing compiler/classifier/validator tests.
- [x] Add raw and compiled exclusion contract.
- [x] Materialize domain paths into exclusions.
- [x] Bypass L0 only for bound higher-risk paths and retain provenance.
- [x] Run focused and official regression suites.
- [x] Complete three fresh Claude review rounds.

## Evidence

- RED: missing compiled exclusion key; domain image remained L0; orphan exclusion was not rejected; authority adapter
  returned raw profile and omitted domain materialization.
- GREEN: compiler/classifier/profile focused aggregate `231 tests` passed.
- Protected authority module: `16 tests` passed, including raw Git profile materialization.
- Official hook suite: `ALL HOOK TESTS PASS`.
- `git diff --check`: pass.

## Broad External Review Round 1

- Reviewer: Claude headless session `7103906f-8bd3-484c-bb8c-937e92496f5a`.
- 수용(P2): schema validation을 거치지 않는 `generate` 경로에서 invalid/missing domain `risk_level`이 조용히
  누락되어 L0 exclusion과 higher-risk owner가 모두 사라졌다.
- 수정: raw compiler contract가 각 domain의 `risk_level`을 exact `L1|L2|L3`로 검사하고 그 외 값은
  `ProfileCompileError`로 fail-closed한다. Unknown/missing regression과 generate/authority aggregate가 PASS했다.
