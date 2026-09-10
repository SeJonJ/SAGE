<!-- sage-doc-source: release-readiness.md sha256:4e30cac4f3538ff2decb6b1838ca97fd7d9b68f7a08e63ad2e89dd6d8f6d3c15 -->
# Release readiness

This document records **how readiness is decided**, not what it currently is. The current answer
changes every cycle, and a value written into a document becomes false the moment it changes. Run
`python3 scripts/ci/publish_preflight.py` on POSIX or `py -3 scripts/ci/publish_preflight.py` on
Windows for the present state.

The Korean authoring source is [release-readiness.md](release-readiness.md).

## Readiness has exactly two values

| Status | Meaning |
|---|---|
| `NOT READY` | An unresolved P0/P1 exists, or the evidence disagrees with itself |
| `READY_FOR_USER_RELEASE_DECISION` | The evidence agrees and independent review is complete. **Whether to release is the user's call** |

`RELEASED` is deliberately absent. Tooling reports whether a release is possible; performing it is a
human decision. A checking tool that crosses that line removes the approval step entirely.

## What blocks a release

Every check in `publish_preflight.py` is independent and all of them run. Stopping at the first
failure means the second problem is only discovered on the next run, so preparation advances one
item at a time.

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
| Windows desktop evidence | `publish_preflight` does not count this for you. Without a record of a real run on that SKU, automatic removal is unverified and the documented support scope diverges from the verified scope |

`publish` cannot be undone. PyPI will not accept the same version twice, and a tag has already
spread to other clones. So this check asks not "does it build" but **"does the artifact claim the
same thing the repository claims"**.

## Platform contract

`scripts/ci/platform_smoke.py` verifies the same items on Linux, macOS and Windows 11 desktop. The
two POSIX platforms run in the hosted matrix on every PR; Windows runs in the **self-hosted job**
described below.

- Installation
- Korean and English help produce different screens
- The local profile's language setting actually changes the screen
- The cycle document language is declared and the marker is written into Phase 00
- `validate` reaches a decision with a documented exit code
- The hook entry point is reported
- `PYTHONIOENCODING=ascii` does not raise `UnicodeEncodeError`

The script **does not use bash**. Whether things work without bash is precisely what is under test,
so a checking tool that requires bash would leave that environment permanently unverified.

A failing platform stays a failure, never a skip. A silent skip counts as a pass and ships a release
with one platform unverified.

## Hosted runners cannot produce the Windows evidence

GitHub-hosted `windows-latest` is really **Windows Server 2025**. Green there is valid backend
regression evidence but **not desktop SKU evidence.**

**The logs now do tell them apart.** The capability report, smoke, race smoke, and core checks each
print edition, build, product type, filesystem, and process bitness. Windows was still removed from
the hosted matrix, for a different reason: reading those values stays a **human step**. The green
itself looks identical on both SKUs, and the distinction only holds if someone goes back to the
summary line. In this cycle a Server runner's green was nearly read as desktop evidence, and what
prevented it was a comment.

So rather than requiring people to read correctly every time, **the place where an out-of-scope
runner could be read as desktop evidence was removed outright.** Inside CI, the one place that
produces this evidence is the `windows11_uninstall` self-hosted job.

| Item | Value |
|---|---|
| Runner | `[self-hosted, windows, x64, win11, sage-uninstall]` |
| Runs when | a `run-win11-uninstall` label is **added** (`labeled`) to a same-repository PR |
| Never runs on | fork PRs, `synchronize`, `opened`, `reopened`, push |
| Gate before anything native | `windows_capability_report.py --require-product-support` |
| Steps | rename probe, capability report, platform smoke (3.12), uninstall smoke, race smoke, core checks (py 3.10, 3.11, 3.12) |

The label is an **approval event, not a state**. A standing label does not carry approval to a new
commit, so verifying the next commit means removing the label and adding it again. Checkout is
pinned to `head.sha` and the evidence step compares the actual tree against it, so **evidence and
commit are bound one to one**.

The removal checks run under `SAGE_UNINSTALL_REQUIRE_PRODUCT_SUPPORT=1`. One policy refusal, zero
real removals, or any of the three scopes not actually running is a non-zero exit — substituting
refusal-contract assertions for real removal is **itself a failure**. If that substitution were
allowed, the job could report evidence without ever having removed anything.

**The evidence is a record of a real run on that SKU.** The required items are edition, build,
product type, filesystem, process bitness, real removal count, policy refusal count, and the commit
under verification; this job is the place that makes such a record **repeatable**. A directly
recorded run on a Windows 11 desktop counts as the same evidence when it records the same items and
the same commit — what cannot be substituted is the SKU, not the way it was run. Without a record of
either kind, automatic removal on that platform is unverified.

## Building a release candidate

The version is changed **only in a temporary source copy**. Stamping the repository itself raises a
version without approval, and until it is reverted every later judgement reads that value as fact.

```bash
# Build a candidate without touching the repository
git archive HEAD | (mkdir -p /tmp/sage-candidate && tar -x -C /tmp/sage-candidate)
# Change the version and build only inside /tmp/sage-candidate
```

The `mutation` check in `publish_preflight.py` enforces this rule.

## Downgrade

There is no automatic downgrade. Restore from the backup left by `sage upgrade --apply`. The report
is at `.sage/upgrades/<run-id>.json` and Git does not track it.

The reverting procedure is deliberately not built into the tool: safely rolling back sometimes
requires reverting files that upgrade does not own. Deciding what to revert belongs to whoever knows
that project's state.
