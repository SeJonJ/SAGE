# [기본 계획] Phase 05 리뷰 규칙 수정 2단계 — 차단 기준 수렴·재작업 정책·변경 전 결함 분류

Cycle-Stem: `sage-phase05-review-rules-stage2`
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1
Status: COMPLETED — 03·04 완료, 05 APPROVED(4차), 06 작성(2026-10-03). 커밋은 사용자 결정

## 이 사이클의 성격

1단계(PR #15, main `1686271`)는 리뷰를 **기록하고, 세고, 상한에서 묻는** 장치를 넣었다. 리뷰를 덜 하게
만들지는 않았다. 이 사이클은 설계 정본의 **2단계**다. 리뷰가 끝나는 기준과 고치는 범위를 바꾼다.

feat-151 의 재리뷰 생존 61건 중 39건은 앞 재작업이 만든 사슬이었다. 그 출발점은 대부분 **비차단 지적
(P2·P3)을 고치려고 들인 새 장치**였다. 원래 diff 에서 재리뷰 중 처음 나온 지적에는 P0·P1 이 없었다.
크리티컬 3건은 모두 변경 전부터 있던 결함이었고, 범위 결정이 run 사이에 손으로 옮겨지다 사라졌다
(설계 정본 2.3~2.5).

2단계 규칙은 **리뷰를 덜 하게 만든다.** 기준이 틀리면 결함을 놓친다. 그래서 세 가지를 지킨다.

- **opt-in.** 기본값은 지금 동작(`converge_on: all`)이다. 프로젝트가 켜야 바뀐다(사용자 결정 1).
- **보이게 낮춘다.** 잔여를 안고 승인하면 그 승인은 보증 저하로 기록되고, 05·06 문서와 게이트·CI 가 그
  사실을 일반 승인과 구분한다.
- **사람이 정할 곳은 사람에게.** 크리티컬 P2 는 자동으로 고치지 않고 개발자에게 묻는다(사용자 결정 2).

이 규칙이 실제로 결함을 놓치지 않는지는 이 사이클이 아니라 다음 검증 사이클(설계 정본 6절)이 잰다.

## 0. 사전 지식

| 구분 | 근거 | 핵심 내용 |
|---|---|---|
| 설계 정본 | 위키 `SAGE - Phase05 리뷰 규칙 수정 설계 (26.10.01)` | 영구 SSOT. repo phase 문서와 다르면 위키가 우선한다. 이 사이클 범위는 7절 2단계(D4·D5·D6) |
| 1단계 기록 | 위키 `SAGE - Phase05 리뷰 규칙 1단계 구현·검증 (26.10.03)`, `plan_docs/*/sage-phase05-review-rules.md` | 사이드카 `sage.review-round/1` 에 `critical`·`preexisting`·`drop_reason` 칸이 이미 있다. 판정 함수는 `loop_audit.loop_verdict` 하나다 |
| 사용자 결정 1 | 2026-10-01 | D4 는 opt-in. 기본 `converge_on: all`, `/sage-profile-modify` 로 켠다. 검증 사이클 뒤 새 설치 기본값을 다시 판단 |
| 사용자 결정 2 | 2026-10-01 | 크리티컬 P2 여섯 개 그대로: 인증 없는 크래시, 노출·경로 탐색, 잘못된 콘텐츠 서빙, 배포 파손, 보안 설정 후퇴, 조용한 데이터 손상. 자동 수정하지 않고 개발자가 수정 또는 잔여 수용을 고른다 |
| 사용자 결정 5 | 2026-10-02 | Jev 는 규칙 개선(1~3단계·검증 사이클) 뒤 |
| codex 지적 (설계 10절·10.3절) | D4·D6 관련 P1 7건 | 승인 자격 검사 공통화, close 잠금 재대조, Fast 최소 라운드, 크리티컬 0 의 영수증 증명, D6 우회 조건, 통일 수렴식, `decide` 의 지적 내용 결속 |
| 선행 계약 | 1단계 「판정은 한 함수」 | `next`·`decide`(CLI·잠금 안)·재진입 문맥이 `loop_verdict` 를 쓴다. 새 판정도 이 함수에만 넣는다 |
| 선행 계약 | 보증 저하 표기(`_reduced_assurance_issues`) | 06←05 게이트와 CI authority 가 **같은 함수**로 05 의 네 표기를 감사와 대조한다. 지금은 `USER_AUTHORIZED_EARLY` 하나만 안다 |
| 저장소 예외 | `.sage/plan_interview.md` | 엔진 저장소에는 profile 이 없어 `sage cycle set` 을 실행하지 않는다. 같은 stem 문서를 직접 쓴다 |
| 작업공간 | 사용자 지시 | 브랜치 `feat/phase05-review-rules-stage2`. worktree·임시 프로젝트는 `sage_project_worktree/` 아래에만 |
| 검증 예산 | 사용자 지시 | 로컬 스위트는 한 파이썬 버전만. 매트릭스·무거운 E2E 는 CI 와 마지막 1회 |
| 데이터 정책 | 사용자 지시 | 회사 자료(ozsaas·eformsign)는 쓰지 않고 외부 LLM 에 보내지 않는다 |

## 1. 요약 (목표와 범위)

`converge_on: blocking` 을 켠 프로젝트에서, **차단 지적(P0·P1·판단 안 된 크리티컬 P2)이 0 이면 비차단
잔여를 기록하고 승인으로 닫는다.** 크리티컬 P2 는 지적마다 개발자에게 묻고 그 답을 지적 내용에 묶어 감사에
남긴다. 비차단 지적은 국소 수정만 하고, 새 장치가 필요하면 잔여로 둔다. 변경 전부터 있던 결함은 이번 변경이
그 결함을 건드렸을 때만 차단으로 다루고, 나머지는 장부로 보낸다.

범위 안:
- **D4** 차단 기준 수렴 — profile `converge_on: all|blocking`(기본 `all`)·크리티컬 P2 분류 목록. 통일
  수렴식(`blocking_open`·`accepted_residual`·`nonblocking`), `NEXT: ASK kind=CRITICAL_P2`, `decide --finding
  <id> --fix|--accept`, 새 close 사유 `CONVERGED_RESIDUAL`(보증 저하 `REDUCED_BY_POLICY`), 게이트·CI 의 보증
  저하 사유 집합, close 잠금 안 재대조, 진행 중 run 은 open 시점 설정을 따름.
- **Fast Cycle 최소 라운드** — Fast run 에 묶인 루프가 최소 라운드 전에 수렴하면 최소치까지 계속한다.
- **D5** 재작업 정책 — 비차단은 국소 수정만, 새 장치가 필요한 수정은 잔여(비차단) 또는 아키텍처 에스컬레이션
  (차단). 재작업이 닫는다고 주장한 지적을 다음 라운드가 확인해 사이드카에 남긴다.
- **D6** 변경 전 결함 — 지적에 변경 전 여부와 이번 변경의 노출 영향을 단다. 크리티컬급이고 노출이 바뀐
  경우만 차단, 나머지는 `out_of_scope_preexisting` 으로 탈락시켜 장부의 「알려진 변경 전 결함」으로 보낸다.

범위 밖:
- D7 재리뷰 범위 축소(3단계, 검증 사이클 뒤 채택).
- 검증 사이클(설계 정본 6절) 자체 — 이 사이클이 끝난 뒤 개인 프로젝트에서 한다.
- `converge_on` 새 설치 기본값 변경 — 검증 사이클 뒤 다시 판단(결정 1).
- run 예산·반복 상한의 open cfg 고정(1단계 F10, 기존 동작).
- 렌즈 수·반박자 수·첫 라운드 범위·피어 단독 P0/P1 보호.
- Jev 적용.

## 2. 영향도 분석 (중요)

**`all` 모드(기본)의 판정은 바뀌지 않아야 한다.** 이 사이클의 정책 변경은 모두 `converge_on: blocking`
에서만 켜진다. 예외는 하나다 — Fast run 에 묶인 루프의 최소 라운드 처리는 모드와 무관하게 적용한다. 지금은
Fast 최소 라운드보다 먼저 수렴하면 루프는 승인으로 닫히는데 `sage fast-cycle review` 가 거부해 진행이
막힌다(조용한 통과가 아니라 막힘). 이것을 고친다.

**커밋되는 감사 형식이 늘어난다.** 새 close 사유 `CONVERGED_RESIDUAL`, 새 `decision` 종류(`critical_p2`),
라운드 영수증의 크리티컬 지적 목록(id·주장 해시), open 레코드의 Fast 최소 라운드 스냅샷. 옛 기록은 소급
변환하지 않고, 옛 run 의 판정·무결성 결과는 바뀌지 않는다.

**06←05 게이트와 CI authority 의 판정이 바뀐다.** 지금은 `USER_AUTHORIZED_EARLY` 만 보증 저하로 안다.
`CONVERGED_RESIDUAL` 을 모르면 잔여를 안은 승인이 `STANDARD` 로 조용히 통과한다. 두 층이 같은 함수
(`_reduced_assurance_issues`)를 쓰므로 그 함수 하나를 사유 집합으로 넓힌다.

**`next` 의 출력 어휘가 늘어난다.** `NEXT: ASK kind=CRITICAL_P2` 와 `STOP result=APPROVED
reason=CONVERGED_RESIDUAL`. 소비자는 스킬·문서와 재진입 문맥이다.

**스킬 문구가 바뀐다.** `sage-review` 의 FIND·REFUTE·TRIAGE·REWORK·TERMINATION·라운드 기록 절, 프로토콜
문서, `sage-profile-modify`. 규칙은 `blocking` 일 때만 적용한다고 명시한다.

## 3. 기술과 리스크

| 리스크 | 대응 |
|---|---|
| 잔여 승인이 일반 승인처럼 06 으로 넘어간다 | `CONVERGED_RESIDUAL` 은 항상 보증 저하(`REDUCED_BY_POLICY`). 게이트·CI 가 같은 함수로 사유→표기를 대조한다. 05·06 이 표기를 빠뜨리면 막힌다 |
| 크리티컬 P2 결정이 다른 지적에 재사용된다(개수만 같고 내용이 바뀜) | 결정은 run·라운드·지적 id·주장 해시에 묶인다. 판정과 close 가 마지막 라운드의 크리티컬 목록과 다시 대조하고, 다르면 결정이 없는 것으로 보고 다시 묻는다 |
| 크리티컬 0 을 증명할 수 없는데 0 으로 읽는다 | `blocking` 수렴은 마지막 라운드에 사이드카 영수증이 있어야 한다. 없으면 「판정 불가 → 수렴 안 함」 |
| 미결 반박·미탐색 렌즈가 있는데 수렴한다 | `blocking` 수렴 조건에 미결 반박 0·미탐색 0 을 넣는다 |
| 진행 중 run 에서 정책을 바꿔 판정이 바뀐다 | `converge_on`·크리티컬 목록·Fast 최소 라운드는 open 레코드의 스냅샷만 읽는다 |
| close 와 라운드·결정이 경합해 옛 판정으로 승인된다 | `CONVERGED_RESIDUAL` close 는 잠금 안에서 `loop_verdict` 를 다시 계산해 같은 판정일 때만 쓴다 |
| 반박자가 변경 전 결함을 핑계로 차단 결함을 버린다 | 크리티컬급(P0·P1·크리티컬 P2)을 `out_of_scope_preexisting` 으로 버리려면 노출 영향이 `unchanged` 여야 한다. 엔진이 사이드카 기록 시 검사한다 |
| 비차단 잔여가 쌓여 실제 결함이 남는다 | 잔여는 장부와 05 `Residual-Findings` 에 남는다. 놓침은 검증 사이클의 감사 라운드가 잰다(이 사이클 범위 밖) |
| `all` 모드 판정이 바뀐다 | 새 판정 분기는 open cfg 가 `blocking` 일 때만 탄다. 기존 판정 회귀 테스트(768 조합 대조와 같은 방식)를 둔다 |

## 4. 최종 결론 및 UX 가이드

`converge_on: blocking` 을 켠 프로젝트의 사용자가 겪는 변화는 셋이다.

- **사소한 지적 때문에 리뷰가 끝나지 않는 일이 없다.** P0·P1 이 없고 크리티컬 P2 를 모두 정했으면, 남은
  P2·P3 는 잔여로 기록하고 승인한다. 05·06 문서에 「보증 저하(정책)」 네 표기를 적는다.
- **크리티컬 P2 는 질문으로 온다.** 루프가 멈추고 지적 원문·근거·예상 수정 범위를 보여 준다. 지적마다
  「고친다」 또는 「잔여로 받는다(이유)」를 고른다. 고르기 전에는 다음 라운드도 종료도 없다.
- **변경 전 결함은 따로 쌓인다.** 이번 변경과 무관한 기존 결함은 리뷰를 막지 않고 장부의 「알려진 변경 전
  결함」에 남아 별도 이슈 후보로 보고된다. 이번 변경이 그 결함을 새로 노출시켰으면 막는다.

켜지 않은 프로젝트는 지금과 같다. 다만 Fast run 에 묶인 루프가 Fast 최소 라운드 전에 수렴하면, 이제 승인
대신 최소치까지 한 라운드를 더 돈다.

## 5. Done Criteria

- [x] `pdca.review_loop.converge_on`(`all`|`blocking`, 기본 `all`)과 크리티컬 P2 분류 목록 키가 profile 검증·schema·템플릿·`/sage-profile-modify` 안내에 들어간다
- [x] 사이드카가 크리티컬 분류·변경 전 노출 영향·재작업 닫힘 확인을 담고, 감사 라운드 영수증에 살아남은 크리티컬 지적의 id·주장 해시 목록이 남는다
- [x] `blocking` run 에서 판단 안 된 크리티컬 P2 가 마지막 라운드에 있으면 `next` 가 `NEXT: ASK kind=CRITICAL_P2` 를 내고, 그 상태에서 `round`·close 가 CLI 와 잠금 안 양쪽에서 거부된다
- [x] `sage review-loop decide --finding <id> --fix|--accept` 가 run·라운드·지적 id·주장 해시에 묶인 결정을 감사에 남기고, 지적 내용이 바뀌면 그 결정은 적용되지 않는다
- [x] `blocking` run 의 판정이 통일 수렴식(`blocking_open == 0`, 미결 반박 0, 미탐색 0, 영수증 있음)을 따르고, 잔여가 있으면 `STOP APPROVED CONVERGED_RESIDUAL`, 영수증이 없으면 수렴으로 보지 않는다
- [x] `close --reason CONVERGED_RESIDUAL` 이 `blocking` run 에서만, 판정이 같을 때만(잠금 안 재계산) 기록되고, 감사 close 에 보증 저하 `REDUCED_BY_POLICY`·잔여 영수증·수용한 크리티컬 결정이 남는다. 승인 자격 검사(감사 무결성·Done Criteria·acceptance)가 조기 종료와 같게 적용된다
- [x] 06←05 게이트와 CI authority 가 `CONVERGED_RESIDUAL` 을 보증 저하로 대조한다 — 05·06 의 네 표기가 없거나 다르면 막고, 표기만 있고 감사가 아니면 자칭으로 막는다
- [x] 종료 검산이 `CONVERGED_RESIDUAL` 을 사실과 대조한다(`all` run·판정 불일치는 mismatch)
- [x] `all`(기본) run 과 옛 감사 기록의 `next`·close·검산·게이트·CI 결과가 바뀌지 않는다(Fast 최소 라운드 제외)
- [x] Fast run 에 묶인 루프는 open 시점에 Fast 최소 라운드를 기록하고, 그보다 적은 라운드에서 수렴하면 `next` 가 `CONTINUE` 를 낸다
- [x] 조기 종료는 `ASK CRITICAL_P2` 에서 거부되고, 장부가 수용한 크리티컬 잔여·알려진 변경 전 결함·닫히지 않은 재작업을 따로 보여 준다
- [x] `blocking` run 에서 크리티컬급 지적을 `out_of_scope_preexisting` 으로 탈락시키려면 노출 영향이 `unchanged` 여야 하고, 아니면 라운드 기록이 거부된다
- [x] `sage-review` 스킬·`review-protocol.md` 가 `blocking` 모드의 FIND(크리티컬·변경 전 표시)·REFUTE(탈락 사유)·TRIAGE·REWORK(국소 수정)·`ASK CRITICAL_P2` 처리·`CONVERGED_RESIDUAL` close 와 05 표기를 설명하고, 사용자 문서(한·영)가 새 키·판정·명령을 설명한다
- [x] `show`·대시보드·감사 보기·재진입 문맥이 `CONVERGED_RESIDUAL` 과 `ASK CRITICAL_P2` 를 보여 준다
- [x] i18n 한·영 catalog 키 동등성과 `validate --check --schema` drift 0 을 유지하고, hook 회귀 전체가 한 파이썬 버전에서 통과한다

## 6. Done Criteria Revision Log

(Revision 1 — 최초 작성, 2026-10-03)
