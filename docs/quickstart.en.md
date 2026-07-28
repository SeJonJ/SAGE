# SAGE Quickstart

[한국어](quickstart.md) | [README](../README.en.md)

## 1. Install

SAGE requires Python 3.10+ and Git. The pipx installation with schema validation is recommended.

```bash
pipx install "sage-harness[schema]"
sage --version
```

On Windows, install pipx first with `py -m pip install --user pipx` and `py -m pipx ensurepath`.
Installed hooks run through `sage-hook.exe` and do not require bash.

## 2. Install Into a Project

```bash
cd your-project

# Codex: keep CORE skills in the repository
sage install --host codex --skill-scope project-local

# Or Claude Code
sage install --host claude
```

Choose `--skill-scope global` to share Codex CORE skills across user projects. The scope is explicit,
and `sage doctor` reports duplicate copies.

## 3. Author the Profile

- Claude Code: `/sage-init`
- Codex: `$sage-init`
- Team member joining an already configured repository: `sage-init-local`

The first init separates shared policy in `sage/project-profile.yaml` from Git-ignored machine
capabilities in `sage/project-profile.local.yaml`.

## 4. Generate and Validate Hooks

```bash
# Codex
sage generate --kind hook --write --target codex
# Use --target claude for Claude Code or --target both for both hosts
sage validate --kind all
sage doctor
```

When validation reports STALE, regenerate the kind named in the output. FAIL indicates a real
contract violation such as a missing file, schema error, or failed execution smoke.

## 5. Start a Delivery Cycle

- Full PDCA: `sage-cycle`
- Planning Phases 00-02: `sage-plan`
- Delivery Phases 03-06: `sage-team`
- Add or modify assets: `sage-asset`
- Resolve developer feedback: `sage-feedback`

Governed changes require an exact Phase 00 declaration using `Risk Level: L1`, `Risk Level: L2`, or
`Risk Level: L3`, plus the required phase documents. Phase 06 completion is blocked until Phase 05
review is APPROVED.

## Next

- [CLI reference](cli-reference.md)
- [Profile reference](profile-reference.md)
- [Troubleshooting](troubleshooting.md)
