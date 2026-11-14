# Overlay 복구 경계 — 최소 설계

Cycle-Stem: overlay-recovery-boundary
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1

Status: COMPLETED

## 최소 설계

- `overlay_delivery.collect_catalog(root, role, ...)`의 기존 snapshot·lint를 재사용하고 적용 예정 profile을 선택적으로 전달한다. runtime 기본 호출 의미는 유지한다. 새 전용 서비스·영구 상태 없음.
- 같은 모듈의 `preflight_delivery(root, hosts, profile=...)`는 본문을 반환하지 않고 오류 하나/없음을 반환한다. profile pair 복구는 caller가 계획한 profile로 판정하고 host 합계는 전체 render로 검사한다. install/sync/upgrade/generate/validate의 해당 적용·검증 지점에 연결한다.
- `overlay_context`가 body-free 무효 상태를 만들고 UPS는 일반 복구 요청을 통과시킨다. 내부 validator unavailable/manifest·profile 무결성 실패는 무조건 경고로 바꾸지 않는다. 위험도 수집 결과를 유지한다.
- `run_hook`의 write-guard에서 전체 overlay 선행 조건을 떼어내고 원래 write-only 보호를 유지한다. recoverable overlay 진단은 문맥 공급 경계에서 처리한다.
- Claude 병합 event 초과는 기존 reserve를 유지하되 overlay만 무효로 표시해 위험도 처리/복구 대화를 전부 막지 않는다. 독립 producer 자체 초과는 별도 검증한다.
- CORE7종과 hook 명세·한영 문제 해결 안내는 변경된 계약만 정렬한다. 기존 API 호환·manifest runtime hash·package integrity를 기존 생성 절차로 확인한다.

## 작업별 검증

M1 기존 overlay_runtime_delivery의 구 차단 기대와 신규 진단/수리/현재 무효·보호 쓰기 테스트 RED→GREEN. M2 신규 shared/personal·호스트 preflight와 설치/upgrade/generate 실패 전후 bytes 확인. M3 Codex-only/dual explicit validate. 관련 suite 후 run-all, wheel consumer/플랫폼 smoke, 최소Python syntax. 실제 모델/Windows 불가 시 NOT_TESTED로 남긴다.

## 적용 예정 상태와 기존 복구 계약

실제 helper는 `preflight_delivery(root, hosts, *, profile=None, validate_manifest=True)`다. install의 기존 force manifest 복구는 설치 절차가 manifest를 교체하고 자체 transaction/preconditions로 검사하므로 해당 입력 검사에서만 `validate_manifest=False`를 사용한다. profile·원문 경로/lint/크기/host 검사는 유지한다. runtime의 기본 검사는 계속 manifest를 검사한다. 최초 설치의 아직 없는 dest에는 overlay도 없으므로 설치 자체의 경로 검사 뒤 빈 입력으로 취급한다.

기존 validate의 휴리스틱 gate-relaxation은 default WARN/strict FAIL 정책을 보존한다. 단순 전달 한도 오류를 그 휴리스틱에 섞어 누락하지 않는다.
