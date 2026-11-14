---
name: sage-cycle-fast
description: Run the complete SAGE Fast Cycle by delegating planning to sage-plan-fast and implementation through completion to sage-team-fast.
---

## Overlay catalog selector (mandatory)

If the current boundary supplies `SAGE_OVERLAY_UNAVAILABLE_V1` for this root/role, it invalidates all earlier overlay bodies. Pause this SAGE workflow, explain the input problem, and allow diagnosis/user-directed source repair under the existing independent gates. Never shorten, split, migrate, or omit invalid overlay content automatically. Resume only after the next boundary supplies a valid current catalog.

Current overlay target: `sage-cycle-fast`. Before acting, use the current boundary's supplied
schema-version-2 catalog for the actual checkout `root` and `role: root`, with a definite
`generation`. Use only `targets["sage-cycle-fast"]` references into `sources`; each source has
`path`, `sha256`, and the exact delivered `content`. The applicable source order is:
`skills/sage-cycle/shared` → `skills/sage-cycle-fast/shared` → `skills/sage-cycle/personal` → `skills/sage-cycle-fast/personal`. Include only present sources; an absent slot adds no guidance.

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

# sage-cycle-fast

Invoke as `/sage-cycle-fast` on Claude or `$sage-cycle-fast` on Codex.

This is a **CORE framework bootstrap asset**, hand-shipped by `sage install` and
not manifest-tracked. Do not edit an installed copy directly.

Fast Cycle is an explicitly enabled L2/L3 alternate protocol, not an override.
It keeps actual risk, deterministic verification, acceptance, independent
approval, 05/06, and audit evidence while consolidating physical 01 through 04
documents into one composite 00 Fast Plan.

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

1. Read the shared profile and stop unless `pdca.fast_cycle.enabled: true`.
2. Resolve the current Cycle-Stem and inspect its exact 00 document and Fast audit.
3. If no composite Fast Plan and active Fast run exist, delegate to
   `sage-plan-fast`. Do not duplicate its interview or planning steps here.
   A Fast run has two entry modes and `sage-plan-fast` owns both: a fresh open from a
   composite Phase 00, and — for a cycle already past Phase 00, only when
   `pdca.fast_cycle.standard_transition.enabled` is true — an explicitly confirmed
   `sage fast-cycle convert`. Read the entry mode before judging a document:
   `sage fast-cycle show --run-id <fc-id>` prints `entry=FAST`, `entry=FAST-CONVERTED`, or
   `entry=UNKNOWN`.
   **Only on `entry=FAST-CONVERTED`** is a missing `Fast-Audit-Run` line normal — that run
   binds by stem instead. On `entry=FAST` the same missing or `pending` line is a defect to
   fix, so never treat it as normal without checking which mode you are in.
   On `entry=UNKNOWN` the opener record cannot be read, so neither rule applies. Stop and
   report it. `UNKNOWN` does not mean "not Fast" and it does not mean "treat as fresh" —
   guessing either way makes a damaged audit look like a decided one.
4. After planning/open succeeds, delegate to `sage-team-fast`. Do not duplicate
   its implementation, review, close, or clear steps here.
5. Report the actual risk, Fast review level, selected lenses, reason, Fast run,
   Loop run, and final result.

This umbrella does not execute cycle declaration or audit commands itself. The
two delegated skills own those state transitions so there is one writer per step.

## Delegated worker overlays (separate role packet)

Do not forward the root catalog to workers. When delegating an eligible worker, query that
worker's own kind/id with `sage overlay-local --kind agent --id <worker-id> --root <project-root>`
and pass its validated content and actual target/path/sha256 references in the existing role
packet, alongside the role's shared guidance. Never read raw personal files after a loader error.
For `sage review` / `sage cross-check`, never preappend shared or personal reviewer additions:
the CLI loads them once and emits `SAGE_LOCAL_OVERLAY_REF`. This role-specific CLI path does
not replace automatic delivery of this root skill's shared/personal sources.
