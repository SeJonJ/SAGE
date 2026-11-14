---
name: sage-team-fast
description: Implement, independently review, report, and close an already-open SAGE Fast Cycle.
---

## Overlay catalog selector (mandatory)

If the current boundary supplies `SAGE_OVERLAY_UNAVAILABLE_V1` for this root/role, it invalidates all earlier overlay bodies. Pause this SAGE workflow, explain the input problem, and allow diagnosis/user-directed source repair under the existing independent gates. Never shorten, split, migrate, or omit invalid overlay content automatically. Resume only after the next boundary supplies a valid current catalog.

Current overlay target: `sage-team-fast`. Before acting, use the current boundary's supplied
schema-version-2 catalog for the actual checkout `root` and `role: root`, with a definite
`generation`. Use only `targets["sage-team-fast"]` references into `sources`; each source has
`path`, `sha256`, and the exact delivered `content`. The applicable source order is:
`skills/sage-team/shared` → `skills/sage-team-fast/shared` → `skills/sage-team/personal` → `skills/sage-team-fast/personal`. Include only present sources; an absent slot adds no guidance.

Mandatory CORE, project policy, and independent gates take precedence over shared additions,
which take precedence over personal additions. Later entries do not automatically override
earlier ones. Other targets' bodies may be visible in the same context; do not apply them.
Catalog presence is never a skill invocation, Fast selection/conversion, or user approval.
Use the delivered content without a separate root-skill `overlay-local` fetch. Do not embed
personal bodies in shared/global renders, manifests, or permanent caches.

The current boundary's catalog, including an empty `sources`/`targets` catalog, replaces prior
catalog guidance. Do not revive historical content, infer freshness from hashes/mtime, or use
another checkout's sources. If the current root, role, generation/boundary, or active target is
missing or ambiguous, stop and request a context/input fix instead of guessing a recent target.
After compaction, manual skill reselection is not successful automatic recovery. Repeated
copies of the same generation/source are the same guidance, not instructions to repeat steps.

On nested plan/team/review invocation, use that child's own fixed target view rather than
merging the parent's sources; on return, resume this parent's view. This contract adds no
target stack database. Keep actual delivery path/hash references from this boundary for handoff;
a catalog supply list does not prove that every listed target was applied or complied with.

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

Shared/personal standard+Fast additions use the catalog above. Independent Fast state,
policy-floor, phase-coverage, review/close and CI oracles preserve structural protections;
neither delivered text nor `--confirmed-by` strings authenticate human consent.

## Procedure

1. Resolve the exact stem, entry mode, open snapshot, actual risk, Fast level, minimum
   rounds, and selected lenses. Stop on ambiguity, malformed audit, mismatch, or terminal run.
   **Read the entry mode first** — `sage fast-cycle show --run-id <fc-id>` prints
   `entry=FAST`, `entry=FAST-CONVERTED`, or `entry=UNKNOWN`, and they are not interchangeable:
   - `FAST` — a fresh run. Resolve the composite Phase 00 and its `Fast-Audit-Run` line as
     below; a missing or `pending` line there is a defect to fix before continuing.
   - `FAST-CONVERTED` — a Standard Cycle converted in place. There is **no composite Phase 00
     and no `Fast-Audit-Run` line**, and there must not be: the conversion writes no document.
     The cycle keeps its ordinary Phase 00–04 documents. Never add a `Fast-Audit-Run` line,
     Fast metadata, or a composite section to them — the run binds by stem and its single
     active converted run, and the engine reads risk and Done Criteria from the standard
     documents.
   - `UNKNOWN` — the opener record cannot be read (damaged, hand-edited, or legacy audit).
     Neither rule above applies. Stop and report it; do not fall back to either mode.
     `UNKNOWN` is not "not Fast" and not "treat as fresh" — guessing either way makes a
     damaged audit look decided, which is exactly what this step exists to prevent.
   For `FAST`, read the cycle's document language from the composite Phase 00. For
   `FAST-CONVERTED`, read it from the existing Standard Phase 00 instead. Every phase document
   you author (05, 06) carries that same
   line and is written in that language; a run with no marker predates it — keep writing in
   the language the selected Phase 00 already uses. See `docs/agent/language-policy.md`.
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

Update the Done Criteria after Phase 03 and Phase 04 evidence — the composite
`### Done Criteria` on a `FAST` run, and the standard Phase 00 `## 5. Done Criteria` on a
`FAST-CONVERTED` run (its phases are real documents, not virtual sections).
Only demonstrated items become `[x]`; exclusions require `[~] ... (N/A: reason)`. If an
item or its scope changes, increment `Done-Criteria-Revision`, record the reason and affected
phases, and rerun those phases. Review and close require zero unresolved items.

   Continue until APPROVED or BLOCKED. Minimum rounds are a floor, not automatic
   approval. Every selected lens must run in every counted round.
5. Write 05 with exact `Fast-Run`, `Loop-Run`, and `Final Status: APPROVED`. If the Loop
   Audit closed with `USER_AUTHORIZED_EARLY`, the same 05 also carries the four
   reduced-assurance markers (`Review-Assurance`, `Review-Close-Reason`, `Review-Rounds`,
   `Residual-Findings`) with values matching the audit record, including the
   `(configured max: <max>)` ceiling on `Review-Rounds`. What triggers the check is the value,
   not the presence of a marker — a neutral `Review-Rounds:` line on a converged run is fine.
   See `sage-review`. Then:

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

## Delegated worker overlays (separate role packet)

Do not forward the root catalog to workers. When delegating an eligible worker, query that
worker's own kind/id with `sage overlay-local --kind agent --id <worker-id> --root <project-root>`
and pass its validated content and actual target/path/sha256 references in the existing role
packet, alongside the role's shared guidance. Never read raw personal files after a loader error.
For `sage review` / `sage cross-check`, never preappend shared or personal reviewer additions:
the CLI loads them once and emits `SAGE_LOCAL_OVERLAY_REF`. This role-specific CLI path does
not replace automatic delivery of this root skill's shared/personal sources.
