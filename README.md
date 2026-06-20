# SAGE — System for Agentic Governance & Engineering

[![CI](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml/badge.svg)](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sage-harness)](https://pypi.org/project/sage-harness/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/sage-harness/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Governance harness for AI coding agents.** One spec file per asset. SAGE generates the runtime config, validates drift, and hooks block violations at execution time — for Claude Code and Codex alike.

---

## The Problem

AI agents are fast, but they quietly break rules:

- Edit high-risk files without a plan document
- Skip PDCA phases mid-task
- Manually overwrite generated artifacts
- Self-review their own code (single-model bias)

The usual fix is either nagging the agent repeatedly, or hand-maintaining `.claude/` and `.codex/` configs project by project. SAGE replaces both with a **closed spec-SSOT loop**.

---

## Quick Start

```bash
pip install sage-harness

cd your-project
sage install          # pick a runtime: claude or codex
                      # deploys hooks, agent specs, AGENT_GUIDE, manifest

sage generate         # spec md → .claude/.codex artifacts + manifest stamp
sage validate         # drift · staleness · conformance check (read-only)
```

That's it. Your AI agent now has enforceable rules.

---

## How It Works

```
You write intent          generate            deployed to runtime       validate / hooks
docs/.../hooks/{id}.md  ──────────►  .claude/hooks/  ──────────────►  gate fires on violation
docs/.../agents/{id}.md             .codex/agents/                     drift detected on validate
docs/.../mcps/{id}.md               .mcp.json                                │
        ▲                           manifest stamp                            │
        └─────────────────── absorb (direct edit → spec patch proposal) ──────┘
```

The key is **closure**: generate artifacts from spec, validate artifacts against spec, block direct edits to artifacts, absorb emergency edits back into spec.

Engine has **zero domain values** — all project-specific values (stack, risk paths, PDCA keywords) come from `sage/project-profile.yaml`. Swap the profile, same engine governs a different stack.

---

## Asset Kinds

| kind | Generation | SSOT | Output |
|---|---|---|---|
| `hook` | Deterministic (pure function) | `docs/sage_harness/hooks/{id}.md` + `{id}_core.py` | `settings.json` / `hooks.json` + runtime shim |
| `agent` | Interpretive (AI renders) | `docs/sage_harness/agents/{id}.md` + `{id}.claims.yml` | `.claude/agents/` / `.codex/agents/` render |
| `skill` | Interpretive (AI renders) | `docs/sage_harness/skills/{id}.md` + `{id}.claims.yml` | `.claude/skills/` / `.codex/skills/` render |
| `mcp` | Deterministic (declarative serialization) | `docs/sage_harness/mcps/{id}.md` (frontmatter payload) | `.mcp.json` (claude) · `.codex/config.toml` managed-block (codex) |

> **MCP governance**: secrets are env var names only (`${VAR}` placeholder). Literal secret values in spec cause a pre-generate FAIL (fail-closed). SAGE owns `.mcp.json`; non-MCP settings in `config.toml` are preserved.

---

## Hooks (What Gets Enforced)

| hook | Fires at | Enforces |
|---|---|---|
| `pre-implementation-gate` | PreToolUse (file write) | Risk classification L0–L3 · plan doc · PDCA phase. BLOCK on miss |
| `pre-phase4-checklist-gate` | Phase transition | Checklist complete before PDCA 03→04 |
| `capture-declared-risk` | UserPromptSubmit | Captures user-declared risk level from prompt |
| `post-tool-logger` | PostToolUse | Appends change classification to session JSONL |
| `stop-compliance-report` | Session Stop | Generates compliance report |
| `generated-artifact-write-guard` | PreToolUse (native) | Blocks direct edits to generated artifacts → redirects to spec |

Hooks use a **pure-core + adapter** architecture: policy logic (`{id}_core.py`) has zero I/O; runtime-specific I/O lives in thin adapters. Same policy, consistent behavior across runtimes.

---

## CLI Reference

| command | What it does |
|---|---|
| `sage install` | Pick runtime (claude/codex) · deploy CORE harness (hooks, agent specs, AGENT_GUIDE, manifest) |
| `sage generate` | spec md → registered artifacts + `{host}/hooks` shim + profile compile + manifest stamp |
| `sage generate --kind roster` | `profile.components` → `implementer-<comp>` agent specs (deterministic scaffold) |
| `sage generate --kind mcp` | `docs/sage_harness/mcps/{id}.md` → `.mcp.json` (claude) / `config.toml` managed-block (codex) |
| `sage validate` | Drift · staleness · conformance · regression check. `--check` (fast) / `--schema` (JSON Schema) |
| `sage review` | `auto_approve_safe_default` — auto-approve passing assets; flag exceptions for human review |
| `sage absorb` | Direct-edit diff → spec patch proposal (no auto-apply) |
| `sage doctor` | Check optional deps · diagnose runtime env (OS/python/bash) · expose cross-model reviewer |
| `sage change` | Natural-language intent → generate/absorb routing hint (v1) |
| `sage override` | Time-limited legal bypass for blocked gates + append-only audit log (`.sage/override.jsonl`) |

---

## Profile Example

```yaml
# sage/project-profile.yaml — all domain values live here, engine has zero
project: { name: "acme", prefix: "acme" }
risk:
  l1_path_globs: ["*frontend/*.js"]           # low risk (UI)
  l2_path_globs: ["*backend/*.java"]          # source (build+test+lint required)
  l3_filename_globs: ["*payment*", "*auth*"]  # high risk (plan + review required)
  l3_content_keywords: ["encrypt", "PrivateKey", "chargeCard"]
  plan_glob: "plan_docs/**/*.md"
components: [backend, frontend]               # → sage generate --kind roster
cross_model:
  enabled: true
  opposite_runtime: codex                     # phase-05 review runs on codex
```

Cross-model review (`opposite_runtime: codex`) has caught P1 issues in real-world validation that the primary model missed.

---

## Installation

**From PyPI** (recommended):

```bash
pip install sage-harness
```

**With JSON Schema validation support:**

```bash
pip install "sage-harness[schema]"
```

**From source (editable):**

```bash
git clone https://github.com/SeJonJ/SAGE.git
cd SAGE
pip install -e .
```

Requirements: Python 3.10+, bash, git.

---

## Publishing a New Release

Tag a version and the [publish workflow](.github/workflows/publish.yml) handles PyPI automatically:

```bash
git tag v0.2.0
git push origin v0.2.0
```

> Prerequisite: configure a [PyPI Trusted Publisher](https://docs.pypi.org/trusted-publishers/) for this repo, or add a `PYPI_API_TOKEN` secret and switch the workflow to token-based auth.

---

## Who This Is For

**You** if you:

- Use Claude Code or Codex for real work and want the agent to follow rules without babysitting
- Have multiple projects and don't want to re-configure `.claude/` and `.codex/` by hand each time
- Run cross-model review (Claude + Codex) and want a structured handoff protocol
- Want a spec-driven, testable harness you can validate in CI

**Not for you** if you just want a quick prompt trick — SAGE is a framework, not a snippet.

---

## Validation Track Record

- **11-item hardening** completed after independent expert review (6.5/10 → SHIP)
- **Weatherapp Tier 2** golden instance: full `install → bootstrap interview → generate → validate → PDCA phases → cross-model review → fix → report` pipeline in a real project
- **MCP kind**: codex 6-round cross-model review, P0×3 + P1×8 + P2×2 all resolved, zero domain tokens in engine
- **CI** enforces wheel smoke test (clean venv, wheel-only install → generate → validate PASS) on every push

---

## License

MIT — see [LICENSE](LICENSE).
