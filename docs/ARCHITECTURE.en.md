<!-- sage-doc-source: ARCHITECTURE.md sha256:7333189fae8c632ce7f4023ba197da2fb7d7aa7ae70ccb9ad1401c0977382b20 -->
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
- Lazy review-loop bypasses: the audit validates contiguous round sequence numbers.

**SAGE does not block by design**

- **A fully compromised host runtime**: SAGE assumes the host invokes CLI commands and skills
  according to their contracts. A maliciously modified runtime is outside the threat model.
- **Tampering with `loop_audit`**: sequence continuity in
  `scripts/sage_harness/hooks/runtime/loop_audit.py` detects **lazy bypasses** such as manual appends,
  reordered records, and omissions. It is a sanity check, not tamper resistance. Because `seq`
  equals the number of existing records, an editor can inspect the file and append the next integer.
  True tamper resistance requires a hash chain and remains a future hardening task
  (`plan_docs/enhancement-backlog.md`, EH-3).

Threats beyond this boundary, such as a compromised runtime or audit-log tampering, are mitigated by
higher-level procedures such as cross-model review and human approval. Deterministic gates prevent
mistakes, laziness, and drift by an honest host; they are not intended to stop an adversarial host.
