# SAGE Architecture

[English](ARCHITECTURE.en.md) | [문서 인덱스](README.md)

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

## 판정 전달 채널

**판정이 맞아도 아무에게도 닿지 않으면 게이트가 없는 것과 같습니다.** 위 원칙("게이트를 조용히
끄지 않는다")은 판정뿐 아니라 전달에도 적용됩니다. 실제로 두 방향의 유실이 모두 관측됐습니다 —
차단 사유가 사라져 원인 불명 차단이 되거나, 통과 메시지가 사라져 낡은 상태가 보이지 않는 경우입니다.

host 는 이벤트와 exit code 에 따라 **읽는 채널이 다릅니다.** 그래서 채널 선택은 런타임과 이벤트가
함께 결정합니다.

| 상황 | Claude Code | Codex |
|---|---|---|
| 차단 (exit 2) | stderr — stdout 은 무시된다 | stderr |
| PreToolUse 통과 (exit 0) | `hookSpecificOutput.additionalContext` | 〃 |
| UserPromptSubmit (exit 0) | 평문 stdout — 그대로 컨텍스트가 된다 | `hookSpecificOutput` |
| Stop 차단 | exit 2 + stderr | exit 0 + `decision: block` |

Claude Code 에서 exit 0 평문 stdout 이 컨텍스트로 올라가는 이벤트는
`UserPromptSubmit`·`UserPromptExpansion`·`SessionStart` 뿐이고, 그 밖의 이벤트는 디버그 로그로만
갑니다. 문구 자체는 `runtime/messages.py` 가 단독 소유하고 채널만 `io_claude`·`io_codex` 가 정합니다.

## 신뢰 경계 (막는 것 / 막지 않는 것)

**막는 것**
- 드리프트 — spec↔산출물 불일치를 `sage validate`가 적발
- 직접수정 — write-guard가 산출물 직접 편집을 막고 spec으로 redirect
- 단일 모델 편향 — cross-model 리뷰로 반대 런타임이 독립 리뷰
- 게이트 침묵 비활성 — profile 오타·미지 키(게이트를 조용히 끄는 원인)를 `sage validate`가 fail-closed로 적발. 이는 **검증 시점**의 fail-closed이며, **런타임**의 profile *파싱* 실패는 위 표대로 fail-open + LOUD로 — 서로 다른 층이다
- 06←05 우회 — 완료 보고를 APPROVED된 리뷰에 결정론으로 묶음
- Loop A 감사 증거의 비재해시 수정·삽입·중간 삭제·재정렬 — run별 strict hash-chain,
  레코드 self-hash, 파일 파싱 무결성을 실제 report gate가 검산
- 로컬 hook 부재·우회 — 로컬 hook은 기여자 머신에 SAGE가 설치돼 있다는 전제 위에서만 동작한다.
  SD-9/Fast Cycle은 서버측 authority(`sage/ci_authority.py`, 순수·git 비의존)가 CI에서
  `.sage/fast_cycle.jsonl`·`loop_audit.jsonl`의 strict hash-chain을 독립 재검증해, hook이 없거나
  우회된 기여자의 PR도 required check로 걸러낸다 — 로컬 게이트가 유일한 방어선이 아니다

**막지 않는 것 (설계상 범위 밖)**
- **완전히 장악된 host runtime** — SAGE는 host가 규칙대로 CLI/스킬을 호출한다고 가정합니다.
  악의적으로 조작된 runtime 자체는 방어 대상이 아닙니다.
- **완전 재계산 또는 legacy로 강등한 loop_audit 재작성** — run별 strict hash-chain은 키 순서와 Unicode
  표현을 고정한 canonical SHA-256으로 각 레코드와 직전 run 레코드를 self-verify합니다. v1 체인 필드가
  하나라도 남은 run에서는 hash를 다시 계산하지 않은 수정·삽입·중간 삭제·재정렬을 탐지하지만, 파일과 체인을
  재계산할 수 있는 공격자를 인증하지는 않습니다. 또한 하위호환을 위해 체인 필드가 전혀 없는 run을
  legacy(`chain_ok=None`)로 허용하므로, run 전체에서 세 체인 필드를 모두 제거한 downgrade는 정당한 legacy
  run과 구분할 수 없습니다. 비밀 키·서명된 head·별도 artifact의 tip·Git 기준선·외부 witness가 없으므로
  독립적인 tamper-resistance가 아니라 **자체 무결성 검증(self-verification)** 입니다. tip 수정은
  self-hash로 탐지하고, 최종 close 삭제는 report gate의 `closed` 불변식으로 차단하며, 완전 재계산·전체
  필드 제거 재작성의 외부 앵커는 Git 이력과 코드 리뷰입니다.

경계를 넘는 위협(장악된 runtime, 감사 로그 위변조)은 결정론 게이트가 아니라
cross-model 리뷰·사람 승인 같은 상위 절차가 완화합니다. 결정론 게이트는 "정직한 host의
실수·게으름·드리프트"를 막는 것이지, "적대적 host"를 막는 것이 아닙니다.
