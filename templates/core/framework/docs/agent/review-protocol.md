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

## Adversarial review-rework loop (Loop A)

When `profile.pdca.review_loop.enabled` is true and the change is L2/L3, Phase 05 runs
as an adversarial loop instead of a single pass. The `sage-review` skill drives it; this
section is the contract it follows.

Per round (up to `review_loop.max_iterations[risk]`):

1. **FIND** — one reviewer per `review_loop.lenses` (parallel, divergent) plus an
   opposite-runtime peer when cross-model is resolved. Findings are deduped by
   `(file, line-bucket, lens, claim-hash)` so resurfaced items don't churn.
2. **REFUTE** — `review_loop.refuters` refuters try to disprove each fresh finding.
   A finding survives only if refuting votes `< ⌈refuters/2⌉` (majority). Refuters bias
   to "refuted when uncertain", so weak findings drop; a wrongly-dropped real issue is
   caught by the human BLOCKED path.
3. **TRIAGE** — surviving findings are classified `within_design` vs `architecture_change`.
   An `architecture_change` at L3 stops the loop and escalates to a human (never auto-reworked).
4. **TERMINATION** (fixed priority): no survivors → APPROVED(CONVERGED); `dry_rounds`
   consecutive empty rounds → APPROVED(DRY); iteration cap hit → BLOCKED(BUDGET_ITER);
   token budget hit → BLOCKED(BUDGET_TOK); architecture escalation → BLOCKED(BLOCKED_ARCH).
5. **REWORK + re-validate** — `within_design` survivors are reworked within the approved
   design; `verify-changes.sh` and `sage validate` must PASS before the next round.

Determinism boundary: the loop *body* (find/refute/rework) is judgement and runs in the
host runtime. SAGE owns the deterministic gates only — round counters, budget, termination,
and the append-only audit trail (`.sage/loop_audit.jsonl`, recorded via `sage review-loop`).
The hard backstop is unchanged: the report←approve hook blocks Phase 06 until Phase 05
records `APPROVED`. The loop never relaxes that gate; it adds audited find→refute→rework
rounds in front of it. Configuration values live only in `profile.pdca.review_loop`
(validated fail-closed by `sage doctor`/`sage validate`).
