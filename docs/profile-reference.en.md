<!-- sage-doc-source: profile-reference.md sha256:cffb34613b7616cbfbb74f27555b8a5f09c2fed76d227e83b16ba00d530787ce -->
# SAGE Profile Reference

[한국어](profile-reference.md) | [Documentation index](README.en.md)

## Shared policy and local capabilities

- `sage/project-profile.yaml`: team policy committed to the repository
- `sage/project-profile.local.yaml`: capabilities for the current machine, excluded from Git
- `sage/project-profile.json`: merged and normalized output created by generate

The local profile owns only machine-specific capabilities such as host, model, and vault paths. It
cannot override shared policy that could weaken gates, including risk, PDCA, and review policy.

Generate converges the compiled profile to mode `0600`. A `0644` file produced by an older release
becomes owner-only on the next generation. In CI or containers where hooks run under another UID,
run them under the same UID or arrange an explicit profile handoff; widening the file mode for
cross-user sharing is not part of the supported contract.

The local profile also owns the interface language.

```yaml
interface:
  language: en      # absent means ko; only ko | en are accepted
```

It never reaches the shared profile, the compiled `project-profile.json`, a manifest, or the
profile hash — a language preference behaves like a machine capability and stays local. For a
single run, put the global `--lang` before the subcommand (`sage --lang en validate`).
Resolution order is `--lang` → local profile → `ko`; hooks take no `--lang` and follow the
local profile and the default only. An invalid value falls back to `ko` and `sage validate`
reports it as a configuration failure, but no gate verdict or exit code changes.

## Minimal workflow

Use `sage-init` for initial authoring and `sage-init-local` when joining an already configured
project.

```bash
# Select claude, codex, or both to match runtime.installed_hosts
sage generate --kind hook --write --target codex
sage validate --kind all
sage doctor --profile sage/project-profile.yaml
```

## Main sections

### Project and version

```yaml
sage:
  required_version: "0.9.72"

project:
  name: "weatherapp"
  prefix: "weatherapp"
```

`required_version` is the exact SAGE version that must interpret the project's assets. Doctor,
validate, and SessionStart report a mismatch with the installed, generated, or runtime version.

### Runtime and cross-model review

```yaml
runtime:
  active_host: auto
  installed_hosts: [claude, codex]

options:
  cross_model: true

cross_model:
  reviewer: { host: codex, model: gpt-5.6-terra }
  effort: xhigh
```

`active_host: auto` detects the host from the current execution environment. Phase 05 cross-model
review selects a runtime other than the actual active host. If the peer CLI cannot be reached, a
required review policy produces BLOCKED.

`cross_model.policy` is `required | recommended | off`. `required` cannot be weakened by a local
`cross_model.enabled: false` (a local profile can never weaken shared policy). `on_unavailable`
governs what happens when the peer CLI cannot be reached: `block` (default, effectively mandatory
under a `required` policy) or `clean_context_same_runtime` (fall back to a fresh session on the same
runtime).

### Risk

```yaml
risk:
  l0_pass_globs: ["docs/**"]
  l1_path_globs: ["frontend/**"]
  l2_path_globs: ["backend/**"]
  l3_filename_globs: ["*payment*", "*auth*"]
  l2_content_keywords: ["transaction"]
  l3_content_keywords: ["PrivateKey", "chargeCard"]
  plan_glob: "plan_docs/**/*.md"
  l3_review_strategy: "claude_grep_first"
```

Effective risk is the highest tier identified by path, filename, content, or user declaration. A
governed cycle requires exactly one `Risk Level: L1`, `L2`, or `L3` declaration in the Phase 00
document with the same stem. If that declaration is lower than the current change, raise Phase 00
before continuing.

`l3_review_strategy` is **required for L3 to be reviewable at all** (`claude_grep_first` |
`codex_feature_signal` | a project-custom module name). When it is empty, independent L3 review
fails safely closed (BLOCK) — an L3 change that never gets past review is usually missing this
value, not a review-loop problem.

### Phase 00 Done Criteria

```yaml
pdca:
  base_plan:
    done_criteria_gate: advisory  # off | advisory | enforce
```

A missing key or `off` preserves existing behavior. `advisory` reports malformed completion
criteria, invalid revisions, stale affected phases, and stale Phase 05 approval without blocking.
`enforce` blocks those conditions at phase transitions, APPROVED, and Phase 06. Normal unresolved
`[ ]` items remain allowed during Phases 01-04. A new Phase 00 starts with
`Done-Criteria-Revision: 1`; changing criterion text or scope records a new revision, reason, and
affected phases. `sage-init` and `sage-profile-modify` collect this shared policy;
`sage-init-local` does not modify it.

### Review loop (Phase 05)

```yaml
pdca:
  review_loop:
    enabled: false
    lenses: { L2: [correctness, security], L3: [correctness, security, concurrency] }
    refuters: 2
    refute_threshold: majority
    max_iterations: { L2: 1, L3: 3 }
    dry_rounds: 1
    budget_tokens: { L2: 150000, L3: 400000 }
    severity_block: ["P0", "P1"]
    termination_enforce: advisory
    report_gate_enforce: advisory
    early_completion:
      enabled: false
      minimum_completed_rounds: 1
```

The Phase 05 find→refute→triage→rework adversarial loop. Disabled by default. `lenses` are the
perspectives each round searches from, `refuters` is how many reviewers challenge each finding,
`max_iterations` caps the rounds, and `dry_rounds` is how many consecutive rounds with zero new
findings count as convergence. `termination_enforce`/`report_gate_enforce` are
`off | advisory | enforce`; `enforce` actually blocks writing Phase 06. This is the standard
cycle's full procedure — the compressed variant for explicitly allowed L2/L3 work is Fast Cycle,
below.

`early_completion` is the opt-in that lets an explicit user authorization close the loop before
convergence; it is off by default, and an absent block reads as off. `minimum_completed_rounds` has
an engine floor of 1 that a project may only raise — allowing 0 would open "approved after zero
review rounds" through a single configuration line. This opt-in **loosens** the gate, so while the
verdict token stays `APPROVED`, Phase 05 also carries
`Review-Assurance: REDUCED_BY_USER_AUTHORIZATION` so a later reader and the CI authority can tell it
apart from a converged approval. **Enabling the setting is not the authorization for any individual
run** — the reason, approver, and confirmation token come from the user at close time.

### Fast Cycle

```yaml
pdca:
  fast_cycle:
    enabled: false
    reason_required: true
    minimum_rounds: { L2: 1, L3: 1 }
    minimum_lenses: { L2: 2, L3: 2 }
    lenses:
      L2: [correctness, error_handling, convention]
      L3: [correctness, security, data_integrity, concurrency]
    standard_transition:
      enabled: false
```

Fast Cycle is a separate compressed L2/L3 protocol, not a generic override. `enabled` is shared
policy and defaults to false. `reason_required` is fixed at true. Minimum rounds must be at least
one, minimum lenses at least two, and each candidate list must satisfy its floor. The operator enters
Fast level, lens count, and a one-line reason through `sage-cycle-fast`. Actual Risk Level remains in
the composite Phase 00 and cannot be lowered by Fast level. `sage-init` and `sage-profile-modify`
collect this shared policy conversationally.

`standard_transition` is a separate opt-in that lets a Standard Cycle already in progress move to
the Fast contract through `sage fast-cycle convert`; it is off by default, and an absent block reads
as off. With it on, a run can reach the Fast review minimums without a composite plan, so the audit
record rather than a document becomes the only evidence of how that run entered Fast. The conversion
writes no document, and a converted run waives only the pre-implementation phases the recorded phase
list can show. **Enabling the setting is not the confirmation for any individual conversion** —
`--confirm FAST-CONVERTED`, the reason, and the approver come from the user at conversion time.

### Components

```yaml
components:
  - id: backend
    paths: ["backend/**"]
    runtime_models: { claude: opus, codex: gpt-5.6-terra }
  - id: frontend
    paths: ["frontend/**"]
```

Components drive the implementer roster and ownership routing. `sage generate --kind roster`
creates an `implementer-<component>` spec for each component.

### Phase 04 checklist scanning

```yaml
checklist_scan_targets:
  - label: "03 implementation"
    glob: "plan_docs/03-implementation/**/*.md"
    is_impl: true
  - label: "backend plan"
    glob: "backend/plan_docs/*.md"
```

Each item requires a `label` and a project-relative `glob`; `is_impl` is an optional boolean.
Absolute, UNC/rooted, Windows drive-relative (`C:private/*.md`), `..` segment, and control-character
paths are rejected. Runtime also checks every match by realpath, so a symlink cannot read a document
outside the repository. If an older release silently ignored a malformed item, the new `sage
generate` preserves existing outputs and fails. Correct the profile and generate again.

### Team runtime

```yaml
team:
  core:
    leader:
      enabled: true
      runtime: { model: opus, effort: xhigh }
    reviewer:
      enabled: true
      runtime: { model: opus }
```

After a change, `sage install --force` redeploys model and effort fields into Claude CORE agent
frontmatter. Codex agent files do not interpret those fields as execution settings, so validate
warns when they have no effect.

### Governance documents

```yaml
governance_docs:
  - { doc: "docs/architecture.md", label: "System architecture" }
  - { doc: ".github/SECURITY.md", label: "Security policy" }
```

Each entry contains a project-relative path and a single-line label of at most 80 characters. Only
the path pointer is rendered into the managed block in `AGENT_GUIDE.md`; it does not create risk
triggers. Run `sage sync-overlays` after changing this section.

### Knowledge capture

```yaml
knowledge_capture:
  vault_path: "/path/to/obsidian/vault"
  provider: obsidian
  scan_before_dev: true
  update_after_dev: true
  fast_cycle_dashboard: false
  note_convention:
    folder: "wiki"
    required_structure: {}
```

Vault features are disabled when `vault_path` is empty. Write-back depth follows the Phase 00 risk
tier. L2 and L3 require a detailed note covering background, design decisions, changes,
verification, and recurrence prevention.
With `fast_cycle_dashboard: true`, terminal Fast runs update a project dashboard in the vault. The
source of truth remains `.sage/fast_cycle.jsonl`; dashboard failure does not roll back an audit event
that was already recorded.

### Feedback

```yaml
feedback:
  enabled: false
  block_release: false
  record: false
  record_target: auto
```

When enabled, SAGE tracks `sage-feedback ::` markers in source files. `block_release` blocks a
release on unresolved blocking markers when CI invokes `sage feedback --release-gate`.

### Verification

```yaml
verification:
  commands:
    build: "npm run build"
    test: "npm test"
    lint: "npm run lint"
  acceptance:
    enabled: true
    require_for_risk: [L2, L3]
    statuses: [PASS, FAIL, "NOT TESTED", N/A]
    unresolved_statuses: [FAIL, "NOT TESTED"]
    report_gate_by_risk: { L2: advisory, L3: enforce }
    waiver: { enabled: true }
```

The project owns its verification commands. SAGE connects commands and evidence declared in the
profile and phase documents, but does not guess the project's build system.

`acceptance` is the per-requirement evidence matrix. It rests on the premise that a passing build and
test suite is not the same claim as "the feature the user asked for actually works." With the default
`enabled: true`, any risk tier listed in `require_for_risk` must record `PASS/FAIL/NOT TESTED/N/A`
for every requirement in Phase 04. `report_gate_by_risk` decides whether an `unresolved_statuses`
entry (FAIL or NOT TESTED by default) blocks writing Phase 06 — **L3 cannot be lowered to advisory
from the profile alone.** An exception requires an explicit CLI-issued waiver matched exactly to the
cycle and requirement ID; there is no silent pass.

### Other gate toggles

| Key | Default | Meaning |
|---|---|---|
| `pdca.cycle_binding_visibility` | `gated` | How far gate **pass** lines disclose the bound cycle stem. `gated` shows it only where a verdict line already exists (L2/L3 pass, WARN). `all` also emits a line on L1/L0 passes — turn it on to catch mis-binding by eye on long-lived branches, at the cost of one line per edit. The binding evidence itself is recorded in `.sage/override.jsonl` regardless of this setting |
| `pdca.retro.report_gate_enforce` | `off` | Stop hook confirms after the fact that `sage retro --check` ran. `enforce` can BLOCK at most once per session |
| `pdca.writeback.depth_review_gate` | `off` | Stop hook confirms an L2/L3 write-back note self-declared a host self-review (`Depth-Self-Review: performed`) |
| `conventions` | `[]` | Pointers to stack-specific convention docs: `[{ scope, stack, doc, file_globs }]` |
| `context_management.compaction` | `enabled: true` | What to preserve on session compaction (`architectural_decisions`, `open_bugs`, etc.) and the max snapshot size |
| `hooks.register` | `[claude]` | Which hosts register hooks. Cross-model projects use `[claude, codex]` |
