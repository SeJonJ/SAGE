# [Base Plan] SAGE 10-f Bilingual Reference Documentation and Hash Synchronization

Cycle-Stem: `sage-bilingual-reference-hash-sync`
Risk Level: L1
Status: COMPLETE

## 1. Context

SAGE 10-d made the README, documentation index, and quickstart bilingual, but left the five
user-facing references in Korean only. English users could install SAGE but could not independently
use the CLI, configure a profile, troubleshoot failures, or inspect architecture and artifact
ownership.

Maintaining translations by convention alone also allows an English mirror to become silently
stale when its Korean source changes.

## 2. Scope

- Add English mirrors for `cli-reference`, `profile-reference`, `troubleshooting`, `ARTIFACTS`, and
  `ARCHITECTURE`.
- Add visible reciprocal language links and make both English indexes reach every English mirror.
- Stamp each English mirror with the normalized SHA-256 of its Korean source.
- Fail documentation tests with the target mirror and replacement marker when a source changes.
- Distinguish the engine source path `templates/core/framework/docs/agent/` from the installed target
  path `docs/agent/`.

Out of scope: translating `templates/core/framework/docs/`, creating a restamp CLI, or attempting to
machine-evaluate translation quality.

## 3. Locked Decisions

- Korean documents remain the authoring sources; English documents are reviewed mirrors.
- Hashing decodes UTF-8 and normalizes CRLF and CR to LF before SHA-256 so checkout line endings do
  not create false STALE results.
- The marker is the first line of each English mirror and appears exactly once:
  `<!-- sage-doc-source: <source>.md sha256:<64 lowercase hex> -->`.
- Tests report the complete replacement marker. No product CLI is added for five document pairs.
- A passing hash proves synchronization was acknowledged, not that the translation is semantically
  correct; human review remains responsible for translation quality.

## 4. Done Criteria

1. Five Korean/English pairs exist with visible reciprocal links.
2. `README.en.md` and `docs/README.en.md` link only to English versions of these references.
3. Changing only a Korean source fails `test_documentation.py` and identifies the mirror and new
   marker.
4. LF and CRLF source checkouts produce the same digest.
5. Local links across onboarding and all ten reference documents resolve.
6. Source distribution, full hook regressions, and wheel smoke pass.
