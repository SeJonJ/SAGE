# [Analyze] SAGE-FB-02 위험도별 acceptance와 명시적 L3 waiver

Cycle-Stem: `sage-fb-02-risk-acceptance-waiver`
Status: ANALYZED_REVIEW_COMPLETE

## 1. Design to Implementation Gap

| Design Item | Implementation | Gap |
|---|---|---|
| L2 advisory/L3 enforce/unknown enforce | core fixed default plus closed profile validation | none |
| exact cycle + required acceptance ID | CLI exact Phase 01 selection and core exact audit matching | none |
| explicit user fields and 24h cap | required CLI args plus library invariants | local confirmer is self-asserted, as designed |
| grant/use/revoke append-only audit | one shared stdlib runtime module with root-fd/openat confinement and directory flock | same-OS-user history rewrite resistance is FB-08 scope |
| FAIL never waived, NOT TESTED remains residual | structured unresolved rows and dedicated WARN result | none |
| use before report and failure BLOCK | shared hook adapter appends then renders | use records authorization attempt before tool completion |
| legacy migration | enforce 보존, advisory/off는 L3 enforce로 안전 승격 plus validate/doctor warning | legacy removal deferred |
| both host parity | common `hook_runtime` and installed runtime resource | none |

## 2. Test Coverage

- Audit domain: required fields, wildcard, TTL, expiry, revoke, malformed/duplicate/conflict, symlink/ancestor-swap,
  concurrent first grant, and post-revoke use.
- CLI: exact required Phase 01 ID, optional/unknown rejection, grant/list/revoke.
- Gate: L2/L3/unknown defaults, exact waiver, FAIL non-waivable, invalid audit, runtime anti-downgrade.
- Adapter: snapshot injection, successful use append, append failure BLOCK.
- Profile/schema/doctor/messages: closed keys, type checks, ambiguity, migration, user output.
- Install/runtime: new module included in both host installs; existing hook and golden-instance regressions remain green.

## 3. Acceptance Evidence

| ID | Status | Evidence |
|---|:---:|---|
| FB02-AC1 | PASS | risk default and anti-downgrade core tests |
| FB02-AC2 | PASS | schema and semantic closed-policy tests |
| FB02-AC3 | PASS | CLI exact required ID and core exact matching tests |
| FB02-AC4 | PASS | required field/wildcard/TTL CLI and library tests |
| FB02-AC5 | PASS | dedicated residual WARN with unchanged NOT TESTED evidence |
| FB02-AC6 | PASS | FAIL, invalid audit, expiry, revoke, duplicate/conflict/symlink tests |
| FB02-AC7 | PASS | shared module, snapshot, append-before-render and failure-BLOCK tests |
| FB02-AC8 | PASS | legacy gate tests plus validate/doctor migration output |
| FB02-AC9 | PASS | Three fresh Claude rounds plus a fresh closure review completed; findings were independently triaged. |

## 4. Pre-Review Residual Boundary

The audit is an exact, fail-closed local governance record, not a remote identity or tamper-proof authority. A process with
the same repository write permission can still rewrite history; `confirmed_by` is deliberately labeled
`self_asserted_local`. Remote attestation and server-side authority remain FB-08 scope.

## 5. Independent Review Round 1 Triage

Claude의 1차 독립 리뷰는 P1 1건과 P2 4건을 보고했다. 공식 harness 누락, 비정상 TTL 예외, legacy L3
downgrade, 동시 grant 복구 부재는 타당하여 수정했다. `waiver.enabled` 기본값 지적은 explicit grant가 별도이며
사용자가 전체 활성화를 확정한 정책과 충돌하므로 수용하지 않았다. 수정 후 focused/full/official 회귀와 2차 fresh
headless review를 수행한다.

## 6. Independent Review Round 2 Triage

Claude 2차 독립 리뷰는 1차 수정 네 건을 모두 확인한 뒤 P1 1건과 P2 2건을 추가 보고했다. waiver 정본의
runtime hash 누락은 실제 변조 미감지 우회이므로 수용했다. CLI filesystem error와 legacy enforce L2 테스트
누락도 재현 가능해 수용했다. 수정 후 focused/official/full 회귀를 다시 수행하고 3차 fresh headless review로
최종 결함을 탐색한다.

## 7. Independent Review Round 3 Triage

Claude 3차 독립 리뷰는 `require_for_risk: [L2]`가 L3 gate를 조용히 통과시키는 P1을 실제 재현했다. 이는
waiver 감사보다 강한 profile-only 우회이므로 runtime과 validator 양쪽에서 L3를 필수화했다. P2 테스트 경로
의존도 수용해 독립 실행을 보장했다. 세 회차 요건은 충족했지만 마지막 회차 수정이 존재하므로 closure review가
clean인지 확인하기 전 AC9를 PASS로 전환하지 않는다.

## 8. Independent Review Round 4 Triage

첫 closure review는 malformed list의 unhashable 값이 runtime L3 floor 전에 예외를 내는 P1과, known-L3를
실제로 구성하지 않은 vacuous test P2를 발견했다. 둘 다 재현 가능해 수용했다. risk/status 정규화와 engine
floor를 보강하고 adapter-level unexpected exception BLOCK을 추가했다. 수정 후 focused/official/full 회귀와
fresh closure review가 clean일 때만 AC9를 PASS로 전환한다.

## 9. Independent Review Round 5 Triage

두 번째 closure review는 `statuses` 어휘 확장이 custom resolved state를 만드는 P1을 재현했다. 이는 정상
schema-valid profile로도 가능하므로 수용했다. schema/semantic/runtime 세 층에서 상태 어휘를 닫고, PASS와
사유 있는 N/A 외 모든 상태가 unresolved가 되도록 수정했다. 재검증과 fresh closure가 clean일 때 종료한다.

## 10. Broad External Review Round 1 Triage

Claude session `7103906f-8bd3-484c-bb8c-937e92496f5a`가 pure core 밖 adapter에서 기존 global override와
FB02 불변식이 충돌함을 찾았다. 실제 `gate=all` grant로 FAIL acceptance와 두 fail-closed 오류가 bypass되고
감사 로그까지 기록되는 것을 RED test로 확인했다. 세 message key만 generic override에서 제외해 운영상 일반
L3 override 호환성은 유지했으며 focused override/profile/authority aggregate가 PASS했다. 복수 advisory WARN 중
첫 결과만 표시되는 P3는 안전 차단을 바꾸지 않아 후속 리뷰까지 보류한다.

## 11. Broad External Review Round 3 Triage

Claude session `a01c9b7a-ee27-483b-9650-bd836aa264ca`의 poisoned audit recovery CLI 제안은 현재 Phase 00~02의
명시적 수리 경계를 바꾸므로 결함으로 수용하지 않았다. 반면 Round 1 P3는 운영 가시성 결함이 맞아 복수 WARN
reason을 결정론적으로 병합했다. 자동 archive는 향후 audit-chain rotation을 별도 설계할 때 검토한다.

## 12. Closure Review

Fresh Claude session `ead09722-14af-4538-b8b0-155761c95973`은 FB02 기능 요구사항을 CLOSED로 판정하고
전체 verdict를 `ADVISORY`로 반환했다. Generic audited override가 acceptance 평가보다 앞선
`block_cycle_binding` 또는 `block_report_without_approval`을 명시적으로 완화할 수 있다는 점은 기존 운영
escape hatch의 경계로 수용한다. FB02의 exact acceptance waiver는 acceptance 결과 자체와 audit failure,
runtime failure를 generic override로 우회하지 못하게 유지한다. 이 상위 report-block까지 non-overridable로
바꿀지는 별도 정책 변경으로 추적하며 이번 acceptance를 재해석하지 않는다.
