<!-- sage-doc-source: ARCHITECTURE.md sha256:d3fac3bd378d2ee81580475e62045a8acdbdb8e942b52cca3f2831f844a925f5 -->
# SAGE Architecture

[한국어](ARCHITECTURE.md) | [Documentation index](README.en.md)

SAGE is a governance harness built on the principle that **AI owns judgment while deterministic code
owns boundaries**. This document consolidates the **two-layer invariant**, **failure policy**, and
**trust boundary** that define that separation. It promotes contracts previously scattered across
code comments into a single reference.

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

## Decision delivery channels

**A decision that reaches nobody is the same as having no gate.** The principle above — never
disable a gate silently — applies to delivery as well as to judgment. Both directions of loss have
been observed in practice: block reasons disappearing so a block looks unexplained, and pass
messages disappearing so a stale state stays invisible.

Hosts read **different channels depending on the event and the exit code**, so the channel is chosen
by runtime and event together.

| Situation | Claude Code | Codex |
|---|---|---|
| Block (exit 2) | stderr — stdout is ignored | stderr |
| PreToolUse pass (exit 0) | `hookSpecificOutput.additionalContext` | same |
| UserPromptSubmit (exit 0) | plain stdout — becomes context directly | `hookSpecificOutput` |
| Stop block | exit 2 with stderr | exit 0 with `decision: block` |

In Claude Code the events whose exit-0 plain stdout is promoted to context are `UserPromptSubmit`,
`UserPromptExpansion`, and `SessionStart`; every other event writes to the debug log only. Message
text is owned solely by `runtime/messages.py`; `io_claude` and `io_codex` decide only the channel.

## OS boundary and the two judgement axes (`sage uninstall`)

This is the one command that errs in an irreversible direction, so it gets its own boundary. The
principle is unchanged — **one place decides, and each layer speaks only to what it knows.**

| Layer | Role | Location |
|---|---|---|
| Plan and execution order | Step order, rollback, verification. **No OS branching** | `sage/uninstall_executor.py`, `uninstall_plan.py` |
| Backend seam | Protocol and backend selection. Decides nothing about which assets to handle | `sage/uninstall_fs.py` |
| POSIX backend | `dir_fd` binding | `sage/uninstall_posix_fs.py` |
| Windows backend | `NtCreateFile` with `OBJECT_ATTRIBUTES.RootDirectory` handle binding. **Only this file knows Windows** | `sage/uninstall_windows_fs.py` |

Safety comes from opening and **holding the target's parent directory** before the first change.
After that, whatever happens to the ancestor path names, the work still lands in the original
directory. What POSIX gets from `dir_fd`, Windows gets from the parent handle. There is no
path-string write fallback, and a source check asserts its absence.

### Support policy and capability are different questions

Folding them into one value makes "did we say we support this environment" indistinguishable from
"can this be done safely here". Then narrowing the documented scope also means losing backend
regression coverage, and the narrower the scope the less you know.

| Axis | What it looks at | Where it is enforced | Screen |
|---|---|---|---|
| **Policy** (`support_policy`) | SKU and build only | One place in the CLI, after planning and before the confirmation prompt | `BLOCKED` (2) on both `--check` and `--yes` |
| **Capability** (`probe_capability`) | Volume, filesystem, native primitives, pointer width, architecture | The execution layer | `--check` shows the plan; only a mutation request is refused |

**The policy asserts nothing about capability in either direction.** All it knows there is the SKU
and the build, so "the primitives are missing" and "the primitives are present" are both claims it
never measured. The one fact a policy refusal can state is this: the environment is outside the
support scope, and capability was not evaluated at this stage.

The screens differ because what the user should do next differs. A policy refusal means automatic
removal will never happen here, so a plain plan would read as something about to run. A capability
limit can become true by switching volumes or choosing a different root, so blocking the plan too
would present something fixable as unfixable.

Authority for the architecture and pointer-width judgement lives in **one place in the product**
(`native_floor`). If CI carried its own table, the environment the product executes in and the
environment CI produces evidence from could diverge, with no place left to ask which one is right.
The CI gate only consumes that result.

## Trust boundary: what SAGE blocks and does not block

**SAGE blocks**

- Drift: `sage validate` detects mismatches between specs and generated assets.
- Destructive execution in an unverified environment: `sage uninstall` asks both axes — support
  policy and capability — **before the first mutation**, and refuses when either is unconfirmed.
  What could not be determined counts as a refusal, not a pass: treating absence as the safe
  direction is exactly how an unverified environment ends up running silently.
- Direct edits: the write guard blocks edits to generated assets and redirects changes to specs.
- Single-model bias: cross-model review uses the opposite runtime for independent review.
- Silent gate disablement: `sage validate` fails closed on profile typos and unknown keys that could
  silently disable gates. This is validation-time fail-closed behavior. Runtime profile *parsing*
  failures are a separate layer and remain fail-open with a LOUD warning, as described above.
- Phase 06 bypassing Phase 05: completion reports are deterministically bound to an APPROVED review.
- Unrehashed mutation, insertion, non-tail deletion, or reordering of Loop A evidence: the real
  report gate validates per-run strict hash chains, record self-hashes, and file parse integrity.
- Missing or bypassed local hooks: local hooks only work if the contributor's machine has SAGE
  installed. SD-9/Fast Cycle add a server-side authority (`sage/ci_authority.py`, pure and
  git-independent) that independently re-verifies the strict hash chains of `.sage/fast_cycle.jsonl`
  and `loop_audit.jsonl` in CI, so a PR from a contributor without hooks — or one who bypassed them
  — is still caught by the required check. The local gate is not the only line of defense.

**SAGE does not block by design**

- **A fully compromised host runtime**: SAGE assumes the host invokes CLI commands and skills
  according to their contracts. A maliciously modified runtime is outside the threat model.
- **A fully recomputed or legacy-downgraded rewrite of `loop_audit`**: the strict per-run hash chain
  uses canonical SHA-256 with fixed key ordering and Unicode representation to self-verify each
  record and its immediate predecessor. While any v1 chain field remains in a run, it detects
  mutation, insertion, non-tail deletion, and reordering when hashes are not recomputed. It does not
  authenticate the file against an attacker who can recalculate the chain. Legacy compatibility also
  accepts a run with no chain fields as `chain_ok=None`, so removing all three chain fields from
  every record in a run is indistinguishable from legitimate legacy data. Without a secret key,
  signed head, a tip in another artifact, a Git baseline, or an external witness, this is
  **self-verification**, not standalone tamper resistance. A tip edit is detected by the record
  self-hash, deletion of the final close is rejected by the report gate's `closed` invariant, and
  Git history plus code review remain the external anchor for fully recomputed or downgraded
  rewrites.

Threats beyond this boundary, such as a compromised runtime or audit-log tampering, are mitigated by
higher-level procedures such as cross-model review and human approval. Deterministic gates prevent
mistakes, laziness, and drift by an honest host; they are not intended to stop an adversarial host.
