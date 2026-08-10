---
name: sage-team-fast
description: Implement, independently review, report, and close an already-open SAGE Fast Cycle.
---

# sage-team-fast

Invoke as `/sage-team-fast` on Claude or `$sage-team-fast` on Codex.

This is a **CORE framework bootstrap asset**, hand-shipped by `sage install` and
not manifest-tracked. Do not edit an installed copy directly.

## Procedure

1. Resolve the exact stem, composite 00, `Fast-Audit-Run`, open snapshot, actual
   risk, Fast level, minimum rounds, and selected lenses. Stop on ambiguity,
   malformed audit, mismatch, or terminal run.
2. Implement only within recorded ownership. Keep Phase 03 current with changed
   files and real build/test/lint results required by the actual risk.
3. Replace the Phase 04 pending marker with design-gap, coverage, acceptance
   evidence, and external review context. Required acceptance IDs must have real
   evidence under the existing acceptance contract.
4. Run the existing independent `sage-review` loop, not a copied review engine.
   Open the Loop Audit with the exact stem and selected lenses, and record every
   round with exact lens receipts:

```text
sage review-loop open --risk <actual-risk> --cycle-stem <stem> --lenses <comma-list>
sage review-loop round ... --lens-receipts <comma-list>
sage review-loop close ...
```

   Continue until APPROVED or BLOCKED. Minimum rounds are a floor, not automatic
   approval. Every selected lens must run in every counted round.
5. Write 05 with exact `Fast-Run`, `Loop-Run`, and `Final Status: APPROVED`, then:

```text
sage fast-cycle review --run-id <fc-id> --loop-run-id <loop-id>
```

6. After report gates pass, write 06 with the same two run ids and final status.
7. Perform the standard write-back, retro, and context snapshot steps. These are
   not reduced by Fast Cycle.
8. Close in this exact order:

```text
sage fast-cycle close --run-id <fc-id>
sage cycle clear
```

   Never clear first. If the work is intentionally abandoned, use
   `sage fast-cycle abort --run-id <fc-id> --reason <reason>` and then clear.
9. Final reporting includes actual risk, Fast level, rounds, lenses, reason,
   Fast/Loop ids, verification results, and `.sage/fast_cycle.jsonl`.
