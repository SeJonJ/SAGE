# [Expert Review] SAGE-FB-08 서버측 PR-diff 권위 게이트와 attestation

Cycle-Stem: `sage-fb-08-server-authority-attestation`
Risk Level: L3
Review-Mode: Claude fresh headless, read-only, no subagents
External Verdict: ADVISORY
Final Status: APPROVED

## 1. Review Evidence

| Round | Session | Resolution |
|---|---|---|
| 1 | `7103906f-8bd3-484c-bb8c-937e92496f5a` | branch leaf binding retained; attestation and nonce limits documented |
| 2 | `637f2d5c-1597-4b9a-a373-8e0b6bc1ebe1` | authority/local risk declaration parser drift reproduced and fixed |
| 3 | `a01c9b7a-ee27-483b-9650-bd836aa264ca` | PR-authored reviewer evidence trust boundary documented; loader hardening deferred |
| Closure | `ead09722-14af-4538-b8b0-155761c95973` | FB08 CLEAN, overall ADVISORY |

## 2. Acceptance

FB08-AC1 through FB08-AC9 are PASS. The protected adapter reads base/head Git objects without executing PR code,
classifies both policies and both rename/delete sides, requires exact L3 phase evidence, and emits a claim-bound,
short-lived HMAC attestation. Local override and acceptance waiver are excluded from the authority decision.

## 3. Verification

- Authority and local gate parity aggregate: 125 passed.
- Full Python suite: 1,316 passed, 1 skipped.
- Official hook suite: `ALL HOOK TESTS PASS`.
- Static checks: PASS.

## 4. Residual Decisions

- Phase 05 is PR-authored structural evidence. A separately protected reviewer issuer and authenticated reviewer identity
  are future architecture work.
- The signed nonce is correlation, not a consumed replay token. Replay is bounded by exact claims and expiry, not an
  external replay store.
- With no local risk declaration, local and authority paths may report different provenance. Authority still classifies
  the protected diff directly and never lowers that risk, so this is an intentional trust-model asymmetry.
- Protected secret custody, pinned workflow source, required check, and branch protection remain FB09 deployment work.

## 5. Decision

The closure ADVISORY concerns external identity and deployment policy, not a bypass in the delivered pure authority
engine. The engine acceptance is complete, so FB08 is APPROVED while FB09 remains separately blocked.
