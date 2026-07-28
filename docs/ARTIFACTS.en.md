<!-- sage-doc-source: ARTIFACTS.md sha256:b92cc746edf26f214cb83b568b1b842ce0d4a7b27261bec9b17d7473abbfe4f4 -->
# SAGE Artifact Map

[한국어](ARTIFACTS.md) | [Documentation index](README.en.md)

Running SAGE creates resources in **different locations for different purposes**. This document is
the single reference for **where** each artifact is created, **what it does**, and **which command,
hook, or skill writes it**. Each entry is grounded in the actual generating code.

Three principles apply throughout:

- **AI hosts own judgment; deterministic code owns placement and gates.** CLI commands and hooks
  determine artifact *locations* deterministically.
- **One write path for the vault.** Only `sage knowledge write-back` and related commands write
  Obsidian notes, logs, and indexes.
- **Use `.sage` without Obsidian; use the vault with Obsidian.** When
  `knowledge_capture.vault_path` is empty, knowledge notes leave only local traces under `.sage/`.

---

## At a glance

| Location | Nature | Representative artifacts | Writer |
|---|---|---|---|
| `<root>/.sage/` | Source-of-truth PDCA execution data; only four audit files are committed | Committed: `override.jsonl`, `acceptance-waivers.jsonl`, `loop_audit.jsonl`, `retro_audit.jsonl`; local: `plan_interview.md`, `knowledge_scan.md`, `tmp/`, `context/` | CLI, skills, hooks |
| `<root>/<host>/logs/` | Per-session hook records | `session-<date>.jsonl`, `compliance-<date>.md`, `declared-risk-<sid>.json` | Hook adapters |
| Obsidian vault (`vault_path`/folder) | Final knowledge notes | Write-back TECH notes, loop audit dashboard, retrospective notes, `log.md` | `sage knowledge`, `review-loop`, `retro` |
| `<root>/sage/asset_overrides/` | CORE overlays, committed but not deployed by install | `agents/<id>.md`, `skills/<id>.md` | Human-authored, with absorb guidance |
| `<root>/<host>/...` plus `docs/sage_harness/.manifest.json` | Generated spec assets and integrity stamps | Hook, agent, skill, and MCP configuration; manifest | `sage generate` |

`<host>` is `.claude` for Claude and `.codex` for Codex
(`scripts/sage_harness/hooks/runtime/io_claude.py:14`, `io_codex.py:15`).

---

## 1. `<root>/.sage/`: PDCA execution sources of truth

These are authoritative records created while PDCA runs. They are stored under `.sage/` relative to
the project root, including when a command is started from a subdirectory.

The tracking policy is **exclude by default and explicitly include only audit trails**. The
"Tracking" column below is authoritative, and `.gitignore` enforces it:

```gitignore
/.sage/*
!/.sage/override.jsonl
!/.sage/acceptance-waivers.jsonl
!/.sage/loop_audit.jsonl
!/.sage/retro_audit.jsonl
```

- **Commit the four audit trails.** Peers, CI, and reviewers must be able to inspect who bypassed or
  waived a gate, or completed a loop, when they did it, and why after cloning. Keeping this only
  locally would make enforced blocks auditable while allowing exception paths to disappear.
- **Do not commit permissions, session state, or reproducible derivatives.** In particular,
  `tmp/grants.jsonl` is an active bypass **permission**. Propagating it could activate another
  person's grant on your machine.
- Ignoring `/.sage/` as a directory prevents Git from descending into it, which disables every `!`
  exception. The rule must therefore use `/.sage/*`.

| File | Tracking | Role | Generating code |
|---|:---:|---|---|
| `.sage/plan_interview.md` | Local | Planning-interview output. In the first `sage-plan` or `sage-cycle` process, the leader records platform, feature, data/API, constraints, and completion criteria, then uses them to write PDCA 00 (CONTEXT) and 01 (CONTENT) | Output contract `templates/core/framework/docs/agent/plan-interview.md`; consumer `sage-plan/SKILL.md` |
| `.sage/knowledge_scan.md` | Local | Pre-development report of related prior knowledge found in the Obsidian vault; an input to PDCA 00 | `sage/commands/knowledge.py:228`, `_write_scan_report(root, ...)` |
| `.sage/loop_audit.jsonl` | **Commit** | Source of truth for Loop A adversarial Phase 05 review rounds. Open, round, and close events are appended and sequence integrity is validated. The vault dashboard is a derived view | `sage/commands/review_loop.py:8`, `:472` |
| `.sage/retro_audit.jsonl` | **Commit** | Append-only evidence that Loop C (`sage retro --check`) succeeded. Each passing check records `{run_id, note_path, digest, ts}`. The Stop hook's `retro_gate` policy uses it to verify that the cycle actually passed. With `pdca.retro.report_gate_enforce` off, the event is recorded without enforcement | `sage/commands/retro.py::_check_note` to `scripts/sage_harness/hooks/runtime/retro_audit.py` |
| `.sage/override.jsonl` | **Commit** | Append-only audit log for temporary gate bypasses from `sage override`; records reason and TTL, with automatic expiration | `sage/commands/override.py:6` |
| `.sage/acceptance-waivers.jsonl` | **Commit** | Explicit `NOT TESTED` waivers for exact L3 cycle and required acceptance IDs. Grant, use, and revoke events include reason, scope, remaining evidence, and confirmer. Malformed, duplicate, and conflicting records fail closed | `sage/commands/acceptance_waiver.py` to `scripts/sage_harness/hooks/runtime/acceptance_waiver.py` |
| `.sage/context/snapshots/<stem>/*.json` | Local | Cross-session source-of-truth packet binding completed-phase profile, manifest, exact Cycle-Stem document paths, and hashes. It does not contain document bodies | `sage context snapshot` |
| `.sage/context/restored/*.md` | Local | Resume briefing generated after validating both the packet and current sources; reproducible derivative | `sage context restore` |

`context/snapshots` is authoritative host/session handoff data, so a team may explicitly track it
when needed. `context/restored` can always be regenerated. Both are local by default.

Server-authority attestations are not local `.sage/` sources of truth. Protected CI passes
`sage authority attest` output as a short-lived job artifact, and `sage authority gate` binds it to
the same base, head, diff, cycle, and risk. Project-local override and waiver audits are excluded
from that decision.

> Execution helpers such as `.sage/tmp/grants.jsonl` may also appear in this tree to track runtime
> grants. `grants.jsonl` is the active bypass **permission** for this machine and must never be
> committed: committing it could activate another person's bypass after clone or pull. The design
> separates committed history in `override.jsonl` from local permissions in `tmp/grants.jsonl`
> (`scripts/sage_harness/hooks/runtime/override_audit.py` module docstring).

---

## 2. `<root>/<host>/logs/`: per-session hook records

Hook adapters write these records under `logs/` in the host directory, either `.claude` or `.codex`
(`scripts/sage_harness/hooks/runtime/hook_runtime.py:220-221, 261-262`).

| File | Role | Generating code |
|---|---|---|
| `session-<date>.jsonl` | `post-tool-logger` appends the operation and classification of changed files for each tool call. This is the source for compliance reports | `hook_runtime.py:250-275`; classifier `scripts/sage_harness/hooks/post_tool_logger_core.py:67` |
| `compliance-<date>.md` | `stop-compliance-report` aggregates that day's session JSONL at session end | `hook_runtime.py:354-...`; `report = os.path.join(log_dir, f"compliance-{today}.md")` |
| `declared-risk-<sid>.json` | `capture-declared-risk` records the user's declared task risk by session. The pre-implementation gate consumes it | `scripts/sage_harness/hooks/runtime/io_claude.py:33` / `io_codex.py:40` |

Unlike `.sage/` sources of truth, these are **session-scoped execution records** that change every
session or day.

---

## 3. Obsidian vault: final knowledge notes

Final knowledge notes are written to the vault selected by `knowledge_capture.vault_path` and
`note_convention.folder` (default `wiki`) through `sage/commands/knowledge.py:92`,
`_vault.vault_target`. Write-back commands are the **only vault write path**. This stage is skipped
when `vault_path` is empty.

| Artifact | Role | Generating code |
|---|---|---|
| Write-back TECH note | Stores knowledge after PDCA completion. Tags follow the vault authoring guide in `AGENT_GUIDE.md`, `CLAUDE.md`, or `GEMINI.md` and can be overridden with CLI `--tags`; they are not hardcoded | `sage/commands/knowledge.py:301`, `_note_path` |
| `TECH - <name> loop audit.md` | One Loop A dashboard per project. Updated on each close as a derived view of `.sage/loop_audit.jsonl`, with a retrospective-link column per run | `sage/commands/review_loop.py:485, :492` |
| `TECH - <name> retro <stem> <date>.md` | Human-gated Loop C retrospective. Created with `approved:false`; it is not absorbed or applied automatically until a person sets `approved:true`. Includes a backlink to the related loop audit. The stem is selected from `--feature`, then the unique Phase 05 filename, then `run_id`. If another run with the same stem writes a retrospective on the same day, the later note is named `TECH - <name> retro <stem> <date> <run_id>.md`, preventing reuse of a prior run's note to pass the completion gate. Dashboard links resolve by frontmatter `run_id`, not filename | `sage/commands/retro.py`, `_write_vault_note` |
| `log.md` and index link | When a note is created, idempotently append `- <date> [[note]] - title` to the vault history hub `log.md` and index | `sage/commands/knowledge.py:278`, `_append_log_once` |

Filenames follow `note_convention`, and tags follow the vault authoring guide, so generation adapts
to each vault's conventions.

---

## 4. `<root>/sage/asset_overrides/`: CORE overlays

`sage install` manually deploys six CORE bootstrap agents and nine skills, and `--force` overwrites
them. This directory customizes those CORE renders through project-local overlays instead of direct
edits.

| Artifact | Role | Generating code |
|---|---|---|
| `sage/asset_overrides/agents/<id>.md` | Overlay appended to a specific CORE agent when its render exists. It cannot weaken AGENT_GUIDE, phase, review, or verification gates | Path guidance in `sage/commands/absorb.py:171` |
| `sage/asset_overrides/skills/<id>.md` | Equivalent overlay for a specific CORE skill | Same |

Key properties:

- **Install does not ship overlays**, so `sage install --force` can overwrite CORE assets without
  removing the overlays.
- **Absorb identifies candidate locations.** When retrospective or loop output suggests improving
  an agent or skill, it points to this path instead of modifying CORE directly. Hooks are
  deterministic, so an overlay file alone cannot change hook behavior; hook changes go through
  specs.

This generalizes the existing `sage/conventions/*.md` and convention-checker pattern across asset
types.

---

## 5. Generated spec assets and manifest: `sage generate`

`sage generate` places runtime configuration files derived from specs, which are the source of
truth, and records integrity stamps. Destinations depend on the asset kind.

| Kind | Artifact location |
|---|---|
| `hook` | `settings.json` / `hooks.json` plus runtime shims |
| `agent` | `.claude/agents/`, `.codex/agents/` |
| `skill` | `.claude/skills/`, `.codex/skills/` |
| `mcp` | `.mcp.json` for Claude, `.codex/config.toml` for Codex |

- **`docs/sage_harness/.manifest.json`** is the source of truth for generated-asset hash stamps.
  `sage validate` compares these stamps with actual files to detect drift and staleness. The write
  guard also uses this ownership contract to block direct edits
  (`sage/commands/generate.py:305, :412`).

These are the output side of the **spec -> generate -> validate -> block closed loop**. Specs
themselves, at `docs/sage_harness/{hooks,agents,skills,mcps}/{id}.md`, are human-authored sources of
truth rather than generated artifacts. See [ARCHITECTURE.en.md](ARCHITECTURE.en.md) for gate and
trust-boundary details.
