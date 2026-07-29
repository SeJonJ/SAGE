<!-- sage-doc-source: troubleshooting.md sha256:b167241b94dc183005aabef8346c6e5a7ef401baa019ddbd372f3a4b0716c03f -->
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
