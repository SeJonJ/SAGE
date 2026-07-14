# SAGE Enhancement 백로그

- SAGE 개발 중 확인된 이슈들로 당장 개발해야하는 내용들은 아니지만, 추후 개발 필요시 참고한다.
- 각 항목 = 배경 · 문제 · 접근 · 규모/위험 · 트리거 · 상태. 즉시 필요 아님 → 트리거 충족 시 착수.

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
- **상태**: ✅ **완료**(2026-06-18, 로드맵 1단계①). `sage generate --kind roster` 신설 — profile.components →
  `implementer-<comp>` spec 결정론 scaffold(접두 명명=함수역할 충돌 회피, 빈 components=고정 implementer-a/b 폴백,
  create-only=손편집 보존). claims/render/manifest 등록은 기존 interpretive agent 파이프라인이 처리(잘 격리된 추가 경로 —
  "중대" cross-cutting 재작성 회피). test_gen_roster(run-all step30, 7케이스) + 변이 teeth. leader/qa/reviewer/convention-checker 고정 유지.

---

## EH-2 — output_contract 마커 profile 주입화 (독립성)

- **배경**: F7(stop 정책 배선) 중 발견 — `policies/output_contract_check.py._MARKERS` 에
  스택 토큰(`backend`/`frontend`/`gradlew` 등)이 하드코딩됨 = 제약 #2(엔진 도메인값 0) 위반.
- **영향**: 현재 output_contract 는 **codex-only** 배선이라 영향 제한적이나, 비-웹 codex-host 인스턴스에서
  마커가 부정확. claude 미적용(F7 결정)이라 즉시 위험은 낮음.
- **접근**: `_MARKERS` 를 profile 주입(예: `profile.output_contract.markers`)으로 빼고 기본값은 중립화.
- **규모/위험**: 소~중. 정책 모듈 + codex stop 어댑터 + 테스트.
- **트리거**: output_contract 를 CORE 승격하거나 비-웹 codex-host 인스턴스 적용 시.
- **상태**: ✅ **완료**(2026-06-18, 로드맵 1단계②). `_MARKERS`→`_DEFAULT_MARKERS` 중립화(backend/frontend/desktop/gradlew
  제거), `check(..., markers=None)` profile 주입 파라미터 신설, io_codex 가 `profile.output_contract.markers` 주입.
  임계 `hit≥(마커수-1)` 일반화(기본 5→4). profile 템플릿 `output_contract.markers` 안내. test 신규(중립성+주입+폴백) + 변이 teeth(스택토큰 재주입→FAIL).

---

## EH-3 — loop_audit 해시체인 위변조 내성 (tamper-resistance)

- **배경**: `scripts/sage_harness/hooks/runtime/loop_audit.py` 의 `_next_seq` 는 seq 연속성 검사가
  *수기 append·순서 뒤바뀜·누락* 같은 게으른 우회를 잡는 **anti-lazy-bypass sanity** 검사이지
  위변조 내성이 아님을 스스로 자인한다(seq = 레코드 수 → 파일을 읽어 다음 정수를 맞춰 append 하면 통과).
- **문제**: 감사 로그(`.sage/loop_audit.jsonl`)가 "위변조 방지"로 오인될 수 있다. 경계는 문서로 명시했으나
  (`docs/ARCHITECTURE.md` 신뢰 경계 · README), 실제 tamper-resistance 메커니즘은 없다.
- **접근**: 각 레코드에 직전 레코드의 해시를 포함하는 **해시체인(prev_hash chaining)** — 중간 삽입/수정/삭제가
  체인 단절로 검출된다. 게이트가 체인 무결성을 검산. 기존 로그 마이그레이션(genesis 재스탬프) 고려.
- **규모/위험**: 중. loop_audit 스키마 확장(prev_hash) + 기록/검증 로직 + 게이트 배선 + 하위호환.
- **트리거**: 위협모델이 "정직한 host"에서 "적대적 host / 감사 로그 신뢰가 필요한 규제·외부 감사"로 확장될 때
  (README "완전 장악된 host runtime 은 방어하지 않음" 전제가 바뀔 때). **현 위협모델상 낮은 긴급도.**
- **상태**: 📋 **로드맵 등재(미착수)**. 감사 표현 정직화(경계 명시)는 완료 — `ARCHITECTURE.md` 신뢰 경계 · README.

---

## EH-4 — cycle-binding ledger (retro 게이트 잔여 우회 봉쇄)

- **배경**: retro 게이트 결정론 강제(v0.9.40)에서 06↔사이클 결속을 **06 자기선언**(`Loop-Run: <run_id>`)으로
  재설계하며 신뢰 경계가 05(리뷰어 작성)→06(host 작성)로 이동했다. Stop 훅은 06 이 선언한 run_id 를 읽어 검증한다.
- **문제(좁은 잔여 우회)**: 06 이 **다른 사이클의 실재+checked+approved** run_id 를 정확히 복붙하면 Stop 이
  그 run 만 보고 통과 → 이번 사이클 retro 미실행이 새어나간다. 오타·지어낸 id·미선언·상충은 전부
  fail-closed BLOCK 이라, **유일 우회는 "과거 checked run_id 정확 복붙"이라는 좁은 경로** 하나뿐.
- **접근**: **cycle-binding ledger 서브시스템** — sage-review(신뢰 경로)가
  `{cycle_id, canonical 06 경로, canonical 05 경로, run_id}` 유일 결속을 영구 기록(`_doc_match` recent-fallback
  제거, 0/2개↑=실패) → 쓰기 성공 **PostToolUse** 에서 `session_id`+operation id 로 확정 → Stop 은 이번 세션
  확정 결속만 소비. 추가: coupling(`retro enforce ⇒ review_loop.enabled`)을 profile_validate **FAIL** 로 강제.
- **규모/위험**: **중대**. sage-review·PostToolUse 어댑터·Stop 게이트·profile_validate 다수 컴포넌트 대공사.
- **트리거**: retro 게이트 우회가 실제 관측되거나 "정직한 host" 전제가 바뀔 때. **현 위협모델상 낮은 긴급도**
  (남은 우회가 좁고, 나머지 실패모드는 이미 BLOCK).
- **상태**: 🕗 **defer(2026-07-11, 유저 승인 "Option 1 로 진행")**. codex R2/R3 파생. 정본 vault
  `SAGE - retro 게이트 결정론 강제 개발(26.07.11)`.

---

## EH-5 — Risk Level 강제 게이트 + 완전 effective-max 결정론화

- **배경**: write-back 심층 노트(9-E)가 "이 사이클 risk tier 로 노트 깊이 결정"을 지시. 후속 A 로
  00 템플릿에 `Risk Level: Lx` 필수 필드 + sage-plan 기입 지침 + write-back 이 그 라인을 읽어 **선언값
  결정론 정본화**는 완료(재개 세션에도 tier 확정, `_cycle_risk` 정규식과 동일 라인).
- **문제(A 의 advisory 한계)**:
  1. **미기입 무방비** — sage-plan Step 3/6 이 채워짐을 *프롬프트로* 확인하나 훅 차단은 아님. leader 가
     placeholder 를 남겨도 결정론으로 막지 못한다(현재는 write-back 이 unknown→L2 심층 fallback 으로 안전 degrade).
  2. **effective-max 불완전** — `_cycle_risk` 는 `event.declared_max` → `snapshot.cycle_risk` → 00~05 스캔
     순서라 **세션 선언이 00 보다 우선**. 00=L3 이어도 세션 declared=L1 이면 acceptance gate 가 낮게 열린다.
     또 00 을 먼저 찾으면 후속 phase 의 더 높은 risk 를 안 본다(첫 매칭 반환).
  3. **재조정 강제 부재** — 계획 L1 이 구현 후 L2/L3 로 커져도 자동 상향 없음. write-back 이 06 전에 `profile.risk`
     로 재분류해 00 을 갱신하도록 *프롬프트로* 지시하나 best-effort(집행 없음).
- **접근**: (1) 00 `Risk Level` 미기입/placeholder 를 WARN/차단하는 **결정론 게이트**(pre-implementation 또는
  전용 훅). (2) `_cycle_risk` 를 `max(declared_max, snapshot, 00~05 전체 스캔)` 로 바꿔 **완전 effective-max**
  반환. (3) 06 작성 전 risk reconciliation(`profile.risk` 재분류→00 상향)을 결정론 단계로.
- **규모/위험**: **중간**. PDCA 문서 계약(00 스키마)·pre-implementation 게이트·`_cycle_risk`·테스트 동시 변경.
- **트리거**: write-back 노트 깊이 오분류가 실제 관측되거나, "정직한 host" 전제로 부족할 때. **현 긴급도 낮음**
  — 미기입/불명확은 write-back 이 L2 심층 fallback 으로 안전 degrade.
- **상태**: 🕗 **defer(2026-07-14, 유저 승인 "A 만 진행, B 는 추후")**. codex A 리뷰 파생. 정본 vault
  `SAGE - write-back 심층 노트 설계 + required_structure 배선(26.07.14)`.

---

## (참고) 보류 — 자산 사이클 내 기록
- F5(클린 업그레이드)는 하드닝에서 해소(profile create-only). F1/F3/F7/malformed 동일.
- 진행 로그: vault `TECH - SAGE 구현 진행 로그.md`
