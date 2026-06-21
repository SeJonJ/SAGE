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

## Project Bootstrap (conversational authoring)

Profile values, specs, and plan docs are **authored by the agent through
conversation, not hand-written by the user** — the user supplies intent and
approves; `sage generate` / `sage validate` then register and verify
deterministically (some assets, e.g. agent/skill renders, still need an
interpretive runtime render step). The profile schema is a guardrail (strict on
top-level + selected sections), not a total type-checker. When a project is first
set up, or a new component/asset is introduced, follow
`docs/agent/bootstrap-authoring.md`: interview → fill profile values → handoff
(`generate` + `validate`) → phase-first plan docs before any code. Never add
schema keys, never edit generated artifacts, never bypass a `validate` FAIL.

The conversational entry point is the **`/sage-init` skill**. It and the other
**CORE framework bootstrap assets** — the `pdca-start` / `sage-review` / `sage-asset`
skills and the six CORE roster agent renders (`leader`, `implementer-a`,
`implementer-b`, `qa`, `reviewer`, `convention-checker`) — are hand-shipped by `sage install` like
this guide and `docs/agent/*`. They are NOT manifest-tracked: the
manifest/claims/`validate` loop is reserved for project-authored assets created
via `generate`/`extract`. The write-guard exempts their paths (editing them
directly is allowed — there is no spec→generate redirect). The CORE skills ship
reference specs under `docs/sage_harness/skills/` (sage-init has none), but those
specs are not manifest-registered. Until the profile is bootstrapped
(`project.name` set + `risk`/`components` configured), `sage generate` is BLOCKED
and `sage validate` WARNs — by design, so an empty profile cannot silently
disable the governance gate.

Runtime discovery differs by host, and `sage install` picks one host (claude OR
codex), so each install deploys only that host's copies. On a **claude** host,
Claude auto-discovers repo-scoped skills and agents under `.claude/` (CORE skills →
`.claude/skills/`, CORE agents → `.claude/agents/`). On a **codex** host, Codex does
not auto-discover repo-scoped skills, so CORE skills install to the user-global
`$CODEX_HOME/skills/` (`$sage-init`, `$pdca-start`, `$sage-review`, `$sage-asset`); and since Codex
has no native subagent auto-discovery either, the CORE roster agent renders install
to repo `.codex/agents/<id>.md` (the SAGE-canonical asset path), which the Codex AI
references as role definitions via the `AGENTS.md` router rather than native
invocation. Codex users also follow `docs/agent/bootstrap-authoring.md` (see `CODEX.md`).

## Risk & Workflow Gate (PDCA)

Every change is classified before implementation. Compound changes use the
highest applicable level. Levels are classified from `profile.risk` (path globs +
content keywords), not from hardcoded domain knowledge — see
`docs/agent/risk-classification.md`.

### PDCA phases

Work proceeds through numbered phase documents under `{paths.plan_docs}`. The
phase set and per-level obligation are defined in `profile.pdca`; the standard
set is:

| Phase | Name | Nature |
|:---:|:---|:---|
| 00 | Base Plan | CONTEXT — why / what / impact / prior knowledge / risk |
| 01 | Plan | CONTENT — requirements, data model, API spec |
| 02 | Design | architecture, sequence, error codes |
| 03 | Implementation | file ownership, checklist, build/test evidence |
| 04 | Analyze | design↔implementation gap (no verdict here) |
| 05 | Expert Review | independent synthesis + final APPROVED/FAIL/BLOCKED |
| 06 | Report | completion report — only after 05 = APPROVED |

Phase definitions, separation rules (00 vs 01, 02 vs 03, 04 vs 05), templates,
and component-level plan_docs are in `docs/agent/pdca-templates.md`.

### Risk → mandatory phase range

| Level | Category (from `profile.risk`) | Required phases | Gate |
|:---:|:---|:---|:---|
| **L0** | docs / text only | none | summary + skipped-validation reason |
| **L1** | low blast radius (UI/markup) | 00–03 (lightweight note allowed) | advisory |
| **L2** | source/config | 00–05 | build + test + lint (block) |
| **L3** | high-risk domains | 00–06 | + independent review rounds before done |

### Mandatory Writing Rule

- The phase range for the level is **mandatory writing**, configured in
  `profile.pdca.pre_implementation_required` (phases required *before* a code
  change) and enforced by the `pre-implementation-gate` hook: a missing required
  phase **blocks** L2/L3 implementation (warns at L1).
- An empty `plan_docs/{phase}/` directory is **not** a convention — treat it as a
  prior task's omission, never a precedent for skipping.
- Skipping a mandatory phase requires an explicit reason in the plan and user approval.
- Phase 06 (report) must not be written until the approve phase (05) records
  `APPROVED` — enforced by the gate (`profile.pdca.report_phase`/`approve_phase`).

### 3.0 Independent PDCA Cycle Rule (MANDATORY)

When the user explicitly requests a new PDCA flow (or an L3-equivalent flow), the
agent MUST start a new, independent `00-base_plan` — even if the change is
technically adjacent to a recently completed cycle. "Technically adjacent" (same
file / service / module) is never a reason to reuse or extend a prior cycle. A new
cycle requires a new 00 base plan, new phase documents, and independent analysis.

### Pre-implementation declaration

Before writing implementation code, declare: risk level, compound rule applied,
applicable phase range, plan/phase doc paths, independent-review status (L3),
component impact, and reference docs read.

If `profile.pdca.enabled` is false (non-PDCA project), the gate falls back to
plan-doc + risk checks only; the phase machinery is inert.

## Non-negotiable safety boundaries

- Do not run `git commit` or `git push` unless the user explicitly asks.
- Do not perform destructive or outward-facing actions without confirmation.
- Do not directly edit generated artifacts (`{host}/agents`, `{host}/skills`,
  `{host}/hooks`) — edit the spec under `docs/sage_harness/` and regenerate.
  (Exception: the hand-shipped CORE bootstrap renders — `sage-init`/`pdca-start`/
  `sage-review` skills and the six CORE roster agent renders — are not generated
  and are write-guard exempt; edit them directly. See the bootstrap section above.)
- Report outcomes faithfully: if tests fail, say so with the output.

These are inherited by every agent/skill claim set as
`AGENT_GUIDE.non_negotiable_boundaries` (referenced, never copied).

## Definition of Done

- Plan doc updated; implementation matches the plan.
- `scripts/verify-changes.sh` passes at the required gate level.
- Conventions in `profile.conventions` satisfied.
- No direct edits to generated artifacts.
