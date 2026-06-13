---
id: frontend
kind: agent
# CORE roster (neutral). Stack/paths come from profile, not this spec.
---
## intent
Frontend implementation and code-convention verification for the frontend
component.

## advisory_scope
- owns: frontend source paths declared in `profile.components` (owns: [frontend])
- role_boundary: backend logic and cross-component integration tests are out of
  scope; coordinates with backend at integration points
- uses: frontend convention skills declared in profile.team
- convention_doc: (frontend convention doc declared in profile.conventions)

## runtime_bindings
- model: (from profile.team.core.frontend.model)
- claims/allowlist are auto-derived into {id}.claims.yml by reverse_extract
