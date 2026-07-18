# [Expert Review] SAGE-FB-07 L0 Domain Risk Exception

Cycle-Stem: `sage-fb-07-l0-domain-risk-exception`
Risk Level: L3
Review-Mode: Claude fresh headless, read-only, no subagents
Final Status: APPROVED

## 1. Review Evidence

Required reviews ran in fresh sessions `7103906f-8bd3-484c-bb8c-937e92496f5a`,
`637f2d5c-1597-4b9a-a373-8e0b6bc1ebe1`, and `a01c9b7a-ee27-483b-9650-bd836aa264ca`.
Round 1 found that an invalid domain risk could disappear before an exclusion was materialized; this was accepted and
fixed at the raw compiler boundary. Closure session `ead09722-14af-4538-b8b0-155761c95973` marked FB07 CLEAN.

## 2. Acceptance

FB07-AC1 through FB07-AC8 are PASS. Domain-owned image globs bypass only the L0 fast path and retain their configured
L1/L2/L3 owner; invalid, missing, scalar, blank, or orphan configuration fails closed. Profiles without the new exclusion
preserve the previous L0-first behavior.

## 3. Verification

- Compiler/classifier/profile aggregate: 231 passed before final hardening.
- Authority and local gate parity aggregate: 125 passed.
- Full Python suite: 1,316 passed, 1 skipped.
- Official hook suite and static checks: PASS.

## 4. Decision

The exception is narrow, explicit, provenance-bearing, and compatible with existing profiles. All required evidence is
complete; the cycle is APPROVED.
