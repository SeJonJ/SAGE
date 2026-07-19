# [Base Plan] SAGE-FB-06 Context Snapshot/Restore

Cycle-Stem: `sage-fb-06-context-snapshot-restore`

Risk Level: L3

## Context

`context_management.compaction` is currently exposed in the profile template but no SAGE runtime consumes it.
The existing `session-start-snapshot` hook is a Phase-06 baseline for the retro gate and is not a resumable context
packet. Reusing it would mix two unrelated trust boundaries.

## Goal

Store a bounded, structured context packet at an explicit PDCA phase boundary, verify its integrity and source
bindings in a later session or host, and materialize a briefing that SAGE skills explicitly consume before resuming.

## Non-Goals

- Automatic Claude/Codex launch, concurrent ownership, or automatic phase transfer.
- Restoration of a host model's hidden conversation state.
- Semantic invention of decisions or bugs from free-form Markdown.
- Reuse of the retro `session-start-snapshot` baseline.

## Impact

- SAGE CLI/profile/schema/CORE skill templates: affected.
- ChatForYou Backend: N/A, no application source change.
- ChatForYou Frontend: N/A, no application source change.
- ChatForYou Desktop: N/A, no application source change.

## References

- `SAGE - ChatForYou 실증 2차 후속 개발 요구사항 (26.07.17)` / `SAGE-FB-06`
- `plan_docs/02-design/sage-fb-03-manual-double-host.md`
- `scripts/sage_harness/hooks/session_start_snapshot_core.py` (separate retro baseline)

