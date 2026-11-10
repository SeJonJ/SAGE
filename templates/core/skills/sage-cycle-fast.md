---
id: sage-cycle-fast
kind: skill
---

## Overlay catalog selector (mandatory)

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

## intent
Delegate a complete explicitly enabled Fast Cycle to sage-plan-fast and sage-team-fast without duplicating their state transitions.
## when_to_use
- When the user explicitly requests the profile-enabled Fast Cycle for an L2/L3 change.
## procedure
0. Resolve the conversation language once: an explicit `--lang ko|en` on this skill's
   invocation, then `interface.language` in `sage/project-profile.local.yaml`, then `ko`.
   Every question, proposal, progress note, warning and summary uses it; machine values
   and Phase 00–06 `Document-Language:` prose do not. Document prose includes section headings
   and list labels, except `## 5. Done Criteria` and `## 6. Done Criteria Revision Log`, which a
   parser reads by their exact string. See `docs/agent/language-policy.md`.
1. Confirm shared policy enables Fast Cycle and resolve the current cycle state.
2. Delegate composite planning and audit open to `sage-plan-fast` — a fresh Fast run from a
   composite Phase 00, or, for a cycle already past Phase 00 and only when
   `pdca.fast_cycle.standard_transition.enabled` is true, an explicitly confirmed conversion.
3. Delegate implementation, review, completion evidence, audit close, and cycle clear to `sage-team-fast`.
## advisory_scope
- self_overlay: shared/personal additions are automatically delivered with standard+Fast inheritance; independent Fast state, policy-floor, phase-coverage, review/close and CI oracles preserve structural protections. Delivery and `--confirmed-by` strings do not authenticate human consent.
## runtime_bindings
- claude: .claude/skills/sage-cycle-fast/SKILL.md
- codex: $CODEX_HOME/skills/sage-cycle-fast/SKILL.md or .codex/skills/sage-cycle-fast/SKILL.md

## Delegated worker overlays (separate role packet)

Do not forward the root catalog to workers. When delegating an eligible worker, query that
worker's own kind/id with `sage overlay-local --kind agent --id <worker-id> --root <project-root>`
and pass its validated content and actual target/path/sha256 references in the existing role
packet, alongside the role's shared guidance. Never read raw personal files after a loader error.
For `sage review` / `sage cross-check`, never preappend shared or personal reviewer additions:
the CLI loads them once and emits `SAGE_LOCAL_OVERLAY_REF`. This role-specific CLI path does
not replace automatic delivery of this root skill's shared/personal sources.
