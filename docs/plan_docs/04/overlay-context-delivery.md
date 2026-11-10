# Overlay 통합 전달 — 04 분석·수용 검증

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 3
Status: VERIFIED — 새 R2 독립 검토 완료; 출시·전역 설치 별도

## 사용자 결정과 정지 경계

사용자는 처음 나머지 단계와 Claude Phase05 cross-review를 요청한 뒤 **04까지만 진행하고 멈추도록 범위를 줄였다**. 이후 잠시 중지와 재개를 지시했다. 중단했던04 검증·분석 정리를 재개하고 여기서 멈춘다. 05/06은 시작하지 않았다.

SAGE PDCA의 개발 방식을 사용한다. 개발 중인 SAGE의 gate/review-loop/waiver를 엔진 자신의 승인 권위로 실행하지 않는다. 아래 CLI/hooks는 격리 consumer의 제품시험이다. 커밋·푸시·머지·릴리스·전역 설치·실사용 프로젝트 적용은 하지 않았다.

## 결과의 의미와 고정 대상

03 구현과후속수리에대해 일반 회귀, 설치 wheel, 두 native host 전달·실제 모델표본을확인했다. 이전04종료시전체미완료기록은당시상태다. 아래2026-11-06재개검산표가현재수용판정이며, 독립05리뷰·최종회귀·출시승인은별개다.

- worktree: `/Users/sejon/project/sage_project_worktree/overlay-context-delivery`, branch `fix/overlay-context-delivery`, base `8e17a88`.
- 최종 product source hash: `sha256:70d33114c45ec4cc80111a7b319bca3ce60a2094915240411793dc3bd0a27bd8`.
- R5 시작/종료 product 파일 맵 동일. 이 hash는 CI/test/분석 문서 전체가 아닌 `source_core_content_snapshot()` 배포 inventory의 식별자다.
- [최종 집계](/Users/sejon/project/sage_project_worktree/overlay-context-evidence/phase04-final-assessment.json), [재검증 assertion](/Users/sejon/project/sage_project_worktree/overlay-context-evidence/assess_phase04_final.py).
- 최종 Codex R3 source378개는 현재와 차이0. 역할 진단은 예산 보완 전 subject이며 현재와7개 파일 차이가 있다(collector/doctor/runtime 및 해당 테스트). reviewer packet 코드는 같지만 최종 후보의 실제 모델 재시험이라고 부르지 않는다.

## 전체 회귀와 wheel

| 실행 | 결과 | 입증 범위 |
|---|---|---|
| `PATH=<consumer-venv>/bin:$PATH TMPDIR=<evidence>/tmp bash scripts/sage_harness/hooks/tests/run-all.sh` R5 | exit0, Python suite114회, 검사 실행4,066건, skip14, 실패0, ERROR0 | 반복 포함 로그 합계. 고유 테스트4,066개 또는 전부 성공4,066개라는 뜻 아님 |
| `python3 -I scripts/ci/check_consumer_integrity.py --work-dir <final-consumer-r5>` | exit0; wheel build/install/import0, bootstrap 전 generate2, bootstrap 후 generate0/validate0, runtime 변조 validate3 | fresh venv 설치 wheel import, source fallback 배제, 원본 엔진 sentinel 불변 |
| localization inventory `--check` / `git diff --check` | 각각 exit0 | 문서 등록·공백 검사 |

[R5 전체 로그](/Users/sejon/project/sage_project_worktree/overlay-context-evidence/phase04-full-r5.log), [wheel report](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-final-consumer-r5/report.json)를 보존한다. wheel SHA256은 `6cd508988e48635284c70ac2e90407aa2698d0842eef640b1f4b84bb001cde40`, 복사 source inventory digest는 `709b1e07b4a0929f196f4a6b395dfa3ed508f8c0caee42055a6c7f77cc7936f9`다. 제품 source hash와 서로 다른 inventory다.

skip14는 jsonschema 부재 분기1, Windows/dir_fd/경쟁 관련5, 별도 역사적 phase 문서 부재7, user-site 비활성1이다. 새 overlay 검사를 skip해 녹색으로 만들지 않았다. 다른 OS/Python matrix와 원격 GitHub Actions는 미실행이다. wheel 시험 이후 변경은 phase 분석 문서이며 제품 소스·CI·테스트는 동일하다.

## 재현 후 추가 수리

| 발견 | 수정 이유와 방식 | 현재 증거 |
|---|---|---|
| QG-01 손상 설치 span | SessionStart 오류 후 UPS/도구가 source만 검사해 통과. 현재 materialize 계획을 읽기 전용으로 검사해 손상·미수렴 보류 | RED→단위 GREEN→독립 QA 재현·외부 수리 PASS. 양 host native UPS/Bash 차단 |
| QG-02 L1 PermissionError | stale shared 본문이 남아도 WARN0/catalog 출력. 본문 없는 오류·catalog 억제와 다음 경계 재검사로 변경 | 실제 chmod0555 반례 수리. Codex native 거부·외부 복구 관측. Claude 권한 오류 전체 native 조합은 미실행 |
| Claude 큰 출력 spill | 49,152-byte catalog가 파일 경로/첫2KB preview로 대체. 공통 byte 한도에 Claude catalog7,500/event10,000 UTF16-unit 검사 추가 | 정확7,500에서14개 전체 원문/hash 일치.7,501 및 종전49,152-byte 입력은 모델 요청0으로 UPS 차단 |
| 엔진 자체 stale 검사 | 역사적 엔진 manifest 재생성 대신 같은 CI 경로에 fresh wheel consumer 정상/변조 검사 연결 | 최종 runner/wheel 통과. 검사 삭제·skip·면제 또는 자기승인 아님 |
| standalone compact helper 호환 | 불필요한 false keyword가 구 package helper5개 subtest 실패 유발 | false일 때 기존3인자 호출 유지. compact15 tests 및 최종 R5 통과 |

정상 source의 한 번 읽기·검사/hash/공급을 유지한다. 복구는 현재 상태 재검사이며 오류 latch/임의 셸 수리 예외를 추가하지 않았다. 공통 source10,000/catalog49,152 UTF8 bytes, Codex generated `additionalContextLimit=60000`은 유지한다. Claude 한도는 serialized catalog와 같은 handler의 합친 문맥에 적용하며 token 수가 아니다. 상세: [예산](budget-evidence.md), [독립 QA](qa-gap-evidence.md), [CI](ci-rework-evidence.md).

## 실제 host 관측

- Claude Code2.1.318 / 실제 `claude-opus-5-5`: native Skill로 일반2/Fast4 출처를 순서대로 적용. 비선택 target의 Fast 전환 유혹 거부. 수동 compact/resume/자동 compact 후 작은 현재-target 진단에서 재선택 없이 일반2개 보고. 최종 runtime 정상 재설치 후 자동 압축·다음 응답 재확인.
- Codex0.166.0 / 실제 `gpt-6.1-sol`: structured/CLI/implicit native 전송, 수동 compact/resume, 실제 자동 compact 후 일반 범위, Fast4개, 작은 nested/return 진단. 최종 R3에서49,152-byte 전달·차단/복구 재확인. 마지막 실제 계정 scope/자동 압축은 앞선 R2이며 R3 실제 모델 재시험이라고 보고하지 않는다.
- 실제 host+로컬 모의 모델 endpoint에서 요청 전체 content/hash와 오류 전 모델 요청0을 확인했다. 실제 계정 모델 행동 진단과 구분한다. 올바른 실제 모델 응답을 remote raw API capture로 표현하지 않는다.
- 양 host headless reviewer는 실제 모델 역할 본문2개/자기 refs/타 역할 신규 본문0을 확인했다. launcher의 hooks 억제·빈 cwd도 작용하므로 role env 단독 인과 증거가 아니다. native Agent worker는 미실행이다.

원자료·한계: [Claude](claude-native-evidence.md), [Codex](codex-native-evidence.md), [역할](role-native-evidence.md).

## 수용 조건 분석 — 2026-11-06 재개 검산

아래는00 Revision1 원문 그대로의 유한 수용 표본 판정이다. 이전 NOT_TESTED 사유 중 원문에 없는 worker 자체 compact 전수·모든 실제 workflow×악성 지침 곱집합·실사용/OS 전수·무한 장기 테스트를 필수 기준으로 추가했던 부분은 [독립 QA 대조](phase05-resume-qa.md)에서 바로잡았다. 기준 문구를 축소하거나 waiver/N/A로 면제하지 않았다. PASS는 관측 가능한 요구를 아래 증거로 확인한 뜻이며 모든 미래 모델/세션의 절대 준수 보장은 아니다. 독립 코드 리뷰와 최종 회귀·출시 승인은 별개다.

| ID | 상태 | 원문에 대응하는 증거 | 경계·한계 |
|---|---|---|---|
| A1 | PASS | 양 native host 직접/구조화/암묵 경로의14 source 전체 content/path/hash, Claude native `/sage-team` expansion 및 mock-selected Skill 전후 전문, Codex structured/explicit/read-tool implicit 전문; actual 작은 표준/Fast 적용 | mock 선택은 모델 자발성 증거가 아니다. 별도 실제 Claude implicit 진단도 std2를 적용했지만 의도적으로 phase를 실행하지 않고 Skill은 호출하지 않았다고 보고했으므로 CORE 진입 증거로 세지 않음 |
| A2 | PASS — 새 R2 재검증 | 양 host 실제 수동/자동 compact/resume+현재 catalog 신규 전달, Claude 원문 변경 뒤 resume/체크리스트3회·auto6, Codex exact 최대 입력 resume 뒤 실제 체크리스트·std2/재선택0 | 유한 제품 검증 작업. 엔진 자체를 consumer cycle로 개발해 작업 전체를 완주하지 않음 |
| A3 | PASS — 새 R2 재검증 | 양 실제 모델 표준2/Fast4 순서, 비선택 target 유혹, 네 슬롯 유혹8표본, Codex 같은 대화의 두 checkout SCOPE→OTHER 적용 | 모델 행동의 표본 결과이며 텍스트의 물리 격리/모든 미래 준수를 보장하지 않음 |
| A4 | PASS | 실제 nested cycle→plan→team→review→cycle 자기2개, 기존4역할 loader/ref와양runtime억제, 실제 Claude Agent packet 수신, 양 실제 headless reviewer1회 append | worker 자체compact/fork 자동화는01§6의 추가 후보이며 실제 회귀 반례 없음. inherited 과거 문맥 삭제를 주장하지 않음 |
| A5 | PASS — 새 R2 재검증 | source/예산/권한/L1/marker/예외 회귀, 양 native UPS차단·지원 도구 거부, Claude8도구/Codex별도apply_patchwire, 외부 수리복귀; Codex compact의 실제reentry유실 RED→GREEN와baseline보존 | 공통 validator/도구별wire 근거를 결합. 오류×host×tool 전체 곱집합이나 자연어 출력0을 보장하지 않음. baseline 실패의 기존비영 종료는보존 |
| A6 | PASS | 세Fast BACKING·악성네슬롯 상태의 독립oracle, 표준최초상속, Fast fresh/converted/review/close 정상·거부85+16회귀 및전체검사; 별도실제8슬롯표본 | 정본§12는 overlay를읽지않는독립oracle을요구. 실제모델workflow전수로대체하지않음 |
| A7 | PASS — 새 R2 재검증 | global/local·두checkout·원본/개인비삽입·sync멱등·upgrade/rollback 회귀, fresh wheel 정상0/변조3, 구runtime혼합의shared유실방지와정상force설치·latefailure rollback | 실사용/전역설치·원격CI·다른OS전수미실행. 최종제품과동일hash의consumer결과및원본보존확인 |
| A8 | PASS | Claude7500UTF16/Codex49152UTF8 정확상한 native full-dict,한국어/quote/emoji·두사본/누적, 실제최대입력 반복자동압축후응답진전·CORE/대화여유; 버전/한도/실제usage단위기록 | Claude auto6/manual1+3후속, Codex compact3+추가resume는유한부하표본. 무한안정성/모든Unicode/전용catalog과금측정은주장하지않음 |

최신 원자료는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-resume-20261106/`에 보존했다. `final-claude-native-assessment.json`, `qa/final-codex/final-boundary-assessment.json`, `qa/narrow-case-assessment.json`, `qa/existing-evidence-audit.json`, `runtime/native-c2-evidence-hashes.json`, `symlink-root-probe/results-green.json`과 개별 raw requests/events를 사용한다. [후속 실제 시험](phase05-followup-evidence.md), [이번 독립 QA](phase05-resume-qa.md), [runtime 수리](../03/runtime-phase05-rework.md), [doctor/설치 수리](../03/doctor-phase05-rework.md)에 세부 근거가 있다.

마지막 제품은 `sha256:5f52ff3bac656b4e4b4200ddaf6f6c25d12918c20b48916524df1f497737bb1f`다. 앞선 실제 계정 근거와 collector/CORE 바이트가 같음을 연결했고, 바뀐runtime/설치 경계는 새native case와 결정적 회귀로 다시 확인했다. C2→C3 등후보교체의 테스트/문서차이는제품hash와구분한다. 이전전체R6 PASS는제품추가수리전, 새전체회귀 R7/R8의 옛SessionStart/alias표시 기대값실패는보존하고 해당기대값을새계약에정렬한정확후보의전체회귀를최종05전에확인한다. 아직 독립05 승인으로 표현하지않는다.

## 다음 경계

04/05에서 재현한 코드 반례를 수리하고 위 유한 수용 근거를 검산했다. 현재05 fresh Claude cross-review와독립L3절차를진행하며최종전체회귀를확인한다. 이 기록은 reviewer verdict나출시승인이 아니다.

이전04종료시에는정지했으나후속사용자지시로현재05~06범위가승인되었다.05가유효하게승인되기전06완료를기록하지않는다.

## 후속 사용자 승인·예약 — 2026-11-06

04 정리 후 사용자가 오늘 한국 시간 새벽2시에05부터 시작하고06까지 계속 진행하도록 명시했다. 기존04까지만 정지 경계는 **2026-11-06 02:00 KST 이후05~06 재개 승인**으로 확장된다. 지금05/06을 시작한 것은 아니다. 필수 수용 공백을 실제 검증하고 독립 Claude cross-review/L3 리뷰를 거쳐 조건을 만족하면06까지 추가 확인 없이 진행한다. 미해결 FAIL/NOT_TESTED를 승인·완료로 바꾸거나 waiver로 통과시키라는 승인은 아니다. 커밋/푸시/머지/릴리스/전역 설치는 미승인이다.

Orca automation `6871b7e1-06da-4baf-8e49-5d76bb41c8ac`를 기존 구현 worktree 대상으로 만들고 활성화했다. timezone Asia/Seoul, RRULE `FREQ=DAILY;BYHOUR=2;BYMINUTE=0;COUNT=1`, 재조회 nextRunAt `2026-11-06T02:00:00+09:00`를 확인했다. provider codex fresh session이며 별도 worktree를 생성하지 않는다. 원자료는 `overlay-context-evidence/phase05-schedule-confirmed.json`, 작업 지시는 `phase05-scheduled-prompt.txt`다. 실제 예약 시각의 프로세스 실행/리뷰/완료는 아직 관측하지 않았다. 로컬 호스트가 예약을 실행할 수 있도록 Mac과 Orca 실행 상태가 필요하다.

## 2026-11-06 실제 후속 실행

예약 실행이 기존 작업 트리에서05 준비를 시작했다. 위 미착수/중지 표현은04 완료 당시 이력이다. 제품 hash 동일성을 확인하고 필수 공백의 실제 추가 시험을 수행했으며 [후속 수용 증거](phase05-followup-evidence.md)에 관측·한계를 구분한다. A1~A8 전체 상태는 이 시점에도 NOT_TESTED이며 체크박스·면제·PASS로 변경하지 않았다. [05 독립 검토](../05/overlay-context-delivery.md) 진행과06 승인 여부는 별도다.

후속05는 실제 추가 수용 시험과 Claude 코드 리뷰를 시도했지만, 시험 harness가 만든 엔진 profile의 diff/snapshot 불일치로 유효 라운드0, Claude 실제 usage limit 및 리뷰 budget 초과, A1~A8 미완료에 따라 BLOCKED다. 생성 profile은 외부 증거로 옮기고 기존 제품 변경을 보존했다.06은 미착수이며 [05 차단 보고](../05/overlay-context-delivery.md)가 정본이다.

R1의새생존반례로A5/A7을재개방했다.수리·재검증전까지미해결이며기존PASS근거는과거후보관측으로보존한다.


## R1 재작업 후 C5 최종 기능 검증

C5 product `sha256:59a43307c6afc428b2bf3442a19d4e18bf9f5097a57aaecf4adcdc69a88bd534`. 전체 R10은 unittest 보고 합계 4,097항목(14 skip), 실패·오류0/exit0이다. 개수는 runner의 Ran 합계이며 고유 테스트 전수 수라고 주장하지 않는다. 새 wheel SHA `138d5c54d6a60b9954eb446a2039a3e4354bc3947cf0227d89a35f22aae0dc50`: build/install/installed import/정상 validate0/실제 runtime 변조 validate3와 engine sentinel 불변 PASS.

독립 QA 상세는 B/qa/c5-finite-assessment.json과 phase05-resume-qa.md의 C5 후속 기록이다. P01의 새로운 inheritedP+eventN은 양 host 실제 설치 entry protocol replay이며 native host 자연 발생 경로를 직접 시험했다는 주장은 아니다. 기존 native/실제 모델 표본은 불변 collector/7CORE 계약 hash와 새 ABI·설치·회귀로 연결하며 모든 버전/worker 자체 compact 전수로 확대하지 않는다. A5/A7을 기능 PASS로 복구했으며 독립05 수렴은 별도다.


## 새 리뷰 재작업 R2 기능 검증

고정product `93d541024b737af26048290415aa8b513855330ef411aa9e591d2ded5efbb611`,검토전체branchpatch `183c47d89cff6ee53b06bd2955509e02c0c1910ce970c112fbb070f0ac6a6f91`. R11전체4115항목(14skip)/실패·오류0/exit0, freshwheelPASS, 독립QA12개선택검사PASS. snapshot획득실제rename·지속2attempt·실제권한failure,원본LF양계획/실제보존,actual8e양primarydual-localupgrade,양hostentryP→Nempty→P와기존API3package호환을각원자료로검산했다. 기본native/실제model의불변_normal_본문계약은함수/CORE별hashbridge로연결하며새자연발생nativeN이나모델전수라고확대하지않는다. 상세는restart증거`r11-summary.json`,`clean-consumer-r11/report.json`,`qa-r2.json`이다. 독립05는아직대기다.

## 이전 한도 150만 시점의 중단 이력

R2 여섯 FIND는 CLEAR이나 반박자 2명 중 1명만 반환했고, 신규 IO 1,496,807/1,500,000 사용 후 잔여3,193으로 추가 필수 검토 예산을 확보하지 못했다. 기능 체크와 독립 승인 상태를 구분한다. Phase05는 BLOCKED, Phase06 미착수다. 현재 정본은 [05 독립 검토](../05/overlay-context-delivery.md)이며 앞선 중간·중단·대기 기록은 각 시점의 이력이다. 추가 제품 수정·상한 증액·자동 새 리뷰 run은 진행하지 않는다.

## 현재 상태 — 누적 180만 한도 승인 후 검토 완료

사용자의 이번 실행 한정180만 승인 후 같은 고정R2의 두 번째 반박자와 첫 반박자의 원장 보충 확인을 끝냈다. 두 반박자 모두 CONSISTENT/미해결0이다. 새 run은 유효2라운드, 이전run포함cycle3라운드로 수렴했으며 신규IO1,511,409/1,800,000이다. A1~A8 유한 수용 근거와 기준문구는 그대로다. 정본05를 APPROVED로 기록한 뒤에만06을 별도 작성한다. 과거BLOCKED와후속해소원문은 외부증거에 보존한다. 제품/테스트/CI/사용자문서 변경은 없다.
