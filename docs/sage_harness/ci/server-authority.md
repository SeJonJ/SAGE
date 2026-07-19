# Server-side PR authority gate

`sage authority` is the protected-CI boundary for SAGE policy. Local hooks remain fast developer feedback; they are
not branch-protection authority because a pull request can change its own hook, profile, workflow, override, and
waiver files.

## Trust model

- Run the verifier from a protected default-branch revision, a reusable workflow pinned by full commit SHA, or a
  separately protected SAGE checkout pinned by full commit SHA.
- Treat the pull request head as git object data only. The adapter may use `git diff`, `git ls-tree`, and
  `git cat-file`; it must not import, source, execute, install, or test code from the head tree.
- Read and validate both `base:sage/project-profile.yaml` and `head:sage/project-profile.yaml`. The authoritative
  risk is the higher result, so a pull request cannot weaken its own classification policy.
- Read exact-cycle Phase 00 through 05 evidence from regular head-tree files only (Git mode `100644` or `100755`;
  symlink mode `120000` is rejected). L3 requires one valid document per phase, canonical acceptance evidence,
  and exactly `Final Status: APPROVED` in Phase 05. The same regular-file rule applies to base/head profiles.
- Phase documents are pull-request-authored structural evidence. This gate does not authenticate the identity of the
  external model or person that produced Phase 05; independent reviewer attestation needs a separately protected issuer.
- Never feed project-local override or acceptance-waiver audit data into the authority API.
- Install the protected engine with its `schema` extra. Authority mode blocks if `jsonschema` is absent; it never
  accepts the normal CLI's WARN-only schema fallback.

## Commands

```bash
python -m sage.cli authority inspect \
  --root pr-data --base "$BASE_SHA" --head "$HEAD_SHA" \
  --repository "$REPOSITORY" --cycle-stem "$CYCLE_STEM" --issuer protected-ci

SAGE_ATTESTATION_KEY="$PROTECTED_SECRET" python -m sage.cli authority attest \
  --issuer protected-ci --repository "$REPOSITORY" --base "$BASE_SHA" --head "$HEAD_SHA" \
  --diff-sha256 "$DIFF_SHA256" --cycle-stem "$CYCLE_STEM" --risk "$RISK" \
  --reviewer github-actions > attestation.token

SAGE_ATTESTATION_KEY="$PROTECTED_SECRET" python -m sage.cli authority gate \
  --root pr-data --base "$BASE_SHA" --head "$HEAD_SHA" \
  --repository "$REPOSITORY" --cycle-stem "$CYCLE_STEM" --issuer protected-ci \
  --attestation-file attestation.token
```

`SAGE_ATTESTATION_KEY` must be at least 32 bytes and must come from a protected CI secret. Missing, short, expired,
tampered, or incorrectly bound attestations exit 2. A fork pull request does not receive normal protected secrets,
so an attestation-required job blocks rather than silently degrading to advisory.

The compact token signs canonical claims for issuer, repository, base/head full SHA, structured-diff digest,
cycle stem, risk, reviewer, verdict, nonce, issue time, and expiry. TTL is capped at one hour. Do not pass the secret
as a command-line argument or persist it in repository artifacts.

In the inactive example, `reviewer=github-actions` identifies the protected gate executor, not an independently
authenticated Phase 05 reviewer. The nonce is a signed issuance-correlation value; without an external consumed-nonce
store it is not replay prevention. Exact diff bindings and the one-hour TTL bound replay to the same evaluated change.

## Workflow activation

`templates/core/framework/docs/agent/sage-authoritative-gate.yml.example` is deliberately non-active. Before copying
it into `.github/workflows/`, replace both action and SAGE placeholders with reviewed 40-hex commit SHAs, choose a
protected source for `CYCLE_STEM`, configure the secret, and give the job the unique required-check name
`sage-authoritative-gate`. Branch protection/ruleset wiring and expected source verification are deployment work,
not properties the engine can assert locally.
