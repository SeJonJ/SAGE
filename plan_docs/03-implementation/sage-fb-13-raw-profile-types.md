# [Implementation] SAGE-FB-13 raw profile 위험 필드 타입 선검증

Cycle-Stem: `sage-fb-13-raw-profile-types`
Status: IMPLEMENTED_APPROVED

## 0. Pre-Implementation Declaration

- Risk: L3 governance compiler/gate hardening.
- Compound rule: invalid type can disable multiple risk levels, so highest L3 applies.
- Required phases: 00~06.
- Independent review: Claude fresh headless 3회, no subagents.
- Application components: Backend/Frontend/Desktop N/A; SAGE engine only.

## 1. File Ownership

| Owner | Files | Responsibility |
|---|---|---|
| compiler | `sage/profile_compile.py`, `schema/profile.schema.json` | raw contract + schema |
| callers | `sage/commands/generate.py`, `sage/commands/validate.py`, `sage/hook_entry.py` | controlled fail-closed handling |
| validator | `sage/profile_validate.py` | dependency-free semantic FAIL |
| QA | profile compile/validate/generate/hook/validate-safety tests | regression evidence |
| Claude reviewer | cycle docs + focused diff | fresh headless rounds 1~3 |

## 2. Checklist

- [x] Add materialization issue collector and exception.
- [x] Validate all present governed top/domain risk fields before coercion.
- [x] Wire semantic validator to the same primitive.
- [x] Tighten schema item types.
- [x] Catch compiler errors in generate/validate/hook entry.
- [x] Add compiler, direct validation, CLI, freshness, and hook tests.
- [x] Run focused and broad profile suites.
- [x] Complete three independent headless review rounds and triage (Claude quota fallback used).

## 3. Acceptance Trace

| Acceptance ID | Implementation | Planned Evidence | Status |
|---|---|---|---|
| FB13-AC1 | top risk field checks | scalar/null/bad-item compiler tests | pass |
| FB13-AC2 | optional domain field checks | scalar/null/bad-item + missing compatibility tests | pass |
| FB13-AC3 | controlled exception | `ProfileCompileError` exact path tests | pass |
| FB13-AC4 | generate pre-write fail | temp destination no-output test | pass |
| FB13-AC5 | validate + hook fail-closed | validate output + both-host hook tests | pass |
| FB13-AC6 | semantic/schema direct input | profile validator/schema tests | pass |
| FB13-AC7 | valid output compatibility | existing compiler/profile suites | pass |
| FB13-AC8 | three independent reviews; Claude unavailable fallback | Phase 05 | pass |

## 4. Baseline

- Profile-focused baseline: `108 passed, 19 deselected`.

## 5. Verification Evidence

- Review-1 rework 이후 Homebrew Python(jsonschema 포함): 5개 스위트 `186 tests`, `1 skipped` 모두 통과.
- 시스템 Python의 optional dependency/PYTHONPATH 실패는 코드 회귀와 분리했으며 동일 테스트를 의존성 충족 환경에서 재실행했다.
- `git diff --check` -> pass.

## 6. Review Rework

- Round 1 P1: domain trigger 누락을 오류로 만든 호환성 회귀를 수용했다. 필드는 선택이며 존재할 때만 검증한다.
- Round 1 P2: top/domain schema item에 비공백 패턴을 추가했다.
- Round 1 P2: YAML/JSON 동일 raw issue를 한 번만 출력하도록 dedupe했다.
- 위 세 finding은 모두 acceptance/호환성 계약과 일치해 수용했다.
- Round 2 P2: semantic validator의 non-mapping `risk` 중복 FAIL을 단일 소유자로 정리했다.
- Round 2 P2: domain trigger missing을 허용하는 positive schema regression을 추가했다.
- Round 3: P0/P1/P2 0, `CLEAN`; 추가 수정 없음.

## 7. Changed Files

- `sage/profile_compile.py`
- `sage/profile_validate.py`
- `sage/commands/generate.py`
- `sage/commands/validate.py`
- `sage/hook_entry.py`
- `schema/profile.schema.json`
- five focused test modules
