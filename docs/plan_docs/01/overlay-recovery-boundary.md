# Overlay 복구 경계 — 요구

Cycle-Stem: overlay-recovery-boundary
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1

Status: COMPLETED

## 요구사항과 수용 연결

C1/M1: source/Claude 합계/개인 입력 오류, rename, worker sync 미완료에서도 일반 진단·수리 통로를 제공한다. 기존 독립 gate가 차단한 작업을 우회하지 않는다.
C2/M1: 짧고 body-free인 현재 root/role 무효 표지를 공급한다. 정상 empty로 위장하지 않는다. CORE7종 공통 앞부분만 처리 규칙을 정렬한다. root/child/다른 checkout의 과거 본문 혼입 금지.
C3/M2: 공통 collector를 재사용한다. 설치가 없는 첫 입력은 빈 profile을 허용하되 기존 profile 오류는 보존한다. generate는 적용 예정 compiled profile을 검사하고 기존 수리를 거부하지 않는다. 기존 cleanup/transaction은 유지한다.
C4/M3: manifest installed_hosts와 요청 host 기준으로 전체 직렬화 크기를 판정한다. write guard의 순수 차단 smoke는 overlay 상태와 독립이다.
C5: 기존 회귀를 실행하고 구 차단 계약만 명시적으로 갱신한다. C6: wheel consumer·native/model·실기 실행을 구분해04에 표기한다.

## 원인·위험·재현

전면 봉쇄: 높은 사용자 영향, 해당 입력에서 반복 재현, 외부 수정으로만 복구. 적용 불일치: 개인11KB install0/sync0/Read2. host 오판: Codex-only8KB Read0/validate1. rename/worker는 동일 M1 원인의 회귀 사례다. 대형 전달 체계로 확장하지 않는다.
