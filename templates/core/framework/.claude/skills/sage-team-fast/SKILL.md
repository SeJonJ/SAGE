---
name: sage-team-fast
description: Implement, independently review, report, and close an already-open SAGE Fast Cycle.
---

# sage-team-fast

Invoke as `/sage-team-fast` on Claude or `$sage-team-fast` on Codex.

This is a **CORE framework bootstrap asset**, hand-shipped by `sage install` and
not manifest-tracked. Do not edit an installed copy directly.

## Conversation language (mandatory)

Resolve it once, before the first turn, in this order:

1. an explicit `--lang ko|en` on this skill's invocation,
2. `interface.language` in `sage/project-profile.local.yaml`,
3. `ko`.

Conduct **every** question, proposal, progress note, warning and summary in that language.

Only the conversation takes it. Machine values are never translated — paths, globs, command
strings, component ids, strategy enums, statuses and the fixed schema keys. Phase 00–06 document
prose follows the cycle's `Document-Language:` marker, which is a **separate** decision and may
differ from the conversation. That document prose includes the **human-facing structure** — section
headings, list labels, table headers and checklist text — not just paragraphs; a Korean document
under English headings is the mixed state the marker exists to prevent. The two headings a parser
reads by their exact string, `## 5. Done Criteria` and `## 6. Done Criteria Revision Log`, stay
English in every language. Only `/sage-init` and `/sage-init-local` may persist a language
preference. Full rules: `docs/agent/language-policy.md`.

## Procedure

1. Resolve the exact stem, composite 00, `Fast-Audit-Run`, open snapshot, actual
   risk, Fast level, minimum rounds, and selected lenses. Stop on ambiguity,
   malformed audit, mismatch, or terminal run.
   Read the cycle's document language from the composite Phase 00's `Document-Language:`
   line before writing anything. Every phase document you author (05, 06) carries that same
   line and is written in that language; a run with no marker predates it — keep writing in
   the language the composite document already uses. See `docs/agent/language-policy.md`.
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

Update the composite `### Done Criteria` after virtual Phase 03 and Phase 04 evidence.
Only demonstrated items become `[x]`; exclusions require `[~] ... (N/A: reason)`. If an
item or its scope changes, increment `Done-Criteria-Revision`, record the reason and affected
virtual phases, and rerun those phases. Review and close require zero unresolved items.

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
