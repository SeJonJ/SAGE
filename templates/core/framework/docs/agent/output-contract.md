# Output contract

What an agent/skill must produce so its work is verifiable and auditable.

- **Faithful reporting** — state outcomes plainly; on failure, include the
  failing output. Never claim done without verification.
- **Plan linkage** — non-trivial work references its plan doc under
  `{paths.plan_docs}`.
- **Verification** — the gate level required for the change has passed
  (`sage_harness/verify-changes.sh`) for checks that ran. Apply
  `verification-protocol.md` **Runner outcomes and scope**: record command, exit,
  observed output and executed/skipped scope. NO_EVIDENCE/exit 0 alone is not
  required-check PASS; retain missing required evidence as NOT TESTED under the
  existing acceptance and approval rules.
- **Acceptance evidence** — for non-trivial PDCA work, Phase 01 lists explicit
  acceptance items and Phase 04 records each item as `PASS`, `FAIL`,
  `NOT TESTED`, or `N/A` with evidence. Both documents bind by the same exact
  `Cycle-Stem`; IDs are well formed, unique, and match exactly. Do not claim done
  while required items are missing, unknown, duplicated, `FAIL`, or `NOT TESTED`.
- **No generated-artifact edits** — changes go to `docs/sage_harness/` specs,
  then `sage generate`.
- **Stop compliance** — at session end, the `stop-compliance-report` hook may
  summarize gate state and pending items per `profile`.

These are the runtime-neutral defaults; projects may add stricter contracts in
`profile`.
