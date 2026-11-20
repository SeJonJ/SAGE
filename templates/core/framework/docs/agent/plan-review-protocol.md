# Optional plan-context review

This is an implementation-planning aid inspired by EGM, not EGM's full pipeline,
Phase 05 review, a new gate, or implementation approval.

## When and how

After normal identity, language, risk and Done Criteria checks, before the human
implementation handoff, inspect shared `pdca.plan_review`. Missing/disabled means
no call. Use only the declared actual L2/L3 risk included in `levels`; a lower Fast
review level never lowers actual risk for this decision.

When enabled for this level, prepare the complete standard 00/01/02 documents or
one populated Fast composite00 (Phase04 remains pending; Fast need not be open).
Select explicit source files that the user has authorized for model transmission.
Do not automatically include conversation logs, interview transcripts, linked files,
glob expansions or unrelated repository context. External sources require explicit
selection; use an authorized local excerpt for a URL and record its missing scope.

Run once, using the actual current host:

```text
sage plan-review --root <project-root> --host <claude|codex> --stem <stem> \
  --plan <phase00> --plan <phase01> --plan <phase02> --source <authorized-source> --json
```

For Fast, pass only `--plan <composite00>`. Omit `--source` when unavailable;
agreement with sources is then unverified. Repeated inputs are deduplicated by real
path. The CLI uses a fresh process of that same host, the CLI's configured default
model, and only the immutable packet. It does not use Phase05 reviewer overlays,
cross-model policy or approval markers. Existing environment/user CLI settings may
still affect the process; this is not a complete host isolation guarantee.

Default limits are one invocation, 300 seconds, and 1MiB of UTF-8 input including
the final prompt/contract. Optional `--timeout` (30..1800) and `--max-input-bytes`
(4096..4194304) change those limits. These are not hard token or billing caps.
No automatic retry, opposite-model fallback, or automatic plan edits are allowed.
`model_observed` records the native CLI-reported name: an assistant-message name
takes precedence over the init header, and an init-only name can still be an alias.
This is an observation, not certification of the provider's inference model.
Without tool IDs, audit counts conservatively describe observed events; the
`tool_identity_unavailable` warning makes that uncertainty explicit.
If usage is absent, record UNKNOWN, never zero. Observe the user's model budget.

## Result and human disposition

The CLI creates the raw result directly in a new `.sage/plan-reviews/` JSON file;
`--output` selects a new file within that directory. It never overwrites a result.
Use the returned `output_path`; do not ask an agent to transcribe JSON from stdout.
If storage fails, preserve stdout before deciding whether to save it or retry.
Inputs, paths and review text can contain private information. These raw results
are local state and are ignored by the installer-managed Git rules; do not paste
them into public logs/issues/docs without reviewing their contents.

| Status | Interpretation |
| --- | --- |
| COMPLETE (exit 0) | Execution finished; not approval, a clean design, or Phase05 completion |
| SKIPPED (0) | Disabled or actual risk excluded; no model call |
| INVALID_INPUT (2) | Fix the profile, identity, source/limit, host or output path before retrying |
| UNSUPPORTED (3) | Required controls unavailable; no uncontrolled fallback |
| PARTIAL / FAILED (3) | Preserve findings/failure and missing scope; do not report review complete |
| STALE (3) | A supplied file changed/disappeared during the run; result covers the old snapshot |

Even with no findings, read FINDINGS, REVIEWED and UNVERIFIED. If the reviewer did
not supply those sections, record the incomplete report structure rather than
treating execution completion as review quality. Check each finding against the
frozen inputs; decide with the user whether to apply, defer or rebut it. Record
ID, evidence, disposition, reason, unresolved assumptions and the raw-result path
in existing standard02 or Fast Phase02. The human decides whether a new assumption
becomes a requirement.

After editing the plan, the old JSON remains evidence for its original hashes.
Compare hashes when referring to it later; do not relabel it a review of changed
plans. On failure, insufficient sources or budget, let the human choose manual
review, an explicit new run, or a documented skip. A skip is not COMPLETE. This
feature adds no implementation block and waives none of the existing checks or
human approval. Continue the ordinary 03 → 04 → independent05 → 06 process.
