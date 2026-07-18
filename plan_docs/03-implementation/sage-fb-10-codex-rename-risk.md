# [Implementation] SAGE-FB-10 Codex rename 목적지 L3 분류 우회 차단

Cycle-Stem: `sage-fb-10-codex-rename-risk`
Status: COMPLETE

## 0. Pre-Implementation Declaration

- Risk: L3, governance gate bypass fix.
- Compound rule: source path, destination path, and added content 중 최고 위험도를 적용한다.
- Required phases: 00~06.
- Independent review: Claude fresh headless session 3회 필수.
- Application impact: Backend/Frontend/Desktop N/A; SAGE Codex runtime only.

## 1. File Ownership

| Owner | Files | Responsibility |
|---|---|---|
| Codex host implementer | `scripts/sage_harness/hooks/runtime/io_codex.py` | rename-aware extraction |
| Codex host QA | `scripts/sage_harness/hooks/tests/test_hook_runtime.py` | parser and classification regression |
| Claude independent reviewer | staged/uncommitted diff + Phase 00~04 | fresh headless review rounds 1~3 |

## 2. Implementation Checklist

- [x] Replace single content cursor with source/destination content target tracking.
- [x] Preserve orphan destination marker fail-safely.
- [x] Add source+destination extraction test.
- [x] Add destination filename-L3 classification test.
- [x] Add rename content-L3 classification test.
- [x] Run targeted and broader hook tests.
- [x] Backfill destination content when Move follows hunk content (Claude R1 P1-1).
- [x] Preserve equal-rank filename/content trigger provenance (Claude R1 P1-2).
- [x] Add noncanonical ordering, L0/unmatched source, reset, and duplicate Move tests.
- [x] Record content-L3 provenance on an already filename-L3 change (Claude R2 P2).
- [x] Keep operator reason aligned with its representative file (Claude R2 P2).
- [x] Add `decide()` BLOCK regression tests (Claude R2 P2).
- [x] Defer L0/L3 overlap precedence to FB-07 and narrow AC2 contract (Claude R2 P2).
- [x] Complete Claude review rounds 1~3 and triage findings.

## 3. Acceptance Trace

| Acceptance ID | Implementation Task | Planned Evidence | Status |
|---|---|---|---|
| FB10-AC1 | rename source/destination normalization | `test_rename_keeps_source_destination_and_added_content` | pass |
| FB10-AC2 | destination L3 gate classification | `test_rename_destination_l3_glob_controls_compound_risk` | pass |
| FB10-AC3 | content mirrored to both paths | extraction + content-L3 tests | pass |
| FB10-AC4 | orphan destination retention | `test_orphan_move_marker_still_preserves_destination` | pass |
| FB10-AC5 | existing extraction regression | hook runtime + pre-gate/runtime smoke suites | pass |
| FB10-AC6 | three independent Claude reviews | Phase 05 evidence + closure review | pass |

## 4. Verification Evidence

Baseline before implementation:

- `pytest -q scripts/sage_harness/hooks/tests/test_hook_runtime.py -k TestExtractChangesCodex`
  -> `2 passed, 53 deselected`.

After implementation:

- `pytest -q scripts/sage_harness/hooks/tests/test_hook_runtime.py`
  -> `59 passed`.
- `pytest -q scripts/sage_harness/hooks/tests/test_pre_implementation_gate.py scripts/sage_harness/hooks/tests/test_runtime_smoke.py`
  -> `75 passed, 24 subtests passed`.
- `git diff --check` -> pass.

After Claude R2 rework:

- `pytest -q scripts/sage_harness/hooks/tests/test_hook_runtime.py scripts/sage_harness/hooks/tests/test_pre_implementation_gate.py scripts/sage_harness/hooks/tests/test_runtime_smoke.py scripts/sage_harness/hooks/tests/test_messages.py`
  -> `151 passed, 24 subtests passed`.
- `git diff --check` -> pass.

After Claude R1 rework:

- `pytest -q scripts/sage_harness/hooks/tests/test_hook_runtime.py`
  -> `63 passed`.
- `pytest -q scripts/sage_harness/hooks/tests/test_pre_implementation_gate.py scripts/sage_harness/hooks/tests/test_runtime_smoke.py`
  -> `75 passed, 24 subtests passed`.
- `git diff --check` -> pass.

## 5. Changed Files

- `scripts/sage_harness/hooks/runtime/io_codex.py`
- `scripts/sage_harness/hooks/tests/test_hook_runtime.py`
- `scripts/sage_harness/hooks/pre_implementation_gate_core.py`

## 6. Claude Review Triage

| Round | Finding | Decision | Reason / Action |
|---|---|---|---|
| R1 | P1 Move-after-hunk destination content loss | accept | parser order dependency can downgrade content-L3; backfill required |
| R1 | P1 equal-rank source masks filename-L3 destination | accept | strict `>` loses hard-block provenance; aggregate same-rank triggers |
| R1 | P2 dead conditional | accept | simplify unconditional append |
| R1 | P2 missing ordering/compound tests | accept | add load-bearing regression matrix |
| R2 | P2 L0-first can swallow overlapping L3 destination | defer | valid pre-existing contract; explicitly owned by FB-07, AC2 narrowed |
| R2 | P2 filename-L3 same change drops content-L3 provenance | accept | preserve complete security trigger provenance |
| R2 | P2 merged reason misattributes another file's trigger | accept | union gate triggers but keep representative reason path-local |
| R2 | P2 no `decide()` BLOCK test | accept | add filename-L3 and content-L3 hard-block tests |
| R3 | P1 01 heading is invisible to acceptance parser | accept | rename heading to include `Acceptance Matrix` |
| R3 | P2 noncanonical 04 status + stale counts + 00 boundary | accept | normalize status and synchronize evidence/boundary |
| R3 | P2 dead risk-membership conditional | accept | simplify to unconditional L3 assignment after earlier returns |
| Closure | no P0/P1; all R3 findings fixed | accept | CLEAN; independent probes and acceptance parser passed |
