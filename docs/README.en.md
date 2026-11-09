<!-- sage-doc-source: README.md sha256:9cd0379947078747c24aef9c9e2b1340d86513bc7ecbee0bbef8d812cd59bf5d -->
# SAGE Documentation

[한국어](README.md) | [Project README](../README.en.md)

Start with the document that matches your task.

| Audience | Start here |
|---|---|
| First-time user | [English quickstart](quickstart.en.md) |
| Developer using the CLI daily | [CLI reference](cli-reference.en.md) |
| Developer separating shared and Git-ignored personal guidance | [Personal overlays and manual migration](cli-reference.en.md#personal-overlays) |
| Developer checking automatic Standard/Fast overlay delivery and limits | [Target-specific context delivery](ARCHITECTURE.en.md#target-specific-overlay-context-delivery) |
| Maintainer configuring project policy | [Profile reference](profile-reference.en.md) |
| Developer who wants to understand Phase 05 review modes and cost | [Cross review](cross-review.en.md) |
| User resolving installation or runtime errors | [Troubleshooting](troubleshooting.en.md) |
| Contributor changing SAGE internals | [Architecture](ARCHITECTURE.en.md) |
| Developer locating generated artifacts and deciding what to commit | [Artifacts](ARTIFACTS.en.md) |
| Maintainer deciding whether a release is possible | [Release readiness](release-readiness.en.md) |

## Harness Specifications

`docs/sage_harness/` is the source of truth for installed hook, agent, skill, and MCP specs plus the
manifest. These files are consumed by the engine and generator. Structural changes must be followed
by `sage generate` and `sage validate`.

## Agent Framework

The engine sources these protocols from `templates/core/framework/docs/agent/`. `sage install`
deploys them to `docs/agent/` in the target repository. Put project policy in
`sage/project-profile.yaml` and project-owned governance documents instead of editing installed
framework renders.

## Development Evidence

The [planning and verification index](plan_docs/README.md) distinguishes approval of the overlay-only
candidate from the Issue #36 integration candidate. Platform tests, current-PR CI, independent review,
and release approval require separate evidence.
