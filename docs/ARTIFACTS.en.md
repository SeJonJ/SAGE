<!-- sage-doc-source: ARTIFACTS.md sha256:acc00735930e54c011f990c3bc304d4795dc8283ec710258ccb1c5af145254fb -->
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
- **`.sage` is always the source of truth; the vault is a derived view.** PDCA execution data and
  audit records live under `.sage/` whether or not Obsidian is in use. An empty
  `knowledge_capture.vault_path` only means the derived view is not produced — nothing canonical is
  lost, and deleting the vault leaves the audit intact. Reading this as "the source of truth moves
  depending on Obsidian" leads people to treat the vault as the thing to back up.

---

## At a glance

| Location | Nature | Representative artifacts | Writer |
|---|---|---|---|
| `<root>/.sage/` | Source-of-truth PDCA execution data; only four shared audit files are committed | Committed: `override.jsonl`, `acceptance-waivers.jsonl`, `loop_audit.jsonl`, `fast_cycle.jsonl`; local: `retro_audit.jsonl`, `feedback.jsonl`, `plan_interview.md`, `knowledge_scan.md`, `tmp/`, `context/` | CLI, skills, hooks |
| `<root>/<host>/logs/` | Per-session hook records | `session-<date>.jsonl`, `compliance-<date>.md`, `declared-risk-<sid>.json` | Hook adapters |
| Obsidian vault (`vault_path`/folder) | Final knowledge notes | Write-back TECH notes, loop/Fast audit dashboards, retrospective notes, `log.md` | `sage knowledge`, `review-loop`, `fast-cycle`, `retro` |
| `<root>/sage/asset_overrides/` | CORE overlays, committed but not deployed by install | `agents/<id>.md`, `skills/<id>.md` | Human-authored, with absorb guidance |
| `<root>/<host>/...` plus `docs/sage_harness/.manifest.json` | Generated spec assets and integrity stamps | Hook, agent, skill, and MCP configuration; manifest | `sage generate` |

`<host>` is `.claude` for Claude and `.codex` for Codex
(`io_claude.HOST_DIR`, `io_codex.HOST_DIR`).

---

## 1. `<root>/.sage/`: PDCA execution sources of truth

These are authoritative records created while PDCA runs. They are stored under `.sage/` relative to
the project root, including when a command is started from a subdirectory.

The tracking policy is **exclude by default and explicitly include only audit trails with shared
review value**. The "Tracking" column below is authoritative, and `.gitignore` enforces it:

```gitignore
!/.sage/
/.sage/*
!/.sage/override.jsonl
!/.sage/acceptance-waivers.jsonl
!/.sage/loop_audit.jsonl
!/.sage/fast_cycle.jsonl
```

- **Commit the four shared audit trails.** Gate bypasses, evidence waivers, Phase 05 review, and
  Fast source of truth must remain visible to peers, CI, and reviewers after cloning.
- **Keep `retro_audit.jsonl` local.** Its private Obsidian note path and check-time digest cannot be
  reproduced by a peer without that vault. Combining per-developer records in one append-only file
  exposes local paths and creates merge conflicts without portable evidence. The Stop gate reads the
  local file directly, so ignoring it does not change the decision.
- **Do not commit session state or reproducible derivatives.**
- **Active bypass permissions do not live here.** `.sage/` is inside the repository, so keeping
  permissions there would make the guarantee depend on an ignore rule, and `.gitignore` is a
  user-owned file that cannot serve as the basis for a security property. The permission cache lives
  **outside** the repository tree, in a machine-local state directory (see section 1.1).
- Ignoring `/.sage/` as a directory prevents Git from descending into it, which disables every `!`
  exception. The rule must therefore use `/.sage/*`.

| File | Tracking | Role | Generating code |
|---|:---:|---|---|
| `.sage/plan_interview.md` | Local | Planning-interview output. In the first `sage-plan` or `sage-cycle` process, the leader records platform, feature, data/API, constraints, and completion criteria, then uses them to write PDCA 00 (CONTEXT) and 01 (CONTENT) | Output contract `templates/core/framework/docs/agent/plan-interview.md`; consumer `sage-plan/SKILL.md` |
| `.sage/knowledge_scan.md` | Local | Pre-development report of related prior knowledge found in the Obsidian vault; an input to PDCA 00 | `sage.commands.knowledge._run_scan`, `_write_scan_report` |
| `.sage/loop_audit.jsonl` | **Commit** | Source of truth for Loop A adversarial Phase 05 review rounds. Open, round, and close events are appended, and the per-run strict hash chain plus sequence integrity are validated. The vault dashboard is a derived view | `sage/commands/review_loop.py`, `scripts/sage_harness/hooks/runtime/loop_audit.py` |
| `.sage/loop_audit.jsonl.lock` | Local | OS-owned process-lock sidecar for the Loop Audit writer. The `SAGE LOCAL STATE` gitignore block installed by SAGE excludes it; a file left after process exit is neither authority nor audit evidence | `loop_audit._audit_lock`, `sage.commands.install._render_local_profile_gitignore` |
| `.sage/fast_cycle.jsonl` | **Commit** | Fast Cycle open/review/close/abort source of truth. Its per-run strict hash chain binds actual risk, Fast level, reason, minimum rounds, lenses, Phase 00 hashes, Loop run, and Phase 05/06 evidence for local and server checks | `sage fast-cycle`, `scripts/sage_harness/hooks/runtime/fast_cycle_audit.py` |
| `.sage/fast_cycle.jsonl.lock` | Local | OS-lock sidecar used by the Fast audit writer. It is neither authority nor audit evidence and remains ignored by the wildcard rule | `fast_cycle_audit`, `loop_audit._audit_lock` |
| `.sage/retro_audit.jsonl` | Local | Append-only local evidence that Loop C (`sage retro --check`) succeeded. Each passing check records `{run_id, note_path, digest, ts}`. The Stop hook's `retro_gate` policy reads it in the same working copy to verify that the cycle actually passed. It is ignored by default so private vault paths and digests that peers cannot reproduce do not enter the shared repository. With `pdca.retro.report_gate_enforce` off, the event is recorded without enforcement | `sage/commands/retro.py::_check_note` to `scripts/sage_harness/hooks/runtime/retro_audit.py` |
| `.sage/override.jsonl` | **Commit** | Append-only audit log for temporary gate bypasses from `sage override`; records reason and TTL, with automatic expiration | `sage.commands.override` |
| `.sage/acceptance-waivers.jsonl` | **Commit** | Explicit `NOT TESTED` waivers for exact L3 cycle and required acceptance IDs. Grant, use, and revoke events include reason, scope, remaining evidence, and confirmer. Malformed, duplicate, and conflicting records fail closed | `sage/commands/acceptance_waiver.py` to `scripts/sage_harness/hooks/runtime/acceptance_waiver.py` |
| `.sage/context/snapshots/<stem>/*.json` | Local | Cross-session source-of-truth packet binding completed-phase profile, manifest, exact Cycle-Stem document paths, and hashes. It does not contain document bodies | `sage context snapshot` |
| `.sage/context/restored/*.md` | Local | Resume briefing generated after validating both the packet and current sources; reproducible derivative | `sage context restore` |

An ignore rule does not remove `.sage/retro_audit.jsonl` from the index of an existing installation.
After reviewing the warning from `sage install`, run this command from the project root:

```bash
git rm --cached -- .sage/retro_audit.jsonl
```

The command preserves the local file but does not change existing Git history. If historical paths
must be removed, the team must make a separate explicit history-rewrite decision. A project that
intentionally shares portable retro notes may add `!/.sage/retro_audit.jsonl` **after**
`# <<< SAGE LOCAL STATE`, outside the managed block. Rules inside the block are replaced by the next
install, and an exception before the block is overridden by its later `/.sage/*` rule.

`context/snapshots` is authoritative host/session handoff data, so a team may explicitly track it
when needed. `context/restored` can always be regenerated. Both are local by default.

Server-authority attestations are not local `.sage/` sources of truth. Protected CI passes
`sage authority attest` output as a short-lived job artifact, and `sage authority gate` binds it to
the same base, head, diff, cycle, and risk. Project-local override and waiver audits are excluded
from that decision. Fast Cycle is the exception: authority reads committed `fast_cycle.jsonl` and
its bound `loop_audit.jsonl` from the head Git tree as regular UTF-8 blobs, then verifies strict
chains, clean terminal state, stem, plan hash, rounds, lens receipts, and Phase 05 markers. The
working tree and vault dashboard are not authority inputs.

### 1.1 Active bypass permissions: outside the repository

| Location | Precedence |
|---|---|
| `$SAGE_STATE_HOME/grants/<repo-key>.jsonl` | 1 (explicit; tests and operations) |
| `$XDG_STATE_HOME/sage/grants/<repo-key>.jsonl` | 2 |
| `%LOCALAPPDATA%\sage\state\grants\<repo-key>.jsonl` | 3 (Windows) |
| `~/.local/state/sage/grants/<repo-key>.jsonl` | 4 (default) |

`<repo-key>` is a SHA-256 over the repository root's **realpath** plus a **working-copy identity**.

- Without realpath normalization, reaching the same repository through a symlink splits it into two
  keys, so an issued grant becomes invisible.
- With the path alone, distinct repositories share one key. Deleting a repository and creating a
  different one at the same path would inherit the previous grant, which happens in practice where
  workspace paths are reused, such as CI runners. The working-copy identity is a
  `.git/sage/state-id` marker that never propagates through clone or commit. The search walks up to
  the enclosing repository, so a monorepo subdirectory used as the root still uses the parent's
  `.git/`. A tool-owned subdirectory follows ecosystem convention, as with `.git/lfs/` and
  `.git/annex/`. Only a directory outside any repository falls back to `.sage/instance-id`, where
  clone and commit paths do not exist at all.

**Two fail-closed rules.** A bypass is a permission, so SAGE refuses to create one when it cannot be
confident about the location.

- A state path that resolves **inside the repository** is rejected. Allowing it would let the grant
  be committed and activate the bypass in another clone, which is exactly what this separation
  prevents.
- An unresolvable home directory (no `HOME` and no passwd entry) is rejected rather than falling
  back. Retreating to a predictable shared location such as the temp directory would let anyone
  create a bypass simply by **planting** a valid grant file there. Set `SAGE_STATE_HOME` to an
  absolute path in that case.

History and permissions move in opposite directions: history in `override.jsonl` **must** be shared,
while permissions **must not** be. Through 0.9.73 permissions also lived inside the repository at
`.sage/tmp/grants.jsonl`, and because no code adds an ignore rule to installed projects, the default
was to track them. Committing them activated the bypass in other developers' clones. Rather than
relying on an ignore rule, the propagation path itself was removed.

`sage override --list` prints the current location. Deleting `.sage/tmp/` no longer resets it. Files
left at the old path are not read, because the 24-hour TTL cap expires every prior grant within a
day.

---

## 2. `<root>/<host>/logs/`: per-session hook records

Hook adapters write these records under `logs/` in the host directory, either `.claude` or `.codex`
(`hook_runtime.run_capture_declared_risk`, `run_post_tool_logger`,
`run_stop_compliance_report`).

| File | Role | Generating code |
|---|---|---|
| `session-<date>.jsonl` | `post-tool-logger` appends the operation and classification of changed files for each tool call. This is the source for compliance reports | `hook_runtime.run_post_tool_logger`; classifier `post_tool_logger_core.decide` |
| `compliance-<date>.md` | `stop-compliance-report` aggregates that day's session JSONL at session end | `hook_runtime.run_stop_compliance_report` |
| `declared-risk-<sid>.json` | `capture-declared-risk` records the user's declared task risk by session. The pre-implementation gate consumes it | `hook_runtime.run_capture_declared_risk`; `io_claude.read_declared_level`; `io_codex.read_declared_level` |

Unlike `.sage/` sources of truth, these are **session-scoped execution records** that change every
session or day.

---

## 3. Obsidian vault: final knowledge notes

Final knowledge notes are written to the vault selected by `knowledge_capture.vault_path` and
`note_convention.folder` (default `wiki`) through `sage.commands.knowledge._kc_gate` and
`sage.commands._vault.vault_target`. Write-back commands are the **only vault write path**. This
stage is skipped when `vault_path` is empty.

| Artifact | Role | Generating code |
|---|---|---|
| Write-back TECH note | Stores knowledge after PDCA completion. Tags follow the vault authoring guide in `AGENT_GUIDE.md`, `CLAUDE.md`, or `GEMINI.md` and can be overridden with CLI `--tags`; they are not hardcoded | `sage.commands.knowledge._write_or_append_note` |
| `TECH - <name> loop audit.md` | One Loop A dashboard per project. Updated on each close as a derived view of `.sage/loop_audit.jsonl`, with a retrospective-link column per run | `sage.commands.review_loop._write_vault_dashboard` |
| `TECH - <name> fast cycle audit.md` | Per-project Fast Cycle derived dashboard. When enabled in the profile it updates after close or abort; `.sage/fast_cycle.jsonl` remains authoritative | `sage fast-cycle show --vault`, `sage/commands/fast_cycle.py` |
| `TECH - <name> retro <stem> <date>.md` | Human-gated Loop C retrospective. Created with `approved:false`; it is not absorbed or applied automatically until a person sets `approved:true`. Includes a backlink to the related loop audit. The stem is selected from `--feature`, then the unique Phase 05 filename, then `run_id`. If another run with the same stem writes a retrospective on the same day, the later note is named `TECH - <name> retro <stem> <date> <run_id>.md`, preventing reuse of a prior run's note to pass the completion gate. Dashboard links resolve by frontmatter `run_id`, not filename | `sage/commands/retro.py`, `_write_vault_note` |
| `log.md` and index link | When a note is created, idempotently append `- <date> [[note]] - title` to the vault history hub `log.md` and index | `sage.commands.knowledge._append_log_once`, `_append_link_once` |

Filenames follow `note_convention`, and tags follow the vault authoring guide, so generation adapts
to each vault's conventions.

---

## 4. `<root>/sage/asset_overrides/`: CORE overlays

`sage install` manually deploys six CORE bootstrap agents and thirteen skills, and `--force`
overwrites them. This directory customizes those CORE renders through project-local overlays instead
of direct edits.

| Artifact | Role | Generating code |
|---|---|---|
| `sage/asset_overrides/agents/<id>.md` | Overlay appended to a specific CORE agent when its render exists. It cannot weaken AGENT_GUIDE, phase, review, or verification gates | Path guidance in `sage.commands.absorb._overlay_hint` |
| `sage/asset_overrides/skills/<id>.md` | Equivalent overlay for a specific CORE skill | Same |

Key properties:

- **Install does not ship overlays**, so `sage install --force` can overwrite CORE assets without
  removing the overlays.
- **Absorb identifies candidate locations.** When retrospective or loop output suggests improving an
  agent or skill, it points to this path instead of modifying CORE directly. Hooks are
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
| `hook` | `settings.json`/`hooks.json` plus runtime shims |
| `agent` | `.claude/agents/`, `.codex/agents/` |
| `skill` | `.claude/skills/`, `.codex/skills/` |
| `mcp` | `.mcp.json` for Claude, `.codex/config.toml` for Codex |

- **`docs/sage_harness/.manifest.json`** is the source of truth for generated-asset hash stamps.
  `sage validate` compares these stamps with actual files to detect drift and staleness. The write
  guard also uses this ownership contract to block direct edits
  (`sage.commands.generate._gen_hook_locked`, `_gen_mcp`,
  `generated_artifact_write_guard_core`).

These are the output side of the **spec -> generate -> validate -> block closed loop**. Specs
themselves, at `docs/sage_harness/{hooks,agents,skills,mcps}/{id}.md`, are human-authored sources of
truth rather than generated artifacts. See [ARCHITECTURE.en.md](ARCHITECTURE.en.md) for gate and
trust-boundary details.

---

## 6. Removal — ownership is the classification

`sage uninstall` sorts the artifacts above into four kinds. The criterion is **evidence that SAGE
created it**, not whether the content matches the current bundle — a user could have written the
same content by hand, and the impossibility of telling those apart is exactly why this command is
careful (`sage.uninstall_plan._project_actions`).

| Kind | Condition | Typical targets |
|---|---|---|
| `DELETE` | One of three proofs — inside a SAGE-only namespace, recorded as placed by the manifest, or carrying a SAGE marker | `sage/`, `.sage/`, `docs/sage_harness/`, `scripts/sage_harness/`, manifest-recorded framework files |
| `STRIP` | A shared file, so only the SAGE block is removed | `settings.json`, `hooks.json`, `.gitignore` |
| `PRESERVE` | Ownership cannot be proven, or the copy was edited by the user | Drifted global skill copies, deployed files whose content differs from the bundle |
| `BLOCK` | Cannot be read or judged, so it is left alone | Damaged settings, paths of unknown ownership |

`PRESERVE` and `BLOCK` **never enter the write-target list** — the only paths the execution layer
may open are `DELETE` and `STRIP` (`UninstallPlan.write_targets`).

**`.sage/` is deleted as a whole tree.** The four committed audit files (`override.jsonl`,
`acceptance-waivers.jsonl`, `loop_audit.jsonl`, `fast_cycle.jsonl`) disappear from the working tree
too; only Git history keeps them. If you need those records, commit them before removing.

**One exception — the receipt outlives the residue.** If host settings remain that SAGE could not
touch, `docs/sage_harness/` is preserved with `uninstall.receipt_retained_for_residual`. The
manifest is the only evidence of what was installed, and deleting it while residue remains would
leave the next run unable to prove why those files are there (`sage.uninstall_plan._project_actions`).

The actual list varies by host, scope, project location, and `CODEX_HOME`, so the list printed by
`sage uninstall --check` is authoritative. For the automatic-removal scope and the two refusal
screens see the [CLI reference](cli-reference.en.md).
