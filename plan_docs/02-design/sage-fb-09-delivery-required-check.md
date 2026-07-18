# [Design] SAGE-FB-09 Delivery and Required Check Proof

Cycle-Stem: `sage-fb-09-delivery-required-check`

## Delivery Sequence

1. Complete all SAGE code/reviews/tests and let the user create the SAGE commit.
2. Publish that commit and verify `git ls-remote` returns the exact 40-hex SHA.
3. Replace every inactive workflow pin with reviewed immutable SHAs; no branch/tag pin.
4. Review the workflow three times before activation, especially `pull_request_target`, checkout credentials, and
   the rule that PR head content is data only and is never executed.
5. Create protected environment and attestation secret through user-authorized GitHub settings/API.
6. Commit/publish the ChatForYou workflow, open/refresh a test PR, and capture positive and negative run evidence.
7. Configure branch protection/ruleset to require exact check `sage-authoritative-gate` from the expected app source.
8. Read protection back and verify merge behavior.

## Fail-Closed Preconditions

- Do not activate `PIN_*` placeholders or a mutable SAGE ref.
- Do not execute PR head scripts under `pull_request_target`.
- Do not print or persist `SAGE_ATTESTATION_KEY`.
- Do not claim branch protection from local workflow syntax alone.
- If the expected check has never reported on the branch/PR, do not configure a guessed context/app binding.

## Existing Reusable Asset

`templates/core/framework/docs/agent/sage-authoritative-gate.yml.example` remains inactive until the SAGE commit,
third-party action pins, environment, and secret are available. FB08's authority inspect/attest/gate implementation is
the execution engine; FB09 should not duplicate it.

