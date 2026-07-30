<!-- sage-doc-source: ARCHITECTURE.md sha256:a436183cfcaef6efa83a3bc0c81f2907c616164b99fcf7713d250c9139f7b264 -->
# SAGE Architecture

[한국어](ARCHITECTURE.md) | [Documentation index](README.en.md)

SAGE is a governance harness built on the principle that **AI owns judgment while deterministic
code owns boundaries**. This document consolidates the **two-layer invariant**, **failure policy**,
and **trust boundary** that define that separation. It promotes contracts previously scattered
across code comments into a single reference.

## Two-layer invariant

| Layer | Role | Property | Location |
|---|---|---|---|
| **core** | Gate decisions, including risk classification, `decide`, and sequence validation | **Purely deterministic**: identical input produces identical output, without side effects or judgment | `scripts/sage_harness/hooks/core/`, `scripts/sage_harness/hooks/runtime/loop_audit.py` |
| **runtime / adapter** | I/O orchestration, including input extraction, profile loading, snapshot construction, output rendering, and host-specific branches | Isolates judgment and environment dependencies | `scripts/sage_harness/hooks/runtime/hook_runtime.py`, `.../runtime/io_claude`, `io_codex` |

The central rule is that **AI owns judgment** such as reviews, analysis, and fixes, while the core
deterministically owns boundaries such as gates, integrity, and validation. Even if an AI judgment
is wrong, the core gate remains intact. The runtime assembles inputs for the core; it does not
replace the core's decision.

## Failure policy: fail-open vs. fail-closed

The direction depends on what failed. The governing principle is **never disable a gate silently**
(preventing silent gate disablement, Pattern A).

| Failure point | Direction | Reason |
|---|---|---|
| Input JSON parsing | **fail-open** (exit 0) with stderr output | Treat it as a transient glitch without blocking development, but do not pass silently |
| Profile parsing | **fail-open** with a **LOUD** warning | The gate is disabled, so the condition must be surfaced prominently |
| L3 strategy crash | **fail-closed** and keep BLOCK | If a high-risk path cannot be evaluated, block it safely |
| Glob outside the root or using an absolute path | Reject | Preserve project independence |

The source contract is the "preservation principles" comment at the top of
`scripts/sage_harness/hooks/runtime/hook_runtime.py` and the profile-loading and L3-strategy-loading
paths.

## Trust boundary: what SAGE blocks and does not block

**SAGE blocks**

- Drift: `sage validate` detects mismatches between specs and generated assets.
- Direct edits: the write guard blocks edits to generated assets and redirects changes to specs.
- Single-model bias: cross-model review uses the opposite runtime for independent review.
- Silent gate disablement: `sage validate` fails closed on profile typos and unknown keys that could
  silently disable gates. This is validation-time fail-closed behavior. Runtime profile *parsing*
  failures are a separate layer and remain fail-open with a LOUD warning, as described above.
- Phase 06 bypassing Phase 05: completion reports are deterministically bound to an APPROVED review.
- Unrehashed mutation, insertion, non-tail deletion, or reordering of Loop A evidence: the real
  report gate validates per-run strict hash chains, record self-hashes, and file parse integrity.

**SAGE does not block by design**

- **A fully compromised host runtime**: SAGE assumes the host invokes CLI commands and skills
  according to their contracts. A maliciously modified runtime is outside the threat model.
- **A fully recomputed or legacy-downgraded rewrite of `loop_audit`**: the strict per-run hash chain
  uses canonical SHA-256 with fixed key ordering and Unicode representation to self-verify each
  record and its immediate predecessor. While any v1 chain field remains in a run, it detects
  mutation, insertion, non-tail deletion, and reordering when hashes are not recomputed. It does not
  authenticate the file against an attacker who can recalculate the chain. Legacy compatibility
  also accepts a run with no chain fields as `chain_ok=None`, so removing all three chain fields
  from every record in a run is indistinguishable from legitimate legacy data. Without a secret
  key, signed head, a tip in another artifact, a Git baseline, or an external witness, this is
  **self-verification**, not standalone tamper resistance. A tip edit is detected by the record
  self-hash, deletion of the final close is rejected by the report gate's `closed` invariant, and
  Git history plus code review remain the external anchor for fully recomputed or downgraded
  rewrites.

Threats beyond this boundary, such as a compromised runtime or audit-log tampering, are mitigated by
higher-level procedures such as cross-model review and human approval. Deterministic gates prevent
mistakes, laziness, and drift by an honest host; they are not intended to stop an adversarial host.
