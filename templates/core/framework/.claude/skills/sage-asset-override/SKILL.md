---
name: sage-asset-override
description: "Author a project-local overlay for an existing CORE agent/skill through conversation — customize leader/implementer/qa/reviewer/convention-checker or a CORE skill without editing the CORE render (which sage install --force would overwrite). Shows the current CORE base, interviews the local deviation, WARNS (with mandatory confirmation) if it looks like it relaxes a governance gate, then writes sage/asset_overrides/{agents,skills}/<id>.md directly. Invoke when the user says /sage-asset-override, 오버레이 작성, CORE 커스터마이즈, override an agent/skill, or a retro/absorb proposal suggests an agent/skill-target learning."
---

# sage-asset-override — Conversational CORE Overlay Authoring

This skill authors a **project-local overlay** for an **existing CORE agent/skill**. It is
the fourth conversational entry point:
- `/sage-init` — first authoring (0→1).
- `/sage-profile-modify` — edit existing profile / governance values.
- `/sage-asset` — add/modify governance assets (hook/agent/skill) via spec→generate.
- **`/sage-asset-override` — overlay an existing CORE agent/skill (this skill).**

Authoritative protocol: `docs/agent/bootstrap-authoring.md`. Rules: `AGENT_GUIDE.md`.

Before acting, read optional project overlay `sage/asset_overrides/skills/sage-asset-override.md`
if it exists. Apply it before these CORE instructions. The overlay is project-local and
survives `sage install --force`. It may add project-specific guidance but must not relax
AGENT_GUIDE, phase, review, or verification gates. Never edit this CORE render for
project-specific loop learning.

> This skill is a **CORE framework bootstrap asset** — hand-shipped by `sage install`,
> NOT manifest-tracked. Its reference spec lives at
> `docs/sage_harness/skills/sage-asset-override.md`. Claude reads this render from the
> repo (`.claude/skills/sage-asset-override/`); Codex reads it from the user-global
> skills dir (`$CODEX_HOME/skills/sage-asset-override/`).

## Why overlays exist

CORE agent/skill renders (leader, reviewer, sage-review, …) are **hand-shipped** and
`sage install --force` overwrites them wholesale. Editing them directly means the next
SAGE upgrade silently discards your change — and the write-guard now blocks that edit.
An **overlay** at `sage/asset_overrides/{agents,skills}/<id>.md` is the supported place
for project-local customization: `sage install` never ships it, so `--force` preserves it,
and each CORE render reads its overlay first (when present).

## What this skill is NOT

- **Not for new assets.** Creating a *new* hook/agent/skill is `/sage-asset` (spec→generate,
  the write-guard forces that path). This skill only overlays an **existing CORE roster id**.
- **Not `sage generate`.** An overlay is hand-authored (like the profile), written directly
  and not generated. There is no manifest/claims stamp for it.
- **Not a gate loophole.** An overlay *adds* project guidance on top of CORE; it must never
  relax AGENT_GUIDE, phase, review, or verification gates.

## Hard rules

- **Existing CORE roster id only.** kind(agent|skill) + id must be one of:
  - agents: `leader`, `implementer-a`, `implementer-b`, `qa`, `reviewer`, `convention-checker`
  - skills: `sage-init`, `sage-cycle`, `sage-plan`, `sage-team`, `sage-review`, `sage-asset`,
    `sage-profile-modify`, `sage-asset-override`
  Anything else → route to `/sage-asset` and stop.
- **Gate-relaxation is a stop condition.** If the drafted overlay reads like it skips/bypasses
  a phase, review, verification, or the gate — or tells the agent to ignore AGENT_GUIDE —
  surface it and get an **explicit "yes"** before writing. Never proceed silently.
- **The user owns intent.** Show the CORE base, propose the overlay, get approval before writing.

## Step 0 — Read context first

Read, in order, before asking anything:
1. `sage/project-profile.yaml` — if **not bootstrapped** (`project.name` empty OR risk globs
   and components both unset), stop and route to `/sage-init`. Overlays presuppose a set-up project.
2. `AGENT_GUIDE.md` — the gates an overlay must not relax.
3. The **target CORE base**: `docs/sage_harness/{agents,skills}/<id>.md` (reference spec) and,
   if helpful, the current render.

## Step 1 — Identify the target (one focused turn)

Pin **kind** (agent|skill) and **id** from the user's intent (or a retro/absorb proposal's
`asset_id` hint). Confirm it is an existing CORE roster id (see Hard rules). If the user
actually wants a *new* asset, route to `/sage-asset` and stop.

## Step 2 — Show the CORE base

Show the current CORE base content relevant to the requested change, so the user sees what
the overlay layers on top of (overlays add; they do not replace the whole render).

## Step 3 — Interview the deviation

Ask what should change for **this project only**, and **why** (e.g. a recurring retro
pattern the CORE render can't encode because it must stay project-neutral).

## Step 4 — Draft + gate-relaxation check (mandatory)

1. Draft the overlay text.
2. Check it for gate-relaxation language. `sage validate` runs the deterministic overlay
   lint (`sage.overlay_lint`) and prints `⚠️ WARN overlay 게이트-완화 의심` for suspect text;
   you can also eyeball it against the Hard rules.
3. **If it looks like it relaxes a gate, require an explicit "yes"** before writing — state
   the concern in plain terms first. This mirrors `/sage-profile-modify`'s mandatory
   consequence warning; do not proceed silently.

## Step 5 — Write the overlay

Write `sage/asset_overrides/{agents,skills}/<id>.md` **directly** (create the dir if needed).
No `sage generate`. Keep it additive — project guidance on top of CORE, not a rewrite.

## Step 6 — Re-validate

```
sage validate --schema --kind all
```
Confirm the file exists and that any overlay gate-relaxation WARN is one the user explicitly
accepted (fix or remove otherwise). Note the overlay survives `sage install --force`, and the
next agent/skill run reads CORE + overlay.

## Done

The overlay is complete when it captures the project-local intent, the gate-relaxation check
ran (and any hit was explicitly accepted), the file is at
`sage/asset_overrides/{agents,skills}/<id>.md`, and `sage validate` shows no unaccepted overlay
WARN. The next run of that agent/skill applies CORE first, then the overlay.
