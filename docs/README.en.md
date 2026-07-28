# SAGE Documentation

[한국어](README.md) | [Project README](../README.en.md)

Start with the document that matches your task.

| Audience | Start here |
|---|---|
| First-time user | [English quickstart](quickstart.en.md) |
| Developer using the CLI daily | [CLI reference](cli-reference.md) |
| Maintainer configuring project policy | [Profile reference](profile-reference.md) |
| User resolving installation or runtime errors | [Troubleshooting](troubleshooting.md) |
| Contributor changing SAGE internals | [Architecture](ARCHITECTURE.md) |
| Developer locating generated artifacts and deciding what to commit | [Artifacts](ARTIFACTS.md) |

## Harness Specifications

`docs/sage_harness/` is the source of truth for installed hook, agent, skill, and MCP specs plus the
manifest. These files are consumed by the engine and generator. Structural changes must be followed
by `sage generate` and `sage validate`.

## Agent Framework

`docs/agent/` contains the PDCA, review, risk, and context-management protocols installed into target
repositories. Put project policy in `sage/project-profile.yaml` and project-owned governance
documents instead of editing installed framework renders.
