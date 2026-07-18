# [Plan] SAGE-FB-07 L0 Domain Risk Exception

Cycle-Stem: `sage-fb-07-l0-domain-risk-exception`

## Acceptance Criteria

| ID | Requirement | Required |
|---|---|:---:|
| FB07-AC1 | A generic image matching only `l0_pass_globs` remains L0. | Yes |
| FB07-AC2 | An image matching L0 plus a domain L3 path is classified L3. | Yes |
| FB07-AC3 | Domain path globs are automatically materialized into the L0 exclusion set. | Yes |
| FB07-AC4 | Explicit exclusions must exactly bind to an L1/L2/L3 path glob or validation fails. | Yes |
| FB07-AC5 | Existing profiles without exclusions preserve L0-first behavior. | Yes |
| FB07-AC6 | Scalar/blank exclusion values fail before compiler coercion. | Yes |
| FB07-AC7 | Classification provenance records that the L0 carve-out was bypassed. | Yes |
| FB07-AC8 | Three independent Claude review rounds complete before approval. | Yes |

