# [Design] SAGE-FB-02 위험도별 acceptance와 명시적 L3 waiver

Cycle-Stem: `sage-fb-02-risk-acceptance-waiver`

## 1. Profile

```yaml
verification:
  acceptance:
    enabled: true
    require_for_risk: [L2, L3]
    report_gate_by_risk:
      L2: advisory
      L3: enforce
    waiver:
      enabled: true
```

`waiver.enabled`는 감사 기록 소비 기능만 켠다. Waiver 자체를 생성하거나 L3를 낮추지 않는다. Audit path,
waivable status, TTL 상한은 engine 고정값으로 두어 profile이 안전 경계를 완화하지 못하게 한다.
`require_for_risk`는 L1/L2 opt-in 범위를 조정할 수 있지만 L3를 제외할 수 없다. semantic validation과 runtime
floor가 이 불변식을 각각 배포 전과 실행 시점에 강제한다.
검증을 우회한 malformed profile도 core를 crash시키지 않도록 risk/status 목록은 문자열만 소비하고 L3 및
FAIL/NOT TESTED 불변식을 합성한다. 그 밖의 예상 밖 core 예외는 공용 adapter가 exit 2 BLOCK으로 변환한다.
Status schema는 canonical 네 값으로 닫고 runtime은 `PASS`와 사유 있는 `N/A` 외 모든 값을 unresolved로
처리한다. 따라서 validation을 우회하거나 어휘를 확장해도 custom resolved state가 생기지 않는다.

## 2. Audit Model

`.sage/acceptance-waivers.jsonl` append-only records:

```text
grant  {waiver_id, cycle_stem, acceptance_id, reason, scope,
        remaining_evidence, confirmed_by, created_at, expires_at}
use    {waiver_id, cycle_stem, acceptance_id, report_path, ts}
revoke {waiver_id, reason, confirmed_by, ts}
```

- grant ID는 random, TTL은 최대 24시간이다.
- active = exactly one valid grant, not expired/revoked, exact cycle/id.
- malformed/duplicate grant IDs and conflicting active grants fail closed.
- gate use 시 runtime adapter가 audit summary를 snapshot에 주입하고 use event를 append한다.
- 동시 grant 충돌을 감지한 writer는 자기 grant를 보상 revoke한다. 이미 충돌한 append-only 기록은 명시적
  `revoke`로 복구할 수 있으며 malformed/duplicate 기록은 VCS 복원 또는 운영자 수리가 필요하다.

## 3. Gate Algorithm

```text
cycle risk -> mode_by_risk (unknown => L3)
parse exact 01 matrix + exact 04 evidence
for every required row:
  PASS -> resolved
  N/A + substantive reason -> resolved
  FAIL -> unresolved, never waivable
  NOT TESTED:
    L3 enforce + exact active waiver -> waived_unresolved
    otherwise -> unresolved
if unresolved -> mode result (L3 block, L2 warn)
elif waived_unresolved -> WARN with residual evidence, never OK/PASS
else -> OK
```

Mixed rows use the strongest outcome: one FAIL or unwaived NOT TESTED keeps L3 BLOCK even if other IDs have waivers.

## 4. Runtime and CLI

- `sage acceptance-waiver`: grant/list/revoke; validation and record functions live in one runtime-neutral module.
- `hook_runtime.build_snapshot`: current cycle-relevant active/invalid waiver summary injection.
- pure core consumes only snapshot data and returns deterministic decision.
- adapter appends use only after the pure result identifies a waiver; logging failure degrades to BLOCK rather than
  silently consuming an unaudited waiver.

## 5. Tests

- L2/L3/unknown mode matrix and legacy fallback
- legacy enforce 유지와 legacy advisory/off의 L3 안전 승격
- exact ID/stem, multi-row strongest result, FAIL non-waivable
- missing confirmation/fields, TTL, revoke/expiry, malformed/duplicate records
- audit logging failure and replay
- Claude/Codex runtime parity and install/template/schema/doctor regressions
