---
name: sage-plan-fast
description: Author and open a composite 00 Fast Plan for an explicitly enabled L2/L3 Fast Cycle.
---

## Overlay catalog selector (mandatory)

If the current boundary supplies `SAGE_OVERLAY_UNAVAILABLE_V1` for this root/role, it invalidates all earlier overlay bodies. Pause this SAGE workflow, explain the input problem, and allow diagnosis/user-directed source repair under the existing independent gates. Never shorten, split, migrate, or omit invalid overlay content automatically. Resume only after the next boundary supplies a valid current catalog.

Current overlay target: `sage-plan-fast`. Before acting, use the current boundary's supplied
schema-version-2 catalog for the actual checkout `root` and `role: root`, with a definite
`generation`. Use only `targets["sage-plan-fast"]` references into `sources`; each source has
`path`, `sha256`, and the exact delivered `content`. The applicable source order is:
`skills/sage-plan/shared` → `skills/sage-plan-fast/shared` → `skills/sage-plan/personal` → `skills/sage-plan-fast/personal`. Include only present sources; an absent slot adds no guidance.

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

# sage-plan-fast

Invoke as `/sage-plan-fast` on Claude or `$sage-plan-fast` on Codex.

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

## Hard boundary

Before any document, cycle declaration, audit, or source write, explicitly obtain:

1. Fast review level: `L2` or `L3`
2. Lens count: at least the profile minimum and no more than its candidate list
3. One-line reason: non-empty, no secrets, control characters, or line breaks

If any value is missing or invalid, stop without writing anything. Separately
classify the actual `Risk Level`; Fast level never lowers actual risk or its
build/test/lint/acceptance requirements. Fast is unavailable for actual L0/L1.

Shared/personal standard+Fast additions use the catalog above. Independent Fast state,
policy-floor, phase-coverage, review/close and CI oracles preserve structural protections;
neither delivered text nor `--confirmed-by` strings authenticate human consent.

## Procedure

1. Read the shared/effective profile and confirm `pdca.fast_cycle.enabled: true`.
2. Collect the three required Fast values one focused turn at a time. Select the
   first N configured lenses for the chosen level and show them for approval.
3. Complete the standard planning interview, propose the actual L2/L3 risk, and
   choose a collision-free Cycle-Stem.
   Ask which language this run's composite Phase 00 through 06 should be written in
   (`ko` or `en`) unless an existing Phase 00 for this stem already carries a
   `Document-Language:` line — that line wins and is not re-asked. This is the
   document language, not the language you talk in; see `docs/agent/language-policy.md`.
4. Run `sage cycle set <stem> --create --risk <actual-risk> --document-language <ko|en>`.
   Fill the generated 00 as a composite Fast Plan containing `Done-Criteria-Revision: 1`, a
   concrete `### Done Criteria` list of initially unchecked outcomes, and exact `## Phase 00`
   through `## Phase 04` sections. Keep Done Criteria separate from the checked Document
   Mapping readiness list. Preserve the standard Phase 00 prior knowledge,
   summary, impact, risks, conclusion, and Document Mapping checklist. Confirm the generated
   skeleton's `Document-Language:` line matches what was asked; it is fixed for the whole
   Fast run and every phase document you author stays in that language.
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

## Converting a Standard Cycle already in progress

A cycle that is already past Phase 00 has no composite plan, and authoring one now would
rewrite documents the cycle already produced. Use the conversion instead — but only when
`pdca.fast_cycle.standard_transition.enabled: true`. If that key is absent or false, the
conversion is unavailable: say so and continue as a Standard Cycle. Never propose editing the
profile mid-cycle to unlock it.

```text
sage fast-cycle convert --stem <stem> --current-phase <00|01|02|03|04> \
  --level <L2|L3> --lens-count <N> --reason <reason> \
  --confirmed-by <approver> --confirm FAST-CONVERTED
```

**The confirmation is the user's, not yours.** `--confirm FAST-CONVERTED`, `--reason` and
`--confirmed-by` must come from the user in this turn. Do not infer them from context, reuse
them from an earlier run, or supply the token because the intent seems obvious. Without all
three the command writes nothing.

`--confirmed-by` is the name the user states in that turn — not `git config`, the profile, or
the host account, which record who is typing rather than who approved the transition.
`--reason` carries the user's own words; do not summarise or improve them.

What the conversion does and does not do:

- It writes no document. Existing Phases 00–04 are not deleted, moved, merged, or rewritten,
  and no conversion metadata is inserted into them.
- The audit record in `.sage/fast_cycle.jsonl` is the only evidence of the transition. It
  records the phases that already existed at conversion time.
- The converted run waives only the pre-implementation phases that snapshot can show. Convert
  at Phase 00 and the plan documents are still required before source edits.
- Actual `Risk Level` still comes from the existing Phase 00 and is unchanged by the
  conversion; only the review contract changes.

After a successful convert, hand off to `sage-team-fast` exactly as with a fresh open. The
converted run has no `Fast-Audit-Run` line to check — it binds by stem and its single active
run, so do not add one to the document.

## Delegated worker overlays (separate role packet)

Do not forward the root catalog to workers. When delegating an eligible worker, query that
worker's own kind/id with `sage overlay-local --kind agent --id <worker-id> --root <project-root>`
and pass its validated content and actual target/path/sha256 references in the existing role
packet, alongside the role's shared guidance. Never read raw personal files after a loader error.
For `sage review` / `sage cross-check`, never preappend shared or personal reviewer additions:
the CLI loads them once and emits `SAGE_LOCAL_OVERLAY_REF`. This role-specific CLI path does
not replace automatic delivery of this root skill's shared/personal sources.
