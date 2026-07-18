# [Plan] SAGE-FB-09 Delivery and Required Check Proof

Cycle-Stem: `sage-fb-09-delivery-required-check`

## Acceptance Criteria

| ID | Requirement | Required |
|---|---|:---:|
| FB09-AC1 | SAGE engine changes are committed and published at an immutable 40-hex SHA. | Yes |
| FB09-AC2 | ChatForYou authority workflow pins SAGE and third-party actions by reviewed full SHAs. | Yes |
| FB09-AC3 | Protected environment and `SAGE_ATTESTATION_KEY` exist without exposing secret value. | Yes |
| FB09-AC4 | A real PR run produces the exact `sage-authoritative-gate` check and passes valid evidence. | Yes |
| FB09-AC5 | A negative PR/evidence case is blocked by the same check. | Yes |
| FB09-AC6 | `chatforyou_v2` requires the exact check from the expected GitHub App source. | Yes |
| FB09-AC7 | Force-push/admin-bypass posture is explicitly decided rather than silently retained. | Yes |
| FB09-AC8 | Three independent Claude reviews validate workflow/security before activation. | Yes |

## Required Evidence

- Published SAGE commit URL/SHA.
- ChatForYou workflow commit SHA.
- Positive and negative GitHub Actions run URLs and conclusions.
- Read-back JSON for branch protection required status check context/app binding.
- No secret values in logs or documents.

