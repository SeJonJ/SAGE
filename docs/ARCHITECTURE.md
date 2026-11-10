# SAGE Architecture

[English](ARCHITECTURE.en.md) | [문서 인덱스](README.md)

SAGE는 "판단은 AI가, 경계는 결정론 코드가"라는 원칙 위에 선 거버넌스 하네스입니다. 이 문서는 그
경계를 이루는 **2층 불변식**, **실패 정책**, **신뢰 경계**를 한곳에 모읍니다. 코드 곳곳의 주석에
흩어져 있던 계약을 단일 참조점으로 승격한 것입니다.

## 2층 불변식

| 층 | 역할 | 성격 | 위치 |
|---|---|---|---|
| **core** | 게이트 판정 로직 (risk 분류, `decide`, seq 검산 등) | **순수 결정론** — 같은 입력 → 같은 판정, 부수효과·판단 없음 | `scripts/sage_harness/hooks/core/`, `scripts/sage_harness/hooks/runtime/loop_audit.py` |
| **runtime / adapter** | IO 오케스트레이션 (입력 추출, profile 로드, snapshot 빌드, 출력 렌더), host별 분기 | 판단·환경 의존을 여기로 격리 | `scripts/sage_harness/hooks/runtime/hook_runtime.py`, `.../runtime/io_claude`·`io_codex` |

핵심: **판단(리뷰·분석·수정)은 AI가, 경계(게이트·무결성·검증)는 core가 결정론으로** 소유합니다. AI의
판단이 틀려도 core 게이트는 무너지지 않습니다. runtime은 core에 입력을 조립해 넘길 뿐, 판정 자체를
대신하지 않습니다.

## 실패 정책 (fail-open vs fail-closed)

무엇이 실패했느냐에 따라 방향이 다릅니다. 관통 원칙은 **"게이트를 조용히 끄지 않는다"** 입니다
(조용한 gate-disable = Pattern A 방지).

| 실패 지점 | 방향 | 이유 |
|---|---|---|
| 입력 JSON 파싱 실패 | **fail-open** (exit 0) + stderr surface | 일시적 글리치로 보고 개발 흐름을 막지 않되, 조용히 넘기지 않는다 |
| profile 파싱 실패 | **fail-open** + **LOUD** surface | 게이트가 무력화된 상태이므로 반드시 시끄럽게 알린다 |
| L3 전략 실행 크래시 | **fail-closed** (BLOCK 유지) | 고위험 경로를 판정할 수 없으면 안전하게 막는다 |
| root 밖 / 절대경로 glob | 거부 | 프로젝트 독립성 보장 |

위 일반 실패 정책과 별도로, 설치된 SAGE checkout의 overlay 입력 검증은 아래 문맥 공급 절의
UPS/PreToolUse fail-closed 계약을 따른다. 손상 마커를 비SAGE로 취급하지 않는다.

근거: `scripts/sage_harness/hooks/runtime/hook_runtime.py` 상단 "보존 원칙" 주석과 profile 로드·L3
전략 로드 경로.

## 판정 전달 채널

**판정이 맞아도 아무에게도 닿지 않으면 게이트가 없는 것과 같습니다.** 위 원칙("게이트를 조용히 끄지
않는다")은 판정뿐 아니라 전달에도 적용됩니다. 실제로 두 방향의 유실이 모두 관측됐습니다 — 차단
사유가 사라져 원인 불명 차단이 되거나, 통과 메시지가 사라져 낡은 상태가 보이지 않는 경우입니다.

host 는 이벤트와 exit code 에 따라 **읽는 채널이 다릅니다.** 그래서 채널 선택은 런타임과 이벤트가
함께 결정합니다.

| 상황 | Claude Code | Codex |
|---|---|---|
| 차단 (exit 2) | stderr — stdout 은 무시된다 | stderr |
| PreToolUse 통과 (exit 0) | `hookSpecificOutput.additionalContext` | 〃 |
| UserPromptSubmit (exit 0) | 단일 `hookSpecificOutput` JSON | `hookSpecificOutput` JSON |
| Stop 차단 | exit 2 + stderr | exit 0 + `decision: block` |

Claude Code 에서 exit 0 평문 stdout 이 컨텍스트로 올라가는 이벤트는
`UserPromptSubmit`·`UserPromptExpansion`·`SessionStart` 뿐이고, 그 밖의 이벤트는 디버그 로그로만
갑니다. 문구 자체는 `runtime/messages.py`가 단독 소유하고 채널만 `io_claude`·`io_codex`가 정합니다.

## 대상별 overlay 문맥 공급

Claude Code와 Codex는 root 스킬 `sage-cycle`, `sage-plan`, `sage-team`, `sage-review`,
`sage-cycle-fast`, `sage-plan-fast`, `sage-team-fast`의 공유/개인 원문을 schema 2 catalog로
자동 공급합니다. SessionStart startup은 본문을 뒤따르는 UserPromptSubmit에 맡기며,
resume/fork/compact는 사용자 메시지 없이도 진행할 수 있어 현재 묶음을 다시 공급합니다.
검증한 호스트는 Claude Code 2.1.318과 Codex CLI 0.166.0입니다. 격리 consumer에서
14개 source의 원문/hash 전달, 수동 압축·resume 경로와 한도/차단·외부 수리 복귀를 native
호스트와 로컬 mock endpoint로 확인했습니다. mock가 유도한 Skill/read-tool 진입은 실제 도구
경로의 전송 시험이며 실제 모델의 자발적 선택 시험은 아닙니다. 별도 실제 모델
`claude-opus-5-5`/`gpt-6.1-sol`의 유한 표본에서는 표준 두 출처·Fast 네 출처의 적용,
수동·자동 압축 뒤 현재 view 유지와 후속 검증 응답을 관측했습니다. 모든 호스트 버전·미래
모델/세션의 준수, 임의 장기 안정성, 모든 worker의 자체 압축/fork 복구를 보장하지 않습니다.

source는 `skills/<id>/shared|personal`별 한 번만 실리고 target은 source 참조 배열입니다.
표준은 공유 표준 → 개인 표준, Fast는 공유 표준 → 공유 Fast → 개인 표준 → 개인 Fast입니다.
7종 모두 같은 root 문맥에 노출되지만 각 CORE는 자신의 고정 id view만 적용합니다.
필수 CORE·프로젝트 정책·독립 gate > 공유 > 개인 우선순위이며 묶음의 존재는 호출·Fast
전환·사람 승인이 아닙니다. 다른 target 적용 방지는 위 유한 모델 행동 표본의 범위에서 확인한 계약입니다.
현재 경계의 빈 catalog도 이전 지침을 대체하며 다른 checkout의 개인 파일은 상속하지 않습니다.

worker 4종의 공유 물리 합성과 역할별 본문/ref packet은 유지합니다. root 7종 묶음을 worker에
새로 붙이지 않습니다. 일반 worker의 역할별 loader 호출과 headless reviewer CLI의 1회 자동
로딩은 별도 경로입니다. 7종의 소유가 확인된 기존 관리 overlay span은 설치/sync에서 제거하고
원문은 보존합니다. 손상 span·소유 불명은 충돌이며 CORE/사용자 바이트를 지우지 않습니다.
개인 원문을 global/local SKILL.md·manifest·영구 cache에 굽지 않습니다.

잘못된 inventory·한도 초과·손상 SAGE 마커·검증 예외는 정상 부분 catalog를 만들지 않습니다.
SessionStart는 본문 없는 진단, UserPromptSubmit은 native block, 모든 지원 도구의 PreToolUse는
native deny/exit 2입니다. 비SAGE checkout은 통과합니다. 복구는 호스트 밖 터미널/에디터에서
입력을 고친 뒤 다음 메시지에서 재검사하는 경로입니다. `profile_yaml_json_mismatch`는 프로젝트
root의 세션 밖 터미널에서 `sage generate --kind hook --write --target <claude|codex|both>`로
YAML/compiled JSON을 정합화합니다. 설치된 host target을 유지하세요: Claude-only는 `claude`,
Codex-only는 `codex`, 교차 모델/양 host 설치는 `both`입니다. 물리 worker 렌더나 routing 변경의 `render_sync_required`는 세션 밖에서
`sage sync-overlays`로 동기화합니다. profile 수정 뒤 두 상태가 함께 있으면 generate 후 sync
순서로 실행하세요. context 전용 root 스킬 원문 편집이 항상 물리 sync를 요구하는 것은 아닙니다.
`sage doctor`는 입력·host 예산·렌더 동기화 상태를 확인하는 읽기 전용 진단이며 직접 수리하지
않습니다. 수리 후 진단과 다음 메시지의 재검사를 확인하세요. hook 미실행, 신뢰 거부·timeout
continue, 호스트 밖 임의 실행까지 차단한다고 보장하지 않습니다.

공통 ceiling은 source별 UTF-8 10,000 bytes, wrapper·JSON escape를 포함한 catalog UTF-8
49,152 bytes입니다. Claude에는 별도로 catalog 7,500 UTF-16 code units 한도를 적용하며,
reentry·declared-risk용 2,500 units를 남깁니다. 최종 병합된 한 `additionalContext` 문자열도
10,000 units 이하인지 검사합니다. 한글은 보통 1 unit, 이모지 등 astral 문자는 2 units이며
bytes나 token 수와 같은 단위가 아닙니다. Codex는 공통 ceiling과 `additionalContextLimit=60000`을 유지합니다.

이는 실제 Claude Code 2.1.318에서 기존 49,152-byte catalog가 파일 경로와 preview로
대체된 관측을 반영한 호스트별 지원 예산입니다. [Claude 공식 문자열 제한](https://code.claude.com/docs/en/hooks#json-output)은
각 필드별 10,000자이며 초과 시 파일/preview로 바뀌고 올릴 설정이 없습니다. 7,500은 SAGE가
나머지 문맥 여유를 확보하는 한도입니다. 공통 source ceiling을 만족하는 단일 10,000-byte 입력도
Claude에서는 전체 직렬화 결과로 거부될 수 있습니다. 이는 기존 입력의 새 지원 제한입니다.
`sage doctor`는 공통 입력 유효성과 각 호스트의 catalog 예산 충족을 구분합니다. 초과는 본문 없는
진단과 native 차단으로 처리하며 축약·분할·preview/fetch fallback으로 성공 처리하지 않습니다.
설치·예산 진단은 실제 모델 전달/적용, 여러 turn 누적이나 자동 압축 비용의 검증을 대신하지 않습니다.

## OS 경계와 두 판정 축 (`sage uninstall`)

되돌릴 수 없는 쪽으로 틀리는 유일한 명령이라 경계를 따로 둡니다. 원칙은 같습니다 — **판정은 한
곳에서, 층마다 자기가 아는 것만.**

| 층 | 역할 | 위치 |
|---|---|---|
| 계획·실행 순서 | 단계 순서·rollback·검증. **OS 분기 0건** | `sage/uninstall_executor.py`, `uninstall_plan.py` |
| backend 경계 | protocol과 backend 선택. 무엇을 처리할지는 판단하지 않음 | `sage/uninstall_fs.py` |
| POSIX backend | `dir_fd` 결속 | `sage/uninstall_posix_fs.py` |
| Windows backend | `NtCreateFile` + `OBJECT_ATTRIBUTES.RootDirectory` 핸들 결속. **이 파일만 Windows를 압니다** | `sage/uninstall_windows_fs.py` |

안전성은 첫 변경 전에 대상의 **부모 디렉터리를 열어 붙드는 것**에서 나옵니다. 그 뒤에는 상위 경로
이름이 어떻게 바뀌어도 작업이 원래 디렉터리로 갑니다. POSIX가 `dir_fd`로 얻던 결속을 Windows에서는
부모 핸들로 얻습니다 — 경로 문자열로 되돌아가는 write fallback은 두지 않으며, 없다는 것을 소스
검사가 단언합니다.

### 지원 정책과 capability는 다른 질문입니다

둘을 한 값으로 접으면 "이 환경을 지원한다고 말했는가"와 "여기서 안전하게 할 수 있는가"가 구별되지
않습니다. 그러면 지원 범위 문구를 좁히는 일이 곧 backend 회귀 검사를 잃는 일이 되고, 범위를 좁힐수록
아는 것이 줄어듭니다.

| 축 | 무엇을 보는가 | 어디서 강제되는가 | 화면 |
|---|---|---|---|
| **정책** (`support_policy`) | SKU와 build만 | CLI 한 자리 — 계획 직후·확인 prompt 이전 | `--check`도 `--yes`도 `BLOCKED`(2) |
| **capability** (`probe_capability`) | 볼륨·파일시스템·native 기능·포인터 폭·아키텍처 | 실행 층 | `--check`는 계획, mutation 요청만 거부 |

**정책은 capability를 어느 쪽으로도 단정하지 않습니다.** 그 자리에서 아는 것은 SKU와 build뿐이라
"기능이 없다"도 "기능은 있다"도 재 본 적 없는 말입니다. 정책 진단이 낼 수 있는 사실은 하나입니다 —
지원 범위 밖이고, capability는 이 단계에서 판정하지 않았다.

화면을 다르게 두는 이유는 사용자가 다음에 할 일이 다르기 때문입니다. 정책 거부는 이 환경에서 자동
제거가 결코 일어나지 않으므로 계획만 보여 주면 곧 실행될 것처럼 읽힙니다. capability 제한은 볼륨을
바꾸거나 다른 root를 고르면 참이 될 수 있는 조건이라, 계획까지 막으면 고칠 수 있는 것을 고칠 수 없는
것처럼 보여 줍니다.

아키텍처·폭 판정의 **권위는 제품 한 곳(`native_floor`)** 에 있습니다. CI가 자기 판정표를 따로 들면
제품이 실행하는 환경과 CI가 증거를 만드는 환경이 갈리고, 갈린 뒤에는 어느 쪽이 옳은지 물을 자리가
없습니다. CI 게이트는 그 결과를 소비할 뿐입니다.

## 신뢰 경계 (막는 것 / 막지 않는 것)

**막는 것**
- 드리프트 — spec↔산출물 불일치를 `sage validate`가 적발
- 직접수정 — write-guard가 산출물 직접 편집을 막고 spec으로 redirect
- 단일 모델 편향 — cross-model 리뷰로 반대 런타임이 독립 리뷰
- 게이트 침묵 비활성 — profile 오타·미지 키(게이트를 조용히 끄는 원인)를 `sage validate`가
  fail-closed로 적발. 이는 **검증 시점**의 fail-closed이며, **런타임**의 profile *파싱* 실패는 위
  표대로 fail-open + LOUD로 — 서로 다른 층이다
- 06←05 우회 — 완료 보고를 APPROVED된 리뷰에 결정론으로 묶음
- Loop A 감사 증거의 비재해시 수정·삽입·중간 삭제·재정렬 — run별 strict hash-chain, 레코드
  self-hash, 파일 파싱 무결성을 실제 report gate가 검산
- 미검증 환경의 파괴적 실행 — `sage uninstall`은 지원 정책과 capability 두 축을 **첫 mutation 전에**
  묻고, 확정하지 못하면 거부한다. 판정하지 못한 것은 통과가 아니라 거부 쪽이다 — 부재를 안전
  방향으로 세면 미검증 환경이 조용히 실행된다
- 로컬 hook 부재·우회 — 로컬 hook은 기여자 머신에 SAGE가 설치돼 있다는 전제 위에서만 동작한다.
  SD-9/Fast Cycle은 서버측 authority(`sage/ci_authority.py`, 순수·git 비의존)가 CI에서
  `.sage/fast_cycle.jsonl`·`loop_audit.jsonl`의 strict hash-chain을 독립 재검증해, hook이 없거나
  우회된 기여자의 PR도 required check로 걸러낸다 — 로컬 게이트가 유일한 방어선이 아니다

**막지 않는 것 (설계상 범위 밖)**
- **완전히 장악된 host runtime** — SAGE는 host가 규칙대로 CLI/스킬을 호출한다고 가정합니다.
  악의적으로 조작된 runtime 자체는 방어 대상이 아닙니다.
- **완전 재계산 또는 legacy로 강등한 loop_audit 재작성** — run별 strict hash-chain은 키 순서와
  Unicode 표현을 고정한 canonical SHA-256으로 각 레코드와 직전 run 레코드를 self-verify합니다. v1
  체인 필드가 하나라도 남은 run에서는 hash를 다시 계산하지 않은 수정·삽입·중간 삭제·재정렬을
  탐지하지만, 파일과 체인을 재계산할 수 있는 공격자를 인증하지는 않습니다. 또한 하위호환을 위해 체인
  필드가 전혀 없는 run을 legacy(`chain_ok=None`)로 허용하므로, run 전체에서 세 체인 필드를 모두
  제거한 downgrade는 정당한 legacy run과 구분할 수 없습니다. 비밀 키·서명된 head·별도 artifact의
  tip·Git 기준선·외부 witness가 없으므로 독립적인 tamper-resistance가 아니라 **자체 무결성
  검증(self-verification)** 입니다. tip 수정은 self-hash로 탐지하고, 최종 close 삭제는 report gate의
  `closed` 불변식으로 차단하며, 완전 재계산·전체 필드 제거 재작성의 외부 앵커는 Git 이력과 코드
  리뷰입니다.

경계를 넘는 위협(장악된 runtime, 감사 로그 위변조)은 결정론 게이트가 아니라 cross-model 리뷰·사람
승인 같은 상위 절차가 완화합니다. 결정론 게이트는 "정직한 host의 실수·게으름·드리프트"를 막는
것이지, "적대적 host"를 막는 것이 아닙니다.
