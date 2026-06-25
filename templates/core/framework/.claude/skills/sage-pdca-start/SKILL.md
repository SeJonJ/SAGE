---
name: sage-pdca-start
description: "Start a SAGE PDCA cycle for a new feature or change — verifies gate conditions, invokes the leader to author plan docs, and distributes file ownership before any implementation begins. Invoke when the user says /sage-pdca-start (Claude) or $sage-pdca-start (Codex), PDCA 시작, 새 기능 시작, or wants to begin a development cycle."
---

# sage-pdca-start — SAGE PDCA Cycle Start

Invoke as `/sage-pdca-start` (Claude) or `$sage-pdca-start` (Codex).

## Read these first (mandatory, in order)

1. `docs/sage_harness/skills/sage-pdca-start.md` — authoritative spec: intent, procedure, drift_checks
2. `AGENT_GUIDE.md` — PDCA phases, risk gate, phase-first rule
3. `sage/project-profile.yaml` — project.name, components, paths.plan_docs

## Gate check (do this before anything else)

Confirm `sage/project-profile.yaml` is bootstrapped:
- `project.name` is non-empty
- `risk` section has L0/L1/L2 globs set
- `components` list is non-empty

If any check fails: stop and say "Profile is not bootstrapped. Run `/sage-init` to
set up the project profile before starting a PDCA cycle."

## Step 1 — Scope the task

If the user has not described the task, ask for a one-sentence description:
"What is the feature or change we are implementing in this PDCA cycle?"

Record the task scope. Do not proceed to leader handoff until scope is confirmed.

## Step 2 — Invoke the leader

Hand off to the `leader` agent with this briefing:
- Task scope: (the one-sentence description from Step 1)
- Profile location: `sage/project-profile.yaml`
- Plan docs directory: the `paths.plan_docs` value from the profile
- Required: author a plan doc covering the task scope, distribute file ownership
  to `implementer-a` and `implementer-b` by component, and state the integration
  point

## Step 3 — Verify plan doc exists

After the leader completes, confirm the plan doc file exists and is non-empty.
If the leader did not create it, block and ask the leader to retry.

## Step 4 — Report ownership map

Present the ownership map to the user:
```
PDCA cycle started for: [task scope]
Plan doc: [path]
implementer-a owns: [component id / paths]
implementer-b owns: [component id / paths]
Integration point: [where the two connect]
```

Confirm the user is ready to proceed to implementation.

## Step 5 — State the phase flow (so the user knows what comes next)

Before handing back, tell the user the phase order and what each phase is *for*,
because 03/04 are easy to misorder. This skill produces 00–02; the rest follow:

- **00–02** (now, by leader) — base plan / requirements / design. Must exist
  before any L2/L3 code edit (`pre-implementation-gate` blocks otherwise).
- **03 Implementation** — write the code **and the unit tests**, then record file
  ownership, the checklist, and build/test results. 03 is filled *during/after*
  implementation, not before — it is evidence, not a pre-plan. Do not author 03
  ahead of the code.
- **04 Analyze** — leader + qa review the result: design↔implementation gap +
  **test coverage** (qa). No verdict here. (Writing tests is 03's job; 04 judges
  their sufficiency.)
- **05 Expert Review** — independent reviewer (cross-model when enabled) issues
  the verdict (APPROVED/FAIL/BLOCKED). Run `/sage-review` here.
- **06 Report** — only after 05 records APPROVED.

---

> This skill is a **CORE framework bootstrap asset**: hand-shipped by `sage install`,
> NOT a manifest-tracked skill (no claims file, no render hash, not gated by
> `sage validate`/`sage review`). Its reference spec lives at
> `docs/sage_harness/skills/sage-pdca-start.md`. To change it, edit the framework
> template, not via `sage generate`. Deploy location is runtime-specific: Claude
> reads it from the repo (`.claude/skills/sage-pdca-start/`); Codex reads it from the
> user-global skills dir (`$CODEX_HOME/skills/sage-pdca-start/`).
