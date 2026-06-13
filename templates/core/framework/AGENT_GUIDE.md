# AGENT_GUIDE.md

This is the runtime-neutral single source of truth (SSOT) for common rules,
workflow, risk routing, safety boundaries, and Definition of Done. Both host
runtimes ({wrapper} = CLAUDE.md | CODEX.md) are thin overrides on top of this.

Project-specific values (paths, risk triggers, conventions, team) live in
`sage/project-profile.yaml`, not here. This guide stays neutral.

## Mandatory read (session start)

1. `AGENT_GUIDE.md` (this file)
2. `sage/project-profile.yaml` — project values
3. Relevant plan doc under `{paths.plan_docs}`
4. Relevant convention docs declared in `profile.conventions`

## Workflow (PDCA)

Plan → Do → Check → Act. Write a plan doc before non-trivial implementation.
Implement against the plan. Verify with `scripts/verify-changes.sh`. Capture
learnings.

## Risk routing (L1/L2/L3)

Risk levels are classified from `profile.risk` (path globs + content keywords),
not from hardcoded domain knowledge. See `docs/agent/risk-classification.md`.

- **L1** — low blast radius (UI/markup). Advisory checks.
- **L2** — source/config changes. Build + test + lint gate (block).
- **L3** — high-risk domains declared in `profile.risk`. Requires a plan doc and
  an independent review (see `docs/agent/review-protocol.md`).

The `pre-implementation-gate` hook enforces this from the profile.

## Non-negotiable safety boundaries

- Do not run `git commit` or `git push` unless the user explicitly asks.
- Do not perform destructive or outward-facing actions without confirmation.
- Do not directly edit generated artifacts (`{host}/agents`, `{host}/skills`,
  `{host}/hooks`) — edit the spec under `docs/sage_harness/` and regenerate.
- Report outcomes faithfully: if tests fail, say so with the output.

These are inherited by every agent/skill claim set as
`AGENT_GUIDE.non_negotiable_boundaries` (referenced, never copied).

## Definition of Done

- Plan doc updated; implementation matches the plan.
- `scripts/verify-changes.sh` passes at the required gate level.
- Conventions in `profile.conventions` satisfied.
- No direct edits to generated artifacts.
