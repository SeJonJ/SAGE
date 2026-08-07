<!-- sage-doc-source: troubleshooting.md sha256:4ec8276ae3ba4c95bb3a029426a155b104027c18f019eabbad5f2ebdd5d60e86 -->
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
sage cycle use <phase-document-basename>   # e.g. sage_project_profile_refresh
sage cycle show                            # what is declared, and where it was read
```

This does not weaken the gate. It supplies the cycle identity the gate could not infer, and every
phase, review, and acceptance requirement still applies to that stem. The first use in a session is
recorded in `.sage/override.jsonl`.

`sage cycle use` also prints the absolute path it wrote, whether git ignores it, and whether the
compiled profile the gate reads is present. If a declaration seems to have no effect, read that
output first.

## The cycle is finished but new work is blocked as an already-completed cycle

A declaration outlives the shell. If the finished cycle's declaration is still in place, new work
binds to it, and the gate blocks that.

```bash
sage cycle clear                     # release the file declaration
unset SAGE_CYCLE_STEM                # if you declared it through the environment
```

The block message states whether the binding was read as **declared** or **inferred from the
branch**, so the guidance tells you which one to clear.

## The write guard blocks an edit to the declaration file

`.sage/cycle.json` is where the gate reads which cycle an edit belongs to. Writing it directly can
point the gate at a completed cycle and switch it off, so the guard blocks that. Use
`sage cycle use|show|clear` instead — the CLI does not go through edit tools and is never guarded.

A `[사이클 선언 무시됨]` notice means the file exists but could not be read. The gate proceeds as if
no declaration were present; rewrite it with `sage cycle use <stem>` or remove it with
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
