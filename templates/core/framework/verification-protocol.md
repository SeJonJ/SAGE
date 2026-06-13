# verification-protocol.md

Gate policy for L1/L2/L3 changes. Concrete commands come from
`profile.verification` and `scripts/verify-changes.sh`; this document defines
the policy that hooks enforce.

| Level | Checks | Mode |
|-------|--------|------|
| L1 | syntax | advisory |
| L2 | build, test, lint | block |
| L3 | build, test, lint, review | block |

## L3 review

L3 changes require an independent review before merge. The reviewer runtime is
resolved by `sage doctor` from `profile.options.cross_model`:

- cross_model off → clean-context review in the same runtime.
- cross_model on + opposite runtime reachable → opposite-runtime review.
- cross_model on + opposite runtime unreachable → clean-context fallback
  (degraded; surfaced by `sage doctor`).

How an L3 change is matched to its review document is a project decision
(`profile.risk.l3_review_strategy`). Until selected, `pre-implementation-gate`
blocks L3 changes (safe default).
