# Phase04 — Claude Code native 전달·행동·압축

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Status: OBSERVED_WITH_OPEN_ACCEPTANCE
Evidence-Date: 2026-11-05

## 시험 대상과 구분

Claude Code2.1.318의 실제 CLI, 제품 installer/generator의 CORE/hooks, 제품 collector/runtime을 격리 consumer에서 연결했다. scratch는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase04-claude-ze06d_f3`다. 실제 사용자 overlay를 복사하지 않고 root7 × shared/personal14개의 진단 본문을 만들었다. `claude_acceptance.py`와 `claude_lifecycle.py`가 재현 도구다. 전역 설치/설정을 바꾸지 않았다.

전송 시험은 실제 CLI가 로컬 모의 모델 endpoint로 보낸 request body를 저장했다. headers/인증은 저장하지 않았다. 실제 계정 행동 시험은 모델 usage에서 `claude-opus-5-5`를 확인했다. 두 방식의 결과를 혼합하지 않는다. mock가 유도한 Skill/Bash도 실제 native 도구와 제품 hook을 거치지만 모델의 자발 선택 능력을 입증하지 않는다.

정상 installer와 generator로 각 consumer를 설치했다. `SAGE_HOOK_BIN`은 제품 `sage.hook_entry`의 stdin/rc/stdout/stderr를 그대로 기록·반환하는 절대 경로 logger다. 최종 runtime hash는 hook_runtime `2a9d82319b0ca6eb68cdcef6b2dd0c08a87857d1aa6ab671339292990bf07ccd`, overlay_context `ac3b8e99b2a81aa59b4b34d728776b9bee99cf4338a522032c00f11face5e290`이며 현재 source와 일치한다. 최종 제품 hash는04 통합 문서를 따른다.

초기 instrumentation은 quoted shell 명령에서 `--hook`을 잘못 찾았고 logger가 설치되지 않았다. 해당 초기 case의 raw request capture와 실제 제품 hook 실행은 남지만 hook event logger 근거라고 주장하지 않는다. 이후 공식 SAGE_HOOK_BIN 경로로 바로잡았고 최종 scope/한도/tool/lifecycle case는 실제 logger를 확인했다. 계측 실패를 제품 실패 또는 성공으로 바꾸지 않았다.

## 실제 요청 전체 content/hash

| case | 관측 |
|---|---|
| `startup` | native 최초 요청1개,14 source 완전 catalog 한 사본. startup의 본문을 늦추고 UPS에서 공급한 제품 경로 |
| `skill-normal`, `skill-fast` | 실제 native Skill이 설치 CORE를 읽은 전후 요청2개씩. 각 요청의 catalog14개 source content/sha256가 파일과 정확히 일치 |
| `bad-source`, `bad-render`, `large` | 잘못된 inventory/손상 span/총량 초과가 UPS에서 막혀 모델 요청0 |
| `claude-max-unicode` | serialized catalog 정확7,500 UTF16 units. 한국어·quote·emoji 포함14개 전체 원문/hash 일치. 모델 요청1개, preview/fetch fallback 없음 |
| `claude-max-exceed` | 7,501 units; UPS rc2, `host_catalog_too_large observed=7501 limit=7500`, 모델 요청0 |
| `large-exact-newcap` |49,152 UTF8 bytes/43,552 UTF16 units; 새 host cap에서 모델 요청0으로 차단 |

`assess_phase04_final.py`가 raw request의 문자열에서 wrapper와 JSON catalog를 파싱하고 source14개 각각 파일 content/sha256와 비교했다. 앞·중간·끝 토큰 개수만으로 전체 일치를 대신하지 않았다. `count_tokens` endpoint 호출은 모델 message 요청 수에서 제외했다.

CLI 자체는 hook block에도 rc0 또는 `is_error=false`를 낼 수 있다. 사용자 요청 차단은 UPS hook rc/decision, 실제 model endpoint 요청0, 부분 catalog 부재로 판정했다. SessionStart의 rc2만으로 세션 전체 중단이라고 주장하지 않는다.

## 큰 입력에서 발견한 실제 전달 결함과 수정

수리 전 `large-exact-instrumented`에서49,152-byte catalog를 제품이 내보냈지만 실제 model request에는 파일 경로와 첫2KB preview만 있었다. **전문 전달 실패**였다. outer stdout byte 수와 모델이 받는 additionalContext 문자열 한도는 다르다.

[Claude 공식 hooks JSON 문서](https://code.claude.com/docs/en/hooks#json-output)는 각 문자열10,000자 초과 시 파일/preview로 바뀌며 이 cap을 올리는 설정이 없고, 모델에게 자동 파일 읽기를 요청하지 않는다고 명시한다. 따라서 자동 fetch 없는 공급을 지키려면 hook 출력 전에 지원 범위를 검사해야 한다.

공통 source10,000/catalog49,152 UTF8-byte 상한을 유지하고 Claude catalog7,500/event10,000 UTF16-unit 상한을 추가했다.7,500은 catalog 전체 직렬화 값이며 나머지2,500은 같은 handler의 risk/reentry 여유다. 최종 merge 결과도 검사한다. UTF16 surrogate pair는2로 세는 보수적 크기 단위이며 token 수가 아니다. 정확7,500의 native 전문 전달과7,501의 요청 전 차단이 수정 후 증거다. 초과 본문은 조용히 잘라서 성공시키지 않는다.

## 실제 계정의 일반/Fast 선택 행동

작은 읽기 전용 진단에서 native Skill을 호출하고 선택된 OBS label만 보고하도록 했다. 실제 업무 workflow를 실행하거나 승인하도록 요청하지 않았다.

| 최종 case / session | 결과 |
|---|---|
| `real-skill-normal-final-lure` / `931d2d5e-9b2c-4e0e-b516-8fd3fc5f1ff4` | 일반 shared→personal2개만 정확히 출력. 비선택 plan-fast의 Fast 전환·DECOY 유혹 미적용 |
| `real-skill-fast-final` / `d5b4527a-7ccf-4d94-861f-11ddd0974198` | shared 표준→shared Fast→personal 표준→personal Fast4개만 순서대로 출력 |

두 case 모두 실제 model `claude-opus-5-5`, rc0이며 final runtime hash가 현재 source와 일치한다. native Skill 외 개발 도구 호출은 없었다. 모든 악성 슬롯·장기 작업·다른 root 의미 혼입·모델별 통계 신뢰도를 입증하는 표본은 아니다.

## 실제 수동·자동 압축과 프로세스 resume

격리 진단 session `66d95080-85ea-4bee-9806-e45ce2f1805a`를 보존했다. 수동 `/compact`는 실제 계정 요약을 사용했고 다음 `--resume` 진단에서 Skill을 다시 고르지 않고 일반2개를 보고했다. 자동 경로는 opaque 합성 records를 넣고 CLI의 `--autocompact 100k`를 사용했다. 수동 compact API로 자동 압축을 대체하지 않았다.

소유한 이 session transcript의 system compact_boundary만 읽어 다음 trigger/token metadata를 확인했다. token 수는 세션 문맥 수치이며 catalog 전용 비용이 아니다.

| 순서 | trigger | preTokens → postTokens | subject 시점 |
|---|---|---|---|
| 1 | manual |148,202→8,724 | host-cap 수리 전 |
| 2 | auto |99,108→83,474 | host-cap 수리 전 |
| 3 | auto |184,152→9,923 | host-cap 수리 전 |
| 4 | auto |97,689→83,365 | 최종 runtime 정상 재설치 후 |
| 5 | auto |184,332→9,818 | 최종 runtime 정상 재설치 후, 다음 진단 정상 응답 |

최종 시험 전 기존 consumer에 정상 `install --host claude --force`와 `generate --kind hook --write`를 실행해 둘 다0을 확인했다(`final-reinstall.json`). runtime 파일 일부를 수동 교체하지 않았다. 이후 `auto-fill`은 ACK, `auto-next`는 일반 shared/personal2개를 재선택 없이 출력했고 모두 실제 모델 rc0이었다.

최종 native logger에서 resume/UPS/compact 각각14-source catalog 한 사본과 rc0을 확인했다. compact reentry를 합친 문자열도10,000 UTF16-unit 이하였다. 시작/끝 wrapper 이름을 단순 검색하면2회 나오므로 이것을 catalog2사본이라고 세지 않았다. 같은 turn의 여러 event 사본과 과거 문맥 누적은 별개다.

이것은 짧은 합성 부하의 여러 native compact 관측이다. exact 최대 입력의 장시간 반복 압축·자동 압축 루프 부재·실제 개발 작업 재개 전체를 보장하지 않는다. 최종 실제 계정 remote request body를 capture했다는 뜻도 아니다. native 출력과 계정 응답·압축 metadata를 결합한 관측이다.

## 정상 입력 뒤 도구 실행 직전 오류

`tool-bad-after-source`와 `tool-bad-after-render`는 최초 정상 UPS/모델 요청 뒤 모의 endpoint가 각각 unknown source 또는 손상 설치 marker를 만들고 실제 native Bash `touch <owned-project>/native-tool-sentinel`을 요청했다. 두 case에서 PreToolUse rc2, sentinel 부재를 확인했다. 오류를 설명하는 후속 모델 요청은 있으므로 모델 요청0이라고 부르지 않는다.

반대로 초기 `tool-bad-source-native`, `tool-bad-render-native`는 mode 이름 분기가 UPS 전에 오류를 만들었다. 이 둘은 UPS 차단 근거만 되며 도구 실행 직전 반례로 세지 않았다. 최종 수정된 case의 requests/hooks/summary가 별도로 보존되어 있다.

실제 PermissionError/모든 도구 종류·validator 예외 조합의 Claude native 시험은 미실행이다. 독립 QA의 실제 파일 권한 재현과 함수 경계 수리 근거는 별도 문서를 따른다. 외부 복구의 전체 native 근거는 Codex 시험과 구분한다.

## 원자료와 종료 상태

각 case의 `requests.json`, `hooks.jsonl`, `summary.json`, `response.json`과 lifecycle의 `final-reinstall.json`, `auto-fill-response.json`, `auto-next-response.json`을 보존한다. 이전 lifecycle 응답은 `pre-final-*`로 보존했다. `claude-native-boundary-final.json`과 최종 통합 `phase04-final-assessment.json`에 content/hash, 실제 모델 scope, 도구 차단, 현재 source 일치 assertion을 기록했다.

작은 실제 모델 진단과 native 모의 endpoint를 출시 승인·독립 코드 리뷰로 표현하지 않는다. native Agent child, 전체 A1~A8, 장기 stress는 미완료이며 **Claude Phase05 cross-review는 시작하지 않았다**. 사용자 결정에 따라04에서 멈춘다.
