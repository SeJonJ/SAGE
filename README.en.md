<!-- sage-doc-source: README.md sha256:caecd4aa4e31ce1193a7d8be2ed6562ee3b3a56e556220a650eb5c937e6cd2a3 -->
# SAGE - System for Agentic Governance & Engineering

[한국어](README.md)

[![CI](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml/badge.svg)](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sage-harness)](https://pypi.org/project/sage-harness/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/sage-harness/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**A tool that automatically checks and blocks AI coding agents — Claude Code or Codex — from editing
risky code without a plan, or reporting "done" without a review.**

## Why you need this

Telling an agent "plan first, be careful with risky files, always get a review" every time is easy
to forget or skip. SAGE turns those reminders into automatic checks (hooks) a human need not repeat.

- **Edits a risky file without a plan?** SAGE blocks it until a plan document exists.
- **Reports "done" without a review?** SAGE checks for an approved review and blocks without one.
- **The AI edits an auto-generated config file directly?** SAGE redirects it to the source
  definition (a direct edit is overwritten on the next generation anyway).
- **One model reviewing its own code?** SAGE hands it to the opposite model (Claude ↔ Codex).
- **Cross-review and review loops raise token usage as much as you use them.**

These checks are not the AI's "judgment" — they are code that decides **deterministically**. The
same situation always produces the same result, so nobody has to re-explain the rules.

## Quickstart

SAGE requires Python 3.10+ and Git.

First, install SAGE itself.

```bash
pipx install "sage-harness[schema]"
cd your-project
```

Then follow **only the path that matches the AI tool you use** — you do not need to run both.

### If you use Codex

```bash
sage install --host codex --skill-scope project-local
```

Once installed, run `$sage-init` **inside Codex** to fill in this project's configuration (profile)
through conversation. Then come back to the terminal to finish:

```bash
sage generate --kind hook --write --target codex
sage validate --kind all
```

### If you use Claude Code

```bash
sage install --host claude
```

Once installed, run `/sage-init` **inside Claude Code** to fill in this project's configuration
(profile) through conversation. Then come back to the terminal to finish:

```bash
sage generate --kind hook --write --target claude
sage validate --kind all
```

When joining a repository that already has a shared profile, run `sage-init-local` instead of
`sage-init`. See the [English quickstart](docs/quickstart.en.md) for the full sequence and
[troubleshooting](docs/troubleshooting.en.md) for installation failures.

## What SAGE 1.0 provides

| Goal | Command or feature |
|---|---|
| Check whether SAGE is ready in this project | `sage status` |
| Explain why a path is blocked | `sage explain --path PATH` |
| Inspect review, override, and waiver audit records | `sage audit show` |
| Verify definitions and generated assets | `sage validate --kind all` |
| Move safely between SAGE versions | `sage upgrade --check` → `sage upgrade --apply` |
| Remove installed project and global assets | `sage uninstall --check` → `sage uninstall --yes` |
| Bind planning, implementation, independent review, and evidence | Standard PDCA, Fast Cycle, Done Criteria |

`status`, `explain`, `audit show`, `upgrade --check`, and `uninstall --check` are read-only. See the
[CLI reference](docs/cli-reference.en.md) for `--json`, all options, and exit codes.

## Supported environments

The general CLI and hooks run on Python 3.10+ with no bash on Windows; only `verify-changes.sh` and
custom `.sh` tests need Git Bash.

The **automatic removal scope** is narrower. SAGE stops before mutation in unverified environments.

| Environment | General CLI and hooks | `sage uninstall` |
|---|:---:|---|
| Linux | Supported | Automatic removal supported |
| macOS | Supported | Automatic removal supported |
| Windows 11 desktop workstation, x64, 64-bit Python, local NTFS | Supported | Automatic removal supported |
| Windows 10 desktop | Supported | Automatic removal deferred; verified plan and manual cleanup list provided |
| Windows Server and domain controllers | Outside formal support (not directly verified) | No automatic removal; plan-based manual list provided |
| 32-bit Python, native ARM64 Python, non-NTFS, network, or UNC paths | Environment-specific limits | No automatic removal; inspect the plan with `--check` |

NTFS is the default filesystem on typical local Windows disks. **Being able to run and being
formally supported are different things** — the general CLI may work outside the supported scope,
but that behaviour is neither promised nor directly verified. Automatic removal on Windows 11
desktop was **verified by actually running it on that SKU** — no Windows Server result was
substituted for it. For the two refusal screens see the [CLI reference](docs/cli-reference.en.md)
and [troubleshooting](docs/troubleshooting.en.md).

On Windows, `sage-hook.exe` runs hooks, so Git Bash and WSL are not required:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
pipx install "sage-harness[schema]"
sage doctor
```

Set `SAGE_BASH` to the Git Bash path when running `.sh` tests on Windows.

## Upgrade to 1.0

When moving from 0.9.x to 1.0, upgrade the package, then inspect and apply the project transition.

```bash
pipx upgrade sage-harness
sage upgrade --check
sage upgrade --apply
sage status
```

`--check` only shows the plan. `--apply` is transactional, rolls back on failure, never downgrades.

## Remove SAGE safely

Inspect the project-specific plan before removing assets. Remove the package itself separately.

```bash
sage uninstall --check
sage uninstall --yes
pipx uninstall sage-harness
```

Even where automatic removal is unsupported, both commands list actual paths as `STRIP` (remove only
SAGE content from a shared file), `DELETE`, `PRESERVE`, and `BLOCK`. Targets vary by host, scope,
and `CODEX_HOME`; never delete `PRESERVE` or `BLOCK` — see
[troubleshooting](docs/troubleshooting.en.md).

## How it works

SAGE separates two kinds of files — **definitions that a human edits**, and the **runtime files an
AI actually reads**, generated automatically from those definitions.

```
definitions (human-edited)       sage generate       runtime files (AI-read)
hook / agent / skill spec     <------------------>   .claude / .codex
             |                                                  |
             +---- check --- sage validate ---------------------+
             +---- direct edit attempt ----> back to the definition
```

Editing a definition and running `sage generate` automatically refreshes the runtime files the AI
reads. If the two drift apart — a direct edit, or a forgotten regeneration — `sage validate` catches
it. If an AI edits a runtime file directly, SAGE blocks it and points to the definition.

Agents own judgment — writing code, reviewing it. SAGE owns deterministic boundaries — integrity,
phase, approval. See [Architecture](docs/ARCHITECTURE.en.md) for the trust boundary and the
fail-open/fail-closed policy.

## Development workflow

- **PDCA** binds planning → implementation → independent review → completion reporting.
- **completion criteria (Done Criteria)** track evidence and revalidate affected phases on change.
- **Profile** separates team policy from machine-local settings.
- **Fast Cycle** reduces document count only when enabled and records the transition in the audit.
- **Early completion** logs explicit user acceptance of residual risk, apart from normal approval.

## Documentation

| Need | Document |
|---|---|
| Install and run SAGE | [English quickstart](docs/quickstart.en.md) |
| Commands and options | [CLI reference](docs/cli-reference.en.md) |
| Configure a profile | [Profile reference](docs/profile-reference.en.md) |
| Resolve errors | [Troubleshooting](docs/troubleshooting.en.md) |
| Architecture and trust | [Architecture](docs/ARCHITECTURE.en.md) |
| Output locations and ownership | [Artifacts](docs/ARTIFACTS.en.md) |
| Browse all documentation | [English docs index](docs/README.en.md) |

## Who it is for

SAGE is for teams changing production repositories with Claude Code or Codex that need enforceable,
reviewable policy rather than prompt-only guidance — and excessive for prompt snippets alone.

## License

Apache License 2.0. Distributions must include [LICENSE](LICENSE) and [NOTICE](NOTICE). Releases
before `v0.9.71` used CC BY-NC-SA 4.0.
