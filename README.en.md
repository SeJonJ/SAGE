# SAGE - System for Agentic Governance & Engineering

[한국어](README.md)

[![CI](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml/badge.svg)](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sage-harness)](https://pypi.org/project/sage-harness/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/sage-harness/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**A deterministic governance harness for Claude Code and Codex.** SAGE manages hook/MCP specs and
agent/skill host renders as authoritative inputs, detects drift, and blocks policy violations before
tools modify the repository.

## Why SAGE

Coding agents can modify high-risk files without a plan, skip delivery phases, or edit generated
configuration directly. SAGE replaces repeated prompt reminders with a closed loop:

```
write specs -> generate runtime assets -> validate manifests -> enforce hooks -> review and retro
```

- **Spec SSOT**: track hook, agent, skill, and MCP definitions as reviewable documents.
- **Runtime gates**: enforce risk, PDCA phase, review approval, and generated-file ownership.
- **Dual host**: execute the same policy cores through Claude Code and Codex I/O contracts.
- **Cross-model review**: ask a peer runtime other than the active host to review independently.
- **Auditable delivery**: retain manifests, phase documents, review-loop rounds, and retrospectives.

## Quickstart

SAGE requires Python 3.10+ and Git. Installed hooks do not require bash, including on Windows.

```bash
pipx install "sage-harness[schema]"

cd your-project
sage install --host codex --skill-scope project-local
# First setup in Codex: $sage-init
sage generate --kind hook --write --target codex
sage validate --kind all

# For Claude Code:
# sage install --host claude
# /sage-init
# sage generate --kind hook --write --target claude
```

When joining a repository that already has a shared profile, run only `sage-init-local`. See the
[English quickstart](docs/quickstart.en.md) for the full sequence and
[troubleshooting](docs/troubleshooting.en.md) for installation failures.

## Windows

`sage-hook.exe` executes all seven installed hooks through Python, so hook execution does not
require Git Bash or WSL.

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
pipx install "sage-harness[schema]"
sage doctor
```

The standard L2/L3 delivery flow still runs `scripts/verify-changes.sh`, and custom `.sh`
regression tests also require Git Bash. Set `SAGE_BASH` explicitly for the latter on Windows.

## How It Works

```
hook / MCP specs                  sage generate       host assets
agent / skill host renders    <------------------>   .claude / .codex
          |                                               |
          +---- manifest hash <--- sage validate ---------+
          +---- blocked edit ----> sage absorb proposal
```

Agents handle code and judgment. SAGE handles deterministic integrity, phase, and approval
boundaries. See [Architecture](docs/ARCHITECTURE.en.md) for trust boundaries and fail-open/fail-closed
policy.

## Core Workflows

### Asset Management

| Kind | Authoring flow | Typical output |
|---|---|---|
| hook | spec-first: `docs/sage_harness/hooks/{id}.md` | host registration + Python runtime |
| agent | render-first: author both host renders, then extract spec/claims | `.claude/agents`, `.codex/agents` |
| skill | render-first: author both host renders, then extract spec/claims | `.claude/skills`, `.codex/skills` |
| MCP | spec-first: `docs/sage_harness/mcps/{id}.md` | `.mcp.json`, `.codex/config.toml` |

The write guard blocks direct edits to generated files. For hooks and MCPs, update the spec and
generate. For agents and skills, author both host renders and generate to reverse-extract the spec
and claims. `sage absorb` can turn an already blocked diff into a spec patch proposal.

### PDCA and Review

`sage-cycle` drives Phases 00-06. `sage-plan` owns planning Phases 00-02, `sage-team` owns delivery
Phases 03-06, and `sage-review` owns Phase 05 review loops. `sage review-loop` records rounds and
`sage retro` analyzes missed patterns after completion.

On a long-lived branch, declare the current cycle with `sage cycle set <stem>`. If
Phase 00 does not exist, use `sage cycle set <stem> --create --risk L1|L2|L3`, then
fill in the generated skeleton. The `sage-cycle` umbrella does not duplicate these
commands: `sage-plan` declares only after stem validation, and `sage-team` reconciles
with `sage cycle show` on resume and runs `sage cycle clear` only after real completion.
A `BLOCKED` or `FAIL` review retains the declaration for resume. An environment
declaration survives file clear and must be removed with `unset SAGE_CYCLE_STEM`.
`set B` changes only the `.sage/cycle.json` pointer; it does not modify cycle A's
documents, evidence, or audits. Running `set A` restores A's evaluation.

### Profiles

`sage/project-profile.yaml` contains shared team policy.
Git-ignored `sage/project-profile.local.yaml` contains machine capabilities such as host, model, and
vault access. Local configuration cannot weaken shared risk or review policy.

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

The README, documentation index, quickstart, and user references are maintained as Korean sources
with English mirrors. Source-hash markers make the documentation test fail when a Korean reference
changes and its English mirror marker has not been refreshed.

## Who It Is For

SAGE is for teams changing production repositories with Claude Code or Codex that need enforceable,
reviewable policy rather than prompt-only guidance. It may be excessive when you only need prompt
snippets or one-off code generation.

## License

Apache License 2.0. Commercial use, modification, and redistribution are allowed; distributions
must include [LICENSE](LICENSE) and [NOTICE](NOTICE). Releases before `v0.9.71` used
CC BY-NC-SA 4.0.
