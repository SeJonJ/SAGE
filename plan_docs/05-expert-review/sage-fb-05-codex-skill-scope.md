# [Expert Review] SAGE-FB-05 Codex CORE Skill Installation Scope

Cycle-Stem: `sage-fb-05-codex-skill-scope`
Risk Level: L3
Review-Mode: Claude fresh headless, read-only, no subagents
Final Status: APPROVED

## 1. Review Evidence

| Round | Session | Resolution |
|---|---|---|
| 1 | `7103906f-8bd3-484c-bb8c-937e92496f5a` | correctness review, no FB05 blocker |
| 2 | `637f2d5c-1597-4b9a-a373-8e0b6bc1ebe1` | symlink legacy marker deletion reproduced and fixed |
| 3 | `a01c9b7a-ee27-483b-9650-bd836aa264ca` | cross-repository global install race fixed with shared lock |
| Closure | `ead09722-14af-4538-b8b0-155761c95973` | FB05 CLEAN |

## 2. Acceptance

FB05-AC1 through FB05-AC10 are PASS. Codex installation requires explicit `global|project-local` scope, records a
receipt, diagnoses duplicates without deleting user-owned copies, and includes the selected write root in transaction
rollback and locking.

## 3. Verification

- Install/transaction aggregate after shared-lock fix: 22 passed.
- Full Python suite: 1,316 passed, 1 skipped.
- Official hook suite and static checks: PASS.

## 4. Residual Risk

When both scopes are present, SAGE cannot prove Codex runtime precedence from filesystem state alone. It reports the
ambiguity and exact cleanup guidance. Global validation also depends on the live environment; doctor remains the live
diagnostic surface.

## 5. Decision

Explicit scope, receipt, drift diagnostics, rollback, and cross-repository lock behavior satisfy the approved design.
The cycle is APPROVED.
