# [Implementation] SAGE-FB-05 Codex CORE Skill Installation Scope

Cycle-Stem: `sage-fb-05-codex-skill-scope`
Risk Level: L3

## 1. Ownership

- Scope resolution and installation: `sage/commands/install.py`
- Receipt contract: `schema/manifest.schema.json`, install manifest validation
- Static/runtime diagnostics: `sage/commands/validate.py`, `sage/commands/doctor.py`
- Guidance: framework agent docs, README, generated onboarding document
- Verification: install/validate/doctor focused tests plus official/full harness suites

## 2. Checklist

- [x] Add failing scope, receipt, duplicate, drift, and onboarding tests.
- [x] Implement explicit scope resolution and selected-root transaction coverage.
- [x] Stamp and validate CORE skill receipts.
- [x] Add validate and doctor diagnostics.
- [x] Update framework/install/onboarding documentation.
- [x] Run focused and official deterministic verification.
- [x] Complete three independent Claude reviews and triage findings.

## 3. Acceptance Trace

FB05-AC1 through FB05-AC10 are tracked in the matching Phase 04 analysis document after implementation.

## 4. Verification Evidence

- Scope/receipt/install focused regressions PASS, including explicit-scope failure and scope switching.
- Doctor/validate focused aggregate: 69 tests PASS, 1 skipped.
- Write guard: 66 cases PASS.
- Project-local symlink escape and late-failure rollback regressions PASS.
- Official harness: `ALL HOOK TESTS PASS`.

## 5. Broad External Review Round 2

- Reviewer: Claude headless session `637f2d5c-1597-4b9a-a373-8e0b6bc1ebe1` (security/TOCTOU/adversarial input).
- 수용(P3): legacy cleanup marker의 `isfile/read_text`가 symlink를 따라가 외부 SAGE marker를 가리키는 사용자
  동명 skill directory를 삭제할 수 있었다.
- 수정: cleanup 대상 directory와 `SKILL.md`를 `lstat` 기준 실제 directory/regular file로 제한했다.
  Symlink marker 보존과 기존 Claude/Codex legacy cleanup regressions가 PASS했다.

## 6. Broad External Review Round 3

- Reviewer: Claude headless session `a01c9b7a-ee27-483b-9650-bd836aa264ca`.
- 수용(P2): global scope install이 repo destination lock만 잡아 서로 다른 저장소에서 같은
  `$CODEX_HOME/skills`를 동시에 갱신할 수 있었다.
- 수정: global scope는 destination과 resolved shared skills root lock을 정렬된 순서로 함께 획득한다.
  Shared-lock contention, global receipt, transaction aggregate `22 tests`가 PASS했다.
- 기각(P3): duplicate surface precedence는 Codex runtime의 로드 증거 없이 추정하지 않는 것이 Phase 02 계약이다.
  Doctor는 모든 live path와 conflict를 표시하고 실제 winner는 ambiguous로 유지한다.
