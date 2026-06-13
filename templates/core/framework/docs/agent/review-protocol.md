# Review protocol

L3 changes require an independent review before they are considered done.

1. A plan doc must exist for the change (matched by ticket or recency).
2. An independent reviewer assesses the change. The reviewer runtime is
   resolved by `sage doctor`:
   - same-runtime clean-context (cross_model off, or fallback), or
   - opposite-runtime review (cross_model on + reachable).
3. The review outcome is recorded in a review/plan document.

How a change is matched to its review document is a project policy
(`profile.risk.l3_review_strategy`). Strategy candidates are preserved under
`scripts/sage_harness/hooks/strategies/`; until one is selected, L3 changes are
blocked (safe default — the gate cannot confirm a review it cannot locate).
