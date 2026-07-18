# [Implementation] SAGE-FB-12 framework overlay 게이트 완화 hard-fail

Cycle-Stem: `sage-fb-12-framework-overlay-hard-fail`
Status: IMPLEMENTED_REVIEWED

## 0. Pre-Implementation Declaration

- Risk: L3 governance composition boundary.
- Required phases: 00~06.
- Review: three fresh headless rounds; Claude error/quota uses user-authorized fallback, no subagents.
- Components: SAGE engine and shipped guidance only; ChatForYou application code N/A.

## 1. Implemented Behavior

- `NON_GATE_COMPOSE_ALLOWED`와 `INDEPENDENT_ORACLE_COMPOSE_ALLOWED`를 분리했다.
- executable independent oracle 등록은 비어 있으며 framework 4종은 `GATE_BEARING_UNBACKED`로 blocked다.
- `plan_materialize`가 이미 읽은 overlay text를 `overlay_lint.scan_text`로 검사하고 hit가 있으면
  `overlay-gate-relaxation` error를 반환하며 eligible plans/receipts를 폐기한다.
- FB12 이전에 blocked 자산에 물리화된 SAGE managed block은 오류 판정을 유지한 채 마커 구간만
  원자적으로 제거한다. base와 manifest receipt는 재축복하지 않는다.
- validate default는 heuristic WARN을 유지하지만 strict는 같은 stable check id를 FAIL로 승격한다.
- CORE authoring guidance는 현재 eligible implementer 2종만 허용하고 framework/gate-bearing target 및
  explicit confirmation bypass를 stop condition으로 명시한다.
- write-guard는 framework 직접 편집을 profile/conventions/critical-domain/project-local docs로 안내한다.

## 2. Changed Surfaces

- `sage/overlay_classify.py`
- `sage/overlay_lint.py`
- `sage/overlay_materialize.py`
- `sage/commands/install.py`
- `sage/commands/sync_overlays.py`
- `sage/commands/validate.py`
- `sage/commands/doctor.py`
- `sage/commands/absorb.py`
- `sage/commands/retro.py`
- `scripts/sage_harness/hooks/runtime/hook_runtime.py`
- `templates/core/framework/AGENT_GUIDE.md`
- `templates/core/skills/sage-asset-override.md`
- `templates/core/framework/.claude/skills/sage-asset-override/SKILL.md`
- CORE agent/skill guidance and generated-artifact write-guard algorithm/spec
- overlay classify/lint/materialize/install/sync/validate/hook/doctor/retro regression tests

## 3. Verification Before Review

| Suite | Result |
|---|---:|
| overlay classify | 13 pass |
| overlay lint | 12 pass |
| overlay materialize | 16 pass |
| validate safety | 30 pass, 1 skip |
| install | 89 pass |
| generated write guard | 66 pass |
| sync overlays | 4 pass |
| overlay common | 17 pass |
| conformance + validate conformance | 20 pass |
| resources | 3 pass |
| hook runtime | 65 pass |
| Final combined Python regression | 399 pass, 1 skip |

- `git diff --check`: pass.

## 4. Checklist

- [x] Block framework composition without independent oracle.
- [x] Bind preflight and strict validation to one gate-relax scanner.
- [x] Preserve default heuristic advisory behavior.
- [x] Prove no eligible materialization/receipt on failure; allow only exact blocked-block cleanup.
- [x] Align authoring and write-guard guidance.
- [x] Complete three independent review rounds and triage.

## 5. Independent Review Round 1

- Claude attempt: unavailable due session limit (`resets 7:30am (Asia/Seoul)`).
- Fallback: fresh headless Codex session `019f6c7a-aa7e-7291-a50c-88a584f6575a` (read-only, no subagents).
- P1 `write guard advertises blocked CORE overlays`: ACCEPTED.
  - `core_overlay_hint` now exposes only `implementer-a/b`, matching `COMPOSE_ALLOWED`.
  - blocked CORE agents/skills receive an explicit unsupported message rather than an unusable path.
  - write-guard spec/tests, doctor, absorb, and the skill reference spec were aligned.
- P2 `mixed-case path emits non-canonical overlay id`: ACCEPTED.
  - hint output is derived from the normalized lowercase path and has a mixed-case regression test.
- Post-fix verification:
  - generated write guard: 66 pass.
  - absorb + doctor: 51 pass.
  - overlay classify/lint/materialize/validate safety: 72 pass, 1 skip.
  - `git diff --check`: pass.

## 6. Independent Review Round 2

- Claude attempt: unavailable due the same session limit.
- Fallback: fresh headless Codex session `019f6c81-a481-7aa1-a987-0e03a2baa1f4` (read-only, no subagents).
- P1 `mixed-case markdown extension bypasses inventory/strict while direct lookup composes`: ACCEPTED.
  - inventory and scanner now enumerate case-insensitive markdown extensions.
  - non-canonical filenames hard-fail materialization/check/sync; `.MD` relaxation has preflight and strict tests.
- P1 `pre-FB12 framework managed block survives blocked overlay error`: ACCEPTED.
  - `plan_blocked_cleanup` strips only SAGE managed blocks from blocked targets before ordinary preflight.
  - materialize/sync/SessionStart tests prove the unsafe block is removed while failure and unchanged manifest remain.
- P2 `optional/not-required/without-approval language not detected`: ACCEPTED.
  - targeted English/Korean patterns and tests were added; this remains a documented heuristic, not a semantic oracle.
- P2 `blocked CORE reference specs advertise overlays`: ACCEPTED.
  - all agent/skill reference specs and shipped CORE skill renders now match `COMPOSE_ALLOWED`.
  - a roster-wide test enforces guidance/classifier consistency.
- P2 `write-guard enforcement summary omits framework/.mcp boundaries`: ACCEPTED; spec aligned.
- Post-fix verification:
  - overlay classify/lint/materialize/validate safety: 78 pass, 1 skip.
  - install: pass.
  - sync-overlays + hook runtime: 70 pass.
  - generated write guard: 66 pass.
  - `git diff --check`: pass.

## 7. Independent Review Round 3

- Claude attempt: unavailable due the same session limit.
- Fallback: fresh headless Codex session `019f6c8d-9273-7340-a969-f3a3f253ef7c` (read-only, no subagents).
- P1 `explicit approval skip wording bypasses scanner`: ACCEPTED.
  - English approval/verification variants and Korean 승인 생략/불필요 variants were added to the shared scanner.
  - stable pattern ids are now emitted by default/strict validation.
- P1 `blocked cleanup occurs after source/version skew exits`: ACCEPTED.
  - `sync-overlays` performs exact managed-block cleanup before source identity and SAGE version checks.
  - manifest and ordinary eligible receipts remain unchanged when the command fails.
- P1 `one malformed blocked target prevents all cleanup and SessionStart passes silently`: ACCEPTED.
  - malformed/duplicate markers hard-block the affected target while independently safe blocked targets are cleaned.
  - SessionStart returns exit 2 for explicit blocked/malformed/gate-relaxation errors.
- P2 `authoring order validates stale renders before sync`: ACCEPTED.
  - guidance now uses write -> `sage sync-overlays` -> `sage validate --strict`.
- P2 `validate discards shared pattern ids`: ACCEPTED; output includes `[pattern_id] description`.
- Post-fix verification:
  - overlay lint/materialize/validate safety: 65 pass, 1 skip.
  - sync-overlays: 5 pass.
  - hook runtime, install/classify, and generated write guard: pass.
  - `git diff --check`: pass.

## 8. Closure Review 1

- Claude attempt: unavailable due the same session limit.
- Fallback: fresh headless Codex session `019f6c9a-e768-7be0-9341-0189c10fe23c`
  (read-only, no subagents).
- Verdict: NOT CLEAN, 2 P1 + 2 P2; all ACCEPTED.
- P1 `install bypasses blocked managed-block cleanup`:
  - non-force install now removes exact blocked blocks before trust/materialization preflight.
  - a path guard rejects symlink/non-regular ancestry before reading; malformed targets do not prevent safe sibling cleanup.
- P1 `natural passive/no-approval wording bypasses the scanner`:
  - stable scanner patterns now cover passive/plural skip, no/not-needed/unnecessary, turn-off, and Korean no-approval forms.
  - scanner, materialization preflight, and strict validation regressions were added.
- P2 `doctor advertises validate before sync`: repair guidance now uses
  `sage sync-overlays` -> `sage validate --strict` and has an output test.
- P2 `PDCA state/inventory stale`: review checklist, AC8 evidence, and changed-surface inventory were refreshed.

## 9. Closure Review 2

- Claude attempt: unavailable due the same session limit.
- Fallback: fresh headless Codex session `019f6ca6-7698-7302-8a8d-c73605c5c742`
  (read-only, no subagents).
- Verdict: NOT CLEAN, 1 P1; ACCEPTED.
- P1 `profile parse/runtime validation can return before install cleanup`:
  - non-force blocked-block cleanup now runs before `_installed_profile` and `team_runtime_issues`.
  - parse failure and invalid team runtime regressions prove exact cleanup while profile/manifest bytes remain unchanged.

## 10. Closure Review 3

- Claude attempt: unavailable due the same session limit.
- Fallback: fresh headless Codex session `019f6cac-0102-7191-b7fb-48cac27e3358`
  (read-only, no subagents).
- Verdict: CLEAN.
- Final verification:
  - combined relevant Python suites: 399 pass, 1 optional-dependency skip.
  - generated write guard shell suite: 66 pass.
  - install module: 89 pass.
  - `git diff --check`: pass.
