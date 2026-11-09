# Overlay 대상별 문맥 전달 — 기술 설계

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 3
Status: FULFILLED — 새 R2 독립 검토 완료; 출시·전역 설치 별도

## 1. 계층과 인터페이스

[정본 설계](../../superpowers/specs/2026-11-05-overlay-context-catalog-design.md)의 schema 2를 구현한다. `overlay_delivery`는 현재 checkout root와 명시 role, 공통 전달 정책을 받아 검증한 catalog 또는 본문 없는 구조화 오류를 반환하는 경계다. 공개 API는 `collect_catalog(root: str, role: str="root") -> dict`, `render_catalog(catalog: dict, *, runtime=None) -> str`이며 오류는 본문 없는 `OverlayDeliveryError(code, path)`로 전달한다. parent runtime은 이 collector를 import해 사용한다. 원문 수집을 host adapter에서 중복 구현하지 않는다.

```text
현재 event cwd/검증된 명시 root + 명시 role
  → 기존 root·inventory·path·자격·content validator
  → 한 번 읽은 정규화 source snapshot
  → schema/root/role/sources/targets 및 deterministic generation
  → 최종 host payload 예산 확인
  → 기존 handler 출력 조립 → host JSON 한 개
```

runtime은 event 의미·root·역할·native 오류 변환을 소유하고 collector는 순수 데이터/검증 경계를 소유한다. 설치/정책 계층은 자격과 물리 합성 여부를 분리한다. standalone 순수 gate에 source package import를 새 필수 조건으로 만들지 않는다. 배포 runtime에서 validator를 사용할 수 없는 조합은 성공이 아닌 지원/설치 진단이다.

## 2. Catalog schema와 snapshot

필드는 `schema_version: 2`, canonical `root`, `role: root`, `generation`, `sources`, `targets`다. source key는 `skills/<id>/shared|personal`, 값은 상대 `path`, 실제 공급 문자열의 `sha256`, `content`다. source는 존재하고 공백뿐이지 않은 원문마다 한 번만 싣는다. 누락 슬롯은 source/참조를 만들지 않는다. 아무 본문도 없으면 root/role/generation과 빈 sources/targets를 가진 명시적 정상 없음 상태를 내보낸다.

generation은 schema/root/role과 정규화 source metadata·content·대응표를 일정 순서로 직렬화한 hash다. hash는 무결성·공급 출처 관측이며 사람 승인/권한/실행 준수 증명은 아니다. 같은 generation/출처가 두 경계에서 전달돼도 실행 절차를 두 번 수행하라는 의미가 아니다.

전체 inventory·경로/심볼릭 링크·canonical 명명·CORE roster·자격·예약 토큰·완화 lint를 기존 의미대로 유지한다. shared/personal을 합쳐 한 event의 snapshot을 만들고 같은 문자열을 검사/hash/전달한다. 파일과 목록의 수집 전후 변화를 감지하면 한 번 새로 수집하고 다시 흔들리면 실패한다. unknown/blocked/read error는 부재로 처리하지 않으며 한 출처 오류도 부분 정상 catalog 출력 없이 실패시킨다.

## 3. Target 대응과 CORE 계약

| 대상 | 존재하는 출처만 순서대로 참조 |
|---|---|
| sage-cycle | shared cycle → personal cycle |
| sage-plan | shared plan → personal plan |
| sage-team | shared team → personal team |
| sage-review | shared review → personal review |
| sage-cycle-fast | shared cycle → shared cycle-fast → personal cycle → personal cycle-fast |
| sage-plan-fast | shared plan → shared plan-fast → personal plan → personal plan-fast |
| sage-team-fast | shared team → shared team-fast → personal team → personal team-fast |

Fast 대상 자격을 먼저 확인하고 상속 source마다 같은 검사에 통과해야 한다. 자격이 막힌 Fast 상태를 표준 source 상속으로 우회하지 않는다. `sage-review-fast`는 만들지 않는다.

7종 CORE 앞부분의 고정 target id 계약은 현재 root/role을 확인하고 자신의 `targets[id]`만 추가 지침으로 적용한다. 다른 source가 같은 문맥에 존재해도 현재 대상 지침으로 적용하지 않고 catalog 존재를 호출/전환/승인으로 해석하지 않는다. 공유 > 개인 우선순위와 CORE/프로젝트/독립 gate를 유지한다. 별도 `overlay-local` fetch를 정상 경로로 요구하지 않는다. 모호한 root/role/대상은 최근 대상을 추측하지 않고 보류·확인한다. 정상 compact 복구에서 반복 보류가 나오면 A2 실패다.

부모 우산 view는 child plan/team/review 진입 시 누적하지 않고 child 자기 view를 쓴다. 반환 시 부모 view를 쓴다. 새로운 실행 stack DB를 도입하지 않고 이 동작은 후속 행동 acceptance로 판정한다.

## 4. 이벤트와 실패 상태

| 경계 | 성공 | 실패 |
|---|---|---|
| SessionStart startup | baseline/입력 상태만, 본문은 UPS에서 공급 | 본문 없는 진단, baseline/reentry 결과 보존 |
| SessionStart resume/fork/compact | 현재 root catalog 공급, UPS 도착을 가정하지 않음 | 본문 없는 진단. `continue:false`를 요청 차단 근거로 삼지 않음 |
| UserPromptSubmit | 현재 inventory 재검사와 catalog 공급 | native `decision:block`, 정상/부분 catalog 없음 |
| 지원 PreToolUse | 같은 validator 통과 후 기존 gate로 진행 | native deny/exit 2, 기존 gate보다 앞에서 입력 오류 보류 |

같은 요청 앞 resume/fork/compact와 UPS가 모두 오면 최대 두 사본을 허용하고 비용에 포함한다. 가짜 turn id나 세션 이력 DB로 생략하지 않는다. 새 경계의 빈 상태가 이전 상태를 대체하지만 과거 문맥을 삭제했다거나 hash/mtime로 시간 순서를 판정한다고 주장하지 않는다.

기존 baseline·declared-risk capture·06 baseline/compact reentry 결과와 catalog를 기존 출력 조립 지점에서 host JSON 하나로 합친다. 별도 hook id/범용 shell 부작용 분류기는 만들지 않는다. generated-artifact-write-guard 등록을 지원 PreToolUse 도구로 넓히되 원래 쓰기 판정·phase gate는 유지한다.

진짜 비SAGE root는 pass-through다. profile/manifest 등 SAGE 마커가 존재하나 손상된 root는 오류다. validator 예외도 최상위에서 본문 없는 진단과 native 차단으로 바꾼다. 자동 compact 후 자연어 한 번까지 차단한다고 주장하지 않으며 호스트 밖 임의 실행이나 hook 미실행/timeout continue도 코드만으로 막지 못한다. 복구는 외부 에디터/터미널에서 입력을 고치고 doctor/검증 후 다음 메시지에서 현재 입력을 재검사하는 경로다. latch/repair token/shell 예외를 만들지 않는다.

## 5. 설치·전달 정책

정책표는 자격과 materialize 동작을 별개로 표현한다. root 스킬 7종은 shared/personal 모두 context 경로, worker 4종은 기존 shared 물리 합성+역할별 본문/ref packet이다. blocked 자산은 자기 overlay 등록·적용 대상이 아니며 다른 대상 본문이 같은 문맥에 노출될 수 있는 한계를 문서화한다.

7종 render에서 소유가 확인된 정상 관리 span만 제거한다. 손상 span/소유 불명은 충돌이고 CORE 및 사용자 바이트와 shared/personal 원본은 보존한다. `sync-overlays`, SessionStart L1, validate 예상 블록, install/upgrade 정상본 비교, write guard는 같은 정책을 사용한다. 개인 원문은 global/local SKILL.md·manifest·영구 cache에 넣지 않는다. upgrade 안내는 상속 source 경로/대응만 본문 없이 제공하고 기존 transaction/rollback을 사용한다.

doctor는 구 CLI/구 hook/새 CORE 혼합, 필요한 hook 설정·신뢰·지원 버전·timeout·출력 예산을 진단한다. 실제 native 검증 전에는 자동 전달 검증 완료로 표시하지 않는다. 지원 host·CLI 확정값은 후속 실측 전 미확정으로 표시한다.

## 6. Root와 역할

실제 event cwd와 프로젝트/git 경계 또는 검증된 명시 root/handoff를 사용한다. global 스킬 위치나 최초 cwd를 현재 checkout으로 대신하지 않는다. 다른 root catalog는 적용하지 않고 새 root의 지원 경계에서 다시 공급한다. 새 worktree에 개인 파일이 없으면 정상 부재다.

SAGE headless reviewer/worker는 런처의 명시 역할 packet으로 root catalog 신규 공급을 억제한다. native generic agent_type만으로 역할을 추측하지 않고 명시 역할 없는 자식에도 root catalog를 새로 붙이지 않는다. fork가 이미 상속한 부모의 과거 문맥까지 삭제한다는 뜻은 아니다. worker packet과 headless reviewer CLI 자동 1회 로딩 경로를 구분하고 기존 계약을 유지한다.

## 7. 예산과 진단

source별 한도, 전체 source·대응표·wrapper·같은 handler reentry를 포함한 최종 payload 한도를 명시적으로 검사한다. JSON escape 후 UTF-8 byte 계산과 host가 쓰는 token/출력 한도는 구분한다. 정확한 tokenizer가 없으면 byte 수를 token 수라고 보고하지 않는다. 두 handler 사본·일반 CORE/대화 여유·여러 turn 누적 비용은 후속 실측 항목이다.

Codex `additionalContextLimit=20000`에서 47,700자 합성 입력을 전달한 관측은 제품 한도 확정이 아니다. 03 개발용 잠정 제품 상수는 source별 UTF-8 10,000 bytes, `render_catalog` 최종 UTF-8 49,152 bytes다. 최종 catalog에는 JSON escape가 포함된다. token upper bound는 UTF-8 byte 수와 같은 보수적 상한으로 표시하며 tokenizer 실측치/추정치라고 부르지 않는다. Codex `additionalContextLimit=60000`, reentry 2,048 및 wrapper 여유를 잠정 설정한다. 해당 수치의 단위·합산은 설정 경계에서 분명하게 적고 byte/token을 서로 혼동하지 않는다. 여러 handler 사본·여러 turn·host spill/압축 비용은 A8 미실행이며 이 잠정치를 실제 host 지원 한도 확정으로 표시하지 않는다. source 10,000 bytes는 새 정책이며 기존 validator의 10,000자 제한이 있었다고 표현하지 않는다. 설치/doctor 진단과 후속 A8에서 실측·보완해야 한다. 초과는 총량·큰 source 경로·지원 한도만 진단하며 개인 본문은 로그에 남기지 않는다. 자동 축약/절단/preview/경로-only/fetch fallback으로 성공 처리하지 않는다.

## 8. Fast 독립 보호와 회귀

세 Fast id의 BACKING은 opt-in·상태/감사/계획 결속, lens/round 하한, fresh/converted 제한, 실제 risk와 review level 분리, verification/review/report/close의 기존 독립 oracle에 연결한다. shared-standard/shared-Fast/personal-standard/personal-Fast에서 각각 phase 생략·손상 감사·잘못된 stem/root·risk 불일치·최소 lens/round 감소·fake close·타 review run 재사용·필수 acceptance 누락을 시도해 overlay 텍스트 없이도 거부하는지 확인한다.

`--confirmed-by`는 사람 인증이 아니다. 기존 선택 출처 한계만으로 인증 체계를 확대하지 않지만 새 catalog의 구조적 우회는 자격 개방 전 최소 수정한다. 요청하지 않은 Fast 선택/전환은 후속 A3 실패이며 구조 oracle 통과로 덮지 않는다.

## 9. 구현 검증과 미실행 경계

결정적 개발 검증은 01의 각 소유 영역 matrix로 수행하고 parent가 03에 실제 증거를 기록한다. 이 문서 작성 시점에 제품 구현·설치·호스트/native·실제 모델 행동을 검증했다고 주장하지 않는다. 후속 04에서는 A1~A8을 실제 두 host에서 검증하고 05 독립 L3 리뷰와 06 종료는 별도 승인 후 진행한다. 이번 작업은 03에서 끝나며 제품 출시/승인 상태는 열어 둔다.

## 10. Phase04 실측에 따른 설계 구체화

03 당시 공통 byte 한도만으로는 Claude의 실제 전송 계약을 만족하지 않았다. 49,152-byte catalog가 파일 경로/첫2KB preview로 바뀌는 것을 재현했다. 공통 byte 정책은 유지하고 Claude catalog7,500 및 합친 event additionalContext10,000 UTF16-unit 한도를 추가한다. Unicode surrogate pair는2units로 계산하는 보수적 상한이며 token 수가 아니다. `render_catalog(..., runtime='claude')`와 최종 merge guard가 같은 helper를 사용한다. 초과는 자동 fetch/절단으로 통과시키지 않는다. 정확7,500의 한국어·quote·emoji 포함 native 전체 원문/hash와7,501의 요청 전 차단을 확인했다. 장기 반복 압축·최대 입력 실제 모델 acceptance는 남아 있다.

QG-01/02 반례에 따라 UPS/PreToolUse의 `current()`는 source 검증에 이어 현재 host 설치의 materialize 계획을 읽기 전용으로 확인한다. 손상 render나 남은 sync 계획은 보류한다. SessionStart는 먼저 collector를 검사하고 L1 sync를 시도하되 예외에 본문 없는 오류를 내며 catalog를 억제하고 baseline/reentry는 시도한다. 지속 오류 latch는 만들지 않아 외부 수리 후 재검사로 복구한다.

자세한 실제 결과·이전/최종 subject 구분·열린 acceptance는04 기록이 정본이다. 최초03까지 제한한 이 문서의 작성 시점과 현재04까지 실행한 범위를 구분한다.05/06은 미착수다.
