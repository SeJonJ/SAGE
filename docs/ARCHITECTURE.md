# SAGE Architecture

SAGE는 "판단은 AI가, 경계는 결정론 코드가"라는 원칙 위에 선 거버넌스 하네스입니다.
이 문서는 그 경계를 이루는 **2층 불변식**, **실패 정책**, **신뢰 경계**를 한곳에 모읍니다.
코드 곳곳의 주석에 흩어져 있던 계약을 단일 참조점으로 승격한 것입니다.

## 2층 불변식

| 층 | 역할 | 성격 | 위치 |
|---|---|---|---|
| **core** | 게이트 판정 로직 (risk 분류, `decide`, seq 검산 등) | **순수 결정론** — 같은 입력 → 같은 판정, 부수효과·판단 없음 | `scripts/sage_harness/hooks/core/`, `scripts/sage_harness/hooks/runtime/loop_audit.py` |
| **runtime / adapter** | IO 오케스트레이션 (입력 추출, profile 로드, snapshot 빌드, 출력 렌더), host별 분기 | 판단·환경 의존을 여기로 격리 | `scripts/sage_harness/hooks/runtime/hook_runtime.py`, `.../runtime/io_claude` · `io_codex` |

핵심: **판단(리뷰·분석·수정)은 AI가, 경계(게이트·무결성·검증)는 core가 결정론으로** 소유합니다.
AI의 판단이 틀려도 core 게이트는 무너지지 않습니다. runtime은 core에 입력을 조립해 넘길 뿐,
판정 자체를 대신하지 않습니다.

## 실패 정책 (fail-open vs fail-closed)

무엇이 실패했느냐에 따라 방향이 다릅니다. 관통 원칙은 **"게이트를 조용히 끄지 않는다"** 입니다
(조용한 gate-disable = Pattern A 방지).

| 실패 지점 | 방향 | 이유 |
|---|---|---|
| 입력 JSON 파싱 실패 | **fail-open** (exit 0) + stderr surface | 일시적 글리치로 보고 개발 흐름을 막지 않되, 조용히 넘기지 않는다 |
| profile 파싱 실패 | **fail-open** + **LOUD** surface | 게이트가 무력화된 상태이므로 반드시 시끄럽게 알린다 |
| L3 전략 실행 크래시 | **fail-closed** (BLOCK 유지) | 고위험 경로를 판정할 수 없으면 안전하게 막는다 |
| root 밖 / 절대경로 glob | 거부 | 프로젝트 독립성 보장 |

근거: `scripts/sage_harness/hooks/runtime/hook_runtime.py` 상단 "보존 원칙" 주석과
profile 로드 · L3 전략 로드 경로.

## 신뢰 경계 (막는 것 / 막지 않는 것)

**막는 것**
- 드리프트 — spec↔산출물 불일치를 `sage validate`가 적발
- 직접수정 — write-guard가 산출물 직접 편집을 막고 spec으로 redirect
- 단일 모델 편향 — cross-model 리뷰로 반대 런타임이 독립 리뷰
- 게이트 침묵 비활성 — profile 오타·미지 키(게이트를 조용히 끄는 원인)를 `sage validate`가 fail-closed로 적발. 이는 **검증 시점**의 fail-closed이며, **런타임**의 profile *파싱* 실패는 위 표대로 fail-open + LOUD로 — 서로 다른 층이다
- 06←05 우회 — 완료 보고를 APPROVED된 리뷰에 결정론으로 묶음
- 루프 라운드의 게으른 우회 — 라운드 기록의 seq 연속성 검산

**막지 않는 것 (설계상 범위 밖)**
- **완전히 장악된 host runtime** — SAGE는 host가 규칙대로 CLI/스킬을 호출한다고 가정합니다.
  악의적으로 조작된 runtime 자체는 방어 대상이 아닙니다.
- **loop_audit 위변조** — `scripts/sage_harness/hooks/runtime/loop_audit.py`의 seq 연속성 검사는 *수기 append·순서
  뒤바뀜·누락* 같은 **게으른 우회(anti-lazy-bypass)** 를 잡는 **sanity 검사**입니다.
  seq = 기록된 레코드 수이므로, 파일을 읽어 다음 정수를 추측해 append 하면 통과합니다.
  진짜 **위변조 내성(tamper-resistance)은 해시체인**이며, 향후 하드닝 과제로 남아 있습니다.

경계를 넘는 위협(장악된 runtime, 감사 로그 위변조)은 결정론 게이트가 아니라
cross-model 리뷰·사람 승인 같은 상위 절차가 완화합니다. 결정론 게이트는 "정직한 host의
실수·게으름·드리프트"를 막는 것이지, "적대적 host"를 막는 것이 아닙니다.
