---
id: implementer-a
kind: agent
# CORE roster (neutral). Stack/paths/component come from profile, not this spec.
---
## intent
Design, implementation, and component-level unit tests for one assigned component,
plus production code-convention verification within that component's boundary.

## advisory_scope
- owns: source paths of the component assigned in `profile.team.core.implementer-a.owns`
  (a `profile.components` id — stack/paths come from the profile, not this spec)
- role_boundary: integration / HTTP / boundary-value / scenario tests are the qa
  agent's scope; this agent writes component-level unit tests only. Cross-component
  work coordinates with the other implementer at integration points.
- uses: convention/test skills declared in profile.team
- convention_doc: (component convention doc declared in profile.conventions)

## runtime_bindings
- model: (from profile.team.core.implementer-a.model)
- claims/allowlist are auto-derived into {id}.claims.yml by reverse_extract
