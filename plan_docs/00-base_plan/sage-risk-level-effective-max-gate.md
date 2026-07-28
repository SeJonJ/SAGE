# [Base Plan] SAGE 10-c Risk Level Enforcement and Effective-Max Reconciliation

Cycle-Stem: `sage-risk-level-effective-max-gate`
Risk Level: L3

## 0. Prior Knowledge

| Type | Source | Key Takeaway |
|---|---|---|
| Repository | `plan_docs/enhancement-backlog.md` EH-5 | Phase 00 declaration enforcement and implementation-time reconciliation remain open. |
| Repository | `pre_implementation_gate_core.py::_cycle_risk` | Declared, injected, and bound Phase 00-05 tiers are already reduced with `max()`; the backlog's first-match description is stale. |
| Repository | `hook_runtime.build_snapshot` | `snapshot.cycle_risk` is consumed but has no production producer, so it does not preserve prior detected edits. |
| Vault | `SAGE - write-back 심층 노트 설계 + required_structure 배선(26.07.14)` | Phase 00 is the durable tier used by acceptance and knowledge write-back. |
| Conversation | 2026-07-27 scope review | Prefer a write-time invariant over a new risk ledger: block a higher-risk edit until Phase 00 is raised. |

Knowledge scan status: N/A. This framework checkout intentionally has no
`sage/project-profile.yaml`; repository and paired-vault sources were inspected
directly.

## 1. Summary

Promote enhancement backlog EH-5 to roadmap section 10-c and close two live
governance gaps:

1. A cycle can currently proceed with a missing or placeholder Phase 00
   `Risk Level`.
2. A source edit can be classified above the Phase 00 tier without forcing the
   durable declaration to be raised.

The change extends the existing `pre-implementation-gate`. It does not add a new
hook, profile option, schema field, or risk ledger.

## 2. Impact Analysis

- Pure gate core: add exact same-cycle Phase 00 selection, declaration validation,
  and under-declaration blocking.
- Runtime messages: expose a deterministic repair instruction for invalid and
  stale Phase 00 risk.
- Runtime override policy: declaration and reconciliation failures cannot be
  bypassed by a generic emergency override.
- Hook tests: cover missing, placeholder, malformed, duplicate, cross-stem,
  under-declared, repair-only, and retry behavior.
- Framework guidance: replace the remaining "best effort = EH-5" wording with the
  enforced contract.
- Existing `_cycle_risk`, acceptance, report-approval, waiver, audit, and
  cycle-binding behavior must remain unchanged.

The current uncommitted 10-b active-host work is outside this cycle. Files already
modified by 10-b must not be overwritten or normalized as part of 10-c.

## 3. Locked Decisions

### 3.1 Phase 00 is the durable accumulator

For every governed write, the effective current tier is the existing
`classify_risk(event, profile)` result, which already applies
`max(detected, user-declared)`. If that tier exceeds the selected Phase 00 tier,
the write is blocked. The host must raise Phase 00 in a separate write and retry.

This turns Phase 00 into a monotonic, cross-session maximum without introducing
state that can expire, split by host, or lose cycle identity.

### 3.2 Enforcement boundary

- A write containing only the bound Phase 00 document is repair-capable and is
  not blocked by the declaration gate.
- Any Phase 01-06 write, or any L1/L2/L3 non-phase write, requires exactly one
  valid declaration in the bound Phase 00 document.
- A patch mixing Phase 00 repair with governed source or later-phase writes is
  not repair-only and is blocked against the pre-write snapshot. Repair and retry
  must be separate operations.
- Missing, placeholder, malformed, multiple, unreadable, or ambiguous Phase 00
  declarations fail closed.
- Existing generic override grants cannot bypass either 10-c block; the only
  recovery is the deterministic Phase 00-only repair path.

### 3.3 Parser and compatibility

Reuse `_parse_risk_declaration` and the existing non-fenced-line parser rather than
creating a second risk grammar. The template's canonical spelling remains
`Risk Level: L1|L2|L3`; currently accepted emphasized and legacy labels remain
read-compatible.

### 3.4 Existing effective-max behavior

Keep `_cycle_risk` as the maximum of user-declared tier, injected snapshot tier,
and every valid same-cycle Phase 00-05 declaration. Add explicit regression teeth
for a lower session declaration plus a higher Phase 00 declaration.

## 4. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Phase 00 cannot be repaired because its own invalid state blocks the edit | Exempt Phase 00-only writes from this new check. |
| Atomic Phase 00 + source patch reads stale snapshot | Deliberately block and require two writes. |
| A different cycle's valid 00 satisfies the gate | Select through existing exact `cycle_binding` only. |
| Parser drift between local gate and CI authority | Reuse `_parse_risk_declaration`. |
| Existing completed legacy cycles lack the field | Enforcement applies when the cycle next performs governed work; repair path remains open. |
| Shell or external-process writes bypass PreToolUse | Preserve the current honest-host boundary; server authority remains the full-diff backstop when enabled. |
| New policy weakens report or acceptance enforcement | L3 independent review plus existing full-suite and wheel gates. |

## 5. Non-goals

- `components[].risk_level` or component-local policy.
- Automatic mutation of Phase 00.
- A persistent risk ledger or per-session risk file.
- Expanding hook coverage to arbitrary shell writes.
- Changing risk glob precedence or content classification.
- Changing profile schema, hook registration, CI authority, or branch protection.

## 6. Phase Mapping

- Phase 01: behavioral requirements and acceptance evidence.
- Phase 02: helper contracts, decision order, and failure semantics.
- Phase 03: implementation and unit tests after ownership is recorded.
- Phase 04: design-gap, adapter parity, and acceptance evidence analysis.
- Phase 05: independent L3 review with final verdict.
- Phase 06: written only after Phase 05 APPROVED.
