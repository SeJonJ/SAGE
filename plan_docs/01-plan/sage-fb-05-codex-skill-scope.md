# [Plan] SAGE-FB-05 Codex CORE Skill Installation Scope

Cycle-Stem: `sage-fb-05-codex-skill-scope`
Risk Level: L3

## 1. Acceptance Matrix

| ID | Requirement | Required? |
|---|---|:---:|
| FB05-AC1 | Normal Codex install requires explicit `--skill-scope global|project-local`. | yes |
| FB05-AC2 | Global scope owns the effective `$CODEX_HOME/skills`; project-local owns `<dest>/.codex/skills`. | yes |
| FB05-AC3 | The manifest receipt records the selected Codex scope and SAGE version. | yes |
| FB05-AC4 | Scope changes update the receipt without silently deleting the opposite copy. | yes |
| FB05-AC5 | validate diagnoses receipt damage, selected-copy drift, and visible duplicate/version conflicts. | yes |
| FB05-AC6 | doctor reports the intended scope, live copies, ambiguous host precedence, and exact cleanup command. | yes |
| FB05-AC7 | onboarding distinguishes committed project-local skill assets from the separately required SAGE CLI. | yes |
| FB05-AC8 | Claude install and deprecated Codex CI opt-out remain compatible. | yes |
| FB05-AC9 | install transaction rollback covers the selected global or project-local write root. | yes |
| FB05-AC10 | three independent Claude review rounds and finding triage are complete. | yes |

## 2. Compatibility

- `sage install --host claude` needs no Codex scope.
- `--no-global-skill` remains a deprecated no-skill mode for existing CI/sandbox callers and conflicts with
  `--skill-scope`.
- Existing manifests without a scope receipt are treated as legacy and receive a migration warning, not a guessed
  scope.

