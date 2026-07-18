# [Plan] SAGE-FB-12 framework overlay 게이트 완화 hard-fail

Cycle-Stem: `sage-fb-12-framework-overlay-hard-fail`

## 1. Acceptance Matrix

| Acceptance ID | Requirement | Required |
|---|---|:---:|
| FB12-AC1 | `AGENT_GUIDE`, `CLAUDE`, `CODEX`, `AGENTS` framework overlay는 독립 oracle 등록 없이는 blocked다. | yes |
| FB12-AC2 | eligible overlay의 gate-relaxation hit는 합성 계획을 비우고 error를 반환한다. | yes |
| FB12-AC3 | 동일 hit는 `validate --strict`에서 `overlay-gate-relaxation` FAIL과 exit 1을 만든다. | yes |
| FB12-AC4 | default validate는 heuristic 특성상 WARN/exit 0 정책을 유지한다. | yes |
| FB12-AC5 | scanner pattern id/description이 preflight와 validate에서 같은 근거로 출력된다. | yes |
| FB12-AC6 | blocked framework overlay와 preflight error는 eligible render/receipt를 쓰지 않는다. 단, FB12 이전에 남은 정확한 SAGE managed block은 fail-closed 정리한다. | yes |
| FB12-AC7 | authoring/write-guard 문서는 framework overlay 및 explicit warning acceptance를 지원 경로로 안내하지 않는다. | yes |
| FB12-AC8 | Claude 또는 오류 시 사용자 지정 fresh headless fallback review를 3회 수행하고 findings를 선별 반영한다. | yes |

## 2. Baseline Evidence

- `test_overlay_classify.py`: framework 4종 compose 기대가 통과한다.
- `test_overlay_materialize.py`: domain contract만 통과한 `AGENT_GUIDE` overlay가 물리화된다.
- `test_gate_relax_suspected_remains_advisory_under_strict`: 완화 문구가 있어도 strict rc=0을 기대하고 통과한다.
- `overlay_materialize.plan_materialize`는 marker injection만 검사하고 `overlay_lint.scan_text` 결과는 사용하지 않는다.

## 3. Compatibility

- non-gate implementer overlay의 clean additive composition은 유지한다.
- default validate의 heuristic WARN은 기존 exit 0을 유지한다.
- framework 프로젝트 규칙은 당분간 profile, conventions, critical-domain pointer 또는 project-local 문서로
  이동해야 하며, 새 independent oracle이 구현되기 전까지 materialized framework override는 지원하지 않는다.

## 4. Failure Contract

- blocked framework overlay는 file inventory 단계에서 명시적 error가 된다.
- gate-relaxation preflight error가 하나라도 있으면 eligible materialization plans/receipts를 폐기한다.
- blocked 자산의 정확한 SAGE managed block 정리는 일반 preflight보다 먼저 수행한다. 마커가 중복/손상돼
  안전하게 경계를 정할 수 없으면 해당 target은 쓰지 않고 hard-fail하되, 독립적으로 식별된 다른 blocked
  target의 block은 제거한다. manifest receipt는 갱신하지 않는다.
- FB-12는 일반 materialization apply 이전 무변경과 위 보안 정리 예외를 보장한다. install 전체 사전
  무변경은 FB-15가 소유한다.
