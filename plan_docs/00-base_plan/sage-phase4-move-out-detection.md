# [Base Plan] SAGE 10-j-5 Phase04 move-out 오탐 제거

Cycle-Stem: `sage-phase4-move-out-detection`
Risk Level: L3
Status: IMPLEMENTED (2026-08-04, 미커밋 · 독립 리뷰 PASS)

## 1. Context

`v0.9.78` 을 ChatForYou 에 역적용한 뒤 Phase-05 2차 cross-model 리뷰가 두 건을 제기했다(J-10·J-11).
착수 전 코드로 재검증한 결과는 다음과 같다.

**J-10 수용 — 단 회귀가 아니라 기존 오탐이다.** `extract_phase4_changes` 는 Move 시 목적지와 원본
update 를 모두 남긴다. Phase 04 문서를 `04-analyze` **밖으로** 빼내는 작업이 Phase 04 작성으로
오인돼 차단된다(실측: 원본 stem 의 base plan 누락으로 exit 2). 리뷰는 "J-8 수정이 만든 회귀"라
했으나 **구버전 추출기도 같은 입력에서 `04-analyze` update 를 남겼다** — v0.9.78 이전부터 있던
오탐을 J-8 수정이 닫지 못한 것이다. 교훈은 유효하다: 지적된 입력(move-in 미탐)만 닫고 그 입력이
속한 부류(move 의 양방향)를 닫지 않았다.

**J-11 기각.** `plan_reads` optional 은 10-i 가 확정한 공개 계약이고(base plan §6.3, cli-reference
한영), 필수화는 `return {"globs": []}` 한 줄로 충족되므로 아무것도 닫지 못하면서 계약만 깬다 —
이것이 결정적 논거다. 10-j-1 리뷰에서 같은 지적이 나와 이미 기각·문서화된 항목의 재상정이다.

기각 초안의 세 번째 논거("빈 snapshot → 증거 부재로 차단")는 **독립 리뷰가 실측으로 반증했다** —
정본 체크리스트 core 조차 빈 snapshot 에서 warn/exit 0 으로 통과한다. 부재의 안전 방향은
framework 가 아니라 **저작자의 decide 설계**에 달렸고, 그것은 plan_reads 필수화로도 달라지지
않는다(빈 globs 가 같은 빈 snapshot 을 만든다). 논거에서 제외하되 결론은 (계약·무효성) 두 논거로
유지된다.

## 2. Goal

- codex `apply_patch` 로 문서를 `04-analyze` 밖으로 이동하는 작업이 Phase 04 게이트를 트리거하지
  않는다.
- 이동으로 문서가 `04-analyze` 안에 **생기는** 경우(밖→안, 안→안)는 계속 트리거한다.
- 등록된 project hook 의 `event.changes` 도 같은 의미론을 따른다 — 문서가 실제로 생기는 경로만.

## 3. Non-Goals

- `extract_changes`(pre-implementation-gate)와 `extract_logged_changes`(post-tool-logger)의 원본
  경로 유지. 위험 분류와 로깅은 "건드린 모든 경로"가 맞다 — 이동으로 빠져나가는 파일도 그 파일을
  건드린 것이다. Phase04 의 "문서가 생기는 경로"와 의미가 다르며, 이 차이를 문서로 고정한다.
- J-11 (`plan_reads` 필수화) — 기각 사유는 §1.
- claude 쪽 변경 — 이동 연산이 없다.

## 4. Invariants

- **차단을 추가·수정하면 반대 방향 비차단을 같은 커밋에서 회귀로 고정한다**(정본 설계 메모 규칙 1).
  move-in 트리거 ↔ move-out 비트리거가 짝으로 존재해야 한다.
- 이동이 아닌 Add/Update/Delete 의 판정은 바이트 단위로 불변이다.

## 5. Architecture

`extract_phase4_changes` 를 라인 스캔에서 **파일 블록 단위** 파싱으로 바꾼다. apply_patch 에서
Move 는 직전 `Update File` 블록의 속성이다 — 문서는 목적지에만 생기고 원본 경로에는 아무것도
쓰이지 않는다. 따라서 Move 를 만나면 그 블록의 변경을 원본이 아니라 **목적지 하나로 대체**한다.

```text
*** Update File: A + *** Move to: B   →  [{B, move}]           (원본 A 는 기록하지 않음)
*** Add|Update File: A (Move 없음)     →  [{A, add|update}]
*** Delete File: A                     →  기록 없음 + 블록 경계 리셋
```

`Delete File` 은 블록 경계를 리셋한다 — 문법상 Move 는 Update 뒤에만 오지만, 잘못 붙은 Move 가
직전 블록을 오염시키지 않게 한다.

## 6. Failure Matrix and Required Regression Teeth

- move-out(04→밖): 게이트 비트리거. **이 사이클의 기준 회귀.**
- move-in(밖→04): 계속 트리거 — 기존 회귀 유지.
- move 내부(04→04): 목적지가 04 이므로 트리거.
- 원본 update 가 target glob 밖이고 목적지가 안인 경우와 그 반대를 대칭으로 단언한다.
- project hook `event.changes` 에 move 원본이 실리지 않고 목적지만 실린다.
- 추출기 3종의 의도된 차이를 회귀로 고정한다 — phase4 는 "생기는 경로", 나머지 둘은 "건드린 경로".
- mutation: 블록 대체 제거(원본 잔존), Delete 리셋 제거, move-out 비트리거 단언 제거가 각각 죽는다.

## 7. Acceptance

- 실측 입력(`Update File: plan_docs/04-analyze/x.md` + `Move to: docs/x.md`)이 exit 0.
- move-in 차단·Delete 제외·비이동 판정 불변.
- none/Claude/Codex 공식 suite, all-kind validate, wheel smoke, `git diff --check`, mutation 통과.
- L3 이므로 Phase 06 전 독립 리뷰. 리뷰는 양방향(move-in/move-out)을 실제 adapter 로 재현해야 한다.

## 8. Implementation Result (2026-08-04)

`extract_phase4_changes` 를 파일 블록 단위 파싱으로 바꿨다. Move 는 직전 Add|Update 블록을
목적지로 대체하고, Delete 는 블록 경계를 리셋한다. 부류 8케이스(move-out/in/내부, 단순
add/update/delete, 고아 Move, 다중 블록)를 착수 시점에 전수 확인했다.

새 의미론에 맞춰 기존 테스트 2건을 갱신했다 — lifecycle 의 이동 테스트는 원본 미포함을 단언하고,
추출기 parity 테스트는 **의도된 분화**(phase4=생기는 경로, 위험/로깅=건드린 경로)를 회귀로
고정한다. move-out 비트리거 e2e 를 move-in 차단의 짝으로 추가했다(Invariant 규칙 1).

변이 3종(블록 대체 제거·Delete 리셋 제거·Move 수집 제거)이 전부 정조준으로 죽었다. 초안에서 변이
하나가 같은 정규식을 가진 `extract_changes` 를 잘못 변이해 엉뚱한 테스트로 죽었는데, 문맥을 포함해
재조준했다.

### 독립 리뷰 (PASS · MINOR 2건)

리뷰어가 양방향을 실제 adapter 로 재현했고(6케이스 표), 블록 파서를 8가지 방식으로 공격해
**모든 비정상 입력이 차단 쪽으로 해소됨**을 확인했다(content 스푸핑 `+*** Move to:` 는 `^***`
앵커로 미매치). manifest 해시 3종·spec hash·doc-source 스탬프도 재계산 대조했다.

- **MINOR-1 수용**: `event.changes` 의미 축소가 contract_version 무변경으로 진행됐다.
  등록 project hook 0개(리뷰어가 manifest 로 확인)라 마이그레이션 대상은 없고, 원본 소멸은
  Delete 미포함이라는 기존 계약과 오히려 일관해졌다. **다음 릴리즈 노트에 의미 변경을 명시한다.**
- **MINOR-2 수용**: J-11 기각 논거 (3)의 사실 오류 — §1 에 정정 반영, 위키 정본도 동일 정정.

## 9. Tracking

- 정본: 위키 `SAGE - 장수 브랜치 다중 사이클 결속·선언 risk 설계` J-10 · J-11(기각 기록)
- 선행: `sage-hook-runtime-io-contract`(J-8, `v0.9.78`)
