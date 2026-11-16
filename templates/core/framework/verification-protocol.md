# verification-protocol.md

Gate policy for L1/L2/L3 changes. Concrete commands come from
`profile.verification` and `sage_harness/verify-changes.sh`; this document defines
the policy that hooks enforce.

| Level | Checks | Mode |
|-------|--------|------|
| L1 | syntax | advisory |
| L2 | build, test, lint | block |
| L3 | build, test, lint, review | block |

## L3 review

L3 changes require an independent review before merge. The reviewer runtime is
resolved by `sage doctor` from `profile.options.cross_model`:

- cross_model off → clean-context review in the same runtime.
- cross_model on + opposite runtime reachable → opposite-runtime review.
- cross_model on + opposite runtime unreachable → BLOCKED
  (fail-closed; surfaced by `sage doctor` and `sage cross-check`).

How an L3 change is matched to its review document is a project decision
(`profile.risk.l3_review_strategy`). Until selected, `pre-implementation-gate`
blocks L3 changes (safe default).

## Acceptance evidence

### Runner outcomes and scope

`verify-changes.sh` reports executed and skipped check names/counts. PASS means only that
commands which ran succeeded, not that skipped checks or all acceptance requirements passed.
NO_EVIDENCE means no command ran (including a missing profile); skipped count is unknown
when the profile is missing. The existing exits remain: success/skip 0, command failure 1.
With an existing profile, an invalid level retains exit 2; the existing missing-profile
early exit 0 stays unchanged. A failed command remains FAIL. Exit 0 alone never proves
a required check was performed.

In Standard, Fast and rework verification, keep required checks and acceptance evidence
under the existing policy. Do not turn NO_EVIDENCE into a required-check PASS merely to
advance a round. NO_EVIDENCE/exit 0 alone is not a command failure and does not itself
trigger rework retries; carry its scope and missing required evidence forward.
Review may inspect missing evidence, but required unresolved acceptance
still prevents approval under the existing rules below; an optional skipped check creates
no new failure rule. In Phase 04, an ID whose required evidence was not obtained is NOT TESTED;
retain the runner observation or UNKNOWN in evidence/notes. Do not introduce these words as
new status values or mark unrelated IDs untested when they have sufficient evidence.

The bundled output contract applies to the bundled runner. A project-owned runner is not
overwritten to adopt it: inspect its actual command/result evidence and report unknown
coverage honestly. Non-force installs may retain older documents or reject changed CORE
trust; verify the installed version and follow the existing explicit update procedure.
### Acceptance rules

Deterministic commands prove that configured checks ran; they do not prove every
explicit user requirement was satisfied. When `profile.verification.acceptance`
is enabled:

- Phase 01 must define an acceptance matrix outside fenced code blocks for explicit user requirements.
- Phase 03 maps implementation and tests to those acceptance IDs.
- Phase 04 records `PASS`, `FAIL`, `NOT TESTED`, or `N/A` for each item with
  concrete evidence.
- Phase 01/04 must be selected by the exact same `Cycle-Stem`; every acceptance
  ID must be well formed and unique, every required Phase 01 ID needs Phase 04
  evidence, and Phase 04 cannot introduce unknown IDs.
- Phase 05 treats required `FAIL` or `NOT TESTED` items as blocking unless the
  report gate records an explicit exact-ID L3 waiver as residual evidence.
- Phase 06 defaults to advisory for L2 and enforce for L3/unknown. A local-only
  L3 `NOT TESTED` item may become a residual WARN only after an explicit
  `sage acceptance-waiver grant` for the exact cycle and required acceptance ID.
  `FAIL` is never waivable, and a waiver never changes the recorded status to PASS.
- Phase 05 approval requires exactly one `Final Status: APPROVED` declaration outside
  fenced code blocks, and Phase 06 is written separately from every 00–05 phase update.
