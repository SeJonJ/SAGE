<!-- sage-doc-source: troubleshooting.md sha256:a73f55cb897f710a90f6aee112f46459d483aed27ede285218c5e117850fcd0e -->
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
