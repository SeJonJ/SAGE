---
id: sage-plan-fast
kind: skill
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

## intent
Collect all mandatory Fast inputs, author the composite 00 through 04 plan, and open a bound audited Fast run before source edits.
## when_to_use
- When an enabled Fast Cycle needs its mandatory inputs and composite Phase 00 before implementation.
## procedure
0. Resolve the conversation language once: an explicit `--lang ko|en` on this skill's
   invocation, then `interface.language` in `sage/project-profile.local.yaml`, then `ko`.
   Every question, proposal, progress note, warning and summary uses it; machine values
   and Phase 00–06 `Document-Language:` prose do not. Document prose includes section headings
   and list labels, except `## 5. Done Criteria` and `## 6. Done Criteria Revision Log`, which a
   parser reads by their exact string. See `docs/agent/language-policy.md`.
1. Collect Fast level, lens count, and one-line reason before any write; classify actual L2/L3 risk separately.
2. Author one composite Phase 00 with `Done-Criteria-Revision: 1`, a concrete
   `### Done Criteria` list of `[ ]` outcomes, exact embedded Phase 00 through 04
   sections, the separate Document Mapping checklist, and acceptance trace.
   Settle the cycle's document language in the same pass: Phase 00's `Document-Language:`
   line if that document exists, else `document_language` in `.sage/cycle.json`, else ask
   the user and record it with `sage cycle set <stem> --create --document-language <ko|en>`.
   The composite document carries that one line outside any code fence and is written in
   that language, fixed for the whole Fast run — see `docs/agent/language-policy.md`.
3. Declare the verified stem and run `sage fast-cycle open`; hand off only after its audit run is bound.
4. A cycle already past Phase 00 converts instead of re-authoring: `sage fast-cycle convert`,
   available only when `pdca.fast_cycle.standard_transition.enabled` is true. The confirmation
   token, reason and approver come from the user in that turn and are never inferred. The
   conversion writes no document; the audit record is the only evidence of the transition, and
   the run waives only the pre-implementation phases its snapshot can show.
## advisory_scope
- self_overlay: shared/personal additions are automatically delivered with standard+Fast inheritance; independent Fast state, policy-floor, phase-coverage, review/close and CI oracles preserve structural protections. Delivery and `--confirmed-by` strings do not authenticate human consent.
## runtime_bindings
- claude: .claude/skills/sage-plan-fast/SKILL.md
- codex: $CODEX_HOME/skills/sage-plan-fast/SKILL.md or .codex/skills/sage-plan-fast/SKILL.md

## Delegated worker overlays (separate role packet)

Do not forward the root catalog to workers. When delegating an eligible worker, query that
worker's own kind/id with `sage overlay-local --kind agent --id <worker-id> --root <project-root>`
and pass its validated content and actual target/path/sha256 references in the existing role
packet, alongside the role's shared guidance. Never read raw personal files after a loader error.
For `sage review` / `sage cross-check`, never preappend shared or personal reviewer additions:
the CLI loads them once and emits `SAGE_LOCAL_OVERLAY_REF`. This role-specific CLI path does
not replace automatic delivery of this root skill's shared/personal sources.
