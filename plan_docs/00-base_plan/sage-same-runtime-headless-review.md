# [Base Plan] Phase 05 same-runtime headless 리뷰 결정론 실행

Cycle-Stem: `sage-same-runtime-headless-review`
Risk Level: L3
Status: PLANNED

## 1. Context

현재 `sage review`는 same-runtime 리뷰를 수행하라는 지침과 `REVIEWER_ACTUAL`만 출력하고 실제 새 프로세스를
실행하지 않는다. 따라서 clean-context 독립성이 caller의 행동에 의존하며 process/model/mode 증거가 없다.

## 2. Goal

- recommended opt-out 또는 policy off 경로에서 active host의 새 headless 프로세스를 직접 실행한다.
- Codex는 `codex exec`, Claude는 `claude -p`를 사용한다.
- required 정책의 local false 시도와 peer 미가용 상태는 BLOCK한다.
- 실제 process, host, model, mode를 Phase 05 입력으로 기록할 수 있게 출력한다.

## 3. Scope

- `sage review` packet 입력과 direct same-runtime invocation
- explicit active host 해석
- required/recommended/off reviewer resolution
- timeout, nonzero exit, parse failure의 fail-closed 처리
- 기존 `sage cross-check` parser/command 경계 재사용

Out of scope: 두 runtime 동시 실행, 자동 phase handoff, 장기 daemon/session 재사용.

## 4. Done Criteria

1. bare instruction-only 성공 경로가 제거된다.
2. same-runtime 리뷰 성공은 실제 headless process 출력이 있어야 한다.
3. required 완화/peer 미가용은 BLOCKED와 nonzero exit를 반환한다.
4. recommended local false는 active host headless review를 수행한다.
5. cross-model 경로와 same-runtime 경로가 동일 packet·timeout·파싱 안전성을 가진다.
6. 세 번의 독립 headless 리뷰를 완료한다.
