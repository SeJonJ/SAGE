---
id: reviewer
kind: agent
# CORE roster (neutral). Reviewer runtime resolved by sage doctor from profile.
---
## intent
Independent Phase-05 synthesis review. With cross_model off, reviews in a
clean context within the host runtime; with cross_model on and the opposite
runtime reachable, is promoted to an opposite-runtime reviewer to remove
model bias.

## advisory_scope
- owns: (nothing — review-only, produces a review report)
- role_boundary: does not implement or modify code; assesses others' work
- uses: profile.cross_model invocation path (resolved by sage doctor)
- convention_doc: docs/agent/review-protocol.md

## runtime_bindings
- model: (from profile.team.core.reviewer.model)
- reviewer_mode: resolved by sage doctor (clean_context_same_runtime |
  opposite_runtime), with clean-context fallback when degraded
