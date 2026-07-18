# [Design] SAGE-FB-04 Host Model Discovery and Routing

Cycle-Stem: `sage-fb-04-host-model-routing`

## 1. Profile Contract

```yaml
components:
  - id: backend
    paths: ["backend/**"]
    model: opus
    runtime_models:
      codex: gpt-5.6-terra
      claude: opus

cross_model:
  peer: opposite_runtime
  reviewer:
    host: claude
    model: opus
```

- `components[].model` remains the legacy work-intensity tier.
- `components[].runtime_models` maps installed hosts to actual CLI model names.
- `cross_model.reviewer` is an explicit interview result. When configured, its host must equal the runtime opposite
  `runtime.active_host`; a manual host handoff therefore requires an explicit reviewer update.

## 2. Discovery Confidence

- Codex: read `models_cache.json` from the effective Codex home. A regular, non-symlink, size-bounded JSON file with
  visible model entries is `cache-confirmed`; cache age is reported.
- Claude: the CLI has no stable account model-list command. SAGE reports documented CLI aliases as
  `syntax-only/account-unverified`; it does not scrape historical session metadata or spend tokens probing models.
- Profile-selected full model IDs remain allowed. Static validation checks shape and routing; `sage doctor` compares
  selections with the local catalog and reports confirmed, syntax-only, unknown, or discovery-unavailable.

## 3. Runtime Wiring

- `sage models` owns discovery and machine-readable JSON output.
- `sage model_routing` owns profile parsing and semantic issues.
- `sage cross-check` resolves `cross_model.reviewer.model` and appends `-m <model>` for Codex or
  `--model <model>` for Claude.
- roster scaffolding records the active-host runtime model separately from the legacy tier.

## 4. Safety

- No shell command construction, network/model probes, credential reads, or account-history scraping.
- Cache paths are regular non-symlink files, bounded in size, and parsed as JSON.
- Unknown profile keys and non-string/blank model values fail closed.

