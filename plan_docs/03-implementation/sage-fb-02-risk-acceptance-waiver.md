# [Implementation] SAGE-FB-02 위험도별 acceptance와 명시적 L3 waiver

Cycle-Stem: `sage-fb-02-risk-acceptance-waiver`
Status: IMPLEMENTED_REVIEW_COMPLETE

## 0. Pre-Implementation Declaration

- Risk: L3 governance gate and explicit waiver authority boundary.
- Compound rule: profile policy, report blocking, local audit authority, CLI mutation이 교차하므로 최고 L3 적용.
- Required phases: 00~06.
- Review: 개발 완료 전 Claude 3회; Claude 오류/사용량 제한 시 매 회 fresh read-only headless session, no subagents.
- Components: SAGE engine only. ChatForYou Backend/Frontend/Desktop N/A.
- References: Phase 00~02, 요구사항 SSOT, existing acceptance/override/loop audit implementations.

## 1. Planned Files and Ownership

- `scripts/sage_harness/hooks/runtime/acceptance_waiver.py`: append-only grant/use/revoke parser and invariants.
- `sage/commands/acceptance_waiver.py`, `sage/cli.py`: explicit grant/list/revoke user contract.
- `scripts/sage_harness/hooks/runtime/hook_runtime.py`: audit snapshot injection and fail-closed use recording.
- `scripts/sage_harness/hooks/pre_implementation_gate_core.py`: risk-specific acceptance result and exact waiver consumption.
- `scripts/sage_harness/hooks/runtime/messages.py`: residual-evidence warning and audit failure messages.
- `sage/profile_validate.py`, `schema/profile.schema.json`, `templates/project-profile.yaml`: closed profile contract and migration.
- `sage/commands/doctor.py`: legacy mode의 안전 승격과 migration guidance.
- `docs/sage_harness/hooks/pre-implementation-gate.md`, `templates/core/framework/**`: operator and agent guidance.
- `scripts/sage_harness/hooks/tests/test_acceptance_waiver.py`: audit and CLI domain regressions.
- existing gate/runtime/profile/doctor/message/CLI tests: integration and compatibility regressions.

## 2. Acceptance Trace and Checklist

- [x] FB02-AC1: L2 advisory, L3/unknown enforce defaults.
- [x] FB02-AC2: closed schema and semantic validation.
- [x] FB02-AC3: exact cycle stem + exact required acceptance ID only.
- [x] FB02-AC4: confirmation, reason, scope, remaining evidence required.
- [x] FB02-AC5: waived L3 NOT TESTED remains WARN/residual, never PASS.
- [x] FB02-AC6: FAIL and invalid/expired/revoked/duplicate/malformed/wildcard records block.
- [x] FB02-AC7: append-only grant/use/revoke with shared hook/CLI implementation.
- [x] FB02-AC8: legacy enforce 보존, legacy advisory/off 안전 승격과 migration guidance.
- [x] FB02-AC9: three independent review rounds and finding triage.

## 3. Verification Plan

- Focused unit tests for waiver audit, acceptance gate, runtime adapter, profile/schema, doctor, CLI, and messages.
- Full Homebrew Python unittest suite.
- Official `scripts/sage_harness/hooks/tests/run-all.sh`.
- `git diff --check`.

## 4. Implemented Behavior

- `report_gate_by_risk`는 L2 advisory/L3 enforce만 허용하고 unknown을 L3 enforce로 처리한다. 런타임도
  validate 우회 상황에서 L3 advisory 설정을 enforce로 올려 profile-only downgrade를 차단한다.
- legacy `report_gate_enforce: enforce`는 기존처럼 전 위험도 enforce다. legacy `advisory`/`off`는 L3를
  advisory/off로 낮추지 않고 L2 advisory/L3 enforce로 안전 승격하며 validate/doctor가 migration을 안내한다.
- `sage acceptance-waiver grant`는 profile의 exact Phase 01 문서를 선택해 required acceptance ID인지 확인한 뒤
  confirmation/reason/scope/remaining evidence/24h 이하 TTL을 가진 self-asserted local grant를 append한다.
- `.sage/acceptance-waivers.jsonl`은 grant/use/revoke를 공유 parser로 검사한다. malformed JSON, duplicate ID,
  conflicting active grant, unknown/out-of-lifetime/post-revoke use, symlink parent/leaf를 invalid로 판정한다.
  root directory fd에서 `.sage`를 `openat + O_NOFOLLOW`로 고정하고 directory flock으로 read/append를
  직렬화해 상위 디렉터리 교체 경쟁과 동시 최초 grant의 부분 관측을 차단한다.
- pure gate는 exact L3 `NOT TESTED` 한 건에만 active grant를 결속한다. `FAIL`, unknown risk, wrong cycle/ID,
  inactive/invalid audit은 계속 BLOCK하며 waiver 결과는 `warn_report_with_l3_waiver`와 residual evidence로 남는다.
- shared adapter는 report write 허용 전에 use를 append한다. append/재검증 실패는
  `block_report_waiver_audit_failure`로 전환한다. Claude/Codex는 같은 adapter와 audit SSOT를 사용한다.
- 동시 grant 충돌은 post-append 재검증으로 감지하고 해당 writer의 grant를 보상 revoke한다. 충돌 상태의 audit은
  명시적 revoke로 복구할 수 있으나 malformed/duplicate 기록은 자동 복구하지 않고 fail-closed한다.
- 자체 closure 검토에서 `.sage` ancestor swap 경쟁을 재현해 secure directory-fd read/write로 보완했다.
  이 과정에서 기존 concurrency test가 worker 예외를 놓치고 있음을 발견해 결과 수와 unexpected exception을
  명시 검증하도록 강화했다. Audit/CLI focused module은 `14 tests` PASS다.
- broad external review에서 기존 `sage override --gate all`이 acceptance FAIL과 waiver audit/core runtime
  fail-closed BLOCK까지 우회함을 재현했다. `block_report_without_acceptance`,
  `block_report_waiver_audit_failure`, `block_gate_runtime_error`는 generic override 비대상으로 고정하고,
  일반 L3 운영 override는 기존대로 유지했다. Adapter regression을 포함한 override module `24 tests`가 PASS다.

## 5. Independent Review Round 1

- Reviewer: Claude headless session `a27adb78-2379-4a83-a283-92ebcae5ad80` (`--effort medium`, read-only).
- 수용: waiver 전용 테스트가 공식 `run-all.sh`에서 누락됨. Section 44로 등록했다.
- 수용: `inf`/`infh` TTL이 `OverflowError`를 노출함. domain error로 정규화하고 회귀 테스트를 추가했다.
- 수용: legacy advisory/off가 L3를 낮출 수 있음. L3 enforce로 안전 승격하고 테스트와 안내를 수정했다.
- 수용: 동시 grant 충돌 후 append-only audit 복구 경로가 없음. 보상 revoke와 명시적 conflict revoke를 추가했다.
- 기각: `waiver.enabled` 기본 true. 사용자가 모든 기능 활성화를 확정했으며 이 값만으로 권한이 생기지 않고
  exact explicit grant가 별도로 필요하므로 현재 기본을 유지한다.

## 6. Independent Review Round 2

- Reviewer: Claude headless session `392d7e39-bec3-41fb-915e-3fbd77de64f7` (`--effort medium`, read-only).
- 수용(P1): `acceptance_waiver.py`가 `hook_runtime_hash`에서 누락됨. shared runtime 추적과 pinned test에 추가했다.
- 수용(P2): grant/revoke의 audit I/O 오류가 traceback으로 노출됨. `OSError`를 CLI reject 결과로 정규화했다.
- 수용(P2): legacy enforce의 declared L2 동작이 테스트되지 않음. L2 unresolved acceptance BLOCK 회귀를 추가했다.
- 범위 분리: `test_install_transaction.py`의 official harness 등록은 FB-02 결함이 아니며 전체 후속 회귀 단계에서 처리한다.

## 7. Independent Review Round 3

- Reviewer: Claude headless session `0b9276e5-ef21-4fd9-aae3-03eb96dade94` (`--effort medium`, read-only).
- 수용(P1): `require_for_risk`에서 L3를 제거하면 acceptance gate 전체를 우회할 수 있음. runtime L3 floor와
  semantic validation FAIL, 두 회귀 테스트를 추가했다.
- 수용(P2): waiver test가 외부 `PYTHONPATH`에 의존함. test module이 REPO를 직접 `sys.path`에 추가해
  plain Python 실행과 official harness 모두 동일하게 동작하도록 수정했다.
- Round 3 수정이 있으므로 별도 fresh headless 세션으로 closure review를 추가한다.

## 8. Independent Review Round 4 (Closure Attempt)

- Reviewer: Claude headless session `69490af8-6478-4cdd-81e2-eec9240b1869` (`--effort medium`, read-only).
- 수용(P1): list 내부 unhashable 값과 non-list status 설정이 core 예외를 일으켜 host에서 exit 1 fail-open될 수
  있음. 문자열만 정규화하고 L3/FAIL/NOT TESTED engine floor를 합성했다.
- 수용(P2): L3 floor 테스트가 unknown risk를 사용해 floor를 실제 검증하지 않음. Phase 00 known-L3 증거를
  넣어 floor 제거 mutation을 실패시키는 테스트로 교정했다.
- 방어 강화: 공용 adapter가 예상 밖 core 예외를 `block_gate_runtime_error` exit 2로 변환하고 양 host가 같은
  message SSOT를 사용하도록 했다.
- Round 4가 clean이 아니므로 수정 후 새 closure session을 추가한다.

## 9. Independent Review Round 5 (Closure Attempt)

- Reviewer: Claude headless session `746aad81-df6f-4d6c-8447-181578d96cf7` (`--effort medium`, read-only).
- 이전 P1/P2와 mutation-killing tests, hash restamp는 모두 폐쇄 확인됐다.
- 수용(P1): `statuses`에 `SKIPPED` 같은 값을 추가하면 required acceptance가 resolved로 처리됨. schema를
  canonical 네 상태로 닫고 validator가 extra status를 FAIL하며 runtime은 PASS/N/A 외 전부 unresolved로
  승격하도록 수정했다.
- Round 5가 clean이 아니므로 수정 후 새 closure session을 추가한다.

## 5. Verification Before Independent Review

- Focused gate/runtime/profile/CLI/doctor/install aggregate: 487 tests, PASS.
- Full Homebrew Python suite: 1,223 tests, PASS, 1 skipped.
- Official `run-all.sh`: `ALL HOOK TESTS PASS`.
- `git diff --check`: PASS.

## 10. Broad External Review Round 1

- Reviewer: Claude headless session `7103906f-8bd3-484c-bb8c-937e92496f5a` (correctness/fail-closed/data integrity).
- 수용(P1): generic `gate=all` override가 acceptance FAIL 및 audit/runtime fail-closed 결과를 통과시켰다.
  acceptance별 명시 waiver와 충돌하므로 세 안전 차단 key를 non-overridable로 고정하고 adapter regression을 추가했다.
- 보류(P3): acceptance waiver WARN과 loop-audit WARN이 동시에 발생할 때 첫 WARN만 렌더되는 문제는 차단 결과를
  약화하지 않는다. 후속 broad review와 함께 출력 계약 변경 필요성을 판단한다.

## 11. Broad External Review Round 3

- Reviewer: Claude headless session `a01c9b7a-ee27-483b-9650-bd836aa264ca` (compatibility/packaging/operations).
- 기각(P2): malformed audit의 자동 archive/rotation은 승인된 append-only 정본 모델 밖이다. 현재 설계대로
  corruption은 fail-closed하고 VCS 복원 또는 운영자 수리를 요구한다.
- 수용(P3 closure): Round 1에서 보류한 복수 advisory 누락을 수정했다. BLOCK 우선순위는 유지하고 모든 WARN
  reason을 첫 결과에 병합해 acceptance residual과 loop-audit 미충족을 함께 표시한다. 관련 `61 tests`가 PASS했다.
