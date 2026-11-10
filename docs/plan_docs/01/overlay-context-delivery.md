# Overlay 대상별 문맥 전달 — 요구사항과 구현 계획

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 3
Status: FULFILLED — 새 R2 독립 검토 완료; 출시·전역 설치 별도

## 1. 근거와 요구사항

[00 목표](../00/overlay-context-delivery.md)의 A1~A8을 수용 기준으로 사용한다. [정본 설계](../../superpowers/specs/2026-11-05-overlay-context-catalog-design.md)와 충돌하는 구현 편의상의 완화는 하지 않는다.

| 요구사항 | 개발 계약 | 장래 수용 조건 |
|---|---|---|
| R1 | 7종 × shared/personal 최대 14 source, Fast는 source 복제 없이 참조 상속 | A1/A3/A6 |
| R2 | event당 공유·개인 inventory 한 번 수집, 한 문자열로 lint/hash/전달, 불안정 입력 1회 재시도 후 실패 | A1/A5 |
| R3 | startup은 baseline만, UPS에서 초기 본문; resume/fork/compact는 UPS를 가정하지 않고 재전달 | A1/A2/A8 |
| R4 | root/role 고정, CORE가 자기 target만 사용, parent/child/return view를 합산하지 않음 | A3/A4 |
| R5 | SessionStart 오류는 본문 없는 진단; UPS block, 지원 PreToolUse deny/exit 2 | A5 |
| R6 | 7종 context 공급과 worker 물리 합성을 분리, 관리 span만 제거, 원본·사용자 바이트 보존 | A4/A7 |
| R7 | Fast 세 대상 자격 개방을 independent BACKING·기존 gate·적대적 테스트에 연결 | A3/A6 |
| R8 | 최종 escape/wrapper/reentry 비용과 지원 한도를 계산·진단; oversize는 축약하지 않고 실패 | A5/A8 |
| R9 | empty catalog가 직전 상태를 대체, stale 정상 generation이나 부분 정상 catalog를 내보내지 않음 | A2/A5 |
| R10 | Codex global/local·비SAGE pass-through·손상 SAGE 마커 fail-closed·외부 수리 경로 설명 | A5/A7 |

## 2. 역할과 파일 소유

| 담당 | 소유 파일/영역 | 의존 관계 |
|---|---|---|
| collector | `sage/overlay_delivery.py`, `tests/test_overlay_delivery.py` | 기존 validator 재사용. policy 담당의 공통 전달 정책을 소비 |
| policy/install | `sage/overlay_classify.py`, `sage/overlay_materialize.py`, `sage/commands/install.py`, `sage/commands/generate.py`, doctor 경로, 설정 등록 및 해당 테스트 | context/physical 정책, Fast BACKING, legacy span 정리, 설정/진단 |
| parent runtime | `sage/hook_entry.py`, `scripts/sage_harness/hooks/runtime/` 및 해당 테스트 | collector API 연결, event/root/role/native 차단, 단일 출력 |
| CORE | 7종 skill spec와 render, 관련 사용자 문서와 selector 테스트 | collector schema와 고정 target 계약. 필요시 parent 담당 |
| leader | `docs/plan_docs/00/`, `01/`, `02/`의 본 cycle 문서 | 제품 코드 수정 없음. 03 기록은 parent 작성 |

테스트는 기존 repository suite 위치를 따른다. 위 새 collector 테스트 경로는 역할 소유 명시이며 실제 harness 위치로 조정할 경우 03에 정확한 경로를 기록한다. 공유 파일 변경은 소유 담당에게 연결하고 같은 파일을 동시에 수정하지 않는다. 한 branch의 통합 변경이며 별도 릴리스로 쪼개지 않는다.

## 3. 03 구현 순서

1. 기준 commit·branch·기존 dirty/untracked 상태를 확인한다. 정본 설계와 기존 validator/설치/호스트의 계약을 읽고 필요한 실패 fixture를 고정한다.
2. 정책 담당은 context 대상 7종과 physical worker 대상의 명시 정책을 분리하고 Fast 세 대상의 BACKING을 기존 독립 oracle·테스트와 연결한다. 단순 allowlist 추가로 끝내지 않는다.
3. collector는 순수 schema 2 수집·검증·hash·직렬화·예산/빈 catalog·불안정 입력 처리를 구현한다. 공개 API는 `collect_catalog(root: str, role: str="root") -> dict`, `render_catalog(catalog: dict) -> str`, 본문 없는 `OverlayDeliveryError(code, path)`로 고정하며 임의의 두 번째 validator를 만들지 않는다.
4. CORE는 7종 spec와 두 host에 공급되는 render 계약을 함께 수정한다. 고정 자기 id를 앞부분에 놓되 기존 STOP·CORE 우선순위·필수 단계를 보존한다.
5. runtime은 collector를 기존 event 조립 지점에 연결한다. SessionStart/UPS/PreToolUse가 여러 JSON을 연속 출력하지 않도록 기존 baseline·declared-risk·reentry 결과와 합성한다.
6. 설치 담당은 정상본 비교·span 정리·sync/L1/validate/write guard·hook matcher/출력 한도·doctor를 동일 전달 정책에 맞춘다. 개인 본문을 영구 결과물에 넣지 않는다.
7. 각 소유 영역의 실패·회귀 테스트와 통합 계약 검사를 실행하고 실제 결과를 03에 기록한다. 여기서 실행하는 것은 개발 중 결정적 검증이며 native acceptance나 Phase 04 승인으로 세지 않는다.
8. 03에서 구현/설정/미실행 native 수용 조건/잔여 위험을 구분하고 중지한다. 04~06, 커밋·푸시·배포를 실행하지 않는다.

## 4. 결정적 개발 검증 계획

| 영역 | 확인할 성질 |
|---|---|
| collector | 최대 14 source, 7 target, 정확한 Fast 순서, whitespace/empty/삭제, 읽기/hash 동일 문자열, inventory 오류 전체 실패, retry 1회, symlink/root/명명/예약 토큰/완화 lint |
| runtime | startup 미주입, UPS 1 catalog, resume/fork/compact 재주입, host당 단일 JSON, stale/다른 root/child 억제, marker 손상 및 validator 예외의 native 차단 |
| policy/install | context 7종과 physical worker 구분, Fast 자격·BACKING, 정상 관리 span만 제거, 손상/불명 소유 충돌, sync 멱등성·upgrade/rollback·개인 비노출 |
| CORE | 7종 spec/render 자기 id 일치, target 순서, shared 우선, CORE/gate 보존, 다른 target/자동 Fast 오적용 금지 문구 |
| 보안 회귀 | 악성 네 슬롯의 phase 생략/risk 하향/lens·round 감소/손상 audit/fake close/타 run 재사용/acceptance 누락을 독립 oracle이 거부 |
| 예산 | 최종 직렬화 bytes와 명시적 계산 방식, 총량·source 한도, 진단에 개인 본문 미포함, 초과 시 정상 부분 본문 미출력 |

기존 test runner와 source-tree 검사에 맞는 명령을 사용하고 03에 실제 명령·rc·결과를 적는다. `sage validate`, 생성/manifest stamp, package smoke 등이 엔진 자신의 승인 gate를 동반하거나 범위를 넓히는 경우 승인을 대체하지 않으며 실행 범위를 먼저 확인한다. framework 전체 재생성은 하지 않는다.

## 5. 후속 04 native acceptance 계획 — 이번에는 실행하지 않음

두 host별 버전·모델·입력 fixture·요청 원문·압축 경계·설치 형태를 보존한다. A1 전달 확인 후 A3 행동 확인을 진행하고 A2/A4/A8 압축·중첩·역할·큰 payload를 구분한다. 한 host 결과나 합성 모델 결과를 다른 host/실제 모델의 근거로 사용하지 않는다.

수동/자동 compact와 resume, Codex 구조화 선택/직접·암묵 진입, Claude native 스킬 호출, root 변경/두 checkout, child 역할 packet, 잘못된 입력·지원 도구 deny·외부 수리, clean wheel consumer, 한계 크기와 두 hook 사본 비용을 시험한다. A3에서 요청하지 않은 Fast 자동 선택·전환이 재현되면 출시 차단이며 BACKING GREEN으로 면제하지 않는다. 05 독립 L3 리뷰와 06 완료도 이번 범위 밖이다.

## 6. 추가 범위 처분

worker 개인 자동 공급 확대·자체 compact 복구, 동일 boundary 중복 억제, 같은 대화 입력 수리는 현재 필수 확장이 아니다. 기존 정상 packet 회귀나 예산 장애처럼 재현된 완료 조건 장애가 나오면 재현·영향·최소 수정·잔여 위험을 03에 남기고 해당 경로만 검토한다. 사람 인증 서버·영구 target DB·범용 shell 분석기는 추가하지 않는다.

## Phase05 입력 정리 — 필수 수용 대응표

2026-11-06 후속 승인에 따라 아래는00 Revision1의 기존 A1~A8을 명시적으로 대응시킨 표다. 범위·기준을 축소하거나 새 면제를 만들지 않았다. 아래 required 항목은04의 동일 ID 증거와 대조한다. 과거03/04 한도 문구는 당시 실행 이력이다.

| ID | 필수 여부 | 수용 조건(00 Revision1) |
|---|---|---|
| A1 | required | 두 host 직접·구조화·암묵 진입, 전체 원문/hash 자동 공급, 자발적 CLI fetch 없음 |
| A2 | required | 수동·자동 compact/resume 뒤 다음 제품 작업의 현재 원문 재전달 |
| A3 | required | 일반2/Fast4 자기 출처 적용, 타 target/root 오적용과 요청 없는 Fast 선택·전환 없음 |
| A4 | required | nested plan/team/review/return 및 worker/headless reviewer 역할·출처 유지 |
| A5 | required | 입력·예산·L1·손상·예외의 부분 catalog/지원 도구 실행 차단 및 외부 수리 후 복구 |
| A6 | required | Fast BACKING, 악성 네 슬롯, 표준 최초 상속, fresh/convert/review/close 회귀 |
| A7 | required | global/local, 두 checkout, upgrade/rollback, clean wheel의 비노출·원본·정상본·멱등성 |
| A8 | required | 최대 입력·두 사본·여러 turn·한국어/escape·CORE/대화 여유, spill/잘림/연속 압축 루프 없음, 한도/버전/비용 |
