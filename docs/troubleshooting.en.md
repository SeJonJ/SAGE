<!-- sage-doc-source: troubleshooting.md sha256:a9190228134cf666946e3f3b334bc75f83ee746325b75ed5bca8dea7ef31f259 -->
# SAGE Troubleshooting

[한국어](troubleshooting.md) | [Documentation index](README.en.md)

## `sage: command not found`

```bash
pipx install "sage-harness[schema]"
pipx ensurepath
```

Open a new terminal and check `sage --version`. If you installed with pip's user mode, run
`python3 -m sage --help`, or `py -m sage --help` on Windows.

## Hooks do not run on Windows

Installed hooks use `sage-hook.exe`, not bash.

```powershell
where sage-hook
sage doctor
```

If the entrypoint is missing, reinstall `sage-harness` into the same Python environment. Set
`SAGE_BASH` to an absolute Git Bash path only when running optional `.sh` developer regressions.
SAGE does not select the WSL launcher implicitly.

## Missing `--host`, `--kind`, or `--skill-scope`

```bash
sage install --host claude
sage install --host codex --skill-scope project-local
sage generate --kind hook --write
```

Select the `sage install` host, Codex skill scope, and `sage generate` kind explicitly.

## `sage validate` reports STALE

STALE means that a spec, core, adapter, or runtime hash differs from its manifest stamp.

```bash
sage generate --kind hook --write
sage validate
```

Immediately after installation, CORE hooks may not yet be stamped, so run generate once. Do not
edit files directly just to force their hashes to match.

## The write guard blocks an edit

Generated `.claude/` and `.codex/` assets, `.mcp.json`, and CORE framework documents are not direct
edit targets.

```bash
sage absorb --kind agent --id my-agent
sage generate --kind agent --write
```

Use `sage-asset-override` for supported CORE asset customization. Put project policy in
`sage/project-profile.yaml` or project-owned governance documents.

## A session risk declaration was captured by mistake and blocks edits

When the gate demands a higher risk level than Phase 00 and that level came from **this session's
declaration**, do not raise Phase 00 — that records a higher risk than the work actually carries.
Clear the declaration instead.

```
risk 선언 취소
```

Send that as a prompt and the session declaration is deleted; later decisions use only path and
content classification. The block message states where the risk level came from, so the guidance
tells you which case you are in.

A declaration is captured only from a plain statement naming a single level, and SAGE tells you when
a prompt was not captured. An unused declaration expires after two days.

## Every document exists but the gate reports missing PDCA phases

When you edit a phase document the gate reads the cycle from its filename. Source edits have no such
anchor, so the gate infers the cycle from the **last segment of the git branch name**. That is right
when each cycle gets its own branch and permanently wrong when one branch carries many cycles — every
governed edit is blocked as "phase documents missing" while all of them exist.

Declare the cycle instead of renaming the branch.

```bash
sage cycle set <phase-document-basename>   # when Phase 00 already exists
sage cycle set <new-stem> --create --risk L2  # when Phase 00 does not exist
sage cycle show                            # what is declared, and where it was read
```

This does not weaken the gate. It supplies the cycle identity the gate could not infer, and every
phase, review, and acceptance requirement still applies to that stem. The first use in a session is
recorded in `.sage/override.jsonl`.

`sage cycle set` also prints the absolute path it wrote, whether git ignores it, and whether the
compiled profile the gate reads is present. If a declaration seems to have no effect, read that
output first.
On a collision with an existing Phase 00, it overwrites nothing and prints every collision plus
three available stem candidates. Use root-relative `--path DIR` only when a custom Phase 00 glob
does not provide an unambiguous directory.

`--create` creates only Phase 00. If the profile requires Phases 01-03, governed source edits remain
blocked until those documents exist. For an urgent, waivable phase gap, grant a short override such
as `sage override --reason "hotfix" --ttl 1h`. Phase 00 risk declaration and reconciliation blocks
are never waivable by override.

The `sage-cycle` umbrella does not run `set` or `clear` itself. `sage-plan` declares
after stem validation, and `sage-team` reconciles with `show` on resume and clears only
after write-back, retro, snapshots, and closing gates. `BLOCKED` or `FAIL` retains the
declaration for resume.
`set B` changes only the pointer, so cycle A's documents, evidence, and audits remain intact;
`set A` restores A's evaluation.

## Blocked by Done Criteria or a stale Phase 05 approval

Repair only the exact-stem Phase 00 first. Restore exactly one `## 5. Done Criteria`, a positive
`Done-Criteria-Revision`, and valid `[ ]`, `[x]`, or reasoned `[~]` items. If criterion text or scope
changed, increment the revision, record Changed-At, Reason, Affected-Phases, and Summary, then rerun
affected phases in order. Do not reuse the previous Phase 05 approval. Run a new review loop with
`--cycle-stem`, then record its `Loop-Run` and the APPROVED close's `Phase00-Hash` in Phase 05.
Write Phase 00 and later phases separately because one mixed write cannot prove post-write evidence.

## The cycle is finished but new work is blocked as an already-completed cycle

A declaration outlives the shell. If the finished cycle's declaration is still in place, new work
binds to it, and the gate blocks that.

```bash
sage cycle clear                     # release the file declaration
unset SAGE_CYCLE_STEM                # if you declared it through the environment
```

The block message states whether the binding was read as **declared** or **inferred from the
branch**, so the guidance tells you which one to clear.

## `sage install` fails with "SAGE source resources changed"

If the SAGE engine sources change while an install is running, the result would be a half-mixed
tree, so install stops itself and rolls back. The check is working as designed; the usual cause is
**a test or review tool editing repository files and reverting them**.

The message names the logical paths that differ.

```
❌ sage install apply 실패: InstallDriftError: SAGE source resources changed during install
   — 변경 2건: hooks/runtime/messages.py, engine/commands/install.py
```

Use the paths to identify what touched them, let that work finish, and install again. Do **not** run
mutation tests or an independent review at the same time as the full suite — both change repository
sources temporarily, so the install tests fail legitimately.

## `sage fast-cycle open` is rejected

```
⛔ [sage fast-cycle] open rejected: pdca.fast_cycle.enabled=true is required
⛔ [sage fast-cycle] open rejected: lens-count must be at least 2 for L2
⛔ [sage fast-cycle] open rejected: lens-count exceeds configured candidates (3)
```

Fast Cycle requires every minimum the shared policy sets to be satisfied before it starts. The
`enabled=true` error means `pdca.fast_cycle.enabled` is off in `sage/project-profile.yaml`. The
`lens-count` errors mean `--lens-count` is below that risk level's `minimum_lenses` or above the
number of configured `lenses` candidates. An empty or malformed `--reason` is rejected the same way.

```bash
sage fast-cycle open --stem <stem> --level L2 --lens-count 2 --reason "short reason"
```

`reason_required` cannot be relaxed from the profile, so filling in a valid value and retrying is
the only path — there is no bypass.

## `sage fast-cycle convert` is rejected

```
⛔ [sage fast-cycle] convert failed: pdca.fast_cycle.standard_transition.enabled=true is required
⛔ [sage fast-cycle] convert failed: --confirm must be exactly FAST-CONVERTED
⛔ [sage fast-cycle] convert failed: Fast audit integrity failed: ...
```

Conversion opens only when both opt-ins are on (`fast_cycle.enabled` and
`fast_cycle.standard_transition.enabled`). If the confirmation token, the reason, or the approver is
missing, the command exits **without writing anything** — neither audit nor document changes. An
integrity error means existing records in `.sage/fast_cycle.jsonl` are damaged; a new run is never
stacked on a damaged audit.

```bash
sage fast-cycle convert --stem <stem> --current-phase 04 --level L2 \
  --lens-count 2 --reason "short reason" --confirmed-by <approver> --confirm FAST-CONVERTED
```

If source edits are still blocked with `block_phase_incomplete` after converting, the phases that
existed at conversion time do not cover `pre_implementation_required` for that risk. A conversion
waives **only what it can show**, so converting at Phase 00 still requires 01–03 to be authored. A
converted run legitimately carries no `Fast-Audit-Run` line in its document; do not add one by hand.

## Early completion (`USER_AUTHORIZED_EARLY`) is rejected

```
[sage review-loop] early completion refused: pdca.review_loop.early_completion.enabled=true is required
[sage review-loop] --survived-by-severity invalid: severity total 2 does not equal survived 3
```

Early completion requires `pdca.review_loop.early_completion.enabled: true` and is meaningful only
while `sage review-loop next` still recommends `CONTINUE`; once it reports `STOP` or `CONVERGED`,
close normally. A receipt-total error means `--survived-by-severity` does not sum to that round's
`--survived` — the check exists to stop a `P0=0`-only receipt from hiding a blocking finding, so
there is no way around it.

Some things an authorization never carries past the engine gate: zero rounds, unresolved findings
at a `severity_block` severity, architecture escalation, unresolved Done Criteria, acceptance
`FAIL`, and audit damage. If one of those is blocking, it has to be genuinely resolved.

A failed required build, test, or lint check also must not be closed early, but those results live
only in Phase 03 prose and are not machine-readable by the engine. The agent must disclose that
failure to the user and refuse to close; this is an agent duty, not an engine-enforced receipt.

## Phase 05 is blocked over reduced-assurance markers

```
조기 완료로 닫히지 않은 run 인데 보증 저하를 자칭함: [...]
Review-Assurance 선언은 fence 밖에 정확히 1개여야 함(found 0)
```

The test is the **value**, not the presence of a marker. Writing either `Review-Assurance:
REDUCED_BY_USER_AUTHORIZATION` or `Review-Close-Reason: USER_AUTHORIZED_EARLY` claims reduced
assurance. Once claimed — or once the audit closed early — record all four markers
(`Review-Assurance`, `Review-Close-Reason`, `Review-Rounds`, `Residual-Findings`) with values
matching the audit record. If the loop converged normally, do not write those two values. A neutral
line such as `Review-Rounds: 3` on a converged run is not blocked. The `(configured max: <max>)`
part of `Review-Rounds` must match the audit too; a project with no ceiling configured writes
`unbounded`, the same word the audit records.

If the markers are written correctly but still report `found 0`, check whether they ended up inside
a fenced code block — lines inside a fence are not counted.

## An early completion is refused with `unresolved acceptance`

The selected Phase 04 still carries an acceptance `FAIL`, or a required `NOT TESTED` with no active
exact waiver. Early completion accepts residual review findings, not unverified requirements, so
this state does not pass on a user confirmation either. Fill the Phase 04 evidence with `PASS`, or
on an L3 cycle grant an explicit waiver for that ID with `sage acceptance-waiver grant`, then run
the close again. The judgment uses the same policy as the Phase 06 report gate, so letting it
through here would only move the block to 06 for the same reason.

## `sage cycle clear` is blocked by an active Fast run

Clearing the declaration while a Fast audit remains open could bind later evidence to another stem,
so SAGE fails closed.

```bash
sage fast-cycle show
# Normal completion
sage fast-cycle close --run-id <fc-id>
sage cycle clear
# Or intentional abandonment
sage fast-cycle abort --run-id <fc-id> --reason "reason for stopping"
sage cycle clear
```

When `close` is rejected, check whether Phase 00 changed after the latest Fast review and whether
Phase 05/06 bind the same `Fast-Run`, `Loop-Run`, and `Final Status: APPROVED`. If the audit text is
damaged, do not delete it or overwrite it with a new run; inspect recoverable Git history together
with `.sage/fast_cycle.jsonl`.

## The write guard blocks an edit to the declaration file

`.sage/cycle.json` is where the gate reads which cycle an edit belongs to. Writing it directly can
point the gate at a completed cycle and switch it off, so the guard blocks that. Use
`sage cycle set|show|clear` instead — the CLI does not go through edit tools and is never guarded.

A `[사이클 선언 무시됨]` notice means the file exists but could not be read. The gate proceeds as if
no declaration were present; rewrite it with `sage cycle set <stem>` or remove it with
`sage cycle clear`.

## Missing arguments for `sage absorb` or `sage override`

```bash
sage absorb --kind agent --id my-agent
sage override --reason "hotfix" --ttl 30m
```

An override requires a reason and expiration time and is recorded in the audit log. Some integrity
and risk-contract blocks cannot be bypassed with a generic override.

## `sage override` rejects the permission-cache location

```
[sage override] The permission cache resolves inside the repository (...)
[sage override] The permission cache location cannot be determined (not an absolute path: ...)
```

Active bypass **permissions** live in a machine-local state directory outside the repository. Keeping
them inside would let them be committed, which activates the bypass in someone else's clone. When the
location cannot be trusted, no permission is created.

- Point `SAGE_STATE_HOME`, `XDG_STATE_HOME`, or `HOME` outside the repository.
- In a container without `HOME`, set `SAGE_STATE_HOME` to an absolute path.
- `sage override --list` prints the current location. Deleting `.sage/tmp/` does not reset it.

The message about an undeterminable repository boundary means a `.git` entry exists but cannot be
interpreted, such as a corrupted pointer file or a missing gitdir. Issuing without a confirmed
repository identity would mix permissions across repositories, so it is refused. Repair the `.git`
state and retry. See [Artifacts](ARTIFACTS.md) section 1.1 for the full location rules.

## Cross-model review is BLOCKED

Use `sage doctor` to verify the opposite runtime CLI and model configuration. Under a required
policy, inability to reach the peer runtime is not downgraded to same-runtime success.

## Schema validation reports WARN

```bash
pipx inject sage-harness jsonschema
# or
pipx install --force "sage-harness[schema]"
```

Without `jsonschema`, hash checks and built-in semantic checks continue, but JSON Schema validation
is skipped with a warning.

## Output stays Korean even with `--lang en`

The global `--lang` only works **before the subcommand**. `sage doctor --lang en` is not a
supported form.

```bash
sage --lang en doctor        # this is the right position
```

Hook output takes no `--lang` at all. To get English hook messages, configure the target
project's `sage/project-profile.local.yaml`.

```yaml
interface:
  language: en
```

If it is still Korean, check three things: that the local profile sits in **the project root the
hook is inspecting**, that the value is `ko` or `en` (anything else falls back to `ko` and
`sage validate` reports it as a configuration failure), and whether the remaining Korean is
**quoted source text** — a fragment read from a file and handed back as evidence is never
translated. That is evidence, not a defect.

Phase 00–06 documents being written in Korean is unrelated to this setting. Document language is
fixed per cycle with `Document-Language:`, and an active cycle does not change with `--lang`.
