# [Fast 기본 계획] 세션 위험도 선언의 적용 범위·경로 판정·Fast 종료 뒤 문서 수정 (#23)

Cycle-Stem: `sage-1.3.2-declared-risk-scope`
Cycle-Mode: FAST
Document-Language: ko
Risk Level: L3
Fast-Review-Level: L3
Fast-Minimum-Rounds: 1
Fast-Lens-Count: 4
Fast-Lenses: correctness, security, error_handling, api_contract
Fast-Reason: 게이트 판정·경로 판정·선언 포착을 고치므로 L3. 각 변경은 함수 단위로 좁고, 풀리면 안 되는 갈래를 시험으로 고정할 수 있어 Fast 로 진행
Fast-Audit-Run: pending
Status: COMPLETED — 05 codex cross-review 6차 APPROVED, 06 작성(2026-10-22)
Done-Criteria-Revision: 5

## Phase 00 — 기본 계획

### 배경

- 이슈: https://github.com/SeJonJ/SAGE/issues/23 (보고 파일 개정판에서 증상 4 추가)
- 엔진 저장소에는 SAGE 를 설치하지 않는다. Fast 문서 절차를 손으로 따르고 감사 run 은 열지 않는다(`Fast-Audit-Run: pending`). 05 는 codex cross-review.
- 재현: v1.3.1(`af48ad2`) core 를 기존 시험 도우미(`test_cycle_stem_declaration` 의 `CLOSED_PROFILE`·`_closed_snapshot`, `test_fast_cycle` 의 `TestFastSourceGate`)로 직접 호출했다.

| 상황 | 선언 L3 | 선언 L2 | 선언 L1 | 선언 L0·없음 |
|---|---|---|---|---|
| 완결 사이클 · `.sage/knowledge_writeback_summary.md` | 차단 | 차단 | 차단 | 통과 |
| 완결 사이클 · 프로젝트 밖 | 차단 | 차단 | 차단 | 통과 |
| 사이클 해제 뒤 · 프로젝트 안 문서 | 차단 | 차단 | 차단 | 통과 |
| 사이클 해제 뒤 · 프로젝트 밖 | 차단 | 차단 | 차단 | 통과 |

| Fast 사이클 close 뒤(선언 없음) | 결과 | 같은 상황 표준 사이클 |
|---|---|---|
| 06 수정 | `block_fast_cycle_audit`(override 불가) — 「Fast Plan run binding mismatch」 | 통과 |
| 00 단독 수정 | 통과(보고의 「00 도 막힘」은 미재현 — 원문 메시지 확인 필요) | 통과 |
| abort 된 run 의 06 수정 | 같은 차단·같은 문구 | — |

- 감사 파일은 정상(`file_ok=True`)이고 close 된 run 은 `terminal=True, result="APPROVED"`, abort 는 `result="ABORTED"` 로 남아 있다. 게이트가 이 구분을 쓰지 않는다.
- 보고서의 원인 서술 정정: Fast 검사가 완결 면제보다 먼저인 것이 아니라, 완결 면제(`_phase_only_change`)가 완결 차단 하나만 건너뛰고 판정을 끝내지 않아 뒤의 Fast 검사까지 내려간다.
- `make_rel` 은 경로 **문자열**만 비교한다. macOS 에서 실제 프로젝트 파일을 다른 표기로 가리키면 모두 `<outside-project>` 가 됐다.

| 같은 프로젝트 파일을 가리키는 표기 | 현재 `make_rel` |
|---|---|
| 대소문자만 다름(`…/proj/src/a.py`) | `<outside-project>` |
| 루트로 가는 심볼릭 링크 별칭 | `<outside-project>` |
| `/tmp` ↔ `/private/tmp` | `<outside-project>` |
| Windows 짧은 이름 `PROJ~1`, UNC, subst 드라이브(`ntpath` 규칙) | 밖 또는 `ValueError` → `<outside-project>` |
| 예외 발생 | `<outside-project>` |

### 호스트 동작 실측과 codex 확인 (2026-10-21)

검증용 hook(입력 stdin 만 기록)을 둔 임시 프로젝트에서 claude 2.1.299·codex 0.162.1 을 실행했고, 같은 가정을 codex 에게 질문했다. 질문·답·로그는 작업 scratchpad `probe-session/` 에 있다.

| 항목 | claude 실측 | codex 실측 | codex 답 |
|---|---|---|---|
| UserPromptSubmit `prompt` 가 원문 그대로 | 그대로 | 그대로 | TUI 에서도 그대로(사용자 명령 확장·첨부는 미확인) |
| 프롬프트·PreToolUse·셸 env 의 세션 id 일치 | 일치(`CLAUDE_CODE_SESSION_ID`) | 일치(`CODEX_SESSION_ID`) | env 이름의 안정 계약은 미확인 |
| resume 시 세션 id 유지 | 유지 | 유지 | fork 는 새 id |
| 서브에이전트 PreToolUse 세션 id | 부모 id + `agent_id` | — | 문서상 부모 id, 실측 못 함 |
| 서브에이전트 결과가 UserPromptSubmit 로 | **들어옴**: `<agent-message from=…>` 로 시작, 본문 들여쓰기 | — | 사람이 치지 않은 글이 `prompt` 로 올 수 있음(내부 메모리 에이전트) |
| 셸에서 `<root>/.codex/` 쓰기 | 해당 없음 | — | 불가(Operation not permitted), `.sage/` 는 가능 |
| 압축 뒤 세션 id | 유지 | — | 미확인 |

결론
- 세션 id 로 선언을 나누는 지금 구조는 두 호스트에서 성립한다. 이번 수정은 이 구조를 바꾸지 않는다.
- 어떤 통로(자연어·표식·CLI)도 「사람이 썼다」를 증명하지 못한다. 에이전트가 셸에서 같은 세션을 resume 해 프롬프트를 만들 수 있다(codex 실측). 이는 ARCHITECTURE 의 신뢰 경계(정직한 호스트의 실수를 막는다) 밖이다. 이번 범위는 **정직한 흐름에서의 오포착**(서브에이전트 보고가 선언·해제로 잡히는 것)을 막는 데까지다.
- CLI 선언(`sage risk set`)은 채택하지 않는다: codex 셸이 `.codex/` 에 못 써서 저장 위치를 에이전트가 고칠 수 있는 곳으로 옮겨야 하고, env 로 세션을 고르면 중첩 실행 시 다른 호스트의 id 가 샌다(실측).

### 문제

1. **경로 판정이 실제 파일이 아니라 표기를 본다.** 별칭으로 쓴 프로젝트 파일이 「밖」으로 분류돼 경로 위험 규칙(L2 `src/**` 등)을 비켜 간다. 선언과 무관한 기존 구멍이다. 예외도 「밖」으로 떨어진다 — 판정 실패가 통과 방향으로 처리된다.
2. **세션 선언이 경로 성격을 무시한다.** `classify_risk()` 는 선언(L1~L3)이 계산값보다 높으면 무조건 올린다. 프로젝트 밖 파일이 사이클 검사에 들어간다.
3. **SAGE 스킬과 게이트가 서로를 막는다.** 스킬 종료 순서는 06 → write-back(`.sage/knowledge_writeback_summary.md` 작성) → retro → `sage cycle clear` 다. 06 과 clear 사이에는 사이클이 선언된 채 완결 판정이 나는 구간이 있고, 완결 면제는 phase 문서뿐이라 요약 파일이 막힌다. Fast 사이클에서는 완결 차단을 지나도 Fast 검사에서 다시 막힌다.
4. **선언 때문에만 생긴 차단이 그 사실을 말하지 않는다.** 해제 안내는 reconciliation 차단 하나에만 있다.
5. **사람이 치지 않은 프롬프트에서 선언을 잡는다.** claude 는 서브에이전트 결과를 UserPromptSubmit 로 넘긴다. 결과 문장에 「L3로 진행했습니다」나 「위험도 선언 해제」가 있으면 지금 규칙이 선언·해제로 잡는다(조용한 상향·조용한 해제).
6. **Fast run 이 정상 종료된 사이클의 phase 문서를 고칠 수 없다.** `_fast_cycle_state` 가 active run 이 아니면 전부 「결속 불일치」로 본다. 정상 close 와 abort, 진짜 불일치가 같은 키·같은 문구이고 override 도 불가다.

버그가 아닌 것: 선언한 세션에서 프로젝트 **안** 문서가 사이클 검사를 받는 것, 그 차단이 override 불가인 것, `sage cycle clear` 가 위험도 선언을 지우지 않는 것(둘은 다른 상태다), 선언이 세션 끝까지 유지되어 다음 사이클에도 적용되는 것은 의도된 동작이다.

### 범위

- 포함
  - 선언 상향에서 「확인된 프로젝트 밖」 변경만 제외한다. 확인은 이 판단에만 쓰는 보수적 함수 하나로 하고 `make_rel` 은 바꾸지 않는다.
  - 06 이 끝난 사이클의 종료 산출물(write-back 요약)을 완결 차단과 Fast 종료 검사에서 면제한다.
  - 선언 때문에만 생긴 위험도 관문 차단에 선언 사실·두 갈래 안내를 싣는다.
  - 선언 포착은 **지금 규칙 그대로** 둔다. 호스트가 넣은 프롬프트(서브에이전트 결과 등)만 판정에서 빼고, 정확한 한 줄 표식 `SAGE-RISK:` 을 **추가** 통로로 연다. 포착·해제 알림에 해제 방법을 함께 적는다.
  - Fast run 이 정상 close 된 완결 사이클의 phase 문서·종료 산출물 수정을 허용하고, 그 밖의 종료 run 은 별도 키·정확한 안내로 막는다.
  - gate·capture spec, troubleshooting(ko/en), ARTIFACTS(ko/en), manifest·localization 인벤토리.
- 제외
  - 선언 수명(세션 끝까지), 세션별 저장, 자연어 포착 규칙, 「선언 세션에서는 프로젝트 문서도 사이클을 받는다」는 의도, sage-team 종료 순서, profile 키 — 바꾸지 않는다.
  - `sage cycle clear` 와 위험도 선언의 연동 — CLI 는 세션을 확실히 알 수 없어 다른 세션의 선언까지 지우게 된다.
  - CLI 선언 통로, 작성자 인증 — 위 실측 결론.
  - write guard 의 경로 판정 — 경로 조각으로 판정해 별칭 문제와 무관하다.
  - `make_rel` 표기 정규화(별칭·대소문자·짧은 이름으로 쓴 프로젝트 파일이 선언 없이도 위험 규칙을 비켜 가는 기존 구멍) — 후속 과제(결정 1).
  - `sage explain` 의 세션 선언 반영, 버전 올림·릴리즈.

### 설계 결정

1. **「확인된 밖」: `make_rel` 은 그대로 두고, 선언 면제를 줄 때만 보수적으로 확인한다.** (5.1판 범위 축소)
   - `make_rel` 의 출력과 그것을 쓰는 hook 4개의 동작은 **바꾸지 않는다**.
   - 구현 전 게이트 runtime 이 `make_rel` 호출을 감싸, `<outside-project>` 로 판정된 **원래 경로**들을 모은다. 변경이 1건 이상 전부 `<outside-project>` 이고 모은 경로가 **모두** 아래 확인을 통과하면 event 에 `outside_confirmed: true` 를 싣는다. core 는 이 값만 본다(core 는 파일을 읽지 않는다).
   - 확인(경로 하나): `raw` = 루트 기준으로 이은 원래 경로(`..` 를 접지 않음).
     - `casefold(realpath(raw))` 가 `casefold(realpath(root))` 아래이거나, `casefold(abspath(raw))` 가 `casefold(abspath(root))` 아래이면 → **확인 실패**(안일 수 있음).
     - 대상이 존재하는 일반 파일이고 링크 수(`st_nlink`)가 2 이상이면 → 확인 실패(하드 링크).
     - 어떤 예외든 → 확인 실패.
     - 그 밖 → 확인된 밖.
   - **틀려도 지금보다 느슨해지지 않는다.** 판정이 틀리는 방향은 둘뿐이다. (a) 실제 밖인데 확인 실패 → 지금처럼 상향(지금 동작 그대로). (b) 실제 안인데 확인된 밖 → `realpath` 가 풀지 못하는 별칭(bind mount 등)만 해당하고, 그 쓰기는 선언 없는 세션에서도 이미 통과한다. 그래서 이 함수에서 새 반례가 나와도 결과는 「지금 동작」 또는 「선언 없는 세션과 같음」 둘 중 하나다.
   - `realpath` 는 링크를 만나는 순서대로 풀므로 끊긴 링크·`링크/..` 를 따라가고, Windows 에서는 짧은 이름·subst 도 푼다. 대소문자 무시 비교는 대소문자 구분 볼륨의 「이름만 다른 진짜 밖 폴더」도 확인 실패로 보는데, 보수 방향이라 허용한다.
   - **범위에서 뺀 것:** 리뷰 1~3회차에서 함께 고치기로 했던 「별칭·대소문자·짧은 이름으로 쓴 프로젝트 파일이 선언 없이도 위험 규칙을 비켜 가는」 기존 구멍(`make_rel` 표기 정규화)은 **후속 과제로 분리한다.** #23 해결에 필요하지 않고, 경로 정규화는 과거(프로젝트 루트 탐색 8갈래 중 4갈래 오류, override 저장소 키, 운영 진단 사이클의 열 라운드 리뷰)와 이번 codex 1~3회차에서 매 라운드 새 반례(끊긴 링크, `..`, 대소문자, 짧은 이름, 안 링크)가 나온 표면이다. 리뷰에서 찾은 반례는 후속 정본에 그대로 넘긴다.
2. **선언 상향 제외는 「변경 1건 이상, 전부 확인된 밖(`outside_confirmed`) 또는 전부 종료 산출물」일 때만.**
   - 확인 실패·빈 경로·변경 0건·밖과 안이 섞인 변경은 지금처럼 상향한다.
   - 종료 산출물(결정 3의 `_CLOSING_ARTIFACTS`)도 같은 취급이다. 완결 차단만 면제하면 뒤의 reconciliation 이 「00 L2 < 선언 L3」로 다시 막는다(자체 리뷰 1회차, 기존 시뮬레이션 결과). 끝난 사이클의 00 을 올리라는 안내는 성립하지 않는다.
   - 약화가 아니다: 같은 쓰기는 선언 없는 세션에서 이미 통과한다. 섞인 변경(요약 + 소스, 밖 + 안)은 지금처럼 상향한다.
   - 밖·종료 산출물이 섞인 변경(밖 1건 + 요약 1건)은 상향한다 — 술어를 하나로 합치지 않고 단순하게 둔다.
3. **종료 산출물 면제: 「06 이 끝난 사이클의 마무리 쓰기」 하나의 술어.**
   - `_CLOSING_ARTIFACTS = (".sage/knowledge_writeback_summary.md",)`. 06 뒤 편집 도구로 프로젝트 안에 쓰는 SAGE 산출물은 이것뿐이다(`plan_interview.md` 는 00 전, retro 노트는 CLI 가 vault 에 씀).
   - 요약만 쓰는 변경은 결정 2로 선언 상향을 받지 않아 PDCA 분기에 들어가지 않는다(선언 없는 세션과 같음). 아래 술어는 요약이 phase 문서와 **한 변경에 섞인** 경우를 위한 것이다.
   - `_closing_only_change(event, cfg)`: 변경 1건 이상, 전부 phase 문서 또는 목록 경로. **완결 차단 면제 자리 한 곳**(지금 `_phase_only_change` 호출부)만 이것으로 바꾸고, 결정 8의 Fast 종료 통과 조건에도 쓴다. missing phases 면제(`_missing_phases`)의 `_phase_only_change` 는 그대로 둔다 — 그쪽은 「요구 phase 문서를 만드는 쓰기」의 교착 해소라 요약 파일과 무관하다.
   - 면제는 완결 차단(과 결정 8의 Fast 종료 검사)뿐이다. phase 문서가 섞인 변경은 뒤따르는 위험도 판정을 그대로 받는다.
   - profile 키로 열지 않는다: 키로 열면 `**/*` 같은 값이 완결 차단을 끄는 통로가 된다. sage-team 렌더·spec 의 경로가 상수와 같은지 시험으로 고정한다.
4. **선언 원인 안내: 위험도 관문 차단 8종 + Fast 종료 차단, 판정 한 곳에서.**
   - 목록: `block_cycle_binding`, `block_cycle_closed`, `block_document_language_conflict`, `block_cycle_risk_declaration`, `block_phase_incomplete`, `block_l3_no_plan`, `block_l3_strategy_unresolved`, `block_l3_review_evidence`, 그리고 결정 8의 `block_fast_cycle_terminal`. 모두 위험도가 연 분기 안의 차단이다. reconciliation 은 이미 출처별 안내가 있어 뺀다. 위험도와 무관한 차단(feedback·desktop·report 계열, 감사 손상)에는 붙이지 않는다.
   - 판정: `classify_risk()` 가 선언 반영 전 위험도 `computed_risk` 를 함께 돌려주고, `decide()` 공개 래퍼가 「목록의 차단 · `computed_risk ∈ {none, L0}` · phase 문서 쓰기 아님 · 선언이 실제로 상향함」이면 `declaration_only: true` 와 **`declared_risk`(선언 등급)** 를 싣는다. 차단 decision 의 `risk` 는 `PDCA`·`FAST` 같은 분류라 선언 등급을 담지 못한다(codex 1회차). `messages` 필드 계약에 `declared_risk` 를 더하고 양 호스트·양 언어 렌더를 시험한다.
   - 표시: `messages.gate_text` 한 곳에서 한 줄 더. 두 갈래 — 「선언이 잘못이면 '위험도 선언 해제' 또는 `SAGE-RISK: clear`, 실제 {level} 작업이면 위 안내대로」. 기본 템플릿 profile 은 위험 glob 이 비어 있어 진짜 작업도 `computed_risk = none` 이므로 해제만 권하면 안 된다.
   - `declared_l3` 의미는 바꾸지 않는다(선언 L3 + 내용 키워드 L3 + plan 없음 → `block_l3_no_plan`).
   - file 칸이 비면 첫 변경 경로를 채운다. `CONTRACT_VERSION` 은 올리지 않는다(선택 필드).
5. **선언 포착: 지금 규칙 유지 + 호스트 봉투 제외 + 정확한 표식 추가.**
   - 자연어 포착·해제 규칙(`_LEVEL_PATTERN_1/2`, 의문·가정 필터, 「위험도 선언 해제」, 부정 처리, 모호 기각)은 **그대로** 둔다.
   - **호스트 봉투 제거:** 프롬프트 **맨 앞**(앞 공백 제외 첫 줄, 0열)이 `<tag …>` 이면 그 줄부터 처음 나오는 0열 `</tag>` 줄까지를 지우고, 이어서 또 봉투로 시작하면 반복한 뒤 **남은 글만** 판정한다(`tag` ∈ `_HOST_ENVELOPES = ("agent-message", "task-notification")`). 호스트 봉투는 프롬프트 시작에 붙으므로 맨 앞만 본다 — 중간에 나온 태그(코드 블록 예시 등)는 봉투로 보지 않아 사람의 표식을 지우지 않는다(codex 1회차). claude 는 서브에이전트 보고의 모든 줄을 들여 써서 0열 줄은 호스트만 만들 수 있다 — 보고 본문이 닫는 태그를 흉내 내 구간을 일찍 끝낼 수 없다. 맨 앞 봉투가 닫히지 않으면 프롬프트 전체를 호스트 글로 보고 `noop` 이다(상태를 바꾸지 않는 방향). 봉투만 있으면 `noop`(출력 없음). 실측 형식(`agent-message`)을 시험 fixture 로 고정한다.
   - **정확한 표식(추가):** 한 줄 전체가 `SAGE-RISK: L0`~`L3` 또는 `SAGE-RISK: clear` 인 줄(대소문자 무시, 앞뒤 공백 허용, 정규식 `^ {0,3}SAGE-RISK:[ \t]*(L[0-3]|clear)[ \t]*$` 줄 단위). 표식이 있는 프롬프트는 표식만 보고 자연어 규칙은 보지 않는다. 서로 다른 값의 표식 줄이 둘 이상이면 상태를 바꾸지 않고 모호 안내.
   - 표식 줄은 **프롬프트의 첫 코드 펜스보다 앞**에서만 인정한다(들여쓰기 코드 줄 제외, 앞 공백 3칸까지). 어느 줄이든 펜스 모양(``` · ~~~)이 처음 나오면 그 뒤 표식은 받지 않는다. 처음에는 펜스 안팎을 끝까지 추적했으나 05 1~3회차에서 닫는 펜스 판정(뒤 글자, 목록·인용 문맥, 상대 들여쓰기) 반례가 매번 나와 규칙을 단순화했다. 자연어 규칙은 지금처럼 전체를 본다. `cycle_binding.non_fenced_lines` 의 닫는 펜스 결함(Cycle-Stem 판정)은 별도 이슈로 보고한다. 문서의 표식 예시는 코드 블록이나 문장 속 인라인 코드로만 적는다.
   - **알림:** 포착 「[Risk 선언 포착] 이번 세션 작업 레벨: L3 … 해제: '위험도 선언 해제' 또는 `SAGE-RISK: clear`」. 모호 기각 안내에 「정확히 지정하려면 `SAGE-RISK: L3` 한 줄」을 덧붙인다. 문구는 i18n(ko/en)으로 옮긴다.
   - 저장 형식·위치(`<root>/.claude|.codex/logs/declared-risk-<session>.json`)·2일 정리·세션별 분리는 그대로다. 상태에 `source`(`explicit`/`natural`)를 더하되 읽는 쪽은 `level` 만 본다(기존 파일 그대로 유효).
6. **불변식: 선언 세션의 판정은 같은 입력의 선언 없는 판정보다 느슨하지 않다.**
   - 입력 행렬(경로 종류 × 사이클 상태 × 00 위험도 × 리뷰 유무 × 사이클 모드) × 선언 등급(L0~L3)에서 엄격도(block > warn > ok)를 비교한다. 「선언 등급이 높을수록 같거나 엄격」도 함께 본다.
   - 「선언 등급이 높을수록 같거나 엄격」(등급 단조)은 **이번 범위에서 보장하지 않는다(알려진 한계).** 래퍼는 미선언 판정과만 비교한다. 단조 profile 에서도 phase 작성 면제 때문에 깨진다 — 계산 L0 인 `02` 문서 작성, 00 만 존재, 필수 phase L1 `[00,01]`·L2·L3 `[00,01,02,03]` 에서 선언 L1 은 `warn`, L2·L3 는 `ok`(codex 4회차, 반례 메커니즘은 3회차와 같음). 영향은 「요구 문서를 쓰는 중」 경고 하나가 덜 나오는 것이고 차단이 풀리지는 않는다. 등급끼리 비교까지 구조로 막으려면 선언 등급마다 판정을 반복해야 해 범위를 넘는다. profile 검증의 단조성 규칙과 함께 **후속 과제**로 둔다.
   - **현재 코드가 이미 깨는 사례(사용자 보고 대상):** ⓐ L0 경로 + L3 내용 키워드: 미선언 `warn_l0_l3_content` → 선언 L1 `ok`, L3 `ok_l3`(codex 1회차, 직접 재현). ⓑ 단조 profile 에서도 phase 작성 면제(`_missing_pre_impl_phases` 의 「바꾸는 phase 가 요구 목록 안이면 결핍 검사 생략」)가 선언으로 넓어진 요구 목록에서 켜져 미선언 `warn_phase_incomplete` 가 선언 `ok_l2` 가 된다(codex 3회차).
   - **조치: 불변식을 구조로 보장한다.** `decide()` 공개 래퍼가 선언이 실제로 상향한 경우에만 같은 입력을 선언 없이(`declared_max=None`) 한 번 더 판정하고, 엄격도(block > warn > ok)가 더 높은 쪽을 돌려준다. 같으면 선언 판정을 쓴다. core 는 순수 함수라 두 번 판정해도 부작용이 없다. 반례를 하나씩 막는 방식은 3회 리뷰에서 매번 새 반례가 나왔다(ⓐ·ⓑ·비단조 profile).
   - 이 래퍼는 불변식을 이미 지키는 입력의 결과를 바꾸지 않는다 — 바뀌는 것은 지금 「선언했더니 오히려 느슨해지는」 입력뿐이다. 미선언 판정이 선택되면 `declaration_only` 는 싣지 않는다(선언 때문에 막힌 것이 아니므로).
7. **모든 수정은 선언 등급과 무관하다.** 시험은 등급별로 돌린다(`declared_l3` 시험만 L3 전용).
8. **Fast run 이 종료된 사이클 (증상 4).**
   - `_fast_cycle_state` 에서 감사 파일 무결성 검사 **뒤**, 결속 불일치 판정 **앞**에서 대상 run 을 고른다: 같은 stem 의 active run 이 없고, 00 의 `Fast-Audit-Run` 이 가리키는 run 이 감사에 있고 `terminal` 이며 `cycle_stem` 이 같으면 그 run 을 대상으로 삼는다(종료 run). 그 밖은 지금 그대로.
   - **종료 run 도 active run 과 같은 검증을 모두 거친다:** `opener_run_issues`(`clean`·`seq_ok`·`chain_ok is True`·opener 필드), `open_issues`(plan 대조), Phase 00 위험도 대조, 정책 하한. 통과 갈래(APPROVED)는 여기에 더해 `review_result == "APPROVED"` 와 `loop_run_id` 존재를 본다 — 기록기(`close_fast`)가 요구하는 「APPROVED 리뷰 뒤 close」 계약을 읽는 쪽도 확인한다(codex 2회차). 하나라도 걸리면 지금처럼 `block_fast_cycle_audit`(override 불가)다. `chain_ok is not False` 처럼 느슨하게 보면 체인이 없는 run(`None`)을 통과시키고, 무결성 손상을 override 가능한 차단으로 내리게 된다(codex 1회차).
   - 검증을 통과한 종료 run 은 다음으로 가른다.
     - **통과:** `result == "APPROVED"`, `_cycle_closed(stem)` 참, 변경이 `_closing_only_change`. 이때 `(state, None)` 을 돌려준다 — `None` 을 돌려주면 뒤의 missing phases 검사가 Fast 가상 phase(composite 00)를 인정하지 못해, 선언 L2·L3 세션의 06 수정이 `block_phase_incomplete`(01·02·03 누락)로 막힌다(codex 1회차 재현). state 에 `terminal: True` 가 있으므로 `warn_fast_cycle` 안내는 종료 run 일 때 「종료된 Fast run」 문구로 바꾼다.
     - **그 밖(ABORTED·완결 아님·문서 아닌 변경):** 새 키 `block_fast_cycle_terminal`. 문구는 「이 사이클의 Fast run {id} 은 이미 {APPROVED/ABORTED} 로 종료됨 — 이 사이클에서 새 작업을 하지 말고 `sage cycle clear` 후 새 사이클」. 감사 손상 문구와 섞지 않는다.
   - `_fast_covers_required` 는 fresh run 이면 참이라 종료 run 에도 그대로 성립한다(composite 00 이 `parse_fast_plan` 검증을 이미 통과).
   - `block_fast_cycle_terminal` 은 **override 불가**다(`_NON_OVERRIDABLE_BLOCKS` 에 추가). abort 된 사이클은 「완결」이 아니어서 완결 차단이 걸리지 않으므로, 이 키가 override 가능하면 abort 사이클의 **소스 수정**까지 override 로 열린다(codex 2회차 재현). 지금 같은 입력이 받는 `block_fast_cycle_audit` 도 override 불가이므로 보호 수준은 그대로이고, 달라지는 것은 키와 안내뿐이다. 진짜 결속 불일치(다른 stem·active 여러 개·plan 과 다른 active)는 지금처럼 `block_fast_cycle_audit` 로 남는다.
   - 보고서의 F-3(감사가 정상이면 결속 차단 override 허용)은 거부한다 — 진짜 불일치까지 열린다. 정당한 경우는 위 두 갈래로 해소된다.

### Done Criteria
- [x] 선언 L1~L3 세션에서 확인된 프로젝트 밖 경로만 바꾸는 쓰기가 통과하고, 별칭·대소문자 변형·링크로 프로젝트를 가리킬 수 있는 경로·하드 링크·섞인 변경·변경 0건은 지금처럼 상향된다
- [x] `make_rel` 출력과 그것을 쓰는 hook 의 동작이 바뀌지 않는다
- [x] 06 이 끝난 사이클(표준·Fast)에서 write-back 요약 쓰기가 선언 유무와 무관하게 막히지 않고, 소스와 섞이면 차단된다
- [x] Fast run 이 APPROVED 로 close 된 완결 사이클에서 06 문서 수정이 통과하고, abort·미완결·문서 아닌 변경은 `block_fast_cycle_terminal`(override 불가), 감사 무결성 이상과 진짜 결속 불일치는 지금처럼 `block_fast_cycle_audit` 다
- [x] 선언 때문에만 생긴 위험도 관문 차단 메시지가 선언 사실과 두 갈래 안내를 싣고, 그 외 차단에는 붙지 않는다
- [x] 자연어 선언·해제가 지금과 같이 동작하고, 서브에이전트 결과 봉투는 선언·해제로 잡히지 않으며, `SAGE-RISK:` 표식이 추가로 동작한다
- [x] 기존 의도된 차단(선언 + 프로젝트 안 문서 + 완결/미결속, 완결 + 소스, 선언 L3 + 내용 키워드 L3 + plan 없음)이 그대로다
- [x] 같은 입력에서 선언 판정이 선언 없는 판정보다 느슨한 경우가 없다
- [x] spec·troubleshooting(ko/en)이 새 동작과 맞고 manifest·인벤토리가 갱신된다 (ARTIFACTS 는 설명이 그대로 맞아 변경 없음)
- [x] 관련 회귀 스위트가 통과한다
- [x] codex cross-review 가 APPROVED 다 (05 6회차)

### Document Mapping (Checklist)
- [x] Phase 00 context complete
- [x] Phase 01 requirements and acceptance matrix embedded
- [x] Phase 02 design and failure handling embedded
- [x] Phase 03 ownership, implementation checklist, and verification plan ready

## Phase 01 — 요구사항

### Acceptance Matrix

| ID | User Requirement | Required Evidence | Owner | Required? |
|---|---|---|---|---|
| O1 | 진짜 밖(존재·비존재 폴더, 다른 볼륨) → 확인된 밖 | runtime 시험 | dev | yes |
| O2 | 루트 별칭 심볼릭 링크·`/tmp`↔`/private/tmp`·대소문자만 다른 루트·끊긴 링크가 프로젝트를 가리킴·`링크/..` 로 프로젝트에 닿음 → 확인 실패 | runtime 시험(POSIX, 대소문자 항목은 대소문자 무시 볼륨에서만) | dev | yes |
| O3 | 하드 링크(링크 수 2 이상)·예외 → 확인 실패 | runtime 시험 | dev | yes |
| O4 | 밖 경로 여러 개 중 하나라도 확인 실패 → `outside_confirmed` 거짓 | runtime 시험 | dev | yes |
| O5 | `make_rel` 출력 불변: 기존 `TestMakeRel` 그대로 통과 | runtime 시험 | dev | yes |
| D1 | 선언 L1·L2·L3 각각 + 완결 사이클 + `outside_confirmed` → 통과 | core 시험 | dev | yes |
| D2 | 선언 L1·L2·L3 각각 + 사이클 미결속 + `outside_confirmed` → 통과 | core 시험 | dev | yes |
| D3 | `outside_confirmed` 거짓(밖 + 안 혼합, 확인 실패, 변경 0건), 밖 + 요약 혼합 → 지금처럼 상향 | core 시험 | dev | yes |
| D4 | hook 경유: 밖 Write 의 event 에 `outside_confirmed` 가 실림 | runtime 시험 | dev | yes |
| C1 | 선언 L1·L2·L3 각각 × 00 L1·L2·L3 × 완결 표준 사이클 + 요약만 → 통과(상향 없음, reconciliation 없음) | core 시험 | dev | yes |
| C2 | 선언 + 요약 + 소스 → `block_cycle_closed` / 선언 + 요약 + 06 문서 → 완결 면제 / 선언 + 변경 0건 → `block_cycle_closed` | core 시험 | dev | yes |
| C3 | sage-team 스킬·렌더(`templates/core/skills/sage-team.md`)의 요약 경로 = core 상수 | 대조 시험 | dev | yes |
| C4 | missing phases 면제는 그대로 `_phase_only_change`(요약이 섞이면 면제 없음) | core 시험 | dev | yes |
| F1 | Fast APPROVED close + 완결 + 06 수정 / 요약 쓰기(선언 유무 각각) → 통과 | core 시험 | dev | yes |
| F2 | Fast abort run + 06 수정 → `block_fast_cycle_terminal`(문구에 run id·결과) | core·messages 시험 | dev | yes |
| F3 | Fast APPROVED close 인데 미완결(05 승인 없음) → `block_fast_cycle_terminal` / 종료 run 의 `clean`·`seq_ok` 이상·`chain_ok` False/None·opener 필드 누락·plan 대조 실패 → `block_fast_cycle_audit` / 리뷰 기록 없는 close(open→close 두 줄) → 통과 아님 | core 시험 | dev | yes |
| F6 | 선언 L2·L3 + Fast APPROVED close + 06 수정 → `block_phase_incomplete` 아님(composite 00 이 01~03 충족) | core 시험 | dev | yes |
| F4 | plan 이 다른 stem 의 run·없는 run 을 가리킴, active 가 plan 과 다름 → `block_fast_cycle_audit`(변경 없음) | core 시험 | dev | yes |
| F5 | `block_fast_cycle_terminal`·`block_fast_cycle_audit` 모두 override 불가, ABORTED + 소스 수정이 활성 grant 로도 통과하지 않음 | runtime 시험 | dev | yes |
| H1 | 계산 `none`/`L0` + 선언으로 닿는 위험도 관문 차단에 `declaration_only`·`declared_risk`, 메시지(claude·codex, ko·en)에 선언 등급·해제 두 방법·실제 작업 갈래 | core·messages 시험 | dev | yes |
| H2 | 선언 없이도 막히는 차단, 위험도 무관 차단, reconciliation, 감사 손상 차단에는 `declaration_only` 없음 | core·messages 시험 | dev | yes |
| H3 | 선언 L3 + 내용 키워드 L3 + plan 없음 → `block_l3_no_plan`(의미 불변) | core 시험 | dev | yes |
| H4 | 선언이 올렸는데 계산상 file 이 비면 첫 변경 경로가 채워짐 | core 시험 | dev | yes |
| S1 | 기존 capture 시험 전부 그대로 통과(자연어 포착·해제·의문·부정·모호) | capture 시험 | dev | yes |
| S2 | `<agent-message …>` 봉투(실측 형식) 안의 「L3로 진행」·「위험도 선언 해제」·`SAGE-RISK: clear` → noop, 출력 없음 / 맨 앞 봉투 + 뒤의 사람 글 → 사람 글만 판정 / 들여 쓴 가짜 닫는 태그가 구간을 끝내지 못함 / 닫히지 않은 맨 앞 봉투 → noop / 중간(코드 블록 예시)의 태그는 봉투 아님 | capture 시험 | dev | yes |
| S3 | `SAGE-RISK: L0`~`L3`·`clear`(대소문자·공백 0~3칸 변형) → capture/clear / 펜스·4칸 들여쓰기 안·줄 일부 → 무시 / ```` ```text ```` 블록 안 ```` ```not-a-fence ```` 뒤의 표식 → 무시 / 서로 다른 두 표식 → 상태 불변 + 모호 안내 / 표식 + 자연어 다른 레벨 → 표식 값 | capture 시험 | dev | yes |
| S4 | 포착·해제·모호 알림에 해제 방법과 표식 안내가 나옴(claude·codex, ko·en) | capture·messages 시험 | dev | yes |
| S5 | 기존 상태 파일(`source` 없음)이 있는 세션의 게이트 판정이 그대로 | runtime 시험 | dev | yes |
| I1 | 불변식: 입력 행렬 × 선언 L0~L3 × (기본 템플릿·단조·비단조 profile)에서 엄격도(선언) ≥ 엄격도(없음). 등급 단조는 검사하지 않음(알려진 한계, codex 4회차 반례를 주석으로 남김) | core 성질 시험 | dev | yes |
| I2 | 반례 고정: L0 경로 + L3 키워드(선언 L1·L3 → `warn_l0_l3_content`), 단조 profile phase 작성 면제(선언 L2 → `warn_phase_incomplete`), 비단조 profile(선언 L2 → 미선언 판정) | core 시험 | dev | yes |
| X1 | spec(gate·capture)·troubleshooting·ARTIFACTS(ko/en)·manifest·인벤토리 | 문서 diff + 문서 시험 | dev | yes |
| X2 | hook 프로세스 경유: 상태 파일을 둔 임시 프로젝트에서 밖 Write·요약 Write exit 0 | runtime 시험 | dev | no |
| X3 | Windows 실기(win11): 다른 드라이브 밖 Write 통과(선언 L3), 짧은 이름으로 쓴 루트 별칭은 확인 실패(상향 유지) | 실기 기록 | dev | no |

## Phase 02 — 설계

### `hook_runtime` — 확인된 밖

```text
run_pre_implementation_gate:
  rel = make_rel(root)                       # 그대로
  outside_raw = []
  rel_rec(p): r = rel(p); if r == "<outside-project>": outside_raw.append(p); return r
  changes = io.extract_changes(raw, rel_rec)
  event["outside_confirmed"] = (changes and 전부 path == "<outside-project>"
                                and outside_raw and 전부 _outside_confirmed(root, p))

_outside_confirmed(root, p):                 # 예외는 False
  raw = p 가 절대경로면 p, 아니면 join(root, p)        # .. 접지 않음
  rr  = casefold(realpath(root)); ra = casefold(abspath(root))
  if casefold(realpath(raw)) 가 rr 아래 or casefold(abspath(raw)) 가 ra 아래: False
  if isfile(raw) and stat(raw).st_nlink >= 2: False
  True
```

- `make_rel` 은 수정하지 않는다. `_outside_confirmed` 는 이 게이트의 선언 면제 판단에만 쓰인다.

### `pre_implementation_gate_core`

```text
classify_risk:
  best["computed_risk"] = best["risk"]                          # 선언 반영 전
  exempt = event.outside_confirmed
           or (changes 1건 이상 and 전부 path in _CLOSING_ARTIFACTS)
  if declared and not exempt and 선언 > 계산값: 상향, 빈 file_short 채움

_CLOSING_ARTIFACTS = (".sage/knowledge_writeback_summary.md",)
_closing_only_change: 변경 1건 이상 and 전부 (phase 문서 or 목록 경로)
  완결 차단 면제(그 호출부 한 곳): _phase_only_change → _closing_only_change

_fast_cycle_state:
  ... file_ok 검사 뒤
  terminal_run = (not matching_active and plan run_id in runs
                  and runs[run_id].terminal and runs[run_id].cycle_stem == stem)
  if not terminal_run: ... 기존 결속 불일치 판정
  state = runs[run_id]
  공통 검증(opener_run_issues, open_issues, actual risk, policy floor) 실패 → 기존 audit 오류(override 불가)
  if terminal_run:
      if APPROVED and _cycle_closed(stem) and _closing_only_change(event): return state, None
      return None, TERMINAL(run_id, result)                    # 호출부가 block_fast_cycle_terminal

_RISK_GATED_BLOCKS = {8종 + block_fast_cycle_terminal}
decide(): d = _stamp_cycle_identity(_decide(event))
          if 선언 상향 있음:
              base = _stamp_cycle_identity(_decide(event with declared_max=None))
              if 엄격도(base) > 엄격도(d): return base          # 불변식 구조 보장
              목록 차단 and computed_risk ∈ {none, L0} and not phase 쓰기
                  → d["declaration_only"] = True, d["declared_risk"] = 선언 등급
```

- `_fast_cycle_state` 의 반환 모양은 `(state, error)` 를 유지하고, 종료 갈래는 error 를 `{"key", "detail"}` dict 로 돌려 호출부가 키를 고른다(문자열이면 지금처럼 `block_fast_cycle_audit`).
- `_closing_only_change` 는 phase glob 과 목록 경로를 같은 `cycle_binding.matches_glob`/정확 일치로 본다(대소문자 구분 — 표기 정규화는 후속 과제).

### `capture_declared_risk_core`

```text
text = 맨 앞 호스트 봉투 구간 제거(prompt); 닫히지 않은 봉투·빈 글이면 noop
explicit = 첫 펜스 모양 줄보다 앞의 줄 단위 ^[ \t]*SAGE-RISK:[ \t]*(L[0-3]|clear)[ \t]*$ 값들(중복 제거, 대소문자 정규화)
  1개 clear → clear(source=explicit)
  1개 Lx    → capture(level=Lx, source=explicit)
  2개 이상  → noop + 모호 안내
0개 → 기존 자연어 판정 그대로(source=natural)
```

### `messages` · i18n · runtime

- 포착·해제·모호 문구를 i18n(ko/en)으로 옮기고 해제 두 방법·표식 안내를 넣는다.
- `hint.declaration_only`(ko/en), `block_fast_cycle_terminal` 메시지·recovery(CYCLE_SHOW, CYCLE_CLEAR), `hint.risk_from_declaration` 에 표식 해제 병기.
- `hook_runtime._NON_OVERRIDABLE_BLOCKS` 에 `block_fast_cycle_terminal` 을 넣는다.
- `recovery.CODE_OF` 에 `block_fast_cycle_terminal → cycle.fast_terminal`, `RECOVERY["cycle.fast_terminal"] = (CYCLE_SHOW, CYCLE_CLEAR)` 를 더한다(`test_recovery_contract` 가 모든 키·코드의 실행 가능한 명령을 검사한다).
- 알림 렌더(`io_*.render_declared_*`)는 표시 언어를 고르기 위해 `root` 를 받는다. 오케스트레이터 한 곳에서만 부르므로 호출부도 함께 바꾼다.
- `capture_declared_risk_core.CONTRACT_VERSION` 은 올리지 않는다: 판정 action 집합(capture/clear/noop)은 그대로이고 상태에 선택 필드 `source` 만 늘어난다.

### 실패 처리 · 반대 방향 고정

| 입력 | 기대 | 지키는 것 |
|---|---|---|
| 완결 + 소스(선언 유무 무관) | `block_cycle_closed` | 완결 사이클 결속 금지 |
| 완결 + 요약 + 소스 | `block_cycle_closed` | 면제 술어 `all` |
| 완결 + 변경 0건 + 선언 | `block_cycle_closed` | 경로 추출 실패 ≠ 사면 |
| 선언 + 밖 + 안 혼합 / `<unresolved-path>` | 상향 유지 | 밖 제외는 확인된 밖 전부일 때만 |
| 선언 + 프로젝트 안 문서 + 완결/미결속 | 차단 유지 | 선언 세션 문서 게이트 |
| 완결 + 요약만 + 00 L2 + 선언 L3 | 통과(상향 없음) | 요약 단독은 선언 제외(결정 2, C1) |
| 완결 + 요약 + 06 문서 + 00 L2 + 선언 L3 | `block_cycle_risk_reconciliation` | 섞인 변경은 상향, 완결 면제는 완결 차단 하나뿐 |
| Fast close + 소스 | `block_cycle_closed` | 종료 갈래보다 완결 차단이 먼저 |
| Fast abort + 06 | `block_fast_cycle_terminal` | abort 사이클은 완결이 아님 |
| Fast plan 이 다른 stem run | `block_fast_cycle_audit` | 진짜 불일치는 override 불가 |
| 선언 L3 + 내용 키워드 L3 + plan 없음 | `block_l3_no_plan` | `declared_l3` 의미 불변 |
| feedback 마커 + 선언 | 차단, `declaration_only` 없음 | 위험도 무관 차단에 해제 오안내 금지 |
| 별칭 경로 + 선언 L3 | 상향 유지(확인 실패) | 「확인된 밖」 아닌 경로에 면제 없음 — 선언 없는 별칭 우회는 후속 과제 |
| 서브에이전트 봉투 속 「위험도 선언 해제」 | 상태 불변 | 조용한 해제 금지 |

### 알려진 한계

- 별칭·대소문자·짧은 이름으로 쓴 프로젝트 파일이 선언 없이도 위험 규칙을 비켜 가는 기존 구멍은 그대로다(후속 과제). 이번 수정은 그 경로에 선언 면제를 주지 않을 뿐이다.
- 선언 등급끼리의 단조성(높은 선언이 같거나 엄격)은 보장하지 않는다. 미선언 대비 불변식만 구조로 보장한다(결정 6).
- 작성자 인증 없음: 에이전트가 셸에서 같은 세션을 resume 해 프롬프트를 만들면 선언·해제할 수 있다(신뢰 경계 밖, 지금과 같음).
- codex 미확인: 압축 뒤 세션 id 유지, 서브에이전트 `apply_patch` 의 세션 id, codex 쪽 호스트 봉투 형식. 앞의 둘이 깨지면 선언이 적용되지 않는 방향(덜 막음)이고 지금 구현도 같다.
- 호스트 봉투 목록은 관측한 형식만 담는다. 새 봉투 형식은 지금처럼 자연어 규칙을 거친다.

## Phase 03 — 구현

- [x] File ownership assigned before source edits
- [x] Acceptance IDs mapped to implementation tasks
- [x] Verification command plan recorded

### 소유 파일 (단독 작업)

- `scripts/sage_harness/hooks/runtime/hook_runtime.py`(`_outside_confirmed`·게이트 오케스트레이터·capture 오케스트레이터·override 목록, `make_rel` 은 수정 안 함), `runtime/io_claude.py`·`runtime/io_codex.py`(알림 렌더)
- `scripts/sage_harness/hooks/pre_implementation_gate_core.py`, `scripts/sage_harness/hooks/capture_declared_risk_core.py`
- `scripts/sage_harness/hooks/runtime/messages.py`, `runtime/recovery.py`, `runtime/i18n/ko.py`, `runtime/i18n/en.py`
- `docs/sage_harness/hooks/pre-implementation-gate.md`, `docs/sage_harness/hooks/capture-declared-risk.md`, `docs/troubleshooting.md`, `docs/troubleshooting.en.md`, `docs/ARTIFACTS.md`, `docs/ARTIFACTS.en.md`
- 시험: `test_hook_runtime.py`, `test_cycle_stem_declaration.py`, `test_pre_implementation_gate.py`, `test_fast_cycle.py`, `test_capture_declared_risk.py`, `test_messages.py`, `test_hook_locale.py`, 필요 시 `test_hook_entry.py`·fixtures
- `docs/sage_harness/.manifest.json`, localization 인벤토리

### 작업 ↔ acceptance

| 작업 | Acceptance |
|---|---|
| `_outside_confirmed`·`rel` 기록 래퍼 | O1~O5 |
| 선언 상향 조건·`computed_risk`·file 채움 | D1~D4, H4 |
| `_closing_only_change`·스킬 대조 | C1~C3 |
| Fast 종료 갈래·새 키·override | F1~F5 |
| `declaration_only`·messages·i18n | H1~H3 |
| 봉투 제외·표식·알림 | S1~S5 |
| 불변식 성질 시험 | I1 |
| 문서·manifest | X1 |
| hook 경유 시험·Windows 실기(필수 아님) | X2, X3 |

### 검증 명령

- 관련 시험: `PYTHONPATH=$PWD python3 scripts/sage_harness/hooks/tests/<file>.py` (위 시험 파일 + `test_documentation`)
- 전체 스위트 로컬 1회: `bash scripts/sage_harness/hooks/tests/run-all.sh`
- `python -m sage validate --check --schema`
- 파이썬 버전 매트릭스는 CI(ubuntu·macos). Windows 는 X3 실기.

### 변경 파일

| 파일 | 변경 |
|---|---|
| `scripts/sage_harness/hooks/pre_implementation_gate_core.py` | `computed_risk`, `_declaration_exempt`(확인된 밖·마무리 산출물), `_CLOSING_ARTIFACTS`·`OUTSIDE_PROJECT`, `_closing_only_change`(완결 차단 면제), Fast 종료 run 갈래·`block_fast_cycle_terminal`, `decide()` 래퍼(미선언 재판정·`declaration_only`·`declared_risk`) |
| `scripts/sage_harness/hooks/runtime/hook_runtime.py` | `_outside_confirmed`, 게이트 오케스트레이터의 밖 경로 기록·`outside_confirmed`, override 불가 목록, capture 알림에 root 전달. `make_rel` 은 그대로 |
| `scripts/sage_harness/hooks/capture_declared_risk_core.py` | 맨 앞 호스트 봉투 제거, `SAGE-RISK:` 표식(첫 펜스 모양 줄보다 앞만, 위치 밖이면 상태 불변·위치 안내), 상태 `source` |
| `runtime/messages.py`·`i18n/ko.py`·`i18n/en.py`·`io_claude.py`·`io_codex.py` | 선언 원인 안내, 새 차단 키 문구·hint, capture 알림 i18n 이관(해제 두 방법·표식 안내) |
| `runtime/recovery.py` | `block_fast_cycle_terminal → cycle.fast_terminal` (`sage cycle show`·`clear`) |
| `docs/sage_harness/hooks/pre-implementation-gate.md`·`capture-declared-risk.md` | 선언 범위·종료 run·봉투·표식 계약 |
| `docs/troubleshooting.md`·`.en.md` | 표식·봉투·면제 설명, `cycle.fast_terminal` 절, 미러 해시 재스탬프 |
| `docs/sage_harness/.manifest.json` | spec·canonical·`hook_runtime_hash` 재스탬프(`sage generate --kind hook --root . --dest <임시> --write`) |
| `tests/test_declared_risk_scope.py`(신규 43건)·`test_messages.py`·`run-all.sh` | acceptance 시험, 알림 문구 기대값, 실행 목록 |

## Phase 04 — 분석

Status: COMPLETE — 구현·로컬 검증 완료, 05 6회차 APPROVED

### Acceptance Evidence

| ID | Status | Evidence |
|---|---|---|
| O1 | PASS | `TestOutsideConfirmation.test_real_outside_is_confirmed` |
| O2 | PASS | `test_aliases_of_the_project_are_not_confirmed`(루트 별칭·끊긴 링크·`링크/..`)·`test_case_variant_of_the_root_is_not_confirmed`. `/tmp`↔`/private/tmp` 는 scratchpad 시제품으로 확인(시험 임시 폴더가 이미 realpath 라 시험으로는 재현 안 함) |
| O3 | PASS | `test_hard_link_and_errors_are_not_confirmed` |
| O4 | PASS | `TestThroughTheHook.test_one_unconfirmed_path_keeps_the_declaration`(codex apply_patch 두 파일) |
| O5 | PASS | `test_make_rel_is_unchanged`, 기존 `test_hook_runtime` 150건 |
| D1·D2 | PASS | `TestOutsideProjectIsNotDeclaredWork.test_confirmed_outside_passes_on_closed_and_unbound_cycles` |
| D3 | PASS | `test_unconfirmed_outside_is_still_raised`·`test_mixed_or_empty_changes_are_raised`·`test_outside_with_l3_keyword_is_not_blocked_by_the_declaration` |
| D4 | PASS | `TestThroughTheHook.test_event_carries_the_confirmation`·`test_outside_and_summary_pass_on_both_hosts` |
| C1 | PASS | `test_summary_alone_passes_for_every_declaration_and_phase00_risk`(선언 3 × 00 3) |
| C2 | PASS | `test_summary_with_source_is_still_closed`·`test_summary_with_a_phase_document_skips_only_the_closed_block`·`test_no_changes_is_not_an_exemption` |
| C3 | PASS | `test_skill_writes_the_same_path` |
| C4 | PASS | `test_missing_phase_exemption_keeps_the_phase_only_rule` |
| F1 | PASS | `TestFastCycleAfterItsRunEnded.test_closed_run_allows_report_correction_and_summary`(실제 감사 기록기로 만든 run) |
| F2 | PASS | `test_aborted_run_gets_its_own_key`(문구·recovery code·06 없는 abort 의 소스) |
| F3 | PASS | `test_closed_run_on_an_incomplete_cycle_is_terminal`·`test_integrity_problems_stay_audit_failures`(chain None/False·clean·seq·ts·다른 stem)·`test_close_without_an_approved_review_does_not_pass` |
| F4 | PASS | `test_integrity_problems_stay_audit_failures` 의 다른 stem 경우 + 기존 `test_fast_cycle` 27건 |
| F5 | PASS | `test_both_fast_blocks_refuse_override`(활성 grant 모형 없이도 목록에서 거부) |
| F6 | PASS | `test_closed_run_allows_report_correction_and_summary` 의 선언 L2·L3 |
| H1 | PASS | `TestDeclarationOnlyBlockSaysSo.test_binding_and_closed_blocks_carry_the_declaration`(claude·codex × ko·en) |
| H2 | PASS | `test_not_attached_when_the_file_itself_is_risky_or_undeclared`·`test_unrelated_blocks_never_carry_it`·`test_reconciliation_keeps_its_own_hint` |
| H3 | PASS | `test_declared_l3_still_blocks_keyword_l3_without_a_plan` |
| H4 | PASS | `test_empty_file_label_is_filled` |
| S1 | PASS | 기존 `test_capture_declared_risk` 21건 무변경 통과 |
| S2 | PASS | `TestCapture.test_host_envelopes_are_not_the_user`(실측 형식·가짜 닫는 태그·미닫힘·`task-notification`·중간 태그) |
| S3 | PASS | `test_explicit_marker` |
| S4 | PASS | `test_notices_name_both_ways_out`, `test_messages.test_declared_capture` |
| S5 | PASS | `TestThroughTheHook` — `source` 없는 상태 파일로 두 host 판정 |
| I1 | PASS | `TestDeclarationNeverLoosens.test_matrix`(경로 7 × 사이클 상태 5 × 내용 2 × stem 2 × 확인 2 × 선언 4 × profile 3) |
| I2 | PASS | `test_known_counterexamples` |
| X1 | PASS | spec 2건·troubleshooting ko/en·manifest 재스탬프, `test_documentation`·`test_localization_inventory` 통과 |
| X2 | PASS | `TestThroughTheHook`(claude Write·codex apply_patch) |
| X3 | NOT TESTED | Windows 실기 미실행(필수 아님) — 06 잔여 위험 |

### 검증 결과

- 새 시험 40건. 소스 9개 파일만 수정 전으로 되돌리면(`git stash`, 시험 파일 유지) 38건 중 29건이 실패한다(당시 38건 기준).
- 관련 묶음 통과: `test_declared_risk_scope`·`test_cycle_stem_declaration`(44)·`test_fast_cycle`(27)·`test_pre_implementation_gate`(142)·`test_capture_declared_risk`(21)·`test_hook_runtime`(150)·`test_messages`·`test_hook_locale`·`test_documentation`·`test_recovery_contract`·`test_localization_inventory`·`test_cycle_state`·`test_diagnostics_contract`·`test_hook_entry`·`test_runner_inventory`.
- 전체 스위트(`run-all.sh`, 로컬 Python 3 한 버전): 1차 3,851건 중 실패 1건 — 새 시험 파일이 실행 목록에 없다는 `test_runner_inventory`(목록 추가로 해결). 05 3차 반영 뒤 3,893건 통과, **최종 소스(05 5차 반영 뒤) 3,894건 통과, 실패 0**. 새 시험은 최종 43건.
- 처음 관련 묶음에서 `test_messages.test_declared_capture` 1건 실패 — 포착 알림 문구를 의도대로 바꾼 것이라 기대값을 갱신.
- `python -m sage validate --check --schema`: WARN(exit 0, main 과 같음). localization 인벤토리 변화 없음.

### 설계와 달라진 점

- `declaration_only` 조건에 「미선언 판정이 차단이 아님」을 더했다. 미선언으로도 막히는 입력에 「선언 때문에만」이라고 말하면 거짓이다.
- 종료 run 통과 뒤 `warn_fast_cycle` 문구는 사유 앞에 「종료된」을 붙이는 것으로 했다(새 키를 만들지 않음).
- ARTIFACTS(ko/en)는 바꾸지 않았다. 선언 파일 설명(세션별 포착, 게이트가 참조)이 그대로 맞고, 새 상태 필드 `source` 는 기록용이다.
- 시험 fixture 보정 두 건: Fast run 의 reason 을 Plan 의 `Fast-Reason` 과 맞춤(어긋나면 무결성 검사가 정상적으로 차단), 「사이클 없음」 경우는 브랜치 결속 때문에 `block_cycle_risk_declaration` 이 나와 위험도 관문 차단 집합으로 판정.

### 05 1차 CHANGES_REQUESTED 뒤 재작업

| 지적 | 독립 확인 | 판단 | 조치 |
|---|---|---|---|
| [P1] 목록 안 코드 블록(`- ```text`)의 표식이 선언·해제로 잡힘 | 확인: 펜스 정규식이 줄 맨 앞 펜스만 봄. 붙여 넣은 문서에서 흔한 형태 | 허용 | 목록·인용 컨테이너 안 펜스도 펜스로 인식(넓게 잡을수록 상태를 덜 바꾸는 방향). 시험 3건 |
| [P2] 조회 오류가 「확인된 밖」이 됨 | 확인: `os.path.isfile` 이 `OSError` 를 삼켜 거짓 → 확인 성공. 기존 시험(`object()`)은 문자열 변환으로 예외를 증명하지 못했음 | 허용 | `os.stat` 직접 호출, 「없음」만 일반 파일 아님으로 보고 그 밖 오류는 확인 실패. `os.stat` 에 권한 오류를 주입하는 시험으로 교체 |
| [P3] 새 Fast 종료 사유·경고 접두사가 영어 출력에도 한국어 | 확인: core 가 한국어 문장을 사유에 조립 | 허용 | 사유를 `<run id> <결과>` 토큰으로, 경고 접두사도 결과 토큰으로. 영어 첫 줄에 한글이 없는지 시험 |

### 05 2차 CHANGES_REQUESTED 뒤 재작업

| 지적 | 독립 확인 | 판단 | 조치 |
|---|---|---|---|
| [P1] 1차 조치가 닫는 펜스에서도 컨테이너 접두사를 벗겨, 일반 블록 안 `> ``` `·`- ``` ` 가 블록을 닫고 뒤의 예시 표식(해제·하향)을 받음 | 재현 확인 — 1차 재작업이 만든 결함 | 허용 | 여는 펜스의 문맥(일반·목록·인용)을 기억하고 닫는 펜스는 그 문맥에서만 인정. 컨테이너 없는 4칸 들여쓰기 줄은 펜스가 아님. 반례 2건 + 정상 닫힘 2건 시험 |
| [P2] 경고 병합(`_select_pending_gate_decision`)이 첫 경고 필드만 복사해 waiver 사용 기록(`waiver_uses`)이 빠짐 — 변경 전 결함 | 코드 확인: 사실. HEAD 에도 같고 이번 변경과 무관(acceptance waiver 감사 계열) | **비허용(이번 범위 밖)** | 사용자 원칙(범위 과확장 금지)에 따라 이번에 고치지 않는다. 06 후속·별도 이슈 후보로 기록 |

### 05 3차 CHANGES_REQUESTED 뒤 재작업

| 지적 | 독립 확인 | 판단 | 조치 |
|---|---|---|---|
| [P1] 목록에서 연 펜스가 과도하게 들여 쓴 줄(상대 4칸, 코드 본문)에서 닫혀 예시 표식을 받음 | 재현 확인. 펜스 판정 반례가 1→2→3회차 연속 | 허용, **방식 변경** | 반례별 패치를 멈추고 계약을 단순화: 표식은 첫 펜스 모양 줄보다 앞에서만 인정. 닫는 펜스 판정 자체를 없앰. 반례 전부와 「맨 위 표식은 뒤 코드 블록과 무관하게 받음」·「펜스 뒤 자연어는 그대로」 시험 |
| [P2] 2차에서 비허용한 waiver 감사 누락이, 이번 변경이 새로 연 Fast 종료 통과 경로에서 도달 가능해짐(HEAD 는 같은 입력을 `block_fast_cycle_audit` 로 차단) | 논리 확인: 결함은 변경 전부터이나 도달 가능성은 이번 변경이 바꿈 — 2차의 「무관」 판단이 틀렸음 | **허용(2차 판단 정정)** | `_select_pending_gate_decision` 이 모든 경고의 `waiver_uses` 를 최종 판정에 모음. 병합 시험 |

### 05 4차 CHANGES_REQUESTED 뒤 재작업

3차 두 조치는 해소 확인(펜스 반례 4건 noop, Fast 종료 경로에서 waiver 사용·cycle stem 감사 각 1회, 감사 실패 시 차단).

| 지적 | 독립 확인 | 판단 | 조치 |
|---|---|---|---|
| [P1] 펜스 뒤 표식을 버린 뒤 자연어 규칙으로 넘어가, 코드 블록 안 예시 문장(「위험도 선언 해제」·「L1 로 진행했습니다」)이 선언을 해제·하향 | 재현 확인. 자연어가 코드 예시를 읽는 것은 HEAD 와 같지만, 표식을 쓴 사람의 의도를 버리고 자연어로 넘어가는 조합은 이번 계약이 만든 것 | 허용 | 프롬프트에 표식 줄이 있는데 인정 위치에 없으면 자연어로 넘어가지 않고 상태 불변 + 위치 안내(`risk_declaration_marker_position`, ko/en, 두 host). 해제·하향 반례와 어댑터 렌더 시험 |

### 05 5차 CHANGES_REQUESTED 뒤 재작업

4차 조치 해소 확인(해제·하향 반례 noop + 위치 안내, 두 host 에서 상태 불변).

| 지적 | 독립 확인 | 판단 | 조치 |
|---|---|---|---|
| [P2] APPROVED close 인데 승인 리뷰·loop 결속이 없는 기록을 `block_fast_cycle_terminal`(정상 종료)로 분류 — HEAD 는 `block_fast_cycle_audit` | 확인: 결정 8 은 무결성 이상을 audit 키로 남기라 했는데 구현이 종료 갈래로 보냄. 시험은 `block` 만 확인 | 허용 | APPROVED 결과에 승인 리뷰·loop 결속이 없으면 audit 오류. 시험이 키와 recovery code(`cycle.fast_audit_missing`)까지 확인 |

### 판정 요청 (05 에)

- `decide()` 래퍼: 두 번 판정해 엄격한 쪽을 고르는 것이 기존 감사 기록(waiver 사용, 선언 stem 감사, override)과 어긋나지 않는가. 래퍼는 core 안이라 기록은 최종 판정 하나에만 일어난다.
- `_outside_confirmed`: 「프로젝트 파일인데 확인된 밖」을 내는 입력이 있는가, 있다면 결과가 선언 없는 세션과 같은가.
- Fast 종료 run 갈래가 active run 과 같은 무결성 검사를 거치는가, 통과 조건이 「APPROVED 리뷰 뒤 close · 완결 · 문서만」으로 좁은가.
- 봉투 제거·표식 판정이 사람의 글을 지우거나 사람이 아닌 글을 선언으로 받는 경우가 있는가.

## Phase 05 — 교차 리뷰 (codex)

`plan_docs/05-expert-review/sage-1.3.2-declared-risk-scope.md` — 1~5차 CHANGES_REQUESTED, 6차 APPROVED.

## Phase 06

`plan_docs/06-report/sage-1.3.2-declared-risk-scope.md` — 후속 과제(1.3.3)와 잔여 위험.

## 리뷰 기록

### 자체 적대 리뷰

| 회차 | 관점 | 발견 | 조치 |
|---|---|---|---|
| 1 | 정확성(판정 흐름 대입) | 완결 면제만으로는 요약 파일이 reconciliation(00 L2 < 선언 L3)에 다시 막힌다 | 결정 2: 종료 산출물도 선언 상향 제외. C1 을 00 등급 × 선언 등급 행렬로 확장 |
| 1 | 정확성 | `_phase_only_change` 는 missing phases 면제에도 쓰인다. 전역 교체 시 요약이 섞인 쓰기가 phase 생성 면제를 받는다 | 교체는 완결 차단 호출부 한 곳만. C4 추가 |
| 1 | 정확성 | 봉투 「전체 일치」 판정은 봉투 뒤에 사람 글이 붙으면 실패해 원래 문제로 돌아간다 | 봉투 **구간 제거** 후 남은 글 판정. 0열 닫는 태그만 인정 |
| 1 | 정확성 | FAST-CONVERTED run 이 close 된 뒤에는 converted 목록이 비고 00 이 표준 문서라 이미 통과한다 | 변경 없음, 결정 8 은 FAST 모드만 대상 |
| 2 | 보안(우회 경로) | 표식을 코드 블록 안에서도 인정하면 문서·로그를 붙여 넣을 때 예시 줄로 선언·해제가 바뀐다 | 코드 블록 밖만 인정. 문서 예시는 블록·인라인으로 |
| 2 | 보안 | 프로젝트 파일의 하드 링크를 밖 경로로 쓰면 폴더 비교로 잡히지 않아 「확인된 밖」이 되고 선언 제외를 받는다 | 링크 수 2 이상 일반 파일은 `<unresolved-path>` |
| 2 | 보안 | 종료 산출물 제외를 악용해 L3 세션에서 요약 파일에 무엇을 쓰든 통과 | 수용: 요약은 실행되지 않는 SAGE 기록 파일이고 선언 없는 세션과 같은 결과. 섞인 변경은 상향 유지 |
| 2 | 보안 | `block_fast_cycle_terminal` override 로 abort 사이클에 소스 작업 | ~~해당 없음~~ **판단 오류**: abort 사이클은 완결이 아니어서 완결 차단이 없다. codex 2회차가 재현으로 지적 → override 불가로 정정 |
| 3 | API·문서 계약 | 새 차단 키는 recovery 코드·명령이 없으면 계약 시험이 깨진다 | `cycle.fast_terminal` 과 명령 추가를 설계에 명시 |
| 3 | API·문서 계약 | 알림 문구를 i18n 으로 옮기면 렌더 함수가 언어를 알아야 한다 | `root` 인자 추가, 호출부 한 곳 |
| 3 | API·문서 계약 | sage-team-fast 에는 요약 경로가 문자 그대로 없다 | C3 대조 대상을 sage-team 스킬·렌더로 한정 |
| 3 | API·문서 계약 | capture 상태 형식 변경이 기존 세션 파일을 깨뜨리는가 | 읽는 쪽은 `level` 만 사용, `source` 는 선택 필드. S5 로 고정 |

### codex 리뷰

판정 원칙: codex 지적을 그대로 받지 않는다. 각 지적을 코드 흐름과 직접 재현으로 확인해 허용/비허용을 정하고 근거를 남긴다.

| 회차 | 지적 | 독립 확인 | 판단 | 조치 |
|---|---|---|---|---|
| 1 | [High] Fast 종료 통과가 `(None, None)` 이면 선언 L2 의 06 수정이 `block_phase_incomplete` | **직접 재현**(`_fast_cycle_state` 를 `(None, None)` 으로 바꿔 끼움): 선언 L2 → `block_phase_incomplete` 01·02·03. 원인은 06 이 요구 목록 밖이라 missing phases 면제가 없고, Fast 의 01~03 은 composite 00 안에 있어 문서 선택이 실패함 | 허용 | 결정 8: `(state, None)` 반환, F6 |
| 1 | [High] 종료 run 검증이 `chain_ok is not False` 라 느슨함 | 코드 확인: 기존 `opener_run_issues` 는 `chain_ok is not True` 를 `chain_unverified` 로 거부(`fast_cycle_contract.py:182`). 종료 run 만 다른 기준을 쓸 근거가 없음. 무결성 손상을 override 가능 키로 내리면 기존 「감사 손상은 override 불가」 원칙과 충돌 | 허용 | 결정 8: active 와 같은 검증, 실패는 `block_fast_cycle_audit` |
| 1 | [High] 끊긴 심볼릭 링크가 밖으로 오판 | 논리 확인: 끊긴 링크는 `os.path.exists` 가 거짓이라 「존재 조상」 해석이 링크를 건너뜀. 쓰기는 링크를 따라 프로젝트 안에 파일을 만듦. 비현실적 경로이긴 하나 고치는 비용이 작고(전체 경로 `realpath`) 더 정확함 | 허용(심각도는 Medium 으로 낮춤 — 정상 흐름에서 생기기 어려움) | 결정 1 ② |
| 1 | [Medium] 대소문자 변형 경로가 glob 을 비켜 감 | 코드 확인: `_canon_relkey` 는 대소문자 보존, `matches_glob` 은 구분. 대소문자 무시 볼륨에서 `root/SRC/a.py` 는 문자열로도 안이라 지금도 `src/**` 를 비켜 감 — 사용자가 요청한 「기존 구멍」과 같은 계열 | 허용(범위 확장, 보고 대상) | 결정 1 ④, P6 |
| 1 | [Medium] `non_fenced_lines` 가 닫는 펜스 뒤 글자를 안 봄 | 코드 확인(`cycle_binding.py:24` 정규식이 펜스 문자열 시작만 매치). CommonMark 상 닫는 펜스에는 info 문자열이 올 수 없음 | 허용. 단 `cycle_binding` 수정은 Cycle-Stem 판정 동작을 바꾸므로 이번 범위 밖 | 결정 5: capture 전용 엄격 판정 |
| 1 | [Medium] 봉투 제거가 코드 블록 예시 태그로 사람 표식을 지움 | 논리 확인: 사람이 0열에 `<agent-message` 를 쓰는 드문 경우지만, 「호스트 봉투는 프롬프트 맨 앞」이라는 실측 사실로 규칙을 좁히면 이 경우와 원래 경우가 함께 풀림 | 허용 | 결정 5: 맨 앞 봉투만 |
| 1 | [Medium] 선언 상향이 `l0_l3_file` 경고를 지움 | **직접 재현**: 미선언 `warn_l0_l3_content` → 선언 L1 `ok`, L3 `ok_l3`. 이번 변경 전부터 있던 결함이고 불변식 I1 을 깸 | 허용, **사용자 보고 대상**(범위 확장) | 결정 6(3회차에 경고 보존 → 구조 보장으로 대체), I2 |
| 1 | [Medium] 안내에 쓸 선언 등급이 decision 에 없음 | 코드 확인: 차단 decision 의 `risk` 는 `PDCA`/`FAST`, `messages` 필드에 선언 등급 없음 | 허용 | 결정 4: `declared_risk` |
| 2 | [High] ABORTED + 소스 수정이 override 가능한 종료 차단으로 통과 | 논리 확인: abort 사이클은 `_cycle_closed` 거짓이라 완결 차단이 없고 Fast 검사가 먼저 반환 — 자체 리뷰 2회차의 「소스는 앞에서 막힌다」 판단이 틀렸음 | 허용 | 결정 8: 새 키 override 불가, F5 |
| 2 | [High] `abspath` 가 `..` 를 먼저 접어 링크 경유 경로를 밖으로 판정 | 논리 확인: POSIX 경로 해석에서 `..` 는 링크를 따른 뒤 적용 | 허용(Medium 으로 낮춤 — 정상 흐름에서 생기기 어려움) | 결정 1 ②, P7 |
| 2 | [High] 리뷰 없이 close 된 run 을 손으로 만들면 종료 통과 | 논리 확인: 상태 요약이 리뷰 수를 버려 검증 불가는 사실. 그러나 이 통과가 여는 것은 「완결 사이클의 phase 문서·요약 수정」뿐이고 표준 사이클은 감사 없이 이미 허용 — 실피해 없음. 또 손으로 쓴 감사는 신뢰 경계 밖 | 부분 허용(Low): 싼 검사(`review_result`·`loop_run_id`)만 추가. Done Criteria 문구 불일치는 허용 | 결정 8, F3, Done Criteria |
| 2 | [Medium] Windows 루트 안 짧은 이름이 복원되지 않음 | 논리 확인: ⑥이 대소문자만 다룸. 짧은 이름은 `samefile` 로 같은 파일이나 이름이 달라 glob 불일치 — 기존 구멍 계열 | 허용 | 결정 1 ④ 표기 맞춤(3회차에 링크 비추적으로 재작성), X3 |
| 2 | [Medium] 비단조 필수 phase profile 에서 불변식이 깨짐 | 논리 확인: 반례는 맞으나 원인은 설정. 「선언 없는 판정을 함께 돌려 더 엄격한 쪽」 같은 코드 해법은 판정 의미를 크게 바꿈 | 부분 허용 → **3회차에 판단 뒤집음**(단조 profile 반례). 불변식은 구조 보장, 등급 단조·profile 검증 강화만 후속 과제 | 결정 6 |
| 3 | [Medium] 단조 profile 에서도 phase 작성 면제 때문에 선언이 결핍 경고를 없앰 | 논리 확인: `_missing_pre_impl_phases` 면제는 「바꾸는 phase ⊆ 요구 목록」이면 결핍 검사를 통째로 건너뜀 — 선언이 요구 목록을 넓히면 이 면제가 새로 켜짐. 2회차의 「비단조 profile 만의 문제」 판단이 틀렸음 | 허용. 2회차 5번 판단도 뒤집음 | 결정 6: 미선언 판정과 비교해 엄격한 쪽(구조 보장), I1·I2 |
| 3 | [High] 프로젝트 안 링크를 대상 경로로 바꿔 `src` 보호·요약 면제를 우회 | 논리 확인: 위험 규칙은 경로 하나만 보고, 2회차 ⑥의 `realpath` 복원은 안 링크도 따라감 — 내 설계가 만든 결함 | 허용 | 결정 1 재작성: 루트에 닿을 때까지만 풀고 안에서는 링크를 따라가지 않음, P8 |
| 3 | [Low] 의사코드가 `abspath` 뒤 경로를 넘겨 P7 과 충돌 | 확인: 본문은 고쳤으나 의사코드·helper 인자는 그대로였음 | 허용 | 의사코드 `raw`/`folded` 분리 |

| 4 | [Medium] 래퍼 도입 뒤에도 단조 profile 에서 등급 단조(L1 warn, L2 ok)가 깨져 I1 계약과 어긋남 | 논리 확인: 래퍼는 미선언과만 비교. 원인은 3회차와 같은 phase 작성 면제(`_missing_pre_impl_phases`), 영향은 경고 하나 | 허용(문서 수정만): 등급 단조를 I1 에서 빼고 알려진 한계·후속 과제로. 코드는 늘리지 않음 | 결정 6, I1 |
| 4 | [Low] 실패 처리 표에 5.1판에서 뺀 「별칭 경로 L2 판정」 행과, 요약 단독이면 통과하는데 차단을 기대하는 reconciliation 행이 남음 | 확인: 두 행 모두 5판 기준 그대로 | 허용 | 실패 처리 표 정정 |

### 범위 조정 (5.1판, 사용자 피드백)

| 항목 | 5판 | 5.1판 | 이유 |
|---|---|---|---|
| 경로 표기 정규화(`make_rel` 재작성: 밖 경로 풀기·안 링크 비추적·대소문자·짧은 이름 복원·하드 링크) | 포함 | **후속 과제로 분리** | 사용자: 과도한 범위·수정 금지, 디렉터리 판정 로직은 과거 많은 리뷰 끝에 실패한 이력. 확인 결과 #23 해결에 필요하지 않음. codex 1~3회차의 경로 반례 5건 중 4건이 이 재작성에서 나옴 |
| 「확인된 밖」 판정 | `make_rel` 재작성 결과 | 선언 면제 판단에만 쓰는 보수 함수 하나(`realpath`+대소문자 무시 비교+하드 링크, 예외는 실패) | 틀려도 「지금 동작」 또는 「선언 없는 세션과 같음」뿐 — 반례가 나와도 느슨해지지 않음 |
| 선언 판정 ≥ 미선언 판정 구조 보장 | 포함 | **유지** | 경로 로직이 아니고 `decide()` 래퍼 몇 줄. 반례별 패치 대신 계약으로 닫는 방식(운영 진단 사이클 교훈) |
| 리뷰가 찾은 경로 반례(끊긴 링크, `..`, 대소문자, 짧은 이름, 안 링크) | 5판 결정 1 | 후속 정본으로 이관 | 버리지 않고 후속 설계의 시험 행렬로 쓴다 |
| P1~P8 acceptance | 있음 | O1~O5 로 대체 | 함수 범위에 맞춤 |
