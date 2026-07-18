# [Design] SAGE-FB-07 L0 Domain Risk Exception

Cycle-Stem: `sage-fb-07-l0-domain-risk-exception`

## Profile Contract

```yaml
risk:
  l0_pass_globs: ["**/*.png"]
  l0_exclude_globs: ["assets/game/**"]
  l3_filename_globs: ["assets/game/**"]
```

`l0_exclude_globs` is path-only and case-insensitive like the existing risk globs. Each entry must exactly appear in
at least one higher-risk path list after compilation. This prevents an exclusion from turning L0 into unclassified
`none`.

## Domain Materialization

For every valid `risk.domains[]` item, compiler adds each `path_glob` to both its configured risk-level list and the
deduplicated `l0_exclude_globs`. Thus a domain path always has a target tier without duplicating author intent.

## Classifier Order

1. Check whether the path matches an L0 exclusion.
2. Apply the existing L0 immediate return only when no exclusion matches.
3. Continue existing L3 -> L2 -> L1 path classification and content escalation.
4. Add `l0_excluded` to provenance when the bypass contributes to a classified result.

No domain names or stack knowledge enter the pure core.

