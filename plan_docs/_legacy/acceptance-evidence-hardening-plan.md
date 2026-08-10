# Acceptance Evidence Hardening Plan

## 1. Problem

The 5th SAGE weather app test passed structural generation and deterministic
commands, but explicit user requirements were still missed. Build/test/review
evidence did not prove that each user requirement was actually satisfied.

## 2. Goal

Add a host-neutral acceptance evidence contract so Claude and Codex both follow
the same rule:

- Phase 01 maps each explicit requirement to required evidence.
- Phase 03 records implementation and verification work against those items.
- Phase 04 marks each item `PASS`, `FAIL`, `NOT TESTED`, or `N/A` with evidence.
- Phase 05 cannot approve if required acceptance items are unresolved.
- Phase 06 can warn or block when acceptance evidence is missing or unresolved.

## 3. Scope

- `verification.acceptance` profile configuration and validation.
- `pre-implementation-gate` report gate for Phase 04 acceptance evidence.
- Runtime-neutral hook messages for Claude and Codex.
- PDCA templates, review protocol, verification protocol, output contract, and
  SAGE core skills.
- Unit tests for profile validation and the report gate.

## 4. Non-goals

- Do not modify the weather app test product.
- Do not commit or push.
- Do not privilege Claude or Codex; runtime-specific output remains adapter-only.

## 5. Claude Collaboration

This is a medium-scope governance change. Target review count: 2-5.

- Review 1 status: blocked. `claude -p` returned `Not logged in · Please run /login`.
- Review 2 status: blocked. `claude -p` returned `You've hit your session limit · resets 2am (Asia/Seoul)`.
- Review 3 status: invalid. Tool-less call returned a refusal because Claude claimed unreliable tools despite no tools being provided.
- Review 4 status: completed from pasted raw diff. Accepted findings:
  - Scope 04 parsing to the acceptance section and Status column, not whole document/free text.
  - Apply `require_for_risk` when cycle risk is known.
  - Check Phase 01 matrix IDs against Phase 04 evidence IDs to catch omitted requirements.

## 6. Post-Claude Adjustments

- `_acceptance_gate` now parses only the acceptance table section.
- It reads the `Status` column cell instead of searching the whole row.
- It compares required Phase 01 acceptance IDs with Phase 04 evidence IDs.
- It skips known L1 cycles when `require_for_risk` is `[L2, L3]`; unknown risk remains gated conservatively.
- Added tests for unrelated table false positives, free-text `fail`, missing 04 evidence IDs, and L1 risk skip.
