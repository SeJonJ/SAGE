# [Base Plan] Documentation restructure and Windows-native write guard

Cycle-Stem: `sage-docs-windows-native`
Risk Level: L3
Status: IN_PROGRESS

## 1. Context

SAGE's 495-line README mixes onboarding, CLI reference, profile configuration, and troubleshooting.
At the same time, the only remaining native hook, `generated-artifact-write-guard.sh`, is launched
through bare `bash` by `run_hook.py`. On Windows this can exit 126/127 and be treated by the host as
a non-blocking hook error, silently disabling generated-artifact protection.

## 2. Goal

- Port the write guard to Python and remove the runtime bash dispatch.
- Make write-guard load or execution failures fail closed with exit 2.
- Add an installed-path smoke check so `sage validate` detects a non-functional guard.
- Make hook output safe on Windows legacy console encodings.
- Split reference material out of README and publish concise Korean and English onboarding paths.

## 3. Locked Delivery Decision

This cycle ships once after all 10-d work is complete. There is no intermediate bash hotfix release.
The former hotfix acceptance requirements are implemented directly in the final Python architecture:
Windows guarded writes exit 2, internal failures exit 2 with diagnostics, and no bash process is
required by the installed write-guard path.

## 4. Scope

- `generated-artifact-write-guard`: native shell form to Python `core_adapter`
- `sage-hook`, shared hook runtime, install/generate/validate manifests and tests
- Windows doctor output and validation execution smoke
- cp949-safe hook output
- README, docs index, CLI/profile/troubleshooting references, English quickstart

Out of scope: translating all contributor references, changing hook policy boundaries, supporting
new overlay-eligible assets, or changing unrelated shell-based developer scripts.

## 5. Done Criteria

1. Both host runtimes block guarded paths with exit 2 without invoking bash.
2. Malformed input remains a non-target pass, while core load/execution failures block with diagnostics.
3. `sage validate` executes the installed write guard and rejects results outside its 0/2 contract.
4. Doctor and README describe the actual Windows-native hook path.
5. Stop/report output does not crash when stdout uses cp949.
6. Each root README is at most 200 lines and links to separated CLI, profile, and troubleshooting references.
7. Korean and English README, docs index, and quickstart pairs exist with reciprocal language links.
8. Full hook suite, wheel smoke, manifest drift checks, and independent L3 review pass.
