---
id: sage-cycle
kind: skill
# CORE skill (neutral). Project specifics come from profile, not this spec.
# CORE framework bootstrap asset: hand-shipped by `sage install`, NOT manifest-tracked.
# The manifest/claims/validate loop is reserved for project-authored skills
# (spec + claims + render hash) created via the generate/extract flow.
---

## Overlay catalog selector (mandatory)

Current overlay target: `sage-cycle`. Before acting, use the current boundary's supplied
schema-version-2 catalog for the actual checkout `root` and `role: root`, with a definite
`generation`. Use only `targets["sage-cycle"]` references into `sources`; each source has
`path`, `sha256`, and the exact delivered `content`. The applicable source order is:
`skills/sage-cycle/shared` → `skills/sage-cycle/personal`. Include only present sources; an absent slot adds no guidance.

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
Run a full PDCA cycle (Phases 00–06) end to end as a single entry point: delegate
the 00–02 planning half to `/sage-plan`, then the 03–06 implementation→review→
completion half to `/sage-team`. This is a thin umbrella — it never reimplements a
gate and never re-does what the two sub-skills own; it only sequences them and
resumes at the right half.

## when_to_use
- When the user wants to run a feature or change start-to-finish in one flow
- When the user says "/sage-cycle" (Claude), "$sage-cycle" (Codex), "전체 사이클",
  "PDCA 전체", "run the whole cycle", "start to finish", or asks to develop a
  feature end to end without driving each half by hand
- Prefer the sub-skills directly for partial/resume work: `/sage-plan` for 00–02
  only, `/sage-team` to resume 03–06 on an existing plan

## procedure
0. Resolve the conversation language once: an explicit `--lang ko|en` on this skill's
   invocation, then `interface.language` in `sage/project-profile.local.yaml`, then `ko`.
   Every question, proposal, progress note, warning and summary uses it; machine values
   and Phase 00–06 `Document-Language:` prose do not. Document prose includes section headings
   and list labels, except `## 5. Done Criteria` and `## 6. Done Criteria Revision Log`, which a
   parser reads by their exact string. See `docs/agent/language-policy.md`.
1. Read `sage/project-profile.yaml` — confirm bootstrapped (`project.name`
   non-empty, `risk` and `components` set). If not → block, direct to `/sage-init`.
2. Identify the single cycle by its plan-doc stem (the feature name) under
   `paths.plan_docs`, the same way the sub-skills do. Ask for a one-sentence task
   description if not given. Match only that stem; ignore stale docs from other
   cycles (never treat another feature's plan as this cycle's).
   When this is a resumed session and the user supplies a context packet, run
   `sage context restore --snapshot <path>`, then read the generated briefing
   before resolving the half/stage. Never claim hidden conversation state was restored.
3. Planning half: check whether a real, non-empty plan doc for this cycle's stem
   exists.
   - No usable plan (absent/empty/stub) → invoke `/sage-plan` to produce the plan
     (00–02) + ownership map, then continue.
   - A real plan for this stem exists → skip planning; do NOT re-author or fork it.
   Do not make a finer completeness judgment here — defer it to the sub-skills'
   gates. `/sage-plan` owns the 00–02 gate; `/sage-team` re-validates on entry
   (refuses to run without a real plan, resume logic treats presence ≠ completion),
   so a wrong guess here cannot advance an unplanned cycle.
4. Invoke `/sage-team` to drive 03–06 (implementation → deterministic verification →
   QA → Phase-05 review via `/sage-review` → completion), honoring the same
   evidence-anchored resume logic sage-team owns.
   The sub-skills own phase-boundary `sage context snapshot` calls when
   `context_management.compaction.enabled: true`; this umbrella does not duplicate them.
5. Relay the same completion summary `/sage-team` produces: per-phase outcome,
   recorded review `run_id`, generated artifact inventory (each named by path), a summary
   of the retro proposals, verification results, and any pending human action (especially
   retro human-gate review/approval). Do not report the cycle complete on a retro note that
   is still the blank template — `sage-team`'s Done gate requires `sage retro --check` clean
   whenever a note was written (vault disabled → a recorded skip reason instead).

## advisory_scope
- role_boundary: does not implement code and does not reimplement any gate; it only
  sequences `/sage-plan` (00–02) then `/sage-team` (03–06)
- uses: sage-plan skill, sage-team skill, project-profile.yaml, AGENT_GUIDE.md
- convention_doc: AGENT_GUIDE.md
- overlay: optional checkout-local shared/personal additions arrive through the current catalog; mandatory CORE/project policy and independent gates remain authoritative

## runtime_bindings
- claude: .claude/skills/sage-cycle/SKILL.md (repo — Claude Code auto-discovers)
- codex:  $CODEX_HOME/skills/sage-cycle/SKILL.md or .codex/skills/sage-cycle/SKILL.md (explicit global or project-local install scope)

## drift_checks
- conformance: procedure step 3 (delegate/skip planning by real-plan presence for
  the identified cycle stem) and step 4 (delegate 03–06 to sage-team) must be
  present; the umbrella must not reimplement planning, orchestration, or the
  sub-skills' gates itself

## Delegated worker overlays (separate role packet)

Do not forward the root catalog to workers. When delegating an eligible worker, query that
worker's own kind/id with `sage overlay-local --kind agent --id <worker-id> --root <project-root>`
and pass its validated content and actual target/path/sha256 references in the existing role
packet, alongside the role's shared guidance. Never read raw personal files after a loader error.
For `sage review` / `sage cross-check`, never preappend shared or personal reviewer additions:
the CLI loads them once and emits `SAGE_LOCAL_OVERLAY_REF`. This role-specific CLI path does
not replace automatic delivery of this root skill's shared/personal sources.
