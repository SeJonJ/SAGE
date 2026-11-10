# Phase05 재개 — 수용 기준의 유한 검증 범위와 독립 재계산

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Status: OBSERVATIONS_AND_GAPS — 기준 변경·면제·최종 승인 아님
Evidence-Date: 2026-11-06

## 독립 판단

A1~A8 전체를 계속 NOT_TESTED로 두게 한 **일부 후속 요구는 00/01·정본의 필수 범위를 넘어섰다**. worker 자체 압축/fork 전수, 모든 악성 지침과 실제 전체 workflow의 곱집합, OS/실사용 설치 전수, 무한 장기 안정성·모든 worst-case·catalog 전용 tokenizer는 기존 완료 조건에 없다. 이를 새 필수 요건처럼 요구할 수 없다. 반대로 실제 재현한 reentry 오류, 구 runtime 혼합, 주 세션 role 오인 등의 코드 지적은 없어지는 것이 아니며 독립 처분·필요 수리·최종 후보 회귀가 필요하다.

이 판단은 기준 축소가 아니다. 기존 원문의 관측 가능한 각 요구를 아래처럼 유한한 case로 매핑하고, 관측하지 않은 조합을 명시하되 전체 검증을 무한히 늘리지 않는다는 뜻이다. 실제 모델의 제한된 표본은 해당 표본의 행동 근거이며 모든 미래 모델/세션의 완전 준수 보장이 아니다. 원문도 그런 확률 보장을 요구하지 않는다.

00/01, 02와 정본 설계의 관련 절, 03 증거, 04 모든 개별 evidence, `phase05-followup-evidence.md`, 05 BLOCKED 문서를 읽었다. 제품 source/test와 00/01을 수정하지 않았고 실제 계정 모델은 호출하지 않았다. 엔진의 SAGE gate/review-loop/waiver를 승인 수단으로 실행하지 않았다. 이 문서는 최종 acceptance 상태나 06 완료를 선언하지 않는다.

## 원문과 달라진 추가 요구

| 항목 | 기존 원문 | 후속 기록에서 확대된 요구 | 독립 처분 |
|---|---|---|---|
| A1 | 직접·구조화·암묵 진입의 **실제 요청에 원문/hash**, 자발적 **CLI fetch** 없음 | 실제 계정 모델이 모든 조합에서 자발적으로 implicit 선택 | A1의 자발적 fetch 금지는 implicit 선택의 자발성 보장과 다르다. 실제 host의 implicit 도구/선택 경로와 raw 요청을 확인해야 하지만 모델의 자발 선택 확률 전수는 별도 요구가 아님 |
| A2 | 수동/자동 압축·resume **다음 제품 작업에서 현재 원문 재전달**, 재선택/과거 요약으로 대체 금지 | 제품 개발 workflow 전체 완주, 모든 source 변경×lifecycle 조합 | 유한 후속 제품 검증 작업과 fresh 전달·새 source 관측을 결합하면 평가 가능. 실제 코드 개발 전체 완주를 새 기준으로 추가하지 않음 |
| A3 | 실제 모델의 표준2/Fast4, 타 target/root와 요청 없는 Fast 오적용 없음 | 모든 악성 phase/risk/audit 지침×모든 workflow×반복 신뢰도 보장 | 작은 실제 모델 표본은 필요. 네 슬롯 유혹·타 root 사례와 구조 oracle을 구분해 평가하되 무한 반복/전수 행동 보장은 요구하지 않음 |
| A4 | nested plan/team/review/return, **기존 worker·headless reviewer의 필요한 본문/역할/출처** | worker4종 모두 native 전수·child 자체 compact/fork 자동 복구 | 01 §6은 worker 개인 자동 공급 확대/자체 compact를 현재 필수 확장에서 제외한다. 정본 §11은 실제 child packet 유실 반례 때만 최소 연결을 추가하고 §13도 추가 후보로 명시한다. 기존 packet 회귀는 필수이나 반례 없는 child compact 자동화 전수는 필수 아님 |
| A5 | 오류 분류와 지원 제품 도구 차단/외부 수리 복귀 | 오류 전부×host 전부×tool 전부의 곱집합 | 각 오류 분류와 각 native dispatch 방식/차단 wire의 커버는 필요. 공통 validator가 도구명과 무관하다는 코드/단위 근거와 native 대표 경로를 결합할 수 있으며 모든 곱집합만이 유일한 증명 방법은 아님 |
| A6 | BACKING·악성 네 슬롯·표준 최초 상속·fresh/convert/review/close **회귀** | 악성 실제 본문×각 workflow의 실제 계정 모델 전수 행동 | 정본 §12는 **overlay 텍스트를 읽지 않는 독립 oracle에 악성 상태를 주입**하도록 명시한다. 기존 구조 회귀를 실제 모델 workflow로 대체하거나 무효화하지 않음. A3 행동 회귀는 별개로 유지 |
| A7 | global/local·두 checkout/worktree·upgrade/rollback·clean wheel의 비노출/원본/정상본/멱등성 | 모든 OS/Python matrix·실사용 프로젝트 설치·전체 곱집합 재실행 | 원문에 OS/실사용 설치 전수 없음. 격리 consumer의 각 명시 경로와 공통 함수 경계를 검증하면 됨. 원격 CI/다른 OS 미실행은 한계로 기록하되 A7의 새 요건으로 만들지 않음 |
| A8 | 최대 입력·두 사본·여러 turn·한국어/escape·CORE/대화 여유에서 무spill/무잘림/무연속 압축루프, 한도/버전/**실측 비용** | 무한 장기 제품 workload, 모든 escape/worst-case, catalog 전용 tokenizer 측정 | 정확 상한의 유한 누적/실제 압축/정상 후속 응답은 의미 있는 수용 표본. 실제 비용은 단위를 구분해 기록해야 하나 catalog 전용 과금이나 무한 안정성 보장은 원문에 없음 |

root `SessionStart source=fork` 전달 계약 자체는 M2/R3에 남는다. 위 A4 판단은 이를 제거하지 않는다. root fork 이벤트 전달과 worker 자신의 packet 자동 복구는 서로 다른 항목이다. 부모에게서 상속한 과거 문맥 삭제도 정본에서 보장하지 않는다.

## 유한 검증 대응표

아래는 새 00/01 기준이 아니라 기존 요구의 증거 검산용 대응표다. 동일한 wire/validator를 공유한다는 근거가 있는 범위에서는 무조건 host×tool×오류 전수로 확대하지 않는다. `기존 근거 있음`은 최종 후보 전체 PASS 선언이 아니다.

| ID | 유한하게 확인할 case/기대 관측 | 기존 근거 | 실제 추가 확인 우선순위 |
|---|---|---|---|
| A1-a | 두 native host UPS 정상 catalog: 14 source content/path/hash 전체 일치; 앞/중간/끝 포함 | Claude raw startup/Skill/max 요청, Codex structured/direct/implicit raw 요청 exact-match | 최종 source 변경의 영향 경계 확인. Claude implicit 별도 경로가 기존 Skill case와 다른 이벤트라면 한 native mock endpoint case로 보완 |
| A1-b | host별 지원 direct/structured/implicit 진입이 같은 현재 UPS catalog를 소비, 별도 overlay-local fetch 없음 | Codex 세 경로, Claude native Skill 전후 raw 요청 및 실제 모델 적용 | Claude 실제 quota 실패는 성공 표본 아님. 다만 실제 계정의 자발 선택 전수는 추가하지 않음 |
| A2-a | host별 manual compact/auto compact/resume 후 현재 catalog 신규 전달, 다음 유한 검증 작업 응답, 수동 재선택 없음 | 두 host 실제 계정 압축·resume와 native raw capture; Claude 새 source 적용 후 체크리스트 3회 | Codex 마지막 resume 응답 `PROBE_MODEL_REACHED`는 의미적 제품 작업 근거가 아님. 신규 전달은 native raw와 결합 가능하나 필요하면 후속 current-view 작업 1개로 경계를 좁혀 보완 |
| A2-b | source 변경/삭제 후 fresh 또는 empty generation이 현재 상태 대체 | Claude changed-source resume, collector 삭제/empty fixture | 오류 후 reentry가 rc2로 유실된다는 R1-01은 native에서 직접 확인/수리 후 재검증 필요 |
| A3-a | 실제 모델 표준2/Fast4 자기 순서, 타 target 유혹 거부 | 양 host 기존 std/Fast, 양 host 네 슬롯 유혹8표본 | 현재 변경이 selector/역할/root에 영향을 주면 해당 분기만 재검증 |
| A3-b | 같은 대화의 다른 checkout에서 새 root 두 표지, 이전 root 적용 없음 | Codex `real-crossroot-fixed`의 실제 두 응답 | 모든 host×모델×target의 확률 전수는 불필요. 원문이 명시한 root 오적용 실제 표본은 존재 |
| A4-a | cycle→plan→team→review→cycle 반환에서 각 자기2개, 누적 없음 | Codex `real-nested`, 실제 CORE read-tool/응답 sequence | 이 원문은 독립 Agent session을 필수 중첩 방식으로 고정하지 않음. 실제 제품 workflow 완료를 추가 요구하지 않음 |
| A4-b | loader가 각 기존 worker 자기 content/ref, 일반 역할은 root 신규 catalog 없음 | 기존 역할 진단+이번 고정 snapshot 4역할×2runtime 검사 | 새 main `--agent`가 root와 child를 구분하는지 R1-05 별도 native payload 확인 필요 |
| A4-c | actual worker packet 수신·필요한 자기 shared/personal/ref, headless 두 host 한 번 append | 실제 Claude Agent spawned1/completed1, 양 실제 headless reviewer | packet/launcher 변경 없음 hash bridge 가능. child owncompact/fork 자동화는 실제 회귀 반례 없으면 새 blocker로 삼지 않음 |
| A5-a | source/예산/L1/marker/예외 각각 정상 부분 catalog 없음, UPS/지원 도구 차단 | source/budget/native, 실제 권한 QA·Codex, collector 예외 단위, Claude marker8tool native | R1-01/reentry와 현재 수리 경로 먼저. Codex apply_patch처럼 native 매핑이 Bash와 다르면 그 분기 1개가 모든 오류×도구 전수보다 우선 |
| A5-b | 같은 thread 외부 수리 후 다음 메시지 fresh catalog/작업, latch 없음 | Codex marker/permission/budget/unknown recovery, Claude source/render repair | 수리 변경된 분기의 최소 native recheck. 자연어 출력0을 새 요구로 추가하지 않음 |
| A6-a | Fast 세 BACKING 존재, 슬롯 네 이름에 악성 상태 floor, 표준 파일만으로 Fast 최초 참조 | collector/분류/BACKING 및 이번 고정 snapshot scoped 회귀 | wrong root/stem/risk/round/lens/fake close/acceptance 등 명시 상태가 기존 suite 어디에 있는지 목록으로 연결 |
| A6-b | fresh/converted provenance·review/close 정상/실패 경로 | `test_fast*.py` 85개+BACKING16개 고정 snapshot 재실행 | 관련 제품 변경 시 해당 tests를 최종 후보에서 재실행. 실제 계정 전체 workflow 전수는 원문 요구 아님 |
| A7-a | global/local·두 checkout의 source 소유와 개인 비삽입, 정상 span만 제거/원본 보존 | install/materialize/transaction·독립 역할 비노출·실제 crossroot | 최종 rework가 installer/transaction 변경 때만 해당 경로 보완 |
| A7-b | upgrade/rollback·sync2회 byte 동등·fresh wheel import/runtime 변조 거부 | R5 전체 및 `final-consumer-r5/report.json` | 최종 frozen 후보 wheel 재실행은 유효. 실사용/전역 설치나 모든 OS는 불필요 |
| A8-a | Claude7500 UTF16/Codex49152 UTF8 정확 상한, 한국어/escape, 두 신규 사본+누적, raw full equality | 최종 native max case, budget guard +1 실패 | 바뀐 payload/host 배분만 재계측. 모든 Unicode 문자열을 전수열거하지 않음 |
| A8-b | 유한 여러 turn+CORE/대화 여유+반복 실제 auto compact 후 응답 진전, 무자기루프 | exact max Claude auto6/manual1/후속3, Codex compaction3/정상 scope3 | 각 boundary는 존재. 후속 문서의 “장기 무한” 부족을 이유로 계속 NOT_TESTED 유지할 근거 없음 |
| A8-c | 한도·버전·관측 usage 단위 명시; 모의 usage를 실제 비용으로 합산하지 않음 | budget/host 문서 및 actual usage | 누적 telemetry를 turn마다 더해 중복 과금 집계하지 않도록 확인. catalog 전용 tokenizer는 별도 optional 진단 |

## 원자료 독립 재계산

새 scratch는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/qa`다. 기존 B=`/Users/sejon/project/sage_project_worktree/overlay-context-phase05-20261106`의 raw 응답/event를 읽고 **26개 입력 artifact의 SHA-256**과 assert 결과를 `existing-evidence-audit.json`에 보존했다. `audit_existing.py` exit0이며 새 모델/endpoint 실행은 없다.

| 재계산 대상 | raw 관측 |
|---|---|
| Claude `changed-source-resume.json`, `after-{0,1,2}.json` | is_error=false; 같은 실제 session; 최신 shared `NEW_sage_team_SHARED_R6`와 personal 표지 포함. 단순 요약의 구 source 잔존만 센 것이 아님 |
| Claude compact metadata | manual1/auto6. 각 압축 뒤 유한 followup들이 완료됐으므로 이 표본에서 무한 자기루프는 없음. 모든 미래 입력 보장이 아님 |
| Codex exact max app-events | 완료된 `contextCompaction` 고유 id3; 최초/manual 뒤/auto 뒤 scope 응답3개, 마지막 resume transport 응답1개. 마지막 응답을 제품 의미 복구로 과장하지 않음 |
| Codex 다른 checkout app-events | `SCOPE_*` 두 표지 → `OTHER_*` 두 표지의 실제 두 완료 응답 |
| 양 host 슬롯 네 개 | 실제 완료 응답8개가 표준 두 표지만 보고. Codex fast_opened=false. 무한 신뢰도 보장으로 표현하지 않음 |
| 실제 Claude worker stream | spawned1/completed1; 실제 loader content/path/hash가 packet에 포함되고 실제 결과가 두 역할 표지를 보고 |
| Claude native tool hooks | Bash/Read/Write/Edit/Glob/Grep/Skill/Agent 각각 실제 PreToolUse rc2. Write/Edit의 다른 hook rc0과 혼동하지 않음 |

이전 원자료의 응답에 “폐기된 표지가 없는지 확인”이라는 체크리스트 문장이 있을 수 있다. 그 문장에서 예전 표지 문자열을 언급한 것을 예전 지침의 **적용**으로 자동 판정하지 않는다. `observed`의 현재 적용 출처와 설명/검증 대상을 구분해야 한다.

## 결정적 scoped 회귀와 source 결속

기존 B/subject 고정 사본에서 일반 unittest를 실행했다. cwd/TMPDIR/fixture/dest는 새 QA scratch이며 엔진 root 소비자 설정을 만들지 않았다.

- `test_fast*.py`: **85 tests, OK, exit0**.
- `test_overlay_reclassification_backing.py`: **16 tests, OK, exit0**.
- `leader`, `implementer-a`, `implementer-b`, `reviewer` 각각 실제 `load_local`의 자기 content/ref SHA 일치, 명시 role에서 Claude/Codex `overlay_context.current` context 없음/issue 없음: **8개 역할-runtime case PASS**.
- `finite_scoped.py`, `scoped-result.json`, `scoped-*.log`에 명령/결과를 보존했다. worker suppression은 함수 경계이며 native 모델 수신과 구분한다.

`source-bridge.json`에서 고정 B/subject와 현재 worktree의 관련 파일 8개를 비교했다. packet/launcher/selector에 해당하는 `overlay_local.py`, `commands/review.py`, `peer_process.py`, `overlay_classify.py`, `overlay_delivery.py`, `hook_runtime.py`, team CORE는 같았고 **`runtime/overlay_context.py`는 달랐다**. 현재 병행 수리가 진행 중이므로 이 과거 snapshot 테스트를 새 최종 제품의 전체 PASS로 승격하지 않는다. 최종 freeze 후 변경된 분기와 그 호출 경계만 다시 실행하고, 유지된 native 근거는 같은 byte/계약의 hash bridge를 명시하여 재사용할 수 있다. 제품 한 줄이 바뀔 때마다 영향 없는 모든 모델 진단을 무조건 처음부터 다시 하는 것도 원문의 요구는 아니다.

## 우선순위와 남은 실제 gap

1. **코드 지적의 진위와 수리:** R1-01 native reentry/rc2, R1-04 mixed runtime, R1-05 main `--agent` 실제 payload와 child 구분, R1-07 baseline/risk 순서, R1-08 doctor null 등 재현 가능한 지적을 별도 수리·처분한다. 이전 review의 subject 결속 무효는 수용 기준을 무한 확대할 근거가 아니라 fresh 유효 review가 필요한 이유다.
2. **경로별 작은 보완:** Claude implicit native 경로의 별도 raw 증거 정리, Codex resume 다음 current-view 작업, Codex apply_patch 등 Bash와 다른 지원 native dispatch가 실제로 존재하면 그 wire 한 case를 우선한다. 실제 계정 모델이 필요한 경우 parent 예산 합의 후 수행하고, 그 전에는 mock endpoint/기존 raw로 전송만 확인한다.
3. **최종 후보 결속:** 변경된 runtime의 경계 회귀와 frozen wheel/지원 예산·native case 영향만 재검증한다. 05에서 올바르게 결속된 독립 review와 미해결 finding 처분을 남긴다.
4. **추가하지 않을 blocker:** 반례 없는 worker 자체 compact/fork 자동화, 모든 역할×host×model native 전수, 악성 전체×실제 workflow 전수, OS/실사용 설치 전수, 무한 장기 테스트·catalog 전용 과금 측정. 기존 유한 evidence의 한계로 기록할 수 있으나 이 항목이 빠졌다는 이유만으로 A1~A8 전체를 자동 NOT_TESTED로 유지하지 않는다.

이 QA는 기존 증거의 충분성 후보와 실제 gap을 구분하여 보고했다. 00/01 체크박스나 기준 문구를 바꾸지 않았고, 현재 source 수리 중에 통합 acceptance·05 승인·06 완료를 선언하지 않았다.

## 추가 좁은 검증 — Codex 실제 resume 작업과 apply_patch native 차단

parent가 위 유한 matrix를 채택하고 실제 계정 **사용자 turn 1개** 및 localhost mock case 1개를 추가 승인했다. 아래 두 case는 그 범위 안에서 실행했으며 재시도나 추가 실제 계정 turn은 없었다. 현재 병행 수리 중인 최종 후보와 구분하여, 기존 immutable source로 남은 경로의 증거를 확보했다.

시험 source는 B/codex/subject이며 product inventory **216파일 / `sha256:70d33114c45ec4cc80111a7b319bca3ce60a2094915240411793dc3bd0a27bd8`**다. 전체 고정 subject 식별자는 `208ee71a8a574a27a5d9d17cf11e8f3b833c6aef36c3f36d70be89ea1c673ef8`이다. 새 harness/결과는 QA scratch 아래 `resume_one_turn.py`, `mock_apply_patch.py`, `assess_narrow_cases.py`, `narrow-case-assessment.json`에 보존했다. 엔진 source/00/01은 수정하지 않았다.

### A2 — 기존 exact-max thread의 새 process resume 후 제품 검증 작업

기존 실제 thread `01a1acab-5b18-7da2-980d-995f2f7ec81a`의 session 파일과 격리 config를 새 `codex-resume-one/home`에 복사하여 **새 app-server process**에서 `thread/resume`했다. 기존 consumer는 후속 slot 시험에서 작은 source로 바뀌어 있었으므로, 사전 합의한 격리 B/codex/consumer에 보존 max catalog의 원문14개를 잠시 복원했다. `collect_catalog`가 과거 `catalog.json`과 **전체 dict 동일**하고 serialized render가 정확 **49,152 UTF8 bytes**임을 먼저 assert했다. 설치 CORE를 재선택하거나 source를 fetch하지 않았다.

사용자 input은 Text 하나뿐이다. 현재 active target으로 다음 제품 검증 단계의 짧은 Markdown checklist와 applicable observed JSON을 작성하도록 했다. 새로운 실제 turn은 `01a1aefe-525b-7973-beac-c18df5074464`이며 native persisted `turn_context.model=gpt-6.1-sol`, CLI `0.166.0`이다.

실제 응답은 체크리스트를 작성하고 다음을 보고했다.

```json
{"target":"sage-team","observed":["SCOPE_sage_team_SHARED","SCOPE_sage_team_PERSONAL"],"fast_opened":false}
```

- 새 hook 원자료에 **SessionStart resume / 실제 자동 compact / UPS**가 각각 rc0이고 각 additionalContext의 catalog가 보존된 exact-max catalog와 전체 동일했다. generation은 `cda0d992a5dbce185e0162b772c05c4dbeba0797cb188576ef4cb1fa86760980`다.
- 새로운 input에 structured Skill이 없고 PreToolUse event도 없었다. 따라서 스킬 재선택/CLI overlay fetch로 복구한 표본이 아니다.
- 마지막 모델 호출 telemetry는 input67,813 / cached input12,288 / output109 tokens, context window475,000이다. `narrow-case-assessment.json`은 `last`와 thread누적 `total`을 분리해 보존한다. 자동 compact 서비스의 별도 비용 전체를 이 마지막 호출 비용이라고 주장하지 않는다. 실제 추가 사용자는 한 turn이며 native 내부 자동 압축도 관측됐다.
- 실행 rc0, 고정 source drift0. `original-fixture-sha.json`의 **14개 파일 목록/SHA가 finally 복구 후 모두 동일**함을 재검산했다. 새 CODEX_HOME의 auth symlink는 제거했고 부재를 확인했다. 현재 root나 사용자 전역 설정을 바꾸지 않았다.

원자료는 `codex-resume-one/{turn-issued,thread-resume,app-events,catalog,result,original-fixture-sha}.json`, `hook-*.json`, `home/sessions`다. 실제 계정의 원격 request body를 capture한 것은 아니며 제품 hook 출력의 신규 catalog와 native 모델 응답/도구 미실행을 결합한 관측이다. 이 case는 이전 표의 **Codex resume 다음 제품 검증 작업 1개** 공백을 보완한다. 실제 제품 코드 변경 workflow 전체 완주를 의미하지 않는다.

### A5 — 별도 native apply_patch wire의 도구 실행 직전 차단

`codex-apply-patch-mock/consumer`는 별도 격리 복사본이다. localhost endpoint만 사용하는 native Codex app-server를 연결했으며 **실제 계정 모델 호출0**이다. 정상 UPS의 완전 catalog를 먼저 확인한 뒤, 첫 model endpoint 응답을 만들 때 installed `.codex/skills/sage-team/SKILL.md`에 닫히지 않은 managed marker를 넣었다. 그 응답은 Code Mode의 `tools.apply_patch`로 sentinel 파일을 추가하도록 요청했다. readonly sandbox 자체의 거부로 오인하지 않도록 이 격리 consumer thread는 workspace-write/approval never였다.

관측 thread는 `01a1aeff-aca2-7c11-8473-bbea0f31cec7`이며 실제 native 이벤트는 **`PreToolUse tool_name=apply_patch`**였다. Bash와 별도 wire가 실제로 존재했다.

- pre-phase4/pre-implementation 다른 hook은 rc0이었다. 제품 `generated-artifact-write-guard`만 **rc2 / `overlay.marker_unpaired`**로 거부했다.
- 두 번째 localhost request에는 `Command blocked by PreToolUse hook`라는 native tool 오류가 있었다. 함수 미존재나 endpoint가 단순히 거부 문장을 합성한 결과가 아니다.
- sentinel `native-apply-patch-sentinel.txt`는 생성되지 않았다. driver rc0, localhost request2개, 손상시킨 fixture CORE는 finally에서 원래 바이트로 복구했다.
- 정상 UPS catalog exact-match, 별도 apply_patch hook rc2, native 오류 반환, sentinel 부재와 복구를 `assess_narrow_cases.py`가 모두 assert하여 exit0을 확인했다.

원자료는 `codex-apply-patch-mock/{requests,app-events,hooks-list,catalog,result}.json`, `hook-*.json`이다. 이는 실제 Codex 도구 dispatch/차단 시험이며 모델의 자발 행동 시험은 아니다. 모든 오류×모든 도구의 곱집합을 추가로 요구하지 않고도, 기존 Bash와 **별도인 apply_patch native 분기**를 추가 커버했다.

두 좁은 case의 상태는 `ASSERTIONS_PASS_NARROW_CASES_ONLY`다. parent의 새 frozen source/유효 peer review 입력에는 이 source/hash와 관측 범위를 함께 전달한다. 현재 병행 수리된 전체 후보의 acceptance·05 승인·06 완료를 이 문서에서 선언하지 않는다.

## 최종 수리 subject-r1 — 현재 Codex native 연결 재검증

이 절은 앞선 immutable 구 후보의 실제 모델 표본을 **현재 변경된 runtime 경계**와 연결하는 제한된 재검증이다. 실제 계정 모델 추가 호출은 **0**이다. 최종 통합 승인 판정은 parent의 유효 독립 review와 함께 별도로 한다.

현재 고정 source는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/subject-r1`이며 parent의 `subject-r1.json`/`subject-r1-files.json`과 대조했다.

- 제품 inventory: **216파일 / `sha256:6450e36ece176d4216f87c51622e173de9409923f90b8e22d9285e970a41e809`**.
- 전체 고정 파일 **495개**의 전후 SHA가 parent map과 정확히 동일하다. `qa/final-codex/source-before.json` 및 `final-boundary-assessment.json`에 보존했다.
- 별도 `qa/final-codex/consumer`에서 이 source의 정상 `install --host codex --skill-scope project-local --dest <consumer> --force`, `generate --kind hook --write --target codex --root <consumer> --dest <consumer>`를 실행했다. 두 명령 cwd도 같은 consumer로 명시했고 모두 exit0이었다. 엔진 cwd/dest에 생성한 파일은 없다. 정확한 argv/cwd/rc는 `setup-result.json`에 있다.
- R3 `run_native.py`와 analyzer를 외부 harness로 재사용하면서 import source를 이 immutable subject로 고정했다. 제품 command/collector/runtime을 mock catalog로 대체하지 않았다. `SAGE_HOOK_BIN` recorder는 제품 entry의 stdin/rc/stdout/stderr를 보존하여 그대로 반환한다.

| 현재 source의 native mock case | 독립 assert 결과 |
|---|---|
| `mock-large-structured-compact` | Codex0.166.0, 14 source, catalog **49,152 UTF8 bytes** 정확 경계. native structured `sage-team`/`sage-team-fast` 선택이 raw 요청에 각각 해당 installed CORE를 포함. 각 thread의 실제 `thread/compact/start` 뒤 다음 UPS까지 총 **6개 localhost 요청**의 모든 catalog가 보존 catalog dict와 전체 동일. 사본 순서 `[1,1,2,1,1,2]`, 잘림/preview 없음, 도구 실행0, 모든 handler는 단일 host JSON 또는 비어 있음 |
| `mock-error-repair` | unknown personal inventory가 UPS **rc2 / native decision:block**. 정상 부분 catalog/개인 sentinel 본문 없음, 수리 전 model endpoint 요청 **0개**. 외부 파일 삭제 수리 뒤 같은 thread 다음 UPS0/완전 catalog/요청 **1개**, stale latch 없음 |

표준 thread는 `01a1af03-1824-7020-bfb1-4d7db836f834`, Fast thread는 `01a1af03-276b-7a31-b5b8-69dc7f4bd8d7`, 입력 오류/복구 thread는 `01a1af03-367d-77e2-a4e9-7574db54f1d2`다. mock summary/response와 model id 문자열은 실제 계정 모델 행동/과금 근거가 아니다. 이 case의 compact는 실제 native lifecycle이지만 요약 응답은 localhost mock이 제공한다. 실제 계정 압축/범위 행동 근거는 앞 절의 실제 모델 표본과 구분한다.

### 이전 실제 모델 근거와 현재 source의 hash bridge

`source-core-bridge.json`에서 이전 실제 모델에 사용한 B/codex/subject와 다음을 직접 비교했다.

- **collector `sage/overlay_delivery.py` 동일**: `350df71a554a3a31206df44b108b5aa4925b1a637b09edc08c6dd52658383aad`.
- 7개 root CORE의 **spec 7개 + render 7개 + 정상 설치된 SKILL 7개가 모두 바이트 hash 동일**. 자기 target selector/표준2/Fast4 순서의 지침이 바뀌지 않았다.
- 비교한 경계 중 변경된 파일은 `sage/overlay_materialize.py`, `runtime/overlay_context.py`, `runtime/hook_runtime.py`다. 이 변경 경계를 거치는 현재 native 최대 입력/압축 전달과 unknown 오류 차단·복구를 위 두 case로 다시 관측했다. runtime 파일 hash도 bridge에 전후값을 보존했다.
- root가 달라 catalog root/generation 및 상한을 맞춘 진단 padding은 달라질 수 있다. 과거 catalog와 현재 catalog의 모든 본문 바이트가 무조건 같다고 주장하지 않는다. **현재 raw 요청과 현재 expected catalog의 전체 일치**, 변경 없는 collector/CORE 지침, 과거 실제 행동 표본을 각각 연결한다.

`final_codex_assess.py`는 위 full-dict/CORE/collector/495 source map/UPS block·복구를 모두 assert해 **exit0 / `PASS_FINAL_CANDIDATE_CODEX_NATIVE_MOCK`**를 기록했다. 남은 auth 경로0, actual account model call0, immutable source drift0이다.

원자료는 `qa/final-codex/{setup-result,source-before,source-core-bridge,assessment,final-boundary-assessment,run-results}.json`, 각 case의 `requests.json`, `catalog.json`, `catalog-rendered.txt`, `hooks-list.json`, `hook-*.json`, `app-events.json`, driver stdout/stderr다. 이 현재 source 연결 검증을 parent의 새 peer review 입력 근거로 전달한다. 기준 문구·면제·00/01 체크박스는 변경하지 않았다.

## C4→C5 재작업 후 유한 독립 QA

R1 triage의 생존 항목 C4-P-01/02/03, DOC-R1-01을 대상으로 했다. 제품/test freeze 뒤에만 C5를 읽고 실행했다. 최종 조직 보고는 **`/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/qa/c5-finite-assessment.json`**이며, 정식 Phase05 review verdict가 아닌 수리 확인·증거 연결 자료다.

- immutable source: `B/subject-c5`, 제품 hash **`sha256:59a43307c6afc428b2bf3442a19d4e18bf9f5097a57aaecf4adcdc69a88bd534`**.
- 전체 snapshot495파일은 parent `subject-c5-files.json`과 전후 SHA 일치. inventory 식별자는 `4fef3eade7b39506f80084d4a37587701ed557efb771181aec387158da4b8d96`다.
- 실제 계정/유료 모델 호출0, 새 native endpoint 모델 호출0, auth 파일/symlink 생성0, 엔진 root profile 생성 없음. 제품·테스트 파일은 수정하지 않았다.
- 독립 C5 consumer/관측/명령은 `qa/c5-verification/`에 있다. 생성 명령의 cwd/root/dest는 해당 consumer로 명시했다. 최초 도구 호출은 아직 없는 cwd를 지정하여 프로세스 생성 전에 실패했고 제품/fixture 실행이나 파일 변경이 없었다. 디렉터리 생성 후 올바른 cwd에서 실행한 결과만 아래 수용 근거로 센다.

| triage 항목 | 독립 관측과 범위 |
|---|---|
| C4-P-01 상태/root 분리 | 기존 `runtime/root-split/installed-consumer-commands.json`의 **양 host raw 명령·event·stdout/stderr**를 요약과 별도로 assert했다. `--root`를 강제하지 않은 entry replay에서 event cwd는 nested non-SAGE, risk state/동일 session의 06 baseline은 parent에만 있고 nested logs는 없다. parent catalog는 출력하지 않았다. Stop은 nested missing-profile shortcut이 아니라 **parent retro gate의 구체 사유**를 반환했다. Claude first rc2, Codex native JSON decision:block, bounded retry rc0 및 parent compliance report의 retro_gate를 구분해 확인했다. API2 혼합 runtime의 rc2 거부도 확인했다 |
| P01 source 결속 | 위 replay에 사용한 `hook_entry.py`, `runtime_api.py`, `hook_runtime.py`, `run_hook.py`, `io_claude.py`, `io_codex.py` **6개 바이트 SHA가 C5와 동일**하다. raw event를 native host가 자연 생성한 표본과 혼동하지 않는다 |
| C4-P-02 routing-only 수렴 | C5 정상 설치/정상 hook 생성의 별도 Claude consumer에 routing-only span과 unrelated USER 바이트를 추가했다. 읽기 전용 계획은 변경 필요, `current`는 `render_sync_required`를 반환했다. 실제 설치본 `sage.hook_entry` SessionStart resume의 L1 실행 뒤 routing만 제거되고 **USER 바이트를 포함한 예상 base와 정확히 동일**했다. 두 번째 계획은 변경0, 다음 `current`는 정상 catalog다 |
| C4-P-03 doctor 읽기 전용 | 동기화 완료 **CURRENT**, 유효 catalog + 미수렴 physical worker **REQUIRED**, YAML/JSON pair mismatch **INVALID**를 별도로 관측했다. 각 `_report_overlay_delivery` 전후 consumer 파일 내용 hash·mode·mtime와 파일 목록이 동일했다. catalog 유효성을 render 수렴으로 오인하지 않는다 |
| P03 실제 외부 복구 | consumer의 shared YAML 변경으로 mismatch를 만든 뒤 메시지가 설치 receipt의 `--target claude`를 명시함을 확인하고, 외부 `generate --kind hook --write --target claude --root <consumer> --dest <consumer>`를 실제 실행해 해제했다. 유효 `agents/implementer-a`의 pending physical render는 외부 `sync-overlays --root <consumer>`로 해제했다. root catalog-only source는 physical sync 없이 정상 공급됐다 |
| P03 다른 설치 target/절차 | 담당자의 `doctor-round2/recovery-target-results.json` 원수치를 검산하여 claude/codex/both 각각 메시지 target·실제 rc0·current issue 없음·등록 surface 유지가 일치함을 확인했다. 독립 직접 실행은 위 Claude consumer이고 다른 target은 기존 원자료 검산임을 구분한다. 세 authoring spec/render와 shared bootstrap 절차도 직접 읽어 외부 terminal/compile→필요 시 sync/검증/guards 유지, root-only·personal의 무물리sync 설명을 확인했다. 새로운 유료 절차 응답 테스트는 하지 않았다 |
| DOC-R1-01 | 한영 architecture/troubleshooting 네 문서가 Claude2.1.318/Codex0.166.0의 native mock 전송과 실제 모델의 유한 행동·압축 관측 및 한계를 구분한다. 내부 “Phase04까지 미검증” 주장으로 소비자 안내를 남기지 않았다. English source-hash marker가 대응 한국어 파일의 실제 SHA와 일치했다 |

### Native host emission과 entry protocol replay의 한계

새 **자연 발생 inherited-P + event-cwd-N native 세션은 NOT_TESTED**다. 설치된 host hook을 nested 비SAGE 프로젝트에서 실행시키기 위해 `--root P` wrapper를 강제하거나 P 설정을 N에 복사한 후 자연 발생이라고 부르지 않았다. 이 항목은 새 mandatory acceptance가 아니며, 이번 수리 확인은 실제 설치본의 양 host entry 프로토콜 replay/API3 검사와 해당 구현 바이트의 C5 동일성에 근거한다. 정적 함수 호출만으로 native 이벤트 발생을 주장하지도 않는다. 이전 native/실제 모델 근거는 기존 출처와 범위를 그대로 유지한다.

### A1~A8의 C4→C5 연결 범위

`qa/c5-verification/c4-c5-hash-bridge.json`은 전체 대조 가능한 파일의 전후 SHA를 보존한다. 다음 그룹은 **모두 동일 바이트**다.

- collector/policy 2개, root7 CORE spec/render14개: 기존 A1 전달·A2 압축·A3 표준/Fast scope·A8 예산/유한 누적 관측을 내용 변경 없이 연결한다. root 분리의 바뀐 entry 경계는 위 P01으로 별도 검증했다.
- worker/reviewer packet loader/launcher 3개: 기존 A4 packet·native reviewer/worker 근거를 유지한다. P01의 host 상태 정본과 event catalog 격리는 별개 성질이다.
- Fast 상태/CLI/독립 oracle: 기존 A6 구조·회귀 근거를 유지하며, 실제 모든 workflow×악성본문의 전수 모델 시험을 새로 요구하지 않는다.
- install/upgrade/transaction/package consumer helper: 기존 A7 근거를 유지한다. **materialize 자체는 변경됐으므로 무조건 전체 A7을 그대로 승격하지 않고**, routing 수렴/바이트 보존/멱등성의 변경 경계를 위에서 직접 검증했다.

P03의 코드별 오류 안내와 authoring 문구는 정상 catalog 본문/selector/예산 한도를 바꾸지 않았다. 추가 문구의 진단 적합성·실제 복구 chain을 위에서 확인했다. 정상 입력의 최대 크기·모든 실제 모델 진단을 전부 다시 실행하지 않았다. C5 전체 R10/최종 clean wheel 및 유효 R2 formal review의 결과는 parent의 별도 근거다.

최종 조직 보고의 상태는 `PASS_C5_FINITE_QA_WITH_EXPLICIT_NATIVE_LIMIT`다. 이는 **확인한 유한 수리/연결 범위의 PASS**이며 최종 05 승인·06 종료가 아니다. 완료 시 immutable495파일 drift0, live worktree의 관련 제품/테스트348파일 drift0을 확인했다. 새 source/test 수리나 기준 문구·면제 변경은 없고, 이 QA 역할이 추가한 것은 외부 원자료와04 기록뿐이다.

## Rev3 — restart R1의 F01~F04 국소 재작업 독립 QA

이 절의 Rev3은 **QA 근거 갱신 번호**이며 00/01의 Done Criteria Revision1이나 A1~A8 기준 문구를 변경하지 않는다. 새 scratch B2는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-restart-20261106`이다. source는 **B2/subject-r2 immutable 사본만 실행**했다.

| subject 식별 | 값 |
|---|---|
| 제품 hash | `sha256:93d541024b737af26048290415aa8b513855330ef411aa9e591d2ded5efbb611` |
| code patch SHA-256 | `183c47d89cff6ee53b06bd2955509e02c0c1910ce970c112fbb070f0ac6a6f91` — 실제 `code-r2.patch`와 대조 |
| 고정 파일 | 496개; 전후 파일별 SHA 일치 |
| 전체 inventory 식별자 | `64732b8088845bf256135fd8f57c5a2287bf70a44ec0de084a691ab9249cc666` |
| 조직 보고 | `B2/qa-r2.json` |
| 독립 script/원자료 | `B2/qa-r2-work/verify.py`, `F04-raw.json`, `scoped.log` |

제품 파일을 수정하지 않았고, 실제 계정·유료 모델 호출은0이다. 엔진 SAGE gate/review-loop/waiver를 승인 수단으로 사용하지 않았으며 엔진 root profile을 생성하지 않았다. 이 QA에서는 인증 파일·symlink를 만들거나 연결하지 않았다. 다른 독립 리뷰 프로세스의 인증 상태까지 이 QA의 부재 주장으로 확대하지 않는다.

### F01 — routing 제거의 비관리 suffix 바이트 보존

Claude/Codex 각각 실제 UTF8 파일에 root-skill routing span과 사용자 prefix·한국어 suffix 및 **끝 LF3바이트**를 넣었다. 두 cleanup 경로(`plan_materialize`, `plan_blocked_cleanup`)의 계획 문자열이 `원본에서 routing span 한 번만 제거한 기대 바이트`와 정확히 같았고 계획 단계는 파일을 바꾸지 않았다. 실제 `materialize`도 동일 바이트를 남겼으며 두 번째 `materialize`는 변경0/오류0이었다.

이는 “바깥 사용자 바이트 보존”의 구체 반례를 재검증한 것이다. 일반 routing helper의 trailing 정규화를 모든 자산에서 폐기한 변경이나 신규 합성 정책으로 확대하지 않는다. 별도 legacy shared-span capability 보호의 기존 회귀도 유지한다.

### F02 — snapshot acquisition의 실제 rename과 권한 오류 구분

스케줄링 위치만 고정하고 **파일시스템에서 실제 디렉터리 rename/mkdir**를 실행했다. `_snapshot`의 초기 수집(listdir boundary1)과 최종 수집(boundary2)을 각각 시험했다.

| 입력 변화 | 독립 결과 |
|---|---|
| 수집 중 디렉터리 1회 사라짐 | 전체 snapshot을 한 번 새로 수집하여 안정된 empty catalog 반환. 중간에 읽은 이전 본문을 부분 정상으로 반환하지 않음 |
| 같은 획득 경계의 rename을 계속 반복 | 실제 rename2회/두 attempt 뒤 `overlay_delivery.unstable_snapshot`, 정상 catalog 없음 |
| 디렉터리 권한을 실제 `chmod 000`으로 바꿔 listdir 거부 | `_snapshot` 호출1회, 즉시 `overlay_delivery.validation_failed`. race로 보고 재시도하지 않음. finally에서 fixture 권한 복구 |

기존 scoped 회귀는 stat→listdir 사이의 실제 directory→file 교체도 추가 확인한다. 권한 오류의 독립 시험은 단순 주입 예외만이 아니라 실제 OS 접근 거부였다. 오류 문자열에 private source/exception sentinel을 포함하지 않음을 확인했다. 장기 concurrency 안정성이나 모든 filesystem의 원자 snapshot을 보장한다고 주장하지 않는다.

### F03 — 실제 base8e 두 host 업그레이드 원자료의 독립 대조

`upgrade-f03/actual-dual-results.json`의 실제 old installer→old generate→old sync→새 upgrade 원자료를 읽고 양 primary 순서를 각각 대조했다. 보존된 source-base의 installer/generator/sync/materialize/team CORE **5개 파일이 Git `8e17a88`의 해당 blob 바이트와 일치**함을 독립 확인했다. 이때 과거 source를 새로 실행하지 않았고 Git blob은 출처 검산으로만 읽었다.

- primary Claude와 primary Codex 각각 old shared body가 두 local render에 있었던 producer 관측과 단계별 rc0를 보존했다.
- 실제 현재 설치본 양 host의 새 `sage-team` selector를 직접 읽었다. shared 원문은 정확히 `ACTUAL_OLD_DUAL_SHARED_RULE\n`로 남았고, 각 render에는 옛 shared 본문이 남지 않았다.
- primary·`installed_hosts` **순서**·host별 `project-local` receipt가 before/after 및 현재 manifest에서 정확히 일치했다.
- 해당 시험의 `unused-global-<primary>` 디렉터리는 생성되지 않았다.
- secondary-global을 새 staging 범위로 확대하지 않았다. 기존 owner 경계 회귀를 선택 실행하여 secondary global 추가 install/쓰기 없음과 기존 primary global 선택 유지만 확인했다. test의 global surface는 자체 TemporaryDirectory fixture이며 사용자 전역 설치가 아니다.

이 결과는 supported dual-local upgrade 수리를 입증하는 범위다. 지원하지 않는 secondary-global을 이번 QA가 새로 구현하거나 실제 사용자 global 디렉터리로 검증하지 않았다.

### F04 — P→N 빈 catalog 대체→P 복귀와 역할/이벤트 경계

두 제품 IO adapter의 원시 stdout/stderr16개를 별도 보존했다. P의 정상 catalog → non-SAGE N의 **schema2/root=N/role=root/sources={}/targets={}** 명시적 빈 catalog → P 복귀 시 원래 정상 catalog와 전체 동일한 상태를 확인했다. 빈 상태 generation은 P와 다르다.

- UPS와 resume/fork/compact3개 reentry 이벤트는 N의 현재 빈 상태를 공급했다.
- startup의 본문 defer와 명시 child의 root 본문 억제는 유지했다. N에는 host log를 새로 쓰지 않았다.
- scoped 테스트는 별도 `sage.hook_entry` subprocess에서도 `--root` 강제 없이 두 host의 P→N→P와 reentry를 확인했다.
- `runtime-F04/old-c5-package-results.json`의 **기존 API3 package** 호환 원자료도 두 host의 schema2/role/root/빈 sources·targets 및 private `_collect`/render 경로와 대조했다. 해당 runtime 담당자의 scoped summary에 기록된 구현3개 SHA가 이번 R2 파일과 같음을 확인했다.

이는 **실제 제품 함수·host IO 및 entry 프로토콜 replay**다. 자연 발생 native host 세션이 P/N 조합을 보냈거나 실제 모델이 그 빈 상태를 적용했다고 바꾸어 표현하지 않는다. 새 native/유료 모델 시험을 필수로 추가하지 않았다.

### 함수 hash에 따른 기존 A1/A2/A3/A8 증거 연결

collector **전체 파일은 변경됐다**. 이를 무변경 파일이라고 보고하지 않는다. C5와 R2의 AST/source segment를 각각 hash해 아래 구분을 저장했다.

| 범위 | C5→R2 결과 | 의미 |
|---|---|---|
| `overlay_delivery.py` 전체 | 다름 | acquisition 예외 처리/재시도 제어 수정 포함 |
| `_collect` | source text/AST SHA 동일 | source 문자열·targets·generation의 정상 내용 조립 계약 유지 |
| `render_catalog` | source text/AST SHA 동일 | 정상 wrapper/escape·host budget 계약 유지 |
| `_snapshot` | source text/AST SHA 동일 | 한 번의 acquisition 내부 inventory/stat 의미 유지 |
| `collect_catalog` | 다름 | acquisition race를 한 번 재시도하고 persistent race와 permission을 구분한 변경 |
| root7 CORE spec/render14개 | 파일 SHA 모두 동일 | 기존 실제 모델 selector/두 슬롯·네 슬롯 행동 근거를 내용 변경 없이 연결 |
| Fast 상태/CLI/독립 oracle3개 | 파일 SHA 모두 동일 | 기존 유한 A6 구조/회귀 근거 유지 |
| worker/reviewer packet3개 | 파일 SHA 모두 동일 | 기존 A4 역할 packet 근거 유지 |

A1의 정상 전문 전달·A2의 유한 압축/재개·A3의 실제 표준/Fast/다른 root 행동·A8의 지원 예산/유한 누적 근거는 이 **정상 본문 불변 범위**로 연결한다. snapshot race와 빈 catalog 경계는 변경됐으므로 위 F02/F04로 별도 검증했다. A7의 upgrade/materialize 변경도 위 F01/F03로 따로 검증했으며 전체 파일 변경을 숨겨 기존 근거를 통째로 동일하다고 하지 않는다.

기존 의미 있는 회귀12개를 선택 실행해 **12 tests / OK / exit0 / 1.954s**를 확인했다. 전체 suite를 중복 재실행하거나 고유 사례 수를 subtest 합으로 부풀리지 않았다. 전수·무한·새 모델 요구, F08~F12의 별도 품질 논의를 이 국소 QA에 추가하지 않았다.

### 종료 확인과 판정 경계

`qa-r2.json`의 상태는 `PASS_R2_LOCAL_REWORK_FINITE_QA`다. source496파일 drift0, live worktree의 관련 제품/테스트348파일 drift0, 엔진 profile 없음, 이 QA의 새 인증 material0·모델 호출0을 확인했다. input artifact SHA, 원시 adapter 출력, actual upgrade provenance와 함수/파일별 hash를 함께 보존했다.

이는 유한 국소 수리 확인이며 정식 Phase05 리뷰 verdict가 아니다. full R11/최종 clean wheel과 유효 독립 리뷰는 parent의 별도 근거다. A1~A8 기준 문구·면제·00/01 체크박스를 변경하거나 여기서06 완료를 선언하지 않았다.
