# [Base Plan] SAGE-FB-12 framework overlay 게이트 완화 hard-fail

Cycle-Stem: `sage-fb-12-framework-overlay-hard-fail`
Risk Level: L3
Status: COMPLETE

## 1. Context

현재 `overlay_classify.COMPOSE_ALLOWED`는 `AGENT_GUIDE`, `CLAUDE`, `CODEX`, `AGENTS` 네 framework
문서를 모두 compose 대상으로 둔다. SD-4 `domain_refs` 검사는 도메인 registry의 트리거 재복제만 막으며,
phase/review/verification 게이트를 독립적으로 보장하는 oracle은 아니다. 동시에 gate-relaxation lint는 WARN
고정이고 strict 승격 목록에도 없어 완화 문구가 materialize되고 `validate --strict`도 exit 0이다.

## 2. Goal

- 독립 oracle이 없는 gate-bearing framework overlay를 fail-closed로 차단한다.
- gate-relaxation 탐지를 합성 전 preflight hard error로 사용한다.
- 같은 탐지를 `validate --strict`에서 FAIL로 승격한다.
- authoring guidance가 explicit confirmation만으로 완화 문구/framework overlay를 쓰라고 안내하지 않게 한다.

## 3. Scope

In scope:

- overlay composition eligibility의 non-gate/oracle-backed 구분
- framework 4종의 compose 차단
- `scan_text` 기반 materialization preflight와 strict validation 결속
- overlay authoring/write-guard 설명 정합화
- classify/lint/materialize/validate/install 관련 회귀 테스트
- 세 번의 independent headless review-rework

Out of scope:

- 의미론적으로 완전한 gate-relaxation parser
- framework용 새 independent oracle 구현
- install 전체 write/prune 전 preflight와 rollback(SAGE-FB-15)
- 서버측 tamper-proof PR authority(SAGE-FB-08/SD-9)

## 4. Done Criteria

1. framework 4종은 independent oracle 등록 없이는 blocked다.
2. gate-relaxation hit가 있는 eligible overlay는 plan/materialize 전에 hard error다.
3. `validate --strict`는 `overlay-gate-relaxation`을 FAIL/exit 1로 승격한다.
4. default validate는 heuristic hit를 WARN으로 표면화하되 exit 정책은 유지한다.
5. preflight와 validate가 같은 scanner 결과를 사용한다.
6. 관련 CORE guidance와 write-guard가 blocked framework 경로 또는 explicit acceptance를 권장하지 않는다.
7. 세 번의 independent review와 finding triage를 완료한다.
