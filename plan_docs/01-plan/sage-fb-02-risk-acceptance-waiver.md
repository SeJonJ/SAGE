# [Plan] SAGE-FB-02 위험도별 acceptance와 명시적 L3 waiver

Cycle-Stem: `sage-fb-02-risk-acceptance-waiver`
Risk Level: L3

## 1. Acceptance Matrix

| ID | Requirement | Required? |
|---|---|:---:|
| FB02-AC1 | acceptance gate 기본 mode는 L2 advisory, L3 enforce이며 unknown은 enforce다. | yes |
| FB02-AC2 | risk별 mode 설정은 닫힌 schema와 semantic validation을 통과해야 한다. | yes |
| FB02-AC3 | waiver는 exact cycle stem과 exact required acceptance ID 한 개에만 적용된다. | yes |
| FB02-AC4 | waiver grant는 명시적 user confirmation, reason, scope, remaining evidence를 모두 요구한다. | yes |
| FB02-AC5 | active waiver가 있는 L3 NOT TESTED는 WARN이지만 문서 상태를 PASS로 바꾸지 않는다. | yes |
| FB02-AC6 | FAIL, invalid/expired/revoked/duplicate/malformed/wildcard waiver는 계속 BLOCK한다. | yes |
| FB02-AC7 | grant/use/revoke 감사가 append-only이며 hook/CLI가 같은 정본을 소비한다. | yes |
| FB02-AC8 | L2와 legacy profile 호환 정책이 명시되고 doctor가 migration을 안내한다. | yes |
| FB02-AC9 | three independent reviews and finding triage를 완료한다. | yes |

## 2. User Confirmation Contract

- Waiver CLI는 `--cycle-stem`, `--acceptance-id`, `--reason`, `--scope`, `--remaining-evidence`,
  `--confirm-user`를 모두 요구한다.
- `--confirm-user`는 대화에서 사용자가 해당 ID의 미검증 상태와 운영 후속을 명시적으로 승인한 경우에만
  실행한다. 로컬 동일 권한 프로세스의 신원을 암호학적으로 증명하지는 못하며 그 한계는 audit에 기록한다.
- wildcard cycle/id, 빈 값, `FAIL` 자동 전환, profile만으로 생성되는 waiver는 없다.

## 3. Mode Contract

- 새 profile key: `verification.acceptance.report_gate_by_risk`.
- 기본: `{L2: advisory, L3: enforce}`. L1이 요구 대상이면 기본 advisory.
- acceptance가 활성화된 profile은 `require_for_risk`에서 L3를 제거할 수 없다. validator는 FAIL하고 런타임도
  L3를 강제 포함해 profile-only gate bypass를 차단한다.
- legacy `report_gate_enforce: enforce`는 전 위험도 enforce를 유지한다. legacy `advisory` 또는 `off`는
  L3를 낮추지 않도록 런타임에서 L2 advisory/L3 enforce로 안전 승격하고 doctor/validate가 migration을 안내한다.
- 두 key를 동시에 설정하면 ambiguity로 FAIL한다.

## 4. Waiver Result

Waiver는 unresolved row를 제거하거나 PASS로 바꾸지 않는다. Gate 결과는 `warn_report_with_l3_waiver`이며
waiver id, acceptance id, reason, scope, remaining evidence를 출력한다. 05/06 문서도 residual evidence를
그대로 기록해야 한다.
Acceptance 상태 어휘는 `PASS`, `FAIL`, `NOT TESTED`, `N/A`로 닫혀 있으며 해결 상태는 `PASS`와 사유 있는
`N/A`뿐이다. Profile에 custom status를 추가해 새로운 해결 상태를 만들 수 없다.
