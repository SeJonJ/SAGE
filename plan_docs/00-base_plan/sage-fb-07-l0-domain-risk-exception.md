# [Base Plan] SAGE-FB-07 L0 Domain Risk Exception

Cycle-Stem: `sage-fb-07-l0-domain-risk-exception`

Risk Level: L3

## Context

The risk core returns immediately on `l0_pass_globs`. Consequently a broad asset rule such as `**/*.png` masks a
more specific WebRTC/Game domain path that the profile compiler already materialized as L3.

## Goal

Keep ordinary assets at L0 while allowing explicit higher-risk domain paths to bypass the L0 early return and reach
their configured L1/L2/L3 rule.

## Safety Boundary

An L0 exclusion is not a risk value. It is valid only when the exact same glob is also present in a higher-risk path
list. Domain `path_globs` satisfy this automatically through profile compilation. An orphan exclusion fails validation.

## Impact

- SAGE risk compiler/schema/validator/hook core: affected.
- ChatForYou Backend/Frontend/Desktop application source: N/A.

