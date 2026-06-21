# CODEX.md

Thin Codex-specific execution override. All common rules, workflow, and the
output contract are governed solely by `AGENT_GUIDE.md`.

## Mandatory read (session start)

1. `AGENT_GUIDE.md` — single source of truth
2. `sage/project-profile.yaml` — project values
3. Relevant plan doc + convention docs (per profile)

## Codex-specific

- Use the Codex runtime asset ecosystem (`.codex/agents`, `.codex/skills`,
  `.codex/hooks`) which are generated from `docs/sage_harness/` specs.
- Do not modify generated artifacts directly — edit the spec and run
  `sage generate`. (The hand-shipped CORE bootstrap skills — `sage-init`,
  `pdca-start`, `sage-review` — install to the user-global `$CODEX_HOME/skills/`,
  not the repo, so they are not generated artifacts; update them via reinstall.)
