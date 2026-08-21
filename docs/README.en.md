<!-- sage-doc-source: README.md sha256:19b8863e0df9d98773e5cb5a0e3ef82163482fabbf5327d6585234d8c193d7d3 -->
# SAGE Documentation

[한국어](README.md) | [Project README](../README.en.md)

Start with the document that matches your task.

| Audience | Start here |
|---|---|
| First-time user | [English quickstart](quickstart.en.md) |
| Developer using the CLI daily | [CLI reference](cli-reference.en.md) |
| Maintainer configuring project policy | [Profile reference](profile-reference.en.md) |
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
