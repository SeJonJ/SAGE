# Overlay 통합 전달 — 개발 완료 보고

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 3
Loop-Run: external-20261106-restart-1
Source-05: docs/plan_docs/05/overlay-context-delivery.md
Status: COMPLETE — 개발·유한 검증·독립 검토 완료; 커밋·배포·실사용 설치 별도
Product-Hash: sha256:93d541024b737af26048290415aa8b513855330ef411aa9e591d2ded5efbb611
Review-Patch-SHA256: 183c47d89cff6ee53b06bd2955509e02c0c1910ce970c112fbb070f0ac6a6f91
Source-05-SHA256: d040ec7207d0ec2064d6a596a25815116c0a29f836b315f9070d848b38244bca

## 1. 완료 요약

원래 세 문제인 **공유 overlay의 압축·재개 후 유실, 개인 overlay의 자발적 CLI 조회 의존, Fast의 표준+Fast 상속 누락**을 하나의 전달 경로로 수정했다. Claude Code와 Codex 양쪽의 제품 경로를 구현하고, 정해진 유한 수용 기준 A1~A8과 최종 회귀·설치 wheel·독립 검토를 마쳤다. 제품은 `fix/overlay-context-delivery` worktree에 있으며 커밋·배포·실사용 설치는 하지 않았다.

이 보고서는 [05 독립 검토](../05/overlay-context-delivery.md)가 APPROVED로 기록된 **다음 별도 변경**에서 작성했다. 00~05의 Cycle-Stem/Revision3/L3/한국어, 00의8개 체크, 01/04의 required/evidence ID 및 PASS, source와 승인 문서 hash를 작성 직전에 다시 대조했다. SAGE의 개발 절차를 외부에서 사용했으며 개발 중인 SAGE 자체 gate/review-loop/waiver로 자신을 승인하지 않았다. 사용자 최종 인수나 출시 승인과 개발 사이클 완료는 구분한다.

## 2. 전달한 가치

| 원래 문제 | 수정한 동작 | 필요한 이유 |
|---|---|---|
| 공유 overlay가 압축·재개 뒤 빠짐 | 현재 원문을 검증한 catalog를 메시지/해당 재진입 경계에서 다시 공급 | 지난 요약이 규칙 원문을 기억한다고 가정하지 않도록 함 |
| 개인 overlay가 CLI fetch 여부에 달림 | 같은 수집·검증 경로에 개인 원문도 포함해 필요한 문맥을 자동 공급 | 모델이 먼저 파일을 찾아 읽어야만 적용되는 의존 제거 |
| Fast에서 표준 overlay 상속 누락 | Fast는 공유 표준→공유 Fast→개인 표준→개인 Fast 순서의4개 슬롯 적용 | 표준 규칙 위에 Fast 추가 규칙을 함께 적용한다는 사용자 결정 구현 |

일반 모드는 공유 표준→개인 표준의2개 슬롯을 적용한다. 해당 파일이 실제 존재하는 경우만 공급하며 Fast 전용 지침을 일반 모드로 역상속하지 않는다. 필수 CORE·프로젝트 정책·독립 gate와 공유 우선순위를 유지한다. root에는7개 대상의 대응표와 원문이 함께 들어가고 각 CORE는 자신의 고정 target을 선택한다. **다른 target 원문의 물리적 비노출을 보장하는 구조는 아니다.**

쉽게 말하면 작업할 때마다 **현재 규칙 묶음을 다시 펼쳐 주고**, Fast 작업이면 그 안의 표준 규칙과 Fast 추가 규칙을 함께 보도록 바꿨다. 어느 규칙을 쓸지는 대상표로 정하고, 파일이 잘못됐거나 지원 크기를 넘으면 일부 규칙만 조용히 적용하지 않고 해당 제품 경계에서 오류를 알린다.

### 실제 변경 지점

| 부분 | 주요 파일·책임 |
|---|---|
| 공통 수집과 대상별 내용 | `sage/overlay_delivery.py` — inventory 검증, 본문/hash/target catalog, snapshot와 예산 |
| 양 host 실제 전달 | `sage/hook_entry.py`, `scripts/sage_harness/hooks/runtime/overlay_context.py`, `runtime/hook_runtime.py`, 두 IO adapter — UPS/재진입, root와 독립 정책 상태 분리, 단일 host 응답 |
| 표준/Fast 적용 | `templates/core/skills/`와 대응 framework render — root7개 자기 target 선택, Fast4슬롯·독립 BACKING·기존 쓰기 보호 |
| 설치와 복구 | `sage/overlay_materialize.py`, install/generate/upgrade/doctor — 소유한 legacy span만 정리, 손상/구버전 거부, 외부 복구 안내, 기존 transaction |
| 배포 검증·문서 | `scripts/ci/check_consumer_integrity.py`, runner/회귀와 한영 사용자 문서 — fresh wheel import·정상/변조, 제한·복구·전달 설명 |

전체 검토 경로는 코드·테스트·CI·사용자 문서74개다. 후반 새 R1에서 확정해 고친 부분은 그중 **제품5파일+테스트4파일의9경로**다. 여러 파일이 바뀐 이유에는 양 host adapter, spec/render 쌍, 언어, 설치와 회귀 연결이 포함되며 파일 개수를 새 기능 개수로 세지 않는다.

### 리뷰에서 추가로 수리한 최소 연결 결함

| 결함 | 왜 고쳤는지 | 수정 경계 |
|---|---|---|
| routing 제거가 사용자 마지막 줄바꿈을 줄임 | 원본 바이트 보존 계약 위반 | 검증된 routing span만 제거; 두 host/두 계획/실제파일/멱등성 확인 |
| 수집 중 directory 교체가 재시도를 건너뜀 | 안정 상태로 회복 가능한 기존 경합을 일반 오류로 처리 | 획득 중 disappearance/replacement만 기존2attempt에 포함; 권한 오류는 즉시 실패 |
| 두 local host upgrade에서 secondary CORE가 구버전으로 남음 | 두 host 전체sync가 구selector에서 실패 | 기록된 두 local CORE를 기존 transaction에서 먼저 설치; 양 primary 순서와 rollback 확인 |
| 비SAGE 경계로 옮겨도 이전 catalog가 최신으로 남음 | 현재 overlay가 없다는 상태도 갱신해야 함 | 해당 P→N 전환에 기존schema의 빈 N catalog 공급; 부모 baseline/risk·child/startup 경계 유지 |

이 수리로 새 인증/상태DB/정책 집계/프록시/추가 전역 설치 기능을 만들지 않았다. 반증된 지적8개를 개발 범위로 자동 편입하지 않았다. 기존 worker4종의 물리 shared 합성과 명시적 역할 packet도 유지한다.

## 3. 검증과 독립 리뷰

| 구분 | 실제 확인한 결과 |
|---|---|
| 최종 전체 회귀 R11 | unittest Ran 합계 **4,115항목,14skip포함**, 실패·오류0/exit0. 반복 포함 로그 합계이며 고유 테스트 전수 수 아님 |
| fresh wheel | build/install/격리 installed import/정상validate0/실제runtime변조validate3, engine sentinel 불변 PASS |
| 검토/패키지 동일성 | 현재 reviewed74경로, 배포 logical216파일, 전체 branch patch가 고정R2 bytes/hash와 일치 |
| 별도 QA | scoped12개, 실제 rename/chmod, Unicode suffix·LF3개, 실제 구base 양primary dual-local upgrade, 양host entry/adapter P→Nempty→P/API3 확인 |
| A1~A8 | 00의 원래 문구를 유지한 유한 수용 근거PASS. 각 항목의 근거와 한계는 [04](../04/overlay-context-delivery.md)와 [독립QA](../04/phase05-resume-qa.md)에 기록 |
| 새 R1 | Codex5관점+fresh Claude, 전체 라운드 반박자2명: 원자 지적12개 중 기존설계내4건 수리·8건 양쪽 반증 |
| 새 R2 | 다시 Codex5관점+fresh Claude, 반박자2명: 신규지적0·수리4건모두closed·미해결0, Phase05 APPROVED |

리뷰는 **R1 전체 원래 변경+의존성, R2 전체9파일 재작업+완전한 변경 함수·연결 경계+불변 파일 hash 연결**의 누적 방식이다. R2에서 원래 전체 PR의 모든 unchanged raw source를 다시 읽었다고 표현하지 않는다. 호출 수는 라운드 수가 아니며, 새 run 유효2라운드·이전run포함cycle3라운드다. 첫 반박자의 비용/다른 반박자 receipt 공백은 원문BLOCKED를 보존한 뒤 같은 session의 추가 확인으로 해소했다.

원자료 `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106`의 `round2-final.json`, `external-approval.json`, `budget-final.json`, `r11-summary.json`, `clean-consumer-r11/report.json`, `wheel-r2-bridge.json`, `qa-r2.json`을 따른다. R11 log SHA `3db24271bbec5a75a463f66d1758356a817938ee9289f2e6c7c17b70a4e66bf6`, wheel SHA `adb48c9982751dfb35e166e8d15e9bb9dadec2a2725cebb799bebb47f9bf4d23`다.

### 실제 host/model 증거의 정확한 범위

- 기존 native 전달/압축·resume와 실제 모델의 일반2/Fast4 적용·유한 악성 슬롯·역할 표본은04의 관측 버전과 원자료를 따른다. Claude Code2.1.318 및 Codex0.166.0의 결과이며 이후 모든 버전/세션을 보장하지 않는다. formal Claude peer CLI2.1.319는 이 native 수용 시험의 버전과 별개다.
- 최종 수리 뒤 `_collect`/`render_catalog`/`_snapshot` 및 root7 CORE의 정상 내용 계약은 hash로 연결했다. `collect_catalog` retry 제어와 runtime/upgrade/materialize는 변경됐으므로 이번 국소 회귀·QA로 별도 확인했다.
- **새 P→N empty 조합은 실제 설치 entry/adapter protocol replay**다. 자연 발생 native host가 그 event를 만들었거나 실제 모델이 빈 catalog를 적용했다고 승격하지 않는다.
- remote GitHub Actions, 다른OS/Python 전체matrix, 실사용 프로젝트/전역 설치는 실행하지 않았다. local PASS를 그 결과로 대신하지 않는다.

## 4. 비용과 배운 점

이번 새 리뷰의 한도는 사용자 승인으로150만→**이번 실행에 한해 누적180만**이 됐다. 최종 실제 신규 입력+출력은 **1,511,409**, 잔여 **288,591**이며 추가 승인 후 사용량은14,602다. 기존 비용은 초기화하지 않았다. 이전 수동run1,266,080과 그 전 무효subject run725,694는 별도 이력으로 보존한다. root/구현/QA 토큰 사용량은 리뷰 subcall 원장 밖의 미측정 값이며0이 아니다.

150만 안에서 마무리하지 못한 원인은 마지막 반박 packet의 고정 요청 비용·두 역할의 여유를 낮게 예상한 진행자의 비용 관리 실패였다. scope가 커져서 마지막에 새 개발이 필요했던 것이 아니다. 앞으로의 같은 방식 리뷰에서는 역할별 실제 요청비용과 보충 가능성을 먼저 확보해야 한다. 이번 작업에서 새 비용 관리 기능이나 정책을 제품에 추가하지는 않았다.

재개 누적 usage는 before/after 차분으로 계산하고 actual model/session/prompt/source를 함께 기록했다. 도구 호출 수·renderer 표본·mock/native/실제모델·단위검사·독립승인을 서로 대신 세지 않았다. 이전BLOCKED·잘못된 예상·parser 오류·추가 증거 뒤 판정 변경을 삭제하지 않고 현재 결과와 구분해 보존했다.

## 5. 남은 확인 한계와 인수 경계

현재 승인된 범위의 미해결 finding은0이다. 아래는 새 개발에 자동 추가하지 않은 확인 한계다.

- 모델 행동과 장기압축은 유한 표본이며 무한 안정성/모든 Unicode/미래버전/worker 자체compact 전수를 보장하지 않는다.
- Claude peer가 비차단이라고 명시한5개 note: 손상legacy scope receipt의 정확 repair route, 이번R2에서 재독하지 않은 routing helper/anchor, 비SAGE의 특이 sage경로, primary-global+secondary-local 정확E2E조합, installed_hosts없는dualmanifest의 실제producer 확인. 원문은05/`reviews-r2/peer/parsed.json`에 보존한다.
- 지원 예산은 공통 source10,000/catalog49,152 UTF8 bytes, Claude catalog7,500/event10,000 UTF16 units다. byte/unit을 token 과금량으로 혼동하지 않는다.
- 현재 결과는 구현·격리 검증·독립검토 완료다. 사용자 최종 인수, git commit/push/PR, 원격CI, 머지/릴리스/실사용 설치는 별도다.

## 6. 지식 캡처와 후속 상태

이 엔진 외부-method run에는 project profile/knowledge write-back이 설정돼 있지 않다. wiki 갱신이나 SAGE 자신의 write-back/retro/cycle clear 명령을 자동 실행하지 않았고 완료했다고 주장하지 않는다. 회고는 위 비용·증거·범위 기록으로 남겼다. 외부 raw receipt·동결 source와 이 worktree의00~06 문서를 보존한다. 현 보고 뒤 추가 제품 개발·추가 모델 리뷰 호출은 예정하지 않았다.
