---
id: sage-review
kind: skill
# CORE skill (neutral). Review mode resolved by sage doctor from profile.
# CORE framework bootstrap asset: hand-shipped by `sage install`, NOT manifest-tracked.
# The manifest/claims/validate loop is reserved for project-authored skills
# (spec + claims + render hash) created via the generate/extract flow.
---
## intent
Run Phase-05 independent review: invoke the reviewer agent (same-runtime clean
context or opposite-runtime cross-model, as resolved by sage doctor) and produce
a structured review report for the current implementation cycle.

## when_to_use
- After implementers complete code and qa completes testing (Phase-04 done)
- Before merging or tagging any L3 change (mandatory sign-off)
- When the user says "/sage-review", "phase-05", "독립 검토", "Phase-05 리뷰",
  or "cross-model review"

## procedure
1. Read `sage/project-profile.yaml` — check `options.cross_model` and
   `cross_model.invocation` to determine the review mode:
   - `cross_model: true` + invocation reachable → opposite-runtime review
   - Otherwise → clean-context same-runtime review
2. Read `docs/agent/review-protocol.md` — the authoritative review output format.
3. Invoke the `reviewer` agent in the resolved mode:
   a. Pass the plan doc path(s) for the current cycle.
   b. Pass the implementer output summary (file paths changed, unit test results).
   c. Pass the qa findings summary.
4. The reviewer produces a structured report per `docs/agent/review-protocol.md`.
   Do not intervene in the reviewer's findings — report them verbatim.
5. If the reviewer issues a BLOCK on an L3 change, record the block in the plan
   doc and stop — do not proceed to release until the reviewer clears it.
6. Record the review outcome in the plan doc under a `## Phase-05 Review` section.

## advisory_scope
- role_boundary: does not implement or modify code; orchestrates reviewer only
- uses: reviewer agent, project-profile.yaml, review-protocol.md
- cross_model: resolved by sage doctor; falls back to clean-context same-runtime
- convention_doc: docs/agent/review-protocol.md

## runtime_bindings
- claude: .claude/skills/sage-review/SKILL.md (repo — Claude Code auto-discovers)
- codex:  $CODEX_HOME/skills/sage-review/SKILL.md (global — codex does not auto-discover repo-scoped skills)

## drift_checks
- conformance: procedure step 1 (profile check) and step 3 (reviewer invocation) must be present
