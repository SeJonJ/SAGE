---
name: pdca-start
description: "Start a SAGE PDCA cycle for a new feature or change — verifies gate conditions, invokes the leader to author plan docs, and distributes file ownership before any implementation begins. Invoke when the user says /pdca-start, PDCA 시작, 새 기능 시작, or wants to begin a development cycle."
---

# pdca-start — SAGE PDCA Cycle Start

## Read these first (mandatory, in order)

1. `docs/sage_harness/skills/pdca-start.md` — authoritative spec: intent, procedure, drift_checks
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

---

> This skill is a **CORE framework bootstrap asset**: hand-shipped by `sage install`,
> NOT a manifest-tracked skill (no claims file, no render hash, not gated by
> `sage validate`/`sage review`). Its reference spec lives at
> `docs/sage_harness/skills/pdca-start.md`. To change it, edit the framework
> template, not via `sage generate`. Deploy location is runtime-specific: Claude
> reads it from the repo (`.claude/skills/pdca-start/`); Codex reads it from the
> user-global skills dir (`$CODEX_HOME/skills/pdca-start/`).
