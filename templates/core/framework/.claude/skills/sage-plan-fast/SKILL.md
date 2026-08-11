---
name: sage-plan-fast
description: Author and open a composite 00 Fast Plan for an explicitly enabled L2/L3 Fast Cycle.
---

# sage-plan-fast

Invoke as `/sage-plan-fast` on Claude or `$sage-plan-fast` on Codex.

This is a **CORE framework bootstrap asset**, hand-shipped by `sage install` and
not manifest-tracked. Do not edit an installed copy directly.

## Hard boundary

Before any document, cycle declaration, audit, or source write, explicitly obtain:

1. Fast review level: `L2` or `L3`
2. Lens count: at least the profile minimum and no more than its candidate list
3. One-line reason: non-empty, no secrets, control characters, or line breaks

If any value is missing or invalid, stop without writing anything. Separately
classify the actual `Risk Level`; Fast level never lowers actual risk or its
build/test/lint/acceptance requirements. Fast is unavailable for actual L0/L1.

## Procedure

1. Read the shared/effective profile and confirm `pdca.fast_cycle.enabled: true`.
2. Collect the three required Fast values one focused turn at a time. Select the
   first N configured lenses for the chosen level and show them for approval.
3. Complete the standard planning interview, propose the actual L2/L3 risk, and
   choose a collision-free Cycle-Stem.
4. Run `sage cycle set <stem> --create --risk <actual-risk>`. Fill the generated
   00 as a composite Fast Plan containing `Done-Criteria-Revision: 1`, a concrete
   `### Done Criteria` list of initially unchecked outcomes, and exact `## Phase 00` through
   `## Phase 04` sections. Keep Done Criteria separate from the checked Document Mapping
   readiness list. Preserve the standard Phase 00 prior knowledge,
   summary, impact, risks, conclusion, and Document Mapping checklist.
5. Embed Phase 01 requirements and acceptance matrix, Phase 02 design/failure
   handling, and Phase 03 ownership/checklists/verification plan. Leave Phase 04
   at the exact pre-implementation pending marker.
6. Obtain user approval of the complete 00 through 03 content, check all required
   pre-edit checklist items, and then run:

```text
sage fast-cycle open --stem <stem> --level <L2|L3> --lens-count <N> --reason <reason>
```

7. Confirm the returned `fc-*` id replaced `Fast-Audit-Run: pending` and the open
   event exists in `.sage/fast_cycle.jsonl`. Only then hand off to `sage-team-fast`.

Always repeat the Fast warning at open. Actual L3 with L2 Fast must explicitly say
that verification assurance is lower than standard L3; do not ask for another
confirmation solely because of the warning.
