# Changelog

## 1.3.8 — 2026-11-17

- Keep requirement sources visible through planning and QA; use approved contracts to derive expected results.
- Distinguish executed and skipped checks. Zero executions now report `NO_EVIDENCE` while existing exit codes remain unchanged.
- Preserve missing required evidence as `NOT TESTED` and keep Standard, Fast and rework interpretations aligned.
- Preserve project-owned verification runners during force installation on Windows when profiles use portable `/` spelling for the supported current/legacy paths.
- Update Korean/English manuals and installed framework guidance. See the [verification and upgrade notes](docs/plan_docs/06/q00-evidence-adoption.md) for scope and remaining limits.

Earlier release notes are preserved on [GitHub Releases](https://github.com/SeJonJ/SAGE/releases).
