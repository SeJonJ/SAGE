# Fast Cycle urgent and convenience development protocol

Cycle-Stem: `sage-fast-cycle`
Risk Level: L3
Status: IMPLEMENTED (2026-08-11, Claude 3R APPROVED)

## 0. Prior Knowledge

- SAGE v0.9.80 already provides explicit cycle declaration, effective-max risk,
  acceptance evidence, independent review, Loop Audit, write-back, retro, and
  context snapshot gates.
- Fast Cycle is an explicitly enabled alternate protocol, not an override. It
  reduces document count and review breadth while preserving deterministic
  verification, actual risk, acceptance, final approval, and audit evidence.
- The canonical detailed design is the Obsidian wiki note
  `SAGE - Fast Cycle 긴급·편의 개발 절차 설계 (26.08.10)`.
- The engine repository is not a bootstrapped consumer project. Tests must build
  isolated consumer fixtures instead of relying on a repository-local profile.

## 1. Summary (Goal & Scope)

Implement `sage-fast-cycle` as one integrated feature:

1. Add a closed shared-profile policy for L2/L3 Fast review rounds and lenses.
2. Add deterministic `sage fast-cycle open|review|close|abort|show` commands.
3. Store strict, locked, append-only evidence in `.sage/fast_cycle.jsonl`.
4. Treat one composite 00 document as virtual phases 00 through 04 only in Fast
   mode, while preserving the standard cycle contract unchanged.
5. Bind Fast review receipts to a clean APPROVED Loop Audit run.
6. Add Claude and Codex Fast skills and conversational profile authoring prompts.
7. Keep shared Git audit data authoritative and Obsidian output derived.

## 2. Impact Analysis (Critical)

- **Profile/schema:** new shared `pdca.fast_cycle` policy and
  `knowledge_capture.fast_cycle_dashboard`; local policy weakening remains
  forbidden.
- **Runtime gate:** active Fast runs must fail closed on missing, malformed, or
  mismatched plan/audit evidence without blocking unrelated standard cycles.
- **Cycle state:** active non-terminal Fast runs prevent clear or stem changes.
- **Review:** actual risk remains authoritative; Fast level controls only the
  minimum review rounds and selected lenses.
- **Packaging:** new command, runtime module, skills, templates, and docs must be
  present in a wheel and survive `install --force`.
- **Compatibility:** existing standard 00 through 06 projects and legacy Loop
  Audit records must retain their current behavior.

## 3. Technology & Risks

- Reuse the hardened Loop Audit locking, chain, separator, and rollback model.
  Do not introduce a hand-written stale-lock takeover.
- Parse composite sections once in a shared helper. Local hooks and server
  authority must consume the same deterministic representation.
- Never infer prose quality. Validate exact metadata, headings, checklists,
  acceptance IDs, receipts, and hashes only.
- Keep actual `Risk Level` separate from `Fast-Review-Level`; L3 verification and
  acceptance rules cannot be lowered by Fast policy.
- Require level, lens count, and reason before any cycle, plan, or audit write.
- Audit write or integrity failures are non-overridable for an active Fast run.
- Vault failures are warnings after the authoritative terminal append, never a
  reason to roll back a completed audit event.

## 4. Final Conclusion & UX Guide

The implementation should make urgent work materially cheaper without making it
invisible. A developer explicitly enables Fast Cycle in the shared profile,
supplies review level, lens count, and reason, works from one composite 00 plan,
completes at least one review round with at least two configured lenses, and
still produces approved 05/06 evidence. L2 and L3 both display a warning; an
actual L3 run using L2 Fast wording additionally reports the downgrade. Warnings
do not require another confirmation and do not independently block execution.

## 5. Document Mapping (Checklist)

- [x] Phase 00 context, scope, impact, risks, and user-facing contract recorded
- [x] Profile/schema/manual validator and conversational authoring completed
- [x] Fast audit writer and CLI state machine completed
- [x] Composite parser and local/server gates completed
- [x] Loop Audit stem/lens receipts and review binding completed
- [x] Claude/Codex Fast skills and installation completed
- [x] Obsidian dashboard and Korean/English references completed
- [x] Manifest restamped and full none/claude/codex/wheel validation completed
