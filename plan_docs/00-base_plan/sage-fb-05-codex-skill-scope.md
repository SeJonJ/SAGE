# [Base Plan] SAGE-FB-05 Codex CORE Skill Installation Scope

Cycle-Stem: `sage-fb-05-codex-skill-scope`
Risk Level: L3

## 1. Problem

Codex CORE skills are currently installed only under the effective `$CODEX_HOME/skills`, or omitted entirely with
`--no-global-skill`. In a dogfooding repository that also carries project-local skills, this can expose duplicate
`$sage-*` names without recording which copy is intended, which version is current, or what a teammate must install.

## 2. Boundary

- Require an explicit `global` or `project-local` scope for normal Codex installs.
- Record the selected scope in the repository installation receipt.
- Diagnose missing, stale, duplicate, and version-conflicting CORE skill copies without inventing a Codex discovery
  precedence that the host does not guarantee.
- Separate repository-contained skill discovery from the separately installed SAGE CLI/runtime in onboarding guidance.
- Preserve `--no-global-skill` only as a deprecated CI/sandbox compatibility path; it is not a normal install scope.

## 3. Impact

- SAGE install/manifest/validate/doctor/framework documentation/tests: affected.
- ChatForYou Backend/Frontend/Desktop source: N/A.

