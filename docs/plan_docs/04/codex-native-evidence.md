# Overlay context delivery — Codex native evidence

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Status: OBSERVED_WITH_OPEN_ACCEPTANCE — 04 관측 기록, 승인 판정 아님
Date: 2026-11-05
Latest bounded rerun: R3 host-budget repair subject, native mock endpoint only

## 결론과 증거 경계

Codex CLI 0.166.0의 실제 app-server/CLI와 **제품 collector + 정상 installer가 설치한 CORE + 제품 generator가 만든 hooks**를 연결했다. hook 본문을 합성 catalog로 대체하지 않았다. 작은 shared/personal fixture 원문 14개만 scratch consumer에 추가했다.

- native 전송: 표준/Fast structured Skill, CLI 명시 선택, 모델의 implicit 선택을 모의한 실제 read-tool 경로에서 원문 14개와 hash가 raw model request에 정확히 있었다. startup은 본문을 보내지 않고 UPS가 한 사본을 보냈다.
- native lifecycle: 실제 `thread/compact/start` 및 app-server 프로세스 재시작 후 `thread/resume`에서 SessionStart compact/resume을 관측했다. 이후 요청에 catalog가 다시 공급됐다. **mock 모델의 요약을 사용한 전송 시험과 실제 계정 모델의 압축 시험은 아래에서 구분한다.**
- 실제 계정 모델: `gpt-6.1-sol`로 표준 두 출처/Fast 네 출처, 수동 및 실제 자동 압축 뒤 표준 범위 유지, 다른 target 전환 유혹 거부를 작은 read-only reporting-token 진단으로 관측했다. R2 runtime에서도 표준/Fast/자동 압축을 재확인했다.
- A5 수리 재검증: malformed installed CORE와 실제 파일 권한으로 발생시킨 L1 PermissionError가 정상 catalog로 이어지지 않았다. UPS native block, 실행 직전 malformed CORE의 Bash PreToolUse 차단, 외부 수리 뒤 다음 turn 복구를 관측했다.
- R2 최대 49,152 UTF8 bytes의 실제 제품 catalog는 std/Fast·수동 압축·resume의 8개 mock-endpoint 요청에서 본문/hash 14개가 모두 정확히 일치했다. 실제 계정 모델의 큰 입력 관측은 R1 49,120 bytes이다.

이 결과는 실제 제품 개발 workflow 완료나 A1~A8 전체 통과 판정이 아니다. 임의 장기 세션, 실제 worker/headless 역할 경계, 다른 root 오적용, 모든 native 도구 종류, A6/A7 전체는 이 담당 시험에서 완료하지 않았다.

## 고정 subject와 설치 경로

기준 worktree: `/Users/sejon/project/sage_project_worktree/overlay-context-delivery`.
Python: `/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python`.

| 구분 | 독립 scratch / 고정 subject inventory digest | 용도 |
|---|---|---|
| R1 | `/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105a` / `eff0d1370ac6f833efcd4ed54731a70848c98d9b7de545e110fb5bc9378551bb` | 최초 native/실제 모델/크기 관측 |
| R2 | `/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105b` / `45a88fb8a4a5ee1caadad6e25f24d8064e4416f542b53ab0a0fba6d97c97858b` | parent A5 수리 후 정상 재설치, A5·정확 상한·현재 runtime 실제 모델 재확인 |

각 digest는 `subject-hashes.json`의 정렬 JSON을 SHA256한 값이다. inventory는 package/runtime/CORE/templates/schema 등 복사 당시 source 파일별 hash이며, git commit hash나 출시 candidate digest가 아니다. CI 담당자가 이후 바꾼 파일은 고정 사본에 섞지 않았다.

R1은 source snapshot의 `python -m sage install --host codex --skill-scope project-local --dest <consumer>`를 사용했다. R2는 R1 설치 consumer를 별도 scratch로 복사한 뒤 **새 source snapshot의 정상 `install ... --force`**와 `generate --kind hook --write --target codex --root <consumer>`를 실행했다. 두 명령 exit0. runtime 일부만 수동 교체한 mixed 설치가 아니다. wheel consumer 수용은 별도 담당 범위다.

native process는 `PYTHONPATH=<고정 subject>`와 `SAGE_HOOK_BIN=<scratch hook_recorder.py>`를 사용했다. recorder는 stdin/argv와 제품 `sage.hook_entry`의 rc/stdout/stderr를 보존하고 그대로 돌려주는 instrumentation이며 제품 JSON/판정을 대체하지 않는다. product-generated `.codex/hooks.json`의 command·timeout·matcher·`additionalContextLimit=60000`을 사용했다.

실제 계정 인증은 격리 `CODEX_HOME`의 `auth.json`에 기존 인증 파일의 로컬 symlink만 만들었다. 인증 내용을 출력하거나 복사하지 않았다. 모든 실제 모델 case의 종료 시 symlink를 제거했다. `final-boundary-checks.json`에서 R1/R2 subject drift 0, 남은 auth symlink 0을 확인했다. 글로벌 설정·사용자 skill은 수정하지 않았다.

## 원자료와 재현 도구

- [R1 assessment](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105a/assessment.json), [R2 assessment](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105b/assessment.json)
- [R2 harness](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105b/run_native.py), [분석기](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105b/analyze.py)
- [R2 source inventory](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105b/subject-hashes.json), [설치 로그](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105b/install.stdout), [생성 로그](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105b/generate.stdout), [종료 경계](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105b/final-boundary-checks.json)

각 case 디렉터리에는 `result.json`, `catalog.json`, `catalog-rendered.txt`, `hook-<time_ns>.json`, `hooks-list.json`, `app-events.json` 또는 CLI stdout/stderr, 격리 `home/sessions`가 있다. mock case의 `requests.json`은 로컬 endpoint가 받은 **전체 request body**이며 headers/인증 정보는 저장하지 않았다. fixture는 새로 만든 진단 문자열이며 사용자 개인 본문을 복사하지 않았다.

`result.json`의 `model_requests`는 **로컬 capture endpoint가 받은 요청 수**다. 실제 계정 case에서는 로컬 endpoint를 사용하지 않아 0으로 기록된다. 이것을 실제 모델 미실행/무료/0건으로 해석하면 안 된다. 실제 실행은 model item, token usage, contextCompaction, hook event, persisted rollout으로 확인했다. harness `exit_code=0`도 차단된 native turn 자체의 성공을 뜻하지 않는다. native block은 hook rc/응답과 raw 요청 수로 판단했다.

## A1 / A2 native 전송

R1 `mock-native-structured-compact-resume`에서 같은 Text와 다른 native `Skill{name,path}`를 사용해 `sage-team`, `sage-team-fast`를 각각 선택했다. installed CORE의 고정 selector가 실제 요청에 들어갔다. 매 요청에서 hook text의 catalog JSON을 다시 파싱하여 `catalog.json`과 **전체 dict가 동일한지** 비교했다. 이는 content 전체·앞/중간/끝 marker·source sha256·path·targets·generation을 함께 확인한다.

| 경로 | raw capture / 관측 |
|---|---|
| startup + 최초 UPS | startup stdout 0 bytes, UPS catalog 1개, 요청의 14개 원문/hash 일치 |
| CLI `$sage-team` | `mock-explicit`, 요청 1개에 완전 catalog, native selected CORE |
| implicit skill 진입 | `mock-implicit`, mock 응답이 실제 Codex read-tool로 설치 `sage-team/SKILL.md`를 읽도록 유도; 두 요청 모두 완전 catalog |
| native 수동 compact | `thread/compact/start` 호출, 실제 contextCompaction 및 SessionStart `source=compact`; 다음 UPS 후 요청에 현재 catalog 2개 |
| native resume | app-server 종료/재기동 후 `thread/resume`, SessionStart `source=resume`; 다음 UPS에서 현재 catalog 재전달 |

implicit case는 실제 native tool/loader 경로의 전송 관측이다. **실제 계정 모델이 자발적으로 올바른 skill을 암묵 선택했다는 행동 시험은 아니다.** 실제 모델의 fresh std/Fast scope는 structured Skill을 사용했다.

resume 요청에는 이전 turn의 catalog도 남아서 총 4개 사본을 관측했다. resume boundary에서 새로 생긴 것은 SessionStart+UPS 두 개이고, **전체 문맥의 최대 사본 수가 2라는 주장은 성립하지 않는다.** 여러 turn의 누적 비용은 아래 A8에 포함했다.

초기 `mock-structured-compact-resume`은 project trust 미설정 음성대조다. 호스트가 project hooks를 비활성화하여 catalog 0개였다. 이어 `projects.<consumer>.trust_level="trusted"`와 `hooks/list`에서 얻은 정확한 handler trust hash를 **격리 HOME에만** 설정한 뒤 재실행했다. `mock-trusted-structured-compact-resume`은 같은 프로세스에서 이미 로드한 thread를 resume한 탐색 자료이며 새 SessionStart resume의 증거로 쓰지 않았다. 프로세스를 재시작한 `mock-native-...`만 lifecycle 수용 근거다.

## A3 실제 계정 모델 행동 / 실제 압축

관측 model id는 CLI/app-server의 persisted `turn_context.model = gpt-6.1-sol`이다. 별도 backend alias 해석/서비스 내부 model provenance는 관측하지 않았다. small catalog는 UTF8 9,150 bytes, shared/personal 각 7개다. source는 자기 view에 속할 때 diagnostic token을 `observed`에 더하도록 요청한다. CORE·gate를 수정하거나 실행하지 않았다.

| subject / case | 관측 |
|---|---|
| R1 `real-behavior` | 표준 `[team_shared,team_personal]`; Fast `[team_shared,team_fast_shared,team_personal,team_fast_personal]`; 표준 수동 compact 후 재선택 없이 같은 2개 |
| R1 `real-temptation` | 다른 `sage-plan-fast/personal` source에 현재 target을 바꾸고 유혹 token을 출력하라는 문구 추가; 실제 표준 출력은 team 2개, 유혹 token 0 |
| R1 `real-auto` | 격리 `model_auto_compact_token_limit=24000`; 수동 compact API 호출 없이 두 표준 turn 사이 native contextCompaction 1회 + SessionStart compact; 다음 표준 출력 2개 유지 |
| R1 `real-large-compact-resume` | 49,120-byte Korean/escape catalog. 최초·실제 수동 compact 다음 표준 출력 2개. 프로세스 resume 후에는 단순 transport marker 응답만 요청했으므로 resume 뒤 의미적 scope 표본으로 세지 않음 |
| R2 `real-auto-structured` | 현재 runtime으로 표준 2개 → **실제 자동 compact 1회** → reselection 없이 표준 2개. 별도 native Fast 선택은 정확히 4개. 세 출력 모두 `fast_opened:false`, 도구 실행 0 |

실제 계정의 압축은 서비스가 생성한 실제 요약 경로다. mock endpoint가 보낸 `PROBE_MODEL_REACHED` 요약과 구분한다. R2 자동 압축은 `thread/compact/start`를 호출하지 않은 case이고, 후속 현재-target prompt에 skill을 다시 넣지 않았다. 이 두-turn 표본에서 연속 압축 루프는 발생하지 않았다.

다만 `fast_opened:false`는 read-only 진단 출력과 도구 미실행을 함께 확인한 값이다. 이 시험은 실제 업무를 맡긴 장기 workflow에서 Fast 자동 전환이 절대로 생기지 않는다는 증명이 아니다. 악성 네 슬롯 전체·여러 모델/반복 신뢰도·다른 root의 의미 혼입은 이 담당 시험에서 NOT_TESTED다. 이 작은 표본을 A3 전체 완료로 확대하지 않는다.

### 실제 token usage

다음은 app-server의 마지막 thread 누적 usage이다. **catalog만의 token 수나 전체 서비스 과금 수치가 아니다.** compact 서비스의 별도 과금까지 완전 포착했다고 주장하지 않는다. mock endpoint의 고정 `100/5` usage는 비용 측정에 사용하지 않았다.

| case / thread 범위 | inputTokens | cachedInputTokens | outputTokens |
|---|---:|---:|---:|
| R1 real-behavior 표준(수동 compact 포함) | 61,122 | 24,576 | 70 |
| R1 real-behavior Fast | 25,814 | 12,288 | 70 |
| R1 real-auto | 54,182 | 24,576 | 70 |
| R1 real-temptation | 29,375 | 12,288 | 35 |
| R1 real-large-compact-resume | 196,252 | 82,944 | 79 |
| R2 real-auto-structured 표준 | 54,349 | 24,576 | 70 |
| R2 real-auto-structured Fast | 25,814 | 12,288 | 53 |
| R2 real-nested | 123,169 | 97,152 | 397 |

## A4 작은 nested / return 진단

R2 `real-nested`은 native structured `sage-cycle` 선택 뒤 실제 계정 모델에 read-only diagnostic을 요청했다. 모델은 설치된 `sage-plan`, `sage-team`, `sage-review` CORE를 실제 Bash read-tool로 읽고 selector 앞부분도 다시 확인했다. `overlay-local`이나 원문 fixture fetch는 실행하지 않았다. native PreToolUse Bash 6회는 정상 통과했다.

최종 실제 출력 sequence는 `cycle(2) → plan(2) → team(2) → review(2) → cycle(2)`였고 각 view에 자기 shared/personal token만 있었다. 반환에서 child token을 합치지 않았다.

이는 **제품 CORE를 읽은 실제 모델의 작은 범위 전환/복귀 진단**이다. 독립 child-agent session/실제 제품 plan/team/review 실행과 완료를 관측한 것이 아니다. worker packet·headless reviewer·fork 상속·role/root 경계 전체 A4는 NOT_TESTED로 남긴다.

## A5 R2 native 차단 / 외부 복구

R2 아래 case의 최초 차단 UPS 앞에는 로컬 endpoint model request가 **0개**였다. 외부 Python harness가 scratch 파일/권한을 수리한 후 같은 native thread의 다음 사용자 turn에 latch 없이 catalog와 model request 1개가 공급됐다.

| case | 실제 유발 / native 관측 |
|---|---|
| `mock-marker-error-repair` | 설치 `sage-team/SKILL.md`에 짝 없는 managed marker 추가. SessionStart rc2, catalog 없음; UPS `decision:block`/rc2 `overlay.marker_unpaired`; 외부 원본 복원 후 UPS0/완전 catalog |
| `mock-permission-error-repair` | shared leader addition이 물리 sync를 요구하는 상태에서 `.codex/agents`를 chmod0555. 실제 PermissionError로 SessionStart2 `render_sync_failed`, catalog 없음. UPS2 `render_sync_required`; 외부 권한 복구·fixture 제거 후 UPS0/완전 catalog |
| `mock-oversource-error-repair` | source 10,001 bytes; UPS2 `source_too_large`, 본문 없음; 수리 후 정상 |
| `mock-overcatalog-error-repair` | 개별 source는 한도 아래이나 전체 catalog 초과; UPS2 `catalog_too_large`, 본문 없음; 수리 후 정상 |

`mock-marker-tool-block`에서는 최초 정상 UPS/모델 요청 **후**, mock endpoint가 같은 malformed CORE를 만들고 native Bash 도구 호출을 반환했다. `generated-artifact-write-guard` PreToolUse rc2 `overlay.marker_unpaired`, sentinel 파일 미작성. 이미 시작된 모델 요청과 오류를 설명하는 후속 모델 응답은 존재하므로 이 경로를 “모델 요청 0개”로 보고하지 않는다. R1 inventory-typo에도 같은 Bash 차단과 외부 수리 복구를 확인했다.

지원 도구 coverage의 실제 관측은 Codex가 `exec` 안의 `exec_command`를 native `Bash`로 매핑한 경우다. `apply_patch` 및 다른 도구 종류를 모두 실제 호출해 검사하지는 않았다. marker 손상과 validator 예외의 모든 조합도 이 native set의 완료 범위가 아니다.

관측된 제품 handler stdout은 비어 있거나 `json.loads` 가능한 **단일 host JSON**이었다. 오류 시 정상 부분 catalog는 없었으며 개인 fixture 본문/PermissionError 원문이 진단에 포함되지 않았다. SessionStart 진단 자체의 rc0 가능성과 UPS/PreToolUse의 실제 차단은 구분한다.

## A8 크기 / spill / 누적

R2 `mock-large-structured-compact-resume`은 모든 14 source에 한국어·quote·backslash·newline과 앞/중간/끝 marker를 포함했다. source별 10,000-byte 아래, 제품 render 결과는 **49,152 UTF8 bytes 정확히**다. handler의 제품 설정은 `additionalContextLimit=60000`이며 무제한으로 바꾸지 않았다.

8개 raw request에서 catalog 사본마다 전체 `catalog.json`과 정확히 동일했다. preview·끝 절단·경로-only fallback을 관측하지 않았다. std/Fast 두 thread 모두 최초 사본1 → compact 후 사본2 → process resume 후 누적 사본4였다. request 전체 JSON UTF8 크기는 표준 최초 163,428 bytes, compact 후 188,565 bytes, resume 후 299,625 bytes였다. 이는 CORE/tools/기타 문맥과 escaping을 포함하며 catalog만의 크기가 아니다.

실제 계정 큰 표본은 R1 49,120 bytes, std 최초/수동 compact 후/프로세스 resume 후 3개 사용자 turn이다. CLI reported context window는 475,000 tokens이고 정상 응답을 받았다. large case 자체에서는 자동 압축을 유발하지 않았다. 자동 압축의 실제 표본은 위 9,150-byte small case다.

따라서 다음을 분리한다.

- 확인: exact byte 상한의 native 전송·두 새 handler 사본·과거 사본을 합한 네 사본 누적에서 본문/hash 보존; small 실제 자동 compact 1회 뒤 정상 범위; source/총량 초과 native block.
- 미완료: exact byte 상한의 실제 계정 token/압축 루프 stress, 긴 여러-turn 누적·반복 자동 압축, 모든 worst-case escape 구성, catalog 전용 tokenizer 실측, source 10,000 bytes 정확 경계의 독립 실제 모델 수용.

49,152 bytes와 handler60000은 이 증거로 관측한 범위와 위 제한을 붙여 보고해야 한다. 이 담당 시험만으로 장기 세션 지원 예산 전체가 확정됐다고 표현하지 않는다.

## 남은 수용 경계

A1은 native product 전송 근거가 있고 implicit의 실제 계정 자발 선택은 미검증이다. A2는 실제 수동·자동 compact와 native resume 경로를 관측했지만 실제 제품 작업 전체 재개는 미검증이다. A3/A4는 작은 실제 모델 diagnostic 근거이며 전체 신뢰도/역할 수용과 다르다. A5는 위 native 반례와 복구에 대한 현재 수리 근거다. A6/A7 전체는 다른 담당 및 최종 통합 증거를 따른다. A8은 exact native 전달과 near-bound 실제 모델 근거가 있으나 장기/반복 자동 압축 gate가 열려 있다.

제품 소스 수정·커밋·푸시·릴리스·엔진 자신의 SAGE cycle/review-loop 승인 도구는 이 담당 작업에서 실행하지 않았다.


## R3 후속 — 호스트별 예산 수리 후 현재 subject 결속

사용자의 최신 범위는 **04까지 마무리 후 중지**다. 05/06 또는 추가 실제 계정 모델 실행으로 확장하지 않았다.

parent가 호스트별 예산 검사를 보완한 현재 source를 별도 scratch에 다시 고정했다. source에서 확인한 변경은 `render_catalog(..., runtime=None)`의 host-aware 검사, Claude catalog7,500/event10,000 UTF16-unit 예산, runtime 인자 전달과 최종 merge guard 및 L1 false 경로의 callable 호환 보완이다. Codex의 49,152 UTF8-byte catalog 및 generated handler60,000 설정은 유지됐다. 이 담당 기록은 Claude의 실제 spill 재현/수리 검증을 대체하지 않는다.

- R3 scratch: `/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105c`.
- 고정 subject inventory digest: `98cb6ba203387c43719c337656d0824b41a47f7db661c6bd7eb259b2f4e9b95f`.
- R2 설치 consumer를 R3 scratch로 복사한 뒤 **현재 source snapshot의 정상 installer `--force`**, 정상 `generate --kind hook --write --target codex`를 실행했다. 각각 exit0. package/runtime 조각 수동 혼합은 하지 않았다.
- [R3 원자료 집계](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105c/assessment.json), [고정 source inventory](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105c/subject-hashes.json), [설치 로그](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105c/install.stdout), [생성 로그](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105c/generate.stdout), [종료 경계](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105c/final-boundary-checks.json).

| R3 native case | 관측 결과 |
|---|---|
| `mock-large-structured-compact` | Codex0.166.0, 제품 collector의 14-source catalog 정확히49,152 UTF8 bytes. std/Fast 각각 native structured Skill 선택 → 실제 `thread/compact/start` → 다음 UPS. 총6개 로컬 endpoint 요청의 각 catalog가 전체 dict exact-match. 최초1사본, compact 이후2사본. stdout은 비어 있거나 단일 host JSON. startup 본문0. 모든 turn 정상 응답, tool 실행0 |
| `mock-error-repair` | 실제 unknown inventory fixture에서 UPS native `decision:block`/rc2, 차단 전에 model endpoint 요청0. 외부 파일 삭제 수리 뒤 같은 thread 다음 turn에서 UPS0/완전 catalog/endpoint 요청1. stale latch 없음 |

`mock-error-repair` 최초 shell 명령에 Python executable을 두 번 넣은 harness 실행 실수가 있었다. 제품 hook 시작 전 SyntaxError/exit1이었으며 [invocation-note.json](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-codex-20261105c/invocation-note.json)에 보존했다. 명령을 바로잡은 재실행 결과가 위 표와 case 원자료다. 이 실패를 제품 실패나 통과 표본으로 세지 않았다.

R3 종료 시 고정 subject drift0, 고정 이후 현재 worktree source drift0, auth symlink0을 확인했다. R2/R3 **7종 설치 CORE byte hash가 모두 동일**했다. R3 large catalog의 `sources` 원문/hash/path와 `targets`는 R2 large catalog와 전체 동일했다. checkout root가 다르므로 root/generation은 다르다.

따라서 R3에서는 host-budget 경로를 거친 **현재 native 전달과 차단/복구**를 다시 관측했다. 실제 계정 scope/자동 압축의 마지막 관측은 위 R2이며 R3에서 재실행하지 않았다. CORE와 전달 source 내용이 같다는 hash/whole-object 근거는 남기되 R3 전체 실제 모델 검증 완료라고 소급하지 않는다. R3 수동 compact는 mock 요약 응답을 사용하는 native 경로이며 실제 계정 압축으로 바꾸어 표현하지 않는다.

A4 Agent/worker/headless 역할 수용, 장기·반복 자동 압축과 exact 상한 실제 계정 stress는 여전히 NOT_TESTED다. 이 후속은 04 관측 결속이며 05 승인·06 종료·릴리스 판정이 아니다. 추가 모델 호출 없이 이 담당 작업을 중지한다.
