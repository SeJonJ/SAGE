# [Design] SAGE-FB-05 Codex CORE Skill Installation Scope

Cycle-Stem: `sage-fb-05-codex-skill-scope`

## 1. CLI and Receipt

```text
sage install --host codex --skill-scope global
sage install --host codex --skill-scope project-local
```

The manifest records:

```json
"core_skill_receipts": {
  "codex": {
    "scope": "project-local",
    "sage_version": "<installed version>"
  }
}
```

Claude records `project-local` because its CORE skills are repository-owned under `.claude/skills`. The Codex
deprecated no-skill path records `disabled`, making omission explicit rather than indistinguishable from legacy data.

## 2. Discovery Surfaces

- Global Codex scope: effective `$CODEX_HOME/skills/<skill-id>/SKILL.md`.
- Project-local Codex scope: `<dest>/.codex/skills/<skill-id>/SKILL.md`.
- Additional visible legacy/local copy: `<dest>/.agents/skills/<skill-id>/SKILL.md`; SAGE diagnoses but never deletes it.
- A selected-scope install does not delete an opposite-scope copy. Deletion in a shared home or repository is a
  separate user-owned cleanup decision.

## 3. Validation and Doctor Split

- `validate` checks receipt structure and selected repository-owned copies. Environment-dependent global checks and
  duplicate copies are warnings, so a clone remains deterministically valid when its receipt points global.
- `doctor` inspects the current global/project-local/legacy-local surfaces, compares each copy with the bundled CORE
  source, and reports missing/stale/duplicate/version-conflict states.
- When more than one Codex-visible copy exists, SAGE reports precedence as ambiguous and names the selected receipt as
  intent only. It never claims which copy Codex loaded without host evidence.

## 4. Team Onboarding

- Project-local: committed `.codex/skills` lets a teammate discover CORE prompts after cloning, but does not install the
  `sage`/`sage-hook` executable or Python runtime. The teammate installs the SAGE CLI separately and runs doctor.
- Global: every teammate installs the CLI and runs a global-scope install in their own Codex home.

## 5. Safety

- Existing transaction preconditions and rollback cover the selected write root.
- Skill sources remain fixed bundled files; destination paths are fixed CORE IDs.
- Duplicate cleanup is diagnostic only; install performs no destructive cross-scope deletion.

