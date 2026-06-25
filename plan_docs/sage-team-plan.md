# /sage-team — 전체 PDCA 팀 오케스트레이션 (R-1, 9단계)

## 배경

4차 weatherapp 평가(vault `TECH - SAGE 프로젝트 4차 테스트(26.06.25)`)에서 드러난 핵심 결함:
PDCA 흐름이 **연결되지 않은 수동 단계**로 돌았고, sage-review 루프 + cross-model + verify-changes 가
host 재량으로 통째 건너뛰어졌다(단발 리뷰가 적대적 루프를 대체, `.sage/loop_audit.jsonl` 0). 06←05
게이트가 `APPROVED` 마커만 검사하기 때문(F-5).

`/sage-pdca-start` 는 사이클을 **열기**만 한다(게이트 + plan + 소유권맵). 그 이후 구현→QA→리뷰→완료는
전부 host 재량이다. chatforyou-dev-team 이 오케스트레이션 패턴(leader→implementer→qa→reviewer→완료)을
증명했지만 claude 전용이고 게이트 인식이 없다.

## 목표

CORE 부트스트랩 스킬 `/sage-team`(`$sage-team` codex)을 신설한다. `sage-pdca-start` 가 만든 소유권맵을
받아 사이클을 **완료까지 구동**하되, sage-review(루프+audit)와 verify-changes 를 **절차로 강제**해
건너뛸 수 없게 한다. 양 host(claude/codex) 적응, 재개 가능.

## 경계 (2층 불변식 준수)

- 오케스트레이션 = host 판단 → **스킬(host 층)** 에 둔다. SAGE 코어(LLM 0)에 넣지 않는다.
- SAGE 결정론 게이트는 불변: `pre-implementation-gate`, `verify-changes`, `sage review-loop` audit,
  06←05 report←approve.
- `/sage-team` 은 **새 게이트를 추가하지 않는다**(그건 9.5단계). 기존 결정론 기구가 실제로 호출되도록
  절차로 보장할 뿐.

## 전제조건 / 재개

- plan doc(00–02)이 존재해야 함(`sage-pdca-start` 산출). 없으면 → `/sage-pdca-start` 로 안내(조용히 저작 금지).
- 재개 가능. **단 "파일 존재 ≠ 완료"** — 존재만으로 단계를 done 으로 오판하지 않도록, 단일 사이클 식별 +
  단계별 증거 앵커로 첫 미완 단계를 판별한다(codex 설계 R1-P1):
  - **사이클 식별**: `sage-pdca-start` 가 정한 단일 feature/cycle stem(plan doc 파일명 = 사이클 키). 여러 사이클·
    stale 문서가 섞여도 이 키로만 매칭.
  - **03 완료** = 구현 파일 + **verify-changes 증거**(build/test 결과)가 03 에 기록됨.
  - **04 완료** = 갭 + 커버리지 컨텍스트가 04 에 존재.
  - **05 상태머신**(codex 설계 R2-P1 — "진행"과 "완료"를 한 앵커로 묶지 말 것. 06 진입은 오직 마지막 상태):
    - `05_started` = 05 문서에 `run_id` 기록 + loop_audit 에 그 run 이 **open(미close)** → 재개 = 05 루프 재진입(이어서).
    - `05_closed_nonapproved` = loop_audit run 이 **closed 인데 result ≠ APPROVED**(BLOCKED 등), 또는 05 문서 판정이
      REJECTED/BLOCKED → 재개 = rework(03 으로) 또는 BLOCKED 유지. **06 진입 금지.**
    - `05_approved`(= 05 완료) = 05 문서 `APPROVED` 마커 **AND** 매칭 `run_id` 의 **closed run + result APPROVED**
      (`loop_audit.integrity_issues` 통과: 고아 open·중복 없음). **오직 이 상태에서만 06 진입 허용.**
  - 위 앵커 중 첫 결손 단계부터 이어감. 앵커 없는 단순 파일 존재는 "미완"으로 본다(보수적).

## 절차

0. profile + plan doc + 소유권맵 읽기. `profile.components` + `team.core` 에서 활성 implementer/컴포넌트 해석.
1. **구현(03)**: 소유권대로 implementer 분배.
   - claude: 컴포넌트별 **병렬 subagent(Task)**, 파일 소유권 경계 엄수.
   - codex: **순차 위임**(병렬 subagent 모델 없음) — 동일 소유권 경계, 하나씩.
   - 각자 구현 파일 + 체크리스트 + **단위 테스트**를 03 에 기록.
2. **검증(결정론)**: host 오케스트레이터가 `profile.verification` 정책에 따라 `scripts/verify-changes.sh` 를
   호출(build/test/lint). **정책·게이트·결과 형식은 SAGE 소유**, 실행 트리거만 스킬이 맡는다(codex 설계 R1-P1:
   `pre-implementation-gate` 는 편집/phase 차단 hook 이지 verify 실행기가 아님 — 혼동 금지). 결과를 03 에 기록.
   red 면 진행 차단 — 빨간 상태로 리뷰 진입 금지.
3. **QA(04)**: qa 에이전트 호출 → 커버리지 평가 + 설계↔구현 갭을 04 에 기록. 판정 없음.
4. **리뷰(05)**: `/sage-review` **호출**(손으로 쓴 05 문서 금지). review_loop.enabled + L2/L3 면 적대적 루프가
   `.sage/loop_audit.jsonl` 기록 + cross-model reviewer 로 돈다. 스킬은 반드시 sage-review 로 위임하며
   자유형식 리뷰로 대체하지 않는다.
5. **완료(06)**: 05 가 APPROVED 기록한 뒤에만 leader 가 06 작성(기존 06←05 게이트가 결정론 강제).

## F-5 대응 위치 — SOFT-ENFORCED (절차적, F-5 미종결)

스킬이 단계 2(verify)와 4(sage-review 루프+audit)를 절차상 필수로 만든다. **그러나 이것은 F-5 를 닫지
않는다**(codex 설계 R1-P0): `/sage-team` 을 **따를 때만** 건너뛸 수 없을 뿐, host 가 `/sage-team` 을
아예 안 쓰고 05 문서를 손으로 써 `APPROVED` 만 박으면 06←05 게이트는 여전히 통과한다. 따라서:

- `/sage-team` 의 강제는 **SOFT-ENFORCED** 로 표기한다("phase 연결·오케스트레이션 하드닝"이지 "건너뛰기
  불가능"이 아님). 스킬은 이 한계를 명시적으로 surface 한다.
- **진짜 결정론 강제**(06←05 가 `.sage/loop_audit.jsonl` run 일관성 + 테스트 증거도 검사)는 **9.5단계** 별도.
  `/sage-team` 은 그 게이트의 의존 대상(loop_audit·verify 증거)을 *생성*하는 역할 — 9.5 와 상보적.

## 호스트 패리티

- claude: Task subagent(병렬 구현) → qa → `/sage-review`.
- codex: 네이티브 순차 위임; 병렬 불가 시 implementer 순차 실행; reviewer 는 sage doctor 가 cross_model/
  clean-context 해석. 우아하게 degrade, 해석된 모드 명시.
- **review 루프 병렬성도 degrade 대상**(codex 설계 R1-P2): review-protocol 의 FIND 는 lens 병렬/발산을
  가정하지만 이는 품질/성능 사안이지 거버넌스 불변식이 아니다. codex 순차 degrade 는 **동일 논리 단계·산출물·
  audit 를 보존할 때만** 허용하고 "sequentialized execution, semantics preserved" 로 명시 표기한다.
  (순차화가 ownership 경계·리뷰 독립성·거버넌스 의미를 바꾸면 불가 — throughput 만 달라야 함.)

## 산출물

- `templates/core/skills/sage-team.md` (중립 spec)
- `templates/core/framework/.claude/skills/sage-team/SKILL.md` (렌더)
- `install.py`: `_CORE_SKILLS` 에 `sage-team` 추가
- write-guard `.sh`/`.md` + `cases.tsv`: sage-team 면제(claude) + `.codex` block 케이스
- docs: AGENT_GUIDE/CLAUDE/CODEX/README 인벤토리
- tests: install(양 host 배포), write-guard 케이스

## codex 설계 리뷰 질문

1. 경계가 맞나 — 오케스트레이션을 host 층 CORE 스킬에 두고 SAGE 코어엔 안 넣는 게 2층 불변식에 맞는가?
2. 재개 판별 — phase 문서 존재 + loop_audit 로 충분한가, 취약한가?
3. 단계 4 강제 — host 가 sage-review 를 건너뛰려 할 때 절차적 강제로 충분한가, 아니면 9.5 게이트 전까지는
   한계가 있나(있다면 그 한계를 스킬이 어떻게 표시해야 하나)?
4. codex 병렬 분배 — 순차 degrade 가 수용 가능한가?
5. 범위 — F-5 절차 강제를 여기 묶는 게 과한가, `/sage-team` 을 순수 오케스트레이션으로 두고 강제는 9.5 로 미뤄야 하나?
