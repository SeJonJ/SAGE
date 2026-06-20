# AGENTS.md

Codex-native session entrypoint for this SAGE project. Codex auto-reads this file
at session start; it is a thin router, not a rules duplicate.

## Read in order

1. `AGENT_GUIDE.md` — the single source of truth (rules, risk gate, PDCA, safety).
2. `CODEX.md` — Codex-specific execution wrapper notes.
3. `sage/project-profile.yaml` — project values.

## Bootstrap first (if not done)

If `sage/project-profile.yaml` is unbootstrapped — `project.name` empty, or
`risk`/`components` unset — run the **conversational bootstrap FIRST, before any
other work**: interview the user → fill the profile values → hand off to
`sage generate` / `sage validate`. Follow the protocol in
`docs/agent/bootstrap-authoring.md`.

`sage generate` is BLOCKED until the profile is bootstrapped (by design — an empty
profile would silently disable the governance gate). So bootstrap is the required
first step, not optional.

(Claude runtime users invoke this same flow via the `/sage-init` skill; Codex has
no portable repo-scoped skill mechanism, so this routing lives here in AGENTS.md.)
