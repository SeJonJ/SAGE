# [Base Plan] Override grant store isolation and bypass actor attribution

Cycle-Stem: `sage-override-grant-store-isolation`
Risk Level: L3
Status: IN_PROGRESS

## 1. Context

`sage override` splits authority from audit on purpose. The audit log `.sage/override.jsonl` is meant
to be committed so reviewers can trace who bypassed which gate and why. The authority cache
`.sage/tmp/grants.jsonl` is meant to stay machine-local so cloning a repository never activates
someone else's bypass. The `override_audit` module docstring states this guarantee explicitly.

The guarantee does not hold in installed projects. `install.py` writes exactly one entry into a
project `.gitignore` (`/sage/project-profile.local.yaml`), and the package ships no `.gitignore`
template. A fresh project therefore tracks `.sage/tmp/grants.jsonl` by default, so committing it is
the normal behaviour of `git add -A` rather than a mistake.

Reproduced end to end against the published 0.9.73 wheel:

```
[projA] alice grants override (reason="urgent deploy", ttl=2h) -> active 1
[projA] git check-ignore .sage/tmp/grants.jsonl -> NOT IGNORED
[projA] git add -A && git commit -> .sage/tmp/grants.jsonl committed
[projB] git clone projA -> active grants 1 (user=alice)
[projB] hook_runtime._maybe_override(...) -> GATE OPENED FOR B: True
```

B never requested a grant, yet a `block_phase_incomplete` BLOCK was lifted.

The same reproduction exposed a second, independent defect: `record_bypass()` writes no actor field,
while `grant` records carry `user`. Audit therefore reads as if the granting user performed the
bypass.

## 2. Goal

- Remove the propagation path structurally instead of defending it: the authority cache must live
  outside the repository working tree, where git cannot carry it.
- Record who consumed a grant, so audit attribution is correct even in single-user use.
- Correct the documentation that asserts a guarantee the code does not provide.

## 3. Locked Scope Decision

Two alternatives were considered and rejected. They are recorded here so the decision is not
relitigated during review.

- Injecting `.sage/tmp/` into the project `.gitignore` during install. A `.gitignore` is a
  user-owned file; a security property must not depend on one. Once the cache leaves the tree there
  is nothing left to ignore.
- Filtering `active_grants()` by the record's `user` field. `USER` is trivially spoofable and
  collapses to `unknown` in CI, which either creates a new hole where `unknown` matches `unknown` or
  breaks override in CI entirely. It is a weak defence layered on a problem already eliminated.

No migration is performed. `MAX_TTL_SECONDS = 24h` is enforced inside `grant()` as a library-level
invariant, so every pre-existing grant expires within a day. The old path is not read. The worst
case is one operator re-issuing a grant, which fails in the safe direction.

## 4. Scope

- E-1: relocate the authority cache to a state directory outside the tree, keyed by the resolved
  real path of the repository root.
- E-2: record the acting user on `bypass` audit events.
- Documentation: `override_audit` module docstring, `sage/commands/override.py` docstring,
  `docs/ARTIFACTS.md`.

Out of scope: the audit log location, TTL semantics, gate scoping, and the server-side authority
gate (SD-9).

## 5. Acceptance

- A grant issued in one clone does not activate in another clone, pinned by regression test.
- A repository reached through a symlink resolves to the same grant store.
- `bypass` records carry the acting user.
- Tests never read or write the developer's real state directory.
- Full hook suite passes under claude, codex, and marker-free environments; wheel closed loop passes.
