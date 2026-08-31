<!-- sage-doc-source: cli-reference.md sha256:0c4ce2eee54b3c16b7ad4326ae90fa57e5f042f4db74b104d397cb06f51f1f00 -->
# SAGE CLI Reference

[한국어](cli-reference.md) | [Documentation index](README.en.md) | Run `sage <command> --help` for the exact options available in your environment

## Installation and generation

| Command | Purpose |
|---|---|
| `sage install --host claude` | Install the Claude Code framework, CORE hooks, agents, and skills |
| `sage install --host codex --skill-scope project-local` | Install Codex assets and repository-local CORE skills |
| `sage install --host codex --skill-scope global` | Install Codex assets and user-global CORE skills |
| `sage generate --kind hook --write --target HOST` | Generate host registration, adapters, and manifest stamps from hook specs |
| `sage generate --kind mcp --write --target HOST` | Generate host configuration from MCP specs |
| `sage generate --kind {agent,skill} --write` | Reverse-extract and reconcile specs and claims from both host renders |
| `sage generate --kind roster` | Generate implementer specs from `profile.components` |
| `sage generate --kind roster --from-existing ID` | Promote an existing implementer's composed render to a new component identity |

Without `--write`, `generate` only previews changes. For hooks and MCPs, select the host with
`--target claude|codex|both`. Agents and skills always require both host renders because they use a
render-first flow, so `--target` cannot narrow their scope.

For a new project hook, first author only `docs/sage_harness/hooks/<id>.md` and
`scripts/sage_harness/hooks/<id>_core.py`, then register it with:

```bash
sage generate --kind hook --id <id> --write --target both
```

The first registration validates both host bindings and `CONTRACT_VERSION`, then writes the
manifest, canonical adapters, host settings, and shims in one transaction. A new ID cannot be
registered for only one host.

Every registered project hook requires a current `sage/project-profile.json`, even when its core
does not inspect the profile. Missing or divergent YAML/compiled profiles block edits with exit 2;
run `sage generate --kind hook --write --target both` after registration or profile changes.

For `decide(event, profile, snapshot)`, `event` provides `hook_id`, `hook_event_name`
(`PreToolUse`), `runtime`, `session_id`, and `changes`. `changes` is a possibly empty list of
`{path, op}` objects extracted from the host input. `op` is `write` on claude and `add`/`update`/`move`
on codex, where `move` carries only the `apply_patch` move destination — the origin path is not a
place where a document materializes, so it is excluded. Deletions are also excluded. Globs returned by optional `plan_reads()` read only regular files inside the project
root. `snapshot` always has the shape `{glob_results, files}` whether or not `plan_reads()` is
declared — both are empty when it is not. `plan_reads()` must return exactly `{'globs': [...]}`;
a missing `globs` key is a contract failure.
Directories matched by recursive globs are skipped; root escapes including symlink ancestors,
symlink leaf matches, and other non-regular paths are contract failures.

### `sage uninstall [--global|--all]`

Reverses what SAGE installed. **It never removes the package itself** — uninstall the CLI separately
with `pipx uninstall sage-harness`.

| Scope | Target |
|---|---|
| `sage uninstall [--dest PATH]` | SAGE assets in the current (or given) project |
| `sage uninstall --global` | Codex global SAGE CORE skills under `$CODEX_HOME/skills/` |
| `sage uninstall --all [--dest PATH]` | Both, as one transaction |

The order is the contract: print an immutable plan (baseline captured) → confirm or `--yes` →
ordered lock → compare the fingerprint → re-check the boundary → back up → execute → verify →
commit → cleanup → unlock. `--check` stops after the first step and changes nothing — it does not
even take the lock. Cancelling ends at `CANCELLED(0)` without a single byte changed.

**The baseline is from the moment the plan was shown to you.** If you edit a target file while the
confirmation prompt is open, nothing is removed and the run stops with `BLOCKED(2)` — the state you
agreed to and the disk no longer agree. Directories are compared down to the files inside them.

If another SAGE command is working on the same location, the run is blocked. It takes the **same
lock** as `install` and `generate`, so one side can never place files while the other removes them.
The lock is released when the process exits, so there is no lock file for you to clean up.

A cleanup failure is **still a success.** The requested removal already finished; we only report the
temporary backup paths we could not clear.

**Ownership is never assumed.** Only SAGE-owned directories and assets the manifest recorded are
removed. `AGENTS.md`, `CLAUDE.md`, `CODEX.md`, and `AGENT_GUIDE.md` cannot be proven to have been
absent before install, so they are **always preserved** and reported with their paths and reasons. A
global copy that differs from the project render was edited, so it is left alone. There is no
`--force` and no ownership override.

Shared files lose only their SAGE parts: the `.gitignore` managed blocks and the SAGE hook
registrations in host JSON. If the markers are not a well-formed pair, or the JSON cannot be read,
the **whole file is preserved** — repairing damage on a guess makes user content disappear quietly.

A host settings file resolves to one of three registration states: **present**, **absent**, or
**unknown**. Broken syntax, non-UTF-8 bytes, and a read that is denied are *unknown*, never absent —
folding what could not be read into "not there" turns absence into a pass, and a pass leads to
deletion. Even an unknown file is reported as preserved when the manifest's `installed_hosts` proves
SAGE installed into that host.

**While an untouched host settings file remains, the install record (`docs/sage_harness`) is kept
with it.** Discarding the receipt first would leave the next run with no way to prove why that file
is there. Every run in that state is a `PARTIAL(1)` that changes nothing and repeats the same paths.
Only once the user repairs the file — so the SAGE registration can actually be removed — is the
install record deleted, as the last asset. Removing the CLI package while residue remains makes the
host invoke a missing executable, so that ordering is called out too.

Damage is reported as **coordinates**, not as one flattened sentence: the JSON pointer with expected
and actual types, the line and column of a syntax error, the byte offset of a UTF-8 error, and the
errno name of a failed read. Configuration values, command strings, surrounding JSON, and raw OS
exception text are never included — that content belongs to the user and flows into logs and CI
output. A JSON key that is not identifier-shaped is redacted from the pointer: losing the coordinate
costs less than leaking the value.

The default (project) scope **neither reads nor writes** `$CODEX_HOME`. It therefore makes no claim
about what remains globally; it states that the global scope was not inspected and points at `--all`.

| Status | exit | Meaning |
|---|---:|---|
| `COMPLETE` | 0 | Everything planned was removed, nothing needs manual review |
| `PARTIAL` | 1 | Safe deletions committed, preserved paths remain |
| `BLOCKED` | 2 | No safe plan could be made, or a rollback was attempted after failure |
| `CANCELLED` | 0 | The user cancelled before any mutation |

`PARTIAL(1)` is **not a failure**. Preserving the top-level shared documents is the ordinary outcome
and lands here. If automation needs to read that distinction, use `--json` — there is deliberately no
`--allow-partial` style flag that changes exit codes. Returning `0` would make "only part of it was
removed" indistinguishable from success, and that distinction is the point of this command. `--json`
Host settings are read as standard JSON only. A duplicate key within one object, or `NaN`/`Infinity`,
is treated as damage — reading leniently would mean the document we read differs from the one the host
reads, and for a removal command that difference becomes "what we said we removed is not what we
removed".

Hook handlers have **a different contract per kind**. The `type` is resolved first, then `command`
requires `command`, `http` requires `url`, `mcp_tool` requires `server` and `tool`, and `prompt` and
`agent` require `prompt`.

**Which kinds an event accepts also differs**, and we follow the host's published contract: some
events accept all five kinds, some accept everything except `prompt` and `agent`, and `SessionStart`
and `Setup` accept only `command` and `mcp_tool`. A handler an event does not accept makes the
document one we do not understand, so the file is preserved rather than rewritten even when a SAGE
registration is visible. For a host whose contract table we carry (currently Claude), an
event missing from that table is likewise not assumed to allow everything — saying we do not know is
better than guessing. Codex does not share Claude's table; it is tracked as a separate contract and is
not restricted by kind until its own table is carried. SAGE ownership comparison and removal apply **only to `command` handlers**,
so a normal `prompt`, `agent`, `http`, or `mcp_tool` hook sitting alongside ours is not reported as
damage and stays untouched. Another kind that happens to carry a `command` property equal to ours is
still not ours. An unknown kind, or a missing field required by its kind, preserves the file rather
than rewriting it.

Global assets come in two families (the CORE id name and the `<prefix>-<aid>` render), so a given
configuration can make both point at **the same path**. When that happens neither one wins: the whole
plan ends as `BLOCKED(2)` with `uninstall.action_conflict`. Two pieces of evidence reaching different
conclusions about one file means we do not know what that file is, and we do not pick an irreversible
deletion from a state of not knowing.

Strings the user wrote — a damaged manifest's keys, a host name — are never carried into diagnostics
verbatim. Identifier-shaped names pass through; anything else is redacted and its position is given as
an `index` instead.

A manifest asset key must be exactly `<kind>s/<id>`. That value is appended to the global skill path
as **a path fragment**, so a single key like `skills/../../../x` would make the plan point outside the
project.

`--json` consumes the same plan as the human-readable screen, so the two can never disagree, and it is
byte-identical in either locale. Executing with `--json` requires `--yes`: the confirmation prompt and
JSON are never mixed into one stream.

Path display goes through **one function** shared by the screen and `--json`. Project assets appear
relative to the repository root, global assets as `$CODEX_HOME/skills/...`, and control characters or
newlines inside file names are escaped — printed raw, one list line becomes two, and a name someone
else chose gets to forge a line in our output. A path pointing outside the write root is shown only as
`<outside-project>` — that string was chosen by whatever tried to escape, not by us. That rendering
is `path`; the old `project_path` field, which appended a relative path to an absolute one, is gone. Every entry also carries the reason code
(`reason`), the structured damage facts (`detail`), and the registration state
(`registration_state`).

The install record (manifest) is first checked for **whether it can serve as ownership evidence**.
Required fields, types, `installed_hosts`, `assets` entries, `core_renders` receipts, and skill
receipts are validated **all the way down** by the **same contract** install uses, and a violation
ends the run with `BLOCKED(2)` before any confirmation. An empty receipt means "we do not know what
was placed", and deleting from a state of not knowing is deleting someone else's file.
Reading an empty manifest as normal means "the install is proven and nothing was placed", which
erases the evidence first and then reports nothing left to do. A destination that is the filesystem
root or one of its direct children (`/usr`, `/opt`, `/Users`) is likewise `BLOCKED(2)` at planning
time, with zero write targets. Even when planning hits input it cannot read, the result is a
`BLOCKED(2)` JSON envelope rather than a traceback — for any input, the outcome is one of the four
states.

`--global` + `--all`, `--check` + `--yes`, and `--global` + `--dest` are usage errors (`2`).

## Validation and diagnostics

| Command | Purpose |
|---|---|
| `sage validate` | Check hashes, staleness, regressions, and profile semantics for the default `hook` scope |
| `sage validate --kind all` | Check all hook, agent, skill, and MCP assets |
| `sage validate --check` | Run a fast consistency check without executing regression commands |
| `sage validate --schema` | Validate the manifest and profile against their JSON Schemas |
| `sage validate --strict` | Promote selected advisory checks, including bootstrap, schema, overlay, and profile drift, to failures |
| `sage status` | Read-only summary, in one to two seconds, of whether SAGE is usable in this project |
| `sage status --json` | The same result as machine-readable schema v1 JSON (locale-independent) |
| `sage explain --path PATH` | Explain a path's risk floor, matched rule, bound cycle, and missing phase documents |
| `sage audit show` | Read all six audit sources on one screen, read-only (the four shared ones by default) |
| `sage audit show --include-local` | Also read the local sources (`retro`, `feedback`) |
| `sage audit show --json` | Print the same result as machine-readable schema v1 JSON (locale-independent) |
| `sage doctor` | Diagnose Python, hook entrypoints, hosts, reviewers, profiles, and optional capabilities |
| `sage models --host HOST` | Show locally discoverable model candidates and their validation level |
| `sage asset-check --gate` | Return CI exit codes for whether an asset change can be auto-approved |

## Asset maintenance

| Command | Purpose |
|---|---|
| `sage absorb --kind K --id ID` | Convert a direct-edit diff into a candidate spec patch |
| `sage sync-overlays` | Reconcile CORE overlays and managed governance-routing blocks |
| `sage change "description"` | Show the appropriate generate or absorb path for an intended change |
| `sage feedback` | Find `sage-feedback ::` markers |
| `sage feedback --release-gate` | Block a release when blocking feedback remains unresolved |
| `sage override --reason R --ttl T` | Create a time-limited bypass for an eligible gate and record its audit trail |
| `sage acceptance-waiver {grant,list,revoke}` | Manage exact L3 acceptance waivers |
| `sage cycle set STEM` | Declare a cycle that already has Phase 00 (required on long-lived branches) |
| `sage cycle set STEM --create --risk L1\|L2\|L3 [--path DIR]` | Create one Phase 00 skeleton, then declare it (`DIR` is project-root-relative) |
| `sage cycle show` | Show the current declaration and where it was read (env or `.sage/cycle.json`) |
| `sage cycle clear` | Release the file declaration after completion; an env declaration needs `unset` |
| `sage fast-cycle open --stem S --level L2\|L3 --lens-count N --reason R` | Validate composite Phase 00 and open a Fast audit run |
| `sage fast-cycle convert --stem S --current-phase 00\|01\|02\|03\|04 --level L2\|L3 --lens-count N --reason R --confirmed-by W --confirm FAST-CONVERTED` | Convert a Standard Cycle already in progress to the Fast contract (writes no document) |
| `sage fast-cycle review --run-id F --loop-run-id L` | Bind a clean APPROVED Loop Audit with matching stem, rounds, and lens receipts |
| `sage fast-cycle close --run-id F` | Verify the latest plan hash and Phase 05/06 bindings, then close |
| `sage fast-cycle abort --run-id F --reason R` | Abort an active Fast run with an audited reason |
| `sage fast-cycle show [--run-id F] [--vault [PATH]]` | Show audit state and optionally render the Obsidian dashboard |

The `sage-cycle` umbrella does not run `set` or `clear` directly. `sage-plan` declares
the verified stem, while `sage-team` reconciles it with `show` on resume and clears it
after write-back, retro, snapshots, and closing gates. `BLOCKED` and `FAIL` retain the
declaration. Use `sage cycle show` to inspect the effective source and the shadowed file;
when the environment wins, release it with `unset SAGE_CYCLE_STEM`.

`set B` switches only the pointer and does not modify cycle A's phase documents,
evidence, or audits; `set A` restores A's evaluation. `--create` creates only Phase 00,
so write any required Phases 01-03 before governed source edits. For an urgent,
waivable phase gap, use a short TTL such as `sage override --reason R --ttl 1h`.
Phase 00 risk declaration and reconciliation blocks are never waivable by override.

`convert` additionally requires `pdca.fast_cycle.standard_transition.enabled: true`. It is the
path for a cycle already past Phase 00 to adopt the Fast contract without authoring a composite
plan. The conversion **writes no document**: existing Phases 00–04 are not deleted, moved, merged,
or rewritten, and no conversion metadata is inserted into them. The record of authority is the
single `fast_convert` entry in `.sage/fast_cycle.jsonl`, which lists the phases that existed at
conversion time. A converted run waives **only the pre-implementation phases that list can show** —
convert at Phase 00 and 01–03 are still required before source edits. Without all of `--confirm
FAST-CONVERTED`, `--reason`, and `--confirmed-by`, the command exits without writing anything. A
converted run carries no `Fast-Audit-Run` line in its document and binds by stem instead.

`show` and the dashboard label every run with a single `entry=` value, because which contract
opened the run is what later verdicts turn on.

| `entry` | Meaning | Where it comes from |
|---|---|---|
| `FAST` | A fresh Fast run opened with `open` | One composite Phase 00 is the plan of record |
| `FAST-CONVERTED` | A run that came across with `convert` | The existing Phases 00–04 stay the record; the document carries no `Fast-Audit-Run` |
| `UNKNOWN` | The opener record cannot be read | Audit damage, hand editing, or an old record. Do not use it as evidence; diagnose with `sage validate` |

`UNKNOWN` does not mean "not Fast" — it means **undecidable**. Do not push that run's evidence
through a gate; check audit integrity first.

Fast commands are available only for L2/L3 when `pdca.fast_cycle.enabled: true`. Actual risk remains
separate from `--level`, which selects the Fast review contract. `open` validates the complete input
set before writing either the plan or audit. An active Fast run blocks `sage cycle clear` and stem
switching. Close normally with `fast-cycle close` before `cycle clear`; abandon with
`fast-cycle abort` before `cycle clear`.

## Reviews and loops

| Command | Purpose |
|---|---|
| `sage review` | Start a fresh same-runtime headless reviewer |
| `sage cross-check --packet-file FILE` | Start a cross-model reviewer in the opposite runtime |
| `sage review-loop open [--cycle-stem S --lenses CSV]` | Start a review loop; Fast binds exact stem and lenses |
| `sage review-loop round [... --lens-receipts CSV] [--survived-by-severity P0=N,P1=N,P2=N,P3=N]` | Record findings, rebuttals, fixes, Fast lens receipts, and the per-severity residual receipt |
| `sage review-loop next` | Produce a deterministic continue-or-stop recommendation |
| `sage review-loop close` | Close the loop with `--result APPROVED|BLOCKED` |
| `sage review-loop close --reason USER_AUTHORIZED_EARLY --authorization-reason R --confirmed-by W --confirm USER_AUTHORIZED_EARLY` | Close before convergence on an explicit user authorization (reduced-assurance markers required) |
| `sage retro --feature STEM` | Generate a completed-cycle retrospective note and distillation input |
| `sage retro --check NOTE` | Verify that a retrospective note is not an untouched template |

Early completion requires `pdca.review_loop.early_completion.enabled: true` and is meaningful only
while `sage review-loop next` still recommends `CONTINUE`. It is not an iteration waiver but an
explicit user acceptance of residual non-blocking risk, so an authorization does not carry any of
these past the gate: zero completed rounds or fewer than `minimum_completed_rounds`, unresolved
findings at a `severity_block` severity, architecture escalation or `BLOCKED_ARCH`, unresolved
Done Criteria or a missing revision rerun, acceptance `FAIL`, a required
`NOT TESTED` without an active waiver, audit damage or chain/sequence failure, and a binding
mismatch.

The verdict token stays `APPROVED` for compatibility, so the Phase 05 document records how it was
reached. What decides a block is **the value, not the presence** of a marker. Writing either
`Review-Assurance: REDUCED_BY_USER_AUTHORIZATION` or `Review-Close-Reason: USER_AUTHORIZED_EARLY`
counts as claiming reduced assurance. Once claimed — or once the audit itself closed early — all
four markers (`Review-Assurance`, `Review-Close-Reason`, `Review-Rounds`, `Residual-Findings`) must
appear exactly once each outside fenced code blocks, with values matching the audit record. A
normally closed run that claims reduced assurance is blocked, and so is an early-closed run that
omits the markers — the server authority applies the same rule to that second case. A single
neutral line such as `Review-Rounds: 3` is not blocked. The `(configured max: <max>)` part of
`Review-Rounds` is matched too — it is the denominator that says how much review was skipped, so
inflating or lowering it changes how the document reads. A project with no ceiling configured
writes `unbounded`, the same word the audit records. The `--survived-by-severity` total must equal
`--survived` exactly — that is what stops a `P0=0`-only receipt from hiding a blocking finding.

What an early completion accepts is residual review findings, not unverified requirements. If the
selected Phase 04 still carries an acceptance `FAIL`, or a required `NOT TESTED` without an active
exact waiver, the early close is refused and nothing is appended. That judgment uses **the same
policy and the same parser** as the Phase 06 report gate, so a project that does not use
`verification.acceptance` gains no new gate here. Build/test/lint results, though, live only in
Phase 03 prose where no gate can read them: an early close over a failing required check is a
state the engine cannot stop, so a person has to.

## Knowledge and context

| Command | Purpose |
|---|---|
| `sage knowledge scan` | Record pre-development Obsidian vault search results in `.sage/knowledge_scan.md` |
| `sage knowledge write-back --append-log` | Write completed knowledge to a vault note and `wiki/log.md` |
| `sage context snapshot --cycle-stem STEM --phase ID` | Save a packet binding the completed phase to profile, manifest, and document hashes |
| `sage context restore --snapshot PATH` | Verify a snapshot against current sources and generate a resume briefing |

## CI authority

| Command | Purpose |
|---|---|
| `sage authority inspect` | Inspect base/head changes and their highest risk |
| `sage authority attest` | Generate an attestation for exact PDCA evidence |
| `sage authority gate` | Bind the attestation to current changes and evaluate it in protected CI |

## Interface language

The global `--lang` goes **before the subcommand**. Put it anywhere else and the command
fails — `sage doctor --lang en` is not a supported form.

```text
sage [--lang {ko,en}] <command> [command options]
```

```bash
sage --lang en doctor        # applies to this invocation only
```

To avoid repeating it, set it in `sage/project-profile.local.yaml`, which Git ignores.

```yaml
interface:
  language: en      # absent means ko
```

Resolution order is `--lang` → local profile → `ko`. Hooks take no `--lang`, so they follow
the local profile and the default only. This setting never appears in the shared profile,
`project-profile.json`, a manifest, or the profile hash — a language preference is a property
of the person at the keyboard, not of the project's governance. **Language never changes a
verdict**: for the same input, `ko` and `en` produce the same status, exit code, and
`message_key`; only the human-readable sentence differs.

The language Phase 00–06 documents are *written* in is a **separate** decision, fixed once per
cycle with `Document-Language:`. Full rules live in
`templates/core/framework/docs/agent/language-policy.md`.

## Which command answers which question

Two commands never answer the same question. Each owns exactly one.

| Question | Command |
|---|---|
| Can I use SAGE right now? | `sage status` |
| Why does this path carry these requirements? | `sage explain --path ...` |
| What happened — who bypassed, waived, or reviewed what? | `sage audit show` |
| Are the installed tools, peer models, and optional capabilities ready? | `sage doctor` |
| Are all assets, schemas, and hashes correct? | `sage validate --kind all --check --schema` |
| Can I move safely to another SAGE version? | `sage upgrade --check` |

When `sage status` finds a problem it **links** to the detailed command above; it never produces
that command's result on its behalf. `status` and `explain` are read-only: they change no files and
no `.sage` audit records, and they never run a recovery command for you. The audit is read without
taking a lock, so these commands neither wait for nor block an in-flight Fast transition.

`status` covers seven areas — project, version, runtime API, profile, host, cycle, and the readiness
of the pre-implementation phases. When the cycle mode cannot be determined (a damaged audit, or one
that grew while being read) it reports `UNKNOWN` rather than downgrading to `STANDARD`: folding the
unknown into a normal value makes a damaged audit look like an ordinary cycle.

Neither command describes a `--root` that does not exist as if it were a healthy project. Both
refuse with exit `2`.

The status tokens are `READY`, `ATTENTION`, `BLOCKED`, and `ERROR`. `BLOCKED` means the project
state really is blocked; `ERROR` means SAGE could not do its own job. They are kept apart because
only the former gives you something to fix.

`sage explain --path` looks only at the path and the current repository state. The real write may be
stricter depending on new content, the session risk declaration, and other files changed at the same
time, so this command never guarantees that a write is allowed — which is why its result contains no
`ALLOW`.

### `sage audit show` — the difference in guarantees is not hidden

The six sources carry different integrity guarantees. The screen reports that difference on two
axes, `method` and `status`.

| Source | `method` | Meaning |
|---|---|---|
| `review`, `fast` | `strict_chain` | An append-ordered hash chain is verified |
| `acceptance` | `semantic` | Only cross-record semantic rules are checked; there is no tamper resistance |
| `retro` | `structural` | Structural parsing only |
| `override`, `feedback` | `none` | No validation at all |

A source without validation is never shown as `valid` by any path. `.sage/override.jsonl` is a
**tracking copy**; the enforcing record lives in the local state home. Divergence between the two is
not detected by this command, and that fact is shown every time you read it.

Older records without integrity fields are `legacy` and exit `0`. That means those records carry no
guarantee, not that they are damaged — treating it as failure would turn every repository with past
runs red.

The command is read-only and **neither creates nor acquires a lock.** It can therefore observe a
file mid-append, and that state is surfaced as `audit.source.concurrent_change` rather than hidden —
there is no path that reports a partial result as normal.

Absolute paths, `HOME`, and vault paths never appear in any output. Path fields and free-text fields
such as `reason` are both checked by value, replaced with `<redacted-path>`, and the replacement is
recorded as a diagnostic.

`--json` has exactly twelve top-level keys: `schema_version`, `ok`, `status`, `exit_code`,
`ordering`, `selection`, `sources`, `events`, `returned`, `omitted`, `truncated`, `diagnostics`.
`ok` is `exit_code == 0`, `returned` is the number of events actually included, `omitted` is how
many `--limit` left out, and `truncated` is the boolean `omitted > 0`. `truncated` does not double
as a count because `0` would then mean both "false" and "nothing omitted".

`diagnostics` is the single home for diagnostics, and which source a diagnostic belongs to is
carried by `evidence.source`. `sources` holds no copy — when the same fact lives in two places
there is nothing to decide which one is right once they diverge.

`--limit` defaults to 100 and its range is 1-10000. Values outside the range are rejected with
exit `2` rather than quietly clamped — `0` does not mean unlimited. Clamping would make the value
you asked for differ from the value you got, with nothing on screen saying so.

A retro note path is never printed, even when it is a valid repository-relative path. The query
answers only whether a note existed (`vault_note_present`) and whether a digest was recorded
(`digest_present`) — this is a place where the reason to hide is not "the path escaped" but the
value itself.

Each source state carries both `policy` (`shared`/`local`) and `tracking` (the actual Git state).
Folding them into one value would make "should be committed but isn't" and "personal record by
design" read the same.

A source's `present` has **three** states. Beyond present and absent, there is the state where
the tool could not read the source and therefore **could not determine** it: text prints
`present=unknown` and JSON emits `null`. Folding it into two would make a tool failure read as
"no records".

There is exactly **one** gate to the local sources: `--include-local`. Passing `--source retro`
without it exits `2` rather than returning an empty result — an empty result reads as "there are no
records in that source".

Cross-source time ordering is **display order only**, not causal or authoritative order, and the
output says so. The result is never an input to any gate.

## Common exit codes

Command-specific `--help` and output take precedence. In general, `0` means PASS, `1` means
validation FAIL, `2` means a tool or gate error or BLOCK, and `3` means STALE. For hooks, `0`
allows the operation and `2` blocks it.
