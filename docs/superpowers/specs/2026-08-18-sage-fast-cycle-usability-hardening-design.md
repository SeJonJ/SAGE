# SAGE Fast Cycle Usability Hardening Design

Status: APPROVED by user on 2026-08-13

Date: 2026-08-13; frozen into this repository on 2026-08-18

Canonical source: the Korean wiki note `SAGE - eformsign Fast Cycle 부트스트랩·전환·리뷰 조기 완료 설계 (26.08.13)`.
This file is the execution copy for the `sage-fast-cycle-usability-hardening` cycle. When the two
disagree, the wiki note wins and this file is corrected; this file exists so that a fresh-context
reviewer who cannot reach the wiki still reads the approved design.

Cycle stem: `sage-fast-cycle-usability-hardening`

Preceding feature: Fast Cycle emergency and convenience procedure, released in `v0.9.81`

Frozen implementation baseline: `feat/sage-stabilization-localization@7375a4a`

Scope: design only; no implementation, commit, merge, or release is authorized by this document

Disclosure policy: the discovering environment is an internal company project. It is named in the
internal wiki only. This repository document generalizes it and carries no personal absolute paths
or business identifiers.

## 1. Purpose

Fast Cycle is not a switch that turns gates off. It is a formal procedure that preserves the risk
level and the verification result while reducing documentation and review cost. Real use surfaced
three defects that chain together and block entry into Fast Cycle entirely, plus two operational
gaps that have no legitimate procedure today.

The three defects:

1. The Fast CLI validates a project-relative `governance_docs` path against the SAGE bundle root,
   so it rejects a profile that is in fact correct.
2. After an L2/L3 declaration, the planning documents themselves are governed at that risk level.
   Writing document 01 is blocked because 02 and 03 do not exist yet, and the documents the gate
   demands cannot be created.
3. The phrase `Risk Level` inside explanatory prose in a Phase 00 document is mistaken for a second
   declaration, which blocks every governed edit.

The two additions:

4. Convert an in-progress Standard Cycle to Fast Cycle on an explicit developer confirmation and
   a recorded reason.
5. Close a review loop early — after at least one completed round with no blocking-severity
   finding — on an explicit developer authorization that accepts the residual non-blocking risk.

All five are verified in one development cycle, but they are implemented as distinct features with
distinct state transitions. In particular, the Standard-to-Fast confirmation does not carry the
authority to close a review early, and the reverse is equally false.

### 1.1 Common invariants

- The actual Risk Level is never lowered or overwritten.
- User confirmation is never inferred. Without explicit CLI input, no state changes.
- A reason is a non-empty single line and its verbatim text is written to the audit log.
- The `.sage` JSONL files are the canonical record for authority and audit. Obsidian is a derived
  read-only mirror.
- Audit write failure, corruption, or binding mismatch fails closed.
- The existing 00–06, acceptance, Done Criteria, build/test/lint, write-back, and retro contracts
  are unchanged except where this document explicitly relaxes them.
- Local confirmation is `self_asserted_local`. It is never presented as remote identity proof or
  as organizational approval.
- `review_loop.max_iterations` is an upper bound on iterations, not a required count. Normal
  convergence may occur on the first round, and the early-completion feature neither replaces
  normal convergence nor attaches a warning to it.

## 2. Scope summary

| ID | Independent feature | Current problem | Goal |
|---|---|---|---|
| A | Fast profile root alignment | The Fast CLI discards the project root it already resolved and uses the bundle root | Narrowly fix the Fast working-tree path; do not unify root resolution globally |
| B | Phase document bootstrap | A write that would create a missing phase document is blocked by that document being missing | Permit phase-only creation and repair; keep mixed source changes blocked |
| C | Risk declaration parser | A word in prose plus a trailing colon is read as a declaration | Separate declaration grammar from prose and report the offending location |
| D | Standard to Fast conversion | The mode can only be chosen at cycle start | A `FAST-CONVERTED` state that rewrites no documents and records evidence at the conversion point |
| E | Early review completion | An unresolved non-blocking finding prevents normal closure even under urgency | The user explicitly accepts the residual risk and the reduced assurance is disclosed |

## 3. A — Profile validation root alignment

### 3.1 Confirmed defect

When `sage fast-cycle open|review|close|show` reads the profile, it passes the SAGE bundle root
rather than the project root into the `root` parameter of `validate_profile(profile, root)`.
A project-relative `governance_docs` file therefore fails as `profile invalid` even when it exists.

### 3.2 Fix contract

- A `sage fast-cycle` invocation running in a working tree passes the project root resolved by
  `_root(args)` into `validate_profile()`.
- An explicit `--root` value and an auto-discovered value must agree across validation, document
  selection, and audit paths.
- `sage validate` and `sage fast-cycle open` reach the same path verdict for the same profile and
  root.

This is not a new root resolver, and it does not force the CLI and the hook to agree on a root.
It is an in-process data-passing fix that stops `_profile(root)` from discarding the value
`fast_cycle._root(args)` already determined.

### 3.3 Boundary against the earlier J-3 root defect

J-3 was the problem of a CLI and a host hook in different execution environments inferring the same
root. Host environment and CLI context differ, full agreement could not be guaranteed, and after
five attempted fixes `K1 — CLI root != gate root` was accepted as a known limitation. A differs
from it because:

- It infers no new root.
- It changes neither the hook's `SAGE_PROJECT_ROOT`, nor the cycle declaration location, nor the
  monorepo discovery rules.
- It forwards a project root already selected inside the same Fast CLI invocation through to
  profile validation.

J-3's global root agreement problem is therefore not reopened.

### 3.4 Authority is split off as a separate defect

`sage authority` contains a similar bundle-root form, but that path inspects the profile of a base
or head Git tree. Simply substituting the current working-tree root would misjudge a past revision
profile that references files as they exist now.

Measurements confirm both failure directions:

- Even when `docs/policy.md` exists inside the commit, bundle-root validation fails with
  `path does not exist`.
- Replacing the bundle root with the checkout root wrongly fails a base profile when the file
  exists in the base commit but has since been deleted from the checkout.

This cycle therefore does not swap one argument in `authority.py`. Before protected authority is
enabled, a separate tree-aware profile validation task implements:

1. Schema, built-in runtime contracts, and default strategies validate against the trusted
   installed SAGE bundle.
2. Project-relative files such as `governance_docs` validate against the regular blob
   (`100644|100755`) of `base_tree` for a base profile and `head_tree` for a head profile.
3. Symlink, submodule, and tree entries do not count as ordinary documents.
4. Validation depends on neither the CWD nor file existence in the current checkout.

This authority follow-up does not block release of the current Fast CLI fix, but it must be
resolved before protected authority is enabled.

### 3.5 Regression teeth

- With a fixture holding three project-relative `governance_docs`, both `validate` and Fast open PASS.
- Removing one of those files makes both commands FAIL.
- A `--root` different from the CWD selects the intended project exactly.
- A mutation that restores `_resources.sage_root()` in Fast profile validation fails.
- Hook root resolver and cycle declaration tests PASS unchanged.
- Authority follow-up tests: base and head fixtures reference only their own revision's file set
  and are independent of the checkout.

## 4. B — Resolving the planning document deadlock

### 4.1 Problem

When session risk is declared L2 or L3, editing the planning documents is also raised to that risk
level. If `pre_implementation_required` demands 00–03, the write that would create 01 is blocked by
the absence of 02 and 03, and the states deadlock against each other. A Fast Plan is likewise not
recognized as Fast until its Fast metadata is on disk, so it cannot start itself.

### 4.2 Permitted range

Only a change satisfying **all** of the following is exempt from the missing pre-implementation
phase check:

- There is at least one change target.
- Every change target matches one of the profile's `pdca.phases[].glob` patterns.
- Each target is a phase document of the exact declared cycle stem.
- No source, configuration, or generated artifact is mixed into the same tool call.
- Desktop block, write guard, cycle binding, risk declaration, and report/approval gates all remain
  in force.

Only the act of creating phase documents is permitted. An `any()`-based exemption that would open
every gate by mixing one document line into a source change is forbidden; the existing `all()`
semantics of `_phase_only_change()` apply.

### 4.3 Fast pending state

`Fast-Audit-Run: pending` **does not** downgrade ordinary source edits to WARN. That would become a
bypass in which the audit run is never opened and pending is simply maintained.

- Creating or repairing the pending Fast Plan itself: permitted.
- Source edits before `sage fast-cycle open` succeeds: still BLOCK.
- The open failure message states the cause, the command to re-run, and the procedure for
  recovering to Standard.

### 4.4 UX boundary

No `sage cycle set --mode FAST` is added. A fresh Fast run keeps the existing `sage-cycle-fast` to
`sage-plan-fast` path that produces a composite 00, and conversion from Standard is owned by
`sage fast-cycle convert`. B only narrows the deadlock so that those two paths can create and repair
the phase documents they need.

## 5. C — Precise Risk Level declaration parsing

### 5.1 Problem

The current candidate expression treats any colon anywhere after `Risk Level` as a declaration
candidate. The following prose is not a declaration, but the colon in the trailing inline setting
causes it to be judged a malformed declaration:

```markdown
Risk Level: L1

> The `Risk Level` above follows the `l1_path_globs: src/**/*.js` verdict.
```

### 5.2 Fix contract

- The canonical declaration is the single header metadata region of the Phase 00 document selected
  by exact stem.
- The header region runs from the start of the document to the first heading of level H2 or deeper.
  An H1 title is permitted inside it.
- Fenced code blocks, blockquotes, indented code, inline examples, and body text after the first H2
  are excluded from declaration candidacy.
- The permitted grammar is the single line `Risk Level: L1|L2|L3`. For backward compatibility a bold
  label (`**Risk Level**: L3`) is also accepted. Bullets, trailing rationale, and other labels are
  not recognized as canonical declaration grammar.
- Exactly one valid declaration must exist in the header region. Duplicates, placeholders, and
  unsupported tiers fail closed.
- Errors distinguish `missing`, `duplicate`, `malformed`, and `placeholder`, and report the line
  number and a short excerpt of the offending text.
- The standard Phase 00, the fresh Fast composite 00, the pre-implementation gate, report and
  write-back tier decisions, and server authority all use the same dependency-free parser.
- Authority does not extract a maximum risk from prose in other phases; it uses only the exact
  Phase 00 declaration.

Shortening one regular expression fixes the example above but drifts again from other consumers
that scan document bodies. The parser is therefore promoted to a shared runtime contract so that
authoring, gate, and authority verdicts are fixed together.

## 6. D — Explicit conversion from Standard Cycle to Fast Cycle

### 6.1 Nature

This is neither an automatic mode change nor a gate override. It is an auditable state transition
in which the developer converts the remaining procedure of an already-started Standard Cycle to the
Fast contract.

### 6.2 Command draft

```bash
sage fast-cycle convert \
  --stem <stem> \
  --current-phase <00|01|02|03|04> \
  --level <L2|L3> \
  --lens-count <N> \
  --reason "<conversion reason>" \
  --confirmed-by "<explicit approver>" \
  --confirm FAST-CONVERTED \
  --root <project-root>
```

If any required input is absent, preflight exits 2 and writes neither files nor audit records.
`--current-phase` is a state input that stops the CLI from guessing completion from document
existence alone. The skill inspects the documents, proposes a candidate, and includes it in the
confirmation screen; the user does not have to supply it separately.

### 6.3 Pre-conversion checks

- `pdca.fast_cycle.enabled=true` in the shared profile
- The new `pdca.fast_cycle.standard_transition.enabled=true`
- An exact cycle stem declaration and a unique Standard Phase 00
- Phase documents up to `--current-phase` with no duplication, ambiguity, path escape, or symlink
- The actual Risk Level read by the shared Phase 00 parser is L2 or L3
- The actual Risk Level is pinned in the audit record; `--level` selects the Fast review policy only
  and does not change the actual risk
- The requested lens count and selected lenses satisfy the profile policy
- No conflict with an active Fast run
- A completed cycle holding a final approved 05 or 06 is refused
- The Phase 00 Done Criteria format and revision are intact. Incomplete items do not block the
  conversion itself, but must be resolved before review and close as the existing policy requires
- Existing audit log integrity PASSES

### 6.4 Developer confirmation screen

```text
⚠️ [SAGE CYCLE MODE CHANGE]

Converting the current Standard Cycle to a Fast Cycle.
Actual risk level: L3
Current phase: Phase 04
Fast verification: L2 / minimum 1 round / 2 lenses
Preserved documents: 00, 01, 02, 03, 04

Verification assurance is lower than the standard procedure. The conversion reason and the
approver are recorded in the audit log.
```

A CLI flag is not a value that imitates an interactive question; it is the channel that records what
the user actually answered. The skill presents the information above, receives the user's explicit
answer, and only then calls the CLI including `--confirm FAST-CONVERTED`. Direct CLI use without the
exact confirmation token does not convert either.

### 6.5 No-document-rewrite contract

- Existing Standard 00–04 are not deleted, moved, merged, or rewritten.
- No new composite 00 is created.
- No `Superseded-*` marker, Fast run ID, or conversion metadata is inserted into Standard documents.
- The canonical record of the conversion is the `fast_convert` opener in `.sage/fast_cycle.jsonl`.
- The conversion records, for each of 00–04 present at that moment, the root-relative POSIX path,
  the raw-byte SHA-256, the byte size, plus `--current-phase` and the Phase 00 Done Criteria
  revision.
- Documents such as Phase 04 may change afterwards through normal development. The conversion-time
  hash is provenance recording how far and with which documents Standard proceeded, not a freeze.
- Entering Fast review records the 00–04 snapshot again and structurally records additions,
  modifications, and deletions relative to the conversion point.
- Done Criteria revision changes and affected-phase re-execution arising from edits to completed
  phases remain owned by the existing EH-19 contract.

Because no document is written, no `conversion_prepare`/`conversion_commit` pair and no cross-file
rollback state are created. If the audit append fails, the pre-conversion state simply persists.

### 6.6 Audit event

The canonical file is the existing `.sage/fast_cycle.jsonl`.

```json
{
  "event": "fast_convert",
  "run_id": "fc-...",
  "entry_mode": "FAST-CONVERTED",
  "cycle_stem": "...",
  "current_phase": "04",
  "actual_risk_open": "L3",
  "fast_review_level": "L2",
  "minimum_rounds": 1,
  "lenses": ["correctness", "error_handling"],
  "reason": "...",
  "confirmed_by": "...",
  "attestation": "self_asserted_local",
  "source_phases_open": {
    "00": {"path": "...", "sha256": "...", "size": 1234},
    "04": {"path": "...", "sha256": "...", "size": 5678}
  }
}
```

A fresh Fast run starts with the existing `fast_open`; a converted run starts with `fast_convert`.
The two events normalize to the common state "exactly one opener" and thereafter share `fast_review`
and `fast_close|fast_abort`. The existing strict hash chain, sequence numbers, OS lock, and
partial-write rollback apply unchanged.

A converted run does not depend on a `Fast-Audit-Run` marker inside a document. It binds through the
exact cycle stem and the unique active converted run, and Phases 05 and 06 state `Fast-Run` and
`Loop-Run` explicitly. This path is not forced through the fresh-Fast `parse_fast_plan()`.

A converted `fast_review` records the review-time snapshot of 00–04 and an overall canonical digest.
`fast_close` recomputes the same snapshot and closes only when the documents have not changed since
review. The existing fresh-Fast `plan_hash_before_review` contract is preserved.

## 7. E — User-authorized early review completion

### 7.1 What the current contract is, and what this feature means

`review_loop.max_iterations.L3: 3` today means "at most three rounds if it does not converge", not
"three rounds required". If `survived=0` on the first round, the existing `CONVERGED` path approves
immediately. That case does not use the early-completion feature and attaches no `REDUCED` warning.

User-authorized early completion is meaningful only in the state where `sage review-loop next`
recommends `CONTINUE` — that is, non-blocking findings remain so the loop has not converged
normally, but the work will not continue because of urgency, token exhaustion, or similar. It is
therefore not a round-count waiver but an **explicit acceptance of residual non-blocking risk**.

It is independent of Standard-to-Fast conversion. A conversion confirmation cannot be reused as an
early-closure confirmation.

### 7.2 States that are never permitted

- Zero review rounds
- A last round whose `survived_by_severity` is absent or whose total differs from `survived`
- Any unresolved finding matching the profile's `severity_block`. The default `P0/P1` blocks on a
  single occurrence
- Architecture escalation or `BLOCKED_ARCH`
- Failure of a required build, test, or lint verification
- Unresolved Phase 00 Done Criteria or a missed revision re-execution
- Acceptance `FAIL`
- A required `NOT TESTED` without a waiver
- Corruption or chain/sequence failure in the Phase 04/05/Loop/Fast audit logs
- Mismatch of cycle stem, plan hash, loop run, or lens receipts
- A state in which the plan or source changed after 05 and re-review is required

Residual findings the profile does not block, such as `P2/P3`, are not treated as having vanished.
Their exact counts and a summary are recorded in Phase 05, Phase 06, and the Loop Audit, and the
user must accept that residual risk.

### 7.3 Profile contract draft

```yaml
pdca:
  fast_cycle:
    enabled: true
    standard_transition:
      enabled: false

  review_loop:
    early_completion:
      enabled: false
      minimum_completed_rounds: 1
```

- Both features must be explicitly enabled in the shared profile.
- The reason and the explicit confirmation are engine invariants rather than configurable knobs, so
  no true-only field for them is placed in the profile.
- A local profile can neither enable them nor lower the floor.
- The engine floor for `minimum_completed_rounds` is 1. A profile may only raise it.
- The `sage-init` and `sage-profile-modify` dialogues explain both features separately and propose
  `false` by default.

### 7.4 Command draft

No separate grant command is added; the existing close performs verification and audit together.

```bash
sage review-loop close \
  --run-id <rl-run-id> \
  --result APPROVED \
  --reason USER_AUTHORIZED_EARLY \
  --iterations <actual recorded round count> \
  --authorization-reason "<early completion reason>" \
  --confirmed-by "<explicit approver>" \
  --confirm USER_AUTHORIZED_EARLY \
  --root <project-root>
```

Attaching authorization arguments to an ordinary `CONVERGED|DRY` close is rejected. Conversely, if
`USER_AUTHORIZED_EARLY` is missing any one of the three arguments, the command exits 2 before any
append.

The command first prints the following state:

```text
⚠️ [SAGE REVIEW EARLY COMPLETION]

Configured iteration ceiling: 3 rounds
Completed reviews: 2 rounds
Residual findings: P0=0, P1=0, P2=2, P3=0
Next normal verdict: CONTINUE

Phase 06 will record REDUCED_BY_USER_AUTHORIZATION. Verification assurance is lower than a
standard L3.
```

### 7.5 Canonical audit record

The canonical record is the terminal `loop_close` in the existing `.sage/loop_audit.jsonl`. No
separate grant/use/revoke file is created. Because the close is appended inside the same OS lock
critical section immediately after verification, there is no TTL, reuse, or post-approval state
change problem.

Required fields for `loop_close(reason=USER_AUTHORIZED_EARLY)`:

- Cycle stem and Loop run ID, Standard/Fast mode, and the Fast run ID when Fast
- The actual Risk Level
- `completed_rounds` and `configured_max_iterations`
- The last round's `survived_by_severity`
- The actual lens receipts
- `authorization_reason`, `confirmed_by`, `attestation=self_asserted_local`
- The Phase 00 hash and Done Criteria revision
- `review_assurance=REDUCED_BY_USER_AUTHORIZATION`

To support this, `review-loop round` accepts `--survived-by-severity P0=0,P1=0,P2=2,P3=0`, records
`survived_by_severity={P0,P1,P2,P3}`, and enforces that the total exactly equals `survived`. The
receipt is mandatory for new runs; legacy rounds without it remain usable for ordinary
`CONVERGED|DRY` closes but cannot be used for early completion.

### 7.6 Representation in Phases 05 and 06

Early completion is the result of the user accepting residual non-blocking risk under their own
authority. For backward compatibility the final verdict remains `APPROVED`, but exactly one set of
the following metadata is enforced so it is never confused with an ordinary approval:

```text
Final Status: APPROVED
Review-Assurance: REDUCED_BY_USER_AUTHORIZATION
Review-Close-Reason: USER_AUTHORIZED_EARLY
Review-Rounds: 2 (configured max: 3)
Residual-Findings: P0=0, P1=0, P2=2, P3=0
```

Phase 06 records the same Loop run, the round count, a secret-free summary of the reason, and the
residual risk. Ordinary `APPROVED` and early-completion `APPROVED` are distinguished by the local
gate, dashboards, authority, and downstream reporting.

### 7.7 Single terminal transition and re-review after change

Because there is no separate grant, there is no pre-use invalidation state. `loop_close` may be
appended only once per run. After an early close, if any of the following changes, the existing 05
approval is stale and the work must be reviewed again under a new Loop run:

- The Phase 00 hash or the Done Criteria revision
- The last round's finding state or the implementation and verification evidence
- The Fast run ID or the plan hash
- The cycle stem
- The profile's review or Fast policy

## 8. Obsidian recording

### 8.1 Separation of roles

| Store | Role | Failure policy |
|---|---|---|
| `.sage/fast_cycle.jsonl` | Canonical record of Fast open, convert, review, close | Failure BLOCKS conversion and progress |
| `.sage/loop_audit.jsonl` | Canonical record of ordinary and early review close, rounds, residual findings | Failure BLOCKS 06 |
| Phases 00/05/06 | Binding IDs and assurance level retained in Git | Absence BLOCKS the gate |
| Obsidian vault | Human-readable derived dashboard | Failure WARNS; canonical success stands |

### 8.2 Vault output

When the effective `knowledge_capture.vault_path` is valid and the relevant dashboard setting is on,
the following per-project dashboards are updated:

```text
SAGE/Audits/Fast Cycle.md
SAGE/Audits/Review Loop.md
```

Displayed items: project and cycle stem; actual risk and the mode before and after a Standard-to-Fast
conversion; Fast level, rounds, and lenses; conversion or early-completion reason; approver and the
`self_asserted_local` marking; Fast run and Loop run; configured ceiling versus completed rounds with
a `REDUCED ASSURANCE` warning; residual finding severity totals and the early-closure reason; and
active/closed/aborted state.

The vault must be reproducible from the JSONL files and is never used for an authority decision. If
the path is absent or unwritable, a stderr WARN and a regeneration command are printed, and the
`.sage` audit success is not rolled back.

## 9. State machines

### 9.1 Standard to Fast

```text
STANDARD_ACTIVE
  -> preflight + explicit confirmation
  -> fast_convert / FAST_CONVERTED
  -> fast_review
  -> fast_close | fast_abort
```

- Because no document is written, there is no prepare/commit intermediate state.
- A failed `fast_convert` append leaves `STANDARD_ACTIVE` intact.
- Immediately after a successful append the active converted run is canonical and the Standard
  documents remain as they are.
- Two concurrent conversions must yield exactly one success.

### 9.2 Early review completion

```text
LOOP_ACTIVE (next=CONTINUE, round >= minimum, blocking survivors=0)
  -> explicit confirmation
  -> loop_close(APPROVED / USER_AUTHORIZED_EARLY)
  -> Phase 05 reduced-assurance metadata
  -> Phase 06 gate validates exact terminal audit
  -> cycle close
```

- If a normal `CONVERGED|DRY` close is possible, the early-closure command is refused and the normal
  close is suggested.
- After the terminal append, no further round or close may be added to the same run.

## 10. Implementation boundaries

### 10.1 Expected code range

- `sage/commands/fast_cycle.py`: root fix, `convert`, conversion preflight and state transition
- `sage/commands/review_loop.py`: `USER_AUTHORIZED_EARLY` close, explicit confirmation, severity
  cross-check
- `scripts/.../runtime/fast_cycle_audit.py`: the `fast_convert` opener and source snapshot
- `scripts/.../runtime/loop_audit.py`: severity receipts and early terminal metadata
- `scripts/.../runtime/risk_declaration.py`: the single canonical Phase 00 header parser
- `scripts/.../pre_implementation_gate_core.py`: phase-only exemption, shared risk parser, converted
  run recognition, 06 reduced-assurance verification
- `scripts/.../runtime/hook_runtime.py`: snapshot and vault derived data, and use of the shared parser
- `sage/ci_authority.py`: fresh/converted and ordinary/early Loop evidence decisions. The tree-aware
  profile fix is excluded
- Profile schema, manual validator, compiler, and the init/modify question contract
- Fast/standard cycle, plan, team, and review CORE skills
- Korean and English README, CLI, profile, and troubleshooting documents, and the vault dashboard
- Manifest re-stamping after tracked asset changes

### 10.2 Out of scope

- Changing the meaning of ordinary gate override
- Merging acceptance waivers with review exceptions
- Approval with zero review rounds
- Passing a profile `severity_block` finding, architecture escalation, FAIL, or audit corruption on
  user confirmation alone
- Using Obsidian as a canonical authority record
- Remote user identity proof
- Automatic Standard/Fast switching, or automatic selection based on the profile alone
- Fast-to-Standard reverse conversion. If needed it is designed as a separate state transition
- Global root unification between CLI and hook; reopening J-3 `K1`
- Replacing the bundle root in `authority.py` with the checkout root. Tree-aware profile validation
  is separate work

## 11. Core regression and attack tests

### A/B/C

- Windows and POSIX fixtures with relative governance documents show validate/Fast parity
- Creating phase 00, 01, 02, or 03 individually is permitted
- A mixed phase-document-plus-source change gets no exemption
- Documents of another stem and ambiguous documents are blocked
- `Risk Level` in prose, inline code, and blockquotes is ignored
- Duplicate, placeholder, and malformed declarations in metadata are blocked with a line number
- The pre-gate, Fast, report/write-back, and authority reach the same verdict on the same Phase 00
  risk fixture

### Standard to Fast

- Missing any one of confirm, reason, level, or lens produces zero writes
- A completed cycle, an active Fast conflict, a corrupted audit, and an actual L1 all block conversion
- The original 00–04 bytes are identical before and after conversion and no composite document is
  created
- `fast_convert` source path, hash, and current-phase snapshot are accurate
- Phase 04 changes after conversion are permitted and the review snapshot records the delta
- A failed audit append leaves zero document and state writes
- Concurrent conversions create exactly one run
- Fresh `fast_open` and converted `fast_convert` openers are never confused
- A conversion approval is not usable as a review early-close confirmation

### Early review completion

- Zero rounds, P0/P1 or any profile-blocking severity, architecture, test FAIL, and unresolved Done
  Criteria all block
- `survived_by_severity` totals that mismatch, are absent, or hold booleans, negatives, or unknown
  severities all block
- With `next=STOP/CONVERGED`, early closure is refused and the normal close is suggested
- With `next=CONTINUE`, zero blocking survivors, and an explicit approval and reason, terminal close
  succeeds
- Missing any one of the confirmation token, reason, or approver produces zero appends
- A failed loop close append leaves the run active and Phase 06 blocked
- Reduced-assurance metadata and the terminal audit blocking each other when absent or divergent
- Standard and Fast each bind to the exact cycle and run
- Rounds after an early close, duplicate closes, and cross-cycle use are all blocked
- No regression in the ordinary single-round CONVERGED path or the run-to-ceiling APPROVED path

### Audit and vault

- Malformed, non-object, modified, deleted, reordered, and partially appended records are detected
- Concurrent append sequence and chain consistency; no stealing of a live lock
- An unset vault is N/A; a vault write failure is WARN
- Vault dashboards are reproducible from the JSONL files
- Tampering with vault content leaves gate verdicts unchanged

### Full verification

- `run-all.sh` under none, Claude, and Codex
- Real adapter subprocesses on both hosts
- `sage validate --kind all --check --schema` with `STALE 0`
- Clean wheel install, generate, validate, and CLI smoke
- Windows native path and lock branches
- `git diff --check`, and mirrored Korean and English documents
- Independent review, at most three rounds. Each finding is reproduced before acceptance is decided

## 12. Implementation order

1. Pin minimal reproductions of A, B, and C as regression tests first.
2. Fix the working-tree root and the phase-only deadlock independently.
3. Introduce the shared Phase 00 risk parser and pin parity across all consumers.
4. Add the Standard-to-Fast and early-completion opt-in contracts to the profile.
5. Implement the document-free `fast_convert` state transition and the fresh/converted common summary.
6. Implement the Loop round severity receipt and the single `USER_AUTHORIZED_EARLY` terminal transition.
7. Bind Phase 05/06 metadata, the local gate, and server authority to the same decision helper.
8. Update the Fast/standard skills and the `sage-init` and `sage-profile-modify` dialogues.
9. Update the Obsidian derived dashboards and the Korean and English user documents.
10. Re-stamp the manifest and run the full suite, the wheel smoke, the Windows regressions, and the
    independent review.

Commit, merge, push, and release are not performed before separate explicit user instruction.

## 13. Decision summary

| Decision | Adopted |
|---|---|
| Naming the discovering project | Named in the internal wiki only; personal absolute paths and business identifiers generalized |
| Public issue tracker | Not filed |
| Pending Fast Plan | Phase repair only; relaxing source edits to WARN is rejected |
| Standard to Fast | Document-free `fast_convert / FAST-CONVERTED` requiring explicit confirmation and a reason |
| Early review completion | `USER_AUTHORIZED_EARLY` terminal close accepting residual non-blocking findings |
| Normal early convergence | Existing `CONVERGED|DRY`; the reduced-assurance feature is not used |
| Unresolved significant defects | Profile-blocking severities and architecture escalation cannot pass on user approval |
| Canonical audit | `.sage/fast_cycle.jsonl` plus the existing `.sage/loop_audit.jsonl` |
| Obsidian | Derived dashboards when configured; failure is WARN |
| Phases 05/06 | Loop run plus `REDUCED_BY_USER_AUTHORIZATION` and structured residual findings |
| A and authority | Split from the current Fast fix; tree-aware validation required before protected authority |
