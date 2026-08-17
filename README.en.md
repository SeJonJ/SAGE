<!-- sage-doc-source: README.md sha256:3ea88b593f2c396664856e38a9abc6bfde92bbfd39aa23e5e686745bcf90a8e9 -->
# SAGE - System for Agentic Governance & Engineering

[한국어](README.md)

[![CI](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml/badge.svg)](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sage-harness)](https://pypi.org/project/sage-harness/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/sage-harness/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**A tool that automatically checks and blocks AI coding agents — Claude Code or Codex — from
editing risky code without a plan, or reporting "done" without a review.**

## Why you need this

Telling an agent "plan first, be careful with risky files, always get a review" every single time
is easy to forget or skip. SAGE turns those reminders into automatic checks (hooks) instead of
something a human has to repeat.

- **Edits a risky file without a plan?** SAGE blocks it until a plan document exists.
- **Reports "done" without a review?** SAGE checks for an approved review and blocks if there is
  none.
- **The AI edits an auto-generated config file directly?** SAGE redirects it to the source
  definition instead (a direct edit would just be overwritten on the next generation anyway).
- **One model reviewing its own code?** SAGE can hand the review to the opposite model
  (Claude ↔ Codex) for an independent look.

These checks are not the AI's "judgment" — they are code that decides **deterministically**. The
same situation always produces the same result, so nobody has to re-explain the rules.

## Quickstart

SAGE requires Python 3.10+ and Git. Installed hooks do not require bash, including on Windows.

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

Once installed, run `$sage-init` **inside Codex** to fill in this project's configuration
(profile) through conversation. Then come back to the terminal to finish:

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

## How it works

SAGE separates two kinds of files — **definitions that a human edits**, and the **runtime files an
AI actually reads**, generated automatically from those definitions.

```
definitions (human-edited)        sage generate       runtime files (AI-read)
hook / agent / skill spec     <------------------>   .claude / .codex
          |                                                |
          +---- check --- sage validate ---------------------+
          +---- direct edit attempt ----> redirected to the definition
```

Editing a definition and running `sage generate` automatically refreshes the runtime files the AI
reads. If the two drift apart — a direct edit, or a forgotten regeneration — `sage validate` catches
it. If an AI tries to edit a runtime file directly, SAGE blocks it and points back to the
definition.

Agents own judgment — writing code, reviewing it. SAGE owns deterministic boundaries — integrity,
phase, and approval. See [Architecture](docs/ARCHITECTURE.en.md) for the full trust boundary and
fail-open/fail-closed policy.

## Learn more

There is more to SAGE than the above. You do not need to learn all of it up front — explore the
documents below as you need them.

- **PDCA workflow** — a delivery cycle from plan to implementation to review to completion report.
- **Done Criteria** — the plan records concrete completion criteria up front, and each one's state
  is updated only as implementation and verification evidence appears. When a criterion changes,
  the affected phases and review run again, so an old approval cannot support a new completion
  report.
- **Profile** — separates shared team policy from settings that apply only to your machine.
- **Fast Cycle** — a compressed procedure with fewer documents for urgent work (only when
  explicitly enabled).

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
reviewable policy rather than prompt-only guidance. It may be excessive when you only need prompt
snippets or one-off code generation.

## License

Apache License 2.0. Commercial use, modification, and redistribution are allowed; distributions
must include [LICENSE](LICENSE) and [NOTICE](NOTICE). Releases before `v0.9.71` used
CC BY-NC-SA 4.0.
