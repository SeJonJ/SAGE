<!-- sage-doc-source: cli-reference.md sha256:a0564fa8e79f8476a574364ba9dd6fe5371e2a56c8d9f1b17c573f22e020f660 -->
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

## Validation and diagnostics

| Command | Purpose |
|---|---|
| `sage validate` | Check hashes, staleness, regressions, and profile semantics for the default `hook` scope |
| `sage validate --kind all` | Check all hook, agent, skill, and MCP assets |
| `sage validate --check` | Run a fast consistency check without executing regression commands |
| `sage validate --schema` | Validate the manifest and profile against their JSON Schemas |
| `sage validate --strict` | Promote selected advisory checks, including bootstrap, schema, overlay, and profile drift, to failures |
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

## Reviews and loops

| Command | Purpose |
|---|---|
| `sage review` | Start a fresh same-runtime headless reviewer |
| `sage cross-check --packet-file FILE` | Start a cross-model reviewer in the opposite runtime |
| `sage review-loop open` | Start a review loop and its audit run |
| `sage review-loop round` | Record findings, rebuttals, and fix outcomes for a round |
| `sage review-loop next` | Produce a deterministic continue-or-stop recommendation |
| `sage review-loop close` | Close the loop with `--result APPROVED|BLOCKED` |
| `sage retro --feature STEM` | Generate a completed-cycle retrospective note and distillation input |
| `sage retro --check NOTE` | Verify that a retrospective note is not an untouched template |

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

## Common exit codes

Command-specific `--help` and output take precedence. In general, `0` means PASS, `1` means
validation FAIL, `2` means a tool or gate error or BLOCK, and `3` means STALE. For hooks, `0`
allows the operation and `2` blocks it.
