# [Base Plan] SAGE 10-h Retro Audit Local-State Boundary

Cycle-Stem: `sage-retro-audit-local-state`
Risk Level: L2
Status: IMPLEMENTED

## 0. Prior Knowledge

| Type | Source | Key Takeaway |
|---|---|---|
| Field evidence | ChatForYou `.sage/retro_audit.jsonl` | Six records exposed a user home, local directory layout, private Obsidian vault name, and note title through `note_path`. |
| Repository | `sage.commands.install._LOCAL_STATE_IGNORE_ENTRIES` | `sage install` revives `retro_audit.jsonl` as a tracked path through a managed `!` rule. |
| Repository | `retro_audit.audit_summary` and `hook_runtime` | The retro gate reads the file from the local working tree. Git tracking is not part of the gate decision. |
| Repository | `retro_audit.digest_of` | The digest records check-time content but is intentionally not rechecked after later human editing. A peer without the private vault cannot reproduce it. |
| Backlog | `plan_docs/enhancement-backlog.md` EH-8 | Integrity and authority hardening for the remaining audit logs is a separate deferred L3 task. |
| Decision | 2026-07-31 user approval | Existing tracked files are detected and reported, but install never changes the Git index or deletes the local file. |

## 1. Goal

Make `.sage/retro_audit.jsonl` machine-local by default so normal use cannot publish private
Obsidian paths or create cross-developer conflicts in a shared append-only file.

The local file remains the runtime evidence used by `sage retro --check`, the Stop hook retro gate,
and `sage doctor`. This change alters Git tracking policy only; it does not weaken or replace the
local gate.

## 2. Problem

The managed `SAGE LOCAL STATE` block currently excludes `.sage/*` and then explicitly re-includes
four audit files, including:

```gitignore
!/.sage/retro_audit.jsonl
```

A successful `sage retro --check` records the CLI path verbatim as `note_path`. For a private
Obsidian vault this is normally an absolute path under the user's home directory. The committed
record therefore exposes machine-local information that peers cannot use:

- the peer does not have the same vault or filesystem path;
- the note is intentionally outside the project repository;
- the check-time digest is not a durable current-content assertion;
- each developer appends different local paths to the same file, causing avoidable merge conflicts.

Changing `note_path` to a relative path does not solve the missing-note, unverifiable-digest, note
title, or multi-writer problems.

## 3. Locked Scope

10-h changes:

- the managed `.gitignore` policy installed by `sage install`;
- this engine repository's own `.gitignore`, which carried the same retro exception. The engine is
  dogfooded with SAGE, so leaving it would expose a maintainer's private vault path in the one
  repository most likely to run `sage retro --check`;
- upgrade diagnostics for an already tracked `.sage/retro_audit.jsonl`;
- Korean and English artifact ownership documentation;
- install regressions for fresh, upgraded, tracked, and explicitly opted-in projects;
- the EH-8 description only where its committed/local premise becomes stale.

10-h does not change:

- `retro_audit.jsonl` record fields, parser, writer, or digest;
- retro gate, Stop hook, doctor, or `sage retro --check` decisions;
- EH-8 hash-chain, locking, authority, or malformed-record work;
- the Git index, working-tree audit file, or repository history automatically;
- the tracking policy for `loop_audit.jsonl`, `override.jsonl`, or
  `acceptance-waivers.jsonl`.

## 4. Tracking Contract

The installed managed block becomes:

```gitignore
!/.sage/
/.sage/*
!/.sage/override.jsonl
!/.sage/acceptance-waivers.jsonl
!/.sage/loop_audit.jsonl
```

`.sage/retro_audit.jsonl` is consequently ignored but remains writable and readable on disk.

The three shared logs retain repository value:

- `override.jsonl` records bypass behavior;
- `acceptance-waivers.jsonl` records explicit evidence waivers;
- `loop_audit.jsonl` is the shared Phase 05 review source of truth.

`retro_audit.jsonl` is different: it binds a local Stop-gate decision to a private, unshared note.
It is local operational state, not portable team evidence.

## 5. Existing Installations

Updating `.gitignore` does not untrack a path already present in the Git index. During install,
SAGE checks whether `.sage/retro_audit.jsonl` is tracked.

If tracked, install prints a deterministic warning with:

```bash
git rm --cached -- .sage/retro_audit.jsonl
```

The warning also states that:

- the command preserves the working-tree file;
- existing Git history is unchanged and requires a separate explicit history-rewrite decision.

The installer must not run that command, stage a deletion, remove the local file, or fail the
installation. A missing Git executable, a non-Git destination, or an untracked file produces no
warning and no error. The advisory Git probe has a five-second timeout; process-launch and timeout
failures are non-fatal because the tracking policy has already been installed successfully.

## 6. Explicit Project Opt-In

A project that deliberately stores portable retro notes may opt back into tracking by adding this
rule after the managed block's end marker:

```gitignore
!/.sage/retro_audit.jsonl
```

Rules inside the managed block are replaced on install. Rules before the managed block lose to its
later `/.sage/*` match. Documentation must therefore say both "outside" and "after."

## 7. Required Regression Teeth

- Fresh install ignores `.sage/retro_audit.jsonl`.
- Fresh install still exposes the other three audit files to Git tracking.
- An old managed block containing the retro exception converges to the new block.
- User-authored content outside the managed block is preserved.
- An explicit retro exception after the end marker remains effective.
- A tracked retro audit produces the migration warning.
- Warning detection leaves both the index and working-tree bytes unchanged.
- An untracked file, non-Git destination, or unavailable Git executable does not warn or fail.
- A non-terminating Git probe is stopped after five seconds and does not stall or fail install.
- Repeated install remains idempotent.
- Focused retro and Stop-gate tests remain green, proving ignore status does not change runtime use.

## 8. Documentation and Backlog

`docs/ARTIFACTS.md` and `docs/ARTIFACTS.en.md` must agree that three audit logs are committed and
`retro_audit.jsonl` is local. They must include the upgrade command, history limitation, and explicit
opt-in placement.

EH-8 remains deferred. Its retro-audit integrity scope is still valid, but its description must no
longer claim that retro audit is a committed source of truth.

## 9. Acceptance

- A default SAGE install cannot newly stage `retro_audit.jsonl`.
- Existing tracked installations receive actionable, non-destructive migration guidance.
- The local retro gate behavior is unchanged.
- The three other audit tracking contracts are unchanged.
- No automatic Git index mutation or history rewrite occurs.
- Korean and English artifact documentation is synchronized.
- Focused install, retro, Stop-hook, full hook, source validation, and wheel checks pass.
