<!-- sage-doc-source: profile-reference.md sha256:8a815b2a1541603362ec56951471137276fc0c842f27290dba31e49bc34740a6 -->
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
```

Effective risk is the highest tier identified by path, filename, content, or user declaration. A
governed cycle requires exactly one `Risk Level: L1`, `L2`, or `L3` declaration in the Phase 00
document with the same stem. If that declaration is lower than the current change, raise Phase 00
before continuing.

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
  note_convention:
    folder: "wiki"
    required_structure: {}
```

Vault features are disabled when `vault_path` is empty. Write-back depth follows the Phase 00 risk
tier. L2 and L3 require a detailed note covering background, design decisions, changes,
verification, and recurrence prevention.

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
```

The project owns its verification commands. SAGE connects commands and evidence declared in the
profile and phase documents, but does not guess the project's build system.
