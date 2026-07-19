# [Base Plan] SAGE-FB-04 Host Model Discovery and Routing

Cycle-Stem: `sage-fb-04-host-model-routing`
Risk Level: L3

## 1. Problem

SAGE currently exposes a component `model` work-intensity tier and cross-review effort, but it neither discovers
host model candidates nor records an actual host model per component. Cross-review deliberately inherits the peer
CLI default, so a profile interview cannot preserve the reviewer host/model the user approved.

## 2. Boundary

- Discover model candidates without claiming unverified account entitlement.
- Preserve the legacy component work-intensity tier.
- Add host-specific component model selections and an explicit cross-reviewer host/model.
- Validate the static profile contract and diagnose local host availability separately.
- Do not auto-switch hosts, probe paid model endpoints, or persist credentials/account metadata.

## 3. Impact

- SAGE CLI/profile/doctor/review/roster/bootstrap docs and tests: affected.
- ChatForYou Backend/Frontend/Desktop source: N/A.

