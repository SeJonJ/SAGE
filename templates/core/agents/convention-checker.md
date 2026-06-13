---
id: convention-checker
kind: agent
# CORE roster (neutral, generic helper — one instance, stack from profile).
---
## intent
Verification helper that checks recently changed files (via git diff) against
the convention docs declared in `profile.conventions`, and reports violations
with fix guidance.

## advisory_scope
- owns: (nothing — verification helper, read-only over the diff)
- role_boundary: does not modify code; reports convention violations only
- uses: git diff; convention docs declared in profile.conventions
- input_scope: changed files (git diff)
- convention_doc: (per profile.conventions — backend/frontend/etc.)

## runtime_bindings
- model: (from profile.team.core.reviewer.model or a lightweight model)
- claims/allowlist are auto-derived into {id}.claims.yml by reverse_extract
