# [기본 계획] Phase 05 리뷰 규칙 수정 1단계 — 라운드 기록·사이클 상한·상한 잔여 승인·경계 압축

Cycle-Stem: `sage-phase05-review-rules`
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1
Status: COMPLETED — 03·04 완료, 05 APPROVED(codex 3차), 06 보고 작성(완료 기준 21/21), Windows 실기 PASS(10-03). 커밋·릴리즈는 사용자 결정 대기

## 이 사이클의 성격

Phase 05 리뷰 비용이 커진 주원인은 리뷰어 수가 아니라 **종료 규칙**이었다. feat-151 은 7 run·17 라운드·
64.0M(입력 환산)을 썼다. 반복 상한에 닿으면 BLOCKED 로 닫혀 새 run 을 열었고, 그때마다 카운터가 0 으로
돌아갔다. 판단에 필요한 정보(지적 원문·반박 사유·수정 diff)는 어디에도 남지 않았다.

이 사이클은 설계 정본의 **1단계**만 구현한다. 1단계는 품질 위험이 없는 변경이다. 리뷰가 무엇을 찾고
버렸는지 기록하고, 사이클 단위로 라운드를 세고, 상한에서 사람에게 묻고, Phase 05 진입 전에 컨텍스트를
줄인다. **리뷰를 덜 하게 만드는 규칙(D4~D7)은 넣지 않는다.** 그 규칙들은 이 사이클이 남기는 기록으로
검증한 뒤 2·3단계에서 다룬다.

## 0. 사전 지식

| 구분 | 근거 | 핵심 내용 |
|---|---|---|
| 설계 정본 | 위키 `SAGE - Phase05 리뷰 규칙 수정 설계 (26.10.01)` | 영구 SSOT. repo phase 문서와 다르면 위키가 우선한다. 이 사이클 범위는 7절 1단계(D1·D2·D3·D8) |
| 근거 자료 | 위키 `SAGE - Jev 재측정 개인 프로젝트 (26.09.30)` | feat-151·bug-145·GMA 실측. 개인 프로젝트 자료만 쓴다 |
| 사용자 결정 1 | 2026-10-01 | D4 차단 기준 수렴은 opt-in. **이 사이클 범위 밖**(2단계) |
| 사용자 결정 2 | 2026-10-01 | 크리티컬 P2 여섯 개는 자동 수정 없이 개발자 판단. **이 사이클 범위 밖**(2단계, `ASK CRITICAL_P2`) |
| 사용자 결정 3 | 2026-10-01 | Phase 05 는 새 세션이 아니라 **같은 세션 + 압축**. 정본은 phase 문서 |
| 사용자 결정 4 | 2026-10-01 | 사이클 라운드 상한 **L3 5 · L2 3**. 넘으면 멈추지 않고 사용자에게 묻는다 |
| 사용자 결정 5 | 2026-10-02 | Jev 적용은 규칙 개선(1~3단계·검증 사이클) 뒤 다시 진행. 이 사이클의 사이드카가 그 자료다 |
| codex 확인 | 설계 10~10.3절 (세션 `01a0f5b1`·`01a0f7dc`, 실기 `01a0f79d`) | 두 호스트 모두 에이전트가 압축을 못 한다. 압축 뒤 `SessionStart`(source `compact`)가 `additionalContext` 로 문맥을 넣는다. `PostCompact` 는 못 넣는다. codex 는 미신뢰 훅을 실행하지 않는다 |
| 선행 계약 | `sage/commands/review_loop.py`·`scripts/sage_harness/hooks/runtime/loop_audit.py` | 감사는 run 별 hash-chain append-only. 쓰기 전 CLI 검사 + 잠금 안 재검사 두 겹이다. 이 구조를 그대로 따른다 |
| 선행 계약 | hook 트리의 엔진 비의존 (`sage-install-ownership-boundary`) | 설치본 hook runtime 은 `sage` 패키지 없이 돈다. SessionStart 재진입 문맥은 엔진을 import 하지 않는다 |
| 저장소 예외 | `.sage/plan_interview.md` | 엔진 저장소에는 profile 이 없어 `sage cycle set` 을 실행하지 않는다. 같은 stem 문서를 직접 쓴다 |
| 작업공간 정책 | 사용자 지시 | 브랜치 `feat/phase05-review-rules`. worktree·임시 소비 프로젝트는 `sage_project_worktree/` 아래에만 |
| 검증 예산 | 사용자 지시 | 로컬 스위트는 한 파이썬 버전만. 매트릭스·무거운 E2E 는 CI 와 마지막 1회 |
| 데이터 정책 | 사용자 지시 | 회사 자료(ozsaas·eformsign)는 쓰지 않고 외부 LLM 에 보내지 않는다 |

## 1. 요약 (목표와 범위)

리뷰 루프가 **무엇을 찾고 버리고 고쳤는지 파일로 남기고**, **사이클 단위로 라운드를 세어 상한에서
사람에게 묻고**, **상한에서 비차단 잔여만 남았으면 사용자 승인으로 닫게** 한다. Phase 05 진입 전에는
사용자 `/compact` 한 번을 안내하고, 압축 직후 훅이 문서 재독을 지시한다.

범위 안:
- **D1** 라운드 사이드카 — `sage review-loop round --findings-file`. 지적 원문·출처·반박 사유·처분·수정
  diff·사용량을 `.sage/review-rounds/` 에 저장하고, 개수·심각도 영수증을 사이드카에서 산출한다.
  승인 판단에 쓰는 값과 사이드카 해시는 감사 라운드 기록에 함께 남긴다.
- **D2** 사이클 단위 집계와 `ASK CYCLE_CAP` — run 의 사이클 결속을 필수로 하고, `next`·`show` 가 같은
  사이클 run 들을 합친다. 새 키 `pdca.review_loop.max_cycle_rounds`(기본 L3 5 · L2 3). 상한에서 `next` 는
  `ASK` 를 내고, 사용자 결정은 `sage review-loop decide` 로 감사에 남는다. run 간 이월 장부를 만든다.
- **D3** 상한 잔여 승인 — 기존 조기 종료(`USER_AUTHORIZED_EARLY`)를 `STOP BUDGET_ITER` 와 `ASK CYCLE_CAP`
  상태에서도 허용한다. 승인 화면에 잔여 지적 목록을 보여 준다.
- **D8** Phase 05 경계 압축 — `sage-team` 04 경계 안내, 기존 `session-start-snapshot` 훅의 `compact`
  분기(재진입 문맥 주입), 대화 결정을 나온 자리에서 문서에 적는 스킬 규칙.

범위 밖:
- D4 차단 기준 수렴·`ASK CRITICAL_P2`·`CONVERGED_RESIDUAL`·`REDUCED_BY_POLICY`(2단계).
- D5 재작업 정책, D6 변경 전 결함 분류·탈락 사유의 판정 규칙(2단계). 단, 사이드카 스키마에는 그 값을
  담을 칸을 둔다.
- D7 검증 라운드 범위 축소(3단계, 검증 뒤 채택).
- 렌즈 수·반박자 수·첫 라운드 범위·피어 단독 P0/P1 보호·06←05 게이트 판정식·Fast Cycle 최소 라운드.
- Jev 적용(4단계).
- 렌즈별 호스트 사용량 자동 수집(트랜스크립트 파싱) — 사이드카에 칸만 둔다.

## 2. 영향도 분석 (중요)

**커밋되는 감사 형식이 바뀐다.** `.sage/loop_audit.jsonl` 은 동료·CI 가 clone 뒤에 읽는 기록이다. 새 이벤트
(`decision`), 새 BLOCKED 사유(`CYCLE_CAP`), 라운드 기록의 새 필드(사이드카 해시·영수증 확장)가 들어간다.
옛 기록은 소급 변환하지 않는다. 옛 run 의 판정·무결성 결과가 바뀌면 안 된다.

**`open` 이 거부할 수 있게 된다.** 지금은 `--cycle-stem` 없이도 열린다. 이제 stem 을 해석하지 못하면 열기를 거부한다.
선언된 사이클이 없는 프로젝트에서 바로 막히므로, 거부 문구가 고칠 방법(`sage cycle set` 또는
`--cycle-stem`)을 말해야 한다.

**`next` 의 출력 어휘가 늘어난다.** `NEXT: ASK kind=CYCLE_CAP` 은 스킬이 처음 보는 줄이다. 소비자는 스킬
문서와 사용자 문서뿐이다(엔진 코드는 `next` 를 파싱하지 않는다 — 전수 확인). 스킬이 이 줄을 모르면 라운드를
계속 열려다 `round` 거부를 받는다. 조용히 지나가지 않는다.

**두 호스트의 SessionStart 출력이 바뀐다.** 지금은 SessionStart 에서 문맥을 넣지 않는다. 압축 직후에만 짧은
JSON 을 stdout 에 낸다. 다른 source(startup·resume·clear)의 동작은 그대로다. 06 baseline write-once 도
그대로다.

**스킬 문구가 바뀐다.** `sage-review`·`sage-team` 렌더(Claude·codex 공용 템플릿)와 프로토콜 문서가 바뀐다.

## 3. 기술과 리스크

| 리스크 | 대응 |
|---|---|
| 사이드카와 감사가 어긋난다(파일 교체·삭제) | 감사 라운드 기록에 사이드카 sha256 과 승인 판단 값을 함께 적는다. 판정은 감사 값을 정본으로 쓰고, 사이드카는 해시가 맞을 때만 읽는다 |
| 사이드카는 git 무시라 CI 가 못 본다 | 승인에 쓰는 값(심각도 영수증·미탐색 수·사이드카 해시)을 감사에 적는다. CI 는 감사만 읽는다 |
| 사이클 상한이 우회된다(결속 없는 run) | `open` 이 stem 을 `resolve_stem`(env > 파일)으로 채우고, 없으면 거부한다. 옛 무결속 run 은 따로 보여 주고 집계하지 않는다 |
| `ASK` 를 무시하고 라운드를 연다 | `round` 가 CLI 와 잠금 안에서 모두 거부한다. 판정 함수 하나를 CLI·잠금 검사·훅이 같이 쓴다 |
| STOP 상태 조기 종료가 BLOCKED 를 덮는 통로가 된다 | 허용은 `BUDGET_ITER` STOP 과 `ASK CYCLE_CAP` 둘뿐이다. `BUDGET_TOK`·`BLOCKED_ARCH` 는 지금처럼 거부한다. `severity_block` 0·acceptance·Done Criteria·감사 무결성 검사는 그대로다 |
| 압축 뒤 엉뚱한 사이클 briefing 을 넣는다 | 훅이 게이트와 같은 해석기로 stem 을 정한다. env·파일·열린 run 의 stem 이 다르면 고르지 않고 사용자 확인을 요청한다 |
| 훅이 엔진을 import 해 설치본에서 죽는다 | 재진입 문맥은 runtime 모듈(`cycle_state`·`loop_audit`)과 파일 목록만 쓴다. `restore` 는 훅이 실행하지 않고 에이전트에게 명령을 알려 준다 |
| 훅 실패가 조용히 지나간다 | 읽기 실패·모호함은 그 사유를 문맥에 넣는다. 아무것도 넣지 않고 넘어가지 않는다 |
| codex 훅 미신뢰 | 주입이 없다. 04 경계 안내 문구가 대체 경로(`/sage-team` 재호출)를 함께 말한다 |
| 문맥 크기 한도(codex 핸들러당 약 2,500 토큰) | 주입 글은 경로·상태만 담고 2KB 를 넘지 않는다. 본문은 briefing 파일에 있다 |

## 4. 최종 결론 및 UX 가이드

사용자가 겪는 변화는 셋이다.

- **상한에서 질문을 받는다.** 사이클 라운드가 L3 5(L2 3)에 닿으면 루프가 멈추고 세 가지를 묻는다.
  계속(상한을 몇 라운드 늘릴지와 이유), 잔여 승인(남는 지적 목록을 보고 승인), 멈춤. 지금처럼 새 run 을
  열어 카운터를 0 으로 되돌리는 일은 없다.
- **반복 상한에서 막히지 않는다.** run 의 반복 상한에 닿았는데 P0·P1 이 남지 않았으면, 새 run 대신
  잔여 목록을 보고 승인으로 닫을 수 있다(조기 종료 opt-in 프로젝트). 05 문서의 네 표기는 지금과 같다.
- **Phase 05 전에 한 번 입력한다.** 04 가 끝나면 「`/compact` 입력 뒤 `계속`(건너뛰려면 바로 `계속`)」
  안내가 나온다. 건너뛰어도 진행은 같다. 압축 직후에는 훅이 사이클·phase·루프 상태와 briefing 경로를
  넣어 주고, 에이전트는 문서를 다시 읽고 이어 간다.

리뷰가 남기는 기록은 사람이 보지 않아도 되는 로컬 산출물이다. 다만 다음 단계 규칙(D4~D7)과 Jev 재측정이
이 기록을 근거로 판단한다.

## 5. Done Criteria

- [x] `sage review-loop round --findings-file` 가 사이드카 스키마를 검사해 `.sage/review-rounds/` 에 저장하고, 감사 라운드 기록에 사이드카 sha256·경로와 승인 판단 값(심각도 영수증·미탐색 수)을 남긴다
- [x] 사이드카가 있으면 found·survived·accepted·arch·심각도 영수증을 사이드카에서 산출하고, 손으로 준 값과 다르면 아무것도 쓰지 않고 거부한다
- [x] 라운드마다 작업 트리 식별자를 기록하고, 직전 라운드 대비 delta 를 `<n>.patch` 로 저장한다(git 이 없거나 실패하면 그 사유를 기록한다)
- [x] 사이드카 없는 라운드는 지금처럼 기록되고 `sidecar: absent` 가 남는다. 옛 감사 기록의 판정·무결성 결과가 바뀌지 않는다
- [x] `open` 이 `--cycle-stem` 이 없으면 `resolve_stem`(env > 파일)으로 채우고, 그래도 없으면 거부하며 고칠 방법을 말한다
- [x] `next`·`show` 가 같은 사이클의 run 들을 합쳐 사이클 라운드 수·누적 사용량을 보여 주고, 사이클 미결속 run 은 따로 표시한다
- [x] `pdca.review_loop.max_cycle_rounds` 가 profile 검증·schema·템플릿에 들어가고, 사이클 라운드가 상한에 닿으면(미수렴) `next` 가 `NEXT: ASK kind=CYCLE_CAP` 을 낸다
- [x] `ASK` 상태에서 `round` 가 CLI 와 잠금 안 양쪽에서 거부된다
- [x] `sage review-loop decide --cycle continue --extend N` 이 결정(누가·무엇을·왜)을 감사 `decision` 기록으로 남기고 상한을 늘린다. 무결성 검사가 `decision` 의 orphan·종료 뒤 기록을 잡는다
- [x] 사이클 상한에서 멈추기로 하면 `close --result BLOCKED --reason CYCLE_CAP` 로 닫히고, 종료 검산이 이 사유를 사실과 대조한다
- [x] 이월 장부가 사이클별로 생성되고(잔여·결정·범위 밖·알려진 변경 전 결함·탈락 사유), 패킷의 「결정·잔여」 절을 장부에서 출력하는 명령이 있다
- [x] 조기 종료가 `STOP BUDGET_ITER` 와 `ASK CYCLE_CAP` 에서 허용되고 `BUDGET_TOK`·`BLOCKED_ARCH` 에서는 거부된다. 기존 조기 종료 검사(사유·승인자·확인 토큰·최소 라운드·`severity_block`·acceptance·Done Criteria·감사 무결성)는 그대로다
- [x] 조기 종료 안내가 실제 판정(`CONTINUE`·`BUDGET_ITER`·`CYCLE_CAP`)과 사이드카의 잔여 지적 목록을 보여 준다
- [x] `session-start-snapshot` 이 source `compact` 일 때 두 호스트 형식으로 2KB 이하 재진입 문맥을 낸다. 다른 source 의 동작과 06 baseline write-once 는 바뀌지 않는다
- [x] 재진입 문맥의 사이클이 모호하면(env·파일·열린 run 불일치) 고르지 않고 값들을 적어 확인을 요청하며, 읽기 실패는 사유를 넣는다
- [x] 재진입 문맥 모듈이 엔진(`sage` 패키지) 없이 import·실행된다
- [x] `sage-team` 04 경계 안내(압축·건너뛰기·훅 미신뢰 대체 경로)와 「대화 결정은 나온 자리에서 phase 문서에 적는다」 규칙이 스킬에 들어간다
- [x] `sage-review` 스킬·`review-protocol.md`·사용자 문서(한·영)가 사이드카·`ASK`·`decide`·`CYCLE_CAP`·STOP 상태 조기 종료를 설명한다
- [x] i18n 한·영 catalog 키 동등성과 `validate --check --schema` drift 0 을 유지한다
- [x] hook 회귀 전체가 한 파이썬 버전에서 통과한다
- [x] 1단계 구현 뒤 양 호스트에서 실제 `/compact` 로 재진입 문맥 주입을 확인한다(설계 10.3 남은 확인)

## 6. Done Criteria Revision Log

(Revision 1 — 최초 작성, 2026-10-02)
