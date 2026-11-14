---
id: sage-team-fast
kind: skill
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

## intent
Implement and verify an open Fast run, bind exact lens review receipts, write 05 and 06, perform standard completion work, and close before clearing.
## when_to_use
- When a composite Fast Plan has a clean active Fast audit run and is ready for implementation.
## procedure
0. Resolve the conversation language once: an explicit `--lang ko|en` on this skill's
   invocation, then `interface.language` in `sage/project-profile.local.yaml`, then `ko`.
   Every question, proposal, progress note, warning and summary uses it; machine values
   and Phase 00–06 `Document-Language:` prose do not. Document prose includes section headings
   and list labels, except `## 5. Done Criteria` and `## 6. Done Criteria Revision Log`, which a
   parser reads by their exact string. See `docs/agent/language-policy.md`.
1. Verify the exact stem, composite plan, audit state, ownership, actual risk, Fast level, rounds, and lenses.
2. Implement and verify while updating composite Done Criteria. Replanning increments its
   revision and records a reason plus affected virtual phases, which are rerun. Require all
   criteria resolved, then run independent review with exact per-round lens receipts and bind APPROVED Phase 05.
3. Write bound Phase 06, complete write-back, retro, and snapshot, then close the Fast audit before clearing the cycle.
## advisory_scope
- self_overlay: shared/personal additions are automatically delivered with standard+Fast inheritance; independent Fast state, policy-floor, phase-coverage, review/close and CI oracles preserve structural protections. Delivery and `--confirmed-by` strings do not authenticate human consent.
## runtime_bindings
- claude: .claude/skills/sage-team-fast/SKILL.md
- codex: $CODEX_HOME/skills/sage-team-fast/SKILL.md or .codex/skills/sage-team-fast/SKILL.md

## Delegated worker overlays (separate role packet)

Do not forward the root catalog to workers. When delegating an eligible worker, query that
worker's own kind/id with `sage overlay-local --kind agent --id <worker-id> --root <project-root>`
and pass its validated content and actual target/path/sha256 references in the existing role
packet, alongside the role's shared guidance. Never read raw personal files after a loader error.
For `sage review` / `sage cross-check`, never preappend shared or personal reviewer additions:
the CLI loads them once and emits `SAGE_LOCAL_OVERLAY_REF`. This role-specific CLI path does
not replace automatic delivery of this root skill's shared/personal sources.
