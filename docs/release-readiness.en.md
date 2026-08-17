<!-- sage-doc-source: release-readiness.md sha256:474a97e8228ad27fb0d618b6889163daca4465019115018dd0f9cce7eb874ac7 -->
# Release readiness

This document records **how readiness is decided**, not what it currently is. The current answer changes every cycle, and a value written into a document becomes false the moment it changes. Ask `python scripts/ci/publish_preflight.py` for the present state.

The Korean authoring source is [release-readiness.md](release-readiness.md).

## Readiness has exactly two values

| Status | Meaning |
|---|---|
| `NOT READY` | An unresolved P0/P1 exists, or the evidence disagrees with itself |
| `READY_FOR_USER_RELEASE_DECISION` | The evidence agrees and independent review is complete. **Whether to release is the user's call** |

`RELEASED` is deliberately absent. Tooling reports whether a release is possible; performing it is a human decision. A checking tool that crosses that line removes the approval step entirely.

## What blocks a release

Every check in `publish_preflight.py` is independent and all of them run. Stopping at the first failure means the second problem is only discovered on the next run, so preparation advances one item at a time.

| Check | Why it blocks |
|---|---|
| `tag-version` | If the tag and `__version__` disagree, what the user installs is not what the tag points at |
| `version` | Publishing a placeholder such as `0.0.0` cannot be undone |
| `catalog` | A key present on only one side falls through to a runtime fallback, so users discover the gap instead of the build |
| `localization-debt` | Even at inventory zero, remaining leaks are counted separately. Having recorded the debt on a list is not grounds to ship |
| `docs-pair` | Releasing with only one language updated lets the two documents drift apart |
| `inventory` | The inventory must match the code and contain zero user-visible literals pending catalog migration. A current list is not completion |
| `upgrade` | A real v0.9.84 consumer must receive each new managed CORE file and its receipt together. Command and test registration alone are insufficient |
| `mutation` | A repository that changed during release preparation means a version was raised without approval |

`publish` cannot be undone. PyPI will not accept the same version twice, and a tag has already spread to other clones. So this check asks not "does it build" but **"does the artifact claim the same thing the repository claims"**.

## Platform contract

`scripts/ci/platform_smoke.py` verifies the same items on Linux, macOS and Windows.

- Installation
- Korean and English help produce different screens
- The local profile's language setting actually changes the screen
- The cycle document language is declared and the marker is written into Phase 00
- `validate` reaches a decision with a documented exit code
- The hook entry point is reported
- `PYTHONIOENCODING=ascii` does not raise `UnicodeEncodeError`

The script **does not use bash**. Whether things work without bash is precisely what is under test, so a checking tool that requires bash would leave that environment permanently unverified.

A failing platform stays a failure, never a skip. A silent skip counts as a pass and ships a release with one platform unverified.

## Building a release candidate

The version is changed **only in a temporary source copy**. Stamping the repository itself raises a version without approval, and until it is reverted every later judgement reads that value as fact.

```bash
# Build a candidate without touching the repository
git archive HEAD | (mkdir -p /tmp/sage-candidate && tar -x -C /tmp/sage-candidate)
# Change the version and build only inside /tmp/sage-candidate
```

The `mutation` check in `publish_preflight.py` enforces this rule.

## Downgrade

There is no automatic downgrade. Restore from the backup left by `sage upgrade --apply`. The report is at `.sage/upgrades/<run-id>.json` and Git does not track it.

The reverting procedure is deliberately not built into the tool: safely rolling back sometimes requires reverting files that upgrade does not own. Deciding what to revert belongs to whoever knows that project's state.
