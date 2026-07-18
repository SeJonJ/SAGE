# [Plan] SAGE-FB-04 Host Model Discovery and Routing

Cycle-Stem: `sage-fb-04-host-model-routing`
Risk Level: L3

## 1. Acceptance Matrix

| ID | Requirement | Required? |
|---|---|:---:|
| FB04-AC1 | `sage models --host <host>` lists candidates with source and verification status. | yes |
| FB04-AC2 | Codex discovery reads a bounded, regular local cache and excludes hidden entries. | yes |
| FB04-AC3 | Claude candidates are clearly marked as CLI aliases with account availability unverified. | yes |
| FB04-AC4 | components may select actual models per host without changing the legacy `model` tier. | yes |
| FB04-AC5 | cross-review host/model are explicit profile interview values and host must oppose active_host. | yes |
| FB04-AC6 | cross-check passes the selected model to the peer CLI without shell interpolation. | yes |
| FB04-AC7 | validate catches malformed/unsupported static routing and doctor reports local catalog support. | yes |
| FB04-AC8 | generated component roster records active-host model selection and its provenance. | yes |
| FB04-AC9 | docs explain discovery confidence, manual selection, and double-host handoff behavior. | yes |
| FB04-AC10 | three independent Claude review rounds and finding triage are complete. | yes |

## 2. Compatibility

- Existing profiles with only `components[].model` remain valid and retain work-intensity semantics.
- Existing `cross_model` profiles without `reviewer` continue to use the opposite runtime and peer CLI default model.
- Model discovery is read-only and never invokes a billable model request.

