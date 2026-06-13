# Output contract

What an agent/skill must produce so its work is verifiable and auditable.

- **Faithful reporting** — state outcomes plainly; on failure, include the
  failing output. Never claim done without verification.
- **Plan linkage** — non-trivial work references its plan doc under
  `{paths.plan_docs}`.
- **Verification** — the gate level required for the change has passed
  (`scripts/verify-changes.sh`).
- **No generated-artifact edits** — changes go to `docs/sage_harness/` specs,
  then `sage generate`.
- **Stop compliance** — at session end, the `stop-compliance-report` hook may
  summarize gate state and pending items per `profile`.

These are the runtime-neutral defaults; projects may add stricter contracts in
`profile`.
