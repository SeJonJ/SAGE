# Overlay 대상별 문맥 전달 — 목표

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 3
Status: VERIFIED_AND_REVIEWED — 새 R2 독립 검토 완료; 출시·전역 설치 별도

## 1. 배경과 기준

기준 브랜치는 `fix/overlay-context-delivery`, 기준 커밋은 `8e17a88`이다. 작업 위치는 `/Users/sejon/project/sage_project_worktree/overlay-context-delivery`이다. 정본 설계는 [대상별 문맥 묶음](../../superpowers/specs/2026-11-05-overlay-context-catalog-design.md) 전체이며, 앞선 초안·실현성 기록은 관측 이력이다.

공유 스킬 overlay의 압축·재개 후 유실, 개인 스킬 overlay의 CLI fetch 의존, Fast에서 표준+Fast 출처의 자동 상속 누락을 하나의 통합 개발 범위로 수정한다. root 문맥에는 스킬 7종의 원문을 대상별 대응표와 함께 공급하고 각 CORE가 자신의 고정 id에 해당하는 출처만 적용한다. 여러 대상의 원문이 같은 문맥에 노출되는 비용과 행동 오적용 위험을 명시적으로 수용한 설계이며 물리 격리를 보장하지 않는다.

## 2. 목표와 승인 경계

최초 승인은00~03이었다. 이후 사용자가 나머지 단계 진행을 요청했다가 **04까지만 진행하고 중지**하도록 제한했고, 잠시 중지 후 재개했다. 현재04 분석·검증 정리까지 수행하고05/06은 미착수다. 실제 `sage-plan`, gate, review-loop로 엔진 자신의 변경을 승인하지 않는다. 커밋·푸시·배포도 하지 않는다. 아래 완료 조건은 통합 제품의 수용 기준이며 부분 검증만으로 체크하지 않는다.

선행 합성 catalog/native 수동 compact 관측과 소수 실제 모델 scope 표본은 설계 실현성 근거다. 제품 collector·설치·자동 압축·적대적 행동 acceptance를 통과한 근거로 승격하지 않는다.

## 3. 필수 범위

| 묶음 | 개발 내용 |
|---|---|
| M1 | 공유/개인 전체 inventory를 event당 공통 수집·검증, 정규화 원문 hash와 root/role별 schema 2 catalog |
| M2 | startup/UPS와 resume/fork/compact 전달 경계, 7종 CORE의 자기 대상 선택 계약 |
| M3 | Fast 3종의 독립 BACKING, 네 슬롯 적대적 회귀, 자격/상속/쓰기 가드 정책 정렬 |
| M4 | 7종의 소유 확인 legacy 공유 span 제거, install/sync/validate/L1/upgrade/rollback/Codex global·local 호환 |
| M5 | 입력 오류/예산 초과의 native 차단, 단일 host 응답, 외부 수리 후 재진입, root/역할 분리 |
| M6 | 명시적 지원 예산과 진단·문서, 후속 native/실제 모델/압축/역할/consumer acceptance 설계 |

## 4. 불변 조건과 제외 범위

공유 > 개인 우선순위와 필수 CORE·프로젝트 정책·독립 gate가 유지된다. Fast view는 공유 표준 → 공유 Fast → 개인 표준 → 개인 Fast이며 표준의 역상속은 없다. root 7종 이외의 worker 4종은 기존 역할 packet과 물리 공유 합성을 유지한다. 개인 본문은 전역 스킬·manifest·영구 cache에 저장하지 않고 다른 checkout에서 승계하지 않는다.

범용 사람 승인 인증, 세션 target/stack DB, transcript parser, 전용 런처/프록시/Codex fork, CORE 전체 축약, 임의 hot reload, 요청 자산만 검사하는 완화는 제외한다. 추가 후보는 완료 조건을 막는 실제 재현·영향·위험도를 근거로 최소 수정만 승격한다. 같은 대화 수리는 기본 범위가 아니며 잘못된 입력은 외부 터미널/에디터에서 고친다.

## 5. Done Criteria

- [x] A1 — Claude/Codex 직접·구조화·암묵 진입에서 존재하는 공유/개인 원문의 앞·중간·끝과 hash가 실제 요청에 있으며 자발적 CLI fetch 없이 성립한다.
- [x] A2 — 양 호스트의 수동·자동 압축과 resume 다음 제품 작업에서 현재 원문이 재전달된다. 과거 요약에 남은 본문이나 수동 재호출을 정상 자동 복구로 세지 않는다.
- [x] A3 — 실제 모델의 표준 호출은 해당 두 슬롯, Fast는 해당 네 슬롯만 적용한다. 다른 target/root 오적용 및 요청하지 않은 Fast 선택·전환이 없다.
- [x] A4 — 중첩 plan/team/review와 반환, 기존 worker·headless reviewer에서 필요한 본문과 역할/출처 분리가 유지된다.
- [x] A5 — 입력 오류·예산 초과·공유 L1 오류·손상 마커·예외가 정상 부분 catalog나 지원 제품 도구 실행으로 이어지지 않으며 외부 수리 후 다음 메시지에서 latch 없이 복구된다.
- [x] A6 — Fast 분류 BACKING, 악성 네 슬롯, 기존 표준 출처 최초 상속, fresh/convert/review/close 회귀가 통과한다.
- [x] A7 — Codex global/local, 두 checkout/worktree, upgrade/rollback, clean wheel consumer에서 개인 비노출·원본 보존·정상본 비교·sync 멱등성이 통과한다.
- [x] A8 — 최대 지원 입력·두 hook 사본·여러 turn 누적·한국어/escape 확장·CORE/대화 여유에서 spill/잘림/연속 압축 루프 없이 동작하며 확정 한도·버전·실측 비용이 기록된다.

## 6. Done Criteria Revision Log

- Revision 1 (2026-11-05): 승인된 설계 A1~A8을 그대로 통합 수용 조건으로 채택. 00~03 작업 한도에 맞춰 모두 미완료로 보존한다. native acceptance 생략은 기준 축소나 면제가 아니다.

## 7. 후속 인계 기준

03 기록에는 수정 파일·결정적 검증의 실제 명령/결과·미실행 항목·잔여 위험을 분리한다. 제품 코드 구현, 설치 설정 지원, 실제 host 전달, 실제 모델 행동, 출시 승인 상태를 서로 대신 보고하지 않는다. 04~06의 후속 승인 없이는 통합 완료·출시 가능·A1~A8 충족으로 표현하지 않는다.

## 8. Phase04 경계 기록

04에서 재현한 설치 손상/L1 예외/Claude 출력 spill을 수리하고 전체 runner R5와 최종 wheel consumer를 확인했다. A1~A8은 모두 부분 근거와 남은 검증을04에 기록했으며 체크박스·기준 문구는 변경하지 않았다. Claude 예산은 catalog7,500/event10,000 UTF16 units로 구체화했다. 공통 source10,000/catalog49,152 UTF8 bytes는 유지한다. 이 지원 한도 보완은 장기·최대 입력 acceptance 면제가 아니며 A8은 미완료다. 사용자 지시에 따라04에서 멈춘다.

## 2026-11-06 예약 실행의 후속 승인

사용자가 02:00 Asia/Seoul부터05 독립 검토와 조건 충족 시06까지 계속 진행하도록 승인했다. 과거04 한도는 해제되었다. 필수 FAIL/NOT_TESTED의 면제, 자기 SAGE gate 승인, 커밋·푸시·PR·머지·릴리스·전역 설치·실사용 설정 변경은 승인되지 않았다. 기존 branch/base/dirty 변경을 보존하고 제품 inventory가04 최종본과 같음을 확인했다. 예약 `6871b7e1-06da-4baf-8e49-5d76bb41c8ac`는 반복 방지를 위해 비활성화하고 재조회 `enabled=false`를 확인했다. 최신 진행·판정은 [05](../05/overlay-context-delivery.md)에 기록한다. 위04 시점의 중지 기록은 이력으로 보존한다.

## 9. 2026-11-06 재개 수용 검산

독립QA가00/01의실제원문과후속NOT_TESTED사유를대조했고, 기준에없던무한/전수시험확대와실제부족증거를구분했다. 누락됐던native암묵/직접진입·resume후제품검증작업·별도apply_patchwire·Codex오류후reentry·혼합설치·mainagent/alias경계증거를추가했다.04의현재유한matrix근거에따라A1~A8진행체크를갱신했다. 기존기준문구/Revision1은변경하지않았고면제/N/A없음. 최종전체회귀와독립05판정은아직별도조건이다.

## Revision2 재개 기록

Changed-At: 2026-11-06
Reason: 고정C4의유효R1에서새실재반례를확인해A5/A7완료체크를재개방함.사용자요구/기준문구축소나면제가아님.
Affected-Phases: 00,01,02,03,04,05
Summary: 非SAGE cwd에서non-overlay상태소유보존,rootSKILLrouting수렴,외부복구절차/진단수리후해당수용을다시증명하고R2를수행.이전미완료05는그대로미승인.


### Revision2 수리 후 기능 검증

고정 C5(product `59a43307...`)에서 R10 전체 4,097항목(14 skip), 실패·오류0/exit0과 새 clean-wheel consumer PASS를 확인했다. 독립 QA는 P01 양 host 설치 entry protocol replay, P02 routing 제거/byte 보존/멱등, P03 read-only doctor와 외부 복구 chain 및 C4→C5 불변 content 계약을 확인했다. A5/A7 기능 재검증으로 체크를 복구한다. 원래 기준 문구를 바꾸거나 면제하지 않았다. Phase05 독립 R2 승인과06 완료는 아직 별도다.


## Revision3 재작업 기록

새고정R1리뷰에서원본LF보존/획득시점retry/dual-hostlocalupgrade/비SAGEemptyreplacement의기존계약반례를확인했다. 원래A1~A8문구는변경하지않고A2/A3/A5/A7증거를재개방한다. 해당기능의좁은수리와재검증·수정본독립확인후에만완료체크를복구한다.


### Revision3 기능 재검증 결과

새R2(product93d541...)에서확정4건의scoped/독립QA,전체R11 4115항목(14skip)/실패·오류0/exit0과freshwheelPASS를확인해기능체크를복구한다. 기준문구·면제·추가요구변경없음. R2독립확인과05승인은별도다.

## 이전 한도 150만 시점의 중단 이력

R2 여섯 FIND는 CLEAR이나 반박자 2명 중 1명만 반환했고, 신규 IO 1,496,807/1,500,000 사용 후 잔여3,193으로 추가 필수 검토 예산을 확보하지 못했다. 기능 체크와 독립 승인 상태를 구분한다. Phase05는 BLOCKED, Phase06 미착수다. 현재 정본은 [05 독립 검토](../05/overlay-context-delivery.md)이며 앞선 중간·중단·대기 기록은 각 시점의 이력이다. 추가 제품 수정·상한 증액·자동 새 리뷰 run은 진행하지 않는다.

## 현재 상태 — 누적 180만 한도 승인 후 검토 완료

사용자의 이번 실행 한정180만 승인 후 같은 고정R2의 두 번째 반박자와 첫 반박자의 원장 보충 확인을 끝냈다. 두 반박자 모두 CONSISTENT/미해결0이다. 새 run은 유효2라운드, 이전run포함cycle3라운드로 수렴했으며 신규IO1,511,409/1,800,000이다. A1~A8 유한 수용 근거와 기준문구는 그대로다. 정본05를 APPROVED로 기록한 뒤에만06을 별도 작성한다. 과거BLOCKED와후속해소원문은 외부증거에 보존한다. 제품/테스트/CI/사용자문서 변경은 없다.
