# SAGE Enhancement Backlog (자산 사이클과 독립 — 추후 적용)

핵심 자산 사이클(install/generate/validate/hook/agent/skill) 밖의 강화 후보를 모은다.
각 항목 = 배경 · 문제 · 접근 · 규모/위험 · 트리거 · 상태. 즉시 필요 아님 → 트리거 충족 시 착수.

---

## EH-1 — 동적 컴포넌트 파생 roster (F2 옵션 2)

- **배경**: F2(team roster 역할명 비중립: backend/frontend)는 **옵션 1(중립 rename)** 로 해소 —
  CORE 가 `implementer-a`/`implementer-b` 2개 고정, 컴포넌트 매핑은 `profile.team.core.*.owns` 가 담당.
- **문제(옵션 1의 한계)**: implementer 에이전트가 **2개 고정**. 컴포넌트 1개면 1개가 비고, 3개 이상이면
  한 에이전트가 여러 컴포넌트를 owns 하거나 `team.extensions` 로 수동 추가해야 함 — 컴포넌트 수와 roster 가 불일치.
- **접근(옵션 2 = 진짜 일반화)**: implementer 에이전트를 `profile.components` 개수·id 에 맞춰 **동적 생성**.
  - install-time 고정 에이전트 파일 배포 → **generate-time 에 profile.components 기반 렌더**로 이전.
  - 컴포넌트 id 별 implementer 스펙을 중립 템플릿에서 생성(예: components=[core, ui] → `core`·`ui` 에이전트).
  - leader/qa/reviewer/convention-checker 는 함수 역할이라 고정 유지.
- **규모/위험**: **중대**. install→generate 아키텍처 변경(에이전트 스펙 생성 경로 신설),
  manifest 에이전트 등록·conformance·reverse_extract 연동 재검토 필요.
- **트리거**: 컴포넌트 수가 2와 크게 다른 인스턴스가 등장 / roster-as-config 를 본격 일반화할 때.
- **상태**: 백로그(유저 결정 — 옵션 1 적용 후 추후). 우선순위 **중**.

---

## EH-2 — output_contract 마커 profile 주입화 (독립성)

- **배경**: F7(stop 정책 배선) 중 발견 — `policies/output_contract_check.py._MARKERS` 에
  스택 토큰(`backend`/`frontend`/`gradlew` 등)이 하드코딩됨 = 제약 #2(엔진 도메인값 0) 위반.
- **영향**: 현재 output_contract 는 **codex-only** 배선이라 영향 제한적이나, 비-웹 codex-host 인스턴스에서
  마커가 부정확. claude 미적용(F7 결정)이라 즉시 위험은 낮음.
- **접근**: `_MARKERS` 를 profile 주입(예: `profile.output_contract.markers`)으로 빼고 기본값은 중립화.
- **규모/위험**: 소~중. 정책 모듈 + codex stop 어댑터 + 테스트.
- **트리거**: output_contract 를 CORE 승격하거나 비-웹 codex-host 인스턴스 적용 시.
- **상태**: 백로그. 우선순위 **중**.

---

## (참고) 보류 — 자산 사이클 내 기록
- F5(클린 업그레이드)는 하드닝에서 해소(profile create-only). F1/F3/F7/malformed 동일.
- 진행 로그: vault `TECH - SAGE 구현 진행 로그.md`, 1차 테스트 평가: `SAGE 프로젝트 1차 테스트(26.06.18)`.
