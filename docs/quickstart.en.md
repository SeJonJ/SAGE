<!-- sage-doc-source: quickstart.md sha256:c530d4cadaff5dede17b872981608db4b6700eef37da24d7ffeafa3bc483b86b -->
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

## 2. Install into a project — pick the path that matches your AI tool

SAGE supports both Claude Code and Codex, but a given project only needs the one you actually use.
If you want both, run each path separately.

**If you use Codex:**

```bash
cd your-project
sage install --host codex --skill-scope project-local
```

`--skill-scope` must be explicit — `project-local` shares Codex CORE skills only within this
repository, `global` shares them across every project on this machine. `sage doctor` reports
duplicate copies.

**If you use Claude Code:**

```bash
cd your-project
sage install --host claude
```

## 3. Author the profile — fill in this project's configuration through conversation

Installing alone makes SAGE check nothing. Project-specific settings — risk tiers, verification
commands — have to be filled in (the profile) before anything actually runs. Run this **inside the
host you just installed for**.

- Claude Code: `/sage-init`
- Codex: `$sage-init`
- Team member joining an already configured repository: `sage-init-local`

The first init separates shared policy in `sage/project-profile.yaml` from Git-ignored machine
capabilities in `sage/project-profile.local.yaml`.

This is where you choose the language SAGE talks to you in. The init conversation asks, and
you can change it later by editing `sage/project-profile.local.yaml`, which Git ignores.

```yaml
interface:
  language: en      # absent means ko
```

For a single run in another language, put the global `--lang` **before** the subcommand:
`sage --lang en doctor`. Language never changes a verdict — the status and exit code stay the
same and only the sentence you read differs. The language Phase 00–06 documents are *written*
in is a separate decision, fixed once when the cycle starts. See the
[CLI reference](cli-reference.en.md).

## 4. Generate and validate hooks — turn the profile into runtime files

Filling in the profile does not create hooks by itself. `generate` reads the profile and produces
the runtime files the AI actually reads; `validate` confirms they match.

```bash
# Codex
sage generate --kind hook --write --target codex
# Use --target claude for Claude Code or --target both for both hosts
sage validate --kind all
sage doctor
```

When validation reports STALE (the definition changed but the runtime file has not been regenerated
yet), regenerate the kind named in the output. FAIL indicates a real contract violation such as a
missing file, schema error, or failed execution smoke — resolve the cause first, then retry.

## 5. Start a delivery cycle — when you actually start writing code

Once you reach this point, SAGE is active as a gate. Real development starts with one of these:

- Full PDCA (plan → deliver → review → completion report): `sage-cycle`
- Profile-enabled compressed L2/L3 delivery (for urgent work): `sage-cycle-fast`
- Author a composite Fast Phase 00: `sage-plan-fast`
- Implement, review, and close Fast delivery: `sage-team-fast`
- Planning only, Phases 00-02: `sage-plan`
- Delivery from Phase 03, Phases 03-06: `sage-team`
- Add or modify a hook/agent/skill/MCP asset: `sage-asset`
- Resolve developer feedback markers: `sage-feedback`

Governed changes require an exact Phase 00 declaration using `Risk Level: L1`, `Risk Level: L2`, or
`Risk Level: L3`, plus the required phase documents — meaning you cannot edit risky code without a
plan first. Phase 06 completion is blocked until Phase 05 review is APPROVED — meaning you cannot
report "done" without a review.
Fast Cycle omits physical Phases 01-04 only after embedding their content and checklists in a
composite Phase 00. It writes no plan or audit until Fast level, lens count, and reason are present.

A new Phase 00 declares `Done-Criteria-Revision: 1` and exactly one `## 5. Done Criteria`, with
concrete outcomes written as `- [ ] ...`. Mark `[x]` only when evidence exists, and use
`[~] ... (N/A: reason)` only for a reasoned exclusion. When criterion text or scope changes,
record the new revision, reason, and affected phases, then rerun those phases and Phase 05 review.

## Next

- [CLI reference](cli-reference.md)
- [Profile reference](profile-reference.md)
- [Troubleshooting](troubleshooting.md)
