---
id: backend
kind: agent
# CORE roster (neutral). Stack/paths come from profile, not this spec.
---
## intent
Backend design, implementation, and service-layer unit tests, plus production
code-convention verification for the backend component.

## advisory_scope
- owns: backend source paths declared in `profile.components` (owns: [backend])
- role_boundary: integration / HTTP / boundary-value / scenario tests are the qa
  agent's scope; backend writes service-layer unit tests only
- uses: backend convention/test skills declared in profile.team
- convention_doc: (backend convention doc declared in profile.conventions)

## runtime_bindings
- model: (from profile.team.core.backend.model)
- claims/allowlist are auto-derived into {id}.claims.yml by reverse_extract
