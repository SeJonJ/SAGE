# SAGE Operability Diagnostics and Recovery UX Design

Status: APPROVED by user on 2026-08-13

Date: 2026-08-13; frozen into this repository on 2026-08-23

Canonical source: the Korean wiki note `SAGE - 1.0 운영 진단과 복구 UX 설계 (26.08.13)`.
This file is the execution copy for the `sage-operability-diagnostics` cycle. When the two
disagree, the wiki note wins and this file is corrected; this file exists so that a fresh-context
reviewer who cannot reach the wiki still reads the approved design.

Cycle stem: `sage-operability-diagnostics`

Preceding work: `v1.0.0 준비` (bilingual CLI/hook catalogs, `upgrade`, version contract) and
`sage-fast-cycle-usability-hardening`, both merged to `main`.

Frozen implementation baseline: `main@63cc3bd`

Scope: design only; no implementation, commit, merge, or release is authorized by this document.

Deviations: the cycle's Phase 00 (`plan_docs/00-base_plan/sage-operability-diagnostics.md`)
records four deviations D1-D4 from this design, each with the measured problem that caused it and
the mechanism that preserves this design's intent. Read that section alongside this file.

## Key takeaways

- After being blocked, a user reads `sage status` for the current state and recovery order instead
  of guessing among several commands.
- `sage explain --path ...` explains which rules a path falls under. It does not receive new file
  content or the session declaration, so it never predicts that a real write will be allowed.
- Every user-facing BLOCK carries a stable diagnostic code and at least one `Next:`.
- If a project hook requires a runtime API newer than the running `sage-hook`, the mismatch is
  closed before core import, preventing a `ModuleNotFoundError` traceback and host-specific
  fail-open interpretation.
- `doctor` and `validate` remain. `status` is the fast operational summary, `doctor` is deep
  environment diagnosis, `validate` is full asset integrity verification.
- Unified audit-log reading and the whole-product no-vault Golden E2E belong to the following item,
  `sage-audit-visibility-no-vault`.

## 1. Problems to solve

### 1.1 The user cannot see the current state at a glance

Diagnosis is split across commands:

| Command | Current role | What is missing |
| --- | --- | --- |
| `sage doctor` | Deep diagnosis of Python, host, reviewer, optional capabilities | Output is long and does not summarize whether work can start now |
| `sage validate` | Schema, hash, manifest, generated asset integrity | Does not explain why a specific path is blocked |
| hook BLOCK | Judgement at actual write/stop time | After the block, the next command differs per message or is absent |
| `sage upgrade --check` | Version movement preflight | Does not unify cycle/profile/hook readiness beyond version |

Users must guess whether to run `doctor`, `validate`, `install`, `generate`, or `upgrade` first.

### 1.2 `--path` alone cannot reproduce the real hook verdict

The real gate verdict depends on more than the path: the content about to be written and its
keywords, the risk declaration captured in the current session, the multi-change list the host
passed, the cycle stem and Phase 00-06 snapshot, and audit/waiver/override state.

Therefore `sage explain --path` asserting `ALLOW` would be a false guarantee. The command must
explain the **path-based risk floor and the currently checkable preconditions**, and structurally
mark that the real write may be stricter depending on content and session input.

### 1.3 A runtime import failure happens before the compatibility error

The observed shape:

1. A consuming project's new hook core imports a new package API such as `sage.done_criteria_contract`.
2. The `sage-hook` on the running machine comes from an older SAGE package.
3. The old `sage-hook` imports the project core first.
4. `ModuleNotFoundError` is raised and, depending on the host, may be treated as a plain hook error.

This is not solved by copying every package module into the consuming project. Under the
operational premise that there is a single pre-1.0 installation user, from 1.0 the system
**generates and verifies a runtime API marker and closes the mismatch before import**.

### 1.4 Escape routes from BLOCK are not uniform

Some hook messages give concrete recovery hints; others state only the cause. Bootstrap and
dispatch exceptions are sometimes printed directly, outside the existing `message_key` render path.
A user must always be given a safe first action right after a BLOCK.

## 2. Scope

### 2.1 Included

1. A language-neutral diagnostic result and recovery step contract.
2. A fast read-only `sage status [--json]`.
3. A per-path read-only `sage explain --path <path>`.
4. A project hook runtime API marker and a pre-import compatibility preflight.
5. A guaranteed `Next:` on every user-facing BLOCK from built-in CLI and hooks.
6. Korean/English output and machine JSON stability.
7. Real Claude/Codex adapter subprocess regressions.
8. Wheel-install environment regression and manifest/schema re-stamping.

### 2.2 Excluded

- `sage audit show`, which merges the four `.sage` audit logs.
- Obsidian dashboard creation or modification.
- Promoting Obsidian MCP or vault existence to a SAGE prerequisite.
- Removing or renaming `doctor` and `validate`.
- Synthesizing a virtual host event in `explain` to run the real gate.
- Automatic fixes, automatic upgrade, automatic `install --force`.
- Inferring the meaning of arbitrary natural-language messages authored by project hooks.
- Cross-process project-root unification, rejected as J-3.
- Vendoring the whole package into the project hook runtime.

## 3. Alternatives considered

### 3.1 Recommended A: a shared diagnostic contract plus thin commands and renderers

Every judgement source returns a `Diagnostic`, and `status`, `explain`, and the hook renderer
consume the same code, severity, and recovery steps. Existing pure judges are called; judgement
logic is not copied into the new commands.

Advantages: text and JSON come from the same facts; a missing `Next:` on a BLOCK can be detected
mechanically; `status` and `explain` do not become new authorization judges; the existing
responsibilities of `doctor` and `validate` are preserved.

Disadvantages: bootstrap BLOCKs that print directly must be structured; the render boundary between
the CLI catalog and the self-contained hook catalog must be maintained.

### 3.2 Alternative B: only extend `doctor` and `validate` output

Rejected: the beginner's "which command do I run" problem remains, there is no `--path` explanation
and no machine-readable operational state, and `doctor` grows longer while its role blurs.

### 3.3 Alternative C: a real hook dry-run

`explain` would synthesize a host event and call the real hook.

Rejected: `--path` alone cannot restore proposed content, session declaration, or the multi-change
event. Guaranteeing that audit and state are untouched also becomes complex. The result would look
precise while differing from the real write.

### 3.4 Conclusion

**A is adopted.** The point is not to build a new judge but to carry existing judgement results
through a stable diagnostic contract with a safe recovery order attached.

## 4. The shared diagnostic contract

### 4.1 Data model

```text
Diagnostic
  code: str
  severity: INFO | WARN | BLOCK
  subject: str
  message_key: str
  arguments: map[str, scalar]
  evidence: map[str, JSON scalar/list/map]
  recovery: tuple[RecoveryStep, ...]

RecoveryStep
  id: str
  command: str | null
  description_key: str
  arguments: map[str, scalar]
  mutating: bool
```

The contract enforces:

1. `code` is a stable, language-independent identifier.
2. Human-readable sentences are owned by the catalog.
3. JSON carries no translated sentences — only `code`, structured evidence, and recovery commands.
4. A `BLOCK` may not have empty recovery, and at least one step must be an executable command.
5. When there is no safe direct recovery command, the first step is a read-only diagnostic command
   such as `sage status` or `sage explain --path ...`. Instructions requiring a human are separated
   as `Action:`.
6. Recovery commands are never executed automatically.
7. Personal or secret data — absolute paths, vault paths, tokens, environment variable values — is
   not placed in evidence.

### 4.2 Code namespace

| Code | Meaning |
| --- | --- |
| `runtime.api_too_old` | The project hook requires an API newer than the current `sage-hook` |
| `runtime.api_marker_missing` | A 1.0 manifest has no marker |
| `version.runtime_mismatch` | The exact required version and the CLI runtime disagree |
| `profile.shared_invalid` | Shared profile parse or semantic error |
| `install.hook_registration_missing` | An active host hook registration is missing |
| `cycle.binding_missing` | The current path lacks a required cycle binding |
| `gate.phase_incomplete` | Prerequisite phases for that risk are unmet |
| `guard.generated_asset` | An attempt to edit a SAGE-generated asset directly |

Existing hook `message_key` values are a compatibility contract and are not renamed. Diagnostic
codes are derived either by a deterministic transform of the key with the `block_` prefix removed,
or by explicit mapping. Ambiguous automatic inference is forbidden and a build-time oracle catches
omissions.

### 4.3 The self-contained hook boundary

An installed hook runtime must keep its existing judgement and message rendering without the main
`sage` package. The shared contract therefore must not cause the hook runtime to import the CLI i18n
package.

- CLI: value objects in `sage/diagnostics.py` plus the CLI catalog.
- hook: existing decision `message_key` and evidence, extended with `diagnostic_code` and
  `recovery_id`, plus the self-contained hook catalog.
- build-time verification: compare both sides' code/recovery sets and placeholder completeness.

What is shared is **shape and meaning**, not a runtime import that would break independent deployment.

## 5. `sage status [--json]`

### 5.1 Purpose

`status` is a read-only operational summary that answers, within a 1-2 second target on a normal
local repository, "can I use SAGE in this project right now" and "what do I fix first".

The default run does not touch the network and does not execute peer CLI, build, or regression
commands. Unavoidable child processes such as root discovery carry a 5-second timeout. The 1-2
second figure is a performance target for a normal local repository, not a guarantee of total wall
time if the filesystem itself stalls. If a required profile or manifest cannot be read, the command
does not guess its way down to READY — it surfaces a BLOCK or a tool error.

### 5.2 Collected areas

| Area | Displayed | Source of truth |
| --- | --- | --- |
| project | root recognition, consumer installation | manifest discovery rules |
| version | required, CLI runtime, installed, generated | `version_contract` |
| runtime API | current API, project required API, compatibility | the new marker contract |
| profile | shared/local load state, compiled profile freshness | `profile_layers`, `profile_compile` |
| host | active/configured host, hook registration and receipt state | `runtime_hosts`, host settings |
| cycle | active stem, mode, risk, declaration source | `cycle_state`, cycle binding |
| gate readiness | currently checkable common blocking causes | existing pure validators |

`status` does not run full asset hashing or regression commands; it points to
`sage validate --check --schema --kind all`. It does not run peer CLIs or query the model catalog;
it points to `sage doctor`.

### 5.3 Text example

```text
SAGE status: BLOCKED
Project: eformsign
Host: codex (configured)
Cycle: welstory-login / STANDARD / L3
Version: required=1.1.0 runtime=1.0.0 installed=1.1.0 generated=1.1.0

[runtime.api_too_old] project hook requires runtime API 2; current sage-hook provides API 1.
Next: pipx upgrade sage-harness
Next: sage install --host codex --force --dest .
Next: sage generate --kind hook --write
```

If the display language is Korean, explanations render in Korean while `SAGE status`, codes, state
tokens, and commands stay stable.

### 5.4 JSON schema v1

```json
{
  "schema_version": 1,
  "status": "BLOCKED",
  "exit_code": 1,
  "project": {"installed": true},
  "version": {
    "required": "1.1.0",
    "runtime": "1.0.0",
    "installed": "1.1.0",
    "generated": "1.1.0"
  },
  "runtime_api": {"required": 2, "current": 1, "compatible": false},
  "host": {"active": "codex", "configured": ["codex"]},
  "cycle": {"stem": "welstory-login", "mode": "STANDARD", "risk": "L3"},
  "diagnostics": [
    {
      "code": "runtime.api_too_old",
      "severity": "BLOCK",
      "evidence": {"required_api": 2, "current_api": 1},
      "recovery": [
        {"id": "upgrade-package", "command": "pipx upgrade sage-harness", "mutating": true}
      ]
    }
  ]
}
```

JSON uses byte-stable keys and enums independent of locale. Diagnostic order is fixed as
`BLOCK → WARN → INFO`, and within one severity by code sort.

### 5.5 Exit codes

| exit | Meaning |
| --- | --- |
| `0` | `READY`, or `ATTENTION` with warnings only |
| `1` | One or more `BLOCK` |
| `2` | Root cannot be determined, or `status` itself cannot interpret its input |

`status` does not reuse `validate`'s STALE-specific exit `3`. In the fast summary, staleness is
expressed as a WARN or BLOCK diagnostic according to real impact; detailed judgement stays with
`validate`.

## 6. `sage explain --path <path>`

### 6.1 Purpose and non-guarantee

The command explains why a file is classified at a given risk, which cycle it currently binds to,
which documents are missing, and what to do next.

It always displays:

> This result is based on the path and the current repository state. The real write may be stricter
> depending on new content, the session risk declaration, and other files changed at the same time.

Therefore `ALLOW` is never used as a final result.

### 6.2 Input safety

- Relative paths resolve against the project root.
- Absolute paths are accepted only inside the project root.
- `..` escapes and gate-forbidden intermediate or leaf symlinks are rejected with exit `2`.
- A path that does not exist yet can still be explained.
- Existing file content is not read to guess content risk, because it differs from the new content
  the user intends to write.

### 6.3 Output

```text
Path: src/payment/LoginService.java
Path risk floor: L2
Matched rule: risk.l2_path_globs[1] = src/**
Component: payment
Cycle: welstory-login (source=.sage/cycle.json)
Required pre-implementation phases: 00, 01, 02, 03
Current phase readiness: BLOCKED (missing: 02, 03)
Dynamic checks at write time: content keywords, session declared risk, multi-file maximum

[gate.phase_incomplete] Phase 02, 03 are missing.
Next: sage cycle show
Next: sage explain --path "src/payment/LoginService.java"
Action: Write Phase 02 and 03 for the same stem, then run the command above again.
```

For a generated asset, write-guard ownership and the correct modification route are shown:

```text
[guard.generated_asset] This path is a generated SAGE asset.
Next: sage change "<asset-id> modification"
Action: Edit the canonical spec named above, then run `sage generate` and `sage validate`.
```

### 6.4 Judgement reuse

`explain` does not call the whole gate. It reuses or narrowly extracts these pure helpers: path
normalization/containment, component ownership resolution, path glob risk floor, generated asset
ownership, cycle binding resolution, and required-phase computation per risk. Content keywords,
session declaration, and multi-change maximum are stated as `dynamic_checks`. A parity test fixes
this split.

## 7. Runtime API compatibility preflight

### 7.1 The marker

A 1.0 manifest gains this top-level contract:

```json
{
  "runtime_api": {
    "required": 1
  }
}
```

The first API in 1.0 is `1`. The package carries the same integer constant `HOOK_RUNTIME_API = 1`.
The integer increases monotonically and only when:

- project-installed core/runtime requires a new `sage.*` module or a new callable contract,
- the `sage-hook` dispatch or profile preflight input contract changes incompatibly, or
- an existing runtime cannot safely execute a new project hook.

Wording changes, new diagnostic codes, and compatible optional fields do not raise it.

The manifest does not store a minimum SAGE version alongside the API. The source of truth for the
required SAGE version remains the exact `sage.required_version` in the shared profile. Compatibility
judgement is owned by the integer API comparison; only the version guidance inside error messages
comes from the existing exact-version contract.

### 7.2 Stamp and verification ownership

- `install --force`: records the installing runtime and the manifest marker together.
- `generate --kind hook --write`: preserves or re-stamps the marker and validates the manifest schema.
- `validate`: cross-checks package API, manifest marker, and generated runtime hash.
- `upgrade --check`: indicates whether an API migration is required.
- `sage-hook`: reads the marker and decides compatibility before importing project core.

### 7.3 Preflight decision table

| Manifest state | gate / project hook | logger / baseline |
| --- | --- | --- |
| Legacy manifest whose `generator_version` major is `0`, no marker | existing behavior; upgrade WARN at SessionStart only | existing behavior; upgrade WARN at SessionStart only |
| 1.0 manifest, marker present and compatible | run | run |
| 1.0 manifest, marker missing or damaged | BLOCK exit 2 | WARN exit 0; the pre-gate blocks separately |
| required API > current API | BLOCK exit 2 | WARN exit 0; the pre-gate blocks separately |

A registered project hook enforces policy, so it is fail-closed like the gate. One incompatible post
logger or baseline hook does not directly block the whole host operation but leaves a LOUD WARN; the
real write is blocked by the pre-implementation gate under the same preflight.

Legacy is not concluded from marker absence alone. Pre-1.0 installation is recognized only when
`generator_version` is valid SemVer with major `0`. If the version is missing or damaged and the
marker is absent too, the state is treated as damaged, so a downgrade that erases both marker and
version does not pass.

### 7.4 Error message

Printed before core import, in this shape. Tracebacks are forbidden.

```text
⛔ BLOCK [runtime.api_too_old]
Project hooks require SAGE runtime API 2, but this sage-hook provides API 1.
Required SAGE: >= 1.1.0
Current sage-hook: 1.0.0
Next: pipx upgrade sage-harness
Next: sage install --host <active-host> --force --dest .
Next: sage generate --kind hook --write
Next: sage status
```

If the runtime already has the 1.0 `upgrade`, the first step offered is `sage upgrade --check`. On a
legacy runtime lacking the command, an unusable command is not suggested; package upgrade comes first.

The wire representation of BLOCK preserves the host contract. Claude PreToolUse/Stop and Codex
PreToolUse use stderr and a blocking exit as before. Codex Stop keeps its existing contract of a
single `{"decision":"block","reason":"..."}` JSON on stdout with rc `0`, with the diagnostic code and
`Next:` inside `reason`. Diagnostic UX is not a reason to unify every host event onto exit `2`.

### 7.5 Security boundary

The runtime API marker is a compatibility and operational-safety contract, not an external anchor
against an attacker. Deleting the marker is not claimed to be a security-complete defense. What it
does provide is that marker absence in a 1.0 manifest is judged as damage, preventing a silent
legacy downgrade.

## 8. The `Next:` contract for every BLOCK

### 8.1 Applies to

- built-in hook decisions with `status=block`
- `sage-hook` bootstrap, runtime, and dispatch BLOCKs
- CLI operational errors that terminate as `BLOCK` or `BLOCKED`
- built-in runtime BLOCKs wrapping a project hook contract failure

Not covered: the literal `BLOCK` used as an example in documentation; state values in enums,
constants, and audit JSON; test fixture strings; renaming all of `validate`'s generic `FAIL` to
BLOCK; arbitrary natural language a project hook author wrote inside their own message.

### 8.2 Render rules

1. At least one `Next:` line follows the BLOCK body.
2. At least one `Next:` line must be an executable command. Manual-edit instructions go under `Action:`.
3. Recovery order is read-only check → required mutation → re-verification.
4. Destructive commands, audit-log deletion, profile relaxation, and generic override are not offered
   as default recovery.
5. Only project-relative paths are displayed.
6. With no safe direct recovery, the sequence starts with `Next: sage status` or
   `Next: sage explain --path ...`.
7. The same recovery id never yields different commands in different places.
8. The `Next:` token stays identical in Korean and English so it remains searchable and collectable.

### 8.3 Completeness oracle

Build/test enforces:

- built-in block message key set minus recovery mapping key set is empty
- every block recovery has at least one executable command
- Korean and English recovery catalog keys and placeholder sets match
- bootstrap direct BLOCKs also pass through the diagnostic renderer
- every rendered BLOCK fixture contains `Next:`
- INFO/WARN/OK are not forced to carry an unnecessary Next

## 9. Role separation from existing commands

| The user's question | Command |
| --- | --- |
| Can I use SAGE right now? | `sage status` |
| Why does this path carry these requirements? | `sage explain --path ...` |
| Are the installed tools, peer models, and optional capabilities ready? | `sage doctor` |
| Are all assets, schemas, and hashes correct? | `sage validate --check --schema --kind all` |
| Can I move safely to another SAGE version? | `sage upgrade --check` |
| Can I see the audit history on one screen? | the following `sage audit show` |

When `status` finds a problem it links to the detailed command; it does not produce that command's
result on its behalf.

## 10. Implementation structure

Expected new and changed boundaries. File names are finalized at implementation start against the
merged state of the preceding branch.

| Boundary | Responsibility |
| --- | --- |
| `sage/diagnostics.py` | immutable diagnostic/recovery model, ordering, JSON serialization |
| `sage/diagnostic_collectors.py` | project/version/profile/host/cycle quick collectors |
| `sage/runtime_api.py` | package API constant and manifest compatibility pure function |
| `sage/commands/status.py` | text/JSON renderer and exit code |
| `sage/commands/explain.py` | contained path resolution and path-only explanation |
| `sage/hook_entry.py` | runtime API preflight before core import |
| hook runtime message layer | block code → recovery id and `Next:` rendering |
| manifest schema/install/generate/validate/upgrade | marker stamp, verification, migration |

An implementation where a collector calls `doctor.run()` or `validate.run()` as a subprocess and
re-parses stdout is forbidden. Reuse the needed pure functions, or extract them narrowly.

## 11. Failure handling

| Failure | Handling |
| --- | --- |
| no root | `status`/`explain` exit 2 with a Next that checks whether this is an install target |
| damaged profile YAML | BLOCK diagnostic, no traceback |
| damaged manifest | BLOCK diagnostic, no automatic overwrite |
| damaged host settings | preserve existing BLOCK or WARN contract, guide `install --force` |
| runtime API mismatch | BLOCK before project core import |
| missing recovery catalog | development test FAIL; at runtime, a safe `Next: sage status` fallback |
| i18n render failure | keep the verdict and exit, expose the diagnostic code |
| `explain` target outside root | exit 2, the path is not read |

## 12. Test strategy

### 12.1 Unit contracts

1. Diagnostic JSON serialization and deterministic ordering
2. Rejection of empty BLOCK recovery
3. Severity and exit aggregation
4. Runtime API decision table: legacy / compatible / newer / missing / malformed
5. Path containment and symlink escape
6. Pure parity of path risk floor, component ownership, and generated ownership

### 12.2 CLI golden

- `status` READY, ATTENTION, BLOCKED, TOOL ERROR
- `status --json` schema v1 and locale independence
- `explain` L0/L1/L2/L3, absent path, generated asset, missing phases, root escape
- Korean/English equivalence of code, Next command, and exit
- identical tracked files and `.sage` byte snapshot before and after each command

### 12.3 Real adapter subprocess

For Claude and Codex each, run through the real `sage-hook` entrypoint:

1. compatible API → existing gate decision preserved
2. required API greater → rc 2, core import not reached, no traceback, `Next:` present
3. 1.0 marker missing → rc 2
4. legacy, no marker → existing behavior, WARN only at SessionStart
5. logger/baseline incompatible → rc 0 LOUD WARN
6. project hook incompatible → rc 2
7. Codex Stop incompatible → rc 0 plus a single `decision:block` JSON whose reason carries code and Next

### 12.4 Mutation teeth

- moving the compatibility preflight after core import fails
- removing the required/current comparison fails
- downgrading a missing 1.0 marker to legacy fails
- removing one BLOCK recovery mapping fails
- `explain` reading existing content to raise risk fails
- putting a translated message into `status --json` fails locale parity
- a collector writing a file fails the read-only snapshot
- removing `Next:` from either the Claude or Codex renderer fails

### 12.5 Integration

- explicit registration of new tests in `run-all.sh` plus test inventory completeness
- full hook suite in none/Claude/Codex environments
- `status`, `explain`, and runtime preflight exercised on the installed wheel in `wheel_smoke.sh`
- `sage validate --kind all --check --schema`
- manifest and runtime hash re-stamping
- `git diff --check`
- identical `status`, `explain`, and hook preflight results with no Obsidian configuration and no vault

The last item is a narrow regression showing these commands do not depend on a vault. The full
no-vault Golden for knowledge, retro, and audit belongs to the following cycle.

## 13. Implementation order

1. Confirm the preceding `v1.0.0 준비` branch is merged to main and re-read the final CLI/hook catalog
   and upgrade APIs.
2. In Phase 00, fix the inventory of current user-facing BLOCKs and direct-print exceptions.
3. Write failing tests first for the Diagnostic/RecoveryStep and runtime API pure contracts.
4. Implement manifest schema, stamp, validate, and upgrade compatibility.
5. Implement the pre-import preflight in `sage-hook` and dual-host subprocess regressions.
6. Implement the `status` collectors, text, and JSON.
7. Implement `explain` path-only analysis and fix gate helper parity.
8. Implement recovery mapping for all built-in BLOCKs and the completeness oracle.
9. Update README, quickstart, troubleshooting, and CLI reference in Korean and English.
10. Run wheel smoke and the full suite, and re-stamp manifest/runtime hashes.
11. Limit independent review to at most 3 rounds, reproducing each finding before deciding acceptance.
12. Do not commit, merge to main, push, or release before explicit user approval.

## 14. Acceptance criteria

- `sage status` prints READY/ATTENTION/BLOCKED read-only on a normal local repository with a 1-2
  second target and child-process timeouts.
- `sage status --json` satisfies schema v1, locale independence, and deterministic ordering.
- `sage explain --path` explains path risk floor, the matched rule, component, cycle, phase
  readiness, and dynamic limitations.
- `explain` never asserts that a real write is allowed.
- When a new project hook API is ahead of an old `sage-hook`, it is blocked with rc 2 before core import.
- Runtime compatibility errors carry no traceback and produce an executable recovery order.
- A missing or damaged marker in a 1.0 manifest is not downgraded to a legacy pass.
- Every built-in user-facing BLOCK carries at least one `Next:`.
- Recovery never offers profile relaxation, audit deletion, or generic override as the default fix.
- The existing roles and exit contracts of `doctor`, `validate`, and `upgrade` are not broken.
- Korean and English carry the same code, command, evidence, and exit.
- Regressions pass on real Claude/Codex adapters and in the wheel environment.
- Manifest, schema, and hook runtime hashes are current.
- These three features behave identically with no Obsidian and no vault.

## 15. Known limits and follow-ups

1. Path-only explain does not know proposed content or the session declaration, so it is not the real
   gate verdict.
2. A pre-1.0 `sage-hook` itself has no preflight code. The single existing user upgrades the package
   first when moving to 1.0.
3. The runtime API marker is an in-repository marker, not an external security anchor against a
   malicious full rewrite.
4. SAGE does not guess semantic recovery commands for custom project hooks; the wrapper guarantees at
   minimum a `sage status` fallback.
5. Unified audit reading and full no-vault verification are designed separately in
   `sage-audit-visibility-no-vault`.

## 16. Final recommendation

Implement this work as a **thin query and render layer built around a shared diagnostic data contract**.

- `status` is the fast operational entrance.
- `explain` explains path rules but promises no permission.
- `doctor` and `validate` remain the deep checks.
- Runtime API mismatch is closed before import.
- `Next:` on a BLOCK is a product contract with a completeness test, not a friendly phrase.

This composition improves usability while preventing the diagnostic commands from becoming a new
authorization bypass or a second source of truth for judgement.
