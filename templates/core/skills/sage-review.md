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
1. Read `sage/project-profile.yaml` — `options.cross_model` + `cross_model.invocation`
   resolve the review mode (cross_model:true + reachable → opposite-runtime; else
   clean-context same-runtime); `pdca.review_loop` resolves pass vs loop.
2. Read `docs/agent/review-protocol.md` — the authoritative output format + loop contract.
3. Choose pass vs loop:
   - `review_loop.enabled` false/absent, or risk L0/L1 → single-pass reviewer invocation.
   - `review_loop.enabled: true` + risk L2/L3 → adversarial review-rework loop (Loop A).
4. Single-pass: invoke the `reviewer` agent in the resolved mode with plan doc path(s),
   implementer summary (changed files, unit tests), qa findings, and the Phase 01/04
   acceptance matrix/evidence. Report findings verbatim.
5. Loop A (find→refute→triage→rework→terminate): drive rounds per review-protocol.md;
   record each boundary with `sage review-loop` (open/round/close). Counters, budget, and
   termination are SAGE-owned (deterministic); judgement (find/refute/rework) runs in-host.
   architecture_change at L3 → BLOCKED_ARCH (human escalation), never auto-reworked.
6. Required acceptance items marked `FAIL` or `NOT TESTED` in Phase 04 block `APPROVED`.
   Use `N/A` only with explicit out-of-scope/deferred/user-approved reasoning.
7. BLOCK / BLOCKED on an L3 change → record in the plan doc and stop (no release until cleared).
   The report←approve hook (06←05 APPROVED) is the deterministic backstop — never bypass it.
8. Record the outcome under `## Phase-05 Review` (Loop A: include Review Loop Iterations
   table + audit run_id). Write a `Loop-Run: <run_id>` line in the Phase-05 doc so the
   06←05 audit gate (report_gate_enforce) can bind the report to this closed APPROVED run.

## advisory_scope
- role_boundary: does not implement or modify code; orchestrates reviewer/implementer only
- uses: reviewer agent, project-profile.yaml, review-protocol.md, `sage review-loop` CLI
- cross_model: resolved by sage doctor; falls back to clean-context same-runtime
- review_loop: deterministic gates (counters/budget/termination/audit) SAGE-owned; the loop
  never bypasses the report←approve (06←05) backstop
- convention_doc: docs/agent/review-protocol.md

## runtime_bindings
- claude: .claude/skills/sage-review/SKILL.md (repo — Claude Code auto-discovers)
- codex:  $CODEX_HOME/skills/sage-review/SKILL.md (global — codex does not auto-discover repo-scoped skills)

## drift_checks
- conformance: procedure step 1 (profile check incl. review_loop) and step 4/5 (reviewer
  invocation / Loop A drive) must be present
