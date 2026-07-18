# [Design] SAGE-FB-03 Manual Double-Host 운영 모델

Cycle-Stem: `sage-fb-03-manual-double-host`

## 1. Profile Contract

```yaml
runtime:
  installed_hosts: [claude, codex]
  active_host: codex
  external_reviewer: opposite_runtime
```

- `installed_hosts`: desired discovery surfaces, unique non-empty subset of claude/codex.
- `active_host`: current single execution host and opposite reviewer derivation source.
- `host`: legacy alias. If present with `active_host`, values must match.
- manifest `installed_hosts`: actual install receipt; doctor compares it with desired profile state.

## 2. Shared Resolver

`sage.runtime_hosts` owns active/configured host resolution and semantic issues. doctor, review, generate, install, and
profile validation call this module instead of independently reading `runtime.host`.

## 3. Manual Handoff

The user finishes durable phase documents, switches runtime manually, updates the single active host, and resumes the
same exact Cycle-Stem. SAGE does not launch the other host, run both concurrently, or infer phase transition from session state.

## 4. Review Routing

`options.cross_model:true` and reachable opposite CLI routes Phase 05 to the host opposite `active_host`. Missing peer
degrades explicitly as before. Double-host intent with cross-model off is WARN, not implicit enablement.
