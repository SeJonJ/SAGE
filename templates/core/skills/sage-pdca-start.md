---
id: sage-pdca-start
kind: skill
# CORE skill (neutral). Project specifics come from profile, not this spec.
# CORE framework bootstrap asset: hand-shipped by `sage install`, NOT manifest-tracked.
# The manifest/claims/validate loop is reserved for project-authored skills
# (spec + claims + render hash) created via the generate/extract flow.
---
## intent
Start a PDCA cycle for a feature: verify gate conditions, invoke the leader to
author plan docs, and distribute file ownership before any L2/L3 code is written.

## when_to_use
- At the beginning of a new feature or change cycle (before implementation)
- When the leader needs to bootstrap plan docs for a task
- When the user says "/sage-pdca-start" (Claude), "$sage-pdca-start" (Codex),
  "start PDCA", "PDCA 시작", "새 기능 시작", or asks to begin a new development cycle

## procedure
1. Read `sage/project-profile.yaml` — confirm the project is bootstrapped
   (`project.name` non-empty, `risk` and `components` set). If not, block and
   direct to `/sage-init`.
2. Read `AGENT_GUIDE.md` — identify the required PDCA phases (00–06) and the
   phase-first rule for L2/L3 files.
3. Determine the task scope: ask the user for a one-sentence description of the
   feature or change if not already provided.
4. Invoke the `leader` agent to:
   a. Author a plan doc under `paths.plan_docs` that covers the task scope.
   b. Distribute file ownership to implementer-a / implementer-b by component.
   c. State the integration point where the two implementers connect.
5. Verify the plan doc exists before handing off:
   check that the file under `paths.plan_docs` is non-empty and references
   the feature scope.
6. Report the ownership map to the user and confirm they are ready to proceed
   to implementation.
7. State the phase flow so the user does not misorder 03/04: 00–02 now (leader);
   03 is opened before source edits with file ownership, implementation checklist,
   and Phase-01 acceptance IDs, then completed after code with implementation,
   unit-test, and verification evidence; 04 = leader + qa judge the
   design↔implementation gap, test coverage, and acceptance evidence (no verdict);
   05 = independent reviewer verdict via `/sage-review`; 06 = report only after
   05 records APPROVED.

## advisory_scope
- role_boundary: does not implement code; invokes leader only
- uses: leader agent, project-profile.yaml, AGENT_GUIDE.md
- convention_doc: AGENT_GUIDE.md

## runtime_bindings
- claude: .claude/skills/sage-pdca-start/SKILL.md (repo — Claude Code auto-discovers)
- codex:  $CODEX_HOME/skills/sage-pdca-start/SKILL.md (global — codex does not auto-discover repo-scoped skills)

## drift_checks
- conformance: procedure step 1 (gate check) and step 4 (leader invocation) must be present
