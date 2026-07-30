# [Base Plan] SAGE 10-g Loop Audit Strict Per-Run Hash Chain

Cycle-Stem: `sage-loop-audit-strict-hash-chain`
Risk Level: L3
Status: DESIGN_APPROVED

## 0. Prior Knowledge

| Type | Source | Key Takeaway |
|---|---|---|
| Repository | `plan_docs/enhancement-backlog.md` EH-3 | The original scope is `loop_audit`, hash chaining, legacy compatibility, and report-gate verification. |
| Repository | `loop_audit._seq_ok` | Sequence continuity catches missing or reordered records but is only an anti-lazy-bypass sanity check. |
| Repository | `pre_implementation_gate_core._audit_gate` | The report gate already consumes per-run `clean`, `seq_ok`, result, and reviewer evidence. |
| Independent review | Rolled-back first 10-g implementation | A file-wide graph that accepted any earlier predecessor allowed sibling modification, deletion, and reordering. Hash stamping without consumer wiring also left authority decisions unchanged. |
| Conversation | 2026-07-30 scope decision | Keep 10-g limited to `loop_audit`; register the other three committed audit logs as a separate enhancement. |

## 1. Goal

Strengthen `.sage/loop_audit.jsonl` from sequence-only sanity checking to a self-verifying,
strict per-run hash chain that the actual Phase 06 report gate consumes.

This is **not tamper resistance against an adversary who can rewrite the file and recompute every
hash**. No secret key, signed head, or external witness is introduced. The delivered guarantee is:

- an edit that does not re-hash the affected run is detected;
- insertion, non-tail deletion, or reordering inside a chained run breaks the
  immediate-predecessor contract;
- modification of the final record is detected by its own `record_hash`;
- deletion of the final close is rejected by the existing `closed` report-gate invariant;
- a report cannot use a run whose chain verification is false.

Git history remains the external review anchor for detecting a fully recomputed rewrite.

## 2. Locked Scope

10-g changes only the Loop A audit path:

- `scripts/sage_harness/hooks/runtime/loop_audit.py`;
- `sage/commands/review_loop.py` only where write failures need a clean exit-2 contract;
- `hook_runtime.build_snapshot` and `pre_implementation_gate_core._audit_gate`;
- Loop A tests, hook bundle registration, generated manifest hashes, and bilingual architecture or
  hook-contract documentation.

The following are explicitly out of scope:

- `.sage/acceptance-waivers.jsonl`;
- `.sage/retro_audit.jsonl`;
- `.sage/override.jsonl`;
- the machine-local override authority store;
- HMAC, signatures, remote witnesses, server authority, or Git-base comparison;
- changes to review-loop result/reason vocabulary, budgets, reviewer routing, or cycle binding.

The remaining committed audit logs have different authority, reader, locking, and failure contracts.
They are tracked as a separate enhancement instead of being forced through one generic writer.

## 3. Record Contract

Every newly written Loop A record carries:

```json
{
  "chain_version": 1,
  "prev_hash": "GENESIS or 64 lowercase hex characters",
  "record_hash": "64 lowercase hex characters"
}
```

`record_hash` is SHA-256 over canonical UTF-8 JSON containing every record field except
`record_hash` itself. Canonical JSON uses sorted keys, compact separators, and
`ensure_ascii=False`. `prev_hash` and `chain_version` are therefore covered by `record_hash`.

`prev_hash` is scoped to `run_id`, not to physical file adjacency:

- no earlier record for the same run: `GENESIS`;
- earlier legacy record for the same run: canonical hash of that immediate predecessor;
- earlier v1 record for the same run: its verified `record_hash`.

Records from different runs may interleave without becoming predecessors of one another.

## 4. Strict Verification

Verification walks the JSONL records in append order and keeps the immediate predecessor for each
`run_id`.

For each run:

1. Records without chain fields before the first v1 record are legacy.
2. The first v1 record must reference `GENESIS` or the immediate legacy predecessor as defined above.
3. Every later v1 record must reference the immediate preceding record for that run.
4. Every v1 record must have a valid `chain_version`, `prev_hash`, and self-consistent `record_hash`.
5. A record without complete v1 fields after chaining starts is invalid.
6. A malformed/non-object line remains a file-integrity issue under the existing raw-line scan.

The result is tri-state per run:

- `True`: at least one v1 record exists and the strict chain is valid;
- `False`: a v1 chain exists but violates the contract;
- `None`: the run is entirely legacy and keeps existing `seq_ok` compatibility.

The verifier must never accept a predecessor merely because its hash appeared somewhere earlier.
There is no sibling or branch state.

## 5. Write and Concurrency Contract

Stamping and appending are one critical section guarded by a process lock scoped to
`.sage/loop_audit.jsonl`.

- POSIX uses `fcntl.flock`.
- Windows uses `msvcrt.locking`.
- The lock is a local sidecar under `.sage/` and remains ignored by the repository tracking policy.
- Lock acquisition, current target-run verification, hash stamping, one-line append, flush, and
  `fsync` happen before release.
- A broken target-run chain is not extended.
- Lock or write failure raises a Loop Audit write error; `sage review-loop open|round|close` prints a
  deterministic diagnostic and exits 2 without a traceback.

The lock serializes physical writes, while the hash chain remains per-run. This prevents honest
same-run concurrent commands from creating sibling records and also prevents partial JSON lines.

## 6. Consumer Wiring

`loop_audit.audit_summary()` adds `chain_ok` to each run summary. It does not expose a file-global
boolean that could let an unrelated run block the selected cycle.

The Phase 06 report gate evaluates the selected run in this order:

1. run exists and is structurally clean;
2. `seq_ok is not False`;
3. `chain_ok is not False`;
4. run is closed and result is `APPROVED`;
5. reviewer execution is not degraded.

`chain_ok=None` preserves legacy behavior. `chain_ok=False` follows the existing gate mode:
advisory produces a warning and enforce blocks.

`loop_audit.integrity_issues()` also reports invalid per-run chains so `review-loop show`, retro
consumers, and existing integrity diagnostics do not silently display untrusted evidence.

## 7. Legacy Boundary

No existing line is rewritten and no genesis re-stamp is performed.

- Entirely legacy runs continue to rely on `clean` and `seq_ok`.
- The first new record appended to an existing legacy run links to the immediate legacy predecessor.
- From that point onward, missing or malformed chain fields fail that run.
- New runs are v1 from their `loop_open` record.

This protects the legacy-to-v1 boundary without making an unverifiable claim about older records.

## 8. Required Regression Teeth

Tests must prove behavior, not only field presence:

- canonical hash stability across key order, spacing, and Unicode;
- new open/round/close records form one strict run chain;
- modification of open, middle round, and final close is detected;
- insertion, non-tail deletion, and reordering within one run are detected;
- deleting the final close leaves the run open and cannot authorize a report;
- two stale same-predecessor siblings are rejected;
- records from different runs may interleave and both remain valid;
- legacy-only run returns `None`;
- legacy-to-v1 transition is valid and a later unstamped record is invalid;
- malformed hash fields fail without crashing;
- a broken chain is surfaced by `integrity_issues`;
- the real report gate warns in advisory mode and blocks in enforce mode;
- removing the gate's `chain_ok` branch makes the regression suite fail;
- lock contention and write failure return CLI exit 2 without traceback.

Full verification requires marker-free, Claude, and Codex host environments, source-tree
`python3 -m sage validate --kind hook --check --schema`, `git diff --check`, and wheel smoke.

## 9. Documentation and Packaging

- Update Korean and English architecture documentation with the exact self-verification boundary.
- Update the pre-implementation gate contract and test inventory.
- Bundle every new runtime file if the implementation introduces one.
- Regenerate hook assets and manifest hashes after runtime or hook-spec changes.
- Do not describe the result as cryptographic tamper resistance.

## 10. Acceptance

- A selected chained run with any unrecomputed record mutation cannot authorize a Phase 06 report.
- A selected legacy run remains backward compatible.
- Concurrent writes cannot produce accepted siblings.
- The final `loop_close` record is self-verified.
- No other audit log behavior changes.
- All required regression, source validation, and wheel gates pass.
